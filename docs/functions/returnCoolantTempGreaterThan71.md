# returnCoolantTempGreaterThan71 @ 0x5E5F0

_source: AI (Haiku) draft, unverified_

**Purpose:** Check if coolant temperature exceeds ~71°C; used as an enable condition for various diagnostics and fuel control logic.

**Inputs:**
- None (reads global coolant temp flag from 0xFFFFD1D0)

**Outputs:**
- r0: Boolean (1 if coolant > 71°C, 0 otherwise)

**Calls:**
- None

**Behavior:**

1. Load address of coolant temp flag: r3 = 0xFFFFD1D0
2. Load byte flag from that address: r0 = [0xFFFFD1D0]
3. Zero-extend byte to 16-bit value
4. Compare r0 == 1
5. Move T flag (condition result) to r4 via movt: r4 = (r0 == 1) ? 1 : 0
6. Return value in r0 (move r4 to r0)

**Draft C:**

```c
uint8_t returnCoolantTempGreaterThan71(void) {
    uint8_t coolant_flag = *(volatile uint8_t *)0xFFFFD1D0;
    return (coolant_flag == 1) ? 1 : 0;
}
```

**Confidence:** high
- Very simple straightforward flag check
- Address 0xFFFFD1D0 likely holds a boolean coolant temp enable flag
- The threshold name "71" suggests this is derived from a temperature comparison elsewhere
- Uncertainties:
  - Whether 0xFFFFD1D0 is the raw temperature or a preprocessed flag
  - Exact threshold temperature (context suggests ~71°C)
  - Whether value==1 check means "enabled/above threshold" (assumed yes)
