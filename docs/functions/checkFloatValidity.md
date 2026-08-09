# checkFloatValidity @ 0x46CC

**ROM:** 60E1D400.bin (also present in 60E0FC00.bin at same offset)
**Track-A verification:** C host test (16 edge cases)

## Overview

This is IEEE 754 floating-point validation. It checks if a float value is NaN or
Infinity by examining the exponent bits.  It writes a status code to a RAM
diagnostic address and returns the original float value unchanged.

## Logic

```c
float checkFloatValidity(float value) {
    uint32_t bits = *(uint32_t*)&value;
    if ((bits & 0x7F800000) == 0x7F800000) {
        // Exponent all 1s: NaN or Infinity
        if (bits & 0x007FFFFF)
            *(uint16_t*)0xFFFF7304 = 0x044D;  // NaN
        else
            *(uint16_t*)0xFFFF7304 = 0x044C;  // Infinity
    }
    return value;  // always pass through
}
```

### IEEE 754 Details

| Condition | Exponent (30:23) | Mantissa (22:0) | Status code |
|-----------|------------------|-----------------|-------------|
| NaN       | 0xFF             | ≠ 0             | 0x044D      |
| Infinity  | 0xFF             | = 0             | 0x044C      |
| Normal    | 0x01..0xFE       | any             | (none)      |
| Subnormal | 0x00             | ≠ 0             | (none)      |
| Zero      | 0x00             | = 0             | (none)      |

## Callers

The sensor processing pipeline uses this function throughout to validate float sensor
values before use in calculations.

## Verification

- [x] Disassembly confirmed
- [x] C code written (`c/checkFloatValidity.c`)
- [x] C host test: all 16 IEEE 754 special-value edge cases pass
- [ ] Emulator test needs FPU support for float bit ops
