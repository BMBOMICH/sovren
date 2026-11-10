/* Native c0_parse: the single-pass parse loop of compile(), C port.
 * 1:1 mirror of compilers/linux/compiler.sov 10444..10671 (pcap alloc
 * through the final bodies/body_lns append) plus every helper it calls:
 * nind (cx86_p5:1854), strip=_sov_trim, strip_span (p6:1763), starts,
 * is_task_hdr (p5:368), tname (p6:2154), tparams/tparams_g (p7:1896),
 * find_col/find_col_q (p4:5297), find_sep/find_sep_do (p4:5328),
 * repl/repl_do (p6:494, BOTH branches incl. the quote-aware machine),
 * file_ln (p4:5292), i2s (p5:235, WITH trailing newline), str_cat,
 * zz_dup/gn_lookup/sg_lookup (blob-local hashes - the three program
 * lists are empty at loop entry, so "added earlier in this loop" is
 * the exact answer), zz_g2 (raw-syscall probe of /tmp/sov_glog2,
 * cached per call) and the per-global /tmp/sov_g2.log writes
 * (open 1089/438, one write syscall per byte, close - like the source).
 * The source's bodies_buf/bodyln_buf allocations (10447-10450) are dead
 * (never read again) and are not reproduced.
 * The law block is transcribed verbatim; note it is unreachable for
 * space-indented lines (s stays raw there, so starts(s,"law ") is 0
 * whenever c0n0>0) - the interpreted loop has the identical structure.
 * Helpers behind the caller tbl (Sovren ABI: rdi,rsi,rdx,...; rax ret):
 *   1 print(a)        - `print a` (emit_print: runtime pointer/int split)
 *   2 print_int(a)    - same task as 1 (kept separate for harness markers)
 *   3 _sov_print(a)   - the runtime native
 *   4 set_err_line(a) - err_line := a
 *   5 err_where()
 *   6 _sov_heap_alloc(n)
 * tbl-as-cell layout (U* slots):
 *   0=count(6), 1..6=helpers, 7=arp, 8=are (written by ar_grow),
 *   9=gen (reserved), 10=src_base, 11=kern_mode, 12=need_priv (in/out),
 *   13=had_err (in/out), 14=blank,
 *   20=names_buf, 21=params, 22=bodies, 23=body_lns, 24=task_lns,
 *   25=task_user, 26=glob_names, 27=sglob_names, 28=tops, 29=tops_lns,
 *   30=tops_users (published by the blob).
 * names_buf is pre-sized pcap=len+8 like the source (cap slot [0]=pcap,
 * count [8], data 16+i*8).  All other lists are growable arena lists
 * ([cap,len,data] - _sov_list_add compatible).  Bump arena: 16-aligned
 * ar_get (the session-11 movdqa lesson); hashes keep load < 50% (the
 * session-11 STAB lesson: cap < (n+1)*2 sizing).
 * No external symbols, no relocations, no .rodata (DEF_EQ/byte-literal
 * discipline), no statement-expression stack buffers.
 * Sovren comparisons are SIGNED: find results are -1; `t > 0 - 1` etc.
 */
#include <stdint.h>
typedef uint64_t U;
typedef long long S;
typedef U (*F1)(U);

enum {
    H_PRINT = 1, H_PRINTINT = 2, H_SPRINT = 3,
    H_SETERR = 4, H_ERRWHERE = 5, H_ALLOC = 6
};

#define LLEN(x) (*(U *)((x) + 8))
#define ELEM(x, i) (*(U *)((x) + 16 + (U)(i) * 8))
#define PB(s, i) (*(const unsigned char *)((s) + (U)(i)))

/* ---- raw syscalls (x86-64: 1=write 2=open 3=close) ---- */
static S sys_open(U p, U f, U m)
{
    S r;
    __asm__ __volatile__("syscall"
                         : "=a"(r)
                         : "a"((U)2), "D"(p), "S"(f), "d"(m)
                         : "rcx", "r11", "memory");
    return r;
}
static S sys_write(U fd, U buf, U n)
{
    S r;
    __asm__ __volatile__("syscall"
                         : "=a"(r)
                         : "a"((U)1), "D"(fd), "S"(buf), "d"(n)
                         : "rcx", "r11", "memory");
    return r;
}
static S sys_close(U fd)
{
    S r;
    __asm__ __volatile__("syscall"
                         : "=a"(r)
                         : "a"((U)3), "D"(fd)
                         : "rcx", "r11", "memory");
    return r;
}

/* ---- context ---- */
typedef struct {
    U *h;    /* cap slots, one pointer each */
    U cap;
    U n;
    U *mem;  /* member list for rebuilds */
    U memcap;
} HX;
typedef struct {
    U *tbl;
    U *arp; /* points at tbl[7] */
    U *are; /* points at tbl[8] */
    S src_base;
    U kern_mode;
    U need_priv;
    U had_err;
    U blank;
    S g2v; /* zz_g2 probe cache (-1 = unknown) */
    /* blob-local membership hashes (answers are hash-independent) */
    HX nh, gh, sh;
} C0;

static inline U t1(U *t, U i, U a) { return ((F1)t[i])(a); }

/* ---- persistent bump arena (1 MiB chunks; 16-aligned) ---- */
#define AR_CHUNK 1048576
static U ar_grow(C0 *c, U n)
{
    U want = AR_CHUNK;
    if (want < n)
        want = n;
    U p = t1(c->tbl, H_ALLOC, want);
    *c->arp = p;
    *c->are = p + want;
    return p;
}
static U ar_get(C0 *c, U n)
{
    *c->arp = (*c->arp + 15) & ~(U)15;
    if (*c->arp + n > *c->are)
        ar_grow(c, n);
    U p = *c->arp;
    *c->arp = p + n;
    return p;
}

