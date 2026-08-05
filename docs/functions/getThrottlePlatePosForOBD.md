# getThrottlePlatePosForOBD @ 0x536B6
**Purpose:** Read and convert throttle plate ADC value for OBD reporting.
**Inputs:** r0: scratch ; Global: ADC register at 0xADC0
**Out:** r0: throttle plate position (float via fr0) ; fr15: saved across call
**Calls:** fixedPointToFloat_16bit_MULT_OFF_SIG @ 0x24C0 (converts ADC value to float) ; floatToInt_SIGNAL_MULT_OFFSET @ 0x24D0 (scales float)
Initialize fr15=0.0 ; Read ADC value from 0xADC0 into r4 ; Load constants: 7.62939e-05 (ADC scale), 20 (multiplier), 0.392157 (offset) ; Call fixedPointToFloat_16bit_MULT_OFF_SIG with ADC value → fr0
; Multiply fr0 by 20 ; Call floatToInt_SIGNAL_MULT_OFFSET with result and 0.392157 offset ; Return result in r0
**Draft C:**
```c
float getThrottlePlatePosForOBD(void) {
  uint16_t adc_val = *(uint16_t*)0xADC0;
  float pos = fixedPointToFloat_16bit_MULT_OFF_SIG(adc_val, 7.62939e-05);
  float scaled = pos * 20.0f;
  return floatToInt_SIGNAL_MULT_OFFSET(scaled, 0.392157);
}
```
**Status:** med – function calls verified but exact scale factors unconfirmed; equinox name reliable
