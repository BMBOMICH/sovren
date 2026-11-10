> v58 layout correction: sources now physically reside in the organized folders. Directory links were not durable. See `docs/architecture/README.md`; the older view-only description below is superseded. Backend completeness remains unfinished.

# Fastest credible route to complete semantics and measured SA parity

This is an execution plan, not a claim that universal parity has been reached.

## What “full backend” means

You are not misunderstanding: a backend advertised as a full Sovren compiler must implement the required language semantics, not merely emit a valid-looking file. Rebuilding its compiler source proves only that the implementation builds. The old evaluator, placeholder and partial-writer implementations do not satisfy that requirement.

Transpilers are compilers too, but a separate discoverable `transpilers/` view is useful. This release adds that view, an `emitters/` view for evaluator/partial mechanisms, and one machine-readable backend registry. Existing `compilers/` paths stay canonical for compatibility with launchers and numbered includes; no binary/source copies are introduced. A directory name never grants semantic certification.

“Full language” needs a versioned language contract. Some targets cannot offer hosted file/process/OS services directly; such capabilities need a target runtime or an explicit, checked unsupported diagnostic. They must not be silently dropped or credited as successful translations. No finite suite proves every program correct, but a construct-by-construct conformance contract, differential testing and explicit limitations make the claim auditable.

## Do less duplicated work, not less validation

1. **One contract and corpus.** Store source, expected output/exit behavior, required features and runtime dependencies once. Reuse it for native backends, transpilers, interpreters, emulators and hardware. Do not maintain 155 divergent parser tests.
2. **One structured frontend and lowered representation per language version.** Share lexical boundaries, declaration IDs, expression trees, control flow and source locations. Thin target adapters own ABI, instruction/source emission and object/container writing. v57 implements that consolidation for the supported C, JavaScript and TypeScript subset, including structured SIR before lowering; it does not replace the whole native frontend.
3. **Reuse reliable downstream toolchains where they help.** A correct C or IR route can cover many hosted targets sooner than writing 155 independent instruction selectors. The registry must name both stages, their versions and runtime requirements. End-to-end timings include downstream compilation/linking. Do not relabel a C emitter as 155 working native backends.
4. **Generate adapters and capability indexes from the registry.** Do not hand-maintain parallel target inventories or duplicate sources under new folders. Existing launcher paths remain working during migration.
5. **Batch correctness, isolate measurements.** Build independent drivers/tests in bounded parallel workers with unique scratch directories. Batch TypeScript type checking where possible. Run latency measurements serially on an otherwise idle host with alternating paired order. Parallel benchmark processes produce unreliable speed comparisons.
6. **Change-impact scheduling.** A parser/runtime change runs every dependent backend's conformance suite. A writer-only change runs format checks, affected ABI/runtime tests and representative frontend tests. Final release gates still run the complete required matrix. Never reuse a green result if any bound source, dependency, compiler or toolchain hash changed.
7. **Counterexample first.** Every bug gets a minimized failing fixture before the fix. Native behavior is a differential oracle, not unquestionable truth; expected language behavior is recorded separately. Rejected, skipped and missing-tool cases are separate from passes.
8. **Use a single final release pass.** Keep staged candidates out of installed paths until focused semantic/reproducibility checks pass. Freeze source once, rebuild the affected dependency closure, then run the complete gate and package once. Avoid regenerating every report/archive after each small edit.

## Parallel work lanes and dependencies

