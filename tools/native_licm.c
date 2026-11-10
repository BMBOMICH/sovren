/* Native licm_scan: the loop-hoist pre-pass, C port.
 * 1:1 mirror of the licm family in compilers/shared/cx86_p6.sov:
 * licm_scan (driver: header hunt + <=16 fixpoint of licm_one/licm2_one),
 * licm_one (outer/inner while detection + guard splice), licm_check
 * (region conservatism), licm2_one/licm2_check/licm2_scan/
 * licm2_argreads/licm2_match/licm2_fresh (invariant pure-call hoist),
 * licm_scan_expr/licm_whdr/licm_lhs/licm_in/licm_add/licm_pure/
 * licm_pure2.  strip_span/indent_of/look/cfind1/cut/str_cat/same/
 * plain_name/is_imm are fused inline as (ptr,len) spans; the splice
 * outputs (gl/hl/modl/nl/ns) are real arena strings/lists.
 * Helpers behind the caller-provided lc_tbl (Sovren ABI:
 * rdi,rsi,rdx,rcx,r8,r9,r10; result rax):
 *   1 lc_set_out(v)      (licm_out := v)
 *   2 lc_set_sln(v)      (licm_sln := v)
 *   3 licm_udef(nm)      (interpreted: nm_lookup + task_user peek)
 *   4 _sov_heap_alloc(n)
 * The tbl block doubles as the persistent cell so the fast path pays
 * ZERO interpreted dispatches: slot 0 = count (4), slots 1..4 = the
 * helpers above, slot 5 = arp, slot 6 = are (the bump-arena extent,
 * written by ar_grow), slot 7 = the generation tag, slot 8 = the udef
 * cache base.  The cache owns a DEDICATED allocation (slot 8), NOT a
 * bump-arena region: ar_grow abandons the old chunk on every growth,
 * and a cache living there died with it (32KB re-zero + every udef
 * re-asked through ~5us T_UDEF dispatches per growth - on all.sov the
 * arena churned until the blob cost ~12.5us/function, +8.5ms W-walk0,
 * 7x the interpreted cost).  (v1 additionally paid T_ARBLK/T_GEN
 * dispatches per call.)
 * licm_udef answers are content-cached per call in the persistent arena
 * (generation-tagged slots; load factor kept < 50%, the STAB lesson).
 * Sovren integer comparisons are SIGNED (look/cfind1 answers are -1).
 * No external symbols, no relocations, no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef long long S;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);
typedef U (*F3)(U,U,U);

enum {
 T_SETOUT=1, T_SETSLN=2, T_UDEF=3, T_ALLOC=4
};
/* tbl-as-cell layout (U* slots): 0=count, 1..4=helpers, 5=arp, 6=are,
 * 7=gen, 8=udc cache base (dedicated allocation, survives ar_grow) */

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }

#define MISS ((U)-1)
#define LLEN(x) (*(U*)((x)+8))
#define ELEM(x,i) (*(U*)((x)+16+(U)(i)*8))
#define PB(s,i) (*(const unsigned char*)((s)+(U)(i)))

/* ---- span model: [b, e) ---- */
typedef struct { const unsigned char *b; const unsigned char *e; } Sp;

static inline U splen(Sp s){ return (U)(s.e - s.b); }

/* persistent bump arena (1 MiB chunks) */
#define AR_CHUNK 1048576
static U ar_grow(U *t, U *arp, U *are, U n){
    U want = AR_CHUNK; if (want < n) want = n;
    U p = t1(t, T_ALLOC, want);
    *arp = p; *are = p + want;
    return p;
}
static inline U ar_get(U *t, U *arp, U *are, U n){
    if (*arp + n > *are) ar_grow(t, arp, are, n);
    U p = *arp; *arp = p + n; return p;
}

/* NUL-terminated arena string from span */
static U ar_str(U *t, U *arp, U *are, Sp s){
    U n = splen(s);
    U p = ar_get(t, arp, are, n + 1);
    U i = 0;
    while (i < n){ *(unsigned char*)(p+i) = s.b[i]; i++; }
    *(unsigned char*)(p+n) = 0;
    return p;
}
/* str_cat(a,b) content: fresh NUL arena string a+b */
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
/* arena list with exact capacity (runtime-compatible header) */
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

/* cfind1: first index of ch in NUL-terminated t, else -1 */
static S cfind1(const unsigned char *t, unsigned ch){
    if (!t) return (S)MISS;
    for (U i=0; t[i]; i++) if (t[i]==ch) return (S)i;
    return (S)MISS;
}
/* first occurrence of needle bytes [nb,ne) inside span s, else -1 */
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
static int span_eq(Sp a, Sp b){
    U n = splen(a);
    if (n != splen(b)) return 0;
    U i = 0;
    while (i < n){ if (a.b[i] != b.b[i]) return 0; i++; }
    return 1;
}

/* _sov_trim span: skip {32,9,10,13} at both ends of the NUL string t */
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
/* strip_span(t) as a span */
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
/* indent_of: space=1, tab=4, stop at first other byte */
static U indent_of(const unsigned char *t){
    U w = 0; U i = 0;
    for (;;){
        unsigned c = t[i];
        if (c == 32) w++;
        else if (c == 9) w += 4;
        else return w;
        i++;
    }
}
/* cut(t,a,b) as span with the runtime clamps (t NUL-terminated) */
static Sp sp_cut(const unsigned char *t, S a, S b){
    S n = (S)xstrlen(t);
    if (a < 0) a = 0;
    if (b > n) b = n;
    if (b < a) b = a;
    Sp r; r.b = t + a; r.e = t + b;
    return r;
}
/* span-of-span cut with the same clamps */
static Sp ssp_cut(Sp s, S a, S b){
    S n = (S)splen(s);
    if (a < 0) a = 0;
    if (b > n) b = n;
    if (b < a) b = a;
    Sp r; r.b = s.b + a; r.e = s.b + b;
    return r;
}

/* plain_name: no byte in the bad set (empty ok) */
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

/* ---- per-call state ---- */
typedef struct {
    U *tbl;
    U *arp, *are;               /* pointers into the [arp][are] block */
    int bad;                      /* licm_bad */
    Sp *reads; U rd_n, rd_cap;    /* licm_reads (dedup'd) */
    int f2;                       /* licm2_found */
    Sp text2;                     /* licm2_text */
    S pos2;                       /* licm2_pos */
    S at2;                        /* licm2_at */
    Sp *A2; U a2_n, a2_cap;       /* licm2_A (dedup'd) */
    Sp *r2; U r2_n, r2_cap;       /* licm2_reads (dedup'd) */
    U out, sln;                   /* licm_out / licm_sln of last success */
} St;

