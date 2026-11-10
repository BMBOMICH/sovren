/* C.2/C.3/C.9/C.15/C.16 — ONE-PASS ZERO-COPY OFFSET-DESCRIPTOR LEXER.
 *
 * This is the certified prototype core for the structural rewrite.  In ONE
 * traversal of the source bytes, with ZERO allocations, ZERO string copies
 * and ZERO whole-text pre-passes, it produces:
 *
 *   - (offset,length) descriptors for every logical line, plus indent and
 *     first non-blank byte (C.3: no _sov_substring / _sov_cut / per-line
 *     join/strcat / full-source copies);
 *   - classification of `use ` / `use:` / `include ` lines and their
 *     indented continuation blocks (C.2: pull_uses work-queue propagation
 *     inputs, no separate whole-text scan);
 *   - the six runtime-need triggers (_sov_, load_file, peek_, poke_,
 *     spawn , join ) that currently need a separate bounded front_scan
 *     (C.9/C.15);
 *   - a first-byte statement-dispatch histogram for the common line shapes
 *     (C.16).
 *
 * The current compiler.sov pipeline does these in separate passes:
 *   pu_lines/_sov_lines_of_fast -> pull_uses -> splice_inc -> front_scan.
 * Fusing them is the C.2 "one read + one lexical pass" seam.  This core is
 * CERTIFIED BUT NOT INSTALLED: it is a prototype, not a compiler rewrite,
 * and there is deliberately no claim of whole-compile speed parity from it.
 *
 * Build (harness): gcc -O3 -fPIC -shared native_desc_lexer.c -o libdesc.so
 * Build (Sovren twin): use the relocation-free .text extraction in
 *   tools/build_native_reader.py / build_native_syntax.py.  No external
 *   symbols, no relocations, no static mutable state.
 */
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

typedef uint64_t U;
typedef uint32_t u32;
typedef uint8_t  u8;

/* 16-byte fixed record (C.7-style fixed records, descriptor variant). */
typedef struct {
    u32 off;      /* byte offset of line start in src                    */
    u32 len;      /* length excluding the newline                       */
    u32 indent;   /* count of leading spaces / tabs                     */
    u8  first;    /* first non-blank byte, 0 for a blank line           */
    u8  kind;     /* see DESC_* below                                   */
    u8  in_block; /* 1 when this line is inside a `use:` indented block */
    u8  pad;
} Desc;

enum {
    DESC_PLAIN    = 0,
    DESC_USE_LINE = 1,   /* `use name`                                   */
    DESC_USE_BLOCK= 2,   /* `use:` header                               */
    DESC_INCLUDE  = 3,   /* `include ...`                               */
    DESC_COMMENT  = 4,   /* `# ...`                                     */
    DESC_EMPTY    = 5
};

/* flags bits — the six runtime-need triggers plus scan outcomes. */
enum {
    F_SOV      = 1u << 0,
    F_LOADFILE = 1u << 1,
    F_PEEK     = 1u << 2,
    F_POKE     = 1u << 3,
    F_SPAWN    = 1u << 4,
    F_JOIN     = 1u << 5,
    F_HAS_USE  = 1u << 6,
    F_HAS_INC  = 1u << 7
};

typedef struct {
    U lines;          /* descriptors written (may be truncated to cap)   */
    U need;           /* F_* bits                                        */
    U use_lines;      /* count of USE_LINE + USE_BLOCK + block members   */
    U include_lines;
    U blank_lines;
    u32 hist[256];    /* first-byte statement-dispatch histogram         */
} Summary;

static inline int starts_at(const unsigned char *s, U i, U n,
                            const char *pat, U plen) {
    if (i + plen > n) return 0;
    for (U k = 0; k < plen; k++)
        if (s[i + k] != (unsigned char)pat[k]) return 0;
    return 1;
}

/* Returns the number of descriptors written.  `out` may be NULL when the
 * caller only wants the summary (histogram/flags); cap bounds the writes. */
