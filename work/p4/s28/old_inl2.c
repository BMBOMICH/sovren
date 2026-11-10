/* Native inl2_scan: the inline-eligibility scanner, C port.
 * 1:1 mirror of the inl2 family in compilers/shared/cx86_p6.sov:
 * inl2_scan (fixpoint driver, <=32 passes, okm/okb body-ok memo),
 * inl2_one (candidate discovery + the zzln splice), inl2_callfind
 * (unique-call finder), inl2_body_ok (straight-line callee check),
 * inl2_scanreads, inl2_rename, inl2_mkcn, inl2_idc/idc2/wop/purecall.
 * strip_span/indent_of/look/cut/strip/cfind1/str_cat/same/plain_name/
 * is_imm/licm_lhs/licm_in/licm_add are fused static span mirrors; splice
 * outputs are arena strings/lists.
 * The env-gated determinism probe (inl2_lopen/inl2_ldec, /tmp/sov_inl2log)
 * is NOT mirrored: it only writes a side log when the gate file exists and
 * never affects translation output; normal runs never create it.
 * Helpers behind the caller-provided tbl (Sovren ABI:
 * rdi,rsi,rdx,rcx,r8,r9,r10; result rax):
 *   1 in_set_out(v)        (inl2_out := v)
 *   2 in_set_sln(v)        (inl2_sln := v)
 *   3 _sov_heap_alloc(n)
 *   4 split_args(inside, argl)  (interpreted splitter, exact semantics;
 *     rare path - once per accepted site - so one dispatch is fine)
 * The tbl block doubles as the persistent cell (zero fast-path dispatch):
 * slot 0 = count (4), slots 1..4 = the helpers, slot 5 = arp, slot 6 =
 * are (written by ar_grow), slot 7 = generation tag, slot 8 = state base.
 * Data slots published by the caller (flor_range) per function:
 *   9 = names list, 10 = params list, 11 = bodies list, 12 = gh set
 *   pointer, 13 = gcap, 14 = task_user list.
 * The state block owns a DEDICATED allocation (the licm lesson: anything
 * inside the bump arena dies at every ar_grow chunk change): okm/okb
 * memo lists, the cnci capture-set memo, a blob-local names hash (names
 * are unique post-parse - zz_dup - so nm_lookup's answer is
 * hash-independent) and a blob-local gh-membership hash (set_has answers
 * membership - hash-independent).  nm_lookup and set_hash therefore never
 * dispatch; task_user is peeked directly.
 * The inl2_one double body_ok call is mirrored exactly: on a memo hit the
 * second call still runs because its side effects on cl/ret feed the
 * splice.
 * Sovren integer comparisons are SIGNED (look/cfind1 answers are -1;
 * look(...) is 0 when the needle sits at index 0 - body_ok's return
 * checks depend on that).
 * No external symbols, no relocations, no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef long long S;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);

enum {
 IN_SETOUT=1, IN_SETSLN=2, IN_ALLOC=3, IN_SPLITARGS=4
};
/* tbl-as-cell layout (U* slots):
 * 0=count, 1..4=helpers, 5=arp, 6=are, 7=gen, 8=state base,
 * 9=names, 10=params, 11=bodies, 12=gh, 13=gcap, 14=task_user */

static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }

#define MISS ((U)-1)
#define LLEN(x) (*(U*)((x)+8))
#define ELEM(x,i) (*(U*)((x)+16+(U)(i)*8))
#define PB(s,i) (*(const unsigned char*)((s)+(U)(i)))

/* ---- span model: [b, e) ---- */
typedef struct { const unsigned char *b; const unsigned char *e; } Sp;
static inline U splen(Sp s){ return (U)(s.e - s.b); }
static Sp sp_empty(void){ Sp r; r.b = 0; r.e = 0; return r; }
/* stack-built literal spans: NO .rodata (the relocation gate) */
#define STACK_SP(name, ...) char name##_buf[] = {__VA_ARGS__}; \
    Sp name; name.b = (const unsigned char*)name##_buf; \
    name.e = (const unsigned char*)name##_buf + sizeof(name##_buf)

/* ---- persistent bump arena (1 MiB chunks; old chunks are abandoned,
 * never freed - pointers into them stay valid for the process lifetime) */
