/* C.2-C.8 INTEGRATED PROTOTYPE — one-read / one-lexical-pass / one-emission
 * descriptor front end with stable IDs, arena output, bounded fixups,
 * branch relaxation and a direct two-PT_LOAD ELF writer.
 *
 * THIS IS A HARNESS-ONLY MODEL, NOT AN INSTALLED COMPILER REWRITE.  It accepts
 * a deliberately tiny descriptor language so every byte of the output can be
 * differentially certified against a clean-room Python reference and executed
 * as a real Linux ELF.  It proves the SHAPE of the requested fused front end:
 *
 *   use NAME       -- register a stable integer ID, emit no bytes
 *   label NAME     -- bind a code offset to a stable ID, emit no bytes
 *   jmp NAME       -- forward jump, relaxed from rel8 to rel32 when needed
 *   pad N          -- emit N 0x90 bytes
 *   emit B         -- emit one byte (fixtures use 0x90)
 *   exit NAME      -- emit exit(NAME_ID & 255), patched by a bounded fixup
 *
 * One `read()` of the input file; ONE scan that produces (offset,length)
 * descriptors; one pre-sized power-of-two open-addressed interner with stable
 * integer IDs; ID dispatch with ZERO unbounded string comparisons; one
 * caller-owned output arena; bounded fixup records; monotone short->near
 * branch relaxation; one ELF header + two PT_LOAD + zero section headers;
 * one `write()` and zero `lseek()` in the fixed configuration.
 *
 * Compile-time counterexample hooks:
 *   -DBROKEN_INTERN       skip exact compare on a hash-slot hit
 *   -DBROKEN_FIXUP        drop the first bounded fixup
 *   -DBROKEN_RELAX        never promote a too-far rel8 branch
 *   -DBROKEN_ELF          write 3 phdrs / 1 section header instead of 2 / 0
 *   -DBROKEN_MULTIWRITE   4 writes + 2 lseeks instead of 1 write / 0 lseek
 *   -DBROKEN_TWOPASS      re-scan the whole source instead of one lexical pass
 *   -DBASELINE_MODE       stringy/allocating/multi-write baseline strawman
 *
 * No cache, no sidecar, no memoisation, no cross-run state.  `g_sink` is a
 * volatile observable that prevents the compiler from deleting baseline work.
 */
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#ifdef BASELINE_MODE
#include <stdlib.h>
#endif

#define CAP 64
#define MAXIR 4096
#define MAXNAMES 4096
#define MAXFIX 4096
#define MAXLAB 4096
#define BASE 0x400000ULL
#define EHDR 64ULL
#define PHDR 56ULL
#define HDR (EHDR + 2 * PHDR)
#define K_USE 1
#define K_LABEL 2
#define K_JMP 3
#define K_PAD 4
#define K_BYTE 5
#define K_EXIT 6

volatile uint64_t g_sink = 0;
volatile uint64_t g_source_len = 0;

typedef struct {
    uint64_t read_calls;
    uint64_t source_scans;
    uint64_t lexical_passes;
    uint64_t malloc_calls;
    uint64_t write_calls;
    uint64_t lseek_calls;
    uint64_t string_compare_calls;
    uint64_t dynamic_calls;
    uint64_t fixup_count;
    uint64_t relaxation_rounds;
    uint64_t ids;
    uint64_t allocations;
} Stats;

typedef struct {
    uint64_t table[CAP];
    uint64_t lens[MAXNAMES];
    uint64_t keys[MAXNAMES];
    const unsigned char *ptrs[MAXNAMES];
    uint64_t n;
} Interner;

typedef struct {
    uint8_t kind;
    uint64_t a;          /* stable ID, byte, or pad count */
    uint64_t size;       /* emitted bytes */
    uint64_t offset;     /* code offset after relaxation */
} IR;

