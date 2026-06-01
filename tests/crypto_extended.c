#include "../runtime/runtime.h"
#include <stdio.h>
#include <string.h>
#include <assert.h>

void hexprint(const char* label, uint8_t* d, int len) {
    printf("%s: ", label);
    for(int i=0;i<len;i++) printf("%02x",d[i]);
    printf("\n");
}

int main(void) {
    printf("=== Extended Crypto Tests ===\n\n");

    printf("HKDF-SHA256 (deterministic)...\n");
    {
        uint8_t ikm[]="test", salt[]="salt", info[]="info", out[32], out2[32];
        sov_hkdf_sha256(salt,4,ikm,4,info,4,out,32);
        sov_hkdf_sha256(salt,4,ikm,4,info,4,out2,32);
        assert(memcmp(out,out2,32)==0);
        printf("  PASS\n");
    }

    printf("PBKDF2-SHA256...\n");
    {
        uint8_t pass[]="password", salt[]="salt", out[32], out2[32];
        sov_pbkdf2_sha256(pass,8,salt,4,1,out,32);
        sov_pbkdf2_sha256(pass,8,salt,4,1,out2,32);
        assert(memcmp(out,out2,32)==0);
        sov_pbkdf2_sha256(pass,8,salt,4,1000,out2,32);
        assert(memcmp(out,out2,32)!=0);
        printf("  PASS\n");
    }

    printf("AES-GCM tamper detection...\n");
    {
        uint8_t k[32]={1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32};
        uint8_t iv[12]={0}, pt[]="Secret", ct[32], tag[16], dec[32];
        sov_aes256_gcm_encrypt(k,iv,12,pt,6,NULL,0,ct,tag);
        ct[0]^=1;
        sov_result r=sov_aes256_gcm_decrypt(k,iv,12,ct,6,NULL,0,tag,dec);
        assert(!r.is_ok);
        printf("  PASS\n");
    }

    printf("ChaCha20-Poly1305 tamper...\n");
    {
        uint8_t k[32]={1}, n[12]={0}, pt[]="Test", ct[32], tag[16], dec[32];
        sov_chacha20_poly1305_encrypt(k,n,pt,4,NULL,0,ct,tag);
        ct[0]^=1;
        sov_result r=sov_chacha20_poly1305_decrypt(k,n,ct,4,NULL,0,tag,dec);
        assert(!r.is_ok);
        printf("  PASS\n");
    }

    printf("SHA-512 long input...\n");
    {
        uint8_t out[64];
        char data[128]; memset(data,'a',128);
        sov_sha512(data,128,out);
        uint8_t e1[64]; sov_sha512(data,128,e1);
        assert(memcmp(out,e1,64)==0);
        printf("  PASS\n");
    }

    printf("Random range...\n");
    {
        int ok=1;
        for(int i=0;i<100;i++){sov_u64 v=sov_random_range(10,20);if(v<10||v>20)ok=0;}
        assert(ok);
        printf("  PASS\n");
    }

    printf("ct_memmove...\n");
    {
        uint8_t d[8]={0}, s[8]={1,2,3,4,5,6,7,8};
        sov_ct_memmove(d,s,8,true);
        assert(memcmp(d,s,8)==0);
        memset(d,0,8);
        sov_ct_memmove(d,s,8,false);
        assert(d[0]==0);
        printf("  PASS\n");
    }

    printf("\n=== ALL EXTENDED TESTS PASSED ===\n");
    return 0;
}
