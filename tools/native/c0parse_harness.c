/* Differential harness for the _sov_c0_parse native blob.
 * Reads a case file (see tools/native/diff_c0parse.py for the writer):
 *   CASE <src_base> <kern_mode> <need_priv> <g2_on>
 *   <escaped line>        (\n -> \\n, \t -> \\t, \r -> \\r, \\ -> \\\\)
 *   ...
 *   END
 * Runs the blob per case with marker-emitting tbl stubs and emits one JSON
 * object per case (JSONL) with every published list + need_priv + had_err +
 * prints (entries \x01-separated) + g2log (the exact /tmp/sov_g2.log bytes).
 * The blob itself is compiled with the strict generator flags; this harness
 * is ordinary C.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint64_t U;
typedef long long S;

extern U _sov_c0_parse(U lns, U tbl);

/* ---- marker-emitting stubs ---- */
static char PBUF[1 << 20];
static size_t PN = 0;
static void papp(const char *s)
{
    while (*s)
        PBUF[PN++] = *s++;
}
static void pent(void) { PBUF[PN++] = '\x01'; } /* entry separator */
static const char *MSGS[7] = {
    0,
    "Error: tab indent, use spaces",
    "Error: two with the same name",
    "Error: too many parameters (7 max)",
    "Error: duplicate top-level definition",
    "Error: a statement inside a task must be indented",
    "Error: law expects a name and a condition",
};
static U h_print(U a)
{
    pent();
    if (a >= 1 && a <= 6)
        papp(MSGS[a]);
    return 0;
}
static U h_printint(U a)
{
    pent();
    char b[64];
    snprintf(b, sizeof b, "<print-int:%lld>", (S)a);
    papp(b);
    return 0;
}
static U h_sprint(U a)
{
    pent();
    papp((const char *)(void *)a);
    return 0;
}
static U h_seterr(U a)
{
    pent();
    char b[64];
    snprintf(b, sizeof b, "<err_line:%lld>", (S)a);
    papp(b);
    return 0;
}
static U h_ew(U a)
{
    (void)a;
    pent();
    papp("<err_where>");
    return 0;
}
static U h_alloc(U n)
{
    return (U)(void *)malloc(n ? (size_t)n : 1);
}

/* ---- JSON helpers ---- */
static void jstr(FILE *o, const char *s, size_t n)
{
    fputc('"', o);
    size_t i = 0;
    while (i < n) {
        unsigned c = (unsigned char)s[i];
        if (c == '"' || c == '\\') {
            fputc('\\', o);
            fputc((int)c, o);
        } else if (c < 0x20) {
            fprintf(o, "\\u%04x", c);
        } else {
            fputc((int)c, o);
        }
        i++;
    }
    fputc('"', o);
}
static void jstrz(FILE *o, const char *s) { jstr(o, s, strlen(s)); }
#define LLEN(x) (*(U *)((x) + 8))
#define ELEM(x, i) (*(U *)((x) + 16 + (U)(i) * 8))
static void jlist_str(FILE *o, U l)
{
    fputc('[', o);
    U n = l ? LLEN(l) : 0;
    U i = 0;
    while (i < n) {
        if (i)
            fputc(',', o);
        U p = ELEM(l, i);
        jstrz(o, p ? (const char *)(void *)p : "");
        i++;
    }
    fputc(']', o);
}
static void jlist_int(FILE *o, U l)
{
    fputc('[', o);
    U n = l ? LLEN(l) : 0;
    U i = 0;
    while (i < n) {
        if (i)
            fputc(',', o);
        fprintf(o, "%lld", (S)(l ? ELEM(l, i) : 0));
        i++;
    }
    fputc(']', o);
}
static void jlist_liststr(FILE *o, U l)
{
    fputc('[', o);
    U n = l ? LLEN(l) : 0;
    U i = 0;
    while (i < n) {
        if (i)
            fputc(',', o);
        jlist_str(o, l ? ELEM(l, i) : 0);
        i++;
    }
    fputc(']', o);
}
static void jlist_listint(FILE *o, U l)
{
    fputc('[', o);
    U n = l ? LLEN(l) : 0;
    U i = 0;
    while (i < n) {
        if (i)
            fputc(',', o);
        jlist_int(o, l ? ELEM(l, i) : 0);
        i++;
    }
    fputc(']', o);
}

