# getSpeedLimitCal @ 0x483C0
**Purpose:** Read vehicle speed limiter calibration value and set ECU diagnostic flags based on speed/mode. Determines which speed limit tier is active.
**Inputs:** Vehicle/engine mode value from subroutine call 0x48488 (returns in r0) ; Diagnostic register at 0xCBD4, 0xCBD5 (read/write)
**Out:** Writes calibration constant to 0xCBD4 (primary output) ; Writes limit tier (0-10, 0x01, 0x02, ..., 0xF0, 0xF1) to 0xCBD5 ; Clears diagnostic flags if mode not recognized
**Calls:** Subroutine 0x48488 - returns vehicle mode/speed class ; Subroutine 0x484E4 - returns throttle/speed condition (0, 1, 2, ...) ; Subroutine 0x48542 - returns limiter status (0, 1, 2, ...)
Call subroutine to get mode value (0, 1, 2, 5, 6, 0xF0, 0xF1, 10) ; Switch on mode: ; 10: set 0x0080 ; 1: set 0x0040 ; 2: set 0x0020 ; 6: set 0x0010 ; 5: set 0x0008 ; 0xF1: set 0x0004 ; 0xF0: set
0x0002 ; else: set 0x0000 (no limit) ; Write constant to 0xCBD4 ; Call second subroutine to get throttle condition result ; Similar switch sets 0xCBD5 value ; Call third subroutine to get limiter
status ; Final switch sets or clears based on status
**Draft C:**
```c
void getSpeedLimitCal() {
    u8 mode = callSubroutine_0x48488();
    u8 throttleCond, limiterStatus;
    u8 limitVal = 0;
    switch (mode) {
        case 10: limitVal = 0x0080; break;
        case 1:  limitVal = 0x0040; break;
        case 2:  limitVal = 0x0020; break;
        case 6:  limitVal = 0x0010; break;
        case 5:  limitVal = 0x0008; break;
        case 0xF1: limitVal = 0x0004; break;
        case 0xF0: limitVal = 0x0002; break;
        default: limitVal = 0x0000; break;
    }
    *(u16*)0xCBD4 = limitVal;
    throttleCond = callSubroutine_0x484E4(limitVal);
    // similar switch on throttleCond result
    limiterStatus = callSubroutine_0x48542(...);
    // apply limiter status logic
}
```
**Status:** med - High-level flow clear; subroutine purposes and exact status logic need verification.
**Uncertainties:** Exact vehicle mode semantics (gear, speed class, transmission state?) ; What throttleCond and limiterStatus values represent ; Whether switches use == or <= comparisons ; Exact condition bit patterns and their meaning
