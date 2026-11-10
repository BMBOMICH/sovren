#!/usr/bin/env python3
"""Rebuild the fnmap for a Sovren compiler binary.

Recipe (validated S20, re-derived S22):
  * /tmp/sov_globs.txt (from a glog run) lists globals then `fn <name>` lines
    in WALK order; fn_names appends at walk time and the code emitter lays
    functions down in the same order.
  * endbr64 markers in the executable segment give the true function starts
    (file offsets).
  * The compiled unit's functions = endbr starts that follow the runtime
    prefix.  The runtime prefix count is calibrated by anchoring on known
    function names from a previous map (order-stable across builds).

Emits `<name> <file_offset_decimal>` lines (sampler: co = start - 0x140).
"""
import struct, sys, bisect

binary = sys.argv[1]
globs = sys.argv[2]
prev_map = sys.argv[3] if len(sys.argv) > 3 else None
out = sys.argv[4] if len(sys.argv) > 4 else "/dev/stdout"

d = open(binary, "rb").read()
e_phoff, = struct.unpack_from("<Q", d, 0x20)
e_phentsize, e_phnum = struct.unpack_from("<HH", d, 0x36)
starts = []
for i in range(e_phnum):
    off = e_phoff + i * e_phentsize
    p_type, p_flags = struct.unpack_from("<II", d, off)
    p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from("<QQQQQ", d, off + 8)
    if p_type == 1 and (p_flags & 1):
        blob = d[p_offset:p_offset + p_filesz]
        j = blob.find(b"\xf3\x0f\x1e\xfa")
        while j >= 0:
            starts.append(p_offset + j)
            j = blob.find(b"\xf3\x0f\x1e\xfa", j + 1)
starts.sort()

fns = [l[3:].strip() for l in open(globs) if l.startswith("fn ")]
print(f"# binary endbr starts: {len(starts)}; glog fns: {len(fns)}", file=sys.stderr)

prev = {}
if prev_map:
    for ln in open(prev_map):
        if ln.startswith("#"):
            continue
        t = ln.split()
        if len(t) == 2:
            try:
                prev[t[0]] = int(t[1])
            except ValueError:
                pass

# Calibration: find the alignment offset k such that starts[k+i] corresponds
# to fns[i], scored by matching a few order-stable anchor names from prev.
best_k, best_score = 0, -1
for k in range(0, max(1, len(starts) - len(fns) + 1)):
    score = 0
    for i, n in enumerate(fns):
        if n in prev and k + i < len(starts):
            po = prev[n]
            so = starts[k + i]
            # allow small drift; exact or near-exact matches score
            if abs(po - so) <= 16:
                score += 2
            elif abs(po - so) <= 4096:
                score += 1
    if score > best_score:
        best_score, best_k = score, k
print(f"# calibration: k={best_k} score={best_score}", file=sys.stderr)

with open(out, "w") as f:
    for i, n in enumerate(fns):
        if best_k + i < len(starts):
            f.write(f"{n} {starts[best_k + i]}\n")
    # any trailing starts get no name -> sampler shows them under the last
    # name; emit them as ?tail markers so they are at least separated
    # (sampler names are per-start; '?' keeps them distinct from real fns)
    for j in range(best_k + len(fns), len(starts)):
        f.write(f"?tail{j} {starts[j]}\n")
print(f"# wrote {min(len(fns), len(starts)-best_k)} named + "
      f"{max(0, len(starts)-best_k-len(fns))} tail entries", file=sys.stderr)
