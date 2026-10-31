"""apple_kits.py - generate the Apple platform back ends from the ios one.

The six Apple targets differ in exactly one line of source: the
LC_BUILD_VERSION command, which carries the platform number, the minimum OS and
the SDK the binary was built against.  Everything else - the arm64 code
generator, the Mach-O layout, the code signature, the XNU syscall table - is
shared, so the variants are GENERATED from compilers/apple/ios/compiler.sov rather
than kept as six hand-edited copies.  This script is the only sanctioned way to
change them, the way tools/sync_kits.sh is for the mirrors.

    platform   name                LC_BUILD_VERSION
    1          macos-arm64         Apple-Silicon macOS slice (x86-64 macOS is compilers/apple/macos)
    2          ios, ipados         iOS: iPadOS reports the iOS platform
    3          tvos
    4          watchos
    7          ios-simulator       the arm64 slice of the iOS simulator
    8          tvos-simulator
    9          watchos-simulator
    11         visionos
    12         visionos-simulator

    usage: python3 tools/apple_kits.py            write the sources
           python3 tools/apple_kits.py --check    verify only, exit 1 on drift

minos and sdk are packed the way Mach-O wants them: (major << 16) | (minor << 8).
"""
import os
import re
import sys

TARGETS = [
    # name,          platform, minos (major,minor,patch), sdk
    ('macos-arm64',   1, (11, 0, 0), (15, 0, 0)),
    ('tvos',          3, (12, 0, 0), (18, 0, 0)),
    ('watchos',       4, (7, 0, 0),  (11, 0, 0)),
    ('visionos',     11, (1, 0, 0),  (2, 0, 0)),
    ('ios-simulator',       7, (12, 0, 0), (18, 0, 0)),
    ('tvos-simulator',      8, (12, 0, 0), (18, 0, 0)),
    ('watchos-simulator',   9, (7, 0, 0),  (11, 0, 0)),
    ('visionos-simulator', 12, (1, 0, 0),  (2, 0, 0)),
]

BASE = 'compilers/apple/ios/compiler.sov'
LINE = re.compile(r'^(\s*flat: poke4 176 \+ 4 \* i: 50 24 )(\d+)( \d+ \d+)$')


def packed(v):
    return (v[0] << 16) | (v[1] << 8) | v[2]


def variant(src, platform, minos, sdk):
    out = []
    hit = 0
    for line in src.split('\n'):
        m = LINE.match(line)
        if m:
            hit += 1
            line = '%s%d %d %d' % (m.group(1), platform, packed(minos), packed(sdk))
        out.append(line)
    if hit != 1:
        raise SystemExit('expected exactly one LC_BUILD_VERSION line, found %d' % hit)
    return '\n'.join(out)


def main():
    check = '--check' in sys.argv[1:]
    src = open(BASE).read()
    drift = 0
    for name, plat, minos, sdk in TARGETS:
        want = variant(src, plat, minos, sdk)
        path = 'compilers/apple/%s/compiler.sov' % name
        have = open(path).read() if os.path.exists(path) else None
        if have == want:
            print('ok   %s (platform %d)' % (path, plat))
            continue
        drift += 1
        if check:
            print('DRIFT %s' % path)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'w').write(want)
        print('GEN  %s (platform %d, minos %d.%d.%d, sdk %d.%d.%d)'
              % (path, plat, minos[0], minos[1], minos[2], sdk[0], sdk[1], sdk[2]))
    if drift and check:
        print('CHECK FAILED: %d back end(s) out of step with %s' % (drift, BASE))
        return 1
    return 0


sys.exit(main())
