/* Differential harness: old inl2 blob vs new inl2 blob (S28).
 * Both blobs are compiled as shared objects from the exact C sources that
 * build the certified emit8 blobs (old entry renamed old_inl2_scan), each
 * driven through its OWN mock tbl-as-cell with identical helper mocks and
 * identical program data (names/params/bodies/gh/gcap/task_user - read
 * only, so sharing the list handles is safe).  Per function index, in
 * flor_range order, one call each, the cell shared across calls exactly
 * like the real compiler: return value, serialized inl2_out and inl2_sln
 * must match byte-for-byte.
 *
 * Case sources:
 *   - hardcoded stress programs (fire-heavy, zzln collisions, memo hits,
 *     the rhs-trim quirk, tabs, trailing blanks, quotes, spawn, >32 sites)
 *   - PRNG-generated programs (seeded, deterministic)
 *   - real .sov files parsed into function blocks (header + indented body)
 *   - the flattened self text (the 1.85MB real workload)
 *
 * ---------------------------------------------------------------------------
 * S28R-1 speedup relay - what was actually wrong and what changed here.
 * Profiled (per-call clock around each blob entry + live hang pinpointing
 * with synthetic gh-N files): the harness was NOT slow inside the blobs.
 * The whole blowup was a harness-side LIVELOCK in the gh scatter:
 *   - run_file collects every indent-0 "name: value" line as a gh member
 *     (occurrences, not distinct names); compiler.sov has 366 such lines,
 *     the 1.85MB flat has 885, but prog_new() fixed the slot table at
 *     gcap=256 and prog_gh_finish() inserts with a linear probe that only
 *     stops at an EMPTY slot.  Once 256 slots are full the 257th insert
 *     spins forever: every input with >=257 global lines (compiler.sov,
 *     both flat halves, the full flat) never terminated at all.  The
 *     ">120s / >540s / 18-22min" numbers from the previous session were
 *     killed-run lower bounds on runs that would never have finished.
 *   - measured blob-side cost after the fix: 0.010s old-side total for the
 *     full flat (1853 cases, biggest real body 2691 lines), so no blob-side
 *     restructuring (Prog chunking / body caps on the certified sources'
 *     hot paths) was warranted - the differential keeps feeding each file
 *     as ONE Prog with whole bodies, exactly like the real compiler.
 * Fixes, all harness-side, both blobs see identical data:
 *   1. gh set: members are deduplicated (a set, like the real compiler's
 *      gh) and the slot table is grown to the next power of two keeping
 *      load < 50% (the same rule the blob's own hashes use), so the
 *      deterministic (i*7+3)%gcap scatter with holes always terminates.
 *   2. line split buffer is sized by counting newlines first (exact
 *      worst case: one line per '\n' plus a possible unterminated tail);
 *      the old n/8+16 guess under-allocated for blank-line runs and
 *      wrote past the heap (100k blank lines = 100k lines, not n/8).
 *   3. per-function body buffer is dynamic (the old fixed body[4096]
 *      silently DROPPED lines beyond 4096); a generous BODY_MAX=65536 hard
 *      cap turns overflow into continuation functions name__cN so no line
 *      is ever silently lost.  Corpus max body is 2691 lines, so nothing
 *      in the required corpus is partitioned or dropped.
 *   4. functions are flushed into a fresh Prog (blob state + arena reset
 *      for BOTH sides equally, gh set replicated) after FMAX=4096
 *      functions; the old code exit(2)'d the whole run at MAXF=8192.
 *      Corpus max is 1322, so the required corpus still runs as a single
 *      Prog per file.
 *   5. optional per-call profiling: S28_PROF=1 prints the slowest blob
 *      calls at exit (used to verify the diagnosis; zero cost when off).
 *   6. stress-bodyok gained "toolong2" (exactly 13 body lines) and
 *      "justfits" (exactly 12) with fully eligible call sites, pinning
 *      the body_ok 12/13-line boundary from both sides: a mutant that
 *      accepts 13-line bodies now diverges on the built-ins alone.
 * ---------------------------------------------------------------------------
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

typedef uint64_t U;
typedef U (*ENTRY)(U, U, U, U);

/* ---- optional per-call profiling (S28_PROF=1) ---- */
static int prof_on;
static double now_sec(void){
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}
#define NTOP 24
static struct { double t; unsigned long long ci, nl; char tag[48]; } topcalls[NTOP];
static int ntop;
static void top_note(double t, U ci, U nl, const char *tag){
    if (ntop < NTOP){
        int i = ntop++;
        while (i > 0 && topcalls[i-1].t < t){
            topcalls[i] = topcalls[i-1]; i--;
        }
        topcalls[i].t = t;
        topcalls[i].ci = ci; topcalls[i].nl = nl;
        snprintf(topcalls[i].tag, 48, "%s", tag);
    } else if (t > topcalls[NTOP-1].t){
        int i = NTOP - 1;
        topcalls[i].t = t; topcalls[i].ci = ci; topcalls[i].nl = nl;
        snprintf(topcalls[i].tag, 48, "%s", tag);
        while (i > 0 && topcalls[i-1].t < t){
            topcalls[i] = topcalls[i-1]; i--;
        }
        topcalls[i].t = t; topcalls[i].ci = ci; topcalls[i].nl = nl;
        snprintf(topcalls[i].tag, 48, "%s", tag);
    }
}

