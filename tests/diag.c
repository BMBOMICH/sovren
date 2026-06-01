#include "../runtime/runtime.h"
#include <stdio.h>
#include <string.h>
int main() {
    printf("=== ct_eq fix test ===\n");
    printf("ct_eq(42,42)=%lld (expect 1)\n", (long long)sov_ct_eq(42,42));
    printf("ct_eq(42,43)=%lld (expect 0)\n", (long long)sov_ct_eq(42,43));
    printf("ct_is_zero(0)=%lld (expect 1)\n", (long long)sov_ct_is_zero(0));
    printf("ct_is_zero(1)=%lld (expect 0)\n", (long long)sov_ct_is_zero(1));
    
    printf("\n=== SHA-512 diagnostic ===\n");
    uint8_t out[64];
    sov_sha512("abc", 3, out);
    printf("SHA-512(abc) = ");
    for(int i=0;i<64;i++) printf("%02x", out[i]);
    printf("\nExpected:      ddafl35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f\n");

    printf("\n=== AES-GCM diagnostic ===\n");
    uint8_t key[32]={1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32};
    uint8_t iv[12]={0};
    uint8_t pt[]="Test";
    uint8_t ct[32],tag[16],dec[32];
    sov_result r = sov_aes256_gcm_encrypt(key,iv,12,pt,4,NULL,0,ct,tag);
    printf("Encrypt: %s\n", r.is_ok ? "OK" : "FAIL");
    r = sov_aes256_gcm_decrypt(key,iv,12,ct,4,NULL,0,tag,dec);
    printf("Decrypt: %s\n", r.is_ok ? "OK" : "FAIL");
    if(r.is_ok) printf("Match: %s\n", memcmp(dec,pt,4)==0?"YES":"NO");
    return 0;
}
