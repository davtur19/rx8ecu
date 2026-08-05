# getCruiseControlAllowedBool @ 0x2DBC4
**Purpose:** Determine if cruise control is allowed to operate based on multiple conditions (engine state, diagnostic mode, speed threshold).
**Inputs:** Inhibit flag 1 from RAM 0xBD1C (uint8_t) ; Inhibit flag 2 from RAM 0xBD18 (uint8_t) ; Inhibit flag 3 from RAM 0xBD19 (uint8_t) ; Inhibit flag 4 from RAM 0xBD1A (uint8_t) ; Diagnostic mode flag from RAM 0xBD2E (uint8_t) ; Additional diagnostic check from ROM 0x762A5 (uint8_t) ; Speed threshold value from ROM 0x76298 (f32) ; Cruise control speed setpoint from RAM 0xBFBC (f32)
**Out:** Writes result (0 or 1) to RAM 0xBD1C (uint8_t)
**Calls:** None (comparison logic only)
If any of inhibit flags (0xBD18, 0xBD19, 0xBD1A) == 1, set result = 0 and return ; If diagnostic mode flag (0xBD2E) == 1, skip speed check ; If diagnostic check at ROM 0x762A5 == 1, set result = 0 and
return ; Load speed threshold from ROM 0x76298, cruise setpoint from RAM 0xBFBC ; If setpoint > threshold: ; If diagnostic check == 1, set result = 0 ; Else set result = 1 ; Else set result = 0 ;
Store result to RAM 0xBD1C
**Draft C:**
```c
uint8_t getCruiseControlAllowed(void) {
    if (*(uint8_t*)0xBD18 == 1 || 
        *(uint8_t*)0xBD19 == 1 || 
        *(uint8_t*)0xBD1A == 1) {
        return 0;  // Inhibited
    }
    if (*(uint8_t*)0xBD2E == 0 && *(uint8_t*)0x762A5 == 1) {
        return 0;  // Diagnostic inhibit
    }
    float speed_threshold = *(float*)0x76298;
    float cruise_setpoint = *(float*)0xBFBC;
    if (cruise_setpoint > speed_threshold && *(uint8_t*)0x762A5 != 1) {
        return 1;
    }
    return 0;
}
```
**Status:** med — inhibit logic chain is clear; speed comparison logic inferred from fcmp instruction; exact semantic of each flag unclear.
**Uncertainties:** Exact meaning of each inhibit flag (clutch, throttle, engine condition, etc.) ; Why diagnostic flag bypasses speed check ; Whether ROM 0x762A5 is a flag or condition
