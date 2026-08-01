# getBaroSensorVal @ 0xD144

_source: AI (Haiku) draft, unverified_

**Purpose:** Reads barometric pressure sensor ADC value, applies fixed-point scaling/conversion, and validates against min/max bounds. Returns normalized float value and status code.

**Inputs:** 
- r3 @ 0xFFFF9F18: ADC sensor register (barometric)
- r14 @ 0xFFFFA3E2: output buffer (or return address)
- r2 @ 0x0006D470: raw sensor value
- r1 @ 0x00002510: fixedPointScaling helper

**Outputs / side effects:** 
- r0: status code (0=valid, 1=overrange_high, 2=overrange_low)
- *r14: normalized 16-bit sensor reading (written at 0xD166)
- *r14+4: float result (at 0xFFFFA3DC and 0xFFFFA3E0)

**Calls:** 
- 0x00002510 (fixedPointScaling): convert 16-bit ADC to normalized value
- 0x000024C0 (fixedPointToFloat_16bit_MULT_OFF_SIG): convert scaled int to float with multiplier/offset/signature

**Behavior:** 
1. Save r14 (frame pointer) and return address
2. Load barometric ADC register @ 0xFFFF9F18 into r2
3. Load min/max thresholds from 0x0006D470 (min) and 0x0006D46E (max)
4. Write ADC value to temp stack location (r15)
5. Call fixedPointScaling(adc_val, r5=?, r6=?) → r0
6. Store result at *r14
7. Load float constant 7.62939e-05 (approx 1/13107)
8. Load pre-computed scale factors from 0x0007978C (fr3) and 0x00079790 (fr2)
9. Compute float: fr0 = fr2 + (fr3 * fr0)  [fmac]
10. Store float result at 0xFFFFA3DC
11. Load r3 = result, compare vs min at 0x0006D46C
12. If r3 > min: status = 1, return
13. Load r3 again, compare vs max at 0x0006D46E
14. If r3 >= max: status = 0, else status = 2
15. Return with status in r0

**Draft C:** 
```c
typedef struct {
    uint16_t raw;
    float normalized;
    uint8_t status;
} BaroSensorResult;

uint8_t getBaroSensorVal(BaroSensorResult *out) {
    uint16_t adc_val = *(volatile uint16_t *)0xFFFF9F18;
    uint16_t min_threshold = *(uint16_t *)0x0006D46C;
    uint16_t max_threshold = *(uint16_t *)0x0006D46E;
    
    uint16_t scaled = fixedPointScaling(adc_val, /* unknown */, /* unknown */);
    out->raw = scaled;
    
    float scale = 7.62939e-05;
    float f2 = *(float *)0x00079790;
    float f3 = *(float *)0x0007978C;
    out->normalized = f2 + (f3 * scale * scaled);
    
    if (scaled > max_threshold) return 1;  // Over range high
    if (scaled >= min_threshold) return 0; // Valid
    return 2;  // Over range low
}
```

**Confidence:** med — control flow and float operations are clear, but exact semantics of fixedPointScaling and threshold interpretation unclear. Status code mapping is inferred.

**Uncertainties:** 
- What are the r5, r6 arguments to fixedPointScaling?
- Why two separate range checks? (Logic seems inverted)
- Is 0xFFFFA3E0 an output or something else?
- Float constant derivation (1/13107)?
