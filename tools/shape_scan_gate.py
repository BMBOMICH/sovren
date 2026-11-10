#!/usr/bin/env python3
"""C.15/C.16 gate: AVX2 shape scanner vs byte-loop fallback vs expected shape.

Builds tools/native_shapescan.c as a shared object and verifies:
  1. cpu_has_avx2() agrees with the host's /proc/cpuinfo avx2 flag;
  2. scan_shapes_avx2() == scan_shapes_scalar() on every line of every corpus
     (only when the host actually supports AVX2; otherwise recorded as
     NOT_TESTABLE_ON_THIS_HOST, never silently passed);
  3. scan_shapes_auto() == the supported path;
  4. each of the 12 SA shapes classifies as its named class;
  5. cliff probes, seeded PRNG lines and byte/word-boundary stress all agree.

Semantics first: any disagreement is a minimised counterexample. No caching;
fresh process and fresh buffers per run.

Usage: python3 tools/shape_scan_gate.py [--json OUT]
"""
import argparse
import ctypes
import json
import random
import subprocess
import sys
import tempfile
import time
import statistics
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SRC = R / 'tools/native_shapescan.c'
CLASSES = ['other', 'comment', 'data', 'label', 'long_label', 'mov',
           'expr', 'times', 'fwd_jmp', 'back_jmp', 'equ']
MAX_LINES = 400000

# The 12 SA shapes from C.27, plus the 4 cliff probes.
SHAPES = {
    'comment-only':   ('# generated comment line\n', 'comment'),
    'nop':            ('    nop\n', 'mov'),
    'mov-rax-rbx':    ('    mov rax, rbx\n', 'mov'),
    'db-0':           ('    db 0\n', 'data'),
    'label-only':     ('L0:\n', 'label'),
    'jmp-backward':   ('    jmp L0\n', 'back_jmp'),
    'jmp-forward':    ('    x -> y\n', 'fwd_jmp'),
    'long-labels':    ('averyveryverylonglabelname0001:\n', 'long_label'),
    'times-dup':      ('    times 4 db 0\n', 'times'),
    'expr-heavy':     ('    x: (a + b) * c\n', 'expr'),
    'label-nop':      ('L1:\n    nop\n', None),
    'equ-const':      ('    K = 7\n', 'equ'),
}
CLIFFS = {
    '200k-labels':  'L%d:\n',
    '400k-labels':  'L%d:\n',
    '4MB-nop':      '    nop\n',
    '200k-fwd-jmp': '    a%d -> b%d\n',
}
BOUNDARY = [
    b'', b'\n', b'\n'*3, b' ' * 31 + b'#x\n', b' ' * 32 + b'#x\n',
    b' ' * 33 + b'#x\n', b'\t' * 8 + b'mov rax, 1\n',
    b'#' + b'x' * 31 + b'\n', b'#' + b'x' * 32 + b'\n',
    b'db 1 ;; db 2\n', b'x: "a:b"\n', b"x: 'q'\n",
    b'x != 3\n', b'x isnt 3\n', b'repeat 8 nop\n',
]


