# Runtime Certificate Plan — emulator-based semantic verification without hardware

Status: **PLAN (phase A exploration done; phase B buildable but from-reset full-ROM run is BLOCKED by a missing peripheral model).**
Date: 2026-08-05. Scope: `roms/stock/60E1D400.bin`, emulator `tools/sh2emu.py`.

## Executive summary (TL;DR)

`tools/sh2emu.py` is a **correct SH-2E interpreter (integer core + FPU)** that executes the *actual
ROM bytes*. It already powers the Track-A verifier (`c/tests/verify_emu.py`, ~100k-random-input
function checks) and the emulator-family regression suite. It exposes an **additive MMIO mock**
(`mmio={addr:byte}` in `SH2.call`), which is the hook a runtime harness needs.

However a **raw run from the reset vector stalls**: boot descends into a hardware poll loop and the
busy-wait never unblocks because no peripheral/timer/port state model exists. So:

- **Feasible now:** instrumented per-function / per-main-loop-entry runs (start at a known entry,
  N-instruction budget, log PC/traps/RAM-writes/MMIO-writes, assert W^X / no-ROM-write / RAM bounds,
  determinism, coverage).
- **Blocked now:** a single unmodified "reset → main loop stabilised" run, until benign anti-stall
  models for the polled hardware registers are added.

## 1. Method — harness spec (`tools/verify_runtime.py`, phase B)

- **Start address:** per-scenario entry (reset `0x8b8` OR a concrete main-loop/leaf entry from
  `FUNCS`/`src/60E1D400_annotated.s`). Reset entry is `0x000008b8` (ROM `d[0:4]`, big-endian).
- **Budget:** N instructions per run (default 10_000). The emulator has **no built-in step-limit API**;
  the harness must **subclass `SH2`** and cap steps by intercepting dispatch (wrap `_exec` / run the
  ram-aware loop) and read `cpu.pc` / `cpu.ram` after the budget or after `RuntimeError("runaway…")`.
- **Log:** PC-set (unique PCs), any `NotImplementedError`/`trapa`, every RAM write (addr,width,val),
  every MMIO write (via a hooked `mmio` dict), and the final reg-file snapshot.
- **Assert (map from `docs/notes/FORMAL_CERT_60E1D400.md` P2 partition, v2, 524288/524288 bytes** —
  instr∩data = 0):
  1. **no-execute-in-data** — every fetched PC must land in the code partition of the P2 map.
  2. **no-ROM-write** — any `wr`/`_wb` whose target < `_romlen` (ROM region) = failure.
  3. **RAM-bounds** — all RAM reads/writes within the emulator's declared RAM window.
  4. **no-trap** — no `NotImplementedError`, no `trapa` (#imm → `raise NotImplementedError`,
     sh2emu.py:309) reached on the covered path.
- **Determinism:** run the same scenario twice; two runs must byte-diff RAM + PC trace to **zero**.
  (Core is deterministic; the only nondeterminism hazard is a future timing/rand model — keep it out.)
- **Coverage:** unique executed instructions / total instructions; report per-region (e.g. boot init
  vs. listed `FUNCS` entries) and per-line-of-C (from the P2 map / `c/*.c` lifts).

## 2. Peripherals — MMIO needing a benign anti-stall model

The emulator's `_rb` gives an optional `mmio` dict priority over RAM/ROM
(sh2emu.py:45-46); `SH2.call(..., mmio={addr:byte})` wires it additively (off by default —
existing tests are unaffected). Precedents: `test_sensorADCRead_68A8.py` builds `{ADCSR…: val}`.

Identified for boot:
- **Reset/boot hardware poll loop `0x8E8..0x8F0`** — after ~200 instructions the reset path busy-waits
  (`and/bt` self-loop); with no model it spins to the 500k runaway at `pc=0x8EA`. The exact polled
  register must be resolved in phase B (candidates: port input via `@(disp,PC)` loads at 0x9B4/0x9AC,
  plus WDT/CMT/power-on registers). Without a benign value that eventually turns the poll bit, boot
  cannot advance.
- **WDT / reset-watchdog** — `resetWatchdog@0x572` writes `0xEC10/0xEC12`; a watch-dog-reload model is
  needed so a long run does not false-trip.
- **Main-loop timing/RTOS** — the later RAM/register polling (`0xFFFFF8xx`-range ports, CMT/TMU timers)
  that keep the scheduler alive each iteration. Identify each read that gates forward progress and give
  it a deterministic, non-stalling value.

## 3. Emulator risks / blockers found

- **No batch "run from X for N instructions, then read state" API.** `SH2.call` is monolithic: it runs
  until an `rts` returns to the sentinel `pr=SENT` (returns `r0`) **or** hits the 500k `RuntimeError
  "runaway"`. Instruction budget is not exposed. → harness must subclass and count steps.
- **From-reset run stalls immediately** (confirmed probe: `call(0x8b8)` → 500k steps in ~0.2 s, then
  `RuntimeError: runaway at 0x8EA`, final PC `0x8ea`, `r0=0`, 12 RAM writes). The stall is the hardware
  poll loop, **not a decoder gap** (`NotImplementedError` opcodes are explicit, sh2emu.py:389/468; only
  `trapa` at :309 is exceptional and is a declared trap-vector, per FORMAL_CERT).
- **Boot is state- and hardware-dependent**, not a pure function: stack/SSR/SR recovery,
  `[0xFFFFDFFC]==0x5AA5A55A` recovery cell, warm/cold paths (see `test_reset_handler_4E0.py`). A
  faithful full-run must model these, not just the poll bits.
- **No interrupt/supervisor-exception model** beyond `rte` popping SR/PC (`_delayed` :309-area) and
  `sleep` as a no-op (:317). Long-lived main-loop scenarios that sleep/idle will need a clock/IRQ stub
  to stay live — or the scenario terminates on budget. (**Non-blocking** for budgeted leaf/main-loop
  runs.)

## 4. Deliverables (phase B)

- `tools/verify_runtime.py` — step-budgeted harness described in §1 (+ `--mmio-model` and
  `--start 0x8b8|entry`, `--budget`, `--log`, `--assert`, `--twice` determinism).
- Benign MMIO model module (list of polled addresses from §2) to unblock full boot.
- New section in `VERIFICATION.md` (runtime cert: method + a table of scenarios/budgets/verdicts).

## 5. Metrics it will produce

- "N instructions executed / M total (code partition)" per scenario.
- "F functions with oracle-validated coverage ≥ X%" (tie back to `verify_emu.py` `FUNCS`).
- "unique-MMIO-addresses disk model reads; {set} unmodelled reads logged".
- determinism diff = 0, W^X violations = 0, ROM-writes = 0, RAM-bounds violations = 0.
- Example headline: *"12,847 instructions executed from reset @0x8b8 (boot init 100%); 0 W^X, 0 ROM-write, 0 bounds violations; deterministic (2-run diff=0); 34/40 lifted functions covered ≥80%"*.

## Blocker list (this is what stops a from-reset full run today)

1. Missing benign models for the boot poll loop (leading address ~`0x8E8`) and WDT/CMT/timer + port inputs.
2. No step-limited execution API in the emulator — harness must subclass (not modify) `sh2emu.py` (repo rule: read-only for the emulator in this task).
3. Boot depends on SR/SSR/recovery-cell state and cold/warm paths — need an initial-state model to be faithful.
4. No interrupt/clock stub for idle/sleep in long main-loop scenarios (soft — budgeted runs work).

The plan for anything less than "full reset→main-loop" (i.e. per-entry/instrumented runs) is **not
blocked** and can be built now.