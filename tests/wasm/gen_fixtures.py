#!/usr/bin/env python3
"""gen_fixtures.py - the wasm spec fixtures for tests/wasmtest.sov.

Each fixture is a small hand-assembled wasm32 module exercising one corner of
the interpreter in library/wasm.sov.  The bytes here are the reference: the
interpreter must load and run them, and tests/wasmtest.sov asserts exact
results.  Run from the repo root:  python3 tests/wasm/gen_fixtures.py
"""
import os
import struct
import sys

OUT = os.path.join(os.path.dirname(__file__))


def uleb(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def sleb(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if (v == 0 and not (b & 0x40)) or (v == -1 and (b & 0x40)):
            out.append(b)
            return bytes(out)
        out.append(b | 0x80)


def vec(items):
    return uleb(len(items)) + b''.join(items)


def section(sid, body):
    return bytes([sid]) + uleb(len(body)) + body


def module(*sections):
    return b'\0asm\x01\0\0\0' + b''.join(sections)


I32, I64 = 0x7F, 0x7E


def functype(params, results):
    return bytes([0x60]) + vec([bytes([p]) for p in params]) \
        + vec([bytes([r]) for r in results])


def funccount(types):
    return section(1, vec(types))


def funsection(tidx):
    return section(3, vec([uleb(t) for t in tidx]))


def memsection(minp, maxp=None):
    if maxp is None:
        return section(5, vec([bytes([0]) + uleb(minp)]))
    return section(5, vec([bytes([1]) + uleb(minp) + uleb(maxp)]))


def exportsection(pairs):
    return section(7, vec([uleb(len(n)) + n.encode() + bytes([0]) + uleb(i)
                           for n, i in pairs]))


def importsection(imports):
    # imports: (module, field, kind, payload)
    out = []
    for m, f, k, payload in imports:
        e = uleb(len(m)) + m.encode() + uleb(len(f)) + f.encode() + bytes([k])
        out.append(e + payload)
    return section(2, vec(out))


def i32const(v):
    out = bytearray()
    more = True
    while more:
        b = v & 0x7F
        v >>= 7
        if (v == 0 and not (b & 0x40)) or (v == -1 and (b & 0x40)):
            more = False
        else:
            b |= 0x80
        out.append(b)
    return bytes([0x41]) + bytes(out)


def body(locals_runs, code):
    b = vec([uleb(c) + bytes([t]) for c, t in locals_runs]) + code
    return uleb(len(b)) + b


def codesection(bodies):
    return section(10, vec(bodies))


def datasection(segs):
    # active segment, memory 0: offset expr (i32.const n end), bytes
    out = []
    for off, data in segs:
        out.append(bytes([0]) + b'\x41' + sleb(off) + b'\x0b'
                   + uleb(len(data)) + data)
    return section(11, vec(out))


def write(name, data):
    path = os.path.join(OUT, name)
    open(path, 'wb').write(data)
    print('%-14s %d bytes' % (name, len(data)))


def main():
    # add.wasm - params and i32.add:  add(2,3) = 5
    write('add.wasm', module(
        funccount([functype([I32, I32], [I32])]),
        funsection([0]),
        exportsection([('add', 0)]),
        codesection([body([], bytes([0x20, 0, 0x20, 1, 0x6A, 0x0B]))])))

    # fib.wasm - recursion: fib(10) = 55
    # fib(n): if n < 2 -> n else fib(n-1) + fib(n-2)
    code = bytes([
        0x20, 0,                       # local.get n
        0x41, 2,                       # i32.const 2
        0x48,                          # i32.lt_s
        0x04, 0x7F,                    # if (result i32)
        0x20, 0,                       #   n
        0x05,                          # else
        0x20, 0, 0x41, 1, 0x6B,        #   n - 1
        0x10, 0,                       #   call fib
        0x20, 0, 0x41, 2, 0x6B,        #   n - 2
        0x10, 0,                       #   call fib
        0x6A,                          #   i32.add
        0x0B,                          # end
        0x0B])                         # end (function)
    write('fib.wasm', module(
        funccount([functype([I32], [I32])]),
        funsection([0]),
        exportsection([('fib', 0)]),
        codesection([body([], code)])))

    # ctrl.wasm - loops, br, br_if, if/else, select
    #   sum10()      = 55: loop accumulating 1..10
    #   mx(a, b)     = max(a, b) via if/else
    #   sel(a, b, c) = select: c ? a : b
    #   dvs(a, b)    = a / b, a % b packed? keep simple: a / b (div_s)
    sum10 = bytes([
        0x41, 0, 0x21, 0,              # i = 0 (local 0)
        0x41, 0, 0x21, 1,              # acc = 1 (local 1)
        0x03, 0x40,                    # loop
        0x20, 0, 0x41, 10, 0x4D,       #   i < 10 ?  (le_s)
        0x0D, 0,                       #   br_if 0 exits? no: br_if branches TO label 0 = loop -> continue
        0x20, 1, 0x20, 0, 0x6A, 0x21, 1,  # acc += i
        0x20, 0, 0x41, 1, 0x6A, 0x21, 0,  # i += 1
        0x0C, 0,                       #   br 0 (loop again)
        0x0B,                          # end loop
        0x20, 1,                       # acc
        0x0B])
    # careful: the loop condition: while i <= 10? Let's do: br_if 0 exits when i >= 10:
    # recompute cleanly below in build()
    sum10 = bytes([
        0x03, 0x40,                    # loop
        0x20, 0, 0x41, 1, 0x6A, 0x21, 0,   # i += 1
        0x20, 1, 0x20, 0, 0x6A, 0x21, 1,   # acc += i
        0x20, 0, 0x41, 10, 0x4E,       #   i >= 10 ? (ge_s)
        0x0D, 1,                       #   br_if 1 -> exits the loop (label 1 = block outside? no outer block!)
        0x0C, 0,                       #   br 0
        0x0B,                          # end loop
        0x20, 1, 0x0B])
    # the loop itself is label 0; br_if 1 inside a bare loop has no label 1 ->
    # restructure: wrap the loop in a block so the exit is br 1 to the block end.
    sum10 = bytes([
        0x02, 0x40,                    # block
        0x03, 0x40,                    #   loop
        0x20, 0, 0x41, 1, 0x6A, 0x21, 0,
        0x20, 1, 0x20, 0, 0x6A, 0x21, 1,
        0x20, 0, 0x41, 10, 0x4E,       #   i >= 10
        0x0D, 1,                       #   br_if 1 (the block)
        0x0C, 0,                       #   br 0 (loop)
        0x0B,                          #   end loop
        0x0B,                          # end block
        0x20, 1,                       # acc
        0x0B])
    mx = bytes([
        0x20, 0, 0x20, 1, 0x4A,        # a > b
        0x04, 0x7F, 0x20, 0,           # if (i32) a
        0x05, 0x20, 1,                 # else b
        0x0B, 0x0B])                   # end, end func
    sel = bytes([
        0x20, 0, 0x20, 1, 0x20, 2, 0x1B, 0x0B])   # a b c select
    dvs = bytes([0x20, 0, 0x20, 1, 0x6D, 0x0B])   # a / b (div_s)
    rms = bytes([0x20, 0, 0x20, 1, 0x6F, 0x0B])   # a % b (rem_s)
    write('ctrl.wasm', module(
        funccount([functype([], [I32]), functype([I32, I32], [I32]),
                   functype([I32, I32, I32], [I32]),
                   functype([I32, I32], [I32]), functype([I32, I32], [I32])]),
        funsection([0, 1, 2, 3, 4]),
        exportsection([('sum10', 0), ('mx', 1), ('sel', 2), ('dvs', 3),
                       ('rms', 4)]),
        codesection([body([(2, I32)], sum10), body([], mx), body([], sel),
                     body([], dvs), body([], rms)])))

    # mem.wasm - linear memory, loads/stores, grow
    #   st(v)          store 0x2A at address 64, load it back
    #   st8(v)         store8 0x3A at 100, load8_u 0x2D
    #   grw(n)         memory.grow
    #   ld16()         load16_u of a data-segment word
    st = bytes([0x41, 0xC0, 0x00, 0x20, 0, 0x36, 2, 0,       # i32.store align2 off0
                0x41, 0xC0, 0x00, 0x28, 2, 0, 0x0B])         # i32.load
    st8 = bytes(i32const(100) + bytes([0x20, 0, 0x3A, 0, 0]) + i32const(100) + bytes([0x2D, 0, 0, 0x0B]))
    grw = bytes([0x20, 0, 0x40, 0x00, 0x0B])         # memory.grow -> old pages
    ld16 = bytes([0x41, 8, 0x2F, 0, 0, 0x0B])        # i32.load16_u at 8
    write('mem.wasm', module(
        funccount([functype([I32], [I32]), functype([I32], [I32]),
                   functype([I32], [I32]), functype([], [I32])]),
        funsection([0, 1, 2, 3]),
        memsection(1),
        exportsection([('st', 0), ('st8', 1), ('grw', 2), ('ld16', 3)]),
        datasection([(8, b'\x34\x12\xff\x7f\x00\x00\x00\x00\xef\xbe')]),
        codesection([body([], st), body([], st8), body([], grw),
                     body([], ld16)])))

    # ops.wasm - the arithmetic battery, one export per question
    defs = [
        ('shl',  [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x74, 0x0B]),
        ('shrs', [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x75, 0x0B]),
        ('shru', [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x76, 0x0B]),
        ('andd', [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x71, 0x0B]),
        ('orr',  [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x72, 0x0B]),
        ('xorr', [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x73, 0x0B]),
        ('subb', [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x6B, 0x0B]),
        ('mull', [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x6C, 0x0B]),
        ('divu', [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x6E, 0x0B]),
        ('remu', [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x70, 0x0B]),
        ('ltu',  [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x49, 0x0B]),
        ('geu',  [I32, I32], [I32], [0x20, 0, 0x20, 1, 0x4F, 0x0B]),
        ('eqz',  [I32],      [I32], [0x20, 0, 0x45, 0x0B]),
        ('wrap', [I64],      [I32], [0x20, 0, 0xA7, 0x0B]),
        ('exts', [I32],      [I64], [0x20, 0, 0xAC, 0x0B]),
        ('extu', [I32],      [I64], [0x20, 0, 0xAD, 0x0B]),
        ('tee',  [I32],      [I32], [0x20, 0, 0x22, 0, 0x20, 0,
                                     0x6A, 0x0B]),   # local.tee doubling
        ('drop1', [I32, I32], [I32], [0x20, 0, 0x1A, 0x20, 1, 0x0B]),
        ('unr',   [I32],     [I32], [0x00, 0x0B]),     # unreachable
    ]
    write('ops.wasm', module(
        funccount([functype(p, r) for _, p, r, _ in defs]),
        funsection(list(range(len(defs)))),
        exportsection([(n, i) for i, (n, _, _, _) in enumerate(defs)]),
        codesection([body([], bytes(c)) for _, _, _, c in defs])))

    # hello.wasm - the WASI shape: fd_write + proc_exit imports, a data
    # segment, and a _start that prints "Hello WASI" and exits 7.
    #   memory layout: 0..15 scratch, 16: iov[ptr,len], 32: "Hello WASI"
    start = bytes([
        0x41, 1, 0x41, 16, 0x41, 1, 0x41, 20,          # fd 1, iovs@16, 1, out@20
        0x10, 0,                                       # call fd_write
        0x1A,                                          # drop errno
        0x41, 7,                                       # i32.const 7
        0x10, 1,                                       # call proc_exit
        0x0B])
    # the iov: ptr=32, len=10 written by a data segment? segments are static:
    # iov = bytes 16..23 = 32,10 ; msg = 32..42
    iov = struct.pack('<II', 32, 10)
    write('hello.wasm', module(
        importsection([
            ('wasi_snapshot_preview1', 'fd_write', 0, uleb(0)),
            ('wasi_snapshot_preview1', 'proc_exit', 0, uleb(1)),
        ]),
        funccount([functype([I32, I32, I32, I32], [I32]),
                   functype([I32], [])]),
        memsection(1),
        exportsection([('_start', 2)]),      # func index 2 (2 imports first)
        datasection([(16, iov + b'\0' * 8 + b'Hello WASI')]),
        codesection([]),
        )) if False else None
    # code section must carry the _start body: rewrite with both pieces
    write('hello.wasm', module(
        importsection([
            ('wasi_snapshot_preview1', 'fd_write', 0, uleb(0)),
            ('wasi_snapshot_preview1', 'proc_exit', 0, uleb(1)),
        ]),
        funccount([functype([I32, I32, I32, I32], [I32]),
                   functype([I32], [])]),
        memsection(1),
        exportsection([('_start', 2)]),
        datasection([(16, iov + b'\0' * 8 + b'Hello WASI')]),
        codesection([body([], start)])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
