/* Fresh independent bodies: AST callback, packed ownership, exact metadata,
 * NUL/prefetched-token lexer entry, and allocation-boundary sanitizers. */
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef uint64_t U;
uintptr_t syntax_build_native(const unsigned char*,U,U*);
U syntax_statement_build_native(U*,U*,unsigned char*,uintptr_t(*)(const unsigned char*,U,U*));
static uint32_t state=8417623;
static uint32_t rnd(void){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
int main(void){
 unsigned trees=0;
 const char *prefix[]={"xx: ","if ","while ","as long as ","print ","return ","join ","wipe ","raise ","stop ","", "  "};
 const char *good[]={"x + 1", "f(1, x)","\"hello\\\"x\"", "xs[id(1)]", "x != 1", "x <= 0", "x >= 1", "as ptr x", "length of x", "spawn task(7)", "(x * 2) + 1", "f(1, x)\t ", "x == 1", "not"};
 const char alphabet[]="abcdefghijklmn_0123456789+-*/%() \t\r\n!<>=[],:\".\\";
 for(unsigned batch=0;batch<20000;batch++){
  U n=rnd()%25,*lines=malloc((n+2)*8);lines[0]=lines[1]=n;
  for(U i=0;i<n;i++){
   const char *p=prefix[rnd()%12];size_t plen=strlen(p),len=rnd()%100;
   unsigned char *s=malloc(plen+len+1);memcpy(s,p,plen);
   for(size_t j=0;j<len;j++)s[plen+j]=(unsigned char)alphabet[rnd()%(sizeof(alphabet)-1)];s[plen+len]=0;
   if(i%3==0){const char*g=good[rnd()%14];free(s);len=strlen(g);s=malloc(plen+len+1);memcpy(s,p,plen);memcpy(s+plen,g,len+1);}
   lines[i+2]=(U)s;
  }
  U budget=syntax_statement_build_native(lines,0,0,0),*a=malloc((2+14*n)*8),*b=malloc((2+14*n)*8);
  unsigned char *arena=malloc(budget+32);memset(arena+budget,0xa7,32);
  syntax_statement_build_native(lines,a,0,0);
  syntax_statement_build_native(lines,b,arena,syntax_build_native);
  assert(a[0]==b[0]&&a[1]==b[1]);
  for(U i=0;i<12*n;i++)assert(a[i+2]==b[i+2]);
  U cursor=(U)arena;
  for(U i=0;i<n;i++){
   U addr=b[2+12*n+i];if(!addr){assert(b[2+13*n+i]==0);continue;}
   trees++;assert(addr==cursor&&addr%16==0);U *h=(U*)addr;
   assert(h[0]>=lines[i+2]&&h[0]+h[1]<=lines[i+2]+strlen((void*)lines[i+2]));
   assert(h[7]==0x4e4154495645&&h[6]<h[2]&&h[2]<=h[1]+1&&h[13]==0);
   cursor+=(128+h[2]*40+15)&~(U)15;assert(cursor<=(U)arena+budget);
  }
  for(U i=0;i<32;i++)assert(arena[budget+i]==0xa7);
  free(arena);free(a);free(b);for(U i=0;i<n;i++)free((void*)lines[i+2]);free(lines);
 }
 printf("PASS 20000 fresh bodies; %u ASTs; metadata, packed ownership and canaries\n",trees);
}
