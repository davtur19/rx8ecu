# REPORT — What the "Cruise Control" function really is in the RX-8 firmware

**Date:** 2026-08-01
**Scope:** Mazda RX-8 PCM (Renesas SH-2A SH7055), ROM `60E0FC00.bin` (RENESIS 6-port, base variant) with cross-check on `60E1D400.bin` (differentiated variant).
**User note:** the user's car does NOT have cruise control installed (no buttons, no actuator).

---

## 1. Question and hypotheses

The functions named `*CruiseControl*` appear in all dumps and internal docs. Three hypotheses:
- **H1 — Mislabel:** the code is not a cruise control; the name is an analysis error.
- **H2 — Platform code:** same firmware shared across models/markets with and without cruise; the code exists but is "something else".
- **H3 — Real cruise, not wired:** the firmware implements a real factory cruise control, simply not connected/active on the user's car.

**Verdict: H3 is confirmed (with an H2 component); H1 is ruled out** except for a single false positive.

---

## 2. Complete inventory of "cruise" hits

### 2.1 Functions (ROM 60E0FC00, source `symbols/symbols_60E0FC00.csv`)

| Address | End | Name | Notes |
|---|---|---|---|
| 0x00C116 | 0x00C14C | `enableDisableCruiseControl??` | init PWM/flag |
| 0x0118FE | 0x01194E | `cruiseControl?` | **mislabel** — periodic diagnostic dispatcher (see §7) |
| 0x02C5D0 | 0x02C5E8 | `calculateCruiseControlSwitchVolt` | ADC → switch voltage (float @0xBC68) |
| 0x02C5F8 | 0x02C8AC | `calculateCruiseControlDriverRequest` | request decode (SET/ACCEL/RES/COAST/CANCEL) |
| 0x02D924 | 0x02D9BC | `calculateCruiseControlDisableCondition` | disable conditions |
| 0x02D9BC | 0x02DB00 | `cruiseControlUndershootingPlausibilityMon` | plausibility monitor |
| 0x02DB00 | 0x02DBC4 | `cruiseControlOvershootPlausibilityMon` | plausibility monitor |
| 0x02DBC4 | 0x02DC2A | `getCruiseControlAllowedBool??` | brake/clutch/VSS/DSC gate + minimum speed |
| 0x02DCDC | 0x02DE64 | `calculateCruiseControlFFTorque` | feed-forward torque |
| 0x02DE64 | 0x02E50C | `calculateCruiseControlProportionalTorque??` | proportional torque |
| 0x02E50C | 0x02E580 | `calculateCruiseControlFinalTorque` | final torque → @0xBD28 |
| 0x02E66C | 0x02E6E2 | `cruiseControlStateStuff` | state handling |
| 0x02EB22 | 0x02EB40 | `cruiseControlFunctions` | dispatcher (called from `throttleTask`) |
| 0x02EB40 | 0x02EBEE | `cruiseControlMain??` | main dispatcher (~22 calls in critical section) |
| 0x02EBEE | 0x02EC0C | `getCruiseControlE2Metrics` | diagnostic metrics |
| 0x0325AC | 0x03269C | `cruiseControllAccelResCheck??` | ACCEL/RES debounce/check |
| 0x032750 | 0x0327CE | `cruiseControlACCELRESAllowed?` | ACCEL/RES admissibility |
| 0x0327CE | 0x032820 | `debounceCruiseControlSET` | SET button debounce |
| 0x032820 | 0x0328D4 | `debounceCruiseControlACCELRES` | ACCEL/RES debounce |
| 0x0328D4 | 0x032ABC | `cruiseControlSetRealted` | SET button handling |
| 0x032ABC | 0x032DDC | `calculateCruiseControlSpeedTarget` | target speed computation (uses config 0x8694) |
| 0x03390C | 0x03395A | `cruiseControlInit` | init (calls enableDisableCruiseControl(0)) |

### 2.2 Functions (ROM 60E1D400, source `symbols/symbols_60E1D400_merged.csv`)

