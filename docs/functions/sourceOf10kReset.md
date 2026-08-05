# sourceOf10kReset @ 0x48B5E
**Purpose:** Check conditions for performing a 10k-mile maintenance reset and flag accordingly.
**Inputs:** None
**Out:** Flag at 0xFFFFCC1B: set to 1 if reset conditions met, 0 otherwise ; Floating-point scratch: fr14, fr15
**Calls:** getFaultStatus ?? @ 0x652F0 (check fault/DTC status with parameter 29 in r4)
Load threshold values from 0xB594 (fr15), 0xA9FC (fr14) ; Call getFaultStatus(29) to check status ; If fault status returned non-zero, exit without setting flag ; Compare various sensor values (likely
fuel trims, temp, etc.) against thresholds: ; Load float from 0x7B128, compare fr15 > value → exit if true ; Load float from 0x7B12C, compare fr15 > value → exit if true ; Load float from 0x7B130,
compare fr14 > value → exit if true ; Load float from 0x7B134, compare fr14 > value → exit if true ; Check enable flags at 0xB129 and 0xAD88 (both must == 1) ; Check inhibit flag at 0xCFD9 (must == 0)
; If all conditions pass, set flag at 0xFFFFCC1B to 1; otherwise set to 0
**Draft C:**
```c
void sourceOf10kReset(void) {
  float threshold_a = *(float*)0xB594;
  float threshold_b = *(float*)0xA9FC;
  uint8_t fault_status = getFaultStatus(29);
  if (fault_status != 0) {
    *(uint8_t*)0xFFFFCC1B = 0;
    return;
  }
  float val1 = *(float*)0x7B128;
  float val2 = *(float*)0x7B12C;
  float val3 = *(float*)0x7B130;
  float val4 = *(float*)0x7B134;
  if (threshold_a > val1 || threshold_a > val2 ||
      threshold_b > val3 || threshold_b > val4) {
    *(uint8_t*)0xFFFFCC1B = 0;
    return;
  }
  uint8_t enable1 = *(uint8_t*)0xB129;
  uint8_t enable2 = *(uint8_t*)0xAD88;
  uint8_t inhibit = *(uint8_t*)0xCFD9;
  if (enable1 == 1 && enable2 == 1 && inhibit == 0) {
    *(uint8_t*)0xFFFFCC1B = 1;
  } else {
    *(uint8_t*)0xFFFFCC1B = 0;
  }
}
```
**Status:** med – logic clear (fault check + threshold comparisons + enable/inhibit flags); exact sensor identities and numerical thresholds unknown
