/* bench.c — the C side of the loop workload: sum of the squares
 * 1..n, the same tight loop tests/bench.sov runs. built in the CI
 * step with -O0 and -O2 and timed against the Sovren build.
 */
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv){
    long long n = 2900000;
    if (argc > 1) n = atoll(argv[1]);
    long long s = 0;
    for (long long i = 1; i <= n; i++) s += i * i;
    printf("%lld\n", s);
    return 0;
}
