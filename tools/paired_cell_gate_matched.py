#!/usr/bin/env python3
"""Matched-work replacement for the 12 noncomparable `--flat` paired cells.

The frozen F7 matrix (`tools/paired_cell_gate.py`) uses FLAGS =
[('none', []), ('flat', ['--flat'])]. Sovren `--flat` emits FLAT TEXT while
`sa` emits an ELF, so 12 of the 24 cells are structurally NOT_MATCHED_WORK and
can never become GREEN no matter how fast the compiler gets (C.39).

This wrapper does NOT relax the gate and does NOT reclassify those cells as
GREEN. It builds a PARALLEL, equally-sized, strictly comparable 24-cell matrix
by swapping `--flat` for `--bare`, which emits an executable ELF with the same
expected exit codes (verified: exit7=7, sum=92, hello=0). Every cell is now
REAL matched work, so 0/24 is an honest speed result rather than 12 speed
results plus 12 definitional refusals.

It is deliberately a SEPARATE evidence file: `agent/completion_gate.py` still
reads the frozen `C20_C25_paired_cells_c4.json` and remains unchanged. An
approved definition change is still required before the frozen gate itself can
adopt this matrix.

Usage: python3 tools/paired_cell_gate_matched.py [--runs 21]
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
E = Path('/home/user/evidence')


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=21)
    a = ap.parse_args()
    out = E / 'C20_C25_matched_work_c4.json'
    pc = load('paired_cell_gate')
    pc.FLAGS = [('none', []), ('bare', ['--bare'])]
    sys.argv = ['paired_cell_gate.py', '--runs', str(a.runs), '--output', str(out)]
    rc = pc.main()          # 1 is expected: the speed cells are still RED
    d = json.loads(out.read_text())
    d['matrix'] = '3 workloads x 2 sizes x 2 modes x 2 flags (MATCHED WORK: none / --bare)'
    d['rules']['flat_cells_not_matched_work'] = False
    d['rules']['all_cells_matched_work'] = True
    d['rules']['frozen_gate_unchanged'] = True
    d['replaces'] = ('12 NOT_MATCHED_WORK --flat cells in '
                     'C20_C25_paired_cells_c4.json; this is a parallel '
                     'measurement, not a change to the frozen acceptance gate.')
    d['harness_valid'] = (d.get('cells') == 24
                          and all(c.get('verdict') in ('GREEN', 'FAIL') for c in d['detail'])
                          and all('NOT_MATCHED_WORK' not in str(c.get('reason', ''))
                                  for c in d['detail']))
    out.write_text(json.dumps(d, indent=2) + '\n')
    print('\nMatched-work matrix: %d/%d GREEN, harness_valid=%s, frozen gate rc=%s'
          % (d['green'], d['cells'], d['harness_valid'], rc))
    print('  -> %s' % out)
    return 0 if d['harness_valid'] else 1


if __name__ == '__main__':
    sys.exit(main())
