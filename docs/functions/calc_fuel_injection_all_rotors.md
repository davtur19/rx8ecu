# calc_fuel_injection_all_rotors

**Address:** 0x013D3C – 0x013E28  (236 bytes)
**Called by:** engineControlCalculateTiming (Phase 2)

## Overview

This function computes the **fuel injection timing for all rotors**. It is
structurally very similar to `calc_ignition_all_rotors_13C2C`, sharing the same
three final dispatch helpers (0x13ED2, 0x13E6C, 0x13EE6). It reads engine
speed, fuel cut flags, and injection mode status; computes the corrected fuel
injection quantity; and writes the result to per-rotor output registers.

## Subcalls

| Address | Name | Purpose |
|---------|------|---------|
| 0x13ED2 | compare_select_two_float_values | Selects between two float values |
| 0x13E6C | calc_fuel_pump_control_output | Writes trailing-edge output |
| 0x13EE6 | calc_fuel_pressure_load_compensation | Writes leading-edge output |

## RAM Variables

| Address | Type | Description |
|---------|------|-------------|
| 0xFFFFA744 | float | Main injection timing / fuel quantity |
| 0xFFFF???? | float | Engine speed (same as ignition reads) |
| 0xFFFF???? | u8 | Fuel cut mode flag |
| 0xFFFF???? | u8 | Injection enable flag |
| 0xFFFF???? | u8 | Rotor-specific injector flags |
| 0xFFFFA734/0xFFFFA738 | float | Ignition timing values — written identically by calc_ignition_all_rotors_13C2C; lead/trail split applied later in rotor_sync_gate_state_ctrl_2100A (0x2100A, unverified) |

## Control Flow

1. **Push registers** (r14-r10, fr15-fr14, pr)
2. **Load inputs:**
   - fr14 = [r12] = main injection value (0xFFFFA744)
   - fr15 = [r10] = engine speed / load
   - r11 = flag byte
   - Check mode flag at [r2]
3. **Fuel cut / enable logic:**
   - If fuel cut flag == 1: bypass normal injection logic
   - If enable flag == 1: continue with injection calculation
4. **Correction lookup:**
   - Load correction from 1D table (similar to ignition)
   - Apply to base injection value
5. **Per-rotor dispatch:**
   - Check individual rotor flags
   - Apply accumulated corrections
   - Dispatch via 0x13ED2, 0x13E6C, 0x13EE6
6. **Store results** to 0xFFFFA734/0xFFFFA738 (ignition timing values, written
   identically; lead/trail split applied later in
   rotor_sync_gate_state_ctrl_2100A (0x2100A), unverified)
7. **Pop registers and return**

## Relationship to Ignition Calculation

Both `calc_fuel_injection_all_rotors` and `calc_ignition_all_rotors_13C2C`:

- Read from the same output address (0xFFFFA744) as input
- Call the same three dispatch helpers (0x13ED2, 0x13E6C, 0x13EE6)
- Write to the same output addresses (0xFFFFA734, 0xFFFFA738), which are
  written identically by calc_ignition_all_rotors_13C2C; the lead/trail split
  is applied later in rotor_sync_gate_state_ctrl_2100A (0x2100A), unverified)
- Execute in the same scheduler tick (Phase 1 for ignition, Phase 2 for fuel)

This suggests that the final output arbitration (pressure compensation, 
leading/trailing separation) is shared between fuel and ignition subsystems.
