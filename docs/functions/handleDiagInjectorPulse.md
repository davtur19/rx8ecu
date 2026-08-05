# handleDiagInjectorPulse @ 0x30904
**Purpose:** Diagnostic fuel injector pulse control; inject fuel on demand for OBD/diagnostic testing with hardware interlock protection.
**Inputs:** Diagnostic injector demand flag from RAM 0xBEBA (uint8_t) ; Engine temperature from RAM 0xA9FC (f32) ; Diagnostic mode code from RAM 0xA42C (uint8_t) ; Engine speed threshold from RAM 0xCCFA (uint8_t) ; Injector counter/state from RAM 0xBECA (uint8_t) and 0xBEC5 (uint8_t) ; Limit check value from ROM 0x77002 (uint8_t, max diagnostic injection count) ; Saturation value from ROM 0x77003 (uint8_t) ; Multiple state flags and values from RAM 0xBEC9, 0xBEC2, 0xBEBB, 0xBEA4, etc.
**Out:** Writes injector pulse width to RAM 0xBEBA (uint8_t) ; Updates internal counters at 0xBECA, 0xBEC5, 0xBEC2, 0xBEBB ; Updates diagnostic injection state at 0xBEC9
**Calls:** addSaturate8Bit @ 0x2478 (saturating add; caps at 255) ; 2DLookup_FP_16bit @ 0x20C4 (2D lookup with f32 input, 16-bit output) ; add16bitSaturate_ADD1_ADD2 @ 0x2460 (16-bit saturating add) ; 2DLookup_FP_8bit @ 0x20AC (2D lookup with f32 input, 8-bit output) ; saturateLow_SIGNAL_LOWERBOUND @ 0x23E4 (floor clamping)
Save multiple registers (r8-r14, fr14-fr15) ; Load diagnostic demand flag from 0xBEBA into r12 ; Load temperature from 0xA9FC into fr15 ; Load diagnostic mode code from 0xA42C into r13 ; Load engine
speed threshold from 0xCCFA ; Load injector counters from 0xBEC5, 0xBECA ; Check limit: if counter ≥ max_from_ROM(0x77002): ; Call addSaturate8Bit(r12, 1) → increment demand counter ; Zero the
injector counter ; Zero another state ; Load threshold from ROM 0x77040 ; If temperature < threshold: ; Load saturation value from ROM 0x77003 ; If demand counter < saturation: CONTINUE ; Else ZERO
output and RETURN ; Check additional conditions (registers 0xA7AC, 0xB594): ; If conditions not met, ZERO output ; Check diagnostic flag 0xBEC9: ; If flag set AND diagnostic_mode == 1: ; ZERO counter,
increment injection flag ; If injection flag active, call addSaturate8Bit(counter, 1) ; Check internal state 0xBEC9: ; If condition met: process 2D lookup ; Load table address 0x68AC4 ; Call
2DLookup_FP_16bit(fr15=temp, table) ; Shift result right by 4 bits (divide by 16) ; Call add16bitSaturate to combine values ; Load correction from ROM 0x77034 ; Write to RAM 0xBEB8 ; Check another
counter: ; If exceeds limit, call 2DLookup_FP_8bit ; Else load default from ROM 0x77000 ; Write result to RAM 0xBEB8 ; If another condition, process another lookup or load default ; If injection flag
== 1: ; Load constant -0.0469 (negative offset) ; Add to current value ; Call saturateLow to floor clamp ; Restore all saved registers and return
**Draft C:**
```c
void handleDiagInjectorPulse(void) {
    uint8_t diag_demand = *(uint8_t*)0xBEBA;
    float temperature = *(float*)0xA9FC;
    uint8_t diag_mode = *(uint8_t*)0xA42C;
    uint8_t speed_threshold = *(uint8_t*)0xCCFA;
    uint8_t counter1 = *(uint8_t*)0xBEC5;
    uint8_t counter2 = *(uint8_t*)0xBECA;
    uint8_t max_count = *(uint8_t*)0x77002;
    uint8_t saturation = *(uint8_t*)0x77003;
    if (counter2 >= max_count) {
        diag_demand = addSaturate8Bit(diag_demand, 1);
        *(uint8_t*)0xBEC5 = 0;
        *(uint8_t*)0xBECA = 0;
    }
    float temp_threshold = *(float*)0x77040;
    if (temperature < temp_threshold) {
        if (diag_demand < saturation) {
            // Continue processing
        } else {
            *(uint8_t*)0xBEBA = 0;
            return;
        }
    }
    // ... additional conditions and lookups ...
    uint8_t injection_active = *(uint8_t*)0xBEC9;
    if (injection_active == 1) {
        float adjustment = -0.0469f;
        float value = *(float*)0xBEA4;
        value += adjustment;
        value = saturateLow(value);
        *(float*)0xBEA4 = value;
    }
    // Restore registers and return
}
```
**Status:** low — very complex function with many conditional paths; multiple 2D lookups and state flags make full understanding difficult; primary logic appears to be injection pulse modulation under diagnostic control with temperature and counter limits.
**Uncertainties:** Exact purpose of multiple counters and flags (demand counter vs. injection counter vs. others) ; What each 2D lookup table represents (likely RPM-based, temperature-based adjustments) ; Exact meaning of "deflood" vs. "injection" vs. "demand" ; Shift amount (4 bits = divide by 16) physical significance ; Negative offset -0.0469 purpose (likely temperature correction or derating) ; When which output path is taken (multiple lookup branches)
