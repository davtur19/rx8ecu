# ignitionCoilPulse @ 0xCA7E
**Purpose:** Modifies ignition coil control register with bitwise AND and OR operations, then jumps to a helper at 0x7188. Likely gates a coil pulse by updating control bits.
**Inputs:** r4: pointer to control register (hardware address) ; r5: pulse enable/disable mask or pattern
**Out:** Writes modified value back to *r4 ; Tail-calls to helper at 0x7188
**Calls:** 0x7188 (FUN_00007188): unknown helper function
Load byte from r4 (control register) ; AND with 0xC7 (mask: 199 = 0b11000111, clears bits 3-5) ; OR with r5 (apply new pulse pattern) ; Write result back to r4 ; Restore stack (add #4, r15) ; Restore
return address from stack ; Load r14 from stack ; Tail-call to 0x7188 with jmp
**Draft C:**
```c
void ignitionCoilPulse(volatile uint8_t *coil_reg, uint8_t pulse_mask) {
    uint8_t val = *coil_reg;
    val = (val & 0xC7) | pulse_mask;  // Clear bits 3-5, apply new pattern
    *coil_reg = val;
    FUN_00007188();  // Tail call
}
```
**Status:** med — register operations are clear, but purpose of 0x7188 tail-call is unknown. The name "pulse" is speculative.
**Uncertainties:** What does 0x7188 do (timing strobe, interrupt, register sync)? ; What coil register is actually being modified? ; Why mask only bits 3-5?
