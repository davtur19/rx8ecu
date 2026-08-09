# getEngineLoadforOBD @ 0x53530
**Purpose:** OBD-II Mode 22 (readDataByIdentifier) handler. Reads live engine load, validates with a divide-by-zero check, scales to 0–100%, and encodes as u8 (0–255).
**Inputs:** None (reads global engine load value)
**Out:** Returns u8 in r0 (0–255, representing 0–100% engine load) ; Calls floatToInt_SIGNAL_MULT_OFFSET to perform scaling/offset conversion
**Calls:** isNotZero_wDivideByZero_Protect (0x00002440): Check divisor for zero; return 0 if div-by-zero detected ; floatToInt_SIGNAL_MULT_OFFSET (0x000024D0): Scale float → u8 with multiplier and offset
Save fr13, fr14, fr15 (callee-save FP regs) ; Load engine load from 0xC0D8 (RAM) → fr14 ; Load max engine load (limit) from 0xC0DC (RAM) → fr15 ; Load constant 1e-05 → fr6 (epsilon for zero check) ;
Call isNotZero_wDivideByZero_Protect(fr14, fr15, fr6) → r0 ; If r0 == 0, return immediately with r4 = 0 ; Check flag at 0xA41C; if == 1, load engine load; else return 0 ; Scale: fr14 * 100.0 / fr15 →
fr4 ; Call floatToInt_SIGNAL_MULT_OFFSET(fr4, fr15=100, fr5=0.392157, fr6=0, offset_val) → r0 ; Return r0 as u8
**Draft C:**
```c
uint8_t getEngineLoadforOBD(void) {
    volatile float32 *eng_load_ptr = (volatile float32 *) 0xC0D8;
    volatile float32 *max_load_ptr = (volatile float32 *) 0xC0DC;
    volatile uint8_t *status_ptr = (volatile uint8_t *) 0xA41C;
    float32 eng_load = *eng_load_ptr;
    float32 max_load = *max_load_ptr;
    if (!isNotZero_wDivideByZero_Protect(eng_load, max_load, 1e-05f)) {
        return 0;  // div-by-zero detected
    }
    if (*status_ptr != 1) {
        return 0;  // status check failed
    }
    float32 normalized = (eng_load * 100.0f) / max_load;
    return floatToInt_SIGNAL_MULT_OFFSET(normalized, 100.0f, 0.392157f, 0.0f, ???);
}
```
**Status:** med (structure clear, RAM addresses unconfirmed, scaling multiplier 0.392157 approximate)
Notes: Engine load encodes as 0–255 representing 0–100% (OBD-II PID 0x04) ; Scale factor 0.392157 ≈ 100/255 (quantization to u8) ; Divide-by-zero check protects against invalid calibration state ; Status flag at 0xA41C gates whether to report valid data
