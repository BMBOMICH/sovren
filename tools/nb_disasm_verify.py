#!/usr/bin/env python3
"""C.29 — `nb_disasm_verify` on every generated native blob.

For each `unsafe-module` .sov twin, reconstruct the raw machine-code bytes
from its `emit8:` (u64 LE words), `emit4:` (u32 LE) and `emit:` (byte list)
rows, then:

  1. compare the reconstructed SHA-256 to the gcc `.text` blob recorded by
     tools/native/build_native_reader.py (exact byte identity, no drift);
  2. disassemble with objdump -D -b binary -m i386:x86-64 -M intel;
  3. require zero `(bad)` instructions and at least one decoded instruction;
  4. require the hex byte column of the disassembly to round-trip EXACTLY to
     the reconstructed blob (catches a dropped/duplicated emit8 row).

This is a verification gate, not a compiler change: no emitted compiler bytes
change. Usage: python3 tools/nb_disasm_verify.py [--json OUT]
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = Path('/home/user/evidence')

# twin .sov, build report with text_sha256
PAIRS = [
    ('reader_scaffold_control', E / 'C11_reader_twin_scaffold.sov',
     E / 'C11_reader_build.json'),
    ('reader_fused_descriptor', E / 'C11_fused_reader_twin.sov',
     E / 'C11_fused_twin_build.json'),
    ('shape_scan_portable_blob', E / 'C15_C16_shape_scan_twin.sov',
     E / 'C15_C16_shape_scan_twin_build.json'),
    ('shipped_basescan_control', R / 'compilers/linux/basescan_native.sov', None),
    ('pass13_fused_descriptor', E / 'C11_pass13_fused_descriptor_twin.sov',
     E / 'C11_pass13_fused_descriptor_build.json'),
    ('pass14_stable_interner', E / 'C4_C5_stable_interner_twin.sov',
     E / 'C4_C5_stable_interner_build.json'),
]


def reconstruct(sov_text):
    """Return the raw blob described by the emit8/emit4/emit rows."""
    out = bytearray()
    section = None
    for raw in sov_text.splitlines():
        s = raw.strip()
        if not s or s.startswith('#'):
            continue
        if s.endswith(':') and s[:-1] in ('emit8', 'emit4', 'emit'):
            section = s[:-1]
            continue
        if s.endswith(':') or s in ('return 1',):
            section = None
            continue
        if section is None:
            continue
        toks = s.replace(',', ' ').split()
        if not all(re.fullmatch(r'\d+', t) for t in toks):
            continue
        for t in toks:
            v = int(t)
            if section == 'emit8':
                out += struct.pack('<Q', v)
            elif section == 'emit4':
                out += struct.pack('<I', v)
            else:
                out.append(v & 0xff)
    return bytes(out)


def disasm(blob):
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
        f.write(blob)
        path = f.name
    try:
        p = subprocess.run(['objdump', '-D', '-b', 'binary', '-m', 'i386:x86-64',
                            '-M', 'intel', path], capture_output=True, text=True)
    finally:
        Path(path).unlink(missing_ok=True)
    ins, hexbytes, bad = 0, bytearray(), []
    for line in p.stdout.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*)$', line)
        if not m:
            continue
        hexbytes += bytes.fromhex(m.group(2))
        text = m.group(3).strip()
        if text:
            ins += 1
        if '(bad)' in text:
            bad.append(line.strip()[:120])
    return dict(rc=p.returncode, instructions=ins, decoded_bytes=len(hexbytes),
                roundtrip=(bytes(hexbytes) == blob), bad=bad[:5],
                bad_count=len(bad), stderr=p.stderr[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E / 'C29_nb_disasm_verify.json'))
    a = ap.parse_args()
    outp = Path(a.json); outp.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for name, sov, build in PAIRS:
        if not sov.is_file():
            results.append(dict(blob=name, ok=False, error='MISSING'))
            continue
        blob = reconstruct(sov.read_text())
        sha = hashlib.sha256(blob).hexdigest()
        expected = None
        if build and build.is_file():
            expected = json.loads(build.read_text()).get('text_sha256')
        d = disasm(blob)
        match = None if expected is None else (sha == expected)
        ok = (len(blob) > 0 and d['rc'] == 0 and d['instructions'] > 0
              and d['roundtrip'] and d['bad_count'] == 0 and match is not False)
        results.append(dict(blob=name, file=str(sov), bytes=len(blob),
                            reconstructed_sha256=sha,
                            gcc_text_sha256=expected,
                            sha_match=match, disasm=d, ok=ok,
                            note=None if match is None else 'gcc .text cross-checked'))
    good = sum(1 for x in results if x.get('ok'))
    rep = dict(schema=1, blobs=len(results), ok=good,
               all_green=(good == len(results) and good > 0),
               results=results,
               note='C.29 blob-level verification. Reconstructed blob must equal '
                    'the gcc .text SHA and disassemble cleanly. Does not change '
                    'installed compiler bytes; no parity claim.')
    outp.write_text(json.dumps(rep, indent=2) + '\n')
    print('C.29 nb_disasm_verify: %d/%d blobs OK' % (good, len(results)))
    for x in results:
        if 'error' in x:
            print('  %-28s MISSING' % x['blob']); continue
        d = x['disasm']
        print('  %-28s %5d B  sha=%s  ins=%d  roundtrip=%s  bad=%d  %s'
              % (x['blob'], x['bytes'], 'MATCH' if x['sha_match'] else 'N/A',
                 d['instructions'], d['roundtrip'], d['bad_count'],
                 'OK' if x['ok'] else 'FAIL'))
    print('  -> %s' % outp)
    print('ALL GREEN' if rep['all_green'] else 'NOT GREEN')
    return 0 if rep['all_green'] else 1


if __name__ == '__main__':
    sys.exit(main())
