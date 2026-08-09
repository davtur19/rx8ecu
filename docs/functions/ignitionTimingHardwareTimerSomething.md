# ignitionTimingHardwareTimerSomething @ 0x8E28
**Purpose:** Configure timer output-compare register for ignition timing; validate timing ready and fire coil if armed.
**Inputs:** r4: spark_id (0–1, selects the spark plug) ; Globals: 0xFFFFA0D8 (spark state), 0x0000D81C (ignition calibration/config table)
**Out:** Writes timing value to hardware output-compare register ; Clears control flags at offset +4 and +5 ; Calls FUN_0000A8A4 (likely coil fire or interrupt handler setup) ; Restores processor status register (interrupt mask)
**Calls:** getSR @ 0x3920: read current status register ; FUN_0000A8A4 @ 0xA8A4: unknown utility, likely hardware register write or coil fire ; setSR @ 0x3934: restore status register
Read status register (disable further context switches) ; Compute spark state offset: 0xFFFFA0D8 + (spark_id * 16) ; Check if control flag at offset +5 is nonzero: ; If not set (==0): skip to end,
clear flags, return ; If set (!=0): proceed with ignition timing setup ; Load ignition config from 0xD81C + (spark_id * 24): ; Read calibration values at offset +12 (hardware reg ptr) and +4 (timing
value) ; Compute timing window: ; current_timer = read calibration[+12] (hardware register) ; expected_time = read calibration[+4] ; delta = expected_time - current_timer ; Check delta >= 0 (timing
not passed): ; If delta < 0: skip fire, clear flags, return ; Read enable bits from calibration[+16] and calibration[+20] (hardware regs): ; Test if enable bits are valid (AND the values) ; If invalid
(zero): skip fire, clear flags, return ; Call FUN_0000A8A4 with the parameter calibration[0] (fire coil or setup timer) ; Clear control flags at offset +4 and +5 ; Restore status register (re-enable
interrupts)
**Draft C:**
```c
void ignitionTimingHardwareTimerSomething(uint8_t spark_id) {
    volatile struct {
        float timing;
        uint32_t reserved;
        uint8_t control;      // offset +4
        uint8_t enable_flag;  // offset +5
        uint8_t fire_req;     // offset +6
    } *spark = (volatile void *)(0xFFFFA0D8 + (spark_id & 0xFF) * 16);
    uint32_t sr = getSR();
    if (!spark->enable_flag) {
        spark->control = 0;
        spark->enable_flag = 0;
        setSR(sr);
        return;
    }
    volatile struct {
        uint32_t coil_data;
        uint16_t *timing_reg;
        uint16_t timing_value;
        uint32_t pad1;
        uint16_t *enable_reg1;
        uint16_t *enable_reg2;
        uint32_t pad2;
    } *config = (volatile void *)(0xD81C + spark_id * 24);
    uint16_t current_timer = *config->timing_reg;
    uint16_t expected_time = config->timing_value;
    int32_t delta = expected_time - current_timer;
    if (delta < 0) {
        setSR(sr);
        return;
    }
    uint16_t en_bits1 = *config->enable_reg1;
    uint16_t en_bits2 = *config->enable_reg2;
    if (!(en_bits1 & en_bits2)) {
        setSR(sr);
        return;
    }
    fire_coil(config->coil_data);  // call 0xA8A4
    spark->control = 0;
    spark->enable_flag = 0;
    setSR(sr);
}
```
**Status:** med-low — flow clear; enable-bits, timing semantics, coil_fire params need verification.
**Uncertainties:** Whether delta < 0 means "timing has passed" or "not yet ready" ; What enable_reg1/enable_reg2 bits represent (channel enables? interrupt masks?) ; Whether coil_data is a coil ID or hardware register value ; Exact semantics of the fire_coil function at 0xA8A4 ; Whether timing_value is crank angle or raw timer count
