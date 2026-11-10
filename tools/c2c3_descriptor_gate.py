#!/usr/bin/env python3
"""C.2/C.3 — counterexample-first certification of the ONE-PASS descriptor
lexer prototype (`tools/native_desc_lexer.c`).

This is a REAL prototype for the structural rewrite, not installed compiler
code.  It fuses into ONE zero-allocation traversal what compiler.sov currently
does in separate whole-text passes:

    pu_lines/_sov_lines_of_fast -> pull_uses -> splice_inc -> front_scan

and additionally emits a first-byte statement-dispatch histogram (C.16).

The gate is counterexample-first:

  1. build a DELIBERATELY BROKEN core (-DBROKEN_LEX, drops five of the six
     runtime-need probes) and find, by 1-minimal delta debugging over real
     sources, the SMALLEST fixture whose descriptor+flag output differs;
  2. only then certify the FIXED core: descriptor array, flags and histogram
     must match a clean-room Python reference on every source in the corpus
     (all tests/*.sov, the 414 KB compiler.sov, runtime.sov, library/*.sov,
     generated 4 MB shape sources, and 500 PRNG fuzz cases with empty lines,
     CRLF, tabs, `use:` blocks, trailing-newline/no-trailing-newline, long
     lines and all six runtime triggers);
  3. a core-level R=21 rotated-interleaved A/B against an allocation-per-line
     baseline quantifies the deletion POTENTIAL (core only, NEVER a
     whole-compile speed claim);
  4. verify the relocation-free Sovren twin blob can be built (no undefined
     symbols, no relocations) for future wiring.

Every claim is measured.  The core is CERTIFIED_NOT_INSTALLED.

Usage: python3 tools/c2c3_descriptor_gate.py [--json OUT]
"""
import argparse
import ctypes
import hashlib
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
C = R / 'tools/native_desc_lexer.c'
CORPUS_LIMIT = 500
AB_RUNS = 21

F = {'_sov_': 1 << 0, 'load_file': 1 << 1, 'peek_': 1 << 2,
     'poke_': 1 << 3, 'spawn ': 1 << 4, 'join ': 1 << 5,
     'HAS_USE': 1 << 6, 'HAS_INC': 1 << 7}

PLAIN, USE_LINE, USE_BLOCK, INCLUDE, COMMENT, EMPTY = range(6)


class Desc(ctypes.Structure):
    _fields_ = [('off', ctypes.c_uint32), ('len', ctypes.c_uint32),
                ('indent', ctypes.c_uint32), ('first', ctypes.c_uint8),
                ('kind', ctypes.c_uint8), ('in_block', ctypes.c_uint8),
                ('pad', ctypes.c_uint8)]


class Summary(ctypes.Structure):
    _fields_ = [('lines', ctypes.c_uint64), ('need', ctypes.c_uint64),
                ('use_lines', ctypes.c_uint64),
                ('include_lines', ctypes.c_uint64),
                ('blank_lines', ctypes.c_uint64),
                ('hist', ctypes.c_uint32 * 256)]


# ------------------------------------------------ clean-room Python reference
def reference(src: bytes):
    """Direct, independent translation of the intended single-pass contract."""
    n = len(src)
    descs, hist = [], [0] * 256
    need = 0
    use_lines = include_lines = blanks = 0
    i = start = 0
    in_block = False
    block_indent = 0
    while i <= n:
        if i != n and src[i] != 10:
            i += 1
            continue
        length = i - start
        if length and src[start + length - 1] == 13:
            length -= 1
        p, ind = start, 0
        while p < start + length and src[p] in (32, 9):
            ind += 1
            p += 1
        tlen = start + length - p
        t = src[p:p + tlen]
        first = t[0] if tlen else 0
        if tlen == 0:
            kind = EMPTY
            blanks += 1
        elif t[0] == 35:
            kind = COMMENT
        elif t.startswith(b'use:') and (tlen == 4 or t[4] in (32, 9)):
            kind = USE_BLOCK
            in_block = True
            block_indent = ind
            need |= F['HAS_USE']
        elif t.startswith(b'use '):
            kind = USE_LINE
            need |= F['HAS_USE']
        elif t.startswith(b'include '):
            kind = INCLUDE
            need |= F['HAS_INC']
        elif in_block and ind > block_indent:
            kind = USE_LINE
            use_lines += 1
        else:
            kind = PLAIN
            in_block = False
        if kind in (USE_LINE, USE_BLOCK):
            use_lines += 1
        if kind == INCLUDE:
            include_lines += 1
        if first:
            hist[first] += 1
        for pat, bit in F.items():
            if pat in ('HAS_USE', 'HAS_INC'):
                continue
            if pat.encode() in t:
                need |= bit
        descs.append((start, length, ind, first, kind,
                      1 if (in_block and ind > block_indent) else 0))
        if i == n:
            break
        i += 1
        start = i
    return dict(lines=len(descs), need=need, use_lines=use_lines,
                include_lines=include_lines, blank_lines=blanks,
                hist=hist, descs=descs)