static void rd_push(St *st, Sp v){
    U i = 0;
    while (i < st->rd_n){ if (span_eq(st->reads[i], v)) return; i++; }
    if (st->rd_n == st->rd_cap){
        U nc = st->rd_cap ? st->rd_cap * 2 : 32;
        Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc * sizeof(Sp));
        U j = 0;
        while (j < st->rd_n){ nb[j] = st->reads[j]; j++; }
        st->reads = nb; st->rd_cap = nc;
    }
    st->reads[st->rd_n++] = v;
}
static void r2_push(St *st, Sp v){
    U i = 0;
    while (i < st->r2_n){ if (span_eq(st->r2[i], v)) return; i++; }
    if (st->r2_n == st->r2_cap){
        U nc = st->r2_cap ? st->r2_cap * 2 : 32;
        Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc * sizeof(Sp));
        U j = 0;
        while (j < st->r2_n){ nb[j] = st->r2[j]; j++; }
        st->r2 = nb; st->r2_cap = nc;
    }
    st->r2[st->r2_n++] = v;
}
static void a2_push(St *st, Sp v){
    U i = 0;
    while (i < st->a2_n){ if (span_eq(st->A2[i], v)) return; i++; }
    if (st->a2_n == st->a2_cap){
        U nc = st->a2_cap ? st->a2_cap * 2 : 32;
        Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc * sizeof(Sp));
        U j = 0;
        while (j < st->a2_n){ nb[j] = st->A2[j]; j++; }
        st->A2 = nb; st->a2_cap = nc;
    }
    st->A2[st->a2_n++] = v;
}
static int in_sp(Sp *set, U n, Sp v){
    U i = 0;
    while (i < n){ if (span_eq(set[i], v)) return 1; i++; }
    return 0;
}

/* ---- literal matchers (char constants only: no .rodata) ---- */
/* Match span p (length n) against a literal given as char constants.
 * MQ evaluates one position; the whole entry is one conjunction. */
#define MQ(i,ch) (p[i] == (ch))
#define MQ_AT(sp,i,ch) ((sp).b[i] == (ch))

static int eq_peek_i64(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==8 && MQ(0,'p')&&MQ(1,'e')&&MQ(2,'e')&&MQ(3,'k')&&MQ(4,'_')&&MQ(5,'i')&&MQ(6,'6')&&MQ(7,'4'); }
static int eq_peek_byte(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==9 && MQ(0,'p')&&MQ(1,'e')&&MQ(2,'e')&&MQ(3,'k')&&MQ(4,'_')&&MQ(5,'b')&&MQ(6,'y')&&MQ(7,'t')&&MQ(8,'e'); }
static int eq_peek_u8(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==7 && MQ(0,'p')&&MQ(1,'e')&&MQ(2,'e')&&MQ(3,'k')&&MQ(4,'_')&&MQ(5,'u')&&MQ(6,'8'); }
static int eq_peek_i32(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==8 && MQ(0,'p')&&MQ(1,'e')&&MQ(2,'e')&&MQ(3,'k')&&MQ(4,'_')&&MQ(5,'i')&&MQ(6,'3')&&MQ(7,'2'); }
static int eq_f64_add(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==7 && MQ(0,'f')&&MQ(1,'6')&&MQ(2,'4')&&MQ(3,'_')&&MQ(4,'a')&&MQ(5,'d')&&MQ(6,'d'); }
static int eq_f64_mul(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==7 && MQ(0,'f')&&MQ(1,'6')&&MQ(2,'4')&&MQ(3,'_')&&MQ(4,'m')&&MQ(5,'u')&&MQ(6,'l'); }
static int eq_f64_sub(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==7 && MQ(0,'f')&&MQ(1,'6')&&MQ(2,'4')&&MQ(3,'_')&&MQ(4,'s')&&MQ(5,'u')&&MQ(6,'b'); }
static int eq_f64_div(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==7 && MQ(0,'f')&&MQ(1,'6')&&MQ(2,'4')&&MQ(3,'_')&&MQ(4,'d')&&MQ(5,'i')&&MQ(6,'v'); }
static int eq_f64_sqrt(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==8 && MQ(0,'f')&&MQ(1,'6')&&MQ(2,'4')&&MQ(3,'_')&&MQ(4,'s')&&MQ(5,'q')&&MQ(6,'r')&&MQ(7,'t'); }
static int eq_f64_from_i64(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==12 && MQ(0,'f')&&MQ(1,'6')&&MQ(2,'4')&&MQ(3,'_')&&MQ(4,'f')&&MQ(5,'r')&&MQ(6,'o')&&MQ(7,'m')&&MQ(8,'_')&&MQ(9,'i')&&MQ(10,'6')&&MQ(11,'4'); }
static int eq_f64_to_i64(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==10 && MQ(0,'f')&&MQ(1,'6')&&MQ(2,'4')&&MQ(3,'_')&&MQ(4,'t')&&MQ(5,'o')&&MQ(6,'_')&&MQ(7,'i')&&MQ(8,'6')&&MQ(9,'4'); }
static int eq_f64_cmp(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==7 && MQ(0,'f')&&MQ(1,'6')&&MQ(2,'4')&&MQ(3,'_')&&MQ(4,'c')&&MQ(5,'m')&&MQ(6,'p'); }
static int eq_f64_from_frac(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==13 && MQ(0,'f')&&MQ(1,'6')&&MQ(2,'4')&&MQ(3,'_')&&MQ(4,'f')&&MQ(5,'r')&&MQ(6,'o')&&MQ(7,'m')&&MQ(8,'_')&&MQ(9,'f')&&MQ(10,'r')&&MQ(11,'a')&&MQ(12,'c'); }
static int eq__sov_list_get(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==13 && MQ(0,'_')&&MQ(1,'s')&&MQ(2,'o')&&MQ(3,'v')&&MQ(4,'_')&&MQ(5,'l')&&MQ(6,'i')&&MQ(7,'s')&&MQ(8,'t')&&MQ(9,'_')&&MQ(10,'g')&&MQ(11,'e')&&MQ(12,'t'); }
static int eq__sov_list_len(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==13 && MQ(0,'_')&&MQ(1,'s')&&MQ(2,'o')&&MQ(3,'v')&&MQ(4,'_')&&MQ(5,'l')&&MQ(6,'i')&&MQ(7,'s')&&MQ(8,'t')&&MQ(9,'_')&&MQ(10,'l')&&MQ(11,'e')&&MQ(12,'n'); }
static int eq_band(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==4 && MQ(0,'b')&&MQ(1,'a')&&MQ(2,'n')&&MQ(3,'d'); }
static int eq_bor(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==3 && MQ(0,'b')&&MQ(1,'o')&&MQ(2,'r'); }
static int eq_bxor(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==4 && MQ(0,'b')&&MQ(1,'x')&&MQ(2,'o')&&MQ(3,'r'); }
static int eq_shl(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==3 && MQ(0,'s')&&MQ(1,'h')&&MQ(2,'l'); }
static int eq_shr(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==3 && MQ(0,'s')&&MQ(1,'h')&&MQ(2,'r'); }
static int eq_str_find(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==8 && MQ(0,'s')&&MQ(1,'t')&&MQ(2,'r')&&MQ(3,'_')&&MQ(4,'f')&&MQ(5,'i')&&MQ(6,'n')&&MQ(7,'d'); }
static int eq_str_len(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==7 && MQ(0,'s')&&MQ(1,'t')&&MQ(2,'r')&&MQ(3,'_')&&MQ(4,'l')&&MQ(5,'e')&&MQ(6,'n'); }
static int eq_str_eq(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==6 && MQ(0,'s')&&MQ(1,'t')&&MQ(2,'r')&&MQ(3,'_')&&MQ(4,'e')&&MQ(5,'q'); }
static int eq_str_starts(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==10 && MQ(0,'s')&&MQ(1,'t')&&MQ(2,'r')&&MQ(3,'_')&&MQ(4,'s')&&MQ(5,'t')&&MQ(6,'a')&&MQ(7,'r')&&MQ(8,'t')&&MQ(9,'s'); }
static int eq_str_ends(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==8 && MQ(0,'s')&&MQ(1,'t')&&MQ(2,'r')&&MQ(3,'_')&&MQ(4,'e')&&MQ(5,'n')&&MQ(6,'d')&&MQ(7,'s'); }
static int eq__sov_find_text(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==14 && MQ(0,'_')&&MQ(1,'s')&&MQ(2,'o')&&MQ(3,'v')&&MQ(4,'_')&&MQ(5,'f')&&MQ(6,'i')&&MQ(7,'n')&&MQ(8,'d')&&MQ(9,'_')&&MQ(10,'t')&&MQ(11,'e')&&MQ(12,'x')&&MQ(13,'t'); }
static int eq__sov_strlen(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==11 && MQ(0,'_')&&MQ(1,'s')&&MQ(2,'o')&&MQ(3,'v')&&MQ(4,'_')&&MQ(5,'s')&&MQ(6,'t')&&MQ(7,'r')&&MQ(8,'l')&&MQ(9,'e')&&MQ(10,'n'); }
static int eq__sov_str_eq(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==11 && MQ(0,'_')&&MQ(1,'s')&&MQ(2,'o')&&MQ(3,'v')&&MQ(4,'_')&&MQ(5,'s')&&MQ(6,'t')&&MQ(7,'r')&&MQ(8,'_')&&MQ(9,'e')&&MQ(10,'q'); }
static int eq__sov_starts_with(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==16 && MQ(0,'_')&&MQ(1,'s')&&MQ(2,'o')&&MQ(3,'v')&&MQ(4,'_')&&MQ(5,'s')&&MQ(6,'t')&&MQ(7,'a')&&MQ(8,'r')&&MQ(9,'t')&&MQ(10,'s')&&MQ(11,'_')&&MQ(12,'w')&&MQ(13,'i')&&MQ(14,'t')&&MQ(15,'h'); }
static int eq_length(Sp nm){ const unsigned char*p=nm.b; U n=splen(nm);
    return n==6 && MQ(0,'l')&&MQ(1,'e')&&MQ(2,'n')&&MQ(3,'g')&&MQ(4,'t')&&MQ(5,'h'); }
