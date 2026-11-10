/* Native dce — C port of dce in compilers/shared/cx86_p7.sov.
 * Function-level dead-code elimination: builds the kept-function set (all
 * functions except the fib-drop name), seeds reachability from entry_nm,
 * walks the patch records in ONE pass (advancing owner window over the
 * ascending kept offsets; krel/kfnaddr records add call edges), BFS-marks
 * the reachable set, compacts oc in place (kept ranges only ever move down:
 * cum starts at first_off and ranges ascend), rebuilds fn_names/fn_offs and
 * the patch tables with per-function shifts, and garbage-collects the string
 * pool (str/strrel/str32 patches keep their strings; suffix-shared strings
 * are copied independently per live offset, duplicating when two live
 * offsets share a suffix - exactly the interpreted behavior).
 * fn_lookup is answered from a blob-local first-index table over fn_names:
 * the answer is hash-independent ("lowest index whose string equals nm"),
 * and the global fn cache is untouched EXCEPT the compaction-branch reset,
 * which the interpreted code performs by clearing fn_htcap/fn_sync_hi (the
 * rebuild changes every index; a stale cache would answer wrong).  fn_sync
 * self-heals on next use (bulk-appends the tail), so not touching it in the
 * early-return branches cannot change any later answer.
 * intern_kid stays behind the table (dkid_ok=0 fallback + the three pool
 * kind ids).  Sovren compares are SIGNED.  No external symbols/relocs.
 */
#include <stdint.h>
typedef uint64_t U;
typedef long long L;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);
typedef U (*F5)(U,U,U,U,U);

enum { T_PA=1, T_PKind=2, T_PKid=3, T_PVal=4, T_PLine=5, T_FN=6, T_FO=7,
       T_OC=11, T_OCN=12, T_STRB=13, T_HE=14, T_FIBD=15, T_FIBNM=16,
       T_ENTRY=17, T_KREL=18, T_KFNADDR=19, T_INTERN=22, T_ALLOC=23, T_AR=24,
       T_PUB_OCN=25, T_PUB_FN=26, T_PUB_PATCH=27, T_PUB_STRB=28 };

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }
static inline U t5(U *t, U i, U a, U b, U c, U d, U e){ return ((F5)t[i])(a,b,c,d,e); }

static inline U llen(U l){ return l ? *(U*)(l + 8) : 0; }
static inline U lget(U l, U i){ return *(U*)(l + 16 + i * 8); }

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
static inline int seq(U a, U b){
    const unsigned char *x = (const unsigned char*)a, *y = (const unsigned char*)b;
    if (a == 0 || b == 0) return a == b;
    while (*x == *y){ if (!*x) return 1; x++; y++; }
    return 0;
}
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
static inline U slen(U s){
    if (s < 4096) return 0; /* the length() rule for non-pointer values */
    const unsigned char *p = (const unsigned char*)s;
    U n = 0; while (p[n]) n++;
    return n;
}

