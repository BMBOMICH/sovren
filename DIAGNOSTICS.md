# Diagnostics — error and warning messages

## Current state, measured

Compiling a 7-line program with one undefined name produces:

```
Compiling
/tmp/w/e1.sov
note: compiler sees raw memory/io sites without unsafe markers; library/sbuf.sov covers checked buffers (count follows)
7
Error: no such name
undefined_thing
/tmp/w/e1.sov
4
Warning: locals
main
2
1
```

And a syntax error:

```
Error: a statement inside a task must be indented
task main
3
```

### What is wrong, concretely

1. **`err_where()` is a stub.** Its entire body is `had_err: 1` then `return`
   (`library/inc/inc03.sov:60`). It attaches no location at all. **18 call
   sites** depend on it: 14 in `library/cx86.sov`, 3 in `library/inc/inc03.sov`,
   1 in `library/inc/inc01.sov`.
2. **No column.** Only a line number is printed, and it is printed bare, with no
   `-->` and no alignment.
3. **No source line echo, no caret.** The reader has to open the file and count
   lines to find the problem.
4. **No error codes.** Messages are free text, so they cannot be documented,
   searched, suppressed, or made machine-readable.
5. **No `help:` / `note:` hints on the main path.** A `did you mean` mechanism
   exists (it fires on some paths) but it is not universal and not labelled.
6. **No colour, no bold, no grouping.** Multiple errors are not grouped by file
   or ordered by position.
7. **Noisy preamble.** `Compiling`, the filename, and the `note:` line are
   printed before anything useful. The bare `7` on its own line is unexplained.
8. **The warning block is unlabelled.** `Warning: locals / main / 2 / 1` gives
   four unlabelled lines and no explanation of what to do.
9. **No `--error-format=json`** for editor and CI integration.
10. **No warning categories or `-W` flags.** Warnings cannot be turned into
    errors, cannot be individually disabled, and have no stability guarantee.

## What "best in class" looks like

The reference implementation is rustc, and the second-best is Elm. The target
format:

```
error[E0425]: cannot find value `undefined_thing` in this scope
  --> src/main.sov:4:9
   |
 4 |     x: undefined_thing + 1
   |         ^^^^^^^^^^^^^^^ not found in this scope
   |
   = help: a task with this name is not in scope
   = note: tasks in scope: main, helper, parse

warning[W0001]: value `x` is never used
  --> src/main.sov:4:5
   |
 4 |     x: undefined_thing + 1
   |         ^
   |
   = note: prefix with `_` to silence this warning
```

Properties that matter, in order: a stable code, a file:line:col, the source
line, a caret that spans exactly the offending token, a `help:` line that says
what to do, colour, grouping, and machine-readable output.

## Plan

### Phase 1 — fix the stub (cheapest, highest value)

Make `err_where()` actually print `file:line:col` and the source line. It needs
three things it does not currently have: the current column, the source buffer,
and the current line's text. All three are already in scope at the call sites
(`src_name`, `src_base`, the spliced source), so this is plumbing, not new
analysis.

**This one change fixes 18 error sites at once.**

### Phase 2 — column tracking

The lexer is line-based (`lines_of`, `cut`, `look`). Add a column to the token
position and thread it through `err_where`. Without a column the caret cannot be
placed.

### Phase 3 — stable error codes

Introduce a table: code -> format string -> default severity -> help text. Every
`print "Error: ..."` site becomes `err(E0425, ...)`. Freeze the codes once
published; never renumber.

Suggested starting set (E = error, W = warning):

| code | meaning |
|---|---|
| E0001 | no such name |
| E0002 | no such task |
| E0003 | a statement inside a task must be indented |
| E0004 | do not know these words |
| E0005 | unterminated text |
| E0006 | include not found |
| E0007 | wrong number of values |
| E0008 | duplicate name |
| W0001 | value never used |
| W0002 | empty block |
| W0003 | unreachable code |

### Phase 4 — `help:` and `note:` lines

Most sovren errors are recoverable and know the fix. "no such name" already
computes candidate names for `did you mean`; promote that to a labelled
`= help:` line and add `= note: tasks in scope: ...`.

### Phase 5 — colour and grouping

ANSI colour gated on `isatty` and `NO_COLOR`. Group by file, sort by line, print
a summary line (`3 errors, 2 warnings`).

### Phase 6 — machine-readable output

`--error-format=json` emitting one object per diagnostic with code, severity,
file, line, col, span, message, help. This is what makes editor integration and
CI possible at all.

### Phase 7 — warning control

`-W<code>`, `-Wno-<code>`, `-Werror`, `-Werror=<code>`, and a documented
stability policy (warnings may be added in a minor release, never removed
without a deprecation cycle).

## Success criteria

- Every diagnostic has a code, a `file:line:col`, a source line and a caret.
- Every recoverable error has a `help:` line that states the fix.
- Zero unlabelled bare numbers in compiler output.
- `--error-format=json` round-trips through a real editor.
- The full suite's expected output is unchanged apart from formatting.
