# getMAFOBD @ 0x5368E

_source: AI (Haiku) draft, unverified_

**Purpose:** OBD-II Mode 22 handler. Reads mass air flow (MAF) sensor value, validates status, and encodes as u16 (0–655.35 g/s).

**Inputs:** None (reads global MAF value and status)

**Outputs / side effects:**
- Returns u16 in r0 (0–655.35 g/s encoded as 0–65535 with scale 0.01 g/s per count)
- Calls floatToFP_16bit_NUMBER_SCALAR_OFFSET for scaling

**Calls:**
- floatToFP_16bit_NUMBER_SCALAR_OFFSET (0x00002490): Scale float → u16 with offset/scale

**Behavior:**
1. Load status flag from 0xA41C (RAM) → r0
2. If r0 != 1, return r4 = 0 (invalid status)
3. Load MAF value from 0xAA74 (RAM) → fr4
4. Load constant 0.0 → fr6 (lower bound / offset)
5. Load constant 0.01 (scale) → fr5
6. Call floatToFP_16bit_NUMBER_SCALAR_OFFSET(fr4, ???, 0.01f, 0.0f, ???) → r0
7. Return r0 as u16

**Draft C:**
```c
uint16_t getMAFOBD(void) {
    volatile uint8_t *maf_status_ptr = (volatile uint8_t *) 0xA41C;
    volatile float32 *maf_ptr = (volatile float32 *) 0xAA74;
    
    uint8_t status = *maf_status_ptr;
    if (status != 1) {
        return 0;  // MAF sensor not ready or invalid
    }
    
    float32 maf_g_per_s = *maf_ptr;
    // OBD-II PID 0x10: MAF as u16 with scale 0.01 g/s per count
    // Range 0–655.35 g/s encoded as 0–65535
    return floatToFP_16bit_NUMBER_SCALAR_OFFSET(maf_g_per_s, ???, 0.01f, 0.0f, ???);
}
```

**Notes:**
- Mass air flow is OBD-II PID 0x10
- Encoding: u16 = MAF / 0.01 (or MAF * 100) where MAF in g/s
- Range 0–655.35 g/s (typical rotary engine MAF ~200–400 g/s at load)
- Status check at 0xA41C (likely shared with other sensors) gates validity
- floatToFP_16bit_* converts to u16 (fixed-point), different from floatToInt_* (u8)
- UNKNOWN: confirm 0xAA74 is MAF value, 0xA41C status meaning

**Confidence:** med (OBD encoding standard for MAF clear, RAM addresses unconfirmed, u16 output width distinct from other PIDs)
