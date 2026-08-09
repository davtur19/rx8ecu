# debounceCalculatedGear @ 0x2CB6A
**Purpose:** Debounce the calculated transmission gear (1–6) with hysteresis; output a single stable gear value.
**Inputs:** Gear state from RAM 0xBC74 (uint8_t, raw gear reading) ; Gear mode indicator from RAM 0xB586 (uint8_t) ; 6 debounce threshold pairs (one per gear) at 0xBC82-0xBC8C (thresholds loaded from ROM at 0x754D2, 0x754D4, 0x754D6, 0x754D8, 0x754DA, 0x754DC)
**Out:** Updates the debounced gear output at RAM 0xBC75 (uint8_t) ; Updates 6 internal accumulator/threshold states at 0xBC82–0xBC8C
**Calls:** add16bitSaturate_ADD1_ADD2 @ 0x2460 (hysteresis counter increment with saturation)
Load the current gear value from 0xBC74. Check if the gear mode == 1 (clutch in), else skip to step 9. For each of 6 gears (1–6): compare the raw gear value against the upper threshold (loaded from ROM at 0x754D2
+ offset). If it is above the threshold AND the counter meets the criteria, update the debounced gear output. Otherwise keep the counter. For each gear again: call add16bitSaturate to update the accumulator at
0xBC82-0xBC8C. Increment with saturation (prevents rollover). Return the updated gear state.
**Draft C:**
```c
void debounceCalculatedGear(void) {
    uint8_t raw_gear = *(uint8_t*)0xBC74;
    uint8_t gear_mode = *(uint8_t*)0xB586;
    if (gear_mode != 1) {
        *(uint8_t*)0xBC75 = 0;
        return;
    }
    uint8_t final_gear = 0;
    // Compare raw_gear to thresholds for gears 1-6
    if (raw_gear >= GEAR1_THRESHOLD && counter1 > DEBOUNCE_COUNT) final_gear = 1;
    else if (raw_gear >= GEAR2_THRESHOLD && counter2 > DEBOUNCE_COUNT) final_gear = 2;
    // ... etc for gears 3-6
    *(uint8_t*)0xBC75 = final_gear;
    // Update accumulators
    for (int i = 0; i < 6; i++) {
        accum[i] = add16bitSaturate(accum[i], 1);
    }
}
```
**Status:** med — the debouncing logic is clear (hysteresis counters visible); the exact threshold values and debounce timing are not verified; the ROM offsets are inferred.
**Uncertainties:** Exact threshold values (likely stored in the ROM table) ; Debounce count threshold (value that triggers gear accept) ; Whether the accumulator increment is per-frame or conditional ; Behavior when gear_mode != 1 (likely outputs 0)
