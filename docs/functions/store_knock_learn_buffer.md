# store_knock_learn_buffer @ 0xC0F0
**Purpose:** Atomically save and restore SR (status register) around the knock learning state update. This likely guards against interrupt-driven knock detection.
**Inputs:** r4: knock state or count value ; r5: another knock parameter
**Out:** RAM 0xFFFFA37E: u16 value (written from r4 after getSR) ; RAM 0xFFFFA37C: u16 value (written from r2) ; return r0: SR value returned from getSR
**Calls:** 0x00003920 (getSR): get the current status register; return r0=SR ; 0x00003934 (setSR): set the status register from r4
Push the return address (pr) to the stack ; Save r4 to the stack @(4,r15) — r4 is one parameter ; Save r5 to the stack @r15 — r5 is the second parameter ; Call getSR() → r0 = current SR ; Set r4 = 16 (prepare for setSR
mask or mode) ; Load r4 with the SR value: r4 = r0 ; Load address 0xFFFFA37E into r3, write r0 (SR value) ; Load r2 with the stack value @(4,r15) (original r4 param) ; Write r2 to RAM 0xFFFFA37E ; Load r1
with address 0xFFFFA37C ; Load r2 with the stack value @r15 (original r5 param) ; Write r2 to RAM 0xFFFFA37C ; Pop r15 by 8 (restore the stack) ; Call setSR(r4) with a jmp to 0x00003934 with r4=SR ; Restore
the return address and return
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
**Status:** low ; The function pattern (getSR → save state → setSR) is clear. The purpose is interrupt-safe state storage. Unknown: why both SR and param values go to the same RAM location; the actual param semantics
