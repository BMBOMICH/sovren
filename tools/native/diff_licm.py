#!/usr/bin/env python3
"""Differential test: native_licm.c blob vs a direct Python transcription
of the interpreted licm family (cx86_p6.sov). Both run on randomized
line-lists; return value, licm_out and licm_sln must match exactly."""
import ctypes, random, subprocess, sys, tempfile, os, struct

ROOT = os.path.dirname(os.path.abspath(__file__))
C_SRC = os.path.normpath(os.path.join(ROOT, "..", "native_licm.c"))

# Must match scripts/build_native_licm.py exactly: the differential certifies
# the bytes that actually land, not just any build of native_licm.c.
FLAGS = ("-O3 -mno-red-zone -fno-tree-vectorize -fno-jump-tables -fno-tree-switch-conversion "
         "-fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables "
         "-fcf-protection=none -fno-builtin -ffreestanding -fPIC").split()

HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t U;
typedef long long S;

static char *names[512]; static int nnames = 0;
static U stub_alloc(U n){ return (U)malloc(n); }
static U stub_udef(U nm){
    const char *s = (const char*)nm;
    for (int i = 0; i < nnames; i++) if (!strcmp(names[i], s)) return 1;
    return 0;
}
static U g_out = 0, g_sln = 0;
static U stub_set_out(U v){ g_out = v; return 0; }
static U stub_set_sln(U v){ g_sln = v; return 0; }

U _sov_licm_scan(U lines, U sln, U tbl);

static unsigned char ibuf[1 << 22];
static size_t ipos = 0, ilen = 0;
static U rd64(void){
    U v = 0;
    for (int i = 0; i < 8; i++) v |= ((U)ibuf[ipos + i]) << (8 * i);
    ipos += 8;
    return v;
}

