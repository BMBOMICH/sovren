/* sc - a fresh .sov compiler in sa's shape.
 *
 * The architecture is the sovren-assembler's, copied on purpose:
 *   * the source file is read once, whole, into one buffer
 *   * one pass over the lines: a statement is parsed and its machine code is
 *     emitted immediately into a growing byte buffer.  No IR, no AST, no
 *     second pass, no rewriting.
 *   * names go into an open-addressing hash table: 16-byte slots, FNV-1a,
 *     Fibonacci hashing (the high bits of hash*golden-ratio, shifted by
 *     64-bsr(slots)), linear probing, pre-sized then doubled, dedup.
 *   * a branch to a name that is not there yet is written with a zero and
 *     remembered, then patched at the end, so one pass is enough.
 *   * output is a static ELF64 with no section headers and no libc: an entry
 *     point, two program headers, and bytes.
 *
 * The runtime is fresh and written here, in emit calls, as raw machine code:
 * write for print, exit for leaving, brk for _sov_alloc.
 */

#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef int i32;
typedef long long i64;

/* ------------------------------------------------------------------ error */

static void die(const char *msg)
{
    static const char p[] = "sc: ";
    write(2, p, sizeof p - 1);
    write(2, msg, strlen(msg));
    write(2, "\n", 1);
    exit(1);
}

static u32 err_line;

static void die2(const char *msg, const char *name, u32 nlen)
{
    static const char p[] = "sc: ";
    static const char q[] = ": ";
    static const char l[] = " (line ";
    static const char e[] = ")\n";
    char buf[32];
    u32 ln = err_line, n = 0;
    write(2, p, sizeof p - 1);
    write(2, msg, strlen(msg));
    write(2, q, 2);
    write(2, name, nlen);
    write(2, l, sizeof l - 1);
    do { buf[n++] = (char)('0' + ln % 10); ln /= 10; } while (ln);
    while (n) write(2, &buf[--n], 1);
    write(2, e, 2);
    exit(1);
}

static void die_at(const char *msg, u32 line)
{
    err_line = line;
    /* like die, but with the line, so a refusal can be located */
    static const char p[] = "sc: ";
    static const char l[] = " (line ";
    static const char e[] = ")\n";
    char buf[16];
    u32 n = 0, ln = err_line;
    write(2, p, sizeof p - 1);
    write(2, msg, strlen(msg));
    write(2, l, sizeof l - 1);
    do { buf[n++] = (char)('0' + ln % 10); ln /= 10; } while (ln);
    while (n) write(2, &buf[--n], 1);
    write(2, e, 2);
    exit(1);
}

/* ------------------------------------------------------- growing buffers */

typedef struct { u8 *p; u64 len, cap; } Buf;

static void *xrealloc(void *q, u64 n)
{
    void *r = realloc(q, n);
    if (!r) die("out of memory");
    return r;
}

static void bgrow(Buf *b, u64 need)
{
    if (b->len + need > b->cap) {
        u64 c = b->cap ? b->cap : 4096;
        while (c < b->len + need) c *= 2;
        b->p = xrealloc(b->p, c);
        b->cap = c;
    }
}

static void bput(Buf *b, u8 c) { bgrow(b, 1); b->p[b->len++] = c; }
static void bputn(Buf *b, const void *s, u64 n) { bgrow(b, n); memcpy(b->p + b->len, s, n); b->len += n; }
static void bputat32(Buf *b, u64 at, u32 v)
{
    b->p[at] = (u8)v; b->p[at+1] = (u8)(v >> 8); b->p[at+2] = (u8)(v >> 16); b->p[at+3] = (u8)(v >> 24);
}

/* the code buffer's fast path: one inline compare per put, no call.  The
 * data buffer keeps bput -- string writes are rare, code bytes are not. */
static Buf code, data;

static void cslack(u64 need)
{
    if (code.len + need > code.cap) {
        u64 c = code.cap ? code.cap : 4096;
        while (c < code.len + need) c *= 2;
        code.p = xrealloc(code.p, c);
        code.cap = c;
    }
}
static void cput(u8 v)        { if (code.len >= code.cap) cslack(1); code.p[code.len++] = v; }
static void cput32(u32 v)
{
    if (code.len + 4 > code.cap) cslack(4);
    u8 *p = code.p + code.len;
    p[0] = (u8)v; p[1] = (u8)(v >> 8); p[2] = (u8)(v >> 16); p[3] = (u8)(v >> 24);
    code.len += 4;
}
static void cput64(u64 v) { cput32((u32)v); cput32((u32)(v >> 32)); }

/* -------------------------------------------------- the symbol tables
 *
 * sa's slot design, twice.  A slot is sixteen bytes: the name word and one
 * word carrying the length, the scope, the kind and the value.  Names of up
 * to seven characters live inside the name word itself (the top bit set is
 * the marker), so a probe touches one cache line, not two -- the string in
 * the source buffer is never fetched on a hit.  Longer names store a pointer
 * as before.  A definition is one store; a use is one probe; a name that is
 * already there is returned, never duplicated.
 *
 * There are two tables.  The global one holds functions and the runtime's
 * own labels (scope 0); it stays small enough to sit in cache, so the call
 * a print statement emits probes warm memory.  The local one holds the
 * variables of the function being built, hashed with the function's serial
 * mixed into the seed, so every function has its own names and none of them
 * ever has to be removed.  It is sized from the source length up front --
 * about one symbol per forty bytes of .sov -- so the common case never
 * rehashes; doubling stays as the fallback. */

#define SYM_START 1024
#define K_VAR   1
#define K_FUNC  2
#define K_CONST 3
#define K_GVAR  4          /* a global slot in the data segment */
#define K_TXT   0x80      /* type bit: text, on VAR/FUNC/CONST */

typedef struct { u64 name; u64 meta; } Slot;   /* 16 bytes */
typedef struct { Slot *s; u32 n, used, shift; } Tbl;

static Tbl gt, lt;

#define NAME_INL 0x8000000000000000ULL

/* a probe key: either a string and its length, or (the rehash path) another
 * slot's own name.  inl carries the assembled inline word when the name is
 * short; the flag bit marks it. */
typedef struct { u64 inl; const char *s; u32 len, scope; } Key;

static Key key_str(const char *s, u32 len, u32 scope)
{
    Key k;
    k.inl = 0; k.s = s; k.len = len; k.scope = scope;
    if (len <= 7) {
        u64 v = NAME_INL;
        for (u32 i = 0; i < len; i++) v |= (u64)(u8)s[i] << (8 * i);
        k.inl = v;
    }
    return k;
}
static Key key_slot(const Slot *q)
{
    Key k;
    k.len = (u32)(q->meta >> 48);
    k.scope = (u32)((q->meta >> 32) & 0xffff);
    if (q->name & NAME_INL) { k.inl = q->name; k.s = 0; }
    else { k.inl = 0; k.s = (const char *)q->name; }
    return k;
}

/* the same name must always hash the same.  Short names hash straight from
 * their inline word: two multiplies, no byte loop, no serial dependency
 * chain.  The word carries at most seven name bytes in bits 0..55 and the
 * length in bits 56..62.  Long names keep the byte-at-a-time FNV-1a. */
static u64 key_hash(const Key *k)
{
    if (k->inl) {
        u64 v = (k->inl & ~NAME_INL) | ((u64)k->len << 56);
        return v * 0x9E3779B97F4A7C15ULL ^ (k->scope * 0xff51afd7ed558ccdULL);
    }
    u64 h = 0xcbf29ce484222325ULL ^ (k->scope * 0x9E3779B97F4A7C15ULL);
    for (u32 i = 0; i < k->len; i++) { h ^= (u8)k->s[i]; h *= 0x100000001b3ULL; }
    return h;
}

/* short names are inline in the slot by construction, long ones are pointers
 * with the flag bit clear, so the length already tells the two apart */
static int key_match(const Key *k, const Slot *q)
{
    u64 m = q->meta;
    if ((u32)(m >> 48) != k->len || (u32)((m >> 32) & 0xffff) != k->scope) return 0;
    if (k->len <= 7) return q->name == k->inl;
    return memcmp((const char *)q->name, k->s, k->len) == 0;
}

static u32 sym_slot(Tbl *t, const Key *k, int *found)
{
    u64 h = key_hash(k);
    u32 i = (u32)((h * 0x9E3779B97F4A7C15ULL) >> t->shift) & (t->n - 1);
    for (;;) {
        Slot *q = &t->s[i];
        if (!q->name) { *found = 0; return i; }       /* the insert position */
        if (key_match(k, q)) { *found = 1; return i; }
        i = (i + 1) & (t->n - 1);
    }
}

static u32 pow2ceil(u64 v)
{
    u32 r = 1;
    while ((u64)r < v) r <<= 1;
    return r;
}

static void tbl_init(Tbl *t, u64 est_syms)
{
    u64 need = est_syms * 4 / 3;
    t->n = pow2ceil(need < SYM_START ? SYM_START : need);
    t->shift = (u32)__builtin_clzll(t->n);
    t->s = xrealloc(NULL, (u64)t->n * sizeof(Slot));
    memset(t->s, 0, (u64)t->n * sizeof(Slot));
    t->used = 0;
}

static void sym_grow(Tbl *t)
{
    Slot *old = t->s; u32 on = t->n;
    t->n *= 2;
    t->shift = (u32)__builtin_clzll(t->n);
    t->s = xrealloc(NULL, (u64)t->n * sizeof(Slot));
    memset(t->s, 0, (u64)t->n * sizeof(Slot));
    for (u32 j = 0; j < on; j++)
        if (old[j].name) {
            Key k = key_slot(&old[j]);
            int f;
            u32 i = sym_slot(t, &k, &f);
            t->s[i] = old[j];
        }
    free(old);
}

static Slot *sym_find(Tbl *t, const char *s, u32 len, u32 scope)
{
    Key k = key_str(s, len, scope);
    int f;
    u32 i = sym_slot(t, &k, &f);
    return f ? &t->s[i] : 0;
}

static Slot *sym_define(Tbl *t, const char *s, u32 len, u32 scope, u32 kind, u32 value)
{
    if ((u64)(t->used + 1) * 4 >= (u64)t->n * 3) sym_grow(t);
    Key k = key_str(s, len, scope);
    int f;
    u32 i = sym_slot(t, &k, &f);
    Slot *q = &t->s[i];
    if (f) return q;                                  /* dedup: the slot it has */
    q->name = len <= 7 ? k.inl : (u64)(uintptr_t)s;
    q->meta = ((u64)len << 48) | ((u64)scope << 32) | ((u64)kind << 24) | value;
    t->used++;
    return q;
}

static u32 slot_val(Slot *t) { return (u32)(t->meta & 0xffffff); }
static u32 slot_kind(Slot *t) { return (u32)((t->meta >> 24) & 0xff); }
static void slot_setval(Slot *t, u32 v) { t->meta = (t->meta & ~(u64)0xffffff) | v; }
static int  slot_txt(Slot *t) { return (slot_kind(t) & K_TXT) != 0; }
static void slot_settxt(Slot *t) { t->meta |= (u64)K_TXT << 24; }
static void slot_clrtxt(Slot *t) { t->meta &= ~((u64)K_TXT << 24); }

/* --------------------------------------------------------- patch list
 * A branch to a name not yet defined is written with a zero and remembered;
 * at the end every remembered name has a place and the bytes are filled in. */

typedef struct { u32 at; const char *name; u32 nlen; } Patch;

static Patch *pat;
static u32 npat, patcap;

static void add_patch(u32 at, const char *name, u32 nlen)
{
    if (npat == patcap) {
        patcap = patcap ? patcap * 2 : 256;
        pat = xrealloc(pat, (u64)patcap * sizeof(Patch));
    }
    pat[npat].at = at; pat[npat].name = name; pat[npat].nlen = nlen;
    npat++;
}

/* ------------------------------------------------------ x86-64 emission
 * rax=0 rcx=1 rdx=2 rbx=3 rsp=4 rbp=5 rsi=6 rdi=7, then r8..r15. */

enum { RAX, RCX, RDX, RBX, RSP, RBP, RSI, RDI, R8, R9, R10, R11, R12, R13, R14, R15 };
static const int argreg[6] = { RDI, RSI, RDX, RCX, 8, 9 };

static void emrex(int w, int r, int x, int b)
{
    int v = 0x40 | (w ? 8 : 0) | (r ? 4 : 0) | (x ? 2 : 0) | (b ? 1 : 0);
    if (v != 0x40) cput((u8)v);
}

/* op r/m64, r64 : rm is the destination, reg the source */
static void x_rm_reg(u8 op, int rm, int reg)
{
    emrex(1, reg >= 8, 0, rm >= 8);
    cput(op);
    cput((u8)(0xc0 | ((reg & 7) << 3) | (rm & 7)));
}

static void x_mov_rr(int d, int s)  { x_rm_reg(0x89, d, s); }
static void x_add_rr(int d, int s)  { x_rm_reg(0x01, d, s); }
static void x_sub_rr(int d, int s)  { x_rm_reg(0x29, d, s); }
static void x_or_rr(int d, int s)   { x_rm_reg(0x09, d, s); }
static void x_and_rr(int d, int s)  { x_rm_reg(0x21, d, s); }
static void x_cmp_rr(int d, int s)  { x_rm_reg(0x39, d, s); }
static void x_test_rr(int d, int s) { x_rm_reg(0x85, d, s); }

static void x_push(int r) { if (r >= 8) cput(0x41); cput((u8)(0x50 | (r & 7))); }
static void x_pop(int r)  { if (r >= 8) cput(0x41); cput((u8)(0x58 | (r & 7))); }

static void x_mov_imm64(int r, u64 v)
{
    emrex(1, r >= 8, 0, 0); cput((u8)(0xb8 | (r & 7))); cput64(v);
}
static void x_mov_imm32(int r, u32 v)
{
    if (r >= 8) cput(0x41);
    cput((u8)(0xb8 | (r & 7)));
    cput32(v);
}

/* mov r, [rbp+disp32] / mov [rbp+disp32], r : a local, reached the long way */
static void x_mov_r_local(int r, i32 d)
{
    emrex(1, r >= 8, 0, 0); cput(0x8b);
    cput((u8)(0x85 | ((r & 7) << 3))); cput32((u32)d);
}
static void x_mov_local_r(i32 d, int r)
{
    emrex(1, r >= 8, 0, 0); cput(0x89);
    cput((u8)(0x85 | ((r & 7) << 3))); cput32((u32)d);
}

static void x_jmp(i32 rel)      { cput(0xe9); cput32((u32)rel); }

static void x_imul_rr(int d, int s)
{
    emrex(1, d >= 8, 0, s >= 8); cput(0x0f); cput(0xaf);
    cput((u8)(0xc0 | ((d & 7) << 3) | (s & 7)));
}
static void x_neg(int r)  { emrex(1, 0, 0, r >= 8); cput(0xf7); cput((u8)(0xd8 | (r & 7))); }
static void x_idiv(int r) { emrex(1, 0, 0, r >= 8); cput(0xf7); cput((u8)(0xf8 | (r & 7))); }
static void x_cqo(void)   { cput(0x48); cput(0x99); }
static void x_setal(u8 cc)    { cput(0x0f); cput(cc); cput(0xc0); }
static void x_movzx_eax_al(void) { cput(0x0f); cput(0xb6); cput(0xc0); }
static void x_xor_eax(void)   { cput(0x31); cput(0xc0); }
static void x_xor_ecx(void)   { cput(0x31); cput(0xc9); }
static void x_xor_edx(void)   { cput(0x31); cput(0xd2); }
static void x_leave(void)     { cput(0xc9); }
static void x_ret(void)       { cput(0xc3); }
static void x_syscall(void)   { cput(0x0f); cput(0x05); }
static void x_push_rbp(void)  { cput(0x55); }
static void x_mov_rbp_rsp(void) { cput(0x48); cput(0x89); cput(0xe5); }
static void x_sub_rsp_imm32(u32 v) { cput(0x48); cput(0x81); cput(0xec); cput32(v); }

/* --------------------------------------------------------- codegen state */

#define TEXT_ORG   0x401000ULL
#define DATA_VADDR 0x600000ULL

static u32 scope_serial;
static u32 cur_scope, nloc;      /* the function being built */
static u32 sub_off;              /* where its `sub rsp, imm32` lives */

static void patch_rel_at(u32 at, u64 target)
{
    bputat32(&code, at, (u32)((i64)target - (i64)(at + 4)));
}

/* an eight-bit jump written blind, its distance filled once the target is
 * known; every native below is small enough for the byte form */
static void patch_j8_at(u32 at, u64 target)
{
    code.p[at] = (u8)((i64)target - (i64)(at + 1));
}

/* a call/jmp/jcc to a name: direct when the name is already on file,
 * remembered for the end when it is not */
