# fuelInjectionRelated @ 0xFF36
**Purpose:** Configure fuel injection pulse width and timing based on injection mode; compute injector on-time in TDC counts.
**Inputs:** r4: pointer to fuel injection control struct with mode byte at offset 0
**Out:** Writes 4-byte values at multiple offsets within r4 struct: ; offset 32: pulse width A (primary, computed) ; offset 56: pulse width B (secondary, computed) ; offset 80: pulse width C or overlap timing (computed) ; offset 40: related value copied/computed ; Uses float scaling constant 65536.0 (fixed-point conversion for TDC timing)
**Calls:** None (self-contained math)
Load constant 65536.0 → fr4 ; Read byte at r4+0 (injection mode) → r0 ; Branch based on mode: ; Mode 0: ; a. Load offset float from 0x1001C (-275.0) ; b. Read current fuel value from 0xA440 ; c. Add
offset: fuel - 275 ; d. Multiply by 65536.0 (convert to TDC counts) ; e. Convert to int32 → store at r4+32 ; f. Load related value from r5+16 → store at r5+64 ; Mode 1: ; a. Load three float
calibration values from 0xA40C, 0xA434, 0xA43C ; b. Multiply each by 65536.0 constant ; c. Convert each to int32 ; d. Store at r4+32, r4+56, r4+80 (three fuel injection parameters) ; Default (Mode
other): ; a. Return (no operation)
**Draft C:**
```c
struct fuel_injection_control {
  uint8_t mode;           // offset 0
  // ... padding
  uint32_t pulse_width_a; // offset 32 (TDC counts)
  uint32_t pulse_width_b; // offset 56 (TDC counts)
  uint32_t pulse_width_c; // offset 80 (TDC counts)
};
void fuelInjectionRelated(fuel_injection_control *ctrl) {
  const float SCALE = 65536.0f;
  if (ctrl->mode == 0) {
    float offset = -275.0f;
    float fuel_base = *(float *)0xA440;
    float pulse = (fuel_base + offset) * SCALE;
    ctrl->pulse_width_a = (int32_t)pulse;
    uint32_t *src = (uint32_t *)(ctrl + 16);
    uint32_t *dst = (uint32_t *)(ctrl + 64);
    *dst = *src;
  } else if (ctrl->mode == 1) {
    float val_a = *(float *)0xA40C;
    float val_b = *(float *)0xA434;
    float val_c = *(float *)0xA43C;
    ctrl->pulse_width_a = (int32_t)(val_a * SCALE);
    ctrl->pulse_width_b = (int32_t)(val_b * SCALE);
    ctrl->pulse_width_c = (int32_t)(val_c * SCALE);
  }
}
```
**Status:** high — branches and float loads clear; 65536 scaling standard for TDC conversion; mode-0 offset (-275) likely pressure/temp correction; mode-1 three-output fits the 3-rotor layout.
