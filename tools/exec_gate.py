#!/usr/bin/env python3
"""exec_gate.py -- the Sovren compiler regression gate.

One command that proves a candidate compiler is safe to install:

  1. FIXED POINT   gen-b (candidate builds the compiler) must equal
                   gen-c (gen-b builds it again), byte for byte.
  2. DIFFERENTIAL  every bench program in the exec corpus must behave
                   identically under the installed compiler and gen-b
                   (stdout + exit code).
  3. SWEEP         the full self-hosting source set (every .sov that
                   takes part in building the compiler) must compile
                   with exactly the same success set under both.
  4. PROBES        the adversarial probe files, same comparison.

Usage:
  python3 tools/exec_gate.py <candidate_compiler> [--quick]

--quick skips the sweep (the slow part).  Exit code 0 = gate passed.

The gate never installs anything and never touches the tree; it only
writes to a temp directory.  Sentinel files the compiler probes for
(/tmp/sov_nopar, /tmp/sov_tklex, /tmp/sov_ptime) are removed before
every invocation so results are cache- and state-independent.
"""
import hashlib
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLED = os.path.join(ROOT, "compilers", "linux", "compiler")
DRIVER = os.path.join(ROOT, "backends", "native", "linux", "compiler.sov")
EXEC_DIR = os.environ.get("EXEC_CORPUS", "/home/user/speedwork/exec")
PROBES = [p for p in ("/tmp/torture.sov", "/tmp/cp_adv.sov", "/tmp/cp_chain.sov",
                      "/tmp/inl_adv.sov", "/tmp/inl2.sov", "/tmp/inl3.sov",
                      "/tmp/nest.sov", "/tmp/helper2.sov",
                      "/tmp/ret_shapes.sov", "/tmp/ret2.sov", "/tmp/greet_t.sov",
                      "/tmp/blank_t1.sov", "/tmp/blank_t2.sov",
                      "/tmp/l8leak2.sov", "/tmp/l8ar.sov", "/tmp/l8fence.sov",
                      "/tmp/bmbat.sov", "/tmp/bmbat2.sov",
                      "/tmp/selbat.sov", "/tmp/ftguard.sov",
                      "/tmp/leabat.sov", "/tmp/catself.sov", "/tmp/growt.sov", "/tmp/lgtest.sov", "/tmp/si_t3.sov")
          if os.path.exists(p)]
SENTINELS = ("/tmp/sov_nopar", "/tmp/sov_tklex", "/tmp/sov_ptime")
TIMEOUT = 30


def clean():
    for f in SENTINELS:
        try:
            os.remove(f)
        except FileNotFoundError:
            pass


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def compile_with(compiler, src, out):
    clean()
    if os.path.exists(out):
        os.remove(out)
    try:
        r = subprocess.run([compiler, src, "-o", out], cwd=ROOT,
                           capture_output=True, timeout=TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0 and os.path.exists(out)


def behavior(binary):
    try:
        r = subprocess.run([binary], capture_output=True, timeout=TIMEOUT)
        return (r.stdout, r.returncode)
    except (subprocess.TimeoutExpired, OSError):
        return (b"<no-run>", -999)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    candidate = os.path.abspath(sys.argv[1])
    quick = "--quick" in sys.argv
    tmp = tempfile.mkdtemp(prefix="exec_gate_")
    fails = []

    # ---- 1. fixed point -------------------------------------------------
    gen_b = os.path.join(tmp, "gen_b")
    gen_c = os.path.join(tmp, "gen_c")
    if not compile_with(candidate, DRIVER, gen_b):
        print("FAIL fixed-point: candidate cannot build the compiler")
        return 1
    os.chmod(gen_b, 0o755)
    if not compile_with(gen_b, DRIVER, gen_c):
        print("FAIL fixed-point: gen-b cannot build the compiler")
        return 1
    hb, hc = sha(gen_b), sha(gen_c)
    if hb != hc:
        fails.append(f"fixed-point: gen-b {hb[:16]} != gen-c {hc[:16]}")
    else:
        print(f"PASS fixed-point  gen-b == gen-c == {hb[:16]}")

    new = gen_b  # the compiler under test from here on

    # ---- 2. differential over the exec corpus ---------------------------
    corpus = sorted(f for f in os.listdir(EXEC_DIR) if f.endswith(".sov"))
    mism = 0
    for f in corpus:
        src = os.path.join(EXEC_DIR, f)
        b1, b2 = os.path.join(tmp, "d_old"), os.path.join(tmp, "d_new")
        ok1 = compile_with(INSTALLED, src, b1)
        ok2 = compile_with(new, src, b2)
        if ok1 != ok2:
            mism += 1
            fails.append(f"differential compile-parity: {f}")
            continue
        if ok1 and behavior(b1) != behavior(b2):
            mism += 1
            fails.append(f"differential behavior: {f}")
    print(f"{'PASS' if mism == 0 else 'FAIL'} differential  "
          f"{len(corpus)} programs, {mism} mismatches")

    # ---- 3. sweep over the self-hosting sources --------------------------
    if not quick:
        allfiles = "/tmp/allfiles.txt"
        if os.path.exists(allfiles):
            with open(allfiles) as fh:
                files = [ln.strip() for ln in fh if ln.strip()]
        else:
            files = []
            for base in ("compilers", "library"):
                for dp, _, fns in os.walk(os.path.join(ROOT, base)):
                    files += [os.path.join(dp, f) for f in fns if f.endswith(".sov")]
            files.append(os.path.join(ROOT, "runtime.sov"))
        ok_old, ok_new = set(), set()
        out = os.path.join(tmp, "swp")
        for src in files:
            if compile_with(INSTALLED, src, out):
                ok_old.add(src)
            if compile_with(new, src, out):
                ok_new.add(src)
        if ok_old != ok_new:
            fails.append(f"sweep: {len(ok_old)} old-ok vs {len(ok_new)} new-ok; "
                         f"symmetric difference {sorted(ok_old ^ ok_new)[:5]}")
        else:
            print(f"PASS sweep        {len(ok_new)}/{len(files)} compile, sets identical")

    # ---- 4. adversarial probes -------------------------------------------
    pmism = 0
    for src in PROBES:
        b1, b2 = os.path.join(tmp, "p_old"), os.path.join(tmp, "p_new")
        ok1 = compile_with(INSTALLED, src, b1)
        ok2 = compile_with(new, src, b2)
        if ok1 != ok2 or (ok1 and behavior(b1) != behavior(b2)):
            # inl_adv prints a raw pointer by (pre-existing buggy) design;
            # compare modulo line 3 there.
            if os.path.basename(src) == "inl_adv.sov" and ok1 and ok2:
                o1 = behavior(b1)[0].splitlines()
                o2 = behavior(b2)[0].splitlines()
                if len(o1) == len(o2):
                    o1[2:3] = o2[2:3] = [b"PTR"]
                    if o1 == o2:
                        continue
            pmism += 1
            fails.append(f"probe: {src}")
    print(f"{'PASS' if pmism == 0 else 'FAIL'} probes        "
          f"{len(PROBES)} files, {pmism} mismatches")

    if fails:
        print("\nGATE FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("\nGATE PASSED -- candidate is safe to install.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
