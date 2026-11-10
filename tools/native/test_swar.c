/* Differential test: SWAR twins vs reference implementations mirroring the
 * exact old-twin semantics. Exhaustive randomized + adversarial edge cases. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

long cfind1n_swar(const char *s, long st, long lim, int ch);
long pu_find_swar(const char *t, long st, long lim);
long sp_hinc_swar(const char *t, long lim);

/* reference cfind1n: old twin semantics — s==0 -> 0, else first idx in
 * [st,lim) with byte==ch else -1 */
static long ref_cfind1n(const char *s, long st, long lim, int ch) {
    if (!s) return 0;
    for (long i = st; i < lim; i++) if (s[i] == (char)ch) return i;
    return -1;
}
/* reference pu_find_use: exact Sovren walk */
static long ref_pu(const char *t, long st, long lim) {
    long i = st;
    while (i < lim) {
        long j = i;
        while (1) {
            if (j >= lim) break;
            unsigned char b = (unsigned char)t[j];
            if (b == 32 || b == 9 || b == 13) j++;
            else break;
        }
        if (j + 3 < lim) {
            if (t[j]==117 && t[j+1]==115 && t[j+2]==101) {
                unsigned char b3 = (unsigned char)t[j+3];
                if (b3 == 32 || b3 == 58) return j;
            }
        }
        long e = -1;
        for (long k = i; k < lim; k++) if (t[k]==10) { e = k; break; }
        if (e < 0) return -1;
        i = e + 1;
    }
    return -1;
}
/* reference sp_hinc_lim: exact Sovren walk bounded by lim */
static long ref_sp(const char *t, long lim) {
    long i = 0;
    while (i < lim) {
        long j = i;
        while (1) {
            if (j >= lim) break;
            unsigned char b = (unsigned char)t[j];
            if (b == 32 || b == 9 || b == 13) j++;
            else break;
        }
        if (j + 8 <= lim) {
            if (memcmp(t + j, "include ", 8) == 0) return 1;
        }
        long e = -1;
        for (long k = i; k < lim; k++) if (t[k]==10) { e = k; break; }
        if (e < 0) return 0;
        i = e + 1;
    }
    return 0;
}

static uint64_t rng = 0x243F6A8885A308D3ULL;
static uint64_t rnd(void) {
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    return rng;
}

static int fails = 0;
static void chk(const char *what, long got, long want, const char *buf, long a, long b, int c) {
    if (got != want) {
        fails++;
        if (fails < 25)
            printf("FAIL %s got=%ld want=%ld args(%ld,%ld,%d) buf=[%.*s]\n",
                   what, got, want, a, b, c, (int)(b > 60 ? 60 : b), buf ? buf : "(null)");
    }
}