/* ---- span model: [b, e) ---- */
typedef struct {
    const unsigned char *b;
    const unsigned char *e;
} Sp;
static U splen(Sp s) { return (U)(s.e - s.b); }
static Sp sp_of(U p)
{
    Sp r;
    r.b = (const unsigned char *)(void *)p;
    r.e = r.b;
    if (r.b) {
        while (r.e[0])
            r.e++;
    }
    return r;
}
static U ar_str(C0 *c, Sp s)
{
    U n = splen(s);
    U p = ar_get(c, n + 1);
    U i = 0;
    while (i < n) {
        *(unsigned char *)(p + i) = s.b[i];
        i++;
    }
    *(unsigned char *)(p + n) = 0;
    return p;
}
static U ar_cat2(C0 *c, Sp a, Sp b)
{
    U na = splen(a), nb = splen(b);
    U p = ar_get(c, na + nb + 1);
    U w = 0, i = 0;
    while (i < na) *(unsigned char *)(p + w++) = a.b[i++];
    i = 0;
    while (i < nb) *(unsigned char *)(p + w++) = b.b[i++];
    *(unsigned char *)(p + w) = 0;
    return p;
}
static U ar_cat3(C0 *c, Sp a, Sp b, Sp d)
{
    U n = splen(a) + splen(b) + splen(d);
    U p = ar_get(c, n + 1);
    U w = 0, i = 0;
    while (i < splen(a)) *(unsigned char *)(p + w++) = a.b[i++];
    i = 0;
    while (i < splen(b)) *(unsigned char *)(p + w++) = b.b[i++];
    i = 0;
    while (i < splen(d)) *(unsigned char *)(p + w++) = d.b[i++];
    *(unsigned char *)(p + w) = 0;
    return p;
}
static U ar_cat4(C0 *c, Sp a, Sp b, Sp d, Sp e)
{
    U n = splen(a) + splen(b) + splen(d) + splen(e);
    U p = ar_get(c, n + 1);
    U w = 0, i = 0;
    while (i < splen(a)) *(unsigned char *)(p + w++) = a.b[i++];
    i = 0;
    while (i < splen(b)) *(unsigned char *)(p + w++) = b.b[i++];
    i = 0;
    while (i < splen(d)) *(unsigned char *)(p + w++) = d.b[i++];
    i = 0;
    while (i < splen(e)) *(unsigned char *)(p + w++) = e.b[i++];
    *(unsigned char *)(p + w) = 0;
    return p;
}
static U ar_list(C0 *c, U cap)
{
    U p = ar_get(c, 16 + cap * 8);
    *(U *)(p) = cap;
    *(U *)(p + 8) = 0;
    return p;
}
static U ladd(C0 *c, U lst, U v)
{
    if (lst == 0)
        lst = ar_list(c, 8);
    U n = LLEN(lst);
    U cap = *(U *)(lst);
    if (n >= cap) {
        U nc = cap * 2;
        if (nc < 8)
            nc = 8;
        U nl = ar_list(c, nc);
        U i = 0;
        while (i < n) {
            ELEM(nl, i) = ELEM(lst, i);
            i++;
        }
        *(U *)(nl + 8) = n;
        lst = nl;
    }
    ELEM(lst, n) = v;
    *(U *)(lst + 8) = n + 1;
    return lst;
}

