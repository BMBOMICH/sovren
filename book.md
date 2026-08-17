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

## Running another machine's program here

Sovren can build for six machines, and it can also run what it built. Two of the
libraries are processors, written in Sovren:

```
use x86     a 64-bit Intel or AMD processor
use arm     a 64-bit ARM processor, the kind in a phone
```

`x86` is a general-purpose 64-bit Intel and AMD processor, not just enough of one to
run what Sovren emits. It runs all three shapes of file — a Linux ELF, a Windows
`.exe`, and a Mac binary — and works out which by looking at the first bytes.

It runs programs from other compilers too. A C program built with gcc and linked
statically against the C library runs and prints exactly what it prints natively,
including `malloc`, `qsort` with a callback, `printf`, and the string functions,
which glibc writes with vector instructions.

```
use x86
main:
    m: x86_new()
    x86_load(m, "app.exe")
    x86_run(m)
    print x86_out(m)
```

Two ready-made tools use it:

```
./sovren windows/run.sov -o run     then    ./run app.exe
./sovren mac/run.sov -o run         then    ./run app
```

Both are strict on purpose. A Windows program that reaches a raw `syscall` is stopped,
because real Windows has no Linux kernel behind it — Wine lets that through and the
program then dies on a real machine. A Mac program using a Linux syscall number is
stopped for the same reason. Each exits `3` when it refuses.

`x86_why` says why it stopped and `x86_reason` says it in words. `x86_code` is the
exit code the program asked for, and `x86_err` is anything it wrote to the error
channel.

What it covers: every whole-number instruction, in all four widths; the flags,
including parity and direction; the full-width multiply and divide, where the
answer is twice as wide as what went in; the string instructions with `rep`; the
bit instructions; the locked ones; the vector registers; and decimal arithmetic.

Decimals are worth a word. Sovren has no decimal numbers, so add, take away,
multiply, divide, compare and square root are all done with whole numbers, the
way the hardware does it underneath: a number is a sign, an exponent and a
fraction, and the work is in lining those up and rounding correctly. Rounding is
to nearest, ties to even, which is what makes a sum give the same answer twice.
Infinity, not-a-number and the very small numbers below the normal range are all
handled. The answers are the same bit patterns a real processor gives — checked
against one, several thousand times over.

It also covers the old stack-based maths unit, the one a compiler reaches for when
a program asks for `long double`. That is a stack of eight registers rather than
sixteen named ones, and it is checked the same way: a C program using `long double`
prints exactly what it prints natively.

Every instruction was checked against a real processor, one at a time, by feeding
both the same bytes and comparing all sixteen registers and every flag afterwards.
`check/x86ins.sov` keeps that check in the suite.

---

## A window

`win` opens a real window and draws in it. On Linux it speaks to the X server
directly, over a socket, so there is no toolkit underneath and nothing to install.

```
use win
main:
    w: win_open(400, 300, "Hello")
    win_fill(w, 0, 0, 400, 300, WIN_WHITE)
    win_fill(w, 50, 50, 100, 80, WIN_RED)
    win_text(w, 30, 30, "Hello from Sovren", WIN_BLACK)
    win_flush(w)
    as long as win_wait(w) is not WIN_CLOSE
        win_flush(w)
```

`win_open` hands back nought when there is no screen, so a program can say so
politely instead of falling over. Nothing appears until `win_flush`.

That one is Linux. On Windows the drawing is done by `user32` and `gdi32`, which
is a different machine entirely, and `winwin` does that. To write a program once
for both, use `window`, which picks whichever works:

```
use window
main:
    w: window_open(400, 300, "Hello")
    if w is 0
        print "no screen here"
        stop
    print window_which(w)
    as long as window_next(w) is 1
        window_fill(w, 0, 0, 400, 300, WHITE)
        window_text(w, 20, 30, "Hello from Sovren", BLACK)
        window_show(w)
    window_shut(w)
```

`window_which` says `X11` or `Windows`. Everything else — `window_fill`,
`window_box`, `window_line`, `window_circle`, `window_text` — is the same on
both.

A Windows program reaches `user32` and `gdi32` through `winapi`, which uses the
two names every Sovren Windows program carries: `LoadLibraryA` opens any library
on the machine and `GetProcAddress` finds a function inside it. So a program can
call anything Windows offers without it being decided at build time:

```
use winapi
main:
    u: dll_open("user32.dll")
    f: dll_find(u, "MessageBoxA")
    wincall4(f, 0, "hello", "Sovren", 0)
```

There are `win_fill`, `win_box`, `win_line`, `win_circle`, `win_dot` and
`win_text`, and colours are made with `win_rgb r g b` or taken from `WIN_RED`,
`WIN_BLUE` and the rest. `win_wait` hands back `WIN_KEY`, `WIN_CLICK`, `WIN_MOVE`,
`WIN_DRAW` or `WIN_CLOSE`, and `win_key`, `win_x` and `win_y` say what happened.

---

## Buttons and boxes to type in

`ui` puts the usual things in a window and tells you which one the person used.

```
use ui
main:
    u: ui_new(300, 200, "Sign in")
    ui_label(u, 20, 16, "Your name:")
    name: ui_entry(u, 20, 40, 260, 28)
    go: ui_button(u, 20, 90, 100, 32, "Go")
    as long as ui_next(u) is not UI_CLOSED
        if ui_clicked(u, go) is 1
            print ui_text(u, name)
```

`ui_next` deals with everything the person did, redraws, and says what happened.
There are labels, buttons, boxes to type in, tick boxes and plain boxes.

---

## A game

`game` is a window with a loop that keeps proper time, and things that move.

```
use game
main:
    g: game_new(400, 300, "Bounce")
    game_speed(g, 60)
    ball: sprite_new(60, 60, 20, 20, WIN_RED)
    sprite_speed(ball, 4, 3)
    as long as game_running(g) is 1
        game_step(g)
        sprite_move(ball)
        sprite_bounce(g, ball)
        game_clear(g, WIN_BLACK)
        sprite_draw(g, ball)
        game_show(g)
```

`game_step` takes in everything the person did and then waits just long enough
that the loop runs at the speed you asked for. Without that a game runs at a
different speed on every machine. `game_held` says whether a key is down right
now, which is what a game wants, rather than whether it was just pressed.

A sprite knows where it is, where it is going and how big it is.
`sprite_bounce` turns it round at the edge, `sprite_clamp` keeps it inside, and
`sprite_hit` says whether two are touching.

---

## Bots

`telegram` and `discord` talk to those two services.

```
use telegram
main:
    t: tg_new("123456:your-token-from-BotFather")
    as long as 1 is 1
        n: tg_poll(t)
        i: 0
        as long as i < n
            tg_say(t, tg_chat(t, i), tg_text(t, i))
            i: i + 1
```

Both services insist on the locked kind of connection, which needs a great deal
of cryptography Sovren does not have yet. Rather than pretend, these libraries
hand the locking to a helper the machine already has, and `tg_ready` and
`dc_ready` say plainly whether one is there. Everything else — building the
request, reading the reply, pulling the message out — is Sovren.

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
