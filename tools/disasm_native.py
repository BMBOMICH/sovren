#!/usr/bin/env python3
"""disasm_native.py - verify a hand-emitted native body before it ever runs.

The emit_nt_* bodies in library/cx86.sov are written as decimal byte lists. A
wrong byte there is invisible until something miscompiles. This takes that same
list and disassembles it, so the encoding is checked by reading, not by crashing.

Helper calls are not bytes in the list - the compiler emits them. They are given
placeholder widths so the listing lines up with the real function:

  calln("x")            -> 5 bytes (e8 rel32)
  load_glob("x")        -> 7 bytes (48 8b 05 rel32)   [PIE / RIP-relative]
  store_glob("x")       -> 7 bytes (48 89 05 rel32)
  jne()/js()/ja()/...   -> 6 bytes (0f 8x rel32), forward refs resolved here

Usage:
  python3 tools/disasm_native.py native.txt
  python3 tools/disasm_native.py native.txt --label general:35 slow:114

Input format: the byte list plus directives, one per line:
    86 82 87
    CALL length
    LOAD cut_used
    STORE cut_used
    JNE general
    LABEL general
"""
import re, subprocess, sys, tempfile, os

WIDTH = {"CALL": 5, "LOAD": 7, "STORE": 7}
JMP = {"JO": 0x80, "JNO": 0x81, "JB": 0x82, "JAE": 0x83, "JZ": 0x84, "JE": 0x84,
       "JNE": 0x85, "JNZ": 0x85, "JBE": 0x86, "JA": 0x87, "JS": 0x88, "JNS": 0x89,
       "JP": 0x8A, "JNP": 0x8B, "JL": 0x8C, "JGE": 0x8D, "JLE": 0x8E, "JG": 0x8F}


def parse(text):
    """-> list of items: int byte, ('CALL',name), ('LOAD',name), ('STORE',name),
       ('JMP',op,name), ('LABEL',name)"""
    items = []
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        m = re.match(r"^LABEL\s+(\w+)$", line)
        if m:
            items.append(("LABEL", m.group(1)))
            continue
        m = re.match(r"^(CALL|LOAD|STORE)\s+(\S+)$", line)
        if m:
            items.append((m.group(1), m.group(2)))
            continue
        m = re.match(r"^([A-Z]+)\s+(\w+)$", line)
        if m and m.group(1) in JMP:
            items.append(("JMP", JMP[m.group(1)], m.group(2)))
            continue
        for tok in line.replace(",", " ").split():
            items.append(int(tok, 0))
    return items


def assemble(items):
    pos, off, labels = {}, 0, {}
    for it in items:
        if isinstance(it, tuple) and it[0] == "LABEL":
            labels[it[1]] = off
        elif isinstance(it, tuple):
            off += WIDTH[it[0]] if it[0] in WIDTH else 6
        else:
            off += 1
    out, o, notes = [], 0, []
    for it in items:
        if isinstance(it, tuple) and it[0] == "LABEL":
            continue
        if isinstance(it, tuple) and it[0] == "JMP":
            _, op, tgt = it
            if tgt not in labels:
                notes.append(f"unresolved jump target: {tgt}")
                d = 0
            else:
                d = labels[tgt] - (o + 6)
            out += [0x0F, op, d & 0xFF, (d >> 8) & 0xFF, (d >> 16) & 0xFF, (d >> 24) & 0xFF]
            o += 6
        elif isinstance(it, tuple) and it[0] == "CALL":
            out += [0xE8, 0, 0, 0, 0]
            o += 5
            notes.append(f"{o-5:#06x}: call {it[1]}")
        elif isinstance(it, tuple) and it[0] == "LOAD":
            out += [0x48, 0x8B, 0x05, 0, 0, 0, 0]
            o += 7
            notes.append(f"{o-7:#06x}: mov rax, [{it[1]}]")
        elif isinstance(it, tuple) and it[0] == "STORE":
            out += [0x48, 0x89, 0x05, 0, 0, 0, 0]
            o += 7
            notes.append(f"{o-7:#06x}: mov [{it[1]}], rax")
        else:
            out.append(it)
            o += 1
    return bytes(out), labels, notes


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    text = open(sys.argv[1]).read()
    blob, labels, notes = assemble(parse(text))
    if labels:
        print("labels: " + "  ".join(f"{k}={v:#x}" for k, v in sorted(labels.items(), key=lambda x: x[1])))
    print(f"bytes:  {len(blob)}\n")
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(blob)
        path = f.name
    try:
        p = subprocess.run(["objdump", "-D", "-b", "binary", "-m", "i386:x86-64",
                            "-M", "intel", path], capture_output=True, text=True)
        for line in p.stdout.splitlines():
            if re.match(r"^\s+[0-9a-f]+:", line):
                print("  " + line.strip())
    finally:
        os.remove(path)
    if notes:
        print("\nrelocations / notes:")
        for n in notes:
            print("  " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
