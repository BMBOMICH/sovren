#!/bin/sh
# correct_battery.sh <compiler> : the five things a Sovren compiler must do.
#
# Run from the tree root.  Written while chasing a generation of the compiler
# that was 2.2x faster than the committed one and quietly wrong: it rejected
# string-literal arguments, and because compilers/linux/compiler.sov parses its
# own flags with _sov_str_eq(argv_i, '--flat'), every switch was ignored too.
# A speed number from a compiler that fails this battery measures nothing.
#
# POSIX sh; needs the committed Linux compiler's hello output as the reference,
# which is regenerated here on every run when REF is not set.
B="$1"
[ -x "$B" ] || { echo "not executable: $B"; exit 2; }
fail=0
REF=${REF:-/tmp/cb_ref_hello.out}
if [ ! -s "$REF" ]; then
    ./compilers/linux/compiler tests/hello.sov -o /tmp/cb_refbin >/dev/null 2>&1 \
        && /tmp/cb_refbin > "$REF" 2>&1
fi

# 1. string-literal arguments reach builtins as strings, not as names
cat > /tmp/cb1.sov <<'SOV'
main:
    print _sov_str_eq('abc', 'abc')
    print _sov_str_eq('abc', 'abd')
    print _sov_str_eq('abcdefghijklmnop', 'abcdefghijklmnop')
    print _sov_str_eq('abcdefghijklmnop', 'abcdefghijklmnoq')
SOV
if $B /tmp/cb1.sov -o /tmp/cb1 >/tmp/cb1.msg 2>&1; then
    got=$(/tmp/cb1 2>&1 | tr '\n' ' ')
    [ "$got" = "1 0 1 0 " ] || { echo "FAIL 1 literal args: got [$got] want [1 0 1 0]"; fail=1; }
else
    echo "FAIL 1 literal args: $(grep -m1 Error /tmp/cb1.msg)"; fail=1
fi

# 2. --flat writes a flat image, not an ELF
$B tests/hello.sov --flat -o /tmp/cb2 >/dev/null 2>&1 || { echo "FAIL 2 --flat compile"; fail=1; }
if [ -s /tmp/cb2 ]; then
    m=$(head -c 4 /tmp/cb2 | od -An -c | tr -d ' \n')
    [ "$m" = "177ELF" ] && { echo "FAIL 2 --flat produced an ELF (switch ignored)"; fail=1; }
fi

# 3. a source that pulls library chunks still compiles
$B tests/fast.sov -o /tmp/cb4 >/tmp/cb4.msg 2>&1 \
    || { echo "FAIL 3 tests/fast.sov: $(grep -m1 Error /tmp/cb4.msg)"; fail=1; }

# 4. hello behaves exactly as the committed reference does
if $B tests/hello.sov -o /tmp/cb5 >/dev/null 2>&1; then
    /tmp/cb5 > /tmp/cb5.out 2>&1
    cmp -s /tmp/cb5.out "$REF" || { echo "FAIL 4 hello output differs from reference"; fail=1; }
else
    echo "FAIL 4 hello did not compile"; fail=1
fi

# 5. it compiles the compiler's own source with no errors
$B compilers/linux/compiler.sov -o /tmp/cb6 >/tmp/cb6.msg 2>&1 \
    || { echo "FAIL 5 self-compile: $(grep -m1 Error /tmp/cb6.msg)"; fail=1; }

[ $fail = 0 ] && echo "correctness: ALL PASS (5/5)"
exit $fail