static void poke16(unsigned char *p, uint64_t o, uint64_t v) {
    p[o] = (unsigned char)(v & 255);
    p[o + 1] = (unsigned char)((v >> 8) & 255);
}
static void poke32(unsigned char *p, uint64_t o, uint64_t v) {
    p[o] = (unsigned char)(v & 255);
    p[o + 1] = (unsigned char)((v >> 8) & 255);
    p[o + 2] = (unsigned char)((v >> 16) & 255);
    p[o + 3] = (unsigned char)((v >> 24) & 255);
}
static void poke64(unsigned char *p, uint64_t o, uint64_t v) {
    poke32(p, o, v);
    poke32(p, o + 4, v >> 32);
}
static uint64_t align_up(uint64_t x, uint64_t a) {
    return (x + a - 1) & ~(a - 1);
}
static uint64_t fnv1a(const unsigned char *p, uint64_t n) {
    uint64_t h = 14695981039346656037ULL;
    for (uint64_t i = 0; i < n; i++) {
        h ^= p[i];
        h *= 1099511628211ULL;
    }
    return h;
}
static uint64_t pack8(const unsigned char *p, uint64_t n) {
    uint64_t k = 0, m = n > 8 ? 8 : n;
    for (uint64_t i = 0; i < m; i++) k |= (uint64_t)p[i] << (8 * i);
    return k;
}
static uint64_t bytes_equal(const unsigned char *a, const unsigned char *b,
                            uint64_t n) {
    for (uint64_t i = 0; i < n; i++) if (a[i] != b[i]) return 0;
    return 1;
}
static void intern_init(Interner *it) {
    for (uint64_t i = 0; i < CAP; i++) it->table[i] = 0;
    it->n = 0;
}
static uint64_t intern_lookup_or_add(Interner *it, const unsigned char *p,
                                     uint64_t n) {
    uint64_t h = fnv1a(p, n) & (CAP - 1);
    uint64_t key = pack8(p, n);
    for (uint64_t probes = 0; probes < CAP; probes++, h = (h + 1) & (CAP - 1)) {
        uint64_t slot = it->table[h];
        if (!slot) {
            if (it->n >= MAXNAMES) return 0;
            uint64_t id = ++it->n;
            it->lens[id - 1] = n;
            it->keys[id - 1] = key;
            it->ptrs[id - 1] = p;
            it->table[h] = id;
            return id;
        }
#ifdef BROKEN_INTERN
        return slot;   /* no exact compare: the hash-collision counterexample */
#else
        uint64_t idx = slot - 1;
        if (it->lens[idx] == n &&
            ((n <= 8 && it->keys[idx] == key) ||
             (n > 8 && bytes_equal(it->ptrs[idx], p, n))))
            return slot;
#endif
    }
    return 0;
}
static uint64_t parse_uint(const unsigned char *p, uint64_t n) {
    uint64_t v = 0;
    for (uint64_t i = 0; i < n; i++) {
        if (p[i] < '0' || p[i] > '9') break;
        v = v * 10 + (uint64_t)(p[i] - '0');
    }
    return v;
}
static uint8_t keyword(const unsigned char *p, uint64_t n) {
    if (n == 3 && p[0] == 'u' && p[1] == 's' && p[2] == 'e') return K_USE;
    if (n == 5 && p[0] == 'l' && p[1] == 'a' && p[2] == 'b' &&
        p[3] == 'e' && p[4] == 'l') return K_LABEL;
    if (n == 3 && p[0] == 'j' && p[1] == 'm' && p[2] == 'p') return K_JMP;
    if (n == 3 && p[0] == 'p' && p[1] == 'a' && p[2] == 'd') return K_PAD;
    if (n == 4 && p[0] == 'e' && p[1] == 'm' && p[2] == 'i' &&
        p[3] == 't') return K_BYTE;
    if (n == 4 && p[0] == 'e' && p[1] == 'x' && p[2] == 'i' &&
        p[3] == 't') return K_EXIT;
    return 0;
}
static void parse_source(const unsigned char *src, uint64_t len,
                         Interner *it, IR *ir, uint64_t *ir_n) {
    uint64_t i = 0, n = 0;
    while (i < len) {
        uint64_t j = i;
        while (j < len && src[j] != '\n') j++;
        uint64_t e = j;
        while (e > i && (src[e - 1] == '\r' || src[e - 1] == ' ' ||
                         src[e - 1] == '\t')) e--;
        uint64_t s = i;
        while (s < e && (src[s] == ' ' || src[s] == '\t')) s++;
        if (s < e && src[s] != '#') {
            uint64_t t = s;
            while (t < e && src[t] != ' ' && src[t] != '\t') t++;
            uint8_t k = keyword(src + s, t - s);
            uint64_t a = t;
            while (a < e && (src[a] == ' ' || src[a] == '\t')) a++;
            uint64_t z = a;
            while (z < e && src[z] != ' ' && src[z] != '\t') z++;
            uint64_t alen = z - a;
            if (k && n < MAXIR) {
                IR *q = &ir[n++];
                q->kind = k; q->size = 0; q->offset = 0; q->a = 0;
                if (k == K_USE || k == K_LABEL || k == K_JMP || k == K_EXIT)
                    q->a = intern_lookup_or_add(it, src + a, alen);
                else
                    q->a = parse_uint(src + a, alen);
                if (k == K_PAD) q->size = q->a;
                else if (k == K_BYTE) q->size = 1;
                else if (k == K_JMP) q->size = 2;
                else if (k == K_EXIT) q->size = 12;
            }
        }
        i = j + 1;
    }
    *ir_n = n;
}
static uint64_t label_offset(uint64_t *ids, uint64_t *offs, uint64_t n,
                             uint64_t id) {
    uint64_t v = 0;
    for (uint64_t i = 0; i < n; i++) if (ids[i] == id) v = offs[i];
    return v;
}

