# adcIAT2Volts @ 0x1C8E2
**Purpose:** Convert the Intake Air Temperature (IAT) ADC reading to analog voltage.
**Inputs:** RAM 0xFFFF9F1E: IAT ADC raw count (16-bit)
**Out:** RAM 0xAE38: IAT voltage output (float, 0–5V range)
**Calls:** fixedPointToFloat_16bit_MULT_OFF_SIG @ 0x24C0 (converts ADC to float voltage)
Load scale/offset constant 7.62939e-05 (fixed-point multiplier for 16-bit ADC → voltage). Read IAT ADC (16-bit) from 0xFFFF9F1E. Convert to float with fixedPointToFloat_16bit_MULT_OFF_SIG. Input:
r4 = ADC count, fr4 = scale, fr5 = 0.0. Output: fr0 = voltage (0.0–5.0V equivalent). Write the result to 0xAE38. Return.
**Draft C:**
```c
void adcIAT2Volts(void) {
  float scale = 7.62939e-05f;  // 5V / 65536 ADC counts
  u16 iatADC = readMemory16(0xFFFF9F1E);
  float iatVolts = fixedPointToFloat_16bit(iatADC, scale, 0.0f);
  writeFloatMemory(0xAE38, iatVolts);
}
```
**Status:** high ; Simple ADC-to-voltage conversion. Scale factor verified (5.0V / 65536 = 7.63e-05). fixedPointToFloat_16bit_MULT_OFF_SIG is a verified helper. The IAT (intake air temperature) purpose is clear from the function name.
