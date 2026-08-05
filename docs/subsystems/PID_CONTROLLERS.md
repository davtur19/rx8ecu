# RX-8 ECU: PID / Feedback Controllers — Verified Analysis

> ROM: `60E1D400` (md5 `5e4236d29b7c05820240fa076dffdd40`)
> Status: **verified against the ROM via the SH-2E emulator** (`tools/sh2emu.py`)
> Verifier: `c/tests/test_{calc_intake_pressure_pid_output_1252C,calc_rotor_sync_idle_gate_B,idle_speed_control_18054,calc_lambda_feedback_pid}.py`
> Lifts: `c/calc_intake_pressure_pid_output_1252C.c`, `c/calc_rotor_sync_idle_gate_B.c`,
> `c/idle_speed_control_18054.c`, `c/calc_lambda_feedback_pid.c`

## 0. Headline Findings

1. **The four "PID" functions in the symbol table are NOT gain-based (Kp/Ki/Kd) controllers.**
   Verified against the ROM: none of `0x1252C` (intake-pressure PID), `0x12BC8`
   (rotor-sync idle gate B), `0x18054` (idle speed control), or `0x11A34` (lambda feedback
   PID) computes a proportional/integral/derivative term. They are, respectively:
   a **selection+clamp output stage**, a **RPM-drop gate**, a **mode/state machine with
   a duty ramp**, and a **17-task sequential dispatcher**.
2. `pid_control_loop_2D600` (408 B) is not a PID at all — it is a **fault-severity
   encoder** (window compares → severity code 0/5/10/15 in `RAM[0xFFFFBCEE]`).
3. The real closed-loop *math* lives in the sub-functions of the dispatchers
   (e.g. lambda core `0x1ACDE` with 247 FPU ops), plus the shared verified FPU leaves
   (`0x23B0` first-order filter, `0x2404` clamp, `0x2440` deadband check, `0x2460`/`0x2478`
   saturating adds). Coefficient extraction from those cores is **still an open task** —
   do not cite specific Kp/Ki values anywhere; none are verified yet.

All statements below were checked against the emulator trace and randomized differential
tests (3128 / 4152 / 3066 / structural tests, 0 failures).

## 1. `calc_intake_pressure_pid_output_1252C` — 0x1252C (174 B)

**Output stage of the intake-pressure correction loop.** Reads three floats and two status
bytes, selects one of three correction references, clamps, and writes the final "PID output"
float.

### RAM map

| Address | Type | Role |
|---------|------|------|
| `0xFFFFB5B8` | f32 | engine speed (rpm) |
| `0xFFFFA790` | f32 | intake-pressure target |
| `0xFFFFBCE4` | f32 | intake-pressure error |
| `0xFFFFAADA` | u8 | closed-loop active flag (shared with lambda subsystem) |
| `0xFFFFCE58` | u8 | idle / overrun condition flag |
| `0xFFFFBC36` | u8 | fuel-cut active flag |
| `0xFFFFA9B8` | f32 | lambda status (>0 required on the alternate path) |
| `0xFFFFA9A8` | f32 | alternate correction reference (cruise path) |
| `0xFFFFA640` | f32 | default correction reference |
| `0xFFFFA658` | f32 | clamp lower bound |
| `0xFFFFA63C` | f32 | **output** — the PID correction |

### Calibration constants

| ROM addr | Value | Meaning |
|----------|-------|---------|
| `0x12600` | `1e-5` | deadband for the complement_shift_u32 checks |
| `0x12608` | `2000.0` | rpm threshold (see branch note below) |
| `0x6E3D8` | `-5.0` | fixed closed-loop idle correction (kPa) |
| `0x6E3F0` | `65.0` | clamp upper bound (kPa) |
| `0x6E3D4` | `0x00` | enable byte; `== 0` ⇒ alternate path ignores `\|error\|` |

### Behavior (verified)

