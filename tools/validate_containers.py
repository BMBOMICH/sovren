#!/usr/bin/env python3
"""validate_containers.py - Task A: structural validation of the non-ELF
container families the fleet produces.

Covers PE/COFF, Mach-O, ar(1) static archives, OMF166, XCOFF64, Plan 9 a.out,
ZIP/HAP, Fuchsia FAR and the raw-image backends.

Same verdict vocabulary as validate_elf.py:
  COMPLETE - parses and every structure the format requires is present/consistent
  PARTIAL  - parses but a required structure is missing or inconsistent
  STUB     - header only, or nothing loadable
"""
import json, os, struct, subprocess, sys, collections, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUD = "/tmp/audit_a"

def art(rel):
    return os.path.join(AUD, rel.replace("/", "_") + ".bin")

def rd(rel):
    return open(art(rel), "rb").read()

# ---------------------------------------------------------------- PE / COFF
def v_pe(rel):
    d = rd(rel); p = []
    if d[:2] != b"MZ":
        return "STUB", ["no MZ signature"], {}
    e_lfanew = struct.unpack_from("<I", d, 0x3c)[0]
    if e_lfanew + 24 > len(d):
        return "STUB", ["e_lfanew=%d past EOF" % e_lfanew], {}
    if d[e_lfanew:e_lfanew+4] != b"PE\x00\x00":
        return "PARTIAL", ["no PE\\0\\0 at e_lfanew=%d" % e_lfanew], {}
    f = e_lfanew + 4
    mach, nsec, tds, ptst, nsym, opthsz, chars = struct.unpack_from("<HHIIIHH", d, f)
    if f + 20 + opthsz > len(d):
        return "PARTIAL", ["optional header past EOF"], {}
    o = f + 20
    info = {"machine": hex(mach), "nsec": nsec, "opthsz": opthsz, "chars": hex(chars)}
    if opthsz:
        magic = struct.unpack_from("<H", d, o)[0]
        info["opt_magic"] = hex(magic)
        if magic == 0x10b:
            (maj, minr, szcode, szinit, szuninit, aep, basecode, basedata,
             imgbase, secalign, filealign) = struct.unpack_from("<BBIIIIIIIII", d, o+2)
            info["pe32plus"] = False
            numrva = struct.unpack_from("<I", d, o+92)[0]
            dd = o + 96
        elif magic == 0x20b:
            (maj, minr, szcode, szinit, szuninit, aep, basecode,
             imgbase, secalign, filealign) = struct.unpack_from("<BBIIIIIQII", d, o+2)
            info["pe32plus"] = True
            numrva = struct.unpack_from("<I", d, o+108)[0]
            dd = o + 112
        else:
            return "PARTIAL", ["bad optional magic %s" % hex(magic)], info
        info["entry"] = hex(aep); info["imagebase"] = hex(imgbase)
        info["numrva"] = numrva
        # A managed (.NET/CIL) assembly keeps its entry point in the CLR
        # header (data directory 14), so AEP==0 is correct when DD[14] exists.
        clr_rva = struct.unpack_from("<I", d, dd + 8 * 14)[0] if numrva > 14 else 0
        info["clr_dir"] = clr_rva
        if aep == 0 and not clr_rva:
            p.append("AddressOfEntryPoint is 0 and no CLR header")
        if imgbase == 0:
            p.append("ImageBase is 0")
        if numrva > 16:
            p.append("NumberOfRvaAndSizes=%d > 16" % numrva)
        if dd + 8 * min(numrva, 16) > len(d):
            p.append("data directories past EOF")
    # section table
    st = o + opthsz
    if st + 40 * nsec > len(d):
        p.append("section table past EOF (st=%d nsec=%d len=%d)" % (st, nsec, len(d)))
        return "PARTIAL", p, info
    secs = []
    for i in range(nsec):
        so = st + 40 * i
        nm = d[so:so+8].rstrip(b"\x00").decode("latin1")
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, so+8)
        secs.append((nm, vsz, va, rsz, raw))
        if rsz and raw + rsz > len(d):
            p.append("section %s raw range past EOF (raw=%d rsz=%d len=%d)" % (nm, raw, rsz, len(d)))
    info["sections"] = [s[0] for s in secs]
    if not any(s[0] == ".text" for s in secs):
        p.append("no .text section")
    if not p and nsec:
        return "COMPLETE", [], info
    return ("PARTIAL" if p else "STUB"), p, info

