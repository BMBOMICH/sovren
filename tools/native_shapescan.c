/* C.15 / C.16 — CPUID/XGETBV-gated AVX2/SWAR shape-specialised line scanner.
 *
 * Three entry points, all with the SAME output contract:
 *   scan_shapes_scalar()  - portable byte-loop fallback, no AVX2 required
 *   scan_shapes_avx2()    - real 32-byte SIMD classification fast path
 *   scan_shapes_auto()    - picks avx2 only after a real CPUID/XGETBV check
 *
 * `cpu_has_avx2()` does the actual feature detection: CPUID leaf 1 for OSXSAVE
 * (bit 27) and AVX (bit 28), XGETBV(0) for XMM/YMM state (bits 1+2), then
 * CPUID leaf 7 EBX bit 5 for AVX2. Anything missing -> scalar fallback.
 *
 * The SIMD path loads 32 bytes, compares against newline / blank / hash /
 * slash / quote / colon / operator / digit vectors with _mm256_cmpeq_epi8 and
 * folds each result to a 32-bit mask with _mm256_movemask_epi8. The resulting
 * flag word is the packed-key prefilter for first-byte statement dispatch.
 * Both paths MUST produce byte-identical class arrays; tools/shape_scan_gate.py
 * proves that on the 12 SA shapes, cliff probes and seeded PRNG corpora.
 *
 * Standalone native scanner, NOT yet wired into compiler.sov. Built without
 * -mavx2 for the TU: AVX2 code is isolated behind target("avx2"), so the
 * scalar fallback can never accidentally contain AVX2 instructions.
 */
#include <stdint.h>
#include <stddef.h>
#include <immintrin.h>

typedef uint64_t U;
#define SHAPE_CLASSES 11

enum {
    S_OTHER = 0, S_COMMENT, S_DATA, S_LABEL, S_LONG_LABEL, S_MOV,
    S_EXPR, S_TIMES, S_FWD_JMP, S_BACK_JMP, S_EQU
};

/* flag bits produced by BOTH scan paths */
#define F_NL   1u
#define F_BLANK 2u
#define F_HASH  4u
#define F_SLASH 8u
#define F_QUOTE 16u
#define F_COLON 32u
#define F_OP    64u
#define F_DIGIT 128u

/* --------------------------- CPU feature gate -------------------------- */
static void cpuid(U leaf, U sub, U *a, U *b, U *c, U *d){
#if defined(__x86_64__) || defined(__i386__)
    __asm__ volatile("cpuid"
        : "=a"(*a), "=b"(*b), "=c"(*c), "=d"(*d)
        : "a"((uint32_t)leaf), "c"((uint32_t)sub));
#else
    *a=*b=*c=*d=0;
#endif
}
static U xgetbv0(void){
#if defined(__x86_64__) || defined(__i386__)
    uint32_t eax, edx;
    __asm__ volatile("xgetbv" : "=a"(eax), "=d"(edx) : "c"(0));
    return ((U)edx<<32)|eax;
#else
    return 0;
#endif
}
int cpu_has_avx2(void){
    U a,b,c,d;
    cpuid(0,0,&a,&b,&c,&d);
    if(a<7) return 0;
    cpuid(1,0,&a,&b,&c,&d);
    if(!((c>>27)&1) || !((c>>28)&1)) return 0;   /* OSXSAVE + AVX */
    if((xgetbv0()&0x6)!=0x6) return 0;           /* XMM + YMM enabled */
    cpuid(7,0,&a,&b,&c,&d);
    return ((b>>5)&1) ? 1 : 0;                    /* AVX2 */
}

/* -------------------- shared packed-key first-byte dispatch ------------ */
/* `flags` is the 32-byte classification word: used as a prefilter so the
 * expensive operator/colon scans are skipped when the flag is absent. */
static U classify_flags(const unsigned char *l, U n, unsigned flags){
    (void)flags;
    U t0=0,t1=n;
    while(t0<n && (unsigned)l[t0]<33) t0++;
    while(t1>t0 && (unsigned)l[t1-1]<33) t1--;
    if(t0>=t1) return S_OTHER;
    const unsigned char *s=l+t0; U len=t1-t0;
    unsigned char f=s[0];
    if(f=='#') return S_COMMENT;
    if(f=='/' && len>1 && s[1]=='/') return S_COMMENT;
    if(f=='d' && len>2 && s[1]=='b' && s[2]==32) return S_DATA;
    if(f=='t' && len>=6 && s[1]=='i' && s[2]=='m' && s[3]=='e' &&
       s[4]=='s' && s[5]==32) return S_TIMES;
    if(f=='r' && len>=7 && s[1]=='e' && s[2]=='p' && s[3]=='e' &&
       s[4]=='a' && s[5]=='t' && s[6]==32) return S_TIMES;
    if(f=='m' && len>=4 && s[1]=='o' && s[2]=='v') return S_MOV;
    if(f=='n' && len>=3 && s[1]=='o' && s[2]=='p') return S_MOV;
    if(s[len-1]==':') return (len>24) ? S_LONG_LABEL : S_LABEL;
    if(flags & F_OP){
        for(U i=0;i<len;i++) if(s[i]=='+'||s[i]=='*'||s[i]=='('||s[i]==')') return S_EXPR;
        for(U i=0;i+1<len;i++) if(s[i]=='-'&&s[i+1]=='>') return S_FWD_JMP;
        for(U i=0;i<len;i++) if(s[i]=='=') return S_EQU;
    }
    if(flags & F_COLON){
        for(U i=0;i<len;i++) if(s[i]==':') return S_LABEL;
    }
    for(U i=0;i<len;i++) if(s[i]=='j' && i+3<len && s[i+1]=='m' && s[i+2]=='p')
        return S_BACK_JMP;
    return S_OTHER;
}

