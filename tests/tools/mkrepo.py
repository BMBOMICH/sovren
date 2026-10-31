#!/usr/bin/env python3
"""mkrepo.py - build the signed repository index + rogue package (T4.3a).

Writes into the served directory:
  repo.idx       lines "name sha256hex" for the three real packages
  repo.idx.sig   Ed25519 signature of repo.idx (trust anchor)
  repo.idx.sha256 digest sibling (transport integrity)
  rogue.sxe[.sig|.sha256] a CORRECTLY signed copy of notes-app that is NOT
                 listed in the index - properly signed and digest-valid, so
                 only the signed-index authority check can reject it.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edsign import sign  # noqa: E402

PACKAGES = ["second-app.sxe", "notes-app.sxe", "net-app.sxe", "tasks-app.sxe"]


def digest_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def write(path, data):
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(path, mode) as f:
        f.write(data)


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: mkrepo.py <served-dir>\n")
        return 2
    d = sys.argv[1]
    lines = []
    for name in PACKAGES:
        p = os.path.join(d, name)
        if not os.path.exists(p):
            sys.stderr.write("missing package: %s\n" % p)
            return 1
        lines.append("%s %s\n" % (name, digest_of(p)))
    idx = "".join(lines)
    write(os.path.join(d, "repo.idx"), idx)
    write(os.path.join(d, "repo.idx.sig"), sign(idx.encode()).hex() + "\n")
    write(os.path.join(d, "repo.idx.sha256"), digest_of(os.path.join(d, "repo.idx")) + "\n")

    src = os.path.join(d, "notes-app.sxe")
    with open(src, "rb") as f:
        body = f.read()
    rogue = os.path.join(d, "rogue.sxe")
    write(rogue, body)
    write(rogue + ".sha256", hashlib.sha256(body).hexdigest() + "\n")
    write(rogue + ".sig", sign(body).hex() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