| Lane | Concrete work | Gate before integration |
|---|---|---|
| Contract and test infrastructure | Versioned constructs/semantics; required workload/host/target matrix; explicit unsupported and skipped states; generated registry | Missing required cells fail, not skip-to-green; no aggregate averages |
| Shared frontend | Token/span descriptors; stable IDs; checked name tables; canonical expressions/statements; source maps | Corpus plus generated differential tests; exact native bootstrap where applicable |
| Runtime and semantics | Integers, strings, collections, memory, calls, closures if specified, errors, modules, OS capabilities | Construct-by-construct executable tests and dependency/ABI coverage |
| C/JS/TS lowering | Shared structured parser; proper runtime loops; calls/forward declarations; integer semantics; safe output writing | Host C compilation, Node execution, actual TypeScript compilation, explicit oracle results |
| Native emission | Use current profile to select hot expression/argument/frame/relocation paths; lower once and reuse metadata | Same artifacts where intended, runtime equivalence, fresh fixed point, paired measurements |
| Cold edits (no cache) | Every edit rebuilds from a fully cold process; there is no dependency graph, no per-function summaries, no relocation/address invalidation and no persisted state | Byte-identical output and identical executed behaviour for one-character/whitespace/body/size/signature/global/import/compiler/flag edits, consecutive edits, interrupted writes and failure injection; cold-vs-warm is never a speed claim |
| Host and target coverage | Host runtime abstraction; portable fallback; real CI runners/emulators; ABI and container validators | Actual execution on each claimed host/target, never just generated headers |
| Release | Registry/source/binary binding; deterministic builds; immutable benchmark reference; full required matrix | All required cells green, no unresolved semantic blockers |

The contract/shared representation is the critical path. Target adapter work can proceed concurrently once that representation and runtime ABI are frozen. Performance work cannot treat incomplete semantics as a fast implementation.

## Ordered acceptance milestones

### A — Eliminate false success

Keep the repaired 155-source rebuild fleet and existing cache/replay gates. Remove source-size truncation and silent unsupported-statement dropping in transpilers. Preserve requested outputs or fail and remove incomplete/stale destinations. Attach rejection reasons to unsupported features.

### B — Establish semantic coverage by target family

Start with a genuine, explicit shared subset and expand it in this order: numeric expressions and control flow; function/parameter/return behavior; text and collections; modules and globals; structured data/memory; runtime/OS interfaces. Unsupported features remain red in the full-language matrix until implemented. Replace evaluator/placeholder routes family by family, validating actual execution, not just probe diversity.

### C — Optimize the real cold pipeline

Collect self-build, library-heavy, expression/call/string/sugar-heavy, all-reachable and large-dependency profiles. Rank exclusive work and allocation costs. Optimize measured repeats using descriptors, checked IDs, append buffers and incremental relocation data. Keep existing prune-list handoff and removed duplicate sugar pass; do not count them again. Test startup separately from large-input throughput/RSS.

### D — Edited, identical and parallel builds

Use one-character/whitespace/body/size/signature/global/import/compiler/flag changes and consecutive edits. Compare every requested artifact and runtime result against a cold build. Add failure injection for workers, pipes and writes; validate descriptor cleanup and fallback before threshold changes. Include read-only cache paths, eviction, large artifacts and concurrent writers. Cold OS caches require controlled host facilities, not an unsupported label on `--uncached`.

### E — Actual host/target validation

Keep host architecture, output architecture, ABI, runtime and filesystem separate in the registry. Use real Linux/Windows/macOS/ARM runners where available, plus appropriate validators/emulators. Missing runners are explicit blockers, not measurements invented from this Linux x86-64 machine.

### F — Require per-cell parity and deploy

For each required workload/size/mode/backend/host, validate semantics before timing. Fresh application, fully uncached, identical, edited and downstream end-to-end rows are distinct. Freeze SA's fingerprint and matched observable task; require upper 95% paired latency ratio ≤ 1 and lower throughput ratio ≥ 1 for every required cell. Preserve raw samples and use repeated confirmation runs; source-byte rates across different languages are diagnostic, not proof of equivalent frontend work. Unknown or absent cells fail global completion.

## Hard constraints that still exist

A request for unlimited resources cannot provide missing hardware, runners or toolchains. Do not claim remote execution without it. Keep generated build artifacts in `/tmp`, preserve the workspace under 100 MB/8,000 files for safety, and keep ample headroom under the 128 MB/10,000-file persistence ceiling. No fixed finish date is defensible until the full-language contract, target-runtime requirements and runner matrix are agreed and the remaining profiles are measured.
