# Sovren book

This is how you write Sovren.

A file ends in `.sov`. Start here:

```
./sovren hello.sov -o /tmp/hello
/tmp/hello
```

`play.sov` is a file you can change. `show.sov` shows every word in one place.
`mysite.sov` makes a page.

---

## A comment

A line that starts with `#` is only for you. Sovren skips it.

```
# this does nothing
```

---

## Start here

Every program needs `main:`. The lines under it run.

```
main:
    print "hello"
```

Spaces at the start of a line matter. Lines that belong under `main:`, under `if`, or
under `as long as` must be indented. Use spaces, not tabs.

---

## A box

A name with no quotes is a box. You put a number or letters in it with `:`.

```
main:
    a: 3
    b: 7
    print a
    print b
    print a + b
```

That prints:

```
3
7
10
```

You can change a box later:

```
    x: 10
    x: x + 1
    print x
```

That prints `11`.

---

## Print

`print` writes one line.

```
    print 3
    print a + b
    print "hello"
```

Quotes mean letters. No quotes means a box.

```
    print "hello"
    x: 10
    print x
```

Print the same line more than once:

```
    print "loop" 2 times
```

That prints:

```
loop
loop
```

---

## Blank

`blank` is empty letters. Use it when a box should hold no letters yet.

```
    s: blank
    print "done"
```

---

## Math

```
    print 3 + 2
    print 7 - 1
    print 4 * 2
    print 8 / 2
    print 7 % 3
```

`*` `/` `%` happen before `+` `-`. Same-strength math goes left to right, so
`5 * 3 / 2` is `7`. Round brackets change the order:

```
    print 2 + 3 * 4
    print (2 + 3) * 4
```

That prints `14` then `20`.

Numbers are whole numbers. For decimals use `use fixed`.

---

## If

```
    if a + b > 5
        print "big"
    if not
        print "small"
```

`if not` is the other side.

`is` means the same. `is not` means not the same. You can also write `<` `>` `<=` `>=`.

```
    if a is 3
        print "yes"
    if a is not 4
        print "diff"
```

`and` and `or` join two checks. They stop early: if the left side already decides the
answer, the right side never runs.

```
    if a is 3 and b is 7
        print "both"
```

`&&` means the same as `and`, and `||` means the same as `or`. Use whichever you like.

```
    if a is 3 && b is 7
        print "both"
    if a is 9 || b is 7
        print "one of them"
```

---

## As long as

Do the lines under it again and again, as long as the check is true.

```
    i: 0
    as long as i < 3
        print i
        i: i + 1
```

That prints:

```
0
1
2
```

---

## A job

A job is a name, then the values it takes, then `:`. Give an answer back with `return`.

```
add a b:
    return a + b

main:
    print add(40, 2)
```

That prints `42`. A job can take up to seven values, and a job can call itself:

```
fib n:
    if n < 2
        return n
    return fib(n - 1) + fib(n - 2)

main:
    print fib(20)
```

That prints `6765`.

---

## Text out of a job

`print` shows a number unless it knows the value is letters. When a job builds letters
itself, say so with `as text`:

```
use mem

shout:
    p: mem_new(4)
    poke_byte(p, 0, 72)
    poke_byte(p, 1, 73)
    poke_byte(p, 2, 0)
    return as text p

main:
    print shout()
```

That prints `HI`.

---

## Stop

`stop` ends the program right there.

```
main:
    print 1
    stop
    print 2
```

That prints only `1`.

---

## Wipe

`wipe` clears letters out of memory. Use it for passwords and keys.

```
use string

main:
    s: str_copy("secret")
    wipe s
    print "gone"
```

`private` at the top of `main` asks the system not to write a crash dump.

---

## Use

`use` pulls in extra words from `library/`.

```
use math

main:
    print abs(0 - 3)
    print max(3, 8)
```

That prints `3` then `8`.

```
use file

main:
    file_write_all("out.txt", "hi")
    print file_read_all("out.txt")
```

There are over a hundred libraries. A few to start with:

| use | what it gives you |
| --- | --- |
| `math` | `abs`, `max`, `min`, `gcd` |
| `string` | join, cut, find, compare |
| `list` | a growing row of values |
| `vec` | a faster growing row, with sort |
| `dict` | look things up by name |
| `fixed` | decimal numbers |
| `file` | read and write files |
| `walk` | the names in a folder |
| `json` | read JSON |
| `sha256` | real hashing |
| `httpd` | a web server |
| `draw` | lines, boxes, circles |
| `site` | a page for a browser |

---

## A page

`use site` makes a page you open in a browser.

```
use site

main:
    site_new("My site")
    site_back("linen")
    site_color("navy")
    site_size(36)
    site_big("Hello")
    site_size(20)
    site_color("black")
    site_say("This page was made with Sovren.")
    site_go("https://example.com", "A link")
    site_save("mysite.html")
    print "wrote mysite.html"
```

Then open `mysite.html`.

---

## Other machines

```
./sovren app.sov              -o app        this machine
./sovren app.sov --windows    -o app.exe    Windows
./sovren app.sov --mac        -o app        Mac
./sovren app.sov --android    -o app        Android and Linux on ARM
./sovren app.sov --android-so -o libapp.so  an Android library
./sovren app.sov --ios        -o app        iPhone and Apple Silicon
```

`--android-so` writes a real shared library. It gives out two names, `sovren_main` and
`Java_com_sovren_Native_run`, so Java can call in with `System.loadLibrary("sovren")`.

`--ios` signs the program the way Apple needs. To put it on a real phone you sign it
again with your own Apple name.

---

## Close to the machine

These do no checking at all. They are for writing an operating system.

```
poke_raw8 addr i v     write one byte anywhere
peek_raw8 addr i       read one byte anywhere
poke_raw64 addr i v    write eight bytes
peek_raw64 addr i      read eight bytes
port_out8 p v          send a byte to a port
port_in8 p             read a byte from a port
cli / sti              turn interrupts off / on
hlt                    wait for the next interrupt
```

`--bare` builds with no runtime and no syscalls, which is what a kernel needs.

---

## Errors

If a line is wrong, Sovren prints `Error:`, the line, and the line number. It does not
write a program.

These are all errors:

- two jobs with the same name
- a name that was never set
- a tab at the start of a line
- letters with no closing quote
- calling a job with the wrong number of values
- a line, or a sum, that is far too long

If a job is never used, or a job is empty, Sovren still writes the program and prints
`Warning:`.

---

## A full file

```
# my first file

add a b:
    return a + b

main:
    a: 3
    b: 7
    print add(a, b)
    if a + b > 5
        print "big"
    if not
        print "small"
    i: 0
    as long as i < 3
        print i
        i: i + 1
    print "loop" 2 times
```

Save it as `mine.sov`, then:

```
./sovren mine.sov -o /tmp/mine
/tmp/mine
```
