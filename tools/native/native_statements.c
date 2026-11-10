/* Structured body IR, one lexical traversal per logical statement.
 * Columns: quote, indent, colon, equals, tab, trailing-space, byte length,
 * parent statement, exclusive block end, significant flag, head-end, cumulative
 * tabs, owned expression tree, expression role. Column 11 is temporary stack
 * during construction. Memory belongs to the active body, never a keyed cache.
 */
#include <stdint.h>
typedef uint64_t U;
typedef uintptr_t (*Parser)(const unsigned char*,U,U*);
static U headkey(const unsigned char*s,U a,U b){U key=0;if(b-a>8)return 0;for(U j=a;j<b;j++)key|=(U)s[j]<<((j-a)*8);return key;}
U syntax_statement_build_native(U *lines,U *out,unsigned char*arena,Parser parse){
 U n=lines[1];
 if(!out){U bytes=0;for(U i=0;i<n;i++){const unsigned char*s=(void*)lines[i+2];U j=0;while(s[j])j++;bytes+=128+(j+1)*64;}return bytes;}
 U cap=out[0]==773411?out[1]:(U)-1;
 unsigned char *arena_end=cap==(U)-1?0:arena+cap;
 U *v=out+2,depth=0;out[0]=(U)lines;out[1]=n;
 for(U i=0;i<n;i++){
  const unsigned char*s=(void*)lines[i+2];U j=0,ind=0,col=(U)-1,eq=(U)-1,quote=(U)-1,tab=0;
  int inside=0,leading=1;
  /* A statement prefix is consumed here; the expression lexer supplies
   * remaining quote/equality/tab/length metadata in the same token walk.
   * Opaque syntax keeps the independent compatibility traversal below. */
  U first0=0;while(s[first0]==' ')first0++;
  U head0=first0;while(s[head0]&&s[head0]>32&&s[head0]!=':'&&s[head0]!='(')head0++;
  U k0=headkey(s,first0,head0),begin0=head0,role0=0,initial0=0;int fast=0,prefix_ok=1;
  for(U p=first0;p<head0;p++)if(!((s[p]>='a'&&s[p]<='z')||(s[p]>='A'&&s[p]<='Z')||(s[p]>='0'&&s[p]<='9')||s[p]=='_'))prefix_ok=0;
  if(k0==0x746e697270)role0=3;
  else if(k0==0x6e7275746572)role0=4;
  else if(k0==0x6669||k0==0x656c696877)role0=2;
  else if(k0==0x6e696f6a)role0=6;
  else if(k0==0x65706977)role0=7;
  else if(k0==0x6573696172)role0=8;
  else if(k0==0x706f7473)role0=9;
  else if(k0==0x6f64||k0==0x7361){
   U a=head0;while(s[a]==' ')a++;U b=a;while(s[b]&&s[b]>32)b++;
   U second=headkey(s,a,b);
   if(k0==0x6f64&&second==0x656c696877){role0=2;begin0=b;}
   else if(k0==0x7361&&second==0x676e6f6c){
    a=b;while(s[a]==' ')a++;b=a;while(s[b]&&s[b]>32)b++;
    if(headkey(s,a,b)==0x7361){role0=2;begin0=b;}
   }
  }else if(s[head0]==':'&&prefix_ok){role0=1;begin0=head0+1;}
  else if(s[head0]=='('&&prefix_ok&&head0>first0&&!(s[first0]>='0'&&s[first0]<='9')){role0=5;begin0=first0;initial0=head0-first0;}
  v[12*n+i]=v[13*n+i]=0;
  if(parse&&role0&&prefix_ok){
   if(arena_end&&(U)(arena_end-arena)<164096)return (U)-1;
   U *tree=(U*)arena;
   if(parse(s+begin0,(initial0<<32)|UINT32_MAX,tree)){
    fast=1;ind=first0;j=begin0+tree[1];
    quote=tree[3]==(U)-1?(U)-1:begin0+tree[3];
    eq=tree[4]==(U)-1?(U)-1:begin0+tree[4];
    tab=(tree[14]&2)!=0;col=role0==1?head0:(U)-1;
    U *root=tree+16+tree[6]*5;
    if(k0==0x6669&&root[0]==265&&headkey((void*)tree[0],root[1],root[2])==0x746f6e)role0=0;
    if(role0){v[12*n+i]=(U)tree;v[13*n+i]=role0;}
   }
  }
  if(!fast){
  while(s[j]){
   unsigned c=s[j];if(leading){if(c==' ')ind++;else leading=0;}
   if(inside){if(c=='\\'&&s[j+1])j++;else if(c=='"')inside=0;}
   else if(c=='\t')tab=1;else if(c=='"'){inside=1;if(quote==(U)-1)quote=j;}
   else if(c==':'&&col==(U)-1)col=j;else if(c=='='&&eq==(U)-1)eq=j;
   j++;
  }
  }
  v[i]=quote;v[n+i]=ind;v[2*n+i]=col;v[3*n+i]=eq;v[4*n+i]=tab;
  v[5*n+i]=j&&s[j-1]<33;v[6*n+i]=j;
  U first=ind;while(first<j&&s[first]<=32)first++;
  U head=first;while(head<j&&s[head]>32&&s[head]!=':'&&s[head]!='(')head++;
  v[10*n+i]=head;v[9*n+i]=first<j&&s[first]!='#';
  v[7*n+i]=(U)-1;v[8*n+i]=n;
  if(!fast&&parse&&v[9*n+i]){
   U k=headkey(s,first,head),begin=first,role=5,finish=j;
   while(finish>first&&s[finish-1]<=32)finish--;
   if(k==0x746e697270){role=3;begin=head;}
   else if(k==0x6e7275746572){role=4;begin=head;}
   else if(k==0x6669||k==0x656c696877){role=2;begin=head;}
   else if(k==0x6f64||k==0x7361){
    U a=head;while(a<j&&s[a]<=32)a++;U b=a;while(b<j&&s[b]>32)b++;
    U second=headkey(s,a,b);
    if(k==0x6f64&&second==0x656c696877){role=2;begin=b;}
    else if(k==0x7361&&second==0x676e6f6c){
     a=b;while(a<j&&s[a]<=32)a++;b=a;while(b<j&&s[b]>32)b++;
     if(headkey(s,a,b)==0x7361){role=2;begin=b;}else role=0;
    }else role=0;
   }else if(col!=(U)-1){role=1;begin=col+1;}
   else if(k==0x6e696f6a){role=6;begin=head;}
   else if(k==0x65706977){role=7;begin=head;}
   else if(k==0x6573696172){role=8;begin=head;}
   else if(k==0x706f7473){role=9;begin=head;}
   if(role==5&&eq!=(U)-1)role=0; /* compound desugaring occurs first */
   while(begin<finish&&s[begin]<=32)begin++;
   if(k==0x6669&&headkey(s,begin,finish)==0x746f6e)role=0;
   if(role&&begin<finish){
    if(arena_end&&(U)(arena_end-arena)<164096)return (U)-1;
   U *tree=(U*)arena;
    if(parse(s+begin,finish-begin,tree)){v[12*n+i]=(U)tree;v[13*n+i]=role;}
   }
  }
  if(v[12*n+i])arena+=(128+((U*)v[12*n+i])[2]*40+15)&~(U)15;
  if(v[9*n+i]){
   while(depth){U parent=v[11*n+depth-1];if(v[n+parent]<ind)break;v[8*n+parent]=i;depth--;}
   if(depth)v[7*n+i]=v[11*n+depth-1];
   v[11*n+depth++]=i;
  }
 }
 U bad=0;for(U i=0;i<n;i++){bad+=v[4*n+i]!=0;v[11*n+i]=bad;}
 return n;
}