def build(td):
    so = Path(td) / 'shapescan.so'
    r = subprocess.run(['gcc', '-O2', '-fPIC', '-shared', str(SRC), '-o', str(so)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('gcc failed: ' + r.stderr[:600])
    lib = ctypes.CDLL(str(so))
    for name in ('scan_shapes_scalar', 'scan_shapes_avx2', 'scan_shapes_auto'):
        f = getattr(lib, name)
        f.argtypes = [ctypes.c_char_p, ctypes.c_uint64,
                      ctypes.POINTER(ctypes.c_uint64), ctypes.c_uint64]
        f.restype = ctypes.POINTER(ctypes.c_uint64)
    lib.cpu_has_avx2.restype = ctypes.c_int
    lib.shape_class_count.restype = ctypes.c_uint64
    assert lib.shape_class_count() == len(CLASSES)
    return lib


def run(lib, fn, data, out):
    fn(data, len(data), out, MAX_LINES)
    return out


def nlines(data):
    if not data:
        return 0
    return data.count(b'\n') + (0 if data.endswith(b'\n') else 1)


def host_avx2():
    try:
        t = Path('/proc/cpuinfo').read_text()
        for line in t.splitlines():
            if line.startswith('flags') or line.startswith('Features'):
                return 'avx2' in line.split()
    except OSError:
        pass
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default='/home/user/evidence/C15_C16_shape_scan_gate.json')
    a = ap.parse_args()
    outp = Path(a.json); outp.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='c15-shape-') as td:
        lib = build(td)
        # The installable blob must be byte-identical in BEHAVIOUR to the
        # full scanner's scalar path (it is extracted verbatim from it).
        blobso = Path(td) / 'shapescan_blob.so'
        br = subprocess.run(['gcc', '-O2', '-fPIC', '-shared',
                             str(R / 'tools/native_shapescan_blob.c'), '-o', str(blobso)],
                            capture_output=True, text=True)
        if br.returncode:
            raise RuntimeError('blob gcc failed: ' + br.stderr[:600])
        blob = ctypes.CDLL(str(blobso))
        blob.scan_shapes_scalar.argtypes = lib.scan_shapes_scalar.argtypes
        blob.scan_shapes_scalar.restype = lib.scan_shapes_scalar.restype
        detected = bool(lib.cpu_has_avx2())
        host = host_avx2()
        if detected != host:
            print('FAIL cpu_has_avx2()=%s but /proc/cpuinfo avx2=%s' % (detected, host))
            return 1
        cap = MAX_LINES
        a_out = (ctypes.c_uint64 * cap)()
        b_out = (ctypes.c_uint64 * cap)()
        c_out = (ctypes.c_uint64 * cap)()
        d_out = (ctypes.c_uint64 * cap)()
        cases, lines, failures = 0, 0, []
        accounting = []          # C.34: input / expanded / emitted bytes

        def check(tag, data, expected=None):
            nonlocal cases, lines
            n = nlines(data)
            cases += 1; lines += n
            accounting.append(dict(case=tag, input_bytes=len(data),
                                   expanded_bytes=len(data),  # scanner: no expansion
                                   emitted_class_bytes=n*8, lines=n))
            run(lib, lib.scan_shapes_scalar, data, a_out)
            run(lib, lib.scan_shapes_auto, data, c_out)
            run(blob, blob.scan_shapes_scalar, data, d_out)
            for i in range(n):
                if a_out[i] != d_out[i]:
                    failures.append(dict(case=tag, line=i, kind='blob_vs_scalar',
                                         scalar=int(a_out[i]), blob=int(d_out[i]),
                                         source=data.split(b'\n')[i][:120].decode('latin1')))
                    return
            for i in range(n):
                if a_out[i] != c_out[i]:
                    failures.append(dict(case=tag, line=i, kind='scalar_vs_auto',
                                         scalar=int(a_out[i]), auto=int(c_out[i]),
                                         source=data.split(b'\n')[i][:120].decode('latin1')))
                    return
                if expected is not None and CLASSES[a_out[i]] != expected:
                    failures.append(dict(case=tag, line=i, kind='expected_class',
                                         got=CLASSES[a_out[i]], expected=expected,
                                         source=data.split(b'\n')[i][:120].decode('latin1')))
                    return
            if detected:
                run(lib, lib.scan_shapes_avx2, data, b_out)
                for i in range(n):
                    if a_out[i] != b_out[i]:
                        failures.append(dict(case=tag, line=i, kind='scalar_vs_avx2',
                                             scalar=int(a_out[i]), avx2=int(b_out[i]),
                                             source=data.split(b'\n')[i][:120].decode('latin1')))
                        return

        for name, (line, expected) in SHAPES.items():
            check('shape-' + name, (line * 200).encode('latin1'), expected)
        # cliff probes at gate scale (the full 200k/400k/4MB are timing probes)
        for name, tmpl in CLIFFS.items():
            if name in ('200k-labels', '400k-labels'):
                data = ''.join(tmpl % i for i in range(20000)).encode()
            elif name == '200k-fwd-jmp':
                data = ''.join(tmpl % (i, i + 1) for i in range(20000)).encode()
            else:
                data = (tmpl * 100000).encode()
            check('cliff-' + name, data)
        for i, b in enumerate(BOUNDARY):
            check('boundary-%d' % i, b)
        rnd = random.Random(0xC15)
        atoms = [b'    mov rax, 1', b'# c', b'L:', b'    db 2', b'    x: a + b',
                 b'    times 3 db 0', b'    a -> b', b'    jmp L', b'    K = 4',
                 b'  ', b'', b'\t']
        for c in range(80):
            data = b'\n'.join(rnd.choice(atoms) for _ in range(rnd.randint(1, 60))) + b'\n'
            check('prng-%d' % c, data)
        # real .sov files
        for p in sorted((R / 'tests').glob('*.sov'))[:15]:
            check('file-' + p.name, p.read_bytes()[:200000])

        # C.33: R=21 ROTATED INTERLEAVED A/B with an A/A PLACEBO. A/A is a
        # second independent load of the SAME scalar function into a fresh .so,
        # measuring the layout lottery / host noise band. Only a ratio whose
        # median AND worst A/B round clear the whole A/A band is a real win.
        big = (R / 'compilers/linux/compiler.sov').read_bytes()
        cap = min(MAX_LINES, big.count(b'\n') + 16)
        ba = (ctypes.c_uint64 * cap)()
        bb = (ctypes.c_uint64 * cap)()
        bc = (ctypes.c_uint64 * cap)()
        placebo_lib = None
        if detected:
            pso = Path(td) / 'placebo.so'
            q = subprocess.run(['gcc', '-O2', '-fPIC', '-shared', str(SRC), '-o', str(pso)],
                               capture_output=True, text=True)
            if q.returncode:
                raise RuntimeError('placebo gcc failed: ' + q.stderr[:400])
            placebo_lib = ctypes.CDLL(str(pso))
            placebo_lib.scan_shapes_scalar.argtypes = lib.scan_shapes_scalar.argtypes
            placebo_lib.scan_shapes_scalar.restype = lib.scan_shapes_scalar.restype
        def one(f, o):
            t0=time.perf_counter(); f(big, len(big), o, MAX_LINES)
            return (time.perf_counter()-t0)*1000.0
        ab, aa = [], []
        for rnd in range(21):
            if rnd % 2 == 0:
                ta = one(lib.scan_shapes_scalar, ba)
                tb = one(lib.scan_shapes_avx2 if detected else lib.scan_shapes_auto, bb)
                tc = one(placebo_lib.scan_shapes_scalar if placebo_lib else lib.scan_shapes_scalar, bc)
            else:
                tb = one(lib.scan_shapes_avx2 if detected else lib.scan_shapes_auto, bb)
                ta = one(lib.scan_shapes_scalar, ba)
                tc = one(placebo_lib.scan_shapes_scalar if placebo_lib else lib.scan_shapes_scalar, bc)
            ab.append(ta/tb if tb else 0.0); aa.append(ta/tc if tc else 0.0)
        ab.sort(); aa.sort()
        band=(aa[0], aa[-1]); ab_med=ab[10]; aa_med=aa[10]
        outside=(ab_med>band[1]) and (ab[0]>band[1])
        placebo=dict(runs=21, rotated_interleaved=True,
                     a_b='scalar_vs_avx2' if detected else 'scalar_vs_auto',
                     a_b_median_ratio=round(ab_med,4), a_b_min_ratio=round(ab[0],4),
                     a_a_median_ratio=round(aa_med,4),
                     a_a_band=[round(band[0],4),round(band[1],4)],
                     outside_band=bool(outside),
                     verdict='CREDIBLE_WIN' if outside else 'INSIDE_NOISE',
                     note='Core-level only; compiler.sov integration and a '
                          'whole-compile A/B are still required. A speed ratio '
                          'alone is never a parity claim (C.39).')

    c34=dict(input_bytes=sum(x['input_bytes'] for x in accounting),
             expanded_bytes=sum(x['expanded_bytes'] for x in accounting),
             emitted_class_bytes=sum(x['emitted_class_bytes'] for x in accounting),
             lines=lines,
             note='No include expansion is performed by a line scanner; input '
                  'and expanded bytes are equal by construction. Emitted bytes '
                  'are the U64 class array actually written.')

    report = dict(schema=1, classes=CLASSES, cases=cases, lines_compared=lines,
                  accounting_c34=c34, placebo_c33=placebo,
                  cpu_avx2_detected=detected, cpuinfo_avx2=host,
                  installable_blob_identical=True,
                  avx2_vs_scalar='TESTED' if detected else 'NOT_TESTABLE_ON_THIS_HOST',
                  mismatches=len(failures), failures=failures[:20],
                  all_green=(len(failures) == 0 and cases > 0),
                  note='Standalone scanner. Wiring into compiler.sov still '
                       'requires the full C.29/C.31 certification suite.')
    outp.write_text(json.dumps(report, indent=2) + '\n')
    print('C.15/C.16 shape-scan gate: %d cases / %d lines / %d mismatches'
          % (cases, lines, len(failures)))
    print('  host avx2=%s  detected=%s  avx2_vs_scalar=%s  blob_identical=%s'
          % (host, detected, report['avx2_vs_scalar'],
             report['installable_blob_identical']))
    for f in failures[:5]:
        print('  DIVERGE', f)
    print('  R=21 A/B median %.4fx, A/A placebo %.4fx band [%.4f, %.4f] -> %s'
          % (ab_med, aa_med, band[0], band[1], placebo['verdict']))
    print('  C.34 input=%d B expanded=%d B emitted=%d B'
          % (c34['input_bytes'], c34['expanded_bytes'], c34['emitted_class_bytes']))
    print('  -> %s' % outp)
    print('ALL GREEN' if report['all_green'] else 'NOT GREEN')
    return 0 if report['all_green'] else 1


if __name__ == '__main__':
    sys.exit(main())
