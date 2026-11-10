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
        # C.30/C.32: never silently skip. Every non-building driver MUST carry
        # the shipped .build-failed marker; record the marker text, the full
        # first error and the process return code as explicit evidence.
        marker = os.path.join(os.path.dirname(d), '.build-failed')
        mark = open(marker).read().strip()[:120] if os.path.isfile(marker) else None
        raw = (rc.stderr or rc.stdout).decode('utf-8', 'replace')
        first = next((l.strip() for l in raw.splitlines() if l.startswith('Error:')), '')
        rows.append({"driver": rel, "status": "lineage-pending",
                     "err": raw.split('Error:')[-1].strip()[:60],
                     "first_error": first[:120], "rc": rc.returncode,
                     "build_failed_marker": mark,
                     "classified": mark is not None})
        print(f"{rel:60s} lineage-pending (marker={'yes' if mark else 'NO'})")
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
builds = sum(1 for r in rows if r['status'] == 'builds')
pending = sum(1 for r in rows if r['status'] == 'lineage-pending')
unmarked = [r['driver'] for r in rows
            if r['status'] == 'lineage-pending' and not r.get('build_failed_marker')]
print("->", "tests/gates/fleet_speed_gate.json", f"({builds}/{len(rows)} build)")
print(f"fleet census: {len(drvs)} drivers discovered, {len(rows)} rows recorded, "
      f"{builds} build, {pending} lineage-pending, {len(unmarked)} UNMARKED")
assert len(rows) == len(drvs), 'driver skipped'
# A pending driver without the shipped marker is a harness/source regression,
# not an acceptable lineage-pending row.
if unmarked:
    print("UNMARKED lineage-pending (fail):", unmarked)
    sys.exit(1)