#define AR_CHUNK 1048576
static U ar_grow(U *t, U *arp, U *are, U n){
    U want = AR_CHUNK; if (want < n) want = n;
    U p = t1(t, IN_ALLOC, want);
    *arp = p; *are = p + want;
    return p;
}
static inline U ar_get(U *t, U *arp, U *are, U n){
    /* keep every allocation 16-byte aligned: gcc moves the 16-byte Sp
     * structs with aligned SSE (movdqa) and a misaligned bump pointer
     * (e.g. after a 14-byte string) crashes the self build */
    *arp = (*arp + 15) & ~(U)15;
    if (*arp + n > *are) ar_grow(t, arp, are, n);
    U p = *arp; *arp = p + n; return p;
}
static U ar_str(U *t, U *arp, U *are, Sp s){
    U n = splen(s);
    U p = ar_get(t, arp, are, n + 1);
    U i = 0;
    while (i < n){ *(unsigned char*)(p+i) = s.b[i]; i++; }
    *(unsigned char*)(p+n) = 0;
    return p;
}
static U ar_cat(U *t, U *arp, U *are, Sp a, Sp b){
    U n = splen(a) + splen(b);
    U p = ar_get(t, arp, are, n + 1);
    U i = 0;
    while (i < splen(a)){ *(unsigned char*)(p+i) = a.b[i]; i++; }
    U j = 0;
    while (j < splen(b)){ *(unsigned char*)(p+i+j) = b.b[j]; j++; }
    *(unsigned char*)(p+n) = 0;
    return p;
}
static U ar_cat3(U *t, U *arp, U *are, Sp a, Sp b, Sp c){
    U n = splen(a) + splen(b) + splen(c);
    U p = ar_get(t, arp, are, n + 1);
    U i = 0;
    while (i < splen(a)){ *(unsigned char*)(p+i) = a.b[i]; i++; }
    U j = 0;
    while (j < splen(b)){ *(unsigned char*)(p+i+j) = b.b[j]; j++; }
    U k = 0;
    while (k < splen(c)){ *(unsigned char*)(p+i+j+k) = c.b[k]; k++; }
    *(unsigned char*)(p+n) = 0;
    return p;
}
static U ar_cat4(U *t, U *arp, U *are, Sp a, Sp b, Sp c, Sp d){
    U n = splen(a) + splen(b) + splen(c) + splen(d);
    U p = ar_get(t, arp, are, n + 1);
    U w = 0;
    U i = 0;
    while (i < splen(a)){ *(unsigned char*)(p+w++) = a.b[i]; i++; }
    i = 0;
    while (i < splen(b)){ *(unsigned char*)(p+w++) = b.b[i]; i++; }
    i = 0;
    while (i < splen(c)){ *(unsigned char*)(p+w++) = c.b[i]; i++; }
    i = 0;
    while (i < splen(d)){ *(unsigned char*)(p+w++) = d.b[i]; i++; }
    *(unsigned char*)(p+n) = 0;
    return p;
}
static U ar_list(U *t, U *arp, U *are, U cap){
    U p = ar_get(t, arp, are, 16 + cap * 8);
    *(U*)(p) = cap;
    *(U*)(p+8) = 0;
    return p;
}
static inline void lput(U l, U i, U v){ *(U*)(l+16+i*8) = v; }
static inline void lpush(U l, U v){ U n = LLEN(l); lput(l, n, v); *(U*)(l+8) = n+1; }

/* ---- string primitives, span forms ---- */
static U xstrlen(const unsigned char *s){ U n=0; while (s[n]) n++; return n; }
static Sp sp_of(U p){
    const unsigned char *b = (const unsigned char*)(void*)p;
    Sp r; r.b = b; r.e = b + xstrlen(b);
    return r;
}
static S cfind1(const unsigned char *t, unsigned ch){
    if (!t) return (S)MISS;
    for (U i=0; t[i]; i++) if (t[i]==ch) return (S)i;
    return (S)MISS;
}
static S span_find(Sp s, const unsigned char *nb, U nl){
    U n = splen(s);
    if (nl == 0) return 0;
    if (n < nl) return (S)MISS;
    U i = 0;
    while (i + nl <= n){
        U j = 0;
        while (j < nl && s.b[i+j] == nb[j]) j++;
        if (j == nl) return (S)i;
        i++;
    }
    return (S)MISS;
}
static S nfind(const unsigned char *t, const unsigned char *ndl){
    if (!t) return (S)MISS;
    return span_find(sp_of((U)(void*)t), ndl, xstrlen(ndl));
}
static int span_eq(Sp a, Sp b){
    U n = splen(a);
    if (n != splen(b)) return 0;
    U i = 0;
    while (i < n){ if (a.b[i] != b.b[i]) return 0; i++; }
    return 1;
}
static Sp sp_trim(const unsigned char *t){
    Sp r; r.b = t; r.e = t + xstrlen(t);
    while (r.b < r.e){
        unsigned c = *r.b;
        if (c==32||c==9||c==10||c==13) r.b++;
        else break;
    }
    while (r.e > r.b){
        unsigned c = r.e[-1];
        if (c==32||c==9||c==10||c==13) r.e--;
        else break;
    }
    return r;
}
static Sp sp_strip_span(const unsigned char *t){
    Sp r; r.b = t; r.e = t;
    if (!t) return r;
    U a = 0;
    while (t[a] == 32) a++;
    if (t[a] == 9) return sp_trim(t);
    const unsigned char *s = t + a;
    U n = xstrlen(s);
    if (n == 0){ r.b = s; r.e = s; return r; }
    if (s[n-1] < 33) return sp_trim(t);
    r.b = s; r.e = s + n;
    return r;
}
static Sp sp_cut(const unsigned char *t, S a, S b){
    S n = (S)xstrlen(t);
    if (a < 0) a = 0;
    if (b > n) b = n;
    if (b < a) b = a;
    Sp r; r.b = t + a; r.e = t + b;
    return r;
}
static Sp ssp_cut(Sp s, S a, S b){
    S n = (S)splen(s);
    if (a < 0) a = 0;
    if (b > n) b = n;
    if (b < a) b = a;
    Sp r; r.b = s.b + a; r.e = s.b + b;
    return r;
}
static int plain_name(Sp s){
    U i = 0, n = splen(s);
    while (i < n){
        unsigned c = s.b[i];
        if (c==32||c==33||c==34||c==37||c==38||c==40||c==41||c==42||
            c==43||c==45||c==47||c==60||c==61||c==62||c==91||c==93||c==124)
            return 0;
        i++;
    }
    return 1;
}
static int is_imm(Sp s){
    U n = splen(s);
    if (n == 0) return 0;
    U i = 0;
    if (s.b[0] == 45) i = 1;
    if (i >= n) return 0;
    while (i < n){
        unsigned c = s.b[i];
        if (c < 48 || c > 57) return 0;
        i++;
    }
    return 1;
}
static int span_starts(Sp s, const char *lit){
    (void)lit;
    return 0;
}
#define DEF_EQ(name, ...) static int name(Sp nm){ \
    const char _c[] = {__VA_ARGS__}; \
    if (splen(nm) != sizeof(_c)) return 0; \
    U _i = 0; while (_i < sizeof(_c)){ if (nm.b[_i] != (unsigned char)_c[_i]) return 0; _i++; } \
    return 1; }
