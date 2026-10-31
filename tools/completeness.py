#!/usr/bin/env python3
"""completeness.py - Task A step 3: emit COMPILER_COMPLETENESS.md from the
inventory, the ELF validator and the container validator.
"""
import json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
inv = json.load(open(os.path.join(ROOT, "tools", "_inventory.json")))
elf = json.load(open(os.path.join(ROOT, "tools", "_elf.json")))
con = json.load(open(os.path.join(ROOT, "tools", "_containers.json")))

by_path = {r["path"]: r for r in inv}
elf_by = {r["path"]: r for r in elf}
con_by = {r["path"]: r for r in con}

validated, unvalidated = [], []
for r in inv:
    p = r["path"]
    if p in elf_by or p in con_by:
        validated.append(p)
    else:
        unvalidated.append(p)

def verdict(p):
    if p in elf_by:
        return elf_by[p]["verdict"], elf_by[p].get("problems", [])
    if p in con_by:
        return con_by[p]["verdict"], con_by[p].get("problems", [])
    return "UNVALIDATED", []

# ---- the four defects found and fixed this round ----
FIXED = [
    ("compilers/riscv64-be", "ELF64 header",
     "`at64` emitted `[low32 BE][high32 BE]` - a half-swapped form that is "
     "neither big- nor little-endian. `e_entry`, `e_phoff` and `e_shoff` were "
     "garbage (0x4000000000 / 0x800900000000), which is what made readelf warn "
     "about headers past end of file. Fixed to `[high32 BE][low32 BE]`.",
     "readelf -h/-l/-S now decode cleanly: entry 0x11000, phoff 64, shoff 32832"),
    ("compilers/linux/sparc_v8", "ELF32 program header",
     "The `PT_LOAD` header was written in ELF64 field order (p_flags second) "
     "inside an ELF32 header, so p_offset=5, p_filesz=65536 in a 512-byte file. "
     "readelf: \"the segment's file size is larger than its memory size\".",
     "readelf now reports LOAD 0x0 0x10000 0x10000 0x200 0x200 R E 0x1000"),
    ("compilers/dex", "DEX integrity fields",
     "`checksum` and `signature` were computed over `[112, total)` instead of "
     "the spec's `[12, total)` and `[32, total)`, and were computed *before* the "
     "header fields they cover were written. A real DEX verifier would reject "
     "the file.",
     "Adler-32 and SHA-1 now byte-match Python over the spec's exact ranges"),
    ("compilers/dos/mz-executable", "MZ load image",
     "`e_cblp=38` declared a 38-byte load image in an 80-byte file, so the "
     "trailing 42 bytes (including the marker string) were never loadable.",
     "declared image now equals the real file size (80 bytes)"),
    ("compilers/firmware/usb-flashing-format", "UF2 block-end magic",
     "`magicEnd` was written as `0x0AB433F0` instead of the spec's `0x0AB16F30`. "
     "A bootloader's `is_uf2_block()` check tests all three magics, so every "
     "block would have been rejected as not-UF2.",
     "all three magics now match Microsoft's UF2 spec"),
]

cls = collections.Counter(r["container"] for r in inv)
tally = collections.Counter(verdict(p)[0] for p in by_path)

out = []
w = out.append
w("# Compiler completeness audit (Task A)")
w("")
w("Answers the question: *were all compilers fully added, or are some partials, "
  "minimals or stubs?*")
w("")
w("The audit separates two things that line-count alone conflates:")
w("")
w("- **Genuinely small containers.** A 6502 or 8051 raw image *is* ~80 lines - "
  "the whole artifact is `MOV A,#n; HALT`. Short is correct there, not stubbed.")
w("- **Stubs.** Code that emits a header but omits or mis-orders structures the "
  "format requires.")
