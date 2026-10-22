"""First line where two engine traces (rust_spike.py trace / SPIKE_TRACE) differ.

Usage: python tools/baselab/trace_diff.py output/trace-py-0.txt output/trace-rs-0.txt
"""
import sys

a = open(sys.argv[1]).read().split("\n")
b = open(sys.argv[2]).read().split("\n")
t = None
for i, (x, y) in enumerate(zip(a, b)):
    if x.startswith("T "):
        t = x
    if x != y:
        print("first difference at line", i, t)
        print("  py:", x)
        print("  rs:", y)
        for k in range(max(0, i - 4), min(len(a), i + 4)):
            print("   ", a[k], "|", b[k] if k < len(b) else "")
        break
else:
    print("identical over", min(len(a), len(b)), "lines; lengths", len(a), len(b))