static u32 emit_branch(u8 kind, u8 cc, const char *nm, u32 nlen)
{
    Slot *t = sym_find(&gt, nm, nlen, 0);
    u32 at;
    if (kind == 0)      { cput(0xe8); at = (u32)code.len; cput32(0); }
    else if (kind == 1) { cput(0xe9); at = (u32)code.len; cput32(0); }
    else                { cput(0x0f); cput(cc); at = (u32)code.len; cput32(0); }
    if (t) {
        if ((slot_kind(t) & 0x7f) != K_FUNC) die2("not a function", nm, nlen);
        patch_rel_at(at, slot_val(t));
    } else {
        add_patch(at, nm, nlen);
    }
    return at;
}

static void def_label(const char *nm, u32 nlen)
{
    Slot *t = sym_define(&gt, nm, nlen, 0, K_FUNC, (u32)code.len);
    slot_setval(t, (u32)code.len);
}

/* names for the runtime's own labels: control characters, which no .sov
 * identifier can contain, so they cannot collide with anything parsed */
static const char L_POS[] = "\x01", L_DIG[] = "\x02", L_WR[] = "\x03";
static const char L_A_DONE[] = "\x04", L_A_LOOP[] = "\x05", L_A_POS[] = "\x06";
static const char N_MAIN[] = "main";
static const char N_ATOI[] = "_sov_atoi";
static const char N_PEEKP[] = "peek_ptr";
static const char N_PEEKB[] = "peek_byte";
static const char N_POKEB[] = "poke_byte";
static const char N_ALLOC[] = "_sov_alloc";
static const char N_EXIT[] = "sys_exit";
static const char N_PINT[] = "\x07print_int";
static const char N_PTEXT[] = "\x06ptext";
static const char N_ITOS[] = "\x05itos";
static const char N_INIT[] = "\x09init";
static const char N_STRLEN[] = "_sov_strlen";
static const char N_STRCAT[] = "_sov_strcat";
static const char N_STREQ[] = "_sov_str_eq";
static const char N_ARGC[] = "_sov_argc";
static const char N_ARGVG[] = "_sov_argv_get";
static const char N_LISTN[] = "_sov_list_new";
static const char N_LISTA[] = "_sov_list_add";
static const char N_LISTG[] = "_sov_list_get";
static const char N_LISTS[] = "_sov_list_set";
static const char N_LISTL[] = "_sov_list_len";
static const char N_MSET[] = "_sov_mem_set";
static const char N_MCOPY[] = "_sov_mem_copy";
static const char N_BAT[] = "_sov_byte_at";
static const char N_FREE[] = "_sov_free";
static const char N_HALLOC[] = "_sov_heap_alloc";
static const char N_PRINT[] = "_sov_print";
static const char N_PRINTI[] = "_sov_print_int";
static const char N_AADD[] = "atomic_add";
static const char N_ASTOR[] = "atomic_store";
static const char N_SREAD[] = "sys_read";
static const char N_SCLOSE[] = "sys_close";
static const char N_SGETPID[] = "sys_getpid";
static const char N_SUBS[] = "_sov_substring";
static const char N_TRIM[] = "_sov_trim";
static const char N_FIND[] = "_sov_find_text";
static const char N_STARTS[] = "_sov_starts_with";
static const char N_ALOAD[] = "atomic_load";
static const char N_BAND[] = "band";
static const char N_RTHEAP[] = "rt_heap";
static const char N_BOR[] = "bor";
static const char N_BXOR[] = "bxor";
static const char N_BSHL[] = "bshl";
static const char N_BSHR[] = "bshr";
static const char N_BSAR[] = "bsar";
static const char N_WIPE[] = "_sov_wipe";
static const char N_PI64[] = "peek_i64";
static const char N_POI64[] = "poke_i64";
static const char N_PR8[] = "peek_raw8";
static const char N_PR16[] = "peek_raw16";
static const char N_PR32[] = "peek_raw32";
static const char N_PR64[] = "peek_raw64";
static const char N_PO8[] = "poke_raw8";
static const char N_PO16[] = "poke_raw16";
static const char N_PO32[] = "poke_raw32";
static const char N_PO64[] = "poke_raw64";
static const char L2_POS[] = "\x10", L2_DIG[] = "\x11", L2_WR[] = "\x12";

/* the runtime names the program may call, with their answer types.  Only
 * text matters: a text answer flows into the caller's type. */
typedef struct { const char *name; u32 nlen; u8 txt; } Nat;
static const Nat nat_tab[] = {
    { "_sov_strcat", 11, 1 },
    { "_sov_substring", 14, 1 },
    { "_sov_trim", 9, 1 },
    { "_sov_argv_get", 13, 1 },
    { "_sov_strlen", 11, 0 },
    { "_sov_str_eq", 11, 0 },
    { "_sov_atoi", 9, 0 },
    { "_sov_alloc", 10, 0 },
    { "_sov_heap_alloc", 15, 0 },
    { "_sov_free", 9, 0 },
    { "_sov_list_new", 13, 0 },
    { "_sov_list_add", 13, 0 },
    { "_sov_list_get", 13, 0 },
    { "_sov_list_set", 13, 0 },
    { "_sov_list_len", 13, 0 },
    { "_sov_mem_set", 12, 0 },
    { "_sov_mem_copy", 13, 0 },
    { "_sov_byte_at", 12, 0 },
    { "_sov_print", 10, 0 },
    { "_sov_print_int", 14, 0 },
    { "_sov_argc", 9, 0 },
    { "atomic_add", 10, 0 },
    { "atomic_store", 12, 0 },
    { "atomic_load", 11, 0 },
    { "band", 4, 0 },
    { "rt_heap", 8, 0 },
    { "bor", 3, 0 },
    { "bxor", 4, 0 },
    { "bshl", 4, 0 },
    { "bshr", 4, 0 },
    { "bsar", 4, 0 },
    { "_sov_wipe", 10, 0 },
    { "peek_i64", 9, 0 },
    { "poke_i64", 9, 0 },
    { "peek_raw8", 10, 0 },
    { "peek_raw16", 11, 0 },
    { "peek_raw32", 11, 0 },
    { "peek_raw64", 11, 0 },
    { "poke_raw8", 10, 0 },
    { "poke_raw16", 11, 0 },
    { "poke_raw32", 11, 0 },
    { "poke_raw64", 11, 0 },
    { "poke_raw64", 10, 0 },
    { "peek_raw64", 10, 0 },
    { "sys_read", 8, 0 },
    { "sys_close", 9, 0 },
    { "sys_getpid", 10, 0 },
    { "sys_exit", 8, 0 },
    { "peek_ptr", 8, 0 },
    { "peek_byte", 9, 0 },
    { "poke_byte", 9, 0 },
};
static const Nat *nat_find(const char *s, u32 len)
{
    /* one bucket per first byte: the old linear scan walked ~45 entries on
     * every call and every miss, which the fns1m shape pays 24,000 times */
    static const Nat *bucket[256];
    static u8 init;
    if (!init) {
        u32 n = (u32)(sizeof(nat_tab) / sizeof(nat_tab[0]));
        for (u32 i = 0; i < n; i++)
            if (!bucket[(u8)nat_tab[i].name[0]])
                bucket[(u8)nat_tab[i].name[0]] = &nat_tab[i];
        init = 1;
    }
    const u8 c = (u8)s[0];
    const Nat *t = bucket[c];
    if (t && t->nlen == len && memcmp(t->name, s, len) == 0) return t;
    /* collision or miss: the walk, rarely taken */
    u32 n = (u32)(sizeof(nat_tab) / sizeof(nat_tab[0]));
    for (u32 i = 0; i < n; i++)
        if (nat_tab[i].nlen == len && memcmp(nat_tab[i].name, s, len) == 0)
            return &nat_tab[i];
    return 0;
}

/* the most recent call to a name that was not yet on file when it was
 * emitted; print uses it to decide the printer after the fact */
static const char *unk_nm;
static u32 unk_len;
static u8 cur_fn_txt;      /* does the function being built answer text */

/* ------------------------------------------------------ the mini-runtime
 * Fresh bytes, written here: _start, print_int, atoi, peek/poke, alloc, exit.
 * Nothing is taken from any other compiler's output. */

