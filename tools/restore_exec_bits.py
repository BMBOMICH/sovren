#!/usr/bin/env python3
"""Repair executable bits lost by the workspace snapshot (metadata only).

The Arena workspace snapshot preserves file BYTES but can drop mode bits
between sessions.  Sovren's gates invoke ELF binaries directly (installed
compiler, SA assembler, sc/sc, oracle-frozen, the 155 fleet drivers, emitted
test programs), so a 0644 mode makes a perfectly correct binary fail with
"Permission denied" -- which looks exactly like a semantic regression.

This tool restores 0755 on ELF files that lack any execute bit.  It NEVER
changes a file's bytes; sha256/md5 of every touched file is unchanged.  It is
metadata hygiene, not a cache, not a warm path, and not a compiler rewrite.

Usage: python3 tools/restore_exec_bits.py [--check]
  --check   report only, do not chmod (exit 1 if any ELF lacks +x)
"""
import argparse
import os
import sys
from pathlib import Path

ROOTS = [Path('/home/user/dl/sovren'), Path('/home/user/dl/sovren-assembler'),
         Path('/home/user/evidence'), Path('/home/user/reference')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    missing, fixed = [], []
    for root in ROOTS:
        if not root.is_dir():
            continue
        for p in root.rglob('*'):
            try:
                if not p.is_file() or p.stat().st_size < 4:
                    continue
                with open(p, 'rb') as f:
                    magic = f.read(4)
                if magic != b'\x7fELF':
                    continue
                if os.access(p, os.X_OK):
                    continue
                missing.append(str(p))
                if not a.check:
                    p.chmod(0o755)
                    fixed.append(str(p))
            except (OSError, PermissionError):
                continue
    print('ELF files lacking +x: %d; chmod restored: %d' % (len(missing), len(fixed)))
    for p in missing[:12]:
        print('  ' + p)
    if len(missing) > 12:
        print('  ... and %d more' % (len(missing) - 12))
    print('VERDICT: %s' % ('NEEDS_REPAIR' if (a.check and missing) else 'OK'))
    return 1 if (a.check and missing) else 0


if __name__ == '__main__':
    sys.exit(main())
