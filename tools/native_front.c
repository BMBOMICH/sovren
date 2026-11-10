/* native_front.c -- C.2/C.9/C.11/C.15 fused front-end need scan.
 *
 * ONE bounded SWAR pass replaces six whole-source look(src, needle)
 * runtime-need probes. Early-exits on the first hit, exactly like the
 * short-circuited `if need is 0` chain it replaces.
 *
 * The first version walked byte-at-a-time and cost 7.2 ms on 4 MB (2x
 * slower than the six SWAR find_text calls it replaced). This version
 * filters candidate first bytes ('_','l','p','s','j') eight at a time with
 * the hasvalue SWAR mask and only runs the detailed needle comparisons on
 * a hit. It also receives the source length explicitly so no read ever
 * crosses the buffer end and no NUL terminator is required.
 *
 * u_prep keeps its own `look(source,"unsafe:")` first gate: that call is a
 * native SWAR find_text and is already fast, so there is nothing to fuse.
 *
 * Pure leaf: no calls, no static mutable state, no string literals (those
 * would create .rodata relocations, forbidden by the blob builder), no libc.
 * Cold only, nothing persisted between runs.
 */
#include <stdint.h>
typedef uint64_t U;

static inline U load8(const unsigned char *p)
{
    return (U)p[0] | ((U)p[1] << 8) | ((U)p[2] << 16) | ((U)p[3] << 24)
         | ((U)p[4] << 32) | ((U)p[5] << 40) | ((U)p[6] << 48) | ((U)p[7] << 56);
}

static inline U eqmask(U q, U c)
{
    U b = c * 0x0101010101010101ULL;
    U x = q ^ b;
    return (x - 0x0101010101010101ULL) & ~x & 0x8080808080808080ULL;
}

/* Exact decision at byte position p; every read is bounded by n. */
static inline int chk(const unsigned char *s, U p, U n)
{
    unsigned char c = s[p];
    if (c == 95) {                                        /* _sov_ */
        return p + 5 <= n && s[p+1] == 115 && s[p+2] == 111 &&
               s[p+3] == 118 && s[p+4] == 95;
    }
    if (c == 108) {                                      /* load_file */
        return p + 9 <= n && s[p+1] == 111 && s[p+2] == 97 &&
               s[p+3] == 100 && s[p+4] == 95 && s[p+5] == 102 &&
               s[p+6] == 105 && s[p+7] == 108 && s[p+8] == 101;
    }
    if (c == 112) {                                      /* peek_ / poke_ */
        return p + 5 <= n &&
               ((s[p+1] == 101 && s[p+2] == 101 && s[p+3] == 107 && s[p+4] == 95) ||
                (s[p+1] == 111 && s[p+2] == 107 && s[p+3] == 101 && s[p+4] == 95));
    }
    if (c == 115) {                                      /* "spawn " */
        return p + 6 <= n && s[p+1] == 112 && s[p+2] == 97 &&
               s[p+3] == 119 && s[p+4] == 110 && s[p+5] == 32;
    }
    if (c == 106) {                                      /* "join " */
        return p + 5 <= n && s[p+1] == 111 && s[p+2] == 105 &&
               s[p+3] == 110 && s[p+4] == 32;
    }
    return 0;
}

U front_scan_native(U src, U n)
{
    const unsigned char *s = (const unsigned char *)src;
    U i = 0;
    while (i + 8 <= n) {
        U q = load8(s + i);
        U m = eqmask(q, 95) | eqmask(q, 108) | eqmask(q, 112)
            | eqmask(q, 115) | eqmask(q, 106);
        while (m) {
            U p = i + (U)(__builtin_ctzll(m) >> 3);
            m &= m - 1;
            if (chk(s, p, n)) return 1;
        }
        i += 8;
    }
    for (; i < n; i++)
        if (chk(s, i, n)) return 1;
    return 0;
}
