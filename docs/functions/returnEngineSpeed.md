# returnEngineSpeed @ 0x5E604

_source: AI (Haiku) draft, unverified_

**Purpose:** Wrapper that loads engine speed (vehicle speed or engine rev rate) from a persistent pointer. Returns float32.

**Inputs:** None (no arguments; reads global)

**Outputs / side effects:** 
- Returns float32 in fr0
- Reads from RAM global pointer stored at 0x5E612 (contains 0xB594)

**Calls:** None

**Behavior:**
1. Load word from ROM address 0x5E612 → r3 (value: 0xB594, a RAM address)
2. Return
3. (unreachable) Load float32 from address in r3 → fr0

**Draft C:**
```c
float32 returnEngineSpeed(void) {
    volatile float32 *eng_speed_ptr = (volatile float32 *) 0xB594;
    return *eng_speed_ptr;
}
```

**Notes:**
- Very thin wrapper; mirrors returnEngineLoad pattern.
- Code after rts is unreachable.
- UNKNOWN: confirm 0xB594 is engine speed (RPM or vehicle speed); name suggests engine speed (not RPM based on distinct returnEngineRPM function).

**Confidence:** low (function boundary unclear)
