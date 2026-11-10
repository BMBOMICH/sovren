# Third-party notices

The Sovren toolchain and SovrenOS are original first-party work in the
Sovren language, except for the following public-domain third-party
material incorporated with attribution.

## font8x8 (library/kfont8.sov)

- **Source:** `font8x8_basic` from the `font8x8` project,
  https://github.com/dhepper/font8x8 (`font8x8_basic.h`).
- **Authors / lineage:** Daniel Hepper <daniel@hepper.net>, based on
  Marcel Sondaar's public-domain 8x8 font work, which in turn derives
  from the public-domain IBM VGA 8x8 font.
- **License:** Public domain (the author dedicates the work to the
  public domain; see the repository's README). Alternatively usable
  under the Unlicense where public-domain dedication is not recognized.
- **What was incorporated:** the 8x8 glyph bitmaps for printable ASCII
  32..126 (95 glyphs, eight rows per glyph, one byte per row,
  least-significant-bit = leftmost pixel). The bitmaps were ported into
  native Sovren source as 64-bit packed constants in
  `library/kfont8.sov`; the rasterizer around them is first-party.
- **Upstream upstream-provenance note (from the source file):** the
  font collection is "free to use for any purpose, no attribution
  required" — attribution is given here regardless, as good practice.

Provenance recorded 2026-09-06; verify against the upstream repository
before any redistribution change.
