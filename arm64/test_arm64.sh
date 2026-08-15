#!/bin/sh
# Compile with the Android (AArch64) back end and run on an emulated ARM64 CPU.
cd "$(dirname "$0")/.." || exit 1
SOV=./sovren
P=0; F=0
t() {
    printf '%s\n' "$2" > /tmp/sov-arm.sov
    if ! $SOV /tmp/sov-arm.sov --android -o /tmp/sov-arm.bin >/dev/null 2>&1; then
        echo "FAIL(compile) $1"; F=$((F+1)); return
    fi
    got=$(timeout 180 python3 arm64/run_arm64.py /tmp/sov-arm.bin 2>&1 | tr '\n' ' ' | sed 's/ *$//')
    if [ "$got" = "$3" ]; then echo "ok   $1"; P=$((P+1))
    else echo "FAIL $1 got=[$got] want=[$3]"; F=$((F+1)); fi
}
t number     'main:
    print 42' '42'
t math       'main:
    print 2 + 3 * 4
    print 100 / 5
    print 7 % 3' '14 20 1'
t precedence 'main:
    print 5 * 3 / 2
    print 100 / 5 * 2
    print 10 - 2 - 3' '7 40 5'
t vars       'main:
    x: 10
    print x + 20' '30'
t if         'main:
    if 5 > 3
        print 1
    if not
        print 0' '1'
t loop       'main:
    i: 0
    t: 0
    as long as i < 100
        t: t + i
        i: i + 1
    print t' '4950'
t fn         'add a b:
    return a + b
main:
    print add(40, 2)' '42'
t recursion  'fib n:
    if n < 2
        return n
    return fib(n - 1) + fib(n - 2)
main:
    print fib(20)' '6765'
t text       'main:
    print "hello arm64"' 'hello arm64'
t negatives  'main:
    print 0 - 7
    print 10 - 20' '-7 -10'
t nested     'main:
    x: 5
    if x > 1
        if x > 3
            print 99' '99'
t andor      'main:
    if 1 is 1 and 2 is 2
        print 1
    if 0 is 1 or 1 is 1
        print 2' '1 2'
t args5      'f a b c d e:
    return a + b + c + d + e
main:
    print f(1,2,3,4,5)' '15'
t globals    'M: 256
f x:
    return x % M
main:
    print f(300)' '44'
t times      'main:
    print "hi" 3 times' 'hi hi hi'
t deep       'd n:
    if n is 0
        return 0
    return d(n - 1)
main:
    print d(1000)' '0'
t locals     'main:
    a: 1
    b: 2
    c: 3
    d: 4
    e: 5
    f: 6
    g: 7
    h: 8
    print a+b+c+d+e+f+g+h' '36'
echo
echo "ARM64: $P passed, $F failed"
[ "$F" = "0" ] || exit 1
