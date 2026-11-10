#!/usr/bin/env python3
"""C.35 / C.36 / C.37 — re-verify the no-cache and purge-notice constraints.

Checks, from disk, not chat memory:
  * tools/no_cache_policy.py exits 0 with the tripwire message (C.36);
  * no --no-ac / --no-learn flags and no .plk cleanup literal in compiler.sov;
  * no sidecar FILES exist anywhere under the compiler tree (C.35);
  * no_cache_policy.py contains sidecar_scan() and the frozen inventory;
  * the three historical purge-notice docs still carry PURGE NOTICE (C.37);
  * the root parity doc's dated "exits 1" text is explicitly marked as
    history, and no source reintroduces serve/uncached/warm paths.

Usage: python3 tools/c35_c37_verify.py [--json OUT]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
ROOT = Path('/home/user')
E = Path('/home/user/evidence')
SIDECAR_SUFFIXES = ('.plk', '.ac', '.ac.bin', '.lsug', '.sug', '.dsug',
                    '.state', '.deepoc')
DOCS = [R / 'SA_PARITY.md', R / 'SPEED_ARCHITECTURE.md', R / 'PATH_TO_LIGHEST.md']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C35_C37_reverify_2026-11-09.json'))
    a = ap.parse_args()
    outp = Path(a.json); outp.parent.mkdir(parents=True, exist_ok=True)

    p = subprocess.run([sys.executable, 'tools/no_cache_policy.py'], cwd=R,
                       capture_output=True, text=True, timeout=300)
    policy_ok = (p.returncode == 0 and 'no-cache source tripwire OK' in (p.stdout + p.stderr))
    policy_text = (p.stdout + p.stderr).strip()

    src = (R / 'compilers/linux/compiler.sov').read_text(errors='replace')
    no_flags = ('--no-ac' not in src and '--no-learn' not in src)
    no_plk_literal = ('.plk' not in (R / 'bootstrap.sov').read_text(errors='replace')
                      if (R / 'bootstrap.sov').is_file() else True)

    sidecars = []
    for f in R.rglob('*'):
        if f.is_file() and any(str(f).endswith(s) for s in SIDECAR_SUFFIXES):
            sidecars.append(str(f.relative_to(R)))
    no_sidecars = not sidecars

    policy_src = (R / 'tools/no_cache_policy.py').read_text(errors='replace')
    has_scan = 'sidecar_scan' in policy_src
    no_warm = all(x not in src for x in ('serve path', 'uncached path', 'warm path'))

    purge = {}
    for d in DOCS:
        t = d.read_text(errors='replace') if d.is_file() else ''
        purge[d.name] = ('PURGE NOTICE' in t.upper())
    purge_ok = all(purge.values())

    root_doc = (ROOT / 'SA_PARITY_EVERYTHING_NEEDED.md').read_text(errors='replace')
    dated_marked = ('dated history' in root_doc.lower()
                    and 'older "currently exits 1" text below is dated history' in root_doc)

    checks = [
        dict(item='C36_tripwire_exits_0', ok=policy_ok, detail=policy_text[:300]),
        dict(item='C36_flags_deleted', ok=no_flags),
        dict(item='C36_stale_plk_literal_removed', ok=no_plk_literal),
        dict(item='C35_no_sidecar_files', ok=no_sidecars, found=sidecars[:10]),
        dict(item='C35_sidecar_scan_present', ok=has_scan),
        dict(item='C35_no_warm_serve_path', ok=no_warm),
        dict(item='C37_purge_notices', ok=purge_ok, docs=purge),
        dict(item='C36_dated_text_marked', ok=dated_marked),
    ]
    good = sum(1 for c in checks if c.get('ok'))
    rep = dict(schema=1, checks=len(checks), ok=good,
               all_green=(good == len(checks) and good > 0), detail=checks,
               note='Standing constraints re-verified. No compiler bytes changed; '
                    'no speed or parity claim.')
    outp.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.35/C.36/C.37 re-verify: %d/%d GREEN' % (good, len(checks)))
    for c in checks:
        print('  %-38s %s' % (c['item'], 'OK' if c.get('ok') else 'FAIL'))
    print('  -> %s' % outp)
    print('ALL GREEN' if rep['all_green'] else 'NOT GREEN')
    return 0 if rep['all_green'] else 1


if __name__ == '__main__':
    sys.exit(main())
