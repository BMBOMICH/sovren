#!/usr/bin/env python3
"""edsign.py - offline RFC 8032 Ed25519 signer for SovrenOS package signing.

Signs a file with the RFC 8032 test-vector-1 key pair (test trust anchor: the
matching public key is compiled into the integrated kernel as cell PP).
Prints the 64-byte signature R||S as 128 lowercase hex chars.

The kernel-side verifier is an independent implementation (16-limb Montgomery
field ops + inline SHA-512 in integrated_kernel.sov); this tool only runs on
the host at pack time. Self-checks against the RFC vectors before signing.
"""
import hashlib
import sys

P = 2**255 - 19
N = 2**252 + 27742317777372353535851937790883648493
BX = 15112221349535400772501151409588531511454012693041857206046113283949847762202
BY = 46316835694926478169428394003475163141307993866256225615783033603165251855960

# RFC 8032 test vector 1 key pair (public half is the kernel trust anchor)
SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
PUB = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
SIG_EMPTY = bytes.fromhex(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)


def sha512(b):
    return hashlib.sha512(b).digest()


def inv(x):
    return pow(x, P - 2, P)


D = (-121665 * inv(121666)) % P


def add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    den1 = (1 + D * x1 * x2 * y1 * y2) % P
    den2 = (1 - D * x1 * x2 * y1 * y2) % P
    if den1 == 0 or den2 == 0:
        return None
    x3 = ((x1 * y2 + x2 * y1) * inv(den1)) % P
    y3 = ((y1 * y2 + x1 * x2) * inv(den2)) % P
    return (x3, y3)


def mul(s, p):
    r = None
    while s > 0:
        if s & 1:
            r = add(r, p)
        p = add(p, p)
        s >>= 1
    return r


def encode(p):
    x, y = p
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def keypair(seed):
    h = sha512(seed)
    a = int.from_bytes(h[:32], "little")
    a = (a & ~7) & ((1 << 255) - 1)  # clear bits 0..2 and 255
    a |= 1 << 254                    # set bit 254
    return a, h[32:]


def sign(msg, seed=SEED):
    a, prefix = keypair(seed)
    pub = encode(mul(a, (BX, BY)))
    r = int.from_bytes(sha512(prefix + msg), "little") % N
    big_r = encode(mul(r, (BX, BY)))
    k = int.from_bytes(sha512(big_r + pub + msg), "little") % N
    s = (r + k * a) % N
    return big_r + s.to_bytes(32, "little")


def selfcheck():
    a, _ = keypair(SEED)
    assert encode(mul(a, (BX, BY))) == PUB, "public key does not match anchor"
    assert sign(b"") == SIG_EMPTY, "empty-message signature mismatch"


def main():
    selfcheck()
    if len(sys.argv) != 2:
        sys.stderr.write("usage: edsign.py <file>\n")
        return 2
    with open(sys.argv[1], "rb") as f:
        msg = f.read()
    sys.stdout.write(sign(msg).hex() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
