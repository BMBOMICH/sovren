/* Native kgrow_ht — C port of kgrow_ht in compilers/shared/cx86_p1.sov.
 * Doubles the kid intern table and re-inserts every tabled string by hash.
 * Walks the OLD TABLE (not the pool): the pointers already handed out stay
 * the canonical ones, so pointer-identity comparisons survive growth.  The
 * hash is the same djb2 (5381, h*33+b) the interpreted rehash uses, and the
 * probe is the same linear sequence, so the resulting table layout is
 * identical.  >64KiB allocations are fresh mmaps (kernel-zeroed); smaller
 * ones are zeroed here (the interpreted _sov_bzero's job).
 * State sync is one publish per growth: kg_pub sets kid_ht and kid_slots
 * together, exactly the two globals the interpreted tail assigns.
 * Entry: rdi = kg_tbl (4 slots).  Returns 1 like the Sovren body.
 * Sovren compares are SIGNED.  No external symbols/relocs/static state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef long long L;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);

enum { T_KH = 1, T_KS = 2, T_ALLOC = 3, T_PUB = 4 };

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }

U kgrow_native(U tbl){
    U *t = (U*)tbl;
    U ht = t0(t, T_KH);
    U slots = t0(t, T_KS);
    U ns = slots + slots;
    U nht = t1(t, T_ALLOC, slots * 16);
    if (slots * 16 <= 65536){
        unsigned char *z = (unsigned char*)nht;
        for (U i = 0; i < slots * 16; i++) z[i] = 0;
    }
    U mask = ns - 1;
    for (U oi = 0; oi < slots; oi++){
        U sp = *(U*)(ht + oi * 8);
        if (sp != 0){
            U h = 5381;
            const unsigned char *p = (const unsigned char*)sp;
            U k = 0;
            while (p[k]){ h = h * 33 + p[k]; k++; }
            U slot = h & mask;
            for (U g = 0; g < ns; g++){
                U ex = *(U*)(nht + slot * 8);
                if (ex == 0){
                    *(U*)(nht + slot * 8) = sp;
                    break;
                }
                slot++;
                if (slot == ns) slot = 0;
            }
        }
    }
    t2(t, T_PUB, nht, ns);
    return 1;
}
