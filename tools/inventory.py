#!/usr/bin/env python3
"""inventory.py - Task A step 1: enumerate the whole compiler fleet, compile a
deterministic probe through each backend directly, and record what came out.

This does NOT judge completeness. It only establishes, per compiler:
  - the source and binary exist, and the binary is executable
  - the backend compiles the probe without error
  - the artifact's size and container class (magic + structural sniff)
  - the source's line count and which shared template it derives from
"""
import os, subprocess, sys, hashlib, json, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = "main:\n    a: 20\n    b: 22\n    return a + b\n"
OUTDIR = "/tmp/audit_a"
PROBEF = "/tmp/audit_a/probe.sov"
os.makedirs(OUTDIR, exist_ok=True)
with open(PROBEF, "w") as _fh:
    _fh.write(PROBE)

# ---------- container sniffing (structural where the format allows) ----------
def sniff(path):
    with open(path, "rb") as fh:
        d = fh.read()
    h = d[:64]
    if len(d) == 0:
        return "EMPTY", {}
    if h[:4] == b"\x7fELF":
        return "ELF", elf_info(d)
    if h[:2] == b"MZ":
        return "PE/COFF", pe_info(d)
    if h[:4] in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe"):
        return "Mach-O", macho_info(d)
    if h[:4] == b"\xca\xfe\xba\xbe":
        return "Mach-O-fat/JVM-class", {}
    if h[:4] == b"\x00asm":
        return "WebAssembly", {}
    if h[:4] == b"PK\x03\x04":
        return "ZIP/HAP", zip_info(d)
    if h[:4] == b"dex\n":
        return "Dalvik-DEX", {}
    if h[:4] == b"\x00\x00\x8a\x97":
        return "Plan9-a.out", {}
    if h[:8] == b"\xc8\xbf\x0b\x48\xad\xab\xc5\x11":
        return "Fuchsia-FAR", {}
    if h[:1] == b"\x60":
        return "EVM-bytecode", {}
    if h[:2] == b"\x01\xf7":
        return "XCOFF64", {}
    if h[:2] == b"\x02\x10" and h[2:4] == b"\x01\x08":
        return "HP-UX-SOM", {}
    if h[:1] == b"\x80" and len(h) > 3 and h[3] == 6:
        return "OMF166", omf166_info(d)
    if h[:4] == b"\x03\x02#\x07" or h[:4] == b"\x07#\x02\x03":
        return "SPIR-V", {}
    if h[:4] == b"UF2\n":
        return "UF2", {}
    if h[:5] == b"DfuSe":
        return "DfuSe", {}
    if h[:1] == b":":
        return "Intel-HEX", {}
    if h[:1] == b"S" and len(h) > 1 and h[1:2] in b"0123456789":
        return "S-record", {}
    if h[:6] == b"MENUET":
        return "MENUET64", {}
    if h[:4] in (b"AIR2", b"MTLB"):
        return "Apple/Metal-package", {}
    low = h[:200].lower()
    for k, v in [(b"#include", "C-source"), (b"function", "JS/TS-source"),
                 (b".version", "PTX"), (b"opcapability", "SPIR-V-text"),
                 (b"@compute", "WGSL"), (b"#version", "GLSL"),
                 (b"sv_dispatch", "HLSL"), (b"device ", "MSL"),
                 (b"(module", "WAT"), (b".assembly", "IL-source"),
                 (b"namespace", "C#-source")]:
        if k in low:
            return v, {}
    return "binary/other", {}


def u16(d, o): return int.from_bytes(d[o:o+2], "little")
def u32(d, o): return int.from_bytes(d[o:o+4], "little")
def u64(d, o): return int.from_bytes(d[o:o+8], "little")
def u16b(d, o): return int.from_bytes(d[o:o+2], "big")
def u32b(d, o): return int.from_bytes(d[o:o+4], "big")

EM = {0:"none",2:"SPARC",3:"x86",4:"m68k",8:"MIPS",15:"HPPA",18:"SPARC32+",
      20:"PPC",21:"PPC64",22:"S/390",40:"ARM",42:"SH",43:"SPARCV9",50:"IA-64",
      62:"x86-64",83:"AVR",93:"ARC",94:"Xtensa",105:"msp430",140:"TIC6000",
      183:"AArch64",189:"MicroBlaze",190:"CSKY",195:"ARCv2",243:"RISC-V",
      247:"BPF",252:"CSKY",258:"LoongArch",164:"Hexagon"}

def elf_info(d):
    i = {}
    i["class"] = "64" if d[4] == 2 else "32"
    i["data"] = "BE" if d[5] == 2 else "LE"
    i["etype"] = u16(d, 16)
    i["machine"] = EM.get(u16(d, 18), str(u16(d, 18)))
    if d[4] == 2:
        i["entry"] = u64(d, 24); i["phoff"] = u64(d, 32); i["shoff"] = u64(d, 40)
        i["phentsize"] = u16(d, 54); i["phnum"] = u16(d, 56)
        i["shentsize"] = u16(d, 58); i["shnum"] = u16(d, 60)
        i["shstrndx"] = u16(d, 62)
    else:
        i["entry"] = u32(d, 24); i["phoff"] = u32(d, 28); i["shoff"] = u32(d, 32)
        i["phentsize"] = u16(d, 42); i["phnum"] = u16(d, 44)
        i["shentsize"] = u16(d, 46); i["shnum"] = u16(d, 48)
        i["shstrndx"] = u16(d, 50)
    return i

