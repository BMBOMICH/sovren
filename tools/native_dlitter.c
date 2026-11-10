/* Native dce_litter — C port of dce_litter in compilers/shared/cx86_p3.sov.
 * Dead register-litter elimination: buckets branch/patch sites per function
 * (functions containing a real branch target or a rel patch are excluded),
 * scans each remaining function's code for removable instruction runs
 * (push/pop reg pairs, reg-reg moves, nops, imm loads feeding nothing), and
 * drops the dead ranges: oc is compacted in place (kept bytes only ever move
 * down), patch_* are rebuilt with per-range shifts, fn_offs are shifted in
 * place.  The decoder mirrors the interpreted byte tests EXACTLY, including
 * the order of the overlapping ifs (later matches overwrite earlier fields)
 * and the signed -1 sentinels for dst/src.
 * bsearch_le: greatest i with lst[i] <= x else -1 (ascending list).
 * The advancing owner window keeps its bsearch fallback for records that
 * sort before the cursor — correctness never depends on monotonicity.
 * Lists are [cap][len][elems@16]; the rebuilt patch tables are published
 * through dce_tbl; oc_n through dce_pub_ocn.  Sovren compares are SIGNED.
 * No external symbols, no relocations, no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef long long L;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F5)(U,U,U,U,U);

enum { T_PA=1, T_PKind=2, T_PKid=3, T_PVal=4, T_PLine=5, T_FO=7, T_BRAT=9,
       T_BRST=10, T_OC=11, T_OCN=12, T_HE=14, T_KREL=18, T_ALLOC=23, T_AR=24,
       T_PUB_OCN=25, T_PUB_PATCH=27 };

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
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
static inline unsigned ocgetf(U oc, U ocn, L i){
    if (i < 0) return 0;
    if ((U)i >= ocn) return 0;
    return *(const unsigned char*)(oc + (U)i);
}
/* greatest i with lst[i] <= x in an ascending list, else -1 */
static L bsearch_le(U lst, L x){
    U n = llen(lst);
    L lo = 0, hi = (L)n - 1, best = -1;
    while (lo <= hi){
        L mid = (lo + hi) / 2;
        L mv = (L)lget(lst, (U)mid);
        if (mv <= x){ best = mid; lo = mid + 1; }
        else hi = mid - 1;
    }
    return best;
}
/* growable run arrays in the arena */
typedef struct { U cap, n; U *at, *len; } RNG;
static void rng_add(RNG *r, U at, U len, U *t, U *arp, U *are){
    if (r->n == r->cap){
        U nc = r->cap ? r->cap * 2 : 256;
        U *na = (U*)ar_get(t, arp, are, nc * 8);
        U *nl = (U*)ar_get(t, arp, are, nc * 8);
        for (U i = 0; i < r->n; i++){ na[i] = r->at[i]; nl[i] = r->len[i]; }
        r->at = na; r->len = nl; r->cap = nc;
    }
    r->at[r->n] = at; r->len[r->n] = len; r->n++;
}

