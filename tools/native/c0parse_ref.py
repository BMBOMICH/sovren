#!/usr/bin/env python3
"""Reference transcription of the Sovren c0 parse loop (compiler.sov 10440-10671).

Executable spec for the _sov_c0_parse native blob. Written from the Sovren
source only. Order-exact, byte-exact.
"""
import hashlib
import json
import random

PRINTS = []      # bytes, in order (print / _sov_print / err_where markers)
G2_ON = False    # /tmp/sov_glog2 gate (zz_g2)
G2LOG = []       # exact bytes the g2 log writes would produce


def _len(s):  # length(s) = strlen (NUL-terminated)
    return s.find(b"\x00") if b"\x00" in s else len(s)


WS = (32, 9, 10, 13)


def byte_at(s, i):
    return s[i] if 0 <= i < len(s) else 0


def strip(t):
    # _sov_trim (runtime.sov:965): trims {32,9,10,13} from BOTH ends
    if t is None:
        return b""
    a = 0
    b = len(t)
    while a < b and t[a] in WS:
        a += 1
    while b > a and t[b - 1] in WS:
        b -= 1
    return t[a:b]


def strip_span(t):
    # cx86_p6.sov:1763 - value model: leading spaces; tab-after-spaces or a
    # trailing byte < 33 falls back to strip(t); else the suffix t[a:]
    if t is None:
        return b""
    a = 0
    while a < len(t) and t[a] == 32:
        a += 1
    if a < len(t) and t[a] == 9:
        return strip(t)
    s = t[a:]
    if len(s) == 0:
        return s
    if s[-1] < 33:
        return strip(t)
    return s


def nind(line, st):
    # cx86_p5.sov:1854: walk spaces; 0 byte -> return count; tab -> error
    c = 0
    i = 0
    while True:
        b = byte_at(line, i)
        if b == 0:
            return c
        if b == 9:
            PRINTS.append(b"Error: tab indent, use spaces")
            PRINTS.append(line)
            PRINTS.append(b"<err_where>")
            st["had_err"] = 1
            return c
        if b != 32:
            return c
        c += 1
        i += 1


def starts(t, p):
    return 1 if t.startswith(p) else 0


def look(t, needle):  # find text, -1 if absent
    i = t.find(needle)
    return i


def cfind1(text, ch):
    i = text.find(bytes([ch]))
    return i


def is_task_hdr(s):
    n = len(s)
    if n < 2:
        return 0
    if byte_at(s, 0) == 35:
        return 0
    if byte_at(s, n - 1) == 58:
        return 1
    return 0


def cut(s, a, b):
    return s[a:b]


def repl(text, old, new):
    if look(text, old) < 0:
        return text
    return repl_do(text, old, new)


def sg_match(text, p, old):
    return text[p:p+len(old)] == old


def repl_do(text, old, new):
    n = len(text)
    o = len(old)
    gn = len(new)
    if o > 0:
        if cfind1(text, 34) < 0:
            hits = 0
            p = 0
            while p + o <= n:
                if sg_match(text, p, old):
                    hits += 1
                    p += o
                else:
                    p += 1
            out = bytearray()
            p = 0
            while p < n:
                m = 0
                if p + o <= n and sg_match(text, p, old):
                    m = 1
                if m == 1:
                    out += new
                    p += o
                else:
                    out += text[p:p+1]
                    p += 1
            return bytes(out)
    # quote-aware branch (p6:494 tail): matches only outside quotes;
    # backslash inside quotes copies the next byte blindly
    r = bytearray(n + gn + 8)
    p = 0
    j = 0
    ins = 0
    while p < n:
        b = byte_at(text, p)
        if ins == 1:
            if b == 92:
                r[j] = b
                j += 1
                p += 1
                if p < n:
                    r[j] = byte_at(text, p)
                    j += 1
                    p += 1
            else:
                r[j] = b
                j += 1
                p += 1
                if b == 34:
                    ins = 0
        else:
            if b == 34:
                ins = 1
                r[j] = b
                j += 1
                p += 1
            else:
                m = 1
                if p + o > n:
                    m = 0
                else:
                    k = 0
                    while k < o:
                        if byte_at(text, p + k) != byte_at(old, k):
                            m = 0
                        k += 1
                if m == 1:
                    k = 0
                    while k < gn:
                        r[j] = byte_at(new, k)
                        j += 1
                        k += 1
                    p += o
                else:
                    r[j] = b
                    j += 1
                    p += 1
    return bytes(r[:j])


