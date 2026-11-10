/* OLD reader side (renamed copy of tools/native_cxread.c, md5 0517bda6):
 * Native cx_read: the compact-form reader, C port with fused scanners
 * (C1 attack, first blob).  Byte-exact mirror of the interpreted cx_read in
 * compiler.sov: same two loops, same quote/block state machine, same helper
 * calls in the same left-to-right order.  The per-line leaf scanners
 * (sg_marks/sg_sqok/sg_ind/sg_trim/cx_info/cx_probe/look/find_col/sg_stmt/
 * sg_unparen/sg_bare/sg_word/sg_num/sg_thresh/sg_qend/_sov_str_eq/digitb)
 * are fused as static C mirrors so a line costs one pass instead of a chain
 * of indirect calls; the allocating helpers (lines_of, sg_cuts, sg_exp_push,
 * u2_conv, sg_sq2, sg_cat*, str_cat, cut, strip, sg_lists, sg_one, sg_cmp,
 * sg_toks, sg_pad3, sg_ph, sg_sub, sg_sp, sg_digits, print, fail) stay
 * table calls with the Sovren ABI (args rdi,rsi,rdx,rcx,r8,r9,r10; rax).
 * The interpreted body stays the portable reference for every other build;
 * this blob is planted only for the self-hosted compiler (nat_gate).
 * Table layout mirrors cx_tbl_init in compiler.sov: slot n at byte n*8,
 * slot 0 = slot count.  Needles/messages are stack-built byte arrays, so the
 * blob carries no .rodata and no relocations.
 * Lists are [cap@0][len@8][elems@16]; strings are NUL-terminated with
 * length(x) = x<4096 ? 0 : strlen(x), matching the runtime tasks.
 * No external symbols, no relocations, no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);
typedef U (*F3)(U,U,U);
typedef U (*F4)(U,U,U,U);
typedef U (*F5)(U,U,U,U,U);

enum {
 T_LINES=1, T_LNEW=2, T_LADD=3, T_ALLOC=4, T_SQ2=5, T_CAT4=6, T_CAT5=7,
 T_TOKS=8, T_STRCAT=9, T_PAD3=10, T_PH=11, T_SUB=12, T_CUT=13, T_STRIP=14,
 T_LISTS=15, T_ONE=16, T_CMP=17, T_SP=18, T_DIGITS=19, T_PRINT=20, T_FAIL=21
};

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }
static inline U t3(U *t, U i, U a, U b, U c){ return ((F3)t[i])(a,b,c); }
static inline U t4(U *t, U i, U a, U b, U c, U d){ return ((F4)t[i])(a,b,c,d); }
static inline U t5(U *t, U i, U a, U b, U c, U d, U e){ return ((F5)t[i])(a,b,c,d,e); }

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
/* look: _sov_find_text semantics - first occurrence of NUL-terminated needle,
 * else -1; empty needle answers 0; the verify mismatches at the haystack NUL */
static U xf_look(const unsigned char *s, const unsigned char *nd){
    if (!nd) return MISS;
    U nl=0; while (nd[nl]) nl++;
    if (nl==0) return 0;
    if (!s) return MISS;
    for (U i=0; s[i]; i++){
        if (s[i]==nd[0]){
            U j=1;
            while (j<nl && s[i+j] && s[i+j]==nd[j]) j++;
            if (j==nl) return i;
        }
    }
    return MISS;
}
/* _sov_str_eq: null==null 1, mixed null 0, else content equality */
static int xstreq(const unsigned char *a, const unsigned char *b){
    if (!a && !b) return 1;
    if (!a || !b) return 0;
    U i=0;
    while (a[i]==b[i]){ if (!a[i]) return 1; i++; }
    return 0;
}
/* sg_marks: bit0 ";;", bit1 '>', bit2 apostrophe - one pass, same answer
 * as cfind1(62)+cfind1(39)+look(";;") (each bit is an existence test) */
static U marks(const unsigned char *l){
    U mk=0; int prev=0;
    for (U i=0; l[i]; i++){
        unsigned b=l[i];
        if (b==62) mk|=2;
        if (b==39) mk|=4;
        if (b==59){ if (prev) mk|=1; prev=1; } else prev=0;
    }
    return mk;
}
/* sg_sqok: quote/escape/comment-aware apostrophe-squash admissibility */
static U sqok(const unsigned char *l){
    U n=xstrlen(l), k=0, dq=0, sq=0;
    while (k<n){
        unsigned b=l[k];
        if (b==92){ k++; }
        else {
            if (dq==1){ if (b==34) dq=0; }
            else {
                if (sq==1){ if (b==39) sq=0; }
                else {
                    if (b==35) k=n;
                    if (b!=35){
                        if (b==34) dq=1;
                        if (b==39) sq=1;
                    }
                }
            }
        }
        k++;
    }
    if (dq==1) return 0;
    if (sq==1) return 0;
    return 1;
}
/* sg_ind: leading blanks (32=+1, 9=+4) */
static U ind_of(const unsigned char *l){
    U n=0, k=0, ln=xstrlen(l);
    while (k<ln){
        unsigned b=l[k];
        if (b==32) n++;
        if (b==9) n+=4;
        if (b!=32 && b!=9) k=ln;
        k++;
    }
    return n;
}
/* bump arena for the blob's fresh strings: they flow into the line list
 * and live for the whole compile (cx_read runs once per compile), matching
 * the cut_arena lifetime model. Grown via the table's _sov_heap_alloc. */
