#!/usr/bin/env python3
"""Permanent private/light gates for the linux compiler (PL-07/08/09/18/27/28).

Usage:  python3 tests/gates/pl_gates.py [compiler] [--quick]
  compiler  default: compilers/linux/compiler
  --quick   skip the 42-file --release battery (PL-27)

Every generated binary runs under `timeout`. Exits 0 iff all gates pass.
Run from the sovren/ tree root.
"""
import hashlib, os, struct, subprocess, sys, tempfile

ROOT = os.getcwd()
COMP = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
    else os.path.join(ROOT, 'compilers/linux/compiler')
QUICK = '--quick' in sys.argv
FAILS = []

def run(cmd, tmo=120, cwd=None, env=None):
    e = dict(os.environ)
    if env: e.update(env)
    return subprocess.run(cmd, capture_output=True, timeout=tmo, cwd=cwd or ROOT, env=e)

def build(src, out, flags=(), cwd=None, env=None):
    try: os.remove('/tmp/sov_nopar')
    except FileNotFoundError: pass
    r = run(['timeout', '120', COMP, src, '-o', out, *flags], cwd=cwd, env=env)
    return r.returncode == 0 and os.path.exists(out)

def execout(path, tmo=10):
    r = subprocess.run(['timeout', str(tmo), path], capture_output=True)
    return r.returncode, r.stdout

def gate(name, ok, detail=''):
    print(f'{"PASS" if ok else "FAIL"}  {name}  {detail}')
    if not ok: FAILS.append(name)

def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()

D = tempfile.mkdtemp(prefix='plgates_')
def W(name, text):
    p = os.path.join(D, name); open(p, 'w').write(text); return p

EMPTY  = W('empty.sov', 'main:\n')
HELLO  = W('hello.sov', 'main:\n    print "hello"\n')
MINSTR = W('minstr.sov', 'use string\nmain:\n    s: str_cat("hello ", "world")\n    print str_len(s)\n    return 0\n')
UNUSED = W('unused.sov', 'dead_task a b:\n    q: a * b + 3\n    return q\nmain:\n')
GINT   = W('gint.sov', 'g_counter: 5\nmain:\n    print g_counter\n')
GSTR   = W('gstr.sov', 'g_msg: "hi there"\nmain:\n    print g_msg\n')

def B(src, name, flags=()):
    out = os.path.join(D, name)
    assert build(src, out, flags), f'build failed: {name}'
    return out, os.path.getsize(out)

# ---- PL-07 size gate -------------------------------------------------
e_out, e_sz   = B(EMPTY, 'empty.bin')
h_out, h_sz   = B(HELLO, 'hello.bin')
ms_out, ms_sz = B(MINSTR, 'minstr_rel.bin', ('--release',))
gate('PL-07 empty<=496', e_sz <= 496, f'{e_sz}B')
gate('PL-07 hello<=528', h_sz <= 528, f'{h_sz}B')
gate('PL-07 minstr --release<=1200', ms_sz <= 1200, f'{ms_sz}B')
rc, so = execout(e_out);  gate('PL-07 empty runs rc0', rc == 0, f'rc={rc}')
rc, so = execout(h_out);  gate('PL-07 hello prints', so == b'hello\n', repr(so))
rc, so = execout(ms_out); gate('PL-07 minstr --release correct', so == b'11\n', repr(so))

# ---- PL-28 growth gate ------------------------------------------------
_, u_sz  = B(UNUSED, 'unused_rel.bin', ('--release',))
_, gi_sz = B(GINT, 'gint_rel.bin', ('--release',))
_, gs_sz = B(GSTR, 'gstr_rel.bin', ('--release',))
gate('PL-28 unused task costs 0 (--release)', u_sz == e_sz, f'{u_sz}B vs empty {e_sz}B')
gate('PL-28 global int bounded', gi_sz <= 700, f'{gi_sz}B')
gate('PL-28 global string bounded', gs_sz <= 1000, f'{gs_sz}B')

# ---- PL-08 privacy scan ----------------------------------------------
FORBIDDEN = [b'/home/', b'/tmp/', b'/proc/self', b'.debug', b'build-id',
             b'BuildID', b'GCC:', b'clang version', os.environ.get('USER', 'user').encode() + b'@']
def phdrs(p):
    d = open(p, 'rb').read()
    n = struct.unpack_from('<H', d, 56)[0]
    return d, [(struct.unpack_from('<II', d, 64 + i * 56)) for i in range(n)]