/* ---- string primitives, span forms ---- */
static S span_cfind1(Sp t, unsigned ch)
{
    U i = 0;
    while (t.b + i < t.e) {
        if (t.b[i] == ch)
            return (S)i;
        i++;
    }
    return (S)-1;
}
static int span_eq(Sp a, Sp b)
{
    U n = splen(a);
    if (n != splen(b))
        return 0;
    U i = 0;
    while (i < n) {
        if (a.b[i] != b.b[i])
            return 0;
        i++;
    }
    return 1;
}
/* span-bounded needle find (signed -1 miss) */
static S span_find(Sp s, const unsigned char *nb, U nl)
{
    U n = splen(s);
    if (nl == 0)
        return 0;
    if (n < nl)
        return (S)-1;
    U i = 0;
    while (i + nl <= n) {
        U j = 0;
        while (j < nl && s.b[i + j] == nb[j])
            j++;
        if (j == nl)
            return (S)i;
        i++;
    }
    return (S)-1;
}
/* strip = _sov_trim: both ends of {32,9,10,13} */
static int is_ws(unsigned ch) { return ch == 32 || ch == 9 || ch == 10 || ch == 13; }
static Sp ss_trim(Sp x)
{
    while (x.b < x.e && is_ws(x.b[0]))
        x.b++;
    while (x.e > x.b && is_ws(x.e[-1]))
        x.e--;
    return x;
}
static Sp sp_trim_line(U t)
{
    Sp r;
    r.b = (const unsigned char *)(void *)t;
    r.e = r.b;
    if (r.b) {
        while (r.e[0])
            r.e++;
    }
    return ss_trim(r);
}
/* strip_span (p6:1763) - value model */
static Sp sp_strip_span(U t)
{
    Sp r;
    r.b = (const unsigned char *)(void *)t;
    r.e = r.b;
    if (t == 0)
        return r;
    U a = 0;
    while (PB(t, a) == 32)
        a++;
    if (PB(t, a) == 9)
        return sp_trim_line(t);
    const unsigned char *s = (const unsigned char *)(void *)t + a;
    U n = 0;
    while (s[n])
        n++;
    r.b = s;
    r.e = s;
    if (n == 0)
        return r;
    if (s[n - 1] < 33)
        return sp_trim_line(t);
    r.e = s + n;
    return r;
}
/* cut clamping (_sov_substring minus the s<4096 guard - never hit) */
static Sp ssp_cut(Sp s, S a, S b)
{
    S n = (S)splen(s);
    if (a < 0)
        a = 0;
    if (b > n)
        b = n;
    if (b < a)
        b = a;
    Sp r;
    r.b = s.b + a;
    r.e = s.b + b;
    return r;
}
/* byte-literal prefix matchers (no .rodata) */
static int pw_wipe(Sp s) /* "wipe " */
{
    return splen(s) >= 5 && s.b[0] == 'w' && s.b[1] == 'i' && s.b[2] == 'p' &&
           s.b[3] == 'e' && s.b[4] == ' ';
}
static int pw_task(Sp s) /* "task " */
{
    return splen(s) >= 5 && s.b[0] == 't' && s.b[1] == 'a' && s.b[2] == 's' &&
           s.b[3] == 'k' && s.b[4] == ' ';
}
static int pw_alias(Sp s) /* "<-- " */
{
    return splen(s) >= 4 && s.b[0] == '<' && s.b[1] == '-' && s.b[2] == '-' &&
           s.b[3] == ' ';
}
static int pw_use(Sp s) /* "use " */
{
    return splen(s) >= 4 && s.b[0] == 'u' && s.b[1] == 's' && s.b[2] == 'e' &&
           s.b[3] == ' ';
}
static int pw_law(Sp s) /* "law " */
{
    return splen(s) >= 4 && s.b[0] == 'l' && s.b[1] == 'a' && s.b[2] == 'w' &&
           s.b[3] == ' ';
}
static int pw_hash(Sp s) /* "#" */
{
    return splen(s) >= 1 && s.b[0] == 35;
}
static S find_with(Sp s) /* " with " */
{
    U n = splen(s);
    if (n < 6)
        return (S)-1;
    U i = 0;
    while (i + 6 <= n) {
        if (s.b[i] == ' ' && s.b[i + 1] == 'w' && s.b[i + 2] == 'i' &&
            s.b[i + 3] == 't' && s.b[i + 4] == 'h' && s.b[i + 5] == ' ')
            return (S)i;
        i++;
    }
    return (S)-1;
}
static S find_sp(Sp s) /* " " */
{
    U n = splen(s);
    U i = 0;
    while (i < n) {
        if (s.b[i] == 32)
            return (S)i;
        i++;
    }
    return (S)-1;
}
#define DEF_EQ(name, ...)                                                      \
    static int name(Sp nm)                                                     \
    {                                                                          \
        char _c[] = {__VA_ARGS__}; /* stack-local: no .rodata, no relocs */      \
        if (splen(nm) != sizeof(_c))                                           \
            return 0;                                                          \
        U _i = 0;                                                              \
        while (_i < sizeof(_c)) {                                              \
            if (nm.b[_i] != (unsigned char)_c[_i])                             \
                return 0;                                                      \
            _i++;                                                              \
        }                                                                      \
        return 1;                                                              \
    }
DEF_EQ(eq_private, 'p', 'r', 'i', 'v', 'a', 't', 'e')
DEF_EQ(d_heap_ptr, 'h', 'e', 'a', 'p', '_', 'p', 't', 'r')
DEF_EQ(d_heap_end, 'h', 'e', 'a', 'p', '_', 'e', 'n', 'd')
DEF_EQ(d_g_slide, 'g', '_', 's', 'l', 'i', 'd', 'e')
DEF_EQ(d_g_canary, 'g', '_', 'c', 'a', 'n', 'a', 'r', 'y')
DEF_EQ(d_g_argc, 'g', '_', 'a', 'r', 'g', 'c')
DEF_EQ(d_g_argv, 'g', '_', 'a', 'r', 'g', 'v')
DEF_EQ(d_pie_walk, 'p', 'i', 'e', '_', 'w', 'a', 'l', 'k')
DEF_EQ(d_sc_write, 's', 'c', '_', 'w', 'r', 'i', 't', 'e')
DEF_EQ(d_sc_exit, 's', 'c', '_', 'e', 'x', 'i', 't')
DEF_EQ(d_sc_mmap, 's', 'c', '_', 'm', 'm', 'a', 'p')
DEF_EQ(d_mmap_flags, 'm', 'm', 'a', 'p', '_', 'f', 'l', 'a', 'g', 's')
DEF_EQ(d_sc_mincore, 's', 'c', '_', 'm', 'i', 'n', 'c', 'o', 'r', 'e')
DEF_EQ(d_sc_rand, 's', 'c', '_', 'r', 'a', 'n', 'd')
DEF_EQ(d_sc_nodump, 's', 'c', '_', 'n', 'o', 'd', 'u', 'm', 'p')
DEF_EQ(d_sc_sigact, 's', 'c', '_', 's', 'i', 'g', 'a', 'c', 't')
DEF_EQ(d_M32, 'M', '3', '2')
static int dupok_name(Sp gn)
{
    return d_heap_ptr(gn) || d_heap_end(gn) || d_g_slide(gn) ||
           d_g_canary(gn) || d_g_argc(gn) || d_g_argv(gn) || d_pie_walk(gn) ||
           d_sc_write(gn) || d_sc_exit(gn) || d_sc_mmap(gn) ||
           d_mmap_flags(gn) || d_sc_mincore(gn) || d_sc_rand(gn) ||
           d_sc_nodump(gn) || d_sc_sigact(gn) || d_M32(gn);
}

/* ---- i2s (p5:235): "digits\n" WITH trailing newline ---- */
static U b_i2s(C0 *c, S n)
{
    char buf[24];
    U i = 0;
    S v = n;
    if (v != 0) {
        while (v != 0) {
            S d = v % 10;
            if (d < 0)
                d = -d;
            buf[i++] = (char)(48 + d);
            v = v / 10;
        }
    } else {
        buf[i++] = '0';
    }
    U need = i + 2; /* optional '-' + digits + '\n' */
    U p = ar_get(c, need + 1);
    U w = 0;
    if (n < 0)
        *(unsigned char *)(p + w++) = '-';
    while (i > 0)
        *(unsigned char *)(p + w++) = (unsigned char)buf[--i];
    *(unsigned char *)(p + w++) = '\n';
    *(unsigned char *)(p + w) = 0;
    return p;
}

