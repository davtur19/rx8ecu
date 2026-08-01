# outputSpark1 @ 0x8DAE
_source: AI (Haiku) draft, unverified_

**Purpose:** Program a hardware output-compare channel to fire a spark coil at a calculated ignition dwell time (for one of the two leading-spark plugs in the rotary engine).

**Inputs:** 
- `r4` (byte): spark plug index (0–7, one per output-compare channel)
- `fr4` (float): spark dwell time / ignition delay (in hardware timer units)
- Calls `getSR()` to read current system status register (likely to lock/unlock interrupt or test state)

**Outputs / side effects:**
- Writes float dwell value to hardware register at `0xFFFFA0D8 + (spark_index * 8)` (output-compare channel control register, offset +0)
- Writes control byte 2 to offset +4 of the same structure (likely output-compare mode/pin control)
- Writes control byte 0 to offset +5 of the same structure (likely disable flag or secondary mode)
- Calls `setSR()` to restore system status register (re-enable interrupts or previous state)
- Calls unknown subroutine at `0x91C6` with spark index and dwell time (likely confirms coil firing or updates ECU state machine)

**Calls:**
1. `getSR()` @ 0x3920 (with r4=16): read current SR; stores result in stack for later restoration
2. Unknown @ 0x91C6 (with r4=spark_index): confirms coil actuation or logs spark event
3. `setSR()` @ 0x3934: restore SR from saved value

**Behavior:**
1. Save current interrupt state (SR register) via `getSR()`
2. Index into per-channel spark configuration array at 0xFFFFA0D8 using spark index (multiply by 8)
3. Write the dwell time (ignition delay) to the output-compare channel's timer register
4. Write control flags (enable output, set pin drive mode)
5. Notify ECU state machine via unknown handler (may arm the coil driver)
6. Restore interrupt state via `setSR()`
7. Return

**Draft C:**
```c
void outputSpark1(uint8_t spark_index, float dwell_time) {
    uint32_t saved_sr = getSR();
    
    // Index into spark channel array (0xFFFFA0D8 is base address of per-channel registers)
    uint8_t *channel_base = (uint8_t *)(0xFFFFA0D8 + (spark_index * 8));
    
    // Write dwell time to output-compare channel
    *(float *)channel_base = dwell_time;
    
    // Set output-compare pin mode (offset +4, value=2)
    channel_base[4] = 2;
    
    // Disable or reset secondary flag (offset +5, value=0)
    channel_base[5] = 0;
    
    // Notify coil driver state machine
    unknown_coil_handler(spark_index, dwell_time);  // @ 0x91C6
    
    // Restore interrupt state
    setSR(saved_sr);
}
```

**Confidence:** med
- Confident in overall structure (timer/output-compare setup with side effects)
- Confident the address 0xFFFFA0D8 is a hardware register base (RAM region, not ROM)
- Uncertain of exact peripheral (MTU = multi-timer unit, or DMAC = DMA controller, or custom Denso spark driver)
- Uncertain of control byte meanings (offsets +4, +5) without datasheet
- Uncertain of the unknown subroutine at 0x91C6 (likely confirmation/state-machine update, not critical to core behavior)
- No floating-point FPU context validation visible (assumes fr4 is valid)
