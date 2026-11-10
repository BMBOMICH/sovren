#!/usr/bin/env python3
"""C.31 counterexample-first fixtures for the sg_extra_ls twin precheck.

The preclaim is: sg_extra(t) can only be nonzero when t contains ";;",
" -> " or ": ". These fixtures hit each of the four sg_extra branches plus
the deliberate skip cases, and compare rc / output bytes / executed stdout
/ --flat text against the previous certified compiler. Cold processes only.
"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
PREV = os.environ.get('PREV_COMPILER', '/tmp/cc_prev4')
CAND = os.environ.get('CAND_COMPILER', str(R / 'compilers/linux/compiler'))

F = {
    'no_forms':        'main:\n    print 7 + 3\n',
    'gt_no_colon':     'main:\n    x: 9\n    if x > 3\n        print 1\n    print x\n',
    'pack_semis':      'main:\n    x: 1 ;; y: 2\n    print x + y\n',
    'arrow_one_line':  'main:\n    x: 2\n    if x > 1 -> print 9\n    print x\n',
    'arrow_aslong':    'main:\n    i: 0\n    as long as i < 3 -> i: i + 1\n    print i\n',
    'run_form':        'main:\n    0: a b c: 1 2 3\n    print 1\n',
    'digit_assign':    'main:\n    1: x y z\n    print 1\n',
    'two_colons':      'main:\n    a: 1: 2\n    print 1\n',
    'colon_in_string': 'main:\n    print ": not a marker"\n',
    'comment_colon':   'main:\n    # note: this has a colon space\n    print 1\n',
    'multiline_str':   'main:\n    print "a: b"\n    print 2\n',
    'unsafe_and_pack': 'main:\n    # unsafe: marker\n    x: 1 ;; y: 2\n    print x + y\n',
}


def run(exe, src, out, flags=()):
    p = subprocess.run([exe, str(src), *flags, '-o', str(out)],
                       cwd=R, capture_output=True, timeout=120)
    data = out.read_bytes() if out.is_file() else b''
    return dict(rc=p.returncode,
                sha=hashlib.sha256(data).hexdigest() if data else None)


def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix='sgx-fixtures-') as td:
        W = Path(td)
        for name, text in F.items():
            src = W / (name + '.sov')
            src.write_text(text)
            a, b = W / (name + '.a'), W / (name + '.b')
            ra, rb = run(PREV, src, a), run(CAND, src, b)
            ok = ra['rc'] == rb['rc'] and ra['sha'] == rb['sha']
            if ok and ra['rc'] == 0 and a.is_file():
                ea = subprocess.run([str(a)], capture_output=True, timeout=20)
                eb = subprocess.run([str(b)], capture_output=True, timeout=20)
                ok = (ea.returncode, ea.stdout, ea.stderr) == (eb.returncode, eb.stdout, eb.stderr)
            fa, fb = W / (name + '.flat.a'), W / (name + '.flat.b')
            qa, qb = run(PREV, src, fa, ('--flat',)), run(CAND, src, fb, ('--flat',))
            ok = ok and qa['sha'] == qb['sha']
            rows.append(dict(name=name, pass_test=ok, rc_a=ra['rc'], rc_b=rb['rc']))
            print(('PASS' if ok else 'FAIL'), name)
    n, ok = len(rows), sum(r['pass_test'] for r in rows)
    out = os.environ.get('OUTPUT', '/home/user/evidence/C31_sgextra_fixtures.json')
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(rows, indent=2))
    print(f'{ok}/{n} sg_extra_ls precheck fixtures identical')
    return 0 if ok == n else 1


if __name__ == '__main__':
    sys.exit(main())