#define AR_CHUNK 1048576
static U ar_grow(U *tbl, U *arp, U *are){
    U want = AR_CHUNK;
    U p = t1(tbl, T_ALLOC, want);
    *arp = p; *are = p + want;
    return p;
}
static inline U ar_get(U *tbl, U *arp, U *are, U n){
    if (*arp + n > *are) ar_grow(tbl, arp, are);
    U p = *arp; *arp = p + n; return p;
}
/* copy s[a..b) into the arena, NUL-terminated */
static U ar_slice(U s, U a, U b, U *tbl, U *arp, U *are){
    U n = b - a;
    U d = ar_get(tbl, arp, are, n + 1);
    for (U i = 0; i < n; i++) *(unsigned char*)(d + i) = *(const unsigned char*)(s + a + i);
    *(unsigned char*)(d + n) = 0;
    return d;
}
/* cat of up to five pieces into one arena string (sg_cat2/4/5 content) */
static U ar_cat(U *tbl, U *arp, U *are, U a, U la, U b, U lb, U c, U lc, U d, U ld, U e, U le){
    U buf = ar_get(tbl, arp, are, la + lb + lc + ld + le + 1);
    U w = 0;
    const unsigned char *ps[5]; U ls[5]; U np = 0;
    if (la) { ps[np]=(const unsigned char*)a; ls[np]=la; np++; }
    if (lb) { ps[np]=(const unsigned char*)b; ls[np]=lb; np++; }
    if (lc) { ps[np]=(const unsigned char*)c; ls[np]=lc; np++; }
    if (ld) { ps[np]=(const unsigned char*)d; ls[np]=ld; np++; }
    if (le) { ps[np]=(const unsigned char*)e; ls[np]=le; np++; }
    for (U k = 0; k < np; k++){
        for (U i = 0; i < ls[k]; i++) *(unsigned char*)(buf + w + i) = ps[k][i];
        w += ls[k];
    }
    *(unsigned char*)(buf + w) = 0;
    return buf;
}
/* sg_sp content: n spaces, NUL-terminated (arena); "" for n<1 */
static U spc(U n, U *tbl, U *arp, U *are){
    U buf = ar_get(tbl, arp, are, n + 1);
    for (U i = 0; i < n; i++) *(unsigned char*)(buf + i) = 32;
    *(unsigned char*)(buf + n) = 0;
    return buf;
}

/* inline _sov_list_add: fast path in place, grow via a fresh 2x copy
 * (content-identical list; the mmap-extend trick is _sov_list_add_slow's
 * private optimization and is not observable through the list contents) */
static inline U ladd(U lst, U item, U *tbl, U *arp, U *are){
    if (lst){
        U ln = *(U*)(lst + 8);
        U cap = *(U*)(lst);
        if (ln < cap){
            *(U*)(lst + 16 + ln * 8) = item;
            *(U*)(lst + 8) = ln + 1;
            return lst;
        }
    }
    /* slow path: grow (cap*2 like _sov_list_add_slow; empty lists get the
     * _sov_list_new shape, cap 24) */
    U cap = 24, len = 0;
    if (lst){ cap = *(U*)(lst); len = *(U*)(lst + 8); if (cap < 24) cap = 24; }
    U nc = cap * 2;
    U b = ar_get(tbl, arp, are, 16 + nc * 8);
    *(U*)(b) = nc;
    *(U*)(b + 8) = len;
    for (U i = 0; i < len; i++) *(U*)(b + 16 + i * 8) = *(U*)(lst + 16 + i * 8);
    *(U*)(b + 16 + len * 8) = item;
    *(U*)(b + 8) = len + 1;
    return b;
}
/* inline _sov_list_new ([cap=24][len=0], same as the runtime task) */
static inline U lnew(U *tbl, U *arp, U *are){
    U b = ar_get(tbl, arp, are, 208);
    *(U*)(b) = 24;
    *(U*)(b + 8) = 0;
    return b;
}
/* cut: cut_full content - interior pointer when b==length(t), arena copy
 * when both bounds are interior (same answer as the runtime task) */
static U cutf(U t, U a, U b, U *tbl, U *arp, U *are){
    U tn = slen(t);
    if (b == tn){
        if (a != MISS){
            if (a <= b) return t + a;
        }
    }
    if (a != MISS){
        if (b >= a){
            if (b <= tn){
                return ar_slice(t, a, b, tbl, arp, are);
            }
        }
    }
    return t3(tbl, T_CUT, t, a, b);
}
/* strip: _sov_trim content - strips leading/trailing " \t\n\r"; identity
 * or interior pointer when clean, arena copy when trimmed at either end */
static U stripf(U t, U *tbl, U *arp, U *are){
    if (t == 0) return 0;
    U n = slen(t);
    const unsigned char *s = (const unsigned char*)t;
    U a = 0;
    while (a < n){
        unsigned c = s[a];
        if (c == 32 || c == 9 || c == 10 || c == 13) a++;
        else break;
    }
    U b = n;
    while (b > a){
        unsigned c = s[b-1];
        if (c == 32 || c == 9 || c == 10 || c == 13) b--;
        else break;
    }
    if (a == 0 && b == n) return t;
    return ar_slice(t, a, b, tbl, arp, are);
}
/* sg_toks: space-separated pieces (arena copies via cutf content) */
static U toksf(U t, U *tbl, U *arp, U *are){
    U out = lnew(tbl, arp, are);
    U n = slen(t);
    const unsigned char *s = (const unsigned char*)t;
    U i = 0, st = MISS;
    while (i < n){
        unsigned c = s[i];
        if (c == 32){
            if (st != MISS){
                out = ladd(out, cutf(t, st, i, tbl, arp, are), tbl, arp, are);
                st = MISS;
            }
        } else {
            if (st == MISS) st = i;
        }
        i++;
    }
    if (st != MISS) out = ladd(out, cutf(t, st, n, tbl, arp, are), tbl, arp, are);
    return out;
}