/* ---- udef content cache ----
 * licm_udef(nm) = "nm is a task defined in the user's own source".
 * The answer set is frozen for a whole compile (parse precedes flor_range),
 * so answers are cached by name content, tagged with a compile generation
 * fetched through the table (lc_gen, bumped once per compile).
 * Cache block (persistent arena):
 *   [0]=magic [8]=gen [16]=nslots [24]=used [32]=used_gen
 *   slots at +64: {gen, hash, len, ans, bytes[3]} = 32 B, linear probe.
 * A slot whose gen != current is free real estate (overwrite on insert).
 * Load factor is kept < 50% per generation (the STAB lesson). */
#define UDC_MAGIC 0x4c49434d43444243ULL
#define UDC_SLOTS 1024

static U udc_block(St *st){
    U base = st->tbl[8];
    if (base == 0 || *(U*)(base) != UDC_MAGIC){
        base = t1(st->tbl, T_ALLOC, 64 + UDC_SLOTS * 32);
        U q = 0;
        while (q < 64 + UDC_SLOTS*32){ *(unsigned char*)(base+q) = 0; q++; }
        *(U*)(base) = UDC_MAGIC;
        st->tbl[8] = base;
        /* gen filled by caller-side cache_gen() */
    }
    return base;
}
/* returns 1 when the generation changed since the last look (resets used) */
static int udc_gen_check(U base, U gen){
    if (*(U*)(base+8) != gen){
        *(U*)(base+8) = gen;
        *(U*)(base+24) = 0;
        *(U*)(base+32) = gen;
        return 1;
    }
    if (*(U*)(base+32) != gen){
        *(U*)(base+32) = gen;
        *(U*)(base+24) = 0;
    }
    return 0;
}
static int call_udef(St *st, Sp nm, U base, U gen){
    U n = splen(nm);
    if (n == 0 || n > 24){
        U s = ar_str(st->tbl, st->arp, st->are, nm);
        return t1(st->tbl, T_UDEF, s) == 1;
    }
    U h = 1469598103934665603ULL;
    U i = 0;
    while (i < n){ h ^= nm.b[i]; h *= 1099511628211ULL; i++; }
    U mask = UDC_SLOTS - 1;
    U idx = h & mask;
    U tries = 0;
    while (tries < UDC_SLOTS){
        U sl = base + 64 + idx * 32;
        if (*(U*)(sl) == gen){
            if (*(U*)(sl+8) == h && *(U*)(sl+16) == n){
                U k2 = 0;
                while (k2 < n){
                    if (*(unsigned char*)(sl+32+k2) != nm.b[k2]) break;
                    k2++;
                }
                if (k2 == n) return *(U*)(sl+24) == 1;
            }
        } else {
            /* stale or never-used slot: miss, insert here */
            U s2 = ar_str(st->tbl, st->arp, st->are, nm);
            U ans = t1(st->tbl, T_UDEF, s2) == 1;
            if (*(U*)(base+24) * 2 < UDC_SLOTS){
                *(U*)(sl) = gen; *(U*)(sl+8) = h; *(U*)(sl+16) = n; *(U*)(sl+24) = ans;
                U k2 = 0;
                while (k2 < n){ *(unsigned char*)(sl+32+k2) = nm.b[k2]; k2++; }
                *(U*)(base+24) = *(U*)(base+24) + 1;
            }
            return ans;
        }
        idx = (idx + 1) & mask;
        tries++;
    }
    U s3 = ar_str(st->tbl, st->arp, st->are, nm);
    return t1(st->tbl, T_UDEF, s3) == 1;
}

