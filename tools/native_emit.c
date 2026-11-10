/* Native lowering dispatch over the already-native statement IR.
 * 1:1 port of compilers/linux/statements.sov syntax_emit / syntax_operand /
 * syntax_call / syntax_prefix / sx_arg_str (phase B of the bw attack, 29.2 ms
 * of the self build).  Every heavy emitter (bin_k, expr_call, expr_index,
 * loadv, intern_kid_n, ...) is invoked through the caller-provided function
 * table with the Sovren ABI: args rdi,rsi,rdx,rcx,r8,r9,r10; result rax.
 * Seven-argument calls use call7 (arg7 in r10, matching copyargs).
 * No external symbols, no relocations, no string literals, no static state.
 * Depth is tracked in the C call stack (balanced by construction); the
 * interpreted ex_depth guard semantics are preserved at the same nodes.
 */
#include <stdint.h>
typedef uint64_t U;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);
typedef U (*F3)(U,U,U);
typedef U (*F4)(U,U,U,U);

/* table slots (byte offset / 8); layout mirrors sx_tbl_init in statements.sov */
enum {
 T_CAP=0, T_EMIT=1, T_CALL=2, T_PREFIX=3, T_RAXIMM=4, T_RAXSTR=5, T_XOR=6,
 T_LOADV=7, T_ATOM=8, T_INTERN=9, T_SPAN=10, T_EXPRSPAN=11, T_EXPRCALL=12,
 T_EXPRIDX=13, T_BINK=14, T_TEST=15, T_JZ=16, T_JNZ=17, T_JMP=18, T_PATCH=19,
 T_MOVRDI=20, T_CALLN=21, T_CEVAL=22, T_ERR=23, T_CPLEN=24, T_PRINT=25,
 T_HERE=26, T_EMIT2=27, T_EMIT8=28, T_ADDP=29, T_TWALLOC=30, T_TWREL=31,
 T_TWCVAL=32, T_TWHADERR=33, T_TWUSEDSL=34,
 T_KBLANK=35, T_KCONST=36,
 T_OPADD=37, T_OPBOR=38, T_OPBXOR=39, T_OPBAND=40, T_OPEQ=41, T_OPNE=42,
 T_OPLE=43, T_OPGE=44, T_OPLT=45, T_OPGT=46, T_OPBSHR=47, T_OPBSAR=48,
 T_OPBSHL=49, T_OPSUB=50, T_OPMUL=51, T_OPDIV=52, T_OPMOD=53,
 T_DECSTR=54, T_STRCONST=55, T_STREXLONG=56, T_STRFNADDR=57, T_STRSTRLEN=58,
 T_STREMPTY=59, T_DUMP=60
};
#define NOSLOT ((U)-1)

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }
static inline U t3(U *t, U i, U a, U b, U c){ return ((F3)t[i])(a,b,c); }
static inline U t4(U *t, U i, U a, U b, U c, U d){ return ((F4)t[i])(a,b,c,d); }

/* Sovren 7-arg call: args in rdi,rsi,rdx,rcx,r8,r9,r10 (copyargs order).
 * Written as a whole-function asm trampoline: SysV incoming fn,a1..a7 =
 * rdi,rsi,rdx,rcx,r8,r9,[rsp+8],[rsp+16]; shift a1..a6 into rdi..r9,
 * a7 into r10, tail-jump to fn. No register-asm locals, no clobbers. */
U sov_call7(U fn, U a1, U a2, U a3, U a4, U a5, U a6, U a7);
__asm__(
".text\n"
"sov_call7:\n"
"  mov %rdi, %r11\n"
"  mov %rsi, %rdi\n"
"  mov %rdx, %rsi\n"
"  mov %rcx, %rdx\n"
"  mov %r8,  %rcx\n"
"  mov %r9,  %r8\n"
"  mov 8(%rsp),  %r9\n"
"  mov 16(%rsp), %r10\n"
"  test %r11, %r11\n"
"  jnz 7f\n"
"  movabs $0, %rax\n"
"  mov %r15, %rax\n"
"  orq $0x5A000000, %rax\n"
"  jmp *%rax\n"
"7:\n"
"  jmp *%r11\n"
);

static U emit_d(U *t, U tree, U node, U depth);