/* ---- find_col / find_col_q (p4:5297) ---- */
static S b_find_col_q(Sp t)
{
    U n = splen(t);
    U i = 0;
    U ins = 0;
    while (i < n) {
        unsigned b = t.b[i];
        if (ins) {
            if (b == 92)
                i++;
            else if (b == 34)
                ins = 0;
        } else {
            if (b == 34)
                ins = 1;
            else if (b == 58)
                return (S)i;
        }
        i++;
    }
    return (S)-1;
}
static S b_find_col(Sp t)
{
    if (span_cfind1(t, 34) < 0)
        return span_cfind1(t, 58);
    return b_find_col_q(t);
}

/* ---- find_sep / find_sep_do (p4:5328): " := " outside quotes ---- */
static int sep4_at(Sp t, U i)
{
    return t.b[i] == ' ' && t.b[i + 1] == ':' && t.b[i + 2] == '=' &&
           t.b[i + 3] == ' ';
}
static S b_find_sep(Sp t)
{
    /* pre-gate: ":=" anywhere (behavior-neutral, mirrors the source) */
    U n = splen(t);
    {
        U i = 0;
        int hit = 0;
        while (i + 2 <= n) {
            if (t.b[i] == ':' && t.b[i + 1] == '=') {
                hit = 1;
                break;
            }
            i++;
        }
        if (!hit)
            return (S)-1;
    }
    S nn = (S)n;
    S i = 0;
    U ins = 0;
    while (i < nn - 3) {
        unsigned b = t.b[i];
        if (ins) {
            if (b == 92)
                i++;
            else if (b == 34)
                ins = 0;
        } else {
            if (b == 34)
                ins = 1;
        }
        if (ins == 0) {
            if (sep4_at(t, (U)i))
                return i;
        }
        i++;
    }
    return (S)-1;
}

/* ---- repl / repl_do (p6:494): BOTH branches, exact quote machine ---- */
static int sp_match(Sp t, U p, const unsigned char *ob, U ol)
{
    U j = 0;
    while (j < ol) {
        if (t.b[p + j] != ob[j])
            return 0;
        j++;
    }
    return 1;
}
static U b_repl(C0 *c, Sp text, const unsigned char *ob, U ol,
                const unsigned char *nb, U nl)
{
    if (span_find(text, ob, ol) < 0)
        return ar_str(c, text);
    S n = (S)splen(text);
    U o = ol, gn = nl;
    if (o > 0 && span_cfind1(text, 34) < 0) {
        /* fast path (no quotes): count with the skip scan */
        U hits = 0;
        S p = 0;
        while (p + (S)o <= n) {
            if (sp_match(text, (U)p, ob, o)) {
                hits++;
                p += (S)o;
            } else {
                p++;
            }
        }
        U r = ar_get(c, (U)(n) + hits * gn + 8 + 1);
        U j = 0;
        p = 0;
        while (p < n) {
            U m = 0;
            if (p + (S)o <= n && sp_match(text, (U)p, ob, o))
                m = 1;
            if (m) {
                U k = 0;
                while (k < gn) {
                    *(unsigned char *)(r + j) = nb[k];
                    j++;
                    k++;
                }
                p += (S)o;
            } else {
                *(unsigned char *)(r + j) = text.b[p];
                j++;
                p++;
            }
        }
        *(unsigned char *)(r + j) = 0;
        return r;
    }
    /* quote-aware path.  NOTE: every call site in this loop has
     * new-length <= old-length (" "->"_", ","->" ", " and "->" "), so
     * the source's n+gn+8 buffer is always sufficient (the interpreted
     * compiler carries the same sizing). */
    U r = ar_get(c, (U)(n) + gn + 8 + 1);
    S p = 0;
    U j = 0;
    U ins = 0;
    while (p < n) {
        unsigned b = text.b[p];
        if (ins) {
            if (b == 92) {
                *(unsigned char *)(r + j) = b;
                j++;
                p++;
                if (p < n) {
                    *(unsigned char *)(r + j) = text.b[p];
                    j++;
                    p++;
                }
            } else {
                *(unsigned char *)(r + j) = b;
                j++;
                p++;
                if (b == 34)
                    ins = 0;
            }
        } else {
            if (b == 34) {
                ins = 1;
                *(unsigned char *)(r + j) = b;
                j++;
                p++;
            } else {
                U m = 0;
                if (p + (S)o <= n && sp_match(text, (U)p, ob, o))
                    m = 1;
                if (m) {
                    U k = 0;
                    while (k < gn) {
                        *(unsigned char *)(r + j) = nb[k];
                        j++;
                        k++;
                    }
                    p += (S)o;
                } else {
                    *(unsigned char *)(r + j) = b;
                    j++;
                    p++;
                }
            }
        }
    }
    *(unsigned char *)(r + j) = 0;
    return r;
}

/* ---- nind (p5:1854) with the tab error path ---- */
static U b_nind(C0 *c, U line)
{
    U cnt = 0;
    U i = 0;
    for (;;) {
        unsigned b = PB(line, i);
        if (b == 0)
            return cnt;
        if (b == 9) {
            t1(c->tbl, H_PRINT, 1); /* Error: tab indent, use spaces */
            t1(c->tbl, H_SPRINT, line);
            t1(c->tbl, H_ERRWHERE, 0);
            c->had_err = 1;
            return cnt;
        }
        if (b != 32)
            return cnt;
        cnt++;
        i++;
    }
}

/* ---- is_task_hdr (p5:368) ---- */
static int is_task_hdr(Sp s)
{
    U n = splen(s);
    if (n < 2)
        return 0;
    if (s.b[0] == 35)
        return 0;
    if (s.b[n - 1] == 58)
        return 1;
    return 0;
}

