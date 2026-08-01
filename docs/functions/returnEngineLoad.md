# returnEngineLoad @ 0x5E5FE

_source: AI (Haiku) draft, unverified_

**Purpose:** Wrapper that loads engine load from a persistent pointer. Returns float32 of current engine load (0.0–1.0 range).

**Inputs:** None (no arguments; reads global)

**Outputs / side effects:** 
- Returns float32 in fr0
- Reads from RAM global pointer stored at 0x5E61E (contains 0xC0D8)

**Calls:** None

**Behavior:**
1. Load word from ROM address 0x5E61E → r3 (value: 0xC0D8, a RAM address)
2. Return
3. (unreachable) Load float32 from address in r3 → fr0

**Draft C:**
```c
float32 returnEngineLoad(void) {
    volatile float32 *eng_load_ptr = (volatile float32 *) 0xC0D8;
    return *eng_load_ptr;
}
```

**Notes:**
- Very thin wrapper function, likely for abstraction/indirection.
- Code after rts is unreachable; suggests disassembler captured beyond boundary or deliberate layout for code organization.
- UNKNOWN: confirm 0xC0D8 is the actual engine load variable; verify units/scaling.

**Confidence:** low (function boundary unclear; unreachable code after rts)
