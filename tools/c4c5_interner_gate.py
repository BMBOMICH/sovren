#!/usr/bin/env python3
"""C.4/C.5 — counterexample-first certification of the STABLE-ID INTERNER.

The restated list says only `ml_collect_cached` landed; `ml_collect`,
`lshf2`, `_sov_inl2_scan`, `intern_kid_n_full`, `kgrow_ht` are still hot, and
string-keyed dispatch / allocation-free expression parsing are open.

This gate builds a REAL prototype core (`tools/native_stable_interner.c`):

  * one PRE-SIZED power-of-two open-addressed table (no fixed 4,096-slot hash,
    no 256 KiB zero-fill band);
  * STABLE integer IDs;
  * inline <=8-byte names packed into a u64, long names FNV-1a hashed and
    exact-compared ONLY on a hash-slot hit;
  * ID/hash dispatch with zero string comparisons.

Counterexample FIRST: a `-DBROKEN_INTERN` build skips the exact compare on a
hash-slot hit; 1-minimal delta debugging finds the smallest name sequence whose
stable-ID output differs. Only then is the fixed core compared against a
clean-room Python reference (real compiler identifiers + PRNG fuzz, two table
sizes) and its ID/hash dispatch checked. A relocation-free 633 B Sovren twin is
built and passed through `nb_disasm_verify`; an R=21 rotated-interleaved A/B
with an A/A placebo compares the core against the string-chain / 4,096-slot /
256 KiB-zero-fill baseline model.

Verdict ALL_GREEN is a PROTOTYPE certificate, `CERTIFIED_NOT_INSTALLED`. It is
NOT a compiler rewrite, NOT a whole-compile speed claim and NOT parity.

Usage: python3 tools/c4c5_interner_gate.py [--json OUT]
"""
import argparse
import ctypes
import hashlib
import json
import platform
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
C = R / 'tools/native_stable_interner.c'
TWIN_SRC = R / 'tools/native_stable_interner_twin.c'
BUILD_TOOL = R / 'tools/native/build_native_reader.py'
TWIN = E / 'C4_C5_stable_interner_twin.sov'
BUILD_JSON = E / 'C4_C5_stable_interner_build.json'
NB_JSON = E / 'C29_nb_disasm_verify.json'
FIXTURE = E / 'C4_C5_interner_counterexample.txt'
CONST = 0x9e3779b97f4a7c15
MASK64 = (1 << 64) - 1


class Interner(ctypes.Structure):
    _fields_ = [('table', ctypes.POINTER(ctypes.c_uint64)),
                ('cap', ctypes.c_uint64),
                ('inl', ctypes.POINTER(ctypes.c_uint64)),
                ('len', ctypes.POINTER(ctypes.c_uint64)),
                ('ptr', ctypes.POINTER(ctypes.c_void_p)),
                ('n', ctypes.c_uint64),
                ('max', ctypes.c_uint64)]


class Baseline(ctypes.Structure):
    _fields_ = [('ht', ctypes.POINTER(ctypes.c_uint64)),
                ('nt', ctypes.POINTER(ctypes.c_ubyte)),
                ('names', ctypes.POINTER(ctypes.c_void_p)),
                ('lens', ctypes.POINTER(ctypes.c_uint64)),
                ('n', ctypes.c_uint64),
                ('max', ctypes.c_uint64)]


def build(td, broken=False):
    so = Path(td) / ('intern_broken.so' if broken else 'intern.so')
    cmd = ['gcc', '-O2', '-fPIC', '-shared', str(C), '-o', str(so)]
    if broken:
        cmd.insert(1, '-DBROKEN_INTERN')
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    lib = ctypes.CDLL(str(so))
    lib.intern_init.argtypes = [ctypes.POINTER(Interner)]
    lib.intern_init.restype = None
    lib.intern_lookup_or_add.argtypes = [ctypes.POINTER(Interner),
                                         ctypes.c_char_p, ctypes.c_uint64]
    lib.intern_lookup_or_add.restype = ctypes.c_uint64
    lib.intern_hash.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
    lib.intern_hash.restype = ctypes.c_uint64
    lib.id_dispatch.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
    lib.id_dispatch.restype = ctypes.c_uint64
    lib.baseline_init.argtypes = [ctypes.POINTER(Baseline), ctypes.c_uint64]
    lib.baseline_init.restype = None
    lib.baseline_reset.argtypes = [ctypes.POINTER(Baseline)]
    lib.baseline_reset.restype = None
    lib.baseline_free.argtypes = [ctypes.POINTER(Baseline)]
    lib.baseline_free.restype = None
    lib.baseline_lookup_or_add.argtypes = [ctypes.POINTER(Baseline),
                                           ctypes.c_char_p, ctypes.c_uint64]
    lib.baseline_lookup_or_add.restype = ctypes.c_uint64
    return lib


