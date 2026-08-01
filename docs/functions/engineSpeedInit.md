# engineSpeedInit @ 0x7F90
_source: AI (Haiku) draft, unverified_

**Purpose:** Initialize engine speed and related state variables to safe/default values at startup.

**Inputs:** None

**Outputs / side effects:**
- Writes initialization values to multiple global RAM locations:
  - 0xFFFF9F84 = 0x7FFFFFFF (max int32)
  - 0xFFFF9F88 = 0x7FFFFFFF (max int32)
  - 0xFFFF9F80 = 0.0 (float)
  - 0xFFFF9FE8 = 0 (byte)
  - 0xFFFF9F90 = 0.0 (float)
  - 0xFFFF9F94 = 0 (byte)

**Calls:** None

**Behavior:**
1. Load constant 0x7FFFFFFF (max positive int32) → r4
2. Store r4 at 0xFFFF9F84
3. Store r4 at 0xFFFF9F88
4. Set r4 = 0
5. Load address 0xFFFF9FE8 → r3
6. Store float 0.0 at 0xFFFF9F80 (fr4 cleared with fldi0)
7. Store byte 0 at 0xFFFF9FE8
8. Store float 0.0 at 0xFFFF9F90
9. Store byte 0 at 0xFFFF9F94

**Draft C:**
```c
void engineSpeedInit(void) {
  // Initialize engine speed state
  *(int32_t *)0xFFFF9F84 = 0x7FFFFFFF;   // Max speed limit (or sentinel)
  *(int32_t *)0xFFFF9F88 = 0x7FFFFFFF;   // Max speed limit (or sentinel)
  *(float *)0xFFFF9F80 = 0.0f;           // Current engine speed
  *(uint8_t *)0xFFFF9FE8 = 0;            // Mode or flag
  
  *(float *)0xFFFF9F90 = 0.0f;           // Derivative (accel) or related
  *(uint8_t *)0xFFFF9F94 = 0;            // Enable/disable or state flag
}
```

**Confidence:** high
- Function is simple initialization: load constants and write to 6 global locations
- No branching, no loops, no function calls
- Value 0x7FFFFFFF (max int32) suggests speed limit sentinel or initialization guard
- Zero initialization for floats and bytes suggests startup reset state
- Likely called once during ECU boot or key-on event
