# returnEngineRPM @ 0x5E57E

**Purpose:** Wrapper that loads engine RPM from a persistent pointer. Returns float32 of current engine revolutions per minute.
In: None (no arguments; reads global)  Out: Returns float32 in fr0 ; Reads from RAM global pointer stored at 0x5E612 (contains 0xB594)  Behavior: Load word from ROM address 0x5E612 → r3 (value: 0xB594, a RAM address) ; Return ; (unreachable) Load float32 from address in r3 → fr0
**Status:** low (function boundary unclear; RAM address overlap with returnEngineSpeed)