/* ---- list helpers (Sovren shape: cap@0 len@8 elems@16) ---- */
static U mklist(U cap){
    U l = (U)malloc(16 + cap * 8 + 8);
    *(U*)(l) = cap; *(U*)(l + 8) = 0;
    return l;
}
static U list_add(U l, U v){
    U n = *(U*)(l + 8);
    if (n >= *(U*)(l)){
        U nc = *(U*)(l) * 2; if (!nc) nc = 8;
        U nl = (U)malloc(16 + nc * 8 + 8);
        *(U*)(nl) = nc; *(U*)(nl + 8) = n;
        memcpy((void*)(nl + 16), (void*)(l + 16), n * 8);
        l = nl;
    }
    *(U*)(l + 16 + n * 8) = v; *(U*)(l + 8) = n + 1;
    return l;
}

/* ---- mock table helpers ---- */
static U g_out = 0, g_sln = 0;
static U mock_alloc(U n){ return (U)malloc(n ? n : 1); }
static U mock_set_out(U v){ g_out = v; return 0; }
static U mock_set_sln(U v){ g_sln = v; return 0; }

/* split_args: mirror of the p4 splitter (destructive in-place trim with
 * NUL pokes, list of inside+ap pointers, grows via list_add).  next_evt
 * is a plain byte walk here: same event positions, same contents. */
static U mock_split_args(U inside, U argl){
    const unsigned char *s = (const unsigned char*)inside;
    U ilen = 0; while (s[ilen]) ilen++;
    int nz = 0;
    for (U i = 0; i < ilen; i++){
        unsigned b = s[i];
        if (b != 32 && b != 9 && b != 10 && b != 13){ nz = 1; break; }
    }
    if (!nz) return argl;
    long depth = 0; int ins = 0; U start = 0;
    for (U i = 0; i < ilen; i++){
        unsigned c = s[i];
        if (ins){
            if (c == 92) i++;
            else if (c == 34) ins = 0;
        } else if (c == 34) ins = 1;
        else if (c == 40) depth++;
        else if (c == 41) depth--;
        else if (c == 44 && depth == 0){
            U ap = start, aq = i;
            while (ap < i && (s[ap]==32||s[ap]==9||s[ap]==10||s[ap]==13)) ap++;
            while (aq > ap && (s[aq-1]==32||s[aq-1]==9||s[aq-1]==10||s[aq-1]==13)) aq--;
            *(unsigned char*)(inside + aq) = 0;
            argl = list_add(argl, inside + ap);
            start = i + 1;
        }
    }
    {
        U ap = start, aq = ilen;
        while (ap < ilen && (s[ap]==32||s[ap]==9||s[ap]==10||s[ap]==13)) ap++;
        while (aq > ap && (s[aq-1]==32||s[aq-1]==9||s[aq-1]==10||s[aq-1]==13)) aq--;
        *(unsigned char*)(inside + aq) = 0;
        argl = list_add(argl, inside + ap);
    }
    return argl;
}

/* tbl-as-cell: 16 slots, one per blob (each blob owns arp/are/state) */
static U to_old[16], to_new[16];

/* ---- program model ---- */
#define MAXF 8192               /* hard array bound inside Prog */
#define FMAX 4096               /* flush a Prog after this many functions */
#define BODY_MAX 65536          /* hard cap per synthetic function body */
typedef struct {
    U nf;
    char *names[MAXF];
    U params[MAXF];
    U bodies[MAXF];
    U sln0[MAXF];          /* first line number of the function */
    U task_user_arr[MAXF];
    U names_l, params_l, bodies_l, task_user_l;
    U gh; U gcap;
    char **gh_names; U gh_n, gh_cap;
} Prog;

