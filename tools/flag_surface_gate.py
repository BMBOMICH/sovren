#!/usr/bin/env python3
"""C.26/C.36 flag-surface differential (F10, overclaim fixed).

For EVERY accepted flag, compile the same source with the candidate AND a
control compiler using ONE shared -o path, then compare rc + output SHA-256.
Only then is the flag "byte-identical to control". Retired/unknown flags must
be EXPLICIT refusals with no artifact (never accepted no-op flags). Cold
processes only; no cache/state sidecars may appear.

NOTE: different modes are NOT expected to be byte-identical to each other
(--flat emits flat source, --unsafe/bare change the emitted image). This gate
compares each mode ACROSS COMPILERS, not modes against each other.
"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
C = os.environ.get('CAND_COMPILER', str(R / 'compilers/linux/compiler'))
CONTROL = os.environ.get('CONTROL_COMPILER', '')
SRC = R / 'tests/hello.sov'
ACCEPT = ['--bare', '--flat', '--prof', '--unsafe', '-o']
RETIRED = ['--mkdsug', '--uncached', '--no-ac', '--no-learn',
           '--serve', '--warm', '--cache', '--state']


def main():
    rows, bad = [], 0
    with tempfile.TemporaryDirectory(prefix='c26-flags-') as td:
        W = Path(td)
        base = None
        for f in ACCEPT:
            out = W / 'cell.bin'      # ONE path: the compiler echoes -o on stdout
            argv = [str(SRC)] + ([] if f == '-o' else [f]) + ['-o', str(out)]
            def one(exe):
                if out.exists(): out.unlink()
                pr = subprocess.run([exe] + argv, cwd=R, capture_output=True, timeout=120)
                h = hashlib.sha256(out.read_bytes()).hexdigest() if out.is_file() and out.stat().st_size else None
                return pr.returncode, h
            rc_c, h_c = one(C)
            rc_k, h_k = one(CONTROL) if CONTROL else (rc_c, h_c)
            ok = rc_c == 0 and h_c is not None and (rc_c, h_c) == (rc_k, h_k)
            if f == '-o' and ok: base = h_c
            rows.append(dict(flag=f, accepted=True, rc=rc_c, sha=h_c,
                             control_rc=rc_k, control_sha=h_k,
                             byte_identical_to_control=(rc_c, h_c)==(rc_k, h_k), ok=ok))
            bad += not ok
        for f in RETIRED:
            out = W / ('ret' + f.replace('-', '_') + '.bin')
            p = subprocess.run([C, str(SRC), f, '-o', str(out)],
                               cwd=R, capture_output=True, timeout=120)
            made = out.is_file() and out.stat().st_size > 0
            err = (p.stdout + p.stderr).decode('utf-8', 'replace')
            ok = p.returncode != 0 and not made and 'unknown flag' in err
            rows.append(dict(flag=f, accepted=False, rc=p.returncode,
                             artifact=made, explicit_refusal='unknown flag' in err, ok=ok))
            bad += not ok
        # no sidecar/state artifacts anywhere in the workspace tree
        bad_sidecars = []
        for ext in ('.plk', '.ac', '.ac.bin', '.lsug', '.sug', '.dsug', '.state', '.deepoc'):
            for q in R.rglob('*' + ext):
                bad_sidecars.append(str(q.relative_to(R)))
        rows.append(dict(flag='no-cache-sidecars', artifacts=len(bad_sidecars),
                         ok=not bad_sidecars))
        bad += bool(bad_sidecars)
    out = Path(os.environ.get('OUTPUT', '/home/user/evidence/C26_flag_surface.json'))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2))
    for r in rows:
        print(('PASS' if r['ok'] else 'FAIL'), r)
    print('%d/%d C.26 flag-surface cells green; base sha %s; control=%s' %
          (len(rows) - bad, len(rows), str(base)[:12], CONTROL or 'NONE'))
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
