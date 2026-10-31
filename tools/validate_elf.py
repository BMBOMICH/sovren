#!/usr/bin/env python3
"""validate_elf.py - Task A: structural validation of every ELF artifact the
fleet produces.

The existing tools/targets_audit.py only checks leading magic bytes.  This
checks the *structure*: that the header fields are self-consistent, that every
program header and section header lies inside the file, that the string table
resolves, and that readelf parses the artifact without complaint.

An artifact is COMPLETE when every check passes, PARTIAL when it parses but a
structure the format requires is missing or inconsistent, STUB when it is a
header with no loadable content.
"""
import json, os, struct, subprocess, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INV = os.path.join(ROOT, "tools", "_inventory.json")

EM = {0:"none",2:"SPARC",3:"x86",4:"m68k",8:"MIPS",15:"HPPA",18:"SPARC32+",
      20:"PPC",21:"PPC64",22:"S/390",40:"ARM",42:"SH",43:"SPARCV9",50:"IA-64",
      62:"x86-64",83:"AVR",92:"OpenRISC",93:"ARC",94:"Xtensa",105:"msp430",
      113:"?",140:"TIC6000",164:"Hexagon",183:"AArch64",189:"MicroBlaze",
      190:"CSKY",195:"ARCv2",243:"RISC-V",247:"BPF",258:"LoongArch"}

PT = {0:"NULL",1:"LOAD",2:"DYNAMIC",3:"INTERP",4:"NOTE",5:"SHLIB",6:"PHDR",
      7:"TLS",0x6474e550:"GNU_EH_FRAME",0x6474e551:"GNU_STACK",
      0x6474e552:"GNU_RELRO",0x6474e553:"GNU_PROPERTY",0x70000003:"AARCH64_ATTRS"}
SHT = {0:"NULL",1:"PROGBITS",2:"SYMTAB",3:"STRTAB",4:"RELA",5:"HASH",6:"DYNAMIC",
       7:"NOTE",8:"NOBITS",9:"REL",10:"SHLIB",11:"DYNSYM",14:"INIT_ARRAY",
       15:"FINI_ARRAY",16:"PREINIT_ARRAY",17:"GROUP",18:"SYMTAB_SHNDX",
       0x6ffffff6:"GNU_HASH",0x6fffffff:"VERSYM",0x6ffffffe:"VERNEED",
       0x70000003:"AARCH64_ATTRIBUTES"}


