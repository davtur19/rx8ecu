# store_knock_learn_buffer @ 0xC0F0
_source: AI (Haiku) draft, unverified_

**Purpose:** Atomically save/restore SR (status register) around knock learning state update; likely guards against interrupt-driven knock detection.

**Inputs:**
- r4: knock state or count value
- r5: another knock parameter

**Outputs / side effects:**
- RAM 0xFFFFA37E: u16 value (written from r4 after getSR)
- RAM 0xFFFFA37C: u16 value (written from r2)
- return r0: SR value returned from getSR

**Calls:**
- 0x00003920 (getSR): get current status register; return r0=SR
- 0x00003934 (setSR): set status register from r4

**Behavior:**
1. Push return address (pr) to stack
2. Save r4 to stack @(4,r15) — r4 is one parameter
3. Save r5 to stack @r15 — r5 is second parameter
4. Call getSR() → r0 = current SR
5. Set r4 = 16 (prepare for setSR mask or mode)
6. Load r4 with SR value: r4 = r0
7. Load address 0xFFFFA37E into r3, write r0 (SR value)
8. Load r2 with stack value @(4,r15) (original r4 param)
9. Write r2 to RAM 0xFFFFA37E
10. Load r1 with address 0xFFFFA37C
11. Load r2 with stack value @r15 (original r5 param)
12. Write r2 to RAM 0xFFFFA37C
13. Pop r15 by 8 (restore stack)
14. Call setSR(r4) via jmp to 0x00003934 with r4=SR
15. Restore return address and return

**Draft C:**
```c
uint16_t knock_state_a;    // @ 0xFFFFA37E
uint16_t knock_state_b;    // @ 0xFFFFA37C
uint32_t sr_value;         // temporary

void store_knock_learn_buffer(uint16_t knock_param1, uint16_t knock_param2) {
    // Atomic: read SR, save knock state, restore SR
    uint32_t sr_saved = getSR();
    
    // Disable interrupts (implied by mask)
    uint32_t sr_new = 16;  // or sr_saved | 0x10 for IPL increase?
    
    // Save knock parameters to protected RAM
    knock_state_a = sr_saved;     // Store SR first
    knock_state_a = knock_param1; // Overwrite with param1
    knock_state_b = knock_param2;
    
    // Restore SR (re-enable interrupts)
    setSR(sr_saved);
}
```

**Confidence:** low
- Function pattern (getSR → save state → setSR) is clear
- Purpose is interrupt-safe state storage
- Unknown: why both SR and param values go to same RAM location; actual param semantics
