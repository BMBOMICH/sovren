/* Native st_build: the statement-table builder, C port.
 * 1:1 mirror of st_build in compilers/linux/compiler.sov: the two per-line
 * passes (strip_span + immutable-prefix strip + find_col + name cut +
 * expr_atom_word gate, then the return/assignment edge pass) and the
 * final BFS queue walk over st_edges. The graph helpers that mutate the
 * global tables (st_node, st_var, st_edge, st_expr, st_scratch,
 * mark_fn_str, strip, cut, find_col_q, expr_atom) stay interpreted or
 * twinned behind the caller-provided sb_tbl (Sovren ABI: args
 * rdi,rsi,rdx,rcx,r8,r9,r10; result rax):
 *   1 sb_names_get()  2 sb_bodies_get()  3 sb_params_get()
 *   4 sb_reset()      (st_need/st_edges/st_done := fresh lists)
 *   5 st_node(k)      6 st_var(name)     7 st_edge(src, dst)
 *   8 st_expr(e, dep) 9 st_scratch(n)   10 sb_vars_reset()
 *  11 sb_need_get()  12 sb_edges_get()  13 sb_done_get()
 *  14 mark_fn_str(nm) 15 strip(s)       16 expr_atom(e)
 *  17 find_col_q(t)  18 cut(t,a,b)      19 sb_arblk_get()
 *  20 _sov_heap_alloc(n)
 * strip_span, find_col, cfind1, starts, cut_full's content and
 * expr_atom_word's word gates are fused inline; cut copies and the queue
 * list live in the persistent bump arena ([arp][are] block, same model
 * as the collect_body twin).  Sovren integer comparisons are SIGNED.
 * No external symbols, no relocations, no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);
typedef U (*F3)(U,U,U);

enum {
 T_NAMES=1, T_BODIES=2, T_PARAMS=3, T_RESET=4, T_STNODE=5, T_STVAR=6,
 T_STEDGE=7, T_STEXPR=8, T_STSCRATCH=9, T_VARSRESET=10, T_NEED=11,
 T_EDGES=12, T_DONE=13, T_MARKFNS=14, T_STRIP=15, T_EATOM=16,
 T_FINDCOLQ=17, T_CUT=18, T_ARBLK=19, T_ALLOC=20,
 T_STVFIND=21, T_SGLOOKUP=22, T_SFLOOKUP=23, T_NMLOOKUP=24,
 T_SPLITARGS=25, T_LISTNEW=26, T_RETPAR=27, T_STIDS=28
};

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }
static inline U t3(U *t, U i, U a, U b, U c){ return ((F3)t[i])(a,b,c); }

#define MISS ((U)-1)
#define LLEN(x) (*(U*)((x)+8))
#define ELEM(x,i) (*(U*)((x)+16+(U)(i)*8))
#define PB(s,i) (*(const unsigned char*)((s)+(U)(i)))

static inline U xstrlen(const unsigned char *s){ U n=0; while (s[n]) n++; return n; }
static inline U slen(U s){ return s<4096 ? 0 : xstrlen((const unsigned char*)s); }

/* cfind1: first index of byte ch in the NUL-terminated t, else -1 */
static U cfind1(const unsigned char *t, unsigned ch){
    if (!t) return MISS;
    for (U i=0; t[i]; i++) if (t[i]==ch) return i;
    return MISS;
}
static int xstreq(const unsigned char *a, const unsigned char *b){
    if (!a && !b) return 1;
    if (!a || !b) return 0;
    U i=0;
    while (a[i]==b[i]){ if (!a[i]) return 1; i++; }
    return 0;
}
/* needle comparisons WITHOUT string literals (the blob must carry no
 * .rodata and no relocations): fixed byte-sequence matches */
