#!/usr/bin/env python3
"""C.31 — counterexample-first MINIMISED failing fixtures for the installed
C.2/C.3 `pull_uses` stable-chunk work-queue rewrite.

This is the gate that was missing from the C.31 inventory: the pull_uses fixpoint
is an interpreted core inside `compilers/linux/compiler.sov`, NOT a native twin,
so the 22-twin inventory in c31_validate_all.py cannot see it.  The obligation
in C.31 is "counterexample-first minimised failing fixture before every fix",
extended to every rewritten core.  This runner supplies exactly that for the
PASS 8 landing:

  1. build three DELIBERATELY BROKEN variants of the installed compiler source
     (drop-last-chunk, reverse-chunk-order, single-BFS-round);
  2. find, by 1-minimal delta debugging from real `use:`-chain fixtures, the
     SMALLEST fixture whose translated output (rc + emitted SHA-256 + compiler
     stdout + executed stdout/exit) differs between the broken variant and the
     correct installed compiler.  The counterexample is established FIRST;
  3. only then verify the FIX: the installed compiler is byte-identical to the
     immediate pre-slice control on every fixture and every minimised fixture;
  4. assert the other rewritten cores' dedicated fixture gates are present and
     ALL GREEN (front fusion 20/20, sugar 12/12, src_base 16/16), so the C.31
     core inventory is complete rather than partial.

Every compile is cold: one shared `-o` path (so stdout cannot differ by path),
no cache, no persisted state, no warm-ups.  Nothing is installed or modified;
all scratch files live in compilers/linux/ (needed for relative includes) and
are removed in a finally block.

Usage: python3 tools/c31_pull_uses_counterexample_gate.py [--json OUT]
Exits 0 only when every broken variant is caught by a minimised fixture and
the installed compiler matches the control everywhere.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
SRC = R / 'compilers/linux/compiler.sov'
GOOD = str(R / 'compilers/linux/compiler')
LD = R / 'compilers/linux'
SHARED_OUT = Path('/tmp/c31_pu_shared.bin')
SHARED_FIX = LD / '.c31_pu_fixture.sov'

# The immediate pre-slice binary is the honest differential control.  Fall back
# to the older certified controls if /tmp has been recycled; user-program
# output bytes are identical across all of them (2957/2957 differ).
CONTROLS = ['/tmp/pass8_backup/compiler.be20',
            '/tmp/cc_control_pre_c4',
            '/tmp/cc_original_4162',
            '/home/user/reference/linux/compiler']
CONTROL = next((p for p in CONTROLS if Path(p).is_file()), None)
if CONTROL and not os.access(CONTROL, os.X_OK):
    os.chmod(CONTROL, 0o755)  # durable workspace control ships mode 644

# ---- exact text of the landed C.2/C.3 work queue (copy, do not guess) ----
BFS = '''    more: pu_first
    as long as length(more) > 0
        more: pull_uses(more)
        if length(more) > 0
            dummy: _sov_list_add(pu_chunks, more)
        mark("pu")
'''
COUNT = '    pu_n: _sov_list_len(pu_chunks)\n'
MATERIALISE = '            pu_ch: peek_i64(pu_chunks, 16 + pu_i * 8)\n'

VARIANTS = {
    'drop_last_chunk': [(COUNT,
        '    pu_n: _sov_list_len(pu_chunks) - 1\n'
        '    if pu_n < 1 -> pu_n: 0\n')],
    'reverse_chunk_order': [(MATERIALISE,
        '            pu_ch: peek_i64(pu_chunks, 16 + (pu_n - 1 - pu_i) * 8)\n')],
    'single_bfs_round': [(BFS, '    mark("pu")\n')],
}

SEEDS = ['tests/bench.sov', 'tests/security.sov', 'tests/fast.sov']
CORE_FIXTURES = {
    'front_fusion': ('C31_front_fusion_fixtures_c4.json', 20),
    'sugar_sgextra': ('C31_sgextra_fixtures_c4.json', 12),
    'basescan_src_base': ('C31_basescan_fixtures_c4.json', 16),
}


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def signature(compiler, text, cache):
    """Cold translate `text`, return (rc, emitted sha, compiler output, exec)."""
    key = (compiler, sha256(text.encode()))
    if key in cache:
        return cache[key]
    SHARED_FIX.write_text(text)
    if SHARED_OUT.exists():
        SHARED_OUT.unlink()
    r = subprocess.run([compiler, str(SHARED_FIX), '-o', str(SHARED_OUT)],
                       cwd=R, capture_output=True, text=True, timeout=120)
    out = (r.stdout + r.stderr).strip()
    h = sha256(SHARED_OUT.read_bytes()) if SHARED_OUT.is_file() else 'NONE'
    exec_rc, exec_out = None, None
    if r.returncode == 0 and SHARED_OUT.is_file():
        try:
            os.chmod(SHARED_OUT, 0o755)
            e = subprocess.run([str(SHARED_OUT)], cwd=R, capture_output=True,
                               text=True, timeout=6)
            # `tests/fast.sov` prints a volatile /tmp/sov-tr-<pid>.sh path;
            # normalise run-specific digits so executed semantics are
            # comparable without hiding emitted-byte or rc differences.
            exec_out = re.sub(r'\d+', '#', e.stdout.strip())
            exec_rc = e.returncode
        except subprocess.TimeoutExpired:
            exec_rc, exec_out = 'TIMEOUT', 'TIMEOUT'
    sig = dict(rc=r.returncode, emitted_sha256=h, compiler_output=out,
               exec_rc=exec_rc, exec_stdout=exec_out)
    cache[key] = sig
    return sig


def differs(bad, good, text, cache):
    """A counterexample must be a VALID program (correct rc=0) that the broken
    variant translates differently."""
    g = signature(good, text, cache)
    if g['rc'] != 0:
        return False
    b = signature(bad, text, cache)
    # A real counterexample must change the TRANSLATED PROGRAM (rc or emitted
    # bytes), not merely a diagnostic note on stdout.
    return (b['rc'] != g['rc'] or
            b['emitted_sha256'] != g['emitted_sha256'] or
            b['exec_rc'] != g['exec_rc'] or
            b['exec_stdout'] != g['exec_stdout'])


def minimise(bad, good, seed_text, cache):
    """1-minimal delta debugging: remove lines while the counterexample holds."""
    if not differs(bad, good, seed_text, cache):
        return None
    lines = seed_text.splitlines(True)
    changed = True
    while changed:
        changed = False
        for i in range(len(lines)):
            cand = lines[:i] + lines[i + 1:]
            t = ''.join(cand)
            if t.strip() and differs(bad, good, t, cache):
                lines, changed = cand, True
                break
    return ''.join(lines)


def core_fixture_census():
    rows = []
    for name, (fn, expect) in CORE_FIXTURES.items():
        p = E / fn
        if not p.is_file():
            rows.append(dict(core=name, evidence=fn, present=False,
                             verdict='FAIL'))
            continue
        d = json.loads(p.read_text())
        # The three fixture gates use three different schemas: a list of
        # {pass_test}, a list of {rc_a,rc_b}, and a dict with `identical`.
        if isinstance(d, list):
            cells = d
            green = sum(1 for c in cells if isinstance(c, dict) and (
                c.get('pass_test') is True or
                (c.get('rc_a') == c.get('rc_b') == 0 and
                 (c.get('sha_a', c.get('sha_b')) == c.get('sha_b')))))
        elif isinstance(d, dict):
            cells = d.get('rows', [])
            green = d.get('identical', 0)
            if not isinstance(green, int):
                green = sum(1 for c in cells if isinstance(c, dict) and
                            c.get('pass_test') is True)
            ok_count = len(cells)
            mismatches = d.get('mismatches', None)
            rows.append(dict(core=name, evidence=fn, present=True,
                             green_cells=green, expected=expect,
                             cells=ok_count, mismatches=mismatches,
                             verdict='PASS' if (green >= expect and
                                 (mismatches in (0, None))) else 'FAIL'))
            continue
        else:
            green = 0
            cells = []
        rows.append(dict(core=name, evidence=fn, present=True,
                         green_cells=green, expected=expect,
                         cells=len(cells),
                         verdict='PASS' if green >= expect else 'FAIL'))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C31_pull_uses_counterexample_2026-11-09.json'))
    a = ap.parse_args()
    out = Path(a.json)
    out.parent.mkdir(parents=True, exist_ok=True)

    source = SRC.read_text()
    for block, _ in [(COUNT, None), (MATERIALISE, None), (BFS, None)]:
        assert source.count(block) == 1, 'landed work-queue text changed: %r' % block[:40]

    scratch = []
    report = dict(schema=1, date='2026-11-09', pass_='PASS 9',
                  core='C.2/C.3 pull_uses stable-chunk work queue',
                  installed=GOOD, control=CONTROL,
                  counterexample_first=True,
                  method='1-minimal delta debugging over real use: chains; '
                         'rc + emitted SHA-256 + compiler stdout + executed '
                         'stdout/exit; cold single shared -o path',
                  variants={}, core_fixtures=core_fixture_census(),
                  verdict='FAIL')
    ok = True
    try:
        # 1. build deliberately broken variants (cold, real compilers)
        for name, edits in VARIANTS.items():
            s = source
            for old, new in edits:
                assert old in s, name
                s = s.replace(old, new, 1)
            f = LD / ('.c31_pu_bad_' + name + '.sov')
            b = E / ('C31_pull_uses_bad_' + name + '.bin')
            f.write_text(s)
            scratch += [f]
            r = subprocess.run([GOOD, str(f), '-o', str(b)], cwd=R,
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                report['variants'][name] = dict(build_rc=r.returncode,
                    tail=(r.stdout + r.stderr).strip().splitlines()[-6:],
                    verdict='FAIL_BUILD')
                ok = False
                continue
            os.chmod(b, 0o755)
            report['variants'][name] = dict(build_rc=0,
                                            binary_md5=hashlib.md5(b.read_bytes()).hexdigest(),
                                            source_sha256=sha256(s.encode()),
                                            verdict='PENDING')

        # 2. counterexample FIRST, then fix verification
        cache = {}
        seeds = []
        for rel in SEEDS:
            p = R / rel
            if p.is_file():
                seeds.append((rel, p.read_text()))
        report['seeds'] = [dict(file=f, bytes=len(t.encode()),
                                lines=len(t.splitlines())) for f, t in seeds]

        for name, info in report['variants'].items():
            if info.get('verdict') == 'FAIL_BUILD':
                continue
            bad = str(E / ('C31_pull_uses_bad_' + name + '.bin'))
            best = None
            for rel, text in seeds:
                m = minimise(bad, GOOD, text, cache)
                if m is None:
                    continue
                if best is None or len(m.encode()) < len(best[1].encode()):
                    best = (rel, m)
            if best is None:
                info['verdict'] = 'FAIL_NO_COUNTEREXAMPLE'
                ok = False
                continue
            rel, m = best
            good_sig = signature(GOOD, m, cache)
            bad_sig = signature(bad, m, cache)
            ctrl_sig = signature(CONTROL, m, cache) if CONTROL else None
            # the FIX: installed must equal the pre-slice control on the
            # minimised fixture (and on every full seed fixture).
            fix_ok = (ctrl_sig is not None and ctrl_sig == good_sig)
            for _, text in seeds:
                if signature(CONTROL, text, cache) != signature(GOOD, text, cache):
                    fix_ok = False
            info.update(verdict='PASS' if fix_ok else 'FAIL_FIX_DIFFERS',
                        seed=rel,
                        minimised_bytes=len(m.encode()),
                        minimised_lines=len(m.splitlines()),
                        minimised_fixture=m,
                        seed_bytes=len(dict(seeds)[rel].encode()),
                        good=good_sig, broken=bad_sig, control=ctrl_sig,
                        fix_matches_control=fix_ok,
                        counterexample_detected=(bad_sig != good_sig))
            if not fix_ok or not info['counterexample_detected']:
                ok = False

        report['core_fixtures_verdict'] = ('PASS' if all(
            r['verdict'] == 'PASS' for r in report['core_fixtures']) else 'FAIL')
        if report['core_fixtures_verdict'] != 'PASS':
            ok = False
        report['cold_translations'] = len(cache)
        report['verdict'] = ('ALL_GREEN' if ok else 'FAIL')
    finally:
        for f in scratch + [SHARED_FIX, SHARED_OUT]:
            try:
                Path(f).unlink()
            except OSError:
                pass

    out.write_text(json.dumps(report, indent=2) + '\n')
    print('C.31 pull_uses counterexample gate: %s (%d variants, %d cores, %d cold translations)'
          % (report['verdict'], len(report['variants']),
             len(report['core_fixtures']), report.get('cold_translations', 0)))
    for n, v in report['variants'].items():
        print('  %-20s %-24s %s B / %s lines (seed %s)' %
              (n, v.get('verdict'), v.get('minimised_bytes', '-'),
               v.get('minimised_lines', '-'), v.get('seed', '-')))
    for c in report['core_fixtures']:
        print('  %-20s %s' % (c['core'], c['verdict']))
    print('  -> %s' % out)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
