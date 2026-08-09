# limitKnockRetardMax_ConditonalRPM @ 0x13AE4
**Purpose:** Apply the RPM-conditional knock retard limit. It constrains the max knock retard angle based on engine speed and operational conditions.
**Inputs:** fr4: knock retard angle (float, in degrees) ; Globals: ; 0xB594 = current engine speed (float, RPM) ; 0xB580 = a condition flag/mode byte ; 0xBB25 = another condition byte ; 0xBC75 = knock counter or condition byte ; 0x78544 = threshold byte (likely RPM threshold or condition mask)
**Out:** fr0: saturated knock retard limit (float), constrained between lower and upper bounds ; Calls saturate_SIGNAL_LOWER_UPPER helper (0x2404) to clamp value
**Calls:** 0x2068 (2DLookup): queries knock retard limit map with engine speed; uses calibration table at 0x78544 or 0x693CC/0x693B8 ; 0x2404 (saturate_SIGNAL_LOWER_UPPER): clamps result between min/max from 0xFFFFBC50 and memory location 0x78584
Save fr4 (input knock retard) on stack ; Load engine speed (0xB594) → fr4 ; Read condition bytes: r5 from 0xB580, r4 from 0xBB25 ; Check if r5 == 1: ; If yes: read r0 from 0xBC75, read r2 from
0x78544, compare r0 >= r2 → if true, jump to use map1 ; If no: check r5 == 0 (else jump to map2) ; If r5 == 0: read condition from 0x78544, if r4 > threshold or r4 == 0, use map2 ; Select lookup
table: ; map1 (0x693CC): 2DLookup with RPM ; map2 (0x693B8): 2DLookup with RPM ; Call 2DLookup → fr0 = lookup result ; Call saturate_SIGNAL_LOWER_UPPER with limits from 0x78584
**Draft C:**
```c
float limitKnockRetardMax_ConditonalRPM(float knock_retard) {
  float rpm = *(float *)0xB594;
  uint8_t cond1 = *(uint8_t *)0xB580;
  uint8_t cond2 = *(uint8_t *)0xBB25;
  uint8_t knock_counter = *(uint8_t *)0xBC75;
  uint8_t threshold = *(uint8_t *)0x78544;
  uint32_t *map_ptr = NULL;
  if (cond1 == 1) {
    if (knock_counter >= threshold) {
      map_ptr = (uint32_t *)0x693CC;  // map1
    }
  } else if (cond1 == 0) {
    if (cond2 <= threshold && cond2 != 0) {
      map_ptr = (uint32_t *)0x693B8;  // map2
    }
  }
  float limit = twoD_lookup(rpm, map_ptr);
  float min_val = *(float *)0xFFFFBC50;
  float max_val = *(float *)0x78584;
  return saturate(limit, min_val, max_val);
}
```
**Status:** med ; General flow is clear: conditional table selection → 2D lookup → saturation ; Exact conditional logic for map selection has ambiguities (nested if/else structure) ; RPM threshold vs knock counter comparison logic unclear without calibration data
