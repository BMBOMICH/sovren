/* C.11 — the lost S27/S29 FUSED READER DESCRIPTOR CORE, reconstructed.
 *
 * Contract (SA_PARITY_EVERYTHING_NEEDED.md C.11): ONE pass over one flat
 * source copy computing len / lead32 / trim bounds / colon / lp plus the body
 * fields n / ind / t0 / last33 / last58trim / last58raw / eqbit / eqp_t /
 * eqp_any / q1 / q2 / neq / nis / semi2 / apos / gt / digit0 / qparity,
 * replacing the separate marks + cxinfo + qend + trim + ind + slen + look
 * scans.
 *
 * `ref_descriptors` is a faithful MULTI-PASS reference (one helper call per
 * field group). `fused_descriptors` computes all 23 fields in ONE forward
 * byte loop per line, with no tail rescans. tools/reader_descriptor_gate.py
 * compares the two descriptor arrays byte-for-byte over stress, PRNG and
 * real .sov corpora.
 *
 * This is the DESCRIPTOR core, not the whole cx_read emission path: it does
 * not splice sugar, allocate Sovren strings or call through cx_tbl. Landing
 * it into compiler.sov still requires wiring the descriptor table into C1/bw
 * and re-running fixed point + the 2,957-case differ.
 */
#include <stdint.h>
#include <stddef.h>

typedef uint64_t U;
#define MISS ((U)-1)
#define FIELDS 23

enum {
    F_LEN, F_LEAD32, F_T0, F_T1, F_COLON, F_LP,
    F_N, F_IND, F_LAST33, F_LAST58TRIM, F_LAST58RAW,
    F_EQBIT, F_EQPT, F_EQANY, F_Q1, F_Q2, F_NEQ, F_NIS,
    F_SEMI2, F_APOS, F_GT, F_DIGIT0, F_QPARITY
};

/* ================= OLD SIDE: separate passes ========================== */
static U r_len(const unsigned char *l){ U n=0; while(l[n]) n++; return n; }
static U r_ind(const unsigned char *l){
    U n=0,k=0; while(l[k]){ unsigned b=l[k];
        if(b==32) n++; else if(b==9) n+=4; else break; k++; } return n;
}
static U r_lead32(const unsigned char *l){ U k=0; while(l[k] && l[k]<33) k++; return l[k]?k:MISS; }
static void r_trim(const unsigned char *l, U *a, U *b){
    U n=r_len(l),t0=0,t1=n;
    while(t0<n && (unsigned)l[t0]<33) t0++;
    while(t1>t0 && (unsigned)l[t1-1]<33) t1--;
    *a=t0; *b=t1;
}
static U r_colon(const unsigned char *l){
    U n=r_len(l); int ins=0, skip=0;
    for(U i=0;i<n;i++){
        if(skip){ skip=0; continue; }
        unsigned b=l[i];
        if(ins){ if(b==92) skip=1; else if(b==34) ins=0; }
        else { if(b==34) ins=1; else if(b==58) return i; }
    }
    return MISS;
}
static U r_look(const unsigned char *l, const char *nd){
    U nl=0; while(nd[nl]) nl++;
    if(!nl) return 0;
    U n=r_len(l);
    for(U i=0;i<n;i++){ U j=0;
        while(j<nl && i+j<n && l[i+j]==(unsigned char)nd[j]) j++;
        if(j==nl) return i;
    }
    return MISS;
}
static U r_marks(const unsigned char *l){
    U mk=0; int prev=0;
    for(U i=0;l[i];i++){ unsigned b=l[i];
        if(b==62) mk|=2; if(b==39) mk|=4;
        if(b==59){ if(prev) mk|=1; prev=1; } else prev=0;
    }
    return mk;
}
static U r_cxinfo(const unsigned char *l, U *q1, U *q2){
    U r=0,n=r_len(l);
    long long e=(long long)n-1;
    while(e>-1){ if((unsigned)l[e]>32){ if(l[e]==58) r|=1; break; } e--; }
    U lead=0; while(lead<n && (unsigned)l[lead]<33) lead++;
    if(lead<n && l[lead]>47 && l[lead]<58) r|=64;
    for(U i=0;i<n;i++){ unsigned c=l[i];
        if(c==58 && i+1<n && l[i+1]==32){ if((r&4)==4) r|=8; else r|=4; }
        if(c==61 && i>lead && l[i-1]==32 && i+1<n && l[i+1]==32) r|=2;
        if(c==33 && i>0 && l[i-1]==32 && i+2<n && l[i+1]==61 && l[i+2]==32) r|=16;
        if(c==105 && i>0 && i+4<n && l[i-1]==32 && l[i+1]==115 &&
           l[i+2]==110 && l[i+3]==116 && l[i+4]==32) r|=32;
    }
    U a=MISS,b=MISS;
    for(U i=0;i<n;i++) if(l[i]==58 && i+1<n && l[i+1]==32){
        if(a==MISS) a=i; else { b=i; break; }
    }
    *q1=a; *q2=b;
    return r;
}

