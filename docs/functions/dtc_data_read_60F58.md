# dtc_data_read_60F58 @ 0x60F58

**Track-A verification:** emulator (500 random initial states)

## Overview

This function fills two consecutive 16-bit diagnostic words at 0xFFFFD6C8 and 0xFFFFD6CC
with the sentinel value 0xFFFF.  The DTC-read pipeline calls this to
initialise a "no fault" state before evaluating a diagnostic condition.

## Logic

```c
void dtc_data_read_60F58(void) {
    *(uint16_t*)0xFFFFD6C8 = 0xFFFF;
    *(uint16_t*)0xFFFFD6CC = 0xFFFF;
}
```

The loop at 0x60F60 writes every other 16-bit word (step 4 bytes). It covers
exactly two addresses.

## Verification

- [x] Disassembly confirmed against capstone + Ghidra
- [x] C code written (`c/dtc_data_read_60F58.c`)
- [x] Emulator test: `test_dtc_data_read_60F58.py` — 500 random initial RAM states, all pass
