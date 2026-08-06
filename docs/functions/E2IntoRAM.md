# E2IntoRAM @ 0x383F8
**Purpose:** Reads an E2 (external EEPROM) block into RAM with (value + complement) cross-validation; handles E2 polling and error detection.
**Inputs:** `r4`: start address/index for E2 read (16-bit value stored at r15+0) ; `r5`: number of bytes to read (8-bit value stored at r15+8) ; `r6`: (unused in visible code path)
**Out:** Copies data from E2 into RAM buffers (0xFFFFC2AA primary, 0xFFFFC3AA complement) ; Performs redundancy validation: compares read value against stored complement ; Returns in `r0`: success/failure flag (1 if validated, 0 on error) ; Modifies flags at stack offsets + global state
**Calls:** `getSR()` @ 0x3920: Read interrupt mask ; `FUN_0000BED8()`: Poll E2 ready status (calls twice; likely waits for EEPROM idle) ; `setSR(mask)` @ 0x3934: Restore interrupt state
Save r8-r14, PR to stack; allocate 32 bytes of local frame ; Store r4 (address) and r5 (length) in local frame at offsets 0 and 8 ; Call `getSR()` to save interrupt state (stack @ offset 20) ; Call
`FUN_0000BED8()` twice; retry if result ≠ 1 (wait for E2 ready) ; If both polls fail, set r9=0 (failure) and jump to exit ; Load E2 buffer addresses: r8=0xFFFFC2AA (values), r14=0xFFFFC3AA
(complements) ; Set up nested loop counters: ; Outer: loop over read addresses (increment by 1) ; Inner: per address, process 2 bytes (value + complement) ; For each E2 location: ; Read value byte
from E2 primary buffer ; Read complement byte from E2 complement buffer ; Validate: if value ≠ ~complement, set r9=0 and exit ; Write validated byte to destination RAM ; Increment address pointers and
repeat until length exhausted ; Call `setSR()` to restore interrupts ; Move r9 (result flag) into r0 and return
**Draft C:**
```c
uint8_t E2IntoRAM(uint16_t e2_addr, uint8_t length) {
    uint32_t sr = getSR();  // Save interrupt state
    // Poll E2 ready twice
    if (FUN_0000BED8() != 1) {
        if (FUN_0000BED8() != 1) {
            setSR(sr);
            return 0;  // E2 not ready
        }
    }
    volatile uint8_t *e2_primary = (uint8_t *)0xFFFFC2AA;
    volatile uint8_t *e2_complement = (uint8_t *)0xFFFFC3AA;
    uint8_t result = 1;
    for (uint16_t offset = 0; offset < length; offset++) {
        uint8_t value = e2_primary[offset];
        uint8_t complement = e2_complement[offset];
        // Validate redundancy
        if (value != (complement ^ 0xFF)) {
            // Try alternate storage location (cross-validation)
            // ... (complex nested validation logic in ASM)
            result = 0;
            break;
        }
    }
    setSR(sr);  // Restore interrupts
    return result;
}
```
**Status:** med — E2 integration confirmed; validation matches writeToE2RAMArea; ASM validation simplified in C; unsure: E2 address mapping, alternate storage logic, why FUN_0000BED8 is called twice.
