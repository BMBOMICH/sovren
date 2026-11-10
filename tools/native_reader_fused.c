/* C.11 — the lost S27/S29 FUSED READER DESCRIPTOR CORE — BLOB BUILD (fused side only).
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


/* This file contains ONLY the fused one-pass core so the emitted blob has
 * no .bss/.rodata relocations. The multi-pass reference lives in
 * tools/native_reader_desc.c and is used by reader_descriptor_gate.py. */

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
