#!/usr/bin/env python3
"""build_census.py - try to build every compilers/**/compiler.sov with the
installed linux compiler; report per-target OK/FAIL/TIMEOUT with the first
error lines (captured output truncated - some failing drivers can produce
unbounded output, which must never reach disk raw)."""
import glob, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMP = os.path.join(ROOT, "compilers/linux/compiler")
TO = float(sys.argv[1]) if len(sys.argv) > 1 else 60
targets = sorted(glob.glob(ROOT + "/compilers/**/compiler.sov", recursive=True))
ok, bad = [], []
for t in targets:
    rel = os.path.relpath(os.path.dirname(t), ROOT + "/compilers")
    out = "/tmp/census_out.bin"
    if os.path.exists(out): os.unlink(out)
    t0 = time.perf_counter()
    try:
        with open("/home/user/census_one.log", "w+b") as lf:
            p = subprocess.run([COMP, t, "-o", out], cwd=ROOT, stdout=lf,
                               stderr=subprocess.STDOUT, timeout=TO)
            lf.seek(0)
            txt = lf.read(65536).decode(errors="replace")
        dt = time.perf_counter() - t0
        good = p.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0
        err = ""
        for ln in txt.splitlines():
            if ln.startswith("Error:"):
                err = ln[:100]; break
        (ok if good else bad).append((rel, dt, p.returncode, err))
    except subprocess.TimeoutExpired:
        bad.append((rel, TO, "TIMEOUT", ""))
    except OSError as e:
        bad.append((rel, 0, f"OSError{e.errno}", ""))
print(f"BUILD OK: {len(ok)}/{len(targets)}")
for rel, dt, rc, err in sorted(bad):
    print(f"  FAIL {rel:44s} rc={rc} {dt:5.1f}s {err}")
slow = sorted(ok, key=lambda r: -r[1])[:8]
print("slowest OK:")
for rel, dt, rc, err in slow:
    print(f"  {dt:6.1f}s {rel}")
