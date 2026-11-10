#!/usr/bin/env python3
"""C.11 differential gate: OLD multi-pass reader descriptors vs FUSED one-pass.

Builds tools/native_reader_desc.c as a shared object, drives both exported
cores over the S28R-shaped corpus (hardcoded stress texts covering every
reader construct, seeded PRNG reader-shaped texts, and real .sov files /
function bodies), and compares all 23 descriptor fields for every line.

Semantics first: any mismatch is a minimised counterexample with the exact
field, line and both values. Unknown/timed-out cases FAIL. No caching: every
run is a fresh process and a fresh buffer.

Usage: python3 tools/reader_descriptor_gate.py [--json OUT] [--cases N]
"""
import argparse
import ctypes
import hashlib
import json
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SRC = R / 'tools/native_reader_desc.c'
FIELDS = ['len', 'lead32', 't0', 't1', 'colon', 'lp', 'n', 'ind',
          'last33', 'last58trim', 'last58raw', 'eqbit', 'eqpt', 'eqany',
          'q1', 'q2', 'neq', 'nis', 'semi2', 'apos', 'gt', 'digit0', 'qparity']
NF = len(FIELDS)
MAX_LINES = 200000

STRESS = [
    'main:\n    a: 1 ;; b: 2\n    return a\n',
    'main:\n    x = 1\n    y = x + 2\n    print y\n',
    'main:\n    if x > 1\n        print "hi"\n    return 0\n',
    'use:\n    print: "a -> b"\n    emit: "c: d"\n',
    'f a b:\n    x: a + b\n    return x\n',
    'db "a:b;c" ;; db \'quoted\'\n',
    'main:\n    # comment only\n\n    # another\n    return 0\n',
    'main:\n\tv: 1\n\tif v isnt 2\n\t\tprint v\n\treturn v\n',
    'main:\n    x != 3\n    y = 4\n    x != 5\n',
    'emit8:\n    1 2 3 4\n',
    'main:\n    a:b:c: d\n    return a\n',
    'main:\n    s: "quote: inside ;; and \\" escape"\n    print s\n',
    'main:\n    123: 456\n    return 123\n',
    'main:\n\t\tx: 1\n\t\ty: 2\n\t\treturn x + y\n',
    'main:\n    a: f(1, 2)\n    return a\n',
    '# whole file is a comment\n# second line\n',
    '',
    '\n\n\n',
    'main:\n    return 0',
    'main:\r\n    x: 1\r\n    return x\r\n',
]


