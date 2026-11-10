/* Differential harness: OLD reader blob vs NEW reader core (S29).
 *
 * The reader is cx_read: source text in, transformed line list out (the
 * "C1"/pu_lines seam of compile()).  Both sides are compiled as shared
 * objects from the exact C sources that build the certified emit8 blobs
 * (old side = work/p4/s29/old_reader.c, a verbatim copy of the certified
 * tools/native_cxread.c with the entry renamed old_cx_read; new side = a
 * .so built from tools/native_reader.c).  Each side is driven through its
 * OWN mock cx_tbl (the cxread table is stateless: 21 fn-pointer slots,
 * slot 0 = count) with faithful C mirrors of the Sovren helpers the blob
 * calls through the table (lines_of_fast / sg_sq2 / cut / strip / toks /
 * lists / one / cmp / cat4 / cat5 / pad3 / ph / sub / sp / digits /
 * str_cat / print / fail / list_new / list_add / heap_alloc - ported from
 * the .sov sources so the serialized outputs match what the real compiler
 * would see).  Per case: one reader call per side; return list serialized
 * (count + escaped bytes per line) and compared byte-for-byte, plus the
 * side-effect log (print/fail calls).
 *
 * Case sources (the S28R full-coverage corpus shape):
 *   - hardcoded stress texts (every reader construct: pack marks ;;/>/',
 *     arrow one-liners, u2 chains, " = "/ != / isnt  rewrites, digit-led
 *     call runs, use:/print:/emit:/emit4:/emit8: blocks, thresh groups,
 *     hd_# lanes, (x): placeholders, quote/escape state across lines,
 *     trailing/leading blanks, blank lines, comments, tabs)
 *   - PRNG-generated texts (seeded, deterministic, reader-shaped lines)
 *   - real .sov files: every function body AND the whole file
 *   - the 1.85MB flattened self text (the real workload)
 *
 * Mutation checks: build the new side with -DMUT_* (see the case list in
 * the session note) and run this differ; a certified core must DIVERGE on
 * the corpus for every mutant (deliberately flipped behavior).
 *
 * Timing mode (-T): drive each side over the flat R times, report median
 * wall time per call (the blob-cost ranking used to scope the rewrite).
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

typedef uint64_t U;
typedef U (*ENTRY)(U, U);

/* ------------------------------------------------------------------ */
/* mock helpers: faithful C mirrors of the Sovren table callees        */
/* ------------------------------------------------------------------ */
#define MISS ((U)-1)
#define LLEN(x) (*(U*)((x)+8))
#define ELEM(x,i) (*(U*)((x)+16+(U)(i)*8))
#define PB(s,i) (*(const unsigned char*)((s)+(U)(i)))

static U xstrlen(const unsigned char *s){ U n=0; while (s[n]) n++; return n; }
static U slen(U s){ return s<4096 ? 0 : xstrlen((const unsigned char*)s); }

static char g_empty[] = "";
#define BLANK ((U)(void*)g_empty)

/* tracked allocator: all mock-side blocks are recorded here and purged
 * after every case (the differ would otherwise hold ~1MB of blob arena
 * per side per case -> gigabytes over the full corpus) */
static void **g_blocks;
static U g_nblocks, g_capblocks;
static U mock_alloc(U n){
    void *p = malloc(n ? n : 1);
    { static int fill = -1; if (fill < 0){ const char *e = getenv("POISON"); fill = e ? (int)strtol(e, 0, 0) : 0xA5; }
      if (p) memset(p, fill, n ? n : 1); }   /* poison: uninit reads become visible */
    if (g_nblocks == g_capblocks){
        g_capblocks = g_capblocks ? g_capblocks*2 : 4096;
        g_blocks = (void**)realloc(g_blocks, g_capblocks*sizeof(void*));
    }
    g_blocks[g_nblocks++] = p;
    return (U)p;
}
static void talloc_purge(void){
    for (U i = 0; i < g_nblocks; i++) free(g_blocks[i]);
    g_nblocks = 0;
}

/* _sov_list_new: [cap 24][len 0][24 slots] */
static U mock_list_new(void){
    U b = mock_alloc(16 + 24*8 + 8);
    *(U*)(b) = 24; *(U*)(b+8) = 0;
    return b;
}
/* _sov_list_add content: in-place when room, else 2x grow copy */
static U mock_list_add(U l, U v){
    U n = LLEN(l), cap = *(U*)l;
    if (n >= cap){
        U nc = cap*2; if (!nc) nc = 8;
        U b = mock_alloc(16 + nc*8 + 8);
        *(U*)b = nc; *(U*)(b+8) = n;
        memcpy((void*)(b+16), (void*)(l+16), n*8);
        l = b;
    }
    ELEM(l,n) = v; *(U*)(l+8) = n+1;
    return l;
}

/* lines_of_fast (compiler.sov:4271): EXACT port - flat copy with NUL
 * poked over every '\n', line = flat+start, trailing '\n' adds nothing,
 * empty source -> empty list. */
static U mock_lines_of_fast(U source){
    if (!source) return mock_list_new();
    U n = xstrlen((const unsigned char*)source);
    if (n == 0) return mock_list_new();
    unsigned char *flat = (unsigned char*)mock_alloc(n+1);
    U lst = mock_alloc(16 + (n+1)*8);
    *(U*)(lst) = n+1;
    memcpy(flat, (const void*)source, n);
    U start = 0, k = 0;
    for (U i = 0; i < n; i++){
        if (flat[i] == 10){
            flat[i] = 0;
            ELEM(lst,k) = (U)(void*)(flat+start); k++;
            start = i+1;
        }
    }
    flat[n] = 0;
    if (start < n){ ELEM(lst,k) = (U)(void*)(flat+start); k++; }
    *(U*)(lst+8) = k;
    return lst;
}

/* look: _sov_find_text semantics (first occurrence of NUL-terminated
 * needle in NUL-terminated haystack, else -1; empty needle -> 0) */