int main(int argc, char **argv){
    ilen = fread(ibuf, 1, sizeof ibuf, stdin);
    /* tbl doubles as the persistent cell (v3, zero fast-path dispatch):
     * 0=count(4), 1..4=helpers, 5=arp, 6=are, 7=gen tag, 8=udc base
     * (dedicated malloc via T_ALLOC, survives ar_grow chunk changes). */
    U tbl[9];
    tbl[0] = 4;
    tbl[1] = (U)(void*)stub_set_out;
    tbl[2] = (U)(void*)stub_set_sln;
    tbl[3] = (U)(void*)stub_udef;
    tbl[4] = (U)(void*)stub_alloc;
    tbl[5] = 0;
    tbl[6] = 0;
    tbl[7] = 1;
    tbl[8] = 0;
    for (int i = 1; i < argc; i++) names[nnames++] = argv[i];
    U nlines = rd64();
    char *lbuf = (char*)malloc(1 << 21); size_t lp = 0;
    U *lines = (U*)malloc(16 + (nlines ? nlines * 8 : 8) + 16);
    lines[0] = nlines; lines[1] = nlines;
    for (U i = 0; i < nlines; i++){
        U len = rd64();
        U p = (U)(void*)(lbuf + lp);
        for (U q = 0; q < len; q++) lbuf[lp++] = ibuf[ipos + q];
        ipos += len;
        lbuf[lp++] = 0;
        lines[2 + i] = p;
    }
    U nsln = rd64();
    U *sln = (U*)malloc(16 + (nsln ? nsln * 8 : 8) + 16);
    sln[0] = nsln; sln[1] = nsln;
    for (U i = 0; i < nsln; i++) sln[2 + i] = rd64();
    U r = _sov_licm_scan((U)(void*)lines, (U)(void*)sln, (U)(void*)tbl);
    printf("RET %llu\n", (unsigned long long)r);
    if (r == 1){
        U o = g_out, s2 = g_sln;
        U on = ((U*)o)[1], sn = ((U*)s2)[1];
        printf("OUT %llu\n", (unsigned long long)on);
        for (U i = 0; i < on; i++){
            const char *t = (const char*)((U*)o)[2 + i];
            printf("L %s\n", t ? t : "(null)");
        }
        printf("SLN %llu", (unsigned long long)sn);
        for (U i = 0; i < sn; i++)
            printf(" %lld", (long long)((U*)s2)[2 + i]);
        printf("\n");
    }
    fflush(stdout);
    return 0;
}
"""

def build():
    td = tempfile.mkdtemp(prefix="licmdiff")
    hp = os.path.join(td, "harness.c")
    open(hp, "w").write(HARNESS)
    # inline the licm C with 'static' entry renamed
    licm = open(os.path.normpath(os.path.join(ROOT, "..", "native_licm.c"))).read()
    licm = licm.replace("U _sov_licm_scan(U lines, U sln, U tbl)",
                        "U _sov_licm_scan(U lines, U sln, U tbl)", 1)
    src = licm + "\n" + HARNESS
    # remove the include (already has stdint)
    cp = os.path.join(td, "all.c")
    open(cp, "w").write(src)
    out = os.path.join(td, "harness")
    subprocess.run(["gcc", *FLAGS, "-o", out, cp], check=True)
    return out

# ---------------- Python transcription of the interpreted licm family ----------------
def p_strip_span(t):
    if t is None: return ""
    a = 0
    while a < len(t) and t[a] == " ": a += 1
    if a < len(t) and t[a] == "\t": return t.strip(" \t\n\r")
    s = t[a:]
    if len(s) == 0: return s
    if ord(s[-1]) < 33: return t.strip(" \t\n\r")
    return s

def p_indent(t):
    w = 0
    for c in t:
        if c == " ": w += 1
        elif c == "\t": w += 4
        else: return w
    return w

def p_whdr(s):
    if s.startswith("as long as "): return 11
    if s.startswith("while "): return 6
    if s.startswith("do while "): return 9
    return 0

PURE = {"peek_i64","peek_byte","peek_u8","peek_i32","f64_add","f64_mul","f64_sub",
        "f64_div","f64_sqrt","f64_from_i64","f64_to_i64","f64_cmp","f64_from_frac",
        "_sov_list_get","_sov_list_len","band","bor","bxor","shl","shr"}
PURE2 = PURE | {"str_find","str_len","str_eq","str_starts","str_ends",
                "_sov_find_text","_sov_strlen","_sov_str_eq","_sov_starts_with","length"}

def idc(c): return ('A'<=c<='Z') or ('a'<=c<='z') or c=='_'
def idc_ext(c): return idc(c) or ('0'<=c<='9')

class L:
    """python mirror with globals as instance attrs"""
    def __init__(self, udef):
        self.udef = udef
    def licm_pure(self, nm):
        if self.udef(nm): return 0
        return 1 if nm in PURE else 0
    def licm_pure2(self, nm):
        if self.licm_pure(nm): return 1
        # interpreted p6: user-defined task => NOT hoistable (the C port
        # shared this transcription's inversion and both sides agreed on
        # the wrong answer; fixed 2026-11-04 after the self-build ratchet
        # caught 3 divergent functions)
        if self.udef(nm): return 0
        return 1 if nm in PURE2 else 0

def scan_expr(e, L_, reads, bad):
    n = len(e); i = 0
    while i < n:
        b = e[i]
        if b == '"': bad[0] = 1; return
        if idc(b):
            j = i + 1
            while j < n and idc_ext(e[j]): j += 1
            nm = e[i:j]
            if j < n:
                if e[j] == '(':
                    if not L_.licm_pure(nm): bad[0] = 1; return
                    i = j
                else:
                    if nm not in reads: reads.append(nm)
                    i = j
            else:
                if nm not in reads: reads.append(nm)
                i = j
        else:
            i += 1

def m2_match(e, p):
    n = len(e); d = 0; i = p
    while i < n:
        b = e[i]
        if b == '"':
            i += 1; dn = 0
            while dn == 0:
                if i >= n: dn = 1
                else:
                    c = e[i]
                    if c == '\\': i += 2
                    elif c == '"': i += 1; dn = 1
                    else: i += 1
        elif b == '(':
            d += 1; i += 1
        elif b == ')':
            d -= 1
            if d == 0: return i
            i += 1
        else:
            i += 1
    return -1

def m2_argreads(e, L_, A, r2, bad):
    n = len(e); i = 0
    while i < n:
        b = e[i]
        if b == '"':
            i += 1; dn = 0
            while dn == 0:
                if i >= n: dn = 1
                else:
                    c = e[i]
                    if c == '\\': i += 2
                    elif c == '"': i += 1; dn = 1
                    else: i += 1
        elif idc(b):
            j = i + 1
            while j < n and idc_ext(e[j]): j += 1
            nm = e[i:j]
            if j < n:
                if e[j] == '(':
                    if not L_.licm_pure2(nm): bad[0] = 1; return
                    i = j
                else:
                    if nm not in r2: r2.append(nm)
                    i = j
            else:
                if nm not in r2: r2.append(nm)
                i = j
        else:
            i += 1

def m2_scan(e, L_, A, st):
    """st: dict with bad, found, pos, text, r2"""
    n = len(e); i = 0
    while i < n:
        b = e[i]
        if b == '"':
            i += 1; dn = 0
            while dn == 0:
                if i >= n: dn = 1
                else:
                    c = e[i]
                    if c == '\\': i += 2
                    elif c == '"': i += 1; dn = 1
                    else: i += 1
        elif idc(b):
            j = i + 1
            while j < n and idc_ext(e[j]): j += 1
            nm = e[i:j]
            if j < n:
                if e[j] == '(':
                    if not L_.licm_pure2(nm): st['bad'] = 1; return
                    if st['found'] == 0:
                        m = m2_match(e, j)
                        if m > -1:
                            st['r2'] = []
                            m2_argreads(e[j+1:m], L_, A, st['r2'], st)
                            if st['bad']: return
                            bad2 = 0
                            for q in st['r2']:
                                if q in A: bad2 = 1
                            if bad2 == 0:
                                st['found'] = 1
                                st['pos'] = i
                                st['text'] = e[i:m+1]
                    i = j
                else:
                    i = j
            else:
                i = j
        else:
            i += 1

def licm_lhs(s):
    p = s.find(":")
    if p < 1: return ""
    if p + 1 >= len(s) or s[p+1] != " ": return ""
    nm = s[:p]
    BAD = set(' !"%,&()*+-/<=>[]|')
    if any(c in BAD for c in nm): return ""
    if nm and (nm.isdigit() or (nm[0]=='-' and nm[1:].isdigit())): return ""
    return nm

def licm_check(ls, k, ocond, h, coff, e, b1, L_):
    lbi = p_indent(ls[k+1])
    bad = [0]
    pre_vars = []; ina = []; posta = []; hlhs = []; hexpr = []
    if "(" in ocond: return 0
    reads = []
    scan_expr(ocond, L_, reads, bad)
    oreads = list(reads)
    if bad[0]: return 0
    i = k + 1
    while i < h:
        s = p_strip_span(ls[i])
        if len(s) == 0: return 0
        if s[0] == '#': return 0
        if p_indent(ls[i]) != lbi: return 0
        nm = licm_lhs(s)
        if len(nm) == 0: return 0
        if nm not in pre_vars: pre_vars.append(nm)
        hlhs.append(nm)
        hexpr.append(s[s.find(":")+2:])
        i += 1
    sh = p_strip_span(ls[h])
    icond = sh[coff:]
    ii = 0
    if h + 1 < e: ii = p_indent(ls[h+1])
    i = h + 1
    while i < e:
        s = p_strip_span(ls[i])
        if len(s) == 0: return 0
        if s[0] == '#': return 0
        if p_indent(ls[i]) != ii: return 0
        nm = licm_lhs(s)
        if len(nm) == 0: return 0
        if nm not in ina: ina.append(nm)
        i += 1
    reads = []
    i = e
    while i < b1:
        s = p_strip_span(ls[i])
        if len(s) == 0: return 0
        if s[0] == '#': return 0
        if p_indent(ls[i]) != lbi: return 0
        nm = licm_lhs(s)
        if len(nm) == 0: return 0
        if nm not in posta: posta.append(nm)
        scan_expr(s[s.find(":")+2:], L_, reads, bad)
        if bad[0]: return 0
        i += 1
    for nm in ina:
        if nm not in pre_vars: return 0
    for nm in posta:
        if nm in pre_vars: return 0
    for nm in oreads:
        if nm in pre_vars: return 0
    defd = []
    reads = []
    for i2 in range(len(hexpr)):
        b4 = len(reads)
        scan_expr(hexpr[i2], L_, reads, bad)
        if bad[0]: return 0
        for j2 in range(b4, len(reads)):
            nm = reads[j2]
            if nm in posta: return 0
            if nm in pre_vars and nm not in defd: return 0
        if hlhs[i2] not in defd: defd.append(hlhs[i2])
    scan_expr(icond, L_, reads, bad)
    if bad[0]: return 0
    i = h + 1
    while i < e:
        s = p_strip_span(ls[i])
        scan_expr(s[s.find(":")+2:], L_, reads, bad)
        if bad[0]: return 0
        i += 1
    for nm in reads:
        if nm in posta: return 0
    return 1

def licm_one(ls, sln, L_):
    n = len(ls)
    for k in range(n):
        lk = ls[k]
        fb = lk[:1]
        ls_ok = fb in ("a", "w", "d")
        wok = p_whdr(p_strip_span(lk)) if ls_ok else 0
        if wok > 0:
            sk = p_strip_span(lk)
            ocond = sk[wok:]
            oi = p_indent(lk)
            b1 = k + 1
            while b1 < n and p_indent(ls[b1]) > oi: b1 += 1
            if b1 > k + 2:
                lbi = p_indent(ls[k+1])
                hh = -1; coff = 0
                j = k + 1
                while j < b1:
                    lj = ls[j]
                    if p_indent(lj) == lbi:
                        fb2 = lj[lbi:lbi+1]
                        w = p_whdr(p_strip_span(lj)) if fb2 in ("a","w","d") else 0
                        if w > 0:
                            hh = j; coff = w; j = b1
                    j += 1
                if hh > k + 1:
                    e = hh + 1
                    while e < b1 and p_indent(ls[e]) > lbi: e += 1
                    good = 0
                    if e > hh + 1 and e < b1:
                        good = licm_check(ls, k, ocond, hh, coff, e, b1, L_)
                    if good == 1:
                        gl = " " * oi + "if " + ocond
                        nl = ls[:k] + [gl] + ls[k+1:e] + [ls[k]] + ls[e:]
                        ns = sln[:k] + [sln[k]] + sln[k+1:e] + [sln[k]] + sln[e:]
                        return nl, ns
    return None

def licm2_check(ls, k, ocond, b1, L_, st):
    lbi = p_indent(ls[k+1])
    st['bad'] = 0
    if "(" in ocond: return 0
    A = []; hidx = []; hrhs = []
    i = k + 1
    while i < b1:
        s = p_strip_span(ls[i])
        if len(s) == 0: return 0
        if s[0] == '#': return 0
        if p_indent(ls[i]) != lbi: return 0
        spc = 0
        while spc < len(ls[i]) and ls[i][spc] == ' ': spc += 1
        if spc < len(ls[i]) and ls[i][spc] == '\t': return 0
        nm = licm_lhs(s)
        if len(nm) == 0: return 0
        if nm not in A: A.append(nm)
        hidx.append(i)
        hrhs.append(s[s.find(":")+2:])
        i += 1
    st['found'] = 0
    st['at'] = -1
    for i2 in range(len(hrhs)):
        m2_scan(hrhs[i2], L_, A, st)
        if st['bad']: return 0
        if st['found'] == 1 and st['at'] < 0:
            st['at'] = hidx[i2]
    if st['found'] == 0: return 0
    return 1

def licm2_fresh(ls):
    tmp = "licm_t"
    for try_ in range(40):
        seen = 0
        for ln in ls:
            if tmp in ln: seen = 1; break
        if seen == 0: return tmp
        tmp = tmp + "t"
    return ""

def licm2_one(ls, sln, L_):
    n = len(ls)
    st = {'bad':0,'found':0,'pos':0,'text':'','r2':[],'at':-1}
    for k in range(n):
        lk = ls[k]
        fb = lk[:1]
        ls_ok = fb in ("a", "w", "d")
        wok = p_whdr(p_strip_span(lk)) if ls_ok else 0
        if wok > 0:
            sk = p_strip_span(lk)
            ocond = sk[wok:]
            oi = p_indent(lk)
            b1 = k + 1
            while b1 < n and p_indent(ls[b1]) > oi: b1 += 1
            if b1 > k + 1:
                if licm2_check(ls, k, ocond, b1, L_, st) == 1:
                    tmp = licm2_fresh(ls)
                    if len(tmp) > 0:
                        lbi = p_indent(ls[k+1])
                        gl = " " * oi + "if " + ocond
                        hl = " " * lbi + tmp + ": " + st['text']
                        orig = ls[st['at']]
                        px = 0
                        while px < len(orig) and orig[px] == ' ': px += 1
                        s = orig.strip(" \t\n\r")
                        cp = s.find(":") + 2 + st['pos']
                        ns1 = s[:cp] + tmp + s[cp + len(st['text']):]
                        modl = orig[:px] + ns1
                        nl = ls[:k] + [gl, hl]
                        for i2 in range(k, n):
                            nl.append(modl if i2 == st['at'] else ls[i2])
                        ns = sln[:k] + [sln[k], sln[st['at']]]
                        ns = ns + sln[k:]
                        return nl, ns
    return None

def py_licm_scan(ls, sln, udef):
    if sln is None: return 0, None, None
    L_ = L(udef)
    n = len(ls)
    lh_any = 0
    for k in range(n):
        if lh_any == 0:
            lk = ls[k]
            sp = 0
            while sp < len(lk) and lk[sp] == ' ': sp += 1
            fb = lk[sp:sp+1]
            if fb in ("a","w","d"):
                if p_whdr(p_strip_span(lk)) > 0: lh_any = 1
    if lh_any == 0: return 0, None, None
    cur = ls; cs = sln; ch = 0
    it = 0
    while it < 16:
        did = 0
        r = licm_one(cur, cs, L_)
        if r: cur, cs = r; ch = 1; did = 1
        if did == 0:
            r = licm2_one(cur, cs, L_)
            if r: cur, cs = r; ch = 1; did = 1
        if did == 0: it = 16
        it += 1
    if ch == 1: return 1, cur, cs
    return 0, None, None

# ---------------- test driver ----------------
def run_case(binary, lines, sln, udefs):
    import struct
    payload = struct.pack("<Q", len(lines))
    for l in lines:
        b = l.encode()
        payload += struct.pack("<Q", len(b)) + b
    payload += struct.pack("<Q", len(sln))
    for x in sln:
        payload += struct.pack("<q", x)
    r = subprocess.run([binary, *udefs], input=payload,
                       capture_output=True, timeout=30)
    out = r.stdout.decode(errors="replace")
    ret = None; outlines = None; slns = None
    for ln in out.splitlines():
        if ln.startswith("RET "): ret = int(ln[4:])
        elif ln.startswith("OUT "):
            outlines = []
            expect_out = int(ln[4:])
        elif ln.startswith("L "):
            if outlines is not None:
                outlines.append(ln[2:])
        elif ln.startswith("SLN "):
            parts = ln[4:].split()
            slns = [int(x) for x in parts[1:]]   # parts[0] is the count
    if ret is None:
        raise RuntimeError("harness failed rc=%d: %s" % (r.returncode, r.stderr.decode(errors='replace')[:500]))
    return ret, outlines, slns

def gen_case(rng, udef_names):
    """random task body: outer while + assignments + inner while + post"""
    r0 = rng.random()
    if r0 < 0.08:
        # trailing-whitespace / tab / colon-in-string torture case
        return ["as long as i < 4 ",
                "    x: y  ",
                "\tq: 2",
                '    s: "a:b" ',
                "    while j < 2",
                "    x: 1"]
    if r0 < 0.12:
        # colon at end / no space after colon / imm lhs
        return ["while i < 4",
                "    x:",
                "    y :2",
                "    42: z",
                "    x: 1"]
    if r0 < 0.16:
        # nested deeper + post reads
        return ["as long as a < b",
                "    t: 1",
                "    while c < d",
                "        while e < f",
                "            g: h",
                "    t: t + 1"]
    vars_ = ["a", "bb", "cnt", "x_1", "total"][:rng.randint(2, 5)]
    def expr():
        r = rng.random()
        v = rng.choice(vars_)
        if r < 0.25: return str(rng.randint(0, 99))
        if r < 0.45: return v
        if r < 0.6: return "%s + %d" % (v, rng.randint(1, 9))
        if r < 0.72: return "peek_i64(%s, %d)" % (rng.choice(vars_), rng.randint(0, 4))
        if r < 0.82: return "band(%s, 255)" % v
        if r < 0.88: return "length(q)" if rng.random() < .5 else 'str_cat("x", y)'
        if r < 0.94: return "%s(%s)" % (rng.choice(["foo", "bar", "peek_u8"]), v)
        return '"lit %d"' % rng.randint(0, 9)
    lines = []
    def stmt(ind):
        r = rng.random()
        v = rng.choice(vars_)
        if r < 0.55: return " " * ind + "%s: %s" % (v, expr())
        if r < 0.65: return " " * ind + "# comment"
        if r < 0.72: return " " * ind + ""
        if r < 0.8: return " " * ind + "print %s" % v
        if r < 0.9: return " " * ind + "%s: %s + 1" % (v, v)
        return " " * ind + "%s: %s" % (v, expr())
    hdr = rng.choice(["as long as ", "while ", "do while "])
    cond = rng.choice(["i < %d" % rng.randint(1, 20), "i < n",
                       "cnt > 0", "peek_byte(p, i) is 10", 's[i] is 44'])
    lines.append(hdr + cond)
    ind = rng.choice([4, 8])
    for _ in range(rng.randint(1, 4)):
        lines.append(stmt(ind))
    if rng.random() < 0.8:
        lines.append(" " * (ind + 4) + rng.choice(["as long as ", "while "]) + rng.choice(["j < %d" % rng.randint(1, 9), "j > 0"]))
        for _ in range(rng.randint(1, 3)):
            lines.append(stmt(ind + 4))
    for _ in range(rng.randint(0, 2)):
        lines.append(stmt(ind))
    return lines

def regression_cases():
    """Shapes the random generator cannot produce. Each: (lines, udefs).
    RG-1: pure nested argument call under a USER-DEFINED outer callee -
    the shape whose transcription inversion (pure2 udef => 1) the 1500
    random cases could not catch because both sides shared the bug."""
    rg1 = ["    ls: lines_of(src)",
           "    out: _sov_list_new()",
           "    i: 0",
           "    as long as i < n",
           "        l: peek_i64(ls, 16 + i * 8)",
           "        ps: sg_cuts(l)",
           "        np: _sov_list_len(ps)",
           "        if np > 1",
           "            pk: 0",
           "            as long as pk < np",
           "                out: sg_exp_push(out, peek_i64(ps, 16 + pk * 8), sg_ind(l), 0)",
           "                pk: pk + 1",
           "        i: i + 1",
           "    return sg_text(out)"]
    return [(rg1, ["sg_cuts", "sg_exp_push", "sg_ind", "sg_qend",
                   "sg_text", "lines_of"])]

def main():
    binary = build()
    rng = random.Random(987654321)
    udef_names = ["foo", "bar", "user_fn"]
    fails = 0
    # targeted regression shapes first (both sides must agree, and must
    # agree with the INTERPRETED semantics: user-defined => no hoist)
    for rlines, rud in regression_cases():
        sln = list(range(1, len(rlines) + 1))
        ret, outlines, slns = run_case(binary, rlines, sln, rud)
        pret, pout, psln = py_licm_scan(rlines, sln, (lambda nm: nm in rud))
        ok = (ret == pret)
        if ok and ret == 1:
            ok = (outlines == pout) and (slns == psln)
        if not ok:
            fails += 1
            print("REGRESSION CASE DIVERGED (lines above)")
            print("  C  : ret=%s out=%s sln=%s" % (ret, outlines, slns))
            print("  PY : ret=%s out=%s sln=%s" % (pret, pout, psln))
        if ret != 0 or pret != 0:
            fails += 1
            print("REGRESSION CASE must be a no-fire on both sides "
                  "(interpreted declines user-defined callees): C=%s PY=%s" % (ret, pret))
    N = 1500
    for t in range(N):
        lines = gen_case(rng, udef_names)
        sln = list(range(1, len(lines) + 1))
        # random udef set per case: same for both sides
        ud = [n for n in udef_names if rng.random() < 0.7]
        ret, outlines, slns = run_case(binary, lines, sln, ud)
        pret, pout, psln = py_licm_scan(lines, sln, (lambda nm: nm in ud))
        ok = (ret == pret)
        if ok and ret == 1:
            ok = (outlines == pout) and (slns == psln)
        if not ok:
            fails += 1
            print("CASE %d DIVERGED" % t)
            print(" lines:", lines)
            print(" udef:", ud)
            print("  C  : ret=%s out=%s sln=%s" % (ret, outlines, slns))
            print("  PY : ret=%s out=%s sln=%s" % (pret, pout, psln))
            if fails >= 5: break
    print("done: %d cases, %d divergences" % (N, fails))
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