/* ---- tname (p6:2154): returns a NUL-terminated arena string ---- */
static U b_tname(C0 *c, Sp line)
{
    Sp s = ss_trim(line); /* strip(line): line is already a trimmed span; idempotent */
    if (is_task_hdr(s)) {
        Sp s2 = ss_trim(ssp_cut(s, 0, (S)splen(s) - 1));
        if (pw_task(s2))
            s2 = ss_trim(ssp_cut(s2, 5, (S)splen(s2)));
        S wp = find_with(s2);
        if (wp > -1) {
            unsigned char ob[] = {' '};
            unsigned char nb[] = {'_'};
            return b_repl(c, ss_trim(ssp_cut(s2, 0, wp)), ob, 1, nb, 1);
        }
        S sp = find_sp(s2);
        if (sp > -1)
            return ar_str(c, ss_trim(ssp_cut(s2, 0, sp)));
        return ar_str(c, s2);
    }
    Sp rest = ss_trim(ssp_cut(line, 5, (S)splen(line)));
    S wp = find_with(rest);
    unsigned char ob[] = {' '};
    unsigned char nb[] = {'_'};
    if (wp > -1)
        return b_repl(c, ss_trim(ssp_cut(rest, 0, wp)), ob, 1, nb, 1);
    S sp = find_sp(rest);
    if (sp > -1)
        return b_repl(c, ss_trim(ssp_cut(rest, 0, sp)), ob, 1, nb, 1);
    return b_repl(c, rest, ob, 1, nb, 1);
}

/* ---- tparams header branch (p7:1896); the non-header branch is
 * unreachable from this loop's only call site (the caller verified
 * is_task_hdr on the same stripped line; _sov_trim is idempotent). ---- */
static U b_tparams(C0 *c, Sp line)
{
    U lst = ar_list(c, 8);
    Sp s = ss_trim(line); /* strip(line): idempotent on the trimmed span */
    if (!is_task_hdr(s))
        return lst;
    Sp s2 = ss_trim(ssp_cut(s, 0, (S)splen(s) - 1));
    if (pw_task(s2))
        s2 = ss_trim(ssp_cut(s2, 5, (S)splen(s2)));
    S wp = find_with(s2);
    Sp p3;
    if (wp > -1) {
        p3 = ss_trim(ssp_cut(s2, wp + 6, (S)splen(s2)));
    } else {
        S sp = find_sp(s2);
        if (sp < 0)
            return lst;
        p3 = ss_trim(ssp_cut(s2, sp + 1, (S)splen(s2)));
    }
    unsigned char cb[] = {','};
    unsigned char sb[] = {' '};
    unsigned char ab[] = {' ', 'a', 'n', 'd', ' '};
    U p = b_repl(c, p3, cb, 1, sb, 1);
    p = b_repl(c, sp_of(p), ab, 5, sb, 1);
    Sp ps = sp_of(p);
    U n = splen(ps);
    U start = 0;
    U i = 0;
    while (i < n) {
        if (ps.b[i] == 32) {
            Sp one = ss_trim(ssp_cut(ps, (S)start, (S)i));
            if (splen(one) > 0)
                lst = ladd(c, lst, ar_str(c, one));
            start = i + 1;
        }
        i++;
    }
    Sp one = ss_trim(ssp_cut(ps, (S)start, (S)n));
    if (splen(one) > 0)
        lst = ladd(c, lst, ar_str(c, one));
    return lst;
}

/* ---- blob-local membership hashes ---- */
static U hash_bytes(const unsigned char *b, U n)
{
    U h = 1469598103934665603ULL;
    U i = 0;
    while (i < n) {
        h ^= b[i];
        h *= 1099511628211ULL;
        i++;
    }
    return h;
}
static int hx_has(C0 *c, HX *x, U s)
{
    (void)c;
    if (x->cap == 0)
        return 0;
    Sp v = sp_of(s);
    U hh = hash_bytes(v.b, splen(v));
    U sl = hh & (x->cap - 1);
    while (x->h[sl] != 0) {
        if (x->h[sl] == s)
            return 1;
        Sp w = sp_of(x->h[sl]);
        if (span_eq(v, w))
            return 1;
        sl = (sl + 1) & (x->cap - 1);
    }
    return 0;
}
static void hx_rebuild(C0 *c, HX *x, U ncap)
{
    while (ncap < (x->n + 1) * 2)
        ncap *= 2;
    U *h = (U *)(void *)ar_get(c, ncap * 8);
    U q = 0;
    while (q < ncap) {
        h[q] = 0;
        q++;
    }
    U i = 0;
    while (i < x->n) {
        U m = x->mem[i];
        Sp v = sp_of(m);
        U hh = hash_bytes(v.b, splen(v));
        U sl = hh & (ncap - 1);
        while (h[sl] != 0)
            sl = (sl + 1) & (ncap - 1);
        h[sl] = m;
        i++;
    }
    x->h = h;
    x->cap = ncap;
}
static void hx_ins(C0 *c, HX *x, U s)
{
    if (x->cap < (x->n + 1) * 2)
        hx_rebuild(c, x, x->cap ? x->cap * 2 : 16);
    if (x->n >= x->memcap) {
        U nc = x->memcap ? x->memcap * 2 : 16;
        U *m = (U *)(void *)ar_get(c, nc * 8);
        U i = 0;
        while (i < x->n) {
            m[i] = x->mem[i];
            i++;
        }
        x->mem = m;
        x->memcap = nc;
    }
    Sp v = sp_of(s);
    U hh = hash_bytes(v.b, splen(v));
    U sl = hh & (x->cap - 1);
    while (x->h[sl] != 0)
        sl = (sl + 1) & (x->cap - 1);
    x->h[sl] = s;
    x->mem[x->n] = s;
    x->n++;
}

