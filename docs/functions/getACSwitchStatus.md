# getACSwitchStatus @ 0x2FD20

_source: AI (Haiku) draft, unverified_

**Purpose:** Read A/C compressor clutch switch status from ADC input and write result.

**Inputs:** 
- ADC input register from RAM 0xFFFF9ECD (uint8_t, contains multiple switch bits)

**Outputs / side effects:** 
- Extracts bit 4 and writes result (0 or 1) to RAM 0xBDD8 (uint8_t)

**Calls:** None

**Behavior:**
1. Load ADC input value from RAM 0xFFFF9ECD into r0
2. Extract bit 4 using `tst #4,r0` (test bit 4)
3. Convert to boolean: movt r0 (sets r0=1 if bit 4 set, else r0=0)
4. If result == 1, set r3 = 1; else r3 = 0
5. Write r3 to RAM 0xBDD8

**Draft C:**
```c
void getACSwitchStatus(void) {
    uint8_t adc_input = *(uint8_t*)0xFFFF9ECD;
    uint8_t ac_status = (adc_input & 0x10) ? 1 : 0;  // Extract bit 4
    *(uint8_t*)0xBDD8 = ac_status;
}
```

**Confidence:** high — bit extraction and write are straightforward; function name confirms A/C switch purpose.

**Uncertainties:** 
- Whether bit 4 is active-high or active-low (assumed active-high per convention)
- Electrical characteristics of the switch (normally open vs normally closed)
