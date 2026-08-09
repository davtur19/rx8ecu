# crankSensorInit @ 0x7C0C
**Purpose:** Initialize the crank sensor hardware registers and the interrupt configuration.
**Inputs:** None
**Out:** Clears the crank sensor interrupt/state flags ; Writes 0xFF to the crank sensor control register (0xFFFF9FCA) — enables all edge types? ; Checks state flag at 0xFFFF9F96; if = 1, clears it and calls the external function ; Return: None or jumps to 0x7668 if the state flag is detected
**Calls:** `0x7668` (unknown) - conditional handler
Set 0xFFFF9FC9 = 0 (clear interrupt flag). Load 0xFF into r3. Write 0xFF to 0xFFFF9FCA (crank sensor control reg — likely the edge detection mask). Check the flag at 0xFFFF9F96. If = 1: clear
0xFFFF9F96 = 0. Jump to 0x7668 (external handler). Else: return.
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
**Status:** high — the logic is simple and clear. The 0xFF value likely selects the crank edges that trigger interrupts; the exact edge encoding requires HW documentation.