static int eq_blank(const unsigned char *e){
    return e[0]==98&&e[1]==108&&e[2]==97&&e[3]==110&&e[4]==107&&e[5]==0;
}
static int eq_as(const unsigned char *e){
    return e[0]==97&&e[1]==115&&e[2]==0;
}
static int eq_addr_of(const unsigned char *e){
    return e[0]==97&&e[1]==100&&e[2]==100&&e[3]==114&&e[4]==95&&e[5]==111&&e[6]==102&&e[7]==0;
}
static int eq_length(const unsigned char *e){
    return e[0]==108&&e[1]==101&&e[2]==110&&e[3]==103&&e[4]==116&&e[5]==104&&e[6]==0;
}
static int eq_spawn(const unsigned char *e){
    return e[0]==115&&e[1]==112&&e[2]==97&&e[3]==119&&e[4]==110&&e[5]==0;
}
/* starts(t, "immutable ") - needle built on the stack (no .rodata) */
static U starts_immutable(const unsigned char *t){
    if (!t) return 0;
    unsigned char pat[10];
    pat[0]=105;pat[1]=109;pat[2]=109;pat[3]=117;pat[4]=116;pat[5]=97;pat[6]=98;pat[7]=108;pat[8]=101;pat[9]=32;
    for (U i=0;i<10;i++) if (t[i]!=pat[i]) return 0;
    return 1;
}
/* starts(t, "return ") - needle built on the stack */
static U starts_return(const unsigned char *t){
    if (!t) return 0;
    unsigned char pat[7];
    pat[0]=114;pat[1]=101;pat[2]=116;pat[3]=117;pat[4]=114;pat[5]=110;pat[6]=32;
    for (U i=0;i<7;i++) if (t[i]!=pat[i]) return 0;
    return 1;
}

/* persistent bump arena (1 MiB chunks via _sov_heap_alloc; the [arp][are]
 * state lives in the interpreter-side block so it persists across calls) */
#define AR_CHUNK 1048576
/* oversized requests get their own full-size chunk (see native_cxread.c:
 * a fixed-AR_CHUNK allocation left big list tails past the chunk end). */
static U ar_grow(U *t, U *arp, U *are, U n){
    U want = AR_CHUNK;
    if (want < n)
        want = n;
    U p = t1(t, T_ALLOC, want);
    *arp = p; *are = p + want;
    return p;
}
static inline U ar_get(U *t, U *arp, U *are, U n){
    if (*arp + n > *are) ar_grow(t, arp, are, n);
    U p = *arp; *arp = p + n; return p;
}

/* cut_full content: interior pointer when b==length(t), arena copy when
 * both bounds are interior (same answer as the runtime task; the exotic
 * out-of-range shapes route to the table's cut) */
static U cutf(U ts, U a, U b, U *t, U *arp, U *are){
    U tn = slen(ts);
    if (b == tn && a != MISS && a <= b) return ts + a;
    if (a != MISS && b >= a && b <= tn){
        U n = b - a;
        U d = ar_get(t, arp, are, n + 1);
        for (U i = 0; i < n; i++) *(unsigned char*)(d + i) = PB(ts, a + i);
        *(unsigned char*)(d + n) = 0;
        return d;
    }
    return t3(t, T_CUT, ts, a, b);
}

/* always-copy variant for DESTRUCTIVE consumers: split_args NUL-pokes the
 * span ends, so the cut must never be an interior pointer into the parsed
 * source (the interpreted call site passes a fresh `cut` copy - same
 * contract here). */
static U cutf_copy(U ts, U a, U b, U *t, U *arp, U *are){
    U tn = slen(ts);
    if (a != MISS && b >= a && b <= tn){
        U n = b - a;
        U d = ar_get(t, arp, are, n + 1);
        for (U i = 0; i < n; i++) *(unsigned char*)(d + i) = PB(ts, a + i);
        *(unsigned char*)(d + n) = 0;
        return d;
    }
    return t3(t, T_CUT, ts, a, b);
}

/* strip_span content: leading-space trim returning interior pointers;
 * tab or dirty tail routes to the interpreted strip (allocates) */