DEF_EQ(eq_is, 'i','s')
DEF_EQ(eq_and, 'a','n','d')
DEF_EQ(eq_or, 'o','r')
DEF_EQ(eq_not, 'n','o','t')
DEF_EQ(eq_of, 'o','f')
DEF_EQ(eq_length, 'l','e','n','g','t','h')
DEF_EQ(eq_if_not, 'i','f',' ','n','o','t')
DEF_EQ(eq_band, 'b','a','n','d')
DEF_EQ(eq_bor, 'b','o','r')
DEF_EQ(eq_bxor, 'b','x','o','r')
DEF_EQ(eq_bshl, 'b','s','h','l')
DEF_EQ(eq_bshr, 'b','s','h','r')
DEF_EQ(eq_bsar, 'b','s','a','r')
DEF_EQ(eq_bnot, 'b','n','o','t')
DEF_EQ(eq_wrap_add, 'w','r','a','p','_','a','d','d')
DEF_EQ(eq_wrap_sub, 'w','r','a','p','_','s','u','b')
DEF_EQ(eq_wrap_mul, 'w','r','a','p','_','m','u','l')
DEF_EQ(eq_peek_byte, 'p','e','e','k','_','b','y','t','e')
DEF_EQ(eq_peek_i64, 'p','e','e','k','_','i','6','4')
DEF_EQ(eq_peek_u8, 'p','e','e','k','_','u','8')
DEF_EQ(eq_char_at, 'c','h','a','r','_','a','t')
DEF_EQ(eq_sov_strlen, '_','s','o','v','_','s','t','r','l','e','n')
DEF_EQ(eq_sov_str_eq, '_','s','o','v','_','s','t','r','_','e','q')
DEF_EQ(eq_sov_list_len, '_','s','o','v','_','l','i','s','t','_','l','e','n')
DEF_EQ(eq_sov_list_get, '_','s','o','v','_','l','i','s','t','_','g','e','t')
DEF_EQ(eq_sov_find_text, '_','s','o','v','_','f','i','n','d','_','t','e','x','t')
/* starts-with matchers without literals */
static int starts_ret7(Sp s){ return splen(s) >= 7 && s.b[0]=='r' && s.b[1]=='e' && s.b[2]=='t' && s.b[3]=='u' && s.b[4]=='r' && s.b[5]=='n' && s.b[6]==' '; }
static int starts_if3(Sp s){ return splen(s) >= 3 && s.b[0]=='i' && s.b[1]=='f' && s.b[2]==' '; }
/* find matchers without literals (first index or -1) */
static S find_ret7(const unsigned char *t){
    U n = xstrlen(t);
    U i = 0;
    while (i + 7 <= n){
        if (t[i]=='r'&&t[i+1]=='e'&&t[i+2]=='t'&&t[i+3]=='u'&&t[i+4]=='r'&&t[i+5]=='n'&&t[i+6]==' ') return (S)i;
        i++;
    }
    return (S)MISS;
}
static S find_ret6(const unsigned char *t){
    U n = xstrlen(t);
    U i = 0;
    while (i + 6 <= n){
        if (t[i]=='r'&&t[i+1]=='e'&&t[i+2]=='t'&&t[i+3]=='u'&&t[i+4]=='r'&&t[i+5]=='n') return (S)i;
        i++;
    }
    return (S)MISS;
}
static S find_spawn6(Sp s){
    U n = splen(s);
    U i = 0;
    while (i + 6 <= n){
        if (s.b[i]=='s'&&s.b[i+1]=='p'&&s.b[i+2]=='a'&&s.b[i+3]=='w'&&s.b[i+4]=='n'&&s.b[i+5]==' ') return (S)i;
        i++;
    }
    return (S)MISS;
}
static int eq_str(Sp nm, const char *lit){
    (void)nm; (void)lit;
    return 0;
}
static S find_lp(Sp s){
    U n = splen(s);
    U i = 0;
    while (i < n){ if (s.b[i] == 40) return (S)i; i++; }
    return (S)MISS;
}
static S cfind1_sp(Sp s){
    U n = splen(s);
    U i = 0;
    while (i < n){ if (s.b[i] == 58) return (S)i; i++; }
    return (S)MISS;
}
/* licm_lhs: stripped assignment LHS name span, or empty */
static Sp licm_lhs(Sp s){
    Sp empty; empty.b = s.b; empty.e = s.b;
    S p = cfind1_sp(s);
    if (p < 1) return empty;
    unsigned nxt = (p + 1 < (S)splen(s)) ? s.b[p+1] : 0;
    if (nxt != 32) return empty;
    Sp nm = ssp_cut(s, 0, p);
    if (!plain_name(nm)) return empty;
    if (is_imm(nm)) return empty;
    return nm;
}

