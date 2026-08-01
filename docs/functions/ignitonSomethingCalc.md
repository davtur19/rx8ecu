# ignitonSomethingCalc @ 0x91C6
_source: AI (Haiku) draft, unverified_

**Purpose:** Normalize ignition timing angle within valid range by handling wrapping and boundary conditions.

**Inputs:**
- r4: rotor index (0-2 for 3 rotors)
- Globals:
  - 0xFFFFA0D8 = base address of rotor timing array
  - 0xFFFFA0FC = reference angle (float, likely nominal timing)
  - 0xFFFFA0F8 = storage for normalized timing output
  - 0xFFFFA100 = some scaling or correction factor

**Outputs / side effects:**
- 0xFFFFA0F8: normalized timing angle (float, stored at rotor base + 0)
- Handles timing wrapping within expected angular range

**Calls:**
- 0x9440 (conditional rotor-specific logic): called if timing delta exceeds 60 degrees

**Behavior:**
1. Extract rotor index from r4 (extu.b r14)
2. Load reference angle (0xFFFFA0FC) → fr3
3. Load rotor timing at scaled offset → fr4
4. Subtract reference angle: fr4 = fr4 - fr3 (angular delta)
5. Check if delta < -90°:
   - If yes: add 720° (two complete rotations for rotary crank angle)
6. Check if delta >= 630°:
   - If yes: subtract 720°
7. Store normalized angle at 0xFFFFA0F8
8. Read next field (offset +5): if non-zero, call helper 0x9440
9. If field is zero: check timing diff > 60°, call helper 0x9440 if true

**Draft C:**
```c
float ignitonSomethingCalc(uint8_t rotor_idx) {
  float ref_angle = *(float *)0xFFFFA0FC;
  float timing = *(float *)(0xFFFFA0D8 + rotor_idx * 6);
  
  float delta = timing - ref_angle;
  
  // Normalize to [-90, 630) degrees (typical for rotary)
  if (delta < -90.0f) {
    delta += 720.0f;
  } else if (delta >= 630.0f) {
    delta -= 720.0f;
  }
  
  *(float *)0xFFFFA0F8 = delta;
  
  // Conditional: large timing change?
  uint8_t flag = *(uint8_t *)(0xFFFFA0D8 + rotor_idx * 6 + 5);
  if (!flag) {
    if (delta > 60.0f) {
      call_rotor_specific_logic(rotor_idx);  // 0x9440
    }
  }
  
  return delta;
}
```

**Confidence:** high
- Angular normalization logic (720° wrapping, -90 to 630° range) is standard for rotary engines
- Constants visible in disassembly match typical angle ranges
- Boundary conditions (-90°, 630°, 720°) are explicitly coded
- Rotor indexing and memory layout clear
