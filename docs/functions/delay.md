# delay @ 0x59808
_source: AI (Haiku) draft, unverified_

**Purpose:** Set up timeout/delay with busy-wait loop based on mode parameter.

**Inputs:**
- r4: timeout mode (0=disable, 1=mode1, 2=mode2, 3=mode3)

**Outputs / side effects:**
- RAM flag at 0xFFFFD0F4 set to r4 value or 0 depending on mode

**Calls:**
- whileLoop @ 0x9EFE (busy-wait)

**Behavior:**
1. Read/write timeout state from 0xFFFFD0F4
2. Based on r4 parameter:
   - 0: Clear flag (write 0 to 0xFFFFD0F4)
   - 1: Set flag to 1, enter busy-wait via whileLoop
   - 2: Check flag at 0xFFFFD0F4; if == 1, call whileLoop
   - 3: Clear flag (write 0 to 0xFFFFD0F4)
3. Return

**Draft C:**
```c
void delay(uint8_t mode) {
  volatile uint8_t* timeout_flag = (volatile uint8_t*)0xFFFFD0F4;
  
  switch (mode) {
    case 0:
      *timeout_flag = 0;
      break;
    case 1:
      *timeout_flag = 1;
      whileLoop();  // Busy-wait until timeout expires
      break;
    case 2:
      if (*timeout_flag == 1) {
        whileLoop();
      }
      break;
    case 3:
      *timeout_flag = 0;
      break;
  }
}
```

**Confidence:** med – delay/timeout pattern clear, whileLoop identity confirmed; exact mode semantics inferred