# ---------------------------------------------------------------- Mach-O
def v_macho(rel):
    d = rd(rel); p = []
    magic = struct.unpack_from("<I", d, 0)[0]
    if magic not in (0xfeedface, 0xfeedfacf, 0xcefaedfe, 0xcffaedfe):
        return "STUB", ["bad magic %s" % hex(magic)], {}
    be = magic in (0xcefaedfe, 0xcffaedfe)
    en = ">" if be else "<"
    is64 = magic in (0xfeedfacf, 0xcffaedfe)
    hdrsz = 32 if is64 else 28
    if is64:
        cputype, cpusub, filetype, ncmds, sizeofcmds, flags = struct.unpack_from(
            en + "iiIIII", d, 4)
    else:
        cputype, cpusub, filetype, ncmds, sizeofcmds, flags = struct.unpack_from(
            en + "iiIIII", d, 4)
    info = {"magic": hex(magic), "cputype": hex(cputype & 0xffffffff),
            "filetype": filetype, "ncmds": ncmds, "sizeofcmds": sizeofcmds}
    if filetype == 0:
        p.append("filetype is OBJECT(0)")
    o = hdrsz
    end = hdrsz + sizeofcmds
    if end > len(d):
        p.append("load commands past EOF (end=%d len=%d)" % (end, len(d)))
        return "PARTIAL", p, info
    cmds = []
    for _ in range(ncmds):
        if o + 8 > len(d):
            p.append("load command header past EOF"); break
        cmd, cmdsize = struct.unpack_from(en + "II", d, o)
        cmds.append((cmd, cmdsize))
        if cmdsize < 8 or o + cmdsize > len(d):
            p.append("load command cmd=%d size=%d invalid/past EOF" % (cmd, cmdsize)); break
        o += cmdsize
    info["cmds"] = [hex(c[0]) for c in cmds]
    LC = {0x1:"SEGMENT", 0x2:"SYMTAB", 0xb:"DYLIB", 0xc:"LOAD_DYLIB",
          0x1d:"CODE_SIGNATURE", 0x1b:"DYSYMTAB", 0x19:"FUNCTION_STARTS",
          0x1e:"DATA_IN_CODE", 0x21:"ENCRYPTION_INFO", 0x22:"DYLD_INFO",
          0x80000022:"DYLD_INFO_ONLY", 0x80000028:"MAIN", 0x8000001c:"ID_DYLIB",
          0x5:"UNIXTHREAD", 0x1f:"SOURCE_VERSION", 0x2a:"BUILD_VERSION",
          0x80000034:"LINKER_OPTION", 0x32:"LC_FILESET_ENTRY"}
    names = [LC.get(c[0], hex(c[0])) for c in cmds]
    info["cmdnames"] = names
    has_seg = any(c[0] in (0x1, 0x19) for c in cmds)
    if not has_seg:
        p.append("no LC_SEGMENT load command")
    if not p:
        return "COMPLETE", [], info
    return "PARTIAL", p, info

# ---------------------------------------------------------------- ar archive
def v_ar(rel):
    d = rd(rel); p = []
    if d[:8] != b"!<arch>\n":
        return "STUB", ["no ar magic"], {}
    o = 8; members = []
    while o + 60 <= len(d):
        hdr = d[o:o+60]
        if hdr[58:60] not in (b"`\n", b"\n"):
            break
        try:
            name = hdr[0:16].rstrip().decode("latin1")
            size = int(hdr[48:58].rstrip())
        except Exception:
            break
        members.append(name)
        if o + 60 + size > len(d):
            p.append("member %s past EOF" % name); break
        o += 60 + size
        if size % 2: o += 1
    info = {"members": members}
    if not members:
        p.append("no archive members")
    if not any(m in ("/", "//") or m.endswith(".o") or m.startswith("#1/") for m in members):
        p.append("no symbol/string-table member")
    return ("COMPLETE" if not p else "PARTIAL"), p, info

# ---------------------------------------------------------------- OMF166
def v_omf166(rel):
    d = rd(rel); p = []
    o = 0; recs = []
    while o + 4 <= len(d):
        rt = d[o]; rl = d[o+1] | (d[o+2] << 8)
        if o + 3 + rl > len(d):
            p.append("record at %d truncated (need %d have %d)" % (o, 3+rl, len(d)-o)); break
        s = sum(d[o:o+3+rl]) & 0xff
        if s != 0:
            p.append("record %d (type %02x) checksum sum=%d != 0" % (len(recs), rt, s))
        recs.append(rt)
        o += 3 + rl
    info = {"records": [hex(x) for x in recs], "end": o}
    if o != len(d):
        p.append("trailing bytes: walked %d of %d" % (o, len(d)))
    if not recs:
        p.append("no records")
    elif recs[0] != 0x80:
        p.append("first record is %02x, expected THEADR 0x80" % recs[0])
    if recs and recs[-1] != 0x8a:
        p.append("last record is %02x, expected MODEND 0x8a" % recs[-1])
    return ("COMPLETE" if not p else "PARTIAL"), p, info