static U build_list_arr(U *elems, U n);

static Prog *prog_new(void){
    Prog *p = (Prog*)malloc(sizeof(Prog));
    memset(p, 0, sizeof(*p));
    p->gh_cap = 64;
    p->gh_names = (char**)malloc(p->gh_cap * sizeof(char*));
    p->gcap = 256;
    p->gh = (U)malloc(p->gcap * 8);
    memset((void*)p->gh, 0, p->gcap * 8);
    return p;
}
static void prog_gh_add(Prog *p, const char *nm){
    /* gh is a SET: dedup occurrences (the flat repeats global lines at
     * every include expansion; duplicates would only burn slots) */
    for (U q = 0; q < p->gh_n; q++){
        if (strcmp(p->gh_names[q], nm) == 0) return;
    }
    if (p->gh_n == p->gh_cap){
        p->gh_cap *= 2;
        p->gh_names = (char**)realloc(p->gh_names, p->gh_cap * sizeof(char*));
    }
    p->gh_names[p->gh_n++] = strdup(nm);
}
/* scatter the gh names into the gh slots (deterministic, with holes).
 * THE FIX: the slot table is sized for < 50% load (pow2 >= 2*(gh_n+1)),
 * so the linear probe always finds an empty slot.  The old fixed
 * gcap=256 livelocked forever once a file had >= 257 global lines -
 * compiler.sov (366) and the flat (885 occurrences) never finished. */
static void prog_gh_finish(Prog *p){
    U want = 256;
    while (want < (p->gh_n + 1) * 2) want *= 2;
    if (want != p->gcap){
        free((void*)p->gh);
        p->gcap = want;
        p->gh = (U)malloc(p->gcap * 8);
    }
    memset((void*)p->gh, 0, p->gcap * 8);
    for (U i = 0; i < p->gh_n; i++){
        U slot = (i * 7 + 3) % p->gcap;
        while (*(U*)(p->gh + slot * 8)) slot = (slot + 1) % p->gcap;
        *(U*)(p->gh + slot * 8) = (U)(void*)p->gh_names[i];
    }
}
static U prog_addfn(Prog *p, const char *name, const char **params, U np,
                    const char **lines, U nl, U tu){
    U fi = p->nf++;
    if (fi >= MAXF){ fprintf(stderr, "too many functions\n"); exit(2); }
    p->names[fi] = strdup(name);
    U pl = mklist(np + 4);
    for (U i = 0; i < np; i++) *(U*)(pl + 16 + i * 8) = (U)(void*)strdup(params[i]);
    *(U*)(pl + 8) = np;
    p->params[fi] = pl;
    U bl = mklist(nl + 8);
    for (U i = 0; i < nl; i++) *(U*)(bl + 16 + i * 8) = (U)(void*)strdup(lines[i]);
    *(U*)(bl + 8) = nl;
    p->bodies[fi] = bl;
    p->sln0[fi] = 1000 * (fi + 1);
    p->task_user_arr[fi] = tu;
    return fi;
}
static void prog_finish(Prog *p){
    p->names_l = build_list_arr((U*)p->names, p->nf);
    p->params_l = build_list_arr(p->params, p->nf);
    p->bodies_l = build_list_arr(p->bodies, p->nf);
    p->task_user_l = build_list_arr(p->task_user_arr, p->nf);
    prog_gh_finish(p);
}
static U build_list_arr(U *elems, U n){
    U l = mklist(n + 8);
    for (U i = 0; i < n; i++) *(U*)(l + 16 + i * 8) = elems[i];
    *(U*)(l + 8) = n;
    return l;
}

/* ---- run one program through both blobs, compare per call ---- */
static ENTRY eo, en;
static int ncase, nfail;
static char bo[1 << 22], bn[1 << 22];

