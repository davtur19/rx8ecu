# INT_ATU101_IMI10AG @ 0x803E

_source: AI (Haiku) draft, unverified_

**Purpose:** Advanced Timer Unit (ATU) input match interrupt handler - accumulate timer data and compute floating-point ratio.

**Inputs (via interrupt state):**
- r4: loop counter / max iteration count
- r5: timer edge counter (incremented)
- r6: accumulator / sum register
- r7: previous or reference value

**Outputs / side effects:**
- 0xFFFF9F88: accumulated timer value (r6 written)
- 0xFFFF9F80: computed float result (fdiv result written)
- ATU timer registers: possibly cleared or updated

**Calls:** none (ATU interrupt handler)

**Behavior:**
1. Copy r7 to r5 (preserve input)
2. Load pointer 0xFFFF9FD0 into r7 (ATU register base)
3. Increment r5 (edge counter += 1)
4. Load 32-bit value from r7 into r3, post-increment r7
5. Zero-extend r5 to r2 (byte-sized counter)
6. Add r3 to r6 (accumulate timer values)
7. Compare: if r2 < r4, loop back to step 4
8. Load output address 0xFFFF9F88 into r4
9. Copy r6 (accumulated sum) to r2
10. Load floating-point scale constant 1.2e+08 from 0x80D4
11. Convert r6 integer to float (fpul -> fr3)
12. Store r6 to 0xFFFF9F88 (raw accumulator)
13. Load scale factor (1.2e+08) from ROM into fr2
14. Divide: fr2 = fr2 / fr3 (scale / accumulator)
15. Load output address 0xFFFF9F80 into r3
16. Store result fr2 (float) to 0xFFFF9F80

**Draft C:**
```c
void INT_ATU101_IMI10AG(void) {
  volatile uint32_t* atu_base = (volatile uint32_t*)0xFFFF9FD0;
  volatile uint32_t* out_raw = (volatile uint32_t*)0xFFFF9F88;
  volatile float* out_scaled = (volatile float*)0xFFFF9F80;
  
  uint32_t accumulator = 0;
  for (int i = 0; i < loop_count; i++) {
    uint32_t timer_val = atu_base[i];
    accumulator += timer_val;
  }
  
  *out_raw = accumulator;
  float scale_factor = 1.2e+08f;
  *out_scaled = scale_factor / (float)accumulator;
}
```

**Confidence:** med - ATU register layout and loop bounds inferred from offsets; floating-point operations clear but scale factor purpose (frequency conversion?) not evident. May be engine speed or timing measurement.