/* ---- zz_g2 probe + per-global log write (raw syscalls) ----
 * Paths are per-byte stores (no initializer: a 16-byte initialized local
 * would become a .rodata template + PC32 relocation - the gate forbids
 * relocations, and objcopy -j .text would drop the bytes). */
static void path_glog2(char *d)
{
    d[0] = '/'; d[1] = 't'; d[2] = 'm'; d[3] = 'p'; d[4] = '/';
    d[5] = 's'; d[6] = 'o'; d[7] = 'v'; d[8] = '_'; d[9] = 'g';
    d[10] = 'l'; d[11] = 'o'; d[12] = 'g'; d[13] = '2'; d[14] = 0;
}
static void path_g2log(char *d)
{
    d[0] = '/'; d[1] = 't'; d[2] = 'm'; d[3] = 'p'; d[4] = '/';
    d[5] = 's'; d[6] = 'o'; d[7] = 'v'; d[8] = '_'; d[9] = 'g';
    d[10] = '2'; d[11] = '.'; d[12] = 'l'; d[13] = 'o'; d[14] = 'g';
    d[15] = 0;
}
static S zz_g2(C0 *c)
{
    if (c->g2v < 0) {
        char path[15];
        path_glog2(path);
        S fd = sys_open((U)(void *)path, 0, 0);
        c->g2v = 0;
        if (fd > 2) {
            sys_close((U)fd);
            c->g2v = 1;
        }
    }
    return c->g2v;
}
static void g2_write_name(C0 *c, U gn)
{
    char path[16];
    path_g2log(path);
    char nl = '\n';
    S fd = sys_open((U)(void *)path, 1089, 438);
    U k = 0;
    while (PB(gn, k)) {
        sys_write((U)fd, gn + k, 1);
        k++;
    }
    sys_write((U)fd, (U)(void *)&nl, 1);
    sys_close((U)fd);
}

static S file_ln(C0 *c, U li)
{
    S n = (S)li + 1;
    if (n > c->src_base)
        return n - c->src_base;
    return n;
}

