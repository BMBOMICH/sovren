#!/usr/bin/env python3
"""fleet_diff.py - differential gate for the whole compiler fleet.

Compiles every compilers/**/compiler.sov with two compiler binaries and compares
the artifacts byte for byte. This is the instrument that makes aggressive change
safe: any compiler edit that alters codegen for any of the 155 backends shows up
here immediately, instead of surfacing later as a mysterious failure.

  python3 tools/fleet_diff.py BASE CANDIDATE

Classification per target:
  SAME        both compiled, artifacts byte-identical
  DIFFER      both compiled, artifacts differ        <-- behaviour change
  ONLY-BASE   base compiled, candidate failed        <-- regression
  ONLY-CAND   candidate compiled, base failed        <-- fixed
  BOTH-FAIL   neither compiled                       <-- pre-existing gap

Exit code 0 only when every target builds and is byte-identical. BOTH-FAIL is not success.
"""
import os, subprocess, sys, tempfile, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def targets():
    out = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "compilers")):
        if "compiler.sov" in files:
            out.append(os.path.join(dirpath, "compiler.sov"))
    return sorted(out)


def build(binary, src, dst):
    if os.path.exists(dst): os.unlink(dst)
    logf = dst + ".log"
    try:
        with open(logf, "w+b") as lf:
            p = subprocess.run([binary, src, "-o", dst], cwd=ROOT,
                               stdout=lf, stderr=subprocess.STDOUT, timeout=180)
            lf.seek(0)
            loghead = lf.read(65536)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    finally:
        if os.path.exists(logf): os.unlink(logf)
    if p.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) == 0:
        err = loghead.decode("utf-8", "replace")
        first = ""
        lines = [l for l in err.splitlines() if l.strip()]
        for i, l in enumerate(lines):
            if l.startswith("Error:"):
                first = " ".join(lines[i:i + 2])
                break
        return False, (first or "no output").strip()
    return True, ""


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    base, cand = sys.argv[1], sys.argv[2]
    for b in (base, cand):
        if not os.access(b, os.X_OK):
            print(f"not executable: {b}")
            return 2

    buckets = {"SAME": [], "DIFFER": [], "ONLY-BASE": [], "ONLY-CAND": [], "BOTH-FAIL": []}
    reasons = {}
    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "a")
        b = os.path.join(td, "b")
        for src in targets():
            name = os.path.relpath(os.path.dirname(src), ROOT)[len("compilers/"):]
            oka, _ = build(base, src, a)
            okb, why = build(cand, src, b)
            if oka and okb:
                ha = hashlib.sha256(open(a, "rb").read()).hexdigest()
                hb = hashlib.sha256(open(b, "rb").read()).hexdigest()
                buckets["SAME" if ha == hb else "DIFFER"].append(name)
            elif oka:
                buckets["ONLY-BASE"].append(name)
                reasons[name] = why
            elif okb:
                buckets["ONLY-CAND"].append(name)
            else:
                buckets["BOTH-FAIL"].append(name)
                reasons[name] = why
            for f in (a, b):
                if os.path.exists(f):
                    os.remove(f)

    print(f"base      {base}")
    print(f"candidate {cand}")
    print()
    for k in ("SAME", "DIFFER", "ONLY-BASE", "ONLY-CAND", "BOTH-FAIL"):
        print(f"  {k:<10} {len(buckets[k]):>4}")
    for k in ("DIFFER", "ONLY-BASE", "ONLY-CAND", "BOTH-FAIL"):
        if buckets[k]:
            print(f"\n-- {k} --")
            for n in buckets[k]:
                extra = f"   [{reasons.get(n, '')}]" if n in reasons else ""
                print(f"  {n}{extra}")
    bad = sum(len(v) for k,v in buckets.items() if k != "SAME")
    print(f"\n{'CLEAN' if bad == 0 else 'NOT CLEAN'}: "
          f"{len(buckets['DIFFER'])} behaviour changes, {len(buckets['ONLY-BASE'])} regressions")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