Same cluster with different offsets: `enableDisableCruiseControl??` @0x00C2E6, `cruiseControl?` @0x011B70, `calculateCruiseControlDisableCondition` @0x02E10C, `Undershooting` @0x02E1A4, `Overshoot` @0x02E2E8, `getCruiseControlAllowedBool??` @0x02E3AC, `cruiseControlStateStuff` @0x02EF74, `debounceCruiseControlSET` @0x0331A2, `debounceCruiseControlACCELRES` @0x0331F4, `cruiseControlSetRealted` @0x0332A8, `cruiseControlInit` @0x03446C, plus IDA-ai `cruise_control_check_0x4FD4C`, `cruise_status_0x5AFE2`.

### 2.3 References in files (grep -ri cruise)

- `docs/functions/calculateCruiseControlSwitchVolt.md`, `enableDisableCruiseControl.md`, `getCruiseControlAllowedBool.md`
- `c/` : `getCruiseControlAllowedBool.c` (0x02E3AC, verified), `enableDisableCruiseControl.c` (0x00C2E6, verified); tests in `c/tests/`
- `src/60E0FC00_annotated.s` : cruise cluster ~lines 114543–120700 (SwitchVolt @114543, DriverRequest @114572, FinalTorque @119670, cruiseControlMain @120686)
- `docs/subsystems/` : `AUXILIARY_CONTROL_SUBSYSTEM.md:128` (cruise condition in the idle branch), `:748` (consumption ~1–2 cc/min); `PID_CONTROLLERS.md:48` (0xFFFFA9A8 "cruise path"); `SENSOR_PIPELINE.md:1053` (post-processing "Cruise Control"); `CALIBRATION_TABLES_CROSS_REFERENCE.md:767` (cruise tables, speed)
- `MANIFEST.md:219/225/351/355/493/522/542` : verified C lifts and docs
- `analysis/coverage/uncovered_60E0FC00.csv:4790+` : data pool of `calculateCruiseControlDriverRequest`
- `web/explorer/data.js` / `data.json` : 1 hit each
- Internal cross-validation (private archive, non-sensitive): §4.4 of `RX8_Ghidra_vs_IDA_CrossValidation.txt` (22+ functions, torque-based), §4.1 of `RX8_New_Subsystems_From_Ghidra.txt` (0x2EB40 chain = 27 calls); xmaps `symbols_60E0E700_N3YLEE_xmap.csv`, `symbols_60E1B900_xmap.csv` (alternative names, same cluster)

---

## 3. Behavioral evidence — the pipeline

The disassembly shows a complete and consistent cruise pipeline:

```
[ADC @0xFFFF9F1A]                 (only reference in the whole ROM)
   → calculateCruiseControlSwitchVolt 0x2C5D0
       × 7.62939e-05 (fixedPointToFloat_16bit_MULT_OFF_SIG 0x24C0)
       → float @0xBC68                  (switch voltage, 0..5 V)
   → calculateCruiseControlDriverRequest 0x2C5F8
       4 float ROM thresholds 0.125/1.0/2.0/3.0 V  @0x754B8..0x754C4
       (60E1D400: 3000/5000/0/9.1/18.1 — different layout, same structure)
       → request state (persistent byte @0x868C via EEPROM helper)
   → cruiseControlMain 0x2EB40  [critical-section lock 0x3920(0x10)/0x3934]
       ├─ 0x2D878            (pre-check)
       ├─ calculateCruiseControlDisableCondition 0x2D924
       ├─ Undershooting/… 0x2D9BC  + Overshoot/… 0x2DB00
       ├─ getCruiseControlAllowedBool 0x2DBC4
       ├─ 0x325AC / 0x3269C / 0x32750 (ACCEL/RES, SET/ACCEL/RES debounce)
       ├─ calculateCruiseControlSpeedTarget 0x32ABC
       ├─ calculateCruiseControlFFTorque 0x2DCDC
       ├─ calculateCruiseControlProportionalTorque 0x2DE64
       └─ calculateCruiseControlFinalTorque 0x2E50C → float @0xBD28
   → calculateThrottlePedalPercent 0x19FC0-0x1A27E  (reads @0xBD28, @0x1A1AE)
       → pedal/DBW request (drive-by-wire)
```

This architecture — resistive-divider switch decode → driver request →
speed target → feed-forward + proportional torque → final torque injected
into the throttle-opening request — is the signature of a torque-based
cruise control. No alternative "cruising speed" function
shares this structure.

