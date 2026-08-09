# LongFunc @ 0x2158
**Purpose:** Fixed-point 32-bit division or reciprocal conversion with saturation.
**Inputs:** r4: dividend / numerator (32-bit fixed-point) ; r5: divisor / denominator (32-bit fixed-point, may be signed) ; r7: dividend (alternative input path)
**Out:** r0: quotient / result (32-bit fixed-point)
**Calls:** none
Check r4 and r5 for special cases (zero divisor, zero dividend) ; Perform SH-2 64-bit division with a `div0s` / `div1` loop (32 iterations) ; Accumulate result in r4 with `rotcl` (rotate carry left) ;
Check result bounds: if result > 0x7FFF or < ~0x7FFF, saturate to MAX_INT / MIN_INT ; Perform second 32-bit division on normalized value ; Aggregate final result
**Draft C:**
```c
int32_t LongFunc(int32_t dividend, int32_t divisor) {
  if (divisor == 0 || dividend == 0) return 0;
  // 64-bit signed division loop (32x div0s/div1 cycles)
  int64_t result = dividend / divisor;
  // Saturate to 16-bit signed range or similar
  if (result > 0x7FFF) result = 0x7FFF;
  if (result < -0x8000) result = -0x8000;
  return (int32_t)result;
}
```
**Status:** low - div0s/div1 loop strongly suggests fixed-point division, but exact semantics of saturation thresholds and output precision unclear. May be reciprocal or reciprocal square root instead.
