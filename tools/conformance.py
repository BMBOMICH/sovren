#!/usr/bin/env python3
"""conformance.py - per-driver fleet conformance gate (EXACT_TODO item 47).

For every registry driver:
  1. build the driver binary from canonical source with the installed
     linux compiler (fresh, no caching of any kind)
  2. run the driver on tests/conformance/corpus/* (or a builtin corpus
     when that directory is absent) plus generated 40 KB and 1 MB
     unique-line sources
  3. classify: PASS (rc=0 and non-empty output), REFUSE (rc!=0, loud),
     STUB (rc=0 but output suspiciously tiny for a big input), TIMEOUT,
     BUILDFAIL
  4. record per-driver MB/s on the 1 MB corpus

A driver PASSES the gate only if it builds and compiles every corpus
file. REFUSE/STUB/TIMEOUT/BUILDFAIL are reported, never silently
skipped; the process exits nonzero unless every driver passes.
Registry "kind" scopes expectation: evaluators are expected to handle
the evaluator corpus (constant-return programs); anything else must be
a loud REFUSE, never a silent STUB.

Usage: python3 tools/conformance.py [--kinds evaluator,...] [--timeout S]
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMP = os.path.join(ROOT, "compilers/linux/compiler")
LOG = "/home/user/conformance_one.log"


def build(src, dst, timeout):
    if os.path.exists(dst):
        os.unlink(dst)
    try:
        with open(LOG, "w+b") as lf:
            p = subprocess.run([COMP, src, "-o", dst], cwd=ROOT, stdout=lf,
                               stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    if p.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) == 0:
        return "BUILDFAIL"
    os.chmod(dst, 0o755)
    return "ok"


def drive(binary, src, dst, cwd, timeout):
    if os.path.exists(dst):
        os.unlink(dst)
    t0 = time.perf_counter()
    try:
        with open(LOG, "w+b") as lf:
            p = subprocess.run([binary, src, "-o", dst], cwd=cwd, stdout=lf,
                               stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 0.0
    dt = time.perf_counter() - t0
    if p.returncode != 0:
        return "REFUSE", dt
    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
        return "REFUSE", dt
    insz, outsz = os.path.getsize(src), os.path.getsize(dst)
    if insz > 200_000 and outsz < 64:
        return "STUB", dt
    return "PASS", dt


def gen_corpus(td):
    corpus = []
    cdir = os.path.join(ROOT, "tests/conformance/corpus")
    if os.path.isdir(cdir):
        for f in sorted(os.listdir(cdir)):
            if f.endswith(".sov"):
                corpus.append(os.path.join(cdir, f))
    if not corpus:
        small = os.path.join(td, "c_small.sov")
        open(small, "w").write("main:\n    return 42\n")
        corpus.append(small)
        pr = os.path.join(td, "c_print.sov")
        open(pr, "w").write("main:\n    x: 6 * 7\n    print x\n    return 0\n")
        corpus.append(pr)
    for name, target in (("c_40kb.sov", 40_000), ("c_1mb.sov", 1_000_000)):
        p = os.path.join(td, name)
        lines, n, tot = [], 0, 0
        while tot < target:
            blk = f"g{n}:\n    return {n * 3 + 1}\n"
            lines.append(blk); tot += len(blk); n += 1
        lines.append("main:\n    return 42\n")
        open(p, "w").write("".join(lines))
        corpus.append(p)
    return corpus


def main():
    timeout = 120
    kinds = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--timeout":
            timeout = int(args[i + 1]); i += 2
        elif args[i] == "--kinds":
            kinds = set(args[i + 1].split(",")); i += 2
        else:
            print("unknown arg", args[i]); return 2
    reg = json.load(open(os.path.join(ROOT, "compilers/registry.json")))
    entries = reg["entries"]
    if kinds:
        entries = [e for e in entries if e.get("kind") in kinds]
    summary = {}
    with tempfile.TemporaryDirectory() as td:
        corpus = gen_corpus(td)
        big = corpus[-1]
        for e in entries:
            name, kind = e["id"], e.get("kind", "?")
            src = os.path.join(ROOT, e["source"])
            binary = os.path.join(td, "drv")
            st = build(src, binary, timeout)
            if st != "ok":
                summary.setdefault(st, []).append(name)
                print(f"{name:<44} {kind:<12} {st}", flush=True)
                continue
            worst, mbps = "PASS", 0.0
            for c in corpus:
                out = os.path.join(td, "o.bin")
                r, dt = drive(binary, c, out, td, timeout)
                if c == big and r == "PASS" and dt > 0:
                    mbps = os.path.getsize(c) / dt / 1e6
                if r != "PASS":
                    worst = r
                    break
            summary.setdefault(worst, []).append(name)
            extra = f" {mbps:7.2f} MB/s" if worst == "PASS" else ""
            print(f"{name:<44} {kind:<12} {worst}{extra}", flush=True)
    print()
    for k in ("PASS", "REFUSE", "STUB", "TIMEOUT", "BUILDFAIL"):
        if k in summary:
            print(f"  {k:<10} {len(summary[k]):>4}")
    return 0 if set(summary) <= {"PASS"} else 1


if __name__ == "__main__":
    sys.exit(main())
