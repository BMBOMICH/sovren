#!/usr/bin/env python3
"""SXE v1 compiler/ABI conformance test used by Linux CI.

The test validates a compiler-produced container, rejects malformed mutations,
applies its standard RELATIVE records, maps two fresh copies at unrelated load
addresses, enforces non-writable CODE before entry, and verifies that status 37
returns to the loader. It does not use ELF program-header loading.
"""
from __future__ import annotations

import ctypes
import mmap
import platform
import struct
import sys
from pathlib import Path

MAGIC = 4_544_595
VERSION = 1
CODE = 1
RODATA = 2
DATA = 3
RELOC = 4
HEADER = 32
SECTION = 24
RELOC_RECORD = 24
RELATIVE = 1
MAX_SECTIONS = 32
PAGE = mmap.PAGESIZE


class InvalidSXE(ValueError):
    pass


def validate(data: bytes | bytearray) -> tuple[int, list[tuple[int, int, int]]]:
    if len(data) < HEADER:
        raise InvalidSXE("truncated header")
    magic, version, entry, count = struct.unpack_from("<4Q", data, 0)
    if magic != MAGIC or bytes(data[:4]) != b"SXE\0":
        raise InvalidSXE("bad magic")
    if version != VERSION:
        raise InvalidSXE("unsupported version")
    if count < 1 or count > MAX_SECTIONS:
        raise InvalidSXE("invalid section count")
    table_end = HEADER + count * SECTION
    if table_end > len(data):
        raise InvalidSXE("truncated section table")

    sections: list[tuple[int, int, int]] = []
    entry_hits = 0
    reloc_count = 0
    for index in range(count):
        kind, off, length = struct.unpack_from("<3Q", data, HEADER + index * SECTION)
        if kind < CODE or kind > 6:
            raise InvalidSXE("unknown v1 section type")
        if off < table_end or off > len(data) or length > len(data) - off:
            raise InvalidSXE("section outside file")
        if length == 0:
            raise InvalidSXE("empty section")
        for _, prior_off, prior_len in sections:
            if off < prior_off + prior_len and prior_off < off + length:
                raise InvalidSXE("overlapping sections")
        sections.append((kind, off, length))
        if kind == CODE and off <= entry < off + length:
            entry_hits += 1
        if kind == RELOC:
            reloc_count += 1
            if length % RELOC_RECORD:
                raise InvalidSXE("partial relocation record")
    if entry_hits != 1:
        raise InvalidSXE("entry is not in exactly one code section")
    if reloc_count > 1:
        raise InvalidSXE("more than one relocation section")

    loadable = [(off, length) for kind, off, length in sections if kind in (CODE, RODATA, DATA)]
    for kind, off, length in sections:
        if kind != RELOC:
            continue
        for pos in range(off, off + length, RELOC_RECORD):
            target, addend, reloc_type = struct.unpack_from("<3Q", data, pos)
            if reloc_type != RELATIVE:
                raise InvalidSXE("unknown relocation type")
            if target > len(data) - 8:
                raise InvalidSXE("relocation target outside image")
            if addend >= len(data):
                raise InvalidSXE("relocation addend outside image")
            if not any(start <= target and target + 8 <= start + size for start, size in loadable):
                raise InvalidSXE("relocation target outside loadable section")
    return entry, sections


def must_reject(name: str, data: bytes | bytearray) -> None:
    try:
        validate(data)
    except InvalidSXE:
        return
    raise AssertionError(f"malformed image accepted: {name}")


def page_span(base: int, off: int, length: int) -> tuple[int, int]:
    start = (base + off) & -PAGE
    end = (base + off + length + PAGE - 1) & -PAGE
    return start, end - start


