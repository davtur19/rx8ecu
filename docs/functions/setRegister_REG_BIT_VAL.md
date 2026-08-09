# setRegister_REG_BIT_VAL @ 0x4BBC
**Purpose:** Set or clear bits in a hardware register based on a condition flag.
**Inputs:** r4: address of register to modify ; r5: bit mask (defines the bits to modify) ; r6: condition/mode flag (non-zero = clear bits, zero = set bits)
**Out:** Memory at r4: register value updated ; r0: modified register value
**Calls:** none
Read the word at r4 into r3 ; Zero-extend r6 into r6 (keep it 16-bit clean) ; Test r6 ; If r6 == 0, skip to write (bits will be set with NOR logic) ; If r6 != 0: ; Invert r5 (NOT r5 -> ~r5) ; AND r3
with ~r5 (clear bits at r5 positions) ; Write r3 back to r4 and return
**Draft C:**
```c
uint16_t setRegister_REG_BIT_VAL(volatile uint16_t* reg, uint16_t mask, int set_or_clear) {
  uint16_t val = *reg;
  if (set_or_clear) {
    val &= ~mask;  // clear bits
  }
  *reg = val;
  return val;
}
```
**Status:** med - only the "clear bits" path is clear. The "set bits" path (when r6==0) is not implemented in the shown code. It may be dead or may rely on caller state.
