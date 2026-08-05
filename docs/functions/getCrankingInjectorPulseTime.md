# getCrankingInjectorPulseTime @ 0x30700
**Purpose:** Look up and store cranking injector pulse time based on engine temperature during cranking.
**Inputs:** Cranking flag from RAM 0xA428 (uint8_t, non-zero if cranking) ; Temperature input from RAM 0xA9FC (f32, likely coolant temperature) ; Lookup table address @ 0x68FCC (ROM 2D table reference)
**Out:** Writes result from 2D lookup to RAM 0xBEA8 (f32) ; Writes secondary value from ROM 0x77014 to RAM 0xBEAC (f32)
**Calls:** 2DLookup @ 0x2068 (performs 2D table interpolation; input fr4=temperature, r4=table_addr, output fr0)
Check if cranking flag (0xA428) is set: ; If not set, skip lookup and return (output remains 0) ; Load temperature from RAM 0xA9FC into fr4 ; Load 2D table address 0x68FCC into r4 ; Call
2DLookup(fr4=temp, r4=table_addr) → returns result in fr0 ; Store result (fr0) to RAM 0xBEA8 ; Load secondary value from ROM 0x77014 into fr3 ; Store secondary value to RAM 0xBEAC
**Draft C:**
```c
void getCrankingInjectorPulseTime(void) {
    if (!*(uint8_t*)0xA428) return;  // Not cranking
    float temp = *(float*)0xA9FC;
    float* table_addr = (float*)0x68FCC;
    float result = 2DLookup(temp, table_addr);
    *(float*)0xBEA8 = result;
    float secondary = *(float*)0x77014;
    *(float*)0xBEAC = secondary;
}
```
**Status:** high — 2D lookup pattern is standard and verified helper; temperature input and storage clear.
**Uncertainties:** Exact nature of secondary value at 0x77014 (multiplier, offset, or alternative value) ; Lookup table structure (1D or 2D, what axes) ; Units of output (microseconds, milliseconds, PWM percentage)
