#!/usr/bin/env python3
"""Build the C.10/C.12 sg_extra_ls native twin into compilers/linux/sgextra_native.sov.

Same contract as tools/build_native_front.py: gcc -fPIC freestanding, no
external symbols, no relocations, .text extracted as raw bytes, emit8 rows.
"""
import hashlib, struct, subprocess, tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
FLAGS = ('-O3 -fno-tree-vectorize -fno-jump-tables -fno-tree-switch-conversion '
         '-fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables '
         '-fcf-protection=none -fno-builtin -ffreestanding -fPIC').split()
SRC, ENTRY, SYMBOL = 'native_sgextra.c', 'sg_extra_ls_native', 'emit_nt_sg_extra_ls'
OUT = R / 'compilers/linux/sgextra_native.sov'


def main():
    with tempfile.TemporaryDirectory() as td:
        obj, binary = Path(td) / 'sgx.o', Path(td) / 'sgx.bin'
        subprocess.run(['gcc', '-c', str(R / 'tools' / SRC), '-o', str(obj), *FLAGS], check=True)
        undef = subprocess.check_output(['nm', '-u', str(obj)], text=True).strip()
        assert not undef, 'external references forbidden: ' + undef
        rel = subprocess.check_output(['readelf', '-r', str(obj)], text=True)
        assert 'There are no relocations' in rel, 'unresolved code/data relocation'
        subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', str(obj), str(binary)], check=True)
        b = binary.read_bytes()
        symbols = subprocess.check_output(['nm', '-n', str(obj)], text=True).splitlines()
        off = int(next(l.split()[0] for l in symbols if l.split()[-1] == ENTRY), 16)
        assert 0 <= off < len(b)
        if off:
            b = b'\xe9' + struct.pack('<i', off) + b
    words = [struct.unpack('<Q', b[i:i+8])[0] for i in range(0, len(b) - 7, 8)]
    rem = b[len(b) & ~7:]
    s = ('# unsafe-module\n# Generated from tools/' + SRC + '; C.10/C.12 sg_extra_ls twin.\n'
         + SYMBOL + ':\n    emit8:\n')
    s += ''.join('        ' + ' '.join(str(w) for w in words[i:i+2]) + '\n'
                 for i in range(0, len(words), 2))
    if len(rem) >= 4:
        s += '    emit4:\n        ' + str(struct.unpack('<I', rem[:4])[0]) + '\n'
        rem = rem[4:]
    if rem:
        s += '    emit:\n        ' + ' '.join(str(x) for x in rem) + '\n'
    s += '    return 1\n'
    OUT.write_text(s)
    print('PASS sg_extra_ls twin', len(b), 'bytes; SHA256',
          hashlib.sha256(b).hexdigest(), '->', OUT.name)


if __name__ == '__main__':
    main()