---

## 4. Authenticity evidence

1. **Dedicated physical input:** ADC address `0xFFFF9F1A` is referenced ONLY by
   `calculateCruiseControlSwitchVolt` (1 literal in ROM). It is the cruise
   command input (multi-button resistive divider, 4 thresholds = 4+ states).
2. **Classic thresholds:** 0.125 / 1.0 / 2.0 / 3.0 V on 5 V is the typical scheme of a
   resistive cruise switch (each button partitions the voltage).
3. **Dedicated calibration tables** (`CALIBRATION_TABLES_CROSS_REFERENCE.md:767`).
4. **Vehicle-side inhibitors:** gates on brake switch, clutch switch, VSS fault and
   ASC/DSC intervention (see §5) — typical cruise safety logic.
5. **Persistent EEPROM-backed config:** 0x868C read/written with the value+complement
   pattern (`readValue_8bit_ADDRESS_VAL` 0x3E0DC / `updateMemoryAtAddress_8bit_ADDR_VAL` 0x3E1F8) and **used exclusively by the cruise cluster** (7 genuine refs: 0x2C696, 0x2C7A2, 0x2C892, 0x2D6DC, 0x2D978, 0x2E5D6, 0x2E74E). It is the "cruise configured/installed" flag.
6. **Two ROMs, same structure:** 60E0FC00 and 60E1D400 implement the same
   cluster with different offsets (RAM layout differs between variants — known pattern in
   this firmware).
7. **Mazda documentation:** the RX-8 was sold with optional cruise control
   (e.g. "SWITCH,ACCEL-CRUISE" 2004; 2005 manual: works above ~30 km/h).

---

## 5. Enable conditions (verified disasm)

### `getCruiseControlAllowedBool` @0x2DBC4 (60E0FC00)
Output @0xBD1C = 1 (cruise allowed) if:

```
(no inhibitor active AND speed > 27.0 km/h)  OR  master_enable == 1
```

- Inhibitors: 0xBD18, 0xBD19, 0xBD1A, 0xBD2E (diag)
- Threshold: f32 @0x76298 = 27.0 (km/h)
- Speed: float @0xBFBC
- master_enable: ROM @0x762A5 = **0x80** → NOT == 1 → factory override inactive
  (in 60E1D400: @0x76B6D = 0x00, same effect)
- Variant 60E1D400 @0x2E3AC (C lift verified in `c/`): brake inhibitor 0xBD54,
  clutch 0xBD55, VSS 0xBD56, ASC/DSC 0xBD6A; output @0xBD58; min threshold @0xC008.

Gate conclusion: in both ROMs the master_enable is a test/diagnostic
override calibration **not enabled in stock**; enabling depends only on
minimum speed (~27 km/h) and the absence of inhibitors. The 27 km/h threshold is
consistent with the official manual (~30 km/h).

### `calculateCruiseControlDisableCondition` @0x2D924
Writes 0xBD19 = 1 (disabled) if **at least one**:
- 0x868C == 0 (cruise config absent → cruise not installed)
- 0xAACC == 0 (vehicle state/engine conditions not satisfied)
- 0xBD7C == 1
- 0xBD69 == 1 AND value@0xBFBC > 22.5 (f32 @0x76280) — plausibility/button channel

---

## 6. Reachability and consumption (active, not dead code)

From `symbols/callgraph.csv`:
- `throttleTask` (0x11584, called from the main task via FUN_000064ba) → `cruiseControlFunctions` (0x2EB22)
- `FUN_000115aa` (throttle/torque task, via FUN_000064e8) → `cruiseControlMain??` (0x2EB40) — together with `calculateTorqueRelatedParams` (0x2D208), `throttlePlateTorqueStuff`, etc.
- `getIOUpdates?` (0x1A35C) → `calculateCruiseControlSwitchVolt` (0x2C5D0) and `cruiseControlInit` (0x3390C)
- `vehicleConditionRelatedFuntions` (0x1A7FA) → `calculateCruiseControlDriverRequest` (0x2C5F8)

