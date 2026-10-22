"""First line where two engine traces differ (rust_export.py trace vs the
Rust engine's trace). Floats written as 16 hex digits of their IEEE bits are
decoded for display.

Usage: python tools/baselab/trace_diff.py output/parity/trace-py-1-0.txt output/parity/trace-rs-1-0.txt
"""

import re
import struct
import sys

HEX = re.compile(r"\b[0-9a-f]{16}\b")


def show(line):
    return HEX.sub(lambda m: repr(struct.unpack("<d", struct.pack("<Q", int(m.group(0), 16)))[0]), line)


def main():
    a = open(sys.argv[1]).read().split("\n")
    b = open(sys.argv[2]).read().split("\n")
    t = None
    for i, (x, y) in enumerate(zip(a, b)):
        if x.startswith("T "):
            t = show(x)
        if x != y:
            print("first difference at line", i, "after", t)
            print("  py:", show(x))
            print("  rs:", show(y))
            for k in range(max(0, i - 6), min(max(len(a), len(b)), i + 6)):
                print("   ", show(a[k]) if k < len(a) else "", "|", show(b[k]) if k < len(b) else "")
            return 1
    if len(a) != len(b):
        print("one trace is longer:", len(a), len(b))
        return 1
    print("identical:", len(a), "lines;", show(a[-2]) if len(a) > 1 else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
