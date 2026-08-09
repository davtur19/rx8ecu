# validateAddressCopy_8bit_ADDRESS @ 0x3E29E
**Purpose:** Validate an 8-bit value at a given address with a checksum check. Return 0 if valid, 1 if invalid.
**Inputs:** `r4`: address in RAM (raw pointer, typically 0xFFFF...)
**Out:** `r0`: validation result: 0 = valid, 1 = invalid ; Modifies the status register (the getSR/setSR pair disables and restores interrupts)
**Calls:** `getSR` (0x3920): save and disable interrupts ; `SetMemoryNotValid2` (0x3E5A8): mark as invalid if the check fails ; `setSR` (0x3934): restore interrupts
Save r14 and PR to the stack ; Add -8 to SP (allocate 8 bytes of local stack) ; Copy the input address r4 → stack at [r15] ; Disable interrupts with `getSR(16)` ; Load the input address from the stack → r3 ; Read the byte at
[r3] → r2 (zero-extended) ; Read the byte at [r3+1] (checksum) ; Calculate the complement: ~checksum ; Zero-extend the complement to 8-bit ; Validation check**: if the complement == read byte, the data is valid ; If
valid, set r14 = 0 and skip to restore (step 12) ; If invalid, call `SetMemoryNotValid2` (flag/log invalid), set r14 = 1 ; Restore interrupts with `setSR(16)` ; Load the restored SR into r4 (argument for
the next call or restoration) ; Move r14 → r0 (return value) ; Clean up the stack, restore PR and r14 ; Return
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
**Status:** med-high (the checksum validation is identical to readValue_8bit; the return pattern is clear; but the SetMemoryNotValid2 semantics are unknown)
**Uncertainties:** The purpose of the `SetMemoryNotValid2` call is inferred (likely logs or flags an invalid access); the exact side effect and arguments are unknown ; How the caller uses the validation result — only the return code (0 vs 1), or is the side effect logging also important? ; Whether the call comes from an error path or from periodic validation checks
