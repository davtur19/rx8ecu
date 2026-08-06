# vfad_control_35BBC @ 0x35BBC
**Purpose:** Stock **V**ariable **F**resh **A**ir **D**uct (VFAD) solenoid control. Boost-pressure ; hysteresis command with hold-in-band, fed through the alternating-sensor state machine ; (0x5D800), whose result is stored in RAM and mirrored onto bit 0x0400 of hardware register ; 0xFFFFF754.
**ROM:** 60E1D400.bin, 0x35BBC, size 312 bytes.
**Inputs:** RAM[0xFFFFB5B8] (f32) boost pressure ; RAM[0xFFFFC234] (u8) previous command (state, used in the hold band) ; ROM[0x7A5AC] (f32) on-threshold (5250.0) ; ROM[0x7A5B0] (f32) hysteresis width (188.0 → off below 5062.0)
**Out:** RAM[0xFFFFC234] (u8) VFAD command: 1 if boost ≥ 5250, 0 if boost < 5062, held in [5062, 5250) ; RAM[0xFFFFF754] (u16) bit 0x0400 = (state-machine result == 1) ; plus the 0x5D800 state-machine side effects (see `docs/functions/alternating_sensor_sm_5D800.md`)
**Calls:** `alternating_sensor_sm_5D800` (0x5D800) — verified alternating-sensor debounce ; `setRegister_REG_BIT_VAL` (0x4BBC) — sets/clears F754 bit 0x0400
**Behavior:**

```
cmd = 1                 if boost >= 5250.0
cmd = 0                 if boost <  5062.0   (= 5250 - 188)
cmd = RAM[0xFFFFC234]   else (hold in band)
out = alternating_sensor_sm_5D800(cmd)
RAM[0xFFFFC234] = out
setRegister_REG_BIT_VAL(&0xFFFFF754, 0x0400, out == 1)
```

**Draft C:**
```c
#include <stdint.h>
uint8_t vfad_control_35BBC(void)
{
    float x = *(volatile float *)0xFFFFB5B8;   /* boost pressure */
    uint8_t cmd;
    if (x >= 5250.0f)
        cmd = 1;
    else if (x < 5250.0f - 188.0f)             /* 5062.0 */
        cmd = 0;
    else
        cmd = *(volatile uint8_t *)0xFFFFC234; /* hold in band */
    uint8_t out = alternating_sensor_sm_5D800(cmd);
    *(volatile uint8_t *)0xFFFFC234 = out;
    setRegister_REG_BIT_VAL((uint16_t *)0xFFFFF754, 0x0400, out == 1);
    return out;
}
```
**Status:** high — verified against the ROM emulator (10000 random inputs, 0 mismatches); the 0x5D800 state machine is verified separately.
Note on fcmp/gt order: the emulator evaluates `fcmp/gt FRn,FRm` as `FRn > FRm`, so the ROM's `fcmp/gt boost,5250` means `5250 > boost` (threshold vs signal); the C lift expresses the hysteresis directly.
> **Note on the old name:** this function was briefly mislabeled
> `launch_status_bit0400` during the mod era. It is the **stock VFAD solenoid
> control** (reads the VFAD open-threshold + hysteresis cal, sets F754 bit 0x0400);
> stock firmware has **no launch control**. A tuned launch-control mod
> repurposes F754 bit 0x0400 as its "launch active" flag, read by
> `CAN_EmitLaunchStatus` (0x57BE8). See `docs/notes/FINDINGS.md`.