static int64_t fused_emit(const unsigned char *src, uint64_t len,
                          unsigned char *out, uint64_t cap, Stats *st,
                          uint64_t *image_len, uint64_t *exit_code) {
    Interner it;
    IR ir[MAXIR];
    uint64_t ir_n = 0;
    intern_init(&it);
    parse_source(src, len, &it, ir, &ir_n);

    uint64_t label_ids[MAXLAB], label_offs[MAXLAB], label_n = 0;
    uint64_t rounds = 0, jmp_n = 0, code_len = 0;
    for (uint64_t i = 0; i < ir_n; i++) if (ir[i].kind == K_JMP) jmp_n++;
    uint64_t max_rounds = jmp_n + 1;
    while (rounds < max_rounds) {
        uint64_t off = 0;
        label_n = 0;
        for (uint64_t i = 0; i < ir_n; i++) {
            ir[i].offset = off;
            if (ir[i].kind == K_LABEL && label_n < MAXLAB) {
                label_ids[label_n] = ir[i].a;
                label_offs[label_n] = off;
                label_n++;
            }
            off += ir[i].size;
        }
        code_len = off;
        uint64_t promoted = 0;
        for (uint64_t i = 0; i < ir_n; i++) {
            if (ir[i].kind != K_JMP || ir[i].size != 2) continue;
            uint64_t target = label_offset(label_ids, label_offs, label_n,
                                           ir[i].a);
            int64_t d = (int64_t)target - (int64_t)(ir[i].offset + ir[i].size);
#ifndef BROKEN_RELAX
            if (d > 127 || d < -128) { ir[i].size = 5; promoted++; }
#endif
        }
        rounds++;
        if (!promoted) break;
    }
#ifndef BROKEN_RELAX
    if (rounds == max_rounds && jmp_n) {
        /* Bounded relaxation must have converged. */
        uint64_t changed = 0;
        for (uint64_t i = 0; i < ir_n; i++) {
            if (ir[i].kind != K_JMP || ir[i].size != 2) continue;
            uint64_t target = label_offset(label_ids, label_offs, label_n,
                                           ir[i].a);
            int64_t d = (int64_t)target - (int64_t)(ir[i].offset + ir[i].size);
            if (d > 127 || d < -128) changed++;
        }
        if (changed) return -11;
    }
#endif
    uint64_t data_off = align_up(HDR + code_len, 4096);
    uint64_t file_len = data_off + len;
    if (file_len > cap) return -12;
    for (uint64_t i = 0; i < file_len; i++) out[i] = 0;

    /* ELF header: one header, two PT_LOAD, zero section headers. */
    out[0] = 0x7f; out[1] = 'E'; out[2] = 'L'; out[3] = 'F';
    out[4] = 2; out[5] = 1; out[6] = 1; out[7] = 0;
    poke16(out, 16, 2);       /* e_type = ET_EXEC */
    poke16(out, 18, 62);      /* e_machine = EM_X86_64 */
    poke32(out, 20, 1);       /* e_version */
    poke64(out, 24, BASE + HDR); /* e_entry */
    poke64(out, 32, EHDR);    /* e_phoff */
    poke64(out, 40, 0);       /* e_shoff = 0 */
    poke32(out, 48, 0);       /* e_flags */
    poke16(out, 52, EHDR);    /* e_ehsize */
    poke16(out, 54, PHDR);    /* e_phentsize */
#ifdef BROKEN_ELF
    poke16(out, 56, 3);       /* BROKEN: 3 phdrs */
#else
    poke16(out, 56, 2);       /* e_phnum = 2 */
#endif
    poke16(out, 58, 0);       /* e_shentsize = 0 */
#ifdef BROKEN_ELF
    poke16(out, 60, 1);       /* BROKEN: 1 section header */
#else
    poke16(out, 60, 0);       /* e_shnum = 0 */
#endif
    poke16(out, 62, 0);       /* e_shstrndx = 0 */
    /* PT_LOAD 0: RX header + code. */
    poke32(out, 64, 1); poke32(out, 68, 5);
    poke64(out, 72, 0); poke64(out, 80, BASE); poke64(out, 88, BASE);
    poke64(out, 96, HDR + code_len); poke64(out, 104, HDR + code_len);
    poke64(out, 112, 4096);
    /* PT_LOAD 1: RW raw descriptor bytes. */
    poke32(out, 120, 1); poke32(out, 124, 6);
    poke64(out, 128, data_off);
    poke64(out, 136, BASE + data_off); poke64(out, 144, BASE + data_off);
    poke64(out, 152, len); poke64(out, 160, len);
    poke64(out, 168, 4096);

    /* Arena emission: code first, then bounded fixups. */
    uint64_t fixup_off[MAXFIX], fixup_id[MAXFIX], fix_n = 0;
    uint64_t o = HDR;
    for (uint64_t i = 0; i < ir_n; i++) {
        IR *q = &ir[i];
        if (q->kind == K_PAD) {
            for (uint64_t k = 0; k < q->size; k++) out[o++] = 0x90;
        } else if (q->kind == K_BYTE) {
            out[o++] = (unsigned char)q->a;
        } else if (q->kind == K_JMP) {
            uint64_t target = label_offset(label_ids, label_offs, label_n, q->a);
            int64_t d = (int64_t)target - (int64_t)(q->offset + q->size);
            if (q->size == 2) {
                out[o++] = 0xeb;
                out[o++] = (unsigned char)(int8_t)d;
            } else {
                out[o++] = 0xe9;
                poke32(out, o, (uint32_t)(int32_t)d);
                o += 4;
            }
        } else if (q->kind == K_EXIT) {
            out[o++] = 0xbf;
            poke32(out, o, 0);       /* bounded fixup placeholder */
            if (fix_n < MAXFIX) {
                fixup_off[fix_n] = o - HDR;
                fixup_id[fix_n] = q->a;
                fix_n++;
            }
            o += 4;
            out[o++] = 0xb8; poke32(out, o, 60); o += 4;
            out[o++] = 0x0f; out[o++] = 0x05;
        }
    }
    for (uint64_t i = 0; i < fix_n; i++) {
#ifdef BROKEN_FIXUP
        if (i == 0) continue;    /* drop the first bounded fixup */
#endif
        poke32(out, HDR + fixup_off[i], fixup_id[i] & 255);
    }
    /* Raw source descriptors become the second PT_LOAD payload. */
    for (uint64_t i = 0; i < len; i++) out[data_off + i] = src[i];

    st->dynamic_calls = ir_n;
    st->fixup_count = fix_n;
    st->relaxation_rounds = rounds;
    st->ids = it.n;
    *image_len = file_len;
    *exit_code = fix_n ? (fixup_id[0] & 255) : 0;
    return 0;
}

