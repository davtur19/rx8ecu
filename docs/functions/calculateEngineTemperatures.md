# calculateEngineTemperatures @ 0x301B0
**Purpose:** Calculate three engine temperatures (coolant, intake air, catalyst) using linear interpolation/filter.
**Inputs:** Temperature sensor raw values from ROM tables: ; Table 1 @ 0x767FC (intercept/offset) ; Table 2 @ 0x76800 (intercept/offset) ; Table 3 @ 0x76804 (intercept/offset) ; Filter coefficient from RAM 0xA9FC (f32, typically 0.0–1.0 for first-order filter)
**Out:** Writes 3 calculated temperatures to RAM: ; 0xFFFFBE10 (coolant temperature, f32) ; 0xFFFFBE14 (intake air temperature, f32) ; 0xFFFFBE18 (catalyst temperature, f32)
**Calls:** None (math-only)
Initialize fr6 = 1.0 (constant for filter blend) ; Load table values (intercepts) from ROM tables at 0x767FC, 0x76800, 0x76804 ; Load filter coefficient from RAM 0xA9FC into fr5 ; For each of 3
temperatures: ; Load current (old) value: temp_old = value_from_table ; Load new (raw) value: temp_new = sensor_raw ; Compute difference: delta = temp_new - 1.0 (fr6 = 1.0) ; Apply first-order filter:
temp_filtered = temp_old + (delta * filter_coeff) + (temp_new * (1.0 - filter_coeff)) ; Actually: temp_filtered = temp_new + (delta * filter_coeff) [simplified] ; Write to output RAM
**Draft C:**
```c
void calculateEngineTemperatures(void) {
    float filter_coeff = *(float*)0xA9FC;
    float baseline = 1.0f;
    // Coolant temperature
    float coolant_raw = *(float*)0x767FC;
    float coolant_delta = coolant_raw - baseline;
    float coolant_filtered = coolant_raw + (coolant_delta * filter_coeff);
    *(float*)0xFFFFBE10 = coolant_filtered;
    // Intake air temperature
    float intake_raw = *(float*)0x76800;
    float intake_delta = intake_raw - baseline;
    float intake_filtered = intake_raw + (intake_delta * filter_coeff);
    *(float*)0xFFFFBE14 = intake_filtered;
    // Catalyst temperature
    float catalyst_raw = *(float*)0x76804;
    float catalyst_delta = catalyst_raw - baseline;
    float catalyst_filtered = catalyst_raw + (catalyst_delta * filter_coeff);
    *(float*)0xFFFFBE18 = catalyst_filtered;
}
```
**Status:** med — float math operations are clear (fmul, fmac); interpretation of filter and baseline values inferred; actual sensor calibration tables unknown.
**Uncertainties:** Exact meaning of baseline constant 1.0 (may be offset, may be denominator) ; Whether filter is first-order IIR or something else ; Whether values at 0x767FC etc. are temperatures or raw sensor readings ; Units (Celsius, Kelvin, offset value)
