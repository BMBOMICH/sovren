#!/usr/bin/env python3
"""C.31 — counterexample-first PAD-LINE slice REJECTION certificate.

The installed compiler prefixes EVERY user source with a full-source copy:

    src = join(join("# pad line: ...", nl), src)          # one whole-text copy

That pad line exists only to guarantee that `extra` (the concatenated `use`
library chunks) ends with a newline before `join(extra, src)`, so the user's
first line cannot be glued onto the last library chunk line.

This gate builds TWO fresh compiler binaries from `compilers/linux/compiler.sov`:

  * NOPAD   — deletes the pad-line full-source copy and replaces it with an
              explicit one-byte separator invariant on `extra`.
  * BROKEN  — deletes the pad-line copy AND strips `extra`'s trailing newline,
              so the first user line merges into the last library line.

Counterexample FIRST: 1-minimal delta debugging over real sources finds the
smallest fixture where BROKEN differs from NOPAD.  Then the gate PROVES that
NOPAD must be rejected: with exact stdout (only 7+ digit timing marks masked,
matching oracle.sh) it changes diagnostic line numbers and `--flat` output
bytes, so the frozen oracle and C.26 mode/flag cells fail.  R=21 placebo A/B is
also inside the layout-lottery band on all three measured lanes.

Verdict ALL_GREEN means: counterexample found, byte-identity break DETECTED,
slice REJECTED, installed compiler bytes unchanged. It is NOT an acceptance
of NOPAD and NOT a speed claim.  No cache, no persisted state, no sidecar.

Usage: python3 tools/c2c3_padline_counterexample_gate.py [--json OUT]
"""
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
CC = R / 'compilers/linux/compiler'
BASE = R / 'compilers/linux/compiler.sov'

PAD = '''    mark("sug")
    nl: _sov_heap_alloc(2)
    dummy: _sov_set_byte(nl, 0, 10)
    dummy: _sov_set_byte(nl, 1, 0)
    src: join(join("# pad line: keeps the user first line off the last chunk line", nl), src)
    mark("f3-sug")'''
NO_PAD = '''    mark("sug")
    # PASS 12 C.2/C.3 experimental slice: no pad-line full-source copy.
    mark("f3-sug")'''

ALLOC = '''    if pu_n > 0
        extra: _sov_heap_alloc(pu_total + 1)'''
ALLOC2 = '''    if pu_n > 0
        extra: _sov_heap_alloc(pu_total + 2)'''

TAIL = '''        dummy: poke_byte(extra, pu_off, 0)
    src: apply_aliases(src)'''
NOPAD_TAIL = '''        dummy: poke_byte(extra, pu_off, 0)
        # C.2/C.3 separator invariant candidate: append a newline only when
        # the last library chunk lacks one. No whole-source copy, no cache.
        if pu_off > 0
            if peek_byte(extra, pu_off - 1) is not 10
                dummy: poke_byte(extra, pu_off, 10)
                dummy: poke_byte(extra, pu_off + 1, 0)
    src: apply_aliases(src)'''
BROKEN_TAIL = '''        dummy: poke_byte(extra, pu_off, 0)
        if pu_off > 0
            if peek_byte(extra, pu_off - 1) is 10
                dummy: poke_byte(extra, pu_off - 1, 0)
    src: apply_aliases(src)'''


def variant_source(kind):
    s = BASE.read_text()
    assert PAD in s and ALLOC in s and TAIL in s, 'installed source shape changed'
    s = s.replace(PAD, NO_PAD, 1).replace(ALLOC, ALLOC2, 1)
    s = s.replace(TAIL, NOPAD_TAIL if kind == 'nopad' else BROKEN_TAIL, 1)
    return s


def build(kind, tmpdir):
    # Scratch source MUST sit inside compilers/linux/ so splice_inc resolves
    # syntax.sov / statements.sov / *_native.sov from the project tree.
    src = R / 'compilers/linux' / ('.c2c3_pad_%s_%d.sov' % (kind, os.getpid()))
    out = Path(tmpdir) / ('c2c3_pad_%s.bin' % kind)
    src.write_text(variant_source(kind))
    try:
        p = subprocess.run([str(CC), str(src), '-o', str(out)], cwd=R,
                           capture_output=True, text=True, timeout=300)
    finally:
        src.unlink(missing_ok=True)
    if p.returncode != 0 or not out.is_file():
        raise RuntimeError('build %s failed rc=%d: %s' % (kind, p.returncode, p.stdout[-300:]))
    out.chmod(0o755)
    return out