static int idc(unsigned c){ return (c>64&&c<91)||(c>96&&c<123)||c==95; }
static int idc2(unsigned c){ return idc(c)||(c>47&&c<58); }
static int inl2_wop(Sp nm){
    return eq_is(nm) || eq_and(nm) || eq_or(nm) ||
           eq_not(nm) || eq_of(nm) || eq_length(nm);
}
static int inl2_purecall(Sp nm){
    return eq_band(nm) || eq_bor(nm) || eq_bxor(nm) ||
           eq_bshl(nm) || eq_bshr(nm) || eq_bsar(nm) ||
           eq_bnot(nm) || eq_wrap_add(nm) || eq_wrap_sub(nm) ||
           eq_wrap_mul(nm) || eq_peek_byte(nm) ||
           eq_peek_i64(nm) || eq_peek_u8(nm) ||
           eq_char_at(nm) || eq_sov_strlen(nm) ||
           eq_sov_str_eq(nm) || eq_sov_list_len(nm) ||
           eq_sov_list_get(nm) || eq_sov_find_text(nm);
}

/* ---- per-call state ---- */
typedef struct {
    U *tbl;
    U *arp, *are;
    int bad;                      /* inl2_bad */
    Sp *reads; U rd_n, rd_cap;    /* inl2_reads (dedup'd) */
    Sp *cl; U cl_n, cl_cap;       /* inl2_cl (dedup'd) */
    Sp *cn; U cn_n, cn_cap;       /* inl2_cn (dedup'd) */
    Sp *mapf, *mapt; U map_n, mapf_cap, mapt_cap;  /* lockstep pair */
    Sp ret;                       /* inl2_ret */
    Sp cnm;                       /* inl2_cnm (callfind) */
    S cb1;                        /* inl2_cb1 (callfind) */
    U out, sln;                   /* last success outputs */
    /* state-block views */
    U okm, okb;
    S cnci;
    U *nh; U nh_cap;
    U *ghh; U ghh_cap;
} St;

static Sp *sparr_grow(U *t, U *arp, U *are, Sp *arr, U *cap){
    U nc = *cap ? *cap * 2 : 32;
    Sp *nb = (Sp*)(void*)ar_get(t, arp, are, nc * sizeof(Sp));
    U j = 0;
    while (j < nc){ nb[j].b = 0; nb[j].e = 0; j++; }
    j = 0;
    while (j < *cap){ nb[j] = arr[j]; j++; }
    *cap = nc;
    return nb;
}
static void sparr_push(U *t, U *arp, U *are, Sp **arr, U *n, U *cap, Sp v){
    if (*n == *cap) *arr = sparr_grow(t, arp, are, *arr, cap);
    (*arr)[(*n)++] = v;
}
static void cl_add(St *st, Sp v){
    U i = 0;
    while (i < st->cl_n){ if (span_eq(st->cl[i], v)) return; i++; }
    sparr_push(st->tbl, st->arp, st->are, &st->cl, &st->cl_n, &st->cl_cap, v);
}
static void cn_add(St *st, Sp v){
    U i = 0;
    while (i < st->cn_n){ if (span_eq(st->cn[i], v)) return; i++; }
    sparr_push(st->tbl, st->arp, st->are, &st->cn, &st->cn_n, &st->cn_cap, v);
}
static void rd_add(St *st, Sp v){
    U i = 0;
    while (i < st->rd_n){ if (span_eq(st->reads[i], v)) return; i++; }
    sparr_push(st->tbl, st->arp, st->are, &st->reads, &st->rd_n, &st->rd_cap, v);
}
static int in_sp(Sp *set, U n, Sp v){
    U i = 0;
    while (i < n){ if (span_eq(set[i], v)) return 1; i++; }
    return 0;
}

/* ---- blob-local hashes (state block) ---- */
#define ST_MAGIC 0x494e4c3253544154ULL
static U hash_bytes(const unsigned char *b, U n){
    U h = 1469598103934665603ULL;
    U i = 0;
    while (i < n){ h ^= b[i]; h *= 1099511628211ULL; i++; }
    return h;
}
/* state block (dedicated allocation):
 * 0 magic, 8 gen, 16 okm, 24 okb, 32 cnci, 40 nh ptr, 48 nh cap,
 * 56 ghh ptr, 64 ghh cap */