def find_col_q(text):
    i = 0
    n = len(text)
    ins = 0
    while i < n:
        b = byte_at(text, i)
        if ins == 1:
            if b == 92:
                i += 1
            elif b == 34:
                ins = 0
        else:
            if b == 34:
                ins = 1
            elif b == 58:
                return i
        i += 1
    return -1


def find_col(text):
    if cfind1(text, 34) < 0:
        return cfind1(text, 58)
    return find_col_q(text)


def find_sep_do(text):
    i = 0
    n = len(text)
    ins = 0
    while i < n - 3:
        b = byte_at(text, i)
        if ins == 1:
            if b == 92:
                i += 1
            elif b == 34:
                ins = 0
        else:
            if b == 34:
                ins = 1
            # (':' followed by '=' within window handled by caller check)
        i += 1
    return -1


def find_sep(text):
    # find_sep_do (p4:5328): " := " outside quotes, i < n-3; the match
    # check runs whenever ins==0 AFTER the quote-state update (so a
    # closing-quote position can match - it never does, ' "' != ' ')
    i = 0
    n = len(text)
    ins = 0
    while i < n - 3:
        b = byte_at(text, i)
        if ins == 1:
            if b == 92:
                i += 1
            elif b == 34:
                ins = 0
        else:
            if b == 34:
                ins = 1
        if ins == 0:
            if text[i:i+4] == b" := ":
                return i
        i += 1
    return -1


def i2s(n):
    # cx86_p5.sov:235 — WITH trailing newline
    if n == 0:
        return b"0\n"
    neg = 0
    v = n
    if v < 0:
        neg = 1
    digits = bytearray()
    while v != 0:
        d = v % 10
        if d < 0:
            d = 0 - d
        digits.append(48 + d)
        v = v // 10
    r = bytes(reversed(digits))
    if neg == 1:
        r = b"-" + r
    return r + b"\n"


def file_ln(li, src_base):
    n = li + 1
    if n > src_base:
        return n - src_base
    return n


def tname(line):
    s = strip(line)
    if is_task_hdr(s) == 1:
        s = strip(cut(s, 0, len(s) - 1))
        if starts(s, b"task ") == 1:
            s = strip(cut(s, 5, len(s)))
        wp = look(s, b" with ")
        if wp > -1:
            return repl(strip(cut(s, 0, wp)), b" ", b"_")
        sp = look(s, b" ")
        if sp > -1:
            return strip(cut(s, 0, sp))
        return s
    rest = strip(cut(line, 5, len(line)))
    wp = look(rest, b" with ")
    if wp > -1:
        return repl(strip(cut(rest, 0, wp)), b" ", b"_")
    sp = look(rest, b" ")
    if sp > -1:
        return repl(strip(cut(rest, 0, sp)), b" ", b"_")
    return repl(rest, b" ", b"_")


def tparams(line):
    lst = []
    s = strip(line)
    if is_task_hdr(s) == 1:
        s = strip(cut(s, 0, len(s) - 1))
        if starts(s, b"task ") == 1:
            s = strip(cut(s, 5, len(s)))
        wp = look(s, b" with ")
        if wp > -1:
            s = strip(cut(s, wp + 6, len(s)))
        else:
            sp = look(s, b" ")
            if sp < 0:
                return lst
            s = strip(cut(s, sp + 1, len(s)))
        p = repl(s, b",", b" ")
        p = repl(p, b" and ", b" ")
        i = 0
        n = len(p)
        one = b""
        while i < n:
            tp_c = byte_at(p, i)
            if tp_c == 32:
                if len(one) > 0:
                    lst.append(one)
                    one = b""
            else:
                one += bytes([tp_c])
            i += 1
        if len(one) > 0:
            lst.append(one)
    return lst


# --- the loop -----------------------------------------------------------