static void emit_runtime(void)
{
    /* data[0..31]: argc, argv, the heap cursor and spare, all written before
     * any literal lands; literals start at data+32 */
    for (int i = 0; i < 32; i++) bput(&data, 0);

    /* _start: argc and argv off the initial stack, then main, then exit(rax) */
    cput(0x48); cput(0x8b); cput(0x3c); cput(0x24);  /* mov rdi,[rsp] */
    cput(0x48); cput(0x8d); cput(0x74); cput(0x24); cput(0x08); /* lea rsi,[rsp+8] */
    cput(0x48); cput(0x83); cput(0xe4); cput(0xf0);  /* and rsp,-16 */
    x_mov_imm64(RAX, DATA_VADDR);                   /* stash them for the natives */
    cput(0x48); cput(0x89); cput(0x38);             /* mov [rax],rdi */
    cput(0x48); cput(0x89); cput(0x70); cput(0x08); /* mov [rax+8],rsi */
    emit_branch(0, 0, N_MAIN, sizeof N_MAIN - 1);                                                /* call main */
    x_mov_rr(RDI, RAX);
    x_mov_imm32(RAX, 60);
    x_syscall();

    /* \x07print_int: rdi = value.  Decimal, signed, newline, one write. */
    def_label(N_PINT, sizeof N_PINT - 1);
    cput(0x48); cput(0x83); cput(0xec); cput(0x30);  /* sub rsp,48 */
    x_mov_rr(RAX, RDI);
    cput(0x4c); cput(0x8d); cput(0x4c); cput(0x24); cput(0x28); /* lea r9,[rsp+40] */
    cput(0x45); cput(0x31); cput(0xc0);                     /* xor r8d,r8d */
    x_test_rr(RAX, RAX);
    emit_branch(2, 0x89, L_POS, 1);                                              /* jns 1: */
    cput(0x41); cput(0xb8); cput32(1);                      /* mov r8d,1 */
    x_neg(RAX);
    def_label(L_POS, 1);
    x_mov_imm32(RCX, 10);
    def_label(L_DIG, 1);
    cput(0x31); cput(0xd2);                                        /* xor edx,edx */
    cput(0x48); cput(0xf7); cput(0xf1);                     /* div rcx */
    cput(0x80); cput(0xc2); cput(0x30);                     /* add dl,'0' */
    cput(0x49); cput(0xff); cput(0xc9);                     /* dec r9 */
    cput(0x41); cput(0x88); cput(0x11);                     /* mov [r9],dl */
    x_test_rr(RAX, RAX);
    emit_branch(2, 0x85, L_DIG, 1);                                              /* jnz 2: */
    cput(0x45); cput(0x85); cput(0xc0);                     /* test r8d,r8d */
    emit_branch(2, 0x84, L_WR, 1);                                               /* jz 3: */
    cput(0x49); cput(0xff); cput(0xc9);                     /* dec r9 */
    cput(0x41); cput(0xc6); cput(0x01); cput(0x2d);  /* mov byte [r9],'-' */
    def_label(L_WR, 1);
    cput(0xc6); cput(0x44); cput(0x24); cput(0x28); cput(0x0a); /* mov byte [rsp+40],10 */
    cput(0x48); cput(0x8d); cput(0x54); cput(0x24); cput(0x29); /* lea rdx,[rsp+41] */
    cput(0x4c); cput(0x29); cput(0xca);                     /* sub rdx,r9 */
    cput(0x4c); cput(0x89); cput(0xce);                     /* mov rsi,r9 */
    x_mov_imm32(RAX, 1);
    x_mov_imm32(RDI, 1);
    x_syscall();
    cput(0x48); cput(0x83); cput(0xc4); cput(0x30);  /* add rsp,48 */
    x_ret();

    /* _sov_atoi: rdi = digits, maybe a minus.  NULL and junk read as 0. */
    def_label(N_ATOI, sizeof N_ATOI - 1);
    x_xor_eax();
    x_test_rr(RDI, RDI);
    emit_branch(2, 0x84, L_A_DONE, 1);                                           /* jz 4: */
    cput(0x45); cput(0x31); cput(0xc0);                     /* xor r8d,r8d */
    cput(0x80); cput(0x3f); cput(0x2d);                     /* cmp byte [rdi],'-' */
    emit_branch(2, 0x85, L_A_LOOP, 1);                                           /* jne 5: */
    cput(0x41); cput(0xb8); cput32(1);                      /* mov r8d,1 */
    cput(0x48); cput(0xff); cput(0xc7);                     /* inc rdi */
    def_label(L_A_LOOP, 1);
    cput(0x0f); cput(0xb6); cput(0x0f);                     /* movzx ecx,[rdi] */
    cput(0x83); cput(0xe9); cput(0x30);                     /* sub ecx,'0' */
    cput(0x83); cput(0xf9); cput(0x09);                     /* cmp ecx,9 */
    emit_branch(2, 0x87, L_A_DONE, 1);                                           /* ja 4: */
    cput(0x48); cput(0x6b); cput(0xc0); cput(0x0a);  /* imul rax,rax,10 */
    x_add_rr(RAX, RCX);
    cput(0x48); cput(0xff); cput(0xc7);                     /* inc rdi */
    emit_branch(1, 0, L_A_LOOP, 1);                                              /* jmp 5: */
    def_label(L_A_DONE, 1);
    cput(0x45); cput(0x85); cput(0xc0);                     /* test r8d,r8d */
    emit_branch(2, 0x84, L_A_POS, 1);                                            /* jz 6: */
    x_neg(RAX);
    def_label(L_A_POS, 1);
    x_ret();

    /* peek_ptr: rdi = base, rsi = index -> rax = the qword there */
    def_label(N_PEEKP, sizeof N_PEEKP - 1);
    cput(0x48); cput(0x8b); cput(0x04); cput(0xf7);  /* mov rax,[rdi+rsi*8] */
    x_ret();

    /* peek_byte: -> rax = the byte there */
    def_label(N_PEEKB, sizeof N_PEEKB - 1);
    cput(0x0f); cput(0xb6); cput(0x04); cput(0x37);  /* movzx eax,[rdi+rsi] */
    x_ret();

    /* poke_byte: rdx = the value */
    def_label(N_POKEB, sizeof N_POKEB - 1);
    cput(0x88); cput(0x14); cput(0x37);                     /* mov [rdi+rsi],dl */
    x_ret();

    /* _sov_alloc: rdi = size -> rax = a block off the break, bumped, no free.
     * The break cursor lives at data+24 so heap_ptr can read it. */
    def_label(N_ALLOC, sizeof N_ALLOC - 1);
    x_push(RBX);
    x_push(RDI);
    cput(0x31); cput(0xff);                                        /* xor edi,edi */
    x_mov_imm32(RAX, 12);                                                        /* brk(0) */
    x_syscall();
    x_pop(RDI);
    cput(0x48); cput(0x8d); cput(0x7c); cput(0x38); cput(0x0f); /* lea rdi,[rax+rdi+15] */
    cput(0x48); cput(0x83); cput(0xe7); cput(0xf0);  /* and rdi,-16 */
    x_mov_rr(RBX, RAX);
    x_mov_imm32(RAX, 12);                                                        /* brk(new) */
    x_syscall();
    x_mov_imm64(RCX, DATA_VADDR + 24);
    cput(0x48); cput(0x89); cput(0x01);                          /* mov [rcx],rax */
    x_mov_rr(RAX, RBX);
    x_pop(RBX);
    x_ret();

    /* rt_heap: seed the break cursor; the answer is the current break */
    def_label(N_RTHEAP, sizeof N_RTHEAP - 1);
    cput(0x31); cput(0xff);                                        /* xor edi,edi */
    x_mov_imm32(RAX, 12);
    x_syscall();
    x_mov_imm64(RCX, DATA_VADDR + 24);
    cput(0x48); cput(0x89); cput(0x01);                          /* mov [rcx],rax */
    x_ret();

    /* sys_exit: rdi = code */
    def_label(N_EXIT, sizeof N_EXIT - 1);
    x_mov_imm32(RAX, 60);
    x_syscall();

    /* \x06ptext: rdi = a text.  Its bytes, then a newline; blank gives one. */
    def_label(N_PTEXT, sizeof N_PTEXT - 1);
    x_test_rr(RDI, RDI);
    u32 t1 = (u32)code.len + 1; cput(0x74); cput(0);            /* jz nl */
    x_mov_rr(RSI, RDI);
    x_xor_eax();
    u32 t2 = (u32)code.len;
    cput(0x80); cput(0x3c); cput(0x06); cput(0x00);             /* cmp byte [rsi+rax],0 */
    u32 t3 = (u32)code.len + 1; cput(0x74); cput(0);            /* jz wr */
    cput(0x48); cput(0xff); cput(0xc0);                          /* inc rax */
    x_jmp((i32)t2 - (i32)(code.len + 5));
    patch_j8_at(t3, code.len);                                   /* wr: */
    x_mov_rr(RDX, RAX);
    x_mov_imm32(RAX, 1); x_mov_imm32(RDI, 1);
    x_syscall();
    patch_j8_at(t1, code.len);                                   /* nl: */
    cput(0x6a); cput(0x0a);                                      /* push 10 */
    x_mov_rr(RSI, RSP);
    x_mov_imm32(RAX, 1); x_mov_imm32(RDI, 1); x_mov_imm32(RDX, 1);
    x_syscall();
    x_pop(RAX);
    x_ret();

    /* _sov_strlen: rdi = text -> rax.  NULL reads as zero. */
    def_label(N_STRLEN, sizeof N_STRLEN - 1);
    x_xor_eax();
    x_test_rr(RDI, RDI);
    u32 u1 = (u32)code.len + 1; cput(0x74); cput(0);            /* jz out */
    u32 u2 = (u32)code.len;
    cput(0x80); cput(0x3c); cput(0x07); cput(0x00);             /* cmp byte [rdi+rax],0 */
    u32 u3 = (u32)code.len + 1; cput(0x74); cput(0);
    cput(0x48); cput(0xff); cput(0xc0);
    x_jmp((i32)u2 - (i32)(code.len + 5));
    patch_j8_at(u3, code.len);
    patch_j8_at(u1, code.len);
    x_ret();

    /* _sov_str_eq: byte compare to the terminator, 1 or 0 */
    def_label(N_STREQ, sizeof N_STREQ - 1);
    u32 v1 = (u32)code.len;
    cput(0x8a); cput(0x07);                                      /* mov al,[rdi] */
    cput(0x8a); cput(0x0e);                                      /* mov cl,[rsi] */
    cput(0x38); cput(0xc8);                                      /* cmp al,cl */
    u32 v2 = (u32)code.len + 1; cput(0x75); cput(0);            /* jne no */
    cput(0x84); cput(0xc0);                                      /* test al,al */
    u32 v3 = (u32)code.len + 1; cput(0x74); cput(0);            /* jz yes */
    cput(0x48); cput(0xff); cput(0xc7);                          /* inc rdi */
    cput(0x48); cput(0xff); cput(0xc6);                          /* inc rsi */
    x_jmp((i32)v1 - (i32)(code.len + 5));
    patch_j8_at(v3, code.len);                                   /* yes: */
    x_mov_imm32(RAX, 1); x_ret();
    patch_j8_at(v2, code.len);                                   /* no: */
    x_xor_eax(); x_ret();

    /* _sov_strcat: rdi, rsi = texts -> rax = a fresh joined text */
    def_label(N_STRCAT, sizeof N_STRCAT - 1);
    x_push(RBX); x_push(R12); x_push(R13); x_push(R14); x_push(R15);
    x_mov_rr(R12, RDI);                                          /* a */
    x_mov_rr(R13, RSI);                                          /* b */
    cput(0x45); cput(0x31); cput(0xf6);                          /* xor r14d,r14d */
    u32 w1 = (u32)code.len;
    x_test_rr(R12, R12);
    u32 w2 = (u32)code.len + 1; cput(0x74); cput(0);
    cput(0x43); cput(0x80); cput(0x3c); cput(0x26); cput(0x00);  /* cmp byte [r14+r12],0 */
    u32 w3 = (u32)code.len + 1; cput(0x74); cput(0);
    cput(0x49); cput(0xff); cput(0xc6);                          /* inc r14 */
    x_jmp((i32)w1 - (i32)(code.len + 5));
    patch_j8_at(w2, code.len); patch_j8_at(w3, code.len);
    cput(0x45); cput(0x31); cput(0xff);                          /* xor r15d,r15d */
    u32 w4 = (u32)code.len;
    x_test_rr(R13, R13);
    u32 w5 = (u32)code.len + 1; cput(0x74); cput(0);
    cput(0x43); cput(0x80); cput(0x3c); cput(0x2f); cput(0x00);  /* cmp byte [r15+r13],0 */
    u32 w6 = (u32)code.len + 1; cput(0x74); cput(0);
    cput(0x49); cput(0xff); cput(0xc7);                          /* inc r15 */
    x_jmp((i32)w4 - (i32)(code.len + 5));
    patch_j8_at(w5, code.len); patch_j8_at(w6, code.len);
    cput(0x4c); cput(0x89); cput(0xf7);                          /* mov rdi,r14 */
    cput(0x4c); cput(0x01); cput(0xff);                          /* add rdi,r15 */
    cput(0x48); cput(0xff); cput(0xc7);                          /* inc rdi: la+lb+1 */
    emit_branch(0, 0, N_ALLOC, sizeof N_ALLOC - 1);
    x_mov_rr(RBX, RAX);                                          /* out */
    cput(0x45); cput(0x31); cput(0xc0);                          /* xor r8d,r8d */
    u32 w7 = (u32)code.len;
    cput(0x4d); cput(0x39); cput(0xf0);                          /* cmp r8,r14 */
    u32 w8 = (u32)code.len + 1; cput(0x73); cput(0);             /* jae b */
    cput(0x43); cput(0x8a); cput(0x04); cput(0x04);              /* mov al,[r12+r8] */
    cput(0x42); cput(0x88); cput(0x04); cput(0x03);              /* mov [rbx+r8],al */
    cput(0x49); cput(0xff); cput(0xc0);                          /* inc r8 */
    x_jmp((i32)w7 - (i32)(code.len + 5));
    patch_j8_at(w8, code.len);                                   /* b: */
    cput(0x49); cput(0x89); cput(0xda);                          /* mov r10,rbx */
    cput(0x4d); cput(0x01); cput(0xf2);                          /* add r10,r14 */
    cput(0x45); cput(0x31); cput(0xc9);                          /* xor r9d,r9d */
    u32 w9 = (u32)code.len;
    cput(0x4d); cput(0x39); cput(0xf9);                          /* cmp r9,r15 */
    u32 wa = (u32)code.len + 1; cput(0x73); cput(0);
    cput(0x43); cput(0x8a); cput(0x44); cput(0x0d); cput(0x00);  /* mov al,[r13+r9] */
    cput(0x43); cput(0x88); cput(0x04); cput(0x0a);              /* mov [r10+r9],al */
    cput(0x49); cput(0xff); cput(0xc1);                          /* inc r9 */
    x_jmp((i32)w9 - (i32)(code.len + 5));
    patch_j8_at(wa, code.len);
    cput(0x43); cput(0xc6); cput(0x04); cput(0x3a); cput(0x00);  /* mov byte [r10+r15],0 */
    x_mov_rr(RAX, RBX);
    x_pop(R15); x_pop(R14); x_pop(R13); x_pop(R12); x_pop(RBX);
    x_ret();

    /* _sov_substring s start end: rdi, rsi, rdx -> rax = s[start..end) fresh.
     * Clamped like the old runtime: start<0 to 0, end>n to n, end<start to
     * start; a null pointer reads as blank. */
    def_label(N_SUBS, sizeof N_SUBS - 1);
    x_push(RBX); x_push(R12); x_push(R13); x_push(R14); x_push(R15);
    x_mov_rr(R12, RDI);                               /* s */
    x_mov_rr(R13, RSI);                               /* start */
    x_mov_rr(R14, RDX);                               /* end */
    cput(0x49); cput(0x81); cput(0xfc); cput32(4096); /* cmp r12,4096 */
    u32 sb1 = (u32)code.len + 1; cput(0x73); cput(0); /* jae ok */
    x_xor_eax();
    u32 sb2 = (u32)code.len + 1; cput(0xeb); cput(0); /* jmp out */
    patch_j8_at(sb1, code.len);                       /* ok: */
    x_mov_rr(RDI, R12);
    emit_branch(0, 0, N_STRLEN, sizeof N_STRLEN - 1);                  /* rax = n */
    x_mov_rr(R15, RAX);
    x_test_rr(R13, R13);
    u32 sb3 = (u32)code.len + 1; cput(0x79); cput(0); /* jns s1 */
    cput(0x45); cput(0x31); cput(0xed);               /* xor r13d,r13d */
    patch_j8_at(sb3, code.len);                       /* s1: */
    x_cmp_rr(R14, R15);
    u32 sb4 = (u32)code.len + 1; cput(0x7e); cput(0); /* jle s2 */
    x_mov_rr(R14, R15);
    patch_j8_at(sb4, code.len);                       /* s2: */
    x_cmp_rr(R14, R13);
    u32 sb5 = (u32)code.len + 1; cput(0x7d); cput(0); /* jge s3 */
    x_mov_rr(R14, R13);
    patch_j8_at(sb5, code.len);                       /* s3: */
    x_mov_rr(RDI, R14);
    x_sub_rr(RDI, R13);
    cput(0x48); cput(0xff); cput(0xc7);               /* inc rdi: L+1 */
    emit_branch(0, 0, N_ALLOC, sizeof N_ALLOC - 1);
    x_mov_rr(RBX, RAX);                               /* out */
    x_mov_rr(RSI, R12);
    x_add_rr(RSI, R13);                               /* s + start */
    x_mov_rr(RDI, RBX);
    x_mov_rr(RCX, R14);
    x_sub_rr(RCX, R13);                               /* L */
    cput(0xf3); cput(0xa4);                           /* rep movsb */
    cput(0xc6); cput(0x07); cput(0x00);               /* mov byte [rdi],0 */
    x_mov_rr(RAX, RBX);
    patch_j8_at(sb2, code.len);                       /* out: */
    x_pop(R15); x_pop(R14); x_pop(R13); x_pop(R12); x_pop(RBX);
    x_ret();

    /* _sov_trim s: rdi -> rax.  Spaces, tabs, newlines and returns off both
     * ends; an all-blank or untouched text comes back as itself. */
    def_label(N_TRIM, sizeof N_TRIM - 1);
    x_push(R12); x_push(R13); x_push(R14); x_push(R15);
    x_mov_rr(R12, RDI);                               /* s */
    cput(0x45); cput(0x31); cput(0xed);               /* xor r13d,r13d  a */
    x_test_rr(R12, R12);
    u32 tm0 = (u32)code.len + 1; cput(0x75); cput(0); /* jnz t1 */
    x_xor_eax();
    u32 tm9 = (u32)code.len + 1; cput(0xe9); cput32(0); /* jmp out (far) */
    patch_j8_at(tm0, code.len);                       /* t1: */
    x_mov_rr(RDI, R12);
    emit_branch(0, 0, N_STRLEN, sizeof N_STRLEN - 1);
    x_mov_rr(R15, RAX);                               /* n */
    x_mov_rr(R14, R15);                               /* b = n */
    u32 ta = (u32)code.len;                           /* ta: */
    cput(0x43); cput(0x0f); cput(0xb6); cput(0x04); cput(0x2c);  /* movzx eax,[r12+r13] */
    cput(0x3c); cput(0x20); u32 ta1 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);
    cput(0x3c); cput(0x09); u32 ta2 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);
    cput(0x3c); cput(0x0a); u32 ta3 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);
    cput(0x3c); cput(0x0d); u32 ta4 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);
    u32 tb = (u32)code.len + 1; cput(0xeb); cput(0);   /* jmp tdone */
    patch_rel_at(ta1, code.len); patch_rel_at(ta2, code.len);
    patch_rel_at(ta3, code.len); patch_rel_at(ta4, code.len);
    cput(0x49); cput(0xff); cput(0xc5);               /* inc r13 */
    x_jmp((i32)ta - (i32)(code.len + 5));
    patch_j8_at(tb, code.len);                        /* tdone: */
    u32 tc = (u32)code.len;                           /* tc: */
    x_cmp_rr(R14, R13);
    u32 tc0 = (u32)code.len + 1; cput(0x7e); cput(0); /* jle tfin */
    cput(0x43); cput(0x0f); cput(0xb6); cput(0x44); cput(0x34); cput(0xff); /* movzx eax,[r12+r14-1] */
    cput(0x3c); cput(0x20); u32 tc1 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);
    cput(0x3c); cput(0x09); u32 tc2 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);
    cput(0x3c); cput(0x0a); u32 tc3 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);
    cput(0x3c); cput(0x0d); u32 tc4 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);
    u32 td = (u32)code.len + 1; cput(0xeb); cput(0);   /* jmp tfin */
    patch_rel_at(tc1, code.len); patch_rel_at(tc2, code.len);
    patch_rel_at(tc3, code.len); patch_rel_at(tc4, code.len);
    cput(0x49); cput(0xff); cput(0xce);               /* dec r14 */
    x_jmp((i32)tc - (i32)(code.len + 5));
    patch_j8_at(tc0, code.len); patch_j8_at(td, code.len);  /* tfin: */
    x_test_rr(R13, R13);
    u32 te = (u32)code.len + 1; cput(0x75); cput(0);  /* jne tsub */
    x_cmp_rr(R14, R15);
    u32 te2 = (u32)code.len + 1; cput(0x75); cput(0); /* jne tsub */
    x_mov_rr(RAX, R12);                               /* untouched: itself */
    u32 tf = (u32)code.len + 1; cput(0xeb); cput(0);  /* jmp out */
    patch_j8_at(te, code.len); patch_j8_at(te2, code.len);   /* tsub: */
    x_mov_rr(RDI, R12);
    x_mov_rr(RSI, R13);
    x_mov_rr(RDX, R14);
    emit_branch(0, 0, N_SUBS, sizeof N_SUBS - 1);                    /* the substring copy */
    patch_j8_at(tf, code.len); patch_rel_at(tm9, code.len);    /* out: */
    x_pop(R15); x_pop(R14); x_pop(R13); x_pop(R12);
    x_ret();

    /* _sov_find_text s n: rdi, rsi -> rax = the first index of n in s, or -1.
     * NULL s reads -1; an empty n reads 0.  Naive scan; the old runtime's
     * horspool skipping is a speed detail with the same answer. */
    def_label(N_FIND, sizeof N_FIND - 1);
    x_push(R12); x_push(R13);
    x_mov_rr(R12, RDI);
    x_mov_rr(R13, RSI);
    x_test_rr(R12, R12);
    u32 fi0 = (u32)code.len + 2; cput(0x0f); cput(0x85); cput32(0);  /* jnz f1 */
    cput(0x48); cput(0xc7); cput(0xc0); cput32(0xffffffff);   /* mov rax,-1 */
    u32 fi9 = (u32)code.len + 1; cput(0xeb); cput(0);          /* jmp out */
    patch_rel_at(fi0, code.len);                               /* f1: */
    cput(0x43); cput(0x80); cput(0x7d); cput(0x00); cput(0x00); /* cmp byte [r13],0 */
    u32 fi1 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);  /* jz fz */
    x_xor_ecx();
    u32 fa = (u32)code.len;                                    /* fa: */
    cput(0x41); cput(0x0f); cput(0xb6); cput(0x04); cput(0x0c);  /* movzx eax,[r12+rcx] */
    x_test_rr(RAX, RAX);
    u32 fa1 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);  /* jz fm1 */
    x_xor_edx();
    u32 fb = (u32)code.len;                                    /* fb: */
    cput(0x4c); cput(0x8d); cput(0x04); cput(0x11);            /* lea r8,[rcx+rdx] */
    cput(0x43); cput(0x0f); cput(0xb6); cput(0x04); cput(0x04);  /* movzx eax,[r12+r8] */
    cput(0x45); cput(0x0f); cput(0xb6); cput(0x4c); cput(0x15); cput(0x00);  /* movzx r9d,[r13+rdx] */
    cput(0x45); cput(0x84); cput(0xc9);                        /* test r9b,r9b */
    u32 fb1 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);  /* jz fyes */
    cput(0x44); cput(0x38); cput(0xc8);                        /* cmp al,r9b */
    u32 fb2 = (u32)code.len + 2; cput(0x0f); cput(0x85); cput32(0);  /* jne fnx */
    cput(0x48); cput(0xff); cput(0xc2);                        /* inc rdx */
    x_jmp((i32)fb - (i32)(code.len + 5));
    patch_rel_at(fb2, code.len);                               /* fnx: */
    cput(0x48); cput(0xff); cput(0xc1);                        /* inc rcx */
    x_jmp((i32)fa - (i32)(code.len + 5));
    patch_rel_at(fa1, code.len);                               /* fm1: */
    cput(0x48); cput(0xc7); cput(0xc0); cput32(0xffffffff);   /* mov rax,-1 */
    u32 fi8 = (u32)code.len + 1; cput(0xeb); cput(0);          /* jmp out */
    patch_rel_at(fb1, code.len);                               /* fyes: */
    x_mov_rr(RAX, RCX);
    u32 fg = (u32)code.len + 1; cput(0xeb); cput(0);           /* jmp out */
    patch_rel_at(fi1, code.len);                               /* fz: rax = 0 */
    x_xor_eax();
    patch_j8_at(fg, code.len); patch_j8_at(fi8, code.len); patch_j8_at(fi9, code.len);    /* out: */
    x_pop(R13); x_pop(R12);
    x_ret();

    /* _sov_starts_with s p: rdi, rsi -> rax = 1 or 0 */
    def_label(N_STARTS, sizeof N_STARTS - 1);
    x_push(R12); x_push(R13);
    x_mov_rr(R12, RDI);
    x_mov_rr(R13, RSI);
    x_test_rr(R12, R12);
    u32 sw0 = (u32)code.len + 2; cput(0x0f); cput(0x85); cput32(0);  /* jnz s1 */
    x_xor_eax();
    u32 sw9 = (u32)code.len + 1; cput(0xeb); cput(0);          /* jmp out */
    patch_rel_at(sw0, code.len);                               /* s1: */
    x_test_rr(R13, R13);
    u32 sw1 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);  /* jz yes */
    x_xor_ecx();
    u32 sa = (u32)code.len;                                    /* sa: */
    cput(0x45); cput(0x0f); cput(0xb6); cput(0x4c); cput(0x0d); cput(0x00);  /* movzx r9d,[r13+rcx] */
    cput(0x45); cput(0x84); cput(0xc9);                        /* test r9b,r9b */
    u32 sa1 = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);  /* jz yes */
    cput(0x41); cput(0x0f); cput(0xb6); cput(0x04); cput(0x0c);  /* movzx eax,[r12+rcx] */
    cput(0x44); cput(0x38); cput(0xc8);                        /* cmp al,r9b */
    u32 sa2 = (u32)code.len + 2; cput(0x0f); cput(0x85); cput32(0);  /* jne no */
    cput(0x48); cput(0xff); cput(0xc1);                        /* inc rcx */
    x_jmp((i32)sa - (i32)(code.len + 5));
    patch_rel_at(sa2, code.len);                               /* no: */
    x_xor_eax();
    u32 sw8 = (u32)code.len + 1; cput(0xeb); cput(0);          /* jmp out */
    patch_rel_at(sa1, code.len); patch_rel_at(sw1, code.len);  /* yes: */
    x_mov_imm32(RAX, 1);
    patch_j8_at(sw8, code.len); patch_j8_at(sw9, code.len);    /* out: */
    x_pop(R13); x_pop(R12);
    x_ret();

    /* \x05itos: rdi = an int -> rax = its decimal text, fresh bytes */
    def_label(N_ITOS, sizeof N_ITOS - 1);
    x_push(RBX); x_push(R12); x_push(R13); x_push(R14);
    x_mov_rr(R12, RDI);
    cput(0x48); cput(0x83); cput(0xec); cput(0x30);              /* sub rsp,48 */
    cput(0x4c); cput(0x8d); cput(0x6c); cput(0x24); cput(0x2c);  /* lea r13,[rsp+44] */
    cput(0x45); cput(0x31); cput(0xf6);                          /* xor r14d,r14d */
    x_test_rr(R12, R12);
    u32 i1 = (u32)code.len + 1; cput(0x75); cput(0);             /* jns pos */
    cput(0x41); cput(0xb8); cput32(1);                           /* mov r8d,1 */
    x_neg(R12);
    patch_j8_at(i1, code.len);                                   /* pos: */
    x_mov_imm32(RCX, 10);
    u32 i2 = (u32)code.len;                                      /* dig: */
    x_mov_rr(RAX, R12);
    cput(0x31); cput(0xd2);                                      /* xor edx,edx */
    cput(0x48); cput(0xf7); cput(0xf1);                          /* div rcx */
    x_mov_rr(R12, RAX);
    cput(0x80); cput(0xc2); cput(0x30);                          /* add dl,'0' */
    cput(0x49); cput(0xff); cput(0xcd);                          /* dec r13 */
    cput(0x41); cput(0x88); cput(0x55); cput(0x00);              /* mov byte [r13],dl */
    x_test_rr(R12, R12);
    u32 i3 = (u32)code.len + 1; cput(0x75); cput(0);
    patch_j8_at(i3, i2);                                         /* jnz dig */
    cput(0x45); cput(0x85); cput(0xc0);                          /* test r8d,r8d */
    u32 i4 = (u32)code.len + 1; cput(0x74); cput(0);             /* jz wr */
    cput(0x49); cput(0xff); cput(0xcd);                          /* dec r13 */
    cput(0x41); cput(0xc6); cput(0x45); cput(0x00); cput(0x2d);  /* mov byte [r13],'-' */
    patch_j8_at(i4, code.len);                                   /* wr: */
    cput(0x4c); cput(0x8d); cput(0x74); cput(0x24); cput(0x2c);  /* lea r14,[rsp+44] */
    cput(0x4d); cput(0x29); cput(0xee);                          /* sub r14,r13 */
    cput(0x49); cput(0x8d); cput(0x7e); cput(0x01);              /* lea rdi,[r14+1] */
    emit_branch(0, 0, N_ALLOC, sizeof N_ALLOC - 1);
    x_mov_rr(RBX, RAX);
    x_mov_rr(RSI, R13); x_mov_rr(RDI, RBX); x_mov_rr(RCX, R14);
    cput(0xf3); cput(0xa4);                                      /* rep movsb */
    cput(0xc6); cput(0x07); cput(0x00);                          /* mov byte [rdi],0 */
    x_mov_rr(RAX, RBX);
    cput(0x48); cput(0x83); cput(0xc4); cput(0x30);              /* add rsp,48 */
    x_pop(R14); x_pop(R13); x_pop(R12); x_pop(RBX);
    x_ret();

    /* _sov_print: rdi = text, its bytes, NO newline */
    def_label(N_PRINT, sizeof N_PRINT - 1);
    x_test_rr(RDI, RDI);
    u32 p1 = (u32)code.len + 1; cput(0x74); cput(0);             /* jz out */
    x_mov_rr(RSI, RDI);
    x_xor_eax();
    u32 p2 = (u32)code.len;
    cput(0x80); cput(0x3c); cput(0x06); cput(0x00);              /* cmp byte [rsi+rax],0 */
    u32 p3 = (u32)code.len + 1; cput(0x74); cput(0);
    cput(0x48); cput(0xff); cput(0xc0);
    x_jmp((i32)p2 - (i32)(code.len + 5));
    patch_j8_at(p3, code.len);
    x_mov_rr(RDX, RAX);
    x_mov_imm32(RAX, 1); x_mov_imm32(RDI, 1);
    x_syscall();
    patch_j8_at(p1, code.len);
    x_ret();

    /* _sov_print_int: rdi = a value, its digits, NO newline */
    def_label(N_PRINTI, sizeof N_PRINTI - 1);
    cput(0x48); cput(0x83); cput(0xec); cput(0x30);              /* sub rsp,48 */
    x_mov_rr(RAX, RDI);
    cput(0x4c); cput(0x8d); cput(0x4c); cput(0x24); cput(0x28);  /* lea r9,[rsp+40] */
    cput(0x45); cput(0x31); cput(0xc0);                          /* xor r8d,r8d */
    x_test_rr(RAX, RAX);
    emit_branch(2, 0x89, L2_POS, 1);                             /* jns pos */
    cput(0x41); cput(0xb8); cput32(1);                           /* mov r8d,1 */
    x_neg(RAX);
    def_label(L2_POS, 1);
    x_mov_imm32(RCX, 10);
    def_label(L2_DIG, 1);
    cput(0x31); cput(0xd2);                                      /* xor edx,edx */
    cput(0x48); cput(0xf7); cput(0xf1);                          /* div rcx */
    cput(0x80); cput(0xc2); cput(0x30);                          /* add dl,'0' */
    cput(0x49); cput(0xff); cput(0xc9);                          /* dec r9 */
    cput(0x41); cput(0x88); cput(0x11);                          /* mov [r9],dl */
    x_test_rr(RAX, RAX);
    emit_branch(2, 0x85, L2_DIG, 1);                             /* jnz dig */
    cput(0x45); cput(0x85); cput(0xc0);                          /* test r8d,r8d */
    emit_branch(2, 0x84, L2_WR, 1);                              /* jz wr */
    cput(0x49); cput(0xff); cput(0xc9);                          /* dec r9 */
    cput(0x41); cput(0xc6); cput(0x01); cput(0x2d);              /* mov byte [r9],'-' */
    def_label(L2_WR, 1);
    cput(0x48); cput(0x8d); cput(0x54); cput(0x24); cput(0x28);  /* lea rdx,[rsp+40] */
    cput(0x4c); cput(0x29); cput(0xca);                          /* sub rdx,r9 */
    cput(0x4c); cput(0x89); cput(0xce);                          /* mov rsi,r9 */
    x_mov_imm32(RAX, 1);
    x_mov_imm32(RDI, 1);
    x_syscall();
    cput(0x48); cput(0x83); cput(0xc4); cput(0x30);              /* add rsp,48 */
    x_ret();

    /* _sov_argc / _sov_argv_get: read the stash _start wrote */
    def_label(N_ARGC, sizeof N_ARGC - 1);
    x_mov_imm64(RAX, DATA_VADDR);
    cput(0x48); cput(0x8b); cput(0x00);                          /* mov rax,[rax] */
    x_ret();
    def_label(N_ARGVG, sizeof N_ARGVG - 1);
    x_mov_imm64(RAX, DATA_VADDR + 8);
    cput(0x48); cput(0x8b); cput(0x00);                          /* mov rax,[rax] */
    cput(0x48); cput(0x8b); cput(0x04); cput(0xf8);              /* mov rax,[rax+rdi*8] */
    x_ret();

    /* the list: three words -- len, cap, ptr.  add grows and moves. */
    def_label(N_LISTN, sizeof N_LISTN - 1);
    x_mov_imm32(RDI, 24);
    emit_branch(0, 0, N_ALLOC, sizeof N_ALLOC - 1);
    cput(0x48); cput(0xc7); cput(0x00); cput32(0);               /* mov qword [rax],0 */
    cput(0x48); cput(0xc7); cput(0x40); cput(0x08); cput32(0);
    cput(0x48); cput(0xc7); cput(0x40); cput(0x10); cput32(0);
    x_ret();
    def_label(N_LISTA, sizeof N_LISTA - 1);
    x_push(RBX);
    x_mov_rr(RBX, RDI);                                          /* lst */
    cput(0x49); cput(0x89); cput(0xf0);                          /* mov r8,rsi */
    cput(0x48); cput(0x8b); cput(0x0b);                          /* mov rcx,[rbx] */
    cput(0x48); cput(0x8b); cput(0x53); cput(0x08);              /* mov rdx,[rbx+8] */
    x_cmp_rr(RCX, RDX);
    u32 l1 = (u32)code.len + 1; cput(0x72); cput(0);             /* jb fit */
    x_test_rr(RDX, RDX);
    u32 l2 = (u32)code.len + 1; cput(0x75); cput(0);             /* jnz dbl */
    x_mov_imm32(RDX, 4);
    u32 l3 = (u32)code.len + 1; cput(0xeb); cput(0);             /* jmp g */
    patch_j8_at(l2, code.len);                                   /* dbl: */
    cput(0x48); cput(0x01); cput(0xd2);                          /* add rdx,rdx */
    patch_j8_at(l3, code.len);                                   /* g: */
    cput(0x4c); cput(0x8b); cput(0x4b); cput(0x10);              /* mov r9,[rbx+16] */
    cput(0x48); cput(0x89); cput(0xd7);                          /* mov rdi,rdx */
    cput(0x48); cput(0xc1); cput(0xe7); cput(0x03);              /* shl rdi,3 */
    emit_branch(0, 0, N_ALLOC, sizeof N_ALLOC - 1);
    x_test_rr(R9, R9);
    u32 l4 = (u32)code.len + 1; cput(0x74); cput(0);             /* jz np */
    x_mov_rr(RSI, R9); x_mov_rr(RDI, RAX);
    cput(0xf3); cput(0x48); cput(0xa5);                          /* rep movsq */
    patch_j8_at(l4, code.len);                                   /* np: */
    cput(0x48); cput(0x89); cput(0x43); cput(0x10);              /* mov [rbx+16],rax */
    cput(0x48); cput(0x89); cput(0x53); cput(0x08);              /* mov [rbx+8],rdx */
    cput(0x48); cput(0x8b); cput(0x0b);                          /* mov rcx,[rbx] */
    patch_j8_at(l1, code.len);                                   /* fit: */
    cput(0x48); cput(0x8b); cput(0x43); cput(0x10);              /* mov rax,[rbx+16] */
    cput(0x4c); cput(0x89); cput(0x04); cput(0xc8);              /* mov [rax+rcx*8],r8 */
    cput(0x48); cput(0xff); cput(0xc1);                          /* inc rcx */
    cput(0x48); cput(0x89); cput(0x0b);                          /* mov [rbx],rcx */
    x_mov_rr(RAX, RBX);
    x_pop(RBX);
    x_ret();
    def_label(N_LISTG, sizeof N_LISTG - 1);
    cput(0x48); cput(0x8b); cput(0x47); cput(0x10);              /* mov rax,[rdi+16] */
    cput(0x48); cput(0x8b); cput(0x04); cput(0xf0);              /* mov rax,[rax+rsi*8] */
    x_ret();
    def_label(N_LISTS, sizeof N_LISTS - 1);
    cput(0x48); cput(0x8b); cput(0x47); cput(0x10);              /* mov rax,[rdi+16] */
    cput(0x48); cput(0x89); cput(0x14); cput(0xf0);              /* mov [rax+rsi*8],rdx */
    x_ret();
    def_label(N_LISTL, sizeof N_LISTL - 1);
    cput(0x48); cput(0x8b); cput(0x07);                          /* mov rax,[rdi] */
    x_ret();

    /* mem: set / copy / byte_at, and the allocator friends */
    def_label(N_MSET, sizeof N_MSET - 1);
    x_test_rr(RDX, RDX);
    u32 m1 = (u32)code.len + 1; cput(0x74); cput(0);             /* jz done */
    u32 m2 = (u32)code.len;
    cput(0x40); cput(0x88); cput(0x37);                          /* mov [rdi],sil */
    cput(0x48); cput(0xff); cput(0xc7);                          /* inc rdi */
    cput(0x48); cput(0xff); cput(0xca);                          /* dec rdx */
    u32 m3 = (u32)code.len + 1; cput(0x75); cput(0);
    patch_j8_at(m3, m2);                                         /* jnz loop */
    patch_j8_at(m1, code.len);                                   /* done: */
    x_ret();
    def_label(N_MCOPY, sizeof N_MCOPY - 1);
    cput(0xf3); cput(0xa4);                                      /* rep movsb */
    x_ret();
    def_label(N_BAT, sizeof N_BAT - 1);
    cput(0x0f); cput(0xb6); cput(0x04); cput(0x37);              /* movzx eax,[rdi+rsi] */
    x_ret();
    def_label(N_FREE, sizeof N_FREE - 1);
    x_ret();                                                     /* the break never shrinks */
    def_label(N_HALLOC, sizeof N_HALLOC - 1);
    emit_branch(1, 0, N_ALLOC, sizeof N_ALLOC - 1);                              /* jmp _sov_alloc */

    /* atomics and raw words, the kernel modules' vocabulary */
    def_label(N_AADD, sizeof N_AADD - 1);
    cput(0xf0); cput(0x48); cput(0x0f); cput(0xc1); cput(0x37);  /* lock xadd [rdi],rsi */
    x_mov_rr(RAX, RSI);
    x_ret();
    def_label(N_ASTOR, sizeof N_ASTOR - 1);
    cput(0x48); cput(0x89); cput(0x37);                          /* mov [rdi],rsi */
    x_ret();
    def_label(N_ALOAD, sizeof N_ALOAD - 1);
    cput(0x48); cput(0x8b); cput(0x07);                          /* mov rax,[rdi] */
    x_ret();
    def_label(N_PO64, sizeof N_PO64 - 1);
    cput(0x48); cput(0x89); cput(0x14); cput(0x37);              /* mov [rdi+rsi],rdx */
    x_ret();
    def_label(N_PR64, sizeof N_PR64 - 1);
    cput(0x48); cput(0x8b); cput(0x04); cput(0x37);              /* mov rax,[rdi+rsi] */
    x_ret();

    /* raw access at the other widths: little-endian, native */
    def_label(N_PR8, sizeof N_PR8 - 1);
    cput(0x0f); cput(0xb6); cput(0x04); cput(0x37);              /* movzx eax,byte */
    x_ret();
    def_label(N_PR16, sizeof N_PR16 - 1);
    cput(0x0f); cput(0xb7); cput(0x04); cput(0x37);              /* movzx eax,word */
    x_ret();
    def_label(N_PR32, sizeof N_PR32 - 1);
    cput(0x8b); cput(0x04); cput(0x37);                          /* mov eax,dword */
    x_ret();
    def_label(N_PO8, sizeof N_PO8 - 1);
    cput(0x88); cput(0x14); cput(0x37);                          /* mov [rdi+rsi],dl */
    x_ret();
    def_label(N_PO16, sizeof N_PO16 - 1);
    cput(0x66); cput(0x89); cput(0x14); cput(0x37);              /* mov [rdi+rsi],dx */
    x_ret();
    def_label(N_PO32, sizeof N_PO32 - 1);
    cput(0x89); cput(0x14); cput(0x37);                          /* mov [rdi+rsi],edx */
    x_ret();

    /* _sov_wipe: rdi = a text; its bytes read as zero until the terminator */
    def_label(N_WIPE, sizeof N_WIPE - 1);
    x_test_rr(RDI, RDI);
    u32 wp1 = (u32)code.len + 1; cput(0x74); cput(0);            /* jz out */
    u32 wp2 = (u32)code.len;                                      /* wp: */
    cput(0xc6); cput(0x07); cput(0x00);                           /* mov byte [rdi],0 */
    cput(0x48); cput(0xff); cput(0xc7);                           /* inc rdi */
    cput(0x80); cput(0x3f); cput(0x00);                           /* cmp byte [rdi],0 */
    u32 wp3 = (u32)code.len + 1; cput(0x75); cput(0);             /* jne wp */
    patch_j8_at(wp3, wp2);
    patch_j8_at(wp1, code.len);                                   /* out: */
    x_ret();

    def_label(N_PI64, sizeof N_PI64 - 1);
    cput(0x48); cput(0x8b); cput(0x04); cput(0x37);              /* mov rax,[rdi+rsi] */
    x_ret();
    def_label(N_POI64, sizeof N_POI64 - 1);
    cput(0x48); cput(0x89); cput(0x14); cput(0x37);              /* mov [rdi+rsi],rdx */
    x_ret();

    /* bitwise helpers: two operands in, one answer out */
    def_label(N_BAND, sizeof N_BAND - 1);
    cput(0x48); cput(0x89); cput(0xf8);                          /* mov rax,rdi */
    cput(0x48); cput(0x21); cput(0xf0);                          /* and rax,rsi */
    x_ret();
    def_label(N_BOR, sizeof N_BOR - 1);
    cput(0x48); cput(0x89); cput(0xf8);
    cput(0x48); cput(0x09); cput(0xf0);                          /* or rax,rsi */
    x_ret();
    def_label(N_BXOR, sizeof N_BXOR - 1);
    cput(0x48); cput(0x89); cput(0xf8);
    cput(0x48); cput(0x31); cput(0xf0);                          /* xor rax,rsi */
    x_ret();
    def_label(N_BSHL, sizeof N_BSHL - 1);
    cput(0x48); cput(0x89); cput(0xf8);                          /* mov rax,rdi */
    cput(0x48); cput(0x89); cput(0xf1);                          /* mov rcx,rsi */
    cput(0x48); cput(0xd3); cput(0xe0);                          /* shl rax,cl */
    x_ret();
    def_label(N_BSHR, sizeof N_BSHR - 1);
    cput(0x48); cput(0x89); cput(0xf8);
    cput(0x48); cput(0x89); cput(0xf1);
    cput(0x48); cput(0xd3); cput(0xe8);                          /* shr rax,cl (logical) */
    x_ret();
    def_label(N_BSAR, sizeof N_BSAR - 1);
    cput(0x48); cput(0x89); cput(0xf8);
    cput(0x48); cput(0x89); cput(0xf1);
    cput(0x48); cput(0xd3); cput(0xf8);                          /* sar rax,cl (arithmetic) */
    x_ret();

    /* sys_* passthroughs */
    def_label(N_SREAD, sizeof N_SREAD - 1);
    x_xor_eax(); x_syscall(); x_ret();
    def_label(N_SCLOSE, sizeof N_SCLOSE - 1);
    x_mov_imm32(RAX, 3); x_syscall(); x_ret();
    def_label(N_SGETPID, sizeof N_SGETPID - 1);
    x_mov_imm32(RAX, 39); x_syscall(); x_ret();
}