def prep(names):
    bufs = [ctypes.create_string_buffer(n) for n in names]
    return names, bufs


def run_fixed(lib, names, bufs=None, cap=64, maxn=None):
    if bufs is None:
        names, bufs = prep(names)
    maxn = maxn or (len(names) + 16)
    table = (ctypes.c_uint64 * cap)()
    inl = (ctypes.c_uint64 * maxn)()
    lens = (ctypes.c_uint64 * maxn)()
    ptrs = (ctypes.c_void_p * maxn)()
    for i, b in enumerate(bufs):
        ptrs[i] = ctypes.cast(b, ctypes.c_void_p)
    it = Interner(ctypes.cast(table, ctypes.POINTER(ctypes.c_uint64)), cap,
                  ctypes.cast(inl, ctypes.POINTER(ctypes.c_uint64)),
                  ctypes.cast(lens, ctypes.POINTER(ctypes.c_uint64)),
                  ctypes.cast(ptrs, ctypes.POINTER(ctypes.c_void_p)), 0, maxn)
    lib.intern_init(ctypes.byref(it))
    out = []
    for n in names:
        out.append(lib.intern_lookup_or_add(ctypes.byref(it), n, len(n)))
    return out


def run_baseline(lib, names, maxn=None):
    maxn = maxn or (len(names) + 16)
    b = Baseline()
    lib.baseline_init(ctypes.byref(b), maxn)
    out = []
    try:
        for n in names:
            out.append(lib.baseline_lookup_or_add(ctypes.byref(b), n, len(n)))
    finally:
        lib.baseline_free(ctypes.byref(b))
    return out


# ------------------------------------------------ clean-room Python reference
def fnv1a(name):
    h = 14695981039346656037
    for b in name:
        h ^= b
        h = (h * 1099511628211) & MASK64
    return h


def pack8(name):
    k = 0
    for i, b in enumerate(name[:8]):
        k |= b << (8 * i)
    return k


def ref_intern(names, cap):
    table = [0] * cap
    entries = []
    ids = []
    for name in names:
        ln = len(name)
        key = pack8(name)
        h = fnv1a(name) & (cap - 1)
        hit = 0
        for _ in range(cap):
            slot = table[h]
            if slot == 0:
                entries.append((ln, key, name))
                table[h] = len(entries)
                hit = table[h]
                break
            e = entries[slot - 1]
            if e[0] == ln and ((ln <= 8 and e[1] == key) or
                               (ln > 8 and e[2] == name)):
                hit = slot
                break
            h = (h + 1) & (cap - 1)
        ids.append(hit)
    return ids


def ref_dispatch(id_, h):
    return (h ^ (id_ * CONST)) & MASK64 & 7


def differs(fixed, broken, names, cap=16):
    return run_fixed(fixed, names, cap=cap) != run_fixed(broken, names, cap=cap)


def minimise(fixed, broken, seed, cap=16):
    names = list(seed)
    if not differs(fixed, broken, names, cap):
        return None
    changed = True
    while changed:
        changed = False
        for i in range(len(names)):
            cand = names[:i] + names[i + 1:]
            if cand and differs(fixed, broken, cand, cap):
                names, changed = cand, True
                break
    return names


def find_collision(cap=16):
    seen = {}
    for i in range(100000):
        n = b'v' + str(i).encode()
        slot = fnv1a(n) & (cap - 1)
        if slot in seen:
            return seen[slot], n
        seen[slot] = n
    raise RuntimeError('no collision found')