/* twin entry: rdi = dce_tbl */
U dlitter_native(U tbl){
    U *t = (U*)tbl;
    if (t0(t, T_HE)) return 0;
    U blk = t0(t, T_AR); U *arp = (U*)blk, *are = (U*)(blk + 8);
    U fo = t0(t, T_FO);
    U nf = llen(fo);
    U oc = t0(t, T_OC), ocln = t0(t, T_OCN);
    U krel = t0(t, T_KREL);
    U *brbad = 0, *pbad = 0, *pbk = 0;
    if (nf){
        brbad = (U*)ar_get(t, arp, are, nf * 8);
        pbad = (U*)ar_get(t, arp, are, nf * 8);
        pbk = (U*)ar_get(t, arp, are, nf * 8);
        for (U i = 0; i < nf; i++){ brbad[i] = 0; pbad[i] = 0; pbk[i] = 0; }
    }
    /* bucket branch sites */
    U brat = t0(t, T_BRAT), brst = t0(t, T_BRST);
    U brn = llen(brat);
    for (U j = 0; j < brn; j++){
        U bq = lget(brat, j);
        U real = 0, dead = 0;
        if (lget(brst, j) == 4) dead = 1;
        if (dead == 0){
            if (ocgetf(oc, ocln, (L)bq - 1) == 233) real = 1;
            if ((L)bq >= 2 && ocgetf(oc, ocln, (L)bq - 2) == 15){
                U pb = ocgetf(oc, ocln, (L)bq - 1);
                if (pb >= 128 && pb < 136) real = 1;
            }
        }
        if (real == 1){
            L jf = bsearch_le(fo, (L)bq);
            if (jf >= 0){
                U je = (jf + 1 < (L)nf) ? lget(fo, (U)jf + 1) : ocln;
                if ((L)bq < (L)je) brbad[jf] = 1;
            }
        }
    }
    /* bucket patch sites with the advancing owner window + bsearch fallback */
    U pa = t0(t, T_PA), pki = t0(t, T_PKid);
    U kn = llen(pa);
    U fo0 = nf ? lget(fo, 0) : 0;
    L wf = 0;
    for (U k = 0; k < kn; k++){
        U kp = lget(pa, k);
        L kf = -1;
        if ((L)kp >= (L)fo0){
            U adv = 1;
            while (adv){
                if (wf + 1 < (L)nf){
                    if ((L)kp >= (L)lget(fo, (U)(wf + 1))) wf++;
                    else adv = 0;
                } else adv = 0;
            }
            if ((L)kp >= (L)lget(fo, (U)wf)) kf = wf;
        }
        if (kf < 0){
            if ((L)kp >= (L)fo0) kf = bsearch_le(fo, (L)kp);
        }
        if (kf >= 0){
            U ke = (kf + 1 < (L)nf) ? lget(fo, (U)kf + 1) : ocln;
            if ((L)kp < (L)ke){
                pbk[kf] = ladd(pbk[kf], kp, t, arp, are);
                if (lget(pki, k) == krel) pbad[kf] = 1;
            }
        }
    }
    /* per-function removable-run scan */
    RNG rng = {0, 0, 0, 0};
    /* run records (arena growables) */
    U rcap = 256, rn = 0;
    U *rist = (U*)ar_get(t, arp, are, rcap * 8);
    U *rilen = (U*)ar_get(t, arp, are, rcap * 8);
    L *ridst = (L*)ar_get(t, arp, are, rcap * 8);
    L *risrc = (L*)ar_get(t, arp, are, rcap * 8);
    U *rirm = (U*)ar_get(t, arp, are, rcap * 8);
    U *rdead = (U*)ar_get(t, arp, are, rcap * 8);
    /* live set: starts [0,7,6,2,10,8,9] at term; growable */
    U lcap = 64;
    L *live = (L*)ar_get(t, arp, are, lcap * 8);
    for (U fi = 0; fi < nf; fi++){
        U s = lget(fo, fi);
        U e = (fi + 1 < nf) ? lget(fo, fi + 1) : ocln;
        U ok = 1;
        if (brbad[fi] == 1) ok = 0;
        if (pbad[fi] == 1) ok = 0;
        if (ok == 1){
            U runst = 0, noprun = 0;
            U pos = s;
            while (pos < e){
                unsigned b = *(const unsigned char*)(oc + pos);
                U len = 0; L dst = -1, src = -1; U rm = 0, term = 0;
                if (b == 144){ len = 1; rm = 1; }
                if (len == 0 && b == 49){
                    unsigned n2 = ocgetf(oc, ocln, (L)pos + 1);
                    for (U r = 0; r < 8; r++){
                        if (n2 == 192 + r * 9){ len = 2; dst = (L)r; rm = 1; }
                    }
                }
                if (len == 0){
                    unsigned n1 = ocgetf(oc, ocln, (L)pos + 1);
                    unsigned n2 = ocgetf(oc, ocln, (L)pos + 2);
                    if (b == 72){
                        if (n1 == 137 && n2 >= 192 && n2 < 200){ len = 3; dst = (L)(n2 - 192); src = 0; rm = 1; }
                        if (n1 == 49){
                            for (U r = 0; r < 8; r++){
                                if (n2 == 192 + r * 9){ len = 3; dst = (L)r; rm = 1; }
                            }
                        }
                        if (n1 == 184){ len = 10; dst = 0; rm = 1; }
                    }
                    if (b == 73){
                        if (n1 == 137 && n2 >= 192 && n2 < 200){ len = 3; dst = (L)(n2 - 192 + 8); src = 0; rm = 1; }
                        if (n1 == 49){
                            for (U r = 0; r < 8; r++){
                                if (n2 == 192 + r * 9){ len = 3; dst = (L)(r + 8); rm = 1; }
                            }
                        }
                        if (n1 >= 184 && n1 < 192){ len = 10; dst = (L)(n1 - 184 + 8); rm = 1; }
                    }
                    if (b == 77){
                        if (n1 == 49){
                            for (U r = 0; r < 8; r++){
                                if (n2 == 192 + r * 9){ len = 3; dst = (L)(r + 8); rm = 1; }
                            }
                        }
                    }
                    if (b == 65){
                        if (n1 >= 80 && n1 < 88){ len = 2; src = (L)(n1 - 80 + 8); }
                        if (n1 >= 88 && n1 < 96){ len = 2; dst = (L)(n1 - 88 + 8); rm = 1; }
                        if (n1 >= 184 && n1 < 192){ len = 6; dst = (L)(n1 - 184 + 8); rm = 1; }
                    }
                }
                if (len == 0){
                    if (b >= 80 && b < 88){ len = 1; src = (L)(b - 80); }
                    if (b >= 88 && b < 96){ len = 1; dst = (L)(b - 88); rm = 1; }
                    if (b >= 184 && b < 192){ len = 5; dst = (L)(b - 184); rm = 1; }
                    if (b >= 176 && b < 184){ len = 2; }
                    if (b == 106){ len = 2; }
                    if (b == 15){
                        unsigned n2 = ocgetf(oc, ocln, (L)pos + 1);
                        if (n2 == 5){ len = 2; term = 1; }
                    }
                }
                if (len == 0){
                    pos++; runst = 0; noprun = 0;
                } else {
                    if (runst == 0){
                        U can = 0;
                        if (pos == s) can = 1;
                        if (term == 1) can = 1;
                        if (noprun >= 3) can = 1;
                        if (can == 1){ runst = 1; rn = 0; }
                    }
                    if (runst == 1){
                        if (rn == rcap){
                            U nc = rcap * 2;
                            U *a1 = (U*)ar_get(t, arp, are, nc * 8);
                            U *a2 = (U*)ar_get(t, arp, are, nc * 8);
                            L *a3 = (L*)ar_get(t, arp, are, nc * 8);
                            L *a4 = (L*)ar_get(t, arp, are, nc * 8);
                            U *a5 = (U*)ar_get(t, arp, are, nc * 8);
                            U *a6 = (U*)ar_get(t, arp, are, nc * 8);
                            for (U i = 0; i < rn; i++){ a1[i] = rist[i]; a2[i] = rilen[i]; a3[i] = ridst[i]; a4[i] = risrc[i]; a5[i] = rirm[i]; a6[i] = rdead[i]; }
                            rist = a1; rilen = a2; ridst = a3; risrc = a4; rirm = a5; rdead = a6;
                            rcap = nc;
                        }
                        rist[rn] = pos; rilen[rn] = len; ridst[rn] = dst;
                        risrc[rn] = src; rirm[rn] = rm; rdead[rn] = 0; rn++;
                        if (term == 1){
                            U ln = 0;
                            live[ln++] = 0; live[ln++] = 7; live[ln++] = 6;
                            live[ln++] = 2; live[ln++] = 10; live[ln++] = 8; live[ln++] = 9;
                            for (L k = (L)rn - 1; k >= 0; k--){
                                L d = ridst[k];
                                if (d > -1){
                                    U inlive = 0;
                                    for (U m = 0; m < ln; m++) if (live[m] == d) inlive = 1;
                                    if (inlive == 1){
                                        U w = 0;
                                        for (U m = 0; m < ln; m++)
                                            if (live[m] != d) live[w++] = live[m];
                                        ln = w;
                                        L sv = risrc[k];
                                        if (sv > -1){
                                            U in2 = 0;
                                            for (U m = 0; m < ln; m++) if (live[m] == sv) in2 = 1;
                                            if (in2 == 0){
                                                if (ln == lcap){
                                                    U nc2 = lcap * 2;
                                                    L *nl2 = (L*)ar_get(t, arp, are, nc2 * 8);
                                                    for (U m = 0; m < ln; m++) nl2[m] = live[m];
                                                    live = nl2; lcap = nc2;
                                                }
                                                live[ln++] = sv;
                                            }
                                        }
                                    } else {
                                        if (rirm[k] == 1){
                                            U h0 = rist[k], h1 = h0 + rilen[k];
                                            U patched = 0;
                                            U bk = pbk[fi];
                                            for (U m = 0; m < llen(bk); m++){
                                                U pp = lget(bk, m);
                                                if ((L)pp >= (L)h0 && (L)pp < (L)h1) patched = 1;
                                            }
                                            if (patched == 0) rdead[k] = 1;
                                        }
                                    }
                                }
                            }
                            for (U m = 0; m < rn; m++){
                                if (rdead[m] == 1) rng_add(&rng, rist[m], rilen[m], t, arp, are);
                            }
                            runst = 0; noprun = 0;
                        }
                    }
                    if (b == 144) noprun++;
                    else noprun = 0;
                    pos += len;
                }
            }
        }
    }
    if (rng.n == 0) return 0;
    /* insertion sort by rng_at (stable: strict >) */
    for (U i = 1; i < rng.n; i++){
        L k = (L)i - 1;
        U ca = rng.at[i], cl = rng.len[i];
        U done = 0;
        while (!done){
            if (k < 0) done = 1;
            else {
                if ((L)rng.at[k] > (L)ca){
                    rng.at[k + 1] = rng.at[k];
                    rng.len[k + 1] = rng.len[k];
                    k--;
                } else done = 1;
            }
        }
        rng.at[k + 1] = ca;
        rng.len[k + 1] = cl;
    }
    /* compact oc in place (kept bytes only ever move down) */
    U w = 0, pos = 0, ri = 0;
    unsigned char *ocb = (unsigned char*)oc;
    while (pos < ocln){
        U cut = 0;
        if (ri < rng.n && rng.at[ri] == pos) cut = 1;
        if (cut == 1){
            pos += rng.len[ri];
            ri++;
        } else {
            ocb[w++] = ocb[pos];
            pos++;
        }
    }
    t1(t, T_PUB_OCN, w);
    /* rebuild the patch tables with per-range shifts */
    U pkind2 = t0(t, T_PKind), pki2 = t0(t, T_PKid), pv2 = t0(t, T_PVal);
    U pline2 = t0(t, T_PLine);
    U na = lnew(t, arp, are), nk = lnew(t, arp, are), nkd = lnew(t, arp, are);
    U nv = lnew(t, arp, are), nl = lnew(t, arp, are);
    for (U pi = 0; pi < kn; pi++){
        U at = lget(pa, pi);
        U sh = 0;
        for (U r = 0; r < rng.n; r++)
            if ((L)rng.at[r] + (L)rng.len[r] <= (L)at) sh += rng.len[r];
        na = ladd(na, at - sh, t, arp, are);
        nk = ladd(nk, lget(pkind2, pi), t, arp, are);
        nkd = ladd(nkd, lget(pki2, pi), t, arp, are);
        nv = ladd(nv, lget(pv2, pi), t, arp, are);
        nl = ladd(nl, lget(pline2, pi), t, arp, are);
    }
    t5(t, T_PUB_PATCH, na, nk, nkd, nv, nl);
    /* shift fn_offs in place (same list object, elements only) */
    for (U fi = 0; fi < nf; fi++){
        U off = lget(fo, fi);
        U sh = 0;
        for (U r = 0; r < rng.n; r++)
            if ((L)rng.at[r] + (L)rng.len[r] <= (L)off) sh += rng.len[r];
        *(U*)(fo + 16 + fi * 8) = off - sh;
    }
    return 0;
}
