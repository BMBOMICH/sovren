/* C.15/C.16 BLOB BUILD — the portable byte-loop scanning kernel only.
 * The CPUID/XGETBV gate and the AVX2 fast path live in tools/native_shapescan.c
 * and are selected by the caller; this blob is the SAFE EVERYWHERE kernel that
 * tools/shape_scan_gate.py proved byte-identical to the AVX2 path.
 * Extracted verbatim from native_shapescan.c so the two can never diverge in
 * the dispatch logic. No calls to other global symbols -> no relocations.
 */
#include <stdint.h>
#include <stddef.h>
typedef uint64_t U;
#define SHAPE_CLASSES 11
enum { S_OTHER=0, S_COMMENT, S_DATA, S_LABEL, S_LONG_LABEL, S_MOV,
       S_EXPR, S_TIMES, S_FWD_JMP, S_BACK_JMP, S_EQU };
/* flag bits produced by BOTH scan paths */
#define F_NL   1u
#define F_BLANK 2u
#define F_HASH  4u
#define F_SLASH 8u
#define F_QUOTE 16u
#define F_COLON 32u
#define F_OP    64u
#define F_DIGIT 128u


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


U shape_class_count(void){ return SHAPE_CLASSES; }
