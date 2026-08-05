# revLimitFuelCutInit @ 0xEE68
**Purpose:** Conditionally initialize rev-limit fuel-cut state: if not yet initialized (flag check), zero out RPM counter, status, and hysteresis variables.
**Inputs:** r4–r7: unused ; Global @ `0xFFFF9F8C`: initialization flag (1 = already initialized, 0 = initialize now)
**Out:** Writes 0 to RAM `0xA4A4` (likely RPM counter or status byte 1) ; Writes 0 to RAM `0xA4A5` (likely RPM counter or status byte 2) ; Writes 0 (word, sign-extended) to RAM `0xFFFFA4A8` (likely hysteresis state or debounce timer) ; No return value (r0 undefined on exit)
**Calls:** None
Load 1-byte flag from `0xFFFF9F8C`; zero-extend to full r0 ; Compare r0 with immediate 1 (test if already initialized) ; If flag ≠ 1 (branch false), skip to exit ; If flag = 1: zero three RAM fields
and return
**Draft C:**
```c
void revLimitFuelCutInit(void) {
  volatile uint8_t *init_flag = (uint8_t *)0xFFFF9F8C;
  if (*init_flag == 1) {
    *(uint8_t *)0xA4A4 = 0;      // zero status/counter byte 1
    *(uint8_t *)0xA4A5 = 0;      // zero status/counter byte 2
    *(uint16_t *)0xFFFFA4A8 = 0; // zero hysteresis/timer state
  }
  // else: do not initialize (already done or condition not met)
}
```
**Status:** med
**Uncertainties:** Semantics of the three RAM fields (0xA4A4, 0xA4A5, 0xFFFFA4A8) are inferred from function name; require cross-reference with callers or downstream use to confirm they are indeed RPM counter, status, and hysteresis. ; Logic is inverted from typical "init-if-not-done" pattern: flag=1 means *do* initialize, not "skip if already done"—may indicate flag is "EnableInit" or "InitRequest" rather than "AlreadyInitialized".
