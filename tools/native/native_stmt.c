/* Native statement lowering: 1:1 port of stmt() (compilers/shared/
 * cx86_p3.sov:1401-2037) for the role fast-path lines body() routes to
 * _sov_stmt (statement tree != 0, role in {1,3,4,5,6,7,9}).  Every state
 * mutation and emitter runs through the caller-provided st_tbl function
 * table with the Sovren ABI: args rdi,rsi,rdx,rcx,r8,r9,r10; result rax.
 * bt_ci is saved and cleared at entry exactly like the interpreted body
 * and restored before every fallback to it, so a fallback re-runs the
 * identical interpreted path.  No external symbols, no relocations, no
 * string literals, no static state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);
typedef U (*F3)(U,U,U);
typedef U (*F4)(U,U,U,U);
#define NOSLOT ((U)-1)

/* table slots (byte offset / 8); layout mirrors st_tbl_init in cx86_p3.sov */
enum {
 T_CAP=0,
 G_TREE=1, G_ROLE=2, G_SLINE=3, G_CI=4, G_SH=5, G_BTOK=6, G_MODE=7,
 G_IR=8, G_BDS=9, G_BDSL=10, G_DBG=11, G_OC=12, G_ERLN=13, G_IMNAMES=14,
 G_CPNM=15, G_CPPK=16, G_BRDEPTH=17, G_HASVM=18, G_LEAF8=19, G_ENTRY=20,
 G_SXE=21, G_FWON=22, G_NOFRAME=23, G_INLD=24, G_DSOK=25, G_TKRUN=26,
 G_OPTIMM=27, G_DIDSTOS=28, G_KN=29, G_KV=30, G_CEMT=31, G_LEXTXT=32,
 G_DBGPCS=33, G_DBGLNS=34, G_BK=35, G_BX=36, G_CPBID=37, G_CPGEN=38,
 K_USE=39, K_IMMUTABLE=40, K_PRIVATE=41, K_WIPE=42, K_JOIN=43, K_PRINT=44,
 K_RETURN=45, K_STOP=46, K_LEAVE=47, K_TRY=48, K_EXCEPT=49, K_WHILE=50,
 K_FOREVER=51, K_REPEAT=52,
 S_LINELONG=53, S_ERR=54, S_IMMUT=55, S_P1=56, S_M1=57, S_P=58, S_M=59,
 S_ASTEXT=60, S_ASPTR=61, S_NL=62, S_PRINT=63, S_PRINTINT=64, S_STRLEN=65,
 S_PEEKBYTE=66, S_BADLINE=67, S_LEAVECROSS=68, S_LEAVENEED=69,
 S_LISTSET=70, S_COMMA=71, S_RPAREN=72,
 SI_CI=73, SI_CPNM=74, SI_CPPK=75, SI_CCHMOD=76, SI_FWON=77, SI_USEDPR=78,
 SI_USEDPI=79, SI_USEDSL=80, SI_SAWSTR=81, SI_VALDEAD=82, SI_RAXSMALL=83,
 SI_KN=84, SI_KV=85, SI_CPLN=86, SI_CPTXT=87, SI_CPBID0=88, SI_CPGEN0=89,
 SI_CPDEP0=90, SI_DBGPCS=91, SI_DBGLNS=92,
 A_HADERR=93, A_KIDINIT=94, A_JOINOP=95, A_MOVRDI=96, A_XOR=97, A_JZ=98,
 A_JMP=99, A_SYSDO=100, A_LEAVE=101, A_RET=102, A_CANARY=103,
 A_RESTORES=104, A_FRAMEWIPE=105, A_STMTLEAVEOP=106, A_CFLUSHALL=107,
 A_HERE=108, A_ERRWHERE=109,
 A_STMT=110, A_TRYTAIL=111, A_FASTRET=112, A_STRIP=113, A_LENGTH=114,
 A_WORDID=115, A_INCVAR=116, A_DECVAR=117, A_EXPR=118, A_ADDRAXSLOT=119,
 A_SUBRAXSLOT=120, A_ADDRAXMEM=121, A_MEMSCALED=122, A_MEMABSSCALED=123,
 A_LSHFINDS=124, A_REGSLOT=125, A_CFLUSH=126, A_NUMOF=127, A_STOREV=128,
 A_LOADV=129, A_RAXIMM=130, A_DROPSTR=131, A_MARKSTR=132, A_CNLOOKUP=133,
 A_GNLOOKUP=134, A_LITEXPRLEN=135, A_RHSPURE=136, A_TRYALLOCIMM=137,
 A_EXPRATOM=138, A_EXPRATOMWORD=139, A_ISIMM=140, A_FINDLASTSP=141,
 A_ENDSTIMES=142, A_UNESC=143, A_EMITWRITELIT=144, A_PRINTCONST=145,
 A_I2S=146, A_CALLN=147, A_EMIT=148, A_SYNLOWER=149, A_PRINT=150,
 A_SOVPRINT=151, A_INTERNKID=152, A_IXNAMEOK=153,
 A_INTERNKIDN=154, A_IXFIND=155, A_LISTFIND=156, A_LOOK=157, A_ADDIMM=158,
 A_ADDINTO=159, A_SUBINTO=160, A_PLOGKN=161, A_PLOGSTR=162, A_STRCAT=163,
 A_TRYSLOT=164, A_TRYDEF=165, A_TRYCHAIN=166, A_TRYINFIX=167,
 A_TRYSTMTINL=168, A_EMIT2=169, A_LISTADD=170,
 A_CUT=171, A_REPL=172, A_CSET=173, A_DOPRINTTIMES=174, A_EMIT3=175,
 A_EMITRAXSCALED=176, A_LISTSET=177,
 A_CUTN=178, A_SYNEXPR=179, A_EMITRAXABS=180,
 SI_CPOK=181, SI_CPKILL=182, A_SFA=183, A_SYSNUM=184, A_PATCH=185,
 A_JOIN=186,
 S_SP=187, S_US=188, S_LP=189, S_0X=190, S_0B=191, S_STRLENP=192,
 T_GPACK=193
};

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }
static inline U t3(U *t, U i, U a, U b, U c){ return ((F3)t[i])(a,b,c); }
static inline U t4(U *t, U i, U a, U b, U c, U d){ return ((F4)t[i])(a,b,c,d); }