static void state_build(St *st){
    U base = st->tbl[8];
    U gen = st->tbl[7];
    if (base == 0 || *(U*)(base) != ST_MAGIC){
        base = t1(st->tbl, IN_ALLOC, 72);
        U q = 0;
        while (q < 72){ *(unsigned char*)(base+q) = 0; q++; }
        *(U*)(base) = ST_MAGIC;
        *(U*)(base+32) = 1000000000ULL;
        st->tbl[8] = base;
    }
    if (*(U*)(base+8) != gen){
        *(U*)(base+8) = gen;
        *(U*)(base+16) = 0;
        *(U*)(base+24) = 0;
        *(U*)(base+32) = 1000000000ULL;
        *(U*)(base+40) = 0;
        *(U*)(base+56) = 0;
    }
    st->okm = *(U*)(base+16);
    st->okb = *(U*)(base+24);
    st->cnci = (S)*(U*)(base+32);
    st->nh = (U*)(void*)*(U*)(base+40);
    st->nh_cap = *(U*)(base+48);
    st->ghh = (U*)(void*)*(U*)(base+56);
    st->ghh_cap = *(U*)(base+64);
}
static void state_save(St *st){
    U base = st->tbl[8];
    *(U*)(base+16) = st->okm;
    *(U*)(base+24) = st->okb;
    *(U*)(base+32) = (U)st->cnci;
    *(U*)(base+40) = (U)(void*)st->nh;
    *(U*)(base+48) = st->nh_cap;
    *(U*)(base+56) = (U)(void*)st->ghh;
    *(U*)(base+64) = st->ghh_cap;
}
static void nh_build(St *st){
    U names = st->tbl[9];
    U n = names ? LLEN(names) : 0;
    U cap = 16;
    /* load < 50% (the STAB lesson): cap must be at least 2x the member
     * count or the linear probe never terminates when the table fills.
     * The first version had the comparison inverted (cap*2 < n+1 ->
     * 195% load at n=1000: the self build hung in the insert probe). */
    while (cap < (n + 1) * 2) cap *= 2;
    U *h = (U*)(void*)t1(st->tbl, IN_ALLOC, cap * 2 * 8);
    U q = 0;
    while (q < cap * 2){ h[q] = 0; q++; }
    U i = 0;
    while (i < n){
        U np = ELEM(names, i);
        if (np){
            U hh = hash_bytes((const unsigned char*)(void*)np, xstrlen((const unsigned char*)(void*)np));
            U sl = hh & (cap - 1);
            while (h[sl*2] != 0) sl = (sl + 1) & (cap - 1);
            h[sl*2] = np; h[sl*2+1] = i;
        }
        i++;
    }
    st->nh = h; st->nh_cap = cap;
}
static S nm_lookup_sp(St *st, Sp nm){
    if (!st->nh) nh_build(st);
    U cap = st->nh_cap;
    U hh = hash_bytes(nm.b, splen(nm));
    U sl = hh & (cap - 1);
    while (st->nh[sl*2] != 0){
        if (span_eq(sp_of(st->nh[sl*2]), nm)) return (S)st->nh[sl*2+1];
        sl = (sl + 1) & (cap - 1);
    }
    return (S)MISS;
}
static void ghh_build(St *st){
    U gh = st->tbl[12];
    U gcap = st->tbl[13];
    U members = 0;
    U i = 0;
    while (i < gcap){ if (*(U*)(gh + i*8)) members++; i++; }
    U cap = 16;
    /* load < 50% (the STAB lesson) */
    while (cap < (members + 1) * 2) cap *= 2;
    U *h = (U*)(void*)t1(st->tbl, IN_ALLOC, cap * 8);
    U q = 0;
    while (q < cap){ h[q] = 0; q++; }
    i = 0;
    while (i < gcap){
        U mp = *(U*)(gh + i*8);
        if (mp){
            U hh = hash_bytes((const unsigned char*)(void*)mp, xstrlen((const unsigned char*)(void*)mp));
            U sl = hh & (cap - 1);
            while (h[sl] != 0) sl = (sl + 1) & (cap - 1);
            h[sl] = mp;
        }
        i++;
    }
    st->ghh = h; st->ghh_cap = cap;
}
static int gh_has(St *st, Sp nm){
    if (!st->ghh) ghh_build(st);
    U cap = st->ghh_cap;
    U hh = hash_bytes(nm.b, splen(nm));
    U sl = hh & (cap - 1);
    while (st->ghh[sl] != 0){
        if (span_eq(sp_of(st->ghh[sl]), nm)) return 1;
        sl = (sl + 1) & (cap - 1);
    }
    return 0;
}

/* ---- inl2_scanreads ---- */
static void inl2_scanreads(St *st, Sp e){
    U n = splen(e);
    U i = 0;
    while (i < n){
        unsigned b = e.b[i];
        if (b == 34){ st->bad = 1; return; }
        if (idc(b)){
            U j = i + 1;
            while (j < n && idc2(e.b[j])) j++;
            Sp nm = ssp_cut(e, (S)i, (S)j);
            if (j < n && e.b[j] == 40){
                if (!inl2_purecall(nm)){ st->bad = 1; return; }
                i = j;
            } else {
                if (splen(nm) > 0) rd_add(st, nm);
                i = j;
            }
        } else {
            i++;
        }
    }
}

/* ---- inl2_rename: word-substitute via mapf -> mapt ---- */
static U inl2_rename(St *st, Sp e){
    U out = ar_str(st->tbl, st->arp, st->are, sp_empty());
    U n = splen(e);
    U i = 0;
    while (i < n){
        if (idc(e.b[i])){
            U j = i + 1;
            while (j < n && idc2(e.b[j])) j++;
            Sp nm = ssp_cut(e, (S)i, (S)j);
            Sp rep = nm;
            U mi = 0;
            while (mi < st->map_n){
                if (span_eq(st->mapf[mi], nm)){ rep = st->mapt[mi]; break; }
                mi++;
            }
            out = ar_cat(st->tbl, st->arp, st->are, sp_of(out), rep);
            i = j;
        } else {
            Sp one; one.b = e.b + i; one.e = e.b + i + 1;
            out = ar_cat(st->tbl, st->arp, st->are, sp_of(out), one);
            i++;
        }
    }
    return out;
}