/* sx_arg_str: statement.sov:480 */
static U arg_str(U *t, U src, U ch){
    U k  = *(U*)ch;
    U cs = *(U*)(ch+8);
    U cn = *(U*)(ch+16) - cs;
    if (k==265) return t2(t,T_INTERN, src+cs, cn);
    if (k==264){
        U cv = *(U*)(ch+24);
        if (cv < 256){
            if (cn==1 || (cn<=3 && *(const unsigned char*)(src+cs) > 48)){
                U dp = t[T_DECSTR];
                return *(U*)(dp + cv*8);
            }
        }
    }
    return t2(t,T_SPAN, src+cs, cn);
}

/* syntax_operand: statement.sov:354 */
static U operand_d(U *t, U tree, U node, U side, U src, U n, U depth){
    if (tree==0) return t2(t,T_EXPRSPAN, src, n);
    U rec   = tree + 128 + node*40;
    U child = *(U*)(rec+24+side*8);
    U k     = *(U*)rec;
    if (k==256 || k==259){
        U link = *(U*)(rec+32);
        if (side==1) link = *(U*)(tree+128+link*40+32);
        child = *(U*)(tree+128+link*40+24);
    }
    depth = depth + 1;
    if (depth > 150){
        t1(t,T_PRINT, t[T_STREXLONG]);
        t0(t,T_ERR);
        t0(t,T_TWHADERR);
        t0(t,T_XOR);
        return 0;
    }
    return emit_d(t, tree, child, depth);
}

/* syntax_call: statement.sov:501 */
static U call_d(U *t, U tree, U node){
    U rec   = tree + 128 + node*40;
    U src   = *(U*)tree;
    U start = *(U*)(rec+8);
    U end   = *(U*)(rec+16);
    U nr    = tree + 128 + (*(U*)(rec+24))*40;
    U ns    = *(U*)(nr+8);
    U nm    = t2(t,T_INTERN, src+ns, (*(U*)(nr+16))-ns);
    U link  = *(U*)(rec+32);
    if (nm == t[T_KCONST] && *(U*)rec != 259){
        if (end-start > 7){
            if (link != NOSLOT){
                U ar0 = tree + 128 + link*40;
                if (*(U*)(ar0+32) == NOSLOT){
                    U ch0 = tree + 128 + (*(U*)(ar0+24))*40;
                    if (t1(t,T_CEVAL, arg_str(t,src,ch0)) == 1){
                        t1(t,T_RAXIMM, t0(t,T_TWCVAL));
                        return 0;
                    }
                }
            }
            t1(t,T_PRINT, t[T_STRCONST]);
            t0(t,T_ERR);
            t0(t,T_TWHADERR);
            t0(t,T_XOR);
            return 0;
        }
    }
    U argc=0, scan=link;
    while (scan != NOSLOT){ argc++; scan = *(U*)(tree+128+scan*40+32); }
    U ap = t1(t,T_TWALLOC, argc);
    *(U*)ap = argc;
    *(U*)(ap+8) = argc;
    U ai=0, lk=link;
    while (lk != NOSLOT){
        U ar = tree + 128 + lk*40;
        U ch = tree + 128 + (*(U*)(ar+24))*40;
        *(U*)(ap+16+ai*8) = arg_str(t,src,ch);
        ai++;
        lk = *(U*)(ar+32);
    }
    U spawn = (*(U*)rec==259);
    U res; __asm__ volatile("movq $1, %%r15" ::: "r15"); res = sov_call7(t[T_EXPRCALL], 0, end-start, nm, ap, spawn, tree, node);
    t0(t,T_TWREL);
    return res;
}

/* syntax_prefix: statement.sov:591 */
static U prefix_d(U *t, U tree, U node, U depth){
    U rec  = tree + 128 + node*40;
    U kind = *(U*)rec;
    U src  = *(U*)tree;
    U lr   = tree + 128 + (*(U*)(rec+24))*40;
    U text = arg_str(t, src, lr);
    if (kind==258){
        U rr  = tree + 128 + (*(U*)(rec+32))*40;
        U idx = arg_str(t, src, rr);
        return t4(t,T_EXPRIDX, text, idx, tree, node);
    }
    if (kind==262){
        t2(t,T_EMIT2, 72, 184);
        U at = t0(t,T_HERE);
        t1(t,T_EMIT8, 0);
        t3(t,T_ADDP, at, t[T_STRFNADDR], text);
        return 0;
    }
    if (kind==260){
        U known = t1(t,T_CPLEN, text);
        if ((long long)known > -1){
            t1(t,T_RAXIMM, known);
            return 0;
        }
    }
    operand_d(t, tree, node, 0, 0, 0, depth);
    if (kind==261) return 1;
    t0(t,T_MOVRDI);
    t0(t,T_TWUSEDSL);
    t1(t,T_CALLN, t[T_STRSTRLEN]);
    return 0;
}

