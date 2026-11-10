/* ASan/UBSan harness: build with tools/native_syntax.c, run locally. */
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <assert.h>
uintptr_t syntax_build_native(const unsigned char *,uint64_t,uint64_t *);
static uint32_t state=1983661;
static uint32_t rnd(void){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
int main(void){
 const char alphabet[]="abcdefghijklmn_0123456789+-*/%() \t\r\n!<>=[],:\".";
 unsigned admitted=0;
 for(unsigned round=0;round<300000;round++){
  size_t n=rnd()%4105;unsigned char *s=malloc(n?n:1);
  for(size_t i=0;i<n;i++)s[i]=(round%3==0)?(unsigned char)rnd():(unsigned char)alphabet[rnd()%(sizeof(alphabet)-1)];
  if(round%100==0)for(size_t i=0;i<n;i++)s[i]=(i%2==0)?'x':'+';
  if(round%100==1)for(size_t i=0;i<n;i++)s[i]='(';
  if(round%100==2)for(size_t i=0;i<n;i++)s[i]=')';
  if(round%100==3){free(s);n=sizeof("as ptr id(2 + x) * (xs[id(1)] + -3)")-1;s=malloc(n);__builtin_memcpy(s,"as ptr id(2 + x) * (xs[id(1)] + -3)",n);}
  size_t bytes=128+(n+1)*64;uint64_t *h=malloc(bytes);
  /* Poison old contents so incomplete initialization cannot hide behind zero. */
  for(size_t i=0;i<bytes/8;i++)h[i]=UINT64_C(0xdeadbeefdeadbeef);
  uintptr_t out=syntax_build_native(s,n,h);
  if(out){
   admitted++;assert(out==(uintptr_t)h);assert(n>=1&&n<=4096);assert(h[2]<=n+1&&h[9]==0&&h[12]==0&&h[13]==0&&h[6]<h[2]);
   uint64_t *nodes=h+16;
   for(size_t i=0;i<h[2];i++){
    uint64_t *p=nodes+i*5;assert(p[1]<p[2]&&p[2]<=n);
    if(p[0]==256||p[0]==259){assert(p[3]<i);assert(p[4]==UINT64_MAX||p[4]<i);}
    else if(p[0]==257){assert(p[3]<i);assert(p[4]==UINT64_MAX||(p[4]>i&&p[4]<h[2]&&nodes[p[4]*5]==257));}
    else if(p[0]==260||p[0]==261||p[0]==262||p[0]==268){assert(p[3]<i&&p[4]==UINT64_MAX);}
    else if(p[0]==264){assert(p[4]==0);}
    else if(p[0]==265||p[0]==266){assert(p[3]==p[1]&&p[4]==p[2]);}
    else {assert(p[0]==258||(p[0]>=300&&p[0]<=308)||p[0]=='+'||p[0]=='-'||p[0]=='*'||p[0]=='/'||p[0]=='%'||p[0]=='<'||p[0]=='>'||p[0]=='&'||p[0]=='|'||p[0]=='^');assert(p[3]<i&&p[4]<i);}
   }
  }
  free(h);free(s);
 }
 printf("PASS 300000 fresh buffers; %u admitted; ASan/UBSan; node ownership/bounds checked\n",admitted);return 0;
}