```
r1 = complement_shift_u32(target, 0.0, 1e-5)   ; 1 if |target| > 1e-5
r2 = complement_shift_u32(error,  0.0, 1e-5)   ; 1 if |error|  > 1e-5

if (AADA == 1 && r1 == 0 && rpm < 2000.0 && CE58 == 1)
    correction = -5.0                        ; closed-loop idle kick
else if (BC36 == 0 && A9B8 > 0.0 && (cal_en == 0 || r2 == 0))
    correction = RAM[0xA9A8]                 ; alternate reference
else
    correction = RAM[0xA640]                 ; default reference

RAM[0xA63C] = clamp(correction, RAM[0xA658], 65.0)
```

> **Branch-direction erratum (caught by the emulator):** the idle kick applies
> **below** 2000 rpm (`fcmp/gt fr15,fr3` = `2000 > rpm`, `T = fr3 > fr15`), not above.
> An earlier hand analysis had the operand order inverted. The C lift and the test encode
> `rpm < 2000.0` and pass 3128 differential tests.

Helpers: `0x2440` `complement_shift_u32` (verified, 710 tests); `0x2404`
`fpu_compare_and_select` = `clamp(val, lo, hi)`.

## 2. `calc_rotor_sync_idle_gate_B` — 0x12BC8 (196 B)

**RPM-drop gate for rotor-sync correction.** Samples "previous RPM", computes the drop on
every call, and sets a one-shot flag when engine speed collapses during closed-loop with a
rotor-sync fault condition. No gain math.

### RAM map

| Address | Type | Role |
|---------|------|------|
| `0xFFFFA444` / `0xFFFFA445` | u8 | rotor A / rotor B position status |
| `0xFFFFB5B8` | f32 | engine speed (rpm) |
| `0xFFFFA694` | f32 | previous RPM sample (**output**, written every call) |
| `0xFFFFA690` | u8 | **output** — correction-enable flag |
| `0xFFFFA6A3` / `0xFFFFA6A4` | u8 | rotor-sync enable A / B (also written back) |
| `0xFFFFB5A4` | u8 | warm-up status |
| `0xFFFFCABC` | u8 | closed-loop enable (rotor-sync side) |
| `0xFFFFAADA` | u8 | closed-loop active (shared) |

### Calibration constants

| ROM addr | Value | Meaning |
|----------|-------|---------|
| `0x72BC4` | `40.0` | minimum RPM drop (rpm) to trigger |
| `0x72BC8` | `2000.0` | maximum RPM for the trigger |

### Behavior (verified)

```
prev = RAM[0xA694]
drop = prev - rpm                      ; computed unconditionally
trigger = ((B5A4 == 1 || CABC == 1) && AADA == 1) &&
          ((A6A3 == 1 && rotorA == 0) || (A6A4 == 1 && rotorB == 0)) &&
          !(40.0 > drop)               ; i.e. drop >= 40.0
          !(rpm > 2000.0)              ; i.e. rpm <= 2000.0
RAM[0xA690] = trigger ? 1 : 0
RAM[0xA694] = rpm                       ; always
RAM[0xA6A3] = rotorA ; RAM[0xA6A4] = rotorB ; always
```

Operationally: a large RPM drop (> 40 rpm, below 2000 rpm) during closed-loop with a
rotor-sync fault condition arms rotor-sync correction — an **anti-stall / limp-in
re-trigger**, not a PID.

## 3. `idle_speed_control_18054` — 0x18054 (404 B)

**Idle-speed state machine + duty ramp.** Drives the IACV duty through a two-state mode
machine, AC compensation latch, duty-threshold limiting and a +1/cycle ramp with 16-bit
saturation. The "PID" label is a misnomer: the output (`RAM[0xFFFFA96E]`) is a **ramped
integer duty**, not a computed control term.

### RAM map