/* sg_trim: strip bytes < 33 at both ends; interior pointer when the tail is
 * clean, cut() (allocating) only when trailing bytes need removal */
static U triml(U l, U *tbl, U *arp, U *are){
    U n=slen(l), t0=0;
    while (t0<n && PB(l,t0)<33) t0++;
    if (t0==n) return l+t0;
    U t1=n;
    while (t1>t0 && PB(l,t1-1)<33) t1--;
    if (t1==n) return l+t0;
    return cutf(l,t0,t1,tbl,arp,are);
}
/* cx_info: bits 1 last58, 2 " = " at/after indent, 4 first ": ", 8 second,
 * 16 " != ", 32 " isnt ", 64 first trimmed byte is a digit */
static U cxinfo(const unsigned char *l){
    U r=0, n=xstrlen(l);
    long long e=(long long)n-1; int e58=0;
    while (e>-1){
        if (e58==0){
            unsigned eb=l[e];
            if (eb>32){ e58=1; if (eb==58) r|=1; }
            else e--;
        }
        if (e58==1) e=-1;
    }
    U lead=0;
    while (lead<n && l[lead]<33) lead++;
    if (lead<n){
        unsigned fb=l[lead];
        if (fb>47 && fb<58) r|=64;
    }
    for (U i=0;i<n;i++){
        unsigned c=l[i];
        if (c==58){
            if (PB(l,i+1)==32){
                if ((r&4)==4) r|=8;
                else r|=4;
            }
        }
        if (c==61){
            if (i>lead){
                if (PB(l,i-1)==32 && PB(l,i+1)==32) r|=2;
            }
        }
        if (c==33){
            if (i>0){
                if (PB(l,i-1)==32 && PB(l,i+1)==61 && PB(l,i+2)==32) r|=16;
            }
        }
        if (c==105){
            if (i>0){
                if (PB(l,i-1)==32 && PB(l,i+1)==115 && PB(l,i+2)==110 && PB(l,i+3)==116 && PB(l,i+4)==32) r|=32;
            }
        }
    }
    return r;
}
/* cx_probe: bits 1 first ": ", 2 second, 4 " != ", 8 " isnt " */
static U cxprobe(const unsigned char *l){
    U r=0, n=xstrlen(l);
    for (U i=0;i<n;i++){
        unsigned c=l[i];
        if (c==58){
            if (PB(l,i+1)==32){
                if ((r&1)==1) r|=2;
                else r|=1;
            }
        }
        if (c==33){
            if (i>0){
                if (PB(l,i-1)==32 && PB(l,i+1)==61 && PB(l,i+2)==32) r|=4;
            }
        }
        if (c==105){
            if (i>0){
                if (PB(l,i-1)==32 && PB(l,i+1)==115 && PB(l,i+2)==110 && PB(l,i+3)==116 && PB(l,i+4)==32) r|=8;
            }
        }
    }
    return r;
}
/* find_col / find_col_q: first ':' outside double quotes, else -1 */
static U findcol_q(const unsigned char *t){
    U n=xstrlen(t), i=0, ins=0;
    while (i<n){
        unsigned b=t[i];
        if (ins==1){
            if (b==92) i++;
            else { if (b==34) ins=0; }
        } else {
            if (b==34) ins=1;
            else { if (b==58) return i; }
        }
        i++;
    }
    return MISS;
}
static U findcol(const unsigned char *t){
    if (cfind1(t,34)==MISS) return cfind1(t,58);
    return findcol_q(t);
}
/* sg_stmt: 1 iff a ': ' occurs outside quotes before the last byte */
static U stmtl(const unsigned char *t){
    if (cfind1(t,58)==MISS) return 0;
    U ep=findcol(t);
    if (ep!=MISS){
        if (ep<xstrlen(t)-1){
            if (PB(t,ep+1)==32) return 1;
        }
    }
    return 0;
}
/* sg_unparen: cut "(x)" to "x" */
static U unparen(U t, U *tbl, U *arp, U *are){
    if (PB(t,0)!=40) return t;
    if (slen(t)>1){
        if (PB(t,slen(t)-1)==41) return cutf(t,1,slen(t)-1,tbl,arp,are);
    }
    return t;
}
/* sg_bare: 1 iff no space and nonempty */
static U bare(const unsigned char *t){
    if (PB(t,0)==0) return 0;
    for (U k=0;;k++){
        unsigned b=t[k];
        if (b==0) return 1;
        if (b==32) return 0;
    }
}
/* sg_word: first byte _/A-Z/a-z, all bytes word chars */
static U wordok(const unsigned char *t){
    unsigned c0=PB(t,0);
    if (c0==0) return 0;
    int ok0=(c0==95)||(c0>64&&c0<91)||(c0>96&&c0<123);
    if (!ok0) return 0;
    U tn=xstrlen(t);
    for (U k=0;k<tn;k++){
        unsigned b=t[k];
        int ok=(b==95)||(b>47&&b<58)||(b>64&&b<91)||(b>96&&b<123);
        if (!ok) return 0;
    }
    return 1;
}
/* sg_num: nonempty all-digits */
static U numok(const unsigned char *t){
    U n=xstrlen(t);
    if (n==0) return 0;
    for (U i=0;i<n;i++){
        unsigned b=t[i];
        if (b<48) return 0;
        if (b>57) return 0;
    }
    return 1;
}
/* sg_thresh: "blank", or optionally '-'-led digits */
static U thresh(const unsigned char *t, const unsigned char *blankw){
    if (xstreq(t,blankw)) return 1;
    U n=xstrlen(t);
    if (n==0) return 0;
    U k=0;
    if (PB(t,0)==45) k=1;
    if (k==n) return 0;
    U d=1;
    while (k<n){
        unsigned b=t[k];
        if (b<48) d=0;
        if (b>57) d=0;
        k++;
    }
    return d;
}
/* sg_qend: string-state after this line (1 = ends inside quotes) */
static U qend(const unsigned char *l, U inp){
    if (cfind1(l,34)==MISS) return inp;
    U ins=inp, i=0, n=xstrlen(l);
    while (i<n){
        unsigned b=l[i];
        if (b==92) i++;
        else { if (b==34) ins=1-ins; }
        i++;
    }
    return ins;
}
static inline int digitb(unsigned b){ return b>=48 && b<=57; }
/* _sov_starts_with: s null 0, p null 1, else prefix test (s may end first -> 0) */
static int sw_startswith(const unsigned char *s, const unsigned char *p){
    if (!s) return 0;
    if (!p) return 1;
    for (U i=0;;i++){
        unsigned cp=p[i];
        if (!cp) return 1;
        if (s[i]!=cp) return 0;
    }
}

