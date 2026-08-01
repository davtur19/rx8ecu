# readValue_16bit_ADDRESS_VAL @ 0x3E11C

_source: AI (Haiku) draft, unverified_

**Purpose:** Read a 16-bit value from RAM at a given address, with validation and fallback to a default value if the data is corrupted (mirror of 8-bit version for 16-bit data).

**Inputs:**
- `r4` (r14): address in RAM (raw pointer, typically 0xFFFF...)
- `r5`: default/fallback value (16-bit)

**Outputs / side effects:**
- `r0`: the read value (16-bit, zero-extended), or the default if validation fails
- Modifies status register (getSR/setSR pair disables/restores interrupts)

**Calls:**
- `getSR` (0x3920): save and disable interrupts
- `setMemInsideFUNCto1` (0x3E3F0): mark as invalid if data is corrupted
- `setSR` (0x3934): restore interrupts

**Behavior:**

1. Save r14 and interrupt state
2. Copy input address (r4) → r14
3. Disable interrupts via `getSR(16)`
4. Read word (16-bit) at [r14] → r3 (zero-extended)
5. Read word (16-bit) at [r14+2] (the checksum/complement)
6. Calculate complement: ~[r14+2]
7. **Validation check**: if complement == original value, data is valid
8. If invalid, call `setMemInsideFUNCto1` with default value (r5 from stack), then use default as result
9. If valid, use the original read word (r3) as result
10. Restore interrupts via `setSR(16)`
11. Return result in r0
12. Restore r14, pr, and return

**Draft C:**

```c
uint16_t readValue_16bit_ADDRESS_VAL(uint16_t *addr, uint16_t default_val)
{
    uint16_t result;
    uint16_t sr = getSR(16);  // disable interrupts
    
    uint16_t read_val = addr[0];
    uint16_t checksum = addr[1];
    
    if ((~checksum & 0xFFFF) == read_val) {
        // Valid
        result = read_val;
    } else {
        // Invalid, use default
        setMemInsideFUNCto1(default_val);
        result = default_val;
    }
    
    setSR(sr);
    return result;
}
```

**Confidence:** high (mirrors 8-bit structure exactly; confirms checksum validation pattern)

**Uncertainties:**
- Same as 8-bit version: setMemInsideFUNCto1 purpose inferred, exact behavior unknown
