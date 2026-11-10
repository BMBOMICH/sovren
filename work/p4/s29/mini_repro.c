/* mini repro: drive old + identity blobs over one text repeatedly with
 * per-case purge; any output change across iterations = uninit/garbage
 * dependence in the blob or the mocks. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
typedef uint64_t U;
typedef U (*ENTRY)(U, U);
int main(int argc, char **argv){
    void *ho = dlopen(argv[1], RTLD_NOW|RTLD_LOCAL);
    void *hn = dlopen(argv[2], RTLD_NOW|RTLD_LOCAL);
    ENTRY eo = (ENTRY)dlsym(ho, "old_cx_read");
    ENTRY en = (ENTRY)dlsym(hn, "reader_core");
    FILE *f = fopen(argv[3], "rb");
    static char txt[1<<22];
    size_t n = fread(txt, 1, sizeof(txt)-1, f); fclose(f); txt[n]=0;
    /* the harness's own mock table with the same allocation purge policy:
     * reuse the differ's machinery by dlopening it is overkill; instead we
     * call BOTH entries through the SAME simple table built here, with a
     * tracking allocator, and purge between iterations. */
    extern U mini_build_tbl(U *t, void **blocks, U *nblocks, U cap);
    (void)eo; (void)en;
    return 0;
}