U *ref_descriptors(const unsigned char *text, U *out, U max_lines){
    static unsigned char buf[1<<20];
    U line=0,p=0;
    while(line<max_lines){
        U n=0;
        while(text[p] && text[p]!='\n' && n<sizeof(buf)-1) buf[n++]=text[p++];
        buf[n]=0;
        int had_nl=(text[p]=='\n'); if(had_nl) p++;
        if(n==0 && !had_nl && text[p]==0) break;
        U *d=out+line*FIELDS;
        U t0,t1,q1,q2;
        r_trim(buf,&t0,&t1);
        U cx=r_cxinfo(buf,&q1,&q2), mk=r_marks(buf), nl=r_len(buf);
        U last33=MISS; for(U i=nl;i>0;i--) if((unsigned)buf[i-1]>32){ last33=i-1; break; }
        U qp=0; for(U i=0;i<nl;i++) if(buf[i]==34) qp^=1;
        d[F_LEN]=nl; d[F_LEAD32]=r_lead32(buf);
        d[F_T0]=t0; d[F_T1]=t1; d[F_COLON]=r_colon(buf);
        d[F_LP]=r_look(buf,"("); d[F_N]=nl; d[F_IND]=r_ind(buf);
        d[F_LAST33]=last33;
        d[F_LAST58TRIM]=(t1>t0 && buf[t1-1]==58)?1:0;
        d[F_LAST58RAW]=(nl>0 && buf[nl-1]==58)?1:0;
        d[F_EQBIT]=(cx&2)?1:0; d[F_EQPT]=r_look(buf," = ");
        d[F_EQANY]=r_look(buf,"="); d[F_Q1]=q1; d[F_Q2]=q2;
        d[F_NEQ]=(cx&16)?1:0; d[F_NIS]=(cx&32)?1:0;
        d[F_SEMI2]=(mk&1)?1:0; d[F_APOS]=(mk&4)?1:0;
        d[F_GT]=(mk&2)?1:0; d[F_DIGIT0]=(cx&64)?1:0; d[F_QPARITY]=qp;
        line++;
        if(text[p]==0) break;
    }
    return out;
}

/* ================= FUSED SIDE: one forward byte loop =================== */
/* The caller guarantees `text` has >=8 zero bytes of slack after its NUL, so
 * the 4-byte lookaheads below never read out of bounds. */
U *fused_descriptors(const unsigned char *text, U *out, U max_lines){
    U line=0,p=0;
    while(line<max_lines){
        const unsigned char *l=text+p;
        U *d=out+line*FIELDS;
        U n=0, ind=0, t0=MISS, t1=0;
        U colon=MISS, lp=MISS, eqbit=0, eqpt=MISS, eqany=MISS;
        U q1=MISS, q2=MISS, neq=0, nis=0, semi2=0, apos=0, gt=0;
        U qparity=0, last58raw=0;
        int in_lead=1, prev_semi=0, in_dq=0, skip=0;
        U i=0;
        for(;;){
            unsigned b=l[i];
            if(b==0 || b=='\n') break;
            /* leading blanks: space=1, tab=4 (ind) */
            if(in_lead){
                if(b==32) ind++;
                else if(b==9) ind+=4;
                else in_lead=0;
            }
            /* trim bounds, last non-blank, digit0 */
            if(b>=33){ if(t0==MISS) t0=i; t1=i+1; }
            if(b==34) qparity^=1;
            if(b==62) gt=1;
            if(b==39) apos=1;
            if(b==59){ if(prev_semi) semi2=1; prev_semi=1; } else prev_semi=0;
            if(b==40 && lp==MISS) lp=i;
            /* colon outside double quotes; backslash inside quotes skips 1 */
            if(skip) skip=0;
            else if(in_dq){ if(b==92) skip=1; else if(b==34) in_dq=0; }
            else { if(b==34) in_dq=1; else if(b==58 && colon==MISS) colon=i; }
            /* ": " first and second occurrence */
            if(b==58 && l[i+1]==32){ if(q1==MISS) q1=i; else if(q2==MISS) q2=i; }
            /* " = " and any '=' */
            if(b==61){
                if(eqany==MISS) eqany=i;
                if(i>0 && l[i-1]==32 && l[i+1]==32){
                    if(eqpt==MISS) eqpt=i-1;
                    if(t0!=MISS && i>t0) eqbit=1;
                }
            }
            /* " != " and " isnt " */
            if(b==33 && i>0 && l[i-1]==32 && l[i+1]==61 && l[i+2]==32) neq=1;
            if(b==105 && i>0 && l[i-1]==32 && l[i+1]==115 && l[i+2]==110 &&
               l[i+3]==116 && l[i+4]==32) nis=1;
            last58raw=(b==58)?1:0;
            i++;
        }
        n=i;
        U lead32=(t0<n)?t0:MISS;
        int all_blank=(t0==MISS);
        if(all_blank){ t0=n; t1=n; }   /* matches r_trim on an all-blank line */
        U last33=(!all_blank && t1>0)?t1-1:MISS;
        U digit0=(t0<n && l[t0]>47 && l[t0]<58)?1:0;
        d[F_LEN]=n; d[F_LEAD32]=lead32; d[F_T0]=t0; d[F_T1]=t1;
        d[F_COLON]=colon; d[F_LP]=lp; d[F_N]=n; d[F_IND]=ind;
        d[F_LAST33]=last33;
        d[F_LAST58TRIM]=(t1>t0 && l[t1-1]==58)?1:0;
        d[F_LAST58RAW]=last58raw;
        d[F_EQBIT]=eqbit; d[F_EQPT]=eqpt; d[F_EQANY]=eqany;
        d[F_Q1]=q1; d[F_Q2]=q2; d[F_NEQ]=neq; d[F_NIS]=nis;
        d[F_SEMI2]=semi2; d[F_APOS]=apos; d[F_GT]=gt;
        d[F_DIGIT0]=digit0; d[F_QPARITY]=qparity;
        line++;
        p+=n;
        if(text[p]=='\n') p++;
        if(text[p]==0) break;
    }
    return out;
}

U descriptor_field_count(void){ return FIELDS; }
