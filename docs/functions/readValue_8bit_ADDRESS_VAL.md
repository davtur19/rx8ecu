# readValue_8bit_ADDRESS_VAL @ 0x3E0DC

_source: AI (Haiku) draft, unverified_

**Purpose:** Read an 8-bit value from RAM at a given address, with validation and fallback to a default value if the data is corrupted.

**Inputs:**
- `r4` (r14): address in RAM (raw pointer, typically 0xFFFF...)
- `r5`: default/fallback value (8-bit)

**Outputs / side effects:**
- `r0`: the read value (8-bit, zero-extended), or the default if validation fails
- Modifies status register (getSR/setSR pair disables/restores interrupts)

**Calls:**
- `getSR` (0x3920): save and disable interrupts
- `setMemInsideFUNCto1` (0x3E3F0): mark as invalid if data is corrupted
- `setSR` (0x3934): restore interrupts

**Behavior:**

1. Save r14 and interrupt state
2. Copy input address (r4) → r14
3. Disable interrupts via `getSR(16)`
4. Read byte at [r14] → r3 (zero-extended)
5. Read byte at [r14+1] (the checksum/complement)
6. Calculate complement of checksum: ~[r14+1]
7. **Validation check**: if complement == original value, data is valid → skip to step 8
8. If invalid, call `setMemInsideFUNCto1` with default value (r5 from stack), then use default as result
9. If valid, use the original read byte (r3) as result
10. Restore interrupts via `setSR(16)`
11. Return result in r0
12. Restore r14, pr, and return

**Draft C:**

```c
uint8_t readValue_8bit_ADDRESS_VAL(uint8_t *addr, uint8_t default_val)
{
    uint8_t result;
    uint16_t sr = getSR(16);  // disable interrupts
    
    uint8_t read_val = addr[0];
    uint8_t checksum = addr[1];
    
    if ((~checksum & 0xFF) == read_val) {
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

**Confidence:** high (structure is clear; checksum validation is redundancy pattern typical of safety-critical ECU code; getSR/setSR is standard critical-section guard)

**Uncertainties:**
- Purpose of `setMemInsideFUNCto1` call is inferred (likely logs/flags the invalid access); exact side effect unknown
- Whether addr is always a 0xFFFF... pointer or can be an index/handle is not confirmed from this function alone
