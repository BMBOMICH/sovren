# Sovren surface forms added 2026-09-24 (syntax compaction)

Four forms. Each one is pure surface sugar: the compiler expands it back into
the plain form before any other pass sees the text, so the two spellings are
the same program. Everything already in the tree still compiles unchanged.

## 1. `use:` — many libraries, one directive

```
use:                     use num
    num          ->      use string
    string
```

## 2. `emit:` / `emit4:` / `emit8:` — a byte run, one directive

```
    emit:                emit(205)
        205      ->      emit(128)
        128
```

Same for `emit4:` and `emit8:`. This is what the codegen tables in
`library/cx86.sov` and the compiler sources now use.

## 3. `<value>:` — a group of names with the same constant

```
0:                       src_base: 0
    src_base     ->      had_err: 0
    had_err              ex_depth: 0
    ex_depth

blank:                   src_name: blank
    src_name     ->      kn: blank
    kn
```

The value may be an integer (`0`, `-1`) or the word `blank`. The header is only
read as a group when the header value is exactly a number or `blank`, so a
zero-argument task definition such as `emit_walk:` is never mistaken for one.

## 4. `name = expr` — assignment without the colon

```
    x = 7                x: 7
    y = x + 1     ->     y: x + 1
```

The head must be a bare name, so `print "a = b"` and `if x is 1` are untouched.
`=` appears nowhere else in the language, so it was free to take.

## Rules

* Children are indented one level under the header (4 spaces).
* A block ends at the first line that is not indented deeper than its header.
* Blank lines and `#` comment lines inside a block are kept as-is.
* `use:` children must be single words; `<value>:` children must be bare names.
* `emit:` children are whole expressions; one byte-run entry per line.
* No nested block headers, no inline "header plus values on the same line".

## `<value>:` needs two or more names

A value group exists to share one value across several names. With a single
name there is nothing to share, so the form buys nothing and only hides the
definition - write it out directly instead:

```
blank:            e: blank        <- one name: not a group, write it directly
    e

0:                0:              <- two names: this is what the form is for
    a         ->  a: 0
    b             b: 0
```

A `<value>:` header followed by fewer than two bare names is an error:

```
Error: a value group needs two or more names; write one name directly
```

`use:`, `emit:` and `name = expr` are unchanged - they work for any count,
including one.

## What was deliberately not added

`if =:` (an `if` whose body is a block of `name = value` pairs) is not in the
language. `=` already means assignment; giving it a second meaning inside a
condition makes the reader decide which one applies from context, and the
`if x is 1` idiom already covers the readable case. A `case` / `match`
construct would remove more duplication without that ambiguity.

## How it is wired

| where | what |
|---|---|
| `library/ccore.sov` | `u_sugar` and its helpers: the whole desugar, one definition, shared by all six compiler sources |
| each `compilers/*/compiler*.sov` main | `src: u_sugar(src)` before the `use` scan (so `use:` blocks load libraries), `all: u_sugar(all)` on the assembled program before codegen |
| `library/cx86.sov`, `library/carm.sov` | `chunk: u_sugar(chunk)` when a library file is read, so libraries may use the forms too |

The pass is line based and allocates one output buffer; it runs on every
compile, including the compiler's own self-build.

## Proof

* `./sovren bootstrap.sov -o /tmp/boot && /tmp/boot` ends `bootstrap clean`:
  the seed compiler reproduces itself three times byte for byte, and all ten
  committed binaries rebuild byte-identically from source.
* The migration of the tree into the new forms was done together with a
  pure-Python model of `u_sugar`; for every file the model's expansion is
  compared against the pre-migration text and must be identical. 688 files, no
  mismatches. The same compiler binary, run over the pre-migration tree and the
  migrated tree, produced byte-identical compilers.
* `tests/` programs and a demo file using all four forms compile to the same
  bytes as their plain-form twins and print the same output.

## Migration record

| item | count |
|---|---|
| comment lines removed | 15,927 |
| `emit(x)` lines collapsed into `emit:` blocks | 7,651 (1,213 blocks) |
| `use x` lines collapsed into `use:` blocks | 586 (148 blocks) |
| constant groups folded into `<value>:` blocks | 80 |
| source lines, before -> after | 189,751 -> 175,633 (-14,118) |

Comment removal keeps the two comment lines that carry meaning for the unsafe
gate: `# unsafe-module` and `# unsafe`.