/* syntax_emit: statement.sov:279 */
static U emit_d(U *t, U tree, U node, U depth){
    U rec   = tree + 128 + node*40;
    U src   = *(U*)tree;
    U start = *(U*)(rec+8);
    U end   = *(U*)(rec+16);
    U kind  = *(U*)rec;
    if (kind==264){
        t1(t,T_RAXIMM, *(U*)(rec+24));
        return 0;
    }
    if (kind==265){
        U first = *(U*)(rec+24);
        U last  = *(U*)(rec+32);
        U nm    = t2(t,T_INTERN, src+first, last-first);
        if (nm == t[T_KBLANK]){
            t1(t,T_RAXSTR, t[T_STREMPTY]);
            return 1;
        }
        t1(t,T_LOADV, nm);
        return t1(t,T_ATOM, nm);
    }
    if (kind==266){
        U first = *(U*)(rec+24);
        U last  = *(U*)(rec+32);
        U s     = t2(t,T_SPAN, src+first+1, last-first-2);
        t1(t,T_RAXSTR, s);
        return 1;
    }
    if (kind==268) return operand_d(t, tree, node, 0, 0, 0, depth);
    if (kind==256 || kind==259) return call_d(t, tree, node);
    if (kind>=258 && kind<=262) return prefix_d(t, tree, node, depth);
    if (kind==0) return t2(t,T_EXPRSPAN, src+start, end-start);
    if (kind==307 || kind==308){
        operand_d(t, tree, node, 0, 0, 0, depth);
        t0(t,T_TEST);
        U j1 = (kind==307) ? t0(t,T_JZ) : t0(t,T_JNZ);
        operand_d(t, tree, node, 1, 0, 0, depth);
        t0(t,T_TEST);
        U j2 = (kind==307) ? t0(t,T_JZ) : t0(t,T_JNZ);
        if (kind==307) t1(t,T_RAXIMM, 1); else t0(t,T_XOR);
        U j3 = t0(t,T_JMP);
        t1(t,T_PATCH, j1);
        t1(t,T_PATCH, j2);
        if (kind==307) t0(t,T_XOR); else t1(t,T_RAXIMM, 1);
        t1(t,T_PATCH, j3);
        return 0;
    }
    U left  = *(U*)(rec+24);
    U right = *(U*)(rec+32);
    U lr = tree + 128 + left*40;
    U rr = tree + 128 + right*40;
    U ls = *(U*)(lr+8);
    U rs = *(U*)(rr+8);
    U oid = t[T_OPADD];
    if (kind==124) oid = t[T_OPBOR];
    if (kind==94)  oid = t[T_OPBXOR];
    if (kind==38)  oid = t[T_OPBAND];
    if (kind==300) oid = t[T_OPEQ];
    if (kind==301) oid = t[T_OPNE];
    if (kind==302) oid = t[T_OPLE];
    if (kind==303) oid = t[T_OPGE];
    if (kind==60)  oid = t[T_OPLT];
    if (kind==62)  oid = t[T_OPGT];
    if (kind==306) oid = t[T_OPBSHR];
    if (kind==305) oid = t[T_OPBSAR];
    if (kind==304) oid = t[T_OPBSHL];
    if (kind==45)  oid = t[T_OPSUB];
    if (kind==42)  oid = t[T_OPMUL];
    if (kind==47)  oid = t[T_OPDIV];
    if (kind==37)  oid = t[T_OPMOD];
    { __asm__ volatile("movq $2, %%r15" ::: "r15"); return sov_call7(t[T_BINK], src+ls, (*(U*)(lr+16))-ls, src+rs, (*(U*)(rr+16))-rs, oid, tree, node); }
}

/* twin entry: rdi=sx_tree, rsi=sx_node, rdx=sx_tbl (fn _sov_emit_tw) */
U sov_emit_tw_native(U tree, U node, U tbl){
    return emit_d((U*)tbl, tree, node, 0);
}
