# getAPVPosVoltage @ 0x432BA
**Purpose:** Read accelerator pedal position (APV) ADC sample and convert to voltage. Measures pedal/throttle demand for engine control.
**Inputs:** ADC raw sample from 0xFFFF9EF0 (u16) ; Scaling factor from ROM 0x43318 (float, value ~7.63e-05) ; Calibration offset via fixedPointToFloat helper
**Out:** Writes converted voltage to 0xC9B0 (APV voltage output register) ; Returns voltage in fr0
**Calls:** fixedPointToFloat_16bit_MULT_OFF_SIG (0x24C0) - ADC to float conversion with multiplier and offset
Initialize fr5 = 0.0 (zero) ; Load scaling multiplier 7.63e-05 from ROM 0x43318 into fr4 ; Read APV ADC sample from 0xFFFF9EF0 into r4 ; Call fixedPointToFloat_16bit_MULT_OFF_SIG(sample, multiplier,
offset) ; Store result to 0xC9B0 ; Return in fr0
**Draft C:**
```c
float getAPVPosVoltage() {
    u16 adcSample = *(u16*)0xFFFF9EF0;
    float scale = 7.62939e-05f;  // 12-bit ADC: 4095 / 5V
    float offset = 0.0f;         // nominal 0V at idle
    float voltage = fixedPointToFloat_16bit_MULT_OFF_SIG(
        adcSample, 
        scale, 
        offset
    );
    *(float*)0xC9B0 = voltage;
    return voltage;
}
```
**Status:** high - Identical structure to pcmBoardTempADCtoVolts; APV context clear from address and purpose.
**Uncertainties:** Exact offset calibration (0.5V nominal at idle?) ; Whether 0xC9B0 is computed or used downstream ; Error handling if sample out of expected range
