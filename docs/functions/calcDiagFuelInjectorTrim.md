# calcDiagFuelInjectorTrim @ 0x4AE38
**Purpose:** Calculate and store the diagnostic fuel injector trim correction. It reads per-rotor trim values and compares them against the engine-on condition and multiple thresholds. It determines if the trim is valid.
**Inputs:** Engine-on flag from 0xA41C (u8, 1 = engine running) ; Trim valid flag from 0xFFFFCD10 (u8) ; Injector ID / rotor select from 0xFFFFCD10 (u8, values 1-5 likely) ; Trim calibration thresholds from ROM (0x7B7E8, 0x7B7EC, 0x7B7F0, 0x7B7F4, 0x7B7F8) ; Global trim enable flag from 0x7B7A6
**Out:** Writes trim result (0 or 1) to 0xFFFFCD1B (diagnostic trim output) ; Writes to register 0xCCFA (with function 0x5BA00)
**Calls:** Function 0x5BA00 - writes trim result to output register; takes trim flag in r4
Read the engine-on flag from 0xA41C. If the engine is NOT running: clear the output, return. Read the injector ID from 0xFFFFCD10 (values 1-5). Read the trim value from 0xA9FC (float, calibration). Switch on the injector
ID: ID 1: compare against threshold 0x7B7E8. ID 2: compare against threshold 0x7B7EC. ID 3: compare against threshold 0x7B7F0. ID 4: compare against threshold 0x7B7F4. ID 5: compare against
threshold 0x7B7F8. If trim > threshold: set the enable flag. Check the global trim enable at 0x7B7A6. If not enabled: clear the flag. Write the final state (0 or 1) to 0xFFFFCD1B.
**Draft C:**
```c
void calcDiagFuelInjectorTrim() {
    if (*(u8*)0xA41C != 1) {  // engine not running
        *(u8*)0xFFFFCD1B = 0;
        callFunction_0x5BA00(0);
        return;
    }
    u8 injectorID = *(u8*)0xFFFFCD10;
    float trimValue = *(float*)0xA9FC;
    float threshold;
    switch (injectorID) {
        case 1: threshold = *(float*)0x0007B7E8; break;
        case 2: threshold = *(float*)0x0007B7EC; break;
        case 3: threshold = *(float*)0x0007B7F0; break;
        case 4: threshold = *(float*)0x0007B7F4; break;
        case 5: threshold = *(float*)0x0007B7F8; break;
        default: threshold = 0.0f; break;
    }
    u8 trimValid = (trimValue > threshold) ? 1 : 0;
    if (*(u8*)0x0007B7A6 != 1) {
        trimValid = 0;  // global disable
    }
    *(u8*)0xFFFFCD1B = trimValid;
    callFunction_0x5BA00(trimValid);
}
```
**Status:** med — the core structure is clear; the threshold comparison and enable logic are unconfirmed.
**Uncertainties:** ID 1-5 maps to rotors or runners? Comparison `>` or `>=`? 0x7B7A6 enable semantics (cal point vs runtime)? What 0x5BA00 does with the result? All 5 injectors or active rotor only?
