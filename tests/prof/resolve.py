#!/usr/bin/env python3
# Sampling profiler resolver for Sovren self-compiles.
# Method (see investigation/FASTEST_IN_EVERYTHING.md Addendum 56):
#   1. Build a "dumpmod" compiler: driver main dumps FNMAP name/offset
#      pairs (fn_names/fn_offs) after write_elf; build it, run it on the
#      same (instrumented) sources -> fixed point + its own layout map.
#   2. Restore clean sources. Run: timeout 90 ./sampler /tmp/cand_dump \
#        compilers/linux/compiler.sov -o /tmp/sam_out > /tmp/rips.txt
#      sampler.c (ptrace) writes sampled RIPs; also saves /tmp/maps.txt.
#   3. python3 resolve.py /tmp/fnmap_raw.log /tmp/rips.txt /tmp/maps.txt
# Code VA = load_base(file offset 0 mapping of the exe) + HDR(320) + oc_off.
import sys, bisect, collections
fnmap_log, rips_file, maps_file = sys.argv[1:4]
load = None
for line in open(maps_file):
    if 'cand_dump' in line or '/compiler' in line:
        load = int(line.split('-')[0], 16); break
lines = [l.rstrip('\n') for l in open(fnmap_log)]
fns = []; i = 0
while i < len(lines):
    if lines[i].startswith('FNMAP'):
        j = i + 1; parts = []
        while j < len(lines):
            s = lines[j].strip()
            if s.lstrip('-').isdigit(): break
            if s: parts.append(s)
            j += 1
        if j < len(lines):
            fns.append((int(lines[j].strip()), ' '.join(parts))); i = j + 1; continue
    i += 1
fns.sort(); offs = [o for o, _ in fns]
BASE = load + 320
cnt = collections.Counter(); total = 0
for line in open(rips_file):
    line = line.strip()
    if not line: continue
    oc = int(line, 16) - BASE; total += 1
    if oc < 0: cnt['<hdr/other>'] += 1; continue
    k = bisect.bisect_right(offs, oc) - 1
    cnt[fns[k][1] if k >= 0 else '<entry-stub>'] += 1
print(f'total samples: {total}  distinct fns: {len(cnt)}')
for name, c in cnt.most_common(40):
    print(f'{c/total*100:5.1f}%  {c:5d}  {name}')
