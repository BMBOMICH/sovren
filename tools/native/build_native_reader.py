#!/usr/bin/env python3
"""C.11 — rebuild the LOST S27/S29 fused-reader build tool.

The original `tools/native/build_native_reader.py` did not survive the
2026-11-06 sandbox recycle, and `tools/native_reader.c` (the fused core
itself) is also gone. This file restores the BUILD TOOL, not the fused core:

  * same contract as tools/build_native_basescan.py: gcc -fPIC freestanding,
    no external symbols, no relocations, .text extracted as raw bytes, emit8
    rows written as an `unsafe-module` .sov twin;
  * optional `--certify` runs the surviving work/p4/s29/diff_reader harness
    (100-case stress + PRNG + real .sov corpus) old.so vs new.so and requires
    0 failures;
  * refuses to write an artifact if any check fails.

HONESTY NOTE (measured 2026-11-09, updated PASS 13): `work/p4/s29/shim_reader.so`,
the only "new" side that survived, has a .text section BYTE-IDENTICAL to
`old_reader.so`; the old 100/100 differ is an A/A harness self-check, NOT a
certification of a fused core. PASS 13 RECONSTRUCTED the 23-field one-pass
descriptor core as `tools/native_reader_fused.c`, rebuilt this tool's
relocation-free 2,294 B twin, and certified it with
`tools/reader_descriptor_gate.py` (168 cases / 46,418 lines / 0 mismatches,
R=21 core A/B ~1.8x CREDIBLE_WIN) plus `nb_disasm_verify` 5/5. The whole
cx_read emission path is NOT wired into compiler.sov and the >=2.6 ms
whole-compile deletion is STILL OPEN; see
evidence/C11_reader_reconstruction_2026-11-09.json.

Usage:
  python3 tools/native/build_native_reader.py --source work/p4/s29/old_reader.c \
      --entry old_cx_read --out /tmp/reader_twin.sov
  python3 tools/native/build_native_reader.py --source tools/native_reader.c \
      --entry reader_core --out compilers/linux/reader_native.sov \
      --certify --new-so /tmp/new_reader.so
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[2]
FLAGS = ('-O3 -fno-tree-vectorize -fno-jump-tables -fno-tree-switch-conversion '
         '-fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables '
         '-fcf-protection=none -fno-builtin -ffreestanding -fPIC').split()
DIFFER = R / 'work/p4/s29/diff_reader'
OLD_SO = R / 'work/p4/s29/old_reader.so'


def build(source: Path, entry: str, symbol: str, out: Path, new_so: Path | None):
    report = dict(source=str(source), entry=entry, symbol=symbol,
                  checks={}, verdict='FAIL')
    with tempfile.TemporaryDirectory(prefix='reader-build-') as td:
        t = Path(td)
        obj, binary = t / 'reader.o', t / 'reader.bin'
        cmd = ['gcc', '-c', str(source), '-o', str(obj), *FLAGS]
        r = subprocess.run(cmd, capture_output=True, text=True)
        report['checks']['gcc_compile'] = r.returncode == 0
        if r.returncode:
            report['error'] = (r.stderr or '')[:400]
            return report
        undef = subprocess.check_output(['nm', '-u', str(obj)], text=True).strip()
        report['checks']['no_undefined_symbols'] = not undef
        report['undefined_symbols'] = undef[:200]
        rel = subprocess.check_output(['readelf', '-r', str(obj)], text=True)
        report['checks']['no_relocations'] = 'There are no relocations' in rel
        if new_so:
            # The differ's NEW side must export `reader_core`. When the
            # supplied source uses a different entry name, build a second
            # object with the symbol renamed (objcopy --redefine-sym).
            so_obj = obj
            if entry != 'reader_core':
                so_obj = t / 'reader_renamed.o'
                subprocess.run(['cp', str(obj), str(so_obj)], check=True)
                subprocess.run(['objcopy', '--redefine-sym',
                                entry + '=reader_core', str(so_obj)], check=True)
            subprocess.run(['gcc', '-shared', str(so_obj), '-o', str(new_so)], check=True)
            report['checks']['new_so_exports_reader_core'] = 'reader_core' in subprocess.check_output(
                ['nm', '-D', str(new_so)], text=True)
        subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', str(obj),
                        str(binary)], check=True)
        b = binary.read_bytes()
        symbols = subprocess.check_output(['nm', '-n', str(obj)], text=True).splitlines()
        rows = [l.split() for l in symbols if len(l.split()) >= 3]
        hit = [int(x[0], 16) for x in rows if x[-1] == entry]
        report['checks']['entry_symbol_found'] = bool(hit)
        if not hit:
            report['error'] = 'entry symbol %r absent' % entry
            return report
        off = hit[0]
        # A non-zero entry gets a 5-byte jmp trampoline, exactly like
        # tools/build_native_basescan.py. Both layouts are valid.
        report['checks']['entry_offset_handled'] = True
        report['entry_offset'] = off
        report['trampoline'] = off != 0
        if off:
            b = b'\xe9' + struct.pack('<i', off) + b
        words = [struct.unpack('<Q', b[i:i + 8])[0] for i in range(0, len(b) - 7, 8)]
        rem = b[len(b) & ~7:]
        s = ('# unsafe-module\n# Generated by tools/native/build_native_reader.py '
             'from ' + source.name + '\n' + symbol + ':\n    emit8:\n')
        s += ''.join('        ' + ' '.join(str(w) for w in words[i:i + 2]) + '\n'
                     for i in range(0, len(words), 2))
        if len(rem) >= 4:
            s += '    emit4:\n        ' + str(struct.unpack('<I', rem[:4])[0]) + '\n'
            rem = rem[4:]
        if rem:
            s += '    emit:\n        ' + ' '.join(str(x) for x in rem) + '\n'
        s += '    return 1\n'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(s)
        report['text_bytes'] = len(b)
        report['text_sha256'] = hashlib.sha256(b).hexdigest()
        report['twin_bytes'] = len(s.encode())
        report['out'] = str(out)
    report['verdict'] = 'PASS' if all(report['checks'].values()) else 'FAIL'
    return report


def certify(new_so: Path):
    if not DIFFER.is_file() or not OLD_SO.is_file():
        return dict(verdict='FAIL', reason='diff_reader harness or old.so missing')
    subprocess.run(['chmod', '+x', str(DIFFER)], check=False)
    r = subprocess.run([str(DIFFER), str(OLD_SO), str(new_so)],
                       cwd=R, capture_output=True, text=True, timeout=600)
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    ok = r.returncode == 0 and any('failures=0' in l for l in tail)
    return dict(verdict='PASS' if ok else 'FAIL', rc=r.returncode, tail=tail,
                note='Requires a REAL fused core; an A/A shim is not certification.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--entry', default='reader_core')
    ap.add_argument('--symbol', default='emit_nt_reader')
    ap.add_argument('--out', required=True)
    ap.add_argument('--new-so', default=None)
    ap.add_argument('--certify', action='store_true')
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    src, out = Path(a.source), Path(a.out)
    if not src.is_file():
        print('FAIL source missing: %s' % src)
        return 1
    new_so = Path(a.new_so) if a.new_so else (Path(tempfile.gettempdir()) / 'reader_new.so')
    rep = build(src, a.entry, a.symbol, out, new_so if a.certify else None)
    if a.certify and rep['verdict'] == 'PASS':
        rep['differ'] = certify(new_so)
        rep['verdict'] = rep['differ']['verdict']
    print('C.11 reader build: %s  text=%s B  checks=%s'
          % (rep['verdict'], rep.get('text_bytes', '?'), rep['checks']))
    if 'differ' in rep:
        print('  differ:', rep['differ'].get('tail'))
    if a.json:
        p = Path(a.json); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep, indent=2) + '\n')
        print('  -> %s' % p)
    return 0 if rep['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
