# throttlePlateSomethingFuelCut @ 0xE914
**Purpose:** Compute the deceleration/overrun fuel cut logic based on the throttle position and engine operating conditions. Write the fuel cut command per rotor.
**Inputs:** Stack arguments (after prologue adjusts r15): ; Multiple float calibration values from global addresses ; Throttle position / sensor readings
**Out:** 0xFFFFA470, 0xFFFFA474, 0xFFFFA47C: intermediate float results ; 0xFFFFA484, 0xFFFFA488: 3D lookup results ; Multiple global memory writes for control state
**Calls:** 0x2068 (2DLookup): throttle-related map lookups × 2 ; 0x20DC (3DLookup): multi-axis map lookups × 2 ; 0x2500 (fixedPointToFloat_8bit_MULT_OFF_SIG): fixed-point to float conversion ; Multiple float arithmetic operations
Save the registers (r14, r13, r12, r11, r10, r9) and the float registers (fr15, fr14, fr13, fr12) ; Load the calibration floats from multiple addresses: ; 0xB594 → fr15 (engine speed) ; 0xB5A8 → fr14 (load or
pressure) ; 0xC0D8 → fr3 (throttle baseline) ; 0xA9FC → fr3 (throttle position sensor) ; 0xA448 → fr13 (fuel cut threshold) ; 0xB468 → fr3 (condition flag) ; 0xB586 → r11 (mode byte) ; 0xAAC6 → r13
(another mode/condition) ; Call 2DLookup with throttle data (0x68A88) → store 0xFFFFA470 ; Call 2DLookup with 0x68A9C → store 0xFFFFA474 ; Multiply the results: 0xFFFFA470 * 0xFFFFA474 → 0xFFFFA478 ; Call
2DLookup with 0x67824 (RPM-based) ; Load the 3D maps from 0x678D0 and 0x678EC ; Complex branches on throttle thresholds and fuel cut conditions ; Store the fuel cut flags at 0xA450 (rotor control byte)
**Draft C:**
```c
// Deceleration fuel cut determination
void throttlePlateSomethingFuelCut(void) {
  float rpm = *(float *)0xB594;
  float load = *(float *)0xB5A8;
  float throttle = *(float *)0xA9FC;
  float fuel_cut_threshold = *(float *)0xA448;
  // Throttle-based lookups
  float tps_result1 = twoD_lookup(rpm, 0x68A88);
  *(float *)0xFFFFA470 = tps_result1;
  float tps_result2 = twoD_lookup(rpm, 0x68A9C);
  *(float *)0xFFFFA474 = tps_result2;
  float combined = tps_result1 * tps_result2;
  *(float *)0xFFFFA478 = combined;
  // RPM correction
  float rpm_correction = twoD_lookup(rpm, 0x67824);
  // 3D lookups for per-rotor fuel cut
  float fuel_cut_map1 = threeD_lookup(load, throttle, 0x678D0);
  *(float *)0xFFFFA484 = fuel_cut_map1;
  float fuel_cut_map2 = threeD_lookup(load, throttle, 0x678EC);
  *(float *)0xFFFFA488 = fuel_cut_map2;
  // Determine per-rotor fuel cut flags based on thresholds
  // Store at 0xA450 (shared flag or per-rotor)
  if (throttle < threshold1) {
    *(uint8_t *)0xA450 = 1;  // Fuel cut active
  } else if (throttle < threshold2) {
    *(uint8_t *)0xA450 = 0;  // Fuel cut inactive
  }
}
```
**Status:** low ; Very large function (1204 bytes); the disassembly is complex with many branches. Core structure: load calibrations → throttle lookups → 3D fuel cut maps → store results. The exact conditional logic for fuel cut determination is not fully traced. Multiple nested conditionals make precise C decompilation uncertain. Flag storage and per-rotor application are unclear without a full trace.
