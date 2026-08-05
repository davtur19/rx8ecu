# injectorRelatedFunc @ 0x83CA
**Purpose:** Compute fuel injector pulse width; apply SR masking, lookup injector map, apply current correction and saturation.
**Inputs:** r4 = injector index (0-3, for two rotors x two plugs each), r5 = ?, r6 = ?
**Out:** Calls getSR/setSR to save/restore interrupt state ; Reads global injector state arrays ; Writes computed injector pulse width to RAM offset +4 within injector state struct ; Writes status byte at offset +19 ; Return: via setSR, r0 = saved SR value
**Calls:** `0x00003920` (getSR) - save processor status register ; `0x00002158` (LongFunc) - unknown computation function ; `0x00003934` (setSR) - restore processor status register
Save SR via getSR (r4=16 for masking) ; Store r5, r6 to stack ; Convert r13 (injector index) to byte and compute offset: ; r14 = r13 + (r13 << 1) = r13 * 3 ; r14 = r14 << 2 = r13 * 12 (12-byte struct
per injector) ; Add base address 0xFFFFA004 (injector state array) ; Load injector accumulator from RAM ; Multiply by scale factor 0xB4 (180 decimal) via MUL.L ; Call LongFunc with computed value ;
Multiply result by 65536.0 (fixed-point to float) ; Convert float result to integer via FTRC ; Subtract from accumulator value ; Check saturation bounds: ; If < 0xFFC40000 (-4000000 fixed): add
0x02D00000 (correction) ; If >= 0x02940000: add 0xFD300000 (correction) ; Store corrected pulse width to struct offset +4 ; Check if >= 0x00230000 (threshold); if yes, call 0x8814 (error handler) ;
Restore SR and return
**Draft C:**
```c
struct InjectorState {
  u32 accum;        // offset 0
  s32 pulsewidth;   // offset 4
  u32 unknown[3];   // offsets 8-14
  u8  status;       // offset 19
};
void injectorRelatedFunc(u8 injector_idx, u32 val1, u32 val2) {
  sr_t sr = getSR();
  // Compute offset: injector_idx * 12 bytes
  u32 offset = (injector_idx + (injector_idx << 1)) << 2;
  InjectorState* inj = (InjectorState*)(0xFFFFA004 + offset);
  // Lookup current correction
  u32 accum = inj->accum;
  u32 scaled = accum * 180;  // 0xB4
  u32 correction = LongFunc(0x67F28, accum);  // lookup table
  // Apply corrections with saturation
  s32 result = accum - (s32)correction;
  if (result < -4000000) {
    result += 47000000;  // 0x02D00000
  } else if (result >= 43000000) {  // 0x02940000
    result += -48300000;  // 0xFD300000
  }
  inj->pulsewidth = result;
  if (result >= 0x00230000) {
    error_handler_0x8814(injector_idx);
    inj->status = 0;
  } else {
    inj->status = 2;
  }
  setSR(sr);
}
```
**Status:** low — the exact meaning of lookup tables, saturation bounds, and the purpose of the computation requires cross-reference with calibration documentation. The SR masking and LongFunc call suggest this is a time-critical function.
