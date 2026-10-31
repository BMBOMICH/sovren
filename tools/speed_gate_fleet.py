#!/usr/bin/env python3
"""Track 0.1 fleet-wide cold speed gate.

Measures every shipped driver binary under compilers/ on canonical corpus
sizes, cold discipline: fresh process per run, whole-run wall clock, best +
median recorded, no warm-ups counted. Any driver failing a corpus is recorded
as FAIL (never skipped, never imputed). Output: CSV + MD under work/baselines/.
"""
from __future__ import annotations
import csv, os, platform, statistics, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work" / "baselines"
OUT.mkdir(parents=True, exist_ok=True)
STAMP = "20261025"

CORPUS = [
    ("hello", ROOT / "tests/hello.sov"),
    ("repl", ROOT / "tests/../repl.sov"),
    ("kacpi", ROOT / "tests/kacpi_test.sov"),
]
RUNS = {"hello": 7, "repl": 5, "kacpi": 5}

def time_compile(drv: Path, src: Path, runs: int, outname: str):
    out = Path("/tmp") / f"gate.{outname}.out"
    vals = []
    for _ in range(runs):
        if out.exists(): out.unlink()
        t = time.perf_counter()
        r = subprocess.run([str(drv), str(src), "-o", str(out)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dt = time.perf_counter() - t
        if r.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            return None
        vals.append(dt)
    return min(vals), statistics.median(vals)

def host_info():
    cpu = "unknown"
    try:
        with open("/proc/cpuinfo") as f:
            for ln in f:
                if ln.startswith("model name"):
                    cpu = ln.split(":", 1)[1].strip(); break
    except OSError:
        pass
    return f"{cpu}; {platform.machine()}; kernel {platform.release()}"

def main():
    drivers = sorted(p for p in (ROOT / "compilers").rglob("compiler") if p.is_file())
    rows = []
    for i, drv in enumerate(drivers, 1):
        rel = str(drv.relative_to(ROOT))
        rec = {"driver": rel}
        for name, src in CORPUS:
            res = time_compile(drv, src, RUNS[name], f"{i}.{name}")
            if res is None:
                rec[name] = "FAIL"
            else:
                best, med = res
                size = src.stat().st_size
                rec[name] = f"{best*1000:.3f}/{med*1000:.3f}/{size/best/1_000_000:.3f}"
        rows.append(rec)
        sys.stdout.write(f"\r[{i:3d}/155] {rel:60s} " +
                         " ".join(f"{k}:{rec[k]}" for k in ("hello","repl","kacpi")))
        sys.stdout.flush()
    print()
    csvp = OUT / f"fleet_cold_{STAMP}.csv"
    with open(csvp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["driver", "hello", "repl", "kacpi"])
        w.writeheader(); w.writerows(rows)
    ok = [r for r in rows if r["hello"] != "FAIL"]
    fast = sorted(ok, key=lambda r: float(r["hello"].split("/")[0]))[:8]
    mdp = OUT / f"fleet_cold_{STAMP}.md"
    with open(mdp, "w") as f:
        f.write(f"# Track 0.1 cold baseline ({STAMP})\n\n")
        f.write(f"Host: {host_info()}\n\n")
        f.write("Per cell: `best_ms/median_ms/MB/s` on each corpus; FAIL = driver could not "
                "compile it cold. Runs: hello x7, repl x5, kacpi x5. Corpus on disk: "
                f"{', '.join(f'{n}={s.stat().st_size}B' for n, s in CORPUS)}\n\n")
        f.write(f"Drivers measured: {len(rows)}; hello-compilable: {len(ok)}; "
                f"repl-compilable: {sum(1 for r in rows if r['repl']!='FAIL')}; "
                f"kacpi-compilable: {sum(1 for r in rows if r['kacpi']!='FAIL')}\n\n")
        f.write("## Fastest 8 on hello.sov\n\n| driver | hello |\n|---|---|\n")
        for r in fast[:8]:
            f.write(f"| {r['driver']} | {r['hello']} |\n")
        f.write(f"\nFull per-cell table: fleet_cold_{STAMP}.csv (columns "
                "driver, hello, repl, kacpi).\n\n")
        f.write("Reference — sa (as of Track 0.0 re-measure intended): 82 MB/s @143 KB, "
                "119 @425 KB, 306 @695 KB, 470-820 @4.2 MB; linux gate self-compile "
                "today: 210 ms / ~3.1 MB/s @660 KB.\n")
    print(f"\nwrote {csvp} and {mdp}")

if __name__ == "__main__":
    main()
