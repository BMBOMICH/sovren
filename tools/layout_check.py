#!/usr/bin/env python3
"""C.29/C.26 rebuilt 12-layout sweep.

The original harness lived outside the downloaded tree
(/home/z/my-project/scripts/layout_check.py). This is a clean-room rebuild:
twelve deterministic, layout-only edits to compilers/linux/compiler.sov
(one comment line inserted at twelve distinct top-level boundaries), each
compiled cold with the installed compiler. A comment emits no code, so all
twelve must produce a binary byte-identical to the certified compiler and
to each other, and each binary must compile tests/hello.sov identically.

No caching, no warm path: a fresh process per compile, temp files removed.
"""
import hashlib, json, os, subprocess, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SRC = R / 'compilers/linux/compiler.sov'
CC = R / 'compilers/linux/compiler'
HELLO = R / 'tests/hello.sov'
N = 12


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    base = SRC.read_text()
    lines = base.splitlines(keepends=True)
    # twelve distinct insertion points spread across the file, all at
    # top-level (column 0) boundaries so the comment cannot join a body.
    tops = [i for i, l in enumerate(lines)
            if l and not l[0].isspace() and not l.lstrip().startswith('#')][:4000]
    picks = [tops[int(k * (len(tops) - 1) / (N - 1))] for k in range(N)]
    rows = []
    ref = sha(CC)
    for k, at in enumerate(picks):
        variant = R / f'compilers/linux/.layout_{k:02d}.sov'
        out = Path(f'/tmp/layout_{k:02d}.bin')
        variant.write_text(''.join(lines[:at]) +
                           f'# layout check {k:02d}: comment-only, emits no code\n' +
                           ''.join(lines[at:]))
        out.unlink(missing_ok=True)
        p = subprocess.run([str(CC), str(variant), '-o', str(out)],
                           cwd=R, capture_output=True, timeout=300)
        ok_rc = p.returncode == 0 and out.is_file() and out.stat().st_size > 1000
        h = sha(out) if ok_rc else None
        same = ok_rc and h == ref
        # executed semantics through the variant binary
        sem = False
        if ok_rc:
            os.chmod(out, 0o755)
            gold = Path('/tmp/layout_gold.bin')
            if not gold.is_file():
                subprocess.run([str(CC), str(HELLO), '-o', str(gold)], cwd=R,
                               capture_output=True, timeout=120)
            probe = Path(f'/tmp/layout_{k:02d}.hello')
            q = subprocess.run([str(out), str(HELLO), '-o', str(probe)], cwd=R,
                               capture_output=True, timeout=120)
            sem = q.returncode == 0 and probe.is_file() and sha(probe) == sha(gold)
        rows.append(dict(layout=k, insert_line=at + 1, rc=p.returncode,
                         binary_identical=same, hello_identical=sem))
        print(f'layout {k:02d} line {at+1:6d}  rc={p.returncode}  '
              f'binary={"IDENTICAL" if same else "DIFFERENT"}  '
              f'hello={"IDENTICAL" if sem else "DIFFERENT"}')
        variant.unlink(missing_ok=True)
    ok = sum(r['binary_identical'] and r['hello_identical'] for r in rows)
    outp = os.environ.get('OUTPUT', '/home/user/evidence/C29_layout_check.json')
    Path(outp).parent.mkdir(parents=True, exist_ok=True)
    Path(outp).write_text(json.dumps(dict(reference_sha256=ref, rows=rows,
                                          green=ok, total=N), indent=2))
    print(f'{ok}/{N} layouts byte-identical and semantics-identical')
    return 0 if ok == N else 1


if __name__ == '__main__':
    sys.exit(main())