static U strip_spanf(U ts, U *t){
    if (ts == 0) return 0;
    U a = 0;
    while (PB(ts, a) == 32) a++;
    if (PB(ts, a) == 9) return t1(t, T_STRIP, ts);
    U s = ts + a;
    U n = slen(s);
    if (n == 0) return s;
    if (PB(s, n - 1) < 33) return t1(t, T_STRIP, ts);
    return s;
}

/* find_col content */
static U find_colf(U ts, U *t){
    if (cfind1((const unsigned char*)ts, 34) == MISS)
        return cfind1((const unsigned char*)ts, 58);
    return t1(t, T_FINDCOLQ, ts);
}

/* expr_atom_word content: expr_atom via the table + the word gates */
static U atom_wordf(U e, U *t){
    if (t1(t, T_EATOM, e) == 0) return 0;
    const unsigned char *w = (const unsigned char*)e;
    unsigned c = w[0];
    if (c > 47 && c < 58) return 0;
    if (c == 98 && eq_blank(w)) return 0;
    if (c == 97){
        if (eq_as(w)) return 0;
        if (eq_addr_of(w)) return 0;
    }
    if (c == 108 && eq_length(w)) return 0;
    if (c == 115 && eq_spawn(w)) return 0;
    return 1;
}

/* ---- st_expr port (compiler.sov:12707).  The trim/scan/literal/lane
 * machinery is fused; the hash-state lookups (stv_find, sg_lookup,
 * sf_lookup, nm_lookup), expr_atom, split_args and the two global list
 * reads (ret_par, st_ids) go through the table.  scut(e,0,lp) is cutf +
 * T_STRIP: identical content, one extra alloc on a rare path.  Sovren
 * comparisons are SIGNED; cut/split_args are destructive on fresh cuts
 * only (same discipline as the interpreted call site). ---- */
