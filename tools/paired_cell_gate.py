#!/usr/bin/env python3
"""F7 — full per-cell paired acceptance gate (semantics first, 2026-11-08).

IMPORTANT SEMANTICS FIX: `--flat` makes the Sovren compiler emit a FLAT TEXT
SOURCE (ASCII, not an ELF executable), while `sa` always emits an executable.
Those cells are therefore NOT matched-observable-work comparisons and are
reported as FAIL / NOT_MATCHED_WORK, never as GREEN. Execution of BOTH outputs
is checked after EVERY translation for all comparable cells.


Enumerate every workload x size x mode x flag cell. For each cell, run FRESH
COLD processes (Sovren compiler and same-session `sa` with positional argv[2]),
verify output SHA-256 on every run, and compute bootstrap 95% intervals for
the PAIRED latency ratio and PAIRED throughput ratio.

A cell is GREEN only when:
    upper 95% paired latency ratio   <= 1.0
    lower 95% paired throughput ratio >= 1.0
Unknown / absent / timed-out / nondeterministic cells FAIL. Global completion
requires ALL cells green; no claim is made otherwise.

Input AND expanded bytes are reported for every cell (C.34).
"""
import argparse, hashlib, json, os, random, shutil, statistics, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cold_gate

ROOT = Path(__file__).resolve().parents[1]
SA = Path('/home/user/dl/sovren-assembler/sa')
FLAG_FILES = ('/tmp/sov_nopar', '/tmp/sov_tklex', '/tmp/sov_ptime')
WORKLOADS = ['exit7', 'sum', 'calls']
SIZES = ['small', 'large-64k']
MODES = [('default', []), ('unsafe', ['--unsafe'])]
FLAGS = [('none', []), ('flat', ['--flat'])]

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if p.is_file() else ''

def fresh():
    for f in FLAG_FILES:
        try: os.unlink(f)
        except FileNotFoundError: pass

