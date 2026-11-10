#!/usr/bin/env python3
"""Process-level compiler/assembler speed gate.

The number this reports is **cold translation**: every measured run compiles
from scratch, in a fresh process, with no build cache anywhere in the tree.
The build cache and the `--no-cache` flag that used to guard it were removed;
`--no-cache` is now an unknown flag and the compiler rejects it, so this gate
cannot silently measure a cache hit.

`--require-ratio` fails CI until cold expanded-source throughput reaches a
chosen fraction of sa's.
"""
from __future__ import annotations
import argparse, os, statistics, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SA_ROOT = ROOT.parent / "sovren-assembler"


def run(cmd: list[str], runs: int, cwd=ROOT):
    vals = []
    for _ in range(runs):
        t = time.perf_counter()
        r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        dt = time.perf_counter() - t
        if r.returncode:
            raise SystemExit(f"command failed ({r.returncode}): {' '.join(cmd)}")
        vals.append(dt)
    return min(vals), statistics.median(vals)


def run_interleaved(cmd_a, cmd_b, runs: int, cwd=ROOT):
    """Track 0.3: strict A/B interleave with order rotation.

    Each round runs both cells back to back; the ORDER alternates every round
    (r%2) so a warming or drift artifact cannot systematically hit the same
    cell first.  Returns (a_best, a_med, b_best, b_med, all_a, all_b).
    """
    import random
    va, vb = [], []
    for r in range(runs):
        cells = [cmd_a, cmd_b] if r % 2 == 0 else [cmd_b, cmd_a]
        for cmd in cells:
            t = time.perf_counter()
            r2 = subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"})
            dt = time.perf_counter() - t
            if r2.returncode:
                raise SystemExit(f"command failed ({r2.returncode}): {' '.join(cmd)}")
            (va if cmd is cmd_a else vb).append(dt)
    return (min(va), statistics.median(va), min(vb), statistics.median(vb), va, vb)


def show(name: str, size: int, timing) -> float:
    best, med = timing
    rate = size / best / 1_000_000
    print(f"{name:26s} {size:9d} B  best {best*1000:10.3f} ms  "
          f"median {med*1000:10.3f} ms  {rate:10.3f} MB/s")
    return rate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=12)
    ap.add_argument('--source', default='tests/x86ins.sov')  # tests/run.sov itself is lineage-broken (era %3/%4 splice leakage); use a green corpus source
    ap.add_argument('--compiler', default='compilers/linux/compiler')
    ap.add_argument('--sa-source', default='bench6.sa.asm')
    ap.add_argument('--require-ratio', type=float, default=0.0,
                    help='fail unless cold expanded-source Sovren MB/s >= this fraction of sa MB/s')
    a = ap.parse_args()

    src = ROOT / a.source
    compiler = ROOT / a.compiler
    sa = SA_ROOT / 'sa'
    sys.path.insert(0, str(SA_ROOT / 't'))
    import srcs  # type: ignore
    sa_src = Path(srcs.ensure(a.sa_source))

    flat = Path('/tmp/sovren-speed.flat')
    subprocess.run([str(compiler), str(src), '--flat', '-o', str(flat)],
                   cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True)
    # Track 0.3 interleaved A/B with order rotation (R>=12 default)
    sa_best, sa_med, sv_best, sv_med, va, vb = run_interleaved(
        [str(compiler), str(src), '-o', '/tmp/sovren-speed.bin'],
        [str(sa), str(sa_src), '/tmp/sovren-speed.sa.bin'], a.runs)
    sa_rate = sa_src.stat().st_size / sa_best / 1_000_000
    print(f"{'sa ' + a.sa_source:26s} {sa_src.stat().st_size:9d} B  best {sa_best*1000:10.3f} ms  "
          f"median {sa_med*1000:10.3f} ms  {sa_rate:10.3f} MB/s")
    in_rate = src.stat().st_size / sv_best / 1_000_000
    exp_rate = flat.stat().st_size / sv_best / 1_000_000
    print(f"{'Sovren cold, input bytes':26s} {src.stat().st_size:9d} B  best {sv_best*1000:10.3f} ms  "
          f"median {sv_med*1000:10.3f} ms  {in_rate:10.3f} MB/s")
    print(f"{'Sovren cold, expanded bytes':26s} {flat.stat().st_size:9d} B  best {sv_best*1000:10.3f} ms  "
          f"median {sv_med*1000:10.3f} ms  {exp_rate:10.3f} MB/s")
    # persist baseline with host+size (Track 0.1)
    import json, platform
    cold = (sv_best, sv_med)
    rec = {
        "at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "host": {"uname": platform.uname()._asdict(), "cpu": platform.processor()},
        "runs": a.runs,
        "sa": {"source": a.sa_source, "bytes": sa_src.stat().st_size,
               "best_ms": sa_best*1000, "median_ms": sa_med*1000, "MBperS": sa_rate},
        "sovren": {"source": str(src), "bytes_in": src.stat().st_size,
                   "bytes_expanded": flat.stat().st_size,
                   "best_ms": sv_best*1000, "median_ms": sv_med*1000,
                   "MBperS_in": in_rate, "MBperS_expanded": exp_rate},
        "ratio_expanded": exp_rate / sa_rate,
    }
    import os
    os.makedirs(ROOT / "work" / "speed", exist_ok=True)
    hist = ROOT / "work" / "speed" / "speed_gate.jsonl"
    with open(hist, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(f"recorded -> {hist}")

    ratio = exp_rate / sa_rate
    print(f"cold expanded-throughput ratio: {ratio:.6f}x sa")
    print(f"  input  ratio: {in_rate/sa_rate:.6f}x sa")
    if a.require_ratio and ratio < a.require_ratio:
        raise SystemExit(f"speed gate failed: {ratio:.6f} < {a.require_ratio:.6f}")


if __name__ == '__main__':
    main()
