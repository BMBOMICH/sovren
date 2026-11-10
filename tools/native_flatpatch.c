/* Native flat-emission patch passes + stub_diet compaction, C port.
 * 1:1 mirror of the write_elf patch loops and the stub_diet compaction in
 * compilers/linux/compiler.sov, behind one mode-dispatched entry
 * flat_pass_native(pass, tbl) (Sovren ABI: rdi=pass, rsi=tbl).
 *   pass 0: rel_n count over the patch records (write_elf loop 1).
 *   pass 1: patch application into flat + the rel entry writes
 *           (write_elf loops 2 and 3); returns the rel_at list.
 *   pass 2: stub_diet g_argc/g_argv liveness scan; returns sd_live.
 *   pass 3: stub_diet five-list compaction + fn_offs shift; returns sd_w.
 * tbl slots (U* indices) mirror flat_tbl_init in compiler.sov:
 *   0 count(52), 1 rel_n(out p0/in p1), 2 had_err(out p1), 3 rc_kok,
 *   4 patch_at, 5 patch_kid, 6 patch_val, 7 patch_kind, 8 patch_line,
 *   9 flat, 10 HDR, 11 BASE, 12 str_addr, 13 glob_addr, 14 rel_off,
 *   15 sl, 16 sbtot, 17 fn_offs, 18 glob_names, 19 sbss_sizes,
 *   20 fn_ht, 21 fn_hti, 22 fn_htcap, 23 gn_tbl, 24 gn_idx, 25 gn_cap,
 *   26 kg_rel, 27 kg_fnaddr, 28 kg_str, 29 kg_strrel, 30 kg_str32,
 *   31 kg_sbss, 32 kg_grel, 33 kg_glob, 34 kg_gwstr_a, 35 kg_gwstr_n,
 *   36 kg_gwipe_a, 37 kg_gwipe_n, 38 rk_fa, 39 rk_str, 40 rk_gl,
 *   41 rk_gw, 42 rk_gp, 43 rk_sb, 44 flp_dbg, 45 flp_rel_err,
 *   46 flp_fa_err, 47 sd_g, 48 sd_gr, 49 sd_n, 50 sd_cut_at, 51 sd_cut,
 *   52 relbuf.
 * fn_lookup/gn_lookup are inlined (nhash/set_h/djb2 chain + open
 * addressing, exact .sov semantics); the caller runs fn_sync/gn_sync once
 * before pass 1 so the tables are complete and frozen for the twin's
 * lifetime. Error and debug paths stay behind tbl callbacks (rare).
 * The /tmp/sov_glog2 per-record probe log is intentionally not mirrored
 * (the inl2/licm precedent: side-log-only, never affects translation
 * output; normal runs never create it). The interpreted fallback
 * _sov_flat_pass keeps it.
 * poke4/poke8 are little-endian unaligned stores (memcpy; the .sov
 * per-byte mod-256 chain produces identical bytes for any 64-bit value).
 * No external symbols, no relocations, no string literals, no static
 * mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef long long S;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);

enum {
 T_DBG=44, T_RELERR=45, T_FAERR=46
};
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }

#define MISS ((U)-1)
#define LLEN(x) (*(U*)((x)+8))
#define ELEM(x,i) (*(U*)((x)+16+(U)(i)*8))
#define PB(s,i) (*(const unsigned char*)((s)+(U)(i)))

static inline U streq(const unsigned char *a, const unsigned char *b){
    if (a == b) return 1;
    if (!a || !b) return 0;
    U i = 0;
    while (a[i] && a[i] == b[i]) i++;
    return a[i] == b[i];
}

/* nhash: per-byte chain h = (h*33 ^ b) & (2^56-1), then the avalanche
 * pair (same value as the SWAR path in the .sov body). */
static U nhash_c(const unsigned char *s){
    U h = 0, i = 0;
    while (s[i]){
        h = ((h * 33) ^ (U)s[i]) & 72057594037927935ULL;
        i++;
    }
    h &= 4294967295ULL;
    h *= 73244475ULL;
    h ^= h >> 15;
    h &= 4294967295ULL;
    h *= 73244475ULL;
    h ^= h >> 15;
    return h & 72057594037927935ULL;
}
/* set_h: plain djb2 (h = h*33 + b, start 5381, full 64-bit wrap). */
static U set_h_c(const unsigned char *s){
    U h = 5381, i = 0;
    while (s[i]){ h = h * 33 + (U)s[i]; i++; }
    return h;
}
/* fn_lookup with pre-synced tables (index stored +1; 0 slot = empty).
 * Pointer-equality fast path first (gn_lookup's rule: the probe key is
 * usually the canonical interned string itself, and pointer equality
 * implies string equality - the same index, one cache line). */
