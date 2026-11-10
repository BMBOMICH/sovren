#!/usr/bin/env python3
"""C.11 / C.29 — rebuild + certify the LOST S27/S29 fused-reader build tool.

The user's list says `tools/native/build_native_reader.py is gone` and asks for
"one pass computing len/lead32/trim bounds/colon/lp plus body fields,
differ-certified, >=2.6 ms real deletion".  PASS 2 had reconstructed the
descriptor core (`tools/native_reader_fused.c`, 23 fields in ONE forward byte
loop) and its differential gate, but the BUILD TOOL's own docstring still said
the fused C source was missing and the surviving `shim_reader.so` was an A/A
placeholder.

This gate closes the *reconstruction* part:

  1. runs `tools/native/build_native_reader.py` on `native_reader_fused.c`,
     producing a relocation-free, undefined-symbol-free .text twin
     (`evidence/C11_pass13_fused_descriptor_twin.sov` + build JSON);
  2. runs `tools/reader_descriptor_gate.py` (counterexample-first 23-field
     differential over stress + PRNG + real .sov corpora, R=21 rotated A/B);
  3. runs `tools/nb_disasm_verify.py` with the new twin registered (C.29:
     reconstructed SHA == gcc .text, zero `(bad)` instructions, exact hex
     round-trip);
  4. proves the old `work/p4/s29/shim_reader.so` is BYTE-IDENTICAL to
     `old_reader.so` in .text, so the old "100/100 differ" was an A/A harness
     self-check, NOT a fused-core certification.

It does NOT claim the >=2.6 ms whole-compile deletion: the descriptor core is
CERTIFIED_NOT_INSTALLED and wiring it into compiler.sov / C1 / bw is still
OPEN.  No compiler bytes change, no whole-compile speed or parity claim.

Usage: python3 tools/c11_reader_reconstruction_gate.py [--json OUT]
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')
BUILD = R / 'tools/native/build_native_reader.py'
SRC = R / 'tools/native_reader_fused.c'
TWIN = E / 'C11_pass13_fused_descriptor_twin.sov'
BUILD_JSON = E / 'C11_pass13_fused_descriptor_build.json'
DESC_JSON = E / 'C11_fused_descriptor_gate.json'
NB_JSON = E / 'C29_nb_disasm_verify.json'
OLD_SO = R / 'work/p4/s29/old_reader.so'
SHIM_SO = R / 'work/p4/s29/shim_reader.so'


def text_of(so, tmp):
    out = Path(tmp) / (so.name + '.text')
    subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', str(so), str(out)],
                   check=True, capture_output=True)
    return out.read_bytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C11_reader_reconstruction_2026-11-09.json'))
    a = ap.parse_args()
    out = Path(a.json)
    rep = dict(schema=1, date='2026-11-09', pass_='PASS 13',
               host=' '.join([platform.node(), platform.system(), platform.machine()]),
               verdict='FAIL', install_status='CERTIFIED_NOT_INSTALLED',
               whole_compile_deletion='NOT_LANDED',
               claim='Rebuilt tool + certified descriptor core only. No '
                     'compiler bytes changed, no whole-compile speed claim, '
                     'no parity/completion claim.')
    checks = {}

    # 1) rebuild the lost build tool's artifact from the reconstructed core
    r = subprocess.run([sys.executable, str(BUILD), '--source', str(SRC),
                        '--entry', 'fused_descriptors',
                        '--symbol', 'emit_nt_reader_desc',
                        '--out', str(TWIN), '--json', str(BUILD_JSON)],
                       cwd=R, capture_output=True, text=True, timeout=300)
    bj = json.loads(BUILD_JSON.read_text()) if BUILD_JSON.is_file() else {}
    checks['build_tool_rc0'] = r.returncode == 0
    checks['build_verdict_pass'] = bj.get('verdict') == 'PASS'
    checks['no_undefined_symbols'] = bj.get('checks', {}).get('no_undefined_symbols') is True
    checks['no_relocations'] = bj.get('checks', {}).get('no_relocations') is True
    checks['text_bytes_2294'] = bj.get('text_bytes') == 2294
    rep['build'] = bj

    # 2) differential + core-level A/B certification
    r2 = subprocess.run([sys.executable, 'tools/reader_descriptor_gate.py',
                         '--cases', '120', '--json', str(DESC_JSON)],
                        cwd=R, capture_output=True, text=True, timeout=900)
    dj = json.loads(DESC_JSON.read_text()) if DESC_JSON.is_file() else {}
    checks['descriptor_gate_rc0'] = r2.returncode == 0
    checks['descriptor_cases_ge_120'] = dj.get('cases', 0) >= 120
    checks['descriptor_zero_mismatches'] = dj.get('mismatches') == 0
    checks['descriptor_23_fields'] = dj.get('fields') == 23
    checks['descriptor_credible_core_ab'] = (
        dj.get('placebo', {}).get('verdict') == 'CREDIBLE_WIN'
        and dj.get('placebo', {}).get('outside_band') is True
        and dj.get('speed_ratio', 0) > 1.5)
    rep['descriptor'] = dict(cases=dj.get('cases'), lines=dj.get('lines_compared'),
                             mismatches=dj.get('mismatches'),
                             speed_ratio=dj.get('speed_ratio'),
                             placebo=dj.get('placebo'),
                             all_green=dj.get('all_green'))

    # 3) C.29 nb_disasm_verify on the new blob (PAIRS updated in the tool)
    r3 = subprocess.run([sys.executable, 'tools/nb_disasm_verify.py',
                         '--json', str(NB_JSON)],
                        cwd=R, capture_output=True, text=True, timeout=300)
    nj = json.loads(NB_JSON.read_text()) if NB_JSON.is_file() else {}
    pair = next((x for x in nj.get('results', [])
                 if x.get('blob') == 'pass13_fused_descriptor'), {})
    checks['nb_disasm_rc0'] = r3.returncode == 0
    checks['nb_disasm_all_green'] = nj.get('ok') == nj.get('blobs') and nj.get('blobs', 0) >= 5
    checks['new_blob_sha_match'] = pair.get('sha_match') is True
    dis = pair.get('disasm', {})
    checks['new_blob_roundtrip'] = dis.get('roundtrip') is True
    checks['new_blob_no_bad'] = dis.get('bad') == []
    rep['nb_disasm'] = dict(blobs=nj.get('blobs'), ok=nj.get('ok'), new_blob=pair)

    # 4) A/A shim proof: the old 100/100 differ was NOT a fused certification
    with __import__('tempfile').TemporaryDirectory(prefix='c11shim-') as td:
        if OLD_SO.is_file() and SHIM_SO.is_file():
            a1, a2 = text_of(OLD_SO, td), text_of(SHIM_SO, td)
            rep['aa_shim'] = dict(old_text_sha=hashlib.sha256(a1).hexdigest(),
                                  shim_text_sha=hashlib.sha256(a2).hexdigest(),
                                  byte_identical=a1 == a2,
                                  note='100/100 differ with this shim is an A/A '
                                       'harness self-check, not fused-core proof')
            checks['aa_shim_identified'] = a1 == a2
        else:
            rep['aa_shim'] = dict(note='old/shim .so absent')
            checks['aa_shim_identified'] = False

    ok = all(checks.values())
    rep['checks'] = checks
    rep['verdict'] = 'ALL_GREEN' if ok else 'FAIL'
    rep['c11_status'] = ('BUILD_TOOL_AND_DESCRIPTOR_CORE_RECONSTRUCTED; '
                         'WHOLE_COMPILE_2.6MS_DELETION_STILL_OPEN')
    out.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.11 reader reconstruction gate: %s' % rep['verdict'])
    print('  build %s B / sha %s; descriptor %s cases / %s lines / %s mismatches / %sx core' %
          (bj.get('text_bytes'), (bj.get('text_sha256') or '')[:12],
           dj.get('cases'), dj.get('lines_compared'), dj.get('mismatches'),
           dj.get('speed_ratio')))
    print('  nb_disasm %s/%s; new blob sha=%s roundtrip=%s' %
          (nj.get('ok'), nj.get('blobs'), pair.get('sha_match'),
           pair.get('disasm', {}).get('roundtrip')))
    print('  A/A shim byte-identical: %s | %s | %s' %
          (rep['aa_shim'].get('byte_identical'), rep['install_status'],
           rep['whole_compile_deletion']))
    print('  -> %s' % out)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
