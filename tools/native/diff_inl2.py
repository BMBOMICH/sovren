#!/usr/bin/env python3
"""Differential test: native_inl2.c blob vs a direct Python transcription
of the interpreted inl2 family (cx86_p6.sov), written from the .sov source.
Both run on randomized program tables + target bodies; return value,
inl2_out and inl2_sln must match exactly."""
import ctypes, random, subprocess, sys, tempfile, os, struct

ROOT = os.path.dirname(os.path.abspath(__file__))
C_SRC = os.path.normpath(os.path.join(ROOT, "..", "native_inl2.c"))

# Must match scripts/build_native_inl2.py exactly: the differential
# certifies the bytes that actually land, not just any build of the C.
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

static U stub_alloc(U n){ return (U)malloc(n ? n : 1); }
/* split_args mirror (p4 semantics, naive walk - no next_evt needed) */
static U g_out = 0, g_sln = 0;
static U stub_set_out(U v){ g_out = v; return 0; }
static U stub_set_sln(U v){ g_sln = v; return 0; }
static U split_args_c(const char *inside, U argl){
    int nz = 0; U i = 0;
    while (inside[i]){ if ((unsigned char)inside[i] > 32){ nz = 1; break; } i++; }
    if (nz){
        long depth = 0; int ins = 0; U start = 0; U ilen = strlen(inside);
        i = 0;
        while (i < ilen){
            char c = inside[i];
            if (ins){
                if (c == '\\') i++;
                else if (c == '"') ins = 0;
            } else {
                if (c == '"') ins = 1;
                else if (c == '(') depth++;
                else if (c == ')') depth--;
                else if (c == ',' && depth == 0){
                    /* append strip(inside[start:i]) */
                    U a = start, b = i;
                    while (a < b && (unsigned char)inside[a] <= 32) a++;
                    while (b > a && (unsigned char)inside[b-1] <= 32) b--;
                    char *t = (char*)malloc(b - a + 1);
                    memcpy(t, inside + a, b - a); t[b-a] = 0;
                    U n = ((U*)argl)[1];
                    if (n + 1 > ((U*)argl)[0]){
                        U nc = ((U*)argl)[0] ? ((U*)argl)[0] * 2 : 4;
                        U *nl = (U*)malloc(16 + nc * 8);
                        nl[0] = nc; nl[1] = n;
                        memcpy(nl + 2, ((U*)argl) + 2, n * 8);
                        argl = (U)nl;
                    }
                    ((U*)argl)[2 + n] = (U)(void*)t;
                    ((U*)argl)[1] = n + 1;
                    start = i + 1;
                }
            }
            i++;
        }
        {
            U a = start, b = ilen;
            while (a < b && (unsigned char)inside[a] <= 32) a++;
            while (b > a && (unsigned char)inside[b-1] <= 32) b--;
            char *t = (char*)malloc(b - a + 1);
            memcpy(t, inside + a, b - a); t[b-a] = 0;
            U n = ((U*)argl)[1];
            if (n + 1 > ((U*)argl)[0]){
                U nc = ((U*)argl)[0] ? ((U*)argl)[0] * 2 : 4;
                U *nl = (U*)malloc(16 + nc * 8);
                nl[0] = nc; nl[1] = n;
                memcpy(nl + 2, ((U*)argl) + 2, n * 8);
                argl = (U)nl;
            }
            ((U*)argl)[2 + n] = (U)(void*)t;
            ((U*)argl)[1] = n + 1;
        }
    }
    return argl;
}

U _sov_inl2_scan(U lines, U sln, U ci, U tbl);

static unsigned char ibuf[1 << 22];
static size_t ipos = 0, ilen = 0;
static U rd64(void){
    U v = 0;
    for (int i = 0; i < 8; i++) v |= ((U)ibuf[ipos + i]) << (8 * i);
    ipos += 8;
    return v;
}
static char *rd_str(void){
    U len = rd64();
    char *s = (char*)malloc(len + 1);
    memcpy(s, ibuf + ipos, len); s[len] = 0; ipos += len;
    return s;
}
static U mk_list(U n){
    U *l = (U*)malloc(16 + (n ? n * 8 : 8) + 64);
    l[0] = n + 4; l[1] = n;
    return (U)l;
}