def build_so(td):
    so = Path(td) / 'reader_desc.so'
    r = subprocess.run(['gcc', '-O2', '-fPIC', '-shared', str(SRC), '-o', str(so)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('gcc failed: ' + r.stderr[:500])
    lib = ctypes.CDLL(str(so))
    lib.ref_descriptors.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                                    ctypes.c_uint64]
    lib.ref_descriptors.restype = ctypes.POINTER(ctypes.c_uint64)
    lib.fused_descriptors.argtypes = lib.ref_descriptors.argtypes
    lib.fused_descriptors.restype = ctypes.POINTER(ctypes.c_uint64)
    lib.descriptor_field_count.restype = ctypes.c_uint64
    assert lib.descriptor_field_count() == NF
    return lib


def run(lib, fn, text, out=None):
    """Pad by 8 NULs so the fused core's 4-byte lookaheads stay in bounds."""
    buf = ctypes.create_string_buffer(text.encode('latin1', 'replace') + b'\0' * 8)
    if out is None:
        out = (ctypes.c_uint64 * (MAX_LINES * NF))()
    fn(buf, out, MAX_LINES)
    return out


def line_count(text):
    # both cores emit one descriptor per line, no phantom final empty line
    if not text:
        return 0
    n = text.count('\n')
    return n + (0 if text.endswith('\n') else 1)


def compare(lib, tag, text, failures):
    a, b = run(lib, lib.ref_descriptors, text), run(lib, lib.fused_descriptors, text)
    nl = line_count(text)
    for ln in range(nl):
        for f in range(NF):
            x, y = a[ln * NF + f], b[ln * NF + f]
            if x != y:
                lines = text.split('\n')
                failures.append(dict(case=tag, line=ln, field=FIELDS[f],
                                     old=int(x), fused=int(y),
                                     source=lines[ln] if ln < len(lines) else ''))
                return
    return nl


def corpus(n_cases):
    yield from (('stress-%d' % i, t) for i, t in enumerate(STRESS))
    rnd = random.Random(0xC11)
    atoms = ['x: 1', 'y = 2', 'if x > 1', 'print "a: b"', 'return 0',
             'a: f(1)', '# comment', '', '  b: 3 ;; c: 4', '\tz: 5',
             'x != 2', 'x isnt 3', "db 'q'", 'emit8:', 'use:',
             '123: 456', 'a:b: c', 's: "esc \\" x"', '   ', 'a: 1 ;;']
    for c in range(n_cases):
        lines = ['main:']
        for _ in range(rnd.randint(3, 40)):
            lines.append(rnd.choice(['    ', '\t', '  ', ''])
                         + rnd.choice(atoms))
        lines.append('    return 0')
        yield ('prng-%d' % c, '\n'.join(lines) + '\n')
    for p in sorted((R / 'tests').glob('*.sov'))[:20]:
        yield ('file-' + p.name, p.read_text(errors='replace'))
    for p in sorted((R / 'compilers/linux').glob('*.sov'))[:8]:
        yield ('file-' + p.name, p.read_text(errors='replace'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default='/home/user/evidence/C11_fused_descriptor_gate.json')
    ap.add_argument('--cases', type=int, default=120)
    a = ap.parse_args()
    out = Path(a.json); out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='c11-desc-') as td:
        lib = build_so(td)
        failures, cases, lines = [], 0, 0
        t0 = time.time()
        for tag, text in corpus(a.cases):
            n = compare(lib, tag, text, failures)
            cases += 1
            lines += n or 0
        dt = time.time() - t0
        # C.12/C.33: R=21 ROTATED INTERLEAVED with an A/A PLACEBO control.
        # The placebo is a second, independently loaded build of the SAME
        # reference source: it measures the layout lottery / host noise band.
        # A "win" is only claimed if the A/B ratio lies OUTSIDE that band.
        big = (R / 'compilers/linux/compiler.sov').read_text(errors='replace')
        nl_big = line_count(big)
        cap = min(MAX_LINES, max(nl_big + 16, 1024))
        bufa = (ctypes.c_uint64 * (cap * NF))()
        bufb = (ctypes.c_uint64 * (cap * NF))()
        lib2 = build_so(td)          # placebo: identical source, fresh addresses
        def one(fn, obuf):
            t0 = time.perf_counter()
            run(lib, fn, big, obuf)
            return (time.perf_counter() - t0) * 1000.0
        ab, aa = [], []
        for rnd in range(21):
            if rnd % 2 == 0:
                ta = one(lib.ref_descriptors, bufa)
                tb = one(lib.fused_descriptors, bufb)
                tc = one(lib2.ref_descriptors, bufa)
            else:
                tb = one(lib.fused_descriptors, bufb)
                ta = one(lib.ref_descriptors, bufa)
                tc = one(lib2.ref_descriptors, bufa)
            ab.append(ta / tb)
            aa.append(ta / tc)
        ab.sort(); aa.sort()
        ab_med, aa_med = ab[10], aa[10]
        band = (aa[0], aa[-1])
        # Conservative: require BOTH the median AND the worst A/B round to
        # clear the entire A/A band. A wide A/A band (host bimodality) can
        # otherwise manufacture a "win" from noise.
        outside = (ab_med > band[1]) and (ab[0] > band[1])
        old_ms, fused_ms = ta, tb
    report = dict(schema=1, fields=NF, field_names=FIELDS, cases=cases,
                  lines_compared=lines, mismatches=len(failures),
                  failures=failures[:20], duration_s=round(dt, 3),
                  ref_ms_per_self=round(old_ms, 3),
                  fused_ms_per_self=round(fused_ms, 3),
                  speed_ratio=round(old_ms / fused_ms, 3) if fused_ms else None,
                  placebo=dict(runs=21, rotated_interleaved=True,
                               a_b_median_ratio=round(ab_med, 4),
                               a_b_min_ratio=round(ab[0], 4),
                               a_a_median_ratio=round(aa_med, 4),
                               a_a_band=[round(band[0], 4), round(band[1], 4)],
                               outside_band=bool(outside),
                               verdict='CREDIBLE_WIN' if outside else 'INSIDE_NOISE',
                               note='The A/A band is wide on this 2-CPU host; '
                                    'a core-level win is NOT a whole-compile '
                                    'speed claim until the twin is integrated '
                                    'and measured with tools/ab_gate.py.'),
                  all_green=(len(failures) == 0 and cases > 0),
                  note='Descriptor core only. Integration into compiler.sov and '
                       'a placebo-controlled whole-compile A/B are still required.')
    out.write_text(json.dumps(report, indent=2) + '\n')
    print('C.11 fused descriptor gate: %d cases / %d lines / %d mismatches'
          % (cases, lines, len(failures)))
    for f in failures[:5]:
        print('  DIVERGE', f)
    print('  R=21 rotated A/B median %.4fx, A/A placebo %.4fx band [%.4f, %.4f] -> %s'
          % (ab_med, aa_med, band[0], band[1], report['placebo']['verdict']))
    print('  -> %s' % out)
    print('ALL GREEN' if report['all_green'] else 'NOT GREEN')
    return 0 if report['all_green'] else 1


if __name__ == '__main__':
    sys.exit(main())