static char *ser_lists(U out, U sln, char *buf, size_t bufsz){
    size_t w = 0;
    U lo = out ? *(U*)(out + 8) : 0, ls = sln ? *(U*)(sln + 8) : 0;
    w += snprintf(buf + w, bufsz - w, "L%llu/%llu:", (unsigned long long)lo, (unsigned long long)ls);
    for (U i = 0; i < lo && w < bufsz - 32; i++){
        const char *e = (const char*)(*(U*)(out + 16 + i * 8));
        size_t n = strlen(e);
        w += snprintf(buf + w, bufsz - w, "%zu:", n);
        for (size_t j = 0; j < n && w < bufsz - 16; j++){
            unsigned char c = (unsigned char)e[j];
            if (c >= 32 && c < 127 && c != '\\' && c != ';' && c != '|') buf[w++] = c;
            else w += snprintf(buf + w, bufsz - w, "\\x%02x", c);
        }
        buf[w++] = ';';
    }
    buf[w++] = '|';
    for (U i = 0; i < ls && w < bufsz - 32; i++){
        w += snprintf(buf + w, bufsz - w, "%llu;", (unsigned long long)(*(U*)(sln + 16 + i * 8)));
    }
    buf[w] = 0;
    return buf;
}

static void tbl_reset(U *t){
    memset(t, 0, 16 * 8);
    *(U*)(t + 0) = 4;
    t[1] = (U)mock_set_out;
    t[2] = (U)mock_set_sln;
    t[3] = (U)mock_alloc;
    t[4] = (U)mock_split_args;
    t[7] = 1;   /* gen: set once, never changed (mirrors il_tbl_init) */
}

static void run_program(const char *tag, Prog *p){
    tbl_reset(to_old);
    tbl_reset(to_new);
    for (U ci = 0; ci < p->nf; ci++){
        to_old[9] = p->names_l; to_new[9] = p->names_l;
        to_old[10] = p->params_l; to_new[10] = p->params_l;
        to_old[11] = p->bodies_l; to_new[11] = p->bodies_l;
        to_old[12] = p->gh; to_new[12] = p->gh;
        to_old[13] = p->gcap; to_new[13] = p->gcap;
        to_old[14] = p->task_user_l; to_new[14] = p->task_user_l;
        /* fresh line lists per call (the blob never mutates its input) */
        U lines = p->bodies[ci];
        U nl = *(U*)(lines + 8);
        U sln = mklist(nl + 8);
        for (U i = 0; i < nl; i++) *(U*)(sln + 16 + i * 8) = p->sln0[ci] + i;
        *(U*)(sln + 8) = nl;
        g_out = 0; g_sln = 0;
        double t0 = prof_on ? now_sec() : 0;
        U ro = eo(lines, sln, ci, (U)(void*)to_old);
        if (prof_on) top_note(now_sec() - t0, ci, nl, tag);
        U oo = g_out, os = g_sln;
        g_out = 0; g_sln = 0;
        U rn = en(lines, sln, ci, (U)(void*)to_new);
        ncase++;
        if (ro != rn){
            nfail++;
            fprintf(stderr, "DIVERGE(ret) %s f%llu ci=%llu: old=%llu new=%llu\n",
                    tag, (unsigned long long)ci, (unsigned long long)ci,
                    (unsigned long long)ro, (unsigned long long)rn);
            continue;
        }
        if (ro == 1){
            ser_lists(oo, os, bo, sizeof(bo));
            ser_lists(g_out, g_sln, bn, sizeof(bn));
            if (strcmp(bo, bn) != 0){
                nfail++;
                fprintf(stderr, "DIVERGE(out) %s ci=%llu:\n old %s\n new %s\n",
                        tag, (unsigned long long)ci, bo, bn);
            }
        }
    }
}

/* ---- real .sov file parser: function = indent-0 header line, body =
 * subsequent indented lines until the next indent-0 line ---- */

/* dynamic body buffer push with the BODY_MAX continuation policy:
 * bodies larger than BODY_MAX lines are partitioned into continuation
 * functions name__c1, name__c2, ... (task_user preserved) so no line is
 * ever silently dropped.  The required corpus never hits this (max real
 * body = 2691 lines); the old code silently dropped lines past 4096. */
typedef struct {
    const char **b; U n, cap;
    char *name;             /* current function name (for continuations) */
    U chunk_seq;            /* last continuation index used */
    U tu;                   /* task_user for the current function */
} BodyBuf;

