# calledLots @ 0xA2B6

_source: AI (Haiku) draft, unverified_

**Purpose:** Increment a counter byte at a RAM address, with saturation at 0xFF. Wraps SR (interrupt mask) save/restore around the critical operation.

**Inputs:**
- r4: offset or direct address (u16)
- Uses implicit globals for SR management

**Outputs / side effects:**
- r0: return value (unknown, possibly the updated counter value)
- Modifies byte @ (0xFFFFA18B + r4) — increments if < 0xFF

**Calls:**
- setSR_PARAM @ 0x2054: save and apply interrupt mask from stack frame
  - Args: r4 = stack frame address (r15)
- loadStatusRegister_ADDR @ 0x2064: restore SR from saved value
  - Args: r4 = saved SR value

**Behavior:**
1. Save pr to stack
2. Create 8-byte stack frame (add #-8, r15)
3. Write input r4 to stack @ offset +4 (r15+4)
4. Load mask 0x00E0 into r5 (interrupt level, probably)
5. Call setSR_PARAM(r15):
   - Saves current SR
   - Applies/changes SR based on r5 mask
6. Load stored r4 from stack+4
7. Add r4 to base address 0xFFFFA18B (RAM array base)
8. Load byte @ (base + r4) into r3
9. Compare r3 to 0xFF (saturation check)
10. If r3 >= 0xFF: jump to restore (skip increment)
11. If r3 < 0xFF: load byte, increment, write back
12. Call loadStatusRegister_ADDR(saved_sr):
    - Restore previous SR
13. Return

**Draft C:**
```c
void calledLots(u16 offset) {
  u32 saved_sr = getSR();
  
  // Apply interrupt mask 0x00E0 (mask certain interrupt levels)
  setSR_with_mask(0x00E0);
  
  u8 *counter = (u8 *)(0xFFFFA18B + offset);
  
  // Increment with saturation at 0xFF
  if (*counter < 0xFF) {
    (*counter)++;
  }
  
  // Restore SR
  setSR(saved_sr);
}

// Or more concisely:
u8 increment_saturating_counter(u16 array_offset) {
  u32 saved_sr = setSR_with_mask(0x00E0);
  
  u8 *counter = (u8 *)(0xFFFFA18B + array_offset);
  if (*counter < 0xFF) {
    (*counter)++;
  }
  
  setSR(saved_sr);
  return *counter;
}
```

**Confidence:** high
- Interrupt masking and critical section pattern is standard
- Counter saturation logic is clear
- Address base 0xFFFFA18B is definite
- All functions called are properly identified

**Uncertainties:**
- What is the semantic purpose of the counter array? (Probably: event counters, fault counts, diagnostic counters)
- What interrupt levels does mask 0x00E0 affect? (Likely: maskable hardware interrupt levels)
- Why is this operation critical? (Probably: counter updates must be atomic to avoid races from ISRs)
- What is the return value used for?
- Why is this function called so frequently?
