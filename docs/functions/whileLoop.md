# whileLoop @ 0x9EFE

_source: AI (Haiku) draft, unverified_

**Purpose:** Emergency halt / infinite loop - disable interrupts and spin forever.

**Inputs:** none

**Outputs / side effects:**
- SR: interrupt priority level set to 15 (all interrupts masked)
- Execution: enters infinite loop at 0x9F08

**Calls:** none

**Behavior:**
1. Read SR into r0
2. Load mask 0xFF0F into r3 (clear upper 4 bits)
3. AND r0 with r3 (preserve non-priority bits)
4. OR with 0xF0 (set priority bits to 15 = disable all interrupts)
5. Load updated SR back via `ldc r0,sr`
6. Branch to self (bra 0x9f08, infinite loop)

**Draft C:**
```c
void whileLoop(void) {
  // Disable all interrupts
  int sr = getSR_raw();
  sr = (sr & 0xFF0F) | 0xF0;  // Set IPL to 15
  ldc(sr);
  
  // Infinite loop - CPU hangs here
  while (1) {
    __asm__ volatile("nop");
  }
}
```

**Confidence:** high - clear pattern of interrupt disabling followed by infinite loop; used as emergency shutdown or watchdog/panic handler.