/* pure byte helpers mirroring the .sov/runtime semantics exactly */
static inline unsigned pb(U s, U i){ return *(const unsigned char*)(s+i); }
static inline int digitb(unsigned b){ return b >= 48 && b <= 57; }
/* cfind1 (ccore.sov:158): first index of ch before the NUL, else -1 */
static U cfind1(U t, unsigned ch){
    if (!t) return NOSLOT;
    for (U i = 0; *(const unsigned char*)(t+i); i++)
        if (*(const unsigned char*)(t+i) == ch) return i;
    return NOSLOT;
}
/* _sov_str_eq: equal contents (both NUL-terminated, neither empty policy:
 * .sov returns 0 for a null pointer, 1 only on full byte equality) */
static int streq(U a, U b){
    if (!a || !b) return 0;
    const unsigned char *x = (const void*)a, *y = (const void*)b;
    while (*x && *x == *y){ x++; y++; }
    return *x == *y;
}
/* _sov_starts_with(s, pre) */
static int starts(U s, U pre){
    const unsigned char *x = (const void*)s, *p = (const void*)pre;
    U i = 0;
    while (p[i]){ if (x[i] != p[i]) return 0; i++; }
    return 1;
}
/* sg_match_n (compiler.sov:5557): needle s (len ls) at t[i..], t length tn.
 * The first-byte probe reads t[i] before any bound check, exactly like the
 * .sov body (peek_byte(t,i) with i possibly == tn reads the NUL). */
static int sgmn(U t, U i, U s, U ls, U tn){
    if (pb(s,0) != 0){ if (pb(t,i) != pb(s,0)) return 0; }
    if (i + ls > tn) return 0;
    if (ls == 0) return 1;
    for (U k = 1; k < ls; k++)
        if (pb(t,i+k) != pb(s,k)) return 0;
    return 1;
}

