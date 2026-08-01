# crankSensorInit @ 0x7C0C

_source: AI (Haiku) draft, unverified_

**Purpose:** Initialize crank sensor hardware registers and interrupt configuration.

**Inputs:** None

**Outputs / side effects:**
- Clears crank sensor interrupt/state flags
- Writes 0xFF to crank sensor control register (0xFFFF9FCA) — enables all edge types?
- Checks state flag at 0xFFFF9F96; if = 1, clears it and calls external function
- Return: None or jumps to 0x7668 if state flag detected

**Calls:**
- `0x7668` (unknown) - conditional handler

**Behavior:**
1. Set 0xFFFF9FC9 = 0 (clear interrupt flag)
2. Load 0xFF into r3
3. Write 0xFF to 0xFFFF9FCA (crank sensor control reg — likely edge detection mask)
4. Check flag at 0xFFFF9F96:
   - If = 1:
     - Clear 0xFFFF9F96 = 0
     - Jump to 0x7668 (external handler)
   - Else: Return

**Draft C:**
```c
void crankSensorInit(void) {
  *(u8*)0xFFFF9FC9 = 0;    // clear interrupt flag
  *(u8*)0xFFFF9FCA = 0xFF; // enable all edge detection
  
  u8 state = *(u8*)0xFFFF9F96;
  if (state == 1) {
    *(u8*)0xFFFF9F96 = 0;
    unknown_handler_0x7668();
  }
}
```

**Confidence:** high — the logic is simple and clear. The 0xFF value likely controls which crank edges trigger interrupts; exact edge encoding requires HW documentation.
