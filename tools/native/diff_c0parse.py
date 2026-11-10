#!/usr/bin/env python3
"""Differential: _sov_c0_parse native blob vs the Python reference.

Drives the C harness (tools/native/c0parse_harness.c linked against the
strict-compiled tools/native_c0parse.c) over the same case set the reference
generator produces (14 regressions with the g2 gate on + 1500 seeded random
cases, every 7th with the g2 gate on), then compares every published list,
need_priv, had_err, the print-marker sequence and the g2 log bytes.

0 divergences required before wiring the blob into compiler.sov.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent          # tools/native
ROOT = HERE.parent.parent                        # sovren repo root
sys.path.insert(0, str(HERE))
import c0parse_ref as ref  # noqa: E402

BLOB = ROOT / "tools" / "native_c0parse.c"
HARNESS = HERE / "c0parse_harness.c"

FLAGS = ("-O3 -mno-red-zone -fno-tree-vectorize -fno-jump-tables "
         "-fno-tree-switch-conversion -fno-stack-protector "
         "-fno-asynchronous-unwind-tables -fno-unwind-tables "
         "-fcf-protection=none -fno-builtin -ffreestanding -fPIC").split()


def esc(b):
    out = bytearray()
    for ch in b:
        if ch == 0x5C:  # backslash
            out += b"\\\\"
        elif ch == 0x0A:
            out += b"\\n"
        elif ch == 0x09:
            out += b"\\t"
        elif ch == 0x0D:
            out += b"\\r"
        else:
            out.append(ch)
    return bytes(out)


def build_cases():
    cases = []
    for name, lines, src_base, kern, np_ in ref.REGRESSIONS:
        cases.append((name, lines, src_base, kern, np_, True))
    import random
    rng = random.Random(20261104)
    words = [b"foo", b"bar_baz", b"x", b"heap_ptr", b"sc_exit", b"g_argc", b"zz"]
    hdrs = [b"task t:", b"t:", b"task nm with a, b:",
            b"task nm with a, b, c, d, e, f, g, h:", b"main argc argv:"]
    for ci in range(1500):
        n = rng.randint(0, 20)
        lines = []
        for _ in range(n):
            k = rng.randint(0, 9)
            ind = b" " * rng.randint(0, 8)
            if k == 0:
                lines.append(rng.choice(hdrs))
            elif k == 1:
                lines.append(rng.choice(words) + b": " +
                             rng.choice([b"1", b'"a:b"', b'"q:=z"', b'"s"']))
            elif k == 2:
                lines.append(ind + b"law " +
                             rng.choice([b'"nm" x is 0', b"nm x is 0", b"nm"]))
            elif k == 3:
                lines.append(b"  " + rng.choice([b"private", b"wipe q", b"r()"]))
            elif k == 4:
                lines.append(b"# comment")
            elif k == 5:
                lines.append(b"")
            elif k == 6:
                lines.append(ind + b"    r()" + b" " * rng.randint(0, 2))
            elif k == 7:
                lines.append(b"<-- " + rng.choice([b"al ias", b"plain"]) +
                             b" := " + b"val")
            elif k == 8:
                lines.append(ind + b"\tx")
            else:
                lines.append(ind + b"use lib")
        src_base = rng.randint(0, len(lines) + 3)
        kern = rng.randint(0, 1)
        cases.append((f"rand{ci}", lines, src_base, kern, 0, ci % 7 == 3))
    return cases


def write_casefile(path, cases):
    with open(path, "wb") as f:
        for name, lines, src_base, kern, np_, g2 in cases:
            f.write(b"CASE %d %d %d %d\n" % (src_base, kern, np_, 1 if g2 else 0))
            for ln in lines:
                f.write(esc(ln) + b"\n")
            f.write(b"END\n")


def E(x):
    """json-loaded latin-1 str -> bytes (recursively for lists)."""
    if isinstance(x, str):
        return x.encode("latin-1")
    if isinstance(x, list):
        return [E(i) for i in x]
    return x


def run_ref(cases):
    results = []
    for name, lines, src_base, kern, np_, g2 in cases:
        ref.PRINTS.clear()
        ref.G2_ON = g2
        r = ref.parse(lines, src_base, kern, np_)
        r = dict(r)
        r["prints"] = list(ref.PRINTS)
        results.append(r)
    return results


def main():
    with tempfile.TemporaryDirectory() as td:
        blob_o = Path(td) / "blob.o"
        har_o = Path(td) / "har.o"
        exe = Path(td) / "harness"
        subprocess.run(["gcc", "-c", str(BLOB), "-o", str(blob_o), *FLAGS],
                       check=True)
        subprocess.run(["gcc", "-c", str(HARNESS), "-o", str(har_o),
                        "-O2", "-Wall"], check=True)
        subprocess.run(["gcc", str(blob_o), str(har_o), "-o", str(exe)],
                       check=True)
        cases = build_cases()
        cf = Path(td) / "cases.txt"
        write_casefile(cf, cases)
        try:
            out = subprocess.run([str(exe), str(cf)], check=True,
                                 capture_output=True, timeout=300).stdout
        except subprocess.TimeoutExpired:
            print("HARNESS TIMEOUT (>300s) - likely an infinite loop in the blob")
            return 1
        hres = [json.loads(l) for l in out.decode().splitlines() if l.strip()]
        rres = run_ref(cases)
        if len(hres) != len(rres):
            print(f"case count mismatch: harness {len(hres)} vs ref {len(rres)}")
            return 1
        bad = 0
        for i, (h, r) in enumerate(zip(hres, rres)):
            name = cases[i][0]
            hp = [E(x) for x in h["prints"].split("\x01")]
            if hp and hp[0] == b"":
                hp = hp[1:]
            hp = hp[1:] if hp and hp[0] == "" else hp
            hr = E(h["g2log"])
            cmp_pairs = [
                ("names", E(h["names"]), r["names"]),
                ("params", E(h["params"]), r["params"]),
                ("bodies", E(h["bodies"]), r["bodies"]),
                ("body_lns", h["body_lns"], [list(x) for x in r["body_lns"]]),
                ("task_lns", h["task_lns"], list(r["task_lns"])),
                ("task_user", h["task_user"], list(r["task_user"])),
                ("glob_names", E(h["glob_names"]), r["glob_names"]),
                ("sglob_names", E(h["sglob_names"]), r["sglob_names"]),
                ("tops", E(h["tops"]), r["tops"]),
                ("tops_lns", h["tops_lns"], list(r["tops_lns"])),
                ("tops_users", h["tops_users"], list(r["tops_users"])),
                ("need_priv", h["need_priv"], r["need_priv"]),
                ("had_err", h["had_err"], r["had_err"]),
                ("prints", hp, r["prints"]),
                ("g2log", hr, r["g2log"]),
            ]
            for field, hv, rv in cmp_pairs:
                if hv != rv:
                    bad += 1
                    if bad <= 6:
                        print(f"DIVERGENCE case {i} ({name}) field {field}:")
                        print(f"  harness: {hv!r:.400}")
                        print(f"  ref    : {rv!r:.400}")
                    break
        if bad:
            print(f"FAIL: {bad} divergent cases of {len(cases)}")
            return 1
        print(f"PASS: {len(cases)} cases, 0 divergences "
              f"(14 regressions + 1500 random, g2 gate exercised)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
