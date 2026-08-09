# whileLoop @ 0x9EFE
**Purpose:** Emergency halt / infinite loop - disable interrupts and spin forever.
**Inputs:** none
**Out:** SR: interrupt priority level set to 15 (all interrupts masked) ; Execution: enters the infinite loop at 0x9F08
**Calls:** none
Read SR into r0 ; Load mask 0xFF0F into r3 (clear upper 4 bits) ; AND r0 with r3 (preserve non-priority bits) ; OR with 0xF0 (set priority bits to 15 = disable all interrupts) ; Load the updated SR back
with `ldc r0,sr` ; Branch to self (bra 0x9f08, infinite loop)
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
**Status:** high - a clear pattern: disable interrupts, then loop forever; used as an emergency shutdown or watchdog/panic handler.
