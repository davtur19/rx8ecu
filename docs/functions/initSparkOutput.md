# initSparkOutput @ 0x8D86
**Purpose:** Initialize ignition output for one spark plug: load dwell angle and set hardware timer register.
**Inputs:** r4: dwell angle (float, single-precision FPU, in degrees)
**Out:** Writes dwell time (float) to spark state at 0xFFFFA0D8 + (spark_id * 16) ; Writes control flags to offset +4 and +5 ; Returns r0 = 1 (completion status)
**Calls:** None
Load FPU constant 30.0 from ROM (0x8E78) ; Compute adjusted_dwell = r4 - 30.0 ; If adjusted_dwell <= 0.0: add 720.0 (full two-rotor cycle) to wrap angle ; Compute spark_id from r4 (extract byte, scale
by 16) ; Write adjusted_dwell to register block 0xFFFFA0D8 + (spark_id * 16) ; Clear control flag at offset +5 (byte) ; Set control flag at offset +4 to 1 (byte) ; Return r0 = 1
**Draft C:**
```c
int32_t initSparkOutput(float dwell_angle) {
    volatile float *spark_base = (volatile float *)0xFFFFA0D8;
    float adj_dwell = dwell_angle - 30.0f;
    if (adj_dwell <= 0.0f) {
        adj_dwell += 720.0f;  // two rotor revolutions
    }
    uint8_t spark_id = (uint8_t)dwell_angle & 0xFF;
    volatile struct {
        float dwell;
        uint32_t reserved;
        uint8_t control;
        uint8_t enable;
    } *spark = (volatile void *)(spark_base + spark_id * 4);
    spark->dwell = adj_dwell;
    spark->enable = 0;
    spark->control = 1;
    return 1;
}
```
**Status:** med — FPU operations and angle wrapping are clear; exact control flag semantics and spark_id extraction need verification.
**Uncertainties:** What does the 30.0 offset represent (crank angle before TDC?) ; Why wrapping is 720 degrees (full two-rotor cycle for 13B Renesis) ; Exact spark_id extraction: is it truly just the low byte of dwell angle? ; What control/enable flags mean; whether 1 = armed/active or 0 = disabled