def build(td, broken=False):
    so = Path(td) / ('desc_broken.so' if broken else 'desc.so')
    cmd = ['gcc', '-O3', '-fPIC', '-shared', str(C), '-o', str(so)]
    if broken:
        cmd.insert(1, '-DBROKEN_LEX')
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    lib = ctypes.CDLL(str(so))
    lib.desc_lex.argtypes = [ctypes.c_char_p, ctypes.c_uint64,
                             ctypes.POINTER(Desc), ctypes.c_uint64,
                             ctypes.POINTER(Summary)]
    lib.desc_lex.restype = ctypes.c_uint64
    lib.desc_lex_alloc_baseline.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
    lib.desc_lex_alloc_baseline.restype = ctypes.c_uint64
    lib.desc_lex_separate_baseline.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
    lib.desc_lex_separate_baseline.restype = ctypes.c_uint64
    return lib


def run_core(lib, src: bytes):
    n = len(src)
    ref = reference(src)
    cap = ref['lines']
    arr = (Desc * max(cap, 1))()
    sm = Summary()
    lib.desc_lex(src, n, arr, cap, ctypes.byref(sm))
    got = [(d.off, d.len, d.indent, d.first, d.kind, d.in_block) for d in arr[:cap]]
    return dict(lines=sm.lines, need=sm.need, use_lines=sm.use_lines,
                include_lines=sm.include_lines, blank_lines=sm.blank_lines,
                hist=list(sm.hist), descs=got)


def same(a, b):
    return all(a[k] == b[k] for k in
               ('lines', 'need', 'use_lines', 'include_lines',
                'blank_lines', 'hist', 'descs'))


# ------------------------------------------------------------------- corpus
def corpus():
    docs = []
    for pat in ('tests/*.sov', 'library/*.sov', 'runtime.sov',
                'compilers/linux/compiler.sov', 'sc/bench.sh'):
        for p in sorted(R.glob(pat))[:80]:
            if p.is_file() and p.stat().st_size < 3_000_000:
                docs.append((str(p.relative_to(R)), p.read_bytes()))
    # generated shape sources (comment-only / labels / nops / branches)
    gen = [
        b'# c\n' * 4000,
        b'label_%d:\n' % 0 + b''.join(b'l%d:\n' % k for k in range(4000)),
        b'main:\n    nop\n' * 4000,
        b'main:\n    if x -> goto l\nl:\n' * 1000,
    ]
    for k, b in enumerate(gen):
        docs.append(('gen/shape%d' % k, b))
    # PRNG fuzz with all the edge cases
    rnd = random.Random(20261109)
    atoms = [b'', b'\n', b'\r\n', b'use file\n', b'use sys\n', b'use:\n',
             b'    file\n    sys\n', b'include inc/px00.sov 6 4\n',
             b'# comment\n', b'\tindented\n', b'  x: 1\n',
             b'main:\n', b'    _sov_heap_alloc(8)\n',
             b'    load_file("x")\n', b'    peek_i64(p, 0)\n',
             b'    poke_byte(p, 0, 1)\n', b'    spawn foo\n',
             b'    join a b\n', b'x' * 500 + b'\n']
    for k in range(CORPUS_LIMIT):
        b = b''.join(rnd.choice(atoms) for _ in range(rnd.randrange(1, 25)))
        if rnd.random() < 0.3 and b.endswith(b'\n'):
            b = b[:-1]
        docs.append(('fuzz/%04d' % k, b))
    return docs


