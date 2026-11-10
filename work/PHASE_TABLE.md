# Post-audit phase table (2026-11-09, compiler 678747567b1af3a3)

Fresh `--prof` runs, one call each, instrumented endpoint-aggregates (mark = endpoint-delta; ns lands in the bucket of the mark).

|---|---|---|---|---|
| phase | self (254.9 ms) | all.sov (52.8 ms) | x86ins (16.9 ms) | what it is |
| `bw` | 136.6 ms / 53.6% | 26.3 ms / 49.8% | 8.7 ms / 51.6% | per-task body statement codegen (interpreted lowering) |
| `W-walk0` | 32.0 ms / 12.6% | 6.3 ms / 12.0% | 3.2 ms / 18.8% | the task walk |
| `C1` | 23.9 ms / 9.4% | 5.0 ms / 9.5% | 1.2 ms / 7.2% | pu_lines, the line reader |
| `c0-parsed` | 22.7 ms / 8.9% | 4.9 ms / 9.3% | 2.2 ms / 12.9% | parse |
| `2-all-spliced` | 5.6 ms / 2.2% | 3.8 ms / 7.2% | 0.6 ms / 3.5% | runtime + chunk + source splice |
| `p-stub` | 7.2 ms / 2.8% | 1.3 ms / 2.4% | 0.1 ms / 0.7% | stub_diet |
| `pu` | 5.7 ms / 2.2% | 2.2 ms / 4.1% | 0.3 ms / 1.5% | pull_uses, chunk loading |
| `4-compiled` | 6.9 ms / 2.7% | 0.7 ms / 1.4% | 0.0 ms / 0.3% | final codegen |
| `3-scanned` | 3.1 ms / 1.2% | 0.9 ms / 1.8% | 0.2 ms / 1.3% | u_scan + u_prep |
| `pre-u` | 3.1 ms / 1.2% | 0.2 ms / 0.4% | 0.1 ms / 0.8% | pre-pass probe |
| `5a-flat0` | 2.8 ms / 1.1% | 0.4 ms / 0.7% | 0.0 ms / 0.2% | ELF flat emission, relocations |
| `p-dce` | 1.9 ms / 0.7% | 0.2 ms / 0.4% | 0.0 ms / 0.2% | prune_dead |
| `1-rt-loaded` | 1.4 ms / 0.5% | 0.3 ms / 0.6% | 0.1 ms / 0.5% |  |
| `z-end` | 0.7 ms / 0.3% | 0.2 ms / 0.3% | 0.0 ms / 0.2% |  |
| `f3-sug` | 0.6 ms / 0.2% | 0.0 ms / 0.0% | 0.0 ms / 0.1% |  |
| `5b-pat` | 0.6 ms / 0.2% | 0.0 ms / 0.1% | 0.0 ms / 0.0% |  |
| `C0b` | 0.0 ms / 0.0% | 0.0 ms / 0.1% | 0.0 ms / 0.1% |  |
| `p-post` | 0.0 ms / 0.0% | 0.0 ms / 0.0% | 0.0 ms / 0.0% |  |
| `C0` | 0.0 ms / 0.0% | 0.0 ms / 0.0% | 0.0 ms / 0.0% |  |
| `aa` | 0.0 ms / 0.0% | 0.0 ms / 0.0% | 0.0 ms / 0.0% |  |
| `Wq1` | 0.0 ms / 0.0% | 0.0 ms / 0.0% | — |  |
| `Wq2` | 0.0 ms / 0.0% | — | — |  |
| `p-wend` | 0.0 ms / 0.0% | 0.0 ms / 0.0% | 0.0 ms / 0.0% |  |
| `Wq3` | 0.0 ms / 0.0% | — | — |  |
| `sug` | 0.0 ms / 0.0% | 0.0 ms / 0.0% | 0.0 ms / 0.0% |  |
| `W-entry-done` | 0.0 ms / 0.0% | 0.0 ms / 0.0% | 0.0 ms / 0.0% |  |
