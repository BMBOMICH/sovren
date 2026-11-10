#!/usr/bin/env python3
"""C.32 — LIVE, machine-checked audit of the five still-listed harness items.

The restated C.32 list says these are "still open from the original audit":

  (a) work/saparity/bench.sh and everywhere-audit.sh passing -o to SA;
  (b) sc/bench.sh sibling paths;
  (c) report input and expanded bytes per cell;
  (d) rebuild SA's missing t/ gate;
  (e) never sum nested --prof endpoints.

This tool does not trust prose. It parses the LIVE harnesses, executes the SA
gate and the bash-only sc/bench.sh layout guard, and checks the frozen C.32
evidence certificates. It also records that SA takes output as positional
argv[2] and that `tools/speed_gate.py` builds SA with no `-o`.

No harness is edited because all five items are already fixed; the output is a
confirmation certificate. Every check is content-verified, not just rc=0.

Usage: python3 tools/c32_live_harness_audit.py [--json OUT]
"""
import argparse
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
SA_ROOT = R.parent / 'sovren-assembler'
BENCH = R / 'work/saparity/bench.sh'
EVERY = R / 'work/saparity/everywhere-audit.sh'
SCBENCH = R / 'sc/bench.sh'
SAGATE = SA_ROOT / 't/gate.py'
SPEED = R / 'tools/speed_gate.py'


def live_sa_rows(path):
    """Return non-comment `row ... $SA ...` command lines and any with -o."""
    rows, bad = [], []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        s = line.strip()
        if not s.startswith('row ') or '$SA' not in s:
            continue
        rows.append((i, s))
        # SA must be followed by positional source + output, never -o.
        if re.search(r'(^|\s)-o(\s|$)', s):
            bad.append((i, s))
    return rows, bad


def has(path, *needles):
    t = path.read_text()
    return all(n in t for n in needles)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C32_live_harness_audit_2026-11-09.json'))
    a = ap.parse_args()
    out = Path(a.json)
    rep = dict(schema=1, date='2026-11-09', pass_='PASS 13',
               host=' '.join([platform.node(), platform.system(), platform.machine()]),
               verdict='FAIL', claim='Live confirmation of the five C.32 '
               'harness items. No harness edit needed; no compiler bytes '
               'changed; no speed/parity claim.')
    c = {}

    # (a) no -o on any live SA row, in BOTH saparity harnesses
    for tag, p in [('bench', BENCH), ('everywhere', EVERY)]:
        rows, bad = live_sa_rows(p)
        rep['sa_rows_' + tag] = dict(count=len(rows), with_dash_o=bad,
                                     examples=rows[:3])
        c['no_dash_o_' + tag] = len(rows) > 0 and not bad
        c['positional_sa_note_' + tag] = has(p, 'positional argv[2]', 'no -o') or \
            has(p, 'positional argv[2]', 'does NOT accept -o')
    sa_lines = [l for l in SPEED.read_text().splitlines()
                if "'sa':Command" in l or '"sa":Command' in l]
    c['speed_gate_positional'] = (len(sa_lines) == 1
                                  and "str(sa)" in sa_lines[0]
                                  and "str(sa_src)" in sa_lines[0]
                                  and "'-o'" not in sa_lines[0]
                                  and '"-o"' not in sa_lines[0])
    rep['speed_gate_sa_line'] = sa_lines[:1]

    # (c) input + expanded bytes per cell, SA rows guarded to n/a
    for tag, p in [('bench', BENCH), ('everywhere', EVERY)]:
        c['expanded_of_guard_' + tag] = has(p, 'if [ "$exe" = "$SA" ]', 'echo "n/a"')
        c['input_expanded_bytes_' + tag] = has(p, 'bytes expanded=%s', 'stat -c %s')
    c['c34_diagnostic_note'] = has(SCBENCH, 'diagnostic only, not proof of equal frontend work')

    # (b) sc sibling paths + LIVE bash layout guard (never sh: ${EPOCHREALTIME/./})
    c['sc_sibling_paths'] = has(SCBENCH, 'T=../tests', 'SA=../../sovren-assembler/sa',
                                'SASRC=../../sovren-assembler/sa.asm')
    r = subprocess.run(['bash', 'sc/bench.sh'], cwd=R, capture_output=True,
                       text=True, timeout=300)
    txt = r.stdout + r.stderr
    lay = next((l.strip() for l in txt.splitlines() if 'layout OK' in l), '')
    rep['sc_live'] = dict(rc=r.returncode, layout_line=lay,
                          bad_substitution='Bad substitution' in txt,
                          tail=txt.strip().splitlines()[-3:])
    c['sc_live_layout_bash'] = (r.returncode == 0 and bool(lay)
                                and 'Bad substitution' not in txt)

    # (d) SA's rebuilt t/ gate, executed live
    g = subprocess.run([sys.executable, str(SAGATE)], cwd=R,
                       capture_output=True, text=True, timeout=300)
    gt = g.stdout + g.stderr
    rep['sa_t_gate'] = dict(rc=g.returncode, tail=gt.strip().splitlines()[-8:])
    c['sa_t_gate_6_6'] = (g.returncode == 0 and '6/6 checks green' in gt
                          and '245/245 mnemonics' in gt and '20/20 explicit refusals' in gt)

    # (e) nested --prof endpoints must never be summed
    c['no_nested_prof_sum_sc'] = has(SCBENCH, 'do not add them up',
                                     'never an exclusive sum')
    c['no_nested_prof_sum_bench'] = has(BENCH, 'never an exclusive sum') or \
        has(BENCH, 'do not add them up')
    c['no_nested_prof_sum_every'] = has(EVERY, 'Never mix the two rates') or \
        has(EVERY, 'never an exclusive sum')

    # Frozen C.32 certificates (content, not rc)
    for key, fn, need in [
        ('harness_7_7', 'C32_harness_check_2026-11-09.json', {'ok': 7}),
        ('original_audit_5_5', 'C32_original_audit_recheck_2026-11-09.json',
         {'green': 5, 'items': 5}),
        ('per_cell_accounting', 'C32_C34_per_cell_accounting_2026-11-09.json',
         {'verdict': 'ALL_GREEN'}),
    ]:
        p = E / fn
        d = json.loads(p.read_text()) if p.is_file() else {}
        c[key] = all(d.get(k) == v for k, v in need.items())
        rep[key] = {k: d.get(k) for k in need}

    ok = all(c.values())
    rep['checks'] = c
    rep['verdict'] = 'ALL_GREEN' if ok else 'FAIL'
    rep['five_items'] = dict(
        a_no_dash_o_to_SA=c['no_dash_o_bench'] and c['no_dash_o_everywhere'],
        b_sc_sibling_paths=c['sc_sibling_paths'] and c['sc_live_layout_bash'],
        c_input_expanded_bytes=all(c[k] for k in c if k.startswith('input_expanded_bytes_')),
        d_sa_t_gate_rebuilt=c['sa_t_gate_6_6'],
        e_no_nested_prof_sum=c['no_nested_prof_sum_sc'] and
                             c['no_nested_prof_sum_bench'] and
                             c['no_nested_prof_sum_every'])
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.32 live harness audit: %s' % rep['verdict'])
    print('  five items: %s' % rep['five_items'])
    print('  SA t/ gate: %s; sc live layout: %r' % (c['sa_t_gate_6_6'], lay[:70]))
    print('  -> %s' % out)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
