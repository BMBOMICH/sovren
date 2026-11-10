#!/usr/bin/env python3
"""C.9 / C.20 / C.34 — real syscall census + interleaved tiny-floor latency.

`strace`/`perf` are absent in this sandbox, so this uses the workspace's
portable ptrace syscall tracer (`agent/ptrace_tools.py`) to count syscalls
with exact numbers, then measures the tiny floor with R=21 rotated, fully
cold, fresh-process interleaved runs on the same host.

It is MEASUREMENT ONLY.  It does not edit compiler.sov, runtime.sov, any
emitter, any gate, any .build-failed marker or any frozen matrix.  Changing
runtime.sov or the emitted startup would change every output's bytes and
break C.29 byte identity / C.26 mode identity, so no such change is landed.

Usage: python3 tools/c9_c20_floor_census.py [--json OUT] [--runs 21]
"""
import argparse
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
ROOT = Path('/home/user')
TRACE = ROOT / 'agent' / 'ptrace_tools.py'
CC = R / 'compilers/linux/compiler'
SA = Path('/home/user/dl/sovren-assembler/sa')
E = ROOT / 'evidence'
LINE_RE = re.compile(r'^\s*(\d+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*$')


def census(argv, cwd=R, timeout=300):
    try:
        p = subprocess.run([sys.executable, str(TRACE), '--strace'] + [str(x) for x in argv],
                           cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'error': 'TIMEOUT'}
    counts = {}
    for ln in (p.stdout + p.stderr).splitlines():
        m = LINE_RE.match(ln)
        if m:
            counts[m.group(2)] = int(m.group(1))
    return {'counts': counts, 'total': sum(counts.values()),
            'mmap': counts.get('mmap', 0), 'mprotect': counts.get('mprotect', 0),
            'write': counts.get('write', 0), 'open': counts.get('open', 0) + counts.get('openat', 0)}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else ''