| Address | Type | Role |
|---------|------|------|
| `0xFFFFA428` | u8 | engine state (low byte; see SENSOR_PIPELINE/AUXILIARY_CONTROL for the TPS-vs-state ambiguity) |
| `0xFFFFAAE0` | u8 | mode select |
| `0xFFFFA979` | u8 | AC request (cleared to 0 on idle-active path) |
| `0xFFFFA998` | u8 | engine running flag |
| `0xFFFFA978` | u8 | load compensation |
| `0xFFFFA96C` | u8 | idle-enable (in/out) |
| `0xFFFFA96A` | u8 | saved status (in: old; out: new) |
| `0xFFFFA970` | u8 | learn counter (in; overwritten with load_comp) |
| `0xFFFFA96E` | u16 | **IACV duty output** |
| `0xFFFFAA10` | f32 | O2 voltage (duty-threshold gate) |
| `0xFFFFA96B` | u8 | out: idle-active flag |
| `0xFFFFA968` | u8 | out: feedback flag |
| `0xFFFFA969` | u8 | out: AC latch |
| `0xFFFFA975` | u8 | out: IACV mode (set to 2 on idle-active path) |

### Calibration constants

| ROM addr | Value | Meaning |
|----------|-------|---------|
| `0x78E42` | `156` | duty ceiling when `O2 >= -40.0` |
| `0x78E44` | `500` | duty ceiling when `O2 < -40.0` (fuel cut / low O2) |
| `0x78E64` | `-40.0` | O2 threshold selecting the ceiling |

### Behavior (verified)

```
if (state == 0 && mode == 1):                 ; idle-active path
    idle_active = 1; RAM[A979] = 0; RAM[A975] = 2
elif (state == 1 && ac == 0 && running == 0): ; feedback path
    feedback = 1
else:
    if ac == 1: ac_latch = 1
    if mode == 0 && ac_latch && !running && check_3ED3C(0x807C, 0) == 0: status = 1
    if status == 0 && !load_comp && learn == 1: idle_en = 1
    if idle_en_orig == 0 && idle_en == 1: duty = 0        ; re-entry kick
store: RAM[A96B]=idle_active; RAM[A968]=feedback;
       RAM[A969]=ac_latch; RAM[A96A]=status
thr  = (O2 < -40.0) ? 500 : 156
if duty >= thr: idle_en = 0                 ; ceiling — stops the ramp
RAM[A96C] = idle_en
duty = add16bitSaturate(duty, 1)            ; +1/cycle, saturates at 0xFFFF
RAM[0xFFFFA96E] = duty; RAM[A970] = load_comp
if old_status == 0 && status == 1: osTaskScheduler(0, 2)
```

Helpers verified in-chain: `0x3ED3C` `check_3ED3C(addr, fallback)` =
`if RAM[a] == ~RAM[a+1] return RAM[a] else fallback` (fallback path also sets
`RAM[0xC6AC] = 1` via `0x3F050`); `0x2460` `add16bitSaturate`; `0x9668` `osTaskScheduler`
(no-ops with an empty task table).

## 4. `calc_lambda_feedback_pid` — 0x11A34 (104 B)

**Closed-loop lambda task dispatcher.** A fixed-order sequence of 16 `jsr` calls followed
by a **single tail `jmp`** into the 17th task (0x16E6A), which returns directly to the
dispatcher's caller (PR restored in the delay slot). Verified by instruction trace: exactly
17 dispatch entries, `r0 = 0x28` on the all-zero-RAM run.

