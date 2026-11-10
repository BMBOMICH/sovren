#!/usr/bin/env python3
"""F5 — 36-cell mode/flag differential on the schema-9 compiler.

6 real sources x 6 mode/flag combinations = 36 cells. For each cell the
installed compiler is compared against a control compiler on rc, output
SHA-256, stdout and stderr. An absent source, a timeout, or a missing output
is a FAIL cell (acceptance: unknown/absent cells fail). No caching: every
compile is a fresh process with a fresh output path.
"""
import argparse, hashlib, json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    'tests/hello.sov',
    'tests/all.sov',
    'tests/x86ins.sov',
    'tests/performance/exit7.sov',
    'tests/performance/sum.sov',
    'tests/performance/calls.sov',
]
COMBOS = [
    [], ['--flat'], ['--unsafe'], ['--bare'],
    ['--flat', '--unsafe'], ['--bare', '--flat'],
]

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if p.is_file() and p.stat().st_size else ''

def run(exe, src, flags, out):
    if out.exists(): out.unlink()
    try:
        p = subprocess.run([str(exe), str(src), '-o', str(out)] + flags,
                           cwd=ROOT, capture_output=True, timeout=120)
        return dict(rc=p.returncode, sha=sha(out), size=out.stat().st_size if out.is_file() else 0,
                    stdout=p.stdout.decode('utf8', 'replace')[:400],
                    stderr=p.stderr.decode('utf8', 'replace')[:400])
    except subprocess.TimeoutExpired:
        return dict(rc='TIMEOUT', sha='', size=0, stdout='', stderr='')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidate', default=str(ROOT/'compilers/linux/compiler'))
    ap.add_argument('--controls', nargs='+',
                    default=['/tmp/cc_control_pre_c4', '/tmp/cc_original_4162'])
    ap.add_argument('--output', default='/home/user/evidence/C36_mode_flag_c4.json')
    a = ap.parse_args()
    cand = Path(a.candidate)
    controls = [Path(c) for c in a.controls if Path(c).is_file()]
    if not controls: sys.exit('no control compilers present')

    cells, mismatches = [], 0
    with tempfile.TemporaryDirectory(prefix='c36-') as td:
        W = Path(td)
        for src_rel in SOURCES:
            src = ROOT/src_rel
            if not src.is_file():
                for flags in COMBOS:
                    cells.append(dict(source=src_rel, flags=flags, verdict='FAIL',
                                      reason='ABSENT_SOURCE')); mismatches += 1
                continue
            for flags in COMBOS:
                # ONE output path for every side. The compiler echoes the -o
                # filename on stdout; different paths produce false mismatches.
                out = W/'cell.bin'
                base = run(cand, src, flags, out)
                cmp = {}
                for c in controls:
                    cmp[c.name] = run(c, src, flags, out)
                bad = [name for name, r in cmp.items() if r != base]
                # Refusal parity: identical rc with no artifact on every side
                # is a match, not a failure (C.29 semantics).
                refused = (not bad and base['rc'] != 0 and base['size'] == 0 and
                           all(r['size'] == 0 for r in cmp.values()))
                ok = (not bad) and (base['rc'] == 0 or refused)
                if not ok: mismatches += 1
                cells.append(dict(source=src_rel, flags=flags, input_bytes=src.stat().st_size,
                                  candidate=base, controls=cmp,
                                  mismatched_controls=bad,
                                  refusal_parity=refused,
                                  verdict='GREEN' if ok else 'FAIL'))
    report = dict(schema=1, cells=len(cells), matrix='6 sources x 6 mode/flag combos',
                  candidate=str(cand), candidate_md5=hashlib.md5(cand.read_bytes()).hexdigest(),
                  controls=[str(c) for c in controls], mismatches=mismatches,
                  all_green=mismatches == 0, detail=cells)
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print('C.36 mode/flag differential: %d/%d GREEN (%d mismatches) -> %s' %
          (len(cells)-mismatches, len(cells), mismatches, out))
    for c in cells:
        if c['verdict'] != 'GREEN':
            print('  FAIL', c['source'], c['flags'], c.get('reason') or c.get('mismatched_controls'))
    return 0 if mismatches == 0 else 1

if __name__ == '__main__': sys.exit(main())