def parse(lns, src_base, kern_mode, need_priv):
    st = {"had_err": 0, "need_priv": need_priv}
    G2LOG.clear()
    names_n = 0
    names = []
    params = []
    bodies = []
    body_lns = []
    task_lns = []
    task_user = []
    glob_names = []
    sglob_names = []
    tops = []
    tops_lns = []
    tops_users = []
    in_t = 0
    cur = []
    cur_ln = []
    ln_n = len(lns)
    li = 0
    while li < ln_n:
        raw = lns[li]
        c0n0 = nind(raw, st)
        s = raw
        th = 0
        if c0n0 == 0:
            s = strip(raw)
            if st["need_priv"] == 0:
                if s == b"private":
                    st["need_priv"] = 1
                elif starts(s, b"wipe ") == 1:
                    st["need_priv"] = 1
            if is_task_hdr(s) == 1:
                th = 1
        if th == 1:
            if in_t == 1:
                bodies.append(cur)
                body_lns.append(cur_ln)
            tn = tname(s)
            if tn in names:  # zz_dup: names added so far
                PRINTS.append(b"Error: two with the same name")
                PRINTS.append(tn)
                PRINTS.append(b"<err_line:%d>" % file_ln(li, src_base))
                PRINTS.append(b"<err_where>")
                st["had_err"] = 1
            names.append(tn)
            names_n += 1
            tpl = tparams(s) if th == 1 else []
            if len(tpl) > 7:
                PRINTS.append(b"Error: too many parameters (7 max)")
                PRINTS.append(tname(s))
                st["had_err"] = 1
            params.append(tpl)
            tu = 0
            if li + 1 > src_base:
                tu = 1
            task_user.append(tu)
            task_lns.append(file_ln(li, src_base))
            cur = []
            cur_ln = []
            in_t = 1
        else:
            if c0n0 == 0:
                gok = 0
                gc = find_col(s)
                if starts(s, b"#") == 1:
                    gok = 0
                    gc = -1
                if gc > 0:
                    if gc < len(s) - 1:
                        gok = 1
                if gok == 1:
                    gn = b""
                    if starts(s, b"<-- ") == 1:
                        rest = cut(s, 4, len(s))
                        t = find_sep(rest)
                        if t > -1:
                            gn = repl(strip(cut(rest, 0, t)), b" ", b"_")
                    else:
                        # `if not` negates starts(s, "<-- ") - the LHS
                        # fallback does NOT run for alias lines whose alias
                        # name came out empty
                        gn = repl(strip(cut(s, 0, gc)), b" ", b"_")
                    if len(gn) > 0:
                        if gn not in glob_names:  # gn_lookup
                            glob_names.append(gn)
                            if G2_ON:
                                G2LOG.append(gn + b"\n")
                            sgin9 = strip(cut(s, gc + 1, len(s)))
                            if byte_at(sgin9, 0) == 34:
                                if gn not in sglob_names:  # sg_lookup
                                    sglob_names.append(gn)
                        else:
                            dupok = 1
                            for w in (b"heap_ptr", b"heap_end", b"g_slide",
                                      b"g_canary", b"g_argc", b"g_argv",
                                      b"pie_walk", b"sc_write", b"sc_exit",
                                      b"sc_mmap", b"mmap_flags", b"sc_mincore",
                                      b"sc_rand", b"sc_nodump", b"sc_sigact",
                                      b"M32"):
                                if gn == w:
                                    dupok = 0
                            if dupok == 1:
                                PRINTS.append(b"Error: duplicate top-level definition")
                                PRINTS.append(gn)
                                PRINTS.append(strip(raw))
                                PRINTS.append(b"<err_line:%d>" % file_ln(li, src_base))
                                PRINTS.append(b"<print-int:%d>" % file_ln(li, src_base))
                                st["had_err"] = 1
                        # sa check: INSIDE `if length(gn) > 0` (an empty gn
                        # skips the tops append entirely)
                        sa = 0
                        if gc + 1 < len(s):
                            grhs = strip(cut(s, gc + 1, len(s)))
                            if repl(grhs, b" ", b"_") == gn:
                                sa = 1
                        if sa == 0:
                            tops.append(raw)
                            tops_lns.append(file_ln(li, src_base))
                            if li + 1 > src_base:
                                tops_users.append(1)
                            else:
                                tops_users.append(0)
                if gok == 0:
                    if len(s) > 0:
                        if in_t == 1:
                            if starts(s, b"use ") == 0:
                                if starts(s, b"#") == 0:
                                    PRINTS.append(b"Error: a statement inside a task must be indented")
                                    PRINTS.append(s)
                                    PRINTS.append(b"<err_line:%d>" % file_ln(li, src_base))
                                    PRINTS.append(b"<print-int:%d>" % file_ln(li, src_base))
                                    st["had_err"] = 1
            else:
                # indented line
                if st["need_priv"] == 0:
                    pwb = byte_at(raw, c0n0)
                    pwh = 0
                    if pwb in (112, 119, 9):
                        pwh = 1
                    if pwh == 1:
                        pnl2 = strip_span(raw)  # strip_span (p6:1763)
                        if pnl2 == b"private":
                            st["need_priv"] = 1
                        elif starts(pnl2, b"wipe ") == 1:
                            st["need_priv"] = 1
                if in_t == 1:
                    law_handled = 0
                    if starts(s, b"law ") == 1:
                        law_handled = 1
                        law_body = strip(cut(s, 4, len(s)))
                        law_bln = len(law_body)
                        law_name = b"unnamed"
                        law_cond = law_body
                        if byte_at(law_body, 0) == 34:
                            law_q2 = 0
                            law_qi = 1
                            while law_qi < law_bln:
                                if byte_at(law_body, law_qi) == 34:
                                    if law_q2 == 0:
                                        law_q2 = law_qi
                                law_qi += 1
                            if law_q2 > 0:
                                law_name = cut(law_body, 1, law_q2)
                                law_cond = strip(cut(law_body, law_q2 + 1, law_bln))
                        law_sp = -1
                        law_ci = 0
                        while law_ci < law_bln:
                            if byte_at(law_body, law_ci) == 32:
                                if law_sp < 0:
                                    law_sp = law_ci
                            law_ci += 1
                        if law_sp > 0:
                            law_name = cut(law_body, 0, law_sp)
                            law_cond = strip(cut(law_body, law_sp, law_bln))
                        if len(law_cond) == 0:
                            PRINTS.append(b"Error: law expects a name and a condition")
                            law_handled = -1
                        law_ind = cut(raw, 0, len(raw) - len(s))
                        law_ln = file_ln(li, src_base)
                        cur.append(law_ind)
                        cur_ln.append(law_ln)
                        cur.append(law_ind + b"if " + law_cond + b" is 0")
                        cur_ln.append(law_ln)
                        cur.append(law_ind + b"    print \"LAW VIOLATED: " + law_name + b"\"")
                        cur_ln.append(law_ln)
                        cur.append(law_ind + b"    print " + i2s(law_ln))
                        cur_ln.append(law_ln)
                        if kern_mode == 1:
                            cur.append(law_ind + b"    as long as 1 is 1")
                            cur_ln.append(law_ln)
                            cur.append(law_ind + b"        hlt()")
                            cur_ln.append(law_ln)
                        if kern_mode == 0:
                            cur.append(law_ind + b"    sys_exit(232)")
                            cur_ln.append(law_ln)
                        if starts(cut(raw, 0, len(raw) - len(s)), b"        ") == 1:
                            pass  # dummy_dp no-op
                    if law_handled == 0:
                        cur.append(raw)
                        cur_ln.append(file_ln(li, src_base))
        li += 1
    if in_t == 1:
        bodies.append(cur)
        body_lns.append(cur_ln)
    return {
        "names": names, "params": params, "bodies": bodies,
        "body_lns": body_lns, "task_lns": task_lns,
        "task_user": task_user, "glob_names": glob_names,
        "sglob_names": sglob_names, "tops": tops, "tops_lns": tops_lns,
        "tops_users": tops_users, "need_priv": st["need_priv"],
        "had_err": st["had_err"], "prints": PRINTS,
        "g2log": b"".join(G2LOG),
    }


