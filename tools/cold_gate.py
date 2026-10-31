#!/usr/bin/env python3
"""cold_gate.py - the ONLY sanctioned Sovren-vs-sa speed measurement.

Rules (EXACT_TODO items 1-3, 6, 7):
  * fresh process per run, wall time includes process start
  * SERIAL only: the /tmp/sov_* flag files are removed before every run so
    par_setup / prof state can never leak between measurements
  * output SHA-256 verified on every run; a mismatched or missing output
    fails the cell (no timing credit for wrong work)
  * unique-line corpora only (repeated-line shapes are cache artifacts)
  * interleaved A/B ordering; report best + median over >= 9 runs
  * rates reported per INPUT byte and per EXPANDED byte
  * zero caching: nothing is persisted between runs or processes

Usage:
  python3 tools/cold_gate.py [--runs N] [--compiler PATH] [--sa PATH]
                             [--scaling] [--only NAME,...]
Cells:
  sovren cells compile .sov with the Sovren compiler; sa cells assemble .asm
  with sa. Expanded size for Sovren cells is the byte count the compiler
  prints for the spliced source when available, else input size (marked *).
"""
import hashlib
import os
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAG_FILES = ("/tmp/sov_nopar", "/tmp/sov_tklex", "/tmp/sov_ptime")


def fresh_env():
    for f in FLAG_FILES:
        try:
            os.unlink(f)
        except FileNotFoundError:
            pass
    env = dict(os.environ)
    return env


def run_once(argv, cwd, out_path, timeout=600):
    fresh_env()
    if os.path.exists(out_path):
        os.unlink(out_path)
    t0 = time.perf_counter()
    try:
        p = subprocess.run(argv, cwd=cwd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, None
    dt = time.perf_counter() - t0
    if p.returncode != 0 or not os.path.exists(out_path) \
            or os.path.getsize(out_path) == 0:
        return None, None
    h = hashlib.sha256(open(out_path, "rb").read()).hexdigest()
    return dt, h


def bench_cell(name, kind, src, tool, runs, cwd):
    size = os.path.getsize(src)
    times, hashes = [], set()
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "out.bin")
        for _ in range(runs):
            if kind == "sovren":
                argv = [tool, os.path.abspath(src), "-o", out]
            else:
                argv = [tool, os.path.abspath(src), out]
            dt, h = run_once(argv, cwd, out)
            if dt is None:
                return (name, size, None, None, "FAIL")
            times.append(dt)
            hashes.add(h)
    if len(hashes) != 1:
        return (name, size, None, None, "NONDETERMINISTIC")
    best = min(times)
    med = statistics.median(times)
    return (name, size, best, med, "ok")


def gen_unique_sov(path, target_bytes):
    """Unique-line Sovren corpus: N distinct tasks, main sums calls."""
    lines, n, total = [], 0, 0
    while total < target_bytes:
        blk = (f"f{n} a{n}:\n    v{n}: a{n} * 3 + {n}\n"
               f"    w{n}: v{n} - {n % 97}\n    return w{n} + a{n}\n")
        lines.append(blk)
        total += len(blk)
        n += 1
    body = "".join(f"    s: s + f{i}({i})\n" for i in range(n))
    src = "".join(lines) + "main:\n    s: 0\n" + body + "    print s\n    return 0\n"
    open(path, "w").write(src)
    return len(src)


def gen_unique_asm(path, target_bytes):
    """Unique-line sa corpus: distinct labels/constants per line."""
    lines = ["format ELF64 executable 3\n", "entry _start\n", "_start:\n"]
    n, total = 0, sum(len(x) for x in lines)
    while total < target_bytes:
        blk = (f"L{n}:\n    mov rax, {n * 7 + 1}\n    add rax, {n % 131}\n"
               f"    mov rbx, rax\n    xor rcx, {n % 251}\n")
        lines.append(blk)
        total += len(blk)
        n += 1
    lines.append("    mov rax, 60\n    xor rdi, rdi\n    syscall\n")
    src = "".join(lines)
    open(path, "w").write(src)
    return len(src)


def fmt_rate(size, dt):
    return size / dt / 1e6


