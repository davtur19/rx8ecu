# adcVoltageOutOfRangeCheck @ 0x3C992
**Purpose:** Validate ADC voltage reading against calibration bounds. Flag out-of-range condition in output byte.
**Inputs:** ADC voltage float in fr4 (input parameter) ; Calibration min bound from 0x000796FC (float) ; Calibration max bound from 0x00079700 (float)
**Out:** Writes 1 to 0xC5D2 if voltage below min ; Writes 0 to 0xC5D2 if voltage in range ; Writes 1 to 0xC5D3 if voltage above max ; Writes 0 to 0xC5D3 if voltage in range
**Calls:** None (direct comparison only)
Load min threshold from 0x000796FC into fr3 ; Compare fr4 (input voltage) > fr3 (min) ; If fr4 <= min: write 1 (out-of-range) to 0xC5D2, else write 0 ; Load max threshold from 0x00079700 into fr3 ;
Compare fr3 (max) > fr4 (input voltage) ; If max <= fr4: write 1 (out-of-range) to 0xC5D3, else write 0
**Draft C:**
```c
void adcVoltageOutOfRangeCheck(float voltage) {
    float minBound = *(float*)0x000796FC;
    float maxBound = *(float*)0x00079700;
    if (voltage <= minBound) {
        *(u8*)0xC5D2 = 1;  // below minimum
    } else {
        *(u8*)0xC5D2 = 0;  // in range
    }
    if (voltage >= maxBound) {
        *(u8*)0xC5D3 = 1;  // above maximum
    } else {
        *(u8*)0xC5D3 = 0;  // in range
    }
}
```
**Status:** high - Function is straightforward; two independent range checks with clear logic.
**Uncertainties:** Whether outputs represent "error" or "warning" flags ; Whether both checks run or if second is conditional on first ; Use context (OBD, EOBD fault codes?)