/* ---- inl2_body_ok ---- */
static int inl2_body_ok(St *st, U cb, U cps){
    U nl = LLEN(cb);
    if (nl < 1) return 0;
    if (nl > 12) return 0;
    st->cl_n = 0;
    U qi = 0;
    U cpn = LLEN(cps);
    while (qi < cpn){ cl_add(st, sp_of(ELEM(cps, qi))); qi++; }
    st->rd_n = 0;
    st->bad = 0;
    int inif = 0;
    Sp *exprs = 0; U ex_n = 0, ex_cap = 0;
    U k = 0;
    while (k < nl){
        const unsigned char *ln = (const unsigned char*)(void*)ELEM(cb, k);
        if (cfind1(ln, 9) > -1) return 0;
        if (cfind1(ln, 34) > -1) return 0;
        Sp s = sp_trim(ln);
        if (splen(s) == 0) return 0;
        if (s.b[0] == 35) return 0;
        if (k == nl - 1){
            if (find_ret7(s.b) != 0) return 0;
            st->ret = sp_of(ar_str(st->tbl, st->arp, st->are,
                                   ssp_cut(s, 7, (S)splen(s))));
            st->ret = sp_trim(st->ret.b);
            if (splen(st->ret) == 0) return 0;
            sparr_push(st->tbl, st->arp, st->are, &exprs, &ex_n, &ex_cap, st->ret);
        } else {
            if (find_ret6(s.b) == 0) return 0;
            U sp2 = 0;
            while (PB(ln, sp2) == 32) sp2++;
            Sp nm = licm_lhs(s);
            if (splen(nm) == 0){
                if (sp2 != 4) return 0;
                if (!starts_if3(s)) return 0;
                if (eq_if_not(s)) return 0;
                sparr_push(st->tbl, st->arp, st->are, &exprs, &ex_n, &ex_cap,
                           ssp_cut(s, 3, (S)splen(s)));
                inif = 1;
            }
            if (splen(nm) > 0){
                if (sp2 == 4) inif = 0;
                else {
                    if (sp2 != 8) return 0;
                    if (inif == 0) return 0;
                }
            }
            if (splen(nm) > 0){
                if (gh_has(st, nm)) return 0;
                cl_add(st, nm);
                sparr_push(st->tbl, st->arp, st->are, &exprs, &ex_n, &ex_cap,
                           ssp_cut(s, cfind1_sp(s) + 2, (S)splen(s)));
            }
        }
        k++;
    }
    k = 0;
    while (k < ex_n){
        inl2_scanreads(st, exprs[k]);
        if (st->bad == 1) return 0;
        k++;
    }
    U ri = 0;
    while (ri < st->rd_n){
        Sp rn = st->reads[ri];
        int ok = 0;
        if (in_sp(st->cl, st->cl_n, rn)) ok = 1;
        if (inl2_wop(rn)) ok = 1;
        if (ok == 0){
            if (gh_has(st, rn)){
                if (!in_sp(st->cn, st->cn_n, rn)) ok = 1;
            }
        }
        if (ok == 0) return 0;
        ri++;
    }
    return 1;
}

/* ---- inl2_callfind ---- */
static S inl2_callfind(St *st, Sp rhs){
    U n = splen(rhs);
    U i = 0;
    U found = 0;
    S fb0 = (S)MISS;
    while (i < n){
        if (idc(rhs.b[i])){
            U j = i + 1;
            while (j < n && idc2(rhs.b[j])) j++;
            int iscl = (j < n && rhs.b[j] == 40);
            if (iscl){
                found++;
                if (found > 1) return (S)MISS;
                fb0 = (S)i;
                st->cnm = ssp_cut(rhs, (S)i, (S)j);
                U d = 1;
                U q = j + 1;
                S inw = -1;
                while (q < n){
                    unsigned cb2 = rhs.b[q];
                    if (cb2 == 40) d++;
                    if (cb2 == 41){
                        d--;
                        if (d == 0){ inw = (S)q; break; }
                    }
                    q++;
                }
                if (inw < 0) return (S)MISS;
                st->cb1 = inw;
                i = inw + 1;
            } else {
                i = j;
            }
        } else {
            i++;
        }
    }
    return fb0;
}

/* ---- inl2_mkcn ---- */
static void inl2_mkcn(St *st, U ls, U ci){
    st->cn_n = 0;
    U cp = ELEM(st->tbl[10], ci);
    U qi = 0;
    U cpn = LLEN(cp);
    while (qi < cpn){ cn_add(st, sp_of(ELEM(cp, qi))); qi++; }
    U k = 0;
    U n = LLEN(ls);
    while (k < n){
        Sp nm = licm_lhs(sp_strip_span((const unsigned char*)(void*)ELEM(ls, k)));
        if (splen(nm) > 0) cn_add(st, nm);
        k++;
    }
}