The code runs **every cycle** in the throttle/IO management tasks. The torque output
@0xBD28 is read by `calculateThrottlePedalPercent` (0x1A1AE: `mov.w 0x1A1FE,r1 ; 0xBD28`
→ `fmov.s @r1,fr5`): the cruise torque feeds directly into the DBW
throttle-opening request. When cruise is inactive @0xBD28 stays ~0 and the pedal
controls normally.

---

## 7. The only false positive

`cruiseControl?` @0x118FE **is not** a cruise function: it is a periodic
diagnostics/conditions dispatcher that calls 13 functions (0x1A9EE, 0x2EBEE
`getCruiseControlE2Metrics`, 0x398F4, 0x21C66, 0x27174, 0x3F0B2, 0x292D8, 0x2AAC8,
0x545BA `checkDeviceControlConditional`, 0x5A78C, 0x63F20, 0x63F48
`coolantTempPlausibilityCheck`, 0x169EA). The name comes from the fact that
`getCruiseControlE2Metrics` (0x2EBEE) is one of the callees. It is the only truly
wrong "cruise" hit.

---

## 8. Why the user's car has no cruise

Combination of the three factors (H3 with H2 component):
1. **Factory option:** cruise was an option (2004–2005). The PCM hardware and
   firmware support it, but the car has neither the buttons nor the optional
   actuator/wiring.
2. **Dedicated ADC input not connected:** 0xFFFF9F1A is read only by cruise; if
   the switch is not wired, the voltage stays in the "off" state and
   `calculateCruiseControlDriverRequest` always produces "no request".
3. **Persistent config:** 0x868C (EEPROM-backed) is read by
   `calculateCruiseControlDisableCondition` with default 0 → cruise kept
   disabled when not marked as installed/configured.
4. **Enable gate** requires speed > ~27 km/h and no inhibitors — in
   any case without a button request the cruise never activates.

**H2:** it is also true that the firmware is shared across variants (same code on
60E0FC00/60E1D400/60E0E700/60E1B900) — cruise is present on all of them, which is
typical of Denso platform software — but the code behavior is
unambiguously "cruise control" and not another function.

---

## 9. Conclusion

- The "cruise control" is **real**: a factory torque-based cruise control,
  complete (switch decode → speed target → FF+P torque → DBW throttle).
- It is **active in the firmware** (executed every cycle by the throttle/IO tasks), not dead code.
- On the user's car it is simply **not installed/not wired**: no
  buttons → no request; 0x868C not configured → disabled.
- **H1 ruled out** (except `cruiseControl?` @0x118FE, mislabel).
- **Confidence:** high for "real torque-based cruise"; high for "not wired/not
  configured on the user's car".

## 10. Open questions (max 3)

1. **Exact semantics of the intermediate flags** 0xBD7C / 0xBD69 / 0xBD2E and who writes them
   (likely: button state, gear/conditions, diagnostics state).
2. **Who feeds the brake/clutch/VSS/ASC inhibitors** (0xBD54/0xBD55/0xBD56/
   0xBD6A in the 60E1D400 variant) — presumably brake switch, clutch switch,
   VSS plausibility and the DSC module; to be confirmed with xref.
3. **Is 0x868C ever written at runtime** (e.g. by UDS diagnostics) or is it
   preconfigured at the factory? And what is the physical pinout of the cruise switch
   connector (not present in `CONNECTOR_PINOUT.md`)?

---

## 11. Useful files for further study

- `symbols/symbols_60E0FC00.csv`, `symbols/symbols_60E1D400_merged.csv`, `symbols/callgraph.csv`
- `src/60E0FC00_annotated.s` (cruise cluster ~lines 114669–120035)
- `c/getCruiseControlAllowedBool.c`, `c/enableDisableCruiseControl.c` (+ `c/tests/`)
- `docs/functions/calculateCruiseControlSwitchVolt.md`, `enableDisableCruiseControl.md`, `getCruiseControlAllowedBool.md`
- `tools/disasm_sh2e.py`, `tools/sh2emu.py`
- `docs/subsystems/PID_CONTROLLERS.md:48`, `SENSOR_PIPELINE.md:1053`, `CALIBRATION_TABLES_CROSS_REFERENCE.md:767`, `AUXILIARY_CONTROL_SUBSYSTEM.md:128,748`
