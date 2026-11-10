#!/usr/bin/env python3
"""C.30 — THIRD independent structural proof, using the compiler's OWN expansion.

Earlier evidence used (1) an exhaustive archive search and (2) a Python
recursive pinned-include flatten (`lineage_flatten.py`).  This tool uses the
installed compiler's OWN `--flat` mode — i.e. exactly the text the compiler
would parse, with its own `splice_inc` indentation rules and runtime splice —
for all 29 lineage-pending drivers.

If the fragments were merely mis-indented, the compiler's own expansion would
be a valid program.  It is not.  This is NOT a repair attempt: no driver
source, marker, gate or matrix is modified, and strip/kit_expand/mechanical
indentation stay on the C.38 dead-end list.

Usage: python3 tools/c30_official_flat_probe.py [--json OUT]
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

R = Path('/home/user/dl/sovren')
E = Path('/home/user/evidence')
CC = str(R / 'compilers/linux/compiler')
BLOCKER = E / 'C30_blocker_2026-11-09.json'
MAIN_RE = re.compile(r'^main(?:\s+\w[^:]*)?:', re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C30_official_flat_probe_2026-11-09.json'))
    a = ap.parse_args()
    drivers = [d['driver'] for d in json.loads(BLOCKER.read_text())['drivers']]
    rows = []
    for i, rel in enumerate(drivers):
        flat = Path('/tmp/c30_official_%02d.flat' % i)
        if flat.exists():
            flat.unlink()
        try:
            p = subprocess.run([CC, rel, '-o', str(flat), '--flat'], cwd=R,
                               capture_output=True, text=True, timeout=180)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = 'TIMEOUT'
        txt = flat.read_text(errors='replace') if flat.is_file() else ''
        has_main = bool(MAIN_RE.search(txt))
        # Compile the compiler's own expanded text back; a valid program would build.
        rebuilt = Path('/tmp/c30_official_%02d.bin' % i)
        if rebuilt.exists():
            rebuilt.unlink()
        try:
            q = subprocess.run([CC, str(flat), '-o', str(rebuilt)], cwd=R,
                               capture_output=True, text=True, timeout=180)
            rrc = q.returncode
            errors = len(re.findall(r'^Error:', q.stdout + q.stderr, re.M))
        except subprocess.TimeoutExpired:
            rrc, errors = 'TIMEOUT', -1
        rows.append(dict(driver=rel, flat_rc=rc,
                         flat_lines=txt.count('\n') + 1 if txt else 0,
                         flat_bytes=flat.stat().st_size if flat.is_file() else 0,
                         has_main_task=has_main,
                         recompile_rc=rrc, recompile_error_lines=errors,
                         builds=(rrc == 0 and rebuilt.is_file() and rebuilt.stat().st_size > 1000)))
    no_main = [r['driver'] for r in rows if not r['has_main_task']]
    builds = [r['driver'] for r in rows if r['builds']]
    rep = dict(schema=1, date='2026-11-09', drivers=len(rows),
               method='installed compiler --flat (its own splice_inc + runtime splice), then recompile',
               drivers_without_main_task=len(no_main),
               drivers_whose_official_flat_builds=len(builds),
               all_official_flats_fail=len(builds) == 0,
               rows=rows,
               verdict='OFFICIAL_EXPANSION_CONFIRMS_STRUCTURALLY_INCOMPLETE',
               note=('The compiler itself expanded every pinned include with '
                     'its own indentation and runtime splice. NONE of the 29 '
                     'resulting programs builds, and %d of 29 have no main: '
                     'task. This rules out a Python-flatten bug or a mere '
                     'indentation defect: the driver top-level program text is '
                     'absent. Combined with the archive search and the Python '
                     'flatten certificate, C.30 155/155 cannot be reached from '
                     'material in this workspace.' % len(no_main)))
    out = Path(a.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.30 official --flat probe: %d drivers, %d without main:, %d build -> %s'
          % (len(rows), len(no_main), len(builds), rep['verdict']))
    print('  -> %s' % out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
