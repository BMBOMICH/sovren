/* Candidate-filtered word tally for lord_build.
 *
 * The portable Sovren path (lb_words + fl_span_tally) tallies EVERY
 * word occurrence in a body into a shared span table, then reads back
 * only the counts of the handful of assignment-target names.  This
 * twin does the same accounting in one native pass: it scans the word
 * runs of every body line, normalises spaces to underscores exactly
 * like fl_span_tally/fl_span_count, and accumulates a weight into the
 * matching candidate's counter.  Words that name no candidate are
 * never stored, so the shared span table stays small.
 *
 * Input is one descriptor block (all fields 8 bytes):
 *   [0] U *lines    per-body line pointers      [24] U *cand
 *   [8] U *weights  per-body line weights       [32] U  ncand
 *  [16] U  nlines                              [40] U *counts
 *
 * cand holds three words per candidate: line pointer, start, end.
 * counts receives one weight total per candidate.
 */
#include <stdint.h>
typedef uint64_t U;
#define INLINE static __attribute__((always_inline)) inline
INLINE int wordc(unsigned c){return c=='_'||(c>='0'&&c<='9')||(c>='A'&&c<='Z')||(c>='a'&&c<='z');}
INLINE int digitc(unsigned c){return c>='0'&&c<='9';}
/* Same normalisation as fl_span_tally: a space byte counts as '_'. */
INLINE unsigned norm(unsigned c){return c==32?95:c;}

uintptr_t lord_tally_native(U *d)
{
 U *lines=(U*)d[0], *weights=(U*)d[8], nlines=d[16];
 U *cand=(U*)d[24], ncand=d[32], *counts=(U*)d[40];
 if(!lines||!cand||!counts)return 0;
 for(U i=0;i<ncand;i++)counts[i]=0;
 if(!ncand||!nlines)return 1;
 for(U li=0;li<nlines;li++){
  const unsigned char *ln=(const unsigned char*)lines[li];
  if(!ln)continue;
  U w=weights?weights[li]:1;
  /* The caller passes the indent-skipped start in cand-style fashion:
   * the word scan starts at the first non-space byte of the line. */
  U i=0;while(ln[i]==' ')i++;
  U n=0;while(ln[n])n++;
  U ws=(U)-1;
  for(U p=i;p<=n;p++){
   unsigned ch=(p<n)?ln[p]:0;
   if(wordc(ch)){
    if(ws==(U)-1)ws=p;
   }else{
    if(ws!=(U)-1){
     if(!digitc(ln[ws])){
      U len=p-ws;
      for(U c=0;c<ncand;c++){
       U *cd=cand+c*3;
       const unsigned char *cl=(const unsigned char*)cd[0];
       U ca=cd[1], cb=cd[2];
       if(!cl)continue;
       if(cb-ca!=len)continue;
       U k=0;int eq=1;
       for(;k<len;k++){
        if(norm(cl[ca+k])!=norm(ln[ws+k])){eq=0;break;}
       }
       if(eq)counts[c]+=w;
      }
     }
     ws=(U)-1;
    }
   }
  }
 }
 return 1;
}
