/* Native lord_build: the register-home seeding line pass, C port.
 * 1:1 mirror of lord_build in compilers/linux/compiler.sov: the per-line
 * indent-stack walk (loop-header detection, lb_words tally, colon-span
 * collection with set_span_has dedup and fl_span_newt registration) and
 * the frequency-ordered insertion sort.
 * S25 slice (the inl2 pattern): the tally family is FUSED into the
 * blob.  lb_words + fl_span_tally (the per-word hot path), set_span_has,
 * fl_span_newt, fl_span_count, the repl(cut(...)) name builder and
 * lord_ins are static C mirrors operating directly on the floc epoch
 * tables, which lb_start publishes into lb_tbl data slots 13..20 on
 * every call (flor_range only rebinds/grows those tables between
 * functions, never during one).  .sov i64 '*' lowers to a bare imul
 * (kid_imul_rax_rcx), so two's-complement wrap is bit-identical to
 * uint64 arithmetic and the djb2 mirrors match exactly.
 * Helpers still dispatched behind the caller-provided lb_tbl (Sovren
 * ABI: rdi,rsi,rdx,rcx,r8,r9,r10; result rax):
 *   1 lb_start()       (floc_epoch++, lord_fcnt := 0, publish slots)
 *   2 lb_set_fcnt(n)   (lord_fcnt := n)
 *  10 find_col_q(t)    (quote-bearing lines only - rare)
 *  11 lb_arblk_get()
 *  12 _sov_heap_alloc(n)
 * Slots 3..9 (lb_words/set_span_has/fl_span_newt/fl_span_count/
 * lord_ins/repl/cut) stay REGISTERED by lb_tbl_init for the interpreted
 * fallback and probe copies, but the blob no longer dispatches them.
 * find_col, cfind1, wordchar, digitb and the header prefixes are fused
 * inline; the local lists (cl/ca/cb/stk/on/os) live in the persistent
 * bump arena with the inline _sov_list_new/_sov_list_add content.
 * Sovren integer comparisons are SIGNED.  No external symbols, no
 * relocations, no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef U (*F0)(void);
typedef U (*F1)(U);

enum {
 T_START=1, T_SETFCNT=2, T_LBWORDS=3, T_SPHAS=4, T_FLNEWT=5, T_FLCNT=6,
 T_LORDINS=7, T_REPL=8, T_CUT=9, T_FINDCOLQ=10, T_ARBLK=11, T_ALLOC=12
};
/* lb_tbl layout (U* slots): 0 = count, 1..12 = helpers, then data slots
 * published by lb_start each call:
 * 13 floc_ep, 14 floc_ln, 15 floc_a, 16 floc_b, 17 floc_c, 18 floc_ce,
 * 19 floc_cap, 20 floc_epoch (post-increment value). */

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }

#define MISS ((U)-1)
#define LLEN(x) (*(U*)((x)+8))
#define ELEM(x,i) (*(U*)((x)+16+(U)(i)*8))
#define PB(s,i) (*(const unsigned char*)((s)+(U)(i)))

static inline U xstrlen(const unsigned char *s){ U n=0; while (s[n]) n++; return n; }
static inline U slen(U s){ return s<4096 ? 0 : xstrlen((const unsigned char*)s); }

static U cfind1(const unsigned char *t, unsigned ch){
    if (!t) return MISS;
    for (U i=0; t[i]; i++) if (t[i]==ch) return i;
    return MISS;
}