/* --------------------------- scalar fallback --------------------------- */
static unsigned scalar_flags(const unsigned char *l, U n){
    unsigned f=0;
    for(U i=0;i<n;i++){ unsigned c=l[i];
        if(c=='\n') f|=F_NL;
        if(c==32||c==9) f|=F_BLANK;
        if(c=='#') f|=F_HASH;
        if(c=='/') f|=F_SLASH;
        if(c=='"'||c=='\'') f|=F_QUOTE;
        if(c==':') f|=F_COLON;
        if(c=='+'||c=='*'||c=='('||c==')'||c=='-'||c=='=') f|=F_OP;
        if(c>=48&&c<=57) f|=F_DIGIT;
    }
    return f;
}
U *scan_shapes_scalar(const unsigned char *text, U n, U *out, U max_lines){
    U p=0,line=0;
    while(p<n && line<max_lines){
        U e=p; while(e<n && text[e]!='\n') e++;
        out[line++]=classify_flags(text+p,e-p,scalar_flags(text+p,e-p));
        p=e+1;
    }
    return out;
}

/* ---------------------------- AVX2 fast path --------------------------- */
__attribute__((target("avx2")))
static unsigned avx2_flags(const unsigned char *l, U n){
    unsigned f=0; U i=0;
    const __m256i nl  =_mm256_set1_epi8('\n');
    const __m256i sp  =_mm256_set1_epi8(' ');
    const __m256i tab =_mm256_set1_epi8('\t');
    const __m256i hash=_mm256_set1_epi8('#');
    const __m256i sl  =_mm256_set1_epi8('/');
    const __m256i dq  =_mm256_set1_epi8('"');
    const __m256i sq  =_mm256_set1_epi8('\'');
    const __m256i col =_mm256_set1_epi8(':');
    const __m256i plus=_mm256_set1_epi8('+');
    const __m256i star=_mm256_set1_epi8('*');
    const __m256i lp  =_mm256_set1_epi8('(');
    const __m256i rp  =_mm256_set1_epi8(')');
    const __m256i dash=_mm256_set1_epi8('-');
    const __m256i eq  =_mm256_set1_epi8('=');
    const __m256i z   =_mm256_set1_epi8('0');
    const __m256i nine=_mm256_set1_epi8('9');
    for(;i+32<=n;i+=32){
        __m256i v=_mm256_loadu_si256((const __m256i*)(l+i));
        unsigned m;
        m=(unsigned)_mm256_movemask_epi8(_mm256_cmpeq_epi8(v,nl));  if(m) f|=F_NL;
        m=(unsigned)_mm256_movemask_epi8(_mm256_cmpeq_epi8(v,sp));  if(m) f|=F_BLANK;
        m=(unsigned)_mm256_movemask_epi8(_mm256_cmpeq_epi8(v,tab)); if(m) f|=F_BLANK;
        m=(unsigned)_mm256_movemask_epi8(_mm256_cmpeq_epi8(v,hash));if(m) f|=F_HASH;
        m=(unsigned)_mm256_movemask_epi8(_mm256_cmpeq_epi8(v,sl));  if(m) f|=F_SLASH;
        m=(unsigned)_mm256_movemask_epi8(_mm256_cmpeq_epi8(v,dq));  if(m) f|=F_QUOTE;
        m=(unsigned)_mm256_movemask_epi8(_mm256_cmpeq_epi8(v,sq));  if(m) f|=F_QUOTE;
        m=(unsigned)_mm256_movemask_epi8(_mm256_cmpeq_epi8(v,col)); if(m) f|=F_COLON;
        for(int k=0;k<6;k++){
            const __m256i op = k==0?plus:k==1?star:k==2?lp:k==3?rp:k==4?dash:eq;
            m=(unsigned)_mm256_movemask_epi8(_mm256_cmpeq_epi8(v,op));
            if(m) f|=F_OP;
        }
        __m256i ge=_mm256_cmpgt_epi8(v,_mm256_set1_epi8('0'-1));
        __m256i le=_mm256_cmpgt_epi8(_mm256_set1_epi8('9'+1),v);
        m=(unsigned)_mm256_movemask_epi8(_mm256_and_si256(ge,le));
        if(m) f|=F_DIGIT;
        (void)z; (void)nine;
    }
    /* tail: byte loop, identical semantics */
    for(;i<n;i++){ unsigned c=l[i];
        if(c=='\n') f|=F_NL;
        if(c==32||c==9) f|=F_BLANK;
        if(c=='#') f|=F_HASH;
        if(c=='/') f|=F_SLASH;
        if(c=='"'||c=='\'') f|=F_QUOTE;
        if(c==':') f|=F_COLON;
        if(c=='+'||c=='*'||c=='('||c==')'||c=='-'||c=='=') f|=F_OP;
        if(c>=48&&c<=57) f|=F_DIGIT;
    }
    return f;
}
__attribute__((target("avx2")))
U *scan_shapes_avx2(const unsigned char *text, U n, U *out, U max_lines){
    U p=0,line=0;
    while(p<n && line<max_lines){
        U e=p; while(e<n && text[e]!='\n') e++;
        out[line++]=classify_flags(text+p,e-p,avx2_flags(text+p,e-p));
        p=e+1;
    }
    return out;
}

U *scan_shapes_auto(const unsigned char *text, U n, U *out, U max_lines){
    if(cpu_has_avx2()) return scan_shapes_avx2(text,n,out,max_lines);
    return scan_shapes_scalar(text,n,out,max_lines);
}
U shape_class_count(void){ return SHAPE_CLASSES; }
