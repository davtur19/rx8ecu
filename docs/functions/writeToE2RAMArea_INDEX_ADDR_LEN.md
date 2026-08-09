# writeToE2RAMArea_INDEX_ADDR_LEN @ 0x385C4
**Purpose:** Write a block of data to external EEPROM ("E2") with redundant (value + complement) storage for fault tolerance. Manage interrupt masking during critical writes.
**Inputs:** `r4`: index/offset or start byte count (used to compute the write range) ; `r5`: destination EEPROM address (or RAM shadow address for length) ; `r6`: source address in RAM (data to write) or count in bytes
**Out:** Writes to the EEPROM block starting at the computed address ; Stores the value at 0xFFFFC2AA (primary buffer) ; Stores the bitwise-NOT complement at 0xFFFFC3AA (complement buffer) ; Disables and restores interrupts during writes (SR saved/restored with the getSR/setSR helpers) ; Returns: none
**Calls:** `getSR()` @ 0x3920: Read the CPU status register (interrupt mask) ; `setSR(mask)` @ 0x3934: Write the CPU status register (restore the interrupt state)
Save the link register and all work registers to the stack ; Call `getSR()` to read the current interrupt state into r0 ; Load the loop count from r6 into r14 (r14 = number of bytes to write) ; Load the EEPROM primary
buffer addr 0xFFFFC2AA into r6 ; Load the EEPROM complement buffer addr 0xFFFFC3AA into r7 ; Loop (while r14 > 0): ; Read a byte from the source (r12) post-increment: `r2 = *r12++` ; Decrement the loop counter:
`r14 -= 1` ; Compute the dest offset: `r5 = r6 + (r4 extended to 16-bit)` ; Write the value to the dest: `*r5 = r2` ; Compute the complement and write it: `*(r7 + r4) = ~r2` ; Increment r4 (offset into the block) ; Call
`setSR(r0)` to restore the interrupt state ; Restore all work registers from the stack and return
**Draft C:**
```c
void writeToE2RAMArea_INDEX_ADDR_LEN(uint16_t index, uint32_t dest_addr, uint16_t length) {
    uint32_t sr = getSR();  // Save interrupt state
    volatile uint8_t *e2_primary = (uint8_t *)0xFFFFC2AA;
    volatile uint8_t *e2_complement = (uint8_t *)0xFFFFC3AA;
    volatile uint8_t *src = (uint8_t *)dest_addr;  // r12
    for (uint16_t i = 0; i < length; i++) {
        uint8_t byte_val = *src++;
        uint16_t offset = index + i;
        // Write value and complement with offset
        e2_primary[offset] = byte_val;
        e2_complement[offset] = ~byte_val;
    }
    setSR(sr);  // Restore interrupt state
}
```
**Status:** high ; The redundant write pattern (value + complement) is standard for fault-tolerant EEPROM. The getSR/setSR calls confirm the interrupt masking during the critical section. The buffer addresses match the E2 subsystem context from KNOWLEDGE.md. The loop structure and post-increment addressing are clear in the disassembly.