/* persistent bump arena */
#define AR_CHUNK 1048576
static U ar_grow(U *t, U *arp, U *are){
    U p = t1(t, T_ALLOC, AR_CHUNK);
    *arp = p; *are = p + AR_CHUNK;
    return p;
}
static inline U ar_get(U *t, U *arp, U *are, U n){
    if (*arp + n > *are) ar_grow(t, arp, are);
    U p = *arp; *arp = p + n; return p;
}
static inline U lnew(U *t, U *arp, U *are){
    U b = ar_get(t, arp, are, 208);
    *(U*)(b) = 24;
    *(U*)(b + 8) = 0;
    return b;
}
static inline U ladd(U lst, U item, U *t, U *arp, U *are){
    if (lst){
        U ln = *(U*)(lst + 8);
        U cap = *(U*)(lst);
        if (ln < cap){
            *(U*)(lst + 16 + ln * 8) = item;
            *(U*)(lst + 8) = ln + 1;
            return lst;
        }
    }
    U cap = 24, len = 0;
    if (lst){ cap = *(U*)(lst); len = *(U*)(lst + 8); if (cap < 24) cap = 24; }
    U nc = cap * 2;
    U b = ar_get(t, arp, are, 16 + nc * 8);
    *(U*)(b) = nc;
    *(U*)(b + 8) = len;
    for (U i = 0; i < len; i++) *(U*)(b + 16 + i * 8) = *(U*)(lst + 16 + i * 8);
    *(U*)(b + 16 + len * 8) = item;
    *(U*)(b + 8) = len + 1;
    return b;
}

/* find_col content: quote-aware first colon */
static U find_colf(U ts, U *t){
    if (cfind1((const unsigned char*)ts, 34) == MISS)
        return cfind1((const unsigned char*)ts, 58);
    return t1(t, T_FINDCOLQ, ts);
}
/* header prefixes, needles on the stack */
static U hdr_long(const unsigned char *s){
    unsigned char p[11];
    p[0]=97;p[1]=115;p[2]=32;p[3]=108;p[4]=111;p[5]=110;p[6]=103;p[7]=32;p[8]=97;p[9]=115;p[10]=32;
    for (U i=0;i<11;i++) if (s[i]!=p[i]) return 0;
    return 1;
}
static U hdr_while(const unsigned char *s){
    unsigned char p[6];
    p[0]=119;p[1]=104;p[2]=105;p[3]=108;p[4]=101;p[5]=32;
    for (U i=0;i<6;i++) if (s[i]!=p[i]) return 0;
    return 1;
}
static U hdr_do(const unsigned char *s){
    unsigned char p[9];
    p[0]=100;p[1]=111;p[2]=32;p[3]=119;p[4]=104;p[5]=105;p[6]=108;p[7]=101;p[8]=32;
    for (U i=0;i<9;i++) if (s[i]!=p[i]) return 0;
    return 1;
}

/* ---- fused tally family (S25) ---- */

/* epoch table view published by lb_start */
typedef struct {
    U *ep;   U *lns;  U *as;   U *bs;   U *cs;   U *ce;
    U cap;   U epoch;
} Fl;

/* kid_wordchar: b==95, or unsigned range [48,58)/[65,91)/[97,123) */
static inline int wordchar(unsigned b){
    if (b == 95) return 1;
    if (b < 48) return 0;
    if (b < 58) return 1;
    if (b < 65) return 0;
    if (b < 91) return 1;
    if (b < 97) return 0;
    if (b < 123) return 1;
    return 0;
}
/* digitb: [48,57] */
static inline int digitb(unsigned b){
    if (b >= 48) if (b <= 57) return 1;
    return 0;
}

/* djb2 over ln[a,b) with spaces read as '_' (i64 wrap == uint64 wrap) */
static inline U span_hash(const unsigned char *ln, U a, U b){
    U h = 5381;
    for (U i = a; i < b; i++){
        U cb = PB(ln, i);
        if (cb == 32) cb = 95;
        h = h * 33 + cb;
    }
    return h;
}
/* span equality, both sides space-normalized */
static inline int sp_eq(const unsigned char *l1, U a1, U b1,
                        const unsigned char *l2, U a2, U b2){
    if (b1 - a1 != b2 - a2) return 0;
    U n = b1 - a1;
    for (U i = 0; i < n; i++){
        U c1 = PB(l1, a1 + i); if (c1 == 32) c1 = 95;
        U c2 = PB(l2, a2 + i); if (c2 == 32) c2 = 95;
        if (c2 != c1) return 0;
    }
    return 1;
}