/* twin entry: rdi = dce_tbl */
U dce_native(U tbl){
    U *t = (U*)tbl;
    if (t0(t, T_HE)) return 0;
    U fn = t0(t, T_FN);
    U n = llen(fn);
    if (n < 2) return 0;
    U oc = t0(t, T_OC), clen = t0(t, T_OCN);
    U fo = t0(t, T_FO);
    U fibd = t0(t, T_FIBD), fibnm = t0(t, T_FIBNM);
    U krel = t0(t, T_KREL), kfnaddr = t0(t, T_KFNADDR);
    U blk = t0(t, T_AR); U *arp = (U*)blk, *are = (U*)(blk + 8);
    /* kept set: dro (offsets), dri (indices), dpos (orig idx -> kept idx) */
    U *dro = (U*)ar_get(t, arp, are, n * 8);
    U *dri = (U*)ar_get(t, arp, are, n * 8);
    L *dpos = (L*)ar_get(t, arp, are, n * 8);
    U nr = 0;
    for (U i = 0; i < n; i++){
        U nm = lget(fn, i);
        U ph = 0;
        if (fibd == 1 && seq(nm, fibnm)) ph = 1;
        if (ph == 0){ dro[nr] = lget(fo, i); dri[nr] = i; nr++; }
    }
    if (nr < 2) return 0;
    for (U i = 0; i < n; i++) dpos[i] = -1;
    for (U i = 0; i < nr; i++) dpos[dri[i]] = (L)i;
    U pa = t0(t, T_PA), pkind = t0(t, T_PKind), pki = t0(t, T_PKid), pv = t0(t, T_PVal);
    U pn = llen(pa);
    U *dreach = (U*)ar_get(t, arp, are, nr * 8);
    for (U i = 0; i < nr; i++) dreach[i] = 0;
    U *dadj = (U*)ar_get(t, arp, are, nr * 8);
    for (U i = 0; i < nr; i++) dadj[i] = 0;
    /* dtodo: growable */
    U tcap = 256, tn = 0;
    U *dtodo = (U*)ar_get(t, arp, are, tcap * 8);
    STAB fst; st_build(&fst, fn, t, arp, are);
    L mi = st_find(&fst, t0(t, T_ENTRY));
    if (mi < 0) return 0;
    L rj = dpos[mi];
    if (rj > -1){ dreach[rj] = 1; dtodo[tn++] = (U)rj; }
    /* owner + call-edge walk in ONE pass */
    U dkid_ok = 0;
    if (pki != 0 && llen(pki) == pn) dkid_ok = 1;
    L ff = 0;
    for (U pp = 0; pp < pn; pp++){
        U at = lget(pa, pp);
        L o = -1;
        if ((L)at >= (L)dro[0]){
            U adv = 1;
            while (adv){
                if (ff + 1 < (L)nr){
                    if ((L)at >= (L)dro[ff + 1]) ff++;
                    else adv = 0;
                } else adv = 0;
            }
            o = ff;
        }
        U dki = 0;
        if (dkid_ok == 1) dki = lget(pki, pp);
        else dki = t1(t, T_INTERN, lget(pkind, pp));
        U iscall = 0;
        if (dki == krel) iscall = 1;
        if (dki == kfnaddr) iscall = 1;
        if (iscall == 1){
            U val = lget(pv, pp);
            L ti = st_find(&fst, val);
            if (ti > -1){
                L rj2 = dpos[ti];
                if (rj2 > -1){
                    if (o == -1){
                        if (dreach[rj2] == 0){
                            dreach[rj2] = 1;
                            if (tn == tcap){
                                U nc = tcap * 2;
                                U *nd = (U*)ar_get(t, arp, are, nc * 8);
                                for (U i = 0; i < tn; i++) nd[i] = dtodo[i];
                                dtodo = nd; tcap = nc;
                            }
                            dtodo[tn++] = (U)rj2;
                        }
                    } else {
                        dadj[o] = ladd(dadj[o], (U)rj2, t, arp, are);
                    }
                }
            }
        }
    }
    /* BFS */
    U dhead = 0;
    while (dhead < tn){
        U u = dtodo[dhead++];
        U nbl = dadj[u];
        U nbn = llen(nbl);
        for (U j = 0; j < nbn; j++){
            U v = lget(nbl, j);
            if (dreach[v] == 0){
                dreach[v] = 1;
                if (tn == tcap){
                    U nc = tcap * 2;
                    U *nd = (U*)ar_get(t, arp, are, nc * 8);
                    for (U i = 0; i < tn; i++) nd[i] = dtodo[i];
                    dtodo = nd; tcap = nc;
                }
                dtodo[tn++] = v;
            }
        }
    }
    U kept = 0;
    for (U i = 0; i < nr; i++) if (dreach[i] == 1) kept++;
    if (kept == nr) return 0;
    /* compact */
    U nfn = lnew(t, arp, are), nfo = lnew(t, arp, are);
    L *dshift = (L*)ar_get(t, arp, are, nr * 8);
    for (U i = 0; i < nr; i++) dshift[i] = 0;
    U cum = dro[0];
    unsigned char *ocb = (unsigned char*)oc;
    for (U i = 0; i < nr; i++){
        if (dreach[i] == 1){
            U s = dro[i];
            U e = (i + 1 < nr) ? dro[i + 1] : clen;
            if (cum != s && e > s){
                /* forward qword+tail blit (cum <= s always) */
                U k = 0;
                while (k + 8 <= e - s){
                    *(U*)(ocb + cum + k) = *(const U*)(ocb + s + k);
                    k += 8;
                }
                while (k < e - s){
                    ocb[cum + k] = ocb[s + k];
                    k++;
                }
            }
            nfn = ladd(nfn, lget(fn, dri[i]), t, arp, are);
            nfo = ladd(nfo, cum, t, arp, are);
            dshift[i] = (L)cum - (L)s;
            cum += e - s;
        }
    }
    /* rebuild patch tables (fresh owner window, same advancing rule) */
    U na = lnew(t, arp, are), nk = lnew(t, arp, are), nkd = lnew(t, arp, are);
    U nv = lnew(t, arp, are), nl = lnew(t, arp, are);
    U pline = t0(t, T_PLine);
    L ff2 = 0;
    for (U pp = 0; pp < pn; pp++){
        U at2 = lget(pa, pp);
        L o = -1;
        if ((L)at2 >= (L)dro[0]){
            U adv = 1;
            while (adv){
                if (ff2 + 1 < (L)nr){
                    if ((L)at2 >= (L)dro[ff2 + 1]) ff2++;
                    else adv = 0;
                } else adv = 0;
            }
            o = ff2;
        }
        U keep = 0; U ns = at2;
        if (o == -1) keep = 1;
        else {
            if (dreach[o] == 1){ keep = 1; ns = ns + (U)dshift[o]; }
        }
        if (keep == 1){
            na = ladd(na, ns, t, arp, are);
            nk = ladd(nk, lget(pkind, pp), t, arp, are);
            nkd = ladd(nkd, lget(pki, pp), t, arp, are);
            nv = ladd(nv, lget(pv, pp), t, arp, are);
            nl = ladd(nl, lget(pline, pp), t, arp, are);
        }
    }
    t1(t, T_PUB_OCN, cum);
    t2(t, T_PUB_FN, nfn, nfo);
    t5(t, T_PUB_PATCH, na, nk, nkd, nv, nl);
    /* string-pool GC (operates on the NEW patch lists before they are
     * observable; the remap happens on the same values the interpreted
     * code writes into its already-published lists).  The kind needles
     * are stack-built byte arrays: the blob carries no .rodata, so no
     * relocations. */
    U kbuf[3];
    unsigned char *q1 = (unsigned char*)&kbuf[0];
    q1[0]='s'; q1[1]='t'; q1[2]='r'; q1[3]=0;
    unsigned char *q2 = (unsigned char*)&kbuf[1];
    q2[0]='s'; q2[1]='t'; q2[2]='r'; q2[3]='r'; q2[4]='e'; q2[5]='l'; q2[6]=0;
    unsigned char *q3 = (unsigned char*)&kbuf[2];
    q3[0]='s'; q3[1]='t'; q3[2]='r'; q3[3]='3'; q3[4]='2'; q3[5]=0;
    U s1 = t1(t, T_INTERN, (U)q1);
    U s2 = t1(t, T_INTERN, (U)q2);
    U s3 = t1(t, T_INTERN, (U)q3);
    U strb = t0(t, T_STRB);
    U sg_sl = strb ? *(U*)(strb + 8) : 0;
    if (sg_sl > 0){
        L *map = (L*)ar_get(t, arp, are, (sg_sl + 1) * 8);
        for (U i = 0; i <= sg_sl; i++) map[i] = -1;
        for (U pp = 0; pp < llen(nkd); pp++){
            U k = lget(nkd, pp);
            U is = 0;
            if (k == s1) is = 1;
            if (k == s2) is = 1;
            if (k == s3) is = 1;
            if (is == 1){
                L v = (L)lget(nv, pp);
                if (v >= 0 && v <= (L)sg_sl) map[v] = 0;
            }
        }
        U nb = ar_get(t, arp, are, sg_sl + 32);
        *(U*)(nb) = sg_sl + 16;
        *(U*)(nb + 8) = 0;
        U sg_nl = 0;
        const unsigned char *sb = (const unsigned char*)(strb + 16);
        unsigned char *db = (unsigned char*)(nb + 16);
        for (U i = 0; i < sg_sl; i++){
            if (map[i] == 0){
                map[i] = (L)sg_nl;
                U sn = slen((U)(sb + i)) + 1;
                for (U q = 0; q < sn; q++) db[sg_nl + q] = sb[i + q];
                sg_nl += sn;
            }
        }
        *(U*)(nb + 8) = sg_nl;
        if (sg_nl < sg_sl){
            for (U pp = 0; pp < llen(nkd); pp++){
                U k = lget(nkd, pp);
                U is = 0;
                if (k == s1) is = 1;
                if (k == s2) is = 1;
                if (k == s3) is = 1;
                if (is == 1){
                    L v = (L)lget(nv, pp);
                    if (v >= 0 && v <= (L)sg_sl){
                        *(U*)(nv + 16 + pp * 8) = (U)map[v];
                    }
                }
            }
            t1(t, T_PUB_STRB, nb);
        }
    }
    return 0;
}
