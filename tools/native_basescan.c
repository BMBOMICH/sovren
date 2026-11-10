/* native_basescan.c -- C.2/C.3/C.12/C.13 fused front-end scan.
 *
 * Replaces, for each of the two texts (`rt` and `extra`), the old chain
 *
 *     sxs: _sov_lines_of_fast(text, lf_tbl)   -> allocates a flat copy + a
 *                                               [cap][len][ptrs...] list
 *     src_base += _sov_list_len(sxs)          -> reads the cached length
 *     src_base += _sov_sg_extra_ls(sxs, tbl) -> walks every line again
 *
 * with ONE pass over one flat copy: each line is NUL-terminated in place,
 * the line count and the sugar-extra count are accumulated together, and no
 * line pointer list is ever built.  `src_base` is SEMANTICALLY LOAD-BEARING
 * (stubbing it to 0 changed tests/all.sov and x86ins.sov outputs), so the
 * split and the sugar decision are mirrored bit-for-bit:
 *
 *   - lines_of_fast emits one line for every '\n' byte, plus one trailing
 *     line when the text does not end in '\n' (start < n).  An empty text
 *     produces zero lines.
 *   - sg_extra_ls's fast decline (from native_sgextra.c) is reused verbatim:
 *     sg_extra can only be nonzero when the line holds ';;', " -> ", or a
 *     ": " with a digit-leading LHS or a second ": ".  strip() is called
 *     through the table before sg_extra(), exactly as in the .sov loop.
 *   - `ins` (multi-line string quote state) starts at 0 for each text and
 *     is updated for every line, including lines skipped by the fast gate.
 *
 * Returns the packed pair  (extra_count << 32) | line_count  so a single
 * Sovren value carries both totals; main unpacks with band(...,4294967295)
 * and bshr(...,32), the same pattern u_scan_wide already uses.
 *
 * Table layout (sg_tbl, built by sg_tbl_init):
 *   slot 0 = slot count, slot 1 = strip, slot 2 = sg_extra,
 *   slot 3 = _sov_heap_alloc.
 * Only volatile registers and a small leaf stack frame are used; no static
 * mutable state, no string literals, no external symbols, no relocations.
 */
#include <stdint.h>
typedef uint64_t U;
typedef U (*F1)(U);

enum { T_STRIP = 1, T_SG_EXTRA = 2, T_ALLOC = 3 };

static inline U call1(U *t, U slot, U a) { return ((F1)t[slot])(a); }

/* _sov_find_text for a fixed 2-byte needle; returns index or -1. */
static long find2(const unsigned char *s, U a, U b)
{
    U i = 0;
    unsigned char c;
    while ((c = s[i]) != 0) {
        if (c == a && s[i+1] == b) return (long)i;
        i++;
    }
    return -1;
}

/* Presence of a fixed 4-byte needle. */
static int has4(const unsigned char *s, U a, U b, U c, U d)
{
    U i = 0;
    unsigned char ch;
    while ((ch = s[i]) != 0) {
        if (ch == a && s[i+1] == b && s[i+2] == c && s[i+3] == d) return 1;
        i++;
    }
    return 0;
}

/* sg_marks: bit0 = ';;', bit1 = '>', bit2 = apostrophe. */
static U marks(const unsigned char *l)
{
    U mk = 0, i = 0;
    unsigned char c;
    while ((c = l[i]) != 0) {
        if (c == 62) mk |= 2;
        if (c == 39) mk |= 4;
        if (c == 59 && l[i+1] == 59) mk |= 1;
        i++;
    }
    return mk;
}

/* sg_qend: quote state after this line; 1 = line ends inside a string. */
static U qend(const unsigned char *l, U inp)
{
    U i = 0, ins = inp;
    unsigned char c;
    while ((c = l[i]) != 0) { if (c == 34) break; i++; }
    if (c != 34) return inp;                 /* cfind1(l,34) < 0 */
    i = 0;
    while ((c = l[i]) != 0) {
        if (c == 92) { i += 2; continue; }  /* backslash skips next byte */
        if (c == 34) ins = 1 - ins;
        i++;
    }
    return ins;
}

/* One line: bump the count, then reproduce sg_extra_ls's exact decision. */
static U do_line(const unsigned char *l, U ins, U *extra, U *t)
{
    U mk, arrow, need = 0, nb = 0;
    long cp;
    unsigned char b;
    if (ins == 0) {
        mk = marks(l);
        cp = find2(l, 58, 32);                  /* ": " */
        arrow = (U)has4(l, 32, 45, 62, 32);     /* " -> " */
        need = (mk & 3) != 0;
        if (!need && cp >= 0) {
            nb = 0;
            while ((b = l[nb]) == 32 || b == 9) nb++;
            if (l[nb] > 47 && l[nb] < 58) need = 1;
            if (!need && find2(l + cp + 2, 58, 32) >= 0) need = 1;
        }
        if (need && ((mk & 1) || cp >= 0 || arrow))
            *extra += call1(t, T_SG_EXTRA, call1(t, T_STRIP, (U)l));
    }
    return qend(l, ins);
}

U base_scan_native(U text, U tbl)
{
    U *t = (U *)tbl;
    const unsigned char *s = (const unsigned char *)text;
    U n = 0, lines = 0, extra = 0, ins = 0, st = 0, i;
    unsigned char *flat;

    /* lines_of_fast's length() guard: a small-int pointer is not a string. */
    if ((long long)text < 4096) return 0;
    while (s[n]) n++;
    if (n == 0) return 0;

    /* One allocation instead of two, and no line-list allocation at all. */
    flat = (unsigned char *)call1(t, T_ALLOC, n + 1);
    for (i = 0; i < n; i++) flat[i] = s[i];
    flat[n] = 0;

    for (i = 0; i < n; i++) {
        if (flat[i] == 10) {
            flat[i] = 0;
            lines++;
            ins = do_line(flat + st, ins, &extra, t);
            st = i + 1;
        }
    }
    if (st < n) {                       /* trailing line, flat[n] is already 0 */
        lines++;
        ins = do_line(flat + st, ins, &extra, t);
    }
    return (extra << 32) | lines;
}
