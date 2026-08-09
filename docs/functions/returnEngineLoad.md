# returnEngineLoad @ 0x5E5FE

**Purpose:** Wrapper that loads engine load from a persistent pointer. It returns float32 of the current engine load (0.0–1.0 range).
In: None (no arguments; reads global)  Out: Returns float32 in fr0 ; Reads from RAM global pointer stored at 0x5E61E (contains 0xC0D8)  Behavior: Load word from ROM address 0x5E61E → r3 (value: 0xC0D8, a RAM address) ; Return ; (unreachable) Load float32 from address in r3 → fr0
**Status:** low (function boundary unclear; unreachable code after rts)
