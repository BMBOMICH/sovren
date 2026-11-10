#!/usr/bin/env python3
"""Track 0.3 purge-clean interleaved A/B gate, with an optional placebo control.

ab_gate.py A B [--src S] [--runs R (default 21)] [--flags "..."] [--placebo P]

Fresh process per run, whole-run wall clock, order-rotated, no warm-ups, no
persisted state anywhere (the tree has none to wipe). Reports min/median per
side and delta %; >0 means B is slower.

--placebo P adds a third side: a certified source rebuilt with one layout-only
change (e.g. a single nop). Its delta defines the measurement noise band. A
result inside that band is NOT a real win (S28R law: the band is ~+-1%). Use
--require-outside-placebo to make such a result fail the gate (exit 2).

Host and source size are recorded with every number. Cross-language source-byte
rates are diagnostic only: report expanded/emitted bytes alongside them.
"""
import argparse, os, platform, statistics, subprocess, sys, time

ap = argparse.ArgumentParser()
ap.add_argument("a")
ap.add_argument("b")
ap.add_argument("--src", default="compilers/linux/compiler.sov")
ap.add_argument("--runs", type=int, default=21)
ap.add_argument("--flags", default="")
ap.add_argument("--placebo", default=None,
                help="layout-only variant binary; measures the noise band")
ap.add_argument("--require-outside-placebo", action="store_true",
                help="exit 2 when B's median delta lies inside the placebo band")
a = ap.parse_args()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sides = [("A", a.a), ("B", a.b)]
if a.placebo:
    sides.append(("P", a.placebo))
for _, exe in sides:
    os.chmod(exe if os.path.isabs(exe) else os.path.join(ROOT, exe), 0o755)

res = {tag: [] for tag, _ in sides}
extra = a.flags.split() if a.flags.strip() else []
for i in range(a.runs):
    rotated = sides[i % len(sides):] + sides[:i % len(sides)]
    for tag, exe in rotated:
        try:
            os.unlink("/tmp/ab_gate.out")
        except FileNotFoundError:
            pass
        t = time.perf_counter()
        p = subprocess.run([exe, a.src, "-o", "/tmp/ab_gate.out"] + extra, cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)
        assert p.returncode == 0, f"{tag} compile failed"
        res[tag].append((time.perf_counter() - t) * 1000)

src_bytes = os.path.getsize(os.path.join(ROOT, a.src)) if not os.path.isabs(a.src) else os.path.getsize(a.src)
print(f"host={platform.node()} machine={platform.machine()} src={a.src} "
      f"input_bytes={src_bytes} runs={a.runs} sides={''.join(t for t, _ in sides)}")
for tag, _ in sides:
    v = res[tag]
    print(f"{tag} {' '.join(f'{x:7.1f}' for x in v)}")
    print(f"{tag} min {min(v):7.2f} med {statistics.median(v):7.2f} ms")

A, B = res["A"], res["B"]
d_min = 100 * (min(B) - min(A)) / min(A)
d_med = 100 * (statistics.median(B) - statistics.median(A)) / statistics.median(A)
print(f"B vs A: min {d_min:+.2f}%  med {d_med:+.2f}%")

inside = False
if a.placebo:
    P = res["P"]
    p_min = 100 * (min(P) - min(A)) / min(A)
    p_med = 100 * (statistics.median(P) - statistics.median(A)) / statistics.median(A)
    lo, hi = min(0.0, p_min, p_med) - 0.5, max(0.0, p_min, p_med) + 0.5
    inside = lo <= d_med <= hi
    print(f"P (placebo) vs A: min {p_min:+.2f}%  med {p_med:+.2f}%  band=[{lo:+.2f}%, {hi:+.2f}%]")
    if inside:
        print("WARNING: B's result is INSIDE THE PLACEBO/LAYOUT-LOTTERY BAND - not a credible win")

if a.require_outside_placebo and inside:
    sys.exit(2)
sys.exit(0 if d_med <= 0.0 else 1)