def norm(s):
    # Exact stdout except for 7+ digit elapsed-time / pointer marks; this is
    # the same mask oracle.sh uses. Masking ALL digits would hide the 18->17
    # line-number regression that makes this slice byte-unsafe.
    return re.sub(rb'\d{7,}', b'T', s or b'')


def run_cc(cc, src, out, extra_flags=()):
    if Path(out).exists():
        Path(out).unlink()
    p = subprocess.run([str(cc), str(src), *extra_flags, '-o', str(out)], cwd=R,
                       capture_output=True, timeout=120)
    b = Path(out).read_bytes() if Path(out).is_file() else b''
    return dict(rc=p.returncode,
                stdout=norm(p.stdout).decode('utf-8', 'replace'),
                stderr=norm(p.stderr).decode('utf-8', 'replace'),
                sha=hashlib.sha256(b).hexdigest(), size=len(b))


def differs(a, b, src, out):
    return run_cc(a, src, out) != run_cc(b, src, out)


def minimise(fixed, broken, seed, out):
    seed_path = Path(str(out) + '.seed')
    seed_path.write_bytes(seed)
    lines = seed.splitlines(True)
    if not differs(fixed, broken, seed_path, str(out) + '.base'):
        return None
    changed = True
    while changed:
        changed = False
        for i in range(len(lines)):
            cand = lines[:i] + lines[i + 1:]
            t = b''.join(cand)
            if not t:
                continue
            w = Path(str(out) + '.min')
            w.write_bytes(t)
            if differs(fixed, broken, w, str(out) + '.run'):
                lines, changed = cand, True
                break
    return b''.join(lines)