/* -------------------------------------------------------- statements
 * The whole file in one buffer, split once, at read time.  One quote-aware
 * pass per line cuts the comment, splits the `;;` pieces and trims them;
 * what lands in the array is every statement in order, with its line's
 * indentation and its line number.  The feed below is then an index into
 * this array -- no scanning at parse time at all. */


/* a backslash inside a quoted stretch: the pair counts as one unit, so a
 * \" never closes the string */
static int esc_at(const u8 *p, u64 k, u64 e)
{
    return k < e && p[k] == '\\' && k + 1 < e;
}

/* where does the literal opening at p[at] end?  Greedy, the way the old
 * compiler's sugar layer reads them: the text spans to the LAST quote of
 * its run before the next depth-0 delimiter (a comma, the enclosing call's
 * closing paren, or the end), and every quote in between is content.  A
 * run that is still open at the delimiter is unterminated. */
static i64 lit_end(const u8 *p, u64 n, u64 at)
{
    u8 q = p[at];
    u64 i = at + 1;
    u64 depth = 0;
    int in = 1;
    i64 lastq = -1;
    while (i < n) {
        u8 c = p[i];
        if (in) {
            if (c == '\\' && i + 1 < n) { i += 2; continue; }
            if (c == q) { in = 0; lastq = (i64)i; }
            i++;
            continue;
        }
        if (c == q) { in = 1; lastq = (i64)i; i++; continue; }
        if (c == '(') { depth++; i++; continue; }
        if (c == ')') {
            if (depth == 0) return in ? -1 : lastq;
            depth--; i++; continue;
        }
        if (c == ',' && depth == 0) return in ? -1 : lastq;
        i++;
    }
    return in ? -1 : lastq;
}

