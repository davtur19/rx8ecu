# reset420CANTimer @ 0x29584

_source: AI (Haiku) draft, unverified_

**Purpose:** Reset the 420 Hz CAN timer counter to zero.

**Inputs:** None (uses global state)

**Outputs / side effects:** 
- Writes 0 to RAM location 0xFFFFBAEC (420 Hz CAN timer counter)

**Calls:** None

**Behavior:**
1. Load address 0xFFFFBAEC into r2
2. Clear r3 to 0
3. Write r3 (0) to memory location in r2
4. Return

**Draft C:**
```c
void reset420CANTimer(void) {
    *(uint16_t*)0xFFFFBAEC = 0;
}
```

**Confidence:** high — straightforward register write; function name confirms purpose.

**Uncertainties:** None
