#!/usr/bin/env python3
"""Rewrite strip(cut(E, A, B)) -> scut(E, A, B) everywhere in the compiler
sources; the special shape strip(cut(ID, A, length(ID))) with a bare
identifier ID becomes scutr(ID, A) so the extra length() call disappears.

Semantics guard: scut == strip . cut exactly (ccore.sov header comment);
scutr == strip(cut(E, A, length(E))) because a bare-identifier read has no
side effects, so evaluating E once instead of twice is unobservable.

Skips matches inside string literals and after an unquoted '#'.
"""
import re
import sys
from pathlib import Path

FILES = [
    "compilers/linux/compiler.sov",
    "compilers/linux/syntax.sov",
    "compilers/linux/statements.sov",
    "compilers/shared/ccore.sov",
    "compilers/shared/carm.sov",
    "compilers/shared/cx86.sov",
    *[f"compilers/shared/cx86_p{i}.sov" for i in range(1, 8)],
]

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def code_end(line):
    """Index where code ends (first unquoted '#'), or len(line)."""
    sq = dq = False
    for i, c in enumerate(line):
        if c == "'" and not dq:
            sq = not sq
        elif c == '"' and not sq:
            dq = not dq
        elif c == "#" and not sq and not dq:
            return i
    return len(line)


def find_close(s, start):
    """start points at '('; return index of its matching ')' or -1."""
    depth = 0
    sq = dq = False
    for i in range(start, len(s)):
        c = s[i]
        if c == "'" and not dq:
            sq = not sq
        elif c == '"' and not sq:
            dq = not dq
        elif sq or dq:
            continue
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def split_args(s):
    """Split top-level commas of s (already inside the parens)."""
    args, depth, cur = [], 0, []
    sq = dq = False
    for c in s:
        if c == "'" and not dq:
            sq = not sq
        elif c == '"' and not sq:
            dq = not dq
        if (sq or dq) or c not in "(,)":
            cur.append(c)
            continue
        if c == "(":
            depth += 1
            cur.append(c)
        elif c == ")":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
    args.append("".join(cur).strip())
    return args


def rewrite_once(text):
    """One left-to-right pass; returns (new_text, n_scut, n_scutr, n_skip)."""
    out = []
    i = 0
    n_scut = n_scutr = n_skip = 0
    while True:
        j = text.find("strip(cut(", i)
        if j < 0:
            out.append(text[i:])
            break
        # skip if the match sits in a comment or string on its line
        ls = text.rfind("\n", 0, j) + 1
        le = text.find("\n", j)
        if le < 0:
            le = len(text)
        if j - ls >= code_end(text[ls:le]):
            out.append(text[i:j + 10])
            i = j + 10
            continue
        cut_open = j + 9   # index of '(' after "cut" in "strip(cut("
        strip_open = j + 5  # index of '(' after "strip"
        close = find_close(text, cut_open)      # cut's ')'
        sclose = find_close(text, strip_open)   # strip's ')'
        if close < 0 or sclose < 0:
            out.append(text[i:j + 10])
            i = j + 10
            n_skip += 1
            continue
        if sclose != close + 1:
            # something sits between cut's close and strip's close: not the
            # plain strip(cut(...)) shape; leave it alone
            out.append(text[i:sclose + 1])
            i = sclose + 1
            n_skip += 1
            continue
        args = split_args(text[cut_open + 1:close])
        if len(args) != 3:
            out.append(text[i:sclose + 1])
            i = sclose + 1
            n_skip += 1
            continue
        e, a, b = args
        if b.startswith("length(") and b.endswith(")"):
            inner = b[7:-1]
            if inner == e and IDENT.match(e):
                rep = f"scutr({e}, {a})"
                n_scutr += 1
            else:
                rep = f"scut({e}, {a}, {b})"
                n_scut += 1
        else:
            rep = f"scut({e}, {a}, {b})"
            n_scut += 1
        out.append(text[i:j])
        out.append(rep)
        i = sclose + 1
    return "".join(out), n_scut, n_scutr, n_skip


def main():
    total_s = total_r = total_k = 0
    for rel in FILES:
        p = Path(rel)
        if not p.exists():
            print(f"MISSING {rel}")
            continue
        text = p.read_text()
        ns = nr = nk = 0
        while True:
            new, a, b, c = rewrite_once(text)
            ns += a; nr += b; nk += c
            text = new
            if a == 0 and b == 0:
                break
        p.write_text(text)
        total_s += ns; total_r += nr; total_k += nk
        print(f"{rel:38s} scut={ns:3d} scutr={nr:3d} skip={nk}")
    print(f"TOTAL scut={total_s} scutr={total_r} skipped={total_k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
