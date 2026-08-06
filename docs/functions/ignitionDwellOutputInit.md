# ignitionDwellOutputInit @ 0x8F2A
**Purpose:** Initialize all four ignition coil dwell outputs; loop through 4 coils, computing dwell and writing to hardware state/control registers.
**Inputs:** None (uses calibration tables from ROM and hardware globals)
**Out:** Initializes 4 ignition dwell state blocks at 0xFFFFA0C4 (4 x 4-byte slots) ; Initializes 4 ignition dwell state blocks at 0xFFFFA0D8 (4 x 8-byte slots) ; Calls FUN_0000A8A4 four times with calibration data for each coil ; Sub-function at 0x8F94: unknown setup (likely hardware init or enable)
**Calls:** sub-function @ 0x8F94: called once at start (global ignition init) ; FUN_0000A8A4 @ 0xA8A4: called 4x per loop, once per coil (fire/setup)
Call sub-function at 0x8F94 (global ignition setup) ; Initialize loop counter r14 = 0, loop max r9 = 4 ; Load base pointers: ; r11 = 0xFFFFA0C4 (dwell state array 1) ; r12 = 0x0000D81C (coil config
table, 24 bytes per coil) ; r13 = 0xFFFFA0D8 (dwell state array 2) ; r8 = 0xA8A4 (fire_coil function) ; Loop for coil 0-3: ; Load coil config from 0xD81C + (coil_id * 24) ; Call fire_coil(config[0])
with r5=0 parameter ; Write 0 to state1[coil_id] (offset at r11, advance r11 by 4 per iteration) ; Write 0 to state2[coil_id*2+4] and state2[coil_id*2+5] (offset at r13, advance r13 by 8 per
iteration) ; Advance coil config pointer by 24 bytes per iteration ; Return
**Draft C:**
```c
void ignitionDwellOutputInit(void) {
    volatile uint32_t *dwell_state1 = (volatile uint32_t *)0xFFFFA0C4;
    volatile uint8_t *dwell_state2 = (volatile uint8_t *)0xFFFFA0D8;
    volatile struct {
        uint32_t coil_data;
        // ... additional fields
    } *coil_config = (volatile void *)0x0000D81C;
    init_global_ignition();  // call 0x8F94
    for (int coil_id = 0; coil_id < 4; coil_id++) {
        fire_coil(coil_config->coil_data, 0);  // call 0xA8A4 with r5=0
        dwell_state1[coil_id] = 0;
        dwell_state2[coil_id * 8 + 4] = 0;
        dwell_state2[coil_id * 8 + 5] = 0;
        coil_config = (volatile void *)((uintptr_t)coil_config + 24);
    }
}
```
**Status:** med — loop and memory layout clear; 0x8F94 and fire_coil(r5=0) semantics unclear.
**Uncertainties:** What 0x8F94 does (timer enable / interrupt config / defaults)? Why fire_coil called with r5=0 during init? Why two state arrays? Coil mapping (lead/trail pairs vs 4 plugs)? coil_data format?