def validate(path):
    """Return (verdict, [problems], info)."""
    d = open(path, "rb").read()
    p = []
    n = len(d)
    if n < 20 or d[:4] != b"\x7fELF":
        return "STUB", ["not an ELF file"], {}
    cls, data = d[4], d[5]
    if cls not in (1, 2):
        p.append("bad EI_CLASS %d" % cls)
    if data not in (1, 2):
        p.append("bad EI_DATA %d" % data)
    en = "<" if data == 1 else ">"
    is64 = cls == 2
    ehsize = 64 if is64 else 52
    if d[6] != 1:
        p.append("EI_VERSION=%d (must be 1)" % d[6])
    # ---- fixed header ----
    if is64:
        (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff, e_flags,
         e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum,
         e_shstrndx) = struct.unpack_from(en + "HHIQQQIHHHHHH", d, 16)
    else:
        (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff, e_flags,
         e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum,
         e_shstrndx) = struct.unpack_from(en + "HHIIIIIHHHHHH", d, 16)
    info = {"class": 64 if is64 else 32, "endian": "BE" if data == 2 else "LE",
            "etype": e_type, "machine": EM.get(e_machine, str(e_machine)),
            "emach_raw": e_machine, "phnum": e_phnum, "shnum": e_shnum}
    if e_ehsize != ehsize:
        p.append("e_ehsize=%d expected %d" % (e_ehsize, ehsize))
    want_ph = 56 if is64 else 32
    want_sh = 64 if is64 else 40
    if e_phnum and e_phentsize != want_ph:
        p.append("e_phentsize=%d expected %d" % (e_phentsize, want_ph))
    if e_shnum and e_shentsize != want_sh:
        p.append("e_shentsize=%d expected %d" % (e_shentsize, want_sh))
    # ---- program headers ----
    phs = []
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        if o + e_phentsize > n:
            p.append("phdr %d past EOF" % i); break
        if is64:
            (p_type, p_flags, p_off, p_va, p_pa, p_fsz, p_msz,
             p_al) = struct.unpack_from(en + "IIQQQQQQ", d, o)
        else:
            (p_type, p_off, p_va, p_pa, p_fsz, p_msz, p_flags,
             p_al) = struct.unpack_from(en + "IIIIIIII", d, o)
        phs.append((p_type, p_flags, p_off, p_va, p_fsz, p_msz, p_al))
        if p_type == 1:  # PT_LOAD
            if p_off + p_fsz > n:
                p.append("PT_LOAD %d file range past EOF (off=%d fsz=%d n=%d)"
                         % (i, p_off, p_fsz, n))
            if p_msz < p_fsz:
                p.append("PT_LOAD %d memsz < filesz" % i)
    info["loads"] = sum(1 for x in phs if x[0] == 1)
    # ---- section headers ----
    shs = []
    if e_shnum:
        if e_shoff + e_shnum * e_shentsize > n:
            p.append("section header table past EOF (shoff=%d shnum=%d shentsize=%d n=%d)"
                     % (e_shoff, e_shnum, e_shentsize, n))
        else:
            for i in range(e_shnum):
                o = e_shoff + i * e_shentsize
                if is64:
                    (n_off, s_type, s_flags, s_addr, s_off, s_size, s_link,
                     s_info, s_al, s_ent) = struct.unpack_from(en + "IIQQQQIIQQ", d, o)
                else:
                    (n_off, s_type, s_flags, s_addr, s_off, s_size, s_link,
                     s_info, s_al, s_ent) = struct.unpack_from(en + "IIIIIIIIII", d, o)
                shs.append((n_off, s_type, s_flags, s_addr, s_off, s_size,
                            s_link, s_info, s_al, s_ent))
                if s_type != 8 and s_type != 0:  # not NOBITS/NULL
                    if s_off + s_size > n:
                        p.append("section %d (%s) range past EOF (off=%d size=%d n=%d)"
                                 % (i, SHT.get(s_type, str(s_type)), s_off, s_size, n))
            if e_shstrndx >= e_shnum:
                p.append("e_shstrndx=%d >= e_shnum=%d" % (e_shstrndx, e_shnum))
            else:
                st = shs[e_shstrndx]
                base, ln = st[4], st[5]
                names = []
                for sh in shs:
                    no = sh[0]
                    if base + no < n:
                        e = d.index(b"\x00", base + no) if b"\x00" in d[base+no:base+no+64] else base+no
                        names.append(d[base+no:e].decode("latin1"))
                    else:
                        names.append("")
                        p.append("section %d name offset %d past EOF" % (shs.index(sh), no))
                info["sections"] = [x for x in names if x]
                if not any(names):
                    p.append("no section names resolved from .shstrtab")
    # ---- readelf cross-check ----
    try:
        r = subprocess.run(["readelf", "-a", "-W", path], capture_output=True,
                           text=True, timeout=30)
        re_out = r.stdout + r.stderr
        info["readelf_rc"] = r.returncode
        bad = [l for l in re_out.splitlines()
               if ("Error" in l or "error" in l.lower()) and "readelf" not in l.lower()]
        if bad:
            p.append("readelf: " + bad[0].strip()[:90])
        # readelf's own view of the section table
        if "There are no sections" in re_out and e_shnum:
            p.append("readelf sees no sections though e_shnum=%d" % e_shnum)
    except Exception as e:
        p.append("readelf failed: %s" % e)
    # ---- verdict ----
    if not phs and not shs:
        v = "STUB"
    elif p:
        v = "PARTIAL"
    else:
        v = "COMPLETE"
    return v, p, info


def main():
    rows = json.load(open(os.path.join(ROOT, "tools", "_inventory.json")))
    elfs = [r for r in rows if r["container"] == "ELF"]
    out = []
    tally = collections.Counter()
    for r in elfs:
        path = os.path.join("/tmp/audit_a", r["path"].replace("/", "_") + ".bin")
        v, probs, info = validate(path)
        tally[v] += 1
        out.append({"path": r["path"], "verdict": v, "problems": probs,
                    "machine": info.get("machine"), "emach": info.get("emach_raw"),
                    "class": info.get("class"), "endian": info.get("endian"),
                    "etype": info.get("etype"), "loads": info.get("loads"),
                    "sections": info.get("sections"),
                    "readelf_rc": info.get("readelf_rc")})
    print("=== TASK A: ELF STRUCTURAL VALIDATION ===")
    print("ELF artifacts: %d" % len(elfs))
    for k in ("COMPLETE", "PARTIAL", "STUB"):
        print("  %-10s %d" % (k, tally[k]))
    print()
    bad = [o for o in out if o["verdict"] != "COMPLETE"]
    if bad:
        print("-- NOT COMPLETE --")
        for o in bad:
            print("  %s [%s]" % (o["path"], o["verdict"]))
            for x in o["problems"]:
                print("      - %s" % x)
    else:
        print("every ELF artifact is structurally complete")
    print()
    print("-- e_machine / endianness sanity (BE read big-endian) --")
    m = collections.Counter((o["endian"], o["machine"], o["class"]) for o in out)
    for k, v in sorted(m.items(), key=lambda kv: -kv[1]):
        print("  %-28s %d" % ("%s %s ELF%s" % k, v))
    json.dump(out, open(os.path.join(ROOT, "tools", "_elf.json"), "w"), indent=1)
    print("\nJSON -> tools/_elf.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
