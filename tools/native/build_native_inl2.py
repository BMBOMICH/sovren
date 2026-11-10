#!/usr/bin/env python3
"""Rebuild the Linux native inl2 blob emitter (compilers/linux/inl2_native.sov).
Compiles tools/native_inl2.c with the certified freestanding flags, asserts no
external symbols / no relocations, extracts .text with the _sov_inl2_scan
entry, and emits the emit8-packed group (one emit8 per 8 bytes, emit4/emit
tail for the exact byte count). Not a runtime tool."""
import argparse, hashlib, subprocess, tempfile, struct
from pathlib import Path
R = Path(__file__).resolve().parents[2]
FLAGS = '-O3 -fno-tree-vectorize -fno-jump-tables -fno-tree-switch-conversion -fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables -fcf-protection=none -fno-builtin -ffreestanding -fPIC'.split()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    source = 'native_inl2.c'; symbol = 'emit_nt_inl2_scan'; entry = '_sov_inl2_scan'
    with tempfile.TemporaryDirectory() as td:
        obj = Path(td) / 'inl2.o'; binary = Path(td) / 'inl2.bin'
        subprocess.run(['gcc', '-c', str(R / 'tools' / source), '-o', str(obj), *FLAGS], check=True)
        assert not subprocess.check_output(['nm', '-u', str(obj)]).strip(), 'external references are forbidden'
        rel = subprocess.check_output(['readelf', '-r', str(obj)], text=True)
        assert 'There are no relocations' in rel, 'unresolved code/data relocation'
        subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', str(obj), str(binary)], check=True)
        b = binary.read_bytes()
        symbols = subprocess.check_output(['nm', '-n', str(obj)], text=True).splitlines()
        offset = int(next(line.split()[0] for line in symbols if line.split()[-1] == entry), 16)
        assert 0 <= offset < len(b), 'entry point outside code section'
        if offset:
            b = b'\xe9' + struct.pack('<i', offset) + b
    words = [struct.unpack('<Q', b[i:i+8])[0] for i in range(0, len(b) - 7, 8)]
    rem = b[len(b) & ~7:]
    s = '# unsafe-module\n# Generated from tools/' + source + '; allocation-free frontend.\n' + symbol + ':\n    emit8:\n'
    s += ''.join('        ' + ' '.join(str(w) for w in words[i:i+2]) + '\n' for i in range(0, len(words), 2))
    if len(rem) >= 4:
        s += '    emit4:\n        ' + str(struct.unpack('<I', rem[:4])[0]) + '\n'
        rem = rem[4:]
    if rem:
        s += '    emit:\n        ' + ' '.join(str(x) for x in rem) + '\n'
    s += '    return 1\n'
    out = R / 'compilers/linux/inl2_native.sov'
    if a.check:
        assert out.read_text() == s, 'inl2 emitter is stale'
    else:
        out.write_text(s)
    print('PASS inl2 emitter', len(b), 'bytes, no relocations/external symbols; SHA256', hashlib.sha256(b).hexdigest())

if __name__ == '__main__':
    main()