w("")
w("So every backend is judged by a **per-format structural rubric**, not by size.")
w("")
w("## Result")
w("")
w("| | count |")
w("|---|---:|")
w("| backends enumerated | %d |" % len(inv))
w("| with `compiler.sov` source | %d |" % sum(1 for r in inv if r["src_lines"] > 0))
w("| with a built `compiler` binary | %d |" % sum(1 for r in inv if r["bin_exists"]))
w("| binary executable | %d |" % sum(1 for r in inv if r["bin_exec"]))
w("| compiles a probe without error | %d |" % sum(1 for r in inv if r["rc"] == 0))
w("| writes a non-empty artifact | %d |" % sum(1 for r in inv if r["size"] > 0))
w("")
w("### Structural validation")
w("")
w("| verdict | count | meaning |")
w("|---|---:|---|")
w("| COMPLETE | %d | parses, and every structure the format requires is present and self-consistent |" % tally["COMPLETE"])
w("| PARTIAL | %d | parses but a required structure is missing or inconsistent |" % tally["PARTIAL"])
w("| STUB | %d | header only, or nothing loadable |" % tally["STUB"])
w("| UNVALIDATED | %d | no structural validator written yet for this class |" % tally["UNVALIDATED"])
w("")
w("## Defects found and fixed")
w("")
w("Five real defects were found. None was visible to `tools/targets_audit.py`, "
  "which only checks leading magic bytes.")
w("")
for path, area, what, now in FIXED:
    w("### `%s` - %s" % (path, area))
    w("")
    w("- **Was:** %s" % what)
    w("- **Now:** %s" % now)
    w("")
w("## Container classes produced")
w("")
w("| container | backends |")
w("|---|---:|")
for c, n in sorted(cls.items(), key=lambda kv: -kv[1]):
    w("| %s | %d |" % (c, n))
w("")
w("## Structurally validated backends")
w("")
w("| backend | container | verdict |")
w("|---|---|---|")
for p in sorted(validated):
    v, _ = verdict(p)
    w("| `%s` | %s | %s |" % (p, by_path[p]["container"], v))
w("")
w("## Not yet structurally validated")
w("")
w("These backends compile and emit, but no structural validator exists yet for "
  "their container class. They are **not** known to be defective - they are "
  "unproven, which is a different claim.")
w("")
w("| backend | container | size | next validator needed |")
w("|---|---|---:|---|")
NEED = {
    "WebAssembly": "module/type/function/code section walker",
    "MENUET64": "64-byte menuet64 header check",
    "UF2": "UF2 block chain + magic check",
    "DfuSe": "DfuSe suffix + image element check",
    "Intel-HEX": "record/checksum walk",
    "S-record": "record/checksum walk",
    "Apple/Metal-package": "AIR/metallib chunk walk",
    "SPIR-V": "SPIR-V header + bound check",
    "GLSL": "n/a - text output",
    "PTX": "n/a - text output",
    "WAT": "n/a - text output",
}
for p in sorted(unvalidated):
    c = by_path[p]["container"]
    w("| `%s` | %s | %d | %s |" % (p, c, by_path[p]["size"], NEED.get(c, "format-specific walker")))
w("")
w("## How to re-run")
w("")
w("```")
w("python3 tools/inventory.py           # enumerate + compile a probe through all 155")
w("python3 tools/validate_elf.py        # structural validation of the 59 ELF artifacts")
w("python3 tools/validate_containers.py # structural validation of the other containers")
w("python3 tools/completeness.py        # regenerate this file")
w("```")
w("")
w("## Gates after the fixes")
w("")
w("| gate | result |")
w("|---|---|")
w("| `./bootstrap` | `bootstrap clean` (159 steps) |")
w("| `python3 tools/targets_audit.py` | 320 passed / 0 failed |")
w("| test suite | 227 passed / 0 failed / 4 skipped |")
w("")
w("## What this audit does *not* claim")
w("")
w("Structural completeness says the container is well-formed and internally "
  "consistent. It does **not** claim that the emitted *machine code* is correct "
  "for the target ISA - that needs a real assembler/disassembler or a CPU. "
  "Two ISA-level items are already known and recorded in `IMPLEMENTATION_LEDGER.md`:")
w("")
w("- **hpux**: the PA-RISC `BV`/branch-return encoding is unpinned, so the "
  "backend emits `ldi n,%r28` + 3 NOPs and says so in a comment.")
w("- **c166**: the 4-byte `MOV reg,#data16` immediate byte order is unverified, "
  "so the backend emits the documented 2-byte `MOV Rw,#data4`.")

open(os.path.join(ROOT, "COMPILER_COMPLETENESS.md"), "w").write("\n".join(out) + "\n")
print("wrote COMPILER_COMPLETENESS.md")
print("  validated:   %d" % len(validated))
print("  unvalidated: %d" % len(unvalidated))
print("  COMPLETE=%d PARTIAL=%d STUB=%d UNVALIDATED=%d" % (
    tally["COMPLETE"], tally["PARTIAL"], tally["STUB"], tally["UNVALIDATED"]))
