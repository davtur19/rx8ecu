# getEngineOnTimeForOilMetering @ 0xE1FE

_source: AI (Haiku) draft, unverified_

**Purpose:** Checks engine running state and conditionally increments cumulative engine on-time counter for oil metering pump duty cycle calculation.

**Inputs:** 
- @0xA428: engine_running flag (1=running, 0=off)
- @0xA422: cumulative_on_time_counter (16-bit)

**Outputs / side effects:** 
- Increments on-time counter if engine is running
- Writes updated counter back to @0xA422

**Calls:** 
- 0x00002460 (add16bitSaturate_ADD1_ADD2): adds two 16-bit values with saturation (overflow caps at 0xFFFF)

**Behavior:** 
1. Check engine_running flag @ 0xA428
2. If engine NOT running (byte == 0): skip to return
3. If engine running:
   - Load counter @ 0xA422 into r4
   - Call add16bitSaturate_ADD1_ADD2(counter, 1) with r5=1
   - Result in r0
   - Store incremented counter back to @0xA422
4. Return

**Draft C:** 
```c
void getEngineOnTimeForOilMetering(void) {
    uint8_t *engine_running_flag = (uint8_t *)0xA428;
    uint16_t *on_time_counter = (uint16_t *)0xA422;
    
    if (*engine_running_flag == 1) {
        uint16_t current = *on_time_counter;
        uint16_t incremented = add16bitSaturate(current, 1);
        *on_time_counter = incremented;
    }
}
```

**Confidence:** high — function is straightforward conditional accumulator. Name suggests oil metering application (2-stroke-style lubrication for rotary apex seals).

**Uncertainties:** 
- Is this called once per engine cycle or once per timer tick?
- What is the time basis? (tick interval determines resolution)
- When/why does counter reset (assumes implicit elsewhere)?
