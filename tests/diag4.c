#include "../runtime/runtime.h"
#include <stdio.h>
#include <string.h>
int main() {
    printf("=== BLAKE2s/BLAKE3 test ===\n");
    uint8_t out[32];
    sov_blake3("", 0, out);
    printf("BLAKE3(''): ");
    for(int i=0;i<32;i++) printf("%02x",out[i]);
    printf("\nExpected BLAKE3: af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262\n");
    
    sov_blake3("abc", 3, out);
    printf("BLAKE3(abc): ");
    for(int i=0;i<32;i++) printf("%02x",out[i]);
    printf("\nExpected BLAKE3: 6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85\n");
    return 0;
}
