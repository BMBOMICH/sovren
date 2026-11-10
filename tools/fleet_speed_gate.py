#!/usr/bin/env python3
# Track 0.1 fleet mode: per-driver cold compile speed, fresh process, whole-run
# wall clock, host+size recorded with EVERY number.  Non-building lineage rows
# are recorded lineage-pending (red), never skipped silently.
import subprocess, time, statistics, glob, os, json, platform, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'tests/conformance/corpus/c01_int_arith.sov')
SIZE = os.path.getsize(SRC)
drvs = sorted(set(glob.glob(ROOT+'/compilers/*/compiler.sov') + glob.glob(ROOT+'/compilers/*/*/compiler.sov')))
RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
rows = []
for d in drvs:
    rel = os.path.relpath(d, ROOT)
    flat = f"/tmp/fsg_{rel.replace('/', '_')}"
    rc = subprocess.run([ROOT+'/compilers/linux/compiler', d, '-o', '/tmp/fsg_drv.bin'],
                        capture_output=True, timeout=300)
    ok = os.path.exists('/tmp/fsg_drv.bin') and os.path.getsize('/tmp/fsg_drv.bin') > 1000
    if not ok:
        rows.append({"driver": rel, "status": "lineage-pending",
                     "err": (rc.stderr or rc.stdout).decode('utf-8', 'replace').split('Error:')[-1].strip()[:60]})
        print(f"{rel:60s} lineage-pending")
        continue
    blob = os.path.getsize('/tmp/fsg_drv.bin'); os.unlink('/tmp/fsg_drv.bin')
    times = []
    for i in range(RUNS):
        t = time.perf_counter()
        r = subprocess.run([ROOT+'/compilers/linux/compiler', d, '-o', '/tmp/fsg_o.bin'],
                           capture_output=True, timeout=300)
        dt = time.perf_counter() - t
        assert r.returncode == 0, rel
        times.append(dt)
    best, med = min(times)*1000, statistics.median(times)*1000
    mbps = os.path.getsize(d) / (best/1000) / 1_000_000
    rows.append({"driver": rel, "status": "builds", "source_bytes": os.path.getsize(d),
                 "compiled_bytes": blob, "best_ms": best, "median_ms": med, "MBperS": mbps})
    print(f"{rel:60s} {best:9.1f} ms  med {med:9.1f}  {mbps:8.3f} MB/s")
out = {"at": __import__('datetime').datetime.now().isoformat(timespec='seconds'),
       "host": platform.uname()._asdict(), "runs_per_driver": RUNS, "rows": rows}
os.makedirs(ROOT+'/tests/gates', exist_ok=True)
json.dump(out, open(ROOT+'/tests/gates/fleet_speed_gate.json', 'w'), indent=1)
print("->", "tests/gates/fleet_speed_gate.json", f"({sum(1 for r in rows if r['status']=='builds')}/{len(rows)} build)")
