# calcDiagFuelInjectorTrim @ 0x4AE38
**Purpose:** Calculate and store diagnostic fuel injector trim correction. Reads per-rotor trim values and compares against engine-on condition and multiple thresholds to determine if trim is valid.
**Inputs:** Engine-on flag from 0xA41C (u8, 1 = engine running) ; Trim valid flag from 0xFFFFCD10 (u8) ; Injector ID / rotor select from 0xFFFFCD10 (u8, values 1-5 likely) ; Trim calibration thresholds from ROM (0x7B7E8, 0x7B7EC, 0x7B7F0, 0x7B7F4, 0x7B7F8) ; Global trim enable flag from 0x7B7A6
**Out:** Writes trim result (0 or 1) to 0xFFFFCD1B (diagnostic trim output) ; Writes to register 0xCCFA (via function 0x5BA00)
**Calls:** Function 0x5BA00 - writes trim result to output register; takes trim flag in r4
Read engine-on flag from 0xA41C ; If engine NOT running: clear output, return ; Read injector ID from 0xFFFFCD10 (values 1-5) ; Read trim value from 0xA9FC (float, calibration) ; Switch on injector
ID: ; ID 1: compare against threshold 0x7B7E8 ; ID 2: compare against threshold 0x7B7EC ; ID 3: compare against threshold 0x7B7F0 ; ID 4: compare against threshold 0x7B7F4 ; ID 5: compare against
threshold 0x7B7F8 ; If trim > threshold: set enable flag ; Check global trim enable at 0x7B7A6 ; If not enabled: clear flag ; Write final state (0 or 1) to 0xFFFFCD1B
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
**Status:** med - Core structure clear; exact threshold comparison and enable logic unconfirmed.
**Uncertainties:** Whether injector ID 1-5 maps to rotors or rotary runners ; Whether comparison is > or >= ; Semantics of 0x7B7A6 enable flag (calibration point or runtime flag?) ; What function 0x5BA00 does with the result (write register, CAN message?) ; Whether all 5 injectors are checked or just active rotor
