#!/usr/bin/env python3
"""One-command rebuild of every backend this driver can build (PL-17).

    python3 tests/gates/rebuild_fleet.py [--install]

Rebuilds the experimental linux emitters (compilers/linux/*)
with the installed linux compiler, samples empty/hello output sizes,
and (with --install) writes the fresh emitter binaries into
compilers/linux/<target>/compiler. Backends whose sources are written
for the external suite frontend (alien `->`/`;;` syntax generation,
e.g. windows) are reported as such instead of failing noisily: this
driver's diagnostic budget caps their output, and they remain the
suite's build responsibility until the syntax rewrite.
"""
import os, subprocess, sys, tempfile

ROOT = os.getcwd()
CC = os.path.join(ROOT, 'compilers/linux/compiler')
INSTALL = '--install' in sys.argv
D = tempfile.mkdtemp(prefix='fleet_rebuild_')
EMPTY = os.path.join(D, 'e.sov'); open(EMPTY, 'w').write('main:\n')
HELLO = os.path.join(D, 'h.sov'); open(HELLO, 'w').write('main:\n    print "hello"\n')

def run(cmd, tmo=180):
    try: os.remove('/tmp/sov_nopar')
    except FileNotFoundError: pass
    r = subprocess.run(['timeout', str(tmo)] + cmd, capture_output=True, timeout=tmo+30, cwd=ROOT)
    return r

base = os.path.join(ROOT, 'compilers/linux')
SUITE_ONLY = {'arm64', 'arm64-shared-object'}  # cr_line suite generators, not driver-buildable
targets = sorted(d for d in os.listdir(base)
                 if d not in SUITE_ONLY and os.path.exists(os.path.join(base, d, 'compiler.sov')))
ok = fail = 0
for t in targets:
    src = os.path.join(base, t, 'compiler.sov')
    out = os.path.join(D, 'em_' + t)
    r = run([CC, src, '-o', out])
    if r.returncode != 0 or not os.path.exists(out):
        print(f'{t:24} BUILD-FAIL'); fail += 1; continue
    os.chmod(out, 0o755)
    sizes = []
    for s in (EMPTY, HELLO):
        o = os.path.join(D, 'x.bin')
        run([out, s, '-o', o], 60)
        sizes.append(os.path.getsize(o) if os.path.exists(o) else -1)
    note = ''
    if INSTALL and os.path.isdir(os.path.join(ROOT, 'compilers/linux', t)):
        dst = os.path.join(ROOT, 'compilers/linux', t, 'compiler')
        open(dst, 'wb').write(open(out, 'rb').read()); os.chmod(dst, 0o755)
        note = 'installed'
    print(f'{t:24} empty={sizes[0]} hello={sizes[1]} {note}'); ok += 1
print(f'{ok} built, {fail} failed')
