#!/usr/bin/env python3
"""C.32 harness item — validate that generated `unsafe-module` .sov twins
actually PARSE, LINK and EXECUTE as included modules of a real Sovren host.

A .sov native twin is NOT a standalone program: compiling it directly returns
rc=1 (no `main`), which is also true for the shipped certified twins. The
correct integration contract is `include <twin>.sov` at top level of a host
program. This gate enforces that contract for every generated twin, plus a
shipped-twin control, and records the honest result of the standalone attempt.

Usage: python3 tools/twin_include_gate.py [--json OUT]
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
CC = R / 'compilers/linux/compiler'
SHIPPED = R / 'compilers/linux/basescan_native.sov'
E = Path('/home/user/evidence')
TWINS = [
    ('reader_scaffold_control', E / 'C11_reader_twin_scaffold.sov'),
    ('reader_fused_descriptor', E / 'C11_fused_reader_twin.sov'),
    ('shape_scan_portable_blob', E / 'C15_C16_shape_scan_twin.sov'),
    ('shipped_basescan_control', SHIPPED),
]


def compile_one(cc, src, out, timeout=180):
    if out.exists():
        out.unlink()
    try:
        p = subprocess.run([str(cc), str(src), '-o', str(out)],
                           cwd=R, capture_output=True, timeout=timeout)
        return dict(rc=p.returncode,
                    stdout=p.stdout.decode('utf8', 'replace')[:200],
                    stderr=p.stderr.decode('utf8', 'replace')[:200],
                    size=out.stat().st_size if out.is_file() else 0)
    except subprocess.TimeoutExpired:
        return dict(rc='TIMEOUT', stdout='', stderr='', size=0)


def exec_one(out, timeout=10):
    if not out.is_file():
        return None
    out.chmod(0o755)
    try:
        p = subprocess.run([str(out)], capture_output=True, timeout=timeout)
        return p.returncode
    except subprocess.TimeoutExpired:
        return 'TIMEOUT'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C32_twin_include_gate.json'))
    a = ap.parse_args()
    outp = Path(a.json); outp.parent.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='twin-include-') as td:
        t = Path(td)
        for name, twin in TWINS:
            if not twin.is_file():
                results.append(dict(twin=name, error='MISSING', ok=False))
                continue
            frag = t / (name + '.sov')
            shutil.copyfile(twin, frag)
            standalone = compile_one(CC, frag, t / (name + '.standalone'))
            host = t / (name + '.host.sov')
            host.write_text('include %s.sov\nmain:\n    return 7\n' % name)
            hout = t / (name + '.host.out')
            linked = compile_one(CC, host, hout)
            erc = exec_one(hout)
            ok = (standalone['rc'] != 0 and linked['rc'] == 0
                  and linked['size'] > 0 and erc == 7)
            results.append(dict(twin=name, file=str(twin),
                                standalone_compile_rc=standalone['rc'],
                                standalone_note='expected: unsafe-module fragment has no main',
                                include_compile_rc=linked['rc'],
                                include_output_bytes=linked['size'],
                                include_exec_rc=erc, ok=ok))
    good = sum(1 for x in results if x.get('ok'))
    rep = dict(schema=1, twins=len(results), ok=good,
               all_green=(good == len(results) and good > 0),
               results=results,
               note='Include/link/exec validation only. These twins are not '
                    'wired into compiler.sov; no whole-compile speed claim.')
    outp.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.32 twin include gate: %d/%d include+link+exec OK' % (good, len(results)))
    for x in results:
        print('  %-28s standalone_rc=%-4s include_rc=%-4s exec=%-4s %s'
              % (x.get('twin'), x.get('standalone_compile_rc'),
                 x.get('include_compile_rc'), x.get('include_exec_rc'),
                 'OK' if x.get('ok') else 'FAIL'))
    print('  -> %s' % outp)
    print('ALL GREEN' if rep['all_green'] else 'NOT GREEN')
    return 0 if rep['all_green'] else 1


if __name__ == '__main__':
    sys.exit(main())
