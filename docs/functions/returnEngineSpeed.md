# returnEngineSpeed @ 0x5E604

**Purpose:** Wrapper that loads engine speed (vehicle speed or engine rev rate) from a persistent pointer. It returns float32.
In: None (no arguments; reads global)  Out: Returns float32 in fr0 ; Reads from RAM global pointer stored at 0x5E612 (contains 0xB594)  Behavior: Load word from ROM address 0x5E612 → r3 (value: 0xB594, a RAM address) ; Return ; (unreachable) Load float32 from address in r3 → fr0
**Status:** low (function boundary unclear)
