# Sovren — handoff for the next agent

Read this first. Everything below was verified by a command that was actually run.

## Where the tree is

`/home/user/sovren` — no git. Working seed copy: `/home/user/seed-good.bin`.

Last verified green:

```
561 passed, 0 failed            (tests/all.sov)
builds: 1044  failures: 0       (174 libraries x 6 targets)
bootstrap clean
hello printed, exit 0
linux compiler 225080
```

176 libraries. **If you change nothing else, do not lose that green.**

## The loop — run this after any change

There is no `rb.sh` in this tree. Rebuild by hand. Mode bits do NOT survive between turns.

```bash
cd /home/user/sovren
chmod 755 sovren sovren-dbg sovren.exe compilers/*/compiler*

# never -o the running compiler. never cp over it without rm -f first.
rm -f /tmp/cc1 /tmp/cc2
./sovren compilers/linux/compiler.sov -o /tmp/cc1
chmod 755 /tmp/cc1
/tmp/cc1 compilers/linux/compiler.sov -o /tmp/cc2
chmod 755 /tmp/cc2
cmp /tmp/cc1 /tmp/cc2                    # must be silent (fixed point)
printf 'main:\n    print 1 + 1\n' > /tmp/t.sov
/tmp/cc2 /tmp/t.sov -o /tmp/t.bin && chmod 755 /tmp/t.bin && /tmp/t.bin   # must print 2
rm -f compilers/linux/compiler
cp /tmp/cc2 compilers/linux/compiler
chmod 755 compilers/linux/compiler

for p in macos/compiler windows/compiler android/compiler ios/compiler android-so/compiler-so; do
  case $p in android-so/compiler-so) src=compilers/android-so/compiler-so.sov ;;
             *) src=compilers/${p}.sov ;; esac
  rm -f /tmp/cnew
  ./sovren $src -o /tmp/cnew
  chmod 755 /tmp/cnew
  rm -f compilers/$p
  cp /tmp/cnew compilers/$p
  chmod 755 compilers/$p
done

./sovren bootstrap.sov -o /tmp/boot && chmod 755 /tmp/boot && /tmp/boot
# must print "bootstrap clean"

rm -f /tmp/allb
./sovren tests/all.sov -o /tmp/allb && chmod 755 /tmp/allb && /tmp/allb | tail -3
```

After changing `emit_alloc` (or anything that changes the compiler's own `_sov_alloc`), the first generation compiled by the old seed can differ from the second. Take the second, then prove g3 == g4.

Windows CI needs `compilers/windows/compiler.exe` (PE). Other PE/Mach-O host copies are rebuilt on demand: `./sovren <src> --windows -o <path>.exe` or `--mac -o <path>.macho`. The launcher still picks `.exe` / `.macho` from its own image magic when those files exist.

Windows `leave_handback` with `fn_save_n` 0 must emit `leave` (0xC9). A bare `pop rbp; ret` after `sub rsp, N` pops zeros and jumps to 0 (CI ACCESS_VIOLATION on `sovren.exe` with no args, which calls `_sov_argc`). Linux chmod must include `sovren-dbg`. Mac job ad-hoc signs then skips exit 137/126/134.

The 1044-build sweep (~3 min):

```bash
fail=0; n=0
for t in "" --windows --mac --android --ios --android-so; do
  for f in library/*.sov; do
    nm=$(basename "$f" .sov); case "$nm" in carm|cx86) continue;; esac
    printf 'use %s\nmain:\n print 1\n' "$nm" > /tmp/L.sov
    timeout 60 ./sovren /tmp/L.sov $t -o /tmp/L.bin >/dev/null 2>&1 \
      || { fail=$((fail+1)); echo "FAIL $nm ${t:-linux}"; }
    n=$((n+1))
  done
done; echo "SWEEP builds: $n  failures: $fail"
```

## The rule that will bite you first

**`compilers/linux/compiler` compiles `compilers/linux/compiler.sov`.** Recover:

```bash
rm -f compilers/linux/compiler
cp /home/user/seed-good.bin compilers/linux/compiler
chmod 755 compilers/linux/compiler
printf 'main:\n    print 1 + 1\n' > /tmp/t.sov
./sovren /tmp/t.sov -o /tmp/t.bin && chmod 755 /tmp/t.bin && /tmp/t.bin   # must print 2
```

## Shipped (all verified)

1. Atomics x86+ARM. Mutex+channel via `thread_slot`. x86 `_sov_alloc` exact size (`32\n32`). Thread-safe bump: `lock xadd` on x86 `emit_alloc`; `atomic_swap` in `runtime.sov`.
2. **#12 in `library/cx86.sov` (functions, no extra globals).** Back-end hooks stay per OS.
3. **ARM spawn on android + android-so.** iOS `spawn_emit` calls `_sov_thread_spawn`; `stmt_join_op` calls `_sov_thread_join`. mmap 9→197 and clone 56→360 in `_sov_sysnum`.
4. **Mac spawn is real.** `spawn_arg`/`spawn_finish` pack and `calln("_sov_thread_spawn")`. Clone is `bsdthread_create` (`_sov_mac_create`); join spins on the status word; fork stays as fallback. `stmt_join_op` calls `_sov_thread_join`.
5. `warn_unused` sees `fnaddr` / `fnaddr64`. Errors print `src_name` then `err_line`. Unknown names/tasks print `did you mean`.
6. Text-return: `seed_str_fns` plus return-of-text-local pass on linux. `idx` is exact (no shorter prefix win). `fuse_cmp` evaluates a call on either side once and uses the real operator width.
7. Windows host: PE copies of all six compilers + launcher `.exe` suffix. LICENSE no longer mentions `book.md`.
8. Linux main exit: `if rax_small … mov al,60` / `if not emit_sys_num(60)` / **then** `emit_sys_do()`.

**Adding functions to cx86.sov is safe. Adding globals is not.**

## Not done

`write_elf` / `emit_stack_wipe` / `call_args` / `copyargs` / `emit_print_int` are format/ABI, not copies. ARM `emit_alloc` keeps the 8-byte length header (`chk_mem` reads it). ELF has no section headers, so DWARF/CodeView are not in the image; `--debug` still records `dbg_pcs`/`dbg_lns`.

Still open (would add surface syntax): namespaces, closures, types, interpolation. Deliberately not: switch/match, defer, exceptions, generics, macros, reflection, overloading, GC.

## Language gotchas

- `if m is 1` / fallthrough is not else. Use `if not`.
- Keep the newline when deleting a task (`sysc()compile source:` is death).
- Never `-o` the running compiler. `rm -f` before `cp`.
- `--mac` not `--macos`. `thread_slot i` is 8 bytes.
- No python3 for project tooling.

## Standing instructions from the user

- Sovren only for tooling. No python3.
- Do not stop to ask or to narrate — do the work, report at the end.
- Do not write confessional recaps of what was not done. One or two lines maximum.
- Report only what a command returned.
- All 176 libraries stay. `./sovren hello.sov` must work with nothing installed.
- Memory model stays never-free plus `arena`.
- New syntax must not complicate the surface language.
- Do not add `tests/bench.sov` numbers to BOOK.md.
- Workspace budget: under 128 MB and 10,000 files.