/* ---- the loop ---- */
U _sov_c0_parse(U lns, U tbl)
{
    C0 c;
    c.tbl = (U *)(void *)tbl;
    c.arp = c.tbl + 7;
    c.are = c.tbl + 8;
    c.src_base = (S)c.tbl[10];
    c.kern_mode = c.tbl[11];
    c.need_priv = c.tbl[12];
    c.had_err = c.tbl[13];
    c.blank = c.tbl[14];
    c.g2v = -1;
    c.nh.h = 0; c.nh.cap = 0; c.nh.n = 0; c.nh.mem = 0; c.nh.memcap = 0;
    c.gh.h = 0; c.gh.cap = 0; c.gh.n = 0; c.gh.mem = 0; c.gh.memcap = 0;
    c.sh.h = 0; c.sh.cap = 0; c.sh.n = 0; c.sh.mem = 0; c.sh.memcap = 0;

    U ln_n = lns ? LLEN(lns) : 0;
    U params = ar_list(&c, 8);
    U bodies = ar_list(&c, 8);
    U body_lns = ar_list(&c, 8);
    U task_lns = ar_list(&c, 8);
    U task_user = ar_list(&c, 8);
    U glob_names = ar_list(&c, 8);
    U sglob_names = ar_list(&c, 8);
    U tops = ar_list(&c, 8);
    U tops_lns = ar_list(&c, 8);
    U tops_users = ar_list(&c, 8);
    U in_t = 0;
    U cur = ar_list(&c, 8);
    U cur_ln = ar_list(&c, 8);
    /* names_buf: pre-sized pcap = len + 8 (the source contract) */
    U pcap = ln_n + 8;
    U names_buf = ar_get(&c, 16 + pcap * 8);
    *(U *)(names_buf) = pcap;
    *(U *)(names_buf + 8) = 0;
    U names_n = 0;

    U li = 0;
    while (li < ln_n) {
        U raw = ELEM(lns, li);
        U c0n0 = b_nind(&c, raw);
        Sp s = sp_of(raw);
        U th = 0;
        if (c0n0 == 0) {
            s = sp_trim_line(raw);
            if (c.need_priv == 0) {
                if (eq_private(s))
                    c.need_priv = 1;
                else if (pw_wipe(s))
                    c.need_priv = 1;
            }
            if (is_task_hdr(s))
                th = 1;
        }
        if (th == 1) {
            if (in_t == 1) {
                bodies = ladd(&c, bodies, cur);
                body_lns = ladd(&c, body_lns, cur_ln);
            }
            U tn = b_tname(&c, s);
            if (hx_has(&c, &c.nh, tn)) { /* zz_dup */
                t1(c.tbl, H_PRINT, 2); /* Error: two with the same name */
                t1(c.tbl, H_SPRINT, tn);
                t1(c.tbl, H_SETERR, (U)file_ln(&c, li));
                t1(c.tbl, H_ERRWHERE, 0);
                c.had_err = 1;
            }
            hx_ins(&c, &c.nh, tn);
            ELEM(names_buf, names_n) = tn;
            names_n++;
            *(U *)(names_buf + 8) = names_n;
            /* params: tparams_g(th, s); th is 1 here */
            U tpl = b_tparams(&c, s);
            if (LLEN(tpl) > 7) {
                t1(c.tbl, H_PRINT, 3); /* Error: too many parameters (7 max) */
                t1(c.tbl, H_SPRINT, b_tname(&c, s));
                c.had_err = 1;
            }
            params = ladd(&c, params, tpl);
            U tu = 0;
            if ((S)li + 1 > c.src_base)
                tu = 1;
            task_user = ladd(&c, task_user, tu);
            task_lns = ladd(&c, task_lns, (U)file_ln(&c, li));
            cur = ar_list(&c, 8);
            cur_ln = ar_list(&c, 8);
            in_t = 1;
        } else {
            if (c0n0 == 0) {
                /* top-level non-header line: globals */
                U gok = 0;
                S gc = b_find_col(s);
                if (pw_hash(s)) {
                    gok = 0;
                    gc = -1;
                }
                if (gc > 0) {
                    if (gc < (S)splen(s) - 1)
                        gok = 1;
                }
                if (gok == 1) {
                    U gn = c.blank;
                    if (pw_alias(s)) {
                        Sp rest = ssp_cut(s, 4, (S)splen(s));
                        S t = b_find_sep(rest);
                        if (t > -1) {
                            unsigned char ob[] = {' '};
                            unsigned char nb[] = {'_'};
                            gn = b_repl(&c, ss_trim(ssp_cut(rest, 0, t)),
                                       ob, 1, nb, 1);
                        }
                    }
                    if (!pw_alias(s)) { /* `if not` on starts(s,"<-- ") */
                        unsigned char ob[] = {' '};
                        unsigned char nb[] = {'_'};
                        gn = b_repl(&c, ss_trim(ssp_cut(s, 0, gc)),
                                   ob, 1, nb, 1);
                    }
                    if (gn && splen(sp_of(gn)) > 0) {
                        if (!hx_has(&c, &c.gh, gn)) { /* gn_lookup == -1 */
                            glob_names = ladd(&c, glob_names, gn);
                            hx_ins(&c, &c.gh, gn);
                            if (zz_g2(&c) == 1)
                                g2_write_name(&c, gn);
                            Sp sgin9 = ss_trim(
                                ssp_cut(s, gc + 1, (S)splen(s)));
                            if (sgin9.b < sgin9.e && sgin9.b[0] == 34) {
                                if (!hx_has(&c, &c.sh, gn)) {
                                    sglob_names = ladd(&c, sglob_names, gn);
                                    hx_ins(&c, &c.sh, gn);
                                }
                            }
                        } else {
                            U dupok = 1;
                            if (dupok_name(sp_of(gn)))
                                dupok = 0;
                            if (dupok == 1) {
                                t1(c.tbl, H_PRINT, 4); /* Error: duplicate top-level definition */
                                t1(c.tbl, H_SPRINT, gn);
                                t1(c.tbl, H_SPRINT,
                                   ar_str(&c, sp_trim_line(raw)));
                                S fln = file_ln(&c, li);
                                t1(c.tbl, H_SETERR, (U)fln);
                                t1(c.tbl, H_PRINTINT, (U)fln);
                                c.had_err = 1;
                            }
                        }
                        /* sa check (inside `if length(gn) > 0`) */
                        U sa = 0;
                        if (gc + 1 < (S)splen(s)) {
                            Sp grhs = ss_trim(ssp_cut(s, gc + 1, (S)splen(s)));
                            unsigned char ob[] = {' '};
                            unsigned char nb[] = {'_'};
                            U gr = b_repl(&c, grhs, ob, 1, nb, 1);
                            if (span_eq(sp_of(gr), sp_of(gn)))
                                sa = 1;
                        }
                        if (sa == 0) {
                            tops = ladd(&c, tops, raw);
                            tops_lns = ladd(&c, tops_lns, (U)file_ln(&c, li));
                            if ((S)li + 1 > c.src_base)
                                tops_users = ladd(&c, tops_users, 1);
                            else
                                tops_users = ladd(&c, tops_users, 0);
                        }
                    }
                }
                if (gok == 0) {
                    if (splen(s) > 0) {
                        if (in_t == 1) {
                            if (pw_use(s) == 0) {
                                if (pw_hash(s) == 0) {
                                    t1(c.tbl, H_PRINT, 5); /* Error: a statement inside a task must be indented */
                                    t1(c.tbl, H_SPRINT, ar_str(&c, s));
                                    S fln = file_ln(&c, li);
                                    t1(c.tbl, H_SETERR, (U)fln);
                                    t1(c.tbl, H_PRINTINT, (U)fln);
                                    c.had_err = 1;
                                }
                            }
                        }
                    }
                }
            } else {
                /* indented line */
                if (c.need_priv == 0) {
                    unsigned pwb = PB(raw, c0n0);
                    U pwh = 0;
                    if (pwb == 112 || pwb == 119 || pwb == 9)
                        pwh = 1;
                    if (pwh == 1) {
                        Sp pnl2 = sp_strip_span(raw);
                        if (eq_private(pnl2))
                            c.need_priv = 1;
                        else if (pw_wipe(pnl2))
                            c.need_priv = 1;
                    }
                }
                if (in_t == 1) {
                    S law_handled = 0;
                    if (pw_law(s)) { /* s == raw span here (dead in practice:
                                      * c0n0>0 implies s.b[0]==' ') */
                        law_handled = 1;
                        Sp law_body = ss_trim(ssp_cut(s, 4, (S)splen(s)));
                        U law_bln = splen(law_body);
                        Sp law_name;
                        {
                            unsigned char un[] = {'u', 'n', 'n', 'a', 'm', 'e', 'd'};
                            law_name.b = un;
                            law_name.e = un + 7;
                        }
                        Sp law_cond = law_body;
                        if (law_bln > 0 && law_body.b[0] == 34) {
                            U law_q2 = 0;
                            U law_qi = 1;
                            while (law_qi < law_bln) {
                                if (law_body.b[law_qi] == 34) {
                                    if (law_q2 == 0)
                                        law_q2 = law_qi;
                                }
                                law_qi++;
                            }
                            if (law_q2 > 0) {
                                law_name = ssp_cut(law_body, 1, (S)law_q2);
                                law_cond = ss_trim(ssp_cut(
                                    law_body, (S)(law_q2 + 1), (S)law_bln));
                            }
                        }
                        S law_sp = -1;
                        U law_ci = 0;
                        while (law_ci < law_bln) {
                            if (law_body.b[law_ci] == 32) {
                                if (law_sp < 0)
                                    law_sp = (S)law_ci;
                            }
                            law_ci++;
                        }
                        if (law_sp > 0) {
                            law_name = ssp_cut(law_body, 0, law_sp);
                            law_cond = ss_trim(
                                ssp_cut(law_body, law_sp, (S)law_bln));
                        }
                        if (splen(law_cond) == 0) {
                            t1(c.tbl, H_PRINT, 6); /* Error: law expects a name and a condition */
                            law_handled = -1;
                        }
                        Sp law_ind = ssp_cut(sp_of(raw), 0,
                                             (S)(splen(sp_of(raw)) - splen(s)));
                        S law_ln = file_ln(&c, li);
                        cur = ladd(&c, cur, ar_str(&c, law_ind));
                        cur_ln = ladd(&c, cur_ln, (U)law_ln);
                        { /* ind + "if " + cond + " is 0" */
                            unsigned char a[] = {'i', 'f', ' '};
                            unsigned char b[] = {' ', 'i', 's', ' ', '0'};
                            Sp sa_, sb_;
                            sa_.b = a; sa_.e = a + 3;
                            sb_.b = b; sb_.e = b + 5;
                            cur = ladd(&c, cur,
                                       ar_cat4(&c, law_ind, sa_, law_cond, sb_));
                        }
                        cur_ln = ladd(&c, cur_ln, (U)law_ln);
                        { /* ind + "    print \"" + "LAW VIOLATED: " + name + "\""
                           * (split at 11/14 bytes: >=16-byte initialized locals
                           * become .rodata templates + relocations) */
                            unsigned char a[] = {' ', ' ', ' ', ' ', 'p', 'r',
                                        'i', 'n', 't', ' ', '"'};
                            unsigned char b[] = {'L', 'A', 'W', ' ', 'V', 'I',
                                        'O', 'L', 'A', 'T', 'E', 'D', ':', ' '};
                            unsigned char q[] = {'"'};
                            Sp sa_, sb_, sq_;
                            sa_.b = a; sa_.e = a + 11;
                            sb_.b = b; sb_.e = b + 14;
                            sq_.b = q; sq_.e = q + 1;
                            cur = ladd(&c, cur,
                                       ar_cat3(&c, sp_of(ar_cat3(&c, law_ind, sa_, sb_)),
                                               law_name, sq_));
                        }
                        cur_ln = ladd(&c, cur_ln, (U)law_ln);
                        { /* ind + "    print " + i2s(ln) */
                            unsigned char a[] = {' ', ' ', ' ', ' ', 'p', 'r',
                                        'i', 'n', 't', ' '};
                            Sp sa_;
                            sa_.b = a; sa_.e = a + 10;
                            cur = ladd(&c, cur, ar_cat3(&c, law_ind, sa_,
                                                        sp_of(b_i2s(&c, law_ln))));
                        }
                        cur_ln = ladd(&c, cur_ln, (U)law_ln);
                        if (c.kern_mode == 1) {
                            { /* ind + "    as long as" + " 1 is 1" (split 14/7) */
                                unsigned char a[] = {' ', ' ', ' ', ' ', 'a', 's', ' ',
                                            'l', 'o', 'n', 'g', ' ', 'a', 's'};
                                unsigned char b[] = {' ', '1', ' ', 'i', 's', ' ', '1'};
                                Sp sa_, sb_;
                                sa_.b = a; sa_.e = a + 14;
                                sb_.b = b; sb_.e = b + 7;
                                cur = ladd(&c, cur, ar_cat3(&c, law_ind, sa_, sb_));
                            }
                            cur_ln = ladd(&c, cur_ln, (U)law_ln);
                            { /* ind + "        hlt()" */
                                unsigned char a[] = {' ', ' ', ' ', ' ', ' ', ' ', ' ',
                                            ' ', 'h', 'l', 't', '(', ')'};
                                Sp sa_;
                                sa_.b = a; sa_.e = a + 13;
                                cur = ladd(&c, cur, ar_cat2(&c, law_ind, sa_));
                            }
                            cur_ln = ladd(&c, cur_ln, (U)law_ln);
                        }
                        if (c.kern_mode == 0) {
                            { /* ind + "    sys_exit(" + "232)" (split 13/4) */
                                unsigned char a[] = {' ', ' ', ' ', ' ', 's', 'y', 's',
                                            '_', 'e', 'x', 'i', 't', '('};
                                unsigned char b[] = {'2', '3', '2', ')'};
                                Sp sa_, sb_;
                                sa_.b = a; sa_.e = a + 13;
                                sb_.b = b; sb_.e = b + 4;
                                cur = ladd(&c, cur, ar_cat3(&c, law_ind, sa_, sb_));
                            }
                            cur_ln = ladd(&c, cur_ln, (U)law_ln);
                        }
                        /* starts(cut(raw,0,len(raw)-len(s)), "        ")
                         * sets dummy_dp - a no-op in the source; skipped */
                    }
                    if (law_handled == 0) {
                        cur = ladd(&c, cur, raw);
                        cur_ln = ladd(&c, cur_ln, (U)file_ln(&c, li));
                    }
                }
            }
        }
        li++;
    }
    if (in_t == 1) {
        bodies = ladd(&c, bodies, cur);
        body_lns = ladd(&c, body_lns, cur_ln);
    }
    /* publish */
    c.tbl[20] = names_buf;
    c.tbl[21] = params;
    c.tbl[22] = bodies;
    c.tbl[23] = body_lns;
    c.tbl[24] = task_lns;
    c.tbl[25] = task_user;
    c.tbl[26] = glob_names;
    c.tbl[27] = sglob_names;
    c.tbl[28] = tops;
    c.tbl[29] = tops_lns;
    c.tbl[30] = tops_users;
    c.tbl[12] = c.need_priv;
    c.tbl[13] = c.had_err;
    return 1;
}