int main(void){
    ilen = fread(ibuf, 1, sizeof ibuf, stdin);
    /* tbl: 0=count(4), 1..4 helpers, 5=arp, 6=are, 7=gen, 8=state,
     * 9=names, 10=params, 11=bodies, 12=gh, 13=gcap, 14=task_user */
    U tbl[15];
    memset(tbl, 0, sizeof tbl);
    tbl[0] = 4;
    tbl[1] = (U)(void*)stub_set_out;
    tbl[2] = (U)(void*)stub_set_sln;
    tbl[3] = (U)(void*)stub_alloc;
    tbl[4] = (U)(void*)split_args_c;
    tbl[7] = 1;

    U n_names = rd64();
    U names = mk_list(n_names);
    for (U i = 0; i < n_names; i++) ((U*)names)[2 + i] = (U)(void*)rd_str();
    U n_fns = rd64();
    U params = mk_list(n_fns);
    U bodies = mk_list(n_fns);
    U task_user = mk_list(n_fns);
    for (U i = 0; i < n_fns; i++){
        U np = rd64();
        U pl = mk_list(np);
        for (U j = 0; j < np; j++) ((U*)pl)[2 + j] = (U)(void*)rd_str();
        ((U*)params)[2 + i] = pl;
        U nb = rd64();
        U bl = mk_list(nb);
        for (U j = 0; j < nb; j++) ((U*)bl)[2 + j] = (U)(void*)rd_str();
        ((U*)bodies)[2 + i] = bl;
        ((U*)task_user)[2 + i] = rd64();
    }
    U n_gh = rd64();
    U ghcap = 16; while (ghcap * 2 < n_gh + 1) ghcap *= 2;
    U gh = (U)malloc(ghcap * 8);
    memset((void*)gh, 0, ghcap * 8);
    for (U i = 0; i < n_gh; i++) ((U*)gh)[i] = (U)(void*)rd_str();
    tbl[9] = names; tbl[10] = params; tbl[11] = bodies;
    tbl[12] = gh; tbl[13] = ghcap; tbl[14] = task_user;

    U nlines = rd64();
    U lines = mk_list(nlines);
    for (U i = 0; i < nlines; i++) ((U*)lines)[2 + i] = (U)(void*)rd_str();
    U nsln = rd64();
    U sln = mk_list(nsln);
    for (U i = 0; i < nsln; i++) ((U*)sln)[2 + i] = rd64();
    U ci = rd64();

    U r = _sov_inl2_scan(lines, sln, ci, (U)(void*)tbl);
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

# ---------------- Python transcription of the interpreted inl2 family ----------------
# (written from compilers/shared/cx86_p6.sov; the licm lesson: DO NOT copy
# from the C port - transcribe the .sov)

def t_trim(s):
    return s.strip(" \t\n\r")

def t_strip_span(s):
    a = 0
    while a < len(s) and s[a] == " ": a += 1
    if a < len(s) and s[a] == "\t": return s.strip(" \t\n\r")
    r = s[a:]
    if len(r) == 0: return r
    if ord(r[-1]) < 33: return s.strip(" \t\n\r")
    return r

def t_look(s, ndl):
    return s.find(ndl)   # -1 when absent, 0 at index 0 - same as look

def t_lhs(s):
    # licm_lhs
    p = s.find(":")
    if p < 1: return ""
    if p + 1 >= len(s) or s[p+1] != " ": return ""
    nm = s[:p]
    if not t_plain_name(nm): return ""
    if t_is_imm(nm): return ""
    return nm

BAD_SET = set(" !\"%&()*+-/<=>[]|")
def t_plain_name(nm):
    return all(c not in BAD_SET for c in nm)

def t_is_imm(s):
    if len(s) == 0: return False
    b = s[1:] if s[0] == "-" else s
    return len(b) > 0 and b.isdigit()

def t_idc(c): return ('A'<=c<='Z') or ('a'<=c<='z') or c=='_'
def t_idc2(c): return t_idc(c) or ('0'<=c<='9')

WOP = {"is","and","or","not","of","length"}
PURECALL = {"band","bor","bxor","bshl","bshr","bsar","bnot","wrap_add",
            "wrap_sub","wrap_mul","peek_byte","peek_i64","peek_u8",
            "char_at","_sov_strlen","_sov_str_eq","_sov_list_len",
            "_sov_list_get","_sov_find_text"}

def split_args(inside):
    nz = 0
    for ch in inside:
        if ord(ch) > 32: nz = 1; break
    out = []
    if nz:
        depth = 0; ins = False; start = 0; i = 0
        while i < len(inside):
            c = inside[i]
            if ins:
                if c == "\\": i += 1
                elif c == "\"": ins = False
            else:
                if c == "\"": ins = True
                elif c == "(": depth += 1
                elif c == ")": depth -= 1
                elif c == "," and depth == 0:
                    out.append(t_trim(inside[start:i]))
                    start = i + 1
            i += 1
        out.append(t_trim(inside[start:]))
    return out

class Inl2:
    def __init__(self, names, params, bodies, gh_members, task_user):
        self.names = names
        self.params = params
        self.bodies = bodies
        self.gh = set(gh_members)
        self.task_user = task_user
        self.okm = None
        self.okb = None
        self.cnci = 1000000000
        # per-call scratch
        self.bad = 0
        self.reads = []
        self.cl = []
        self.cn = []
        self.ret = ""
        self.cnm = ""
        self.cb1 = 0
        self.mapf = []
        self.mapt = []
        self.out = None
        self.sln = None

    def nm_lookup(self, nm):
        try: return self.names.index(nm)
        except ValueError: return -1

    def scanreads(self, e):
        n = len(e); i = 0
        while i < n:
            b = e[i]
            if b == "\"": self.bad = 1; return
            if t_idc(b):
                j = i + 1
                while j < n and t_idc2(e[j]): j += 1
                nm = e[i:j]
                if j < n and e[j] == "(":
                    if nm not in PURECALL: self.bad = 1; return
                    i = j
                    nm = ""
                if len(nm) > 0:
                    if nm not in self.reads: self.reads.append(nm)
                i = j
            else:
                i += 1

    def rename(self, e):
        out = ""
        n = len(e); i = 0
        while i < n:
            if t_idc(e[i]):
                j = i + 1
                while j < n and t_idc2(e[j]): j += 1
                nm = e[i:j]
                rep = nm
                for mi in range(len(self.mapf)):
                    if self.mapf[mi] == nm:
                        rep = self.mapt[mi]; break
                out += rep
                i = j
            else:
                out += e[i]
                i += 1
        return out

    def body_ok(self, cb, cps):
        nl = len(cb)
        if nl < 1: return 0
        if nl > 12: return 0
        self.cl = list(cps)
        def cl_add(nm):
            if nm not in self.cl: self.cl.append(nm)
        self.reads = []
        self.bad = 0
        inif = 0
        exprs = []
        for k in range(nl):
            ln = cb[k]
            if "\t" in ln: return 0
            if "\"" in ln: return 0
            s = t_trim(ln)
            if len(s) == 0: return 0
            if s[0] == "#": return 0
            if k == nl - 1:
                if t_look(s, "return ") != 0: return 0
                self.ret = t_trim(s[7:])
                if len(self.ret) == 0: return 0
                exprs.append(self.ret)
            else:
                if t_look(s, "return") == 0: return 0
                sp2 = 0
                while sp2 < len(ln) and ln[sp2] == " ": sp2 += 1
                nm = t_lhs(s)
                if len(nm) == 0:
                    if sp2 != 4: return 0
                    if not s.startswith("if "): return 0
                    if s == "if not": return 0
                    exprs.append(s[3:])
                    inif = 1
                if len(nm) > 0:
                    if sp2 == 4: inif = 0
                    else:
                        if sp2 != 8: return 0
                        if inif == 0: return 0
                if len(nm) > 0:
                    if nm in self.gh: return 0
                    cl_add(nm)
                    exprs.append(s[t_look(s, ":") + 2:])
        for ex in exprs:
            self.scanreads(ex)
            if self.bad == 1: return 0
        for rn in self.reads:
            ok = 0
            if rn in self.cl: ok = 1
            if rn in WOP: ok = 1
            if ok == 0:
                if rn in self.gh:
                    if rn not in self.cn: ok = 1
            if ok == 0: return 0
        return 1

    def callfind(self, rhs):
        n = len(rhs); i = 0
        found = 0
        fb0 = -1
        while i < n:
            if t_idc(rhs[i]):
                j = i + 1
                while j < n and t_idc2(rhs[j]): j += 1
                iscl = j < n and rhs[j] == "("
                if iscl:
                    found += 1
                    if found > 1: return -1
                    fb0 = i
                    self.cnm = rhs[i:j]
                    d = 1
                    q = j + 1
                    inw = -1
                    while q < n:
                        cb2 = rhs[q]
                        if cb2 == "(": d += 1
                        if cb2 == ")":
                            d -= 1
                            if d == 0:
                                inw = q
                                break
                        q += 1
                    if inw < 0: return -1
                    self.cb1 = inw
                    i = inw + 1
                else:
                    i = j
            else:
                i += 1
        return fb0

    def mkcn(self, ls, ci):
        self.cn = list(self.params[ci])
        for k in range(len(ls)):
            nm = t_lhs(t_strip_span(ls[k]))
            if len(nm) > 0 and nm not in self.cn:
                self.cn.append(nm)

    def one(self, ls, sln, ci):
        n = len(ls)
        for k in range(n):
            lk = ls[k]
            s = t_strip_span(lk)
            fire = 0
            if s.find("(") < 0: s = ""
            nsp = 0
            while nsp < len(lk) and lk[nsp] == " ": nsp += 1
            if nsp >= 4 and (nsp >= len(lk) or (lk[nsp] != " " and ord(lk[nsp]) != 0)):
                dst = t_lhs(s)
                kind = 0
                pre = ""
                rhs = ""
                if len(dst) > 0:
                    p = t_look(s, ":")
                    rhs = t_trim(s[p+2:])
                if len(dst) == 0:
                    if s.startswith("return "):
                        kind = 1
                        pre = "return "
                        rhs = t_trim(s[7:])
                if len(dst) == 0 and kind == 0:
                    if s.startswith("if "):
                        kind = 2
                        pre = "if "
                        rhs = t_trim(s[3:])
                if rhs.find("spawn ") >= 0: rhs = ""
                if len(rhs) > 0:
                    if rhs.find("\"") > -1: rhs = ""
                if len(rhs) > 0:
                    b0 = self.callfind(rhs)
                    if b0 > -1:
                        idx = self.nm_lookup(self.cnm)
                        if idx > -1:
                            if idx != ci:
                                if self.task_user[idx] == 1:
                                    fire = 1
            if fire == 1:
                if self.cnci != ci:
                    self.mkcn(ls, ci)
                    self.cnci = ci
                cps = self.params[idx]
                cb = self.bodies[idx]
                lp = t_look(rhs[b0:], "(") + b0
                argtxt = rhs[lp+1:self.cb1]
                argl = split_args(argtxt)
                argo = 1
                if len(argl) != len(cps): argo = 0
                for ai in range(len(argl)):
                    av = t_trim(argl[ai])
                    if not t_is_imm(av):
                        if not t_plain_name(av): argo = 0
                if argo == 1:
                    bok = 0
                    mhit = 0
                    if len(self.okm) > idx:
                        if self.okb[idx] == cb:
                            if self.okm[idx] != 9:
                                bok = self.okm[idx]
                                mhit = 1
                    if bok == 0:
                        bok = self.body_ok(cb, cps)
                        if len(self.okm) > idx:
                            self.okm[idx] = bok
                            self.okb[idx] = cb
                    if bok == 1:
                        # second call: cl/ret side effects feed the splice
                        self.body_ok(cb, cps)
                        ind = lk[:nsp]
                        base = "zzln"
                        btry = 0
                        bseen = 1
                        while bseen:
                            bseen = 0
                            for i2 in range(n):
                                if ls[i2].find(base) > -1: bseen = 1
                            for i2 in range(len(cb)):
                                if cb[i2].find(base) > -1: bseen = 1
                            if bseen:
                                base = base + "t"
                                btry += 1
                                if btry > 40: return 0
                        self.mapf = []
                        self.mapt = []
                        for ai in range(len(cps)):
                            self.mapf.append(cps[ai])
                            self.mapt.append(t_trim(argl[ai]))
                        for li2 in range(len(self.cn)):
                            cnm = self.cn[li2]
                            if cnm not in self.mapf:
                                tn = base + "_" + cnm
                                self.mapf.append(cnm)
                                self.mapt.append(tn)
                        gen = []
                        for i2 in range(len(cb) - 1):
                            rl2 = cb[i2]
                            sp3 = 0
                            while sp3 < len(rl2) and rl2[sp3] == " ": sp3 += 1
                            ex2 = ""
                            if sp3 > 4: ex2 = rl2[4:sp3]
                            gen.append(ind + ex2 + self.rename(t_trim(rl2)))
                        rre = self.rename(self.ret)
                        if b0 > 0:
                            nrhs = rhs[:b0] + "(" + rre + ")" + rhs[self.cb1+1:]
                        else:
                            if self.cb1 < len(rhs) - 1:
                                nrhs = "(" + rre + ")" + rhs[self.cb1+1:]
                            else:
                                nrhs = rre
                        if kind == 0:
                            gl = ind + dst + ": "
                        else:
                            gl = ind + pre
                        gl = gl + nrhs
                        gen.append(gl)
                        nl = ls[:k] + gen + ls[k+1:]
                        kln = sln[k]
                        ns = sln[:k] + [kln] * len(gen) + sln[k+1:]
                        self.out = nl
                        self.sln = ns
                        return 1
        return 0

    def scan(self, lines, sln, ci):
        if self.okm is None:
            self.okm = [9] * len(self.bodies)
            self.okb = [None] * len(self.bodies)
        cur = lines
        cs = sln
        ch = 0
        p = 0
        while p < 32:
            if self.one(cur, cs, ci) == 1:
                cur = self.out
                cs = self.sln
                ch = 1
            else:
                p = 32
            p += 1
        if ch == 1:
            return 1, cur, cs
        return 0, None, None


def build():
    td = tempfile.mkdtemp(prefix="inl2diff")
    licm = open(C_SRC).read()
    cp = os.path.join(td, "all.c")
    open(cp, "w").write(licm + "\n" + HARNESS)
    out = os.path.join(td, "harness")
    subprocess.run(["gcc", *FLAGS, "-o", out, cp], check=True)
    return out


def pack_case(case):
    names, params, bodies, gh_members, task_user, lines, sln, ci = case
    payload = struct.pack("<Q", len(names))
    for nm in names:
        b = nm.encode()
        payload += struct.pack("<Q", len(b)) + b
    payload += struct.pack("<Q", len(bodies))
    for i in range(len(bodies)):
        payload += struct.pack("<Q", len(params[i]))
        for pn in params[i]:
            b = pn.encode()
            payload += struct.pack("<Q", len(b)) + b
        payload += struct.pack("<Q", len(bodies[i]))
        for ln in bodies[i]:
            b = ln.encode()
            payload += struct.pack("<Q", len(b)) + b
        payload += struct.pack("<Q", task_user[i])
    payload += struct.pack("<Q", len(gh_members))
    for gm in gh_members:
        b = gm.encode()
        payload += struct.pack("<Q", len(b)) + b
    payload += struct.pack("<Q", len(lines))
    for ln in lines:
        b = ln.encode()
        payload += struct.pack("<Q", len(b)) + b
    payload += struct.pack("<Q", len(sln))
    for x in sln:
        payload += struct.pack("<q", x)
    payload += struct.pack("<Q", ci)
    return payload


def run_case(binary, case):
    payload = pack_case(case)
    r = subprocess.run([binary], input=payload, capture_output=True, timeout=30)
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
            slns = [int(x) for x in parts[1:]]
    if ret is None:
        raise RuntimeError("harness failed rc=%d: %s" % (r.returncode, r.stderr.decode(errors='replace')[:500]))
    return ret, outlines, slns


def py_run(case):
    names, params, bodies, gh_members, task_user, lines, sln, ci = case
    m = Inl2(names, params, bodies, gh_members, task_user)
    return m.scan(lines, sln, ci)


def gen_case(rng):
    n_fns = rng.randint(2, 6)
    names = ["fn%d" % i for i in range(n_fns)]
    params = [[rng.choice(["a", "b", "x", "y", "cnt"]) for _ in range(rng.randint(0, 3))]
              for _ in range(n_fns)]
    task_user = [1] * n_fns
    if rng.random() < 0.3:
        task_user[rng.randrange(n_fns)] = 0
    bodies = []
    for i in range(n_fns):
        if rng.random() < 0.25:
            bodies.append(["        return %d" % rng.randint(0, 99)])
            continue
        bl = []
        for _ in range(rng.randint(1, 5)):
            pn = params[i]
            v = rng.choice(pn) if pn else "1"
            r = rng.random()
            if r < 0.4: bl.append("    q%d: %s + 1" % (len(bl), v))
            elif r < 0.6: bl.append("    q%d: band(%s, 255)" % (len(bl), v))
            elif r < 0.8: bl.append("    if %s > 2" % v)
            else: bl.append("    q%d: %s" % (len(bl), v))
        bl.append("    return %s" % (rng.choice(params[i]) if params[i] else "7"))
        bodies.append(bl)
    gh_members = []
    for _ in range(rng.randint(0, 4)):
        gh_members.append(rng.choice(["g1", "g2", "heap_ptr", "zzglob"]))
    ci = rng.randrange(n_fns)
    callee = rng.choice([j for j in range(n_fns) if j != ci] or [ci])
    call = "%s(%s)" % (names[callee], ", ".join(
        rng.choice(["1", "2", "a", "b", "cnt"]) for _ in range(max(len(params[callee]), 0))) or "()")
    if len(params[callee]) == 0:
        call = "%s()" % names[callee]
    r = rng.random()
    if r < 0.4:
        lines = ["    t0: 0", "    t1: %s" % call, "    return t1"]
    elif r < 0.6:
        lines = ["    return %s" % call]
    elif r < 0.75:
        lines = ["    if a > 1", "        t0: %s" % call, "    return 2"]
    else:
        lines = ["    t0: 0", "    as long as t0 < 4", "        t1: %s" % call,
                 "        t0: t0 + 1", "    return t0"]
    sln = list(range(1, len(lines) + 1))
    return (names, params, bodies, gh_members, task_user, lines, sln, ci)


def regression_cases():
    """Shapes the generator misses (the licm lesson)."""
    cases = []
    # RG-1: caller with locals shadowing callee params (rename paths),
    # callee with if-guard bodies and a nested arg call
    names = ["outer", "inner", "helper"]
    params = [["acc"], ["p", "q"], []]
    bodies = [
        ["    acc: 0",
         "    z: inner(acc, 3)",
         "    return z"],
        ["    if p > 2",
         "        t: p + q",
         "    return t"],
        ["    return 42"],
    ]
    task_user = [1, 1, 1]
    cases.append((names, params, bodies, [], task_user,
                  ["    acc: 0", "    z: inner(acc, 3)", "    return z"],
                  [1, 2, 3], 0))
    # RG-2: zzln collision (callee body references zzln)
    bodies2 = [
        ["    acc: 0",
         "    z: inner(acc, 3)",
         "    return z"],
        ["    zzln: p + 1",
         "    return zzln"],
    ]
    cases.append((["outer", "inner"], [["acc"], ["p"]], bodies2, [],
                  [1, 1],
                  ["    acc: 0", "    z: inner(acc, 3)", "    return z"],
                  [1, 2, 3], 0))
    # RG-3: global read in callee (gh member) not captured -> reject
    cases.append((["outer", "inner"], [["acc"], ["p"]],
                  [["    acc: 0", "    z: inner(acc, 3)", "    return z"],
                   ["    return p + g1"]],
                  ["g1"], [1, 1],
                  ["    acc: 0", "    z: inner(acc, 3)", "    return z"],
                  [1, 2, 3], 0))
    # RG-4: memo hit path (same callee twice, two rounds)
    cases.append((["outer", "inner"], [["a"], ["p"]],
                  [["    a: 1", "    b: inner(a)", "    c: inner(b)",
                    "    return c"],
                   ["    return p + 1"]],
                  [], [1, 1],
                  ["    a: 1", "    b: inner(a)", "    c: inner(b)",
                   "    return c"],
                  [1, 2, 3, 4], 0))
    # RG-5: b0 == 0 (call at rhs start)
    cases.append((["outer", "inner"], [["a"], ["p"]],
                  [["    return inner(a)"],
                   ["    return p * 2"]],
                  [], [1, 1],
                  ["    return inner(a)"], [1], 0))
    # RG-6: string in rhs (quote rejection)
    cases.append((["outer", "inner"], [["a"], ["p"]],
                  [["    b: inner(a) + 1", "    return b"],
                   ["    return p"]],
                  [], [1, 1],
                  ["    b: inner(a) + \"x\"", "    return b"],
                  [1, 2], 0))
    # RG-7: BIG name table (1000 names) - the inverted load-factor sizing
    # hung the insert probe at 195% load; must stay fast and correct
    n = 1000
    names7 = ["fn%d" % i for i in range(n)]
    params7 = [[] for _ in range(n)]
    params7[500] = ["p"]
    bodies7 = [["    return 7"] for _ in range(n)]
    bodies7[500] = ["    return p + 1"]
    cases.append((names7, params7, bodies7, [], [1] * n,
                  ["    q: fn500(3)", "    return q"], [1, 2], 0))
    # RG-8: zero-arg callee under `if X() is 0` - the b0==0 + paren-tail
    # splice shape (statement-expression stack buffers died before the
    # concat and nrhs came out empty; caught by the self-build ratchet on
    # bin_memop_k's is_rel() inline)
    cases.append((["binm", "is_rel"], [["oid", "name"], []],
                  [["    sl: lsh_find_s(name)", "    rex: 72", "    absm: 0",
                    "    if sl < 0", "        if is_rel() is 0",
                    "            absm: 1", "            rex: 73", "    emit(rex)"],
                   ["    return 1"]],
                  [], [1, 1],
                  ["    sl: lsh_find_s(name)", "    rex: 72", "    absm: 0",
                   "    if sl < 0", "        if is_rel() is 0",
                   "            absm: 1", "            rex: 73", "    emit(rex)"],
                  list(range(1, 9)), 0))
    return cases


def main():
    binary = build()
    rng = random.Random(424242)
    fails = 0
    for case in regression_cases():
        ret, outlines, slns = run_case(binary, case)
        pret, pout, psln = py_run(case)
        ok = (ret == pret)
        if ok and ret == 1:
            ok = (outlines == pout) and (slns == psln)
        if not ok:
            fails += 1
            print("REGRESSION CASE DIVERGED")
            print("  C  : ret=%s out=%s sln=%s" % (ret, outlines, slns))
            print("  PY : ret=%s out=%s sln=%s" % (pret, pout, psln))
            if fails >= 5: break
    N = 1500
    for t in range(N):
        case = gen_case(rng)
        ret, outlines, slns = run_case(binary, case)
        pret, pout, psln = py_run(case)
        ok = (ret == pret)
        if ok and ret == 1:
            ok = (outlines == pout) and (slns == psln)
        if not ok:
            fails += 1
            print("CASE %d DIVERGED" % t)
            names, params, bodies, gh_members, task_user, lines, sln, ci = case
            print(" lines:", lines)
            print(" bodies:", bodies)
            print(" params:", params)
            print(" gh:", gh_members, "tu:", task_user, "ci:", ci)
            print("  C  : ret=%s out=%s sln=%s" % (ret, outlines, slns))
            print("  PY : ret=%s out=%s sln=%s" % (pret, pout, psln))
            if fails >= 5: break
    print("done: %d cases, %d divergences" % (N, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
