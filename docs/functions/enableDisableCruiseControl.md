# enableDisableCruiseControl @ 0xC116
**Purpose:** Enable or disable cruise control with interrupt mask management.
**Inputs:** r4: desired interrupt mask value (typically 0x10=enable all, 0x00=disable)
**Out:** Cruise control state flags at 0xFFFFA324, 0xFFFFA384, 0xFFFFA385 modified ; CPU SR (status register) interrupt mask updated
**Calls:** getSR @ 0x3920 (read current interrupt mask) ; setSR @ 0x3934 (write new interrupt mask)
Read current SR (interrupt mask) via getSR() ; Store desired mask in r4 ; Load current mask from 0xFFFFA38C ; Save desired mask (from stack) ; If current mask != desired mask: ; Write 0xFF to
0xFFFFA384 (enable?) ; Write 0x00 to 0xFFFFA385 (disable?) ; Write 0x00 to 0xFFFFA324 (control flag) ; Store desired mask to 0xFFFFA38C ; Apply new SR via setSR() with current SR in r4
**Draft C:**
```c
void enableDisableCruiseControl(uint8_t interrupt_mask) {
  uint8_t current_sr = getSR();
  uint8_t* state_flag = (uint8_t*)0xFFFFA38C;
  if (current_sr != interrupt_mask) {
    *(uint8_t*)0xFFFFA384 = 0xFF;    // Enable
    *(uint8_t*)0xFFFFA385 = 0x00;    // Disable
    *(uint8_t*)0xFFFFA324 = 0x00;    // Control
    *state_flag = interrupt_mask;
  }
  setSR(current_sr);
}
```
**Status:** med – getSR/setSR pattern confirmed, interrupt masking logic clear; exact semantic (what each state flag controls) uncertain
