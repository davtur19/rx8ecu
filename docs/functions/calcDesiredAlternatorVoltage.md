# calcDesiredAlternatorVoltage @ 0x26520
**Purpose:** Calculate the desired alternator voltage output. The calculation uses battery temperature, vehicle load conditions, and thermal constraints. It implements a complex multi-stage state machine with multiple operating modes.
**Inputs:** RAM 0xA9FC: engine coolant or battery temperature (float) ; RAM 0xAE40: reference temperature offset (float) ; RAM 0xBBE8: alternator current or load indicator (float) ; RAM 0xB694: voltage adjustment factor (float) ; RAM 0xC6A8: system mode flag or condition (float) ; RAM 0xAACC: vehicle load or state byte ; RAM 0xAAC6: thermal warning flag byte ; RAM 0xB129: battery state flag byte ; RAM 0xCEF2: operational mode flag byte ; RAM 0x74AD4..0x74AE0: multiple calibration/limit floats (6 values) ; RAM 0xB686, 0xB687, 0xB688: three output control bytes
**Out:** RAM 0xB686: alternator control byte 1 (0=low volt, 1=high volt) ; RAM 0xB687: alternator control byte 2 ; RAM 0xB688: alternator control byte 3 ; RAM 0xB66B: alternator state indicator (byte) ; RAM 0xB66C: output voltage register (float)
**Calls:** saturateLow_SIGNAL_LOWERBOUND @ 0x23E4 (clamp minimum) ; minValue @ 0x23F4 (return minimum of two values) ; isNotZero_wDivideByZero_Protect @ 0x2440 (safe zero check) ; alternatorPIDsomething @ 0x5B394 (PID controller or state update) ; addSaturate8Bit @ 0x2478 (saturating increment for state byte)
Read multiple input parameters (temperature, load, mode flags). Initialize the output control bytes to 0 (low voltage mode). Load the calibration limits into floating-point registers fr7, fr8, fr13, fr14,
fr15. Perform nested comparisons against thresholds. Compare the base temperature (fr7) against the load limits. If it is within range 1: set ctrl byte 1 to 0 (low); if above range: set it to 1 (high). Repeat for
two additional control stages with different threshold pairs. Check the mode flag (0xCEF2, r15). If mode == 1: apply the special voltage calculation logic. Else: use the alternate calculation path. For mode
1: load the upper/lower voltage bounds from calibration. Compare the current voltage (fr14) against the bounds. Conditionally apply a saturating decrement or increment to the control bytes. For the alternate mode:
check the secondary flags (0xB66A, 0xB688). Apply the minValue logic to select the voltage output. Call isNotZero_wDivideByZero_Protect to validate the non-zero scaling factor. Call alternatorPIDsomething to
update the final voltage or state. Call addSaturate8Bit to manage the state counter (0xB680) with saturation.
**Draft C:**
```c
void calcDesiredAlternatorVoltage(void) {
  float tempLoad = readFloatMemory(0xA9FC);
  float refOffset = readFloatMemory(0xAE40);
  float altCurrent = readFloatMemory(0xBBE8);
  float voltAdj = readFloatMemory(0xB694);
  // Load calibration limits
  float lim1 = readFloatMemory(0x74AD4);
  float lim2 = readFloatMemory(0x74AD8);
  float lim3 = readFloatMemory(0x74ADC);
  u8 ctrlMode = readMemory8(0xCEF2);
  // First voltage control stage
  if (tempLoad > lim1) {
    writeMemory8(0xB686, 0);
  } else {
    float upper1 = readFloatMemory(0xB694);
    if (tempLoad < upper1) {
      writeMemory8(0xB686, 1);
    }
  }
  // Second voltage control stage
  if (tempLoad > lim2) {
    writeMemory8(0xB687, 0);
  } else {
    float upper2 = readFloatMemory(0xB687);
    if (tempLoad < upper2) {
      writeMemory8(0xB687, 1);
    }
  }
  // Third voltage control stage
  if (altCurrent > lim1) {
    writeMemory8(0xB688, 1);
  } else if (altCurrent < (lim1 - lim3)) {
    writeMemory8(0xB688, 0);
  }
  // Mode-specific processing
  if (ctrlMode == 1) {
    float currentVolt = readFloatMemory(0xB66C);
    float upperBound = readFloatMemory(0x74B0C);
    float lowerBound = readFloatMemory(0x74B10);
    float adjusted = saturateLow(currentVolt - upperBound, lowerBound);
    float result = adjusted - minValue(currentVolt, lim1);
    writeFloatMemory(0xB66C, result);
  } else {
    // Alternate voltage calculation
  }
  // PID update and state counter increment
  u32 scaleFactor = isNotZero_wDivideByZero_Protect(readFloatMemory(0xB5E8));
  if (scaleFactor) {
    alternatorPIDsomething(readFloatMemory(0xB66C));
    u8 stateCounter = readMemory8(0xB680);
    stateCounter = addSaturate8Bit(stateCounter, 1);
    writeMemory8(0xB680, stateCounter);
  }
}
```
**Status:** low ; The function implements a multi-stage state machine; the exact operating modes are unclear ; The voltage regulation logic is non-standard (not typical PID); the purpose of each stage is unknown ; The mode selection (ctrlMode) purpose is unclear ; The control byte outputs (0xB686, 0xB687, 0xB688) may be discrete control signals or state indicators ; The calibration table meanings require deeper RE or ECU documentation