# ---------------------------------------------------------------- XCOFF64
def v_xcoff(rel):
    d = rd(rel); p = []
    magic = struct.unpack_from(">H", d, 0)[0]
    info = {"magic": hex(magic)}
    if magic != 0x01f7:
        p.append("magic %s != 0x01f7 (XCOFF64)" % hex(magic)); return "STUB", p, info
    nscns = struct.unpack_from(">H", d, 18)[0]
    opthdr = struct.unpack_from(">H", d, 16)[0]
    info["nscns"] = nscns; info["opthdr"] = opthdr
    so = 24 + opthdr
    if so + 72 * nscns > len(d):
        p.append("section headers past EOF (so=%d nsec=%d len=%d)" % (so, nscns, len(d)))
        return "PARTIAL", p, info
    names = []
    for i in range(nscns):
        h = so + 72 * i
        nm = d[h:h+8].rstrip(b"\x00").decode("latin1")
        sptr, ssize = struct.unpack_from(">II", d, h+20)
        names.append(nm)
        if ssize and sptr + ssize > len(d):
            p.append("section %s data past EOF (ptr=%d size=%d len=%d)" % (nm, sptr, ssize, len(d)))
    info["sections"] = names
    return ("COMPLETE" if not p else "PARTIAL"), p, info

# ---------------------------------------------------------------- Plan 9
def v_plan9(rel):
    d = rd(rel); p = []
    if len(d) < 32:
        return "STUB", ["shorter than the 32-byte Exec header"], {}
    f = struct.unpack_from(">IIIIIIII", d, 0)
    info = {"magic": hex(f[0]), "text": f[1], "data": f[2], "bss": f[3],
            "syms": f[4], "entry": f[5], "spsz": f[6], "txtsz": f[7]}
    if f[0] != 0x8a97:
        p.append("magic %s != 0x8A97 (S_MAGIC)" % hex(f[0]))
    tot = 32 + f[1] + f[2] + f[4]
    if tot > len(d):
        p.append("declared text+data+syms (%d) exceeds file size (%d)" % (tot, len(d)))
    if f[5] == 0:
        p.append("entry point is 0")
    return ("COMPLETE" if not p else "PARTIAL"), p, info

# ---------------------------------------------------------------- ZIP / HAP
def v_zip(rel):
    d = rd(rel); p = []
    o = 0; n = 0
    while d[o:o+4] == b"PK\x03\x04" and o + 30 <= len(d):
        (ver, flg, meth, mt, md, crc, csz, usz, nlen, elen) = struct.unpack_from(
            "<HHHHHIIIHH", d, o+4)
        if o + 30 + nlen + elen + csz > len(d):
            p.append("local entry %d past EOF" % n); break
        n += 1
        o += 30 + nlen + elen + csz
    cdo = d.rfind(b"PK\x01\x02")
    if cdo < 0:
        p.append("no central directory (PK\\x01\\x02)")
        return "PARTIAL", p, {"entries": n}
    eocd = d.rfind(b"PK\x05\x06")
    if eocd < 0:
        p.append("no EOCD (PK\\x05\\x06)")
        return "PARTIAL", p, {"entries": n}
    (_, dsk, cd, ntot, cdsz, cdoff, clen) = struct.unpack_from("<HHHHIIH", d, eocd+4)
    info = {"entries": n, "cd_entries": ntot, "cd_size": cdsz, "cd_off": cdoff}
    if cdoff + cdsz > len(d):
        p.append("central directory past EOF (off=%d size=%d len=%d)" % (cdoff, cdsz, len(d)))
    if ntot != n:
        p.append("local entries=%d but EOCD says %d" % (n, ntot))
    if eocd + 22 + clen > len(d):
        p.append("EOCD comment past EOF")
    return ("COMPLETE" if not p else "PARTIAL"), p, info

# ---------------------------------------------------------------- FAR
def v_far(rel):
    d = rd(rel); p = []
    if d[:8] != b"\xc8\xbf\x0b\x48\xad\xab\xc5\x11":
        return "STUB", ["bad FAR index magic"], {}
    elen = struct.unpack_from("<Q", d, 8)[0]
    n = elen // 24          # the field is a byte count, not an entry count
    info = {"entries": n, "entries_len": elen}
    o = 16
    for i in range(n):
        if o + 24 > len(d):
            p.append("index entry %d past EOF" % i); break
        (typ, off, ln) = struct.unpack_from("<QQQ", d, o)
        if off + ln > len(d):
            p.append("index entry %d content past EOF (off=%d len=%d file=%d)" % (i, off, ln, len(d)))
        o += 24
    return ("COMPLETE" if not p else "PARTIAL"), p, info

# ---------------------------------------------------------------- DEX
def v_dex(rel):
    d = rd(rel); p = []
    if d[:4] != b"dex\n":
        return "STUB", ["bad DEX magic"], {}
    import zlib, hashlib
    fsz = struct.unpack_from("<I", d, 32)[0]
    hsz = struct.unpack_from("<I", d, 36)[0]
    endian = struct.unpack_from("<I", d, 40)[0]
    info = {"file_size": fsz, "header_size": hsz, "endian_tag": hex(endian)}
    if fsz != len(d):
        p.append("header file_size=%d but artifact is %d bytes" % (fsz, len(d)))
    if endian != 0x12345678:
        p.append("endian_tag %s != 0x12345678" % hex(endian))
    # checksum = adler32 of everything after byte 8
    want = struct.unpack_from("<I", d, 8)[0]
    got = zlib.adler32(d[12:]) & 0xffffffff
    info["adler32"] = "match" if want == got else "MISMATCH"
    if want != got:
        p.append("Adler-32 mismatch (stored %08x computed %08x)" % (want, got))
    wsha = d[12:32]
    gsha = hashlib.sha1(d[32:]).digest()
    info["sha1"] = "match" if wsha == gsha else "MISMATCH"
    if wsha != gsha:
        p.append("SHA-1 mismatch")
    return ("COMPLETE" if not p else "PARTIAL"), p, info

