# debounceCalculatedGear @ 0x2CB6A

_source: AI (Haiku) draft, unverified_

**Purpose:** Debounce calculated transmission gear (1–6) with hysteresis; output single stable gear value.

**Inputs:** 
- Gear state from RAM 0xBC74 (uint8_t, raw gear reading)
- Gear mode indicator from RAM 0xB586 (uint8_t)
- 6 debounce threshold pairs (one per gear) at 0xBC82-0xBC8C (thresholds loaded from ROM at 0x754D2, 0x754D4, 0x754D6, 0x754D8, 0x754DA, 0x754DC)

**Outputs / side effects:** 
- Updates debounced gear output at RAM 0xBC75 (uint8_t)
- Updates 6 internal accumulator/threshold states at 0xBC82–0xBC8C

**Calls:** 
- add16bitSaturate_ADD1_ADD2 @ 0x2460 (hysteresis counter increment with saturation)

**Behavior:**
1. Load current gear value from 0xBC74
2. Check if gear mode == 1 (clutch in), else skip to step 9
3. For each of 6 gears (1–6):
   - Compare raw gear value against upper threshold (loaded from ROM at 0x754D2 + offset)
   - If above threshold AND counter meets criteria, update debounced gear output
   - Otherwise keep counter
4. For each gear again:
   - Update accumulator at 0xBC82-0xBC8C by calling add16bitSaturate
   - Increment with saturation (prevents rollover)
5. Return updated gear state

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

**Confidence:** med — debouncing logic is clear (hysteresis counters visible); exact threshold values and debounce timing not verified; ROM offsets inferred.

**Uncertainties:**
- Exact threshold values (likely stored in ROM table)
- Debounce count threshold (value that triggers gear accept)
- Whether accumulator increment is per-frame or conditional
- Behavior when gear_mode != 1 (likely outputs 0)