def corpus():
    txt = (R / 'compilers/linux/compiler.sov').read_text(errors='replace')
    real = list(dict.fromkeys(re.findall(r'[A-Za-z_][A-Za-z0-9_]{0,23}', txt)))[:800]
    rnd = random.Random(20261109)
    alpha = b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789'
    pool = [r.encode() for r in real] + [
        bytes(rnd.choice(alpha) for _ in range(rnd.randrange(1, 25)))
        for _ in range(800)]
    cases = [[rnd.choice(pool) for _ in range(30)] for _ in range(500)]
    return cases


def make_fixed_state(lib, names, bufs, cap, maxn):
    table = (ctypes.c_uint64 * cap)()
    inl = (ctypes.c_uint64 * maxn)()
    lens = (ctypes.c_uint64 * maxn)()
    ptrs = (ctypes.c_void_p * maxn)()
    for i, b in enumerate(bufs):
        ptrs[i] = ctypes.cast(b, ctypes.c_void_p)
    it = Interner(ctypes.cast(table, ctypes.POINTER(ctypes.c_uint64)), cap,
                  ctypes.cast(inl, ctypes.POINTER(ctypes.c_uint64)),
                  ctypes.cast(lens, ctypes.POINTER(ctypes.c_uint64)),
                  ctypes.cast(ptrs, ctypes.POINTER(ctypes.c_void_p)), 0, maxn)
    # Keep the arrays alive; intern_init resets table + n each run.
    return dict(it=it, keep=(table, inl, lens, ptrs))


def run_fixed_prealloc(lib, names, state):
    it = state['it']
    lib.intern_init(ctypes.byref(it))
    out = []
    for n in names:
        out.append(lib.intern_lookup_or_add(ctypes.byref(it), n, len(n)))
    return out


def make_baseline_state(lib, maxn):
    b = Baseline()
    lib.baseline_init(ctypes.byref(b), maxn)
    return b


def run_baseline_prealloc(lib, names, state):
    b = state
    lib.baseline_reset(ctypes.byref(b))
    out = []
    for n in names:
        out.append(lib.baseline_lookup_or_add(ctypes.byref(b), n, len(n)))
    return out


def ab_core(lib, runs=21):
    txt = (R / 'compilers/linux/compiler.sov').read_text(errors='replace')
    real = list(dict.fromkeys(re.findall(r'[A-Za-z_][A-Za-z0-9_]{0,23}', txt)))[:4000]
    names = (([r.encode() for r in real]) * 6)[:20000]
    names, bufs = prep(names)
    cap, maxn = 8192, 25000
    fstate = make_fixed_state(lib, names, bufs, cap, maxn)
    bstate = make_baseline_state(lib, maxn)
    fast, slow, aa = [], [], []
    try:
        for k in range(runs):
            order = [('fast', fast), ('slow', slow), ('aa', aa)]
            if k % 2:
                order.reverse()
            for which, acc in order:
                t0 = time.perf_counter()
                if which == 'slow':
                    run_baseline_prealloc(lib, names, bstate)
                else:
                    run_fixed_prealloc(lib, names, fstate)
                acc.append((time.perf_counter() - t0) * 1000.0)
    finally:
        lib.baseline_free(ctypes.byref(bstate))
    fm, sm, am = statistics.median(fast), statistics.median(slow), statistics.median(aa)
    ratio = sm / fm if fm else None
    # C.33 placebo band in PERCENT, exactly like tools/ab_gate.py: min+median
    # of the A/A side, widened by 0.5 percentage points. A single per-run
    # outlier must not be allowed to define an enormous band.
    p_min_pct = 100 * (min(aa) - min(fast)) / min(fast)
    p_med_pct = 100 * (am - fm) / fm
    d_med_pct = 100 * (sm - fm) / fm
    lo = min(0.0, p_min_pct, p_med_pct) - 0.5
    hi = max(0.0, p_min_pct, p_med_pct) + 0.5
    outside = not (lo <= d_med_pct <= hi)
    credible = bool(ratio and ratio > 1.0 and outside and d_med_pct > 0)
    return dict(runs=runs, names=len(names), cap=cap, maxn=maxn,
                fixed_median_ms=round(fm, 5), baseline_median_ms=round(sm, 5),
                aa_median_ms=round(am, 5), median_speedup=round(ratio, 4) if ratio else None,
                b_vs_a_median_pct=round(d_med_pct, 3),
                placebo_min_pct=round(p_min_pct, 3),
                placebo_median_pct=round(p_med_pct, 3),
                aa_band_pct=[round(lo, 3), round(hi, 3)],
                outside_band=outside,
                verdict='CREDIBLE_WIN' if credible else 'INSIDE_NOISE',
                unfair_draft_median_speedup=0.4112,
                unfair_draft_note=('First A/B allocated 65,536-slot ctypes arrays '
                                   'inside the timed loop and gave 0.4112x; that was '
                                   'Python allocation noise, not core cost. Buffers '
                                   'are now preallocated and only C reset work is timed.'),
                note='CORE-LEVEL only. Baseline = string-compare chain + 4,096-slot '
                     'hash + 256 KiB zero-fill. Not a whole-compile or parity claim.')


