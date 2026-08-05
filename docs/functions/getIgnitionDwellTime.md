# getIgnitionDwellTime @ 0x9490
**Purpose:** Look up ignition dwell time from 3D table based on engine conditions, add offset, clamp to max value.
**Inputs:** r4 (implicit): RPM or similar parameter for 3D lookup ; r5 (implicit): second parameter for 3D lookup ; RAM 0xFFFF9F68: RPM or main condition (fr5) ; RAM 0xFFFF9F80: second condition or offset (fr4)
**Out:** RAM 0xFFFFA0D4: final dwell time as u16, clamped to 0xFFFF ; Sets 0xFFFFA0D6 as intermediate (may be offset value) ; return r0: u16 result (return value via r0, then extu.w to zero-extend)
**Calls:** 0x0000213C (ThreeDLookup_FP_16bit): takes r4=table_address(0x00069F30), fr5=RPM, fr4=second_param → returns r0 (u16 lookup result)
Push return address (pr) to stack (sts.l pr,@-r15) ; Load fr5 from RAM 0xFFFF9F68 (RPM/condition1) ; Load fr4 from RAM 0xFFFF9F80 (offset/condition2) ; Call ThreeDLookup_FP_16bit with table at
0x00069F30 ; Zero-extend lookup result (u16) to r0 ; Move r0 to r4 (prepare for addition) ; Load u16 offset from RAM 0xFFFFA0D6 ; Add offset to lookup result: r4 = r0 + offset_value ; Load max dwell =
0xFFFF into r6 ; If r4 > 0xFFFF (hi), clamp to 0xFFFF; else store r4 ; Store clamped result to RAM 0xFFFFA0D4 ; Restore return address and return
**Draft C:**
```c
uint16_t dwell_table_lookup_addr = 0x00069F30;  // 3D table
float rpm_value;                // @ 0xFFFF9F68
float condition2_value;         // @ 0xFFFF9F80
uint16_t dwell_offset;          // @ 0xFFFFA0D6
uint16_t final_dwell_time;      // @ 0xFFFFA0D4
uint16_t getIgnitionDwellTime() {
    // Call 3D lookup: table at 0x00069F30, params rpm_value and condition2_value
    uint16_t lookup_result = ThreeDLookup_FP_16bit(dwell_table_lookup_addr, rpm_value, condition2_value);
    // Add offset
    uint32_t dwell_with_offset = (uint32_t)lookup_result + (uint32_t)dwell_offset;
    // Clamp to max 0xFFFF
    if (dwell_with_offset > 0xFFFF) {
        final_dwell_time = 0xFFFF;
    } else {
        final_dwell_time = (uint16_t)dwell_with_offset;
    }
    return final_dwell_time;
}
```
**Status:** med ; 3D lookup + offset + clamping pattern is standard ; Table address and max value are clear ; Unknown: exact meaning of lookup parameters; whether offset comes from EEPROM or calculation