static int licm_pure(St *st, Sp nm, U base, U gen){
    if (call_udef(st, nm, base, gen)) return 0;
    if (eq_peek_i64(nm)) return 1;
    if (eq_peek_byte(nm)) return 1;
    if (eq_peek_u8(nm)) return 1;
    if (eq_peek_i32(nm)) return 1;
    if (eq_f64_add(nm)) return 1;
    if (eq_f64_mul(nm)) return 1;
    if (eq_f64_sub(nm)) return 1;
    if (eq_f64_div(nm)) return 1;
    if (eq_f64_sqrt(nm)) return 1;
    if (eq_f64_from_i64(nm)) return 1;
    if (eq_f64_to_i64(nm)) return 1;
    if (eq_f64_cmp(nm)) return 1;
    if (eq_f64_from_frac(nm)) return 1;
    if (eq__sov_list_get(nm)) return 1;
    if (eq__sov_list_len(nm)) return 1;
    if (eq_band(nm)) return 1;
    if (eq_bor(nm)) return 1;
    if (eq_bxor(nm)) return 1;
    if (eq_shl(nm)) return 1;
    if (eq_shr(nm)) return 1;
    return 0;
}
static int licm_pure2(St *st, Sp nm, U base, U gen){
    if (licm_pure(st, nm, base, gen)) return 1;
    /* interpreted p6 licm_pure2: a user-defined task is NOT hoistable
     * (conservative: effects unknown).  This was transcribed inverted
     * (return 1) and the diff harness transcription shared the inversion,
     * so both sides agreed user-defined callees were hoistable and the
     * 1500-case differential passed while the real compiler diverged on
     * the self source (fn sg_pad-style bodies: pure nested argument
     * calls under user-defined outer callees). */
    if (call_udef(st, nm, base, gen)) return 0;
    if (eq_str_find(nm)) return 1;
    if (eq_str_len(nm)) return 1;
    if (eq_str_eq(nm)) return 1;
    if (eq_str_starts(nm)) return 1;
    if (eq_str_ends(nm)) return 1;
    if (eq__sov_find_text(nm)) return 1;
    if (eq__sov_strlen(nm)) return 1;
    if (eq__sov_str_eq(nm)) return 1;
    if (eq__sov_starts_with(nm)) return 1;
    if (eq_length(nm)) return 1;
    return 0;
}

/* ---- scanners ---- */
static int idc(unsigned c){
    return (c > 64 && c < 91) || (c > 96 && c < 123) || c == 95;
}
static int idc_ext(unsigned c){
    return idc(c) || (c > 47 && c < 58);
}
static S cfind1_sp(Sp s, unsigned ch){
    U n = splen(s);
    U i = 0;
    while (i < n){
        if (s.b[i] == ch) return (S)i;
        i++;
    }
    return (S)MISS;
}

/* licm_scan_expr: dedup'd identifier reads into st->reads;
 * st->bad on any non-whitelisted call or string literal. */
static void licm_scan_expr(St *st, Sp e, U base, U gen){
    U n = splen(e);
    U i = 0;
    while (i < n){
        unsigned b = e.b[i];
        if (b == 34){ st->bad = 1; return; }
        if (idc(b)){
            U j = i + 1;
            while (j < n && idc_ext(e.b[j])) j++;
            Sp nm; nm.b = e.b + i; nm.e = e.b + j;
            if (j < n){
                if (e.b[j] == 40){
                    if (!licm_pure(st, nm, base, gen)){ st->bad = 1; return; }
                    i = j;
                } else {
                    rd_push(st, nm);
                    i = j;
                }
            } else {
                rd_push(st, nm);
                i = j;
            }
        } else {
            i++;
        }
    }
}

/* licm2_argreads: dedup'd identifier reads into st->r2 (quote-aware) */
static void licm2_argreads(St *st, Sp e, U base, U gen){
    U n = splen(e);
    U i = 0;
    while (i < n){
        unsigned b = e.b[i];
        if (b == 34){
            i++;
            int dn = 0;
            while (dn == 0){
                if (i >= n) dn = 1;
                else {
                    unsigned c = e.b[i];
                    if (c == 92) i += 2;
                    else if (c == 34){ i++; dn = 1; }
                    else i++;
                }
            }
        } else if (idc(b)){
            U j = i + 1;
            while (j < n && idc_ext(e.b[j])) j++;
            Sp nm; nm.b = e.b + i; nm.e = e.b + j;
            if (j < n){
                if (e.b[j] == 40){
                    if (!licm_pure2(st, nm, base, gen)){ st->bad = 1; return; }
                    i = j;
                } else {
                    r2_push(st, nm);
                    i = j;
                }
            } else {
                r2_push(st, nm);
                i = j;
            }
        } else {
            i++;
        }
    }
}

/* licm2_match: index of the close paren matching the '(' at p, else -1 */
static S licm2_match(Sp e, U p){
    U n = splen(e);
    U d = 0;
    U i = p;
    while (i < n){
        unsigned b = e.b[i];
        if (b == 34){
            i++;
            int dn = 0;
            while (dn == 0){
                if (i >= n) dn = 1;
                else {
                    unsigned c = e.b[i];
                    if (c == 92) i += 2;
                    else if (c == 34){ i++; dn = 1; }
                    else i++;
                }
            }
        } else if (b == 40){
            d++;
            i++;
        } else if (b == 41){
            d--;
            if (d == 0) return (S)i;
            i++;
        } else {
            i++;
        }
    }
    return (S)MISS;
}

/* licm2_scan: record the first pure call whose subtree reads avoid A2 */
static void licm2_scan(St *st, Sp e, U base, U gen){
    U n = splen(e);
    U i = 0;
    while (i < n){
        unsigned b = e.b[i];
        if (b == 34){
            i++;
            int dn = 0;
            while (dn == 0){
                if (i >= n) dn = 1;
                else {
                    unsigned c = e.b[i];
                    if (c == 92) i += 2;
                    else if (c == 34){ i++; dn = 1; }
                    else i++;
                }
            }
        } else if (idc(b)){
            U j = i + 1;
            while (j < n && idc_ext(e.b[j])) j++;
            Sp nm; nm.b = e.b + i; nm.e = e.b + j;
            if (j < n){
                if (e.b[j] == 40){
                    if (!licm_pure2(st, nm, base, gen)){ st->bad = 1; return; }
                    if (st->f2 == 0){
                        S m = licm2_match(e, j);
                        if (m != (S)MISS){
                            st->r2_n = 0;
                            Sp args; args.b = e.b + (j+1); args.e = e.b + m;
                            licm2_argreads(st, args, base, gen);
                            if (st->bad) return;
                            int bad2 = 0;
                            U q = 0;
                            while (q < st->r2_n){
                                if (in_sp(st->A2, st->a2_n, st->r2[q])) bad2 = 1;
                                q++;
                            }
                            if (bad2 == 0){
                                st->f2 = 1;
                                st->pos2 = (S)i;
                                st->text2.b = e.b + i;
                                st->text2.e = e.b + (m + 1);
                            }
                        }
                    }
                    i = j;
                } else {
                    i = j;
                }
            } else {
                i = j;
            }
        } else {
            i++;
        }
    }
}