for tag, p in [('empty', e_out), ('hello', h_out), ('minstr_rel', ms_out), ('compiler', COMP)]:
    d, ph = phdrs(p)
    types = [t for t, f in ph]
    shoff = struct.unpack_from('<Q', d, 40)[0]
    # The compiler itself legitimately names its /tmp flag files and
    # /proc/self/exe (audited PL-23 surface); user outputs must not
    # contain any of these.
    allow = [b'/tmp/sov_', b'/tmp/pdx.txt', b'/proc/self/exe', b'/proc/cpuinfo'] if tag == 'compiler' else []
    bad = [x for x in FORBIDDEN if x in d and not any(a in x or x in a for a in allow)]
    if tag == 'compiler':
        import re
        found = set(re.findall(rb'/(?:tmp|proc)/[A-Za-z0-9_./-]*', d))
        extra = [f for f in found if not any(f.startswith(a) for a in allow)]
        bad += extra
    stack = [f for t, f in ph if t == 0x6474e551]
    ok = (shoff == 0 and not bad and 3 not in types          # no sections, no leaks, no PT_INTERP
          and stack and not (stack[0] & 1)                   # GNU_STACK present, non-exec
          and 0x6474e553 in types)                           # GNU_PROPERTY present
    gate(f'PL-09 privacy[{tag}]', ok,
         f'shoff={shoff} interp={3 in types} forbidden={[x.decode("latin1") for x in bad]} stack={stack}')

# ---- PL-09 reproducibility -------------------------------------------
D2 = tempfile.mkdtemp(prefix='plgates2_')
o1, o2 = os.path.join(D, 'r1.bin'), os.path.join(D2, 'r2.bin')
import shutil
MINSTR2 = os.path.join(D2, 'minstr.sov'); shutil.copy(MINSTR, MINSTR2)
build(MINSTR, o1, ('--release',), env={'TZ': 'UTC', 'HOSTNAME': 'alpha'})
build(MINSTR2, o2, ('--release',), env={'TZ': 'Pacific/Kiritimati', 'HOSTNAME': 'beta'})
gate('PL-08 repro (env/dir independent)', sha(o1) == sha(o2))
src = os.path.join(ROOT, 'compilers/linux/compiler.sov')
s1, s2 = os.path.join(D, 'self1'), os.path.join(D, 'self2')
build(src, s1)
r = run(['timeout', '300', s1, src, '-o', s2])
gate('PL-08 self-compile fixed point', os.path.exists(s2) and sha(s1) == sha(s2))

# ---- PL-10 toolchain size ---------------------------------------------
def treesize(path):
    t = 0
    for dp, dn, fn in os.walk(path):
        for f in fn: t += os.path.getsize(os.path.join(dp, f))
    return t
tc = os.path.getsize(COMP) + os.path.getsize(os.path.join(ROOT, 'runtime.sov')) + treesize(os.path.join(ROOT, 'library'))
gate('PL-10 toolchain <= 3MB', tc <= 3145728, f'{tc}B')

# ---- PL-18 spew gate ---------------------------------------------------
log = os.path.join(D, 'spew.log')
cmd = (f"cd {ROOT} && rm -f /tmp/sov_nopar && "
       f"(timeout 90 {COMP} compilers/windows/compiler.sov -o {D}/win.bin 2>&1 | head -c 3000000 > {log})")
subprocess.run(['bash', '-c', cmd], timeout=150)
sz = os.path.getsize(log) if os.path.exists(log) else -1
gate('PL-18 foreign-source stdout <= 1MB', 0 <= sz <= 1048576, f'{sz}B')

# ---- PL-27 --release battery ------------------------------------------
if not QUICK:
    bat = sorted(f for f in os.listdir('/home/user/sovren/tests/exec') if f.endswith('.sov'))
    diffs = []
    for f in bat:
        sp = os.path.join('/home/user/sovren/tests/exec', f)
        a, b = os.path.join(D, 'bat_a'), os.path.join(D, 'bat_b')
        ba, bb = build(sp, a), build(sp, b, ('--release',))
        if ba != bb:
            diffs.append(f + ':build-parity'); continue
        if not ba:
            continue  # negative test: fails identically in both modes
        ra, rb = execout(a), execout(b)
        if ra != rb: diffs.append(f + ':run')
        if os.path.getsize(b) > os.path.getsize(a): diffs.append(f + ':bigger')
    gate(f'PL-01 default-vs-release battery ({len(bat)} files)', not diffs, ','.join(diffs[:5]))

print('\n' + ('ALL GATES PASS' if not FAILS else f'FAILED: {FAILS}'))
sys.exit(1 if FAILS else 0)