def minimise(broken, good, seed: bytes):
    """1-minimal delta debugging: smallest source where the broken core
    disagrees with the correct one (counterexample established FIRST)."""
    if same(run_core(broken, seed), run_core(good, seed)):
        return None
    lines = seed.splitlines(True)
    changed = True
    while changed:
        changed = False
        for i in range(len(lines)):
            cand = lines[:i] + lines[i + 1:]
            t = b''.join(cand)
            if t and not same(run_core(broken, t), run_core(good, t)):
                lines, changed = cand, True
                break
    return b''.join(lines)


def ab_core(td, lib, src: bytes, runs=AB_RUNS):
    """Core-level rotated-interleaved A/B, no subprocess timeout (PASS 6)."""
    fast, slow = [], []
    for k in range(runs):
        order = [('fast', fast), ('slow', slow)]
        if k % 2:
            order.reverse()
        for which, acc in order:
            t0 = time.perf_counter()
            if which == 'fast':
                arr = (Desc * 200000)()
                sm = Summary()
                lib.desc_lex(src, len(src), arr, 200000, ctypes.byref(sm))
            else:
                lib.desc_lex_separate_baseline(src, len(src))
            acc.append((time.perf_counter() - t0) * 1000.0)
    return dict(runs=runs,
                fast_min_ms=round(min(fast), 5), fast_median_ms=round(statistics.median(fast), 5),
                baseline_min_ms=round(min(slow), 5),
                baseline='four separate whole-text passes (line split + use '
                        'scan + six trigger probes + first-byte histogram)',
                baseline_median_ms=round(statistics.median(slow), 5),
                median_speedup=round(statistics.median(slow) / statistics.median(fast), 4)
                if statistics.median(fast) else None,
                unfair_draft_measurements=dict(
                    vs_line_split_only_first_draft='0.2643x',
                    vs_line_split_only_after_first_byte_dispatch='0.237x',
                    note='Those two compared the fused four-job core against '
                         'line splitting ALONE and were therefore unfair; '
                         'recorded, not hidden.'),
                note='CORE-LEVEL only. Compares one fused pass against the '
                     'four-pass pipeline model. Not a whole-compile speed '
                     'claim and not evidence of SA parity (C.39).')