/* set_span_has: probe the gh name-set table (stored bytes raw) */
static int sp_has(U gh, U gc, const unsigned char *ln, U a, U b){
    U h = span_hash(ln, a, b);
    U sl = h & (gc - 1);
    for (;;){
        U cur = *(U*)(gh + sl * 8);
        if (cur == 0) return 0;
        if (slen(cur) == b - a){
            int eq = 1;
            U n = b - a;
            U i = 0;
            while (i < n){
                U cb = PB(ln, a + i);
                if (cb == 32) cb = 95;
                if (PB(cur, i) != cb){ eq = 0; break; }
                i++;
            }
            if (eq == 1) return 1;
        }
        sl = sl + 1;
        if (sl == gc) sl = 0;
    }
}

/* fl_span_tally: insert-with-w or accumulate-w (never touches ce) */
static void tally(Fl *f, const unsigned char *ln, U a, U b, U w){
    U h = span_hash(ln, a, b);
    U msk = f->cap - 1;
    U cs = h & msk;
    U g = 0;
    while (g <= msk){
        if (f->ep[cs] != f->epoch){
            f->ep[cs] = f->epoch;
            f->lns[cs] = (U)(void*)ln;
            f->as[cs] = a;
            f->bs[cs] = b;
            f->cs[cs] = w;
            return;
        }
        if (sp_eq(ln, a, b, (const unsigned char*)(void*)f->lns[cs], f->as[cs], f->bs[cs])){
            f->cs[cs] = f->cs[cs] + w;
            return;
        }
        cs = (cs + 1) & msk;
        g++;
    }
}

/* fl_span_newt: register a candidate span this epoch (1 = fresh) */
static int newt(Fl *f, const unsigned char *ln, U a, U b){
    U h = span_hash(ln, a, b);
    U msk = f->cap - 1;
    U cs = h & msk;
    U g = 0;
    while (g <= msk){
        if (f->ep[cs] != f->epoch){
            f->ep[cs] = f->epoch;
            f->lns[cs] = (U)(void*)ln;
            f->as[cs] = a;
            f->bs[cs] = b;
            f->cs[cs] = 0;
            f->ce[cs] = f->epoch;
            return 1;
        }
        if (sp_eq(ln, a, b, (const unsigned char*)(void*)f->lns[cs], f->as[cs], f->bs[cs])){
            if (f->ce[cs] == f->epoch) return 0;
            f->ce[cs] = f->epoch;
            return 1;
        }
        cs = (cs + 1) & msk;
        g++;
    }
    return 1;
}

/* fl_span_count: the accumulated tally for a span (0 when absent) */
static U fcount(Fl *f, const unsigned char *ln, U a, U b){
    U h = span_hash(ln, a, b);
    U msk = f->cap - 1;
    U cs = h & msk;
    U g = 0;
    while (g <= msk){
        if (f->ep[cs] != f->epoch) return 0;
        if (sp_eq(ln, a, b, (const unsigned char*)(void*)f->lns[cs], f->as[cs], f->bs[cs]))
            return f->cs[cs];
        cs = (cs + 1) & msk;
        g++;
    }
    return 0;
}

/* lb_words: wordchar-run scan, digit-led runs skipped, per-word tally */
static void lb_words_f(Fl *f, const unsigned char *ln, U ai, U lnn, U w){
    U i = ai;
    U ws = MISS;
    while (i <= lnn){
        unsigned ch = 0;
        if (i < lnn) ch = PB(ln, i);
        if (wordchar(ch)){
            if (ws == MISS) ws = i;
        } else {
            if (ws != MISS){
                if (digitb(PB(ln, ws)) == 0) tally(f, ln, ws, i, w);
                ws = MISS;
            }
        }
        i++;
    }
}

/* repl(cut(ln,a,b)," ","_"): the span with spaces as underscores */
static U name_build(U *t, U *arp, U *are, const unsigned char *ln, U a, U b){
    U n = b - a;
    U p = ar_get(t, arp, are, n + 1);
    for (U i = 0; i < n; i++){
        U c = PB(ln, a + i);
        if (c == 32) c = 95;
        *(unsigned char*)(p + i) = (unsigned char)c;
    }
    *(unsigned char*)(p + n) = 0;
    return p;
}

/* lord_ins: insert v at p (in-place tail shift when capacity is free,
 * doubling rebuild otherwise; capacity never leaks into output) */
