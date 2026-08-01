# returnEngineRPM @ 0x5E57E

_source: AI (Haiku) draft, unverified_

**Purpose:** Wrapper that loads engine RPM from a persistent pointer. Returns float32 of current engine revolutions per minute.

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
float32 returnEngineRPM(void) {
    volatile float32 *rpm_ptr = (volatile float32 *) 0xB594;
    return *rpm_ptr;
}
```

**Notes:**
- Same RAM address (0xB594) as returnEngineSpeed, but named distinctly for RPM.
- UNKNOWN: whether returnEngineSpeed and returnEngineRPM read the same variable (both point to 0xB594) or if this is a coincidence.
- May be that one is a wrapper around the other, or both are data-access patterns for the same source.
- Code after rts is unreachable.

**Confidence:** low (function boundary unclear; RAM address overlap with returnEngineSpeed)
