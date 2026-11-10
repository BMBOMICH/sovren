/* C.4/C.5 — ONE INTERNER WITH STABLE IDs + ID/HASH DISPATCH (prototype).
 *
 * This is a certified prototype core, NOT installed compiler code.  It
 * replaces the string-keyed dispatch / 4,096-slot hash / 256 KiB name-table
 * zero-fill model with:
 *
 *   - a PRE-SIZED power-of-two open-addressed table supplied by the caller;
 *   - STABLE integer IDs (1..n; 0 = empty slot);
 *   - INLINE <=8-byte names packed into a uint64_t, with length kept for
 *     exact compare; long names are FNV-1a hashed and compared byte-for-byte
 *     ONLY on a hash-slot hit;
 *   - ID/HASH dispatch (`id_dispatch`) with zero string comparisons.
 *
 * No libc, no malloc, no memset/memcpy, no static mutable state, no external
 * symbols in the NO_BASELINE translation unit (used for the relocation-free
 * Sovren twin).  The BASELINE model (string-compare chain + 4,096-slot hash
 * + 256 KiB zero-filled name table) is compiled only into the harness .so
 * for the core-level A/B, guarded by NO_BASELINE.
 *
 * A BROKEN_INTERN build skips the exact compare on a hash-slot hit, so the
 * gate can find a minimised counterexample BEFORE certifying the fixed core.
 *
 * Build (harness): gcc -O2 -fPIC -shared native_stable_interner.c -o lib.so
 * Build (twin):    tools/native/build_native_reader.py --source this file
 *                  --entry intern_lookup_or_add --symbol emit_nt_intern
 */
#include <stdint.h>

typedef uint64_t U;
typedef uint8_t u8;

typedef struct {
    U *table;                 /* cap slots, 0 = empty, else id+1            */
    U cap;                    /* power of two                               */
    U *inl;                   /* packed <=8-byte key, per id                */
    U *len;                   /* name length, per id                        */
    const unsigned char **ptr;/* original bytes, per id (for long compare)  */
    U n;                      /* number of interned names                   */
    U max;                    /* capacity of inl/len/ptr                    */
} Interner;

static inline U fnv1a(const unsigned char *s, U n) {
    U h = 14695981039346656037ULL;
    for (U i = 0; i < n; i++) {
        h ^= (U)s[i];
        h *= 1099511628211ULL;
    }
    return h;
}

static inline U pack8(const unsigned char *s, U n) {
    U k = 0;
    U m = n < 8 ? n : 8;
    for (U i = 0; i < m; i++) k |= (U)s[i] << (8 * i);
    return k;
}

static inline int bytes_eq(const unsigned char *a, const unsigned char *b, U n) {
    for (U i = 0; i < n; i++) if (a[i] != b[i]) return 0;
    return 1;
}

/* Zero ONLY the probe table; the per-ID arrays are uninitialised until their
 * id is created.  The caller pre-sizes cap from the expected name count, so
 * there is no fixed 256 KiB zero-fill band. */
void intern_init(Interner *it) {
    for (U i = 0; i < it->cap; i++) it->table[i] = 0;
    it->n = 0;
}

/* Returns a STABLE id (1..n), or 0 if the caller's capacity is exhausted. */
U intern_lookup_or_add(Interner *it, const unsigned char *name, U len) {
    if (!it || !name || it->cap == 0 || (it->cap & (it->cap - 1)) != 0) return 0;
    U key = pack8(name, len);
    U h = fnv1a(name, len);
    U idx = h & (it->cap - 1);
    for (U probe = 0; probe < it->cap; probe++) {
        U slot = it->table[idx];
        if (slot == 0) {
            if (it->n >= it->max) return 0;
            U id = it->n + 1;
            it->inl[it->n] = key;
            it->len[it->n] = len;
            it->ptr[it->n] = name;
            it->table[idx] = id;
            it->n = id;
            return id;
        }
        U e = slot - 1;
#ifdef BROKEN_INTERN
        /* Deliberately WRONG: skip exact compare on a hash-slot hit. */
        return slot;
#else
        if (it->len[e] == len) {
            if (len <= 8) {
                if (it->inl[e] == key) return slot;
            } else if (bytes_eq(it->ptr[e], name, len)) {
                return slot;
            }
        }
#endif
        idx = (idx + 1) & (it->cap - 1);
    }
    return 0;
}

/* C.5: ID/hash dispatch.  No name, no string compare, no allocation. */
U id_dispatch(U id, U hash) {
    return (hash ^ (id * 0x9e3779b97f4a7c15ULL)) & 7ULL;
}

U intern_hash(const unsigned char *s, U n) {
    return fnv1a(s, n);
}

#ifndef NO_BASELINE
/* ---------------- Harness-only baseline model (NOT in the twin) ---------- */
#include <stdlib.h>
#include <string.h>

typedef struct {
    U *ht;                 /* 4,096 slots                                  */
    unsigned char *nt;     /* 256 KiB zero-filled name table               */
    const unsigned char **names;
    U *lens;
    U n, max;
} Baseline;

static const char *KW[8] = {
    "main", "return", "if", "use", "include", "emit", "print", "while"
};

void baseline_reset(Baseline *b);
void baseline_init(Baseline *b, U max) {
    b->ht = (U *)malloc(4096 * sizeof(U));
    b->nt = (unsigned char *)malloc(262144);
    b->names = (const unsigned char **)malloc(max * sizeof(void *));
    b->lens = (U *)malloc(max * sizeof(U));
    b->n = 0; b->max = max;
    baseline_reset(b);
}

/* Repeat the 4,096-slot hash + 256 KiB zero-fill band without re-allocating,
 * so the A/B measures CORE WORK rather than Python/ctypes array allocation. */
void baseline_reset(Baseline *b) {
    memset(b->ht, 0, 4096 * sizeof(U));
    memset(b->nt, 0, 262144);
    b->n = 0;
}

void baseline_free(Baseline *b) {
    free(b->ht); free(b->nt); free(b->names); free(b->lens);
    b->ht = 0; b->nt = 0; b->names = 0; b->lens = 0;
}

/* String-keyed dispatch + linear string-compare chain, the model C.4/C.5
 * asks to replace.  Returns 1..n. */
U baseline_lookup_or_add(Baseline *b, const unsigned char *name, U len) {
    for (U k = 0; k < 8; k++) {
        U kl = (U)strlen(KW[k]);
        if (kl == len && memcmp(name, KW[k], len) == 0) return k + 1;
    }
    U h = fnv1a(name, len) & 4095;
    U idx = h;
    for (U probe = 0; probe < 4096; probe++) {
        if (b->ht[idx] == 0) break;
        U e = b->ht[idx] - 1;
        if (b->lens[e] == len && memcmp(b->names[e], name, len) == 0)
            return e + 1;
        idx = (idx + 1) & 4095;
    }
    if (b->n >= b->max) return 0;
    U id = b->n + 1;
    b->names[b->n] = name;
    b->lens[b->n] = len;
    b->ht[idx] = id;
    b->n = id;
    return id;
}
#endif /* NO_BASELINE */