static void bodybuf_flush(Prog *p, BodyBuf *bb, const char **params, U np){
    if (!bb->name) return;
    prog_addfn(p, bb->name, params, np, bb->b, bb->n, bb->tu);
    bb->n = 0;
}
static void bodybuf_push(Prog *p, BodyBuf *bb, const char *L){
    if (bb->n == BODY_MAX){
        char cbuf[512];
        bb->chunk_seq++;
        snprintf(cbuf, sizeof(cbuf), "%s__c%llu", bb->name,
                 (unsigned long long)bb->chunk_seq);
        prog_addfn(p, cbuf, 0, 0, bb->b, bb->n, bb->tu);
        bb->n = 0;
    }
    if (bb->n == bb->cap){
        bb->cap = bb->cap ? bb->cap * 2 : 256;
        bb->b = (const char**)realloc(bb->b, bb->cap * sizeof(char*));
        if (!bb->b){ fprintf(stderr, "out of memory\n"); exit(2); }
    }
    bb->b[bb->n++] = L;
}

static void run_file(const char *tag, const char *path){
    FILE *f = fopen(path, "rb");
    if (!f){ fprintf(stderr, "open %s failed\n", path); return; }
    static char src[32 << 20];
    size_t n = fread(src, 1, sizeof(src) - 1, f);
    if (n >= sizeof(src) - 1){
        fprintf(stderr, "%s: too big (>%zu bytes), skipped\n", path, sizeof(src) - 1);
        fclose(f);
        return;
    }
    src[n] = 0;
    fclose(f);
    Prog *p = prog_new();
    /* split into lines (keep every byte except the newline).
     * A bare '\n' is a 1-byte line, so the exact worst case is one line
     * per newline plus a possible unterminated tail: count first, then
     * allocate exactly (the old n/8+16 and even n/2+16 guesses
     * under-allocated for blank-line runs and wrote past the heap). */
    U ln = 0;
    {
        const char *scan = src;
        while (scan < src + n){
            const char *e = (const char*)memchr(scan, '\n', src + n - scan);
            ln++;
            if (!e) break;
            scan = e + 1;
        }
    }
    U cap_lines = ln + 2;
    char **lines = (char**)malloc(cap_lines * sizeof(char*));
    if (!lines){ fprintf(stderr, "out of memory\n"); exit(2); }
    ln = 0;
    {
        char *cur = src;
        while (cur < src + n){
            char *e = (char*)memchr(cur, '\n', src + n - cur);
            size_t L = e ? (size_t)(e - cur) : (size_t)(src + n - cur);
            char *dup = (char*)malloc(L + 1);
            memcpy(dup, cur, L); dup[L] = 0;
            lines[ln++] = dup;
            if (!e) break;
            cur = e + 1;
        }
    }
    U i = 0;
    char *pending_name = 0;
    const char *pend_params[16]; U pend_np = 0;
    BodyBuf bb; memset(&bb, 0, sizeof(bb));
    U nchunks = 0;             /* Progs flushed for this file (FMAX) */
    while (i <= ln){
        int last = (i == ln);
        const char *L = last ? "" : lines[i];
        int ind0 = (!last) && (L[0] != ' ') && (L[0] != 0) && (L[0] != '#');
        if (ind0){
            size_t ll = strlen(L);
            int is_hdr = ll > 0 && L[ll-1] == ':';
            if (is_hdr){
                /* flush pending (params still belong to pending_name) */
                if (pending_name){
                    bodybuf_flush(p, &bb, pend_params, pend_np);
                    free(pending_name); pending_name = 0;
                }
                /* Prog chunking: after FMAX functions, run what we have
                 * and start a fresh Prog with the same gh set (blob state
                 * and arena reset for BOTH sides equally).  Corpus max is
                 * 1322 functions, so this never triggers on the required
                 * inputs - it replaces the old hard exit(2) at 8192. */
                if (p->nf >= FMAX){
                    char tag2[300];
                    prog_finish(p);
                    snprintf(tag2, sizeof(tag2), "%s#%llu", tag, (unsigned long long)nchunks++);
                    run_program(tag2, p);
                    /* replicate the gh set (same names, same order) into
                     * the fresh Prog so later functions still see it */
                    char **gn = p->gh_names; U gnn = p->gh_n;
                    p = prog_new();
                    for (U q = 0; q < gnn; q++) prog_gh_add(p, gn[q]);
                }
                /* name = first token, params = rest before ':'.
                 * (hdr is intentionally kept alive: pend_params point
                 * into it and are strdup'd only at prog_addfn time) */
                char *hdr = strdup(L);
                hdr[ll-1] = 0;
                char *sp = strchr(hdr, ' ');
                if (sp) *sp = 0;
                pending_name = strdup(hdr);
                pend_np = 0;
                if (sp){
                    char *rest = sp + 1;
                    char *tok = strtok(rest, " ");
                    while (tok && pend_np < 15){ pend_params[pend_np++] = tok; tok = strtok(0, " "); }
                }
                bb.n = 0; bb.chunk_seq = 0; bb.tu = 1;
                bb.name = pending_name;
            } else {
                /* global assignment "g: v" -> gh member (name before ':') */
                char *c = strchr(L, ':');
                if (c && c > L && ((size_t)(c - L) < 64)){
                    char nm[64];
                    size_t L2 = (size_t)(c - L);
                    memcpy(nm, L, L2); nm[L2] = 0;
                    int ok = 1;
                    for (size_t q = 0; q < L2; q++){
                        char cc = nm[q];
                        if (!((cc>='a'&&cc<='z')||(cc>='A'&&cc<='Z')||cc=='_'||(q&&cc>='0'&&cc<='9'))){ ok = 0; break; }
                    }
                    if (ok) prog_gh_add(p, nm);
                }
                if (pending_name){
                    bodybuf_push(p, &bb, L);
                }
            }
        } else if (pending_name){
            bodybuf_push(p, &bb, L);
        }
        i++;
    }
    if (pending_name){
        bodybuf_flush(p, &bb, pend_params, pend_np);
        free(pending_name);
    }
    prog_finish(p);
    if (nchunks){
        char tag2[300];
        snprintf(tag2, sizeof(tag2), "%s#%llu", tag, (unsigned long long)nchunks);
        run_program(tag2, p);
    } else {
        run_program(tag, p);
    }
    free(lines);
    free(bb.b);
}

