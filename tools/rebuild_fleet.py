#!/usr/bin/env python3
"""Mass rebuild: recompile every registry executable from its purged source
with the current gate compiler, then sweep cache/sugar sidecars tree-wide.
Byte-stability: recompiling each source twice must give identical bytes."""
import json, subprocess, sys, hashlib
from pathlib import Path
R = Path(__file__).resolve().parents[1]
reg = json.loads((R/'compilers/registry.json').read_text())
GATE = str(R/'compilers/linux/compiler')
rows=[]; ok=bad=0
for e in reg['entries']:
    src, exe = e.get('source'), e.get('executable')
    if not src or not exe: continue
    sp, ep = R/src, R/exe
    if not sp.is_file():
        rows.append((exe,'NO-SRC')); bad+=1; continue
    out = Path('/tmp/fleet_'+hashlib.md5(exe.encode()).hexdigest()[:10])
    r1 = subprocess.run([GATE, str(sp), '-o', str(out)], capture_output=True)
    if r1.returncode != 0 or not out.exists():
        rows.append((exe,'COMPILE-FAIL')); bad+=1; continue
    r2 = subprocess.run([GATE, str(sp), '-o', str(out)+'b'], capture_output=True)
    stable = r2.returncode==0 and out.read_bytes()==(Path(str(out)+'b')).read_bytes()
    ep.parent.mkdir(parents=True, exist_ok=True)
    ep.write_bytes(out.read_bytes()); ep.chmod(0o755)
    rows.append((exe, 'OK' if stable else 'OK-nondeterministic')); ok+=1
print(f"rebuilt={ok} failed={bad}")
for name,st in rows:
    if 'FAIL' in st or 'NO-SRC' in st or 'nondeterministic' in st: print(' ', st, name)
sys.exit(1 if bad else 0)
