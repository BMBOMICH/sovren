#include "../runtime/runtime.h"
#include <stdio.h>
#include <string.h>

void hexdump(const char* label, uint8_t* d, int len) {
    printf("%s: ", label);
    for(int i=0;i<len;i++) printf("%02x",d[i]);
    printf("\n");
}

int main() {
    uint8_t key[32]={1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32};
    uint8_t iv[12]={1,2,3,4,5,6,7,8,9,10,11,12};
    uint8_t pt[]="Test", ct[32], tag1[16], tag2[16], dec[32];

    sov_result r1 = sov_aes256_gcm_encrypt(key,iv,12,pt,4,NULL,0,ct,tag1);
    printf("Encrypt: %s\n", r1.is_ok?"OK":"FAIL");
    hexdump("Tag1", tag1, 16);

    sov_result r2 = sov_aes256_gcm_encrypt(key,iv,12,pt,4,NULL,0,ct,tag2);
    printf("Re-encrypt: %s\n", r2.is_ok?"OK":"FAIL");
    hexdump("Tag2", tag2, 16);
    printf("Tags match: %s\n", memcmp(tag1,tag2,16)==0?"YES":"NO");

    sov_result r3 = sov_aes256_gcm_decrypt(key,iv,12,ct,4,NULL,0,tag1,dec);
    printf("Decrypt with tag1: %s\n", r3.is_ok?"OK":"FAIL");
    if(r3.is_ok) printf("Match: %s\n", memcmp(dec,pt,4)==0?"YES":"NO");

    return 0;
}
