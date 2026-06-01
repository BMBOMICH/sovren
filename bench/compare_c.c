/*
 * Sovereign vs C Performance Comparison
 * 
 * This file is the C equivalent of the Sovereign benchmarks.
 * Compile: gcc -O2 bench_compare.c -o bench_c -lm
 * Run:     ./bench_c
 * 
 * Compare with:
 *   Sovereign (C backend):  sovereign build tests/bench_performance.sov && gcc -O2 output.c runtime/runtime.c -o bench_sov && ./bench_sov
 *   Sovereign (LLVM backend): sovereign build tests/bench_performance.sov --target llvm && llc -O3 output.ll && clang -O2 output.s runtime/runtime.c -o bench_sov_llvm && ./bench_sov_llvm
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdint.h>

/* ── Timing helper ─────────────────────────────────────────────────────── */

static double get_time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1000000.0;
}

#define BENCH(name, expr) do { \
    double start = get_time_ms(); \
    expr; \
    double end = get_time_ms(); \
    printf("  %-35s %8.2f ms\n", name, end - start); \
} while(0)

/* ── Fibonacci ──────────────────────────────────────────────────────────── */

static int64_t fib(int64_t n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

/* ── Matrix Multiplication ──────────────────────────────────────────────── */

static void matrix_multiply(int64_t* a, int64_t* b, int64_t* c, int n) {
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            int64_t sum = 0;
            for (int k = 0; k < n; k++) {
                sum += a[i * n + k] * b[k * n + j];
            }
            c[i * n + j] = sum;
        }
    }
}

/* ── Prime Sieve ────────────────────────────────────────────────────────── */

static int sieve_count(int n) {
    char* is_prime = (char*)calloc(n + 1, 1);
    for (int i = 2; i <= n; i++) is_prime[i] = 1;
    
    for (int i = 2; i <= n; i++) {
        if (is_prime[i]) {
            for (int j = i * 2; j <= n; j += i) {
                is_prime[j] = 0;
            }
        }
    }
    
    int count = 0;
    for (int i = 2; i <= n; i++) {
        if (is_prime[i]) count++;
    }
    
    free(is_prime);
    return count;
}

/* ── String Operations ──────────────────────────────────────────────────── */

static char* str_repeat(const char* s, int n) {
    size_t len = strlen(s);
    char* result = (char*)malloc(len * n + 1);
    for (int i = 0; i < n; i++) {
        memcpy(result + i * len, s, len);
    }
    result[len * n] = '\0';
    return result;
}

/* ── Main ───────────────────────────────────────────────────────────────── */

int main(void) {
    printf("╔══════════════════════════════════════════╗\n");
    printf("║     C Performance Baseline               ║\n");
    printf("╚══════════════════════════════════════════╝\n\n");
    
    /* Fibonacci */
    printf("── Fibonacci ──────────────────────────\n");
    {
        int64_t r;
        BENCH("fib(30)", r = fib(30));
        printf("    result: %lld (expected: 832040)\n", (long long)r);
    }
    {
        int64_t r;
        BENCH("fib(35)", r = fib(35));
        printf("    result: %lld (expected: 9227465)\n", (long long)r);
    }
    {
        int64_t r;
        BENCH("fib(40)", r = fib(40));
        printf("    result: %lld (expected: 102334155)\n", (long long)r);
    }
    
    /* Matrix Multiplication */
    printf("\n── Matrix Multiplication ──────────────\n");
    {
        const int n = 200;
        int64_t* a = (int64_t*)calloc(n * n, sizeof(int64_t));
        int64_t* b = (int64_t*)calloc(n * n, sizeof(int64_t));
        int64_t* c = (int64_t*)calloc(n * n, sizeof(int64_t));
        for (int i = 0; i < n * n; i++) {
            a[i] = i % 100;
            b[i] = (i + 50) % 100;
        }
        BENCH("matrix 200x200", matrix_multiply(a, b, c, n));
        free(a); free(b); free(c);
    }
    
    /* Prime Sieve */
    printf("\n── Prime Sieve ────────────────────────\n");
    {
        int count;
        BENCH("sieve(100000)", count = sieve_count(100000));
        printf("    count: %d (expected: 9592)\n", count);
    }
    
    /* String Operations */
    printf("\n── String Operations ──────────────────\n");
    {
        char* haystack;
        BENCH("repeat 100K", haystack = str_repeat("abcdefghij", 10000));
        BENCH("strstr 100K", { volatile char* p = strstr(haystack, "ghij"); (void)p; });
        free(haystack);
    }
    
    /* Memory Allocation */
    printf("\n── Memory Allocation ──────────────────\n");
    BENCH("malloc/free 100K", {
        for (int i = 0; i < 100000; i++) {
            void* p = malloc(64);
            free(p);
        }
    });
    
    printf("\n╔══════════════════════════════════════════╗\n");
    printf("║  C baseline complete                     ║\n");
    printf("╚══════════════════════════════════════════╝\n");
    
    return 0;
}
