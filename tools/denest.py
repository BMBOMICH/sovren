#!/usr/bin/env python3
"""De-nest calls in sovren task bodies (PS42cr law).

Nested calls in argument positions (native or task, e.g. look(peek_i64(x), "'"))
are the banked pending-arg clobber class: latent until register pressure shifts,
then a segfault. Every call lands in an ltN temp, deepest-first.

usage: python3 tools/denest.py <file.sov> [task-name-prefix ...]
       prefixes default to l3_ (the transcription slices). Writes in place.
"""
import re, sys

path = sys.argv[1]
prefixes = sys.argv[2:] or ['l3_']
src = open(path).read()
lines = src.split('\n')
task_re = re.compile(r'^(%s)[a-z_0-9]*( [a-z_0-9, ]+)?:$' % '|'.join(prefixes))
end_re  = re.compile(r'^[a-z_][a-z_0-9]*( [a-z_0-9, ]+)?:$')
spans, cur = [], None
for i, l in enumerate(lines):
    if task_re.match(l):
        if cur: spans.append(cur)
        cur = [i, None]
    elif cur and end_re.match(l):
        spans.append(cur); cur = None
if cur: spans.append(cur)
covered = set()
for s, e in spans:
    for i in range(s, (e if e else len(lines)-1)+1):
        covered.add(i)

def scan_calls(line):
    calls = []; n = len(line); depth = 0; i = 0; instr = False
    while i < n:
        c = line[i]
        if instr:
            if c == '\\': i += 2; continue
            if c == '"': instr = False
            i += 1; continue
        if c == '"': instr = True; i += 1; continue
        if c == '(':
            j = i - 1
            while j >= 0 and (line[j].isalnum() or line[j] == '_'): j -= 1
            name = line[j+1:i]
            if name: calls.append([depth, name, j+1, i])
            depth += 1
        elif c == ')': depth -= 1
        i += 1
    return calls

def close_of(line, popen):
    d = 0; k = popen; instr = False
    while k < len(line):
        c = line[k]
        if instr:
            if c == '\\': k += 2; continue
            if c == '"': instr = False
            k += 1; continue
        if c == '"': instr = True
        elif c == '(': d += 1
        elif c == ')':
            d -= 1
            if d == 0: return k
        k += 1
    return -1

def balanced(line):
    d = 0; i = 0; instr = False
    while i < len(line):
        c = line[i]
        if instr:
            if c == '\\': i += 2; continue
            if c == '"': instr = False
            i += 1; continue
        if c == '"': instr = True
        elif c == '(': d += 1
        elif c == ')':
            d -= 1
            if d < 0: return False
        i += 1
    return d == 0

counter = [1]
out = []
def hoist(line):
    while True:
        calls = scan_calls(line)
        best = None
        for b in range(len(calls)):
            pb, sb = calls[b][3], calls[b][2]
            cb = close_of(line, pb)
            if cb < 0: raise SystemExit("unbalanced: " + line)
            for a in range(len(calls)):
                if a == b: continue
                pa, ca = calls[a][3], close_of(line, calls[a][3])
                if pa < sb and cb < ca:
                    if best is None or pb > best[0]: best = (pb, sb, cb)
        if best is None: return line
        _, sb, close = best
        tname = "lt%d" % counter[0]; counter[0] += 1
        ind = line[:len(line)-len(line.lstrip())]
        hl = ind + tname + ": " + line[sb:close+1]
        nl = line[:sb] + tname + line[close+1:]
        if not balanced(nl) or not balanced(hl):
            raise SystemExit("unbalanced hoist:\n" + line + "\n->\n" + hl + "\n" + nl)
        out.append(hl)
        line = nl

for i, l in enumerate(lines):
    if i in covered and l.strip() and not l.strip().startswith('#'):
        calls = scan_calls(l)
        nested = False
        for b in range(len(calls)):
            pb, sb = calls[b][3], calls[b][2]
            cb = close_of(l, pb)
            for a in range(len(calls)):
                if a == b: continue
                pa, ca = calls[a][3], close_of(l, calls[a][3])
                if pa < sb and cb < ca: nested = True
        if nested:
            out.append(hoist(l))
            continue
    out.append(l)

open(path, 'w').write('\n'.join(out))
print("denested", counter[0]-1, "calls in", path)