/* interpret the escapes of a literal's raw text into fresh bytes:
 * \\n newline, \\t tab, \\r return, \\\\ a backslash, \\" a quote */
static u32 emit_unescaped(Buf *b, const char *p, u32 n)
{
    u32 out = 0;
    for (u32 i = 0; i < n; i++) {
        u8 c = (u8)p[i];
        if (c == '\\' && i + 1 < n) {
            u8 d = (u8)p[i+1];
            if (d == 'n') { bput(b, '\n'); i++; out++; continue; }
            if (d == 't') { bput(b, '\t'); i++; out++; continue; }
            if (d == 'r') { bput(b, '\r'); i++; out++; continue; }
            if (d == '\\' || d == '"') { bput(b, d); i++; out++; continue; }
        }
        bput(b, c);
        out++;
    }
    return out;
}

typedef struct { const char *p; u32 len, indent; u32 line; } Stmt;

/* a source file's statements.  Modules stack as frames; pull drains the top
 * frame, then the one under it, in order. */
typedef struct { Stmt *st; u32 n, cur, cap; } Frame;
static Frame fr[64];
static u32 nfr;

static void push_stmt(const u8 *base, u64 b, u64 e, u32 ind, u32 line, Frame *f, u64 *cap)
{
    while (b < e && (base[b] == ' ' || base[b] == '\t')) b++;
    while (e > b && (base[e-1] == ' ' || base[e-1] == '\t')) e--;
    if (b >= e) return;                                /* nothing there */
    if (f->n == *cap) { *cap *= 2; f->st = xrealloc(f->st, *cap * sizeof(Stmt)); f->cap = *cap; }
    f->st[f->n].p = (const char *)base + b;
    f->st[f->n].len = (u32)(e - b);
    f->st[f->n].indent = ind;
    f->st[f->n].line = line;
    f->n++;
}

static void build_statements(const Buf *src, Frame *f)
{
    u64 cap = src->len / 16 + 64;
    f->st = xrealloc(NULL, cap * sizeof(Stmt));
    f->n = 0;
    f->cur = 0;
    f->cap = (u32)cap;
    u64 i = 0;
    u32 ln = 0;
    while (i < src->len) {
        u64 s = i;
        while (i < src->len && src->p[i] != '\n') i++;
        u64 e = i;
        if (i < src->len) i++;                       /* the newline itself */

        u32 ind = 0;
        u64 b = s;
        while (b < e && (src->p[b] == ' ' || src->p[b] == '\t')) { ind++; b++; }

        u64 end = e;
        int q = 0;
        u64 k = b;
        while (k < e) {                              /* comment, then pieces */
            u8 c = src->p[k];
            if (q) {
                if (esc_at(src->p, k, e)) { k += 2; continue; }
                if (c == (u8)q) q = 0;
            }
            else if (c == '\'' || c == '"') q = c;
            else if (c == '#') { end = k; break; }    /* the comment cut */
            else if (c == ';' && k + 1 < e && src->p[k+1] == ';') {
                push_stmt(src->p, b, k, ind, ln, f, &cap);   /* a piece ends */
                k += 2;
                b = k;
                continue;
            }
            k++;
        }
        push_stmt(src->p, b, end, ind, ln, f, &cap);  /* the last piece */
        ln++;
    }
}

/* ---------------------------------------------------- the statement feed
 * A stack of frames; pull drains the top one, then the one under it. */

static int feed_peek(Stmt *out)
{
    while (nfr) {
        Frame *f = &fr[nfr - 1];
        if (f->cur < f->n) { *out = f->st[f->cur]; return 1; }
        nfr--;                                  /* this frame is spent */
    }
    return 0;
}

static int feed_pull(Stmt *out)
{
    if (!feed_peek(out)) return 0;
    fr[nfr - 1].cur++;
    return 1;
}

static void feed_unpull(const Stmt *st)
{
    (void)st;
    fr[nfr - 1].cur--;
}

static void feed_next(Stmt *out)
{
    if (!feed_pull(out)) die("statement stream ended unexpectedly");
}

/* the lexer's cursor: p..p+n the text, i the position */
typedef struct { const char *p; u32 n, i; } Lx;
static void lxws(Lx *l);
static int lxc(Lx *l);
static int lx_int(Lx *l, u64 *v);

/* --------------------------------------------------------- use modules
 * `use name` splices library/name.sov in as a frame, once per name no
 * matter how many files ask for it.  The buffers persist because every
 * statement points into them. */

static void read_file(const char *path, Buf *b);

static Buf modbuf[256];  static u32 nmodbuf;
static const char *modname[256]; static u32 modlen[256]; static u32 nmod;

static void use_module(const char *nm, u32 nlen)
{
    for (u32 i = 0; i < nmod; i++)
        if (modlen[i] == nlen && memcmp(modname[i], nm, nlen) == 0) return;
    if (nmod >= 256 || nmodbuf >= 256 || nfr >= 63) die("too many modules");
    char path[512];
    static const char *pats[] = {
        "library/%.*s.sov", "../library/%.*s.sov",
        "sovren/library/%.*s.sov", "../sovren/library/%.*s.sov", "%.*s.sov"
    };
    Buf *b = &modbuf[nmodbuf++];
    b->p = 0; b->len = 0; b->cap = 0;
    int ok = 0;
    for (u32 i = 0; i < 5 && !ok; i++) {
        snprintf(path, sizeof path, pats[i], (int)nlen, nm);
        int fd = open(path, O_RDONLY);
        if (fd >= 0) { close(fd); read_file(path, b); ok = 1; }
    }
    if (!ok) die2("cannot read library", nm, nlen);
    modname[nmod] = nm; modlen[nmod] = nlen; nmod++;
    build_statements(b, &fr[nfr]);
    nfr++;
}


/* ------------------------------------------------- the include engine
 * `include file`, `include file from n`, `include file from n (a b c)` --
 * a LINE RANGE of the file is cut, %1..%N in each line replaced by the
 * parenthesized tokens (double-quoted spans are left alone), the include
 * line's own indentation prepended, and the result inserted into the
 * current frame right where the include sits.  No dedup: the same file
 * can be spliced twice with different ranges or names. */

static Buf *new_buf(void)
{
    if (nmodbuf >= 256) die("too many includes");
    Buf *b = &modbuf[nmodbuf++];
    b->p = 0; b->len = 0; b->cap = 0;
    return b;
}

static int tmpl_line(Buf *out, const char *ln, u32 n,
                     const char * const *pars, const u32 *parl, u32 npars)
{
    int dq = 0;
    u32 i = 0;
    while (i < n) {
        u8 c = (u8)ln[i];
        if (dq) { bput(out, c); if (c == '"') dq = 0; i++; continue; }
        if (c == '"') { dq = 1; bput(out, c); i++; continue; }
        if (c == '%' && i + 1 < n && ln[i+1] >= '0' && ln[i+1] <= '9') {
            u32 j = i + 1;
            u32 idx = 0;
            while (j < n && ln[j] >= '0' && ln[j] <= '9' && idx < 99)
                idx = idx * 10 + (u32)(ln[j++] - '0');
            if (idx >= 1 && idx <= npars) {
                bputn(out, pars[idx-1], parl[idx-1]);
                i = j;
                continue;
            }
        }
        bput(out, c);
        i++;
    }
    return 1;
}

static void splice_include(Lx *ul, const Stmt *st)
{
    lxws(ul);
    u32 fs = ul->i;
    while (ul->i < ul->n) {
        u8 c = (u8)ul->p[ul->i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
            || c == '_' || c == '.' || c == '/')
            ul->i++;
        else break;
    }
    if (ul->i == fs) die_at("include file expected", st->line + 1);
    const char *fn = ul->p + fs;
    u32 fl = ul->i - fs;

    u64 from = 0, nlin = 0;
    const char *pars[16]; u32 parl[16]; u32 npars = 0;
    lxws(ul);
    u64 v;
    if (lx_int(ul, &v)) {
        from = v;
        lxws(ul);
        if (lx_int(ul, &v)) { nlin = v; lxws(ul); }
    }
    if (lxc(ul) == '(') {
        ul->i++;
        for (;;) {
            lxws(ul);
            u32 ps = ul->i;
            while (ul->i < ul->n) {
                u8 c = (u8)ul->p[ul->i];
                if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
                    || c == '_' || c == '.' || c == '-' || c == '+')
                    ul->i++;
                else break;
            }
            if (ul->i > ps) {
                if (npars < 16) { pars[npars] = ul->p + ps; parl[npars] = ul->i - ps; npars++; }
                if (lxc(ul) == ' ') { ul->i++; continue; }   /* one separator */
            }
            break;
        }
        lxws(ul);
        if (lxc(ul) == ')') { ul->i++; lxws(ul); }
        else die_at("missing ) after include names", st->line + 1);
    }
    if (ul->i < ul->n) die_at("junk after include", st->line + 1);

    /* find and read the file */
    char path[512];
    Buf *src = new_buf();
    int ok = 0;
    static const char *pats[] = { "library/%.*s", "../sovren/library/%.*s", "%.*s" };
    for (u32 i = 0; i < 3 && !ok; i++) {
        snprintf(path, sizeof path, pats[i], (int)fl, fn);
        int fd = open(path, O_RDONLY);
        if (fd >= 0) { close(fd); read_file(path, src); ok = 1; }
    }
    if (!ok) die2("cannot read include", fn, fl);
    if (getenv("SC_DEBUG_INC")) fprintf(stderr, "[inc file=%.*s from=%llu nlin=%llu npars=%u]\n", (int)fl, fn, (unsigned long long)from, (unsigned long long)nlin, npars);

    /* cut the range, substitute, and keep the text alive */
    Buf *out = new_buf();
    u64 ln = 0;
    u64 i = 0;
    while (i < src->len && ln < (from ? from - 1 : 0)) {
        if (src->p[i] == '\n') ln++;
        i++;
    }
    u64 taken = 0;
    while (i < src->len && (!nlin || taken < nlin)) {
        u64 s = i;
        while (i < src->len && src->p[i] != '\n') i++;
        u64 e = i;
        if (i < src->len) i++;
        for (u32 k = 0; k < st->indent; k++) bput(out, ' ');   /* the include's base */
        tmpl_line(out, (const char *)src->p + s, (u32)(e - s), pars, parl, npars);
        bput(out, '\n');
        taken++;
    }

    if (getenv("SC_DEBUG_INC")) fprintf(stderr, "[splice text:\n%.*s---]\n", (int)out->len, out->p);
    /* statements from the spliced text, inserted after this one */
    Frame tmp;
    build_statements(out, &tmp);
    if (tmp.n) {
        Frame *f = &fr[nfr - 1];
        u32 at = f->cur;                    /* just past the include itself */
        while (f->n + tmp.n > f->cap) {
            f->cap = f->cap ? f->cap * 2 : 1024;
            f->st = xrealloc(f->st, (u64)f->cap * sizeof(Stmt));
        }
        memmove(f->st + at + tmp.n, f->st + at, (f->n - at) * sizeof(Stmt));
        memcpy(f->st + at, tmp.st, tmp.n * sizeof(Stmt));
        f->n += tmp.n;
    }
}


