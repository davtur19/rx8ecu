# calculatePerRotorIgnitionDwell @ 0x10FEA
**Purpose:** Compute the ignition dwell time (coil charge duration) for each of the 3 rotors in a rotary engine.
**Inputs:** r4: pointer to ignition dwell array struct (base address 0xFFFFA578) ; Global: 0xFFFFA0C4 = lookup table for dwell values indexed by rotor index
**Out:** Writes 3x 4-byte dwell values (in microseconds or TDC counts) at offsets 0, 16, 32 within the dwell array ; Memory writes at offsets relative to 0xFFFFA578 (r13 base)
**Calls:** 0x10F84 (called per rotor, receives rotor index in r4, returns computed dwell in r0)
Load the base address of the dwell array (0xFFFFA578) into r13 and r10 (+ offset 88). Outer loop: iterate r13 through 3 rotors (each struct is 44 bytes apart). Inner loop: read 1 byte from the rotor struct (+12
offset) as the rotor index. Scale the rotor index (shll2 → shll to get the offset into lookup table 0xFFFFA0C4). Call helper 0x10F84 with the rotor index (r4 = r12) → it returns the dwell value in r0. Store the result at
the current rotor's base + 0 bytes. Continue until all 3 rotors are processed, then advance to the next rotor struct (+44 bytes).
**Draft C:**
```c
struct rotor_ignition {
  uint32_t dwell_values[3];  // offsets 0, 16, 32 (4 bytes each, 12 bytes spacing)
  // ... other fields
};
void calculatePerRotorIgnitionDwell(rotor_ignition *arr) {
  uint8_t *base = (uint8_t *)0xFFFFA578;
  uint32_t *lut = (uint32_t *)0xFFFFA0C4;
  for (int rot = 0; rot < 3; rot++) {
    uint8_t *rotor_ptr = base + rot * 44;
    uint8_t rotor_id = rotor_ptr[12];
    uint32_t dwell = calculate_dwell_helper(rotor_id);  // 0x10F84
    *(uint32_t *)(rotor_ptr + 0) = dwell;
  }
}
```
**Status:** med ; The loop structure and offset calculations are clear ; The exact dwell computation (0x10F84) is not analyzed; the rotor struct layout is inferred ; 3 rotors and offset spacing (44 bytes) are confirmed by the loop bounds
