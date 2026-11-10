#!/usr/bin/env python3
"""Classify profile functions: twin-planted blobs vs small interpreted code.

A kept-name native blob occupies a large code range at the function's map
offset; interpreted functions are small. Joins map sizes with sampler counts.
"""
import re
import sys

MAP = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fn.s12.map.clean"
PROF = sys.argv[2] if len(sys.argv) > 2 else "/tmp/prof_self.txt"

entries = []
for line in open(MAP):
    t = line.split()
    if len(t) == 2:
        try:
            entries.append((t[0], int(t[1])))
        except ValueError:
            pass
entries.sort(key=lambda e: e[1])
sizes = {}
for i, (nm, off) in enumerate(entries):
    nxt = entries[i + 1][1] if i + 1 < len(entries) else off
    sizes[nm] = nxt - off

counts = {}
mode = 0
for line in open(PROF):
    if line.startswith("# top call sites"):
        mode = 1
        continue
    m = re.match(r"^\s*(\d+)\s+\d+\.\d+%\s+(\S+)$", line)
    if m and mode == 0:
        counts[m.group(2)] = int(m.group(1))

total = sum(counts.values())
print(f"{'name':32s} {'count':>7s} {'pct':>6s} {'bytes':>7s}  class")
rows = sorted(counts.items(), key=lambda kv: -kv[1])
for nm, n in rows:
    sz = sizes.get(nm, 0)
    if sz >= 2500:
        cls = "BLOB"
    elif sz >= 700:
        cls = "big"
    else:
        cls = "interp"
    print(f"{nm:32s} {n:7d} {100.0*n/total:6.2f}% {sz:7d}  {cls}")
