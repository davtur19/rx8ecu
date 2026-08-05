# mod32_signed @ 0x4144

**Track-A verification:** C host test (100K random + 22 edge cases)

## Overview

Full 32-bit signed remainder (modulo) using the SH-2E's div0s/div1
algorithm.  The remainder counterpart to `div32_signed` (0x3FE8).
Computes the remainder with truncation toward zero, matching C99
`dividend % divisor` semantics.

On divide-by-zero: writes error code 0x44E to 0xFFFF7304 and returns 0.

## Signature

```c
int32_t mod32_signed(int32_t divisor /* r0 */, int32_t dividend /* r1 */);
```

## Logic

```c
int32_t mod32_signed(int32_t divisor, int32_t dividend) {
    if (divisor == 0) {
        error_write(0xFFFF7304, 0x44E);
        return 0;
    }
    return dividend % divisor;  // truncating toward zero
}
```

## Relationship to div32_signed

Both functions use the same div0s/div1 initialisation and 32-iteration
loop.  `div32_signed` returns the quotient (r1 after correction);
`mod32_signed` returns the remainder (r3 after correction).

## Verification

- [x] Disassembly confirmed against capstone + Ghidra
- [x] C code written (`c/mod32_signed.c`)
- [x] C host test: `test_mod32_signed.c` — 100K random + 22 edge cases, matches C99 remainder
