# secondaryAirRelated @ 0x31C50
**Purpose:** Control the secondary air injection (SAI) system for emissions warm-up. Read temperature and condition thresholds. Activate or deactivate SAI with multi-condition logic.
**Inputs:** Floats from memory (0xA9FC, 0xAE40, multiple cal tables at 0x7791x) ; Engine state/condition flags from 0xC6B0, 0xC4DE, 0xCBD4 ; ADC/sensor values from 0xFFFF9F70, 0x8088
**Out:** Write the SAI control state (0 or 1) to 0xFFFFBF8E ; Intermediate float calculation stored at 0xFFFFBF90
**Calls:** readValue_float_DEFAULTVAL_ADDRESS (0x3E1AA) - reads float with default fallback
Load calibration floats into fr14, fr15 ; Read the current SAI state and related conditions ; If the engine is on: calculate delta, apply complex conditional logic ; If the engine is off: use the alternate path
with the subtractAbsolute helper ; Write 1 (enable) or 0 (disable) based on all conditions
**Draft C:**
```c
void secondaryAirRelated() {
    float refTemp = *(float*)0xA9FC;    // calibration ref
    float refTemp2 = *(float*)0xAE40;
    if (*(u8*)0xC6B0 != 0) {  // engine running?
        float sensorVal = readValue_float(0x8088);
        float delta = sensorVal - refTemp;
        // Multi-level threshold checks
        if (checkCondition1() && checkCondition2() && ...) {
            *(u8*)0xFFFFBF8E = 1;  // enable SAI
        } else {
            *(u8*)0xFFFFBF8E = 0;
        }
    } else {
        // Engine off path
        float result = subtractAbsolute(refTemp, refTemp2);
        // more logic...
    }
}
```
**Status:** med - The function structure is clear. The exact threshold logic and condition ordering are unconfirmed. Sensor sources are partially identified.
**Uncertainties:** The exact meaning of the nested comparison chain ; Whether conditions are AND or OR ; Register allocation for intermediate values