/* ---- inl2_one: inline the first eligible site ---- */
static int inl2_one(St *st, U ls, U sln, U ci){
    U n = LLEN(ls);
    U k = 0;
    while (k < n){
        const unsigned char *lk = (const unsigned char*)(void*)ELEM(ls, k);
        Sp s = sp_strip_span(lk);
        int fire = 0;
        if (find_lp(s) == (S)MISS){
            s = sp_empty();
        }
        U nsp = 0;
        while (PB(lk, nsp) == 32) nsp++;
        U idx = 0;
        if (nsp >= 4){
            if (PB(lk, nsp) != 32){
                if (PB(lk, nsp) != 0){
                    Sp dst = licm_lhs(s);
                    U kind = 0;
                    Sp pre = sp_empty();
                    Sp rhs = sp_empty();
                    if (splen(dst) > 0){
                        S p = cfind1_sp(s);
                        rhs = sp_of(ar_str(st->tbl, st->arp, st->are,
                                           ssp_cut(s, p + 2, (S)splen(s))));
                        rhs = sp_trim(rhs.b);
                    }
                    if (splen(dst) == 0){
                        if (starts_ret7(s)){
                            kind = 1;
                            pre = ssp_cut(s, 0, 7);
                            rhs = sp_of(ar_str(st->tbl, st->arp, st->are,
                                               ssp_cut(s, 7, (S)splen(s))));
                            rhs = sp_trim(rhs.b);
                        }
                    }
                    if (splen(dst) == 0){
                        if (kind == 0){
                            if (starts_if3(s)){
                                kind = 2;
                                pre = ssp_cut(s, 0, 3);
                                rhs = sp_of(ar_str(st->tbl, st->arp, st->are,
                                                   ssp_cut(s, 3, (S)splen(s))));
                                rhs = sp_trim(rhs.b);
                            }
                        }
                    }
                    if (find_spawn6(rhs) != (S)MISS){
                        rhs = sp_empty();
                    }
                    if (splen(rhs) > 0){
                        if (cfind1(rhs.b, 34) > -1){
                            rhs = sp_empty();
                        }
                    }
                    if (splen(rhs) > 0){
                        S b0 = inl2_callfind(st, rhs);
                        if (b0 > -1){
                            S lidx = nm_lookup_sp(st, st->cnm);
                            if (lidx > -1){
                                idx = (U)lidx;
                                if (idx != ci){
                                    if (ELEM(st->tbl[14], idx) == 1){
                                        fire = 1;
                                        if (st->cnci != (S)ci){
                                            inl2_mkcn(st, ls, ci);
                                            st->cnci = (S)ci;
                                        }
                                        U cps = ELEM(st->tbl[10], idx);
                                        U cb = ELEM(st->tbl[11], idx);
                                        S lp = find_lp(ssp_cut(rhs, b0, (S)splen(rhs))) + b0;
                                        Sp argtxt = ssp_cut(rhs, lp + 1, st->cb1);
                                        U argtxt_s = ar_str(st->tbl, st->arp, st->are, argtxt);
                                        U argl = ar_list(st->tbl, st->arp, st->are, 0);
                                        argl = t2(st->tbl, IN_SPLITARGS, argtxt_s, argl);
                                        U argo = 1;
                                        if (LLEN(argl) != LLEN(cps)) argo = 0;
                                        U ai = 0;
                                        while (ai < LLEN(argl)){
                                            Sp av = sp_trim((const unsigned char*)(void*)ELEM(argl, ai));
                                            if (is_imm(av) == 0){
                                                if (plain_name(av) == 0) argo = 0;
                                            }
                                            ai++;
                                        }
                                        if (argo == 1){
                                            U bok = 0;
                                            U mhit = 0;
                                            if (LLEN(st->okm) > idx){
                                                if (ELEM(st->okb, idx) == cb){
                                                    if (ELEM(st->okm, idx) != 9){
                                                        bok = ELEM(st->okm, idx);
                                                        mhit = 1;
                                                    }
                                                }
                                            }
                                            if (bok == 0){
                                                bok = (U)inl2_body_ok(st, cb, cps);
                                                if (LLEN(st->okm) > idx){
                                                    lput(st->okm, idx, bok);
                                                    lput(st->okb, idx, cb);
                                                }
                                            }
                                            if (bok == 1){
                                                /* second call: cl/ret side
                                                 * effects feed the splice */
                                                (void)inl2_body_ok(st, cb, cps);
                                                Sp ind = sp_cut(lk, 0, (S)nsp);
                                                STACK_SP(zzln4, 'z','z','l','n');
                                                U base = ar_str(st->tbl, st->arp, st->are, zzln4);
                                                U btry = 0;
                                                int bseen = 1;
                                                while (bseen){
                                                    bseen = 0;
                                                    U i2bi = 0;
                                                    while (i2bi < n){
                                                        if (nfind((const unsigned char*)(void*)ELEM(ls, i2bi),
                                                                  (const unsigned char*)(void*)base) > -1) bseen = 1;
                                                        i2bi++;
                                                    }
                                                    i2bi = 0;
                                                    while (i2bi < LLEN(cb)){
                                                        if (nfind((const unsigned char*)(void*)ELEM(cb, i2bi),
                                                                  (const unsigned char*)(void*)base) > -1) bseen = 1;
                                                        i2bi++;
                                                    }
                                                    if (bseen){
                                                        STACK_SP(t1c, 't');
                                                        base = ar_cat(st->tbl, st->arp, st->are, sp_of(base), t1c);
                                                        btry++;
                                                        if (btry > 40) return 0;
                                                    }
                                                }
                                                    st->map_n = 0;
                                                    ai = 0;
                                                    while (ai < LLEN(cps)){
                                                        Sp pn = sp_of(ELEM(cps, ai));
                                                        Sp mt = sp_trim((const unsigned char*)(void*)ELEM(argl, ai));
                                                        if (st->map_n == st->mapf_cap) st->mapf = sparr_grow(st->tbl, st->arp, st->are, st->mapf, &st->mapf_cap);
                                                        if (st->map_n == st->mapt_cap) st->mapt = sparr_grow(st->tbl, st->arp, st->are, st->mapt, &st->mapt_cap);
                                                        st->mapf[st->map_n] = pn;
                                                        st->mapt[st->map_n] = mt;
                                                        st->map_n++;
                                                        ai++;
                                                    }
                                                    U li2 = 0;
                                                    while (li2 < st->cn_n){
                                                        Sp cnm = st->cn[li2];
                                                        if (!in_sp(st->mapf, st->map_n, cnm)){
                                                            STACK_SP(us1, '_');
                                                            U tn = ar_cat(st->tbl, st->arp, st->are, sp_of(base),
                                                                sp_of(ar_cat(st->tbl, st->arp, st->are, us1, cnm)));
                                                            if (st->map_n == st->mapf_cap) st->mapf = sparr_grow(st->tbl, st->arp, st->are, st->mapf, &st->mapf_cap);
                                                            if (st->map_n == st->mapt_cap) st->mapt = sparr_grow(st->tbl, st->arp, st->are, st->mapt, &st->mapt_cap);
                                                            st->mapf[st->map_n] = cnm;
                                                            st->mapt[st->map_n] = sp_of(tn);
                                                            st->map_n++;
                                                        }
                                                        li2++;
                                                    }
                                                U cbl = LLEN(cb);
                                                Sp *gen = 0; U gen_n = 0, gen_cap = 0;
                                                U i2bi = 0;
                                                while (i2bi + 1 < cbl){
                                                    const unsigned char *rl2 = (const unsigned char*)(void*)ELEM(cb, i2bi);
                                                    U sp3 = 0;
                                                    while (PB(rl2, sp3) == 32) sp3++;
                                                    Sp ex2 = sp_empty();
                                                    if (sp3 > 4){
                                                        ex2 = sp_cut(rl2, 4, (S)sp3);
                                                    }
                                                    U rnm = inl2_rename(st, sp_trim(rl2));
                                                    U gl = ar_cat3(st->tbl, st->arp, st->are, ind, ex2, sp_of(rnm));
                                                    sparr_push(st->tbl, st->arp, st->are,
                                                               &gen, &gen_n, &gen_cap, sp_of(gl));
                                                    i2bi++;
                                                }
                                                U rre = inl2_rename(st, st->ret);
                                                U nrhs = rre;
                                                S rhs_len = (S)splen(rhs);
                                                if (b0 > 0){
                                                    STACK_SP(lpc, '(');
                                                    STACK_SP(rpc, ')');
                                                    nrhs = ar_cat4(st->tbl, st->arp, st->are,
                                                        ssp_cut(rhs, 0, b0),
                                                        lpc,
                                                        sp_of(rre),
                                                        rpc);
                                                    nrhs = ar_cat(st->tbl, st->arp, st->are, sp_of(nrhs),
                                                        ssp_cut(rhs, st->cb1 + 1, rhs_len));
                                                } else {
                                                    if (st->cb1 < rhs_len - 1){
                                                        STACK_SP(lpc2, '(');
                                                        STACK_SP(rpc2, ')');
                                                        nrhs = ar_cat4(st->tbl, st->arp, st->are,
                                                            lpc2,
                                                            sp_of(rre),
                                                            rpc2,
                                                            ssp_cut(rhs, st->cb1 + 1, rhs_len));
                                                    }
                                                }
                                                U gl;
                                                STACK_SP(colsp, ':', ' ');
                                                if (kind == 0){
                                                    gl = ar_cat3(st->tbl, st->arp, st->are, ind,
                                                        dst, colsp);
                                                } else {
                                                    gl = ar_str(st->tbl, st->arp, st->are, ind);
                                                    gl = ar_cat(st->tbl, st->arp, st->are, sp_of(gl), pre);
                                                }
                                                gl = ar_cat(st->tbl, st->arp, st->are, sp_of(gl), sp_of(nrhs));
                                                sparr_push(st->tbl, st->arp, st->are,
                                                           &gen, &gen_n, &gen_cap, sp_of(gl));
                                                U nl2 = ar_list(st->tbl, st->arp, st->are, n + gen_n + 4);
                                                U ns2 = ar_list(st->tbl, st->arp, st->are, n + gen_n + 4);
                                                U w = 0;
                                                while (w < k){
                                                    lpush(nl2, ELEM(ls, w));
                                                    lpush(ns2, ELEM(sln, w));
                                                    w++;
                                                }
                                                U kln = ELEM(sln, k);
                                                w = 0;
                                                while (w < gen_n){
                                                    lpush(nl2, (U)(void*)gen[w].b);
                                                    lpush(ns2, kln);
                                                    w++;
                                                }
                                                w = k + 1;
                                                while (w < n){
                                                    lpush(nl2, ELEM(ls, w));
                                                    lpush(ns2, ELEM(sln, w));
                                                    w++;
                                                }
                                                st->out = nl2;
                                                st->sln = ns2;
                                                return 1;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        k++;
    }
    return 0;
}

/* ---- entry: old_inl2_scan(lines, sln, ci, tbl) ---- */
U old_inl2_scan(U lines, U sln, U ci, U tbl){
    St st;
    st.tbl = (U*)(void*)tbl;
    st.arp = st.tbl + 5;
    st.are = st.tbl + 6;
    st.bad = 0;
    st.reads = 0; st.rd_n = 0; st.rd_cap = 0;
    st.cl = 0; st.cl_n = 0; st.cl_cap = 0;
    st.cn = 0; st.cn_n = 0; st.cn_cap = 0;
    st.mapf = 0; st.mapt = 0; st.map_n = 0; st.mapf_cap = 0; st.mapt_cap = 0;
    st.ret = sp_empty();
    st.cnm = sp_empty();
    st.cb1 = -1;
    st.out = 0; st.sln = 0;

    state_build(&st);

    if (st.okm == 0){
        U bodies = st.tbl[11];
        U bn = bodies ? LLEN(bodies) : 0;
        st.okm = ar_list(st.tbl, st.arp, st.are, bn + 4);
        st.okb = ar_list(st.tbl, st.arp, st.are, bn + 4);
        U mi = 0;
        while (mi < bn){
            lput(st.okm, mi, 9);
            lput(st.okb, mi, 0);
            mi++;
        }
        /* the memo lists are pre-sized: elements written above, length
         * published now (a len of 0 disabled every LLEN(okm)>idx check
         * and body_ok re-ran per candidate per round - the self build
         * crawled for minutes) */
        *(U*)(st.okm + 8) = bn;
        *(U*)(st.okb + 8) = bn;
    }
    U cur = lines;
    U cs = sln;
    U ch = 0;
    U pass = 0;
    while (pass < 32){
        if (inl2_one(&st, cur, cs, ci) == 1){
            cur = st.out;
            cs = st.sln;
            ch = 1;
        } else {
            pass = 32;
        }
        pass++;
    }
    state_save(&st);
    if (ch == 1){
        t1(st.tbl, IN_SETOUT, cur);
        t1(st.tbl, IN_SETSLN, cs);
        return 1;
    }
    return 0;
}
