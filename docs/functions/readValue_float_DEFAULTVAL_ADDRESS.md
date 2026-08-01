# readValue_float_DEFAULTVAL_ADDRESS @ 0x3E1AA

_source: AI (Haiku) draft, unverified_

**Purpose:** Read a 32-bit IEEE-754 single-precision float from RAM at a given address, with validation and fallback to a default float value if the data is corrupted.

**Inputs:**
- `r4` (r14): address in RAM (raw pointer, typically 0xFFFF...)
- `fr4`: default/fallback float value

**Outputs / side effects:**
- `fr0`: the read float value, or the default if validation fails
- Modifies status register (getSR/setSR pair disables/restores interrupts)

**Calls:**
- `getSR` (0x3920): save and disable interrupts
- `setMemInsideFUNCto1` (0x3E3F0): mark as invalid if data is corrupted
- `setSR` (0x3934): restore interrupts

**Behavior:**

1. Save r14, fr15 to stack (float is caller-saved)
2. Copy input address (r4) → r14
3. Copy default float from fr4 → fr15 (preserved across calls)
4. Disable interrupts via `getSR(16)`
5. Read word (16-bit) at [r14] → r3
6. Read word (16-bit) at [r14+2] → r0
7. Add r3 + r0 → r0 (sum of two halves)
8. Calculate checksum complement: ~r0 → r4, zero-extend to 16-bit
9. Read word (16-bit) at [r14+4] (first validation word) → r0
10. Compare validation: if r0 == checksum complement, continue...
11. Read word (16-bit) at [r14+6] (second validation word) → r0
12. Compare validation: if r0 == checksum complement, data is valid
13. If valid, read the float at [r14] → fr15
14. If invalid, call `setMemInsideFUNCto1` and use default (fr15 already set to default)
15. Restore interrupts via `setSR(16)`
16. Move fr15 → fr0 (return value)
17. Clean up stack and return

**Draft C:**

```c
float readValue_float_DEFAULTVAL_ADDRESS(float *addr, float default_val)
{
    float result;
    uint16_t sr = getSR(16);  // disable interrupts
    
    uint16_t w0 = ((uint16_t*)addr)[0];
    uint16_t w1 = ((uint16_t*)addr)[1];
    uint16_t sum = w0 + w1;
    uint16_t checksum = (~sum) & 0xFFFF;
    
    uint16_t val0 = ((uint16_t*)addr)[2];
    uint16_t val1 = ((uint16_t*)addr)[3];
    
    if ((val0 == checksum) && (val1 == checksum)) {
        // Valid
        result = addr[0];
    } else {
        // Invalid, use default
        setMemInsideFUNCto1(/* ... */);
        result = default_val;
    }
    
    setSR(sr);
    return result;
}
```

**Confidence:** med (float handling is clear; dual validation check is unusual but pattern fits redundancy model; exact checksum algorithm inferred from word summation)

**Uncertainties:**
- Purpose of dual validation words (offset +4, +6) unclear—may be two independent checksums or a split structure
- Whether the checksum is computed as simple sum of two halves or if there's additional processing
- Stack frame offsets and float argument passing are architecture-standard but not fully verified
- Whether addr is always a 0xFFFF... pointer or can be an index/handle
