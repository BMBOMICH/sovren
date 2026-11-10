#!/usr/bin/env python3
"""Standing gate for compiler-speed milestones.
usage: gate.py probe_binary [full]
  fast:  --flat text battery on tiny+cmp+torture + tiny full-output
  full:  + all outputs, anchors, best-of-7 timing vs installed compiler
exit 0 = PASS."""
import hashlib, subprocess, sys, time, os
R = '/home/user/sovren'
NEW = sys.argv[1]
FULL = len(sys.argv) > 2 and sys.argv[2] == 'full'
OLD = R + '/compilers/linux/compiler'
def md5f(p):
    try: return hashlib.md5(open(p,'rb').read()).hexdigest()[:12]
    except FileNotFoundError: return 'MISSING'
def run(exe, args, out, t=300):
    for suf in ('', '.state', '.ac', '.ac.bin'):
        try: os.unlink(out + suf)
        except FileNotFoundError: pass
    try: os.unlink(out + '.map')
    except FileNotFoundError: pass
    try: os.unlink(out + '.flat')
    except FileNotFoundError: pass
    # stale input sidecars from an older driver generation silently redirect
    # builds to oc-replay with baked-in state - wipe before verifying
    src = args[-1] if args else ''
    if src.endswith('.sov'):
        for suf in ('.plk', '.state', '.ac', '.ac.bin', '.deep', '.deepoc', '.lsug'):
            try: os.unlink(src + suf)
            except FileNotFoundError: pass
    # C.36: --no-ac/--no-learn are retired and now rejected; never pass them.
    r = subprocess.run([exe] + args + ['-o', out], capture_output=True, timeout=t, cwd=R)
    if r.returncode != 0:
        print('RC', r.returncode, exe.split('/')[-1], args[-1] if args else '', r.stderr.decode()[:80], r.stdout.decode()[-80:])
    if r.returncode == 0 and (not os.path.isfile(out) or os.path.getsize(out) == 0):
        return 125
    return r.returncode
battery = ['/tmp/tiny.sov', '/tmp/cmp.sov', '/tmp/torture.sov']

# self-heal the battery sources: /tmp is wiped between sessions and the gate
# must survive it (same law as exec bits). All three are deterministic
# synthetics (the historic /tmp originals are unrecoverable; library/cmp.sov
# is a mainless library and was the wrong thing to copy).
def _gen(n, label):
    parts = ["main:", '    print "%s"' % label, "    t: 0",
             "    dummy: f0(3, 4)", "    print 1"]
    for i in range(n):
        parts.append("f%d a b:" % i)
        parts.append("    c: a * %d + b" % (i + 2))
        parts.append("    if c > 100")
        parts.append("        c: c - 100")
        parts.append("    return c")
    parts.append("    return 0")
    return "\n".join(parts) + "\n"

def _heal_battery():
    if not os.path.isfile('/tmp/cmp.sov'):
        open('/tmp/cmp.sov', 'w').write(_gen(600, "cmp"))
    if not os.path.isfile('/tmp/tiny.sov'):
        open('/tmp/tiny.sov', 'w').write(_gen(3, "tiny"))
    if not os.path.isfile('/tmp/torture.sov'):
        open('/tmp/torture.sov', 'w').write(_gen(1200, "torture"))
_heal_battery()

if FULL:
    battery += [R+'/tests/hello.sov', R+'/tests/fast.sov', R+'/tests/gates/fixtures/q0.sov', R+'/tests/gates/fixtures/q1.sov']
bad = 0
for f in battery:
    a, b, fa, fb = '/tmp/g_o.bin', '/tmp/g_n.bin', '/tmp/g_o.flat', '/tmp/g_n.flat'
    r1 = run(OLD, [f], a); r2 = run(NEW, [f], b)
    m1, m2 = md5f(a), md5f(b)
    # L5 rtobj era: need=1 programs link object bodies, so the new binary is
    # intentionally != the classic landed one. Correctness canary = the flat
    # (parser input, built classic below) + NEW-side double-run determinism;
    # behavior equivalence for the big programs is certified separately
    # (P_fast/P_run suite passes). Binary divergence is informational.
    b2 = '/tmp/g_n2.bin'
    run(NEW, [f], b2)
    m2b = md5f(b2)
    # --flat canary compares the CLASSIC parse input: stash the rtobj so the
    # new driver loads the runtime text (the rtobj path excludes it from `all`
    # by design - bodies come from the object, not the text).
    robbed = R + '/runtime.sov.rtobj'
    stash = '/tmp/g_rtobj.stash'
    robbed_now = False
    if os.path.exists(robbed):
        open(stash, 'wb').write(open(robbed, 'rb').read()); os.unlink(robbed); robbed_now = True
    try:
        r3 = run(OLD, ['--flat', f], fa); r4 = run(NEW, ['--flat', f], fb)
    finally:
        if robbed_now:
            open(robbed, 'wb').write(open(stash, 'rb').read()); os.unlink(stash)
    t1, t2 = md5f(fa), md5f(fb)
    ok = all(rc == 0 for rc in (r1,r2,r3,r4)) and all(h != "MISSING" for h in (m1,m2,m2b,t1,t2)) and (m2 == m2b) and (t1 == t2)
    if not ok:
        bad += 1
        print('FAIL', os.path.basename(f), m1, m2, m2b, t1, t2)
    elif m1 != m2:
        print('DIFF-BIN', os.path.basename(f), 'old', m1, 'new', m2, '(rtobj path)')
if FULL:
    anchors = {'hello': 'eacfcd953ef4', 'q0': '64fb7f91fcce', 'q1': '6e48aa60e0a2', 'fast': '43b650760e67'}  # fast refreshed PS42bj: fast.sov embeds the inlined find_text body (159 B) by design; behavior certified by 182/0/2 self-run + identical 60s run-transcript cut + fleet 37/37
    for nm, want in anchors.items():
        src = {'hello': R+'/tests/hello.sov', 'q0': R+'/tests/gates/fixtures/q0.sov', 'q1': R+'/tests/gates/fixtures/q1.sov', 'fast': R+'/tests/fast.sov'}[nm]
        run(NEW, [src], '/tmp/g_a.bin')
        got = md5f('/tmp/g_a.bin')
        if got != want:
            bad += 1
            print('ANCHOR FAIL', nm, got, want)
ts_old, ts_new = [], []
for _ in range(7):
    t0 = time.time(); run(OLD, ['/tmp/cmp.sov'], '/tmp/g_t.bin'); ts_old.append(time.time()-t0)
    t0 = time.time(); run(NEW, ['/tmp/cmp.sov'], '/tmp/g_t.bin'); ts_new.append(time.time()-t0)
o, n = min(ts_old)*1000, min(ts_new)*1000
print('old %.1f ms  new %.1f ms  delta %+.1f ms (%.1f%%)' % (o, n, n-o, (n-o)/o*100))
print('GATE', 'FAIL' if bad else 'PASS')
sys.exit(1 if bad else 0)
