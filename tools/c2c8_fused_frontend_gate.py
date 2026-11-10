#!/usr/bin/env python3
"""C.2-C.8 — counterexample-first CERTIFICATION of an INTEGRATED fused front end.

The restated list requires one read + one lexical pass + one emission; fuse the
whole front end; stable-ID work queue; zero-copy `(offset,length)` descriptors;
one interner with stable IDs / pre-sized open-addressed table; ID/hash dispatch;
arena emission; bounded fixups / branch relaxation; and a direct ELF with one
header / two PT_LOAD / zero section headers / <=3 writes+lseeks, byte-identical
to an oracle.

`tools/native_fused_frontend.c` is a HARNESS-ONLY prototype of exactly that
shape over a tiny descriptor language. It is NOT installed in `compiler.sov`.
The gate:

  1. builds SIX deliberately BROKEN variants and finds a 1-minimal failing
     fixture for EACH before trusting the fixed core (counterexample FIRST);
  2. differentially compares the fixed core against a CLEAN-ROOM Python
     reference on 500 real-identifier + PRNG cases (two table sizes were
     already covered by the C.4/C.5 gate; here the whole emitted ELF is
     compared byte for byte), and executes 50 real Linux ELFs;
  3. checks one `read`, one source scan, one lexical pass, zero allocations /
     zero unbounded string comparisons, one `write`, zero `lseek`, two
     PT_LOAD, zero section headers, and bounded fixup/relaxation on EVERY case;
  4. runs an R=21 rotated-interleaved, cold-process, no-warm-up A/B with an
     A/A placebo against a real allocating / 3-scan / 4-write baseline driver;
  5. records input, expanded, and emitted bytes with every aggregate (C.34).

Verdict ALL_GREEN is `CERTIFIED_NOT_INSTALLED`: a prototype certificate, NOT a
compiler rewrite, NOT a whole-compile deletion, and NOT parity/completion.

Usage: python3 tools/c2c8_fused_frontend_gate.py [--json OUT]
"""
import argparse
import ctypes
import hashlib
import itertools
import json
import os
import platform
import random
import re
import statistics
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
CORE = R / 'tools/native_fused_frontend.c'
DRIVER = R / 'tools/native_fused_frontend_driver.c'
OUT = E / 'C2_C8_fused_frontend_2026-11-09.json'
FIXTURE_DIR = E / 'C2_C8_fused_frontend_fixtures'
BASE = 0x400000
EHDR, PHDR, HDR = 64, 56, 64 + 2 * 56
CAP, MASK64 = 64, (1 << 64) - 1
SRC_CAP, OUT_CAP = 262144, 2 * 1024 * 1024
AB_SRC_CAP, AB_OUT_CAP = 262144, 8 * 1024 * 1024
COUNTER = itertools.count()

VARIANTS = ['BROKEN_INTERN', 'BROKEN_FIXUP', 'BROKEN_RELAX',
            'BROKEN_ELF', 'BROKEN_MULTIWRITE', 'BROKEN_TWOPASS']
SEEDS = {
    'BROKEN_INTERN': ['use x7', 'use x12', 'exit x12'],
    'BROKEN_FIXUP': ['use x7', 'exit x7'],
    'BROKEN_RELAX': ['use x7', 'jmp done', 'pad 130', 'label done', 'exit x7'],
    'BROKEN_ELF': ['use x7', 'exit x7'],
    'BROKEN_MULTIWRITE': ['use x7', 'exit x7'],
    'BROKEN_TWOPASS': ['use x7', 'exit x7'],
}


class Stats(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in (
        'read_calls', 'source_scans', 'lexical_passes', 'malloc_calls',
        'write_calls', 'lseek_calls', 'string_compare_calls',
        'dynamic_calls', 'fixup_count', 'relaxation_rounds', 'ids',
        'allocations')]