static int starts_needle(const unsigned char *p, U en, const unsigned char *n, U ln){
    if (en < ln) return 0;
    for (U i = 0; i < ln; i++) if (p[i] != n[i]) return 0;
    return 1;
}
static int tail_needle(const unsigned char *p, U en, U off, const unsigned char *n, U ln){
    if ((long long)off < 0) return 0;
    if (off + ln > en) return 0;
    for (U i = 0; i < ln; i++) if (p[off + i] != n[i]) return 0;
    return 1;
}
/* licm2_match: index of the ')' matching the '(' at p (quote-aware), -1 */
static U licm2_matchf(U es, U pp){
    const unsigned char *p = (const unsigned char*)es;
    U n = slen(es);
    long long d = 0;
    U i = pp;
    while (i < n){
        unsigned b = p[i];
        if (b == 34){
            i++;
            while (i < n){
                unsigned c = p[i];
                if (c == 92){ i += 2; continue; }
                i++;
                if (c == 34) break;
            }
            continue;
        }
        if (b == 40){ d++; i++; continue; }
        if (b == 41){
            d--;
            if (d == 0) return i;
            i++;
            continue;
        }
        i++;
    }
    return MISS;
}
/* is_lit: len>=2, first and last byte are '"' */
static int is_litf(const unsigned char *p, U en){
    if (en < 2) return 0;
    return p[0] == 34 && p[en - 1] == 34;
}
static U sx(U *t, U e0, U dep, U *arp, U *are){
    if ((long long)dep > 32) return 0;
    U e = e0, en = slen(e0);
    const unsigned char *p = (const unsigned char*)e;
    if (en > 0){
        unsigned tb = p[en - 1];
        if (tb == 32 || tb == 9 || tb == 10 || tb == 13){
            e = t1(t, T_STRIP, e0);
            en = slen(e);
            p = (const unsigned char*)e;
        } else {
            unsigned hb = p[0];
            if (hb == 32 || hb == 9 || hb == 10 || hb == 13){
                U sk = 0;
                while (sk < en){
                    unsigned cb = p[sk];
                    if (cb != 32 && cb != 9 && cb != 10 && cb != 13) break;
                    sk++;
                }
                e = e0 + sk; en -= sk; p = (const unsigned char*)e;
            }
        }
    }
    unsigned char atx[9], aptr[8], satx[9], saptr[8];
    atx[0]=97;atx[1]=115;atx[2]=32;atx[3]=116;atx[4]=101;atx[5]=120;atx[6]=116;atx[7]=32;atx[8]=0;
    aptr[0]=97;aptr[1]=115;aptr[2]=32;aptr[3]=112;aptr[4]=116;aptr[5]=114;aptr[6]=32;aptr[7]=0;
    satx[0]=32;satx[1]=97;satx[2]=115;satx[3]=32;satx[4]=116;satx[5]=101;satx[6]=120;satx[7]=116;satx[8]=0;
    saptr[0]=32;saptr[1]=97;saptr[2]=115;saptr[3]=32;saptr[4]=112;saptr[5]=116;saptr[6]=114;saptr[7]=0;
    if (is_litf(p, en)) return 1;
    if (starts_needle(p, en, atx, 8)) return 1;
    if (starts_needle(p, en, aptr, 7)) return 1;
    if (en > 8){ if (tail_needle(p, en, en - 8, satx, 8)) return 1; }
    if (en > 7){ if (tail_needle(p, en, en - 7, saptr, 7)) return 1; }
    if (en > 1){
        if (p[0] == 40){
            if (licm2_matchf(e, 0) == (long long)(en - 1))
                return sx(t, cutf(e, 1, en - 1, t, arp, are), dep + 1, arp, are);
        }
    }
    if (t1(t, T_EATOM, e) == 1){
        unsigned c0 = p[0];
        if (c0 > 47 && c0 < 58) return 0;
        U vi = t1(t, T_STVFIND, e);
        if ((long long)vi >= 0){
            U ids = t0(t, T_STIDS);
            return *(U*)(ids + 16 + vi * 8);
        }
        if ((long long)t1(t, T_SGLOOKUP, e) >= 0) return 1;
        return 0;
    }
    U lp = cfind1(p, 40);
    if ((long long)lp > 0){
        if (licm2_matchf(e, lp) == (long long)(en - 1)){
            U nm = cutf(e, 0, lp, t, arp, are);
            nm = t1(t, T_STRIP, nm);
            if (t1(t, T_EATOM, nm) == 1){
                if ((long long)t1(t, T_SFLOOKUP, nm) >= 0) return 1;
                U fi = t1(t, T_NMLOOKUP, nm);
                if ((long long)fi >= 0){
                    U rp = t0(t, T_RETPAR);
                    U pk = *(U*)(rp + 16 + fi * 8);
                    if ((long long)pk >= 0){
                        U args = t1(t, T_LISTNEW, 0);
                        args = t2(t, T_SPLITARGS, cutf_copy(e, lp + 1, en - 1, t, arp, are), args);
                        U an = LLEN(args);
                        if ((long long)pk < (long long)an)
                            return sx(t, ELEM(args, pk), dep + 1, arp, are);
                    }
                    return fi + 2;
                }
            }
        }
    }
    return 0;
}

