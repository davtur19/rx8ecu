# getMAFSensorValue @ 0x7438
**Purpose:** Read raw MAF sensor ADC value, apply calibration lookup and scaling factor, compute flag for out-of-range condition.
**Inputs:** None (reads global MAF raw value)
**Out:** Reads raw MAF ADC from RAM at 0xFFFF9EEA ; Calls 2DLookup with MAF value and scaling factor ; Writes scaled MAF sensor value to 0xFFFF9F78 ; Writes status flag (0=normal, 1=high, 2=low) to 0xFFFF9F7C ; Return: None
**Calls:** `0x00002068` (2DLookup) - 2D calibration map lookup: (inputs in r3=MAF_raw, fr4=scale_factor) -> (output in fr0=scaled_value)
Load raw MAF sensor value from 0xFFFF9EEA (16-bit) ; Convert to float with the FPU (lds fpul, fmov to fr3) ; Load scale factor from 0x7490 = 7.62939e-05 (fixed-point to float conversion) ; Multiply MAF by
scale factor into fr4 ; Call 2DLookup (r3=0x67F28, r4 has MAF scaled) ; Store result to 0xFFFF9F78 ; Compare MAF value against upper/lower limits: ; Upper limit from 0x6D402 ; Lower limit from 0x6D404
; Set flag: 0=normal, 1=exceeds upper, 2=exceeds lower ; Store flag to 0xFFFF9F7C
**Draft C:**
```c
void getMAFSensorValue(void) {
  u16 maf_raw = *(u16*)0xFFFF9EEA;
  float scale = 7.62939e-05f;
  float maf_scaled = (float)maf_raw * scale;
  // Call 2DLookup with calibration table
  float maf_processed = TwoDLookup(0x67F28, maf_scaled);
  *(float*)0xFFFF9F78 = maf_processed;
  u16 upper_limit = *(u16*)0x6D402;
  u16 lower_limit = *(u16*)0x6D404;
  u8 status = 0;
  if (maf_raw > upper_limit) {
    status = 1;
  } else if (maf_raw >= lower_limit) {
    status = 2;
  }
  *(u8*)0xFFFF9F7C = status;
}
```
**Status:** med — the flow is clear (read, scale, lookup, check bounds) but the exact meaning of the lookup table address and bound semantics need verification.