def twin_build():
    r = subprocess.run([sys.executable, str(BUILD_TOOL),
                        '--source', str(TWIN_SRC),
                        '--entry', 'intern_lookup_or_add',
                        '--symbol', 'emit_nt_stable_intern',
                        '--out', str(TWIN), '--json', str(BUILD_JSON)],
                       cwd=R, capture_output=True, text=True, timeout=300)
    bj = json.loads(BUILD_JSON.read_text()) if BUILD_JSON.is_file() else {}
    return dict(rc=r.returncode, report=bj,
                verdict=bj.get('verdict'),
                no_relocations=bj.get('checks', {}).get('no_relocations'),
                no_undefined=bj.get('checks', {}).get('no_undefined_symbols'),
                text_bytes=bj.get('text_bytes'),
                text_sha=bj.get('text_sha256'))


def nb_check():
    r = subprocess.run([sys.executable, 'tools/nb_disasm_verify.py',
                        '--json', str(NB_JSON)], cwd=R,
                       capture_output=True, text=True, timeout=300)
    nj = json.loads(NB_JSON.read_text()) if NB_JSON.is_file() else {}
    pair = next((x for x in nj.get('results', [])
                 if x.get('blob') == 'pass14_stable_interner'), {})
    dis = pair.get('disasm', {})
    return dict(rc=r.returncode, blobs=nj.get('blobs'), ok=nj.get('ok'),
                pair=pair, sha_match=pair.get('sha_match'),
                roundtrip=dis.get('roundtrip'), bad=dis.get('bad'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C4_C5_stable_interner_2026-11-09.json'))
    a = ap.parse_args()
    out = Path(a.json)
    rep = dict(schema=1, date='2026-11-09', pass_='PASS 14',
               host=' '.join([platform.node(), platform.system(), platform.machine()]),
               verdict='FAIL', install_status='CERTIFIED_NOT_INSTALLED',
               whole_compile_deletion='NOT_LANDED',
               claim='Prototype core only. No compiler bytes changed, no '
                     'whole-compile speed claim, no parity/completion claim.')
    with tempfile.TemporaryDirectory(prefix='intern-') as td:
        fixed = build(td)
        broken = build(td, broken=True)

        # 1) counterexample FIRST
        a1, b1 = find_collision(16)
        seed = [a1, b1] + [b'x' + str(i).encode() for i in range(20)]
        best = minimise(fixed, broken, seed, 16)
        rep['counterexample'] = dict(
            found=best is not None,
            names=[n.decode() for n in best] if best else None,
            lines=len(best) if best else None,
            bytes=sum(len(n) + 1 for n in best) if best else None,
            text=(b'\n'.join(best) + b'\n').decode() if best else None,
            method='1-minimal delta debugging over a name sequence; BROKEN '
                   'skips exact compare on a hash-slot hit')
        if best is None:
            out.write_text(json.dumps(rep, indent=2) + '\n')
            print('C.4/C.5 interner gate: FAIL (no counterexample)')
            return 1
        FIXTURE.write_bytes(b'\n'.join(best) + b'\n')
        rep['counterexample']['fixture'] = str(FIXTURE)
        rep['broken_detected_on_counterexample'] = differs(
            fixed, broken, best, 16)

        # 2) fixed vs clean-room reference + ID/hash dispatch
        cases = corpus()
        mism, dispatch_checks, dispatch_bad = [], 0, 0
        for ci, names in enumerate(cases):
            for cap in (16, 64):
                got = run_fixed(fixed, names, cap=cap)
                want = ref_intern(names, cap)
                if got != want:
                    mism.append(dict(case=ci, cap=cap, first_diff=next(
                        (i for i, (x, y) in enumerate(zip(got, want)) if x != y), None)))
            for n, id_ in zip(names, run_fixed(fixed, names, cap=64)):
                h = fixed.intern_hash(n, len(n))
                d = fixed.id_dispatch(id_, h)
                w = ref_dispatch(id_, h)
                dispatch_checks += 1
                if d != w:
                    dispatch_bad += 1
        rep['differential'] = dict(cases=len(cases), caps=[16, 64],
                                   comparisons=len(cases) * 2,
                                   mismatches=len(mism), first=mism[:5],
                                   dispatch_checks=dispatch_checks,
                                   dispatch_mismatches=dispatch_bad)

        # 3) core A/B + 4) twin / nb_disasm
        rep['core_ab'] = ab_core(fixed)
        rep['twin'] = twin_build()
        rep['nb_disasm'] = nb_check()

    ok = (rep['counterexample']['found']
          and rep['counterexample']['bytes'] <= 32
          and rep['broken_detected_on_counterexample']
          and rep['differential']['cases'] >= 500
          and rep['differential']['mismatches'] == 0
          and rep['differential']['dispatch_mismatches'] == 0
          and rep['core_ab']['verdict'] == 'CREDIBLE_WIN'
          and rep['twin']['verdict'] == 'PASS'
          and rep['twin']['no_relocations'] is True
          and rep['twin']['no_undefined'] is True
          and rep['twin']['text_bytes'] == 633
          and rep['nb_disasm']['rc'] == 0
          and rep['nb_disasm']['ok'] == rep['nb_disasm']['blobs']
          and rep['nb_disasm']['blobs'] >= 6
          and rep['nb_disasm']['sha_match'] is True
          and rep['nb_disasm']['roundtrip'] is True
          and rep['nb_disasm']['bad'] == []
          and rep['install_status'] == 'CERTIFIED_NOT_INSTALLED')
    rep['verdict'] = 'ALL_GREEN' if ok else 'FAIL'
    rep['checks'] = dict(
        counterexample_first=rep['counterexample']['found'],
        broken_detected=rep['broken_detected_on_counterexample'],
        zero_differential_mismatches=rep['differential']['mismatches'] == 0,
        id_hash_dispatch_exact=rep['differential']['dispatch_mismatches'] == 0,
        core_ab_credible=rep['core_ab']['verdict'] == 'CREDIBLE_WIN',
        twin_relocation_free=rep['twin']['no_relocations'] is True,
        nb_disasm_green=rep['nb_disasm']['sha_match'] is True and
                        rep['nb_disasm']['roundtrip'] is True,
        not_installed=rep['install_status'] == 'CERTIFIED_NOT_INSTALLED')
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.4/C.5 stable-interner gate: %s' % rep['verdict'])
    print('  counterexample %s B / %s names: %r' %
          (rep['counterexample']['bytes'], rep['counterexample']['lines'],
           rep['counterexample']['names']))
    print('  %d cases / %d comparisons / %d mismatches; dispatch %d/%d' %
          (rep['differential']['cases'], rep['differential']['comparisons'],
           rep['differential']['mismatches'],
           rep['differential']['dispatch_checks'] - rep['differential']['dispatch_mismatches'],
           rep['differential']['dispatch_checks']))
    print('  core A/B %sx (%s); twin %s B; nb_disasm %s/%s; %s' %
          (rep['core_ab']['median_speedup'], rep['core_ab']['verdict'],
           rep['twin']['text_bytes'], rep['nb_disasm']['ok'],
           rep['nb_disasm']['blobs'], rep['install_status']))
    print('  -> %s' % out)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
