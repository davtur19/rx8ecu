# ignitionCoilPulse @ 0xCA7E

_source: AI (Haiku) draft, unverified_

**Purpose:** Modifies ignition coil control register via bitwise AND/OR operations, then jumps to a helper at 0x7188. Likely gates a coil pulse by updating control bits.

**Inputs:** 
- r4: pointer to control register (hardware address)
- r5: pulse enable/disable mask or pattern

**Outputs / side effects:** 
- Writes modified value back to *r4
- Tail-calls to helper at 0x7188

**Calls:** 
- 0x7188 (FUN_00007188): unknown helper function

**Behavior:** 
1. Load byte from r4 (control register)
2. AND with 0xC7 (mask: 199 = 0b11000111, clears bits 3-5)
3. OR with r5 (apply new pulse pattern)
4. Write result back to r4
5. Restore stack (add #4, r15)
6. Restore return address from stack
7. Load r14 from stack
8. Tail-call to 0x7188 via jmp

**Draft C:** 
```c
void ignitionCoilPulse(volatile uint8_t *coil_reg, uint8_t pulse_mask) {
    uint8_t val = *coil_reg;
    val = (val & 0xC7) | pulse_mask;  // Clear bits 3-5, apply new pattern
    *coil_reg = val;
    FUN_00007188();  // Tail call
}
```

**Confidence:** med — register operations are clear, but purpose of 0x7188 tail-call is unknown. Naming as "pulse" is speculative.

**Uncertainties:** 
- What does 0x7188 do (timing strobe, interrupt, register sync)?
- What coil register is actually being modified?
- Why mask only bits 3-5?