/* licm_lhs: stripped assignment LHS name span, or empty */
static Sp licm_lhs(Sp s){
    Sp empty; empty.b = s.b; empty.e = s.b;
    S p = cfind1_sp(s, 58);
    if (p < 1) return empty;
    /* interpreted reads the NUL past the trimmed copy's end; a span end
     * must behave exactly like that NUL */
    unsigned nxt = (p + 1 < (S)splen(s)) ? s.b[p+1] : 0;
    if (nxt != 32) return empty;
    Sp nm = ssp_cut(s, 0, p);
    if (!plain_name(nm)) return empty;
    if (is_imm(nm)) return empty;
    return nm;
}

/* ---- licm_whdr: condition offset when span is a loop header ---- */
static S licm_whdr(Sp sk){
    U n = splen(sk);
    if (n >= 11 && MQ_AT(sk,0,'a')&&MQ_AT(sk,1,'s')&&MQ_AT(sk,2,' ')&&MQ_AT(sk,3,'l')&&
        MQ_AT(sk,4,'o')&&MQ_AT(sk,5,'n')&&MQ_AT(sk,6,'g')&&MQ_AT(sk,7,' ')&&
        MQ_AT(sk,8,'a')&&MQ_AT(sk,9,'s')&&MQ_AT(sk,10,' ')) return 11;
    if (n >= 6 && MQ_AT(sk,0,'w')&&MQ_AT(sk,1,'h')&&MQ_AT(sk,2,'i')&&MQ_AT(sk,3,'l')&&
        MQ_AT(sk,4,'e')&&MQ_AT(sk,5,' ')) return 6;
    if (n >= 9 && MQ_AT(sk,0,'d')&&MQ_AT(sk,1,'o')&&MQ_AT(sk,2,' ')&&MQ_AT(sk,3,'w')&&
        MQ_AT(sk,4,'h')&&MQ_AT(sk,5,'i')&&MQ_AT(sk,6,'l')&&MQ_AT(sk,7,'e')&&
        MQ_AT(sk,8,' ')) return 9;
    return 0;
}

/* ---- licm_check: region conservatism ---- */
static int licm_check(St *st, U ls, S k, Sp ocond, S h, S coff, S e, S b1,
                      U base, U gen){
    S lbi = (S)indent_of((const unsigned char*)(void*)ELEM(ls, (U)(k+1)));
    st->bad = 0;
    Sp *pre_vars = 0; U pv_n = 0, pv_cap = 0;
    Sp *ina = 0; U in_n = 0, in_cap = 0;
    Sp *posta = 0; U po_n = 0, po_cap = 0;
    Sp *hlhs = 0; U hh_n = 0, hh_cap = 0;
    Sp *hexpr = 0; U hx_n = 0, hx_cap = 0;
    /* ocond: no calls at all */
    if (cfind1_sp(ocond, 40) != (S)MISS) return 0;
    st->rd_n = 0;
    licm_scan_expr(st, ocond, base, gen);
    U oreads_n = st->rd_n;
    Sp *oreads = 0;
    if (oreads_n){
        oreads = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, oreads_n * sizeof(Sp));
        U q = 0;
        while (q < oreads_n){ oreads[q] = st->reads[q]; q++; }
    }
    if (st->bad) return 0;
    /* pass 1a: pre region [k+1, h) */
    S i = k + 1;
    while (i < h){
        const unsigned char *li_t = (const unsigned char*)(void*)ELEM(ls, (U)i);
        Sp s = sp_strip_span(li_t);
        if (splen(s) == 0) return 0;
        if (s.b[0] == 35) return 0;
        if ((S)indent_of(li_t) != lbi) return 0;
        Sp nm = licm_lhs(s);
        if (splen(nm) == 0) return 0;
        if (!in_sp(pre_vars, pv_n, nm)){
            if (pv_n == pv_cap){
                U nc = pv_cap ? pv_cap*2 : 16;
                Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc*sizeof(Sp));
                U q=0; while (q<pv_n){nb[q]=pre_vars[q];q++;} pre_vars=nb; pv_cap=nc;
            }
            pre_vars[pv_n++] = nm;
        }
        if (hh_n == hh_cap){
            U nc = hh_cap ? hh_cap*2 : 16;
            Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc*sizeof(Sp));
            U q=0; while (q<hh_n){nb[q]=hlhs[q];q++;} hlhs=nb; hh_cap=nc;
        }
        hlhs[hh_n++] = nm;
        if (hx_n == hx_cap){
            U nc = hx_cap ? hx_cap*2 : 16;
            Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc*sizeof(Sp));
            U q=0; while (q<hx_n){nb[q]=hexpr[q];q++;} hexpr=nb; hx_cap=nc;
        }
        hexpr[hx_n++] = ssp_cut(s, cfind1_sp(s, 58) + 2, (S)splen(s));
        i++;
    }
    Sp sh = sp_strip_span((const unsigned char*)(void*)ELEM(ls, (U)h));
    Sp icond = ssp_cut(sh, coff, (S)splen(sh));
    S ii = 0;
    if (h + 1 < e) ii = (S)indent_of((const unsigned char*)(void*)ELEM(ls, (U)(h+1)));
    /* pass 1b: inner region [h+1, e) */
    i = h + 1;
    while (i < e){
        const unsigned char *li_t = (const unsigned char*)(void*)ELEM(ls, (U)i);
        Sp s = sp_strip_span(li_t);
        if (splen(s) == 0) return 0;
        if (s.b[0] == 35) return 0;
        if ((S)indent_of(li_t) != ii) return 0;
        Sp nm = licm_lhs(s);
        if (splen(nm) == 0) return 0;
        if (!in_sp(ina, in_n, nm)){
            if (in_n == in_cap){
                U nc = in_cap ? in_cap*2 : 16;
                Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc*sizeof(Sp));
                U q=0; while (q<in_n){nb[q]=ina[q];q++;} ina=nb; in_cap=nc;
            }
            ina[in_n++] = nm;
        }
        i++;
    }
    /* post region [e, b1) */
    st->rd_n = 0;
    i = e;
    while (i < b1){
        const unsigned char *li_t = (const unsigned char*)(void*)ELEM(ls, (U)i);
        Sp s = sp_strip_span(li_t);
        if (splen(s) == 0) return 0;
        if (s.b[0] == 35) return 0;
        if ((S)indent_of(li_t) != lbi) return 0;
        Sp nm = licm_lhs(s);
        if (splen(nm) == 0) return 0;
        if (!in_sp(posta, po_n, nm)){
            if (po_n == po_cap){
                U nc = po_cap ? po_cap*2 : 16;
                Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc*sizeof(Sp));
                U q=0; while (q<po_n){nb[q]=posta[q];q++;} posta=nb; po_cap=nc;
            }
            posta[po_n++] = nm;
        }
        licm_scan_expr(st, ssp_cut(s, cfind1_sp(s, 58) + 2, (S)splen(s)), base, gen);
        if (st->bad) return 0;
        i++;
    }
    /* every inner-assigned name re-initialized in pre */
    U q2 = 0;
    while (q2 < in_n){
        if (!in_sp(pre_vars, pv_n, ina[q2])) return 0;
        q2++;
    }
    /* post must not assign any hoisted-region name */
    q2 = 0;
    while (q2 < po_n){
        if (in_sp(pre_vars, pv_n, posta[q2])) return 0;
        q2++;
    }
    /* outer cond must not read any hoisted-region name */
    q2 = 0;
    while (q2 < oreads_n){
        if (in_sp(pre_vars, pv_n, oreads[q2])) return 0;
        q2++;
    }
    /* pass 2: ordered reads in pre */
    Sp *defd = 0; U df_n = 0, df_cap = 0;
    st->rd_n = 0;
    q2 = 0;
    while (q2 < hx_n){
        U b4 = st->rd_n;
        licm_scan_expr(st, hexpr[q2], base, gen);
        if (st->bad) return 0;
        U j2 = b4;
        while (j2 < st->rd_n){
            Sp nm = st->reads[j2];
            if (in_sp(posta, po_n, nm)) return 0;
            if (in_sp(pre_vars, pv_n, nm)){
                if (!in_sp(defd, df_n, nm)) return 0;
            }
            j2++;
        }
        if (!in_sp(defd, df_n, hlhs[q2])){
            if (df_n == df_cap){
                U nc = df_cap ? df_cap*2 : 16;
                Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc*sizeof(Sp));
                U q=0; while (q<df_n){nb[q]=defd[q];q++;} defd=nb; df_cap=nc;
            }
            defd[df_n++] = hlhs[q2];
        }
        q2++;
    }
    /* inner cond + body reads */
    licm_scan_expr(st, icond, base, gen);
    if (st->bad) return 0;
    i = h + 1;
    while (i < e){
        Sp s = sp_strip_span((const unsigned char*)(void*)ELEM(ls, (U)i));
        licm_scan_expr(st, ssp_cut(s, cfind1_sp(s, 58) + 2, (S)splen(s)), base, gen);
        if (st->bad) return 0;
        i++;
    }
    q2 = 0;
    while (q2 < st->rd_n){
        if (in_sp(posta, po_n, st->reads[q2])) return 0;
        q2++;
    }
    return 1;
}

