#!/usr/bin/env python3
"""Fresh-process translation gate. Shipped SA is the target (it uses in-run reuse).
No compiler artifacts/intermediates are reused. OS page-cache state is uncontrolled.
Latency and byte throughput are distinct; tiny sources are never bulk-gated.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SA_ROOT = ROOT.parent / 'sovren-assembler'
if not SA_ROOT.exists():
    SA_ROOT = ROOT.parent / 'downloads' / 'sovren-assembler'

@dataclass(frozen=True)
class Command:
    argv: list[str]
    artifact: Path

@dataclass(frozen=True)
class Timing:
    samples_seconds: list[float]
    @property
    def best_seconds(self): return min(self.samples_seconds)
    @property
    def median_seconds(self): return statistics.median(self.samples_seconds)
    def record(self):
        return dict(samples_seconds=self.samples_seconds,
                    best_ms=self.best_seconds*1000, median_ms=self.median_seconds*1000)

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def checked(command: Command, cwd=ROOT, timeout=120):
    # Remove stale output before every invocation: failure cannot inherit success.
    command.artifact.unlink(missing_ok=True)
    start = time.perf_counter()
    result = subprocess.run(command.argv, cwd=cwd, capture_output=True, timeout=timeout,
                            env={**os.environ, 'LC_ALL':'C'})
    elapsed = time.perf_counter()-start
    if result.returncode or not command.artifact.is_file() or command.artifact.stat().st_size == 0:
        message = (result.stdout+result.stderr).decode(errors='replace')[-4000:]
        raise RuntimeError(f'command failed rc={result.returncode}: {command.argv!r}\n{message}')
    return elapsed

def run_interleaved(commands: dict[str, Command], runs: int, cwd=ROOT, runner=checked):
    if runs < 1: raise ValueError('runs must be positive')
    names=list(commands)
    if not names: raise ValueError('no commands')
    samples={name: [] for name in names}
    for round_number in range(runs):
        for name in names[round_number % len(names):]+names[:round_number % len(names)]:
            samples[name].append(runner(commands[name], cwd=cwd))
    return {name:Timing(values) for name,values in samples.items()}

def source_manifest():
    # Evidence only: hashes never select or reuse a translation artifact.
    paths=[ROOT/'runtime.sov', *sorted((ROOT/'compilers').rglob('*.sov')),
           *sorted((ROOT/'library').rglob('*.sov'))]
    return {str(p.relative_to(ROOT)):sha256(p) for p in paths if p.is_file()}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runs',type=int,default=21)
    ap.add_argument('--source',default='tests/x86ins.sov')
    ap.add_argument('--compiler',default='compilers/linux/compiler')
    ap.add_argument('--sa',default=str(SA_ROOT/'sa'))
    ap.add_argument('--sa-source',default='bench6.sa.asm')
    ap.add_argument('--flag',action='append',default=[])
    ap.add_argument('--output',default='work/p0/speed.json')
    ap.add_argument('--require-ratio',type=float,default=0)
    ap.add_argument('--bulk-min-bytes',type=int,default=100000)
    a=ap.parse_args()
    if a.runs<1: ap.error('--runs must be positive')
    src=(ROOT/a.source).resolve(); compiler=(ROOT/a.compiler).resolve(); sa=Path(a.sa).resolve()
    sap=Path(a.sa_source)
    if sap.is_file(): sa_src=sap.resolve()
    else:
        sys.path.insert(0,str(sa.parent/'t'))
        import srcs
        sa_src=Path(srcs.ensure(a.sa_source)).resolve()
    # Pin pre-run evidence, reject changes during measurement.
    before={str(p):sha256(p) for p in [compiler,sa,src,sa_src]}
    implementation=source_manifest()
    with tempfile.TemporaryDirectory(prefix='sovren-speed-') as directory:
        d=Path(directory); flat=d/'expanded.txt'
        checked(Command([str(compiler),str(src),*a.flag,'--flat','-o',str(flat)],flat))
        expanded=flat.stat().st_size; flat_hash=sha256(flat)
        commands={
            'sovren':Command([str(compiler),str(src),*a.flag,'-o',str(d/'sovren.bin')],d/'sovren.bin'),
            'sa':Command([str(sa),str(sa_src),str(d/'sa.bin')],d/'sa.bin')}
        timings=run_interleaved(commands,a.runs)
        artifacts={name:sha256(cmd.artifact) for name,cmd in commands.items()}
        emitted=(d/'sovren.bin').stat().st_size
    if before != {p:sha256(p) for p in before} or implementation != source_manifest():
        raise RuntimeError('inputs or implementation changed during measurement')
    sv_rate=expanded/timings['sovren'].median_seconds/1e6
    sv_input_rate=src.stat().st_size/timings['sovren'].median_seconds/1e6
    sa_rate=sa_src.stat().st_size/timings['sa'].median_seconds/1e6
    expansion=expanded/src.stat().st_size if src.stat().st_size else 0.0
    emission=emitted/src.stat().st_size if src.stat().st_size else 0.0
    bulk=expanded>=a.bulk_min_bytes and sa_src.stat().st_size>=a.bulk_min_bytes
    if a.require_ratio and not bulk:
        raise RuntimeError('tiny source: refusing a bulk MB/s parity gate; use matched latency workloads')
    record=dict(schema=2,host=platform.uname()._asdict(),runs=a.runs,
        policy=dict(fresh_process=True,compiler_artifact_reuse=False,os_pages_evicted=False,
                    target='shipped SA; in-process reuse is present',metric='cross-language byte throughput; not equivalent semantic work'),
        hashes=before,implementation_sources_sha256=implementation,expanded_sha256=flat_hash,
        source=str(src),sa_source=str(sa_src),flags=a.flag,bytes_input=src.stat().st_size,
        bytes_expanded=expanded,bytes_emitted=emitted,sa_bytes=sa_src.stat().st_size,
        expansion_factor=expansion,emission_factor=emission,
        timings={name:timing.record() for name,timing in timings.items()},
        artifacts_sha256=artifacts,sovren_median_MBps=sv_rate,
        sovren_input_MBps=sv_input_rate,sa_median_MBps=sa_rate,
        workload_class='bulk' if bulk else 'latency',ratio_expanded=sv_rate/sa_rate if bulk else None,
        correctness_qualified=False)
    output=ROOT/a.output;output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(record,indent=2)+'\n')
    for name,timing in timings.items():print(f'{name}: median {timing.median_seconds*1000:.3f} ms; best {timing.best_seconds*1000:.3f} ms')
    print(f'class={record["workload_class"]}; raw timings and hashes: {output}')
    print(f'bytes: input={src.stat().st_size} expanded={expanded} emitted={emitted}; '
          f'expansion={expansion:.2f}x emission={emission:.2f} B/B')
    print(f'input MB/s: Sovren={sv_input_rate:.3f}; expanded MB/s: Sovren={sv_rate:.3f}')
    if bulk:
        print(f'expanded MB/s: Sovren={sv_rate:.3f}, SA={sa_rate:.3f}; ratio={sv_rate/sa_rate:.6f}')
        if a.require_ratio and sv_rate/sa_rate<a.require_ratio:raise SystemExit('speed gate failed')
    print('Translation-success measurement only; run correctness gate before accepting a candidate.')

if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.TimeoutExpired) as e:raise SystemExit(str(e))