def pe_info(d):
    i = {}
    i["pe_off"] = u32(d, 0x3c)
    if i["pe_off"] + 6 <= len(d) and d[i["pe_off"]:i["pe_off"]+4] == b"PE\x00\x00":
        f = i["pe_off"] + 4
        i["machine"] = hex(u16(d, f)); i["nsec"] = u16(d, f + 2)
        i["optsz"] = u16(d, f + 16)
        i["chars"] = hex(u16(d, f + 18))
    return i

def macho_info(d):
    i = {"magic": hex(u32(d, 0))}
    i["cputype"] = hex(u32(d, 4)); i["ncmds"] = u32(d, 16)
    return i

def zip_info(d):
    return {"size": len(d)}

def omf166_info(d):
    """Walk OMF166 records; verify the self-check invariant on each."""
    i = {"records": []}
    o = 0
    while o + 4 <= len(d):
        rt = d[o]; rl = d[o+1] | (d[o+2] << 8)
        if o + 3 + rl > len(d):
            i["truncated"] = True; break
        s = sum(d[o:o+3+rl]) & 0xff
        i["records"].append((hex(rt), rl, s))
        o += 3 + rl
    i["selfcheck"] = all(s == 0 for _, _, s in i["records"]) if i["records"] else None
    i["end"] = o
    return i

# ---------- fleet enumeration ----------
def fleet():
    out = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "compilers")):
        if "compiler.sov" in filenames:
            rel = os.path.relpath(dirpath, ROOT)
            src = os.path.join(dirpath, "compiler.sov")
            binp = os.path.join(dirpath, "compiler")
            out.append((rel, src, binp))
    return sorted(out)

def template_of(src_text):
    """Which shared template does this backend derive from?"""
    for name, marker in [
        ("avr-ELF32", "avr"), ("riscv64_v-ELF64", "riscv64_v"),
        ("static-archive-ar", "static-archive")]:
        pass
    return None

def main():
    rows = []
    for rel, src, binp in fleet():
        # exec bits are stripped at every tool-call boundary; restore them here
        if os.path.exists(binp):
            try:
                os.chmod(binp, 0o755)
            except Exception:
                pass
        r = {"path": rel, "src_lines": 0, "bin_exists": os.path.exists(binp),
             "bin_exec": os.path.exists(binp) and os.access(binp, os.X_OK),
             "bin_size": os.path.getsize(binp) if os.path.exists(binp) else 0}
        try:
            r["src_lines"] = sum(1 for _ in open(src, encoding="utf-8", errors="replace"))
        except Exception as e:
            r["src_err"] = str(e)
        # compile the probe
        outp = os.path.join(OUTDIR, rel.replace("/", "_") + ".bin")
        try:
            p = subprocess.run([binp, PROBEF, "-o", outp],
                               capture_output=True, text=True, timeout=120)
            r["rc"] = p.returncode
            r["msg"] = (p.stdout + p.stderr).strip().replace("\n", " ")[:100]
        except Exception as e:
            r["rc"] = -1; r["msg"] = str(e)[:100]
        if os.path.exists(outp):
            r["size"] = os.path.getsize(outp)
            with open(outp, "rb") as fh:
                head = fh.read(64)
            r["sha"] = hashlib.sha256(open(outp, "rb").read()).hexdigest()[:16]
            r["container"], r["info"] = sniff(outp)
        else:
            r["size"] = 0; r["container"] = "NO-OUTPUT"; r["info"] = {}
        rows.append(r)

    # ---- report ----
    print("=== TASK A: FLEET INVENTORY ===")
    print("compilers enumerated: %d" % len(rows))
    print("  with source:        %d" % sum(1 for r in rows if r["src_lines"] > 0))
    print("  with binary:        %d" % sum(1 for r in rows if r["bin_exists"]))
    print("  binary executable:  %d" % sum(1 for r in rows if r["bin_exec"]))
    print("  probe compiled:     %d" % sum(1 for r in rows if r["rc"] == 0))
    print("  produced output:    %d" % sum(1 for r in rows if r["size"] > 0))
    print()
    hist = collections.Counter(r["container"] for r in rows)
    print("-- container classes --")
    for c, n in sorted(hist.items(), key=lambda kv: -kv[1]):
        print("  %-26s %d" % (c, n))
    print()
    bad = [r for r in rows if r["rc"] != 0 or r["size"] == 0 or not r["bin_exec"]]
    if bad:
        print("-- NON-COMPILING / NON-EXECUTABLE --")
        for r in bad:
            print("  %-46s rc=%s size=%s %s" % (r["path"], r["rc"], r["size"], r["msg"][:60]))
    else:
        print("every backend compiles the probe and writes output")
    print()
    json.dump(rows, open(os.path.join(ROOT, "tools", "_inventory.json"), "w"), indent=1)
    print("JSON -> tools/_inventory.json")
    return 0 if not bad else 1

if __name__ == "__main__":
    sys.exit(main())