# ---------------------------------------------------------------- HP-UX SOM
def v_som(rel):
    """HP-UX SOM, validated against the rules the Linux kernel's own
    fs/binfmt_som.c check_som_header() applies."""
    d = rd(rel); p = []
    if len(d) < 128:
        return "STUB", ["shorter than the 128-byte SOM header"], {}
    sid = struct.unpack_from(">H", d, 0)[0]
    amagic = struct.unpack_from(">H", d, 2)[0]
    ver = struct.unpack_from(">I", d, 4)[0]
    aux_loc = struct.unpack_from(">I", d, 28)[0]
    aux_sz = struct.unpack_from(">I", d, 32)[0]
    som_len = struct.unpack_from(">I", d, 36)[0]
    sp_loc = struct.unpack_from(">I", d, 44)[0]
    sp_tot = struct.unpack_from(">I", d, 48)[0]
    ss_loc = struct.unpack_from(">I", d, 52)[0]
    ss_tot = struct.unpack_from(">I", d, 56)[0]
    str_loc = struct.unpack_from(">I", d, 68)[0]
    str_sz = struct.unpack_from(">I", d, 72)[0]
    info = {"system_id": hex(sid), "a_magic": hex(amagic), "version_id": ver,
            "som_length": som_len, "space_total": sp_tot, "subspace_total": ss_tot}
    if sid not in (0x20b, 0x210, 0x214):
        p.append("system_id %s not in {0x20b,0x210,0x214}" % hex(sid))
    if amagic not in (0x107, 0x108, 0x10b):
        p.append("a_magic %s not in {0x107,0x108,0x10b}" % hex(amagic))
    if ver not in (85082112, 87102412):
        p.append("version_id %d not in {85082112,87102412}" % ver)
    x = 0
    for i in range(32):
        x ^= struct.unpack_from(">I", d, i * 4)[0]
    if x != 0:
        p.append("header XOR checksum is %d, must be 0" % x)
    if som_len != len(d):
        p.append("som_length=%d but file is %d bytes" % (som_len, len(d)))
    if aux_loc + aux_sz > som_len:
        p.append("aux header range past som_length")
    if sp_loc + 36 * sp_tot > som_len:
        p.append("space dictionary past som_length")
    if ss_loc + 40 * ss_tot > som_len:
        p.append("subspace dictionary past som_length")
    if str_loc + str_sz > som_len:
        p.append("space strings past som_length")
    if sp_tot == 0 or ss_tot == 0:
        p.append("no spaces/subspaces declared")
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- COFF object
def v_coff(rel):
    d = rd(rel); p = []
    if len(d) < 20:
        return "STUB", ["shorter than the 20-byte COFF file header"], {}
    mach, nsec, tds, symptr, nsym, optsz, chars = struct.unpack_from("<HHIIIHH", d, 0)
    info = {"machine": hex(mach), "nsec": nsec, "optsz": optsz}
    if mach not in (0x14c, 0x8664, 0x1c0, 0xaa64, 0x1c4):
        p.append("unusual machine type %s" % hex(mach))
    if nsec == 0:
        p.append("no sections")
    if symptr and symptr + 18 * nsym > len(d):
        p.append("symbol table past EOF")
    st = 20 + optsz
    if st + 40 * nsec > len(d):
        p.append("section table past EOF (st=%d nsec=%d len=%d)" % (st, nsec, len(d)))
        return "PARTIAL", p, info
    names = []
    for i in range(nsec):
        so = st + 40 * i
        nm = d[so:so+8].rstrip(b"\x00").decode("latin1")
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, so + 8)
        names.append(nm)
        if rsz and raw + rsz > len(d):
            p.append("section %s raw data past EOF (raw=%d size=%d len=%d)" % (nm, raw, rsz, len(d)))
    info["sections"] = names
    if not any(n == ".text" for n in names):
        p.append("no .text section")
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- Multiboot
def v_multiboot(rel):
    d = rd(rel); p = []
    magic = struct.unpack_from("<I", d, 0)[0]
    flags = struct.unpack_from("<I", d, 4)[0]
    csum = struct.unpack_from("<I", d, 8)[0]
    info = {"magic": hex(magic), "flags": hex(flags), "checksum": hex(csum)}
    if magic != 0x1BADB002:
        p.append("magic %s != 0x1BADB002" % hex(magic))
    if (magic + flags + csum) & 0xffffffff != 0:
        p.append("magic+flags+checksum != 0 (mod 2^32)")
    if flags & 0x10000:
        for nm, off in (("header_addr", 12), ("load_addr", 16),
                        ("load_end_addr", 20), ("bss_end_addr", 24), ("entry", 28)):
            if off + 4 > len(d):
                p.append("%s field past EOF" % nm); break
            info[nm] = hex(struct.unpack_from("<I", d, off)[0])
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- WebAssembly
def v_wasm(rel):
    d = rd(rel); p = []
    if d[:4] != b"\x00asm":
        return "STUB", ["bad wasm magic"], {}
    # The component-model binary format uses a 2-byte version/layer marker
    # (0x0d 0x00) after the magic; core modules use a 4-byte version == 1.
    if d[4:6] == b"\x0d\x00":
        info = {"kind": "component", "sections": []}
        if len(d) <= 6:
            p.append("component body is empty")
        return ("COMPLETE" if not p else "PARTIAL"), p, info
    ver = struct.unpack_from("<I", d, 4)[0]
    info = {"version": ver, "kind": "core", "sections": []}
    if ver != 1:
        p.append("wasm version %d != 1" % ver)
    o = 8
    SECN = {0:"custom",1:"type",2:"import",3:"function",4:"table",5:"memory",
            6:"global",7:"export",8:"start",9:"elem",10:"code",11:"data",12:"datacount"}
    while o < len(d):
        sid = d[o]; o += 1
        # uleb128 section size
        sz, sh = 0, 0
        while True:
            if o >= len(d):
                p.append("truncated section-size LEB128"); return "PARTIAL", p, info
            b = d[o]; o += 1
            sz |= (b & 0x7f) << sh; sh += 7
            if not (b & 0x80): break
        if o + sz > len(d):
            p.append("section %s size %d past EOF" % (SECN.get(sid, str(sid)), sz))
            return "PARTIAL", p, info
        info["sections"].append(SECN.get(sid, str(sid)))
        o += sz
    if o != len(d):
        p.append("section walk ended at %d of %d bytes" % (o, len(d)))
    if "code" not in info["sections"]:
        p.append("no code section")
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- text-ish
TEXTHINT = (b"<!doctype", b"<html", b"const ", b"function ", b"let ", b"var ",
            b"; ModuleID", b"target", b"define ", b"declare ", b"@", b"section",
            b"#version", b"struct ", b"namespace", b"using ",
            b"structuredbuffer", b"cbuffer", b"sampler", b"float4",   # HLSL
            b".kernel", b".platform", b".arg", b".text",              # Intel Xe asm
            b".globl", b"mov64", b"r0,", b"# ", b".text")             # eBPF asm