/* ---- licm_one ---- */
static int licm_one(St *st, U ls, U sln, U base, U gen){
    U n = LLEN(ls);
    S k = 0;
    while (k < (S)n){
        const unsigned char *lk = (const unsigned char*)(void*)ELEM(ls, (U)k);
        U spd = 0;
        unsigned fb = PB(lk, 0);
        while (fb == 32){ spd++; fb = PB(lk, spd); }
        S wok = 0;
        if (fb == 97 || fb == 119 || fb == 100)
            wok = licm_whdr(sp_strip_span(lk));
        if (wok > 0){
            Sp sk = sp_strip_span(lk);
            Sp ocond = ssp_cut(sk, wok, (S)splen(sk));
            S oi = (S)indent_of(lk);
            S b1 = k + 1;
            while (b1 < (S)n &&
                   (S)indent_of((const unsigned char*)(void*)ELEM(ls, (U)b1)) > oi)
                b1++;
            if (b1 > k + 2){
                S lbi = (S)indent_of((const unsigned char*)(void*)ELEM(ls, (U)(k+1)));
                S h = -1;
                S coff = 0;
                S j = k + 1;
                while (j < b1){
                    const unsigned char *lj = (const unsigned char*)(void*)ELEM(ls, (U)j);
                    if ((S)indent_of(lj) == lbi){
                        unsigned fb2 = PB(lj, (U)lbi);
                        S w = 0;
                        if (fb2 == 97 || fb2 == 119 || fb2 == 100)
                            w = licm_whdr(sp_strip_span(lj));
                        if (w > 0){
                            h = j;
                            coff = w;
                            j = b1;
                        }
                    }
                    j++;
                }
                if (h > k + 1){
                    S e = h + 1;
                    while (e < b1 &&
                           (S)indent_of((const unsigned char*)(void*)ELEM(ls, (U)e)) > lbi)
                        e++;
                    int good = 0;
                    if (e > h + 1 && e < b1)
                        good = licm_check(st, ls, k, ocond, h, coff, e, b1, base, gen);
                    if (good == 1){
                        /* splice: [0..k) + guard-if + [k+1..e) + [k] + [e..n) */
                        U cap = (U)((S)n + 1);
                        U nl = ar_list(st->tbl, st->arp, st->are, cap);
                        U ns = ar_list(st->tbl, st->arp, st->are, cap);
                        U gl = 0;
                        {
                            U i2 = 0;
                            Sp gsp; gsp.b = 0; gsp.e = 0;
                            /* build " "*oi + "if " + ocond */
                            U tot = (U)oi + 3 + splen(ocond);
                            U p2 = ar_get(st->tbl, st->arp, st->are, tot + 1);
                            while (i2 < (U)oi){ *(unsigned char*)(p2+i2) = 32; i2++; }
                            *(unsigned char*)(p2+i2) = 'i'; i2++;
                            *(unsigned char*)(p2+i2) = 'f'; i2++;
                            *(unsigned char*)(p2+i2) = ' '; i2++;
                            U q3 = 0;
                            while (q3 < splen(ocond)){
                                *(unsigned char*)(p2+i2+q3) = ocond.b[q3]; q3++;
                            }
                            *(unsigned char*)(p2+tot) = 0;
                            gl = p2;
                        }
                        U i3 = 0;
                        while (i3 < (U)k){
                            lpush(nl, ELEM(ls, i3));
                            lpush(ns, ELEM(sln, i3));
                            i3++;
                        }
                        lpush(nl, gl);
                        lpush(ns, ELEM(sln, (U)k));
                        i3 = (U)(k + 1);
                        while (i3 < (U)e){
                            lpush(nl, ELEM(ls, i3));
                            lpush(ns, ELEM(sln, i3));
                            i3++;
                        }
                        lpush(nl, ELEM(ls, (U)k));
                        lpush(ns, ELEM(sln, (U)k));
                        i3 = (U)e;
                        while (i3 < n){
                            lpush(nl, ELEM(ls, i3));
                            lpush(ns, ELEM(sln, i3));
                            i3++;
                        }
                        st->out = nl;
                        st->sln = ns;
                        return 1;
                    }
                }
            }
        }
        k++;
    }
    return 0;
}

