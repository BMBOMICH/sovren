#!/usr/bin/env python3
"""C.31 minimised fixtures for the C.2/C.3/C.12/C.13 fused front-end scan.

`_sov_base_scan` replaced four whole-text passes (lines_of_fast + list_len +
sg_extra_ls for `rt` and `extra`) with ONE native pass over ONE flat copy.
`src_base` is SEMANTICALLY LOAD-BEARING: a wrong line/extra count changes
error line numbers and, for sugar-expanded sources, the emitted bytes. These
fixtures target exactly the shapes that decide that count:

  trailing newline / no trailing newline / empty / blank-only text,
  CRLF, blank and comment lines, `;;` pack marks, ` -> ` arrow one-liners,
  `: ` digit-leading assignments (run forms), apostrophes, quotes spanning
  lines (the `ins` multi-line string gate), and nested `use`/`include`.

Every case is compiled COLD with the control (pre-fusion) compiler and the
installed compiler; rc, output SHA-256, stdout/stderr and executed semantics
must all match. No caching, no shared state between invocations.

Usage: tools/basescan_fixture_gate.py [--control PATH] [--output PATH]
"""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
HERE = R

FIXTURES = {
    'empty': 'main:\n    return 0\n',
    'no-trailing-nl': 'main:\n    a: 1\n    print a',
    'one-trailing-nl': 'main:\n    a: 1\n    print a\n',
    'two-trailing-nl': 'main:\n    a: 1\n    print a\n\n',
    'blank-lines': '\n\nmain:\n\n    a: 2\n\n    print a\n\n',
    'comments-only': '# one\n# two\n\nmain:\n    return 0\n',
    'crlf': 'main:\r\n    a: 3\r\n    print a\r\n',
    'pack-marks': 'main:\n    a: 1 ;; b: 2\n    c: a + b ;; print c\n',
    'arrow-oneliners': 'main:\n    a: 7\n    if a > 0 -> print a\n    if not -> print 0 - 1\n',
    'digit-run-form': 'main:\n    1: 4\n    2: 5\n    print 1 + 2\n',
    'two-colons': 'main:\n    a: 1: 2\n    print a\n',
    'apostrophes': "main:\n    print 'a: b'\n    print \"x: y\"\n",
    'multiline-quote': 'main:\n    print "first\nsecond: third"\n    return 0\n',
    'long-identifiers': 'main:\n    a_very_long_identifier_name_0123456789: 11\n    print a_very_long_identifier_name_0123456789\n',
    'nested-if': 'main:\n    a: 5\n    if a > 2\n        if a > 4\n            print a\n    return 0\n',
    'forward-calls': 'main:\n    r: f1()\n    print r\n    return 0\nf1:\n    return 42\n',
}


def run(binary, src, out):
    p = subprocess.run([str(binary), src, '-o', out], cwd=HERE,
                       capture_output=True, timeout=120)
    digest = (hashlib.sha256(Path(out).read_bytes()).hexdigest()
              if os.path.exists(out) else 'NOFILE')
    ex = ('NOFILE', '', '')
    if os.path.exists(out) and os.access(out, os.X_OK):
        try:
            q = subprocess.run([out], capture_output=True, timeout=20)
            ex = (q.returncode, q.stdout.decode('utf8', 'replace'),
                  q.stderr.decode('utf8', 'replace'))
        except subprocess.TimeoutExpired:
            ex = ('TIMEOUT', '', '')
    return (p.returncode, digest,
            p.stdout.decode('utf8', 'replace'),
            p.stderr.decode('utf8', 'replace'), ex)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--control', default='/tmp/cc_control_c2')
    ap.add_argument('--candidate', default=str(R / 'compilers/linux/compiler'))
    ap.add_argument('--output',
                    default='/home/user/evidence/C31_basescan_fixtures.json')
    a = ap.parse_args()
    rows, bad = [], 0
    with tempfile.TemporaryDirectory() as td:
        for name, text in FIXTURES.items():
            src = os.path.join(td, name + '.sov')
            Path(src).write_bytes(text.encode())
            # Same output path for both sides: the compiler echoes the path
            # in stdout, so distinct paths would create fake mismatches.
            out = os.path.join(td, 'out.bin')
            for f in (out,):
                if os.path.exists(f):
                    os.remove(f)
            ra = run(a.control, src, out)
            if os.path.exists(out):
                os.remove(out)
            rb = run(a.candidate, src, out)
            ok = ra == rb
            if not ok:
                bad += 1
            rows.append({'fixture': name, 'identical': ok,
                         'control': repr(ra)[:400], 'candidate': repr(rb)[:400]})
    doc = {'gate': 'C.31 basescan src_base fixtures', 'fixtures': len(FIXTURES),
           'identical': len(FIXTURES) - bad, 'mismatches': bad,
           'control': a.control, 'candidate': a.candidate, 'rows': rows}
    Path(a.output).write_text(json.dumps(doc, indent=1) + '\n')
    print('%d/%d basescan fixtures identical%s' %
          (len(FIXTURES) - bad, len(FIXTURES), '' if not bad else ' -- FAIL'))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
