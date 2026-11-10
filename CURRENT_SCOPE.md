# Retained compiler scope

Backup: Desktop/sovren-backup-2026-11-09-before-cleanup. See compilers/cleanup-manifest.json for the complete removal list and original file hashes.

Thirty native compiler drivers and ten WebAssembly entries remain. Native means the implementation is a genuine compiler; it does not certify builds, correctness, compiler-host support or speed. All supplied driver executables are Linux-hosted. Of the native entries, only the Linux x86-64 driver has a built binary; the other 29 already lacked binaries before cleanup. All ten WebAssembly driver binaries exist. WebAssembly retains its original partial/transpiler classification as the requested exception.

Separate IR exporters and transpiler lowering were removed. Internal representations and machine-code emission inside retained compilers are necessary to compile source and remain. Native machine-code helper source files are not separate emitter products.

No compiler cache was added. No speed parity is certified by this cleanup. Full fresh self-compilation, edited source, tiny and large inputs, compiler modes, dependencies, output formats and retained targets remain required.

| Target | Kind | Availability |
|---|---|---|
| android | native | stale-cache-lineage |
| android/shared-object | native | stale-cache-lineage |
| apple/arm64_32 | native | experimental |
| apple/arm64e | native | experimental |
| apple/ios | native | experimental |
| apple/ios-simulator | native | experimental |
| apple/macos | native | experimental |
| apple/macos-arm64 | native | experimental |
| apple/tvos | native | experimental |
| apple/tvos-simulator | native | experimental |
| apple/visionos | native | experimental |
| apple/visionos-simulator | native | experimental |
| apple/watchos | native | experimental |
| apple/watchos-simulator | native | experimental |
| linux/arm64 | native | stale-cache-lineage |
| linux/arm64-shared-object | native | stale-cache-lineage |
| linux | native | reference-tested |
| operating-systems/dragonfly | native | experimental |
| operating-systems/freebsd | native | experimental |
| operating-systems/haiku | native | experimental |
| operating-systems/illumos | native | experimental |
| operating-systems/menuetos | native | experimental |
| operating-systems/netbsd | native | experimental |
| operating-systems/openbsd | native | experimental |
| operating-systems/qnx | native | experimental |
| operating-systems/redox | native | experimental |
| operating-systems/serenityos | native | experimental |
| operating-systems/sovrenos | native | experimental |
| webassembly/browser | transpiler | experimental |
| webassembly/component-model | partial | experimental |
| webassembly/edge | transpiler | experimental |
| webassembly/emscripten | transpiler | experimental |
| webassembly/wasm32-single-instruction-multiple-data | partial | experimental |
| webassembly/wasm32-threads-atomics | partial | experimental |
| webassembly/wasm32-unknown-unknown | partial | experimental |
| webassembly/wasm64-memory64 | partial | experimental |
| webassembly/webassembly-system-interface | partial | experimental |
| webassembly/webassembly-text | transpiler | experimental |
| windows | native | unbuildable (source drift) |
| windows/store | native | unbuildable (source drift) |

## Follow-up cleanup

Removed marker-only firmware/GPU/RTOS/transpiler directories, obsolete Linux compiler binaries and duplicate probe sources. The current target documents and launcher source list only retained targets. All ten WebAssembly variants remain by explicit user choice. The existing Linux launcher binary still needs rebuilding to reflect its edited source.
