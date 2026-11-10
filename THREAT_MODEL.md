# Sovren threat model — "most private" means this, measurably

"Most private in everything/everywhere" is only meaningful per adversary. The
channels: tool<->disk, tool<->network, tool<->environment, artifact->builder,
program<->local observer, program<->remote parties, ecosystem->third parties.

| adversary | guarantee | status |
|---|---|---|
| Remote parties (network endpoints) | compiler+runtime open no socket; opt-in network only via http/sock/tls libraries, never by default | verified (privacy_gate: closure scan + artifact syscall scan) |
| The build machine's owner (forensics) | no telemetry, no phone-home, builds deterministic, caches local + documented; sidecars (.ac .lsug .deep .deepoc) hold derived data next to inputs, purgeable via prvpurge | verified; purge shipped |
| Whoever inspects the artifact | no absolute build paths, no builder-fingerprint strings, byte-identical rebuilds (reproducibility makes "same source?" checkable) | verified by gate on fresh builds |
| Process memory inspection / core dumps | secret_wipe_bytes + secret_harden (MADV_DONTDUMP/WIPEONFORK) + secret_noswap (mlock) + secret_lockdown (prctl PR_SET_DUMPABLE 0) + secret_scrub_argv/env | implemented in library/secret.sov; opt-in per program |
| Local malware / root | BOUNDED BY THE OS. No language can protect a process's memory from root; sovren reduces residual surface (zeroing, dump-off, noswap) but this channel is documented, not solvable | documented boundary |
| Microsoft (Store distribution) | Store metadata/account/diagnostics handled by Microsoft under their policy; outside sovren's control; disclosed in PRIVACY.md | documented boundary |
| Future supply chain | no package manager, dependency-free default; any future manager must be opt-in + auditable | policy |

OutOf scope by physics: hardware keyloggers, DMA attacks, EM side channels.
Crypto timing: aes.sov computes GF math (no secret-indexed tables), chacha20 is
ARX, poly1305 arithmetic, tag compares go through constant.sov ct_eq (suite
tested). ed25519's early-exit is on the PUBLIC signature only.