static U mock_look(const unsigned char *s, const unsigned char *nd){
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
static U mock_cfind1(const unsigned char *t, unsigned ch){
    if (!t) return MISS;
    for (U i=0; t[i]; i++) if (t[i]==ch) return i;
    return MISS;
}
static int mock_streq(const unsigned char *a, const unsigned char *b){
    if (!a && !b) return 1;
    if (!a || !b) return 0;
    U i=0; while (a[i]==b[i]){ if (!a[i]) return 1; i++; }
    return 0;
}
static int mock_startswith(const unsigned char *s, const unsigned char *p){
    if (!s) return 0;
    if (!p) return 1;
    for (U i=0;;i++){ unsigned c=p[i]; if (!c) return 1; if (s[i]!=c) return 0; }
}

/* str_cat / sg_cat4 / sg_cat5: plain concatenations */
static U cat2s(U a, U b){
    U la=slen(a), lb=slen(b);
    unsigned char *r=(unsigned char*)mock_alloc(la+lb+1);
    memcpy(r,(const void*)a,la); memcpy(r+la,(const void*)b,lb); r[la+lb]=0;
    return (U)(void*)r;
}
static U mock_str_cat(U a, U b){ return cat2s(a,b); }
static U mock_sg_cat4(U a, U b, U c, U d){
    U la=slen(a),lb=slen(b),lc=slen(c),ld=slen(d);
    unsigned char *r=(unsigned char*)mock_alloc(la+lb+lc+ld+1);
    memcpy(r,(const void*)a,la); memcpy(r+la,(const void*)b,lb);
    memcpy(r+la+lb,(const void*)c,lc); memcpy(r+la+lb+lc,(const void*)d,ld);
    r[la+lb+lc+ld]=0;
    return (U)(void*)r;
}
static U mock_sg_cat5(U a, U b, U c, U d, U e){
    return cat2s(mock_sg_cat4(a,b,c,d), e);
}
/* sg_sp: n spaces, "" for n<1 */
static U mock_sg_sp(U n){
    if (n < 1) return BLANK;
    unsigned char *r=(unsigned char*)mock_alloc(n+1);
    for (U i=0;i<n;i++) r[i]=32;
    r[n]=0;
    return (U)(void*)r;
}
/* sg_ind: leading 32=+1, 9=+4, stop at any other byte */
static U mock_sg_ind(U l){
    U n=0,k=0,ln=slen(l);
    while (k<ln){
        unsigned b=PB(l,k);
        if (b==32) n++;
        else if (b==9) n+=4;
        else break;
        k++;
    }
    return n;
}
/* sg_trim: strip bytes <33 at both ends; tail-clean -> interior ptr */
static U mock_sg_trim(U l){
    U n=slen(l),t0=0;
    while (t0<n && PB(l,t0)<33) t0++;
    if (t0==n) return l+t0;
    U t1=n;
    while (t1>t0 && PB(l,t1-1)<33) t1--;
    if (t1==n) return l+t0;
    /* cut(l,t0,t1) arena copy */
    U nn=t1-t0;
    unsigned char *r=(unsigned char*)mock_alloc(nn+1);
    memcpy(r,(const void*)(l+t0),nn); r[nn]=0;
    return (U)(void*)r;
}
/* _sov_substring clamps (the cut_full fallback) */
static U mock_substring(U t, U a, U b){
    U n=slen(t);
    long long st=(long long)a, en=(long long)b;
    if (st<0) st=0;
    if ((U)en>n) en=n;
    if (en<st) en=st;
    U L=(U)en-(U)st;
    unsigned char *r=(unsigned char*)mock_alloc(L+1);
    if (L) memcpy(r,(const void*)(t+(U)st),L);
    r[L]=0;
    return (U)(void*)r;
}
/* cut_full (cx86_p3:3009): b==len -> interior ptr; valid bounds -> copy;
 * else _sov_substring */
static U mock_cut(U t, U a, U b){
    U tn=slen(t);
    if (b==tn && a!=MISS && a<=b) return t+a;
    if (a!=MISS && b>=a && b<=tn){
        U n=b-a;
        unsigned char *r=(unsigned char*)mock_alloc(n+1);
        if (n) memcpy(r,(const void*)(t+a),n);
        r[n]=0;
        return (U)(void*)r;
    }
    return mock_substring(t,a,b);
}
/* strip = _sov_trim: strip ' \t\n\r' at both ends (always a copy unless
 * clean-leading? _sov_trim always returns a fresh string per scut's
 * comment; content is what matters here) */
static U mock_strip(U t){
    if (!t) return BLANK;
    U n=slen(t);
    const unsigned char *s=(const unsigned char*)t;
    U a=0;
    while (a<n){ unsigned c=s[a]; if (c==32||c==9||c==10||c==13) a++; else break; }
    U b=n;
    while (b>a){ unsigned c=s[b-1]; if (c==32||c==9||c==10||c==13) b--; else break; }
    U L=b-a;
    unsigned char *r=(unsigned char*)mock_alloc(L+1);
    if (L) memcpy(r,s+a,L);
    r[L]=0;
    return (U)(void*)r;
}
/* scut: strip(cut(s,st,en)) fused; scutr: scut(s,st,len) */
static U mock_scut(U s, U st, U en){
    if (s<4096) return BLANK;
    U n=xstrlen((const unsigned char*)s);
    long long a=(long long)st, b=(long long)en;
    if (a<0) a=0;
    if ((U)b>n) b=n;
    if (b<a) b=a;
    const unsigned char *p=(const unsigned char*)s;
    while (a<b){ unsigned c=p[a]; if (c==32||c==9||c==10||c==13) a++; else break; }
    while (b>a){ unsigned c=p[b-1]; if (c==32||c==9||c==10||c==13) b--; else break; }
    U L=(U)b-(U)a;
    unsigned char *r=(unsigned char*)mock_alloc(L+1);
    if (L) memcpy(r,p+a,L);
    r[L]=0;
    return (U)(void*)r;
}
static U mock_scutr(U s, U st){ return mock_scut(s, st, slen(s)); }
/* sg_toks (6026): space-separated cut pieces */
static U mock_sg_toks(U t){
    U out=mock_list_new();
    U n=slen(t);
    long long st=-1;
    for (U i=0;i<n;i++){
        unsigned c=PB(t,i);
        if (c==32){ if (st>=0){ out=mock_list_add(out, mock_cut(t,(U)st,i)); st=-1; } }
        else { if (st<0) st=i; }
    }
    if (st>=0) out=mock_list_add(out, mock_cut(t,(U)st,n));
    return out;
}
/* sg_num: nonempty all digits */
static int mock_sg_num(U t){
    U n=slen(t);
    if (!n) return 0;
    for (U i=0;i<n;i++){ unsigned b=PB(t,i); if (b<48||b>57) return 0; }
    return 1;
}
/* sg_word (5755) */
static int mock_sg_word(U t){
    unsigned c0=PB(t,0);
    if (!c0) return 0;
    int ok0=(c0==95)||(c0>64&&c0<91)||(c0>96&&c0<123);
    if (!ok0) return 0;
    U tn=xstrlen((const unsigned char*)t);
    for (U k=0;k<tn;k++){
        unsigned b=PB(t,k);
        int ok=(b==95)||(b>47&&b<58)||(b>64&&b<91)||(b>96&&b<123);
        if (!ok) return 0;
    }
    return 1;
}
/* sg_digits (5684) */
static U mock_sg_digits(U t){
    U v=0, got=0, k=0, n=slen(t);
    while (k<n){
        unsigned b=PB(t,k);
        if (b<48||b>57) break;
        v=v*10+(b-48); got=1;
        k++;
    }
    if (!got) return MISS;
    return v;
}
/* sg_pad3 (5704) */
static U mock_sg_pad3(U v){
    char buf[32];
    U w=30;
    buf[31]=0;
    if (v==0){ buf[30]='0'; w=31; }
    U d=v;
    while (d>0){ w--; buf[w]='0'+d%10; d/=10; }
    U L=31-w;
    char *r=(char*)mock_alloc(L+3);
    if (v<10){ memcpy(r,"00",2); memcpy(r+2,buf+w,L); r[L+2]=0; }
    else if (v<100){ memcpy(r,"0",1); memcpy(r+1,buf+w,L); r[L+1]=0; }
    else { memcpy(r,buf+w,L); r[L]=0; }
    return (U)(void*)r;
}
/* sg_wc + sg_ph (5847) + sg_sub (5864) + letter */
static int sgwc(unsigned b){ return (b==95)||(b>47&&b<58)||(b>64&&b<91)||(b>96&&b<123); }
static U mock_sg_ph(U t){
    U n=slen(t);
    for (U k=0;k<n;k++){
        if (PB(t,k)==95){
            int lp=1, rp=1;
            if (k>0 && sgwc(PB(t,k-1))) lp=0;
            if (k+1<n && sgwc(PB(t,k+1))) rp=0;
            if (lp&&rp) return 1;
        }
    }
    return 0;
}
static U mock_letter(U t, U i){
    unsigned char *r=(unsigned char*)mock_alloc(2);
    r[0] = (t<4096||((long long)i<0)) ? 0 : PB(t,i);
    r[1]=0;
    return (U)(void*)r;
}
static U mock_sg_sub(U h, U nm){
    U n=slen(h);
    U r=BLANK;
    for (U k=0;k<n;k++){
        unsigned b=PB(h,k);
        int ph=0;
        if (b==95){
            int lp=1,rp=1;
            if (k>0 && sgwc(PB(h,k-1))) lp=0;
            if (k<n-1+0 && k+1<n && sgwc(PB(h,k+1))) rp=0;
            if (lp&&rp) ph=1;
        }
        if (ph) r=cat2s(r,nm);
        else r=cat2s(r,mock_letter(h,k));
    }
    return r;
}
/* sg_match (5585) */
static int mock_sg_match(U t, U i, U s){
    const unsigned char *tt=(const unsigned char*)t, *ss=(const unsigned char*)s;
    if (ss[0]!=0 && tt[i]!=ss[0]) return 0;
    U ls=xstrlen(ss);
    if (i+ls > xstrlen(tt)) return 0;
    if (ls==0) return 1;
    for (U k=1;k<ls;k++) if (tt[i+k]!=ss[k]) return 0;
    return 1;
}
/* sg_cmp (5634): compare-word rewriter */
static U mock_sg_cmp(U t){
    static const unsigned char nd_eq[]={' ','=',' ',0};
    static const unsigned char nd_ne[]={' ','!','=',' ',0};
    static const unsigned char nd_is[]={' ','i','s','n','t',' ',0};
    if (mock_cfind1((const unsigned char*)t,61)==MISS)
        if (mock_look((const unsigned char*)t,nd_is)==MISS)
            return t;
    if (mock_look((const unsigned char*)t,nd_eq)==MISS)
        if (mock_look((const unsigned char*)t,nd_ne)==MISS)
            if (mock_look((const unsigned char*)t,nd_is)==MISS)
                return t;
    U cur=t;
    U i=0, ins=0;
    U n=slen(cur);
    while (i<n){
        unsigned b=PB(cur,i);
        if (b==92){ i+=2; continue; }
        if (b==34){ ins=1-ins; i++; continue; }
        if (ins==0){
            if (mock_sg_match(cur,i,(U)(void*)nd_is)){
                cur = cat2s(cat2s(mock_cut(cur,0,i),(U)(void*)" is not "), mock_cut(cur,i+6,slen(cur)));
                n=slen(cur); i+=8; continue;
            }
            if (mock_sg_match(cur,i,(U)(void*)nd_ne)){
                cur = cat2s(cat2s(mock_cut(cur,0,i),(U)(void*)" is not "), mock_cut(cur,i+4,slen(cur)));
                n=slen(cur); i+=8; continue;
            }
            if (mock_sg_match(cur,i,(U)(void*)nd_eq)){
                cur = cat2s(cat2s(mock_cut(cur,0,i),(U)(void*)" is "), mock_cut(cur,i+3,slen(cur)));
                n=slen(cur); i+=4; continue;
            }
        }
        i++;
    }
    return cur;
}
/* str_num: parse decimal (leading digits) */
static U mock_str_num(U t){
    U v=0; U n=slen(t);
    for (U i=0;i<n;i++){
        unsigned b=PB(t,i);
        if (b<48||b>57) break;
        v=v*10+(b-48);
    }
    return v;
}
/* sg_numt (6077) */
static U mock_sg_numt(U n){
    if (n<1) n=0;
    char *buf=(char*)mock_alloc(32);
    U w=30; U v=n;
    if (v==0){ buf[30]='0'; w=31; }
    while (v>0){ w--; buf[w]='0'+v%10; v/=10; }
    buf[31]=0;
    return (U)(void*)(buf+w);
}
/* sg_run_head (6089) */
static U mock_sg_run_head(U t){
    U out=mock_list_new();
    static const unsigned char nd_cs[]={':',' ',0};
    static const unsigned char nd_ap[]={' ','+',' ',0};
    U q=mock_look((const unsigned char*)t,(const unsigned char*)nd_cs);
    if (q==MISS) return out;
    U recv=mock_scut(t,0,q);
    U rword=recv, rstart=(U)(void*)"0";
    if (!mock_sg_word(recv)){
        U ap=mock_look((const unsigned char*)recv,nd_ap);
        if (ap==MISS) return out;
        if (!mock_sg_word(mock_scut(recv,0,ap))) return out;
        if (!mock_sg_num(mock_scutr(recv,ap+3))) return out;
        rword=mock_scut(recv,0,ap);
        rstart=mock_scutr(recv,ap+3);
    }
    U rest=mock_cut(t,q+2,slen(t));
    U cp=mock_look((const unsigned char*)rest,nd_cs);
    if (cp==MISS) return out;
    U head=mock_scut(rest,0,cp);
    U sp1=mock_look((const unsigned char*)head,(const unsigned char*)" ");
    if (sp1==MISS) return out;
    U vtext=mock_scutr(rest,cp+2);
    U vals=mock_sg_toks(vtext);
    if (LLEN(vals)<2) return out;
    for (U k=0;k<LLEN(vals);k++)
        if (mock_look((const unsigned char*)ELEM(vals,k),(const unsigned char*)" ")!=MISS) return out;
    out=mock_list_add(out,recv);
    out=mock_list_add(out,mock_cut(head,0,sp1));
    out=mock_list_add(out,mock_scutr(head,sp1+1));
    out=mock_list_add(out,vtext);
    out=mock_list_add(out,rword);
    out=mock_list_add(out,rstart);
    return out;
}
/* sg_step_expr (6138) */
static U mock_sg_step_expr(U a){
    U shape=0, base=0, step=1;
    U extras=BLANK, tail=BLANK;
    if (mock_startswith((const unsigned char*)a,(const unsigned char*)"i")){
        shape=2;
        tail=mock_strip(a+1);
        if (mock_startswith((const unsigned char*)tail,(const unsigned char*)"*")){
            tail=mock_strip(tail+1);
            U cm=mock_look((const unsigned char*)tail,(const unsigned char*)",");
            U npart=tail, rest2=BLANK;
            if (cm!=MISS){
                npart=mock_scut(tail,0,cm);
                rest2=mock_cut(tail,cm,slen(tail));
            }
            if (mock_sg_num(npart)){ step=mock_str_num(npart); tail=rest2; }
            else shape=0;
        }
    }
    if (shape==0){
        U ri=mock_look((const unsigned char*)a,(const unsigned char*)" + ");
        if (ri!=MISS){
            if (mock_sg_num(mock_scut(a,0,ri))){
                base=mock_str_num(mock_scut(a,0,ri));
                tail=mock_cut(a,ri+3,slen(a));
                if (!mock_startswith((const unsigned char*)tail,(const unsigned char*)"i")){
                    U mt=mock_look((const unsigned char*)tail,(const unsigned char*)" * i");
                    if (mt==MISS) return mock_list_new();
                    if (!mock_sg_num(mock_scut(tail,0,mt))) return mock_list_new();
                    step=mock_str_num(mock_scut(tail,0,mt));
                    tail=mock_cut(tail,mt+4,slen(tail));
                } else {
                    tail=tail+1;
                }
                shape=1;
            }
        }
    }
    if (shape==0) return mock_list_new();
    tail=mock_strip(tail);
    if (slen(tail)>0){
        if (!mock_startswith((const unsigned char*)tail,(const unsigned char*)","))
            return mock_list_new();
        extras=tail;
    }
    if (step<1) step=1;
    U ok=mock_list_new();
    ok=mock_list_add(ok,shape);
    ok=mock_list_add(ok,base);
    ok=mock_list_add(ok,step);
    ok=mock_list_add(ok,extras);
    return ok;
}
/* sg_run (6192) */
static U mock_sg_run(U l, U out){
    U t=mock_strip(l);
    U h=mock_sg_run_head(t);
    if (LLEN(h)==0) return out;
    U rbase=ELEM(h,0);
    U rword=ELEM(h,4);
    U rstart=mock_str_num(ELEM(h,5));
    U fn=ELEM(h,1);
    U e=mock_sg_step_expr(ELEM(h,2));
    if (LLEN(e)==0) return out;
    U shape=ELEM(e,0), base=ELEM(e,1), step=ELEM(e,2), extras=ELEM(e,3);
    U vals=mock_sg_toks(ELEM(h,3));
    U sp=mock_sg_sp(mock_sg_ind(l));
    for (U k=0;k<LLEN(vals);k++){
        U at=base+step*k;
        U line=mock_sg_cat4(sp,fn,(U)(void*)"(",BLANK);
        if (shape==2)
            line=cat2s(line,cat2s(rword,cat2s((U)(void*)" + ",mock_sg_numt(rstart+at))));
        if (shape==1)
            line=cat2s(line,cat2s(rbase,cat2s((U)(void*)", ",mock_sg_numt(at))));
        if (slen(extras)>0) line=cat2s(line,extras);
        line=cat2s(line,cat2s((U)(void*)", ",cat2s(ELEM(vals,k),(U)(void*)")")));
        out=mock_list_add(out,line);
    }
    return out;
}
/* sg_lists (6237) */
static U mock_sg_lists(U l){
    U t=l;
    if (PB(l,0)<33) t=mock_sg_trim(l);
    U out=mock_list_new();
    static const unsigned char nd_cs[]={':',' ',0};
    U q1=mock_look((const unsigned char*)t,nd_cs);
    if (q1==MISS) return out;
    if (mock_look((const unsigned char*)(t+q1+2),nd_cs)!=MISS){
        out=mock_sg_run(l,out);
        if (LLEN(out)>0) return out;
    }
    if (PB(t,0)<48 || PB(t,0)>57) return out;
    U left=mock_scut(t,0,q1);
    if (!mock_sg_num(left)) return out;
    U right=mock_scutr(t,q1+2);
    U toks=mock_sg_toks(right);
    U okv=1;
    for (U k=0;k<LLEN(toks);k++)
        if (!mock_sg_word(ELEM(toks,k))) okv=0;
    if (!okv) return out;
    if (LLEN(toks)<2) return out;
    U sp=mock_sg_sp(mock_sg_ind(l));
    for (U k=0;k<LLEN(toks);k++)
        out=mock_list_add(out,mock_sg_cat4(sp,ELEM(toks,k),(U)(void*)": ",left));
    return out;
}
/* sg_text (5818) */
static U mock_sg_text(U ls){
    U tot=1;
    for (U i=0;i<LLEN(ls);i++) tot+=slen(ELEM(ls,i))+1;
    unsigned char *buf=(unsigned char*)mock_alloc(tot+2);
    U w=0;
    for (U i=0;i<LLEN(ls);i++){
        U ln=ELEM(ls,i);
        U kl=slen(ln);
        if (kl) memcpy(buf+w,(const void*)ln,kl);
        w+=kl;
        buf[w++]=10;
    }
    buf[w]=0;
    return (U)(void*)buf;
}
/* sg_one (6045): recursive full expansion */
static U mock_sg_one(U l){
    U t=l;
    if (PB(l,0)<33) t=mock_sg_trim(l);
    if (mock_startswith((const unsigned char*)t,(const unsigned char*)"#")) return l;
    static const unsigned char nd_eq[]={' ','=',' ',0};
    U eqp=mock_look((const unsigned char*)t,nd_eq);
    if (eqp!=MISS){
        U hd2=mock_scut(t,0,eqp);
        if (mock_sg_word(hd2))
            return mock_sg_cat4(mock_sg_sp(mock_sg_ind(l)),hd2,(U)(void*)": ",mock_cut(t,eqp+3,slen(t)));
    }
    U gen=mock_sg_lists(l);
    if (LLEN(gen)>0){
        if (LLEN(gen)==1 && mock_streq((const unsigned char*)ELEM(gen,0),(const unsigned char*)l))
            return mock_sg_cmp(l);
        U out=mock_list_new();
        for (U gk=0;gk<LLEN(gen);gk++)
            out=mock_list_add(out,mock_sg_one(ELEM(gen,gk)));
        return mock_sg_text(out);
    }
    return mock_sg_cmp(l);
}
/* sg_sq2 (5937): apostrophe squasher */
static U mock_sg_sq2(U l){
    U n=slen(l);
    unsigned char *buf=(unsigned char*)mock_alloc(n*2+8);
    U w=0, i=0, dq=0, sq=0;
    while (i<n){
        unsigned c=PB(l,i);
        if (dq==1){
            buf[w++]=c;
            if (c==92){ if (i+1<n){ buf[w++]=PB(l,i+1); i++; } }
            else if (c==34) dq=0;
        } else if (sq==1){
            if (c==39){ buf[w++]=34; sq=0; }
            else {
                if (c==92){ buf[w++]=c; if (i+1<n){ buf[w++]=PB(l,i+1); i++; } }
                else {
                    if (c==34) buf[w++]=92;
                    buf[w++]=c;
                }
            }
        } else {
            if (c==35){ while (i<n){ buf[w++]=PB(l,i); i++; } }
            else {
                if (c==34){ dq=1; buf[w++]=c; }
                else if (c==39){ buf[w++]=34; sq=1; }
                else buf[w++]=c;
            }
        }
        i++;
    }
    buf[w]=0;
    return (U)(void*)buf;
}

/* side-effect log: print/fail */
static char g_log[4096];
static U g_logn;
static U mock_print(U s){
    const unsigned char *p=(const unsigned char*)s;
    U k=0;
    if (p) while (p[k] && g_logn+2<sizeof(g_log)){ g_log[g_logn++]=(char)p[k]; k++; }
    g_log[g_logn++]='|';
    return 0;
}
static U g_failed;
static U mock_fail(void){ g_failed=1; g_log[g_logn++]='F'; return 0; }

/* ------------------------------------------------------------------ */
/* the two mock tables                                                */
/* ------------------------------------------------------------------ */
static U to_old[24], to_new[24];
static void tbl_reset(U *t){
    memset(t,0,24*8);
    *(U*)(t+0)=21;
    t[1]=(U)mock_lines_of_fast;
    t[2]=(U)mock_list_new;
    t[3]=(U)mock_list_add;
    t[4]=(U)mock_alloc;
    t[5]=(U)mock_sg_sq2;
    t[6]=(U)mock_sg_cat4;
    t[7]=(U)mock_sg_cat5;
    t[8]=(U)mock_sg_toks;
    t[9]=(U)mock_str_cat;
    t[10]=(U)mock_sg_pad3;
    t[11]=(U)mock_sg_ph;
    t[12]=(U)mock_sg_sub;
    t[13]=(U)mock_cut;
    t[14]=(U)mock_strip;
    t[15]=(U)mock_sg_lists;
    t[16]=(U)mock_sg_one;
    t[17]=(U)mock_sg_cmp;
    t[18]=(U)mock_sg_sp;
    t[19]=(U)mock_sg_digits;
    t[20]=(U)mock_print;
    t[21]=(U)mock_fail;
}

/* ------------------------------------------------------------------ */
/* run + serialize + compare                                          */
/* ------------------------------------------------------------------ */
static ENTRY eo, en;
static long ncase, nfail;
static char bo[1<<23], bn[1<<23];

static char *ser_out(U out, char *buf, size_t bufsz){
    size_t w=0;
    U lo = out ? LLEN(out) : 0;
    w += snprintf(buf+w, bufsz-w, "L%llu:", (unsigned long long)lo);
    for (U i=0;i<lo && w<bufsz-32;i++){
        const unsigned char *e=(const unsigned char*)ELEM(out,i);
        size_t n=e?xstrlen(e):0;
        w += snprintf(buf+w, bufsz-w, "%zu:", n);
        for (size_t j=0;j<n && w<bufsz-16;j++){
            unsigned char c=e[j];
            if (c>=32 && c<127 && c!='\\' && c!=';' && c!='|') buf[w++]=c;
            else w += snprintf(buf+w, bufsz-w, "\\x%02x", c);
        }
        buf[w++]=';';
    }
    buf[w]=0;
    return buf;
}

static void run_case(const char *tag, U text){
    tbl_reset(to_old);
    tbl_reset(to_new);
    g_log[0]=0; g_logn=0; g_failed=0;
    U ro = eo(text, (U)(void*)to_old);
    static char lo[sizeof(g_log)];
    memcpy(lo, g_log, g_logn+1);
    U fl_o = g_failed;
    g_log[0]=0; g_logn=0; g_failed=0;
    U rn = en(text, (U)(void*)to_new);
    ncase++;
    if (ro != rn && !ro && !rn){
        /* both empty-ish: fall through to serialize (0 vs 0 handled) */
    }
    ser_out(ro, bo, sizeof(bo));
    ser_out(rn, bn, sizeof(bn));
    int bad = 0;
    if ((ro==0) != (rn==0)) bad = 1;
    if (!bad && strcmp(bo,bn)!=0) bad = 1;
    if (!bad && (fl_o != g_failed || strcmp(lo, g_log)!=0)) bad = 1;
    if (getenv("DUMP_SER")){
        static FILE *df;
        if (!df) df = fopen(getenv("DUMP_SER"), "wb");
        fprintf(df, "== %s\n%s\n", tag, bo);
    }
    if (bad){
        nfail++;
        fprintf(stderr, "DIVERGE %s:\n old %s%s\n new %s%s\n", tag, bo, lo, bn, g_log);
    }
    talloc_purge();
}

/* ---- stress texts ---- */
static const char *stress_texts[] = {
    /* pack marks + expansion */
    "main:\n    a: 1 ;; b: 2\n    return a",
    "main:\n    if x > 0 -> print y\n    as long as i < 9 -> j: i + 1\n    return 0",
    "main:\n    t: f(1) -> g(2) -> h(3)\n    return t",
    /* arrows with empty halves (must NOT split) */
    "main:\n    if b1 > b0\n        x: 1\n    return x",
    /* quotes: multi-line string state */
    "main:\n    s: \"abc\n    def\"\n    t: 'q'\n    return s",
    "main:\n    s: \"a\\\"b\"\n    u: \"x\n\" ; y\n    return s",
    /* " = " rewrites */
    "main:\n    x = 1\n    y  =  2\n    z = x + y\n    return z",
    "main:\n    a = b\n    if a != c -> d = 1\n    e isnt f\n    return a",
    /* digit-led call runs */
    "0: STP BOK BBAD RES\n    x: 1\n    return x",
    "4: poke_byte 4 + i: 1 2 3\n    y: 2\n    return y",
    "m: poke_byte i, 0: 1 2 3\n    z: 3\n    return z",
    "16 + 4 * i: peek a: 7 8\n    w: 4\n    return w",
    /* use:/print:/emit: blocks */
    "use:\n    fn1\n    fn2\nmain:\n    return 1",
    "print:\n    hello\n    world\nmain:\n    return 1",
    "emit:\n    1 2 3\n    4 5\nmain:\n    return 1",
    "emit4:\n    12 34\n    56\nmain:\n    return 1",
    "emit8:\n    1122 3344\nmain:\n    return 1",
    /* thresh value groups */
    "blank:\n    a\n    b\nmain:\n    return 1",
    "3:\n    x\n    y\n    z\nmain:\n    return 1",
    "-2:\n    p\n    q\nmain:\n    return 1",
    /* hd_# lanes and (x): placeholders */
    "lone_:\n    a: 1\n    b: 2\nmain:\n    return 1",
    "hdr(x):\n    a: b_\nmain:\n    return 1",
    "dst: fn(a, b) -> c\n    z: 1\nmain:\n    return 1",
    /* comments/blank/trailing shapes */
    "# comment: with: colons\nmain:\n\n    a: 1\n   \n\tb: 2\n    return a\n",
    "main:",
    "main:\n",
    "",
    "\n\n\n",
    "a: 1",
    "    indented only",
    "main:\n    x: 'apostrophe'\n    y: \"don't\"\n    return x",
    "main:\n    q: \"it's ;; not > a mark\"\n    return q",
    "main:\n    n: 5\n    m: n ; 6\n    return m",
    "x: 1\nmain:\n    return x",
    "g1: 1\ng2: 2\nmain:\n    return g1",
    /* tail ' = ' over-match quirk: trailing-space occurrence */
    "main:\n    a: b = \n    return a",
    "main:\n    zz: 1 =\n    return zz",
    /* colon+space inside strings and after backslash */
    "main:\n    s: \"a: b\"\n    t: \"c\\\\: d\"\n    return s",
    /* 12/13-line body boundary is a c0parse concern; reader just passes */
    "main:\n    t0: 1\n    t1: 2\n    t2: 3\n    t3: 4\n    t4: 5\n    t5: 6\n    t6: 7\n    t7: 8\n    t8: 9\n    t9: 10\n    t10: 11\n    t11: 12\n    return t0",
    "main:\n    t0: 1\n    t1: 2\n    t2: 3\n    t3: 4\n    t4: 5\n    t5: 6\n    t6: 7\n    t7: 8\n    t8: 9\n    t9: 10\n    t10: 11\n    t11: 12\n    t12: 13\n    return t0",
    NULL
};

/* ---- PRNG texts ---- */
static U rng_s = 0x12345678u;
static U rnd(U m){ rng_s = rng_s*6364136223846793005ULL + 1442695040888963407ULL; return (rng_s>>33)%m; }

/* line pool modeled on the S28 PRNG shapes plus reader-sensitive bytes */
static const char *prng_line(char *buf, size_t sz){
    static const char *shapes[] = {
        "    v%llu: %llu",
        "    v%llu: f%llu(%llu, %llu)",
        "    if p%llu is %llu",
        "        w%llu: g%llu(3)",
        "    v%llu: \"f%llu(9)\"",
        "    v%llu = p%llu + %llu",
        "    v%llu != p%llu",
        "    v%llu isnt p%llu",
        "    v%llu: h%llu ;; w%llu: %llu",
        "    if x%llu > %llu -> y%llu: %llu",
        "    as long as i%llu < %llu -> j%llu: i%llu + 1",
        "    v%llu: '%c'",
        "    v%llu: \"q%llu: s\"",
        "%llu: aa%llu bb%llu cc%llu",
        "    t%llu: poke_byte 4 + i: %llu %llu",
        "    # comment %llu: with colon",
        "    v%llu: 'a > b ;; c'",
        "    v%llu = 'x' ;  y = 2",
        "use:",
        "print:",
        "emit:",
        "blank:",
        "    ",
        "",
    };
    U si = rnd(sizeof(shapes)/sizeof(shapes[0]));
    switch (si){
    case 11: snprintf(buf,sz,shapes[si],rnd(100),'a'+rnd(26)); break;
    case 13: snprintf(buf,sz,shapes[si],rnd(100),rnd(100),rnd(100),rnd(100)); break;
    case 22: case 23: snprintf(buf,sz,"%s",shapes[si]); break;
    default: snprintf(buf,sz,shapes[si],rnd(100),rnd(100),rnd(100)); break;
    }
    return buf;
}

/* harness-side plain lists: NOT purged per case (bodies live for the
 * whole file); every mock_ helper above stays tracked+purged */
static U h_list_new(void){
    U b=(U)malloc(16+24*8+8);
    *(U*)b=24; *(U*)(b+8)=0;
    return b;
}
static U h_list_add(U l, U v){
    U n=LLEN(l), cap=*(U*)l;
    if (n>=cap){
        U nc=cap*2;
        U b=(U)malloc(16+nc*8+8);
        *(U*)b=nc; *(U*)(b+8)=n;
        memcpy((void*)(b+16),(void*)(l+16),n*8);
        l=b;
    }
    ELEM(l,n)=v; *(U*)(l+8)=n+1;
    return l;
}

/* ---- real .sov file parser (S28 shape): functions + bodies + whole file ---- */
#define MAXF 8192
#define BODY_MAX 65536
typedef struct {
    U nf;
    char *names[MAXF];
    U bodies[MAXF];       /* line lists */
    U blens[MAXF];
} Parsed;

static Parsed *parse_file(const char *path){
    FILE *f=fopen(path,"rb");
    if (!f) return NULL;
    static char src[32<<20];
    size_t n=fread(src,1,sizeof(src)-1,f);
    fclose(f);
    if (n>=sizeof(src)-1){ fprintf(stderr,"skip big %s\n",path); return NULL; }
    src[n]=0;
    Parsed *P=(Parsed*)malloc(sizeof(Parsed));
    memset(P,0,sizeof(*P));
    /* exact line count then split (keep every byte except newline) */
    U ln=0;
    { const char *sc=src; while (sc<src+n){ const char *e=(const char*)memchr(sc,'\n',src+n-sc); ln++; if(!e) break; sc=e+1; } }
    char **lines=(char**)malloc((ln+2)*sizeof(char*));
    ln=0;
    { char *cur=src; while (cur<src+n){ char *e=(char*)memchr(cur,'\n',src+n-cur); size_t L=e?(size_t)(e-cur):(size_t)(src+n-cur); char *dup=(char*)mock_alloc(L+1); memcpy(dup,cur,L); dup[L]=0; lines[ln++]=dup; if(!e) break; cur=e+1; } }
    /* function = indent-0 header ending ':', body = indented lines until next */
    U i=0;
    char *cur_name=0;
    char **body=(char**)malloc(BODY_MAX*sizeof(char*)); U bn=0;
    while (i<=ln){
        int last=(i==ln);
        const char *L=last?"":lines[i];
        int ind0=(!last)&&L[0]!=' '&&L[0]!=0&&L[0]!='#';
        if (ind0){
            size_t ll=strlen(L);
            int is_hdr=ll>0&&L[ll-1]==':';
            if (is_hdr){
                if (cur_name&&bn){
                    U bl=h_list_new();
                    for (U q=0;q<bn;q++) bl=h_list_add(bl,(U)(void*)strdup(body[q]));
                    P->names[P->nf]=cur_name; P->bodies[P->nf]=bl; P->blens[P->nf]=bn; P->nf++;
                }
                char *hdr=strdup(L); hdr[ll-1]=0;
                char *sp=strchr(hdr,' '); if (sp)*sp=0;
                cur_name=hdr; bn=0;
            }
        } else if (cur_name && !last){
            if (bn<BODY_MAX) body[bn++]=(char*)strdup(L);
        }
        i++;
    }
    if (cur_name&&bn){
        U bl=h_list_new();
        for (U q=0;q<bn;q++) bl=h_list_add(bl,(U)(void*)strdup(body[q]));
        P->names[P->nf]=cur_name; P->bodies[P->nf]=bl; P->blens[P->nf]=bn; P->nf++;
    }
    free(lines); free(body);
    return P;
}

/* join a body's lines back into a text with trailing newline */
static U body_text(U lines_list, U nl){
    size_t tot=2;
    for (U i=0;i<nl;i++) tot+=xstrlen((const unsigned char*)ELEM(lines_list,i))+1;
    char *buf=(char*)malloc(tot+1);   /* harness-side: freed by caller */
    size_t w=0;
    for (U i=0;i<nl;i++){
        const char *l=(const char*)ELEM(lines_list,i);
        size_t kl=strlen(l);
        memcpy(buf+w,l,kl); w+=kl;
        buf[w++]='\n';
    }
    buf[w]=0;
    return (U)(void*)buf;
}

static void run_text_file(const char *tag, const char *path){
    /* whole file as one case + every function body as a case */
    FILE *f=fopen(path,"rb");
    if (!f){ fprintf(stderr,"open %s failed\n",path); return; }
    static char src[32<<20];
    size_t n=fread(src,1,sizeof(src)-1,f);
    fclose(f);
    if (n>=sizeof(src)-1){ fprintf(stderr,"%s too big, skipped\n",path); return; }
    src[n]=0;
    char tag2[512];
    snprintf(tag2,sizeof(tag2),"file:%s",tag);
    run_case(tag2,(U)(void*)src);
    Parsed *P=parse_file(path);
    if (!P) return;
    for (U fi=0;fi<P->nf;fi++){
        char tag3[600];
        snprintf(tag3,sizeof(tag3),"%s/%s",tag,P->names[fi]);
        U txt=body_text(P->bodies[fi],P->blens[fi]);
        run_case(tag3,txt);
        free((void*)txt);
    }
}

/* ------------------------------------------------------------------ */
/* timing mode                                                        */
/* ------------------------------------------------------------------ */
static double now_sec(void){
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts);
    return (double)ts.tv_sec+(double)ts.tv_nsec*1e-9;
}
static int tcmp(const void*a,const void*b){
    double x=*(const double*)a,y=*(const double*)b;
    return x<y?-1:x>y?1:0;
}
static void time_side(ENTRY e, U tbl_, U text, int runs, const char *name){
    U *tbl=(U*)tbl_;
    double t[64];
    if (runs>64) runs=64;
    for (int r=0;r<runs;r++){
        double t0=now_sec();
        U out=e(text,(U)(void*)tbl);
        t[r]=now_sec()-t0;
        (void)out;
    }
    qsort(t,runs,sizeof(double),tcmp);
    fprintf(stderr,"TIME %-6s median %.3f ms  best %.3f ms\n",name,t[runs/2]*1000,t[0]*1000);
}

