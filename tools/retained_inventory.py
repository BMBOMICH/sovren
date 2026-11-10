"""Current retained source inventory. This does not certify execution or speed."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def entries():return json.loads((ROOT/'compilers/registry.json').read_text(encoding='utf-8'))['entries']
def document(title):
    lines=['# '+title,'','30 native compiler entries and all 10 WebAssembly variants are retained. Firmware, GPU/shader, RTOS, ancient evaluator, standalone IR and other transpiler targets are removed. WebAssembly browser/text variants are the explicit exception.','', 'Only the Linux x86-64 native compiler has a built binary in the supplied project; the other 29 native binaries are absent. Ten WebAssembly driver binaries exist. The supplied binaries require Linux x86-64 as their compiler host. A target name does not establish a compiler that runs on that OS.','', 'Full-language validation, fresh self-compilation and SA translation parity remain unfinished. No compiler cache was added. See CURRENT_SCOPE.md and compilers/registry.json.','', '| Target | Kind | Source | Driver binary | Availability |','|---|---|---|---|---|']
    for e in entries():
        state='present' if (ROOT/e['executable']).is_file() else 'missing'
        lines.append('| '+e['id']+' | '+e['kind']+' | ['+e['source']+']('+e['source']+') | '+state+' | '+e['availability']+' |')
    lines += ['', 'Earlier target-space inventories and obsolete compiler snapshots are recoverable from the Desktop backups. Current sources retain internal machine-code emission and parsing structures needed to compile source.','', 'The launcher source contains only retained target routes. Its existing Linux executable requires a later rebuild to reflect the source cleanup; no Linux compiler was executed during this cleanup.']
    return '\n'.join(lines)+'\n'
