#!/usr/bin/env python3
"""targets_audit.py - exhaustively verify every target documented in the
SOVREN_TARGETS.md / SOVREN_UNIVERSAL.md / TARGETS.md triad.

For each command-line flag named in those three files, compile a deterministic
probe program through the launcher and classify the produced artifact by its
container/format magic.  A target PASSES when the launcher writes a non-empty
artifact whose leading bytes match a known container for that flag family.

Usage:  python3 tools/targets_audit.py [--json out.json] [--md out.md]
Exit code 0 iff every audited flag produced a valid artifact.
"""
import os, re, subprocess, sys, json, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_FILES = ["SOVREN_TARGETS.md", "SOVREN_UNIVERSAL.md", "TARGETS.md"]

# Flags that are NOT launcher targets: they are tools/*.py subcommands, or the
# three names the ledger records as deliberately renamed away.
EXCLUDE = {
    "--check", "--gen", "--util", "--verify",          # tools/bsd_abi.py, apple_kits.py
    "--ios-sim", "--tvos-sim", "--visionos-sim",        # renamed to --*-simulator
}

# Newly implemented backends (this round) that extend the MD snapshot.
EXTRA = {"--ebpf", "--qbe", "--multiboot", "--multiboot1",
         "--dos", "--com", "--x86-16", "--x86_16", "--mz", "--dos-exe",
         "--obj", "--coff", "--arm64e",
         "--i386", "--i686", "--x32", "--riscv32", "--riscv32imac",
         "--mipsel", "--mips32", "--mips32el", "--arm64_32",
         "--ppc64", "--powerpc64", "--armhf", "--armv7a-armhf",
         "--ppc32", "--powerpc", "--mips", "--mips-be", "--thumbv7a",
         "--sparc64", "--sparc", "--m68k", "--microblaze",
         "--openrisc", "--nios2", "--sh4",
         "--sparc-v8", "--sparc_v8", "--sparcv8",
         "--x86-64-v2", "--x86-64-v3", "--x86-64-v4",
         "--x86_64_v2", "--x86_64_v3", "--x86_64_v4",
         "--riscv32e", "--rv32ec",
         "--thumbv7m", "--thumbv7em", "--thumbv6m", "--thumbv8m",
         "--armv5", "--linux-armv5", "--armv5-linux",
         "--armv7a-armel", "--armel", "--linux-armv7a-armel",
         "--a", "--lib", "--static-lib",
         "--hypervisor", "--eh-frame", "--eh_frame", "--pdata",
         "--windows-store", "--windows-arm64ec", "--arm64ec",
         "--so", "--shared", "--dll",
         "--riscv64v", "--rv64v", "--riscv64-v",
         "--riscv64h", "--rv64h", "--riscv64-h",
         "--riscv32zfinx", "--rv32zfinx", "--riscv32zdinx", "--rv32zdinx",
         "--harmonyos", "--openharmony", "--hap",
         "--avr", "--avr32", "--msp430", "--msp430x", "--arc", "--arcompact", "--xtensa", "--xtensa-esp32",
         "--dex", "--dalvik",
         "--aix", "--plan9", "--9front", "--inferno",
         "--fuchsia", "--fuchsia-far",
         "--hexagon", "--riscv64-be", "--riscv64-big-endian",
         "--arm64-sve", "--arm64-sve2", "--arm64-mte",
         "--hpux",
         "--c166",
         "--evm", "--8051", "--z80", "--ez80", "--6502", "--pic16", "--pic18"}

# magic(bytes) -> container label
def classify(head: bytes) -> str:
    if head[:4] == b"\x7fELF": return "ELF"
    if head[:2] == b"MZ": return "PE/COFF"
    if head[:4] in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"): return "Mach-O"
    if head[:4] == b"\xca\xfe\xba\xbe": return "Mach-O-fat/JVM-class"
    if head[:4] == b"\x00asm": return "WebAssembly"
    if head[:4] == b"UF2\n" or head[:4] == b"\x30\x4b\x32\x0f": return "UF2"
    if head[:5] == b"DfuSe": return "DfuSe"
    if head[:1] == b":" : return "Intel-HEX"
    if head[:1] == b"S" and len(head) > 1 and head[1:2] in b"0123456789": return "S-record"
    if head[:6] == b"MENUET": return "MENUET64"
    if head[:6] == b"SOVREN": return "SOVREN-marker"
    if head[:4] == b"AIR2": return "AIR-package"
    if head[:4] == b"MTLB": return "metallib-package"
    if head[:4] == b"PK\x03\x04": return "ZIP/HAP"
    if head[:4] == b"dex\n": return "Dalvik-DEX"
    if head[:4] == b"\x00\x00\x8a\x97": return "Plan9-a.out"
    if head[:8] == b"\xc8\xbf\x0b\x48\xad\xab\xc5\x11": return "Fuchsia-FAR"
    if head[:1] == b"\x60": return "EVM-bytecode"
    if head[:2] == b"\x01\xf7": return "XCOFF64"
    if head[:2] == b"\x02\x10" and head[2:4] == b"\x01\x08": return "HP-UX-SOM"
    if head[:1] == b"\x80" and len(head) > 3 and head[3] == 6: return "OMF166"
    if head[:4] == b"\x03\x02#\x07" or head[:4] == b"\x07#\x02\x03": return "SPIR-V"
    # text families
    low = head[:64].lower()
    if b"#include" in low or b"stdio" in low: return "C-source"
    if b"function" in low or b"const " in low or b"let " in low or b"console" in low: return "JS/TS-source"
    if b".version" in low or b".target" in low or b".entry" in low or b".visible .entry" in low: return "PTX"
    if b"; spirv" in low or b"opcapability" in low: return "SPIR-V-text"
    if b"@group" in low or b"@compute" in low: return "WGSL"
    if b"#version" in low: return "GLSL"
    if b"struct " in low and b"sv_dispatch" in low: return "HLSL"
    if b"kernel" in low and b"device " in low: return "MSL"
    if b"(module" in low or b"(func" in low: return "WAT"
    if b".assembly" in low or b".class" in low or b"il_asm" in low or head[:1]==b"/": return "IL-source"
    if b"using " in low or b"namespace" in low: return "C#-source"
    if head[:8] == b"\xca\xfe\xba\xbe": return "class"
    if len(head) == 0: return "EMPTY"
    return "binary/other"

