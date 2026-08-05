# calcInjectorCrankingTime @ 0x306B4
**Purpose:** Calculate cranking injector pulse time based on multiple scaling factors and stored calibration values.
**Inputs:** Cranking flag from RAM 0xA428 (uint8_t, non-zero if cranking) ; Base temperature from RAM 0xBE5C (uint8_t or int8_t, likely coolant temp) ; Multiplier 1 from RAM 0xBE88 (f32) ; Multiplier 2 from RAM 0xBE9C (f32) ; Multiplier 3 from RAM 0xBEA0 (f32) ; Multiplier 4 from RAM 0xBEA4 (f32) ; Calibration value from ROM 0x7700C (f32)
**Out:** Writes result to RAM 0xBE78 (f32, cranking injector pulse time) ; Writes intermediate result to RAM 0xBEAC (f32)
**Calls:** None (math-only, loads and multiplies)
Check if cranking flag (0xA428) is set: ; If not set or temperature is negative, skip to rts (no calculation) ; Load calibration base value from ROM 0x7700C into fr2 ; Multiply by multiplier 1
(0xBE88) → result in fr2 ; Multiply by multiplier 2 (0xBE9C) → result in fr2 ; Load multiplier 3 (0xBEA0) into fr0 ; Multiply by multiplier 3 → result in fr2 ; Load multiplier 4 (0xBEA4) into fr3 ;
Store intermediate (fr2) into temp register fr4 ; Multiply intermediate (fr4) by multiplier 4 (fr3) → result in fr2 ; Write result to RAM 0xBE78 ; Load multiplier from RAM 0xBEAC ; Multiply
intermediate (fr4) by this multiplier → result in fr3 ; Write result to RAM 0xBEAC
**Draft C:**
```c
void calcInjectorCrankingTime(void) {
    if (!*(uint8_t*)0xA428) return;  // Not cranking
    int8_t temp = *(int8_t*)0xBE5C;
    if (temp <= 0) return;  // Temperature negative
    float base = *(float*)0x7700C;
    float mult1 = *(float*)0xBE88;
    float mult2 = *(float*)0xBE9C;
    float mult3 = *(float*)0xBEA0;
    float mult4 = *(float*)0xBEA4;
    float mult5 = *(float*)0xBEAC;
    float result = base * mult1 * mult2 * mult3 * mult4;
    *(float*)0xBE78 = result;
    float result2 = base * mult1 * mult2 * mult3 * mult5;
    *(float*)0xBEAC = result2;
}
```
**Status:** med — sequential multiplications are clear; purpose of multiple multipliers (likely RPM-based, temperature-based, load-based factors) inferred from name pattern.
**Uncertainties:** Physical meaning of each multiplier (likely RPM, temp, load, pressure, etc.) ; Temperature comparison threshold (why negative check) ; Units of output (microseconds, milliseconds, or normalized)
