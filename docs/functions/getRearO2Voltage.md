# getRearO2Voltage @ 0xD1E0
**Purpose:** Read rear O2 (oxygen sensor) ADC value from RAM and convert to voltage via fixed-point scaling.
**Inputs:** Global @ 0xFFFF9EF2: ADC count (16-bit, rear O2 sensor raw reading)
**Out:** Global @ 0xFFFFA3E4: Float voltage value (result of ADC * 7.62939e-05) ; Return: None (void function)
**Calls:** None (no subroutine calls)
Load rear O2 ADC address (0xFFFF9EF2) into r4 ; Read 16-bit ADC count from that address ; Zero-extend to 32-bit unsigned integer ; Load scaling constant 7.62939e-05 (≈ 1/13107) into fr2 from ROM
0xD200 ; Convert ADC count (r4) to single-precision float (fr3) ; Multiply float by scaling constant: fr3 = fr3 * fr2 ; Store result float to output location 0xFFFFA3E4 ; Return
**Draft C:**
```c
void getRearO2Voltage(void) {
    volatile uint16_t *adc_addr = (volatile uint16_t *)0xFFFF9EF2;
    volatile float *result_addr = (volatile float *)0xFFFFA3E4;
    uint16_t adc_count = *adc_addr;
    float voltage = (float)adc_count * 7.62939e-05f;
    *result_addr = voltage;
}
```
**Status:** High. Function structure is straightforward: read ADC, scale by constant, store float. The scaling factor 7.62939e-05 is typical for SH-2E single-precision FPU calibration (ADC counts 0–13107 ≈ 0–1.0V). Exact meaning of the RAM globals depends on ECU memory map documentation, but the operation is clear.
