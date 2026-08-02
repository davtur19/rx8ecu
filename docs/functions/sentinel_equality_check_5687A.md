# sentinel_equality_check_5687A @ 0x5687A

**Address:** 0x5687A – 0x56892  (24 bytes)
**ROM:** 60E1D400.bin
**Source label:** ida-ai
**Track-A verification:** emulator (256×5 + 500 random)

---

## Overview

Compares an input byte against a memory-mapped calibration value at
0xFFFFD20B, returning the smaller (least) of the two.  Acts as a
clamp / saturate operation for byte-sized parameters.

## Logic

```c
uint8_t sentinel_equality_check_5687A(uint8_t input) {
    uint8_t cal = *(uint8_t*)0xFFFFD20B;
    return (input < cal) ? input : cal;
}
```

## Verification

- [x] Disassembly confirmed against capstone + Ghidra
- [x] C code written (`c/sentinel_equality_check_5687A.c`)
- [x] Emulator test: `test_sentinel_equality_check_5687A.py` — all 256 input values × 5 calibration values + 500 random, all pass
