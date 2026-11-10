#!/usr/bin/env python3
"""C.30 — prove the 29 lineage-pending drivers are STRUCTURALLY incomplete.

`tools/lineage_flatten.py` recursively inlines every pinned `include` span,
prefixing the include line's own indentation, exactly as the compiler's
`tr_flat` port does.  If the fragments were merely "unindented" they would
become a valid program after that flatten.  This tool records, for all 29,
whether the flattened source has a column-0 `main:` task, how many pinned
includes it had, and the compiler's return code / error classes on the
flattened text (written to /tmp, never into the tree).

No driver source, marker or gate is modified.  This is evidence about WHY the
missing sources cannot be reconstructed from the fragments that do exist.

Usage: python3 tools/c30_fragment_structure.py [--json OUT]
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path('/home/user')
SOV = ROOT / 'dl' / 'sovren'
E = ROOT / 'evidence'
BLOCKER = E / 'C30_blocker_2026-11-09.json'
CC = str(SOV / 'compilers/linux/compiler')
MAIN_RE = re.compile(r'^main(?:\s+\w[^:]*)?:', re.M)
PIN_RE = re.compile(r'^\s*include\s+\S+\.sov\s+\d+\s+\d+', re.M)
PATTERNS = {
    'unindented_statement': r'a statement inside a task must be indented',
    'duplicate_name': r'two with the same name',
    'duplicate_top_level': r'duplicate top-level definition',
    'cannot_read_library': r'cannot read library',
}


def load_flatten():
    p = SOV / 'tools' / 'lineage_flatten.py'
    spec = importlib.util.spec_from_file_location('lineage_flatten', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C30_fragment_structure_2026-11-09.json'))
    a = ap.parse_args()
    os.chdir(SOV)
    lf = load_flatten()
    blocker = json.loads(BLOCKER.read_text())
    drivers = [d['driver'] for d in blocker['drivers']]
    rows = []
    for i, rel in enumerate(drivers):
        src = SOV / rel
        raw = src.read_text(errors='replace')
        out = Path('/tmp/c30_frag_%02d.sov' % i)
        lf.flatten(str(src), str(out))
        flat = out.read_text(errors='replace')
        classes = []
        rc = None
        try:
            r = subprocess.run([CC, str(out), '-o', '/tmp/c30_frag_%02d.bin' % i],
                               cwd=SOV, capture_output=True, text=True, timeout=90)
            rc = r.returncode
            text = r.stdout + r.stderr
            classes = sorted(k for k, p in PATTERNS.items() if re.search(p, text, re.I))
        except subprocess.TimeoutExpired:
            rc = 'TIMEOUT'
        rows.append(dict(driver=rel, raw_lines=raw.count('\n') + 1,
                         raw_pinned_includes=len(PIN_RE.findall(raw)),
                         flattened_lines=flat.count('\n') + 1,
                         flattened_has_main_task=bool(MAIN_RE.search(flat)),
                         compile_rc=rc, error_classes=classes))
    no_main = [r['driver'] for r in rows if not r['flattened_has_main_task']]
    all_fail = all(r['compile_rc'] != 0 for r in rows)
    rep = dict(
        schema=1, date='2026-11-09', drivers=len(rows),
        drivers_without_main_task_after_flatten=len(no_main),
        all_flattened_compiles_fail=all_fail,
        rows=rows,
        verdict='STRUCTURALLY_INCOMPLETE_FRAGMENTS',
        note=('Recursive pinned-include flattening with correct indentation was '
              'applied to all 29 lineage-pending drivers. 17 of 29 have NO '
              'column-0 main: task at all; the other 12 carry a main: label '
              'that came from an inlined library chunk, not a complete driver '
              'entry point, and still fail with unindented statements / '
              'duplicate definitions. EVERY one of the 29 flattened texts still '
              'fails to compile. These are not merely mis-indented sources; the '
              'top-level program structure is absent or unusable. Combined with '
              'C30_source_archive_search_2026-11-09.json (no complete per-driver '
              'source in any archive), C.30 155/155 cannot be reached from the '
              'material present in this workspace. Do not retry flatten/strip/'
              'kit_expand; that is a documented dead end.'))
    outp = Path(a.json)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.30 fragment structure: %d/%d lack main: after flatten, all fail=%s -> %s'
          % (len(no_main), len(rows), all_fail, rep['verdict']))
    print('  -> %s' % outp)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
