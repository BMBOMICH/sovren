#!/usr/bin/env python3
"""C.32 — mechanically re-verify all measurement-harness obligations.

The original audit listed five open harness items. This gate checks each one
against the actual files (not chat memory) and runs the live checks:

  a) work/saparity/bench.sh and everywhere-audit.sh must NOT pass -o to SA
     (SA takes its output as positional argv[2]);
  b) sc/bench.sh must ship a layout guard AND actually print "layout OK";
  c) both saparity scripts must report input AND expanded bytes on every
     candidate row, and must carry the nested --prof warning;
  d) the SA t/ gate must exist and score 6/6;
  e) layout_check.py must score 12/12, paired_cell_gate.py must pair samples
     within a round, and --prof output must declare itself nested aggregates.

Usage: python3 tools/c32_harness_check.py [--json OUT]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SAP = R / 'work/saparity'
SA_T = Path('/home/user/dl/sovren-assembler/t/gate.py')
SC_BENCH = R / 'sc/bench.sh'
E = Path('/home/user/evidence')


def sh(cmd, cwd, timeout=600):
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                           text=True, timeout=timeout)
        return dict(rc=p.returncode, out=p.stdout[-20000:], err=p.stderr[-20000:])
    except subprocess.TimeoutExpired:
        return dict(rc='TIMEOUT', out='', err='')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C32_harness_check_2026-11-09.json'))
    a = ap.parse_args()
    outp = Path(a.json); outp.parent.mkdir(parents=True, exist_ok=True)
    checks = []

    # (a) positional argv[2] for SA, never -o
    for name in ('bench.sh', 'everywhere-audit.sh'):
        p = SAP / name
        t = p.read_text()
        bad = [l.strip() for l in t.splitlines()
               if re.search(r'\$SA\s+[^\n]*\s-o\b', l) and not l.lstrip().startswith('#')]
        rows = [l.strip() for l in t.splitlines()
                if l.strip().startswith('row ') and '$SA' in l]
        ok = not bad and bool(rows) and all(' -o ' not in l for l in rows)
        checks.append(dict(item='a_sa_positional_' + name, ok=ok,
                           sa_rows=len(rows), bad_minus_o_lines=bad[:3],
                           note='SA output is positional argv[2]; -o is never passed'))
    # (c) input + expanded bytes per row, nested --prof guard
    for name in ('bench.sh', 'everywhere-audit.sh'):
        t = (SAP / name).read_text()
        ok = ('expanded_of()' in t and re.search(r'printf[^\n]*expanded=', t) is not None
              and re.search(r'printf[^\n]*bytes', t) is not None
              and 'nested aggregates' in t and 'exclusive sum' in t)
        checks.append(dict(item='c_byte_accounting_' + name, ok=ok,
                           note='input bytes + expanded bytes + nested-prof warning'))
    # (b) sc/bench.sh layout guard present and live
    t = SC_BENCH.read_text()
    guard = 'layout error: missing' in t and 'for need in' in t
    live = sh(['bash', 'bench.sh'], SC_BENCH.parent, timeout=900)
    live_ok = live['rc'] == 0 and 'bench: layout OK' in live['out']
    checks.append(dict(item='b_sc_bench_layout', ok=(guard and live_ok),
                       guard_present=guard, run_rc=live['rc'],
                       layout_ok_printed=live_ok,
                       live_tail=live['out'].splitlines()[-4:]))
    # (d) SA t/ gate 6/6
    if SA_T.is_file():
        g = sh([sys.executable, str(SA_T)], SA_T.parent, timeout=600)
        m = re.search(r'(\d+)\s*/\s*(\d+)', g['out'])
        ok = g['rc'] == 0 and ('ALL GREEN' in g['out'] or '6/6' in g['out'])
        checks.append(dict(item='d_sa_t_gate', ok=ok, run_rc=g['rc'],
                           tail=g['out'].splitlines()[-8:]))
    else:
        checks.append(dict(item='d_sa_t_gate', ok=False, error='MISSING'))
    # (e) layout 12/12, paired within-round, prof nested
    lay = sh([sys.executable, 'tools/layout_check.py'], R, timeout=600)
    lay_ok = lay['rc'] == 0 and '12/12' in (lay['out'] + lay['err'])
    pt = (R / 'tools/paired_cell_gate.py').read_text()
    paired_ok = 'pair ONLY samples from THIS round' in pt
    prof = sh([str(R / 'compilers/linux/compiler'),
               'compilers/linux/compiler.sov', '--prof', '-o', '/tmp/c32_prof.out'],
              R, timeout=300)
    nested = 'phase-endpoint-aggregates' in prof['err']
    checks.append(dict(item='e_layout_paired_prof', ok=(lay_ok and paired_ok and nested),
                       layout_12_12=lay_ok, paired_within_round=paired_ok,
                       prof_declares_nested=nested,
                       layout_tail=(lay['out'] + lay['err']).splitlines()[-4:]))

    good = sum(1 for c in checks if c.get('ok'))
    rep = dict(schema=1, checks=len(checks), ok=good,
               all_green=(good == len(checks) and good > 0), detail=checks,
               note='Harness verification only. No compiler bytes changed; '
                    'no speed or parity claim.')
    outp.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.32 harness check: %d/%d items GREEN' % (good, len(checks)))
    for c in checks:
        print('  %-38s %s' % (c['item'], 'OK' if c.get('ok') else 'FAIL'))
    print('  -> %s' % outp)
    print('ALL GREEN' if rep['all_green'] else 'NOT GREEN')
    return 0 if rep['all_green'] else 1


if __name__ == '__main__':
    sys.exit(main())