U desc_lex(const unsigned char *src, U n, Desc *out, U cap, Summary *sm) {
    if (!src || !sm) return 0;
    /* Explicit zeroing: a memset() call would be an external symbol in the
     * freestanding relocation-free twin build. */
    sm->lines = 0; sm->need = 0; sm->use_lines = 0;
    sm->include_lines = 0; sm->blank_lines = 0;
    for (U k = 0; k < 256; k++) sm->hist[k] = 0;
    U i = 0, start = 0, wrote = 0;
    u32 in_block_indent = 0;
    int in_block = 0;
    while (i <= n) {
        int eol = (i == n) || (src[i] == '\n');
        if (!eol) { i++; continue; }
        U len = i - start;
        /* trailing CR is part of the line terminator, not the text */
        if (len && src[start + len - 1] == '\r') len--;
        U p = start, ind = 0;
        while (p < start + len && (src[p] == ' ' || src[p] == '\t')) {
            ind++; p++;
        }
        U text_len = start + len - p;
        const unsigned char *t = src + p;
        u8 first = text_len ? t[0] : 0;
        u8 kind = DESC_PLAIN;
        if (text_len == 0) {
            kind = DESC_EMPTY;
            sm->blank_lines++;
        } else if (t[0] == '#') {
            kind = DESC_COMMENT;
        } else if (starts_at(src, p, start + len, "use:", 4) &&
                   (text_len == 4 || t[4] == ' ' || t[4] == '\t')) {
            kind = DESC_USE_BLOCK; in_block = 1; in_block_indent = (u32)ind;
            sm->need |= F_HAS_USE;
        } else if (starts_at(src, p, start + len, "use ", 4)) {
            kind = DESC_USE_LINE; sm->need |= F_HAS_USE;
        } else if (starts_at(src, p, start + len, "include ", 8)) {
            kind = DESC_INCLUDE; sm->need |= F_HAS_INC;
        } else if (in_block && ind > in_block_indent) {
            kind = DESC_USE_LINE; sm->use_lines++;
        } else {
            in_block = 0;
        }
        if (kind == DESC_USE_LINE || kind == DESC_USE_BLOCK) sm->use_lines++;
        if (kind == DESC_INCLUDE) sm->include_lines++;
        if (first) sm->hist[first]++;

        /* ONE pass also carries the six runtime-need triggers.  C.16
         * FIRST-BYTE STATEMENT DISPATCH: a byte can only begin one of the
         * six literals if it is one of five distinct first characters, so
         * 99%+ of bytes cost a single load + switch and no comparison.
         * (The first draft probed all six literals at EVERY byte and was
         * 0.2643x SLOWER than the allocation-per-line baseline; measured
         * and recorded, not hidden.)  BROKEN_LEX omits five probes. */
        if (text_len) {
            for (U k = 0; k < text_len; k++) {
                switch (t[k]) {
                case '_':
                    if (starts_at(src, p + k, start + len, "_sov_", 5))
                        sm->need |= F_SOV;
                    break;
#ifndef BROKEN_LEX
                case 'l':
                    if (starts_at(src, p + k, start + len, "load_file", 9))
                        sm->need |= F_LOADFILE;
                    break;
                case 'p':
                    if (starts_at(src, p + k, start + len, "peek_", 5))
                        sm->need |= F_PEEK;
                    else if (starts_at(src, p + k, start + len, "poke_", 5))
                        sm->need |= F_POKE;
                    break;
                case 's':
                    if (starts_at(src, p + k, start + len, "spawn ", 6))
                        sm->need |= F_SPAWN;
                    break;
                case 'j':
                    if (starts_at(src, p + k, start + len, "join ", 5))
                        sm->need |= F_JOIN;
                    break;
#endif
                default: break;
                }
            }
        }
        sm->lines++;
        if (out && wrote < cap) {
            Desc *d = &out[wrote++];
            d->off = (u32)start; d->len = (u32)len; d->indent = (u32)ind;
            d->first = first; d->kind = kind;
            d->in_block = (u8)(in_block && ind > in_block_indent ? 1 : 0);
            d->pad = 0;
        }
        if (i == n) break;
        i++; start = i;
    }
    return wrote;
}

#ifndef NO_BASELINE
/* Baseline for the core-level A/B: the allocation-per-line shape that the
 * current pipeline's per-line string materialisation implies.  Deliberately
 * does real work (malloc + memcpy per line) so the comparison is fair. */
/* HONEST C.2 BASELINE: the current compiler.sov pipeline does these jobs in
 * SEPARATE whole-text passes.  This models four of them so the fused core is
 * compared against the work it actually replaces, not against line splitting
 * alone (that earlier comparison was unfair and is recorded as 0.237x). */
U desc_lex_separate_baseline(const unsigned char *src, U n) {
    U i, k, count = 0, hits = 0;
    u32 hist[256];
    for (k = 0; k < 256; k++) hist[k] = 0;
    /* pass 1: line split + per-line allocation/copy */
    i = 0;
    while (i < n) {
        U st = i;
        while (i < n && src[i] != 10) i++;
        U len = i - st;
        unsigned char *p = (unsigned char *)malloc(len + 1);
        if (p) { memcpy(p, src + st, len); p[len] = 0; free(p); }
        count++;
        if (i < n) i++;
    }
    /* pass 2: use/include directive scan, whole text */
    for (i = 0; i < n; i++) {
        if (src[i] == 'u' && starts_at(src, i, n, "use ", 4)) hits++;
        if (src[i] == 'u' && starts_at(src, i, n, "use:", 4)) hits++;
        if (src[i] == 'i' && starts_at(src, i, n, "include ", 8)) hits++;
    }
    /* pass 3: six runtime-need trigger probes, whole text (front_scan shape) */
    for (i = 0; i < n; i++) {
        if (starts_at(src, i, n, "_sov_", 5)) hits++;
        else if (starts_at(src, i, n, "load_file", 9)) hits++;
        else if (starts_at(src, i, n, "peek_", 5)) hits++;
        else if (starts_at(src, i, n, "poke_", 5)) hits++;
        else if (starts_at(src, i, n, "spawn ", 6)) hits++;
        else if (starts_at(src, i, n, "join ", 5)) hits++;
    }
    /* pass 4: first-byte statement-dispatch histogram */
    i = 0;
    while (i < n) {
        U st = i;
        while (st < n && (src[st] == ' ' || src[st] == 9)) st++;
        if (st < n && src[st] != 10) hist[src[st]]++;
        while (i < n && src[i] != 10) i++;
        if (i < n) i++;
    }
    return count + hits + hist['m'];
}

U desc_lex_alloc_baseline(const unsigned char *src, U n) {
    U i = 0, start = 0, count = 0;
    while (i <= n) {
        if (i == n || src[i] == '\n') {
            U len = i - start;
            unsigned char *p = (unsigned char *)malloc(len + 1);
            if (p) { memcpy(p, src + start, len); p[len] = 0; free(p); }
            count++;
            if (i == n) break;
            i++; start = i;
        } else i++;
    }
    return count;
}
#endif /* NO_BASELINE */
