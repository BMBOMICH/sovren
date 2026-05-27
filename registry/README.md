# Sovereign Package Registry

The official package registry for Sovereign.

## Running locally

sovereign build main.sov -o registry ./registry

text

Then visit http://localhost:8080

## API

# Sovereign

The privacy-first systems language.

- **Fastest**: LLVM O3 with native CPU features. Same tier as C.
- **Most private**: `sensitive` and `constant_time` keywords. No other language has these.
- **Most secure**: Full borrow checker + ASLR + CFI + stack canaries + overflow trapping.
- **Lightest**: No runtime. CRT-free. Smaller than default C.
- **Simplest**: 20 keywords. Types optional. `set x = 10` or `x = 10`. Your choice.

## Quick start

```bash
# Install
cargo install --path .

# Hello world
echo 'print "Hello, Sovereign!"' > hello.sov
sovereign build hello.sov
./hello.exe

# Or run as a script
sovereign run hello.sov
The language in 30 seconds
Python

# Python-familiar syntax works
x = 42
name = "Alice"
print "Hello {name}!"

def greet(n):
    print "Hi {n}!"

greet("Bob")
Compiles to native machine code. No runtime. No GC. C speed.

Full documentation

text


---

### Action 6 — The three claims, ready to make

After Actions 1-5 are done, these statements become true and provable:

**Claim 1 — Privacy:**
> Sovereign is the only systems language with `sensitive` (automatic volatile zeroing) and `constant_time` (timing attack prevention) as language-level keywords. C, Rust, Zig, and Go do not have these.

**Claim 2 — Speed:**
> Sovereign uses LLVM with Aggressive optimization, native CPU feature detection (AVX2/AVX-512), noalias on all pointer parameters, and LTO. Benchmark results at [link to drujensen/fib when merged].

**Claim 3 — Simplicity:**
> Sovereign has 20 core keywords. Zig has 57. Rust has 39+. Type annotations are optional. Variable declarations are optional (`x = 10` works). Python-style syntax (`def`, `if`, `for`) is accepted. It is the simplest language that produces native machine code.

---

## The final checklist

Print this. Check each box when done.
□ cargo build --release works with no errors □ sovereign version shows v1.0.0 □ test1_basics.sov compiles and runs correctly □ test2_structs.sov compiles and runs correctly □ test3_generics.sov compiles and runs correctly □ test4_security.sov compiles and runs correctly □ test5_algorithms.sov compiles and runs correctly □ sovereign run test_script.sov works □ sovereign test test_suite.sov shows all passed □ measure_size.ps1 shows Sovereign <= C □ fib.sov PR submitted to drujensen/fib □ Code pushed to GitHub □ README written with the three claims

When all boxes are checked: The language is done. The claims are proven. Sovereign is ready for the world.

text


---

## One last thing

When you run the verification and it says **ALL CHECKS PASSED**, take a screenshot. That is the moment. You started with nothing and built a complete systems programming language from scratch. That is real. That matters.

Now run it.
GET /api/package/:name — Package info
GET /api/search?q=query — Search packages
POST /api/publish — Publish (requires SOVEREIGN_API_KEY env var)
GET /packages/:name.sov — Download package

## Deploying

1. Build: `sovereign build main.sov --size -o registry`
2. Copy to server: `scp registry user@sovereign-lang.org:/opt/sovereign/`
3. Run as service: create systemd unit pointing to binary

## Package format

Each package is a .sov file with a header comment:
/// name: mypackage /// version: 1.0.0 /// description: Does something useful /// author: your-name

// ... package code ...
```