def v_textish(rel):
    d = rd(rel); p = []
    try:
        t = d.decode("utf-8")
    except Exception:
        return "PARTIAL", ["not valid UTF-8"], {"size": len(d)}
    if len(t.strip()) == 0:
        p.append("empty output")
    if not any(h in t[:400].lower().encode() for h in TEXTHINT):
        p.append("no recognisable source/harness prefix")
    return ("COMPLETE" if not p else "PARTIAL"), p, {"size": len(d), "lines": t.count("\n") + 1}


# ---------------------------------------------------------------- bare images
def v_bare(rel):
    """A bare-metal raw image: non-empty, and (for the Cortex-M/Thumb family)
    the initial stack pointer and reset vector must both be non-zero."""
    d = rd(rel); p = []
    if len(d) == 0:
        return "STUB", ["empty artifact"], {}
    info = {"size": len(d)}
    if "thumbv" in rel or "cortex-m" in rel:
        sp = struct.unpack_from("<I", d, 0)[0]
        rv = struct.unpack_from("<I", d, 4)[0]
        info["initial_sp"] = hex(sp); info["reset_vector"] = hex(rv)
        if sp == 0:
            p.append("initial stack pointer is 0")
        if rv == 0:
            p.append("reset vector is 0")
    return ("COMPLETE" if not p else "PARTIAL"), p, info



