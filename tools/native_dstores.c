/* Native dce_stores — C port of dce_stores in compilers/shared/cx86_p3.sov.
 * Global-store dead-code elimination: kgrel patches into all-stores globals
 * whose store site is not the `mov [rip+..], rax` prologue (48 89 05) mark the
 * global as NOT all-stores; every store site of an any/all global gets
 * nop-filled (ocset 144 over [at-3, at+3]); kgrel patches landing on
 * nop-filled sites are dropped from the patch tables; everything else in the
 * tables is rebuilt 1:1.  Same lists rebuilt ([cap][len][elems@16]), same
 * publishes through the shared dce_tbl.
 * gn_lookup is answered from a blob-local first-index table over glob_names
 * (the global gn cache self-heals on next use: gn_sync rebuilds on shrink and
 * appends the tail, so not touching it here cannot change any later answer).
 * Sovren integer comparisons are SIGNED: value compares are (long long).
 * No external symbols, no relocations, no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef long long L;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);
typedef U (*F5)(U,U,U,U,U);

enum { T_PA=1, T_PKind=2, T_PKid=3, T_PVal=4, T_PLine=5, T_GN=8, T_OC=11,
       T_OCN=12, T_HE=14, T_KGREL=20, T_KGLOB=21, T_ALLOC=23, T_AR=24,
       T_PUB_PATCH=27 };

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t5(U *t, U i, U a, U b, U c, U d, U e){ return ((F5)t[i])(a,b,c,d,e); }

static inline U llen(U l){ return l ? *(U*)(l + 8) : 0; }
static inline U lget(U l, U i){ return *(U*)(l + 16 + i * 8); }

/* persistent bump arena: the shared dce_arblk 16-byte block [arp][are].
 * Chunks come from the table's _sov_heap_alloc; an allocation larger than
 * the chunk size gets its own chunk (strb-sized rebuilds must not overrun). */
#define AR_CHUNK 1048576
static U ar_grow(U *t, U *arp, U *are, U n){
    U c = AR_CHUNK; if (n > c) c = n;
    U p = t1(t, T_ALLOC, c);
    *arp = p; *are = p + c;
    return p;
}
static inline U ar_get(U *t, U *arp, U *are, U n){
    if (*arp + n > *are) ar_grow(t, arp, are, n);
    U p = *arp; *arp = p + n; return p;
}
/* inline list ops: fast path in place, grow = 2x copy (the mmap-extend trick
 * is _sov_list_add_slow's private optimization, unobservable through content) */
static inline U lnew(U *t, U *arp, U *are){
    U b = ar_get(t, arp, are, 208);
    *(U*)(b) = 24; *(U*)(b + 8) = 0;
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
    *(U*)(b) = nc; *(U*)(b + 8) = len;
    for (U i = 0; i < len; i++) *(U*)(b + 16 + i * 8) = *(U*)(lst + 16 + i * 8);
    *(U*)(b + 16 + len * 8) = item;
    *(U*)(b + 8) = len + 1;
    return b;
}
/* oc mirrors with the exact ocget/ocset bounds semantics */
static inline unsigned ocgetf(U oc, U ocn, L i){
    if (i < 0) return 0;
    if ((U)i >= ocn) return 0;
    return *(const unsigned char*)(oc + (U)i);
}
static inline void ocsetf(U oc, U ocn, L i, unsigned v){
    if (i > -1 && (U)i < ocn) *(unsigned char*)(oc + (U)i) = (unsigned char)(v & 255);
}
static inline int seq(U a, U b){
    const unsigned char *x = (const unsigned char*)a, *y = (const unsigned char*)b;
    if (a == 0 || b == 0) return a == b;
    while (*x == *y){ if (!*x) return 1; x++; y++; }
    return 0;
}
/* blob-local first-index table over a name list; any hash works because the
 * answer ("lowest index whose string equals nm") is hash-independent.  The
 * real tables insert in list order with first-wins on duplicates. */
