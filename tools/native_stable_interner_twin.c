/* Relocation-free twin translation unit for the C.4/C.5 stable interner.
 * The harness baseline (malloc/memset/memcmp/strlen) is excluded so the
 * extracted .text has no undefined symbols and no relocations. */
#define NO_BASELINE
#include "native_stable_interner.c"
