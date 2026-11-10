/* Native u_scan core: the unsafe-site lint walk, fused to one pass per line.
 * Byte-exact mirror of the interpreted u_scan in compiler.sov (2026-11-01):
 * same indent/trim walks, same unsafe: block tracking, same six-needle
 * recognition, same smark/smod suppressions, same lint prints (raw write
 * syscalls; the interpreted path goes through _sov_print, which is the same
 * two writes when the string is short ASCII).
 * The fused u_san (blank string interiors) is equivalent to the two-pass
 * strip+u_san+scan: a needle chain that crosses a quote always fails on the
 * quote byte itself (34 is no needle byte), so raw reads match blanked reads
 * everywhere a chain can pass.
 * No external symbols, no relocations, no static mutable state.
 * Returns sbad in the low 32 bits, this-call bare count in the high 32.
 */
#include <stdint.h>
typedef uint64_t U;
typedef unsigned char C;

static inline U sys3(U n, U a, U b, U c) {
    U r;
    __asm__ volatile("syscall"
                     : "=a"(r)
                     : "a"(n), "D"(a), "S"(b), "d"(c)
                     : "rcx", "r11", "memory");
    return r;
}

/* uskip gate: 1 iff none of peek_ / poke_ / port_ occurs (all 'p'-led). */
static int any_needle_prefix(const C *s, U n) {
    for (U i = 0; i + 5 <= n; i++) {
        if (s[i] != 'p') continue;
        C c1 = s[i + 1];
        if (c1 == 'e') {
            if (s[i + 2] == 'e' && s[i + 3] == 'k' && s[i + 4] == '_') return 1;
        } else if (c1 == 'o') {
            if (s[i + 2] == 'k' && s[i + 3] == 'e' && s[i + 4] == '_') return 1;
            if (s[i + 2] == 'r' && s[i + 3] == 't' && s[i + 4] == '_') return 1;
        }
    }
    return 0;
}

