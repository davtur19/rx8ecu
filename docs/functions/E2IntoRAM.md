# E2IntoRAM @ 0x383F8

_source: AI (Haiku) draft, unverified_

**Purpose:** Reads a block of data from external EEPROM ("E2") into RAM with cross-validation using stored (value + complement) pairs; handles E2 polling and error detection.

**Inputs:**
- `r4`: start address/index for E2 read (16-bit value stored at r15+0)
- `r5`: number of bytes to read (8-bit value stored at r15+8)
- `r6`: (unused in visible code path)

**Outputs / side effects:**
- Copies data from E2 into RAM buffers (0xFFFFC2AA primary, 0xFFFFC3AA complement)
- Performs redundancy validation: compares read value against stored complement
- Returns in `r0`: success/failure flag (1 if validated, 0 on error)
- Modifies flags at stack offsets + global state

**Calls:**
- `getSR()` @ 0x3920: Read interrupt mask
- `FUN_0000BED8()`: Poll E2 ready status (calls twice; likely waits for EEPROM idle)
- `setSR(mask)` @ 0x3934: Restore interrupt state

**Behavior:**

1. Save r8-r14, PR to stack; allocate 32 bytes of local frame
2. Store r4 (address) and r5 (length) in local frame at offsets 0 and 8
3. Call `getSR()` to save interrupt state (stack @ offset 20)
4. Call `FUN_0000BED8()` twice; retry if result ≠ 1 (wait for E2 ready)
5. If both polls fail, set r9=0 (failure) and jump to exit
6. Load E2 buffer addresses: r8=0xFFFFC2AA (values), r14=0xFFFFC3AA (complements)
7. Set up nested loop counters:
   - Outer: loop over read addresses (increment by 1)
   - Inner: per address, process 2 bytes (value + complement)
8. For each E2 location:
   - Read value byte from E2 primary buffer
   - Read complement byte from E2 complement buffer
   - Validate: if value ≠ ~complement, set r9=0 and exit
   - Write validated byte to destination RAM
9. Increment address pointers and repeat until length exhausted
10. Call `setSR()` to restore interrupts
11. Move r9 (result flag) into r0 and return

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

**Confidence:** med
- E2 subsystem integration (buffer addresses, ready polling) confirmed
- Redundant validation pattern matches writeToE2RAMArea
- Nested validation logic in ASM is complex; simplified in C model
- Loop termination condition verified against computed block size
- Uncertainties: exact E2 address mapping, alternate storage location logic, why FUN_0000BED8 is called twice
