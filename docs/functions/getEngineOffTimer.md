# getEngineOffTimer @ 0x31DCA
**Purpose:** Increment and return engine-off timer counter. Tracks elapsed time since engine shut down for emissions or diagnostic purposes.
**Inputs:** Condition flag from 0xA41C (engine state?) ; Current counter value from 0xFFFFBF8A (RAM storage)
**Out:** Updates counter at 0xFFFFBF8A (increment or reset) ; Returns updated value in r0
**Calls:** add16bitSaturate_ADD1_ADD2 (0x2460) - adds two 16-bit values with saturation
**Behavior:** Check if flag at 0xA41C equals 1 ; If true: read current timer, call add16bitSaturate(current, 1), write result back ; If false: write 0 (reset timer) ; Return result
**Draft C:**
```c
u16 getEngineOffTimer() {
    if (*(u8*)0xA41C == 1) {
        u16 current = *(u16*)0xFFFFBF8A;
        u16 result = add16bitSaturate_ADD1_ADD2(current, 1);
        *(u16*)0xFFFFBF8A = result;
        return result;
    } else {
        *(u16*)0xFFFFBF8A = 0;
        return 0;
    }
}
```
**Status:** high - Function is straightforward; flow and memory layout clear.
**Uncertainties:** Exact semantic of 0xA41C flag (engine running state?) ; Whether counter represents milliseconds, seconds, or cycles
