/* Speed check: old byte-loop twins (reference style) vs new SWAR twins
 * on a ~6MB synthetic corpus shaped like Sovren source (40-byte lines). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

long cfind1n_swar(const char *s, long st, long lim, int ch);
long pu_find_swar(const char *t, long st, long lim);
long sp_hinc_swar(const char *t, long lim);

static double now(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/* old twin shapes, byte-at-a-time, mirroring the emitted asm loops */
extern long old_cfind1n(const char*,long,long,int);
extern long old_pu(const char*,long,long);
extern long old_sp(const char*,long);

int main(void) {
    size_t N = 6u << 20;
    char *buf = malloc(N + 64);
    /* fill with 40-byte lines of source-ish text */
    const char *word[] = {"x: x + 1","fn_call(a, b)","  indented stmt","return 42"};
    size_t w = 0;
    for (size_t i = 0; i < N; ) {
        const char *s = word[w & 3]; w++;
        size_t l = strlen(s);
        memcpy(buf + i, s, l); i += l;
        if (i < N) buf[i++] = '\n';
    }
    /* sprinkle includes and uses */
    for (int k = 0; k < 400; k++) {
        size_t pos = ((size_t)rand() % (N - 64));
        while (pos && buf[pos-1] != '\n') pos--;
        memcpy(buf + pos, "include inc/x.sov\n", 18);
    }
    memset(buf + N, 0, 64);
    double t0, t1; volatile long sink = 0; int R = 20;

    t0 = now();
    for (int r = 0; r < R; r++) sink += old_sp(buf, N);
    t1 = now(); double old_sp_t = (t1 - t0) / R * 1e3;
    t0 = now();
    for (int r = 0; r < R; r++) sink += sp_hinc_swar(buf, N);
    t1 = now(); double new_sp_t = (t1 - t0) / R * 1e3;

    t0 = now();
    for (int r = 0; r < R; r++) sink += old_pu(buf, 0, N);
    t1 = now(); double old_pu_t = (t1 - t0) / R * 1e3;
    t0 = now();
    for (int r = 0; r < R; r++) sink += pu_find_swar(buf, 0, N);
    t1 = now(); double new_pu_t = (t1 - t0) / R * 1e3;

    /* cfind1n: walk per-line like the callers do */
    t0 = now();
    for (int r = 0; r < R; r++) {
        long i = 0;
        while (i < (long)N) { long e = old_cfind1n(buf, i, N, 10); if (e < 0) break; i = e + 1; }
        sink += i;
    }
    t1 = now(); double old_cf_t = (t1 - t0) / R * 1e3;
    t0 = now();
    for (int r = 0; r < R; r++) {
        long i = 0;
        while (i < (long)N) { long e = cfind1n_swar(buf, i, N, 10); if (e < 0) break; i = e + 1; }
        sink += i;
    }
    t1 = now(); double new_cf_t = (t1 - t0) / R * 1e3;

    printf("sp_inc : old %7.3f ms  new %7.3f ms  (%.1fx)\n", old_sp_t, new_sp_t, old_sp_t/new_sp_t);
    printf("pu_find: old %7.3f ms  new %7.3f ms  (%.1fx)\n", old_pu_t, new_pu_t, old_pu_t/new_pu_t);
    printf("cfind1n: old %7.3f ms  new %7.3f ms  (%.1fx)\n", old_cf_t, new_cf_t, old_cf_t/new_cf_t);
    printf("(sink %ld)\n", (long)sink);
    return 0;
}