/* ---- hardcoded stress programs ---- */
static void run_stress(void){
    {
        /* fire-heavy: small straight-line callees called from many sites,
         * zzln collisions (lines and bodies already contain zzln/zzlnt),
         * the rhs double-space trim quirk, memo reuse, >32 sites */
        Prog *p = prog_new();
        prog_addfn(p, "zzln", 0, 0, (const char*[]){"    zzln_t: 1", "    return zzln_t"}, 2, 1);
        prog_addfn(p, "zzlnt", (const char*[]){"a"}, 1, (const char*[]){"    zzlnt2: a", "    return zzlnt2"}, 2, 1);
        prog_addfn(p, "small", (const char*[]){"a", "b"}, 2,
                   (const char*[]){"    t: a", "    u: t + b", "    return u"}, 3, 1);
        prog_addfn(p, "doublesp", (const char*[]){"a"}, 1,
                   (const char*[]){"    t:  a", "    return t"}, 2, 1);
        const char *big[80]; U bn3 = 0;
        big[bn3++] = "    zzln_hit: zzln()";
        for (U q = 0; q < 36; q++){
            char buf[128];
            snprintf(buf, sizeof(buf), "    x%llu: small(%llu, zzlnt(x%llu))", (unsigned long long)q, (unsigned long long)q, (unsigned long long)q);
            big[bn3++] = strdup(buf);
            snprintf(buf, sizeof(buf), "    y%llu:  doublesp(x%llu)", (unsigned long long)q, (unsigned long long)q);
            big[bn3++] = strdup(buf);
        }
        big[bn3++] = "    return x0";
        prog_addfn(p, "caller", (const char*[]){"q"}, 1, big, bn3, 1);
        prog_finish(p);
        run_program("stress-fire", p);
    }
    {
        /* strip paths: tabs after spaces, trailing blanks, empty lines,
         * comments, quotes, spawn, unbalanced parens, if-chains */
        Prog *p = prog_new();
        prog_addfn(p, "plain", (const char*[]){"a"}, 1,
                   (const char*[]){"    t: a + 1", "    return t"}, 2, 1);
        const char *body[] = {
            "    a: plain(1)",
            "     b: plain(2)",
            "    c:  plain(3)",
            "   \td: plain(4)",
            "    e: plain(5) ",
            "    ",
            "    # comment: plain(6)",
            "    f: \"plain(7)\"",
            "    g: spawn plain(8)",
            "    h: plain((9)",
            "    if plain(10) is 1",
            "        i: plain(11)",
            "    return h",
        };
        prog_addfn(p, "weird", 0, 0, body, 13, 1);
        prog_addfn(p, "notuser", 0, 0, (const char*[]){"    t: 1", "    return t"}, 2, 0);
        const char *body2[] = { "    z: notuser(1)", "    return z" };
        prog_addfn(p, "caller2", 0, 0, body2, 2, 1);
        prog_gh_add(p, "plain");   /* gh member blocks plain's lhs */
        prog_finish(p);
        run_program("stress-strip", p);
    }
    {
        /* callfind edges: two calls on a line, nested calls, callee ==
         * self, unknown name, deep nesting, paren imbalance in strings */
        Prog *p = prog_new();
        prog_addfn(p, "one", (const char*[]){"a"}, 1, (const char*[]){"    return a"}, 1, 1);
        const char *body[] = {
            "    a: one(1) + one(2)",
            "    b: one(one(one(3)))",
            "    c: nosuch(4)",
            "    d: selfcaller(5)",
            "    e: one(\"x)y\")",
            "    f: one(6",
            "    g: one(7",
            "    return g",
        };
        prog_addfn(p, "selfcaller", 0, 0, body, 8, 1);
        prog_finish(p);
        run_program("stress-callfind", p);
    }
    {
        /* body_ok edges: 13-line body (too long), tab lines, quote lines,
         * '#' first, non-return tail, if-chain shapes at indent 4/8 */
        Prog *p = prog_new();
        const char *b1[14];
        for (U q = 0; q < 12; q++){
            char buf[64]; snprintf(buf, sizeof(buf), "    t%llu: %llu", (unsigned long long)q, (unsigned long long)q);
            b1[q] = strdup(buf);
        }
        b1[12] = "    return t0";
        prog_addfn(p, "toolong", 0, 0, b1, 13, 1);
        const char *b2[] = {"\tx: 1", "    return x"};
        prog_addfn(p, "tabbody", 0, 0, b2, 2, 1);
        const char *b3[] = {"    x: \"q\"", "    return x"};
        prog_addfn(p, "quotebody", 0, 0, b3, 2, 1);
        const char *b4[] = {"    # c", "    return 1"};
        prog_addfn(p, "hashbody", 0, 0, b4, 2, 1);
        const char *b5[] = {"    if a is 1", "        x: 2", "    return x"};
        prog_addfn(p, "ifchain", (const char*[]){"a"}, 1, b5, 3, 1);
        const char *cs[] = {
            "    r1: toolong(1)", "    r2: tabbody(2)", "    r3: quotebody(3)",
            "    r4: hashbody(4)", "    r5: ifchain(5)", "    return r1",
        };
        prog_addfn(p, "bocaller", 0, 0, cs, 6, 1);
        /* S28R-1: pin the 12/13-line body_ok boundary from BOTH sides with
         * callees whose call sites satisfy every other eligibility gate
         * (1 param, 1 imm arg, task_user, unique call).  "toolong2" has
         * exactly 13 body lines: certified blobs must reject it (nl > 12),
         * a mutant accepting 13-line bodies fires here and diverges.
         * "justfits" has exactly 12 lines and must fire on both sides. */
        const char *b6[13];
        b6[0] = "    t0: a";
        for (U q = 1; q < 12; q++){
            char buf[64]; snprintf(buf, sizeof(buf), "    t%llu: t%llu + 1",
                                   (unsigned long long)q, (unsigned long long)q - 1);
            b6[q] = strdup(buf);
        }
        b6[12] = "    return t11";
        prog_addfn(p, "toolong2", (const char*[]){"a"}, 1, b6, 13, 1);
        const char *b7[12];
        b7[0] = "    s0: a";
        for (U q = 1; q < 11; q++){
            char buf[64]; snprintf(buf, sizeof(buf), "    s%llu: s%llu + 1",
                                   (unsigned long long)q, (unsigned long long)q - 1);
            b7[q] = strdup(buf);
        }
        b7[11] = "    return s10";
        prog_addfn(p, "justfits", (const char*[]){"a"}, 1, b7, 12, 1);
        const char *cs2[] = {
            "    q1: toolong2(7)", "    q2: justfits(9)", "    return q2",
        };
        prog_addfn(p, "bo2caller", (const char*[]){"z"}, 1, cs2, 3, 1);
        prog_finish(p);
        run_program("stress-bodyok", p);
    }
}