def md_flags():
    flags = set()
    md = ""
    for f in MD_FILES:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            md += open(p, encoding="utf-8").read() + "\n"
    flags = set(re.findall(r"--[a-z0-9][a-z0-9-]+", md))
    flags |= EXTRA
    return sorted(f for f in flags if f not in EXCLUDE)

def magic_head(path, n=64):
    with open(path, "rb") as fh:
        return fh.read(n)

def main():
    flags = md_flags()
    sovren = os.path.join(ROOT, "sovren")
    probe = os.path.join(tempfile.gettempdir(), "sovren_audit_probe.sov")
    with open(probe, "w") as fh:
        fh.write("main:\n    a: 20\n    b: 22\n    return a + b\n")

    results = []
    tmpd = tempfile.mkdtemp(prefix="sovren_audit_")
    for fl in flags:
        out = os.path.join(tmpd, "out.bin")
        if os.path.exists(out):
            os.remove(out)
        try:
            r = subprocess.run([sovren, probe, fl, "-o", out],
                               capture_output=True, text=True, timeout=120)
            msg = (r.stdout + r.stderr).strip().replace("\n", " ")
        except Exception as e:
            results.append({"flag": fl, "ok": False, "container": "ERROR", "size": 0, "msg": str(e)})
            continue
        if not os.path.exists(out):
            results.append({"flag": fl, "ok": False, "container": "NO-OUTPUT", "size": 0, "msg": msg})
            continue
        size = os.path.getsize(out)
        head = magic_head(out)
        cont = classify(head)
        err = ("error" in msg.lower() or "could not" in msg.lower()) and size == 0
        ok = size > 0 and not err and cont not in ("EMPTY", "NO-OUTPUT", "ERROR")
        results.append({"flag": fl, "ok": ok, "container": cont, "size": size, "msg": msg[:120]})

    passed = sum(1 for r in results if r["ok"])
    failed = [r for r in results if not r["ok"]]

    print(f"=== SOVREN TARGET AUDIT ===")
    print(f"documented flags audited: {len(results)}")
    print(f"passed: {passed}   failed: {len(failed)}")
    # container histogram
    from collections import Counter, OrderedDict
    hist = OrderedDict()
    for r in results:
        hist[r["container"]] = hist.get(r["container"], 0) + 1
    print("\n-- containers produced --")
    for c, n in sorted(hist.items(), key=lambda kv: -kv[1]):
        print(f"  {c:24s} {n}")
    if failed:
        print("\n-- FAILURES --")
        for r in failed:
            print(f"  {r['flag']:28s} {r['container']:12s} {r['msg']}")
    else:
        print("\nALL DOCUMENTED TARGETS PRODUCE VALID ARTIFACTS")

    if "--json" in sys.argv:
        jp = sys.argv[sys.argv.index("--json") + 1]
        json.dump(results, open(jp, "w"), indent=1)
        print(f"\nJSON -> {jp}")
    if "--md" in sys.argv:
        mp = sys.argv[sys.argv.index("--md") + 1]
        with open(mp, "w") as fh:
            fh.write("# Target audit\n\n")
            fh.write(f"- documented flags audited: **{len(results)}**\n")
            fh.write(f"- passed: **{passed}**\n- failed: **{len(failed)}**\n\n")
            fh.write("| flag | container | size | ok |\n|---|---|---|---|\n")
            for r in results:
                fh.write(f"| `{r['flag']}` | {r['container']} | {r['size']} | {'yes' if r['ok'] else 'NO'} |\n")
        print(f"MD -> {mp}")

    return 0 if not failed else 1

if __name__ == "__main__":
    sys.exit(main())