static U fn_lookup_c(const unsigned char *nm, U ht, U hti, U htcap){
    U fh = nhash_c(nm) & (htcap - 1);
    for (;;){
        U fs = *(U*)(ht + fh * 8);
        if (fs == 0) return MISS;
        if (fs == (U)nm) return (*(U*)(hti + fh * 8)) - 1;
        if (streq((const unsigned char*)fs, nm))
            return (*(U*)(hti + fh * 8)) - 1;
        fh = (fh + 1) & (htcap - 1);
    }
}
/* gn_lookup with pre-synced tables (pointer fast path, then str_eq). */
static U gn_lookup_c(const unsigned char *nm, U gt, U gi, U gcap){
    if (gt == 0 || gcap == 0) return MISS;
    U sl = set_h_c(nm) & (gcap - 1);
    for (;;){
        U cur = *(U*)(gt + sl * 8);
        if (cur == 0) return MISS;
        if (cur == (U)nm) return *(U*)(gi + sl * 8);
        if (streq((const unsigned char*)cur, nm)) return *(U*)(gi + sl * 8);
        sl = sl + 1;
        if (sl == gcap) sl = 0;
    }
}
/* _sov_atoi mirror: optional '-', 0x hex, 0b binary, decimal stop. */
static U atoi_c(const unsigned char *s){
    if (!s) return 0;
    U n = 0, sign = 1, i = 0;
    if (PB(s,0) == 45){ sign = (U)-1; i = 1; }
    if (PB(s,i) == 48){
        U hx = PB(s,i+1);
        if (hx == 120){
            i += 2;
            for (;;){
                U c = PB(s,i), v = MISS;
                if (c > 47 && c < 58) v = c - 48;
                if (v == MISS && c > 96 && c < 103) v = c - 87;
                if (v == MISS && c > 64 && c < 71) v = c - 55;
                if (v == MISS) return n * sign;
                n = n * 16 + v;
                i++;
            }
        }
        if (hx == 98){
            i += 2;
            for (;;){
                U c = PB(s,i);
                if (c == 48){ n = n * 2; i++; }
                else if (c == 49){ n = n * 2 + 1; i++; }
                else return n * sign;
            }
        }
    }
    for (;;){
        U c = PB(s,i);
        if (c < 48 || c > 57) return n * sign;
        n = n * 10 + (c - 48);
        i++;
    }
}

static inline void poke8c(U p, U v){ __builtin_memcpy((void*)p, &v, 8); }
static inline void poke4c(U p, U v){ __builtin_memcpy((void*)p, &v, 4); }

