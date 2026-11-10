#!/usr/bin/env python3
"""C.31 counterexample-first minimised fixtures for the C.2/C.9/C.11
fused front-end scan.

Every fix gets the smallest source that distinguishes it from the previous
compiler: one fixture per runtime-need needle, one per u_prep first-gate
shape, plus the six needles embedded in comments/strings (over-match traps).
Semantics first: rc, output bytes, executed stdout and --flat text must all
match the certified previous binary. Cold processes only, no caching.
"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
PREV = os.environ.get('PREV_COMPILER', '/tmp/cc_prev')
CAND = os.environ.get('CAND_COMPILER', str(R / 'compilers/linux/compiler'))

# name -> source text. Each is a minimal distinguishing case.
F = {}
F['plain'] = 'main:\n    print 7 + 3\n'
for i, nd in enumerate(['_sov_', 'load_file', 'peek_', 'poke_', 'spawn ', 'join ']):
    # comment-only occurrence: must NOT trigger the runtime need (over-match trap)
    F['need_comment_' + str(i)] = 'main:\n    # ' + nd + ' mentioned here\n    print 1\n'
# real runtime-need triggers, one needle at a time
F['need_live_alloc'] = 'main:\n    p: _sov_alloc(8)\n    print 1\n'
F['need_live_load'] = 'main:\n    x: load_file("does-not-exist")\n    print 1\n'
F['need_live_peek'] = 'main:\n    b: _sov_heap_alloc(8)\n    print peek_byte(b, 0)\n'
# u_prep first-gate shapes (bit 1): every one of these must keep u_prep alive
F['unsafe_line0'] = 'unsafe:\nmain:\n    print 1\n'
F['unsafe_indent16'] = 'main:\n' + ' ' * 16 + 'unsafe:\n    print 1\n'
F['unsafe_indent17'] = 'main:\n' + ' ' * 17 + 'unsafe:\n    print 1\n'
F['unsafe_tab'] = 'main:\n\tunsafe:\n    print 1\n'
F['unsafe_string'] = 'main:\n    print "unsafe: not a marker"\n'
F['unsafe_midline'] = 'main:\n    print 1 # unsafe: tail\n'
F['unsafe_comment'] = 'main:\n    # unsafe: in a comment\n    print 1\n'
F['unsafe_2occ'] = 'main:\n    # unsafe: one\n    # unsafe: two\n    print 1\n'
F['unsafe_empty'] = 'unsafe:\n'
# combined: need + unsafe in the same source
F['combined'] = 'main:\n    # unsafe: header\n    p: _sov_alloc(8)\n    print 2\n'


def run(exe, src, out, flags=()):
    p = subprocess.run([exe, str(src), *flags, '-o', str(out)],
                       cwd=R, capture_output=True, timeout=120)
    data = out.read_bytes() if out.is_file() else b''
    return dict(rc=p.returncode, sha=hashlib.sha256(data).hexdigest() if data else None,
                log=(p.stdout + p.stderr).decode(errors='replace')[-200:])


def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix='front-fixtures-') as td:
        W = Path(td)
        for name, text in F.items():
            src = W / (name + '.sov')
            src.write_text(text)
            a, b = W / (name + '.a'), W / (name + '.b')
            ra, rb = run(PREV, src, a), run(CAND, src, b)
            ok = ra['rc'] == rb['rc'] and ra['sha'] == rb['sha']
            # executed semantics
            if ok and ra['rc'] == 0 and a.is_file():
                ea = subprocess.run([str(a)], capture_output=True, timeout=20)
                eb = subprocess.run([str(b)], capture_output=True, timeout=20)
                ok = (ea.returncode, ea.stdout, ea.stderr) == (eb.returncode, eb.stdout, eb.stderr)
            # --flat text equality
            fa, fb = W / (name + '.flat.a'), W / (name + '.flat.b')
            qa, qb = run(PREV, src, fa, ('--flat',)), run(CAND, src, fb, ('--flat',))
            ok = ok and qa['sha'] == qb['sha']
            rows.append(dict(name=name, pass_test=ok, rc_a=ra['rc'], rc_b=rb['rc'],
                             sha_a=ra['sha'], sha_b=rb['sha']))
            print(('PASS' if ok else 'FAIL'), name)
    n, ok = len(rows), sum(r['pass_test'] for r in rows)
    out = os.environ.get('OUTPUT', '/home/user/evidence/C31_front_fusion_fixtures.json')
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(rows, indent=2))
    print(f'{ok}/{n} minimised front-fusion fixtures identical')
    return 0 if ok == n else 1


if __name__ == '__main__':
    sys.exit(main())
