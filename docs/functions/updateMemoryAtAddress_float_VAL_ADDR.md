# updateMemoryAtAddress_float_VAL_ADDR @ 0x3E258
**Purpose:** Write a 32-bit IEEE-754 single-precision float to RAM together with redundant checksum validation words. Use interrupt masking.
**Inputs:** `fr4`: float value to write ; `r4` (r13): target address in RAM
**Out:** Writes the float at [addr], the checksum/validation at [addr+2], [addr+4], [addr+6] ; Returns r0 = 0 on success, 1 on NaN or invalid input ; Modifies the status register (the getSR/setSR pair disables and restores interrupts)
**Calls:** `getSR` (0x3920): save and disable interrupts ; `setSR` (0x3934): restore interrupts
Save r14, r13, fr15 to the stack ; Copy the float input fr4 → fr15 (preserve it across calls) ; Save the PR register ; Check if fr4 is NaN: fcmp/eq fr15, fr15 (NaN != NaN) ; If NaN is detected, jump to the error path
(return r0 = 1) ; Copy the target address r4 → r13 (preserve it for the write) ; Copy the stack pointer (r15) → r4 (create a local buffer) ; Write the float to the buffer: fmov.s fr15, @r4 ; Read the buffer words to compute the
checksum: ; Read the word at [r4+0] → r3 ; Read the word at [r4+2] → r0 ; Sum: r0 = r3 + r0 ; Compute the checksum complement: ~r0 → r14, zero-extend to 16-bit ; Disable interrupts with `getSR(16)` ; Write the float
to the target: fmov.s fr15, @r13 ; Write the checksum to [r13+4]: mov.w r0 (complement), @(4, r13) ; Write the checksum to [r13+6]: mov.w r0 (complement), @(6, r13) ; Restore interrupts with `setSR(16)` ; Return
r0 = 0 (success) ; Error path: return r0 = 1 (NaN detected)
**Draft C:**
```c
int updateMemoryAtAddress_float_VAL_ADDR(float value, float *addr)
{
    if (isnan(value)) {
        return 1;  // invalid
    }
    uint16_t sr = getSR(16);  // disable interrupts
    // Compute checksum
    uint16_t *w = (uint16_t*)&value;
    uint16_t sum = w[0] + w[1];
    uint16_t checksum = (~sum) & 0xFFFF;
    // Write to RAM
    addr[0] = value;
    ((uint16_t*)addr)[2] = checksum;
    ((uint16_t*)addr)[3] = checksum;
    setSR(sr);
    return 0;  // success
}
```
**Status:** med (the float NaN check is clear; the checksum computation mirrors readValue_float; but the dual validation word semantics are unclear)
**Uncertainties:** Why dual validation words at offsets +4 and +6? They may be (a) redundant copies, (b) split validation, or (c) structure-dependent layout. ; Whether the checksum is the simple sum of the two float halves or uses additional calculation ; The NaN return path (r0=1) suggests that the caller handles errors, but the exact semantics are unknown ; The stack buffer usage for the intermediate checksum computation is inferred