/* ---- licm2_check ---- */
static int licm2_check(St *st, U ls, S k, Sp ocond, S b1, U base, U gen,
                       S *at_out){
    S lbi = (S)indent_of((const unsigned char*)(void*)ELEM(ls, (U)(k+1)));
    st->bad = 0;
    if (cfind1_sp(ocond, 40) != (S)MISS) return 0;
    st->a2_n = 0;
    U *hidx = 0; U hi_n = 0, hi_cap = 0;
    Sp *hrhs = 0; U hr_n = 0, hr_cap = 0;
    S i = k + 1;
    while (i < b1){
        const unsigned char *li_t = (const unsigned char*)(void*)ELEM(ls, (U)i);
        Sp s = sp_strip_span(li_t);
        if (splen(s) == 0) return 0;
        if (s.b[0] == 35) return 0;
        if ((S)indent_of(li_t) != lbi) return 0;
        U spc = 0;
        while (PB(li_t, spc) == 32) spc++;
        if (PB(li_t, spc) == 9) return 0;
        Sp nm = licm_lhs(s);
        if (splen(nm) == 0) return 0;
        a2_push(st, nm);
        if (hi_n == hi_cap){
            U nc = hi_cap ? hi_cap*2 : 16;
            U *nb = (U*)(void*)ar_get(st->tbl, st->arp, st->are, nc*sizeof(U));
            U q=0; while (q<hi_n){nb[q]=hidx[q];q++;} hidx=nb; hi_cap=nc;
        }
        hidx[hi_n++] = (U)i;
        if (hr_n == hr_cap){
            U nc = hr_cap ? hr_cap*2 : 16;
            Sp *nb = (Sp*)(void*)ar_get(st->tbl, st->arp, st->are, nc*sizeof(Sp));
            U q=0; while (q<hr_n){nb[q]=hrhs[q];q++;} hrhs=nb; hr_cap=nc;
        }
        hrhs[hr_n++] = ssp_cut(s, cfind1_sp(s, 58) + 2, (S)splen(s));
        i++;
    }
    st->f2 = 0;
    st->at2 = -1;
    U i4 = 0;
    while (i4 < hr_n){
        licm2_scan(st, hrhs[i4], base, gen);
        if (st->bad) return 0;
        if (st->f2 == 1){
            if (st->at2 < 0)
                st->at2 = (S)hidx[i4];
        }
        i4++;
    }
    if (st->f2 == 0) return 0;
    *at_out = st->at2;
    return 1;
}

/* ---- licm2_fresh: a temp name unused by any line ---- */
static U licm2_fresh(St *st, U ls){
    /* "licm_t" then "licm_t"++"t"... up to 40 tries; returns arena string
     * or 0 (interpreted returns ""). */
    U n = LLEN(ls);
    U tmplen = 6;
    U tmp = 0;
    U tries = 0;
    while (tries < 40){
        /* build the candidate: 'licm_t' + tries*'t' */
        U p2 = ar_get(st->tbl, st->arp, st->are, tmplen + 1);
        *(unsigned char*)(p2+0)='l'; *(unsigned char*)(p2+1)='i';
        *(unsigned char*)(p2+2)='c'; *(unsigned char*)(p2+3)='m';
        *(unsigned char*)(p2+4)='_'; *(unsigned char*)(p2+5)='t';
        U q4 = 6;
        while (q4 < tmplen){ *(unsigned char*)(p2+q4) = 't'; q4++; }
        *(unsigned char*)(p2+tmplen) = 0;
        tmp = p2;
        int seen = 0;
        U i5 = 0;
        while (i5 < n){
            if (seen == 0){
                const unsigned char *ln = (const unsigned char*)(void*)ELEM(ls, i5);
                if (cfind1(ln, 108) != (S)MISS){
                    /* look(line, tmp): find tmp's bytes in the NUL line */
                    U ll = xstrlen(ln);
                    U tl = tmplen;
                    U pos = 0;
                    while (pos + tl <= ll){
                        U q5 = 0;
                        while (q5 < tl && ln[pos+q5] == ((const unsigned char*)(void*)tmp)[q5]) q5++;
                        if (q5 == tl){ seen = 1; break; }
                        pos++;
                    }
                } else {
                    /* cfind1 miss means no 'l' at all: tmp contains 'l',
                     * so look must miss too; but mirror look() exactly:
                     * _sov_find_text would also miss. keep seen=0 */
                }
            }
            if (seen) break;
            i5++;
        }
        if (seen == 0) return tmp;
        tmplen++;
        tries++;
    }
    return 0;
}

