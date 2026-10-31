# transpilers

This directory contains real files, not directory symlinks. Transpiler implementations live under top-level `transpilers/`; `backends/transpilers/` contains shared lowering and compatibility entry points. Other backend implementations live in their respective `backends/` families. Installed binaries remain under `compilers/` for existing launchers.

The authoritative inventory is `backends/registry.json`. No incomplete implementation is renamed to claim completeness.

| Backend | Availability |
|---|---|
| [c-language](c-language/compiler.sov) | validated-subset |
| [csharp](csharp/compiler.sov) | experimental |
| [extended-berkeley-packet-filter](extended-berkeley-packet-filter/compiler.sov) | experimental |
| [firmware/intel-hex](firmware/intel-hex/compiler.sov) | experimental |
| [firmware/s-record](firmware/s-record/compiler.sov) | experimental |
| [graphics-processing-units/amd-graphics-core-next](graphics-processing-units/amd-graphics-core-next/compiler.sov) | experimental |
| [graphics-processing-units/high-level-shading-language](graphics-processing-units/high-level-shading-language/compiler.sov) | experimental |
| [graphics-processing-units/intel-xe](graphics-processing-units/intel-xe/compiler.sov) | experimental |
| [graphics-processing-units/msl](graphics-processing-units/msl/compiler.sov) | experimental |
| [graphics-processing-units/opengl-shading-language](graphics-processing-units/opengl-shading-language/compiler.sov) | experimental |
| [graphics-processing-units/parallel-thread-execution](graphics-processing-units/parallel-thread-execution/compiler.sov) | experimental |
| [graphics-processing-units/webgpu-shading-language](graphics-processing-units/webgpu-shading-language/compiler.sov) | experimental |
| [javascript](javascript/compiler.sov) | validated-subset |
| [real-time-operating-systems/chromium-ec](real-time-operating-systems/chromium-ec/compiler.sov) | experimental |
| [real-time-operating-systems/embos](real-time-operating-systems/embos/compiler.sov) | experimental |
| [real-time-operating-systems/freertos](real-time-operating-systems/freertos/compiler.sov) | experimental |
| [real-time-operating-systems/mbed](real-time-operating-systems/mbed/compiler.sov) | experimental |
| [real-time-operating-systems/nuttx](real-time-operating-systems/nuttx/compiler.sov) | experimental |
| [real-time-operating-systems/riot](real-time-operating-systems/riot/compiler.sov) | experimental |
| [real-time-operating-systems/rt-thread](real-time-operating-systems/rt-thread/compiler.sov) | experimental |
| [real-time-operating-systems/threadx](real-time-operating-systems/threadx/compiler.sov) | experimental |
| [real-time-operating-systems/ti-rtos](real-time-operating-systems/ti-rtos/compiler.sov) | experimental |
| [real-time-operating-systems/zephyr](real-time-operating-systems/zephyr/compiler.sov) | experimental |
| [typescript](typescript/compiler.sov) | validated-subset |
| [webassembly/browser](webassembly/browser/compiler.sov) | experimental |
| [webassembly/edge](webassembly/edge/compiler.sov) | experimental |
| [webassembly/emscripten](webassembly/emscripten/compiler.sov) | experimental |
| [webassembly/webassembly-text](webassembly/webassembly-text/compiler.sov) | experimental |
