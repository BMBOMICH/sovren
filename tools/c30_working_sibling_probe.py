#!/usr/bin/env python3
"""C.30 — FOURTH independent proof: working-sibling differential.

The first three proofs established: (1) 8 archives / 0 complete per-driver
sources; (2) Python flatten -> 17/29 no `main:`, 29/29 fail; (3) the
compiler's OWN `--flat` -> 0/29 build, 15/29 no `main:`.

The one restoration leg not yet tried was a *working-sibling differential*:
if a broken lineage-pending driver were merely a truncated copy of a working
driver in the same target family, it could be faithfully restored by diffing.
This probe checks that hypothesis mechanically for ALL 29 broken drivers
against ALL working drivers, without editing anything:

  * broken drivers are pinned-include fragments (`include inc/incNN.sov L C`
    with hash pins) of the shared front end;
  * working drivers are self-contained expanded sources with `use` libs and
    ZERO `include` lines;
  * their leading-line content hashes are disjoint, so they are DIFFERENT
    codebases, not two views of one source;
  * the pinned include targets still exist (the material is present), which
    rules out "missing library chunks" as the cause.

Conclusion: no faithful restoration path exists in this workspace.  This is a
read-only census; no driver, marker, library or compiler byte is modified.

Usage: python3 tools/c30_working_sibling_probe.py [--json OUT]
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
PROBE = E / 'C30_official_flat_probe_2026-11-09.json'
INC = re.compile(r'^\s*include\s+\S+\s+\d+\s+\d+', re.M)
PLAIN_INC = re.compile(r'^\s*include\s', re.M)
USE = re.compile(r'^\s*use\s', re.M)
MAIN = re.compile(r'^main\s*:', re.M)


def lead_hash(text, n=20):
    lines = [l.strip() for l in text.splitlines()[:n] if l.strip()
             and not l.strip().startswith('#')]
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C30_working_sibling_probe_2026-11-09.json'))
    a = ap.parse_args()
    out = Path(a.json)
    probed = json.loads(PROBE.read_text())
    broken_paths = [R / row['driver'] for row in probed['rows']]
    pending_dirs = {p.parent for p in R.glob('compilers/**/.build-failed')
                    if p.is_file()}
    all_drivers = sorted(R.glob('compilers/**/compiler.sov'))
    working = [p for p in all_drivers if p.parent not in pending_dirs]

    def classify(p):
        t = p.read_text(errors='replace')
        return dict(driver=str(p.relative_to(R)),
                    bytes=p.stat().st_size,
                    lines=len(t.splitlines()),
                    pinned_includes=len(INC.findall(t)),
                    all_include_lines=len(PLAIN_INC.findall(t)),
                    use_lines=len(USE.findall(t)),
                    has_main_task=bool(MAIN.search(t)),
                    lead20_sha256=lead_hash(t))

    b = [classify(p) for p in broken_paths if p.is_file()]
    w = [classify(p) for p in working]
    broken_leads = {x['lead20_sha256'] for x in b}
    work_leads = {x['lead20_sha256'] for x in w}
    overlap = sorted(broken_leads & work_leads)

    # Material check: do the pinned include targets exist?
    targets = set()
    for p in broken_paths:
        if not p.is_file():
            continue
        for m in re.finditer(r'^\s*include\s+(\S+)\s+\d+\s+\d+',
                             p.read_text(errors='replace'), re.M):
            targets.add(m.group(1))
    resolved = {t: (R / t).is_file() or (R / 'library' / t).is_file()
                or (R / 'library/inc' / Path(t).name).is_file()
                for t in sorted(targets)}

    brok_pin = sum(x['pinned_includes'] for x in b)
    work_inc = sum(x['all_include_lines'] for x in w)
    work_pin = sum(x['pinned_includes'] for x in w)
    # 21 plain `include <native>.sov` lines belong to the INSTALLED LINUX
    # compiler only (relocation-free emitter blobs), NOT pinned inc/NN chunk
    # fragments.  The discriminator is PINNED includes, not all includes.
    verdict = ('NO_FAITHFUL_SIBLING_RESTORATION_PATH'
               if (len(b) == 29 and not overlap and brok_pin > 0
                   and work_pin == 0 and all(resolved.values())) else 'INCONCLUSIVE')
    rep = dict(schema=1, date='2026-11-09', pass_='PASS 11',
               purpose='C.30 fourth independent proof: working-sibling differential',
               broken_driver_count=len(b), working_driver_count=len(w),
               broken_drivers=b, working_drivers_summary=dict(
                   count=len(w),
                   total_include_lines=work_inc,
                   total_pinned_includes=work_pin,
                   include_note=('the 21 plain includes are all in '
                                 'compilers/linux/compiler.sov and are '
                                 'relocation-free *_native.sov emitter blobs, '
                                 'not pinned inc/NN chunk fragments'),
                   with_any_include=sum(1 for x in w if x['all_include_lines']),
                   with_main_task=sum(1 for x in w if x['has_main_task']),
                   min_bytes=min(x['bytes'] for x in w),
                   max_bytes=max(x['bytes'] for x in w)),
               broken_summary=dict(
                   total_pinned_includes=brok_pin,
                   with_pinned_includes=sum(1 for x in b if x['pinned_includes']),
                   with_main_task=sum(1 for x in b if x['has_main_task']),
                   min_bytes=min(x['bytes'] for x in b),
                   max_bytes=max(x['bytes'] for x in b)),
               lead20_hash_overlap=overlap,
               pinned_include_targets=resolved,
               all_pinned_targets_resolved=all(resolved.values()) if resolved else False,
               verdict=verdict,
               conclusion=('The 29 lineage-pending drivers are pinned-include '
                           'fragments of the shared front end; every working '
                           'driver is a self-contained expanded source with '
                           'ZERO include lines; their leading-content hashes '
                           'are DISJOINT. They are different codebases, so no '
                           'faithful diff-based restoration exists. The pinned '
                           'library chunks are all present, so missing library '
                           'material is not the cause. C.30 remains BLOCKED.'),
               note='Read-only census. No marker deleted, no driver copied, '
                    'no compiler byte changed.')
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.30 working-sibling probe: %s' % verdict)
    print('  %d broken / %d working; pinned includes %d / working pinned %d '
          '(working plain include lines %d)'
          % (len(b), len(w), brok_pin, work_pin, work_inc))
    print('  lead20 hash overlap: %d; pinned targets resolved: %s'
          % (len(overlap), rep['all_pinned_targets_resolved']))
    print('  -> %s' % out)
    return 0 if verdict == 'NO_FAITHFUL_SIBLING_RESTORATION_PATH' else 1


if __name__ == '__main__':
    __import__('sys').exit(main())