def sh(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def gcc(argv):
    r = subprocess.run(['gcc', '-O2'] + argv, cwd=R,
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('gcc failed: %s\n%s' % (' '.join(argv), r.stderr))


def compile_artifacts(td):
    libs = {}
    fixed_so = td / 'fused_fixed.so'
    gcc(['-fPIC', '-shared', str(CORE), '-o', str(fixed_so)])
    libs['fixed'] = load_so(fixed_so)
    for v in VARIANTS:
        so = td / ('fused_%s.so' % v)
        gcc(['-fPIC', '-shared', '-D' + v, str(CORE), '-o', str(so)])
        libs[v] = load_so(so)
    fd = td / 'fused_driver'
    bd = td / 'fused_driver_baseline'
    gcc(['-Itools', str(DRIVER), '-o', str(fd)])
    gcc(['-DBASELINE_MODE', '-Itools', str(DRIVER), '-o', str(bd)])
    return libs, fd, bd


def load_so(path):
    lib = ctypes.CDLL(str(path))
    fn = lib.fused_compile_file
    fn.restype = ctypes.c_int64
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                   ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64,
                   ctypes.POINTER(Stats), ctypes.POINTER(ctypes.c_uint64),
                   ctypes.POINTER(ctypes.c_uint64)]
    return (lib, fn)   # keep lib alive


def call(which, libs, src, td):
    j = next(COUNTER)
    in_p = td / ('in_%d.sov' % j)
    out_p = td / ('out_%d.bin' % j)
    in_p.write_bytes(src)
    srcbuf = ctypes.create_string_buffer(SRC_CAP)
    outbuf = ctypes.create_string_buffer(OUT_CAP)
    st = Stats()
    ilen = ctypes.c_uint64()
    ec = ctypes.c_uint64()
    _, fn = libs[which]
    rc = fn(str(in_p).encode(), str(out_p).encode(),
            ctypes.cast(srcbuf, ctypes.c_void_p), SRC_CAP,
            ctypes.cast(outbuf, ctypes.c_void_p), OUT_CAP,
            ctypes.byref(st), ctypes.byref(ilen), ctypes.byref(ec))
    b = outbuf.raw[:ilen.value]
    fb = out_p.read_bytes() if out_p.is_file() else b''
    return dict(rc=rc, bytes=b, file=fb, path=out_p,
                image_len=ilen.value, exit_code=ec.value,
                stats={n: getattr(st, n) for n, _ in Stats._fields_})


def signature(r):
    s = r['stats']
    b = r['bytes']
    phnum = struct.unpack_from('<H', b, 56)[0] if len(b) >= 58 else None
    shnum = struct.unpack_from('<H', b, 60)[0] if len(b) >= 62 else None
    return (b, r['file'], r['exit_code'], phnum, shnum,
            s['read_calls'], s['source_scans'], s['lexical_passes'],
            s['malloc_calls'], s['write_calls'], s['lseek_calls'],
            s['string_compare_calls'], s['dynamic_calls'],
            s['fixup_count'], s['relaxation_rounds'], s['ids'],
            s['allocations'])


def differs(which, libs, lines, td):
    src = ('\n'.join(lines) + '\n').encode()
    f = call('fixed', libs, src, td)
    b = call(which, libs, src, td)
    return signature(f) != signature(b), f, b


def valid(lines):
    if not any(x.startswith('exit ') for x in lines):
        return False
    for i, x in enumerate(lines):
        if x.startswith('jmp '):
            name = x[4:].strip()
            if not any(y == 'label ' + name for y in lines[i + 1:]):
                return False
    return True


def minimise(which, libs, seed, td):
    lines = list(seed)
    if not differs(which, libs, lines, td)[0]:
        return None
    changed = True
    while changed:
        changed = False
        for i in range(len(lines)):
            cand = lines[:i] + lines[i + 1:]
            if valid(cand) and differs(which, libs, cand, td)[0]:
                lines, changed = cand, True
                break
    return lines


# ----------------------------------------------------- clean-room reference
def fnv1a(b):
    h = 14695981039346656037
    for x in b:
        h ^= x
        h = (h * 1099511628211) & MASK64
    return h


def pack8(b):
    return int.from_bytes(b[:8], 'little')


def ref_intern(names):
    table = [0] * CAP
    entries = []
    ids = []
    for name in names:
        n = len(name)
        key = pack8(name)
        h = fnv1a(name) & (CAP - 1)
        hit = 0
        for _ in range(CAP):
            slot = table[h]
            if slot == 0:
                entries.append((n, key, name))
                table[h] = len(entries)
                hit = table[h]
                break
            e = entries[slot - 1]
            if e[0] == n and ((n <= 8 and e[1] == key) or
                              (n > 8 and e[2] == name)):
                hit = slot
                break
            h = (h + 1) & (CAP - 1)
        ids.append(hit)
    return ids


def keyword(t):
    return {'use': 1, 'label': 2, 'jmp': 3, 'pad': 4,
            'emit': 5, 'exit': 6}.get(t, 0)


def parse_uint(t):
    v = 0
    for c in t:
        if not c.isdigit():
            break
        v = v * 10 + ord(c) - 48
    return v


def ref_parse(src):
    ir, names = [], []
    for raw in src.decode().split('\n'):
        line = raw.rstrip(' \t\r').lstrip(' \t')
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        k = keyword(parts[0])
        if not k:
            continue
        tok = parts[1] if len(parts) > 1 else ''
        if k in (1, 2, 3, 6):
            names.append(tok.encode())
        ir.append(dict(k=k, tok=tok))
    id_of = {}
    for name, id_ in zip(names, ref_intern(names)):
        id_of.setdefault(name, id_)
    out = []
    for q in ir:
        k, tok = q['k'], q['tok']
        a = id_of.get(tok.encode(), 0) if k in (1, 2, 3, 6) else parse_uint(tok)
        if k == 4:
            size = a
        elif k == 5:
            size = 1
        elif k == 3:
            size = 2
        elif k == 6:
            size = 12
        else:
            size = 0
        out.append(dict(k=k, a=a, size=size, offset=0))
    return out


def p16(b, o, v): struct.pack_into('<H', b, o, v)
def p32(b, o, v): struct.pack_into('<I', b, o, v & 0xffffffff)
def p64(b, o, v): struct.pack_into('<Q', b, o, v & MASK64)


def ref_emit(src):
    ir = ref_parse(src)
    jmp_n = sum(1 for q in ir if q['k'] == 3)
    rounds = 0
    while rounds < jmp_n + 1:
        off, labels = 0, {}
        for q in ir:
            q['offset'] = off
            if q['k'] == 2:
                labels[q['a']] = off
            off += q['size']
        promoted = 0
        for q in ir:
            if q['k'] != 3 or q['size'] != 2:
                continue
            d = labels.get(q['a'], 0) - (q['offset'] + q['size'])
            if d > 127 or d < -128:
                q['size'] = 5
                promoted += 1
        rounds += 1
        if not promoted:
            break
    code_len = sum(q['size'] for q in ir)
    data_off = (HDR + code_len + 4095) & ~4095
    file_len = data_off + len(src)
    out = bytearray(file_len)
    out[0:8] = b'\x7fELF\x02\x01\x01\x00'
    p16(out, 16, 2); p16(out, 18, 62); p32(out, 20, 1)
    p64(out, 24, BASE + HDR); p64(out, 32, EHDR); p64(out, 40, 0)
    p32(out, 48, 0); p16(out, 52, EHDR); p16(out, 54, PHDR)
    p16(out, 56, 2); p16(out, 58, 0); p16(out, 60, 0); p16(out, 62, 0)
    p32(out, 64, 1); p32(out, 68, 5); p64(out, 72, 0)
    p64(out, 80, BASE); p64(out, 88, BASE)
    p64(out, 96, HDR + code_len); p64(out, 104, HDR + code_len)
    p64(out, 112, 4096)
    p32(out, 120, 1); p32(out, 124, 6); p64(out, 128, data_off)
    p64(out, 136, BASE + data_off); p64(out, 144, BASE + data_off)
    p64(out, 152, len(src)); p64(out, 160, len(src)); p64(out, 168, 4096)
    code = bytearray()
    fixups = []
    for q in ir:
        k, a = q['k'], q['a']
        if k == 4:
            code += b'\x90' * q['size']
        elif k == 5:
            code.append(a & 255)
        elif k == 3:
            d = (next((x['offset'] for x in reversed(ir)
                       if x['k'] == 2 and x['a'] == a), 0)
                 - (q['offset'] + q['size']))
            if q['size'] == 2:
                code.append(0xeb)
                code.append(d & 255)
            else:
                code.append(0xe9)
                code += struct.pack('<i', d)
        elif k == 6:
            code.append(0xbf)
            fixups.append((len(code), a))
            code += b'\x00' * 4
            code.append(0xb8); code += struct.pack('<I', 60)
            code += b'\x0f\x05'
    out[HDR:HDR + len(code)] = code
    for off, id_ in fixups:
        p32(out, HDR + off, id_ & 255)
    out[data_off:data_off + len(src)] = src
    near = sum(1 for q in ir if q['k'] == 3 and q['size'] == 5)
    short = sum(1 for q in ir if q['k'] == 3 and q['size'] == 2)
    return dict(bytes=bytes(out), exit_code=fixups[0][1] & 255 if fixups else 0,
                near=near, short=short, fixups=len(fixups),
                rounds=rounds, code_len=code_len, data_off=data_off)


def check_fixed(r, src, execute=False):
    s, b = r['stats'], r['bytes']
    phnum = struct.unpack_from('<H', b, 56)[0]
    shnum = struct.unpack_from('<H', b, 60)[0]
    shoff = struct.unpack_from('<Q', b, 40)[0]
    phoff = struct.unpack_from('<Q', b, 32)[0]
    pt0 = struct.unpack_from('<I', b, 64)[0]
    pt1 = struct.unpack_from('<I', b, 120)[0]
    checks = dict(
        rc_ok=r['rc'] == 0 and len(b) == r['image_len'] and b == r['file'],
        one_read=s['read_calls'] == 1,
        one_scan=s['source_scans'] == 1 and s['lexical_passes'] == 1,
        zero_alloc=s['allocations'] == 0 and s['malloc_calls'] == 0,
        zero_string_compare=s['string_compare_calls'] == 0,
        low_writes=s['write_calls'] + s['lseek_calls'] <= 3,
        two_ptload=phnum == 2 and pt0 == 1 and pt1 == 1 and phoff == EHDR,
        zero_section_headers=shnum == 0 and shoff == 0,
        bounded_fixups=s['fixup_count'] >= 1 and s['fixup_count'] <= 4096,
        bounded_relaxation=s['relaxation_rounds'] >= 1,
        ids=s['ids'] >= 1,
        data_segment=b[-len(src):] == src if src else True)
    exec_ok, rc = None, None
    if execute:
        os.chmod(r['path'], 0o755)
        p = subprocess.run([str(r['path'])], capture_output=True)
        rc = p.returncode
        exec_ok = (rc == (r['exit_code'] & 255))
        checks['executed_semantics'] = exec_ok
    return dict(ok=all(checks.values()), checks=checks,
                executed_rc=rc, executed_ok=exec_ok)


def corpus():
    txt = (R / 'compilers/linux/compiler.sov').read_text(errors='replace')[:200000]
    real = list(dict.fromkeys(re.findall(r'[A-Za-z_][A-Za-z0-9_]{0,23}', txt)))[:800]
    rnd = random.Random(20261109)
    alpha = b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789'
    pool = [r.encode() for r in real] + [b'x7', b'x12', b'v8', b'v20'] + [
        bytes(rnd.choice(alpha) for _ in range(rnd.randrange(1, 25)))
        for _ in range(200)]
    cases = []
    for ci in range(500):
        lines = []
        for _ in range(rnd.randrange(1, 6)):
            lines.append('use ' + rnd.choice(pool).decode())
        label = 'L%d' % ci
        lines.append('jmp ' + label)
        lines.append('pad ' + str(rnd.choice([0, 1, 2, 7, 64, 127, 128,
                                               130, 180, 200])))
        lines.append('label ' + label)
        if rnd.random() < 0.5:
            lines.append('emit 144')
        lines.append('exit ' + rnd.choice(pool).decode())
        if rnd.random() < 0.3:
            lines.append('exit ' + rnd.choice(pool).decode())
        cases.append(lines)
    return cases


def synthetic_source():
    lines = []
    for i in range(600):
        lines += ['use v%d' % i, 'jmp L%d' % i, 'pad 7',
                  'label L%d' % i, 'emit 144', 'exit v%d' % i]
    return ('\n'.join(lines) + '\n').encode()


def parse_driver(out):
    d = dict((k, int(v)) for k, v in re.findall(r'(\w+)=(-?\d+)', out))
    if d.get('rc') != 0:
        raise RuntimeError('driver failed: %s' % out.strip())
    return d


def ab(td, fixed_driver, baseline_driver):
    src = synthetic_source()
    src_path = td / 'ab_source.sov'
    src_path.write_bytes(src)
    argv_tail = [str(src_path), '/dev/null',
                 str(AB_SRC_CAP), str(AB_OUT_CAP)]
    fast, slow, aa = [], [], []
    fields = {}
    for k in range(21):
        order = [('fast', fast, fixed_driver), ('slow', slow, baseline_driver),
                 ('aa', aa, fixed_driver)]
        if k % 2:
            order.reverse()
        for label, acc, driver in order:
            p = subprocess.run([str(driver)] + argv_tail, cwd=R,
                               capture_output=True, text=True)
            d = parse_driver(p.stdout)
            acc.append(d['elapsed_ns'] / 1e6)
            if label == 'fast':
                fields = d
    fm, sm, am = statistics.median(fast), statistics.median(slow), statistics.median(aa)
    ratio = sm / fm if fm else None
    p_min_pct = 100 * (min(aa) - min(fast)) / min(fast)
    p_med_pct = 100 * (am - fm) / fm
    d_med_pct = 100 * (sm - fm) / fm
    lo = min(0.0, p_min_pct, p_med_pct) - 0.5
    hi = max(0.0, p_min_pct, p_med_pct) + 0.5
    outside = not (lo <= d_med_pct <= hi)
    credible = bool(ratio and ratio > 1.0 and outside and d_med_pct > hi)
    return dict(R=21, rotation='alternating reversed every round',
                cold_process=True, warmups=0, timeouts_used=0,
                output='/dev/null', no_warm_path=True,
                host=' '.join([platform.node(), platform.system(), platform.machine()]),
                size=dict(input_bytes=fields['source_len'],
                          expanded_bytes=fields['source_len'],
                          emitted_bytes=fields['image_len'],
                          src_cap=AB_SRC_CAP, out_cap=AB_OUT_CAP),
                fixed_min_ms=round(min(fast), 5),
                fixed_median_ms=round(fm, 5),
                baseline_min_ms=round(min(slow), 5),
                baseline_median_ms=round(sm, 5),
                aa_min_ms=round(min(aa), 5), aa_median_ms=round(am, 5),
                median_speedup=round(ratio, 4) if ratio else None,
                b_vs_a_median_pct=round(d_med_pct, 3),
                placebo_min_pct=round(p_min_pct, 3),
                placebo_median_pct=round(p_med_pct, 3),
                aa_band_pct=[round(lo, 3), round(hi, 3)],
                outside_band=outside,
                verdict='CREDIBLE_WIN' if credible else 'INSIDE_NOISE',
                driver_stats=dict(
                    fixed=dict(read_calls=fields['read_calls'],
                               source_scans=fields['source_scans'],
                               lexical_passes=fields['lexical_passes'],
                               allocations=fields['allocations'],
                               malloc_calls=fields['malloc_calls'],
                               write_calls=fields['write_calls'],
                               lseek_calls=fields['lseek_calls'],
                               string_compare_calls=fields['string_compare_calls'],
                               dynamic_calls=fields['dynamic_calls'],
                               fixup_count=fields['fixup_count'],
                               relaxation_rounds=fields['relaxation_rounds'],
                               ids=fields['ids'])),
                note='CORE-LEVEL / cold-process only. Input and expanded bytes '
                     'are the descriptor source; emitted bytes are the ELF. '
                     'Not a whole-compile or parity claim.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(OUT))
    a = ap.parse_args()
    out = Path(a.json)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    report = dict(schema=1, date='2026-11-09', pass_='PASS 14',
                  verdict='FAIL', install_status='CERTIFIED_NOT_INSTALLED',
                  whole_compile_deletion='NOT_LANDED',
                  claim='Harness-only integrated prototype. No compiler bytes '
                        'changed, no whole-compile speed claim, no '
                        'parity/completion/absolute-superlative claim.',
                  host=' '.join([platform.node(), platform.system(),
                                 platform.machine()]),
                  installed_compiler_sha256=sh(R / 'compilers/linux/compiler'))
    with tempfile.TemporaryDirectory(prefix='c2c8-') as td_s:
        td = Path(td_s)
        libs, fixed_driver, baseline_driver = compile_artifacts(td)

        # 1) counterexample FIRST for every broken variant
        report['counterexamples'] = {}
        for v in VARIANTS:
            best = minimise(v, libs, SEEDS[v], td)
            if best is None:
                report['counterexamples'][v] = dict(found=False)
                continue
            src = ('\n'.join(best) + '\n').encode()
            fx = FIXTURE_DIR / ('%s.sov' % v)
            fx.write_bytes(src)
            detected, f, b = differs(v, libs, best, td)
            ref = ref_emit(src)
            chk = check_fixed(f, src, execute=True)
            report['counterexamples'][v] = dict(
                found=True, lines=len(best), bytes=len(src),
                text=src.decode(), fixture=str(fx), detected=detected,
                fixed_matches_reference=f['bytes'] == ref['bytes'] and
                                        f['exit_code'] == ref['exit_code'],
                fixed_stats_ok=chk['ok'], fixed_checks=chk['checks'],
                executed_rc=chk['executed_rc'],
                executed_ok=chk['executed_ok'],
                broken_image_len=b['image_len'],
                fixed_image_len=f['image_len'],
                method='1-minimal delta debugging over source lines; '
                       'signature = emitted bytes + file bytes + exit code '
                       '+ all accounting counters + ELF phnum/shnum')

        # 2) whole-ELF clean-room differential + executed semantics
        cases = corpus()
        mism, executed, exec_bad = [], 0, 0
        near_cases = short_cases = 0
        total_in = total_expanded = total_emitted = 0
        for ci, lines in enumerate(cases):
            src = ('\n'.join(lines) + '\n').encode()
            r = call('fixed', libs, src, td)
            ref = ref_emit(src)
            chk = check_fixed(r, src, execute=(ci < 50))
            total_in += len(src)
            total_expanded += len(src)
            total_emitted += r['image_len']
            if r['bytes'] != ref['bytes'] or r['exit_code'] != ref['exit_code']:
                mism.append(dict(case=ci, kind='reference_bytes'))
            if not chk['ok']:
                mism.append(dict(case=ci, kind='fixed_constraints',
                                 checks=chk['checks']))
            if ci < 50:
                executed += 1
                if not chk['executed_ok']:
                    exec_bad += 1
            if ref['near']:
                near_cases += 1
            else:
                short_cases += 1
        report['differential'] = dict(
            cases=len(cases), comparisons=len(cases), mismatches=len(mism),
            first=mism[:5], executed_cases=executed,
            executed_mismatches=exec_bad,
            near_branch_cases=near_cases, short_branch_cases=short_cases,
            input_bytes_total=total_in, expanded_bytes_total=total_expanded,
            emitted_bytes_total=total_emitted,
            note='Every number above is accompanied by input, expanded, and '
                 'emitted bytes (C.34). Expanded == input for this descriptor '
                 'language because it has no includes.')

        # 4) R=21 cold-process placebo-controlled A/B
        report['core_ab'] = ab(td, fixed_driver, baseline_driver)

    cx = report['counterexamples']
    ok = (all(cx.get(v, {}).get('found') is True for v in VARIANTS)
          and all(cx[v]['detected'] is True for v in VARIANTS)
          and all(cx[v]['bytes'] <= 64 for v in VARIANTS)
          and all(cx[v]['fixed_matches_reference'] is True for v in VARIANTS)
          and all(cx[v]['fixed_stats_ok'] is True for v in VARIANTS)
          and all(cx[v]['executed_ok'] is True for v in VARIANTS)
          and report['differential']['cases'] >= 500
          and report['differential']['mismatches'] == 0
          and report['differential']['executed_cases'] >= 50
          and report['differential']['executed_mismatches'] == 0
          and report['differential']['near_branch_cases'] > 0
          and report['differential']['short_branch_cases'] > 0
          and report['core_ab']['verdict'] == 'CREDIBLE_WIN'
          and report['core_ab']['R'] == 21
          and report['core_ab']['cold_process'] is True
          and report['core_ab']['warmups'] == 0
          and report['core_ab']['timeouts_used'] == 0
          and report['core_ab']['driver_stats']['fixed']['source_scans'] == 1
          and report['core_ab']['driver_stats']['fixed']['write_calls'] == 1
          and report['core_ab']['driver_stats']['fixed']['lseek_calls'] == 0
          and report['core_ab']['driver_stats']['fixed']['allocations'] == 0
          and report['install_status'] == 'CERTIFIED_NOT_INSTALLED'
          and report['whole_compile_deletion'] == 'NOT_LANDED')
    report['verdict'] = 'ALL_GREEN' if ok else 'FAIL'
    report['checks'] = dict(
        six_counterexamples_first=all(cx.get(v, {}).get('found') is True
                                      for v in VARIANTS),
        all_broken_detected=all(cx[v]['detected'] is True for v in VARIANTS),
        all_fixtures_minimal=all(cx[v]['bytes'] <= 64 for v in VARIANTS),
        fixed_matches_clean_room_on_fixtures=all(
            cx[v]['fixed_matches_reference'] is True for v in VARIANTS),
        whole_elf_differential=report['differential']['mismatches'] == 0,
        executed_elf_semantics=report['differential']['executed_mismatches'] == 0,
        short_and_near_relaxation=report['differential']['near_branch_cases'] > 0
                                  and report['differential']['short_branch_cases'] > 0,
        one_read_one_pass_one_write=all(
            cx[v]['fixed_checks']['one_read'] and
            cx[v]['fixed_checks']['one_scan'] and
            cx[v]['fixed_checks']['low_writes'] for v in VARIANTS),
        two_ptload_zero_sections=all(
            cx[v]['fixed_checks']['two_ptload'] and
            cx[v]['fixed_checks']['zero_section_headers'] for v in VARIANTS),
        ab_credible=report['core_ab']['verdict'] == 'CREDIBLE_WIN',
        not_installed=report['install_status'] == 'CERTIFIED_NOT_INSTALLED')
    out.write_text(json.dumps(report, indent=2) + '\n')
    print('C.2-C.8 fused-frontend gate: %s' % report['verdict'])
    print('  counterexamples: %d/%d, max %d B; whole-ELF %d cases / %d mismatches; executed %d/%d' %
          (sum(1 for v in VARIANTS if cx[v]['found']), len(VARIANTS),
           max(cx[v]['bytes'] for v in VARIANTS),
           report['differential']['cases'], report['differential']['mismatches'],
           report['differential']['executed_cases'] -
           report['differential']['executed_mismatches'],
           report['differential']['executed_cases']))
    print('  R=21 A/B %sx (%s), placebo band %s%%; installed=%s' %
          (report['core_ab']['median_speedup'], report['core_ab']['verdict'],
           report['core_ab']['aa_band_pct'], report['install_status']))
    print('  -> %s' % out)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
