/* Native list_find: linear scan with pointer + string equality.
 * 1:1 mirror of the compiler task list_find (compilers/linux/compiler.sov):
 * lst == 0 -> -1; the first i where lst[i] == name (pointer equality)
 * or str_eq(lst[i], name) wins; -1 when absent.  str_eq null rules per
 * runtime.sov: both-null -> 1 (unreachable here: the pointer case returns
 * first), one-null -> 0, else byte equality up to and including the first
 * shared NUL.  Pure leaf: no calls, no globals, no relocations.
 * Sovren integer comparisons are SIGNED (n and i are long long). */
typedef unsigned long U;
typedef long long S;

S emit_nt_list_find(U lst, U name){
    if (lst == 0) return -1;
    S n = *(S*)(lst + 8);
    for (S i = 0; i < n; i++){
        U s = *(U*)(lst + 16 + (U)i * 8);
        if (s == name) return i;
        if (s != 0 && name != 0){
            const unsigned char *a = (const unsigned char*)(void*)s;
            const unsigned char *b = (const unsigned char*)(void*)name;
            while (*a != 0 && *a == *b){ a++; b++; }
            if (*a == *b) return i; /* loop exited: both NUL or differ */
        }
    }
    return -1;
}