def oracle_counts(binary, tmpdir):
    p = subprocess.run(['sh', 'work/saparity/oracle.sh', str(binary)], cwd=R,
                       capture_output=True, text=True, timeout=600)
    m = re.search(r'oracle: (\d+) pass, (\d+) refuse-parity, (\d+) FAIL', p.stdout)
    return dict(rc=p.returncode,
                pass_=int(m.group(1)) if m else None,
                refuse=int(m.group(2)) if m else None,
                fail=int(m.group(3)) if m else None,
                tail=p.stdout.strip().splitlines()[-1] if p.stdout.strip() else '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C2_C3_padline_counterexample_2026-11-09.json'))
    a = ap.parse_args()
    out = Path(a.json)
    rep = dict(schema=2, date='2026-11-09', pass_='PASS 12',
               host=' '.join([platform.node(), platform.system(), platform.machine()]),
               verdict='FAIL', install_status='CERTIFIED_NOT_INSTALLED',
               claim='Measured REJECTION. No compiler bytes changed; no '
                     'speed/parity/completion claim.')
    with tempfile.TemporaryDirectory(prefix='c2c3pad-') as td:
        nopad = build('nopad', td)
        broken = build('broken', td)
        rep['binaries'] = dict(nopad=hashlib.sha256(nopad.read_bytes()).hexdigest(),
                               broken=hashlib.sha256(broken.read_bytes()).hexdigest(),
                               installed=hashlib.sha256(CC.read_bytes()).hexdigest())
        run_out = Path(td) / 'run.bin'
        seeds = [R / 'tests/fast.sov', R / 'tests/security.sov']
        best = None
        for s in seeds:
            m = minimise(nopad, broken, s.read_bytes(), str(run_out))
            if m is not None and (best is None or len(m) < len(best)):
                best = m
        rep['counterexample'] = dict(
            found=best is not None,
            bytes=len(best) if best else None,
            lines=len(best.splitlines()) if best else None,
            text=best.decode('utf-8', 'replace') if best else None,
            method='1-minimal line-level delta debugging over real sources; '
                   'BROKEN strips extra\'s trailing newline')
        if best is None:
            out.write_text(json.dumps(rep, indent=2) + '\n')
            print('C.2/C.3 pad-line gate: FAIL (no counterexample)')
            return 1
        fixture = E / 'C2_C3_padline_counterexample.sov'
        fixture.write_bytes(best)
        rep['counterexample']['fixture'] = str(fixture)

        corpus = [fixture] + [R / p for p in
                  ('tests/exit7.sov', 'tests/hello.sov', 'tests/fast.sov',
                   'tests/security.sov', 'tests/all.sov', 'tests/x86ins.sov',
                   'tests/q0.sov', 'tests/q1.sov', 'compilers/linux/compiler.sov',
                   'tests/addons.sov', 'tests/run.sov', 'tests/macos-run.sov',
                   'tests/rtos_corpus.sov', 'tests/rtos_dyn.sov')]
        exact_mismatch, flat_mismatch, detected, fixture_detected = [], [], 0, False
        for src in corpus:
            a1 = run_cc(CC, src, run_out)
            b1 = run_cc(nopad, src, run_out)
            if a1 != b1:
                exact_mismatch.append(dict(source=str(src), installed=a1, nopad=b1))
            # --flat emits the program text; the removed pad line changes it.
            fa = run_cc(CC, src, run_out, ('--flat',))
            fb = run_cc(nopad, src, run_out, ('--flat',))
            if fa['sha'] != fb['sha']:
                flat_mismatch.append(dict(source=str(src),
                                          installed_sha=fa['sha'][:16],
                                          nopad_sha=fb['sha'][:16]))
            d = differs(nopad, broken, src, run_out)
            if d:
                detected += 1
            if src == fixture and d:
                fixture_detected = True
        rep['byte_identity_break'] = dict(
            exact_stdout_or_output_mismatches=len(exact_mismatch),
            flat_output_sha_mismatches=len(flat_mismatch),
            first_exact=exact_mismatch[:2], first_flat=flat_mismatch[:2])
        rep['broken_detections'] = dict(cases=len(corpus), detected=detected,
                                        fixture_detected=fixture_detected)
        rep['oracle_nopad'] = oracle_counts(nopad, td)
        # Also record that the DEFAULT ELF is still byte-identical on the
        # 2,957-case differ corpus (measured separately); the break is in
        # stdout/--flat, not in default codegen.
        rep['differ_2957_evidence'] = str(E / 'C29_differ_p12b.json')
        rep['differ_2957_note'] = ('2957/2957 default-compile rc + emitted SHA '
                                  '+ executed semantics identical; C.26/C.28 '
                                  'exact stdout and --flat are NOT identical')

    ab = {}
    for key, name in [('self', 'compilers_linux_compiler.sov'),
                      ('x86ins', 'tests_x86ins.sov'), ('all', 'tests_all.sov')]:
        p = E / ('C33_placebo_p12_%s.txt' % name)
        if p.is_file():
            txt = p.read_text()
            m = re.search(r'B vs A: min ([+\-0-9.]+)%\s+med ([+\-0-9.]+)%', txt)
            ab[key] = dict(min_pct=float(m.group(1)) if m else None,
                           median_pct=float(m.group(2)) if m else None,
                           inside_noise='INSIDE THE PLACEBO' in txt,
                           evidence=str(p))
    rep['ab'] = ab
    rep['ab_verdict'] = ('NO_CREDIBLE_WIN' if len(ab) == 3 and all(
        v.get('inside_noise') for v in ab.values()) else 'NOT_MEASURED')

    byte_break = (rep['byte_identity_break']['exact_stdout_or_output_mismatches'] > 0
                  and rep['byte_identity_break']['flat_output_sha_mismatches'] > 0)
    oracle_break = (rep['oracle_nopad']['fail'] or 0) > 0
    ok = (rep['counterexample']['found'] and
          rep['broken_detections']['fixture_detected'] and
          byte_break and oracle_break and
          rep['ab_verdict'] == 'NO_CREDIBLE_WIN' and
          rep['install_status'] == 'CERTIFIED_NOT_INSTALLED')
    rep['verdict'] = 'ALL_GREEN' if ok else 'FAIL'
    rep['checks'] = dict(
        counterexample_first=rep['counterexample']['found'],
        broken_detected_on_counterexample=rep['broken_detections']['fixture_detected'],
        byte_identity_break_detected=byte_break,
        frozen_oracle_break_detected=oracle_break,
        ab_inside_noise_recorded=rep['ab_verdict'] == 'NO_CREDIBLE_WIN',
        not_installed=rep['install_status'] == 'CERTIFIED_NOT_INSTALLED')
    rep['slice_verdict'] = ('REJECTED_BYTE_IDENTITY_BREAK_AND_NO_CREDIBLE_WIN'
                            if ok else 'INCONCLUSIVE')
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.2/C.3 pad-line gate: %s (%s)' % (rep['verdict'], rep['slice_verdict']))
    print('  counterexample %s B / %s lines: %r' %
          (rep['counterexample']['bytes'], rep['counterexample']['lines'],
           (rep['counterexample']['text'] or '')[:70]))
    print('  byte break: exact %d, --flat %d; oracle %s/%s/%s; A/B %s' %
          (rep['byte_identity_break']['exact_stdout_or_output_mismatches'],
           rep['byte_identity_break']['flat_output_sha_mismatches'],
           rep['oracle_nopad']['pass_'], rep['oracle_nopad']['refuse'],
           rep['oracle_nopad']['fail'], rep['ab_verdict']))
    print('  -> %s' % out)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
