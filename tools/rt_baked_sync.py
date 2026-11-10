#!/usr/bin/env python3
"""Gate: library/rt_baked.sov must decode to exactly runtime.sov's bytes.

Since the baked runtime became the primary source (2026-11-03), a diverged
baked text would silently change every compiled artifact. This check makes
divergence a hard gate failure instead.
"""
import base64
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]

def main():
    src = (R / 'library' / 'rt_baked.sov').read_text()
    chunks = [l.split('"')[1] for l in src.split('\n')
              if l.startswith('    t: join(t, "')]
    if not chunks:
        sys.exit('rt_baked_sync: no payload chunks found')
    decoded = base64.b64decode(''.join(chunks))
    disk = (R / 'runtime.sov').read_bytes()
    if decoded != disk:
        sys.exit('rt_baked_sync: baked text (%d B) != runtime.sov (%d B) — '
                 'run scripts/regen_rt_baked.py'
                 % (len(decoded), len(disk)))
    print('rt_baked_sync: baked payload == runtime.sov (%d bytes)' % len(disk))

if __name__ == '__main__':
    main()
