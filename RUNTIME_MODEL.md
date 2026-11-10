# Runtime model — allocator, GC, and what "automatic" should mean here

## What sovren has today (verified in `runtime.sov`)

There is **no garbage collector**. Memory management is a manual, size-classed
allocator with per-class free lists, plus an opt-in bump arena.

```
rt_heap / rt_init                      bootstrap the metadata region
_sov_small_region  (runtime.sov:137)   16-byte units, 2 MB regions, per-class free list
_sov_small_try / _sov_alloc_small      pop free list, else carve
_sov_free_small                        push back onto the class free list
_sov_med_region    (runtime.sov:206)   4096-byte pages, free list indexed by page
_sov_med_try / _sov_alloc_med          pop free list, else carve
_sov_free_med                          push back
_sov_alloc_large   (runtime.sov:266)   direct mmap
_sov_free_large                        munmap
_sov_fast_alloc   (runtime.sov:290+)   single-threaded, no-context, size<=1024 fast path
_sov_heap_alloc / _sov_alloc           general path / public pass-through
_sov_arena_new / _sov_arena_alloc / _sov_arena_destroy  (runtime.sov:422-446)
_sov_free / _sov_realloc / _sov_heap_wipe
```

Allocation census from the e_run corpus: **1,759,867 allocations** for a
147 KB source, of which `_sov_strcat` accounts for 525,650 and `_sov_list_add`
for 509,387. That is ~12 allocations per input byte, and it is the main reason
the compiler is slow.

## Is this the best choice?

**For sovren's target set, yes — manual allocation is the correct default.**

Sovren builds kernels, bootloaders, firmware, `#![no_std]`-style bare-metal
targets and standalone binaries with no runtime dependency. A tracing GC is
wrong for all of those: it needs a runtime, a write barrier on every pointer
store, and it pauses. C, Rust and Zig all make the same choice.

**But "manual" and "no automatic option" are not the same thing, and sovren
currently only has the second.** The pieces for an automatic mode already exist
as libraries (`arena.sov`, `kdefer.sov`); they are simply not exposed as a
language mode.

## What to add, in order

### 1. Opt-in region/arena mode (highest value, lowest risk)

```
region:
    p: alloc(4096)
    ...
# everything allocated in the region is freed here, automatically
```

A region is a bump pointer with no per-object free. It makes allocation
O(1) with no free-list search, and it makes "automatic" true by construction:
the region dies at the closing brace. This is what `arena.sov` already does;
the work is to make it a *scoped language construct* rather than a library
call, and to route `alloc`/`_sov_heap_alloc` through the active region.

Expected effect: removes most of the 1.76M allocations' cost, because a bump
pointer is ~4 instructions versus the current free-list/carve path.

### 2. `defer` as a language construct

`kdefer.sov` exists. Promote it to a keyword so that:

```
task main:
    p: alloc(64)
    defer -> _sov_free(p)
```

gives deterministic, scope-bound, automatic reclamation without a GC. This is
Zig's model and it is the right one for a systems language.

### 3. An ownership/escape lint (not an enforcement pass)

A warning-only analysis: "value returned by `alloc` may leak here", "pointer to
`p` escapes the region", "double free possible on this path". Warnings, never
errors, so no existing program breaks. This is the cheapest possible step
toward memory safety and it needs no runtime at all.

### 4. Optional deferred reference counting (opt-in, per type)

Only for programs that want it, and only reachable from safe code. A RC header
of 4 bytes, incremented on copy, decremented on scope exit, with a cycle
collector run on demand. This gives automatic reclamation for the 90% of
programs that do not care about the last 10% of performance.

Explicitly **not** recommended: a tracing mark-sweep GC as the default. It is
the wrong default for this target set and it would be a large, permanent tax on
every binary.

## Verdict

| question | answer |
|---|---|
| Do we use an allocator or a GC? | A manual size-classed allocator with free lists, plus an opt-in bump arena. **No GC.** |
| Is it the best? | The allocator is good and the *choice* of manual-by-default is right for the target set. |
| Is it automatic? | **No.** Freeing is manual; the only automatic reclamation is process exit or `_sov_heap_wipe`. |
| What is missing | A scoped region construct, `defer` as a keyword, an ownership lint, and an opt-in RC mode. |