| # | Callee | Size (i) | FPU ops | Role (working model) |
|---|--------|---------:|--------:|----------------------|
| 1 | `0x1ACDE` | 644 | 247 | O2 conditioning / filter / trim core |
| 2 | `0x2F51E` | 216 | 5 | status/bank trim chain |
| 3 | `0x3A1CC` | 872 | 84 | secondary lambda math |
| 4 | `0x2204C` | 640 | 32 | trim/learn chain |
| 5 | `0x1490E` | 161 | 0 | state updates (no FP) |
| 6 | `0x2766A` | 115 | 3 | sensor status chain |
| 7 | `0x16AA8` | 278 | 21 | fuel-cut / transient logic |
| 8 | `0x3FCE0` | 108 | 19 | O2 sensor conditioning |
| 9 | `0x32A9C` | 650 | 92 | fueling trim core |
| 10 | `0x17F7C` | 611 | 143 | lambda feedback core #2 |
| 11 | `0x225A2` | 464 | 8 | closed-loop enable logic |
| 12 | `0x35B6A` | 167 | 9 | status |
| 13 | `0x35B96` | 145 | 8 | status |
| 14 | `0x2971C` | 646 | 0 | DTC / fault chain |
| 15 | `0x2B0D6` | 610 | 9 | O2 heater control |
| 16 | `0x67482` | 7 | 0 | wrapper → `0x60DB4`, stores u16 to `RAM[0xFFFFD96C]` |
| 17 | `0x16E6A` | 23 | 0 | status latch; may `jmp 0x16D04` (tail call) |

The FP-heavy cores (esp. `0x1ACDE`, `0x17F7C`, `0x32A9C`, `0x3A1CC`) hold the actual
closed-loop lambda math; they call the shared verified leaves (`0x23B0` first-order filter,
`0x23E4`, `0x2404` clamp, `0x2460`, `0x2478` saturating adds, `0x2068`/`0x20DC` map
lookups). **Extracting the numeric coefficients (any claimed P/I values) is not yet done —
see Open Questions.**

## 5. Reclassification: `pid_control_loop_2D600` (0x2D600, 408 B)

Not a PID. Fault-severity encoder: compares coolant (`RAM[0xFFFFC12C]`), O2
(`RAM[0xFFFFAA10]`) and RPM (`RAM[0xFFFFB5B8]`) against hysteresis windows built from
constants at `0x75CC8–0x75CF4` (0.25, 0.04, 0, 5, 4800, 100, 9500, 100, 10000, 100,
11000, 100) and writes a severity code (0/5/10/15) to `RAM[0xFFFFBCEE]`.

## 6. Verified Toolchain & Artifacts

- `tools/disasm_sh2e.py` — fixed this session: `jsr @Rn` / `jmp @Rn` source register is
  bits 11-8 (was incorrectly bits 7-4).
- `tools/sh2emu.py` — SH-2E emulator; all four functions verified against the ROM.
- Tests (all passing, run from repo root):
  - `python3 c/tests/test_calc_intake_pressure_pid_output_1252C.py` — 3128 tests
  - `python3 c/tests/test_calc_rotor_sync_idle_gate_B.py` — 4152 tests
  - `python3 c/tests/test_idle_speed_control_18054.py` — 3066 tests
  - `python3 c/tests/test_calc_lambda_feedback_pid.py` — dispatch-structure test
- C lifts: `c/calc_intake_pressure_pid_output_1252C.c`, `c/calc_rotor_sync_idle_gate_B.c`,
  `c/idle_speed_control_18054.c`, `c/calc_lambda_feedback_pid.c`.

## 7. Open Questions

1. Extract the numeric lambda PI/PD coefficients from the FP-heavy lambda cores
   (`0x1ACDE`, `0x17F7C`, `0x32A9C`, `0x3A1CC`) — is the loop PI (as claimed in some older
   notes) or richer (cascaded/feed-forward)? **No coefficient value is confirmed yet.**
2. `0xFFFFA428` remains ambiguous between TPS-processed u16 (SENSOR_PIPELINE.md) and
   engine-state byte (AUXILIARY_CONTROL_SUBSYSTEM.md); `idle_speed_control_18054` reads its
   low byte — resolution requires tracing the writer.
3. `calc_idle_speed_target` (0x12F5E, prior session, `c/calc_idle_speed_target.c`) is still
   unverified against the emulator.