/* ------------------------------------------------------------- lexer */

static int lxc(Lx *l)
{
    return l->i < l->n ? (u8)l->p[l->i] : -1;
}

static void lxws(Lx *l)
{
    while (l->i < l->n && (l->p[l->i] == ' ' || l->p[l->i] == '\t')) l->i++;
}

static int is_idc(int c)
{
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_';
}

static int lx_word(Lx *l, const char **w, u32 *wl)
{
    lxws(l);
    u32 s = l->i;
    if (s >= l->n) return 0;
    int c = (u8)l->p[s];
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_')) return 0;
    while (l->i < l->n && is_idc((u8)l->p[l->i])) l->i++;
    *w = l->p + s; *wl = l->i - s;
    return 1;
}

static int lx_int(Lx *l, u64 *v)
{
    lxws(l);
    u32 s = l->i;
    if (s >= l->n || l->p[s] < '0' || l->p[s] > '9') return 0;
    u64 x = 0;
    while (l->i < l->n && l->p[l->i] >= '0' && l->p[l->i] <= '9') {
        x = x * 10 + (u64)(l->p[l->i] - '0');
        l->i++;
    }
    *v = x;
    return 1;
}

static int word_isN(const char *w, u32 wl, const char *lit, u32 n)
{
    return wl == n && (n == 0 || memcmp(w, lit, n) == 0);
}
#define word_is(w, wl, lit) word_isN((w), (wl), (lit), sizeof(lit) - 1)

/* ------------------------------------------------------- expressions
 * or < and < compare < add < mul < unary.  Values move as descriptors: a
 * literal or a local is carried as data (nothing emitted) until an operation
 * actually needs it in a register, so `z: x + y` is one load, one add, one
 * store.  The stack machine's push/pop pair per operator is gone; the stack
 * is touched only when a materialized left side meets a right side whose
 * evaluation could clobber it (a call or a nested expression). */

enum { O_ADD, O_SUB, O_MUL, O_DIV, O_MOD, O_EQ, O_NE, O_LT, O_GT, O_LE, O_GE, O_AND, O_OR };

enum { V_RAX, V_IMM, V_LOCAL };              /* in rax / known / in a slot */
typedef struct { u8 kind, txt, unk; u64 imm; i32 loff; } Val;

/* constant values, indexed by a K_CONST slot's 24-bit field */
static u64 cval[8192];
static u32 ncval;

static Val pExpr(Lx *l);
static Val pUn(Lx *l);
static Val prec(Lx *l, int minp);

static int fits_i32(u64 v) { return (i64)v >= -2147483648LL && (i64)v <= 2147483647LL; }

/* zero-extend for small positives, sign-extend for small negatives, full
 * form otherwise */
static void x_mov_reg_imm(int r, u64 v)
{
    if (v <= 0xffffffffULL) x_mov_imm32(r, (u32)v);
    else if (fits_i32(v)) {
        emrex(1, 0, 0, r >= 8); cput(0xc7);
        cput((u8)(0xc0 | (r & 7))); cput32((u32)v);
    }
    else x_mov_imm64(r, v);
}

/* op rax, [rbp+d] : the r64, r/m64 forms -- add 03 sub 2b cmp 3b and 23 or 0b,
 * reg field = the destination rax, r/m = the local */
static void x_op_rax_local(u8 op, i32 d)
{
    emrex(1, 0, 0, 0); cput(op);
    cput(0x85); cput32((u32)d);
}
static void x_imul_rax_local(i32 d) { cput(0x0f); cput(0xaf); cput(0x85); cput32((u32)d); }
static void x_idiv_local(i32 d)     { cput(0xf7); cput(0xbd); cput32((u32)d); }
static void x_setcl(u8 cc)          { cput(0x0f); cput(cc); cput(0xc1); }
static void x_store_local_imm32(i32 d, i32 v)
{
    cput(0x48); cput(0xc7); cput(0x85);
    cput32((u32)d); cput32((u32)v);
}

static void force_rax(Val v)
{
    if (v.kind == V_IMM) x_mov_reg_imm(RAX, v.imm);
    else if (v.kind == V_LOCAL) x_mov_r_local(RAX, v.loff);
}

/* meet the two sides; whatever the shapes, the answer lands in rax */
static Val combine(int op, Val L, Val R)
{
    static const u8 setcc[6] = {0x94, 0x95, 0x9c, 0x9f, 0x9e, 0x9d}; /* eq ne lt gt le ge */
    int ccix = op >= O_EQ ? (int)(op - O_EQ) : 0;

    if (op == O_AND) {
        if (L.kind != V_RAX && R.kind == V_RAX) x_mov_rr(RBX, RAX);
        force_rax(L);
        x_test_rr(RAX, RAX); x_setal(0x95); x_movzx_eax_al();
        if (R.kind == V_IMM)      { x_mov_reg_imm(RCX, R.imm); x_test_rr(RCX, RCX); }
        else if (R.kind == V_LOCAL) {
            cput(0x48); cput(0x83); cput(0xbd);   /* cmp qword [rbp+d],0 */
            cput32((u32)R.loff); cput(0x00);
        }
        else                      x_test_rr(RBX, RBX);
        x_setcl(0x95); x_and_rr(RAX, RCX);
        L.kind = V_RAX; return L;
    }
    if (op == O_OR) {
        if (L.kind != V_RAX && R.kind == V_RAX) x_mov_rr(RBX, RAX);
        force_rax(L);
        if (R.kind == V_IMM) {
            if (fits_i32(R.imm)) { cput(0x48); cput(0x0d); cput32((u32)R.imm); }
            else { x_mov_reg_imm(RCX, R.imm); x_or_rr(RAX, RCX); }
        }
        else if (R.kind == V_LOCAL) x_op_rax_local(0x0b, R.loff);
        else x_or_rr(RAX, RBX);
        x_setal(0x95); x_movzx_eax_al();
        L.kind = V_RAX; return L;
    }

    if (op == O_DIV || op == O_MOD) {                 /* dividend rax, cqo, divisor anywhere */
        if (L.kind != V_RAX && R.kind == V_RAX) {     /* right sits in rax: park it */
            x_mov_rr(RCX, RAX);
            force_rax(L);
            x_cqo(); x_idiv(RCX);
        } else {
            force_rax(L);
            if (R.kind == V_RAX) { x_cqo(); x_idiv(RBX); }
            else if (R.kind == V_LOCAL) { x_cqo(); x_idiv_local(R.loff); }
            else { x_mov_reg_imm(RCX, R.imm); x_cqo(); x_idiv(RCX); }
        }
        if (op == O_MOD) x_mov_rr(RAX, RDX);
        L.kind = V_RAX; return L;
    }

    /* commutative join with the left still unmaterialized: the right side
     * in rax meets the literal (imm form) or the local (mem form) where it
     * sits */
    if (L.kind != V_RAX && R.kind == V_RAX) {
        if (op == O_ADD) {
            if (L.kind == V_IMM) {
                if (fits_i32(L.imm)) { cput(0x48); cput(0x05); cput32((u32)L.imm); }
                else { x_mov_reg_imm(RCX, L.imm); x_add_rr(RAX, RCX); }
            }
            else x_op_rax_local(0x03, L.loff);
        } else if (op == O_MUL) {
            if (L.kind == V_IMM) {
                if (fits_i32(L.imm)) { cput(0x48); cput(0x69); cput(0xc0); cput32((u32)L.imm); }
                else { x_mov_reg_imm(RCX, L.imm); x_imul_rr(RAX, RCX); }
            }
            else x_imul_rax_local(L.loff);
        } else {                                          /* a comparison: the
                                                          * rax side is the RIGHT
                                                          * one, so the condition
                                                          * code mirrors */
            static const u8 mir[6] = {0x94, 0x95, 0x9f, 0x9c, 0x9d, 0x9e};
            if (L.kind == V_IMM) {
                if (fits_i32(L.imm)) { cput(0x48); cput(0x3d); cput32((u32)L.imm); }
                else { x_mov_reg_imm(RCX, L.imm); x_cmp_rr(RAX, RCX); }
            }
            else x_op_rax_local(0x3b, L.loff);
            x_setal(mir[ccix]); x_movzx_eax_al();
        }
        L.kind = V_RAX; return L;
    }

    /* a non-commutative op with the right side already in rax: park it in
     * rcx (nothing between here and the op can call), load the left */
    if (L.kind != V_RAX && R.kind == V_RAX) {
        x_mov_rr(RCX, RAX);
        force_rax(L);
        if (op == O_SUB) x_sub_rr(RAX, RCX);
        else { x_cmp_rr(RAX, RCX); x_setal(setcc[ccix]); x_movzx_eax_al(); }
        L.kind = V_RAX; return L;
    }

    force_rax(L); L.kind = V_RAX;                        /* left in rax now */
    if (R.kind == V_RAX) {                               /* right parked in rbx */
        switch (op) {
        case O_ADD: x_add_rr(RAX, RBX); break;
        case O_SUB: x_sub_rr(RAX, RBX); break;
        case O_MUL: x_imul_rr(RAX, RBX); break;
        default:    x_cmp_rr(RAX, RBX); x_setal(setcc[ccix]); x_movzx_eax_al(); break;
        }
    } else if (R.kind == V_LOCAL) {
        switch (op) {
        case O_ADD: x_op_rax_local(0x03, R.loff); break;
        case O_SUB: x_op_rax_local(0x2b, R.loff); break;
        case O_MUL: x_imul_rax_local(R.loff); break;
        default:    x_op_rax_local(0x3b, R.loff); x_setal(setcc[ccix]); x_movzx_eax_al(); break;
        }
    } else {                                             /* immediate */
        switch (op) {
        case O_ADD:
            if (fits_i32(R.imm)) { cput(0x48); cput(0x05); cput32((u32)R.imm); }
            else { x_mov_reg_imm(RCX, R.imm); x_add_rr(RAX, RCX); }
            break;
        case O_SUB:
            if (fits_i32(R.imm)) { cput(0x48); cput(0x2d); cput32((u32)R.imm); }
            else { x_mov_reg_imm(RCX, R.imm); x_sub_rr(RAX, RCX); }
            break;
        case O_MUL:
            if (fits_i32(R.imm)) { cput(0x48); cput(0x69); cput(0xc0); cput32((u32)R.imm); }
            else { x_mov_reg_imm(RCX, R.imm); x_imul_rr(RAX, RCX); }
            break;
        default:
            if (fits_i32(R.imm)) { cput(0x48); cput(0x3d); cput32((u32)R.imm); }
            else { x_mov_reg_imm(RCX, R.imm); x_cmp_rr(RAX, RCX); }
            x_setal(setcc[ccix]); x_movzx_eax_al(); break;
        }
    }
    return L;
}

static void emit_call_args(Lx *l, const char *nm, u32 nlen);   /* after '(' */

static Val pPrim(Lx *l)
{
    lxws(l);
    u64 v;
    if (lx_int(l, &v)) { Val r = {V_IMM, 0, 0, v, 0}; return r; }
    int c = lxc(l);
    if (c == '\'' || c == '"') {                  /* a literal as a value */
        i64 e = lit_end((const u8 *)l->p, l->n, l->i);
        if (e < 0) die_at("unterminated text", err_line);
        u32 s = l->i + 1;
        u32 n = (u32)e - s;
        l->i = (u32)e + 1;
        u64 off = data.len;
        emit_unescaped(&data, l->p + s, n);
        bput(&data, 0);                              /* texts are NUL-run */
        Val r = {V_IMM, 1, 0, DATA_VADDR + off, 0};
        return r;
    }
    if (c == '(') {
        l->i++;
        Val r = pExpr(l);
        lxws(l);
        if (lxc(l) != ')') die_at("missing )", err_line);
        l->i++;
        return r;
    }
    const char *w; u32 wl;
    if (lx_word(l, &w, &wl)) {
        lxws(l);
        if (lxc(l) == '(') {                       /* a call: type follows the name */
            l->i++;
            emit_call_args(l, w, wl);
            Val r = {V_RAX, 0, 0, 0, 0};
            const Nat *nt = nat_find(w, wl);         /* the natives carry types */
            if (nt) r.txt = nt->txt;
            else {
                Slot *t = sym_find(&gt, w, wl, 0);
                if (t && (slot_kind(t) & 0x7f) == K_FUNC) r.txt = slot_txt(t);
                else { r.unk = 1; unk_nm = w; unk_len = wl; }
            }
            return r;
        }
        if (word_is(w, wl, "times")) die_at("times without a count", err_line);
        if (word_is(w, wl, "blank")) { Val r = {V_IMM, 1, 0, 0, 0}; return r; }
        if (word_is(w, wl, "heap_ptr")) {                    /* the break cursor */
            x_mov_imm64(RAX, DATA_VADDR + 24);
            cput(0x48); cput(0x8b); cput(0x00);               /* mov rax,[rax] */
            Val r = {V_RAX, 0, 0, 0, 0};
            return r;
        }
        if (word_is(w, wl, "heap_end")) {                    /* the region's top */
            Val r = {V_IMM, 0, 0, 0x800000000ULL, 0};
            return r;
        }
        if (word_is(w, wl, "g_argv")) {                       /* the argv array */
            x_mov_imm64(RAX, DATA_VADDR + 8);
            cput(0x48); cput(0x8b); cput(0x00);               /* mov rax,[rax] */
            Val r = {V_RAX, 0, 0, 0, 0};
            return r;
        }
        if (word_is(w, wl, "as")) {                 /* as text: int to decimal */
            const char *tw; u32 twl;
            if (!lx_word(l, &tw, &twl) || !word_is(tw, twl, "text"))
                die_at("as text expected", err_line);
            Val v2 = pUn(l);
            force_rax(v2);
            x_mov_rr(RDI, RAX);
            emit_branch(0, 0, N_ITOS, sizeof N_ITOS - 1);
            Val r = {V_RAX, 1, 0, 0, 0};
            return r;
        }
        Slot *t = sym_find(&lt, w, wl, cur_scope);
        if (t) {
            if ((slot_kind(t) & 0x7f) != K_VAR) die2("not a variable", w, wl);
            Val r = {V_LOCAL, slot_txt(t), 0, 0, -(i32)(8 * slot_val(t))};
            return r;
        }
        t = sym_find(&gt, w, wl, 0);
        if (t) {
            if ((slot_kind(t) & 0x7f) == K_GVAR) {        /* a global slot */
                x_mov_imm64(RCX, DATA_VADDR + slot_val(t));
                cput(0x48); cput(0x8b); cput(0x01);       /* mov rax,[rcx] */
                Val r = {V_RAX, slot_txt(t), 0, 0, 0};
                return r;
            }
            if ((slot_kind(t) & 0x7f) != K_CONST) die2("not a variable", w, wl);
            Val r = {V_IMM, slot_txt(t), 0, cval[slot_val(t)], 0};
            return r;
        }
        die2("unknown name", w, wl);
    }
    die_at("expression expected", err_line);
    Val z = {V_RAX, 0, 0, 0, 0}; return z;
}

static Val pUn(Lx *l)
{
    lxws(l);
    if (lxc(l) == '-') {
        l->i++;
        Val v = pUn(l);
        if (v.kind == V_IMM) { v.imm = (u64)(0ULL - v.imm); return v; }
        force_rax(v); x_neg(RAX);
        v.kind = V_RAX; return v;
    }
    u32 save = l->i;
    const char *w; u32 wl;
    if (lx_word(l, &w, &wl) && word_is(w, wl, "not")) {
        /* logical not, binding at the comparison level: `not s is blank` */
        Val v = prec(l, 3);
        force_rax(v);
        x_test_rr(RAX, RAX);
        cput(0x0f); cput(0x94); cput(0xc0);          /* sete al */
        x_movzx_eax_al();
        Val r = {V_RAX, 0, 0, 0, 0};
        return r;
    }
    l->i = save;
    return pPrim(l);
}

/* precedence climbing, one loop instead of five nested levels: the driver
 * pExpr/pAnd/pCmp/pAdd/pMul chain walked seven calls deep for every plain
 * operand, most of them to see nothing and return.  Here one loop reads the
 * operand, then one operator check decides: not mine (hand it back to the
 * caller by rewinding), or mine (parse the right side one level tighter and
 * join).  or=1 and=2 cmp=3 add=4 mul=5, left-associative, same grammar. */
static int cmp_op(Lx *l, int *op);