int main(int argc, char **argv){
    if (argc<3){ fprintf(stderr,"usage: %s old.so new.so [-T runs] [file.sov...]\n",argv[0]); return 2; }
    int timing=0, truns=9;
    int ai0=3;
    if (argc>3 && !strcmp(argv[3],"-T")){ timing=1; truns=argc>4?atoi(argv[4]):9; ai0=5; }
    void *ho=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
    void *hn=dlopen(argv[2],RTLD_NOW|RTLD_LOCAL);
    if (!ho||!hn){ fprintf(stderr,"dlopen failed: %s\n",dlerror()); return 2; }
    eo=(ENTRY)dlsym(ho,"old_cx_read");
    en=(ENTRY)dlsym(hn,"reader_core");
    if (!eo||!en){ fprintf(stderr,"dlsym failed: %p %p\n",(void*)eo,(void*)en); return 2; }

    /* timing first (before any case state) */
    if (timing){
        static char flat[32<<20];
        FILE *f=fopen("work/p4/s29/self.flat","rb");
        if (!f){ fprintf(stderr,"no work/p4/s29/self.flat for -T\n"); return 2; }
        size_t n=fread(flat,1,sizeof(flat)-1,f); fclose(f);
        flat[n]=0;
        /* warm both sides once (page faults, arena setup) */
        tbl_reset(to_old); tbl_reset(to_new);
        eo((U)(void*)flat,(U)(void*)to_old);
        en((U)(void*)flat,(U)(void*)to_new);
        time_side(eo,(U)(void*)to_old,(U)(void*)flat,truns,"old");
        time_side(en,(U)(void*)to_new,(U)(void*)flat,truns,"new");
    }

    /* stress */
    for (int q=0;stress_texts[q];q++){
        char tag[64]; snprintf(tag,sizeof(tag),"stress-%d",q);
        run_case(tag,(U)(void*)stress_texts[q]);
    }
    /* PRNG */
    for (int c=0;c<60;c++){
        char buf[65536];
        size_t w=0;
        U nl=4+rnd(30);
        for (U q=0;q<nl;q++){
            char lb[256];
            prng_line(lb,sizeof(lb));
            size_t kl=strlen(lb);
            if (w+kl+2>=sizeof(buf)) break;
            memcpy(buf+w,lb,kl); w+=kl;
            buf[w++]='\n';
        }
        buf[w]=0;
        char tag[32]; snprintf(tag,sizeof(tag),"prng-%d",c);
        if (getenv("DUMP_PRNG")){ char fn[64]; snprintf(fn,sizeof(fn),"/tmp/prng-%d.txt",c); FILE *df=fopen(fn,"wb"); fwrite(buf,1,w,df); fclose(df); }
        run_case(tag,(U)(void*)buf);
    }
    /* files */
    for (int ai=ai0;ai<argc;ai++)
        run_text_file(argv[ai],argv[ai]);

    printf("cases=%ld failures=%ld\n",ncase,nfail);
    return nfail?1:0;
}