int main(void) {
    /* cfind1n: null */
    chk("cfind-null", cfind1n_swar(0, 0, 10, 10), ref_cfind1n(0, 0, 10, 10), 0, 0, 10, 10);

    char buf[4096];
    /* randomized small alphabets incl. target char and 0x80/0xFF bytes */
    for (int iter = 0; iter < 200000; iter++) {
        int n = (int)(rnd() % 200);
        int alpha = 2 + (int)(rnd() % 4);   /* tiny alphabet: lots of collisions */
        int ch;
        switch (rnd() % 5) {
            case 0: ch = 10; break;
            case 1: ch = 0; break;
            case 2: ch = (int)(rnd() & 0xFF); break;
            case 3: ch = 0x80; break;
            default: ch = (int)(rnd() % 3) + 32; break;
        }
        for (int i = 0; i < n; i++) {
            uint64_t r = rnd();
            unsigned char v;
            switch (alpha) {
                case 2: v = (r & 1) ? (unsigned char)ch : (unsigned char)(0x41 + (r & 3)); break;
                case 3: v = (unsigned char)(r % 3 == 0 ? ch : (r % 3 == 1 ? 0x80 : 10)); break;
                default: v = (unsigned char)(r & 0xFF); break;
            }
            /* keep NULs only where intended? cfind1n is NUL-transparent: the
             * reference scans bytes regardless, so any byte is fine. */
            buf[i] = (char)v;
        }
        long st = (long)(rnd() % (n + 3)) - 1;   /* allow st slightly <0 and >n */
        long lim = (long)(rnd() % (n + 3)) - 1;
        if (st < 0) st = 0;
        if (rnd() & 1) lim = n; else if (lim < st) { long t = st; st = lim; lim = t; }
        if (lim > n) lim = n + 1;  /* one-past reads are NOT allowed: clamp */
        if (lim > n) lim = n;
        chk("cfind", cfind1n_swar(buf, st, lim, ch), ref_cfind1n(buf, st, lim, ch), buf, st, lim, ch);
    }

    /* pu_find + sp_hinc: alphabets over {' ', '\t', '\r', '\n', 'u','s','e',':','i','n','c','l','d', x} */
    const char alph[] = " \t\r\nuse:incldx";
    for (int iter = 0; iter < 200000; iter++) {
        int n = (int)(rnd() % 300);
        for (int i = 0; i < n; i++) buf[i] = alph[rnd() % (sizeof(alph) - 1)];
        long st = (long)(rnd() % (n + 1));
        long lim = (rnd() & 1) ? n : (long)(rnd() % (n + 1));
        if (lim < st) lim = st;
        chk("pu", pu_find_swar(buf, st, lim), ref_pu(buf, st, lim), buf, st, lim, 0);
        chk("sp", sp_hinc_swar(buf, lim), ref_sp(buf, lim), buf, 0, lim, 0);
    }

    /* targeted edges */
    strcpy(buf, "include ");           /* exact 8, no newline */
    chk("sp-exact8", sp_hinc_swar(buf, 8), ref_sp(buf, 8), buf, 0, 8, 0);
    strcpy(buf, " include x");         /* indented */
    chk("sp-ind", sp_hinc_swar(buf, 11), ref_sp(buf, 11), buf, 0, 11, 0);
    strcpy(buf, "includex");
    chk("sp-tail7", sp_hinc_swar(buf, 9), ref_sp(buf, 9), buf, 0, 9, 0);
    strcpy(buf, "x\n\n  \t\r include y\nz");
    chk("sp-wsmix", sp_hinc_swar(buf, 22), ref_sp(buf, 22), buf, 0, 22, 0);
    strcpy(buf, "  \t\r  ");           /* all ws */
    chk("sp-allws", sp_hinc_swar(buf, 6), ref_sp(buf, 6), buf, 0, 6, 0);
    strcpy(buf, "use x\nno\n use: y");
    chk("pu-ind", pu_find_swar(buf, 0, 18), ref_pu(buf, 0, 18), buf, 0, 18, 0);
    strcpy(buf, "abc\nuse");
    chk("pu-tail3", pu_find_swar(buf, 0, 7), ref_pu(buf, 0, 7), buf, 0, 7, 0);
    strcpy(buf, "abc\nuse\n");
    chk("pu-tail4", pu_find_swar(buf, 0, 8), ref_pu(buf, 0, 8), buf, 0, 8, 0);
    strcpy(buf, "\r use: z");
    chk("pu-cr", pu_find_swar(buf, 0, 8), ref_pu(buf, 0, 8), buf, 0, 8, 0);
    /* long unaligned lines crossing qword boundaries */
    memset(buf, 'a', 4000);
    for (int off = 0; off < 64; off++) {
        long p = 300 + off;
        buf[p] = '\n';
        memcpy(buf + p + 1, "   include q", 12);
        buf[p + 13] = '\n';
        chk("sp-un", sp_hinc_swar(buf, 4000), ref_sp(buf, 4000), buf, 0, 4000, 0);
        buf[p + 4] = 'x';   /* break it */
        chk("sp-un2", sp_hinc_swar(buf, 4000), ref_sp(buf, 4000), buf, 0, 4000, 0);
        buf[p + 4] = 'i';
        buf[p] = 'a';
        buf[p + 13] = 'a';
    }
    /* 0x80/0xFF bytes near patterns (SWAR borrow edge) */
    for (int iter = 0; iter < 50000; iter++) {
        int n = 8 + (int)(rnd() % 24);
        for (int i = 0; i < n; i++) {
            uint64_t r = rnd();
            buf[i] = (char)(r % 4 == 0 ? 0x80 : r % 4 == 1 ? 0xFF : r % 4 == 2 ? 10 : (r & 0x0F) + 32);
        }
        chk("hi-pu", pu_find_swar(buf, 0, n), ref_pu(buf, 0, n), buf, 0, n, 0);
        chk("hi-sp", sp_hinc_swar(buf, n), ref_sp(buf, n), buf, 0, n, 0);
        int ch = (int)(rnd() & 0xFF);
        chk("hi-cf", cfind1n_swar(buf, 0, n, ch), ref_cfind1n(buf, 0, n, ch), buf, 0, n, ch);
    }

    if (fails) { printf("%d FAILURES\n", fails); return 1; }
    printf("ALL SWAR TWIN TESTS PASS\n");
    return 0;
}
