# MAFStuffMaybeVE @ 0x20EEC
**Purpose:** Calculate volumetric efficiency (VE) or apply MAF-related calibration adjustments. The calculation uses the operating conditions and lookup tables.
**Inputs:** RAM 0xBE1C: MAF value (float, fr15) ; RAM 0xAA74: corrected/reference value (float, fr14) ; RAM 0xB348: intermediate calculation (float) ; RAM 0xB594: lookup table input (float) ; RAM 0x00068678: 2D lookup table address ; RAM 0xB280: constraint/threshold (float) ; RAM 0xFFFFB238: calculated result register (float) ; Multiple limit calibration addresses (0x72594, 0x7256A, 0x7256C)
**Out:** RAM 0xFFFFB238: calculated VE or MAF adjustment value (float) ; RAM 0xFFFFB296: lookup result (16-bit word) ; RAM 0xFFFFB290: output/state float
**Calls:** 2DLookup_FP_16bit @ 0x20C4 (fixed-point 16-bit lookup, fr4=input, r4=table addr)
Load MAF value (fr15) and reference (fr14 from 0xAA74) ; Load calibration constant 100.0 ; Divide: (intermediate value * fr14) / 100.0 → fr3 (normalized comparison) ; Perform 2DLookup_FP_16bit with
input from 0xB594, table at 0x68678 ; Store result as 16-bit word in 0xFFFFB296 ; Load result, scale by 4 (shll2) to use as offset into result register 0xFFFFB238 ; Compare result against threshold at
0xB280: ; If result < threshold: check upper bound conditions (0x72594, 0x7256A) ; If upper bound OK: load calibration from 0x72598 or 0x7259C (conditional) ; Else: load from 0x725A0 (alternate
calibration) ; Write final float result to 0xFFFFB290
**Draft C:**
```c
void MAFStuffMaybeVE(void) {
  float mafVal = readFloatMemory(0xBE1C);
  float refVal = readFloatMemory(0xAA74);
  float intermediate = readFloatMemory(0xB348);
  float normalized = (intermediate * refVal) / 100.0f;
  float lookupInput = readFloatMemory(0xB594);
  u16 lookupResult = twoD_Lookup_FP_16bit(lookupInput, (void*)0x68678);
  writeMemory16(0xFFFFB296, lookupResult);
  float threshold = readFloatMemory(0xB280);
  float resultFloat = (float)lookupResult;
  if (resultFloat < threshold) {
    u16 upperBound1 = readMemory16(0x7256A);
    u16 upperBound2 = readMemory16(0x7256C);
    if (mafVal <= upperBound1) {
      float calibration = readFloatMemory(0x72598);
      writeFloatMemory(0xFFFFB290, calibration);
    } else {
      float calibration = readFloatMemory(0x7259C);
      writeFloatMemory(0xFFFFB290, calibration);
    }
  } else {
    float calibration = readFloatMemory(0x725A0);
    writeFloatMemory(0xFFFFB290, calibration);
  }
}
```
**Status:** med ; Volumetric efficiency (VE) purpose inferred from complexity and lookup pattern ; Exact parameter meanings unclear (intermediate calculation purpose, reference normalization) ; Threshold logic and upper bound conditions inferred from conditional branches ; Lookup table address verified in extraction
