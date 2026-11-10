/* Cold one-shot driver for the C.2-C.8 fused-frontend A/B.  Each invocation
 * is a fresh process: no warm-up, no cache, no persisted intermediate. */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "native_fused_frontend.c"

extern volatile uint64_t g_sink;
extern volatile uint64_t g_source_len;

int main(int argc, char **argv) {
    if (argc != 5) {
        fprintf(stderr, "usage: driver IN OUT SRC_CAP OUT_CAP\n");
        return 2;
    }
    const char *in = argv[1], *out = argv[2];
    uint64_t src_cap = strtoull(argv[3], 0, 10);
    uint64_t out_cap = strtoull(argv[4], 0, 10);
    unsigned char *srcbuf = (unsigned char *)malloc(src_cap);
    unsigned char *outbuf = (unsigned char *)malloc(out_cap);
    if (!srcbuf || !outbuf) return 3;
    Stats st;
    uint64_t image_len = 0, exit_code = 0;
    struct timespec a, b;
    clock_gettime(CLOCK_MONOTONIC, &a);
    int64_t rc = fused_compile_file(in, out, srcbuf, src_cap,
                                    outbuf, out_cap, &st,
                                    &image_len, &exit_code);
    clock_gettime(CLOCK_MONOTONIC, &b);
    uint64_t ns = (uint64_t)(b.tv_sec - a.tv_sec) * 1000000000ULL +
                  (uint64_t)(b.tv_nsec - a.tv_nsec);
    printf("rc=%lld elapsed_ns=%llu source_len=%llu image_len=%llu "
           "exit_code=%llu read_calls=%llu source_scans=%llu "
           "lexical_passes=%llu malloc_calls=%llu write_calls=%llu "
           "lseek_calls=%llu string_compare_calls=%llu dynamic_calls=%llu "
           "fixup_count=%llu relaxation_rounds=%llu ids=%llu "
           "allocations=%llu sink=%llu\n",
           (long long)rc, (unsigned long long)ns,
           (unsigned long long)g_source_len,
           (unsigned long long)image_len, (unsigned long long)exit_code,
           (unsigned long long)st.read_calls,
           (unsigned long long)st.source_scans,
           (unsigned long long)st.lexical_passes,
           (unsigned long long)st.malloc_calls,
           (unsigned long long)st.write_calls,
           (unsigned long long)st.lseek_calls,
           (unsigned long long)st.string_compare_calls,
           (unsigned long long)st.dynamic_calls,
           (unsigned long long)st.fixup_count,
           (unsigned long long)st.relaxation_rounds,
           (unsigned long long)st.ids,
           (unsigned long long)st.allocations,
           (unsigned long long)g_sink);
    free(srcbuf); free(outbuf);
    return rc == 0 ? 0 : 1;
}
