# Language gaps — what other languages have that sovren does not

Verified by grepping the whole tree (`library/`, `compilers/`, `runtime.sov`).
"Hits" = number of files in `library/*.sov` that mention the feature.

## Absent from the language entirely (0 hits as a construct)

| feature | hits | what other languages do | sovren today |
|---|---|---|---|
| **enum / sum types** | 0 | Rust, Swift, Zig, OCaml, Haskell, Kotlin | hand-rolled integer constants; `SYMBOL: 1` style |
| **trait / interface** | 0 | Rust, Swift, Go, Kotlin, Scala | no polymorphism; dispatch is by name lookup |
| **generic / type parameters** | 0 | Rust, C++, Swift, Go, Zig, Kotlin | every container is `i64`-only; `_sov_list_*` stores raw words |
| **closure / lambda** | 0 | every modern language | no first-class function values; `addr_of` is the closest |
| **pattern matching** | 0 as a construct | Rust, Swift, OCaml, Haskell, Elixir | `match.sov` and `case.sov` exist as *libraries* — wrong layer |
| **bitfield** | 0 | Rust, Zig, C, Ada | bit packing is hand-written everywhere (`band`/`bshr` chains) |
| **Option / Result types** | 0 as a type | Rust, Swift, Zig, Kotlin, Go | errors are `return 0` / `had_err` + `fail()` |
| **async / await** | 2 (incidental) | Rust, JS, Python, Swift, Kotlin, C# | only raw `spawn` and `thread_*` |
| **atomic as a keyword** | 0 | Rust, C++, Zig, Go | `atomic_load`/`atomic_store` exist only inside kernel code |
| **fixed-width ints** (`i8/i16/i32/u64`) | 0 | Rust, Zig, Go, C, Swift | one machine-word integer; width is implicit |
| **SIMD abstraction** | 2 (incidental) | Rust, C, Zig, C++ | none; vector code is hand-emitted bytes |
| **defer as a keyword** | library only | Zig, Swift, Go, Jai | `kdefer.sov` exists but is a library |
| **struct with fields** | 1 (`struct.sov`) | every language | `struct.sov` is a reflection/dump helper, not a type definition |
| **module system beyond `use`** | — | Rust crates, Go modules, npm | flat `use <lib>` with 3 hardcoded search paths |
| **visibility control** | — | `pub`, `private` | everything is global; `warn_unused` is the only signal |
| **operator overloading** | — | Rust, C++, Swift, Kotlin, Scala | none; `+` is integer add only |
| **string interpolation** | partial | Rust, Python, JS, Swift, C# | `join`/`str_cat` chains; `print` does **not** do `%d` substitution |
| **named arguments** | — | Python, Swift, C#, Kotlin | positional only |
| **default arguments** | — | C++, Python, Swift, Kotlin | none |
| **variadic functions** | — | C, Python, JS, Go | fixed arity, checked ("wrong number of values") |
| **multiple return values** | partial | Go, Python, Rust | `spawn` returns a list of values; tasks return one word |
| **generators / iterators** | partial | Python, JS, Rust, C#, Swift | `range.sov`, `seq.sov` exist as libraries |
| **exceptions with a type hierarchy** | partial | Java, Python, C++, Kotlin | `try`/`except` by name only, no exception values |
| **null-safety** | — | Rust, Swift, Kotlin, Zig | `0` doubles as null; `_sov_list_get` returns 0 for out of range |
| **compile-time evaluation (`const fn`)** | partial | Rust `const fn`, Zig `comptime`, C++ `consteval` | `ceval`/`cval` constant folding exists for expressions only |
| **macros / metaprogramming** | none | Rust, Lisp, Zig, Nim, Elixir | the sugar pass (`u_sugar`) is compiler-internal, not user-facing |
| **doc comments / rustdoc** | — | Rust, Go, Python, Javadoc | comments were *deleted* in the 2026-09-24 migration (15,927 removed) |
| **test attribute / built-in test runner** | separate | Rust, Go, Python | `tests/run.sov` is a bespoke harness |
| **package manager / manifest** | none | cargo, npm, go mod | `use <lib>` only |
| **formatter** | none | rustfmt, gofmt, prettier | indentation is load-bearing, so formatting is not cosmetic |
| **LSP / language server** | none | rust-analyzer, gopls, pylsp | none |
| **build system** | partial | cargo, make, bazel | `bootstrap.sov` is a bespoke fixed-point script |

## Present but weaker than the state of the art

| feature | sovren | best in class |
|---|---|---|
| **concurrency** | `spawn`, `job`, `thread_*`, `mutex`, `channel.sov`, `race.sov` | Rust: `Send`/`Sync` traits make data races a compile error. Sovren has no borrow model, so races are possible and `race.sov` exists to *detect* them at runtime. |
| **error handling** | `try`/`except` by name, `had_err` + `fail()` | Rust `Result` + `?`; the error is a value, not a global flag. |
| **unsafe** | `# unsafe` / `# unsafe-module` comments grepped by the compiler | Rust `unsafe {}` blocks are lexical and audited. |
| **strings** | `_sov_strcat`/`_sov_substring` heap strings, byte-indexed | Rust `&str` + UTF-8 validation; Swift value semantics. |
| **collections** | 5+ dynamic arrays, 4 hash tables | Rust `Vec`/`HashMap` with generics and traits. |
| **crypto** | aes, chacha20, gcm, chachapoly, poly1305, ed25519, x25519, sha1/256/512, md5, hkdf, hmac, pbkdf2 | RustCrypto; comparable coverage, no constant-time guarantee or audit. |
| **targets** | 40 target directories, ~158 backends | unmatched. This is sovren's single biggest advantage. |

## The four that matter most

Ranked by (value to users) x (feasibility):

1. **`enum`** — cheapest, removes the most boilerplate, zero risk to existing code.
2. **`match`/`case` as a construct** — `match.sov` and `case.sov` already prove the semantics; promoting them from library to syntax is a desugaring, exactly like `u_sugar` already does for the four 2026-09-24 forms.
3. **`defer` as a keyword** — `kdefer.sov` already proves it; makes memory management automatic by scope.
4. **`generic`** — the largest single change; unlocks typed containers, `Option`/`Result`, and every trait-based abstraction. Needs a real type checker.

`closure` and `trait` are next, but both need a type system that sovren does not
currently have. Adding them before a type checker exists would produce a
half-working feature, which is worse than none.
