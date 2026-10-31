static long acc;
static long f0(long a, long b){ long x=a*b+0; long y=x^(a<<3); if(y>0) y=y-b; else y=y+a; return y+(x>>2); }
static long f1(long a, long b){ long x=a*b+1; long y=x^(a<<3); if(y>7) y=y-b; else y=y+a; return y+(x>>2); }
static long f2(long a, long b){ long x=a*b+2; long y=x^(a<<3); if(y>14) y=y-b; else y=y+a; return y+(x>>2); }
static long f3(long a, long b){ long x=a*b+3; long y=x^(a<<3); if(y>21) y=y-b; else y=y+a; return y+(x>>2); }
static long f4(long a, long b){ long x=a*b+4; long y=x^(a<<3); if(y>28) y=y-b; else y=y+a; return y+(x>>2); }
static long f5(long a, long b){ long x=a*b+5; long y=x^(a<<3); if(y>35) y=y-b; else y=y+a; return y+(x>>2); }
static long f6(long a, long b){ long x=a*b+6; long y=x^(a<<3); if(y>42) y=y-b; else y=y+a; return y+(x>>2); }
static long f7(long a, long b){ long x=a*b+7; long y=x^(a<<3); if(y>49) y=y-b; else y=y+a; return y+(x>>2); }
static long f8(long a, long b){ long x=a*b+8; long y=x^(a<<3); if(y>56) y=y-b; else y=y+a; return y+(x>>2); }
static long f9(long a, long b){ long x=a*b+9; long y=x^(a<<3); if(y>63) y=y-b; else y=y+a; return y+(x>>2); }
static long f10(long a, long b){ long x=a*b+10; long y=x^(a<<3); if(y>70) y=y-b; else y=y+a; return y+(x>>2); }
static long f11(long a, long b){ long x=a*b+11; long y=x^(a<<3); if(y>77) y=y-b; else y=y+a; return y+(x>>2); }
static long f12(long a, long b){ long x=a*b+12; long y=x^(a<<3); if(y>84) y=y-b; else y=y+a; return y+(x>>2); }
static long f13(long a, long b){ long x=a*b+13; long y=x^(a<<3); if(y>91) y=y-b; else y=y+a; return y+(x>>2); }
static long f14(long a, long b){ long x=a*b+14; long y=x^(a<<3); if(y>98) y=y-b; else y=y+a; return y+(x>>2); }
static long f15(long a, long b){ long x=a*b+15; long y=x^(a<<3); if(y>105) y=y-b; else y=y+a; return y+(x>>2); }
static long f16(long a, long b){ long x=a*b+16; long y=x^(a<<3); if(y>112) y=y-b; else y=y+a; return y+(x>>2); }
static long f17(long a, long b){ long x=a*b+17; long y=x^(a<<3); if(y>119) y=y-b; else y=y+a; return y+(x>>2); }
static long f18(long a, long b){ long x=a*b+18; long y=x^(a<<3); if(y>126) y=y-b; else y=y+a; return y+(x>>2); }
static long f19(long a, long b){ long x=a*b+19; long y=x^(a<<3); if(y>133) y=y-b; else y=y+a; return y+(x>>2); }
int main(void){ long s=0;
 s+=f0(s,3);
 s+=f13(s,16);
 return (int)(s&63); }
