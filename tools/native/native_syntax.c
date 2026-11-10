/* Linux expression frontend. Single cursor lexer + precedence parser.
 * Nodes and parser state belong exclusively to the caller's active arena.
 * No external calls, static mutable state, source-keyed lookup or saved result.
 */
#include <stdint.h>
typedef uint64_t U;
typedef struct { U kind,start,end,left,right; } Node;
enum { CALL=256, ARG=257, INDEX=258, SPAWN=259, LENGTH=260, CAST=261, ADDRESS=262, NUMBER=264, NAME=265, TEXT=266, GROUP=268, EQ=300,NE,LE,GE,SHL,SAR,SHR,LAND,LOR };
enum { POS=8,TOK,START,END,DEPTH,BAD };
#define INLINE static __attribute__((always_inline)) inline
INLINE int word(unsigned c){return c=='_'||(c>='0'&&c<='9')||(c>='A'&&c<='Z')||(c>='a'&&c<='z');}
INLINE int digit(unsigned c){return c>='0'&&c<='9';}
INLINE U key(const unsigned char*s,U a,U b){
 U k=0;if(b-a>8)return 0;for(U i=a;i<b;i++)k|=(U)s[i]<<((i-a)*8);return k;
}
INLINE U tokenkey(U*h){return key((void*)h[0],h[10],h[11]);}
INLINE int prec(U c){
 if(c==LOR)return 1;if(c==LAND)return 2;if(c=='|')return 3;
 if(c=='^')return 4;if(c=='&')return 5;if(c==EQ)return 6;
 if(c==NE)return 7;if(c==LE)return 8;if(c==GE)return 9;
 if(c=='<')return 10;if(c=='>')return 11;if(c==SHR)return 12;
 if(c==SAR)return 13;if(c==SHL)return 14;
 if(c=='+'||c=='-')return 15;if(c=='*'||c=='/'||c=='%')return 16;return 0;
}
INLINE Node *nodes(U*h){return (Node*)(h+16);}
INLINE U add(U*h,U k,U s,U e,U l,U r){
 if(k==0){
  const unsigned char*p=(void*)h[0];if(s>=e||e>h[1]){h[BAD]=1;return 0;}
  unsigned c=p[s];
  if(c=='"'){k=TEXT;l=s;r=e;}
  else if(digit(c)||c=='-'){
   k=NUMBER;U i=s,negative=0,value=0,base=10;if(c=='-'){negative=1;i++;}
   if(i+2<e&&p[i]=='0'&&p[i+1]=='x'){base=16;i+=2;}
   else if(i+2<e&&p[i]=='0'&&p[i+1]=='b'){base=2;i+=2;}
   for(;i<e;i++){
    unsigned d=p[i];U v=99;
    if(digit(d))v=d-'0';else if(d>='a'&&d<='f')v=d-'a'+10;else if(d>='A'&&d<='F')v=d-'A'+10;
    if(base==2){if(v<2)value=value*2+v;}
    else {if(v>=base)break;value=value*base+v;}
   }
   l=negative?0-value:value;r=0;
  }else{k=NAME;l=s;r=e;}
 }
 U id=h[2]++;if(id>h[1]+(h[1]>>1)){h[BAD]=1;return 0;}
 nodes(h)[id]=(Node){k,s,e,l,r};return id;
}
static __attribute__((noinline)) void next(U*h){
 const unsigned char*s=(void*)h[0];U n=h[1],i=h[POS];int nul=h[7]==1;
 while(i<n&&s[i]<=32&&(!nul||s[i])){if(s[i]=='\t')h[14]|=2;i++;}
 h[START]=i;h[TOK]=0;
 if(i==n||(nul&&!s[i])){if(nul){if(i==4096&&s[i])h[BAD]=16;h[1]=i;}h[END]=i;h[POS]=i;return;}
 unsigned c=s[i++];U kind=c;if(c=='='&&h[4]==(U)-1)h[4]=i-1;
 if(word(c)){
  kind=digit(c)?2:1;while(i<n&&word(s[i]))i++;
  if(kind==2){
   U a=h[START];int hex=i>a+2&&s[a]=='0'&&(s[a+1]=='x'||s[a+1]=='b');
   if(!hex)for(U j=a;j<i;j++)if(!digit(s[j]))h[BAD]=2;
  }else if(h[START]>0&&s[h[START]-1]==' '&&i<n&&s[i]==' '){
   U k=key(s,h[START],i);
   if(k==0x7369){kind=EQ;if(i+4<n&&s[i+1]=='n'&&s[i+2]=='o'&&s[i+3]=='t'&&s[i+4]==' '){kind=NE;i+=4;}}
   if(k==0x646e61)kind=LAND;
   if(k==0x726f)kind=LOR;
  }
 }else if(c=='"'){
  if(h[3]==(U)-1)h[3]=i-1;
  kind=3;int closed=0;
  while(i<n){unsigned b=s[i++];if(nul&&!b){i--;break;}if(b=='\\'){if(i<n&&(!nul||s[i]))i++;else break;}else if(b=='"'){closed=1;break;}}
  if(!closed)h[BAD]=3;
  /* String content is data, not syntax: word operators and ampersands inside a
   * quoted literal never reach the operator grammar, so they set no flag and
   * trigger no compatibility decline.  This matches the interpreted lexer. */
  if(h[14]&1)h[BAD]=12;
 }else if(i<n){
  unsigned d=s[i];if(d=='='&&(c=='!'||c=='<'||c=='>')&&h[4]==(U)-1)h[4]=i;
  if(c=='='&&d=='='){kind=EQ;i++;}else if(c=='!'&&d=='='){kind=NE;i++;}
  else if(c=='<'&&d=='='){kind=LE;i++;}else if(c=='>'&&d=='='){kind=GE;i++;}
  else if(c=='<'&&d=='<'){kind=SHL;i++;}else if(c=='>'&&d=='>'){kind=SAR;i++;if(i<n&&s[i]=='>'){kind=SHR;i++;}}
  else if(c=='&'&&d=='&'){kind=LAND;i++;}else if(c=='|'&&d=='|'){kind=LOR;i++;}
 }
 if(kind==LAND||kind==LOR)h[15]=1;
 h[TOK]=kind;h[END]=i;h[POS]=i;
}
static U expression(U*h,int minimum){
 if(h[BAD])return 0;
 if(++h[DEPTH]>150){h[BAD]=4;h[DEPTH]--;return 0;}
 U kind=h[TOK],start=h[START],end=h[END],root=0;int text_head=0;
 if(kind==1||kind==2||kind==3){
  U k=kind==1?tokenkey(h):0;next(h);
  if(k==0x6874676e656c&&h[TOK]==1&&tokenkey(h)==0x666f){
   next(h);U child=expression(h,1);root=add(h,LENGTH,start,nodes(h)[child].end,child,(U)-1);h[5]++;
  }else if(k==0x7361&&h[TOK]==1&&(tokenkey(h)==0x74786574||tokenkey(h)==0x727470)){
   next(h);U child=expression(h,1);root=add(h,CAST,start,nodes(h)[child].end,child,(U)-1);h[5]++;
  }else if(k==0x666f5f72646461&&h[TOK]==1){
   U child=add(h,0,h[START],h[END],(U)-1,(U)-1);next(h);
   if(prec(h[TOK]))h[BAD]=13;
   root=add(h,ADDRESS,start,nodes(h)[child].end,child,(U)-1);h[5]++;
  }else{
   U callkind=CALL;
   if(k==0x6e77617073&&h[TOK]==1){
    callkind=SPAWN;kind=1;U ns=h[START],ne=h[END];next(h);root=add(h,0,ns,ne,(U)-1,(U)-1);
    if(h[TOK]!='(')h[BAD]=14;
   }else root=add(h,0,start,end,(U)-1,(U)-1);
   text_head=kind==3;
   if(kind==1&&h[TOK]=='('){
    U callee=root,first=(U)-1,last=(U)-1;next(h);
    if(h[TOK]!=')')for(;;){
     U arg=expression(h,1);if(h[BAD])break;
     U link=add(h,ARG,nodes(h)[arg].start,nodes(h)[arg].end,arg,(U)-1);
     if(last!=(U)-1)nodes(h)[last].right=link;else first=link;last=link;
     if(h[TOK]!=',')break;next(h);
    }
    if(h[TOK]!=')')h[BAD]=5;
    root=add(h,callkind,start,h[END],callee,first);h[5]++;next(h);
   }else if(kind==1&&h[TOK]=='['){
    if(h[14]&1)h[BAD]=12;h[14]++;next(h);U child=expression(h,1);h[14]--;
    if(h[TOK]!=']')h[BAD]=5;
    root=add(h,INDEX,start,h[END],root,child);h[5]++;next(h);
   }
  }
 }else if(kind=='('){
  next(h);root=expression(h,1);if(h[TOK]!=')')h[BAD]=5;
  root=add(h,GROUP,start,h[END],root,(U)-1);next(h);
 }else if(kind=='-'){
  next(h);if(h[TOK]!=2)h[BAD]=6;
  root=add(h,0,start,h[END],(U)-1,(U)-1);next(h);
 }else h[BAD]=7;
 while(!h[BAD]){
  int p=prec(h[TOK]);if(!p||p<minimum)break;
  /* Legacy text-head recognizer claims a whole quoted surface. Decline
   * instead of silently changing that compatibility rule into pointer math. */
  if(text_head){h[BAD]=8;break;}
  U op=h[TOK];next(h);U right=expression(h,p+1);
  root=add(h,op,nodes(h)[root].start,nodes(h)[right].end,root,right);h[5]++;
 }
 if(minimum==1&&h[TOK]==1&&tokenkey(h)==0x7361){
  next(h);U k=tokenkey(h);
  if(h[TOK]!=1||(k!=0x74786574&&k!=0x727470))h[BAD]=15;
  root=add(h,CAST,nodes(h)[root].start,h[END],root,(U)-1);h[5]++;next(h);
 }
 h[DEPTH]--;return root;
}
uintptr_t syntax_build_native(const unsigned char*s,U n,U*h){
 int nul=(uint32_t)n==UINT32_MAX;U initial=nul?n>>32:0;
 if((!nul&&(n<1||n>4096))||initial>4096)return 0;
 h[0]=(U)s;h[1]=nul?4096:n;for(int i=2;i<16;i++)h[i]=0;
 h[3]=h[4]=(U)-1;h[7]=nul;
 if(initial){h[POS]=initial;h[TOK]=1;h[START]=0;h[END]=initial;}else next(h);
 U root=expression(h,1);
 if(h[BAD])return 0;if(h[TOK]){h[BAD]=9;return 0;}
 h[6]=root;h[7]=0x4e4154495645;return (uintptr_t)h;
}