static U lord_ins_f(U *t, U *arp, U *are, U l, U p, U v){
    if (l){
        U n = LLEN(l);
        if (n < *(U*)(l)){
            U i = n;
            while ((long long)i > (long long)p){
                *(U*)(l + 16 + i * 8) = *(U*)(l + 16 + (i - 1) * 8);
                i--;
            }
            *(U*)(l + 16 + p * 8) = v;
            *(U*)(l + 8) = n + 1;
            return l;
        }
    }
    U cap = 24, len = 0;
    if (l){ cap = *(U*)(l); len = LLEN(l); if (cap < 24) cap = 24; }
    U nc = cap * 2;
    if (nc < 24) nc = 24;
    U b = ar_get(t, arp, are, 16 + nc * 8);
    *(U*)(b) = nc;
    U out = 0;
    U i = 0;
    while (i < len){
        if (i == p){ *(U*)(b + 16 + out * 8) = v; out++; }
        *(U*)(b + 16 + out * 8) = *(U*)(l + 16 + i * 8);
        out++;
        i++;
    }
    if ((long long)p >= (long long)len){ *(U*)(b + 16 + out * 8) = v; out++; }
    *(U*)(b + 8) = out;
    return b;
}

/* twin entry: rdi=lb_fb, rsi=lb_gh, rdx=lb_gc, rcx=lb_fc, r8=lb_np, r9=lb_tbl */
U lord_build_native(U fb, U gh, U gc, U fc, U np, U tbl){
    U *t = (U*)tbl;
    U blk = t0(t, T_ARBLK);
    U *arp = (U*)blk, *are = (U*)(blk + 8);
    t0(t, T_START);
    Fl fl;
    fl.ep = (U*)(void*)t[13];
    fl.lns = (U*)(void*)t[14];
    fl.as = (U*)(void*)t[15];
    fl.bs = (U*)(void*)t[16];
    fl.cs = (U*)(void*)t[17];
    fl.ce = (U*)(void*)t[18];
    fl.cap = t[19];
    fl.epoch = t[20];
    U fcnt = 0;
    U cl = lnew(t, arp, are);
    U ca = lnew(t, arp, are);
    U cb = lnew(t, arp, are);
    U stk = lnew(t, arp, are);
    U stkn = 0;
    U n = LLEN(fb);
    for (U j = 0; j < n; j++){
        U ln = ELEM(fb, j);
        U ai = 0;
        while (PB(ln, ai) == 32) ai++;
        U pop = 1;
        while (pop == 1){
            pop = 0;
            if (stkn > 0){
                if (ELEM(stk, stkn - 1) >= ai){
                    stkn = stkn - 1;
                    *(U*)(stk + 8) = stkn;
                    pop = 1;
                }
            }
        }
        U hdr = 0;
        unsigned b0 = PB(ln, ai);
        if (b0 == 97){
            if (hdr_long((const unsigned char*)(ln + ai)) == 1) hdr = 1;
        }
        if (b0 == 119){
            if (hdr_while((const unsigned char*)(ln + ai)) == 1) hdr = 1;
        }
        if (b0 == 100){
            if (hdr_do((const unsigned char*)(ln + ai)) == 1) hdr = 1;
        }
        U w = 1;
        if (stkn > 0) w = 10;
        if (hdr == 1) w = 10;
        U lnn = slen(ln);
        lb_words_f(&fl, (const unsigned char*)(void*)ln, ai, lnn, w);
        unsigned lb_b0 = PB(ln, ai);
        if (lb_b0 != 0 && lb_b0 != 35 && lb_b0 != 34){
            U gc2 = find_colf(ln, t);
            if ((long long)gc2 > (long long)ai && (long long)gc2 < (long long)(lnn - 1)){
                U eb = gc2;
                U dun = 0;
                while (dun == 0){
                    if ((long long)eb <= (long long)ai) dun = 1;
                    if (dun == 0){
                        if (PB(ln, eb - 1) == 32) eb = eb - 1;
                        else dun = 1;
                    }
                }
                if ((long long)eb > (long long)ai){
                    if (sp_has(gh, gc, (const unsigned char*)(void*)ln, ai, eb) == 0){
                        if (newt(&fl, (const unsigned char*)(void*)ln, ai, eb) == 1){
                            fcnt = fcnt + 1;
                            cl = ladd(cl, ln, t, arp, are);
                            ca = ladd(ca, ai, t, arp, are);
                            cb = ladd(cb, eb, t, arp, are);
                        }
                    }
                }
            }
        }
        if (hdr == 1){
            stk = ladd(stk, ai, t, arp, are);
            stkn = stkn + 1;
        }
    }
    t1(t, T_SETFCNT, fcnt);
    if ((long long)(fcnt + np) < 6) return 0;
    U cln = LLEN(cl);
    if (cln < 32){
        /* small bodies: the classic position scan + middle insert is
         * cheaper than the sort scaffolding (mirrors the interpreted
         * threshold path; identical order either way). */
        U on = lnew(t, arp, are);
        U os = lnew(t, arp, are);
        for (U k = 0; k < cln; k++){
            U ln = ELEM(cl, k);
            U a = ELEM(ca, k);
            U b = ELEM(cb, k);
            U sc = fcount(&fl, (const unsigned char*)(void*)ln, a, b);
            U nm = name_build(t, arp, are, (const unsigned char*)(void*)ln, a, b);
            U pos = LLEN(on);
            for (U q = 0; q < pos; q++){
                if ((long long)ELEM(os, q) < (long long)sc){
                    pos = q;
                    q = LLEN(on);
                }
            }
            on = lord_ins_f(t, arp, are, on, pos, nm);
            os = lord_ins_f(t, arp, are, os, pos, sc);
        }
        return on;
    }
    /* Arrival order first, then one bottom-up merge sort by (score desc,
     * arrival asc) - the exact total order the old per-item position scan
     * plus middle insert produced, without its O(n^2) scan+shift per
     * distinct target.  Mirrors the interpreted lord_build tail. */
    U an = lnew(t, arp, are);
    U as2 = lnew(t, arp, are);
    for (U k = 0; k < cln; k++){
        U ln = ELEM(cl, k);
        U a = ELEM(ca, k);
        U b = ELEM(cb, k);
        U sc = fcount(&fl, (const unsigned char*)(void*)ln, a, b);
        U nm = name_build(t, arp, are, (const unsigned char*)(void*)ln, a, b);
        an = ladd(an, nm, t, arp, are);
        as2 = ladd(as2, sc, t, arp, are);
    }
    U n2 = LLEN(an);
    /* index arrays in list layout ([hdr 16][n2 * 8]) so ELEM addressing
     * matches the collected lists */
    U src = ar_get(t, arp, are, 16 + n2 * 8);
    U tmp = ar_get(t, arp, are, 16 + n2 * 8);
    for (U i = 0; i < n2; i++) ELEM(src, i) = i;
    for (U w = 1; w < n2; w <<= 1){
        for (U i = 0; i < n2; ){
            U lo = i;
            U mid = i + w < n2 ? i + w : n2;
            U hi = i + 2*w < n2 ? i + 2*w : n2;
            U a2 = lo, b2 = mid, o = lo;
            while (o < hi){
                U ta = 0;
                if (a2 < mid && b2 >= hi) ta = 1;
                if (a2 < mid && b2 < hi){
                    U va = ELEM(as2, ELEM(src, a2));
                    U vb = ELEM(as2, ELEM(src, b2));
                    /* score desc; the left run holds the earlier arrivals,
                     * so >= keeps the tie order stable (signed, like the
                     * old scan). */
                    if ((long long)va >= (long long)vb) ta = 1;
                }
                if (ta) { ELEM(tmp, o) = ELEM(src, a2); a2++; }
                else    { ELEM(tmp, o) = ELEM(src, b2); b2++; }
                o++;
            }
            i = hi;
        }
        U sw = src; src = tmp; tmp = sw;
    }
    U on = lnew(t, arp, are);
    U os = lnew(t, arp, are);
    for (U i = 0; i < n2; i++){
        U j = ELEM(src, i);
        on = ladd(on, ELEM(an, j), t, arp, are);
        os = ladd(os, ELEM(as2, j), t, arp, are);
    }
    return on;
}
