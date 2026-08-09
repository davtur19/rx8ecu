# throttleDownDeFloodCheck @ 0x3083C
**Purpose:** Prevent fuel flooding on throttle-down during engine crank by cutting the injector pulse (deflood).
**Inputs:** Cranking flag from RAM 0xA428 (uint8_t) ; Throttle position from RAM 0xBE88 (f32) ; Throttle threshold from ROM 0x77044 (f32) ; Intake air temperature from RAM 0xAA2C (f32) ; Startup configuration from ROM 0x77028 (f32) ; Additional check register from RAM 0xC5EA (uint8_t) ; Deflood flag from RAM 0xB46F (uint8_t) ; Speed/RPM value from RAM 0xADA8 (f32) ; Lookup table address @ 0x68F98 (ROM 2D table)
**Out:** Writes the deflood injector pulse time to RAM 0xBE88 (f32) ; Clears the output if the conditions are not met
**Calls:** 2DLookup @ 0x2068 (2D table lookup on speed/RPM and other parameters)
Check if not cranking (0xA428 == 0): ; If not cranking, set the deflood result = 0.0 and return ; Load the throttle position from RAM 0xBE88 ; Load the throttle threshold from ROM 0x77044 ; Compare: if throttle ≤
threshold, set the result = 0.0 and skip to step 11 ; Load the intake temp from ROM 0x77028 ; Load the startup reference value from RAM 0xA9FC ; Compare: if startup_ref ≤ intake_temp, check the deflood conditions ;
Check the register at 0xC5EA and the deflood flag at 0xB46F: ; If either is non-zero, set the result = 1.0 (activate deflood, cut fuel) ; Else: ; Load speed/RPM from RAM 0xADA8 ; Call 2DLookup(speed/RPM, table @
0x68F98) → result in fr0 ; Store the result to RAM 0xBE88
**Draft C:**
```c
void throttleDownDeFloodCheck(void) {
    if (!*(uint8_t*)0xA428) {
        *(float*)0xBE88 = 0.0f;  // No cranking, no deflood
        return;
    }
    float throttle = *(float*)0xBE88;
    float throttle_thresh = *(float*)0x77044;
    if (throttle <= throttle_thresh) {
        *(float*)0xBE88 = 0.0f;  // Throttle closed, no deflood
        return;
    }
    float intake_temp = *(float*)0xAA2C;
    float startup_ref = *(float*)0x77028;
    if (intake_temp > startup_ref) {
        *(float*)0xBE88 = 0.0f;  // Engine warm, no deflood
        return;
    }
    uint8_t check_reg = *(uint8_t*)0xC5EA;
    uint8_t deflood_flag = *(uint8_t*)0xB46F;
    if (check_reg == 0 && deflood_flag == 0) {
        float speed = *(float*)0xADA8;
        float* table = (float*)0x68F98;
        float result = 2DLookup(speed, table);
        *(float*)0xBE88 = result;
    } else {
        *(float*)0xBE88 = 1.0f;  // Activate deflood (cut fuel)
    }
}
```
**Status:** med — flow and conditions are clear. The deflood thresholds and table purpose are inferred.
**Uncertainties:** "deflood" value semantics (1.0 = cut all fuel vs multiplier)? What is the purpose of check register 0xC5EA? OR vs AND trigger logic? Table structure?
