# calculateCruiseControlSwitchVolt @ 0x2C5D0
**Purpose:** Convert cruise control switch ADC reading to a float voltage value (normalized, scaled).
**Inputs:** ADC value from RAM 0xFFFF9F1A (uint16_t) ; Scaling constant 7.62939e-05 (from ROM 0x2C6A8)
**Out:** Converts ADC to float ; Stores result in two memory locations (fr0 stored at 0xBC68 as f32)
**Calls:** fixedPointToFloat_16bit_MULT_OFF_SIG @ 0x24C0 (converts 16-bit fixed-point to float with multiplier)
Initialize fr5 to 0.0 (fldi0) ; Load scaling multiplier 7.62939e-05 into address r0 (mova) ; Read ADC value from 0xFFFF9F1A into r4 ; Call fixedPointToFloat_16bit_MULT_OFF_SIG(ADC_value, multiplier) ;
Load multiplier as f32 from address in r0 into fr4 ; Store result (fr0) to RAM 0xBC68
**Draft C:**
```c
void calculateCruiseControlSwitchVolt(void) {
    uint16_t adc_val = *(uint16_t*)0xFFFF9F1A;
    float multiplier = 7.62939e-05f;
    float result = fixedPointToFloat_16bit_MULT_OFF_SIG(adc_val, multiplier);
    *(float*)0xBC68 = result;
}
```
**Status:** med — function name and equinox naming confirmed; actual implementation likely involves offset + multiplication; unclear if there's offset applied.
**Uncertainties:** Whether "MULT_OFF_SIG" includes offset calculation (likely yes, but unknown magnitude) ; Purpose of fr5 initialization (may be unused)
