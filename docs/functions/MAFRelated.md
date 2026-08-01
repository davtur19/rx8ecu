# MAFRelated @ 0x1ACAE

_source: AI (Haiku) draft, unverified_

**Purpose:** Process Mass Air Flow (MAF) sensor data, compare against thresholds, and update RAW MAF and filtered MAF values with saturation logic.

**Inputs:** 
- RAM 0xFFFF9EEA: MAF ADC value (16-bit)
- RAM 0x0006F64C: MAF threshold 1
- RAM 0x0006F64E: MAF threshold 2
- RAM 0xFFFFAAB4: computed float MAF value (input)
- RAM 0xFFFF9F78: smoothed/filtered MAF (input)

**Outputs / side effects:**
- RAM 0xFFFFAAB4: updated raw MAF float
- RAM 0xFFFFAAB9: MAF counter/accumulator byte 1 (saturated 0–255)
- RAM 0xFFFFAABA: MAF counter/accumulator byte 2 (saturated 0–255)
- RAM 0xAA6C: raw MAF output float
- RAM 0xAA70: smoothed MAF output float

**Calls:**
- fixedPointToFloat_16bit_MULT_OFF_SIG @ 0x24C0 (convert ADC to float)
- addSaturate8Bit @ 0x2478 (saturating increment)

**Behavior:**
1. Load scale factor 7.62939e-05 (fixed-point multiplier)
2. Read MAF ADC (16-bit) from 0xFFFF9EEA
3. Convert to float using fixedPointToFloat_16bit_MULT_OFF_SIG
4. Compare converted value against threshold1 (0x0006F64C):
   - If >= threshold: saturate-increment counter at 0xFFFFAAB9
   - Else: reset counter to 0
5. Repeat for threshold2 (0x0006F64E) against counter at 0xFFFFAABA
6. If both counters remain < 3: write MAF floats to output locations; else hold previous values

**Draft C:**
```c
void MAFRelated(void) {
  float mafScale = 7.62939e-05f;
  u16 mafADC = readMemory16(0xFFFF9EEA);
  float mafFloat = fixedPointToFloat_16bit(mafADC, mafScale);
  
  u16 threshold1 = readMemory16(0x0006F64C);
  u8 cnt1 = readMemory8(0xFFFFAAB9);
  if ((u16)mafFloat >= threshold1) {
    cnt1 = addSaturate8Bit(cnt1, 1);
  } else {
    cnt1 = 0;
  }
  writeMemory8(0xFFFFAAB9, cnt1);
  
  u16 threshold2 = readMemory16(0x0006F64E);
  u8 cnt2 = readMemory8(0xFFFFAABA);
  if ((u16)mafFloat >= threshold2) {
    cnt2 = addSaturate8Bit(cnt2, 1);
  } else {
    cnt2 = 0;
  }
  writeMemory8(0xFFFFAABA, cnt2);
  
  if (cnt1 < 3 && cnt2 < 3) {
    writeFloatMemory(0xAA6C, readFloatMemory(0xFFFFAAB4));
    writeFloatMemory(0xAA70, readFloatMemory(0xFFFF9F78));
  }
}
```

**Confidence:** med
- Counter purpose unclear: likely MAF validation or sensor fault detection
- Threshold comparison logic inferred from conditional branches
- fixedPointToFloat_16bit verified in symbols