# --- regression + random cases -----------------------------------------


def result_hash(r):
    def ser(x):
        if isinstance(x, bytes):
            return x.decode("latin-1")
        if isinstance(x, list):
            return [ser(i) for i in x]
        if isinstance(x, dict):
            return {k: ser(v) for k, v in x.items()}
        return x
    return hashlib.sha256(json.dumps(ser(r), sort_keys=False).encode()).hexdigest()


REGRESSIONS = [
    ("tab-indent", [b"\tfoo"], 1, 0, 0),
    ("unindented-stmt", [b"task t:", b"x: 1"], 1, 0, 0),
    ("dup-task", [b"task t:", b" r()", b"task t:", b" r()"], 1, 0, 0),
    ("dup-global-dupok", [b"heap_ptr: 1", b"heap_ptr: 2"], 1, 0, 0),
    ("dup-global-bad", [b"zz: 1", b"zz: 2"], 1, 0, 0),
    ("too-many-params", [b"task t with a, b, c, d, e, f, g, h:"], 1, 0, 0),
    ("law-no-cond", [b"task t:", b" law unnamed"], 1, 0, 0),
    ("empty", [], 1, 0, 0),
    ("law-quoted", [b"task t:", b' law "the name" x < 3'], 1, 0, 0),
    ("law-kern", [b"task t:", b" law nm x is 0"], 1, 1, 0),
    ("private-top", [b"private", b"task t:", b" r()"], 1, 0, 0),
    ("wipe-indented", [b"task t:", b" wipe x", b" r()"], 1, 0, 0),
    ("global-quoted-colon", [b's: "a:b:=c"'], 1, 0, 0),
    ("alias", [b"<-- foo bar", b"x: 1"], 1, 0, 0),
]


