# Runtime Certificate Plan — emulator-based semantic verification without hardware

Status: **PLAN (phase A exploration done; phase B buildable but from-reset full-ROM run BLOCKED by a missing peripheral model).** 2026-08-05. Scope: `roms/stock/60E1D400.bin`, emulator `tools/sh2emu.py`.

## TL;DR

`tools/sh2emu.py` is a **correct SH-2E interpreter (integer core + FPU)** executing the *actual ROM bytes*. Powers the Track-A verifier (`c/tests/verify_emu.py`, ~100k-random-input checks) and the emulator-family regression suite. Exposes an **additive MMIO mock** (`mmio={addr:byte}` in `SH2.call`) — the hook a runtime harness needs.

A **raw run from the reset vector stalls**: boot descends into a hardware poll loop; the busy-wait never unblocks (no peripheral/timer/port model).

- **Feasible now:** instrumented per-function / per-main-loop-entry runs (known entry, N-instruction budget, log PC/traps/RAM-writes/MMIO-writes, assert W^X / no-ROM-write / RAM bounds, determinism, coverage).
- **Blocked now:** single unmodified "reset → main loop stabilised" run, until benign anti-stall models for polled hardware registers are added.

## 1. Method — harness spec (`tools/verify_runtime.py`, phase B)

- **Start address:** per-scenario entry (reset `0x8b8` OR a concrete main-loop/leaf entry from `FUNCS`/`src/60E1D400_annotated.s`). Reset entry `0x000008b8` (ROM `d[0:4]`, big-endian).
- **Budget:** N instructions (default 10_000). No built-in step-limit API — harness must **subclass `SH2`** and cap steps by intercepting dispatch; read `cpu.pc`/`cpu.ram` after budget or after `RuntimeError("runaway…")`.
- **Log:** PC-set, `NotImplementedError`/`trapa`, every RAM write (addr,width,val), every MMIO write (hooked `mmio` dict), final reg-file snapshot.
- **Assert** (map from `docs/notes/FORMAL_CERT_60E1D400.md` P2 partition, v2, 524288/524288 bytes — instr∩data = 0):
  1. **no-execute-in-data** — fetched PC must land in the code partition.
  2. **no-ROM-write** — any `wr`/`_wb` target < `_romlen` = failure.
  3. **RAM-bounds** — all RAM reads/writes within the declared RAM window.
  4. **no-trap** — no `NotImplementedError`, no `trapa` (sh2emu.py:309) on the covered path.
- **Determinism:** same scenario twice → RAM + PC trace byte-diff to **zero**.
- **Coverage:** unique executed instructions / total; per-region and per-line-of-C.

## 2. Peripherals — MMIO needing a benign anti-stall model

`_rb` gives optional `mmio` dict priority over RAM/ROM (sh2emu.py:45-46); `SH2.call(..., mmio={addr:byte})` wires it additively (off by default). Precedent: `test_sensorADCRead_68A8.py` builds `{ADCSR…: val}`.

Identified for boot:
- **Reset/boot hardware poll loop `0x8E8..0x8F0`** — after ~200 instructions the reset path busy-waits (`and/bt` self-loop); no model → spins to the 500k runaway at `pc=0x8EA`. Polled register must be resolved in phase B (candidates: port input via `@(disp,PC)` loads at 0x9B4/0x9AC, WDT/CMT/power-on registers).
- **WDT / reset-watchdog** — `resetWatchdog@0x572` writes `0xEC10/0xEC12`; watch-dog-reload model needed for long runs.
- **Main-loop timing/RTOS** — `0xFFFFF8xx`-range ports, CMT/TMU timers keeping the scheduler alive. Each read that gates forward progress needs a deterministic, non-stalling value.

## 3. Emulator risks / blockers

- **No batch "run N instructions, read state" API.** `SH2.call` runs until `rts` to sentinel `pr=SENT` (returns `r0`) or the 500k `RuntimeError "runaway"`. → harness must subclass and count steps.
- **From-reset run stalls immediately** (probe: `call(0x8b8)` → 500k steps in ~0.2 s, `RuntimeError: runaway at 0x8EA`, final PC `0x8ea`, `r0=0`, 12 RAM writes). Stall is the hardware poll loop, **not a decoder gap** (`NotImplementedError` opcodes explicit, sh2emu.py:389/468; only `trapa` :309 is exceptional — declared trap-vector per FORMAL_CERT).
- **Boot is state-/hardware-dependent**, not pure: stack/SSR/SR recovery, `[0xFFFFDFFC]==0x5AA5A55A` recovery cell, warm/cold paths (`test_reset_handler_4E0.py`).
- **No interrupt/supervisor-exception model** beyond `rte` popping SR/PC (`_delayed` :309-area) and `sleep` as no-op (:317). Long main-loop scenarios need a clock/IRQ stub — or terminate on budget. (**Non-blocking** for budgeted runs.)

## 4. Deliverables (phase B)

- `tools/verify_runtime.py` — step-budgeted harness (§1; `--mmio-model`, `--start 0x8b8|entry`, `--budget`, `--log`, `--assert`, `--twice`).
- Benign MMIO model module (polled addresses from §2) to unblock full boot.
- New `VERIFICATION.md` section (runtime cert: method + scenarios/budgets/verdicts table).

## 5. Metrics it will produce

- "N instructions executed / M total (code partition)" per scenario.
- "F functions with oracle-validated coverage ≥ X%" (tie back to `verify_emu.py` `FUNCS`).
- "unique-MMIO-addresses model reads; {set} unmodelled reads logged".
- determinism diff = 0, W^X = 0, ROM-writes = 0, RAM-bounds violations = 0.
- Example headline: *"12,847 instructions from reset @0x8b8 (boot init 100%); 0 W^X, 0 ROM-write, 0 bounds; deterministic (2-run diff=0); 34/40 lifted functions covered ≥80%"*.

## Blocker list (stops a from-reset full run today)

1. Missing benign models for the boot poll loop (~`0x8E8`) and WDT/CMT/timer + port inputs.
2. No step-limited execution API — harness must subclass (not modify) `sh2emu.py` (repo rule: read-only for the emulator).
3. Boot depends on SR/SSR/recovery-cell state and cold/warm paths — needs an initial-state model.
4. No interrupt/clock stub for idle/sleep in long main-loop scenarios (soft — budgeted runs work).

Per-entry/instrumented runs (anything less than full reset→main-loop) are **not blocked** and can be built now.