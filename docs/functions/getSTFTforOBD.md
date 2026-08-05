# getSTFTforOBD @ 0x535A6
**Purpose:** OBD-II Mode 22 handler. Reads short-term fuel trim (STFT), adds -1.0 bias, scales to 0–100%, and encodes as s8 (-100 to +99.6%).
**Inputs:** None (reads global STFT value)
**Out:** Returns s8 in r0 (range -100 to +100, representing -100% to +100% fuel trim in OBD-II units) ; Calls floatToInt_SIGNAL_MULT_OFFSET for scaling/offset
**Calls:** floatToInt_SIGNAL_MULT_OFFSET (0x000024D0): Scale float with multiplier/offset clamped to s8 range
Load constant 1.0 → fr3 ; Negate to -1.0 → fr3 ; Load STFT from 0xAE50 (RAM) → fr2 ; Add -1.0 to fr2 → fr2 (fr2 now contains STFT - 1.0) ; Load constant 100.0 → fr1 ; Multiply fr2 * 100.0 → fr4 ; Load
constant -100.0 → fr6 (lower bound) ; Load constant 0.78125 → fr5 (upper bound / scale) ; Call floatToInt_SIGNAL_MULT_OFFSET(fr4, 100.0, 0.78125, -100.0, ???) → r0 ; Return r0 as s8
**Draft C:**
```c
int8_t getSTFTforOBD(void) {
    volatile float32 *stft_ptr = (volatile float32 *) 0xAE50;
    float32 stft = *stft_ptr;
    // OBD-II PID 0x06: STFT encoded as (STFT - 1.0) * 100 as s8 (-100 to +99.6)
    float32 biased = stft - 1.0f;
    float32 scaled = biased * 100.0f;
    return floatToInt_SIGNAL_MULT_OFFSET(scaled, 100.0f, 0.78125f, -100.0f, ???);
}
```
**Status:** med (OBD encoding logic clear, RAM address unconfirmed)
Notes: Fuel trim is OBD-II PID 0x06 (STFT) ; Encoding: s8 = ((STFT - 1.0) * 100), range -100 to +99.6% ; The -1.0 bias converts from internal 0.0 baseline to OBD-II -100% minimum ; Scale 0.78125 = 100/128 (quantization to s8: -128 to +127 → -100 to +99.6%) ; UNKNOWN: confirm 0xAE50 is STFT variable
