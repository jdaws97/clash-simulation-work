"""Read layout-key windows from an existing, process-bound read-only scan.

No process writes, debugger attachment, privilege changes, raw dumps, or network
operations are performed. Only whitelisted numeric layout fields are exported.
"""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from clashlab.layout_records import LAYOUT_KEYS, inspect_layout_value


EXPECTED_IMAGE = r"C:\Program Files\Google\Play Games\current\emulator\crosvm.exe"
MAXIMUM_WINDOW_BYTES = 262144


class ReadOnlyProcess:
    def __init__(self, record):
        if os.name != "nt":
            raise RuntimeError("Live process reads require Windows")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.api.ReadProcessMemory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.api.ReadProcessMemory.restype = wintypes.BOOL
        self.api.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.api.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.api.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            *[ctypes.POINTER(wintypes.FILETIME)] * 4,
        ]
        self.api.GetProcessTimes.restype = wintypes.BOOL
        self.handle = self.api.OpenProcess(0x0410, False, record["process_id"])
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            self._verify(record)
        except BaseException:
            self.close()
            raise

    def _verify(self, record):
        capacity = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(capacity.value)
        if not self.api.QueryFullProcessImageNameW(
            self.handle, 0, image, ctypes.byref(capacity)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if os.path.normcase(image.value) != os.path.normcase(EXPECTED_IMAGE):
            raise RuntimeError("The process is not the expected game emulator")
        times = [wintypes.FILETIME() for _ in range(4)]
        if not self.api.GetProcessTimes(self.handle, *map(ctypes.byref, times)):
            raise ctypes.WinError(ctypes.get_last_error())
        ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        created = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(
            microseconds=ticks // 10
        )
        timestamp = record["process_start_time_utc"].replace("Z", "+00:00")
        timestamp = re.sub(r"(\.\d{6})\d+(?=[+-])", r"\1", timestamp)
        expected = datetime.fromisoformat(timestamp)
        if abs((created - expected).total_seconds()) > 0.000001:
            raise RuntimeError("The process ID has been reused since the scan")

    def read(self, address, maximum_bytes=MAXIMUM_WINDOW_BYTES):
        if not 0 < maximum_bytes <= 2**20:
            raise ValueError("Read windows must be bounded to one MiB")
        chunks = []
        total = 0
        while total < maximum_bytes:
            requested = min(4096 - ((address + total) % 4096), maximum_bytes - total)
            buffer = ctypes.create_string_buffer(requested)
            count = ctypes.c_size_t()
            succeeded = self.api.ReadProcessMemory(
                self.handle, address + total, buffer, requested, ctypes.byref(count)
            )
            chunks.append(buffer.raw[: count.value])
            total += count.value
            if not succeeded or count.value != requested:
                break
        return b"".join(chunks)

    def regions(self):
        class MemoryInformation(ctypes.Structure):
            _fields_ = [
                ("base", ctypes.c_void_p),
                ("allocation_base", ctypes.c_void_p),
                ("allocation_protect", wintypes.DWORD),
                ("partition_id", wintypes.WORD),
                ("region_size", ctypes.c_size_t),
                ("state", wintypes.DWORD),
                ("protect", wintypes.DWORD),
                ("type", wintypes.DWORD),
            ]

        self.api.VirtualQueryEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.POINTER(MemoryInformation),
            ctypes.c_size_t,
        ]
        self.api.VirtualQueryEx.restype = ctypes.c_size_t
        address = 0
        while address < 0x0000800000000000:
            info = MemoryInformation()
            if not self.api.VirtualQueryEx(
                self.handle, address, ctypes.byref(info), ctypes.sizeof(info)
            ):
                break
            following = (info.base or 0) + info.region_size
            if following <= address:
                raise RuntimeError("Memory-region query did not advance")
            readable = (
                info.state == 0x1000
                and not info.protect & 0x100
                and (info.protect & 0xFF) in {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}
                and info.type != 0x1000000
            )
            if readable:
                yield {"address": info.base, "size": info.region_size}
            address = following

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scan", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    scan = json.loads(arguments.scan.read_text(encoding="utf-8-sig"))
    findings = []
    for record in scan["processes"]:
        matches = [
            match
            for match in record["matches"]
            if match["Needle"].strip('"') in LAYOUT_KEYS
        ]
        if not matches:
            continue
        process = ReadOnlyProcess(record)
        try:
            for match in matches:
                key = match["Needle"].strip('"')
                data = process.read(int(match["Address"], 16))
                finding = inspect_layout_value(data, key)
                finding.update(
                    process_id=record["process_id"],
                    anchor=match["Address"],
                    bytes_read=len(data),
                )
                findings.append(finding)
        finally:
            process.close()
    output = {
        "inspected_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_scan": str(arguments.scan.resolve()),
        "process_writes": False,
        "raw_memory_saved": False,
        "findings": findings,
        "simulator_data_changed": False,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "windows": len(findings),
                "layout_candidates": sum(
                    item["status"] == "UNVERIFIED_LAYOUT_CANDIDATE" for item in findings
                ),
                "statuses": [item["status"] for item in findings],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
