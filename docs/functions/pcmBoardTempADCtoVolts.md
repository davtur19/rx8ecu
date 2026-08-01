# pcmBoardTempADCtoVolts @ 0x3F158

_source: AI (Haiku) draft, unverified_

**Purpose:** Convert PCM board temperature ADC raw sample to calibrated voltage value. Applies scaling factor and offset from calibration table.

**Inputs:**
- ADC raw sample from 0xFFFF9F16 (u16)
- Scaling multiplier from ROM 0x3F174 (float, value ~7.63e-05)
- Offset/signature from calibration (handled by fixedPointToFloat_16bit_MULT_OFF_SIG)

**Outputs / side effects:**
- Writes converted voltage float to 0xC6A8 (register/memory output)
- Returns converted float in fr0

**Calls:**
- fixedPointToFloat_16bit_MULT_OFF_SIG (0x24C0) - converts fixed-point ADC to float with multiplier and offset

**Behavior:**
1. Initialize fr5 = 0.0 (zero)
2. Load scaling factor 7.63e-05 from ROM into fr4
3. Read ADC sample from 0xFFFF9F16 into r4
4. Call fixedPointToFloat_16bit_MULT_OFF_SIG(adc_sample, multiplier, offset)
5. Store result to 0xC6A8
6. Return in fr0

**Draft C:**
```c
float pcmBoardTempADCtoVolts() {
    u16 adcSample = *(u16*)0xFFFF9F16;
    float scale = 7.62939e-05f;  // 1/13107.2 (12-bit ADC / 5V range)
    float offset = 0.0f;         // or from calibration
    
    float voltage = fixedPointToFloat_16bit_MULT_OFF_SIG(
        adcSample, 
        scale, 
        offset
    );
    
    *(float*)0xC6A8 = voltage;
    return voltage;
}
```

**Confidence:** high - Conversion pattern clear; scaling factor suggests 12-bit ADC with 5V full scale.

**Uncertainties:**
- Exact offset value and where it comes from
- Whether 0xC6A8 is a register or RAM storage
- Context (is this board temp or sensor temp?)
- Return value semantics vs side effect