/* twin entry: rdi=line, rsi=st_tbl  (fn _sov_stmt) */
U sov_stmt_native(U line, U tbl){
    U *t = (U*)tbl;
    /* one packed read of the statement-stable globals (st_g_pack in
     * cx86_p3.sov): tree, role, sline, ci, sh, btok, mode, ir, bds, bdsl,
     * tkrun, dsok, inld, imnames, cppk, dbg.  Volatile globals (cp_nm,
     * lex_txt, cemt, bk, kn, kv, ...) stay per-read-point getters because
     * lane callbacks mutate them. */
    U pk[16];
    t1(t, T_GPACK, (U)pk);
    U tree = 0, role = 0;
    U sline = pk[2];
    if (line == sline && sline != 0){ tree = pk[0]; role = pk[1]; }
    /* p3.sov:1410-1412 */
    U st_ci = pk[3];
    U st_sh = pk[4];
    t1(t, SI_CI, NOSLOT);
    /* fallback helper: restore bt_ci, run the whole interpreted body */
    #define FB() do{ t1(t, SI_CI, st_ci); return t1(t, A_STMT, line); }while(0)
    /* p3.sov:1413-1415 */
    if (pk[14] == 1){ t1(t, SI_CPNM, 0); t1(t, SI_CPPK, 0); }
    /* kid ids and message strings are table constants (st_tbl_init ran
     * kid_init), so the per-statement kid_init() call is redundant here. */
    /* p3.sov:1420-1429.  _sov_stmt is only called on role fast-path lines
     * (tree != 0, role in {1,3,4,5,6,7,9}); anything else, or an immutable
     * line (which grows im_names mid-forest), is the interpreted body's. */
    if (tree == 0 || (role != 1 && role != 3 && role != 4 && role != 5 &&
                      role != 6 && role != 7 && role != 9)) FB();
    if (role != 1){
        U tzz0 = pb(line, 0);
        if (tzz0 == 114){ if (t1(t, A_TRYTAIL, line) == 1) return 0; }
        if (tzz0 == 32){ if (t1(t, A_TRYTAIL, line) == 1) return 0; }
        if (t1(t, A_FASTRET, line) == 1) return 0;
    }
    /* p3.sov:1430-1433 */
    if (pk[15] == 1){
        if (t0(t, G_OC) != 0){
            U pcs = t0(t, G_DBGPCS);
            pcs = t2(t, A_LISTADD, pcs, t0(t, A_HERE));
            t1(t, SI_DBGPCS, pcs);
            U lns = t0(t, G_DBGLNS);
            lns = t2(t, A_LISTADD, lns, t0(t, G_ERLN));
            t1(t, SI_DBGLNS, lns);
        }
    }
    /* p3.sov:1434-1446 */
    U s = line;
    if (pb(line, 0) < 33){
        s = t1(t, A_STRIP, line);
    } else {
        long long ln = -1;
        if (line == pk[8]) ln = (long long)pk[9];
        if (ln < 0) ln = (long long)t1(t, A_LENGTH, line);
        if (ln > 0 && pb(line, (U)(ln-1)) < 33) s = t1(t, A_STRIP, line);
    }
    if (pb(s, 0) == 0) return 0;                       /* p3.sov:1447-1448 */
    if (pb(s, 0) == 35) return 0;                      /* p3.sov:1449-1450 */
    /* tree != 0: the fxreg/compound branch (1451-1456) is dead. */
    t1(t, SI_CCHMOD, 0);                               /* p3.sov:1457-1458 */
    /* p3.sov:1459-1467 */
    long long st_sl = -1;
    if (st_ci != NOSLOT && pk[5] == 1 && pk[6] > 0){
        U ir = pk[7];
        U bn = *(U*)(ir + 8);
        if (*(U*)(ir + 16 + bn*40 + st_ci*8) == 0 &&
            *(U*)(ir + 16 + bn*32 + st_ci*8) == 0)
            st_sl = (long long)(*(U*)(ir + 16 + (bn*6 + st_ci)*8)) - (long long)st_sh;
    }
    if (st_sl < 0) st_sl = (long long)t1(t, A_LENGTH, s);
    t1(t, SI_RAXSMALL, 0);                             /* p3.sov:1468 */
    /* p3.sov:1469-1493: bt_hasq stays -1 for tree lines, so the quote
     * parity walk never runs.  p3.sov:1494-1498: */
    if (st_sl > 1000){
        t1(t, A_PRINT, t[S_LINELONG]);
        t0(t, A_ERRWHERE);
        t0(t, A_HADERR);
        return 0;
    }
    /* p3.sov:1499-1505 (the wid_hp cache is a pure memo; word_id is the
     * same answer) */
    U wid = t1(t, A_WORDID, s);
    if (wid == t[K_USE]) return 0;
    if (wid == t[K_IMMUTABLE]) FB();                   /* p3.sov:1506-1519 */
    /* p3.sov:1520-1541 (im_skip is always 0 here) */
    long long col = -1;
    int bt_hasc = 0;
    if (pk[5] == 1 && st_ci != NOSLOT){
        U ir = pk[7];
        U bn = *(U*)(ir + 8);
        U bc_raw = *(U*)(ir + 16 + bn*16 + st_ci*8);
        bt_hasc = 1;
        if (bc_raw != NOSLOT) col = (long long)bc_raw - (long long)st_sh;
    }
    if (bt_hasc == 0) col = (long long)cfind1(s, 58);

    if (col > 0 && col < (long long)t1(t, A_LENGTH, s) - 1){
        /* ---------------- assignment lane (p3.sov:1542-1859) ------------ */
        int ds_go = 0;
        if (pk[10] == 0){
            if (pk[11] == 1) ds_go = 1;
            if ((long long)pk[12] > 0) ds_go = 1;
        }
        U var, rhs; long long vn, rn;
        if (ds_go){
            /* destructive split (p3.sov:1558-1628) */
            U dsv = (U)col;
            for (;;){
                unsigned dsb = pb(s, dsv-1);
                if (dsb == 32 || dsb == 9 || dsb == 10 || dsb == 13) dsv--;
                else break;
            }
            if (tree != 0 && role == 1){
                var = t2(t, A_INTERNKIDN, s, dsv);
            } else {
                *(unsigned char*)(s + dsv) = 0;
                for (U dsi = 0; dsi < dsv; dsi++)
                    if (pb(s, dsi) == 32) *(unsigned char*)(s + dsi) = 95;
                if ((long long)t2(t, A_IXFIND, s, dsv) < 0)
                    var = t2(t, A_INTERNKIDN, s, dsv);
                else
                    var = s;
            }
            vn = (long long)dsv;
            U dsr = (U)col + 1;
            for (;;){
                unsigned dsb = pb(s, dsr);
                if (dsb == 32 || dsb == 9 || dsb == 10 || dsb == 13) dsr++;
                else break;
            }
            U dse = (U)st_sl;
            for (;;){
                if (dse <= dsr) break;
                unsigned dsb = pb(s, dse-1);
                if (dsb == 32 || dsb == 9 || dsb == 10 || dsb == 13) dse--;
                else break;
            }
            *(unsigned char*)(s + dse) = 0;
            rhs = s + dsr;
            rn = (long long)(dse - dsr);
        } else {
            /* p3.sov:1630-1635 */
            var = t3(t, A_REPL, t1(t, A_STRIP, t4(t, A_CUTN, s, 0, (U)col, (U)st_sl)),
                     t[S_SP], t[S_US]);
            rhs = t1(t, A_STRIP, t4(t, A_CUTN, s, (U)col + 1, (U)st_sl, (U)st_sl));
            vn = (long long)t1(t, A_LENGTH, var);
            rn = (long long)t1(t, A_LENGTH, rhs);
            if ((long long)t2(t, A_IXFIND, var, (U)vn) < 0)
                var = t2(t, A_INTERNKIDN, var, (U)vn);
        }
        /* p3.sov:1636-1646: indexed-store rewrite (runs when role != 1) */
        if (role != 1){
            long long ix_w = (long long)t2(t, A_IXFIND, var, (U)vn);
            if (ix_w > 0){
                U head = t3(t, A_CUT, var, 0, (U)ix_w);
                if (t1(t, A_IXNAMEOK, head) == 1){
                    tree = 0;
                    U ix_bn = t1(t, A_INTERNKID, head);
                    U ix_bi = t3(t, A_CUT, var, (U)ix_w + 1, (U)vn - 1);
                    rhs = t2(t, A_STRCAT, t[S_LISTSET],
                          t2(t, A_STRCAT, ix_bn,
                          t2(t, A_STRCAT, t[S_COMMA],
                          t2(t, A_STRCAT, ix_bi,
                          t2(t, A_STRCAT, t[S_COMMA],
                          t2(t, A_STRCAT, rhs, t[S_RPAREN]))))));
                    var = ix_bn;
                    vn = (long long)t1(t, A_LENGTH, var);
                    rn = (long long)t1(t, A_LENGTH, rhs);
                }
            }
        }
        /* p3.sov:1647-1655 (im_skip is 0, so the hit is the error path) */
        U imn = pk[13];
        if (imn != 0 && *(U*)(imn + 8) > 0){
            if ((long long)t2(t, A_LISTFIND, imn, var) > -1){
                t1(t, A_PRINT, t2(t, A_JOIN, t[S_ERR],
                                  t2(t, A_JOIN, var, t[S_IMMUT])));
                t1(t, A_SOVPRINT, s);
                t0(t, A_ERRWHERE);
                t0(t, A_HADERR);
                return 0;
            }
        }
        /* p3.sov:1656 */
        if (t4(t, A_SFA, tree, role, var, rhs) == 1) return 0;
        /* p3.sov:1657-1677 */
        long long cpx_p = (long long)t1(t, A_LITEXPRLEN, rhs);
        U cpx_t = t0(t, G_LEXTXT);
        if (cpx_p > -1){
            U cp = t0(t, G_CPNM);
            if (cp != 0){ if (streq(var, cp)) t1(t, SI_CPNM, 0); }
        } else {
            U cp = t0(t, G_CPNM);
            if (cp != 0){
                if (streq(var, cp)) t1(t, SI_CPNM, 0);
                else {
                    if (t1(t, A_RHSPURE, rhs) == 0){
                        if ((long long)t2(t, A_LOOK, rhs, cp) < 0) t1(t, SI_CPNM, 0);
                        else t1(t, SI_CPPK, 1);
                    }
                }
            }
        }
        /* p3.sov:1678-1685 */
        if (rn == vn + 4){
            if (sgmn(rhs, 0, var, (U)vn, (U)rn) == 1){
                if (sgmn(rhs, (U)vn, t[S_P1], 4, (U)rn) == 1){ t1(t, A_INCVAR, var); return 0; }
                if (sgmn(rhs, (U)vn, t[S_M1], 4, (U)rn) == 1){ t1(t, A_DECVAR, var); return 0; }
            }
        }
        /* p3.sov:1686-1699 */
        if (t2(t, A_TRYSLOT, var, rhs) == 1){ t1(t, A_DROPSTR, var); return 0; }
        if (t2(t, A_TRYDEF, var, rhs) == 1){ t1(t, A_DROPSTR, var); return 0; }
        if (t2(t, A_TRYCHAIN, var, rhs) == 1){ t1(t, A_DROPSTR, var); return 0; }
        if (t2(t, A_TRYINFIX, var, rhs) == 1){ t1(t, A_DROPSTR, var); return 0; }
        if (t2(t, A_TRYSTMTINL, var, rhs) == 1) return 0;
        /* p3.sov:1700-1742: var + other */
        if (rn > vn + 3){
            if (sgmn(rhs, 0, var, (U)vn, (U)rn) == 1){
                if (sgmn(rhs, (U)vn, t[S_P], 3, (U)rn) == 1){
                    U other = t1(t, A_STRIP, t3(t, A_CUT, rhs, (U)vn + 3, (U)rn));
                    if ((long long)t1(t, A_LENGTH, other) > 0){
                        if ((long long)t2(t, A_LOOK, other, t[S_LP]) < 0){
                            if ((long long)t2(t, A_LOOK, other, t[S_SP]) < 0){
                                if (digitb(pb(other, 0))){
                                    t2(t, A_ADDIMM, var, t1(t, A_NUMOF, other));
                                    t1(t, A_DROPSTR, var);
                                    return 0;
                                }
                                t2(t, A_ADDINTO, var, t3(t, A_REPL, other, t[S_SP], t[S_US]));
                                t1(t, A_DROPSTR, var);
                                return 0;
                            }
                            U rs = t1(t, A_REGSLOT, var);
                            if ((long long)rs > -1){
                                t1(t, A_CFLUSH, var);
                                t1(t, SI_CPOK, 1);
                                t1(t, SI_CPKILL, 0);
                                t1(t, A_EXPR, other);
                                t1(t, SI_CPOK, 0);
                                t1(t, A_ADDRAXSLOT, rs);
                                t1(t, A_DROPSTR, var);
                                return 0;
                            } else {
                                long long sl6 = (long long)t1(t, A_LSHFINDS, var);
                                if (sl6 > 4){
                                    U mm3 = t1(t, A_MEMSCALED, other);
                                    if (mm3 != NOSLOT){
                                        t1(t, A_CFLUSH, var);
                                        U ms3 = mm3 >> 16;
                                        U mq3 = mm3 & 0xFFFF;
                                        t3(t, A_EMITRAXSCALED, ms3, mq3 >> 12, (mq3 & 4095) - 128);
                                        t1(t, A_ADDRAXMEM, (U)sl6);
                                        t1(t, A_DROPSTR, var);
                                        return 0;
                                    }
                                    U mm4 = t1(t, A_MEMABSSCALED, other);
                                    if (mm4 != NOSLOT){
                                        t1(t, A_CFLUSH, var);
                                        t2(t, A_EMITRAXABS, (mm4 >> 32) - 1, mm4 & 0xFFFFFFFF);
                                        t1(t, A_ADDRAXMEM, (U)sl6);
                                        t1(t, A_DROPSTR, var);
                                        return 0;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        /* p3.sov:1743-1766: var - other */
        if (rn > vn + 3){
            if (sgmn(rhs, 0, var, (U)vn, (U)rn) == 1){
                if (sgmn(rhs, (U)vn, t[S_M], 3, (U)rn) == 1){
                    U other = t1(t, A_STRIP, t3(t, A_CUT, rhs, (U)vn + 3, (U)rn));
                    if ((long long)t1(t, A_LENGTH, other) > 0){
                        if ((long long)t2(t, A_LOOK, other, t[S_LP]) < 0){
                            if ((long long)t2(t, A_LOOK, other, t[S_SP]) < 0){
                                if (digitb(pb(other, 0))){
                                    t2(t, A_ADDIMM, var, 0 - t1(t, A_NUMOF, other));
                                    t1(t, A_DROPSTR, var);
                                    return 0;
                                }
                                t2(t, A_SUBINTO, var, t3(t, A_REPL, other, t[S_SP], t[S_US]));
                                t1(t, A_DROPSTR, var);
                                return 0;
                            }
                            U rs = t1(t, A_REGSLOT, var);
                            if ((long long)rs > -1){
                                t1(t, A_CFLUSH, var);
                                t1(t, SI_CPOK, 1);
                                t1(t, SI_CPKILL, 0);
                                t1(t, A_EXPR, other);
                                t1(t, SI_CPOK, 0);
                                t1(t, A_SUBRAXSLOT, rs);
                                t1(t, A_DROPSTR, var);
                                return 0;
                            }
                        }
                    }
                }
            }
        }
        /* p3.sov:1767-1781 */
        if ((long long)t1(t, A_LENGTH, rhs) > 0){
            if (digitb(pb(rhs, 0))){
                if ((long long)t2(t, A_LOOK, rhs, t[S_SP]) < 0){
                    if ((long long)t0(t, G_BRDEPTH) == 0){
                        U nv = t1(t, A_NUMOF, rhs);
                        if (cfind1(rhs, 46) != NOSLOT){} else t2(t, A_CSET, var, nv);
                        if ((long long)nv > 0){
                            t1(t, SI_KN, var);
                            t1(t, SI_KV, nv);
                            t2(t, A_PLOGKN, nv, var);
                        }
                        t1(t, A_DROPSTR, var);
                        if ((long long)t0(t, G_HASVM) == 0){
                            if (cfind1(rhs, 46) != NOSLOT){} else return 0;
                        }
                    }
                }
            }
        }
        /* p3.sov:1782-1784 */
        if (t2(t, A_TRYALLOCIMM, var, rhs) == 1){
            t1(t, A_MARKSTR, var);
            return 0;
        }
        /* p3.sov:1785-1811 */
        if ((long long)t1(t, A_LENGTH, rhs) == 1){
            if (pb(rhs, 0) == 48){
                long long zl = (long long)t1(t, A_LSHFINDS, var);
                if (zl > -1){
                    if ((long long)t1(t, A_GNLOOKUP, var) < 0){
                        if (zl < 5){
                            t2(t, A_CSET, var, 0);
                            if (zl == 0) t3(t, A_EMIT3, 72, 49, 219);
                            else { t2(t, A_EMIT2, 77, 49); t1(t, A_EMIT, 192 + 9 * (zl + 3)); }
                            U zi = t1(t, A_CNLOOKUP, var);
                            t3(t, A_LISTSET, t0(t, G_CEMT), zi, 1);
                            t2(t, A_PLOGSTR, 4, var);
                            t1(t, A_DROPSTR, var);
                            return 0;
                        }
                        if ((long long)t0(t, G_LEAF8) == 1){
                            if (zl < 9){
                                t2(t, A_CSET, var, 0);
                                t2(t, A_EMIT2, 77, 49);
                                t1(t, A_EMIT, 192 + 9 * (zl - 5));
                                U zi = t1(t, A_CNLOOKUP, var);
                                t3(t, A_LISTSET, t0(t, G_CEMT), zi, 1);
                                t2(t, A_PLOGSTR, 4, var);
                                t1(t, A_DROPSTR, var);
                                return 0;
                            }
                        }
                    }
                }
            }
        }
        /* p3.sov:1812-1838 */
        U fa0 = pb(rhs, 0);
        int fa_go = 0;
        if (digitb((unsigned)fa0)){
            if (cfind1(rhs, 32) != NOSLOT){} else {
                if (starts(rhs, t[S_0X])){ t1(t, A_RAXIMM, t1(t, A_NUMOF, rhs)); fa_go = 1; }
                if (!fa_go){
                    if (starts(rhs, t[S_0B])){ t1(t, A_RAXIMM, t1(t, A_NUMOF, rhs)); fa_go = 1; }
                }
                if (!fa_go){
                    if (t1(t, A_ISIMM, rhs) == 1){ t1(t, A_RAXIMM, t1(t, A_NUMOF, rhs)); fa_go = 1; }
                }
            }
        }
        if (!fa_go){
            if ((long long)t2(t, A_LOOK, rhs, t[S_SP]) < 0){
                if ((long long)t2(t, A_LOOK, rhs, t[S_LP]) < 0){
                    if (t1(t, A_EXPRATOM, rhs) == 1){
                        if (t1(t, A_EXPRATOMWORD, rhs) == 1){
                            t1(t, A_LOADV, rhs);
                            fa_go = 1;
                        }
                    }
                }
            }
        }
        if (fa_go){
            t1(t, A_STOREV, var);
            t1(t, A_DROPSTR, var);
            return 0;
        }
        /* p3.sov:1839-1859 */
        t1(t, SI_CPOK, 1);
        t1(t, SI_CPKILL, 0);
        U typ = t4(t, A_SYNEXPR, tree, role, 1, rhs);
        t1(t, SI_CPOK, 0);
        t1(t, A_STOREV, var);
        if (cpx_p > -1){
            t1(t, SI_CPNM, var);
            t1(t, SI_CPLN, (U)cpx_p);
            t1(t, SI_CPTXT, cpx_t);
            t1(t, SI_CPBID0, t0(t, G_CPBID));
            t1(t, SI_CPGEN0, t0(t, G_CPGEN));
            U bkl = t0(t, G_BK);
            U dep = bkl ? *(U*)(bkl + 8) : 0;
            t1(t, SI_CPDEP0, dep);
        }
        if (typ == 1) t1(t, A_MARKSTR, var); else t1(t, A_DROPSTR, var);
        if (starts(rhs, t[S_STRLENP])){
            if ((long long)t0(t, G_DIDSTOS) == 1){
                if ((long long)t0(t, G_KV) > 0) t1(t, SI_KN, var);
            }
        }
        return 0;
    }
    /* p3.sov:1860-1863 */
    t1(t, SI_CPNM, 0);
    if (wid == t[K_PRIVATE]){ t1(t, SI_FWON, 1); return 0; }
    /* p3.sov:1864-1877 */
    if (wid == t[K_WIPE]){
        t1(t, A_EXPR, t1(t, A_STRIP, t3(t, A_CUT, s, 5, t1(t, A_LENGTH, s))));
        t0(t, A_MOVRDI);
        t3(t, A_EMIT3, 72, 133, 255);
        U wsk = t0(t, A_JZ);
        t1(t, A_EMIT, 87);
        t1(t, SI_USEDSL, 1);
        t1(t, A_CALLN, t[S_STRLEN]);
        t3(t, A_EMIT3, 72, 137, 193);
        t1(t, A_EMIT, 95);
        t0(t, A_XOR);
        t3(t, A_EMIT3, 252, 243, 170);
        t1(t, A_PATCH, wsk);
        return 0;
    }
    /* p3.sov:1878-1884 */
    if (wid == t[K_JOIN]){
        if (tree != 0 && role == 6) t1(t, A_SYNLOWER, tree);
        else t1(t, A_EXPR, t1(t, A_STRIP, t3(t, A_CUT, s, 5, t1(t, A_LENGTH, s))));
        t0(t, A_JOINOP);
        return 0;
    }
    /* p3.sov:1885-1926 */
    if (wid == t[K_PRINT]){
        U arg = t1(t, A_STRIP, t3(t, A_CUT, s, 6, t1(t, A_LENGTH, s)));
        if (t1(t, A_ENDSTIMES, arg) == 1){
            U head = t1(t, A_STRIP, t3(t, A_CUT, arg, 0, t1(t, A_LENGTH, arg) - 6));
            long long sp = (long long)t1(t, A_FINDLASTSP, head);
            if (sp > -1){
                t2(t, A_DOPRINTTIMES,
                   t1(t, A_STRIP, t3(t, A_CUT, head, 0, (U)sp)),
                   t1(t, A_STRIP, t3(t, A_CUT, head, (U)sp + 1, t1(t, A_LENGTH, head))));
                return 0;
            }
        }
        U alen = t1(t, A_LENGTH, arg);
        if (alen >= 8){
            if (sgmn(arg, alen - 8, t[S_ASTEXT], 8, alen) == 1){
                t1(t, A_EXPR, t3(t, A_CUT, arg, 0, alen - 8));
                t0(t, A_MOVRDI);
                t1(t, SI_USEDPR, 1);
                t1(t, A_CALLN, t[S_PRINT]);
                return 0;
            }
        }
        if (alen >= 7){
            if (sgmn(arg, alen - 7, t[S_ASPTR], 7, alen) == 1){
                t1(t, A_EXPR, t3(t, A_CUT, arg, 0, alen - 7));
                t0(t, A_MOVRDI);
                t1(t, SI_USEDPR, 1);
                t1(t, A_CALLN, t[S_PRINT]);
                return 0;
            }
        }
        if (alen > 1){
            if (pb(arg, 0) == 34){
                U lit = t1(t, A_UNESC, t3(t, A_CUT, arg, 1, alen - 1));
                t1(t, A_EMITWRITELIT, t2(t, A_JOIN, lit, t[S_NL]));
                return 0;
            }
        }
        if (starts(arg, t[S_PEEKBYTE])){
            if ((long long)t0(t, G_OPTIMM) > 0){
                t1(t, A_EMITWRITELIT, t1(t, A_I2S, t0(t, G_OPTIMM)));
                return 0;
            }
        }
        if (t1(t, A_PRINTCONST, arg) == 1) return 0;
        U typ = t4(t, A_SYNEXPR, tree, role, 3, arg);
        t0(t, A_MOVRDI);
        if (typ == 1){ t1(t, SI_USEDPR, 1); t1(t, A_CALLN, t[S_PRINT]); }
        else { t1(t, SI_USEDPI, 1); t1(t, A_CALLN, t[S_PRINTINT]); }
        return 0;
    }
    /* p3.sov:1927-1951 */
    if (wid == t[K_RETURN]){
        if (pb(s, 6) == 0){
            if ((long long)t0(t, G_ENTRY) == 1){
                if ((long long)t0(t, G_SXE) == 1){ t0(t, A_XOR); t0(t, A_LEAVE); t0(t, A_RET); }
                else { t2(t, A_EMIT2, 49, 255); t1(t, A_SYSNUM, 60); t0(t, A_SYSDO); }
                return 0;
            }
            if ((long long)t0(t, G_FWON) == 1){
                if ((long long)t0(t, G_NOFRAME) == 0){
                    t0(t, A_CANARY);
                    t0(t, A_XOR);
                    t0(t, A_RESTORES);
                    t0(t, A_FRAMEWIPE);
                    t0(t, A_STMTLEAVEOP);
                    t0(t, A_RET);
                    return 0;
                }
            }
            t0(t, A_XOR);
            t0(t, A_LEAVE);
            t0(t, A_RET);
            return 0;
        }
    }
    /* p3.sov:1952-1978 */
    if (wid == t[K_RETURN]){
        if (pb(s, 6) == 32){
            U typ = t4(t, A_SYNEXPR, tree, role, 4, s + 7);
            if (typ == 1) t1(t, SI_SAWSTR, 1);
            if ((long long)t0(t, G_ENTRY) == 1){
                if ((long long)t0(t, G_SXE) == 1){ t0(t, A_LEAVE); t0(t, A_RET); }
                else { t3(t, A_EMIT3, 72, 137, 199); t1(t, A_SYSNUM, 60); t0(t, A_SYSDO); }
                return 0;
            }
            if ((long long)t0(t, G_FWON) == 1){
                if ((long long)t0(t, G_NOFRAME) == 0){
                    t0(t, A_CANARY);
                    t1(t, A_EMIT, 80);
                    t0(t, A_RESTORES);
                    t0(t, A_FRAMEWIPE);
                    t1(t, A_EMIT, 88);
                    t0(t, A_STMTLEAVEOP);
                    t0(t, A_RET);
                    return 0;
                }
            }
            t0(t, A_LEAVE);
            t0(t, A_RET);
            return 0;
        }
    }
    /* p3.sov:1979-1983 */
    if (wid == t[K_STOP]){
        t2(t, A_EMIT2, 49, 255);
        t1(t, A_SYSNUM, 60);
        t0(t, A_SYSDO);
        return 0;
    }
    /* p3.sov:1984-2028 */
    if (wid == t[K_LEAVE]){
        U bkl = t0(t, G_BK);
        long long ld = (long long)(bkl ? *(U*)(bkl + 8) : 0) - 1;
        long long lfound = 0;
        int lbad = 0;
        while (ld > -1){
            U lkind = *(U*)(bkl + 16 + (U)ld * 8);
            if (lkind == t[K_TRY])      { lbad = 1; ld = -1; }
            else if (lkind == t[K_EXCEPT]) { lbad = 1; ld = -1; }
            else if (lkind == t[K_WHILE])  { lfound = ld + 1; ld = -1; }
            else if (lkind == t[K_FOREVER]){ lfound = ld + 1; ld = -1; }
            else if (lkind == t[K_REPEAT]) { lfound = ld + 1; ld = -1; }
            else ld = ld - 1;
        }
        if (lbad == 1){
            t1(t, A_PRINT, t[S_LEAVECROSS]);
            t1(t, A_SOVPRINT, s);
            t0(t, A_ERRWHERE);
            t0(t, A_HADERR);
            return 0;
        }
        if (lfound == 0){
            t1(t, A_PRINT, t[S_LEAVENEED]);
            t1(t, A_SOVPRINT, s);
            t0(t, A_ERRWHERE);
            t0(t, A_HADERR);
            return 0;
        }
        ld = lfound - 1;
        t0(t, A_CFLUSHALL);
        U bxl = t0(t, G_BX);
        U lx = *(U*)(bxl + 16 + (U)ld * 8);
        lx = t2(t, A_LISTADD, lx, t0(t, A_JMP));
        t3(t, A_LISTSET, bxl, (U)ld, lx);
        return 0;
    }
    /* p3.sov:2029-2037 */
    if ((long long)t2(t, A_LOOK, s, t[S_LP]) < 0){
        t1(t, A_PRINT, t[S_BADLINE]);
        t1(t, A_SOVPRINT, s);
        t0(t, A_ERRWHERE);
        t0(t, A_HADERR);
        return 0;
    }
    t1(t, SI_VALDEAD, 1);
    t4(t, A_SYNEXPR, tree, role, 5, s);
    t1(t, SI_VALDEAD, 0);
    return 0;
}