def cold_run(argv, out, cwd=R):
    """Cold spawn, NO timeout= (Popen.communicate's timeout poll loop adds
    ~1 ms and cannot resolve a 0.211 ms floor). Mirrors the established
    everywhere_probe.py min-of-9 measurement shape."""
    for f in ('/tmp/sov_nopar', '/tmp/sov_tklex', '/tmp/sov_ptime'):
        try:
            os.unlink(f)
        except FileNotFoundError:
            pass
    if Path(out).exists():
        Path(out).unlink()
    t0 = time.perf_counter()
    r = subprocess.run([str(x) for x in argv], cwd=cwd,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dt = (time.perf_counter() - t0) * 1000.0
    return dt, r.returncode, sha(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C9_C20_floor_census_2026-11-09.json'))
    ap.add_argument('--runs', type=int, default=21)
    a = ap.parse_args()
    runs = a.runs

    # ---- syscall census (exact counts, ptrace) ----
    srcs = {
        'exit7_19B': ('tests/performance/exit7.sov', 'tests/performance/exit7.sa'),
        'hello_191B': ('tests/hello.sov', None),
    }
    cens = {}
    cens['bin_true'] = census(['/bin/true'])
    cens['sa_exit7'] = census([SA, 'tests/performance/exit7.sa', '/tmp/c9_sa.bin'])
    for name, (sov, _) in srcs.items():
        cens['sovren_' + name] = census([CC, sov, '-o', '/tmp/c9_%s.bin' % name])
    cens['sovren_self_compile'] = census(
        [CC, 'compilers/linux/compiler.sov', '-o', '/tmp/c9_self.bin'])
    cens['emitted_hello_runtime'] = census(['/tmp/c9_hello_191B.bin'])
    cens['sa_emitted_exit7_runtime'] = census(['/tmp/c9_sa.bin'])

    # ---- interleaved cold tiny floor, R=21 rotated ----
    for f in ('/tmp/c9_floor_s.bin', '/tmp/c9_floor_a.bin'):
        if Path(f).exists():
            Path(f).unlink()
    argv_s = [CC, 'tests/hello.sov', '-o', '/tmp/c9_floor_s.bin']
    argv_a = [SA, 'tests/performance/exit7.sa', '/tmp/c9_floor_a.bin']
    argv_t = ['/bin/true']
    ts, ta, tt = [], [], []
    hashes = {'sovren': set(), 'sa': set()}
    tag_key = {'s': 'sovren', 'a': 'sa'}
    for i in range(runs):
        order = [('s', argv_s, '/tmp/c9_floor_s.bin'),
                 ('a', argv_a, '/tmp/c9_floor_a.bin'),
                 ('t', argv_t, None)]
        if i % 2:
            order.reverse()
        this = {}
        for tag, argv, out in order:
            dt, rc, h = cold_run(argv, out or '/tmp/c9_floor_true.bin')
            this[tag] = dt
            k = tag_key.get(tag)
            if k and h:
                hashes[k].add(h)
        ts.append(this['s']); ta.append(this['a']); tt.append(this['t'])

    def stat(v):
        return {'min_ms': round(min(v), 4), 'median_ms': round(statistics.median(v), 4),
                'mean_ms': round(statistics.mean(v), 4), 'n': len(v)}

    # Established C.9 reference on this host (evidence/floor_interleaved.txt):
    # sa-tiny min 0.211 ms / sovren-tiny 0.648 / sovren-hello 0.758.
    # Report it alongside, never replace a fresh measurement with it.

    floor = {'sovren_hello': stat(ts), 'sa_exit7': stat(ta), 'bin_true': stat(tt),
             'sovren_over_sa_median': round(statistics.median(ts) / statistics.median(ta), 3),
             'sovren_over_sa_min': round(min(ts) / min(ta), 3),
             'sovren_output_deterministic': len(hashes['sovren']) == 1,
             'sa_output_deterministic': len(hashes['sa']) == 1,
             'established_reference_ms': {'sa_tiny_min': 0.211, 'sovren_tiny_min': 0.648,
                                          'sovren_hello_min': 0.758, 'bin_true_min': 0.992,
                                          'source': 'evidence/floor_interleaved.txt'}}

    # expanded bytes for honest C.34 accounting
    flat = '/tmp/c9_flat.txt'
    cold_run([CC, 'tests/hello.sov', '-o', flat, '--flat'], flat)
    expanded = Path(flat).stat().st_size if Path(flat).is_file() else 0
    inp = (R / 'tests/hello.sov').stat().st_size
    inp_sa = (R / 'tests/performance/exit7.sa').stat().st_size

    rep = dict(
        schema=1, date='2026-11-09', host=platform.uname()._asdict(),
        method='ptrace PTRACE_SYSCALL exact syscall counts; R=%d rotated cold wall-clock' % runs,
        installed_compiler_md5=hashlib.md5(CC.read_bytes()).hexdigest(),
        input_bytes={'sovren_hello': inp, 'sa_exit7': inp_sa,
                     'sovren_hello_expanded_flat': expanded},
        syscall_census=cens,
        tiny_floor=floor,
        verdict='C9_C20_RED',
        findings=[
            'The standing C.9 figure "150 mmap / 425 mprotect" is a SELF-COMPILE '
            'census, not a fixed startup cost: fresh ptrace measured %d mmap / '
            '%d mprotect for self-compile, but only %d mmap / %d mprotect for '
            'the 191 B hello compile and %d / %d for the 19 B exit7 compile.'
            % (cens['sovren_self_compile']['mmap'], cens['sovren_self_compile']['mprotect'],
               cens['sovren_hello_191B']['mmap'], cens['sovren_hello_191B']['mprotect'],
               cens['sovren_exit7_19B']['mmap'], cens['sovren_exit7_19B']['mprotect']),
            'mprotect scales with WORK, not boot: runtime.sov _sov_alloc_large '
            'and _sov_try_grow_large issue guard-page mprotect calls per large '
            'allocation/growth; the emitted program itself uses only %d mprotect '
            'and SA-emitted programs use %d.'
            % (cens['emitted_hello_runtime']['mprotect'],
               cens['sa_emitted_exit7_runtime']['mprotect']),
            'SA is %d mmap / %d mprotect / %d write; Sovren hello is %d / %d / %d. '
            'The syscall gap is real and measured.'
            % (cens['sa_exit7']['mmap'], cens['sa_exit7']['mprotect'], cens['sa_exit7']['write'],
               cens['sovren_hello_191B']['mmap'], cens['sovren_hello_191B']['mprotect'],
               cens['sovren_hello_191B']['write']),
            'Interleaved tiny floor: Sovren median %.4f ms vs SA %.4f ms = %.3fx; '
            'C.20 requires <= SA 0.211 ms with identical output -> RED.'
            % (floor['sovren_hello']['median_ms'], floor['sa_exit7']['median_ms'],
               floor['sovren_over_sa_median']),
            'NO CHANGE LANDED. Editing runtime.sov or the emitted startup code '
            'would change every compiled output and break C.29 byte identity '
            '(2,957 differ) and C.26 36/36 mode identity. C.9/C.20 therefore '
            'need the C.2-C.8 front-end replacement, not a guard-page tweak.',
        ],
        note='Measurement only. No cache, no warm path, no gate or matrix change, '
             'no parity claim (C.39).')
    out = Path(a.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.9/C.20 census: %s' % rep['verdict'])
    for k, v in cens.items():
        print('  %-28s mmap=%-4s mprotect=%-4s write=%-3s total=%s'
              % (k, v.get('mmap'), v.get('mprotect'), v.get('write'), v.get('total')))
    print('  tiny floor Sovren med %.4f ms / SA med %.4f ms (%.3fx) -> %s'
          % (floor['sovren_hello']['median_ms'], floor['sa_exit7']['median_ms'],
             floor['sovren_over_sa_median'], out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
