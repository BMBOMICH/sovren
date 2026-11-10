# Retained compiler availability

30 native compiler entries and all 10 WebAssembly variants are retained. Firmware, GPU/shader, RTOS, ancient evaluator, standalone IR and other transpiler targets are removed. WebAssembly browser/text variants are the explicit exception.

Only the Linux x86-64 native compiler has a built binary in the supplied project; the other 29 native binaries are absent. Ten WebAssembly driver binaries exist. The supplied binaries require Linux x86-64 as their compiler host. A target name does not establish a compiler that runs on that OS.

Full-language validation, fresh self-compilation and SA translation parity remain unfinished. No compiler cache was added. See CURRENT_SCOPE.md and compilers/registry.json.

| Target | Kind | Source | Driver binary | Availability |
|---|---|---|---|---|
| android | native | [compilers/android/compiler.sov](compilers/android/compiler.sov) | missing | stale-cache-lineage |
| android/shared-object | native | [compilers/android/shared-object/compiler.sov](compilers/android/shared-object/compiler.sov) | missing | stale-cache-lineage |
| apple/arm64_32 | native | [compilers/apple/arm64_32/compiler.sov](compilers/apple/arm64_32/compiler.sov) | missing | experimental |
| apple/arm64e | native | [compilers/apple/arm64e/compiler.sov](compilers/apple/arm64e/compiler.sov) | missing | experimental |
| apple/ios | native | [compilers/apple/ios/compiler.sov](compilers/apple/ios/compiler.sov) | missing | experimental |
| apple/ios-simulator | native | [compilers/apple/ios-simulator/compiler.sov](compilers/apple/ios-simulator/compiler.sov) | missing | experimental |
| apple/macos | native | [compilers/apple/macos/compiler.sov](compilers/apple/macos/compiler.sov) | missing | experimental |
| apple/macos-arm64 | native | [compilers/apple/macos-arm64/compiler.sov](compilers/apple/macos-arm64/compiler.sov) | missing | experimental |
| apple/tvos | native | [compilers/apple/tvos/compiler.sov](compilers/apple/tvos/compiler.sov) | missing | experimental |
| apple/tvos-simulator | native | [compilers/apple/tvos-simulator/compiler.sov](compilers/apple/tvos-simulator/compiler.sov) | missing | experimental |
| apple/visionos | native | [compilers/apple/visionos/compiler.sov](compilers/apple/visionos/compiler.sov) | missing | experimental |
| apple/visionos-simulator | native | [compilers/apple/visionos-simulator/compiler.sov](compilers/apple/visionos-simulator/compiler.sov) | missing | experimental |
| apple/watchos | native | [compilers/apple/watchos/compiler.sov](compilers/apple/watchos/compiler.sov) | missing | experimental |
| apple/watchos-simulator | native | [compilers/apple/watchos-simulator/compiler.sov](compilers/apple/watchos-simulator/compiler.sov) | missing | experimental |
| linux/arm64 | native | [compilers/linux/arm64/compiler.sov](compilers/linux/arm64/compiler.sov) | missing | stale-cache-lineage |
| linux/arm64-shared-object | native | [compilers/linux/arm64-shared-object/compiler.sov](compilers/linux/arm64-shared-object/compiler.sov) | missing | stale-cache-lineage |
| linux | native | [compilers/linux/compiler.sov](compilers/linux/compiler.sov) | present | reference-tested |
| operating-systems/dragonfly | native | [compilers/operating-systems/dragonfly/compiler.sov](compilers/operating-systems/dragonfly/compiler.sov) | missing | experimental |
| operating-systems/freebsd | native | [compilers/operating-systems/freebsd/compiler.sov](compilers/operating-systems/freebsd/compiler.sov) | missing | experimental |
| operating-systems/haiku | native | [compilers/operating-systems/haiku/compiler.sov](compilers/operating-systems/haiku/compiler.sov) | missing | experimental |
| operating-systems/illumos | native | [compilers/operating-systems/illumos/compiler.sov](compilers/operating-systems/illumos/compiler.sov) | missing | experimental |
| operating-systems/menuetos | native | [compilers/operating-systems/menuetos/compiler.sov](compilers/operating-systems/menuetos/compiler.sov) | missing | experimental |
| operating-systems/netbsd | native | [compilers/operating-systems/netbsd/compiler.sov](compilers/operating-systems/netbsd/compiler.sov) | missing | experimental |
| operating-systems/openbsd | native | [compilers/operating-systems/openbsd/compiler.sov](compilers/operating-systems/openbsd/compiler.sov) | missing | experimental |
| operating-systems/qnx | native | [compilers/operating-systems/qnx/compiler.sov](compilers/operating-systems/qnx/compiler.sov) | missing | experimental |
| operating-systems/redox | native | [compilers/operating-systems/redox/compiler.sov](compilers/operating-systems/redox/compiler.sov) | missing | experimental |
| operating-systems/serenityos | native | [compilers/operating-systems/serenityos/compiler.sov](compilers/operating-systems/serenityos/compiler.sov) | missing | experimental |
| operating-systems/sovrenos | native | [compilers/operating-systems/sovrenos/compiler.sov](compilers/operating-systems/sovrenos/compiler.sov) | missing | experimental |
| webassembly/browser | transpiler | [compilers/webassembly/browser/compiler.sov](compilers/webassembly/browser/compiler.sov) | present | experimental |
| webassembly/component-model | partial | [compilers/webassembly/component-model/compiler.sov](compilers/webassembly/component-model/compiler.sov) | present | experimental |
| webassembly/edge | transpiler | [compilers/webassembly/edge/compiler.sov](compilers/webassembly/edge/compiler.sov) | present | experimental |
| webassembly/emscripten | transpiler | [compilers/webassembly/emscripten/compiler.sov](compilers/webassembly/emscripten/compiler.sov) | present | experimental |
| webassembly/wasm32-single-instruction-multiple-data | partial | [compilers/webassembly/wasm32-single-instruction-multiple-data/compiler.sov](compilers/webassembly/wasm32-single-instruction-multiple-data/compiler.sov) | present | experimental |
| webassembly/wasm32-threads-atomics | partial | [compilers/webassembly/wasm32-threads-atomics/compiler.sov](compilers/webassembly/wasm32-threads-atomics/compiler.sov) | present | experimental |
| webassembly/wasm32-unknown-unknown | partial | [compilers/webassembly/wasm32-unknown-unknown/compiler.sov](compilers/webassembly/wasm32-unknown-unknown/compiler.sov) | present | experimental |
| webassembly/wasm64-memory64 | partial | [compilers/webassembly/wasm64-memory64/compiler.sov](compilers/webassembly/wasm64-memory64/compiler.sov) | present | experimental |
| webassembly/webassembly-system-interface | partial | [compilers/webassembly/webassembly-system-interface/compiler.sov](compilers/webassembly/webassembly-system-interface/compiler.sov) | present | experimental |
| webassembly/webassembly-text | transpiler | [compilers/webassembly/webassembly-text/compiler.sov](compilers/webassembly/webassembly-text/compiler.sov) | present | experimental |
| windows | native | [compilers/windows/compiler.sov](compilers/windows/compiler.sov) | missing | unbuildable (source drift) |
| windows/store | native | [compilers/windows/store/compiler.sov](compilers/windows/store/compiler.sov) | missing | unbuildable (source drift) |

Earlier target-space inventories and obsolete compiler snapshots are recoverable from the Desktop backups. Current sources retain internal machine-code emission and parsing structures needed to compile source.

The launcher source contains only retained target routes. Its existing Linux executable requires a later rebuild to reflect the source cleanup; no Linux compiler was executed during this cleanup.