def main():
    out = {"regressions": [], "random_hashes": [], "random_first20": []}
    global G2_ON
    for name, lines, src_base, kern, np_ in REGRESSIONS:
        PRINTS.clear()
        G2_ON = True  # regressions exercise the g2 path
        r = parse(lines, src_base, kern, np_)
        r = dict(r)
        r["prints"] = list(PRINTS)
        out["regressions"].append({"name": name, "hash": result_hash(r), "result": r})
    rng = random.Random(20261104)
    words = [b"foo", b"bar_baz", b"x", b"heap_ptr", b"sc_exit", b"g_argc", b"zz"]
    hdrs = [b"task t:", b"t:", b"task nm with a, b:", b"task nm with a, b, c, d, e, f, g, h:",
            b"main argc argv:"]
    for ci in range(1500):
        n = rng.randint(0, 20)
        lines = []
        for _ in range(n):
            k = rng.randint(0, 9)
            ind = b" " * rng.randint(0, 8)
            if k == 0:
                lines.append(rng.choice(hdrs))
            elif k == 1:
                lines.append(rng.choice(words) + b": " + rng.choice([b"1", b'"a:b"', b'"q:=z"', b'"s"']))
            elif k == 2:
                lines.append(ind + b"law " + rng.choice([b'"nm" x is 0', b"nm x is 0", b"nm"]))
            elif k == 3:
                lines.append(b"  " + rng.choice([b"private", b"wipe q", b"r()"]))
            elif k == 4:
                lines.append(b"# comment")
            elif k == 5:
                lines.append(b"")
            elif k == 6:
                lines.append(ind + b"    r()" + b" " * rng.randint(0, 2))
            elif k == 7:
                lines.append(b"<-- " + rng.choice([b"al ias", b"plain"]) + b" := " + b"val")
            elif k == 8:
                lines.append(ind + b"\tx")
            else:
                lines.append(ind + b"use lib")
        src_base = rng.randint(0, len(lines) + 3)
        PRINTS.clear()
        G2_ON = (ci % 7 == 3)  # every 7th random case exercises the g2 path
        r = parse(lines, src_base, rng.randint(0, 1), 0)
        r["prints"] = list(PRINTS)
        r["g2"] = G2_ON
        h = result_hash(r)
        out["random_hashes"].append(h)
        if ci < 20:
            out["random_first20"].append(r)
    print(json.dumps(out, indent=1, default=lambda x: x.decode("latin-1") if isinstance(x, bytes) else str(x)))


if __name__ == "__main__":
    main()
