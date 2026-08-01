# getFuelCutRequestStatus @ 0xFF08
_source: AI (Haiku) draft, unverified_

**Purpose:** Return current fuel cut request status as a bit field (one bit per rotor).

**Inputs:** None

**Outputs / side effects:**
- r0: fuel cut status word (16-bit, typically bit 0-2 = rotor 0-2 fuel cut request flags)

**Calls:** None

**Behavior:**
1. Load address 0xA430 → r3
2. Load 16-bit word from 0xA430 → r0
3. Return r0 (r0 becomes return value)

**Draft C:**
```c
uint16_t getFuelCutRequestStatus(void) {
  return *(uint16_t *)0xA430;
}
```

**Confidence:** high
- Trivial 2-line function: load global word and return
- No conditional logic, no branches
- Memory address 0xA430 is the sole state source
- Return value directly used by callers for per-rotor fuel cut testing