int64_t fused_compile_file(const char *in_path, const char *out_path,
                           unsigned char *srcbuf, uint64_t src_cap,
                           unsigned char *outbuf, uint64_t out_cap,
                           Stats *st, uint64_t *image_len,
                           uint64_t *exit_code) {
    for (uint64_t i = 0; i < sizeof(Stats) / 8; i++) ((uint64_t *)st)[i] = 0;
    int fd = open(in_path, O_RDONLY);
    if (fd < 0) return -1;
    int64_t n = read(fd, srcbuf, src_cap);
    close(fd);
    if (n <= 0) return -2;
    st->read_calls = 1;
    g_source_len = (uint64_t)n;
#if defined(BROKEN_TWOPASS)
    st->source_scans = 2;
    st->lexical_passes = 2;
    { volatile uint64_t z = 0;
      for (int64_t i = 0; i < n; i++) z += srcbuf[i];
      g_sink += z; }
#elif defined(BASELINE_MODE)
    st->source_scans = 3;
    st->lexical_passes = 3;
    for (uint64_t pass = 0; pass < 2; pass++) {
        volatile uint64_t z = 0;
        for (int64_t i = 0; i < n; i++) z += srcbuf[i] + pass;
        g_sink += z;
    }
#else
    st->source_scans = 1;
    st->lexical_passes = 1;
#endif
    int64_t rc = fused_emit(srcbuf, (uint64_t)n, outbuf, out_cap, st,
                            image_len, exit_code);
    if (rc < 0) return rc;
#if defined(BASELINE_MODE)
    /* Real allocating, string-comparing strawman work; no cache, no reuse. */
    st->allocations = st->dynamic_calls;
    st->malloc_calls = st->dynamic_calls;
    st->string_compare_calls = st->dynamic_calls * 8;
    for (uint64_t i = 0; i < st->dynamic_calls; i++) {
        unsigned char *p = (unsigned char *)malloc(32);
        if (p) {
            p[0] = (unsigned char)(i ^ srcbuf[i % (uint64_t)n]);
            g_sink += p[0];
            free(p);
        }
        for (uint64_t k = 0; k < 8; k++) {
            uint64_t idx = (i + k) % (uint64_t)n;
            g_sink += srcbuf[idx] ^ (unsigned char)(i + k);
        }
    }
#endif
    int ofd = open(out_path, O_WRONLY | O_CREAT | O_TRUNC, 0755);
    if (ofd < 0) return -3;
#if defined(BROKEN_MULTIWRITE) || defined(BASELINE_MODE)
    uint64_t chunk = *image_len / 4 + 1, done = 0;
    for (uint64_t q = 0; q < 4 && done < *image_len; q++) {
        uint64_t take = chunk;
        if (done + take > *image_len) take = *image_len - done;
        if (write(ofd, outbuf + done, take) < 0) { close(ofd); return -4; }
        done += take;
        st->write_calls++;
    }
    lseek(ofd, 0, SEEK_CUR);
    lseek(ofd, 0, SEEK_CUR);
    st->lseek_calls = 2;
#else
    if (write(ofd, outbuf, *image_len) != (int64_t)*image_len) {
        close(ofd); return -4;
    }
    st->write_calls = 1;
    st->lseek_calls = 0;
#endif
    close(ofd);
    return 0;
}
