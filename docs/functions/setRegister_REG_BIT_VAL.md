# setRegister_REG_BIT_VAL @ 0x4BBC

_source: AI (Haiku) draft, unverified_

**Purpose:** Set or clear bits in a hardware register based on a condition flag.

**Inputs:**
- r4: address of register to modify
- r5: bit mask (defines which bits to modify)
- r6: condition/mode flag (non-zero = clear bits, zero = set bits)

**Outputs / side effects:**
- Memory at r4: register value updated
- r0: modified register value

**Calls:** none

**Behavior:**
1. Read word at r4 into r3
2. Zero-extend r6 into r6 (ensure it's 16-bit clean)
3. Test r6
4. If r6 == 0, skip to write (bits will be set via NOR logic)
5. If r6 != 0:
   - Invert r5 (NOT r5 -> ~r5)
   - AND r3 with ~r5 (clear bits at r5 positions)
6. Write r3 back to r4 and return

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

**Confidence:** med - only the "clear bits" path is clear; "set bits" path (when r6==0) is not implemented in shown code, may be dead or may rely on caller state.