def timed(argv, out, timeout=120, expect_exit=None, allow_stdout=False):
    fresh()
    if out.exists(): out.unlink()
    t0 = time.perf_counter()
    try:
        p = subprocess.run(argv, cwd=ROOT, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, None, 'TIMEOUT'
    dt = time.perf_counter() - t0
    if p.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        return None, None, 'TRANSLATION_FAILED'
    h = sha(out)
    if expect_exit is not None:
        os.chmod(out, 0o755)
        try:
            r = subprocess.run([str(out)], capture_output=True, timeout=10)
            if r.returncode != expect_exit or r.stderr or (r.stdout and not allow_stdout):
                return None, None, 'EXECUTION_MISMATCH'
        except (OSError, subprocess.TimeoutExpired):
            return None, None, 'NOT_EXECUTABLE'
    return dt, h, ''

def bootstrap_ci(values, lo_pct=2.5, hi_pct=97.5, B=2000):
    if not values: return (None, None)
    r = random.Random(20261108)
    meds = []
    n = len(values)
    for _ in range(B):
        s = [values[r.randrange(n)] for _ in range(n)]
        meds.append(statistics.median(s))
    meds.sort()
    return (meds[int(B*lo_pct/100)], meds[min(B-1, int(B*hi_pct/100))])

def make_sources(W, workload, size):
    if size == 'small':
        s = ROOT/'tests/performance'/(workload+'.sov')
        a = ROOT/'tests/performance'/(workload+'.sa')
        if not s.is_file() or not a.is_file(): return None, None
        return s, a
    s = W/(workload+'-64k.sov'); a = W/(workload+'-64k.sa')
    cold_gate.gen_unique_sov(str(s), 65536)
    cold_gate.gen_unique_asm(str(a), 65536)
    return s, a

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--compiler', default=str(ROOT/'compilers/linux/compiler'))
    ap.add_argument('--sa', default=str(SA))
    ap.add_argument('--runs', type=int, default=21)
    ap.add_argument('--output', default='/home/user/evidence/C20_C25_paired_cells_c4.json')
    a = ap.parse_args()
    cc, sa = Path(a.compiler), Path(a.sa)
    if not sa.is_file(): sys.exit('SA reference missing: ' + str(sa))
    cells = []
    with tempfile.TemporaryDirectory(prefix='paired-cells-') as td:
        W = Path(td)
        for w in WORKLOADS:
            for sz in SIZES:
                sov_src, sa_src = make_sources(W, w, sz)
                if sov_src is None:
                    for mn, _ in MODES:
                        for fn, _ in FLAGS:
                            cells.append(dict(workload=w, size=sz, mode=mn, flag=fn,
                                verdict='FAIL', reason='ABSENT_SOURCE'))
                    continue
                in_s, in_a = sov_src.stat().st_size, sa_src.stat().st_size
                # expanded bytes: one --flat compile of this source
                flat_out = W/'flat.bin'
                timed([str(cc), str(sov_src), '-o', str(flat_out), '--flat'], flat_out)
                expanded = flat_out.stat().st_size if flat_out.is_file() else in_s
                expect = {'exit7': 7, 'sum': 92, 'calls': 224}[w] if sz == 'small' else 0
                for mn, mflags in MODES:
                    for fn, fflags in FLAGS:
                        comb = mflags + fflags
                        # --flat emits TEXT; sa emits an ELF. Not matched work.
                        if '--flat' in comb:
                            cells.append(dict(workload=w, size=sz, mode=mn, flag=fn,
                                flags=comb, input_bytes_sovren=in_s, input_bytes_sa=in_a,
                                expanded_bytes=expanded, verdict='FAIL',
                                reason='NOT_MATCHED_WORK: --flat emits flat text, sa emits ELF',
                                comparable=False))
                            continue
                        out_s, out_a = W/'s.bin', W/'a.bin'
                        lat, thr, hs_s, hs_a = [], [], set(), set()
                        reason = ''
                        for i in range(a.runs):
                            # interleaved rotation, fresh cold processes
                            order = [(cc, sov_src, out_s, ['-o']+comb, 'sov'),
                                     (sa, sa_src, out_a, [], 'sa')]
                            if i % 2: order.reverse()
                            this = {}
                            for exe, src, out, extra, kind in order:
                                if kind=='sov':
                                    argv = [str(exe), str(src), '-o', str(out)] + comb
                                else:
                                    argv = [str(exe), str(src), str(out)]  # positional argv[2]
                                dt, h, err = timed(argv, out, expect_exit=expect,
                                                   allow_stdout=(sz != 'small'))
                                if dt is None: reason=err or 'TIMEOUT_OR_REFUSAL'; break
                                (hs_s if kind=='sov' else hs_a).add(h)
                                this[kind]=dt
                            if reason: break
                            # pair ONLY samples from THIS round
                            ts, ta = this['sov'], this['sa']
                            lat.append(ts/ta)
                            thr.append((expanded/ts)/(in_a/ta))
                        if not reason and (len(hs_s)!=1 or len(hs_a)!=1):
                            reason='NONDETERMINISTIC'
                        if reason or not lat:
                            cells.append(dict(workload=w, size=sz, mode=mn, flag=fn,
                                flags=comb, input_bytes_sovren=in_s, input_bytes_sa=in_a,
                                expanded_bytes=expanded, verdict='FAIL', reason=reason or 'NO_PAIRS'))
                            continue
                        llo, lhi = bootstrap_ci(lat)
                        tlo, thi = bootstrap_ci(thr)
                        green = lhi is not None and lhi <= 1.0 and tlo >= 1.0
                        cells.append(dict(workload=w, size=sz, mode=mn, flag=fn,
                            flags=comb, input_bytes_sovren=in_s, input_bytes_sa=in_a,
                            expanded_bytes=expanded, runs=a.runs,
                            paired_latency_ratio_med=statistics.median(lat),
                            paired_latency_ratio_ci95=[llo,lhi],
                            paired_throughput_ratio_med=statistics.median(thr),
                            paired_throughput_ratio_ci95=[tlo,thi],
                            comparable=True, execution_checked_every_run=True,
                            expected_exit=expect, green=green,
                            verdict='GREEN' if green else 'FAIL',
                            reason='' if green else 'ratio gate RED'))
    ngreen = sum(1 for c in cells if c['verdict']=='GREEN')
    report = dict(schema=1, matrix='3 workloads x 2 sizes x 2 modes x 2 flags',
        cells=len(cells), green=ngreen, all_green=ngreen==len(cells),
        rules=dict(fresh_cold_processes=True, sa_positional_argv2=True,
                   upper95_latency_le_1=True, lower95_throughput_ge_1=True,
                   input_and_expanded_bytes_reported=True, absent_cells_fail=True,
                   execution_checked_after_every_translation=True,
                   flat_cells_not_matched_work=True),
        compiler_md5=hashlib.md5(cc.read_bytes()).hexdigest(),
        sa_sha256=hashlib.sha256(sa.read_bytes()).hexdigest()[:16],
        runs=a.runs, detail=cells)
    out=Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n')
    print('F7 paired-cell gate: %d/%d GREEN -> %s' % (ngreen,len(cells),out))
    for c in cells:
        print('  %-6s %-9s %-7s %-5s %s%s' % (c['workload'],c['size'],c['mode'],c['flag'],
              c['verdict'], ' ('+c['reason']+')' if c.get('reason') else ''))
    return 0 if ngreen==len(cells) else 1

if __name__=='__main__': sys.exit(main())
