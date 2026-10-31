#!/usr/bin/env python3
"""mktamper.py - build the T4.2 negative-case package in the served directory.

Creates tamper.sxe (deterministic 200-byte synthetic body), signs it with the
trust-anchor key (edsign), THEN flips one body byte and regenerates the
sha256 digest for the flipped bytes. Result: the sha256 sibling is VALID for
the tampered content (the hash gate passes) while the .sig sibling is STALE
(signs the original bytes) - exactly the case only the Ed25519 verify catches.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edsign import sign  # noqa: E402


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: mktamper.py <served-dir>\n")
        return 2
    d = sys.argv[1]
    body = bytearray(b"TAMPERPKG-T4-NEGATIVE-CASE" + b"\x00" * 174)
    assert len(body) == 200
    path = os.path.join(d, "tamper.sxe")

    # 1) write the original body and sign it
    with open(path, "wb") as f:
        f.write(bytes(body))
    sig = sign(bytes(body))

    # 2) flip one byte in the middle of the body (tamper!)
    body[100] ^= 0x5A
    with open(path, "wb") as f:
        f.write(bytes(body))

    # 3) digest matches the TAMPERED bytes (hash check will pass),
    #    signature still belongs to the ORIGINAL bytes (verify must fail)
    with open(path + ".sig", "w") as f:
        f.write(sig.hex() + "\n")
    with open(path + ".sha256", "w") as f:
        f.write(hashlib.sha256(bytes(body)).hexdigest() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
