#!/usr/bin/env python3
"""Aggregate multiple sampler.py runs into one statistically solid profile.

Usage: sample_n.py <runs> <binary> <map> <args...>
Each run re-executes the child fresh; counts and callee<-caller pairs are
summed across runs. Rate/deadline come from SAMPLER_HZ / SAMPLER_MAX_S.
"""
import os
import re
import subprocess
import sys
from collections import defaultdict


def one_run(binary, mapfile, args):
    env = dict(os.environ)
    p = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "sampler.py"),
         binary, mapfile, *args],
        capture_output=True, text=True, env=env, timeout=300)
    counts = defaultdict(int)
    pairs = defaultdict(int)
    total = 0
    mode = 0
    for line in p.stdout.splitlines() + p.stderr.splitlines():
        m = re.match(r"^# (\d+) samples in ", line)
        if m:
            total += int(m.group(1))
            continue
        if line.startswith("# top call sites"):
            mode = 1
            continue
        m = re.match(r"^\s*(\d+)\s+\d+\.\d+%\s+(\S.*)$", line)
        if m:
            n = int(m.group(1))
            rest = m.group(2).strip()
            if mode == 0:
                counts[rest] += n
            else:
                cal, _, cur = rest.partition(" <- ")
                pairs[(cal, cur)] += n
    return total, counts, pairs


def main():
    runs = int(sys.argv[1])
    binary, mapfile, args = sys.argv[2], sys.argv[3], sys.argv[4:]
    tot, counts, pairs = 0, defaultdict(int), defaultdict(int)
    for i in range(runs):
        t, c, pr = one_run(binary, mapfile, args)
        tot += t
        for k, v in c.items():
            counts[k] += v
        for k, v in pr.items():
            pairs[k] += v
        print(f"# run {i+1}/{runs}: +{t} samples", file=sys.stderr)
    self_time = sum(counts.values())
    print(f"# {tot} samples over {runs} runs ({self_time} attributed)")
    for nm, n in sorted(counts.items(), key=lambda kv: -kv[1])[:40]:
        print(f"{n:8d} {100.0*n/max(self_time,1):6.2f}%  {nm}")
    print("\n# top call sites (callee <- caller)")
    for (cal, cur), n in sorted(pairs.items(), key=lambda kv: -kv[1])[:40]:
        print(f"{n:8d} {100.0*n/max(self_time,1):6.2f}%  {cal} <- {cur}")


if __name__ == "__main__":
    main()