def load_and_execute(data: bytes, entry: int, sections: list[tuple[int, int, int]]):
    # Begin writable but non-executable so relocation never requires W+X.
    image = mmap.mmap(-1, len(data), flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                      prot=mmap.PROT_READ | mmap.PROT_WRITE)
    image.write(data)
    base = ctypes.addressof(ctypes.c_char.from_buffer(image))

    for kind, off, length in sections:
        if kind != RELOC:
            continue
        for pos in range(off, off + length, RELOC_RECORD):
            target, addend, _ = struct.unpack_from("<3Q", data, pos)
            ctypes.c_uint64.from_address(base + target).value = base + addend

    libc = ctypes.CDLL(None, use_errno=True)
    libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    libc.mprotect.restype = ctypes.c_int
    for kind, off, length in sections:
        if kind == CODE:
            start, size = page_span(base, off, length)
            if libc.mprotect(start, size, mmap.PROT_READ | mmap.PROT_EXEC) != 0:
                raise OSError(ctypes.get_errno(), "mprotect CODE RX")
        elif kind in (RODATA, RELOC):
            start, size = page_span(base, off, length)
            if libc.mprotect(start, size, mmap.PROT_READ) != 0:
                raise OSError(ctypes.get_errno(), "mprotect immutable section")

    status = int(ctypes.CFUNCTYPE(ctypes.c_int64)(base + entry)())
    return image, base, status


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_sxe.py IMAGE.sxe")
    data = Path(sys.argv[1]).read_bytes()
    entry, sections = validate(data)
    code_ranges = [(off, length) for kind, off, length in sections if kind == CODE]

    # Callable startup is CALL rel32; RET. This detects the stale-HDR regression
    # where an optimized image's header entry landed in unrelated bytes.
    if data[entry] != 0xE8 or data[entry + 5] != 0xC3:
        raise AssertionError(f"entry is not callable SXE start: {data[entry:entry+8].hex()}")
    if any(b"\x0f\x05" in data[off:off + length] for off, length in code_ranges):
        raise AssertionError("freestanding SXE code contains a Linux syscall instruction")
    if not any(kind == DATA for kind, _, _ in sections):
        raise AssertionError("compiler did not separate writable SXE data")
    if not any(kind == RELOC for kind, _, _ in sections):
        raise AssertionError("test payload did not exercise an SXE relocation record")

    bad = bytearray(data)
    bad[0] ^= 0xFF
    must_reject("magic", bad)
    must_reject("truncated header", data[:31])
    must_reject("truncated section table", data[:55])
    bad = bytearray(data)
    struct.pack_into("<Q", bad, 24, MAX_SECTIONS + 1)
    must_reject("section count", bad)
    bad = bytearray(data)
    struct.pack_into("<Q", bad, 16, len(data))
    must_reject("entry outside code", bad)
    bad = bytearray(data)
    struct.pack_into("<Q", bad, 48, len(data))
    must_reject("section overflow", bad)
    if len(sections) > 1:
        bad = bytearray(data)
        struct.pack_into("<Q", bad, HEADER + SECTION + 8, sections[0][1])
        must_reject("section overlap", bad)
    reloc = next((x for x in sections if x[0] == RELOC), None)
    if reloc:
        bad = bytearray(data)
        struct.pack_into("<Q", bad, reloc[1] + 16, 99)
        must_reject("relocation type", bad)
        bad = bytearray(data)
        struct.pack_into("<Q", bad, reloc[1], len(data))
        must_reject("relocation target", bad)

    loaded = [load_and_execute(data, entry, sections) for _ in range(2)]
    try:
        bases = [item[1] for item in loaded]
        statuses = [item[2] for item in loaded]
        if bases[0] == bases[1]:
            raise AssertionError("fresh SXE mappings unexpectedly share a load address")
        if statuses != [37, 37]:
            raise AssertionError(f"payload status was not propagated: {statuses}")
    finally:
        for image, _, _ in loaded:
            image.close()

    print("SXE ABI: sections/W^X, RELATIVE relocation at two biases, malformed "
          f"inputs rejected, return=37 at {hex(bases[0])}, {hex(bases[1])}")
    return 0


if __name__ == "__main__":
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        raise SystemExit("SXE execution test requires an x86-64 runner")
    raise SystemExit(main())