/* ---- PRNG programs ---- */
static U rng_s = 0x12345678u;
static U rnd(U m){ rng_s = rng_s * 6364136223846793005ULL + 1442695040888963407ULL; return (rng_s >> 33) % m; }
static void run_prng(int count){
    for (int c = 0; c < count; c++){
        Prog *p = prog_new();
        U nf = 3 + rnd(12);
        char nmbuf[32][64];
        for (U fi = 0; fi < nf; fi++){
            snprintf(nmbuf[fi], 64, "fn%llu%s", (unsigned long long)fi, (fi % 5 == 0) ? "zzln" : "");
            const char *params[4]; U np = rnd(3);
            char pbuf[4][32];
            for (U q = 0; q < np; q++){ snprintf(pbuf[q], 32, "p%llu", (unsigned long long)q); params[q] = pbuf[q]; }
            const char *body[24]; U bn4 = 0;
            U nlines = 1 + rnd(12);
            for (U q = 0; q < nlines; q++){
                char *buf = (char*)malloc(128);
                U kind = rnd(8);
                const char *pad = (rnd(4) == 0) ? "  " : " ";
                if (kind == 0 && q == nlines - 1)
                    snprintf(buf, 128, "    return %sp%llu", (rnd(2) ? " " : ""), (unsigned long long)rnd(np ? np : 1));
                else if (kind <= 2){
                    U callee = rnd(nf);
                    snprintf(buf, 128, "    v%llu%sfn%llu(p%llu, %llu)", (unsigned long long)q, pad,
                             (unsigned long long)callee, (unsigned long long)rnd(np ? np : 1), (unsigned long long)rnd(100));
                }
                else if (kind == 3)
                    snprintf(buf, 128, "    v%llu%sfn%llu(fn%llu(1), 2)", (unsigned long long)q, pad,
                             (unsigned long long)rnd(nf), (unsigned long long)rnd(nf));
                else if (kind == 4)
                    snprintf(buf, 128, "    if p%llu is %llu", (unsigned long long)rnd(np ? np : 1), (unsigned long long)rnd(3));
                else if (kind == 5)
                    snprintf(buf, 128, "        w%llu: fn%llu(3)", (unsigned long long)q, (unsigned long long)rnd(nf));
                else if (kind == 6)
                    snprintf(buf, 128, "    v%llu: \"fn%llu(9)\"", (unsigned long long)q, (unsigned long long)rnd(nf));
                else
                    snprintf(buf, 128, "    v%llu: p%llu + %llu", (unsigned long long)q, (unsigned long long)rnd(np ? np : 1), (unsigned long long)rnd(50));
                body[bn4++] = buf;
            }
            /* last line: often a return so body_ok can pass */
            if (rnd(2)){
                char *buf = (char*)malloc(128);
                snprintf(buf, 128, "    return v%llu", (unsigned long long)(nlines ? nlines - 1 : 0));
                body[bn4++] = buf;
            }
            prog_addfn(p, nmbuf[fi], params, np, body, bn4, rnd(5) ? 1 : 0);
        }
        for (U q = 0; q < 3 + rnd(6); q++){
            char g[32]; snprintf(g, 32, "g%llu", (unsigned long long)q);
            prog_gh_add(p, g);
        }
        if (rnd(3) == 0) prog_gh_add(p, "fn0");
        prog_finish(p);
        char tag[32]; snprintf(tag, 32, "prng-%d", c);
        run_program(tag, p);
    }
}

