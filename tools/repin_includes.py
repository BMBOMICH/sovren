#!/usr/bin/env python3
"""repin_includes.py - repair drifted `include` span pins.

Driver sources splice fragments out of library/inc/*.sov with lines like

    include inc/inc05.sov 789 1 #-436431011756251617

(from-line, line-count, pinned span hash).  When an inc file is edited the
spans drift: the window now covers different lines than it did when pinned,
and the spliced text is wrong.  The compiler's drift check (inc_span_hash in
compilers/shared/cx86_p7.sov) reports the mismatch; this tool does the
repair the check makes possible: for every pinned span whose hash no longer
matches at the recorded offset, search the inc file for the (unique) window
of the same length whose hash DOES match the pin, and rewrite the offset.

Hash (verified byte-for-byte against the compiler): h = 7, then for every
byte of every line in the window (newlines excluded): h = (h*16777619) ^ b,
all in unsigned 64-bit; the pin is the signed reading of h.

Spans with no match anywhere mean the content itself changed, not just its
position; those are reported and left alone for a human.

    python3 tools/repin_includes.py [--check] [paths...]
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INC_RE = re.compile(r'^(\s*include\s+)(\S+)\s+(\d+)\s+(\d+)\s+(--\d+|-?#?-?\d+)(.*)$')
MASK = (1 << 64) - 1

def H(lines_bytes, a, b):
    h = 7
    for i in range(a, b):
        for ch in lines_bytes[i]:
            h = ((h * 16777619) & MASK) ^ ch
    return h - (1 << 64) if h >= (1 << 63) else h

def resolve(pname, src_dir):
    for cand in (ROOT / pname, ROOT / src_dir / pname, ROOT / "library" / pname,
                 ROOT / "library" / "inc" / Path(pname).name):
        if cand.is_file():
            return cand
    return None

def main():
    check = "--check" in sys.argv
    accept = "--accept-current" in sys.argv
    paths = [p for p in sys.argv[1:] if not p.startswith("--")]
    files = [Path(p) for p in paths] or sorted((ROOT / "backends/native").rglob("*.sov")) \
        + sorted((ROOT / "library/inc").rglob("*.sov"))
    inc_cache = {}
    stats = {"ok": 0, "repinned": 0, "nomatch": 0, "ambig": 0, "missing": 0}
    problems = []
    for f in files:
        lines = f.read_text().split("\n")
        changed = False
        for idx, line in enumerate(lines):
            m = INC_RE.match(line)
            if not m:
                continue
            pre, pname, frm, nlin, pin, rest = m.groups()
            frm, nlin = int(frm), int(nlin)
            pin = pin.lstrip("#")
            if pin.startswith("--"):
                pin = "-" + pin[2:]   # generated flats wrote -<negative hash>
            try:
                pin = int(pin)
            except ValueError:
                continue              # a bare "--" separator, not a pin
            if nlin <= 0 or pin == 0:
                continue
            inc = resolve(pname, f.parent.relative_to(ROOT) if f.is_relative_to(ROOT) else Path("."))
            if inc is None:
                stats["missing"] += 1
                problems.append(f"{f}:{idx+1} include file not found: {pname}")
                continue
            if inc not in inc_cache:
                inc_cache[inc] = [l.encode() for l in inc.read_text().split("\n")]
            ib = inc_cache[inc]
            a, b = frm - 1, min(frm - 1 + nlin, len(ib))
            if a < len(ib) and H(ib, a, b) == pin:
                stats["ok"] += 1
                continue
            if accept and a < len(ib):
                cur = H(ib, a, b)
                lines[idx] = f"{pre}{pname} {frm} {nlin} #{cur}{rest}"
                changed = True
                stats["repinned"] += 1
                continue
            hits = [s for s in range(0, len(ib) - nlin + 1) if H(ib, s, s + nlin) == pin]
            if len(hits) == 1:
                new = f"{pre}{pname} {hits[0]+1} {nlin} #{pin}{rest}"
                lines[idx] = new
                changed = True
                stats["repinned"] += 1
            elif not hits:
                stats["nomatch"] += 1
                problems.append(f"{f}:{idx+1} {pname} from={frm} nlin={nlin} pin={pin}: no window matches (content changed)")
            else:
                stats["ambig"] += 1
                problems.append(f"{f}:{idx+1} {pname} from={frm} nlin={nlin}: {len(hits)} matching windows")
        if changed and not check:
            f.write_text("\n".join(lines))
    print(" ".join(f"{k}={v}" for k, v in stats.items()))
    for p in problems[:60]:
        print("  ", p)
    if len(problems) > 60:
        print(f"  ... and {len(problems)-60} more")
    return 1 if (stats["nomatch"] or stats["ambig"] or stats["missing"]) else 0

if __name__ == "__main__":
    raise SystemExit(main())