static int cmp_op(Lx *l, int *op)
{
    lxws(l);
    u32 s = l->i;
    const char *p = l->p;
    if (s + 1 < l->n && p[s] == '=' && p[s+1] == '=') { l->i = s + 2; *op = O_EQ; return 1; }
    if (s + 1 < l->n && p[s] == '!' && p[s+1] == '=') { l->i = s + 2; *op = O_NE; return 1; }
    if (s + 1 < l->n && p[s] == '<' && p[s+1] == '=') { l->i = s + 2; *op = O_LE; return 1; }
    if (s + 1 < l->n && p[s] == '>' && p[s+1] == '=') { l->i = s + 2; *op = O_GE; return 1; }
    if (s < l->n && p[s] == '=') { l->i = s + 1; *op = O_EQ; return 1; }
    if (s < l->n && p[s] == '<') { l->i = s + 1; *op = O_LT; return 1; }
    if (s < l->n && p[s] == '>') { l->i = s + 1; *op = O_GT; return 1; }
    return 0;
}

static Val prec(Lx *l, int minp)
{
    Val left = pUn(l);
    for (;;) {
        lxws(l);
        u32 save = l->i;
        int c = lxc(l);
        int op = 0, p = 0, right0 = 0;
        if (c == '+' || c == '-') { op = c == '+' ? O_ADD : O_SUB; p = 4; l->i++; }
        else if (c == '*' || c == '/' || c == '%') {
            op = c == '*' ? O_MUL : c == '/' ? O_DIV : O_MOD; p = 5; l->i++;
        }
        else if (c >= 0) {
            if (cmp_op(l, &op)) p = 3;
            else {
                const char *w; u32 wl;
                if (!lx_word(l, &w, &wl)) { l->i = save; return left; }
                if (word_is(w, wl, "and")) { op = O_AND; p = 2; }
                else if (word_is(w, wl, "or")) { op = O_OR; p = 1; }
                else if (word_is(w, wl, "is")) {
                    p = 3;
                    op = O_EQ;                          /* plain `is expr` */
                    const char *w2; u32 wl2;
                    u32 sv = l->i;
                    if (lx_word(l, &w2, &wl2)) {
                        if (word_is(w2, wl2, "blank")) { right0 = 1; }
                        else if (word_is(w2, wl2, "not")) {
                            op = O_NE;
                            const char *w3; u32 wl3;
                            u32 sv2 = l->i;
                            if (lx_word(l, &w3, &wl3) && word_is(w3, wl3, "blank")) right0 = 1;
                            else l->i = sv2;
                        }
                        else l->i = sv;
                    } else l->i = sv;
                }
                else { l->i = save; return left; }
            }
        }
        else return left;                            /* end of the expression */
        if (p < minp) { l->i = save; return left; }  /* the caller's operator */
        Val right;
        if (right0) { right.kind = V_IMM; right.txt = 1; right.unk = 0; right.imm = 0; right.loff = 0; }
        else if (left.kind == V_RAX) {               /* park: the right may emit */
            x_push(RAX);
            right = prec(l, p + 1);
            if (right.kind == V_RAX) x_mov_rr(RBX, RAX);
            x_pop(RAX);
        } else {
            right = prec(l, p + 1);                  /* left is data: safe */
        }
        left = combine(op, left, right);
    }
}

static Val pExpr(Lx *l)
{
    return prec(l, 1);
}

/* arguments: each is parsed to a descriptor; a complex one parks its rax
 * on the stack at parse time, the plain ones go straight to their argument
 * registers at the end.  Six is the register count.
 *
 * More than six, or the syscall primitive: every argument is materialized
 * into a slot cut off the stack first (`sub rsp, 8n`), because a later
 * argument's evaluation may itself call and clobber.  Then the first six
 * go to their registers and the rest stay on the stack for the callee,
 * which reads them at [rbp+16] and up.  syscall(7) maps its arguments to
 * the kernel's register order itself and executes inline. */

/* how many arguments are waiting, without consuming anything.  Literals
 * are skipped whole (greedy), so a comma inside one is content. */
static u32 count_args(const Lx *l)
{
    u32 depth = 1, n = 1, i = l->i;
    while (i < l->n) {
        u8 c = (u8)l->p[i];
        if (c == '\'' || c == '"') {
            i64 e = lit_end((const u8 *)l->p, l->n, i);
            if (e < 0) return n;                  /* the parser will complain */
            i = (u32)e + 1;
            continue;
        }
        if (c == '(') depth++;
        else if (c == ')') { if (--depth == 0) return n; }
        else if (c == ',' && depth == 1) n++;
        i++;
    }
    return n;
}

static void x_mov_r_slot(int r, u32 k)     /* mov r, [rsp+8k] */
{
    emrex(1, r >= 8, 0, 0);
    cput(0x8b);
    cput((u8)(0x44 | ((r & 7) << 3)));     /* mod=01: a disp8 follows */
    cput(0x24);
    cput((u8)(8 * k));
}
static void x_mov_slot_r(u32 k)            /* mov [rsp+8k], rax */
{
    cput(0x48); cput(0x89); cput(0x44); cput(0x24); cput((u8)(8 * k));
}
static void x_add_rsp(u32 v)               /* add rsp, imm32 */
{
    cput(0x48); cput(0x81); cput(0xc4); cput32(v);
}

static void emit_call_args(Lx *l, const char *nm, u32 nlen)
{
    int is_sys = nlen == 7 && memcmp(nm, "syscall", 7) == 0;
    lxws(l);
    u32 na = count_args(l);
    if (na > 6 || is_sys) {                       /* the slot path */
        u32 n = 0;
        x_sub_rsp_imm32(8 * na);
        lxws(l);
        if (lxc(l) != ')') {
            for (;;) {
                Val v = pExpr(l);
                force_rax(v);
                x_mov_slot_r(n);
                n++;
                lxws(l);
                if (lxc(l) == ',') { l->i++; continue; }
                break;
            }
        }
        lxws(l);
        if (lxc(l) != ')') die2("missing ) in call", nm, nlen);
        l->i++;
        if (is_sys) {
            static const int kreg[7] = { RAX, RDI, RSI, RDX, R10, 8, 9 };
            for (int k = (int)n - 1; k >= 0; k--)
                if (k < 7) x_mov_r_slot(kreg[k], (u32)k);
            x_add_rsp(8 * na);
            x_syscall();                          /* the answer is in rax */
            return;
        }
        for (u32 k = 0; k < n && k < 6; k++)
            x_mov_r_slot(argreg[k], k);
        x_add_rsp(48);                            /* the rest stay for the callee */
        emit_branch(0, 0, nm, nlen);
        x_add_rsp(8 * (na - 6));                  /* the cut was 8*na: balance it */
        return;
    }
    Val vars[6];
    u8 parked[6];
    u32 n = 0;
    lxws(l);
    if (lxc(l) != ')') {
        for (;;) {
            vars[n] = pExpr(l);
            if (vars[n].kind == V_RAX) { x_push(RAX); parked[n] = 1; }
            else parked[n] = 0;
            n++;
            lxws(l);
            if (lxc(l) == ',') { l->i++; continue; }
            break;
        }
    }
    lxws(l);
    if (lxc(l) != ')') die2("missing ) in call", nm, nlen);
    l->i++;
    for (u32 k = 0; k < n; k++)
        if (!parked[k]) {
            if (vars[k].kind == V_IMM) x_mov_reg_imm(argreg[k], vars[k].imm);
            else x_mov_r_local(argreg[k], vars[k].loff);
        }
    for (u32 k = n; k > 0; k--)
        if (parked[k-1]) x_pop(argreg[k-1]);
    emit_branch(0, 0, nm, nlen);
}

/* ------------------------------------------------------- statements */

static void parse_statement(const Stmt *st);
static void parse_block(u32 parent_indent);


/* the write of a string literal: the bytes live in the data segment with a
 * newline appended, so one write does the whole print */
static void emit_str_write(const char *s, u32 n)
{
    u64 off = data.len;
    u32 m = emit_unescaped(&data, s, n);        /* m: the bytes it became */
    bput(&data, '\n');
    x_mov_imm32(RAX, 1);                        /* write */
    x_mov_imm32(RDI, 1);                        /* stdout */
    x_mov_imm64(RSI, DATA_VADDR + off);         /* the bytes */
    x_mov_imm32(RDX, m + 1);                    /* with the newline */
    x_syscall();
}

static void emit_int_print(void)
{
    emit_branch(0, 0, N_PINT, sizeof N_PINT - 1);           /* rdi already carries the value */
}

/* `... N times`: a counter in a stack slot, counted down to zero.  A string
 * body writes the bytes each round; an expression was evaluated once before
 * the loop and lives in its own slot. */
static void emit_times_loop(u32 tmpslot, int isstr, const char *sp, u32 sn, u32 vtmp)
{
    i32 off = -(i32)(8 * tmpslot);
    x_mov_local_r(off, RAX);                        /* the count */
    u64 top = code.len;
    cput(0x48); cput(0x83); cput(0xbd); cput32((u32)off); cput(0x00); /* cmp qword [rbp+off],0 */
    u32 jle = (u32)code.len + 2; cput(0x0f); cput(0x8e); cput32(0);                    /* jle out */
    if (isstr) emit_str_write(sp, sn);
    else {
        x_mov_r_local(RDI, -(i32)(8 * vtmp));
        emit_int_print();
    }
    cput(0x48); cput(0xff); cput(0x8d); cput32((u32)off); /* dec qword [rbp+off] */
    x_jmp((i32)top - (i32)(code.len + 5));          /* jmp top */
    patch_rel_at(jle, code.len);
}

/* does what is left of the statement end with the word `times`?  if so cut
 * it off; what remains before it is the count expression */
static int cut_times(Lx *l)
{
    u32 e = l->n;
    while (e > l->i && (l->p[e-1] == ' ' || l->p[e-1] == '\t')) e--;
    if (e < l->i + 6) return 0;
    if (memcmp(l->p + e - 5, "times", 5) != 0) return 0;
    u32 k = e - 6;
    if (l->p[k] != ' ' && l->p[k] != '\t') return 0;
    l->n = e - 5;
    return 1;
}

static void s_print(const Stmt *st, Lx *lx)
{
    lxws(lx);
    int c = lxc(lx);
    int isstr = (c == '\'' || c == '"');
    const char *sp = 0; u32 sn = 0;
    Val val = {V_RAX, 0, 0, 0, 0};
    if (isstr) {
        i64 e = lit_end((const u8 *)lx->p, lx->n, lx->i);
        if (e < 0) die_at("unterminated text", err_line);
        sp = lx->p + lx->i + 1;
        sn = (u32)e - (lx->i + 1);
        lx->i = (u32)e + 1;
    } else {
        val = pExpr(lx);                        /* the value, as a descriptor */
    }
    if (cut_times(lx)) {
        u32 vtmp = 0;
        if (!isstr) { vtmp = ++nloc; force_rax(val); x_mov_local_r(-(i32)(8 * vtmp), RAX); }
        lxws(lx);
        if (lx->i >= lx->n) die_at("times without a count", err_line);
        Val cv = pExpr(lx);                     /* the count */
        force_rax(cv);
        lxws(lx);
        if (lx->i < lx->n) die_at("junk after count", err_line);
        u32 tmp = ++nloc;
        emit_times_loop(tmp, isstr, sp, sn, vtmp);
    } else {
        lxws(lx);
        if (lx->i < lx->n) die_at("junk after print", err_line);
        if (isstr) emit_str_write(sp, sn);
        else {
            if (val.kind == V_LOCAL) x_mov_r_local(RDI, val.loff);
            else if (val.kind == V_IMM) x_mov_reg_imm(RDI, val.imm);
            else x_mov_rr(RDI, RAX);
            if (val.txt) emit_branch(0, 0, N_PTEXT, sizeof N_PTEXT - 1);          /* text */
            else emit_branch(0, 0, N_PINT, sizeof N_PINT - 1);                   /* int */
        }
    }
    (void)st;
}

/* the rest of an `if cond ->` or `as long as cond ->` line, then the block
 * of more-indented lines under it */
static void parse_branch_tail(const Stmt *st)
{
    Stmt nx;
    while (feed_pull(&nx)) {
        if (nx.line != st->line) { feed_unpull(&nx); break; }
        err_line = nx.line + 1;
        parse_statement(&nx);
    }
    parse_block(st->indent);
}

/* find `->` outside quotes; return where the tail starts, 0 when absent */
static u32 find_arrow(const Stmt *st, u32 from)
{
    int q = 0;
    for (u32 i = from; i < st->len; i++) {
        u8 ch = (u8)st->p[i];
        if (q) {
            if (esc_at((const u8 *)st->p, i, st->len)) { i++; continue; }
            if (ch == q) q = 0;
        }
        else if (ch == '\'' || ch == '"') q = ch;
        else if (ch == '-' && i + 1 < st->len && st->p[i+1] == '>') return i + 2;
    }
    return 0;
}

/* the body of an if or a loop: the `->` statement, the rest of the line,
 * and the indented block below */
static void parse_body(const Stmt *st, u32 arrow)
{
    if (arrow) {
        Stmt tail;
        tail.p = st->p + arrow; tail.len = st->len - arrow;
        tail.indent = st->indent; tail.line = st->line;
        parse_statement(&tail);
    }
    parse_branch_tail(st);
}

/* is the next statement a bare `if not` (or `if not -> tail`), at this
 * indent?  That is the else form; `if not <condition>` is a negated if
 * and stays put. */
static int peek_is_if_not(u32 indent)
{
    Stmt nx;
    if (!feed_peek(&nx) || nx.indent != indent) return 0;
    Lx nl = { nx.p, nx.len, 0 };
    const char *w, *w2; u32 wl, wl2;
    if (!(lx_word(&nl, &w, &wl) && word_is(w, wl, "if")
          && lx_word(&nl, &w2, &wl2) && word_is(w2, wl2, "not"))) return 0;
    lxws(&nl);
    if (nl.i >= nl.n) return 1;                    /* nothing after: bare */
    return nl.p[nl.i] == '-' && nl.i + 1 < nl.n && nl.p[nl.i + 1] == '>';
}

static void s_if(const Stmt *st, Lx *lx)
{
    u32 arrow = find_arrow(st, lx->i);
    u32 cond_end = arrow ? arrow - 2 : st->len;
    Lx cl = { st->p, cond_end, lx->i };
    force_rax(pExpr(&cl));
    lxws(&cl);
    if (cl.i < cl.n) die_at("junk in condition", err_line);
    x_test_rr(RAX, RAX);
    u32 jz = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);   /* jz else */

    parse_body(st, arrow);
    u32 jmp = (u32)code.len + 1; cput(0xe9); cput32(0);                    /* jmp end */

    if (peek_is_if_not(st->indent)) {
        Stmt el;
        feed_next(&el);
        err_line = el.line + 1;
        Lx elx = { el.p, el.len, 0 };
        const char *w, *w2; u32 wl, wl2;
        lx_word(&elx, &w, &wl); lx_word(&elx, &w2, &wl2);       /* "if not" */
        patch_rel_at(jz, code.len);                             /* else starts here */
        u32 earrow = find_arrow(&el, elx.i);
        parse_body(&el, earrow);
        patch_rel_at(jmp, code.len);
    } else {
        patch_rel_at(jz, code.len);
        patch_rel_at(jmp, code.len);
    }
}

/* the loop-exit jumps that `leave` cut inside the body; each loop owns the
 * ones recorded after its marker */
static u32 lv[512];
static u32 nlv;

static void s_while(const Stmt *st, Lx *lx)
{
    u32 arrow = find_arrow(st, lx->i);
    u32 cond_end = arrow ? arrow - 2 : st->len;
    Lx cl = { st->p, cond_end, lx->i };
    u64 top = code.len;
    force_rax(pExpr(&cl));
    lxws(&cl);
    if (cl.i < cl.n) die_at("junk in condition", err_line);
    x_test_rr(RAX, RAX);
    u32 jz = (u32)code.len + 2; cput(0x0f); cput(0x84); cput32(0);   /* jz out */
    u32 mark = nlv;                            /* leaves below here are mine */
    parse_body(st, arrow);
    x_jmp((i32)top - (i32)(code.len + 5));          /* jmp top */
    patch_rel_at(jz, code.len);
    for (u32 i = mark; i < nlv; i++)               /* every leave lands here */
        patch_rel_at(lv[i], code.len);
    nlv = mark;
}

static void s_return(const Stmt *st, Lx *lx)
{
    lxws(lx);
    if (lx->i < lx->n) {
        Val v = pExpr(lx);
        if (v.txt) cur_fn_txt = 1;                 /* the function answers text */
        force_rax(v);
    }
    else x_xor_eax();
    x_leave();
    x_ret();
    (void)st;
}

