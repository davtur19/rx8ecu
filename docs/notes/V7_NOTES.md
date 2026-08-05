# v7 SH-2 call-composition — selection findings (session notes)

## pool_v5 measurement (open question resolved)

The previous session's "~74 pool_v5 candidates (functions rejected ONLY for `call`,
targets resolvable + already lifted)" does NOT reproduce against the current
catalog + lifted-state.  Concrete counts (faithful re-scan, `tmp/analyze_*`):

### v4 flow (the real selector `select_fpu` universe; catalog-end only, sanitized span)
- call-rejected total                        = 135  (matches dryrun `rejected_call` v4)
- full-span scan passes with calls admitted  = 112
  - jmp-only (tail jumps, no jsr/bsr)        = 109
  - composable (has >=1 jsr/bsr)             = 3    (0x8B8, 0x17B24, 0x56F10)
      - only 2 have jsr/bsr targets resolvable-to-literal; their callees
        (0x8CC/0x8F6/0x4E0/0x1038) are NOT already lifted.
- pools: composable-with-already-lifted-callees = **3** (all tail-jmp ->
  0x03EE58 / 0x03EE68, already lifted as updateMemoryAtAddress_*bit*).

### v3 flow (with no-span estimated ends, the v3 selector universe)
- call-rejected total = 626 (matches v3 dryrun `rejected_call` written)
- jmp-only 121, composable 9, reject-after-call 496.

### Prefix definition (scan stops at first call; only first call target matters)
- v4: 32 candidates whose FIRST call is a jmp @r 0x03EE58/0x03EE68 (already lifted).

## Conclusions
- The genuinely composable jsr/bsr call pool is tiny: **9 (v3-est) / 3 (v4-cat)**,
  NOT ~74.
- The 626-vs-74 gap came from the v3 selector counting no-span candidates that are
  dropped entirely in v4.
- To lift any composable caller, the callee must be re-generated as a NEW
  `c/lib/f_<hex>.c` (state-struct ABI); most callees contain nested calls ->
  recursive composition needed (depth guard).
- Smallest reliably-composable cohort = the tail jump family to
  `updateMemoryAtAddress_8bit_3ee58` / `_16bit_3ee68` (simple leaf callees,
  already lifted + re-emittable).

## v7 design (state-struct)
- Shared `ST { r[16], pr, T, macl, mach, sr, gbr, fpul, fpscr; ram/stack assembly }`.
- Callee: `void f_<hex>(ST *s)` — reads args from `s->r[4..5]`, returns `s->r[0]`.
- Caller: `void caller_<addr>(ST *s)`; call site emits
  `s->pr = <retaddr>; <delay slot>; f_<callee>(s);`
- Tail jmp: emit `f_<callee>(s); return;` (no pr set).
- r8..r14 callee-clobber without save -> mismatch -> drop caller.

## Blockers / scope notes
- callee-struct/C emission + merged-mirror test is large; implemented only for the
  tail-call leaf cohort so far.  Full recursive jsr/bsr composition is the next
  milestone.
## 2026-08-05 session — v7 implemented and diff-verified (28/28 PASS)

Implemented `tools/gen_c_lift_v7.py` (new, standalone tool — pool_v5 selector +
ST callee lib + caller composition + composition differential test).

- `ST` ABI callee emission (`c/lib/f_<hex>.c`, `void f_X(ST *s)`): re-emits any
  call-free span from the v3 walker with register/system tokens rewritten to
  `s->r[N]`/`s->pr`/`s->T`...; compile-gated (`cc -O2 -c`, deletes on failure).
  Verified ST-ABI vs original lift ABI over 5000 random inputs: identical r0 +
  memory (seed 42) for f_3EE58.
- Caller emission (`--compose 0xADDR`): `caller_<hex>.c` — jsr/bsr ->
  `s->pr=pc+4; <delay slot>; f_<callee>(s);` (pr set BEFORE slot, per HW); tail
  jmp -> `f_<callee>(s); return;`.  Forward-declares callees, compile-gates.
- Chain-validated strict pool_v5: **= 0** in both flows — every jsr/bsr
  caller's callee chain hits at least one un-liftable leaf (base_unresolved /
  no_mem_op / branch_v3-target_fuori / fpu-oltre).  The tail-jmp family to
  0x3EE58/0x3EE68 IS fully clean: caller clean-except-call AND callee clean.
- Composition differential test (`--compose-test 0xADDR`):
  flattened caller+callee CODE, nested-return mirror semantics
  (`call` -> pc=target; `rts` -> pc=pr; exit when pc leaves CODE) vs sh2emu
  oracle.  **28/32 tail-dispatch callers PASS 500/500, 0 skipped**; 4 declined
  (multi-dispatch: 2 jmp sites with conditional branch to the second — needs
  full CFG, out of scope).
- **Fixed latent sh2emu bug**: `jmp @Rn` was treated as a DELAY-slot branch
  (executed the next instruction).  Per SH-2 ISA `jmp @Rm` is non-delayed.
  Moved to `_exec` (non-delayed, `pc = r[n]`), out of `_delayed`.  No existing
  test regressions (154 pass, 2 fail = pre-existing test_checkFloatValidity.c
  link wiring in user tree, unrelated).
- Evidence: `c/lib/f_3EE58.c`, `c/lib/f_3EE68.c`, `c/tests/test_caller_*.py`
  (28 files), all in git status as untracked; NO commits made.

## 2026-08-05 follow-up — sh2emu jmp correction (CI gate)

The "jmp @Rm is non-delayed" change above was WRONG and is reverted.  The
Hitachi SH-1/SH-2 Programming Manual (3rd ed.) Table 4.2 lists **JMP @Rm and
JSR @Rm among the DELAYED-branch instructions** — the P+2 slot executes before
the branch (the only non-delayed return is `rts/n`).  Evidence in this ROM:
setSR@0x3934 (`jmp @r6` / `ldc r4,SR` — SR would never be set if the slot were
skipped), and every tail-dispatch caller (`jmp @r3` / `mov #imm,r5` — the slot
is the last-arg setup).

Consequences found by the full CI (run_tests_parallel.py, 1125 suites):
- the "non-delayed" change broke 11 existing emulator tests
  (test_calc_fuel_trims_adaptive_117B4, test_calc_lambda_feedback_pid[2],
  test_dtc_code_set_clear, test_dtc_handler_*x2, test_engineControlCalculateTiming,
  test_idle_speed_control, test_init_main_3E10, test_obd_freezeframe_uds01,
  test_omp_accessors) — all pass again with the delayed model;
- the v7 caller tests only passed because the lift AND the buggy emulator both
  dropped the tail-jmp delay slot.  `gen_c_lift_v7.py` `_call_records` now
  emits the jmp P+2 slot (C: slot stmts before `f_<callee>(s); return;`;
  test mirror: `slot_py` on the call record) — 28/28 `test_caller_*` PASS
  against the corrected emulator.
