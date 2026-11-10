/* Native collect_body: the walk's per-task body collector, C port.
 * 1:1 mirror of collect_body in compilers/shared/cx86_p3.sov: the
 * syntax-mode fast path (syntax_block_end + the precomputed live/indent/
 * tab/trailing columns of the body IR) and the generic strip/nind scan.
 * Callees that stay interpreted run through the caller-provided cb_tbl
 * (Sovren ABI: args rdi,rsi,rdx,rcx,r8,r9,r10; result rax):
 *   slot 1 cb_ir_get()      -> syntax_body_ir global
 *   slot 2 cb_mode_get()    -> syntax_mode global
 *   slot 3 syntax_block_end(lines, start, indent)
 *   slot 4 strip(s)
 *   slot 5 nind(raw)        (full interpreted form: prints the tab error)
 *   slot 6 _sov_heap_alloc(n)
 *   slot 7 cb_arblk_get()   -> 16-byte block [arp][are], arena state
 * The bt_ind/bt_tab/bt_tr globals are pure functions of syntax_body_ir
 * (set together in syntax_prepare_statements), so the blob recomputes them
 * from the ir pointer it fetched through the table - the identity check
 * inside syntax_block_end guarantees lines matches the current ir.
 * Lists are [cap@0][len@8][elems@16]; strings NUL-terminated with
 * length(x) = x<4096 ? 0 : strlen(x).  The generic path's strings/lists
 * are built in a PERSISTENT bump arena whose [arp][are] state lives in
 * the interpreter-side block (returned strings must outlive the call),
 * with the inline _sov_list_new/_sov_list_add content (fast path in
 * place, grow = 2x copy) - the same proven-shape model as the cx_read
 * blob: allocation patterns are not observable through list contents.
 * NOTE: Sovren integer comparisons are SIGNED (verified: 0-1 >= 1 is
 * false), so the syntax_block_end answer is compared as long long -
 * it returns -1 on any identity/shape mismatch.
 * No external symbols, no relocations, no static mutable state.
 */
#include <stdint.h>
typedef uint64_t U;
typedef U (*F0)(void);
typedef U (*F1)(U);
typedef U (*F2)(U,U);
typedef U (*F3)(U,U,U);

enum { T_IR=1, T_MODE=2, T_END=3, T_STRIP=4, T_NIND=5, T_ALLOC=6, T_ARBLK=7 };

static inline U t0(U *t, U i){ return ((F0)t[i])(); }
static inline U t1(U *t, U i, U a){ return ((F1)t[i])(a); }
static inline U t2(U *t, U i, U a, U b){ return ((F2)t[i])(a,b); }
static inline U t3(U *t, U i, U a, U b, U c){ return ((F3)t[i])(a,b,c); }

#define MISS ((U)-1)

/* persistent bump arena: 1 MiB chunks via the table's _sov_heap_alloc.
 * arp/are are POINTERS INTO the interpreter-side 16-byte block, so every
 * bump is visible to the next collect_body call. */
#define AR_CHUNK 1048576
static U ar_grow(U *t, U *arp, U *are){
    U p = t1(t, T_ALLOC, AR_CHUNK);
    *arp = p; *are = p + AR_CHUNK;
    return p;
}
static inline U ar_get(U *t, U *arp, U *are, U n){
    if (*arp + n > *are) ar_grow(t, arp, are);
    U p = *arp; *arp = p + n; return p;
}
/* inline _sov_list_new: [cap=24][len=0] */
static inline U lnew(U *t, U *arp, U *are){
    U b = ar_get(t, arp, are, 208);
    *(U*)(b) = 24;
    *(U*)(b + 8) = 0;
    return b;
}
/* inline _sov_list_add: fast path in place, grow = 2x copy (the mmap-extend
 * trick is _sov_list_add_slow's private optimization, unobservable) */
static inline U ladd(U lst, U item, U *t, U *arp, U *are){
    if (lst){
        U ln = *(U*)(lst + 8);
        U cap = *(U*)(lst);
        if (ln < cap){
            *(U*)(lst + 16 + ln * 8) = item;
            *(U*)(lst + 8) = ln + 1;
            return lst;
        }
    }
    U cap = 24, len = 0;
    if (lst){ cap = *(U*)(lst); len = *(U*)(lst + 8); if (cap < 24) cap = 24; }
    U nc = cap * 2;
    U b = ar_get(t, arp, are, 16 + nc * 8);
    *(U*)(b) = nc;
    *(U*)(b + 8) = len;
    for (U i = 0; i < len; i++) *(U*)(b + 16 + i * 8) = *(U*)(lst + 16 + i * 8);
    *(U*)(b + 16 + len * 8) = item;
    *(U*)(b + 8) = len + 1;
    return b;
}

