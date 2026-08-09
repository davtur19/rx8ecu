# v7 SH-2 call-composition — selection findings (session notes)

## pool_v5 measurement (open question resolved)

The previous session reported "~74 pool_v5 candidates". This count does NOT reproduce with the current catalog and lifted state. Faithful re-scan (`tmp/analyze_*`):

### v4 flow (the real selector `select_fpu` universe; catalog-end only, sanitized span)
- call-rejected total = **135** (matches dryrun `rejected_call` v4)
- full-span passes with calls admitted = **112** — jmp-only (tail jumps) **109**, composable (≥1 jsr/bsr) **3** (`0x8B8`, `0x17B24`, `0x56F10`)
  - only 2 with jsr/bsr targets resolvable-to-literal; callees (`0x8CC`/`0x8F6`/`0x4E0`/`0x1038`) NOT already lifted
- composable-with-already-lifted-callees = **3** (all tail-jmp → `0x03EE58`/`0x03EE68`, already lifted as `updateMemoryAtAddress_*bit*`)

### v3 flow (no-span estimated ends, the v3 selector universe)
- call-rejected total = **626** (matches v3 dryrun `rejected_call`); jmp-only 121, composable 9, reject-after-call 496

### Prefix definition (scan stops at first call; only first call target matters)
- v4: **32** candidates whose FIRST call is a jmp @r `0x03EE58`/`0x03EE68` (already lifted)

## Conclusions
- Genuinely composable jsr/bsr pool: **9 (v3-est) / 3 (v4-cat)**, NOT ~74.
- 626-vs-74 gap: the v3 selector counted no-span candidates. v4 drops them entirely.
- To lift a composable caller, the callee must be re-generated as NEW `c/lib/f_<hex>.c` (state-struct ABI); most callees nest calls → recursive composition (depth guard).
- Smallest reliably-composable cohort = tail-jump family to `updateMemoryAtAddress_8bit_3ee58`/`_16bit_3ee68` (leaf callees, already lifted + re-emittable).

## v7 design (state-struct)
- Shared `ST { r[16], pr, T, macl, mach, sr, gbr, fpul, fpscr; ram/stack assembly }`.
- Callee `void f_<hex>(ST *s)`: reads args `s->r[4..5]`, returns `s->r[0]`.
- Caller `void caller_<addr>(ST *s)`; call site: `s->pr = <retaddr>; <delay slot>; f_<callee>(s);`
- Tail jmp: `f_<callee>(s); return;` (no pr set).
- r8..r14 callee-clobber without save → mismatch → drop caller.

## Blockers / scope
- The callee-struct/C emission and the merged-mirror test are large items. Implementation covers only the tail-call leaf cohort. Full recursive jsr/bsr composition = next milestone.

## 2026-08-05 session — v7 implemented, diff-verified (28/28 PASS)

`tools/gen_c_lift_v7.py` (new standalone tool: pool_v5 selector + ST callee lib + caller composition + differential test).

- **ST-ABI callee emission** (`c/lib/f_<hex>.c`, `void f_X(ST *s)`): it re-emits every call-free span from the v3 walker. Register/system tokens become `s->r[N]`/`s->pr`/`s->T`; compile-gated (`cc -O2 -c`, delete on failure). Verified vs original lift ABI over **5000 random inputs: identical r0 + memory (seed 42)** for `f_3EE58`.
- **Caller emission** (`--compose 0xADDR`): jsr/bsr → `s->pr=pc+4; <delay slot>; f_<callee>(s);` (**pr set BEFORE slot, per HW**); tail jmp → `f_<callee>(s); return;`. Forward-declares callees, compile-gates.
- Chain-validated strict pool_v5 **= 0 in both flows**: every jsr/bsr caller's callee chain hits an un-liftable leaf (`base_unresolved`/`no_mem_op`/`branch_v3-target_fuori`/`fpu-oltre`). Tail-jmp family to `0x3EE58`/`0x3EE68` fully clean (caller clean-except-call AND callee clean).
- **Differential test** (`--compose-test 0xADDR`): flattened caller+callee CODE, nested-return mirror (`call`→pc=target; `rts`→pc=pr; exit when pc leaves CODE) vs sh2emu oracle. **28/32 tail-dispatch callers PASS 500/500, 0 skipped**; 4 declined (multi-dispatch: 2 jmp sites with a conditional branch to the 2nd — full CFG needed).
- **sh2emu fix (later reverted, see follow-up)**: `jmp @Rn` was "non-delayed" → moved to `_exec`. No regressions (154 pass; 2 fail = pre-existing `test_checkFloatValidity.c` link wiring, unrelated).
- Evidence: `c/lib/f_3EE58.c`, `c/lib/f_3EE68.c`, `c/tests/test_caller_*.py` (28) — untracked; NO commits made.

## 2026-08-05 follow-up — jmp correction (CI gate): REVERTED

`jmp @Rm` non-delayed was **WRONG**. Hitachi SH-1/SH-2 Programming Manual (3rd ed.) Table 4.2: **JMP @Rm and JSR @Rm are DELAYED branches** (P+2 slot executes first); only non-delayed return is `rts/n`. ROM evidence: `setSR@0x3934` (`jmp @r6`/`ldc r4,SR` — SR would never be set if the slot was skipped); every tail-dispatch caller (`jmp @r3`/`mov #imm,r5` — slot = last-arg setup).

Full CI (`run_tests_parallel.py`, 1125 suites): "non-delayed" broke **11 emulator tests** (test_calc_fuel_trims_adaptive_117B4, test_calc_lambda_feedback_pid[2], test_dtc_code_set_clear, test_dtc_handler_*x2, test_engineControlCalculateTiming, test_idle_speed_control, test_init_main_3E10, test_obd_freezeframe_uds01, test_omp_accessors) — all pass again with the delayed model. v7 caller tests had passed only because the lift AND the buggy emulator both dropped the tail-jmp delay slot. `gen_c_lift_v7.py` `_call_records` now emits the jmp P+2 slot (C: slot stmts before `f_<callee>(s); return;`; test mirror: `slot_py` on call record) — **28/28 `test_caller_*` PASS** vs corrected emulator.