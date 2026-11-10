#!/usr/bin/env python3
"""Transfer function names old-binary -> new-binary via size-sequence alignment.

Function sizes (gaps between endbr64 starts) are layout-independent: a code
change alters only the changed functions' sizes.  Align the two size
sequences (Needleman-Wunsch, gap penalty) and carry names across.
Functions whose aligned size differs are marked '~' (changed body).
"""
import struct, sys

def starts_of(p):
    d = open(p, "rb").read()
    e_phoff, = struct.unpack_from("<Q", d, 0x20)
    e_ps, e_pn = struct.unpack_from("<HH", d, 0x36)
    st = []
    for i in range(e_pn):
        off = e_phoff + i * e_ps
        pt, pf = struct.unpack_from("<II", d, off)
        po, _, _, pz, _ = struct.unpack_from("<QQQQQ", d, off + 8)
        if pt == 1 and pf & 1:
            b = d[po:po + pz]
            j = b.find(b"\xf3\x0f\x1e\xfa")
            while j >= 0:
                st.append(po + j)
                j = b.find(b"\xf3\x0f\x1e\xfa", j + 1)
    return sorted(st)

def sizes(starts, total):
    return [starts[i+1] - starts[i] for i in range(len(starts) - 1)] + [total - starts[-1]]

old_bin, new_bin, old_map, out = sys.argv[1:5]
o = starts_of(old_bin)
n = starts_of(new_bin)
os_, ns = sizes(o, len(open(old_bin, 'rb').read()),), sizes(n, len(open(new_bin, 'rb').read()))

names = {}
for ln in open(old_map):
    t = ln.split()
    if len(t) == 2 and not ln.startswith("#"):
        try:
            names[int(t[1])] = t[0]
        except ValueError:
            pass
onames = [names.get(s, f"?{i}") for i, s in enumerate(o)]

# NW alignment on sizes
A, B = len(os_), len(ns)
GAP = 60  # penalty for insert/delete; sizes differ by less for same fn
import array
score = array.array('d', [0.0]) * ((A + 1) * (B + 1))
ptr = array.array('b', [0]) * ((A + 1) * (B + 1))
W = B + 1
for i in range(1, A + 1):
    score[i * W] = -GAP * i; ptr[i * W] = 1
for j in range(1, B + 1):
    score[j] = -GAP * j; ptr[j] = 2
for i in range(1, A + 1):
    for j in range(1, B + 1):
        d = -abs(os_[i-1] - ns[j-1])  # similarity
        diag = score[(i-1)*W + (j-1)] + d
        up = score[(i-1)*W + j] - GAP
        left = score[i*W + (j-1)] - GAP
        best = diag; p = 0
        if up > best: best, p = up, 1
        if left > best: best, p = left, 2
        score[i*W + j] = best; ptr[i*W + j] = p

# traceback
i, j = A, B
pairs = []
while i > 0 or j > 0:
    p = ptr[i*W + j] if i > 0 and j > 0 else (1 if i > 0 else 2)
    if i == 0: p = 2
    if j == 0: p = 1
    if p == 0:
        pairs.append((i-1, j-1)); i -= 1; j -= 1
    elif p == 1:
        i -= 1
    else:
        j -= 1
pairs.reverse()

changed = aligned = 0
with open(out, "w") as f:
    for oi, nj in pairs:
        nm = onames[oi]
        if os_[oi] != ns[nj]:
            nm = "~" + nm
            changed += 1
        else:
            aligned += 1
        f.write(f"{nm} {n[nj]}\n")
print(f"# aligned {len(pairs)} functions; exact-size {aligned}; changed {changed}", file=sys.stderr)
