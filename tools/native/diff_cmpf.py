#!/usr/bin/env python3
"""Differential: native cmpf (sg_cmp port) vs the interpreted sg_cmp semantics."""
import ctypes, random, subprocess, sys, os

# --- reference: exact transcription of interpreted sg_cmp ---
def sg_cmp_ref(ts):
    t = list(ts)  # list of ints (bytes)
    if ts.find(b"=") < 0 and ts.find(b" isnt ") < 0:
        return bytes(t)
    if ts.find(b" = ") < 0 and ts.find(b" != ") < 0 and ts.find(b" isnt ") < 0:
        return bytes(ts)
    t = list(ts); n = len(t); i = 0; ins = 0
    while i < n:
        b = t[i]
        if b == 92:
            i += 2
            continue
        if b == 34:
            ins = 1 - ins
            i += 1
            continue
        hit = 0
        if ins == 0:
            def m(nd):
                return all(i + k < n and t[i + k] == nd[k] for k in range(len(nd)))
            if m(b" isnt "):
                hit = 1
                t = t[:i] + list(b" is not ") + t[i + 6:n]
                n = len(t); i += 8
            else:
                if m(b" != "):
                    hit = 1
                    t = t[:i] + list(b" is not ") + t[i + 4:n]
                    n = len(t); i += 8
                else:
                    if m(b" = "):
                        hit = 1
                        t = t[:i] + list(b" is ") + t[i + 3:n]
                        n = len(t); i += 4
        if hit == 0:
            i += 1
    return bytes(t)

# --- build the C harness ---
src = r'''
#define _GNU_SOURCE 1
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
typedef uint64_t U;
typedef U (*F1)(U);
static U my_alloc(U n){ return (U)malloc(n); }
#include "native_cxread_body.h"
int main(void){
    /* tbl: slot 0 = count(21), slots 1..20; only T_ALLOC used by cmpf */
    U *tbl = calloc(32, sizeof(U));
    tbl[0] = 21; tbl[T_ALLOC] = (U)my_alloc;
    U arp = 0, are = 0;
    char line[65536];
    while (fgets(line, sizeof line, stdin)) {
        U n = 0; while (line[n] && line[n] != '\n') n++;
        line[n] = 0;
        /* wrap in a heap copy so arena/pointer paths are realistic */
        char *h = (char*)malloc(65537); { U z=0; while (line[z]) { h[z]=line[z]; z++; } h[z]=0; }
        U r = cmpf((U)h, tbl, &arp, &are);
        const char *p = (const char*)r;
        fwrite(p, 1, strlen_(p), stdout);
        fputc('\n', stdout);
    }
    return 0;
}
'''
# extract just the needed statics from native_cxread.c
body = open('/home/z/my-project/work-v4/sovren-projects/sovren/tools/native_cxread.c').read()
start = body.index('typedef uint64_t U;')  # skip the file header
# take everything from the typedefs through cmpf's end
end = body.index('/* twin entry')
need = body[start:end]
open('/tmp/native_cxread_body.h', 'w').write(need)
# add a strlen_ helper
need2 = 'static U strlen_(const char *s){ U n=0; while (s[n]) n++; return n; }\n'
open('/tmp/native_cxread_body.h', 'a').write(need2)
open('/tmp/test_cmpf.c', 'w').write(src)

r = subprocess.run(['gcc', '-O1', '-w', '-o', '/tmp/test_cmpf', '/tmp/test_cmpf.c'],
                   capture_output=True, text=True, timeout=60)
if r.returncode:
    print(r.stderr[-2000:]); sys.exit(1)

# --- cases ---
cases = [
    b"", b"plain line", b"x = y", b"x != y", b"x isnt y",
    b"a = b = c", b"a = b != c", b"x  =  y", b"==", b"x==y",
    b'if a = "b = c" then', b's = "he said \\"hi = there\\" ok"',
    b"tail = ", b" =", b" = ", b" != ", b" isnt ", b"x isnt ",
    b'a = "unterminated', b"backslash = \\", b"\\ = x",
    b'q" = "r = s', b"a isnt b isnt c", b"x != y isnt z = w",
    b"    indented = value", b"tab\t= value", b'= " = " =',
    b"isnt = isnt", b'"\\"', b"= = = =", b"a = b isnt c != d = e",
]
random.seed(42)
alpha = list(b'abc ="!\\nt xyz') + [ord('='), ord('"'), ord(' '), ord('\\')]
for _ in range(3000):
    n = random.randint(0, 60)
    cases.append(bytes(random.choice(alpha) for _ in range(n)))

bad = 0
for c in cases:
    if b'\n' in c or b'\0' in c:
        continue
    exp = sg_cmp_ref(c)
    inp = c + b'\n'
    p = subprocess.run(['/tmp/test_cmpf'], input=inp, capture_output=True, timeout=30)
    got = p.stdout[:-1]
    if got != exp:
        bad += 1
        if bad <= 5:
            print("DIVERGE in=%r\n  exp=%r\n  got=%r" % (c, exp, got))
print("cases=%d divergences=%d" % (len(cases), bad))
sys.exit(1 if bad else 0)