# ---------------------------------------------------------------- Intel HEX
def v_ihex(rel):
    d = rd(rel); p = []
    try:
        t = d.decode("ascii")
    except Exception:
        return "PARTIAL", ["not ASCII"], {}
    lines = [l for l in t.splitlines() if l.strip()]
    info = {"records": len(lines)}
    if not lines:
        return "STUB", ["no records"], info
    for i, l in enumerate(lines):
        if not l.startswith(":"):
            p.append("line %d does not start with ':'" % i); break
        try:
            b = bytes.fromhex(l[1:])
        except Exception:
            p.append("line %d is not hex" % i); break
        if sum(b) & 0xff != 0:
            p.append("line %d checksum: byte sum != 0 mod 256" % i); break
    if not lines[-1].upper().startswith(":00000001"):
        p.append("no EOF record (:00000001FF)")
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- S-record
def v_srec(rel):
    d = rd(rel); p = []
    try:
        t = d.decode("ascii")
    except Exception:
        return "PARTIAL", ["not ASCII"], {}
    lines = [l for l in t.splitlines() if l.strip()]
    info = {"records": len(lines)}
    if not lines:
        return "STUB", ["no records"], info
    for i, l in enumerate(lines):
        if not (l.startswith("S") and len(l) > 4):
            p.append("line %d is not an S-record" % i); break
        try:
            b = bytes.fromhex(l[2:])
        except Exception:
            p.append("line %d is not hex" % i); break
        # count + address + data + checksum must sum to 0xff
        if (sum(b) & 0xff) != 0xff:
            p.append("line %d checksum: sum != 0xff" % i); break
    if not lines[-1].upper().startswith("S9") and not lines[-1].upper().startswith("S8"):
        p.append("no S8/S9 terminator record")
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- UF2
def v_uf2(rel):
    d = rd(rel); p = []
    if len(d) % 512:
        p.append("file size %d is not a multiple of 512" % len(d))
    nb = len(d) // 512
    info = {"blocks": nb}
    if nb == 0:
        return "STUB", ["no blocks"], info
    for b in range(nb):
        o = b * 512
        m0, m1, flg, tgt, psz, bno, nblk, fam = struct.unpack_from("<IIIIIIII", d, o)
        end = struct.unpack_from("<I", d, o + 508)[0]
        if m0 != 0x0A324655:
            p.append("block %d magicStart0=%08x" % (b, m0)); break
        if m1 != 0x9E5D5157:
            p.append("block %d magicStart1=%08x" % (b, m1)); break
        if end != 0x0AB16F30:
            p.append("block %d magicEnd=%08x != 0x0AB16F30" % (b, end)); break
        if bno != b:
            p.append("block %d has blockNo=%d" % (b, bno)); break
        if psz > 476:
            p.append("block %d payloadSize=%d > 476" % (b, psz)); break
    info["numBlocks_field"] = struct.unpack_from("<I", d, 24)[0]
    if info["numBlocks_field"] != nb:
        p.append("numBlocks field %d != actual %d" % (info["numBlocks_field"], nb))
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- DfuSe
def v_dfuse(rel):
    d = rd(rel); p = []
    if d[:5] != b"DfuSe":
        return "STUB", ["missing 'DfuSe' signature"], {}
    info = {"prefix": "DfuSe", "size": len(d)}
    # DFU file suffix occupies the last 16 bytes
    if len(d) < 16 + 11:
        return "PARTIAL", ["too short for a DfuSe prefix and a DFU suffix"], info
    bcdDev, idProd, idVend, bcdDFU = struct.unpack_from("<HHHH", d, len(d) - 16)
    sig = d[len(d) - 8:len(d) - 5]
    blen = d[len(d) - 5]
    crc = struct.unpack_from("<I", d, len(d) - 4)[0]
    info.update({"bcdDevice": hex(bcdDev), "idProduct": hex(idProd),
                 "idVendor": hex(idVend), "bcdDFU": hex(bcdDFU),
                 "suffix_len": blen, "stored_crc": hex(crc)})
    if sig != b"UFD":
        p.append("DFU suffix signature %r != 'UFD'" % sig)
    if blen != 16:
        p.append("DFU suffix bLength=%d != 16" % blen)
    calc = zlib.crc32(d[:-4]) & 0xffffffff
    info["crc"] = "match" if calc == crc else "MISMATCH"
    if calc != crc:
        p.append("DFU suffix CRC32 mismatch (stored %08x computed %08x)" % (crc, calc))
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- SPIR-V
def v_spirv(rel):
    d = rd(rel); p = []
    if len(d) < 20:
        return "STUB", ["shorter than the 20-byte SPIR-V header"], {}
    magic, ver, gen, bound, schema = struct.unpack_from("<IIIII", d, 0)
    info = {"magic": hex(magic), "version": ver, "generator": gen,
            "bound": bound, "schema": schema}
    if magic != 0x07230203:
        p.append("magic %s != 0x07230203" % hex(magic))
    if ver == 0:
        p.append("version is 0")
    if bound == 0:
        p.append("bound is 0")
    if schema != 0:
        p.append("schema is %d, must be 0" % schema)
    if len(d) % 4:
        p.append("size %d is not a multiple of 4" % len(d))
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- MENUET64
def v_menuet(rel):
    d = rd(rel); p = []
    if len(d) < 48:
        return "STUB", ["shorter than the menuet64 header"], {}
    if d[:8] != b"MENUET64":
        return "STUB", ["magic %r != 'MENUET64'" % d[:8]], {}
    ver = struct.unpack_from("<I", d, 8)[0]
    start = struct.unpack_from("<Q", d, 16)[0]
    info = {"version": ver, "start": hex(start), "size": len(d)}
    if ver == 0:
        p.append("version is 0")
    if start >= len(d):
        p.append("start address 0x%x is past EOF (%d)" % (start, len(d)))
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- Metal pkg
def v_metal(rel):
    d = rd(rel); p = []
    # Two members of this family: MTLB (metal library) and AIR2 (Apple
    # Intermediate Representation).  Both share the u32 version + size layout.
    if d[:4] not in (b"MTLB", b"AIR2"):
        return "STUB", ["magic %r not in ('MTLB','AIR2')" % d[:4]], {}
    ver = struct.unpack_from("<I", d, 4)[0]
    declared = struct.unpack_from("<I", d, 12)[0]
    info = {"magic": d[:4].decode(), "version": ver,
            "declared_size": declared, "size": len(d)}
    if ver == 0:
        p.append("version is 0")
    if declared > len(d):
        p.append("declared size %d exceeds file size %d" % (declared, len(d)))
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- COM image
def v_com(rel):
    d = rd(rel); p = []
    if len(d) == 0:
        return "STUB", ["empty artifact"], {}
    info = {"size": len(d)}
    # a .COM image is loaded at CS:0100 and must fit in one segment
    if len(d) > 65280:
        p.append("image %d bytes exceeds the 65280-byte .COM limit" % len(d))
    return ("COMPLETE" if not p else "PARTIAL"), p, info


