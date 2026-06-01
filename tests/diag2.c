#include "../runtime/runtime.h"
#include <stdio.h>
#include <string.h>
int main() {
    printf("=== SHA-512 empty string ===\n");
    uint8_t out[64];
    sov_sha512("", 0, out);
    for(int i=0;i<64;i++) printf("%02x", out[i]);
    printf("\nExpected: cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e\n");

    printf("\n=== AES-GCM with non-zero key ===\n");
    uint8_t key[32]={1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32};
    uint8_t iv[12]={1,2,3,4,5,6,7,8,9,10,11,12};
    uint8_t pt[]="Hello World";
    uint8_t ct[32],tag[16],dec[32];
    sov_result r = sov_aes256_gcm_encrypt(key,iv,12,pt,11,NULL,0,ct,tag);
    printf("Encrypt: %s tag=", r.is_ok?"OK":"FAIL");
    for(int i=0;i<16;i++) printf("%02x",tag[i]);
    printf("\n");
    r = sov_aes256_gcm_decrypt(key,iv,12,ct,11,NULL,0,tag,dec);
    printf("Decrypt: %s\n", r.is_ok?"OK":"FAIL");
    if(r.is_ok) printf("Match: %s\n", memcmp(dec,pt,11)==0?"YES":"NO");
    return 0;
}