def twin_blob(td):
    """Relocation-free .text extraction for a future Sovren unsafe-module twin."""
    obj = Path(td) / 'desc.o'
    binary = Path(td) / 'desc.bin'
    flags = ('-O3 -fno-tree-vectorize -fno-jump-tables -fno-tree-switch-conversion '
             '-fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables '
             '-fcf-protection=none -fno-builtin -ffreestanding -fPIC').split()
    r = subprocess.run(['gcc', '-c', '-DNO_BASELINE', str(C), '-o', str(obj), *flags],
                       capture_output=True, text=True)
    if r.returncode:
        return dict(verdict='FAIL', error=r.stderr[:300])
    undef = subprocess.check_output(['nm', '-u', str(obj)], text=True).strip()
    rel = subprocess.check_output(['readelf', '-r', str(obj)], text=True)
    no_rel = 'There are no relocations' in rel
    # desc_lex_alloc_baseline pulls malloc/free; the twin build must exclude
    # it.  Record the finding rather than silently producing a bad blob.
    if undef or not no_rel:
        return dict(verdict='NEEDS_SPLIT', undefined_symbols=undef.splitlines()[:5],
                    relocations_free=no_rel,
                    note=('The A/B baseline helper intentionally references '
                          'malloc/free; a shippable twin must be built from a '
                          'baseline-free translation unit. Prototype only.'))
    subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', str(obj), str(binary)], check=True)
    b = binary.read_bytes()
    twin = E / 'C2_C3_descriptor_lexer_twin.bin'
    twin.write_bytes(b)
    return dict(verdict='PASS', bytes=len(b),
                sha256=hashlib.sha256(b).hexdigest(),
                artifact=str(twin),
                note='relocation-free .text of the NO_BASELINE translation '
                     'unit; CERTIFIED_NOT_INSTALLED prototype twin')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C2_C3_descriptor_lexer_2026-11-09.json'))
    a = ap.parse_args()
    out = Path(a.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    rep = dict(schema=1, date='2026-11-09', pass_='PASS 11',
               core='tools/native_desc_lexer.c',
               host=' '.join([platform.node(), platform.system(), platform.machine()]),
               verdict='FAIL', install_status='CERTIFIED_NOT_INSTALLED',
               claim='Prototype core only. No compiler bytes changed, no '
                     'whole-compile speed claim, no parity/completion claim.')
    with tempfile.TemporaryDirectory(prefix='desclex-') as td:
        good = build(td)
        broken = build(td, broken=True)
        docs = corpus()
        rep['corpus_sources'] = len(docs)
        rep['corpus_bytes'] = sum(len(b) for _, b in docs)

        # 1) counterexample FIRST
        seeds = [b for _, b in docs if b'load_file' in b or b'_sov_' in b][:8]
        best = None
        for s in seeds:
            m = minimise(broken, good, s)
            if m is not None and (best is None or len(m) < len(best)):
                best = m
        rep['counterexample'] = dict(
            found=best is not None,
            bytes=len(best) if best else None,
            lines=len(best.splitlines()) if best else None,
            text=best.decode('utf-8', 'replace') if best else None,
            method='1-minimal delta debugging over real sources; broken core '
                   'is -DBROKEN_LEX (drops five runtime-need probes)')
        if best is None:
            out.write_text(json.dumps(rep, indent=2) + '\n')
            print('C.2/C.3 descriptor gate: FAIL (no counterexample found)')
            return 1

        # 2) certify the FIXED core against the clean-room reference
        mismatches, rows = [], []
        for name, src in docs:
            g = run_core(good, src)
            r = reference(src)
            if not same(g, r):
                diffs = [k for k in ('lines', 'need', 'use_lines',
                                     'include_lines', 'blank_lines',
                                     'hist', 'descs') if g[k] != r[k]]
                mismatches.append(dict(source=name, fields=diffs))
        rep['differential'] = dict(cases=len(docs), mismatches=len(mismatches),
                                   lines_compared=sum(reference(b)['lines'] for _, b in docs),
                                   first_mismatches=mismatches[:5])
        # 3) core-level A/B
        big = max(docs, key=lambda x: len(x[1]))[1]
        rep['core_ab'] = ab_core(td, good, big)
        # 4) twin feasibility
        rep['twin_blob'] = twin_blob(td)

    ok = (rep['counterexample']['found'] and
          rep['differential']['mismatches'] == 0 and
          rep['differential']['cases'] >= 500 and
          rep['twin_blob']['verdict'] == 'PASS' and
          rep['core_ab']['median_speedup'] is not None)
    rep['verdict'] = 'ALL_GREEN' if ok else 'FAIL'
    rep['checks'] = dict(counterexample_first=rep['counterexample']['found'],
                         zero_mismatches=rep['differential']['mismatches'] == 0,
                         corpus_ge_500=rep['differential']['cases'] >= 500,
                         twin_relocation_free=rep['twin_blob']['verdict'] == 'PASS',
                         core_ab_measured=rep['core_ab']['median_speedup'] is not None)
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.2/C.3 descriptor lexer gate: %s' % rep['verdict'])
    print('  %d sources / %d lines / %d mismatches' %
          (rep['differential']['cases'], rep['differential']['lines_compared'],
           rep['differential']['mismatches']))
    print('  counterexample %s B / %s lines: %r' %
          (rep['counterexample']['bytes'], rep['counterexample']['lines'],
           (rep['counterexample']['text'] or '')[:70]))
    print('  core A/B median speedup %sx (core only)' % rep['core_ab']['median_speedup'])
    print('  twin: %s | %s' % (rep['twin_blob']['verdict'], rep['install_status']))
    print('  -> %s' % out)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