/* twin entry: rdi=sb_tbl */
U st_build_native(U tbl){
    U *t = (U*)tbl;
    U blk = t0(t, T_ARBLK);
    U *arp = (U*)blk, *are = (U*)(blk + 8);
    /* phase 0: reset the three global tables, seed two nodes */
    t0(t, T_RESET);
    t1(t, T_STNODE, 0);
    t1(t, T_STNODE, 0);
    U names = t0(t, T_NAMES);
    U bodies = t0(t, T_BODIES);
    U params = t0(t, T_PARAMS);
    U nn = LLEN(names);
    for (U fi = 0; fi < nn; fi++) t1(t, T_STNODE, MISS);
    /* per function: params, then the two line passes */
    for (U fi = 0; fi < nn; fi++){
        t0(t, T_VARSRESET);
        U bl = ELEM(bodies, fi);
        U ps = ELEM(params, fi);
        U psn = LLEN(ps);
        for (U pi = 0; pi < psn; pi++){
            U vi = t1(t, T_STVAR, ELEM(ps, pi));
            t2(t, T_STEDGE, 0, vi);
        }
        U bln = LLEN(bl);
        U scr = t1(t, T_STSCRATCH, bln);
        for (U bi = 0; bi < bln; bi++){
            U line = strip_spanf(ELEM(bl, bi), t);
            if (starts_immutable((const unsigned char*)line) == 1)
                line = strip_spanf(cutf(line, 10, slen(line), t, arp, are), t);
            U co = find_colf(line, t);
            *(U*)(scr + 16 + bi * 24) = line;
            *(U*)(scr + 24 + bi * 24) = co;
            U nm = 0;
            if ((long long)co > 0){
                nm = cutf(line, 0, co, t, arp, are);
                if (PB(nm, co - 1) < 33) nm = t1(t, T_STRIP, nm);
                if (atom_wordf(nm, t) == 0) nm = 0;
            }
            *(U*)(scr + 32 + bi * 24) = nm;
            if (nm != 0) t1(t, T_STVAR, nm);
        }
        for (U bi = 0; bi < bln; bi++){
            U line = *(U*)(scr + 16 + bi * 24);
            U co = *(U*)(scr + 24 + bi * 24);
            U nm = *(U*)(scr + 32 + bi * 24);
            if (starts_return((const unsigned char*)line) == 1){
                U e = sx(t, cutf(line, 7, slen(line), t, arp, are), 0, arp, are);
                t2(t, T_STEDGE, e, fi + 2);
            } else if ((long long)co > 0 && nm != 0){
                U vn = t1(t, T_STVAR, nm);
                U e = sx(t, cutf(line, co + 1, slen(line), t, arp, are), 0, arp, are);
                t2(t, T_STEDGE, e, vn);
            }
        }
    }
    /* queue walk: BFS from node 1 over the final edge lists */
    U need = t0(t, T_NEED);
    U edges = t0(t, T_EDGES);
    U done = t0(t, T_DONE);
    U queue = ar_get(t, arp, are, 16 + 24 * 8);
    *(U*)(queue) = 24;
    *(U*)(queue + 8) = 1;
    *(U*)(queue + 16) = 1;
    *(U*)(done + 24) = 1;
    U qi = 0;
    while (qi < LLEN(queue)){
        U ni = ELEM(queue, qi);
        U adj = ELEM(edges, ni);
        U an = LLEN(adj);
        for (U ai = 0; ai < an; ai++){
            U dst = ELEM(adj, ai);
            U nd = *(U*)(need + 16 + dst * 8);
            if ((long long)nd > 0){
                nd = nd - 1;
                *(U*)(need + 16 + dst * 8) = nd;
            }
            if ((long long)nd <= 0){
                if (*(U*)(done + 16 + dst * 8) == 0){
                    *(U*)(done + 16 + dst * 8) = 1;
                    U ln = LLEN(queue);
                    U cap = *(U*)(queue);
                    if (ln < cap){
                        *(U*)(queue + 16 + ln * 8) = dst;
                        *(U*)(queue + 8) = ln + 1;
                    } else {
                        U nc2 = cap * 2;
                        U b2 = ar_get(t, arp, are, 16 + nc2 * 8);
                        *(U*)(b2) = nc2;
                        *(U*)(b2 + 8) = ln;
                        for (U i2 = 0; i2 < ln; i2++) *(U*)(b2 + 16 + i2 * 8) = *(U*)(queue + 16 + i2 * 8);
                        *(U*)(b2 + 16 + ln * 8) = dst;
                        *(U*)(b2 + 8) = ln + 1;
                        queue = b2;
                    }
                    if (dst >= 2 && dst < nn + 2)
                        t1(t, T_MARKFNS, ELEM(names, dst - 2));
                }
            }
        }
        qi++;
    }
    return 0;
}
