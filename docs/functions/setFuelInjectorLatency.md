# setFuelInjectorLatency @ 0x86F8
**Purpose:** Set fuel injector pulse latency (dead-time offset) for one of three rotor phases, indexed by r4, writing the same value to two paired registers (primary and shadow).
**Inputs:** `r4` — injector selector: 0, 1, or 2 (three rotor phases) ; `r5` — latency value (likely fixed-point delay or raw timer counts) ; Global: read-only base address 0xFFFFA094 (injector control structure)
**Out:** Writes `r5` to two hardware register offsets within the structure at 0xFFFFA094: ; If r4=0: offsets +0 and +12 ; If r4=1: offsets +4 and +16 ; If r4=2: offsets +8 and +20 ; No return value (void)
**Calls:** None. Pure register write.
Load structure base address 0xFFFFA094 into r6 ; Test r4 against 0; if true, write r5 to [r6+0] and [r6+12], then exit ; Test r4 against 1; if true, write r5 to [r6+4] and [r6+16], then exit ; Test r4
against 2; if true, write r5 to [r6+8] and [r6+20], then exit ; If r4 is not 0, 1, or 2, no write occurs; exit
**Draft C:**
```c
void setFuelInjectorLatency(int injectorIndex, uint32_t latency) {
    volatile uint32_t *base = (volatile uint32_t *)0xFFFFA094;
    switch (injectorIndex) {
        case 0:
            base[0] = latency;
            base[3] = latency;  // offset +12
            break;
        case 1:
            base[1] = latency;  // offset +4
            base[4] = latency;  // offset +16
            break;
        case 2:
            base[2] = latency;  // offset +8
            base[5] = latency;  // offset +20
            break;
    }
}
```
**Status:** Medium ; Offsets and control flow clearly visible in disassembly ; Dual writes (primary/shadow pairs) inferred from pattern, not documented ; Actual register layout and latency units (time vs. counts) unknown without hardware datasheet ; r5 type assumed uint32_t; could be float or other encoding
