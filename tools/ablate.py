#!/usr/bin/env python3
"""ablate.py - time attribution by ablation.

Call counts are not costs: `cut` had the highest call count of any interpreted
function at the fixed point and was worth 0.9%. This measures time instead. For
each named task it builds a compiler whose version of that task is stubbed to
`return 0`, self-hosts it to the fixed point, and reports how much slower the
real one is. The delta is that task's contribution.

Only tasks in the free (non-line-addressed) files can be ablated:
library/cx86.sov, library/ccore.sov, library/carm.sov, compilers/linux/compiler.sov

  python3 tools/ablate.py body stmt expr_body
  python3 tools/ablate.py --runs 5 --src tests/all.sov body

Every subprocess is bounded: a stubbed compiler that loops forever is reported
as TIMEOUT, not allowed to hang the run.

Caveats, stated because they matter:
  * Stubbing also removes work that would happen downstream, so a delta is an
    upper bound on that task's own cost.
  * A task whose stub breaks or hangs the build is reported, never counted as 0.
"""
import os, re, shutil, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREE = ["compilers/linux/compiler.sov", "compilers/shared/ccore.sov",
        *["compilers/shared/cx86_p%d.sov" % i for i in range(1, 8)],
        "compilers/shared/carm.sov"]
SRC_REL = "compilers/linux/compiler.sov"
BUILD_TIMEOUT = 90
RUN_TIMEOUT = 25


def find_task(name):
    for rel in FREE:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        lines = open(p, errors="replace").read().split("\n")
        for i, l in enumerate(lines):
            if re.match(rf"^{re.escape(name)}( [A-Za-z_0-9]+)*:\s*$", l):
                return rel, i
    return None


def stub_into(text, idx):
    lines = text.split("\n")
    j = idx + 1
    while j < len(lines) and (lines[j].startswith((" ", "\t")) or not lines[j].strip()):
        j += 1
    lines[idx + 1:j] = ["    return 0"]
    return "\n".join(lines)


def build(tree, boot, out):
    src = os.path.join(tree, SRC_REL)
    try:
        r = subprocess.run([boot, src, "-o", out], cwd=tree,
                           capture_output=True, timeout=BUILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, "build TIMEOUT"
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
        err = (r.stdout + r.stderr).decode("utf-8", "replace").splitlines()
        for i, l in enumerate(err):
            if l.startswith("Error:"):
                return False, " ".join(err[i:i + 2])[:70]
        return False, "build failed"
    os.chmod(out, 0o755)
    return True, ""


def selfhost(tree, boot, out):
    """gen1 with the launcher, then gen2 with gen1 -> the fixed point"""
    g1 = out + ".g1"
    ok, why = build(tree, boot, g1)
    if not ok:
        return False, "gen1: " + why
    ok, why = build(tree, g1, out)
    if not ok:
        return False, "gen2: " + why
    return True, ""


def timeit(binary, src, runs):
    ts = []
    for _ in range(runs):
        t0 = time.perf_counter()
        try:
            subprocess.run([binary, src, "-o", "/tmp/_abl_out"], cwd=ROOT,
                           capture_output=True, timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            return None, None
        ts.append((time.perf_counter() - t0) * 1000.0)
    ts.sort()
    return ts[0], ts[len(ts) // 2]


def main():
    args = sys.argv[1:]
    runs, src = 5, os.path.join(ROOT, "tests/all.sov")
    names, i = [], 0
    while i < len(args):
        if args[i] == "--runs":
            runs = int(args[i + 1]); i += 2
        elif args[i] == "--src":
            src = args[i + 1]; i += 2
        else:
            names.append(args[i]); i += 1
    if not names:
        print(__doc__); return 2

    boot = os.path.join(ROOT, "sovren")
    print(f"source {os.path.relpath(src, ROOT)}   runs={runs}", flush=True)

    with tempfile.TemporaryDirectory() as td:
        tree = os.path.join(td, "t")
        shutil.copytree(ROOT, tree, symlinks=True,
                        ignore=shutil.ignore_patterns(".git", "work"))
        base_bin = "/tmp/_abl_base"
        ok, why = selfhost(tree, boot, base_bin)
        if not ok:
            print(f"baseline failed: {why}"); return 1
        bb, bm = timeit(base_bin, src, runs)
        if bb is None:
            print("baseline TIMED OUT"); return 1
        print(f"\n  {'BASELINE':<20} best {bb:8.2f} ms  median {bm:8.2f} ms\n", flush=True)

        rows = []
        for nm in names:
            loc = find_task(nm)
            if not loc:
                print(f"  {nm:<20} NOT FOUND in free files", flush=True); continue
            rel, idx = loc
            p = os.path.join(tree, rel)
            orig = open(p, errors="replace").read()
            open(p, "w").write(stub_into(orig, idx))
            try:
                out = "/tmp/_abl_" + re.sub(r"\W", "_", nm)
                ok, why = selfhost(tree, boot, out)
                if not ok:
                    print(f"  {nm:<20} UNUSABLE ({why})", flush=True); continue
                ab, am = timeit(out, src, runs)
                if ab is None:
                    print(f"  {nm:<20} TIMEOUT at runtime", flush=True); continue
                r = bb / ab if ab else 0.0
                rows.append((r, nm, ab, am, rel))
                print(f"  {nm:<20} best {ab:8.2f} ms  median {am:8.2f} ms"
                      f"   real cost {r:6.3f}x   [{rel}]", flush=True)
            finally:
                open(p, "w").write(orig)

        if rows:
            print("\n  ranked by time attributed:", flush=True)
            for r, nm, ab, am, where in sorted(rows, reverse=True):
                share = (1 - 1 / r) * 100 if r > 1 else 0.0
                print(f"    {r:6.3f}x  {nm:<18} {share:5.1f}% of runtime   {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
