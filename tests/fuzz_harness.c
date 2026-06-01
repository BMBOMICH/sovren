#include "../runtime/runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static void hexdump(const char* label, uint8_t* d, int n) {
    printf("%s: ", label);
    for(int i=0;i<n;i++) printf("%02x",d[i]);
    printf("\n");
}

int main(int argc, char** argv) {
    int iterations = argc > 1 ? atoi(argv[1]) : 1000;
    printf("Sovereign Fuzz Harness v0.1.0\n");
    printf("Running %d iterations...\n\n", iterations);

    srand((unsigned)time(NULL));
    int passed = 0, failed = 0;

    for(int iter = 0; iter < iterations; iter++) {
        int len = rand() % 1024;
        uint8_t* data = (uint8_t*)malloc(len);
        for(int i=0;i<len;i++) data[i] = rand() & 0xFF;

        uint8_t sha256_out[32], sha256_out2[32];
        sov_sha256(data, len, sha256_out);
        sov_sha256(data, len, sha256_out2);
        if(memcmp(sha256_out, sha256_out2, 32) != 0) {
            printf("FAIL: SHA-256 not deterministic at iter %d\n", iter);
            failed++;
        } else {
            passed++;
        }

        uint8_t hmac_out[32], hmac_out2[32];
        uint8_t key[32]; sov_random_bytes(key, 32);
        sov_hmac_sha256(key, 32, data, len, hmac_out);
        sov_hmac_sha256(key, 32, data, len, hmac_out2);
        if(memcmp(hmac_out, hmac_out2, 32) != 0) {
            printf("FAIL: HMAC not deterministic at iter %d\n", iter);
            failed++;
        } else {
            passed++;
        }

        free(data);
    }

    printf("\nResults: %d passed, %d failed\n", passed, failed);
    return failed > 0 ? 1 : 0;
}