/* twin entry: rdi=pass, rsi=tbl (fn _sov_flat_pass) */
U flat_pass_native(U pass, U *tbl){
    if (pass == 0){
        U pat = tbl[4], pkid = tbl[5], pkind = tbl[7];
        U rc_n = LLEN(pat);
        U rc_kok = tbl[3];
        U rel_n = 0;
        if (rc_kok == 1){
            U fa = tbl[38], st = tbl[39], gl = tbl[40];
            U gw = tbl[41], gp = tbl[42], sb = tbl[43];
            for (U i = 0; i < rc_n; i++){
                U kd = ELEM(pkid, i);
                if (kd == fa || kd == st || kd == gl || kd == gw || kd == gp || kd == sb)
                    rel_n++;
            }
        } else {
            /* stack literals; the .sov compares against these strings */
            unsigned char s_fa[7]; s_fa[0]=102;s_fa[1]=110;s_fa[2]=97;s_fa[3]=100;s_fa[4]=100;s_fa[5]=114;s_fa[6]=0;
            unsigned char s_st[4];  s_st[0]=115;s_st[1]=116;s_st[2]=114;s_st[3]=0;
            unsigned char s_gl[5];  s_gl[0]=103;s_gl[1]=108;s_gl[2]=111;s_gl[3]=98;s_gl[4]=0;
            unsigned char s_gw[8];  s_gw[0]=103;s_gw[1]=119;s_gw[2]=115;s_gw[3]=116;s_gw[4]=114;s_gw[5]=95;s_gw[6]=97;s_gw[7]=0;
            unsigned char s_gp[8];  s_gp[0]=103;s_gp[1]=119;s_gp[2]=105;s_gp[3]=112;s_gp[4]=101;s_gp[5]=95;s_gp[6]=97;s_gp[7]=0;
            unsigned char s_sb[5];  s_sb[0]=115;s_sb[1]=98;s_sb[2]=115;s_sb[3]=115;s_sb[4]=0;
            for (U i = 0; i < rc_n; i++){
                const unsigned char *rk = (const unsigned char*)ELEM(pkind, i);
                if (streq(rk, s_fa) || streq(rk, s_st) || streq(rk, s_gl) ||
                    streq(rk, s_gw) || streq(rk, s_gp) || streq(rk, s_sb))
                    rel_n++;
            }
        }
        tbl[1] = rel_n;
        return rel_n;
    }
    if (pass == 1){
        U pat = tbl[4], pkid = tbl[5], pval = tbl[6], pline = tbl[8];
        U flat = tbl[9], HDR = tbl[10], BASE = tbl[11];
        U str_addr = tbl[12], glob_addr = tbl[13], rel_off = tbl[14];
        U sl = tbl[15], sbtot = tbl[16], fn_offs = tbl[17];
        U glob_names = tbl[18], sbss_sizes = tbl[19];
        U ht = tbl[20], hti = tbl[21], htcap = tbl[22];
        U gt = tbl[23], gi = tbl[24], gcap = tbl[25];
        U kg_rel = tbl[26], kg_fnaddr = tbl[27], kg_str = tbl[28];
        U kg_strrel = tbl[29], kg_str32 = tbl[30], kg_sbss = tbl[31];
        U kg_grel = tbl[32], kg_glob = tbl[33], kg_gwstr_a = tbl[34];
        U kg_gwstr_n = tbl[35], kg_gwipe_a = tbl[36], kg_gwipe_n = tbl[37];
        U relbuf = tbl[52];
        U rel_n = tbl[1];
        U had_err = tbl[2];
        U rel_len = 0, rel_cap = 0;
        if (relbuf){ rel_cap = *(U*)relbuf; rel_len = *(U*)(relbuf + 8); }
        U n = LLEN(pat);
        for (U i = 0; i < n; i++){
            U at = ELEM(pat, i);
            U kind = ELEM(pkid, i);
            U val = ELEM(pval, i);
            if ((S)at < 0) t2(tbl, T_DBG, kind, i);
            if (kind == kg_rel){
                U fi = fn_lookup_c((const unsigned char*)val, ht, hti, htcap);
                if ((S)fi > -1){
                    U tgt = ELEM(fn_offs, fi);
                    poke4c(flat + HDR + at, tgt - (at + 4));
                } else {
                    t2(tbl, T_RELERR, val, ELEM(pline, i));
                    had_err = 1;
                }
            }
            unsigned k0 = PB((const unsigned char*)kind, 0);
            if (k0 == 102){
                if (kind == kg_fnaddr){
                    U fi = fn_lookup_c((const unsigned char*)val, ht, hti, htcap);
                    if ((S)fi > -1){
                        poke8c(flat + HDR + at, BASE + HDR + ELEM(fn_offs, fi));
                        if (rel_len < rel_cap) *(U*)(relbuf + 16 + rel_len * 8) = at;
                        rel_len++;
                    } else {
                        t1(tbl, T_FAERR, val);
                        had_err = 1;
                    }
                }
            }
            if (k0 == 115){
                if (kind == kg_str){
                    poke8c(flat + HDR + at, str_addr + val);
                    if (rel_len < rel_cap) *(U*)(relbuf + 16 + rel_len * 8) = at;
                    rel_len++;
                }
                if (kind == kg_strrel)
                    poke4c(flat + HDR + at, str_addr + val - (BASE + HDR + at + 4));
                if (kind == kg_str32)
                    poke4c(flat + HDR + at, str_addr + val);
                if (kind == kg_sbss){
                    U bi = atoi_c((const unsigned char*)val);
                    U baddr = glob_addr + LLEN(glob_names) * 8;
                    for (U bj = 0; bj < bi; bj++){
                        U bs = ELEM(sbss_sizes, bj);
                        baddr = baddr + 15;
                        baddr = baddr - baddr % 16;
                        baddr = baddr + bs;
                    }
                    baddr = baddr + 15;
                    baddr = baddr - baddr % 16;
                    poke8c(flat + HDR + at, baddr);
                    if (rel_len < rel_cap) *(U*)(relbuf + 16 + rel_len * 8) = at;
                    rel_len++;
                }
            }
            if (k0 == 103){
                if (kind == kg_grel){
                    U gx = gn_lookup_c((const unsigned char*)val, gt, gi, gcap);
                    poke4c(flat + HDR + at, glob_addr + gx * 8 - (BASE + HDR + at + 4));
                }
                if (kind == kg_glob){
                    U gx = gn_lookup_c((const unsigned char*)val, gt, gi, gcap);
                    poke8c(flat + HDR + at, glob_addr + gx * 8);
                    if (rel_len < rel_cap) *(U*)(relbuf + 16 + rel_len * 8) = at;
                    rel_len++;
                }
                if (kind == kg_gwstr_a){
                    poke8c(flat + HDR + at, str_addr);
                    if (rel_len < rel_cap) *(U*)(relbuf + 16 + rel_len * 8) = at;
                    rel_len++;
                }
                if (kind == kg_gwstr_n)
                    poke4c(flat + HDR + at, (sl + 7) / 8);
                if (kind == kg_gwipe_a){
                    poke8c(flat + HDR + at, glob_addr);
                    if (rel_len < rel_cap) *(U*)(relbuf + 16 + rel_len * 8) = at;
                    rel_len++;
                }
                if (kind == kg_gwipe_n){
                    U gbytes = LLEN(glob_names) * 8 + sbtot;
                    poke4c(flat + HDR + at, (gbytes + 7) / 8);
                }
            }
        }
        if (relbuf) *(U*)(relbuf + 8) = rel_len;
        tbl[2] = had_err;
        if (rel_n > 0){
            poke8c(flat + rel_off, rel_n);
            for (U ri = 0; ri < rel_n; ri++)
                poke8c(flat + rel_off + 8 + ri * 8, HDR + ELEM(relbuf, ri));
        }
        return relbuf;
    }
    if (pass == 2){
        U pat = tbl[4], pkid = tbl[5], pval = tbl[6];
        U sd_n = tbl[49], sd_g = tbl[47], sd_gr = tbl[48];
        unsigned char ga[7]; ga[0]=103;ga[1]=95;ga[2]=97;ga[3]=114;ga[4]=103;ga[5]=99;ga[6]=0;
        unsigned char gv[7]; gv[0]=103;gv[1]=95;gv[2]=97;gv[3]=114;gv[4]=103;gv[5]=118;gv[6]=0;
        for (U i = 0; i < sd_n; i++){
            U at = ELEM(pat, i);
            if (at >= 41){
                U kd = ELEM(pkid, i);
                if (kd == sd_g || kd == sd_gr){
                    const unsigned char *v = (const unsigned char*)ELEM(pval, i);
                    if (streq(v, ga) || streq(v, gv)) return 1;
                }
            }
        }
        return 0;
    }
    /* pass 3: stub compaction */
    {
        U pat = tbl[4], pkind = tbl[7], pkid = tbl[5], pval = tbl[6], pline = tbl[8];
        U fn_offs = tbl[17];
        U sd_n = tbl[49], sd_cut_at = tbl[50], sd_cut = tbl[51];
        U w = 0;
        for (U i = 0; i < sd_n; i++){
            U at = ELEM(pat, i);
            U keep = 0, na2 = at;
            if (at < sd_cut_at) keep = 1;
            if (at >= 41){ keep = 1; na2 = at - sd_cut; }
            if (keep == 1){
                if (w != i){
                    ELEM(pkind, w) = ELEM(pkind, i);
                    ELEM(pkid, w)  = ELEM(pkid, i);
                    ELEM(pval, w)  = ELEM(pval, i);
                    ELEM(pline, w) = ELEM(pline, i);
                }
                ELEM(pat, w) = na2;
                w++;
            }
        }
        *(U*)(pat + 8) = w;
        *(U*)(pkind + 8) = w;
        *(U*)(pkid + 8) = w;
        *(U*)(pval + 8) = w;
        *(U*)(pline + 8) = w;
        U fo_n = LLEN(fn_offs);
        for (U j = 0; j < fo_n; j++)
            ELEM(fn_offs, j) = ELEM(fn_offs, j) - sd_cut;
        return w;
    }
}