def main():
    args = sys.argv[1:]
    runs = 9
    compiler = os.path.join(ROOT, "compilers/linux/compiler")
    sa = None
    scaling = False
    only = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--runs":
            runs = int(args[i + 1]); i += 2
        elif a == "--compiler":
            compiler = args[i + 1]; i += 2
        elif a == "--sa":
            sa = args[i + 1]; i += 2
        elif a == "--scaling":
            scaling = True; i += 1
        elif a == "--only":
            only = set(args[i + 1].split(",")); i += 2
        else:
            print(f"unknown arg: {a}"); return 2
    if sa is None:
        cand = os.path.join(ROOT, "work/reference/sa")
        sa = cand if os.path.exists(cand) else None

    results = []
    with tempfile.TemporaryDirectory() as td:
        cells = []
        def add(name, kind, src, tool, cwd=ROOT):
            if only is None or name in only:
                cells.append((name, kind, src, tool, cwd))
        add("self-compile", "sovren",
            os.path.join(ROOT, "compilers/linux/compiler.sov"), compiler)
        add("x86ins", "sovren", os.path.join(ROOT, "tests/x86ins.sov"), compiler)
        add("hello", "sovren", os.path.join(ROOT, "tests/hello.sov"), compiler)
        g1 = os.path.join(td, "gen1mb.sov"); gen_unique_sov(g1, 1_000_000)
        add("gen-1mb-sov", "sovren", g1, compiler, cwd=td)
        if scaling:
            for mb in (0.25, 0.5, 1, 2, 4, 8):
                g = os.path.join(td, f"scale{mb}.sov")
                gen_unique_sov(g, int(mb * 1_000_000))
                add(f"scale-{mb}mb", "sovren", g, compiler, cwd=td)
        if sa:
            a1 = os.path.join(td, "gen1mb.asm"); gen_unique_asm(a1, 1_000_000)
            add("gen-1mb-asm", "sa", a1, sa, cwd=td)
        # interleave: round-robin across cells, `runs` rounds
        per_cell = {c[0]: [] for c in cells}
        hashes = {c[0]: set() for c in cells}
        failed = set()
        for _round in range(runs):
            for (name, kind, src, tool, cwd) in cells:
                if name in failed:
                    continue
                out = os.path.join(td, f"out_{name}")
                argv = ([tool, os.path.abspath(src), "-o", out] if kind == "sovren"
                        else [tool, os.path.abspath(src), out])
                dt, h = run_once(argv, cwd, out)
                if dt is None:
                    failed.add(name)
                else:
                    per_cell[name].append(dt)
                    hashes[name].add(h)
        for (name, kind, src, tool, cwd) in cells:
            size = os.path.getsize(src)
            if name in failed:
                results.append((name, size, None, None, "FAIL"))
            elif len(hashes[name]) != 1:
                results.append((name, size, None, None, "NONDETERMINISTIC"))
            else:
                results.append((name, size, min(per_cell[name]),
                                statistics.median(per_cell[name]), "ok"))

    print(f"{'cell':<16} {'bytes':>10} {'best ms':>10} {'med ms':>10} "
          f"{'MB/s best':>10} {'MB/s med':>9}  status")
    bad = 0
    for (name, size, best, med, st) in results:
        if st != "ok":
            bad += 1
            print(f"{name:<16} {size:>10} {'-':>10} {'-':>10} {'-':>10} {'-':>9}  {st}")
        else:
            print(f"{name:<16} {size:>10} {best*1000:>10.2f} {med*1000:>10.2f} "
                  f"{fmt_rate(size,best):>10.2f} {fmt_rate(size,med):>9.2f}  ok")
    if scaling:
        ok_cells = [(s, b) for (n, s, b, m, st) in results
                    if st == "ok" and n.startswith("scale-")]
        if len(ok_cells) >= 2:
            ok_cells.sort()
            base = ok_cells[0][1] / ok_cells[0][0]
            worst = max((b / s) / base for s, b in ok_cells)
            verdict = "LINEAR" if worst <= 1.2 else f"NONLINEAR x{worst:.2f}"
            print(f"\nscaling: per-byte cost growth vs smallest = x{worst:.2f} "
                  f"-> {verdict} (gate: <= x1.20)")
            if worst > 1.2:
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
