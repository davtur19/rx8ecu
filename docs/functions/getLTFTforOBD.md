# getLTFTforOBD @ 0x535CC
**Purpose:** OBD-II Mode 22 handler. Reads long-term fuel trim (LTFT), scales to 0–100%, and encodes as s8 (-100 to +99.6%).
**Inputs:** None (reads global LTFT value)
**Out:** Returns s8 in r0 (range -100 to +100, representing -100% to +100% fuel trim) ; Calls floatToInt_SIGNAL_MULT_OFFSET for scaling/offset
**Calls:** floatToInt_SIGNAL_MULT_OFFSET (0x000024D0): Scale float with multiplier/offset → s8
Load constant 100.0 → fr3 ; Load LTFT from 0xB12C (RAM) → fr4 ; Multiply fr4 * 100.0 → fr4 ; Load constant -100.0 → fr6 (lower bound) ; Load constant 0.78125 → fr5 (upper bound / scale) ; Call
floatToInt_SIGNAL_MULT_OFFSET(fr4, 100.0, 0.78125, -100.0, ???) → r0 ; Return r0 as s8
**Draft C:**
```c
int8_t getLTFTforOBD(void) {
    volatile float32 *ltft_ptr = (volatile float32 *) 0xB12C;
    float32 ltft = *ltft_ptr;
    // OBD-II PID 0x07: LTFT encoded as LTFT * 100 as s8 (-100 to +99.6%)
    float32 scaled = ltft * 100.0f;
    return floatToInt_SIGNAL_MULT_OFFSET(scaled, 100.0f, 0.78125f, -100.0f, ???);
}
```
**Status:** med (OBD encoding logic clear, RAM address unconfirmed, comparison with STFT suggests similar derivation)
Notes: Long-term fuel trim is OBD-II PID 0x07 ; Encoding: s8 = LTFT * 100, range -100 to +99.6% ; Unlike STFT, no -1.0 bias (internal LTFT baseline already 0.0) ; Scale 0.78125 = 100/128 (quantization to s8) ; UNKNOWN: confirm 0xB12C is LTFT variable