/* strip content (_sov_trim): strips leading/trailing " \t\n\r"; identity
 * or interior pointer when clean, arena copy when trimmed at either end */
static U stripf(U s, U *t, U *arp, U *are){
    if (s == 0) return 0;
    const unsigned char *p = (const unsigned char*)s;
    U n = 0; while (p[n]) n++;
    U a = 0;
    while (a < n){
        unsigned c = p[a];
        if (c == 32 || c == 9 || c == 10 || c == 13) a++;
        else break;
    }
    U b = n;
    while (b > a){
        unsigned c = p[b-1];
        if (c == 32 || c == 9 || c == 10 || c == 13) b--;
        else break;
    }
    if (a == 0 && b == n) return s;
    U d = ar_get(t, arp, are, b - a + 1);
    for (U i = 0; i < b - a; i++) *(unsigned char*)(d + i) = p[a + i];
    *(unsigned char*)(d + (b - a)) = 0;
    return d;
}

/* nind content: leading spaces count; a tab routes to the interpreted
 * nind (it prints the error, calls err_where and sets had_err) and uses
 * its answer, so the error path stays byte-identical */
static U nindf(U raw, U *t){
    const unsigned char *p = (const unsigned char*)raw;
    U c = 0, i = 0;
    while (1){
        unsigned b = p[i];
        if (b == 0) return c;
        if (b == 9) return t1(t, T_NIND, raw);
        if (b != 32) return c;
        c++; i++;
    }
}

/* twin entry: rdi=lines, rsi=start, rdx=bind, rcx=cb_tbl */
U collect_body_native(U lines, U start, U bind, U tbl){
    U *t = (U*)tbl;
    U blk = t0(t, T_ARBLK);
    U *arp = (U*)blk, *are = (U*)(blk + 8);
    U mode = t0(t, T_MODE);
    if (mode > 0){
        U cb_end = t3(t, T_END, lines, start, bind);
        if ((long long)cb_end >= (long long)start){
            U cb_cnt = cb_end - start;
            /* exact-size output list from the persistent arena (same
             * [cap][len][elems] content as the interpreted heap_alloc
             * version; allocation patterns are not observable through
             * list contents - the cx_read v4 proof) */
            U cb_out = ar_get(t, arp, are, 16 + (cb_cnt + 1) * 8);
            *(U*)(cb_out) = cb_cnt + 1;
            U ir = t0(t, T_IR);
            U cb_n = *(U*)(ir + 8);
            U bt_ind = ir + cb_n * 8;
            U bt_tab = ir + cb_n * 32;
            U bt_tr  = ir + cb_n * 40;
            U cb_k = 0;
            for (U cb_j = start; cb_j < cb_end; cb_j++){
                if (*(U*)(ir + 16 + (cb_n * 9 + cb_j) * 8) == 1){
                    U cb_raw = *(U*)(lines + 16 + cb_j * 8);
                    U cb_s = cb_raw + *(U*)(bt_ind + 16 + cb_j * 8);
                    if (*(U*)(bt_tab + 16 + cb_j * 8) != 0 ||
                        *(U*)(bt_tr + 16 + cb_j * 8) != 0){
                        cb_s = t1(t, T_STRIP, cb_raw);
                    }
                    *(U*)(cb_out + 16 + cb_k * 8) = cb_s;
                    cb_k++;
                }
            }
            *(U*)(cb_out + 8) = cb_k;
            return cb_out;
        }
    }
    U out = lnew(t, arp, are);
    U n = *(U*)(lines + 8);
    U j = start;
    while (j < n){
        U raw = *(U*)(lines + 16 + j * 8);
        if (raw == 0){ j++; continue; } /* strip(0)=blank -> empty -> skip */
        U s = stripf(raw, t, arp, are);
        unsigned b0 = *(const unsigned char*)s;
        if (b0 == 0){ j++; continue; }
        if (b0 == 35){ j++; continue; }
        if (nindf(raw, t) > bind){
            out = ladd(out, s, t, arp, are);
            j++;
        } else {
            return out;
        }
    }
    return out;
}
