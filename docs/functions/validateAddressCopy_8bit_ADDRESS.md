# validateAddressCopy_8bit_ADDRESS @ 0x3E29E

_source: AI (Haiku) draft, unverified_

**Purpose:** Validate an 8-bit value at a given address by checking checksum; return 0 if valid, 1 if invalid.

**Inputs:**
- `r4`: address in RAM (raw pointer, typically 0xFFFF...)

**Outputs / side effects:**
- `r0`: validation result: 0 = valid, 1 = invalid
- Modifies status register (getSR/setSR pair disables/restores interrupts)

**Calls:**
- `getSR` (0x3920): save and disable interrupts
- `SetMemoryNotValid2` (0x3E5A8): mark as invalid if check fails
- `setSR` (0x3934): restore interrupts

**Behavior:**

1. Save r14 and PR to stack
2. Add -8 to SP (allocate 8 bytes local stack)
3. Copy input address r4 → stack at [r15]
4. Disable interrupts via `getSR(16)`
5. Load input address from stack → r3
6. Read byte at [r3] → r2 (zero-extended)
7. Read byte at [r3+1] (checksum)
8. Calculate complement: ~checksum
9. Zero-extend complement to 8-bit
10. **Validation check**: if complement == read byte, data is valid
11. If valid, set r14 = 0 and skip to restore (step 12)
12. If invalid, call `SetMemoryNotValid2` (flag/log invalid), set r14 = 1
13. Restore interrupts via `setSR(16)`
14. Load restored SR into r4 (argument for next call or restoration)
15. Move r14 → r0 (return value)
16. Clean up stack, restore PR and r14
17. Return

**Draft C:**

```c
int validateAddressCopy_8bit_ADDRESS(uint8_t *addr)
{
    uint16_t sr = getSR(16);  // disable interrupts
    
    uint8_t read_val = addr[0];
    uint8_t checksum = addr[1];
    
    int result = 0;
    if ((~checksum & 0xFF) != read_val) {
        // Invalid
        SetMemoryNotValid2(/* ... */);
        result = 1;
    }
    
    setSR(sr);
    return result;
}
```

**Confidence:** med-high (checksum validation is identical to readValue_8bit; return pattern is clear; but SetMemoryNotValid2 semantics unknown)

**Uncertainties:**
- Purpose of `SetMemoryNotValid2` call is inferred (likely logs/flags invalid access); exact side effect and arguments unknown
- How result of validation is used by caller—only return code (0 vs 1), or side effect logging is also important?
- Whether this is called from error-recovery paths or periodic validation checks
