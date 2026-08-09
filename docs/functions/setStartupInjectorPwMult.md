# setStartupInjectorPwMult @ 0x3089A
**Purpose:** Set the startup injector pulse-width multiplier based on the cold-start condition and the deflood state.
**Inputs:** Cranking flag from RAM 0xA428 (uint8_t, non-zero if cranking) ; Deflood enabled flag from RAM 0xC590 (uint8_t, non-zero if deflood is active) ; Startup multiplier value from ROM 0x7702C (f32, likely a 1.5–2.5× multiplier)
**Out:** Writes the multiplier to RAM 0xBEA0 (f32) ; If cranking but not deflood: loads the multiplier from ROM 0x7702C ; If not deflood: writes 1.0 (normal multiplier)
**Calls:** None (load and store only)
Check if not cranking (0xA428 == 0): ; If not cranking, skip to step 5 ; Check if the deflood flag (0xC590) == 0 (deflood NOT active): ; If deflood is not active, load the startup multiplier from ROM 0x7702C and
go to step 4 ; Else go to step 5 ; Load the ROM value 0x7702C into fr3 (startup multiplier) ; Write fr3 to RAM 0xBEA0 and return ; Write 1.0 (normal, no startup enrichment) to RAM 0xBEA0 ; Return
**Draft C:**
```c
void setStartupInjectorPwMult(void) {
    uint8_t cranking = *(uint8_t*)0xA428;
    uint8_t deflood_flag = *(uint8_t*)0xC590;
    if (cranking && deflood_flag == 0) {
        float startup_mult = *(float*)0x7702C;
        *(float*)0xBEA0 = startup_mult;
    } else {
        *(float*)0xBEA0 = 1.0f;  // Normal multiplier
    }
}
```
**Status:** high — the logic is straightforward; the function name and assembly pattern confirm the startup multiplier behavior.
**Uncertainties:** The exact startup multiplier value (likely stored in ROM, approximately 1.5–2.5) ; Whether deflood entirely suppresses startup enrichment or modulates it ; Whether "deflood" means cutting fuel (1.0) or reducing enrichment
