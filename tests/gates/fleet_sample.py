#!/usr/bin/env python3
"""Fleet sampler (PL-16/17/21 + PL-19/20/22 evidence): for every runnable
x86-64 host cross-compiler under compilers/**, build empty+hello, record
sizes, magic, ELF padding, PE TimeDateStamp, Mach-O LC_UUID, and
double-build reproducibility. Samples, never modifies the tree."""
import os, shutil, struct, subprocess, sys, tempfile

ROOT = os.getcwd()
D = tempfile.mkdtemp(prefix='fleet_')
EMPTY = os.path.join(D, 'empty.sov'); open(EMPTY, 'w').write('main:\n')
HELLO = os.path.join(D, 'hello.sov'); open(HELLO, 'w').write('main:\n    print "hello"\n')

def is_x64_elf(p):
    try:
        d = open(p, 'rb').read(20)
        return d[:4] == b'\x7fELF' and d[4] == 2 and d[18] == 62
    except Exception:
        return False

def trybuild(comp, src, out):
    try: os.remove('/tmp/sov_nopar')
    except FileNotFoundError: pass
    try:
        r = subprocess.run(['timeout', '30', comp, src, '-o', out],
                           capture_output=True, timeout=40, cwd=ROOT)
        return os.path.exists(out) and os.path.getsize(out) > 0
    except Exception:
        return False

def analyze(out):
    d = open(out, 'rb').read()
    info = {'size': len(d)}
    if d[:4] == b'\x7fELF':
        cls, mach = d[4], struct.unpack_from('<H', d, 18)[0]
        info['fmt'] = f'ELF{32 if cls==1 else 64}/m{mach}'
        if cls == 2:
            info['shoff'] = struct.unpack_from('<Q', d, 40)[0]
            n = struct.unpack_from('<H', d, 56)[0]
            types = [struct.unpack_from('<I', d, 64+i*56)[0] for i in range(n)]
            info['interp'] = 3 in types
            info['gnustack'] = 0x6474e551 in types
            # entry code start: min nonzero file content past headers
            info['phnum'] = n
        else:
            info['shoff'] = struct.unpack_from('<I', d, 32)[0]
            n = struct.unpack_from('<H', d, 44)[0]
            phoff = struct.unpack_from('<I', d, 28)[0]
            phent = struct.unpack_from('<H', d, 42)[0] or 32
            info['phnum'] = n
            loads = []
            for i in range(n):
                t, off, va, pa, fs, ms, fl, al = struct.unpack_from('<IIIIIIII', d, phoff+i*phent)
                if t == 1: loads.append((off, va, fs))
            info['loads'] = loads
    elif d[:2] == b'MZ':
        info['fmt'] = 'PE'
        pe = struct.unpack_from('<I', d, 0x3c)[0]
        if d[pe:pe+4] == b'PE\0\0':
            info['timestamp'] = struct.unpack_from('<I', d, pe+8)[0]
            info['has_rich'] = b'Rich' in d[:pe]
            nsec = struct.unpack_from('<H', d, pe+6)[0]
            optsz = struct.unpack_from('<H', d, pe+20)[0]
            magic = struct.unpack_from('<H', d, pe+24)[0]
            dd_base = pe + 24 + (96 if magic == 0x10b else 112)
            dbg_rva, dbg_sz = struct.unpack_from('<II', d, dd_base + 6*8)
            info['debug_dir'] = (dbg_rva, dbg_sz)
            info['sections'] = nsec
    elif d[:4] in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe'):
        info['fmt'] = 'Mach-O'
        ncmds = struct.unpack_from('<I', d, 16)[0]
        off, uuid = 32, None
        for _ in range(ncmds):
            cmd, sz = struct.unpack_from('<II', d, off)
            if cmd == 0x1b: uuid = d[off+8:off+24].hex()
            off += sz
        info['uuid'] = uuid
        info['ncmds'] = ncmds
    else:
        info['fmt'] = 'other/' + d[:4].hex()
    return info

rows = []
comps = []
for dp, dn, fn in os.walk(os.path.join(ROOT, 'compilers')):
    if 'compiler' in fn:
        p = os.path.join(dp, 'compiler')
        if is_x64_elf(p): comps.append(p)
comps.sort()
print(f'{len(comps)} runnable host cross-compilers found')
for p in comps:
    rel = os.path.relpath(p, ROOT)
    c = os.path.join(D, 'cc')
    shutil.copy(p, c); os.chmod(c, 0o755)
    e_out, h_out, h2 = (os.path.join(D, x) for x in ('e.bin', 'h.bin', 'h2.bin'))
    ok_e, ok_h = trybuild(c, EMPTY, e_out), trybuild(c, HELLO, h_out)
    if not (ok_e or ok_h):
        rows.append((rel, 'BUILD_FAIL', '')); continue
    parts = []
    try:
        an_e = analyze(e_out) if ok_e else None
    except Exception as ex:
        an_e = {'error': str(ex)[:60], 'size': os.path.getsize(e_out) if ok_e else 0}
    if ok_e: parts.append(f"empty={an_e}")
    if ok_h:
        try: a = analyze(h_out)
        except Exception as ex: a = {'error': str(ex)[:60]}
        repro = trybuild(c, HELLO, h2) and open(h_out, 'rb').read() == open(h2, 'rb').read()
        parts.append(f"hello={a} repro={repro}")
    rows.append((rel, 'OK', ' '.join(parts)))
for r in rows: print('|', ' | '.join(r))
ok = sum(1 for r in rows if r[1] == 'OK')
print(f'sampled OK: {ok}/{len(rows)}')
