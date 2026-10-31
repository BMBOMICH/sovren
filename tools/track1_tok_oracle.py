#!/usr/bin/env python3
"""Track 1.1 oracle: independent Python reference tokenizer for the Sovren
token grammar, cross-checked byte-exactly against the Sovren tok_scan
implementation (work/track1/tok_oracle binary).

Usage: track1_tok_oracle.py <oracle-binary> <file...>
Exit 0 only when every file's token stream + line table matches exactly.

Kind codes: 1=NL 2=WORD 3=NUMBER 4=STRING 5=COLON 6=LPAREN 7=RPAREN
            8=COMMA 9=OP 10=COMMENT 11=INDENT
Flags: bit0 escape-in-string, bit1 glued-to-prev-token, bit2 apostrophe-quoted.
Both sides print (off len kind flags) per token then LINES then line starts.
"""
import subprocess, sys

WORD = frozenset(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.$")


def reference(data: bytes):
    n = len(data)
    toks = []
    lstarts = [0]
    ln = 0
    i = 0
    ls = True       # at line start (indent still open)
    pre_sp = True   # whitespace seen since last token
    while i < n:
        b = data[i]
        if b == 10:
            lstarts.append(i + 1); ln += 1
            toks.append((i, 1, 1, 0))
            i += 1; ls = True; pre_sp = True
        elif b < 33:
            if ls:
                st = i
                while i < n and data[i] != 10 and data[i] < 33:
                    i += 1
                if i > st:
                    toks.append((st, i - st, 11, 0))
                ls = False; pre_sp = True
            else:
                i += 1; pre_sp = True
        elif b == 35:  # '#' comment
            st = i
            while i < n and data[i] != 10:
                i += 1
            toks.append((st, i - st, 10, 0))
            ls = False; pre_sp = True
        elif b in (34, 39):  # string
            st = i; esc = False; i += 1
            while True:
                if i >= n:
                    break
                b2 = data[i]
                if b2 == 10:
                    break
                if b2 == 92:
                    esc = True; i += 2
                elif b2 == b:
                    i += 1; break
                else:
                    i += 1
            fl = (1 if esc else 0) | (4 if b == 39 else 0)
            if not pre_sp:
                fl |= 2
            toks.append((st, i - st, 4, fl))
            ls = False; pre_sp = False
        elif b in WORD:
            st = i
            while i < n and data[i] in WORD:
                i += 1
            kd = 3 if 48 <= data[st] < 58 else 2
            fl = 0 if pre_sp else 2
            toks.append((st, i - st, kd, fl))
            ls = False; pre_sp = False
        else:
            kd = {58: 5, 40: 6, 41: 7, 44: 8}.get(b, 9)
            fl = 0 if pre_sp else 2
            toks.append((i, 1, kd, fl))
            i += 1; ls = False; pre_sp = False
        # note: comment/string paths in sovren scanner do NOT clear ls on
        # indent-stops; match exactly the branch order above.
    lstarts.append(n); ln += 1
    flat = []
    for (o, l, k, f) in toks:
        flat += [str(o), str(l), str(k), str(f)]
    flat.append("LINES"); flat.append(str(ln))
    flat += [str(x) for x in lstarts]
    return flat, len(toks), ln


def main():
    binpath, files = sys.argv[1], sys.argv[2:]
    bad = 0
    for f in files:
        data = open(f, "rb").read()
        got = subprocess.run([binpath, f], capture_output=True, timeout=60)
        if got.returncode != 0:
            print(f"FAIL {f}: oracle binary rc={got.returncode}"); bad += 1; continue
        fields = got.stdout.decode(errors="surrogateescape").split()
        exp, ntok, nl = reference(data)
        if fields == exp:
            print(f"OK {f} ({ntok} toks, {nl} lines)")
            continue
        print(f"FAIL {f}")
        for j in range(min(len(fields), len(exp))):
            if fields[j] != exp[j]:
                print(f"  first diff at field {j}: got {fields[j]!r} want {exp[j]!r}")
                t = j // 4 if fields[0] != "LINES" else 0
                print(f"  (token index ~{t} of {ntok})")
                break
        if len(fields) != len(exp):
            print(f"  field count: got {len(fields)} want {len(exp)}")
        bad += 1
    sys.exit(1 if bad else 0)


main()