static void s_assign(const Stmt *st, Lx *lx, const char *name, u32 nlen)
{
    lx->i++;                                        /* the ':' */
    Val v = pExpr(lx);
    lxws(lx);
    if (lx->i < lx->n) die_at("junk after assignment", err_line);
    u32 before = lt.used;
    Slot *t = sym_define(&lt, name, nlen, cur_scope, K_VAR, nloc + 1);
    if (lt.used != before) nloc++;                   /* a fresh slot was cut */
    else if ((slot_kind(t) & 0x7f) != K_VAR) die2("not a variable", name, nlen);
    if (v.txt) slot_settxt(t);                       /* the type follows the */
    else slot_clrtxt(t);                             /* latest assignment */
    i32 off = -(i32)(8 * slot_val(t));
    if (v.kind == V_IMM && fits_i32(v.imm)) x_store_local_imm32(off, (i32)v.imm);
    else if (v.kind == V_LOCAL && v.loff == off) { }          /* x: x */
    else if (v.kind == V_LOCAL) { x_mov_r_local(RAX, v.loff); x_mov_local_r(off, RAX); }
    else { force_rax(v); x_mov_local_r(off, RAX); }
    (void)st;
}

static void s_call(const Stmt *st, Lx *lx, const char *name, u32 nlen)
{
    lx->i++;                                        /* the '(' */
    emit_call_args(lx, name, nlen);
    lxws(lx);
    if (lx->i < lx->n) die_at("junk after call", err_line);
    (void)st;
}

/* `wipe s` -- a call whose arguments are separated by spaces instead of
 * commas and parens.  Each piece parses as one expression. */
static void s_call_spaces(const Stmt *st, Lx *lx, const char *name, u32 nlen)
{
    Val vars[6];
    u8 parked[6];
    u32 n = 0;
    for (;;) {
        lxws(lx);
        if (lx->i >= lx->n || n >= 6) break;
        vars[n] = pExpr(lx);
        if (vars[n].kind == V_RAX) { x_push(RAX); parked[n] = 1; }
        else parked[n] = 0;
        n++;
    }
    for (u32 k = 0; k < n; k++)
        if (!parked[k]) {
            if (vars[k].kind == V_IMM) x_mov_reg_imm(argreg[k], vars[k].imm);
            else x_mov_r_local(argreg[k], vars[k].loff);
        }
    for (u32 k = n; k > 0; k--)
        if (parked[k-1]) x_pop(argreg[k-1]);
    emit_branch(0, 0, name, nlen);
    (void)st;
}

static void parse_statement(const Stmt *st)
{
    err_line = st->line + 1;
    Lx lx = { st->p, st->len, 0 };
    const char *w; u32 wl;
    if (!lx_word(&lx, &w, &wl)) die_at("empty statement", err_line);
    if (word_is(w, wl, "print")) { s_print(st, &lx); return; }
    if (word_is(w, wl, "return")) { s_return(st, &lx); return; }
    if (word_is(w, wl, "stop") && lxc(&lx) != ':'
        && !sym_find(&lt, "stop", 4, cur_scope) && !sym_find(&gt, "stop", 4, 0)) {
        x_mov_imm32(RDI, 0);                        /* halt the program */
        x_mov_imm32(RAX, 60);
        x_syscall();
        return;
    }
    if (word_is(w, wl, "private") && lxc(&lx) != ':'
        && !sym_find(&lt, "private", 7, cur_scope) && !sym_find(&gt, "private", 7, 0))
        return;                                   /* a privacy marker: nothing */
    if (word_is(w, wl, "include") && lxc(&lx) != ':'
        && !sym_find(&lt, "include", 7, cur_scope) && !sym_find(&gt, "include", 7, 0)) {
        splice_include(&lx, st);
        return;
    }
    if (word_is(w, wl, "wipe") && lxc(&lx) != ':'
        && !sym_find(&lt, "wipe", 4, cur_scope) && !sym_find(&gt, "wipe", 4, 0)) {
        /* zero the text named after it */
        const char *aw; u32 awl;
        if (!lx_word(&lx, &aw, &awl)) die_at("wipe expects a name", err_line);
        Slot *t = sym_find(&lt, aw, awl, cur_scope);
        if (!t) die2("unknown name", aw, awl);
        x_mov_r_local(RDI, -(i32)(8 * slot_val(t)));
        emit_branch(0, 0, N_WIPE, sizeof N_WIPE - 1);
        lxws(&lx);
        if (lx.i < lx.n) die_at("junk after wipe", err_line);
        return;
    }
    if (word_is(w, wl, "leave") && lxc(&lx) != ':'
        && !sym_find(&lt, "leave", 5, cur_scope) && !sym_find(&gt, "leave", 5, 0)) {
        if (nlv >= 512) die("too many leaves");
        cput(0xe9);                                 /* jmp, patched by the loop */
        lv[nlv] = (u32)code.len; cput32(0);
        nlv++;
        return;
    }
    if (word_is(w, wl, "if")) { s_if(st, &lx); return; }   /* `not` is pUn's */
    if (word_is(w, wl, "as")) {
        const char *w2, *w3; u32 wl2, wl3;
        if (!lx_word(&lx, &w2, &wl2) || !word_is(w2, wl2, "long")
            || !lx_word(&lx, &w3, &wl3) || !word_is(w3, wl3, "as"))
            die_at("as long as expected", err_line);
        s_while(st, &lx);
        return;
    }
    /* a name: assignment, a call, or a space-separated call */
    lxws(&lx);
    if (lxc(&lx) == ':') { s_assign(st, &lx, w, wl); return; }
    if (lxc(&lx) == '(') { s_call(st, &lx, w, wl); return; }
    if (lx.i < lx.n) { s_call_spaces(st, &lx, w, wl); return; }
    die_at("statement not understood", err_line);
}

static void parse_block(u32 parent_indent)
{
    Stmt st;
    while (feed_pull(&st)) {
        if (st.indent <= parent_indent) { feed_unpull(&st); return; }
        parse_statement(&st);
    }
}

/* ---------------------------------------------------------- functions */

static void parse_function(const Stmt *st)
{
    err_line = st->line + 1;
    Lx lx = { st->p, st->len, 0 };
    const char *name; u32 nlen;
    if (!lx_word(&lx, &name, &nlen)) die_at("function name expected", err_line);
    if (code.len >= 0xffffff) die("program too large for this sc");

    Slot *f = sym_define(&gt, name, nlen, 0, K_FUNC, (u32)code.len);
    slot_setval(f, (u32)code.len);

    x_push_rbp();
    x_mov_rbp_rsp();
    x_sub_rsp_imm32(0);                     /* patched when the body is done */
    sub_off = (u32)code.len - 4;

    cur_scope = ++scope_serial;
    nloc = 0;
    cur_fn_txt = 0;
    u32 npar = 0;
    const char *pw; u32 pwl;
    while (lx_word(&lx, &pw, &pwl)) {
        if (npar < 6) {
            Slot *p = sym_define(&lt, pw, pwl, cur_scope, K_VAR, ++nloc);
            x_mov_local_r(-(i32)(8 * slot_val(p)), argreg[npar]);
        } else {
            /* the seventh and up arrive on the stack at [rbp+16] and up;
             * each is copied into its own local slot on entry */
            Slot *p = sym_define(&lt, pw, pwl, cur_scope, K_VAR, ++nloc);
            i32 dst = -(i32)(8 * slot_val(p));
            x_mov_r_local(RAX, (i32)(16 + 8 * (npar - 6)));
            x_mov_local_r(dst, RAX);
        }
        npar++;
    }

    parse_block(st->indent);                /* the indented body */

    if (cur_fn_txt) slot_settxt(f);         /* answers text */

    u32 frame = (8 * nloc + 15) & ~15u;
    bputat32(&code, sub_off, frame);
    x_xor_eax();                            /* falling off the end returns 0 */
    x_leave();
    x_ret();
    cur_scope = 0;
}

/* a top-level line is a function when it ends with ':' */
static int line_is_def(const Stmt *st)
{
    return st->len > 0 && st->p[st->len - 1] == ':';
}

/* globals: top-level `NAME: <runtime value>` -- a slot plus a statement to
 * replay into the init sequence once every function is on file */
typedef struct { Stmt st; const char *name; u32 nlen, off; } Glob;
static Glob glob[4096];
static u32 nglob;

/* constants: a top-level `NAME: value`.  The value lives in the side table
 * above, indexed by the slot's 24-bit field, so 64-bit constants are fine. */
static void parse_const(const Stmt *st)
{
    err_line = st->line + 1;
    Lx lx = { st->p, st->len, 0 };
    const char *w; u32 wl;
    if (!lx_word(&lx, &w, &wl)) die_at("statement outside a function", err_line);
    lxws(&lx);
    if (lxc(&lx) != ':') die_at("statement outside a function", err_line);
    lx.i++;
    Val v = pExpr(&lx);
    lxws(&lx);
    if (lx.i < lx.n) die_at("junk after constant", err_line);
    if (v.kind == V_IMM) {                        /* a foldable constant */
        if (ncval >= 8192) die("too many constants");
        cval[ncval] = v.imm;
        sym_define(&gt, w, wl, 0, K_CONST, ncval);
        ncval++;
        return;
    }
    /* anything else is a global: an eight-byte slot in the data segment,
     * filled before main runs by the init sequence */
    u64 off = data.len;
    for (int i = 0; i < 8; i++) bput(&data, 0);
    Slot *t = sym_define(&gt, w, wl, 0, K_GVAR, (u32)off);
    if (v.txt) slot_settxt(t);
    if (nglob >= 4096) die("too many globals");
    glob[nglob].st = *st;
    glob[nglob].name = w;
    glob[nglob].nlen = wl;
    glob[nglob].off = (u32)off;
    nglob++;
}

/* ---------------------------------------------------------- the ELF file
 * The shape sa writes: a header page, text readable and executable at
 * 0x401000, data readable and writable at 0x600000, no section headers. */

static void put32_at(u8 *h, u32 at, u32 v) { memcpy(h + at, &v, 4); }
static void put64_at(u8 *h, u32 at, u64 v) { memcpy(h + at, &v, 8); }
static void put16_at(u8 *h, u32 at, u16 v) { memcpy(h + at, &v, 2); }

static void write_all(int fd, const void *p, u64 n)
{
    const u8 *b = p;
    while (n) {
        i64 r = write(fd, b, n);
        if (r <= 0) die("write failed");
        b += r; n -= (u64)r;
    }
}

static void write_elf(const char *path)
{
    u64 code_len = code.len, data_len = data.len;
    u64 data_off = 0x1000 + ((code_len + 0xfffull) & ~0xfffull);
    u8 *h = calloc(1, 0x1000);
    if (!h) die("out of memory");
    h[0] = 0x7f; h[1] = 'E'; h[2] = 'L'; h[3] = 'F';
    h[4] = 2; h[5] = 1; h[6] = 1;                      /* 64-bit, LSB, v1 */
    put16_at(h, 16, 2);                                /* ET_EXEC */
    put16_at(h, 18, 62);                               /* x86-64 */
    put32_at(h, 20, 1);
    put64_at(h, 24, TEXT_ORG);                         /* entry: _start */
    put64_at(h, 32, 64);                               /* phoff */
    put16_at(h, 52, 64);                               /* ehsize */
    put16_at(h, 54, 56);                               /* phentsize */
    put16_at(h, 56, 2);                                /* phnum */
    put16_at(h, 58, 64);                               /* shentsize */
    /* text: readable, executable */
    put32_at(h, 64, 1); put32_at(h, 68, 5);
    put64_at(h, 72, 0x1000); put64_at(h, 80, TEXT_ORG); put64_at(h, 88, TEXT_ORG);
    put64_at(h, 96, code_len); put64_at(h, 104, code_len); put64_at(h, 112, 0x1000);
    /* data: readable, writable */
    put32_at(h, 120, 1); put32_at(h, 124, 6);
    put64_at(h, 128, data_off); put64_at(h, 136, DATA_VADDR); put64_at(h, 144, DATA_VADDR);
    put64_at(h, 152, data_len); put64_at(h, 160, data_len); put64_at(h, 168, 0x1000);

    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0755);
    if (fd < 0) die("cannot open output");
    write_all(fd, h, 0x1000);
    write_all(fd, code.p, code_len);
    if (data_len) {
        if (lseek(fd, (off_t)data_off, SEEK_SET) < 0) die("seek failed");
        write_all(fd, data.p, data_len);
    }
    close(fd);
    free(h);
}

/* --------------------------------------------------------------- main */

static void read_file(const char *path, Buf *b)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0) die("cannot open source");
    for (;;) {
        bgrow(b, 65536);
        i64 r = read(fd, b->p + b->len, 65536);
        if (r < 0) die("read failed");
        if (r == 0) break;
        b->len += (u64)r;
    }
    close(fd);
}

int main(int argc, char **argv)
{
    const char *file = 0, *out = "a.out";
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-o") && i + 1 < argc) out = argv[++i];
        else if (!file) file = argv[i];
        else die("usage: sc FILE.sov [-o OUT]");
    }
    if (!file) die("usage: sc FILE.sov [-o OUT]");

    Buf src = {0};
    read_file(file, &src);
    build_statements(&src, &fr[0]);
    nfr = 1;

    /* two tables: locals are sized from the source, globals from the count
     * of top-level definition lines, which the split has already produced
     * (see tbl_init) */
    u32 ndefs = 0;
    for (u32 i = 0; i < fr[0].n; i++)
        if (fr[0].st[i].indent == 0 && fr[0].st[i].len > 0
            && fr[0].st[i].p[fr[0].st[i].len - 1] == ':')
            ndefs++;
    tbl_init(&gt, ndefs);
    tbl_init(&lt, src.len / 40);
    emit_runtime();

    Stmt st;
    while (feed_pull(&st)) {
        /* `use name` / `use:` / `include file` -- splice library text in */
        if (st.indent == 0) {
            Lx ul = { st.p, st.len, 0 };
            const char *uw, *mw; u32 uwl, mwl;
            if (lx_word(&ul, &uw, &uwl) && word_is(uw, uwl, "use")) {
                if (lxc(&ul) == ':') {                    /* the block form */
                    /* the items belong to THIS frame; read them directly so a
                     * module pushed for an earlier item cannot leak in here */
                    Frame *f = &fr[nfr - 1];
                    u32 k = f->cur;
                    u32 cnt = 0;
                    while (k + cnt < f->n && f->st[k + cnt].indent > st.indent) cnt++;
                    for (u32 j = cnt; j > 0; j--) {       /* reverse: first item on top */
                        Stmt *m = &f->st[k + j - 1];
                        Lx ml = { m->p, m->len, 0 };
                        if (lx_word(&ml, &mw, &mwl) && ml.i >= ml.n) use_module(mw, mwl);
                        else die_at("module name expected", m->line + 1);
                    }
                    f->cur = k + cnt;
                    continue;
                }
                if (lx_word(&ul, &mw, &mwl) && ul.i >= ul.n) { use_module(mw, mwl); continue; }
                die_at("junk after use", st.line + 1);
            }
            ul.i = 0;                                    /* rewind, then include */
            if (lx_word(&ul, &uw, &uwl) && word_is(uw, uwl, "include")) {
                splice_include(&ul, &st);
                continue;
            }
        }
        if (line_is_def(&st)) {
            if (st.indent != 0) die_at("nested function definition", st.line + 1);
            parse_function(&st);
        } else if (st.indent == 0) {
            parse_const(&st);                /* NAME: value */
        } else {
            die_at("statement outside a function", st.line + 1);
        }
    }

    for (u32 i = 0; i < npat; i++) {
        Slot *t = sym_find(&gt, pat[i].name, pat[i].nlen, 0);
        if (!t) die2("unknown function", pat[i].name, pat[i].nlen);
        patch_rel_at(pat[i].at, slot_val(t));
    }

    /* the init sequence: every global's statement replayed in order, with
     * every function now on file so even forward references resolve */
    def_label(N_INIT, sizeof N_INIT - 1);
    for (u32 i = 0; i < nglob; i++) {
        Glob *g = &glob[i];
        err_line = g->st.line + 1;
        Lx lx = { g->st.p, g->st.len, 0 };
        const char *gw; u32 gwl;
        if (!lx_word(&lx, &gw, &gwl) || gwl != g->nlen || memcmp(gw, g->name, gwl) != 0)
            die_at("global lost its name", err_line);
        lx.i++;                                   /* the ':' */
        Val v = pExpr(&lx);
        lxws(&lx);
        if (lx.i < lx.n) die_at("junk after global", err_line);
        force_rax(v);
        x_mov_imm64(RCX, DATA_VADDR + g->off);
        cput(0x48); cput(0x89); cput(0x01);       /* mov [rcx],rax */
        Slot *t = sym_find(&gt, g->name, g->nlen, 0);
        if (t && v.txt) slot_settxt(t);           /* text is sticky here too */
    }
    x_ret();

    write_elf(out);
    return 0;
}
