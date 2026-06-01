#include "../runtime/runtime.h"
#include <stdio.h>
#include <string.h>
int main() {
    uint8_t out[32];
    
    sov_blake2s("",0,out); printf("''  : "); for(int i=0;i<8;i++)printf("%02x",out[i]); printf("\n");
    sov_blake2s("a",1,out); printf("'a' : "); for(int i=0;i<8;i++)printf("%02x",out[i]); printf("\n");
    sov_blake2s("ab",2,out); printf("'ab': "); for(int i=0;i<8;i++)printf("%02x",out[i]); printf("\n");
    sov_blake2s("abc",3,out); printf("'abc':"); for(int i=0;i<8;i++)printf("%02x",out[i]); printf("\n");
    
    uint8_t buf[64]={0};
    memcpy(buf,"abc",3);
    printf("buf[0]=%02x buf[1]=%02x buf[2]=%02x buf[3]=%02x\n",buf[0],buf[1],buf[2],buf[3]);
    return 0;
}
