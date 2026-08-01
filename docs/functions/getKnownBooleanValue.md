# getKnownBooleanValue @ 0x11F54

_source: AI (Haiku) draft, unverified_

**Purpose:** Retrieve one of two persistent boolean/flag values from RAM, check if equal to 0x01, return true/false (via movt r4).

**Inputs:**
- No explicit inputs; selection of which flag to read is determined by entry point:
  - 0x11F54: read flag @ 0xFFFF8E9C
  - 0x11F62: read flag @ 0xFFFF8E9E

**Outputs / side effects:**
- r0: result (1 if flag==0x01, 0 otherwise)
- Uses movt (move-if-true) to set r4 based on comparison result
- Return value is in r4 (not r0), likely caller convention

**Calls:**
- None (direct memory load and comparison)

**Behavior:**
1. **First entry (0x11F54):**
   - Load byte @ 0xFFFF8E9C into r0
   - Extend to word (unsigned)
   - Compare r0 to 1
   - If equal: movt r4 (move true: r4 = 1)
   - Return r4 in r0
2. **Second entry (0x11F62):**
   - Load byte @ 0xFFFF8E9E into r0
   - Extend to word (unsigned)
   - Compare r0 to 1
   - If equal: movt r4 (move true: r4 = 1)
   - Return r4 in r0

**Draft C:**
```c
// Two distinct entry points for reading different flags
u8 getEngineRunningFlag(void) {
  u8 flag = *(u8 *)0xFFFF8E9C;
  return (flag == 1) ? 1 : 0;
}

u8 getImmobilizerActiveFlag(void) {
  u8 flag = *(u8 *)0xFFFF8E9E;
  return (flag == 1) ? 1 : 0;
}

// Or possibly compiled from single template with parameter:
u8 getKnownBooleanValue(u8 index) {
  static const u32 flags[] = {
    0xFFFF8E9C,  // index 0
    0xFFFF8E9E,  // index 1
  };
  
  u8 val = *(u8 *)flags[index];
  return (val == 1) ? 1 : 0;
}
```

**Confidence:** high
- Code structure is simple and deterministic
- Comparison value (0x01) and addresses are exact
- movt semantics clear (sets destination to 1 if last comparison was true, else 0)

**Uncertainties:**
- What do flags @ 0xFFFF8E9C and 0xFFFF8E9E represent semantically?
  - Likely: engine-running state, immobilizer state, crank enable, etc.
- Is this a dual-entry-point function, or are these two separate functions inlined at two addresses?
- Why only check for ==1 and not >=1 or other values?
- Are these flags set by other parts of the firmware or by external input (CAN)?
