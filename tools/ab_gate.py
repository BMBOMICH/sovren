#!/usr/bin/env python3
"""Track 0.3 purge-clean interleaved A/B gate.
ab_gate.py A B [--src S] [--runs R (default 12)] [--flags "..." ]
Fresh process per run, whole-run wall clock, order-rotated, no warm-ups, no
persisted state anywhere (the tree has none to wipe). Reports min/median per
side and delta %; >0 means B is slower."""
import argparse, os, statistics, subprocess, sys, time
ap = argparse.ArgumentParser()
ap.add_argument("a"); ap.add_argument("b")
ap.add_argument("--src", default="compilers/linux/compiler.sov")
ap.add_argument("--runs", type=int, default=12)
ap.add_argument("--flags", default="")
a = ap.parse_args()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for exe in (a.a, a.b):
    os.chmod(exe, 0o755)
res = {"A": [], "B": []}
extra = a.flags.split() if a.flags.strip() else []
for i in range(a.runs):
    for tag, exe in (("A", a.a), ("B", a.b)) if i % 2 == 0 else (("B", a.b), ("A", a.a)):
        try: os.unlink("/tmp/ab_gate.out")
        except FileNotFoundError: pass
        t = time.perf_counter()
        p = subprocess.run([exe, a.src, "-o", "/tmp/ab_gate.out"] + extra, cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)
        assert p.returncode == 0, f"{tag} compile failed"
        res[tag].append((time.perf_counter() - t) * 1000)
A, B = res["A"], res["B"]
print(f"A {' '.join(f'{x:7.1f}' for x in A)}")
print(f"B {' '.join(f'{x:7.1f}' for x in B)}")
print(f"A min {min(A):7.2f} med {statistics.median(A):7.2f} ms")
print(f"B min {min(B):7.2f} med {statistics.median(B):7.2f} ms")
d_min = 100 * (min(B) - min(A)) / min(A); d_med = 100 * (statistics.median(B) - statistics.median(A)) / statistics.median(A)
print(f"B vs A: min {d_min:+.2f}%  med {d_med:+.2f}%")
sys.exit(0 if d_med <= 0.0 else 1)
