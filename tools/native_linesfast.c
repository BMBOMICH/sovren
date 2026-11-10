/* Native lines_of_fast: the reader's line splitter, C port.
 * 1:1 mirror of lines_of_fast in compilers/linux/compiler.sov: one
 * traversal copies the source into the flat buffer while splitting on
 * '\n' (qword SWAR haszero test, per-byte walk only inside a hit qword),
 * then writes the [cap][len][ptrs...] list.  length() semantics first:
 * a source below 4096 (small-int or negative) answers the empty list via
 * the table's _sov_list_new, byte-identical to the interpreted head.
 * The two allocations stay table calls with the Sovren ABI (rdi = size;
 * rax = pointer).  Table layout: slot 1 = _sov_list_new, slot 2 =
 * _sov_heap_alloc; slot 0 = slot count.
 * No external symbols, no relocations, no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef long long S;
typedef U (*F0)(void);
typedef U (*F1)(U);

enum { T_LISTNEW = 1, T_ALLOC = 2 };

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1f(U *t, U i, U a){ return ((F1)t[i])(a); }

U lines_of_fast_native(U src, U tbl){
    U *t = (U*)tbl;
    S n = 0;
    if ((S)src >= 4096){
        const unsigned char *s = (const unsigned char*)src;
        while (s[n]) n++;
    }
    if (n <= 0)
        return t0(t, T_LISTNEW);
    U un = (U)n;
    U flat = t1f(t, T_ALLOC, un + 1);
    U lst = t1f(t, T_ALLOC, 16 + (un + 1) * 8);
    *(U*)(lst) = un + 1;
    const unsigned char *s = (const unsigned char*)src;
    unsigned char *f = (unsigned char*)flat;
    U i = 0, start = 0, k = 0;
    while (i + 8 <= un){
        U q;
        {
            const unsigned char *p = s + i;
            q = (U)p[0] | ((U)p[1] << 8) | ((U)p[2] << 16) | ((U)p[3] << 24)
              | ((U)p[4] << 32) | ((U)p[5] << 40) | ((U)p[6] << 48) | ((U)p[7] << 56);
        }
        {
            unsigned char *p = f + i;
            p[0] = (unsigned char)q; p[1] = (unsigned char)(q >> 8);
            p[2] = (unsigned char)(q >> 16); p[3] = (unsigned char)(q >> 24);
            p[4] = (unsigned char)(q >> 32); p[5] = (unsigned char)(q >> 40);
            p[6] = (unsigned char)(q >> 48); p[7] = (unsigned char)(q >> 56);
        }
        U x = q ^ 0x0A0A0A0A0A0A0A0AULL;
        U m = (x - 0x0101010101010101ULL) & ~x & 0x8080808080808080ULL;
        if (m){
            U j = 0;
            while (j < 8){
                if (f[i + j] == 10){
                    f[i + j] = 0;
                    *(U*)(lst + 16 + k * 8) = flat + start;
                    k++;
                    start = i + j + 1;
                }
                j++;
            }
        }
        i += 8;
    }
    while (i < un){
        unsigned char c = s[i];
        f[i] = c;
        if (c == 10){
            f[i] = 0;
            *(U*)(lst + 16 + k * 8) = flat + start;
            k++;
            start = i + 1;
        }
        i++;
    }
    f[un] = 0;
    if (start < un){
        *(U*)(lst + 16 + k * 8) = flat + start;
        k++;
    }
    *(U*)(lst + 8) = k;
    return lst;
}