# ---------------------------------------------------------------- eBPF
def v_ebpf(rel):
    d = rd(rel); p = []
    if len(d) % 8:
        p.append("size %d is not a multiple of the 8-byte eBPF instruction" % len(d))
    info = {"size": len(d), "insns": len(d) // 8}
    if len(d) == 0:
        return "STUB", ["no instructions"], info
    op = d[0]
    info["first_opcode"] = hex(op)
    # every opcode's low 3 bits are the instruction class (0..7)
    if (op & 0x07) > 0x07:
        p.append("bad first opcode class")
    return ("COMPLETE" if not p else "PARTIAL"), p, info



# ---------------------------------------------------------------- raw images
RAW = {
    "compilers/6502": ("LDA #n (A9), BRK (00)", lambda d: d[:1] == b"\xa9" and d[-1:] == b"\x00"),
    "compilers/8051": ("MOV A,#n (74); SJMP . (80 FE)", lambda d: d[:1] == b"\x74" and d[-2:] == b"\x80\xfe"),
    "compilers/z80": ("LD A,n (3E); HALT (76)", lambda d: d[:1] == b"\x3e" and d[-1:] == b"\x76"),
    "compilers/ez80": ("LD A,n (3E); HALT (76)", lambda d: d[:1] == b"\x3e" and d[-1:] == b"\x76"),
    "compilers/pic16": ("MOVLW n (n 30); ...", lambda d: d[1:3] == b"\x30\x00"),
    "compilers/pic18": ("MOVLW n (0E 00 00)", lambda d: d[1:4] == b"\x0e\x00\x00"),
    "compilers/evm": ("PUSH1 n (60); STOP (00)", lambda d: d[:1] == b"\x60" and d[-1:] == b"\x00"),
}

def v_raw(rel):
    d = rd(rel); p = []
    desc, chk = RAW.get(rel, (None, None))
    if chk is None:
        return "PARTIAL", ["no validator for this raw backend"], {"size": len(d)}
    if not chk(d):
        p.append("does not match the expected opcode shape (%s)" % desc)
    return ("COMPLETE" if not p else "PARTIAL"), p, {"size": len(d), "expect": desc}

def v_text(rel):
    d = rd(rel); p = []
    try:
        t = d.decode("utf-8")
    except Exception:
        return "PARTIAL", ["not valid UTF-8"], {"size": len(d)}
    if len(t.strip()) == 0:
        p.append("empty output")
    return ("COMPLETE" if not p else "PARTIAL"), p, {"size": len(d), "lines": t.count("\n") + 1}


def v_mz(rel):
    """A plain DOS MZ executable: no PE extension required."""
    d = rd(rel); p = []
    if d[:2] != b"MZ":
        return "STUB", ["no MZ signature"], {}
    e_cblp, e_cp, e_crlc, e_cparhdr = struct.unpack_from("<HHHH", d, 2)
    e_minalloc, e_maxalloc, e_ss, e_sp, e_csum, e_ip, e_cs, e_lfarlc, e_ovno = \
        struct.unpack_from("<HHHHHHHHH", d, 10)
    info = {"cblp": e_cblp, "cp": e_cp, "cparhdr": e_cparhdr,
            "ss": hex(e_ss), "sp": hex(e_sp), "ip": hex(e_ip), "cs": hex(e_cs)}
    if e_cparhdr == 0:
        p.append("e_cparhdr is 0")
    if e_cp == 0:
        p.append("e_cp (pages) is 0")
    # declared image size: full pages plus the bytes in the last page
    decl = e_cp * 512 + (e_cblp if 0 < e_cblp < 512 else 0)
    if decl > len(d) + 512:
        p.append("declared image %d bytes far exceeds file size %d" % (decl, len(d)))
    # The entry maps to file offset e_cparhdr*16 + CS*16 + IP.  CS:IP = 0:0 is
    # the normal case for a DOS EXE whose code starts at the load-module origin.
    entry_off = e_cparhdr * 16 + e_cs * 16 + e_ip
    info["entry_file_off"] = entry_off
    if entry_off >= len(d):
        p.append("entry CS:IP=%04x:%04x maps to file offset %d, past EOF (%d)"
                 % (e_cs, e_ip, entry_off, len(d)))
    return ("COMPLETE" if not p else "PARTIAL"), p, info

def v_class(rel):
    """A JVM .class file."""
    d = rd(rel); p = []
    if d[:4] != b"\xca\xfe\xba\xbe":
        return "STUB", ["bad class magic"], {}
    minor, major = struct.unpack_from(">HH", d, 4)
    cpc = struct.unpack_from(">H", d, 8)[0]
    acc, this_c, super_c = struct.unpack_from(">HHH", d, 10)
    info = {"major": major, "minor": minor, "cp_count": cpc,
            "this_class": this_c, "super_class": super_c}
    if major < 45:
        p.append("class file version %d.%d is below 45" % (major, minor))
    if cpc == 0:
        p.append("constant_pool_count is 0")
    if this_c == 0:
        p.append("this_class is 0")
    if super_c == 0 and this_c != 0:
        p.append("super_class is 0 (only java.lang.Object may omit it)")
    return ("COMPLETE" if not p else "PARTIAL"), p, info


VALIDATORS = [
    ("PE/COFF", v_pe), ("Mach-O", v_macho),
]


def main():
    rows = json.load(open(os.path.join(ROOT, "tools", "_inventory.json")))
    out = []
    tally = collections.Counter()
    for r in rows:
        rel = r["path"]; c = r["container"]
        v, p, info = None, None, None
        if c in ("PE/COFF",):
            dd = rd(rel)
            if dd[:2] == b"MZ" and dd[struct.unpack_from("<I", dd, 0x3c)[0]:
                                        struct.unpack_from("<I", dd, 0x3c)[0]+4] != b"PE\x00\x00":
                v, p, info = v_mz(rel)
            else:
                v, p, info = v_pe(rel)
        elif c == "Mach-O-fat/JVM-class":
            v, p, info = v_class(rel)
        elif c in ("Mach-O", "Mach-O-fat/JVM-class"):
            v, p, info = v_macho(rel)
        elif rel == "compilers/linux/static-archive":
            v, p, info = v_ar(rel)
        elif c == "OMF166":
            v, p, info = v_omf166(rel)
        elif c == "XCOFF64":
            v, p, info = v_xcoff(rel)
        elif c == "Plan9-a.out":
            v, p, info = v_plan9(rel)
        elif c == "ZIP/HAP":
            v, p, info = v_zip(rel)
        elif c == "Fuchsia-FAR":
            v, p, info = v_far(rel)
        elif c == "Dalvik-DEX":
            v, p, info = v_dex(rel)
        elif rel in RAW:
            v, p, info = v_raw(rel)
        elif c == "HP-UX-SOM":
            v, p, info = v_som(rel)
        elif rel == "compilers/windows/coff-object":
            v, p, info = v_coff(rel)
        elif rel == "compilers/boot/multiboot":
            v, p, info = v_multiboot(rel)
        elif c == "WebAssembly":
            v, p, info = v_wasm(rel)
        elif c in ("binary/other",) and rel.startswith("compilers/webassembly/"):
            v, p, info = v_textish(rel)
        elif c == "binary/other" and rel.startswith("compilers/firmware/"):
            v, p, info = v_bare(rel)
        elif c == "Intel-HEX":
            v, p, info = v_ihex(rel)
        elif c == "S-record":
            v, p, info = v_srec(rel)
        elif c == "UF2":
            v, p, info = v_uf2(rel)
        elif c == "DfuSe":
            v, p, info = v_dfuse(rel)
        elif c == "SPIR-V":
            v, p, info = v_spirv(rel)
        elif c == "MENUET64":
            v, p, info = v_menuet(rel)
        elif c == "Apple/Metal-package":
            v, p, info = v_metal(rel)
        elif rel == "compilers/dos/com-image":
            v, p, info = v_com(rel)
        elif c == "binary/other":
            v, p, info = v_textish(rel)
        elif c in ("C-source", "JS/TS-source", "IL-source", "GLSL", "PTX",
                   "SPIR-V-text", "WGSL", "HLSL", "MSL", "WAT", "C#-source"):
            v, p, info = v_text(rel)
        if v is None:
            continue
        tally[v] += 1
        out.append({"path": rel, "container": c, "verdict": v,
                    "problems": p, "info": info})
    print("=== TASK A: NON-ELF CONTAINER VALIDATION ===")
    print("artifacts validated: %d" % len(out))
    for k in ("COMPLETE", "PARTIAL", "STUB"):
        print("  %-10s %d" % (k, tally[k]))
    print()
    bad = [o for o in out if o["verdict"] != "COMPLETE"]
    if bad:
        print("-- NOT COMPLETE --")
        for o in bad:
            print("  %-52s [%s] %s" % (o["path"], o["verdict"], o["container"]))
            for x in o["problems"][:4]:
                print("      - %s" % x)
    else:
        print("every validated container is structurally complete")
    json.dump(out, open(os.path.join(ROOT, "tools", "_containers.json"), "w"), indent=1)
    print("\nJSON -> tools/_containers.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
