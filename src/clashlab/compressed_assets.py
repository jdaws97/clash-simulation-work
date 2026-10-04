"""Read-only, bounded Windows emulator scan for complete compressed logic tables.

The scan requires a prior process manifest from inspect_game_memory.ps1 and
verifies executable and creation time before reading. It does not enable debug
privileges, modify the process, inject code, or save unrelated memory windows.
"""

import argparse
from collections import Counter
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

from .asset_decode import AssetDecodeError, inspect_asset, MAX_DICTIONARY, MAX_OUTPUT


EXPECTED_EXECUTABLE = r"C:\Program Files\Google\Play Games\current\emulator\crosvm.exe"
SIGNATURE = b"\x5d\x00\x00"
CHUNK_BYTES = 1024 * 1024
PROBE_BYTES = 256 * 1024
KNOWN_NAMES = {"Barbarian", "Archer", "RootRider", "Thrower", "Dragon", "Balloon"}


class MemoryBasicInformation(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


class WindowsMemoryReader:
    def __init__(self, process_id, expected_start):
        if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise RuntimeError("Run with 64-bit Windows Python")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        self.kernel.VirtualQueryEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.POINTER(MemoryBasicInformation),
            ctypes.c_size_t,
        ]
        self.kernel.VirtualQueryEx.restype = ctypes.c_size_t
        self.kernel.ReadProcessMemory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.handle = self.kernel.OpenProcess(0x0410, False, process_id)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            path = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(path))
            if not self.kernel.QueryFullProcessImageNameW(
                self.handle, 0, path, ctypes.byref(size)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if path.value.casefold() != EXPECTED_EXECUTABLE.casefold():
                raise RuntimeError("Process is not the expected emulator")
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            if not self.kernel.GetProcessTimes(
                self.handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
            start = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(
                microseconds=ticks // 10
            )
            if start != datetime.fromisoformat(expected_start.replace("Z", "+00:00")):
                raise RuntimeError(
                    "Process creation time changed; refresh the manifest"
                )
        except Exception:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def regions(self):
        address = 0
        while address < 0x7FFFFFFFFFFF:
            info = MemoryBasicInformation()
            count = self.kernel.VirtualQueryEx(
                self.handle, address, ctypes.byref(info), ctypes.sizeof(info)
            )
            if not count:
                break
            base = info.BaseAddress or 0
            end = base + info.RegionSize
            if end <= address:
                raise RuntimeError("Memory region query did not advance")
            readable = (info.Protect & 0xFF) in {2, 4, 8, 0x20, 0x40, 0x80}
            if (
                info.State == 0x1000
                and readable
                and not info.Protect & 0x100
                and info.Type != 0x1000000
            ):
                yield base, info.RegionSize
            address = end

    def read(self, address, size):
        buffer = ctypes.create_string_buffer(size)
        received = ctypes.c_size_t()
        success = self.kernel.ReadProcessMemory(
            self.handle, address, buffer, size, ctypes.byref(received)
        )
        if not success or received.value != size:
            return None
        return buffer.raw


def plausible_headers(data):
    """Yield bounded short-header candidates; a signature alone proves nothing."""
    offset = data.find(SIGNATURE)
    while offset != -1:
        if offset + 9 <= len(data):
            dictionary = int.from_bytes(data[offset + 1 : offset + 5], "little")
            declared = int.from_bytes(data[offset + 5 : offset + 9], "little")
            if 4096 <= dictionary <= MAX_DICTIONARY and (
                64 <= declared <= MAX_OUTPUT or declared == 0xFFFFFFFF
            ):
                yield offset
        offset = data.find(SIGNATURE, offset + 1)


def scan(reader, budget, maximum_candidates):
    report = {
        "status": "BOUNDED_COMPRESSED_ASSET_SEARCH",
        "bytes_attempted": 0,
        "bytes_read": 0,
        "probe_bytes_attempted": 0,
        "probe_bytes_read": 0,
        "failed_reads": 0,
        "candidate_headers": 0,
        "rejection_counts": Counter(),
        "tables": [],
        "budget_reached": False,
        "candidate_limit_reached": False,
        "regions_completed": 0,
        "process_writes": False,
        "raw_memory_saved": False,
        "verified_live_battle_state": False,
        "catalog_modified": False,
    }
    seen_addresses = set()
    seen_tables = set()
    regions = sorted(reader.regions(), key=lambda item: item[1], reverse=True)
    report["regions_selected"] = len(regions)
    for base, size in regions:
        tail = b""
        for offset in range(0, size, CHUNK_BYTES):
            remaining = (
                budget - report["bytes_attempted"] - report["probe_bytes_attempted"]
            )
            if remaining <= 0:
                report["budget_reached"] = True
                return report
            available = min(CHUNK_BYTES, size - offset)
            requested = min(available, remaining)
            chunk = reader.read(base + offset, requested)
            report["bytes_attempted"] += requested
            if chunk is None:
                report["failed_reads"] += 1
                tail = b""
                if requested < available:
                    report["budget_reached"] = True
                    return report
                continue
            report["bytes_read"] += len(chunk)
            joined = tail + chunk
            window_start = base + offset - len(tail)
            for index in plausible_headers(joined):
                address = window_start + index
                if address in seen_addresses:
                    continue
                if report["candidate_headers"] >= maximum_candidates:
                    report["candidate_limit_reached"] = True
                    return report
                seen_addresses.add(address)
                report["candidate_headers"] += 1
                remaining = (
                    budget - report["bytes_attempted"] - report["probe_bytes_attempted"]
                )
                probe_size = min(PROBE_BYTES, base + size - address, remaining // 2)
                if probe_size < 9:
                    report["budget_reached"] = True
                    return report
                first = reader.read(address, probe_size)
                second = reader.read(address, probe_size)
                report["probe_bytes_attempted"] += probe_size * 2
                report["probe_bytes_read"] += sum(len(x) for x in (first, second) if x)
                if first is None or second is None:
                    report["rejection_counts"]["probe_read_failed"] += 1
                    continue
                try:
                    result = inspect_asset(first, "supercell-lzma", allow_trailing=True)
                except AssetDecodeError as error:
                    reason = str(error).split(":", 1)[0]
                    report["rejection_counts"][reason] += 1
                    continue
                consumed = result["encoded_bytes_consumed"]
                if first[:consumed] != second[:consumed]:
                    report["rejection_counts"]["asset_changed_between_reads"] += 1
                    continue
                names = {row["entity_name"] for row in result["table"]["rows"]}
                if not names.intersection(KNOWN_NAMES):
                    report["rejection_counts"]["no_known_clash_troop_name"] += 1
                    continue
                digest = result["decoded_sha256"]
                if digest not in seen_tables:
                    seen_tables.add(digest)
                    result["host_address"] = hex(address)
                    result["stable_encoded_read"] = True
                    report["tables"].append(result)
            tail = joined[-8:]
            if requested < available:
                report["budget_reached"] = True
                return report
        report["regions_completed"] += 1
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scan_manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--maximum-mib", type=int, default=4096)
    parser.add_argument("--maximum-candidates", type=int, default=256)
    args = parser.parse_args()
    if not 1 <= args.maximum_mib <= 4096 or not 1 <= args.maximum_candidates <= 1024:
        parser.error("Scan limits are outside supported bounds")
    if args.output.exists():
        parser.error("Use a new output path to preserve prior evidence")
    manifest = json.loads(args.scan_manifest.read_text(encoding="utf-8-sig"))
    entries = [
        item for item in manifest["processes"] if item["process_id"] == args.process_id
    ]
    if len(entries) != 1:
        parser.error("The manifest must contain exactly one matching process")
    entry = entries[0]
    started = time.monotonic()
    reader = WindowsMemoryReader(args.process_id, entry["process_start_time_utc"])
    try:
        report = scan(reader, args.maximum_mib * CHUNK_BYTES, args.maximum_candidates)
    finally:
        reader.close()
    report.update(
        process_id=args.process_id,
        process_start_time_utc=entry["process_start_time_utc"],
        inspected_at_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=round(time.monotonic() - started, 3),
        maximum_scan_mib=args.maximum_mib,
        maximum_probe_bytes=PROBE_BYTES,
        limitations=[
            "Only short LZMA signatures beginning 5d0000 are searched",
            "Contiguous host reads do not reconstruct scattered guest virtual pages",
            "No match does not prove absence of compressed or decoded game assets",
            "A decoded asset still needs active version and semantic validation",
        ],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "tables"}, indent=2
        )
    )
    print(f"Decoded typed tables: {len(report['tables'])}")


if __name__ == "__main__":
    main()
