# getFaultStatus @ 0x652F0
**Purpose:** Query fault status for a specific DTC index. Reads from a fault status table in ROM (at 0x0007CCB8) and checks if the fault is active (bit set in fault flags at FFFF:D740).
**Inputs:** r4: DTC index (word, zero-extended) ; Global: Fault flags buffer at 0xFFFFD740
**Out:** r0: 0 if fault is not set; 1 if fault is set/active ; Reads from ROM fault table and RAM fault flags
**Calls:** 0x65348 (sub_65348): Helper function; takes r4 (zero-extended) as argument. Returns fault state candidate in r0. Used only in non-active path.
Load fault flags at 0xFFFFD740 into r5 ; Convert DTC index (r4) to word and use as offset to index ROM table at 0x0007CCB8 ; Load indexed fault status word from ROM into r2 ; AND with fault flags (r5)
to get current state ; If result is 0 (fault not set), return r14=0; otherwise set r14=1 ; In the alternative path (if r14 was 0), call sub_65348 with index and re-check with 0xFFFF0000 mask ; If the
masked result is non-zero after the subcall, set r14=1 (fault active) ; Return r14 (0 or 1) in r0
**Draft C:**
```c
uint8_t getFaultStatus(uint16_t dtcIndex) {
    uint16_t *faultFlagsBuf = (uint16_t *)0xFFFFD740;
    uint16_t *faultTable = (uint16_t *)0x0007CCB8;
    uint16_t flags = *faultFlagsBuf;
    uint16_t faultEntry = faultTable[dtcIndex];
    uint16_t state = faultEntry & flags;
    if (state == 0) {
        // Try alternative fault source
        uint16_t alt = sub_65348(dtcIndex);
        state = alt & flags;
        if ((state & 0xFFFF0000) == 0) {
            return 0;
        }
        return 1;
    }
    return 1;
}
```
**Status:** med ; Purpose (query fault status) is clear from table indexing and bit masking ; Uncertainty on sub_65348 purpose and the exact fault confirmation logic (why two paths?) ; The 0xFFFF0000 mask operation suggests high byte filtering but context unclear
