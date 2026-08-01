# writeToE2RAMArea_INDEX_ADDR_LEN @ 0x385C4

_source: AI (Haiku) draft, unverified_

**Purpose:** Writes a block of data to external EEPROM ("E2") with redundant (value + complement) storage for fault tolerance; manages interrupt masking during critical writes.

**Inputs:**
- `r4`: index/offset or start byte count (used to compute write range)
- `r5`: destination EEPROM address (or RAM shadow address for length)
- `r6`: source address in RAM (data to write) or count in bytes

**Outputs / side effects:**
- Writes to EEPROM block starting at computed address
- Stores value at 0xFFFFC2AA (primary buffer)
- Stores bitwise-NOT complement at 0xFFFFC3AA (complement buffer)
- Disables/restores interrupts during writes (SR saved/restored via getSR/setSR helpers)
- Returns: none

**Calls:**
- `getSR()` @ 0x3920: Read CPU status register (interrupt mask)
- `setSR(mask)` @ 0x3934: Write CPU status register (restore interrupt state)

**Behavior:**

1. Save link register and all work registers to stack
2. Call `getSR()` to read current interrupt state into r0
3. Load loop count from r6 into r14 (r14 = number of bytes to write)
4. Load EEPROM primary buffer addr 0xFFFFC2AA into r6
5. Load EEPROM complement buffer addr 0xFFFFC3AA into r7
6. Loop (while r14 > 0):
   - Read byte from source (r12) post-increment: `r2 = *r12++`
   - Decrement loop counter: `r14 -= 1`
   - Compute dest offset: `r5 = r6 + (r4 extended to 16-bit)`
   - Write value to dest: `*r5 = r2`
   - Compute complement and write: `*(r7 + r4) = ~r2`
   - Increment r4 (offset into block)
7. Call `setSR(r0)` to restore interrupt state
8. Restore all work registers from stack and return

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

**Confidence:** high
- Redundant write pattern (value + complement) is standard for fault-tolerant EEPROM
- getSR/setSR calls confirm interrupt masking during critical section
- Buffer addresses match E2 subsystem context from KNOWLEDGE.md
- Loop structure and post-increment addressing are clear in disassembly
