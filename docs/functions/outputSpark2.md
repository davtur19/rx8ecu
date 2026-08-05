# outputSpark2 @ 0x8DE8
**Purpose:** Fire the second spark plug (trailing spark on rotor); manage timing and hardware control flags.
**Inputs:** r4: spark_id (0–1, for spark plug selection) ; fr4: spark timing angle (float, single-precision) ; Globals: 0xFFFFA0D8 (spark state block), getSR/setSR functions
**Out:** Writes timing angle to hardware register at 0xFFFFA0D8 + (spark_id * 16) ; Clears control flag at offset +6 ; Calls helper function at 0x91C6 (likely fire spark coil) ; Restores processor status register (interrupt mask)
**Calls:** getSR @ 0x3920: read current status register ; sub-function at 0x91C6: fire trailing spark (unknown details) ; setSR @ 0x3934: restore status register
Save link register (for local call at 0x91C6) ; Read status register (r0 = getSR()) ; Build local stack frame: save spark_id, timing angle (fr4) ; Extract spark_id from r4 (low byte, scale by 16) ;
Compute spark state offset: 0xFFFFA0D8 + (spark_id * 16) ; Check control flag at offset +4: if == 2, write timing angle to register at offset 0 ; Clear control flag at offset +6 ; Call sub-function at
0x91C6 with spark_id to fire the spark ; Restore status register to re-enable interrupts ; Return
**Draft C:**
```c
void outputSpark2(uint8_t spark_id, float timing_angle) {
    volatile struct {
        float timing;
        uint32_t reserved;
        uint8_t control;      // offset +4
        uint8_t unknown;      // offset +5
        uint8_t fire_flag;    // offset +6
    } *spark_state = (volatile void *)(0xFFFFA0D8 + (spark_id & 0xFF) * 16);
    uint32_t sr = getSR();
    if (spark_state->control == 2) {
        spark_state->timing = timing_angle;
    }
    spark_state->fire_flag = 0;
    fire_spark_trailing(spark_id);  // call 0x91C6
    setSR(sr);  // restore interrupts
}
```
**Status:** med — control flow is clear; exact hardware semantics for the fire_spark_trailing call and control flag values need verification.
**Uncertainties:** What does control == 2 mean (armed? ready to fire?) ; What is the purpose of fire_flag at offset +6 (completion status? error flag?) ; Details of sub-function at 0x91C6 (coil charge/discharge? PWM pulse?) ; Whether timing_angle is crank angle or timer counter