/* ---- line unescape ---- */
static char *unescape(const char *src, size_t n)
{
    char *d = (char *)malloc(n + 1);
    size_t w = 0, i = 0;
    while (i < n) {
        char c = src[i];
        if (c == '\\' && i + 1 < n) {
            char e = src[i + 1];
            if (e == 'n')
                d[w++] = '\n';
            else if (e == 't')
                d[w++] = '\t';
            else if (e == 'r')
                d[w++] = '\r';
            else
                d[w++] = e;
            i += 2;
        } else {
            d[w++] = c;
            i++;
        }
    }
    d[w] = 0;
    return d;
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <casefile>\n", argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "r");
    if (!f) {
        perror(argv[1]);
        return 2;
    }
    char line[65536];
    size_t cap = 256, cnt = 0;
    char **lines = (char **)malloc(cap * sizeof(char *));
    long caseno = 0;
    while (fgets(line, sizeof line, f)) {
        size_t ln = strlen(line);
        while (ln && (line[ln - 1] == '\n' || line[ln - 1] == '\r'))
            line[--ln] = 0;
        if (strncmp(line, "CASE ", 5) != 0)
            continue;
        S src_base = 0, kern = 0, npv = 0, g2 = 0;
        sscanf(line + 5, "%lld %lld %lld %lld", &src_base, &kern, &npv, &g2);
        cnt = 0;
        for (;;) {
            if (!fgets(line, sizeof line, f))
                break;
            size_t n = strlen(line);
            while (n && (line[n - 1] == '\n' || line[n - 1] == '\r'))
                line[--n] = 0;
            if (strcmp(line, "END") == 0)
                break;
            if (cnt == cap) {
                cap *= 2;
                lines = (char **)realloc(lines, cap * sizeof(char *));
            }
            lines[cnt++] = unescape(line, n);
        }
        /* lns list: [cap, len, data...] */
        char *lst = (char *)malloc(16 + (cnt + 8) * 8);
        *(U *)(void *)(lst) = cnt + 8;
        *(U *)(void *)(lst + 8) = cnt;
        size_t i2 = 0;
        while (i2 < cnt) {
            *(U *)(void *)(lst + 16 + i2 * 8) = (U)(void *)lines[i2];
            i2++;
        }
        /* tbl */
        U *tbl = (U *)(void *)calloc(32, 8);
        tbl[0] = 6;
        tbl[1] = (U)(void *)h_print;
        tbl[2] = (U)(void *)h_printint;
        tbl[3] = (U)(void *)h_sprint;
        tbl[4] = (U)(void *)h_seterr;
        tbl[5] = (U)(void *)h_ew;
        tbl[6] = (U)(void *)h_alloc;
        tbl[10] = (U)src_base;
        tbl[11] = (U)kern;
        tbl[12] = (U)npv;
        tbl[13] = 0;
        tbl[14] = (U)(void *)"";
        /* g2 FS state */
        if (g2) {
            FILE *t = fopen("/tmp/sov_glog2", "w");
            if (t)
                fclose(t);
        } else {
            remove("/tmp/sov_glog2");
        }
        remove("/tmp/sov_g2.log");
        PN = 0;
        U rv = _sov_c0_parse((U)(void *)lst, (U)(void *)tbl);
        char g2b[1 << 16];
        size_t gn = 0;
        FILE *gf = fopen("/tmp/sov_g2.log", "rb");
        if (gf) {
            gn = fread(g2b, 1, sizeof g2b, gf);
            fclose(gf);
        }
        printf("{\"case\":%ld,\"rv\":%llu,", caseno, (unsigned long long)rv);
        printf("\"names\":");
        jlist_str(stdout, tbl[20]);
        printf(",\"params\":");
        jlist_liststr(stdout, tbl[21]);
        printf(",\"bodies\":");
        jlist_liststr(stdout, tbl[22]);
        printf(",\"body_lns\":");
        jlist_listint(stdout, tbl[23]);
        printf(",\"task_lns\":");
        jlist_int(stdout, tbl[24]);
        printf(",\"task_user\":");
        jlist_int(stdout, tbl[25]);
        printf(",\"glob_names\":");
        jlist_str(stdout, tbl[26]);
        printf(",\"sglob_names\":");
        jlist_str(stdout, tbl[27]);
        printf(",\"tops\":");
        jlist_str(stdout, tbl[28]);
        printf(",\"tops_lns\":");
        jlist_int(stdout, tbl[29]);
        printf(",\"tops_users\":");
        jlist_int(stdout, tbl[30]);
        printf(",\"need_priv\":%lld,\"had_err\":%lld,\"prints\":",
               (S)tbl[12], (S)tbl[13]);
        jstr(stdout, PBUF, PN);
        printf(",\"g2log\":");
        jstr(stdout, g2b, gn);
        printf(",\"g2\":%lld}\n", g2);
        fflush(stdout);
        caseno++;
        i2 = 0;
        while (i2 < cnt) {
            free(lines[i2]);
            i2++;
        }
        free(lst);
        free(tbl);
    }
    fclose(f);
    return 0;
}