U u_scan_core_native(const C *src, U listing, U srclen) {
    /* .sov strings are length-tracked; a NUL is not guaranteed (the
     * self-source buffer is exact-fit, so slen ran onto the guard page).
     * The caller passes length(src) explicitly, matching the interpreted
     * walk's length-bounded cursor. */
    U n = srclen;
    if (!any_needle_prefix(src, n)) return 0;
    U sbad = 0, bare = 0;
    U us_pos = 0, more = 1;
    U blk_at = 0, blk_ind = 0, smod = 0, smark = 0;
    while (more) {
        U us_e = us_pos;
        while (us_e < n && src[us_e] != 10) us_e++;
        if (us_e >= n) more = 0;
        const C *osl = src + us_pos;
        U on = us_e - us_pos;
        U sind = 0, toff = 0;
        for (;;) {
            if (toff >= on) break;
            C cb = osl[toff];
            if (cb == 32) { sind++; toff++; }
            else if (cb == 9) { sind += 4; toff++; }
            else if (cb == 10) { toff++; }
            else if (cb == 13) { toff++; }
            else break;
        }
        U tend = on;
        for (;;) {
            if (tend <= toff) break;
            C cb = osl[tend - 1];
            if (cb == 32 || cb == 9 || cb == 10 || cb == 13) tend--;
            else break;
        }
        U sln = tend - toff;
        U blk_new = 0;
        if (sln == 7) {
            if (osl[toff] == 'u' && osl[toff + 1] == 'n' && osl[toff + 2] == 's' &&
                osl[toff + 3] == 'a' && osl[toff + 4] == 'f' && osl[toff + 5] == 'e' &&
                osl[toff + 6] == ':')
                blk_new = 1;
        }
        if (blk_new) { blk_at = 1; blk_ind = sind; }
        U in_blk = 0;
        if (blk_at) {
            if (sind > blk_ind) {
                in_blk = 1;
            } else {
                U dd = 1;
                if (blk_new) dd = 0;
                if (sln == 0) dd = 0;
                if (toff < tend && osl[toff] == 35) dd = 0;
                if (dd) blk_at = 0;
            }
        }
        if (sln > 0) {
            U cm = (osl[toff] == 35);
            if (cm) {
                if (sln > 14 &&
                    osl[toff + 1] == ' ' && osl[toff + 2] == 'u' && osl[toff + 3] == 'n' &&
                    osl[toff + 4] == 's' && osl[toff + 5] == 'a' && osl[toff + 6] == 'f' &&
                    osl[toff + 7] == 'e' && osl[toff + 8] == '-' && osl[toff + 9] == 'm' &&
                    osl[toff + 10] == 'o' && osl[toff + 11] == 'd' && osl[toff + 12] == 'u' &&
                    osl[toff + 13] == 'l' && osl[toff + 14] == 'e')
                    smod = 1;
                if (sln == 8 &&
                    osl[toff + 1] == ' ' && osl[toff + 2] == 'u' && osl[toff + 3] == 'n' &&
                    osl[toff + 4] == 's' && osl[toff + 5] == 'a' && osl[toff + 6] == 'f' &&
                    osl[toff + 7] == 'e')
                    smark = 1;
            }
            if (!cm) {
                if (smod == 0 && in_blk == 0) {
                U hit = 0;
                for (U j = toff; j < tend; j++)
                    if (osl[j] == 'p') { hit = 1; break; }
                if (hit) {
                    U L = tend - toff;
                    U uraw = 0, ubare = 0;
                    U instr = 0, esc = 0;
                    for (U j = toff; j < tend; j++) {
                        C b = osl[j];
                        if (b == 92) {
                            if (esc == 0) esc = 1; else esc = 0;
                        } else {
                            if (b == 34) { if (esc == 0) instr = !instr; }
                            esc = 0;
                        }
                        if (instr) continue;
                        if (b != 'p') continue;
                        U i = j - toff;
                        U c1 = (j + 1 < tend) ? osl[j + 1] : 0;
                        U u2r = 0, u2b = 0;
                        if (c1 == 101) {
                            if (i + 10 <= L) {
                                if (osl[j + 2] == 101 && osl[j + 3] == 107 && osl[j + 4] == 95 &&
                                    osl[j + 5] == 98 && osl[j + 6] == 121 && osl[j + 7] == 116 &&
                                    osl[j + 8] == 101 && osl[j + 9] == 40)
                                    u2r = 1;
                            }
                            if (i + 8 <= L) {
                                if (osl[j + 2] == 101 && osl[j + 3] == 107 && osl[j + 4] == 95 &&
                                    osl[j + 5] == 114 && osl[j + 6] == 97) {
                                    if (osl[j + 7] == 119) u2r = 1;
                                    u2b = 1;
                                }
                            }
                        } else if (c1 == 111) {
                            if (i + 10 <= L) {
                                if (osl[j + 2] == 107 && osl[j + 3] == 101 && osl[j + 4] == 95 &&
                                    osl[j + 5] == 98 && osl[j + 6] == 121 && osl[j + 7] == 116 &&
                                    osl[j + 8] == 101 && osl[j + 9] == 40)
                                    u2r = 1;
                            }
                            if (i + 8 <= L) {
                                if (osl[j + 2] == 107 && osl[j + 3] == 101 && osl[j + 4] == 95 &&
                                    osl[j + 5] == 114 && osl[j + 6] == 97) {
                                    if (osl[j + 7] == 119) u2r = 1;
                                    u2b = 1;
                                }
                            }
                            if (i + 8 <= L) {
                                if (osl[j + 2] == 114 && osl[j + 3] == 116 && osl[j + 4] == 95 &&
                                    osl[j + 5] == 111 && osl[j + 6] == 117) {
                                    if (osl[j + 7] == 116) u2r = 1;
                                    u2b = 1;
                                }
                            }
                            if (i + 7 <= L) {
                                if (osl[j + 2] == 114 && osl[j + 3] == 116 && osl[j + 4] == 95 &&
                                    osl[j + 5] == 105) {
                                    if (osl[j + 6] == 110) u2r = 1;
                                    u2b = 1;
                                }
                            }
                        }
                        if (u2r) uraw = 1;
                        if (u2b) ubare = 1;
                    }
                    if (uraw == 1) {
                        if (smark == 1) uraw = 0;
                    }
                    if (uraw == 1) {
                        sbad++;
                        if (ubare == 1) bare++;
                        if (listing == 1) {
                            /* immediate stores: no .rodata, no relocations */
                            C msg[42];
                            msg[0]='u';msg[1]='n';msg[2]='s';msg[3]='a';msg[4]='f';msg[5]='e';
                            msg[6]=' ';msg[7]='l';msg[8]='i';msg[9]='n';msg[10]='t';msg[11]=':';
                            msg[12]=' ';msg[13]='u';msg[14]='n';msg[15]='m';msg[16]='a';msg[17]='r';
                            msg[18]='k';msg[19]='e';msg[20]='d';msg[21]=' ';msg[22]='r';msg[23]='a';
                            msg[24]='w';msg[25]=' ';msg[26]='m';msg[27]='e';msg[28]='m';msg[29]='o';
                            msg[30]='r';msg[31]='y';msg[32]='/';msg[33]='i';msg[34]='o';msg[35]=' ';
                            msg[36]='l';msg[37]='i';msg[38]='n';msg[39]='e';msg[40]=':';msg[41]=0;
                            C nlb = 10;
                            sys3(1, 1, (U)msg, 41);
                            sys3(1, 1, (U)&nlb, 1);
                            sys3(1, 1, (U)(osl + toff), tend - toff);
                            sys3(1, 1, (U)&nlb, 1);
                        }
                    }
                }
                }
                /* the interpreted walk clears smark inside `if cm is 0`
                 * (indent 16, sibling of `if smod is 0`), so a comment
                 * line never clears it; match that exactly. */
                smark = 0;
            }
        }
        us_pos = us_e + 1;
    }
    return sbad + (bare << 32);
}
