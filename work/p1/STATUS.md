# Current Linux compiler: P0 completed; first measured P1 improvement qualified

## Installed artifact
`compilers/linux/compiler` = `work/p1/spans.g2`.
SHA256: `801b21d88dddba0c0f3742ff982ae3a2b8561361c90a701f8774cba994e4fed2`.
The ordinary self-host generations are byte-identical. Linux launcher/debugger binaries were rebuilt and installed too.

## First optimization after P0
The profiler identified repeated complete-source NUL scans in the safety scanner. Each candidate line called `cut(source, start, end)`, even though the enclosing scanner already knows the complete source bound. It now passes that bound to `cutn`.

This is use of the current source's existing span length, **not caching**: no prior translation, syntax result or emitted artifact is saved/replayed. Scanner results and unmarked-access counts match the exact frozen P0 implementation on **521 boundary/annotation fixtures**.

### Measured operation reduction
For the all-suite input, covered native reads in the safety-scan interval fell from **504,467,256 to 1,798,960 bytes**. Total covered scan reads fell from **529,769,138 to 27,100,842 bytes**. For x86ins, safety-scan reads fell from **26,016,808 to 427,752 bytes**. These counters have explicit implementation coverage; they are not estimates of all memory traffic.

### Ordinary translation timings
21 rotating fresh-process rounds on identical current inputs; old and new emitted artifacts must be byte-identical on **every** round. Timing excludes execution checking. Raw samples, quartiles, artifact/source hashes, host and affinity are in `ab-speed.json`.

| Workload | P0 median | Current median | P0/current |
|---|---:|---:|---:|
| x86ins | 19.037 ms | 17.043 ms | 1.117× |
| all-suite source | 73.522 ms | 50.391 ms | 1.459× |
| compiler self-source | 129.585 ms | 129.383 ms | 1.002× |

The self-source result is effectively unchanged, not a claimed improvement. Small matched-work latency measurements are also published without cherry-picking: current medians were 0.831/0.871/3.650 ms vs P0 0.778/0.820/3.591 ms on exit7/sum/calls. Shared-host noise is not a production confidence interval. SA remains substantially faster; **no parity claim** is made.

## Current qualification
`ACCEPTANCE.json` records 14 passing current-candidate checks:
- **103/103 focused checks** on both ordinary and instrumented compiler builds.
- **2,096 exact scan alignment/length profiler oracles**, plus exact allocator/copy counts.
- **521 safety-scanner differential fixtures** against the frozen P0 implementation.
- Four ordinary/instrumented profile workload outputs byte-identical, with per-endpoint counters and source ownership.
- Executed syscall policy including worker children; no-cache guards; 5/5 correctness battery and 5/5 timing harness unit tests.
- Full suites unchanged from completed P0: all **310/91**, fast **307/82/12 not run**, both rc1. All residual failed assertion names remain explicitly non-Linux in the scope ledger. They have not been made green or silently suppressed.

## Reproduction and evidence
- `tools/p0_gate.py`: current Linux regressions/fixed point, never installs its candidate.
- `tools/profile_gate.py`: builds a separate untimed instrumented compiler and verifies exact counters plus artifact identity; use `--workdir`/`--output` to keep new evidence separate.
- `tools/linux_syscall_gate.py`: native syscall trace qualification, including workers.
- `tools/p1_span_gate.py`: scanner boundary/annotation differential tests.
- `tools/ab_speed.py`: rotating A/B measurement with artifact equality required every round.
- `tools/paired_workloads.py`: matched-observable-work latency checks; execution verified every round.
- `implementation.patch` and `changed-files.json`: complete current overlay against untouched `/home/user/downloads/sovren`.
- `input-manifest.json`: exact current source/tool/binary pins. Frozen P0 evidence and its source snapshot remain under `work/p0/`.

## Remaining performance work
This removes one measured quadratic scanning cost. It does **not** implement the remaining lower-once/token syntax, semantic function records, compact lowering/native hot-loop or source/reference-graph work, and does not establish that the backlog is exhaustive. Those representation changes remain the next large performance priorities. No new caching, and no unsupported sufficiency or speedup promises.
