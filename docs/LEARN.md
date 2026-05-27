# Learn Sovereign in 30 Minutes

Sovereign compiles to native machine code.
No runtime. No garbage collector. Faster than C on modern CPUs.

---

## The simplest possible program

print "Hello, World!"

text

That is it. Same as Python. No main function. No imports. No semicolons.

---

## Variables — two styles

Explicit (recommended):
set name = "Alice" set age = 30

text

Implicit (Python-style shorthand):
name = "Alice" age = 30

text

Both work identically. Use whichever feels natural.

---

## Functions — three styles

Sovereign style:
task add(a: int, b: int) -> int { return a + b }

text

Short style (types inferred):
task add(a, b) { return a + b }

text

Python-familiar style:
def add(a, b) { return a + b }

text

All three compile to identical machine code.

---

## If statements — two styles

Sovereign style:
check x > 5 { print "big" }

text

Universal style:
if x > 5 { print "big" }

text

Single line (no braces needed):
if x > 5: print "big"

text

---

## Loops — every style supported

// Sovereign style loop i from 0 to 9 { print i }

// Range style (Python-familiar) for i in 0..10 { print i }

// While style while x < 10 { x += 1 }

// Times style loop 5 times { print "hello" }

// For-each (Python-familiar) for item in my_array { print item }

text

---

## Types are optional

These are identical:
// Explicit set x: int = 42 task square(n: int) -> int { return n \* n }

// Inferred (simpler) x = 42 task square(n) { return n \* n }

text

The compiler figures out the types automatically.

---

## The one thing Python cannot do that Sovereign can

sensitive set password = "my_secret" // password is automatically zeroed from memory when done // No Python program can guarantee this // This is what makes Sovereign the right tool for // security-critical code

text

# Learn Sovereign

## What Sovereign is

Sovereign compiles to native machine code.
Zero runtime. Zero garbage collector.
Faster than C on modern CPUs. Safer than Rust for security-critical code.

It is NOT simpler than Python for absolute beginners.
It IS simpler than every other systems language.
If you know Python, you can learn Sovereign in one hour.

---

## Run instantly without compiling

```bash
sovereign run hello.sov
Or use the interactive REPL:

Bash

sovereign repl
>>> x = 42
>>> print x
42
>>> task double(n) { return n * 2 }
>>> print double(21)
42
The familiar syntax
Every common syntax style works:

Python

# Python programmers
x = 10
def greet(name):
    print "Hello, {name}!"

greet("Alice")
JavaScript

// JavaScript programmers
let x = 10
fn greet(name) {
    print "Hello, {name}!"
}
Rust

// Rust programmers
let x = 10;
fn greet(name: string) {
    print "Hello, {name}!";
}
sovereign

// Sovereign native style
set x = 10
task greet(name: string) {
    print "Hello, {name}!"
}
---

## Python vs Sovereign — honest comparison

|                             | Python         | Sovereign     |
| --------------------------- | -------------- | ------------- |
| Learn by tonight            | ✅             | Mostly        |
| No type declarations needed | ✅             | ✅ (optional) |
| Reads like English          | ✅             | ✅            |
| Native speed                | ❌ 100x slower | ✅            |
| No runtime needed           | ❌             | ✅            |
| Memory control              | ❌             | ✅            |
| Timing attack prevention    | ❌             | ✅            |
| Compiles to 50KB binary     | ❌             | ✅            |

Python is simpler for beginners writing scripts.
Sovereign is simpler than every other systems language.
If you already know Python, you can learn Sovereign in one hour.
```
