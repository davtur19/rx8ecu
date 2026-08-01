# ignitionTimingHardwareTimerSomething @ 0x8E28
_source: AI (Haiku) draft, unverified_

**Purpose:** Configure hardware timer output-compare register for ignition timing; validate timing is ready and fire ignition coil if armed.

**Inputs:**
- r4: spark_id (0–1, selects which spark plug)
- Globals: 0xFFFFA0D8 (spark state), 0x0000D81C (ignition calibration/config table)

**Outputs / side effects:**
- Writes timing value to hardware output-compare register
- Clears control flags at offset +4 and +5
- Calls FUN_0000A8A4 (likely coil fire or interrupt handler setup)
- Restores processor status register (interrupt mask)

**Calls:**
- getSR @ 0x3920: read current status register
- FUN_0000A8A4 @ 0xA8A4: unknown utility, likely hardware register write or coil fire
- setSR @ 0x3934: restore status register

**Behavior:**
1. Read status register (disable further context switches)
2. Compute spark state offset: 0xFFFFA0D8 + (spark_id * 16)
3. Check if control flag at offset +5 is nonzero:
   - If not set (==0): skip to end, clear flags, return
   - If set (!=0): proceed with ignition timing setup
4. Load ignition config from 0xD81C + (spark_id * 24):
   - Read calibration values at offset +12 (hardware reg ptr) and +4 (timing value)
5. Compute timing window:
   - current_timer = read calibration[+12] (hardware register)
   - expected_time = read calibration[+4]
   - delta = expected_time - current_timer
6. Check delta >= 0 (timing not passed):
   - If delta < 0: skip fire, clear flags, return
7. Read enable bits from calibration[+16] and calibration[+20] (hardware regs):
   - Test if enable bits are valid (AND the values)
   - If invalid (zero): skip fire, clear flags, return
8. Call FUN_0000A8A4 with calibration[0] as parameter (fire coil or setup timer)
9. Clear control flags at offset +4 and +5
10. Restore status register (re-enable interrupts)

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

**Confidence:** med-low — overall flow is clear, but exact interpretation of enable_bits, timing semantics, and coil_fire parameters need verification.

**Uncertainties:**
- Whether delta < 0 means "timing has passed" or "not yet ready"
- What enable_reg1/enable_reg2 bits represent (channel enables? interrupt masks?)
- Whether coil_data is a coil ID or hardware register value
- Exact semantics of the fire_coil function at 0xA8A4
- Whether timing_value is crank angle or raw timer count