/* sg_starts_at: does the prefix sit at offset a of t (scan only) */
static int starts_at(const unsigned char *t, U a, const unsigned char *p){
    for (U k=0;;k++){
        unsigned cp=p[k];
        if (!cp) return 1;
        if (t[a+k]!=cp) return 0;
    }
}
/* sg_seg: sp(ind) + s[a..b) in one allocation (spaces written inline,
 * matching sg_sp+memcpy content; the sg_sp intermediate alloc is gone) */
static U seg(U s, U a, U b, U ind, U *tbl, U *arp, U *are){
    U sn=b-a;
    U buf=ar_get(tbl,arp,are,ind+sn+1);
    for (U i=0;i<ind;i++) *(unsigned char*)(buf+i)=32;
    for (U i=0;i<sn;i++) *(unsigned char*)(buf+ind+i)=*(const unsigned char*)(s+a+i);
    *(unsigned char*)(buf+ind+sn)=0;
    return buf;
}
/* sg_cat2(sg_sp(ind), t) content: ind spaces + t in one arena string */
static U cat_sp(U ind, U t, U *tbl, U *arp, U *are){
    U tn=slen(t);
    U buf=ar_get(tbl,arp,are,ind+tn+1);
    for (U i=0;i<ind;i++) *(unsigned char*)(buf+i)=32;
    for (U i=0;i<tn;i++) *(unsigned char*)(buf+ind+i)=*(const unsigned char*)(t+i);
    *(unsigned char*)(buf+ind+tn)=0;
    return buf;
}
/* sg_exp_push: one line of the long form - arrow split, same verdict as the
 * interpreted body (header 'if '/'as long as ', non-empty halves; note the
 * source's `if b1 > b0` line has an empty body, so the k-probes gate on
 * a1 > ah alone, exactly as written) */
static U exp_push(U out, U l, U ind, U keep, U *tbl, U *arp, U *are,
                  const unsigned char *nd_arr, const unsigned char *nd_if,
                  const unsigned char *nd_al){
    const unsigned char *lc=(const unsigned char*)l;
    if (cfind1(lc,62)==MISS){
        if (keep==1) return ladd(out,l,tbl,arp,are);
        U t=l;
        if (PB(l,0)<33) t=triml(l,tbl,arp,are);
        U c2=cat_sp(ind,t,tbl,arp,are);
        return ladd(out,c2,tbl,arp,are);
    }
    U t=l;
    if (PB(l,0)<33) t=triml(l,tbl,arp,are);
    const unsigned char *tc=(const unsigned char*)t;
    U pp=xf_look(tc,nd_arr);
    if (pp!=MISS){
        U a0=0, ah=pp;
        while (a0<pp){ if (tc[a0]<33) a0++; else { ah=a0; a0=pp; } }
        U a1=pp, ad=0;
        while (!ad){ if (a1>ah){ if (tc[a1-1]<33) a1--; else ad=1; } else ad=1; }
        U b0=pp+4, bn=slen(t), bh=b0;
        while (bh<bn){ if (tc[bh]<33) bh++; else { b0=bh; bh=bn; } }
        U b1=bn; ad=0;
        while (!ad){ if (b1>b0){ if (tc[b1-1]<33) b1--; else ad=1; } else ad=1; }
        if (a1>ah){
            int k1=starts_at(tc,ah,nd_if);
            int k2=0;
            if (k1==0) k2=starts_at(tc,ah,nd_al);
            if (k1==1 || k2==1){
                U g1=seg(t,ah,a1,ind,tbl,arp,are);
                out=ladd(out,g1,tbl,arp,are);
                U g2=seg(t,b0,b1,ind+4,tbl,arp,are);
                out=ladd(out,g2,tbl,arp,are);
                return out;
            }
        }
    }
    if (keep==1) return ladd(out,l,tbl,arp,are);
    U c2=cat_sp(ind,t,tbl,arp,are);
    return ladd(out,c2,tbl,arp,are);
}
/* u2_conv: chained one-liner arrows, one more split per piece */
static U u2conv(U c, U *tbl, U *arp, U *are,
                const unsigned char *nd_arr, const unsigned char *nd_if,
                const unsigned char *nd_al){
    U cn=LLEN(c);
    if (cn<2) return c;
    U cx=lnew(tbl,arp,are);
    for (U ck=0;ck<cn;ck++){
        U cp=ELEM(c,ck);
        if (cfind1((const unsigned char*)cp,62)!=MISS){
            U nl=lnew(tbl,arp,are);
            U ui=ind_of((const unsigned char*)cp);
            U ct=exp_push(nl,cp,ui,1,tbl,arp,are,nd_arr,nd_if,nd_al);
            if (LLEN(ct)==2){
                cx=ladd(cx,ELEM(ct,0),tbl,arp,are);
                cx=ladd(cx,ELEM(ct,1),tbl,arp,are);
            } else {
                cx=ladd(cx,cp,tbl,arp,are);
            }
        } else {
            cx=ladd(cx,cp,tbl,arp,are);
        }
    }
    return cx;
}
/* sg_cut_at: next unquoted ';;' at/after start (-1 none) */
static U cut_at(const unsigned char *l, U start){
    U n=xstrlen(l), k=start, dq=0, sq=0, go=0;
    while (k<n){
        unsigned b=l[k];
        go=1;
        if (b==92){ go=0; k++; }
        if (go==1){
            if (b==34){ if (dq==1) dq=0; else if (sq==0) dq=1; }
        }
        if (go==1){
            if (b==39){ if (sq==1) sq=0; else if (dq==0) sq=1; }
        }
        if (go==1){
            if (b==59){
                if (dq==0 && sq==0){
                    if (k+1<n){
                        if (l[k+1]==59) return k;
                    }
                }
            }
        }
        k++;
    }
    return MISS;
}
/* sg_cuts: split at unquoted ';;' (cut() arena pieces stay table calls) */
static U cuts(U l, U *tbl, U *arp, U *are){
    U out=lnew(tbl,arp,are);
    U n=slen(l);
    U start=0;
    U k=cut_at((const unsigned char*)l,start);
    while (k!=MISS){
        U cu=cutf(l,start,k,tbl,arp,are);
        out=ladd(out,cu,tbl,arp,are);
        start=k+2;
        k=cut_at((const unsigned char*)l,start);
    }
    U cu=cutf(l,start,n,tbl,arp,are);
    out=ladd(out,cu,tbl,arp,are);
    return out;
}