int main(int argc, char **argv){
    if (argc < 3){ fprintf(stderr, "usage: %s old.so new.so [file.sov...]\n", argv[0]); return 2; }
    prof_on = getenv("S28_PROF") != 0;
    void *ho = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    void *hn = dlopen(argv[2], RTLD_NOW | RTLD_LOCAL);
    if (!ho || !hn){ fprintf(stderr, "dlopen failed: %s\n", dlerror()); return 2; }
    eo = (ENTRY)dlsym(ho, "old_inl2_scan");
    en = (ENTRY)dlsym(hn, "_sov_inl2_scan");
    if (!eo || !en){ fprintf(stderr, "dlsym failed: %p %p\n", (void*)eo, (void*)en); return 2; }
    run_stress();
    run_prng(60);
    for (int ai = 3; ai < argc; ai++){
        char tag[256];
        snprintf(tag, sizeof(tag), "file:%s", argv[ai]);
        run_file(tag, argv[ai]);
    }
    printf("cases=%d failures=%d\n", ncase, nfail);
    if (prof_on){
        fprintf(stderr, "S28_PROF top blob(old) calls:\n");
        for (int q = 0; q < ntop; q++){
            fprintf(stderr, "  %8.4fs ci=%-5llu nl=%-6llu %s\n",
                    topcalls[q].t, topcalls[q].ci, topcalls[q].nl, topcalls[q].tag);
        }
    }
    return nfail ? 1 : 0;
}