/* ---- licm2_one ---- */
static int licm2_one(St *st, U ls, U sln, U base, U gen){
    U n = LLEN(ls);
    S k = 0;
    while (k < (S)n){
        const unsigned char *lk = (const unsigned char*)(void*)ELEM(ls, (U)k);
        U spd = 0;
        unsigned fb = PB(lk, 0);
        while (fb == 32){ spd++; fb = PB(lk, spd); }
        S wok = 0;
        if (fb == 97 || fb == 119 || fb == 100)
            wok = licm_whdr(sp_strip_span(lk));
        if (wok > 0){
            Sp sk = sp_strip_span(lk);
            Sp ocond = ssp_cut(sk, wok, (S)splen(sk));
            S oi = (S)indent_of(lk);
            S b1 = k + 1;
            while (b1 < (S)n &&
                   (S)indent_of((const unsigned char*)(void*)ELEM(ls, (U)b1)) > oi)
                b1++;
            if (b1 > k + 1){
                S at = -1;
                if (licm2_check(st, ls, k, ocond, b1, base, gen, &at) == 1){
                    U tmp = licm2_fresh(st, ls);
                    if (tmp != 0){
                        S lbi = (S)indent_of((const unsigned char*)(void*)ELEM(ls, (U)(k+1)));
                        /* gl = " "*oi + "if " + ocond */
                        U gl = 0;
                        {
                            U tot = (U)oi + 3 + splen(ocond);
                            U p2 = ar_get(st->tbl, st->arp, st->are, tot + 1);
                            U i6 = 0;
                            while (i6 < (U)oi){ *(unsigned char*)(p2+i6) = 32; i6++; }
                            *(unsigned char*)(p2+i6)='i'; i6++;
                            *(unsigned char*)(p2+i6)='f'; i6++;
                            *(unsigned char*)(p2+i6)=' '; i6++;
                            U q6 = 0;
                            while (q6 < splen(ocond)){
                                *(unsigned char*)(p2+i6+q6) = ocond.b[q6]; q6++;
                            }
                            *(unsigned char*)(p2+tot) = 0;
                            gl = p2;
                        }
                        /* hl = " "*lbi + tmp + ": " + licm2_text */
                        U tl = xstrlen((const unsigned char*)(void*)tmp);
                        Sp tx = st->text2;
                        U hl = 0;
                        {
                            U tot = (U)lbi + tl + 2 + splen(tx);
                            U p2 = ar_get(st->tbl, st->arp, st->are, tot + 1);
                            U i7 = 0;
                            while (i7 < (U)lbi){ *(unsigned char*)(p2+i7) = 32; i7++; }
                            U q7 = 0;
                            while (q7 < tl){ *(unsigned char*)(p2+i7+q7) = ((const unsigned char*)(void*)tmp)[q7]; q7++; }
                            i7 += tl;
                            *(unsigned char*)(p2+i7)=':'; i7++;
                            *(unsigned char*)(p2+i7)=' '; i7++;
                            q7 = 0;
                            while (q7 < splen(tx)){ *(unsigned char*)(p2+i7+q7) = tx.b[q7]; q7++; }
                            *(unsigned char*)(p2+tot) = 0;
                            hl = p2;
                        }
                        /* rewrite the containing statement positionally */
                        const unsigned char *orig = (const unsigned char*)(void*)ELEM(ls, (U)at);
                        U px = 0;
                        while (PB(orig, px) == 32) px++;
                        Sp s = sp_trim(orig);
                        S cp = cfind1_sp(s, 58) + 2 + st->pos2;
                        Sp tx2 = st->text2;
                        Sp ns1 = {0,0};
                        {
                            Sp left = ssp_cut(s, 0, cp);
                            Sp right = ssp_cut(s, cp + (S)splen(tx2), (S)splen(s));
                            Sp tmpsp; tmpsp.b = (const unsigned char*)(void*)tmp;
                            tmpsp.e = tmpsp.b + tl;
                            ns1.b = 0; ns1.e = 0;
                            U tot = splen(left) + tl + splen(right);
                            U p3 = ar_get(st->tbl, st->arp, st->are, tot + 1);
                            U q8 = 0;
                            while (q8 < splen(left)){ *(unsigned char*)(p3+q8) = left.b[q8]; q8++; }
                            U r8 = 0;
                            while (r8 < tl){ *(unsigned char*)(p3+q8+r8) = tmpsp.b[r8]; r8++; }
                            q8 += tl;
                            r8 = 0;
                            while (r8 < splen(right)){ *(unsigned char*)(p3+q8+r8) = right.b[r8]; r8++; }
                            *(unsigned char*)(p3+tot) = 0;
                            ns1.b = (const unsigned char*)(void*)p3;
                            ns1.e = ns1.b + tot;
                        }
                        Sp left2 = sp_cut(orig, 0, (S)px);
                        U modl = 0;
                        {
                            U tot = splen(left2) + splen(ns1);
                            U p3 = ar_get(st->tbl, st->arp, st->are, tot + 1);
                            U q9 = 0;
                            while (q9 < splen(left2)){ *(unsigned char*)(p3+q9) = left2.b[q9]; q9++; }
                            U r9 = 0;
                            while (r9 < splen(ns1)){ *(unsigned char*)(p3+q9+r9) = ns1.b[r9]; r9++; }
                            *(unsigned char*)(p3+tot) = 0;
                            modl = p3;
                        }
                        /* splice: [0..k) + gl + hl + [k..n) with at -> modl */
                        U cap = n + 2;
                        U nl = ar_list(st->tbl, st->arp, st->are, cap);
                        U ns = ar_list(st->tbl, st->arp, st->are, cap);
                        U i8 = 0;
                        while (i8 < (U)k){
                            lpush(nl, ELEM(ls, i8));
                            lpush(ns, ELEM(sln, i8));
                            i8++;
                        }
                        lpush(nl, gl);
                        lpush(ns, ELEM(sln, (U)k));
                        lpush(nl, hl);
                        lpush(ns, ELEM(sln, (U)at));
                        i8 = (U)k;
                        while (i8 < n){
                            if ((S)i8 == at) lpush(nl, modl);
                            else lpush(nl, ELEM(ls, i8));
                            lpush(ns, ELEM(sln, i8));
                            i8++;
                        }
                        st->out = nl;
                        st->sln = ns;
                        return 1;
                    }
                }
            }
        }
        k++;
    }
    return 0;
}

/* ---- entry: _sov_licm_scan(lines, sln, tbl) ---- */
U _sov_licm_scan(U lines, U sln, U tbl){
    St st;
    st.tbl = (U*)(void*)tbl;
    if (sln == 0) return 0;
    st.arp = st.tbl + 5;
    st.are = st.tbl + 6;
    st.bad = 0;
    st.reads = 0; st.rd_n = 0; st.rd_cap = 0;
    st.f2 = 0; st.text2.b = 0; st.text2.e = 0; st.pos2 = 0; st.at2 = -1;
    st.A2 = 0; st.a2_n = 0; st.a2_cap = 0;
    st.r2 = 0; st.r2_n = 0; st.r2_cap = 0;
    st.out = 0; st.sln = 0;

    U base = udc_block(&st);
    U gen = st.tbl[7];
    udc_gen_check(base, gen);

    U n = LLEN(lines);
    /* header hunt: first non-space byte in {a,w,d} + a loop header */
    int lh_any = 0;
    U kk = 0;
    while (kk < n){
        if (lh_any == 0){
            const unsigned char *lk = (const unsigned char*)(void*)ELEM(lines, kk);
            U lh_sp = 0;
            unsigned lh_fb = PB(lk, 0);
            while (lh_fb == 32){ lh_sp++; lh_fb = PB(lk, lh_sp); }
            if (lh_fb == 97 || lh_fb == 119 || lh_fb == 100){
                if (licm_whdr(sp_strip_span(lk)) > 0) lh_any = 1;
            }
        }
        kk++;
    }
    if (lh_any == 0) return 0;

    U cur = lines;
    U cs = sln;
    int ch = 0;
    U it = 0;
    while (it < 16){
        int did = 0;
        if (licm_one(&st, cur, cs, base, gen)){
            cur = st.out; cs = st.sln; ch = 1; did = 1;
        }
        if (did == 0){
            if (licm2_one(&st, cur, cs, base, gen)){
                cur = st.out; cs = st.sln; ch = 1; did = 1;
            }
        }
        if (did == 0) it = 16;
        it++;
    }
    if (ch == 1){
        t1(st.tbl, T_SETOUT, cur);
        t1(st.tbl, T_SETSLN, cs);
        return 1;
    }
    return 0;
}