/* twin entry: rdi=source, rsi=cx_tbl (fn _sov_cx_read) */
U old_cx_read(const unsigned char *source, U *tbl)
{
    /* stack-built needles/messages: content identical to the interpreted
     * literals, no .rodata, no relocations */
    const unsigned char nd_apos[]={'\'',0};
    const unsigned char nd_eq[]={' ','=',' ',0};
    const unsigned char nd_arr[]={' ','-','>',' ',0};
    const unsigned char nd_if[]={'i','f',' ',0};
    const unsigned char nd_al[]={'a','s',' ','l','o','n','g',' ','a','s',' ',0};
    const unsigned char nd_cs[]={':',' ',0};
    const unsigned char nd_hash[]={'#',0};
    const unsigned char nd_usec[]={'u','s','e',':',0};
    const unsigned char nd_prtc[]={'p','r','i','n','t',':',0};
    const unsigned char nd_emc[]={'e','m','i','t',':',0};
    const unsigned char nd_e4c[]={'e','m','i','t','4',':',0};
    const unsigned char nd_e8c[]={'e','m','i','t','8',':',0};
    const unsigned char nd_uses[]={'u','s','e',' ',0};
    const unsigned char nd_prts[]={'p','r','i','n','t',' ',0};
    const unsigned char nd_ems[]={'e','m','i','t',0};
    const unsigned char nd_e4s[]={'e','m','i','t','4',0};
    const unsigned char nd_e8s[]={'e','m','i','t','8',0};
    const unsigned char nd_lp[]={'(',0};
    const unsigned char nd_rp[]={')',0};
    const unsigned char nd_cq[]={':',' ','"',0};
    const unsigned char nd_q[]={'"',0};
    const unsigned char nd_cm[]={',',' ',0};
    volatile const unsigned char nd_emp[]={0};
    const unsigned char nd_blank[]={'b','l','a','n','k',0};
    unsigned char nd_err[72];
    *(U*)(nd_err+0) = 0x61203a726f727245ULL;
    *(U*)(nd_err+8) = 0x672065756c617620ULL;
    *(U*)(nd_err+16) = 0x65656e2070756f72ULL;
    *(U*)(nd_err+24) = 0x6f206f7774207364ULL;
    *(U*)(nd_err+32) = 0x6e2065726f6d2072ULL;
    *(U*)(nd_err+40) = 0x7277203b73656d61ULL;
    *(U*)(nd_err+48) = 0x20656e6f20657469ULL;
    *(U*)(nd_err+56) = 0x72696420656d616eULL;
    *(U*)(nd_err+64) = 0x000000796c746365ULL;

    U ls = t1(tbl, T_LINES, (U)source);
    U u_q39 = xf_look(source, nd_apos);
    U u_qskip = (u_q39 == MISS) ? 1 : 0;
    U arp = 0, are = 0;
    U out = lnew(tbl, &arp, &are);
    U sls = lnew(tbl, &arp, &are);
    U u2_scratch = 0;
    U ins = 0, blk = 0, bind = 0;
    U bval = 0, bfn = 0, bhd = 0, btgt = 0;
    U g3n = 0;
    U kl = LLEN(ls);
    for (U k = 0; k < kl; k++) {
        U q = ELEM(ls, k);
        U sq2v = q;
        U mkq = marks((const unsigned char*)q);
        if (u_qskip == 0) {
            if (mkq > 3) {
                U sok = sqok((const unsigned char*)q);
                if (sok == 1) {
                    sq2v = t1(tbl, T_SQ2, q);
                    if (!xstreq((const unsigned char*)sq2v, (const unsigned char*)q)) {
                        mkq = marks((const unsigned char*)sq2v);
                    }
                }
            }
        }
        U cxk = MISS;
        U e0 = LLEN(sls);
        if (ins == 1) {
            sls = ladd(sls, sq2v, tbl, &arp, &are);
        } else {
            U mk4 = mkq - 4 * (mkq / 4);
            U nsc = (mk4 - 2 * (mk4 / 2) == 0) ? 1 : 0;
            U nar = (mk4 < 2) ? 1 : 0;
            if (nsc == 1) {
                if (nar == 1) {
                    /* plain-line bypass: cx_info answers last58/" = "/probe
                     * for the whole line in one pass (blk==0 only) */
                    U cxfast = 0;
                    if (blk == 0) {
                        U cxi = cxinfo((const unsigned char*)sq2v);
                        cxk = cxi;
                        if ((cxi & 51) == 0) {
                            if ((cxi & 4) == 0) cxfast = 1;
                            else if ((cxi & 72) == 0) cxfast = 1;
                        }
                    }
                    if (cxfast == 1) out = ladd(out, sq2v, tbl, &arp, &are);
                    else sls = ladd(sls, sq2v, tbl, &arp, &are);
                } else {
                    /* u2_c recycled per line: len:=0 reseats the scratch */
                    if (u2_scratch == 0) u2_scratch = lnew(tbl, &arp, &are);
                    U u2_c = u2_scratch;
                    *(U*)(u2_c + 8) = 0;
                    u2_c = exp_push(u2_c, sq2v, ind_of((const unsigned char*)sq2v), 1, tbl, &arp, &are, nd_arr, nd_if, nd_al);
                    u2_c = u2conv(u2_c, tbl, &arp, &are, nd_arr, nd_if, nd_al);
                    U u2_n = LLEN(u2_c);
                    for (U u2_k = 0; u2_k < u2_n; u2_k++)
                        sls = ladd(sls, ELEM(u2_c, u2_k), tbl, &arp, &are);
                }
            }
            if (nsc == 0) {
                U np = 1;
                U ps = 0;
                if ((mkq & 1) == 1) {
                    ps = cuts(sq2v, tbl, &arp, &are);
                    np = LLEN(ps);
                }
                U uind = ind_of((const unsigned char*)sq2v);
                if (u2_scratch == 0) u2_scratch = lnew(tbl, &arp, &are);
                U u2_c = u2_scratch;
                *(U*)(u2_c + 8) = 0;
                if (np == 1) u2_c = exp_push(u2_c, sq2v, uind, 1, tbl, &arp, &are, nd_arr, nd_if, nd_al);
                if (np > 1) {
                    for (U pk = 0; pk < np; pk++)
                        u2_c = exp_push(u2_c, ELEM(ps, pk), uind, 0, tbl, &arp, &are, nd_arr, nd_if, nd_al);
                }
                if (nar == 0) u2_c = u2conv(u2_c, tbl, &arp, &are, nd_arr, nd_if, nd_al);
                U u2_n = LLEN(u2_c);
                for (U u2_k = 0; u2_k < u2_n; u2_k++)
                    sls = ladd(sls, ELEM(u2_c, u2_k), tbl, &arp, &are);
            }
        }
        U ne = LLEN(sls);
        for (U i = e0; i < ne; i++) {
            U l = ELEM(sls, i);
            U t = l;
            if (PB(l, 0) < 33) t = triml(l, tbl, &arp, &are);
            U ind = ind_of((const unsigned char*)l);
            U last58 = 0;
            U lcxi = MISS;
            if (i == e0) lcxi = cxk;
            if (lcxi == MISS) {
                U cxtl = slen(t);
                if (cxtl > 0) {
                    if (PB(t, cxtl - 1) == 58) last58 = 1;
                }
            }
            if (lcxi != MISS) last58 = lcxi & 1;
            U eqp = MISS;
            if (lcxi == MISS) eqp = xf_look((const unsigned char*)t, nd_eq);
            if (lcxi != MISS) {
                if ((lcxi & 2) == 2) eqp = xf_look((const unsigned char*)t, nd_eq);
            }
            U done = 0;
            U bl_ok = 0;
            if (blk > 0) {
                U tn = unparen(t, tbl, &arp, &are);
                U stl = stmtl((const unsigned char*)t);
                if (slen(t) > 0) {
                    if (ind > bind) bl_ok = 1;
                }
                if (bl_ok == 1) {
                    if (sw_startswith((const unsigned char*)t, nd_hash) == 1) bl_ok = 0;
                }
                if (bl_ok == 1) {
                    if (stl == 0) {
                        if (blk == 1) { if (bare((const unsigned char*)tn) == 0) bl_ok = 0; }
                        if (blk == 3) { if (bare((const unsigned char*)tn) == 0) bl_ok = 0; }
                        if (blk == 5) { if (bare((const unsigned char*)tn) == 0) bl_ok = 0; }
                    }
                }
                if (bl_ok == 1) {
                    if (stl == 1) {
                        done = 1;
                        U c2 = cat_sp(ind, t, tbl, &arp, &are);
                        out = ladd(out, c2, tbl, &arp, &are);
                    }
                }
                if (bl_ok == 1) {
                    if (stl == 0) {
                        done = 1;
                        if (blk == 1) {
                            U sp = spc(bind, tbl, &arp, &are);
                            U c4 = ar_cat(tbl, &arp, &are, sp, bind, (U)nd_uses, 4, tn, slen(tn), 0, 0, 0, 0);
                            out = ladd(out, c4, tbl, &arp, &are);
                        }
                        if (blk == 2) {
                            U tv = toksf(tn, tbl, &arp, &are);
                            U tv_ok = 1;
                            U tv_ln = LLEN(tv);
                            for (U tz = 0; tz < tv_ln; tz++)
                                if (numok((const unsigned char*)ELEM(tv, tz)) == 0) tv_ok = 0;
                            if (tv_ok == 1) {
                                U tz_ln = LLEN(tv);
                                for (U tz = 0; tz < tz_ln; tz++) {
                                    U sp = spc(bind, tbl, &arp, &are);
                                    U tk = ELEM(tv, tz);
                                    U c5 = ar_cat(tbl, &arp, &are, sp, bind, bfn, slen(bfn), (U)nd_lp, 1, tk, slen(tk), 0, 0);
                                    U c5b = ar_cat(tbl, &arp, &are, c5, slen(c5), (U)nd_rp, 1, 0, 0, 0, 0, 0, 0);
                                    out = ladd(out, c5b, tbl, &arp, &are);
                                }
                            }
                            if (tv_ok == 0) {
                                U sp = spc(bind, tbl, &arp, &are);
                                U c5 = ar_cat(tbl, &arp, &are, sp, bind, bfn, slen(bfn), (U)nd_lp, 1, tn, slen(tn), 0, 0);
                                U c5b = ar_cat(tbl, &arp, &are, c5, slen(c5), (U)nd_rp, 1, 0, 0, 0, 0, 0, 0);
                                out = ladd(out, c5b, tbl, &arp, &are);
                            }
                        }
                        if (blk == 3) {
                            U sp = spc(bind, tbl, &arp, &are);
                            U c4 = ar_cat(tbl, &arp, &are, sp, bind, tn, slen(tn), (U)nd_cs, 2, bval, slen(bval), 0, 0);
                            out = ladd(out, c4, tbl, &arp, &are);
                            g3n = g3n + 1;
                        }
                        if (blk == 4) {
                            U rv = t1(tbl, T_DIGITS, tn);
                            if (rv != MISS) {
                                U sp = spc(bind, tbl, &arp, &are);
                                U p3 = t1(tbl, T_PAD3, rv);
                                U x1 = ar_cat(tbl, &arp, &are, bfn, slen(bfn), p3, slen(p3), (U)nd_cq, 3, tn, slen(tn), 0, 0);
                                U x2 = ar_cat(tbl, &arp, &are, x1, slen(x1), (U)nd_q, 1, 0, 0, 0, 0, 0, 0);
                                U x5 = ar_cat(tbl, &arp, &are, sp, bind, x2, slen(x2), 0, 0, 0, 0, 0, 0);
                                out = ladd(out, x5, tbl, &arp, &are);
                            }
                        }
                        if (blk == 5) {
                            U ph5 = t1(tbl, T_PH, bhd);
                            if (ph5 == 1) {
                                U sb = t2(tbl, T_SUB, bhd, tn);
                                U c2 = cat_sp(bind, sb, tbl, &arp, &are);
                                out = ladd(out, c2, tbl, &arp, &are);
                            }
                            if (ph5 == 0) {
                                U sp = spc(bind, tbl, &arp, &are);
                                U c4 = ar_cat(tbl, &arp, &are, sp, bind, tn, slen(tn), (U)nd_cs, 2, bhd, slen(bhd), 0, 0);
                                out = ladd(out, c4, tbl, &arp, &are);
                            }
                        }
                        if (blk == 7) {
                            U sp = spc(bind, tbl, &arp, &are);
                            U c4 = ar_cat(tbl, &arp, &are, sp, bind, (U)nd_prts, 6, tn, slen(tn), 0, 0, 0, 0);
                            out = ladd(out, c4, tbl, &arp, &are);
                        }
                        if (blk == 6) {
                            U pp6 = xf_look((const unsigned char*)t, nd_arr);
                            U ea6 = t;
                            U eb6 = 0;
                            if (pp6 != MISS) {
                                ea6 = cutf(t, 0, pp6, tbl, &arp, &are);
                                eb6 = cutf(t, pp6 + 4, slen(t), tbl, &arp, &are);
                            }
                            U sp = spc(bind, tbl, &arp, &are);
                            U acc6 = ar_cat(tbl, &arp, &are, sp, bind, btgt, slen(btgt), (U)nd_cs, 2, bfn, slen(bfn), 0, 0);
                            U acc6b = ar_cat(tbl, &arp, &are, acc6, slen(acc6), (U)nd_lp, 1, 0, 0, 0, 0, 0, 0);
                            U y1 = ar_cat(tbl, &arp, &are, btgt, slen(btgt), (U)nd_cm, 2, ea6, slen(ea6), 0, 0, 0, 0);
                            U acc6c;
                            if (slen(eb6) > 0) {
                                U y2 = ar_cat(tbl, &arp, &are, y1, slen(y1), (U)nd_cm, 2, eb6, slen(eb6), 0, 0, 0, 0);
                                acc6c = ar_cat(tbl, &arp, &are, acc6b, slen(acc6b), y2, slen(y2), (U)nd_rp, 1, 0, 0, 0, 0);
                            } else {
                                acc6c = ar_cat(tbl, &arp, &are, acc6b, slen(acc6b), y1, slen(y1), (U)nd_rp, 1, 0, 0, 0, 0);
                            }
                            out = ladd(out, acc6c, tbl, &arp, &are);
                        }
                    }
                }
            }
            if (bl_ok == 0) {
                if (blk == 3) {
                    if (g3n < 2) {
                        t1(tbl, T_PRINT, (U)nd_err);
                        t0(tbl, T_FAIL);
                    }
                }
                blk = 0;
                if (slen(t) == 0) {
                    done = 1;
                    out = ladd(out, l, tbl, &arp, &are);
                }
                if (sw_startswith((const unsigned char*)t, nd_hash) == 1) {
                    done = 1;
                    out = ladd(out, l, tbl, &arp, &are);
                }
            }
            if (done == 0) {
                if (last58 == 1) {
                    if (xstreq((const unsigned char*)t, nd_usec)) { done = 1; blk = 1; bind = ind; }
                    if (xstreq((const unsigned char*)t, nd_prtc)) { done = 1; blk = 7; bind = ind; }
                    if (xstreq((const unsigned char*)t, nd_emc)) { done = 1; blk = 2; bind = ind; bfn = (U)nd_ems; }
                    if (xstreq((const unsigned char*)t, nd_e4c)) { done = 1; blk = 2; bind = ind; bfn = (U)nd_e4s; }
                    if (xstreq((const unsigned char*)t, nd_e8c)) { done = 1; blk = 2; bind = ind; bfn = (U)nd_e8s; }
                    if (done == 0) {
                        if (slen(t) > 1) {
                            if (PB(t, slen(t) - 2) == 35) {
                                U hd9 = cutf(t, 0, slen(t) - 2, tbl, &arp, &are);
                                if (slen(hd9) > 0) {
                                    if (wordok((const unsigned char*)hd9) == 1) {
                                        if (PB(hd9, slen(hd9) - 1) == 95) {
                                            done = 1; blk = 4; bind = ind; bfn = hd9;
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            if (done == 0) {
                U ep = MISS;
                if (last58 == 1) ep = findcol((const unsigned char*)t);
                if (ep != MISS) {
                    if (ep == slen(t) - 1) {
                        U cu = cutf(t, 0, ep, tbl, &arp, &are);
                        U hd = stripf(cu, tbl, &arp, &are);
                        if (numok((const unsigned char*)hd) == 1) {
                            done = 1;
                            out = ladd(out, l, tbl, &arp, &are);
                        }
                        if (done == 0) {
                            if (thresh((const unsigned char*)hd, nd_blank) == 1) {
                                done = 1; blk = 3; bind = ind; bval = hd; g3n = 0;
                            }
                        }
                    }
                }
            }
            if (done == 0) {
                if (last58 == 1) {
                    U cu = cutf(t, 0, slen(t) - 1, tbl, &arp, &are);
                    U hd6 = stripf(cu, tbl, &arp, &are);
                    U q6 = xf_look((const unsigned char*)hd6, nd_cs);
                    if (q6 != MISS) {
                        U a1 = cutf(hd6, 0, q6, tbl, &arp, &are);
                        U lt6 = stripf(a1, tbl, &arp, &are);
                        U a2 = cutf(hd6, q6 + 2, slen(hd6), tbl, &arp, &are);
                        U rt6 = stripf(a2, tbl, &arp, &are);
                        if (wordok((const unsigned char*)lt6) == 1) {
                            if (wordok((const unsigned char*)rt6) == 1) {
                                done = 1; blk = 6; bind = ind; btgt = lt6; bfn = rt6;
                            }
                        }
                    }
                }
            }
            if (done == 0) {
                U ep5 = MISS;
                if (last58 == 1) ep5 = findcol((const unsigned char*)t);
                if (ep5 != MISS) {
                    if (ep5 == slen(t) - 1) {
                        U cu = cutf(t, 0, ep5, tbl, &arp, &are);
                        U hd5 = stripf(cu, tbl, &arp, &are);
                        if (slen(hd5) > 0) {
                            if (bare((const unsigned char*)hd5) == 1) {
                                if (PB(hd5, slen(hd5) - 1) == 41) {
                                    done = 1; blk = 5; bind = ind; bhd = hd5;
                                }
                            }
                        }
                    }
                }
            }
            if (done == 0) {
                if (eqp != MISS) {
                    U cu = cutf(t, 0, eqp, tbl, &arp, &are);
                    U hd2 = stripf(cu, tbl, &arp, &are);
                    if (wordok((const unsigned char*)hd2) == 1) {
                        done = 1;
                        U sp = spc(ind, tbl, &arp, &are);
                        U cu2 = cutf(t, eqp + 3, slen(t), tbl, &arp, &are);
                        U c4 = ar_cat(tbl, &arp, &are, sp, ind, hd2, slen(hd2), (U)nd_cs, 2, cu2, slen(cu2), 0, 0);
                        out = ladd(out, c4, tbl, &arp, &are);
                    }
                }
            }
            if (done == 0) {
                if (sw_startswith((const unsigned char*)t, nd_hash) == 1) {
                    out = ladd(out, l, tbl, &arp, &are);
                } else {
                    U cxp = 0;
                    if (lcxi == MISS) cxp = cxprobe((const unsigned char*)l);
                    if (lcxi != MISS) cxp = (lcxi & 60) / 4;
                    U cxplain = 0;
                    if (eqp == MISS) {
                        if ((cxp & 12) == 0) {
                            if ((cxp & 1) == 0) cxplain = 1;
                            else {
                                if ((cxp & 2) == 0) {
                                    U b0 = PB(t, 0);
                                    if (!digitb(b0)) cxplain = 1;
                                }
                            }
                        }
                    }
                    if (cxplain == 1) {
                        out = ladd(out, l, tbl, &arp, &are);
                    } else {
                        if ((cxp & 1) == 0) {
                            U c = t1(tbl, T_CMP, l);
                            out = ladd(out, c, tbl, &arp, &are);
                        } else {
                            U gen = t1(tbl, T_LISTS, l);
                            if (LLEN(gen) > 0) {
                                U gk_ln = LLEN(gen);
                                for (U gk = 0; gk < gk_ln; gk++) {
                                    U o = t1(tbl, T_ONE, ELEM(gen, gk));
                                    out = ladd(out, o, tbl, &arp, &are);
                                }
                            }
                            if (LLEN(gen) == 0) {
                                U c = t1(tbl, T_CMP, l);
                                out = ladd(out, c, tbl, &arp, &are);
                            }
                        }
                    }
                }
            }
        }
        ins = qend((const unsigned char*)sq2v, ins);
    }
    if (blk == 3) {
        if (g3n < 2) {
            t1(tbl, T_PRINT, (U)nd_err);
            t0(tbl, T_FAIL);
        }
    }
    return out;
}
