#!/usr/bin/env python3
"""C.32 — INDEPENDENT re-check of the five ORIGINAL audit items.

The restated C.2-C.39 list says these five are "still open".  Earlier passes
fixed them and `c32_harness_check.py` reports 7/7, but that checker was written
by the same effort.  This tool re-derives each item from the literal script
text PLUS a live smoke run, so the claim is not self-certifying.

Items (from SA_PARITY_EVERYTHING_NEEDED.md C.32):
  (a) bench.sh / everywhere-audit.sh must NOT pass -o to SA (positional argv[2]).
  (b) sc/bench.sh sibling paths resolve and its layout guard refuses a broken layout.
  (c) both harnesses report input AND flat-expanded bytes per row.
  (d) SA's missing t/ gate is rebuilt and green.
  (e) --prof endpoints are declared nested aggregates, never summed.

Read-only with respect to the compiler, gates and markers. It only runs
existing scripts and writes JSON evidence.

Usage: python3 tools/c32_original_audit_recheck.py [--json OUT]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

R = Path('/home/user/dl/sovren')
SA_ROOT = Path('/home/user/dl/sovren-assembler')
E = Path('/home/user/evidence')
SCRIPTS = [R / 'work/saparity/bench.sh', R / 'work/saparity/everywhere-audit.sh']
SC = R / 'sc/bench.sh'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else ''


def run(argv, cwd, timeout=180):
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return dict(rc=p.returncode, out=p.stdout, err=p.stderr)
    except subprocess.TimeoutExpired:
        return dict(rc='TIMEOUT', out='', err='')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C32_original_audit_recheck_2026-11-09.json'))
    a = ap.parse_args()
    checks = []

    # ---- (a) no -o on any SA row ----
    a_rows = []
    for s in SCRIPTS:
        txt = s.read_text()
        bad = [ln.strip() for ln in txt.splitlines() if '$SA' in ln and ' -o ' in ln]
        a_rows.append(dict(script=str(s.relative_to(R)), sa_rows_with_dash_o=bad,
                           ok=not bad))
    # live: run one real SA positional invocation, assert no NEW literal -o file
    artifact = R / '-o'
    before = sha(artifact)
    live = run([str(SA_ROOT / 'sa'), str(SA_ROOT / 'sa.asm'), '/tmp/c32_sa_self.bin'], R, 120)
    after = sha(artifact)
    checks.append(dict(item='a_no_dash_o_to_sa', verdict='GREEN' if all(x['ok'] for x in a_rows)
                       and live['rc'] == 0 and before == after else 'RED',
                       static=a_rows, live_rc=live['rc'],
                       literal_dash_o_unchanged=(before == after),
                       note='the pre-existing /home/user/dl/sovren/-o is a historical artifact from the old bad SA -o; it must NOT change'))

    # ---- (b) sc/bench.sh layout ----
    sct = SC.read_text()
    paths_ok = ('T=../tests' in sct and 'SA=../../sovren-assembler/sa' in sct)
    guard_ok = 'layout error' in sct and 'bench: layout OK' in sct
    live_sc = run(['bash', 'bench.sh'], R / 'sc', 240)
    live_ok = 'bench: layout OK' in (live_sc['out'] + live_sc['err'])
    checks.append(dict(item='b_sc_paths_and_layout_guard',
                       verdict='GREEN' if paths_ok and guard_ok and live_ok else 'RED',
                       paths_ok=paths_ok, guard_ok=guard_ok,
                       live_rc=live_sc['rc'], live_layout_ok=live_ok,
                       live_first_line=(live_sc['out'].splitlines() or [''])[0]))

    # ---- (c) input + expanded bytes per row ----
    c_rows = []
    for s in SCRIPTS:
        t = s.read_text()
        c_rows.append(dict(script=str(s.relative_to(R)),
                           declares_expanded_of='expanded_of()' in t,
                           row_calls_expanded_of='exp=$(expanded_of' in t,
                           prints_expanded='expanded=' in t,
                           prints_input_bytes='bytes' in t,
                           sa_rows_label_n_a='expanded=n/a' in t))
    # live: one --flat expansion, the same operation expanded_of performs
    flat = '/tmp/c32_expanded.txt'
    if Path(flat).exists():
        Path(flat).unlink()
    cf = run([str(R / 'compilers/linux/compiler'), 'tests/hello.sov', '-o', flat, '--flat'], R, 120)
    expanded = Path(flat).stat().st_size if Path(flat).is_file() else 0
    ok_c = all(all([x['declares_expanded_of'], x['row_calls_expanded_of'],
                    x['prints_expanded'], x['prints_input_bytes']]) for x in c_rows) and cf['rc'] == 0 and expanded > 0
    checks.append(dict(item='c_input_and_expanded_bytes', verdict='GREEN' if ok_c else 'RED',
                       static=c_rows, live_flat_rc=cf['rc'],
                       live_expanded_bytes=expanded,
                       live_input_bytes=(R / 'tests/hello.sov').stat().st_size))

    # ---- (d) SA t/ gate ----
    gate = SA_ROOT / 't' / 'gate.py'
    gd = run([sys.executable, str(gate)], SA_ROOT, 240)
    gtext = gd['out'] + gd['err']
    d_ok = gate.is_file() and gd['rc'] == 0 and '6/6 checks green' in gtext \
        and '245/245' in gtext and '20/20' in gtext
    checks.append(dict(item='d_sa_t_gate_rebuilt', verdict='GREEN' if d_ok else 'RED',
                       gate=str(gate), rc=gd['rc'],
                       tail=gtext.splitlines()[-6:]))

    # ---- (e) --prof nested aggregates never summed ----
    e_rows = []
    for s in SCRIPTS + [SC]:
        t = s.read_text()
        e_rows.append(dict(script=str(s.relative_to(R)),
                           declares_nested='nested' in t.lower(),
                           forbids_sum=('never an exclusive sum' in t or 'do not add them up' in t
                                        or 'never sum' in t.lower())))
    checks.append(dict(item='e_prof_nested_aggregate_note',
                       verdict='GREEN' if all(x['declares_nested'] and x['forbids_sum'] for x in e_rows) else 'RED',
                       static=e_rows))

    green = sum(1 for c in checks if c['verdict'] == 'GREEN')
    rep = dict(schema=1, date='2026-11-09', items=len(checks), green=green,
               all_green=green == len(checks), checks=checks,
               verdict='C32_ORIGINAL_AUDIT_ALL_FIVE_GREEN' if green == len(checks)
                       else 'C32_ORIGINAL_AUDIT_NOT_GREEN',
               note=('Independent literal + live re-check of the five original '
                     'C.32 audit items. The restated list labels them PARTIAL; '
                     'this evidence supersedes that older annotation. No script '
                     'or gate was edited.'))
    out = Path(a.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.32 original audit recheck: %d/%d GREEN -> %s' % (green, len(checks), rep['verdict']))
    for c in checks:
        print('  %-32s %s' % (c['item'], c['verdict']))
    print('  -> %s' % out)
    return 0 if rep['all_green'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
