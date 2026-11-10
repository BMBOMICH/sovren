/* native_sgextra.c -- C.10/C.12 native twin for sg_extra_ls.
 *
 * sg_extra_ls walks the runtime/extra line lists to count how many lines
 * sugar expansion adds (a value that feeds src_base and is SEMANTICALLY
 * LOAD-BEARING: replacing it with 0 changed tests/all.sov and x86ins.sov
 * outputs, 8/40 differential mismatches). The interpreted loop costs
 * 3.49 ms on self-compile (2-all-spliced 4.95 ms -> 1.46 ms with it stubbed).
 *
 * The twin keeps every decision bit-exact, including the `ins` multi-line
 * string gate. Two pure C scans per line replace the interpreted decline.
 * Only strip() and sg_extra() stay as table calls through the Sovren ABI
 * (rdi = arg, rax = result) -- and sg_extra() is now skipped whenever the
 * line provably cannot expand:
 *
 *   sg_extra(t) can return nonzero ONLY through one of four branches:
 *     (1) _sov_find_text(t,";;")  -> sg_cuts splits
 *     (2) sg_arrow(t)             -> requires " -> "
 *     (3) sg_run_count(t)         -> requires ": "
 *     (4) the digit/assignment branch -> requires ": "
 *   So a line with none of ";;", " -> ", ": " returns 0. strip() only
 *   removes leading/trailing whitespace and cannot create any of those
 *   forms, so skipping the call is decision-equivalent, not a heuristic.
 *
 * No caching: the table is built once in-run, all state is per call. No
 * string literals (would create .rodata relocations), no external symbols,
 * no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef U (*F1)(U);

enum { T_STRIP = 1, T_SG_EXTRA = 2 };

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

U sg_extra_ls_native(U ls, U tbl)
{
    U *t = (U *)tbl;
    U n = *(U *)(ls + 8);                    /* list: [cap][len][ptrs...] */
    U d = 0, ins = 0, i = 0;
    while (i < n) {
        const unsigned char *l = (const unsigned char *)*(U *)(ls + 16 + i * 8);
        if (ins == 0) {
            U mk = marks(l);
            long cp = find2(l, 58, 32);      /* ": " */
            U arrow = (U)has4(l, 32, 45, 62, 32);  /* " -> " */
            U need = (mk & 3) != 0;
            if (!need && cp >= 0) {
                U nb = 0;
                unsigned char b;
                while ((b = l[nb]) == 32 || b == 9) nb++;
                if (l[nb] > 47 && l[nb] < 58) need = 1;
                if (!need && find2(l + cp + 2, 58, 32) >= 0) need = 1;
            }
            /* sg_extra can only be nonzero with one of these three forms. */
            if (need && ((mk & 1) || cp >= 0 || arrow))
                d += call1(t, T_SG_EXTRA, call1(t, T_STRIP, (U)l));
        }
        ins = qend(l, ins);
        i++;
    }
    return d;
}
