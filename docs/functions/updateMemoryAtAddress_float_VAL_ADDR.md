# updateMemoryAtAddress_float_VAL_ADDR @ 0x3E258
**Purpose:** Write a 32-bit IEEE-754 single-precision float to RAM along with redundant checksum validation words, with interrupt masking.
**Inputs:** `fr4`: float value to write ; `r4` (r13): target address in RAM
**Out:** Writes float at [addr], checksum/validation at [addr+2], [addr+4], [addr+6] ; Returns r0 = 0 on success, 1 on NaN or invalid input ; Modifies status register (getSR/setSR pair disables/restores interrupts)
**Calls:** `getSR` (0x3920): save and disable interrupts ; `setSR` (0x3934): restore interrupts
Save r14, r13, fr15 to stack ; Copy float input fr4 → fr15 (preserve across calls) ; Save PR register ; Check if fr4 is NaN: fcmp/eq fr15, fr15 (NaN != NaN) ; If NaN detected, jump to error path
(return r0 = 1) ; Copy target address r4 → r13 (preserve for write) ; Copy stack pointer (r15) → r4 (create local buffer) ; Write float to buffer: fmov.s fr15, @r4 ; Read buffer words to compute
checksum: ; Read word at [r4+0] → r3 ; Read word at [r4+2] → r0 ; Sum: r0 = r3 + r0 ; Compute checksum complement: ~r0 → r14, zero-extend to 16-bit ; Disable interrupts via `getSR(16)` ; Write float
to target: fmov.s fr15, @r13 ; Write checksum to [r13+4]: mov.w r0 (complement), @(4, r13) ; Write checksum to [r13+6]: mov.w r0 (complement), @(6, r13) ; Restore interrupts via `setSR(16)` ; Return
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
**Status:** med (float NaN check is clear; checksum computation mirrors readValue_float; but dual validation word semantics unclear)
**Uncertainties:** Why dual validation words at offsets +4 and +6? May be (a) redundant copies, (b) split validation, or (c) structure-dependent layout ; Whether the checksum is the simple sum of the two float halves or if there's additional processing ; NaN return path (r0=1) suggests caller error handling, but exact semantics unknown ; Stack buffer usage for intermediate checksum computation is inferred
