"""Expand Sovren's block includes: `include <file> <start> <count> [(params)]`.

This is a faithful Python port of tr_flat/tr_psub in library/testrun.sov.  The
library/inc/*.sov files are line-addressable stores of shared code blocks; a
source line that names a range splices those lines back in, indented to the
line's own level, with %1 %2 ... replaced by the parameter list when one is
given.  It is what the compiler itself does when it reads a source.
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
LIB = 'library' if os.path.isdir('library') else os.path.join(_here, '..', 'library')
cache = {}


def block(name):
    if name not in cache:
        with open(os.path.join(LIB, name)) as f:
            cache[name] = f.read().split('\n')
    return cache[name]


def psub(line, pars):
    out = []
    i, n = 0, len(line)
    toks = [t.strip() for t in pars.split(' ')]
    while i < n:
        c = line[i]
        hit = False
        if c == '%' and i + 1 < n:
            d = line[i + 1]
            if d.isdigit() and int(d) > 0:
                k = int(d)
                v = toks[k - 1] if k <= len(toks) else ''
                if v:
                    out.append(v)
                    i += 2
                    hit = True
        if not hit:
            out.append(c)
            i += 1
    return ''.join(out)


def expand(path):
    out = []
    for line in open(path).read().split('\n'):
        p = line.find('include ')
        if p < 0:
            out.append(line)
            continue
        try:
            ind = line[:p]
            spec = line[p + 8:].strip()
            pars = ''
            op = spec.find('(')
            if op >= 0:
                pars = spec[op + 1:len(spec) - 1].strip()
                spec = spec[:op].strip()
            nm, start, count = spec, 0, 0
            sp = spec.find(' ')
            nm_try = spec[:sp] if sp >= 0 else spec
            if not nm_try or not os.path.exists(os.path.join(LIB, nm_try)):
                out.append(line)      # prose that merely mentions an include
                continue
            if sp >= 0:
                nm = spec[:sp]
                rest = spec[sp + 1:].strip()
                sp2 = rest.find(' ')
                if sp2 >= 0:
                    start = int(rest[:sp2])
                    count = int(rest[sp2 + 1:].strip())
                else:
                    count = int(rest)
            if not os.path.exists(os.path.join(LIB, nm)):
                out.append(line)
                continue
            fl = block(nm)
            j = 0
            m = len(fl)
            if count > 0:
                j = start - 1
                m = j + count
                if m > len(fl):
                    m = len(fl)
            while j < m:
                fj = fl[j]
                if fj.strip():
                    if pars:
                        fj = psub(fj, pars)
                    fj = ind + fj
                out.append(fj)
                j += 1
        except (ValueError, IndexError):
            out.append(line)
    return '\n'.join(out)


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    with open(dst, 'w') as f:
        f.write(expand(src))
    print('%s -> %s (%d lines)' % (src, dst, len(expand(src).split('\n'))))
