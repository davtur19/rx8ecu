# getACSwitchStatus @ 0x2FD20

**Purpose:** Read A/C compressor clutch switch status from ADC input and write result.
In: ADC input register from RAM 0xFFFF9ECD (uint8_t, contains multiple switch bits)  Out: Extracts bit 4 and writes result (0 or 1) to RAM 0xBDD8 (uint8_t)  Behavior: Load ADC input value from RAM 0xFFFF9ECD into r0 ; Extract bit 4 using `tst #4,r0` (test bit 4) ; Convert to boolean: movt r0 (sets r0=1 if bit 4 set, else r0=0) ; If result == 1, set r3 = 1; else r3 = 0 ; Write r3 to RAM 0xBDD8
**Status:** high — bit extraction and write are straightforward; function name confirms A/C switch purpose. ; Whether bit 4 is active-high or active-low (assumed active-high per convention) ; Electrical characteristics of the switch (normally open vs normally closed)