static U st_hash(U s){
    U h = 5381; const unsigned char *p = (const unsigned char*)s;
    while (*p){ h = h * 33 + *p; p++; }
    return h;
}
typedef struct { U cap, mask; U *keys; L *vals; } STAB;
static void st_build(STAB *st, U lst, U *t, U *arp, U *are){
    U n = llen(lst); U cap = 64; while (cap < 2 * n + 4) cap <<= 1; /* load < 50% */
    st->cap = cap; st->mask = cap - 1;
    st->keys = (U*)ar_get(t, arp, are, cap * 8);
    st->vals = (L*)ar_get(t, arp, are, cap * 8);
    for (U i = 0; i < cap; i++){ st->keys[i] = 0; st->vals[i] = 0; }
    for (U i = 0; i < n; i++){
        U s = lget(lst, i); if (!s) continue;
        U j = st_hash(s) & st->mask;
        while (st->keys[j]){ if (seq(st->keys[j], s)) break; j = (j + 1) & st->mask; }
        if (!st->keys[j]){ st->keys[j] = s; st->vals[j] = (L)i; }
    }
}
static L st_find(STAB *st, U s){
    if (!s) return -1;
    U j = st_hash(s) & st->mask;
    while (st->keys[j]){ if (seq(st->keys[j], s)) return st->vals[j]; j = (j + 1) & st->mask; }
    return -1;
}

/* twin entry: rdi = dce_tbl */
U dstores_native(U tbl){
    U *t = (U*)tbl;
    if (t0(t, T_HE)) return 0;
    U blk = t0(t, T_AR); U *arp = (U*)blk, *are = (U*)(blk + 8);
    U gn = t0(t, T_GN);
    U gil = llen(gn);
    U oc = t0(t, T_OC), ocn = t0(t, T_OCN);
    U kgrel = t0(t, T_KGREL), kglob = t0(t, T_KGLOB);
    U *anyv = 0, *allv = 0, *pl = 0;
    if (gil){
        anyv = (U*)ar_get(t, arp, are, gil * 8);
        allv = (U*)ar_get(t, arp, are, gil * 8);
        pl = (U*)ar_get(t, arp, are, gil * 8);
        for (U i = 0; i < gil; i++){ anyv[i] = 0; allv[i] = 1; pl[i] = 0; }
    }
    STAB gst; st_build(&gst, gn, t, arp, are);
    U pk = t0(t, T_PKind), pv = t0(t, T_PVal), pki = t0(t, T_PKid), pa = t0(t, T_PA);
    U pn = llen(pk);
    for (U pi = 0; pi < pn; pi++){
        U dsp = lget(pki, pi);
        if (dsp == kgrel){
            L gi = st_find(&gst, lget(pv, pi));
            if (gi > -1){
                anyv[gi] = 1;
                U at = lget(pa, pi);
                pl[gi] = ladd(pl[gi], at, t, arp, are);
                U st = 0;
                if ((L)at >= 3){
                    if (ocgetf(oc, ocn, (L)at - 3) == 72 &&
                        ocgetf(oc, ocn, (L)at - 2) == 137 &&
                        ocgetf(oc, ocn, (L)at - 1) == 5) st = 1;
                }
                if (st == 0) allv[gi] = 0;
            }
        }
        if (dsp == kglob){
            L gi = st_find(&gst, lget(pv, pi));
            if (gi > -1){ anyv[gi] = 1; allv[gi] = 0; }
        }
    }
    for (U gi = 0; gi < gil; gi++){
        if (anyv[gi] == 1 && allv[gi] == 1){
            U sub = pl[gi];
            for (U sj = 0; sj < llen(sub); sj++){
                L at = (L)lget(sub, sj);
                for (L k = at - 3; k < at + 4; k++) ocsetf(oc, ocn, k, 144);
            }
        }
    }
    /* rebuild the patch tables, dropping nop-filled kgrel sites */
    U pa2 = t0(t, T_PA), pkind2 = t0(t, T_PKind), pki2 = t0(t, T_PKid);
    U pv2 = t0(t, T_PVal), pline2 = t0(t, T_PLine);
    U qn = llen(pa2);
    U na = lnew(t, arp, are), nk = lnew(t, arp, are), nkd = lnew(t, arp, are);
    U nv = lnew(t, arp, are), nl = lnew(t, arp, are);
    for (U pi = 0; pi < qn; pi++){
        U drop = 0;
        U at = lget(pa2, pi);
        if (lget(pki2, pi) == kgrel){
            if ((L)at >= 3){
                if (ocgetf(oc, ocn, (L)at - 3) == 144 &&
                    ocgetf(oc, ocn, (L)at - 2) == 144 &&
                    ocgetf(oc, ocn, (L)at - 1) == 144) drop = 1;
            }
        }
        if (drop == 0){
            na = ladd(na, at, t, arp, are);
            nk = ladd(nk, lget(pkind2, pi), t, arp, are);
            nkd = ladd(nkd, lget(pki2, pi), t, arp, are);
            nv = ladd(nv, lget(pv2, pi), t, arp, are);
            nl = ladd(nl, lget(pline2, pi), t, arp, are);
        }
    }
    t5(t, T_PUB_PATCH, na, nk, nkd, nv, nl);
    return 0;
}
