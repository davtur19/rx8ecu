/* vfad_control_35BBC.c
 *
 * ROM: 60E1D400  |  Address: 0x35BBC  |  Size: 312 bytes  |  VERIFIED vs ROM emulator
 *
 * Variable Fresh Air Duct (VFAD) control task driving the 0x0400 output bit.
 * Boost-pressure hysteresis
 * command with hold-in-band, fed through the alternating sensor state
 * machine (0x5D800), whose result is stored and mirrored onto an output
 * bit in register 0xFFFFF754.
 *
 * Inputs:
 *   RAM[0xFFFFB5B8] (f32)  boost pressure
 *   RAM[0xFFFFC234] (u8)   previous command (state, used in the hold band)
 *   ROM[0x7A5AC]    (f32)  on-threshold (5250.0)
 *   ROM[0x7A5B0]    (f32)  hysteresis width (188.0 -> off below 5062.0)
 *
 * Outputs:
 *   RAM[0xFFFFC234] (u8)   launch status bit 0x0400 command: 1 if boost>=5250, 0 if boost<5062,
 *                          held in [5062, 5250)
 *   RAM[0xFFFFF754] (u16)  bit 0x0400 = (sm result == 1)
 *   (plus the 0x5D800 state machine side effects, see
 *    docs/functions/alternating_sensor_sm_5D800.md)
 *
 * Note on fcmp/gt operand order: the SH-2E emulator evaluates
 * `fcmp/gt FRn,FRm` as FRn > FRm, so `fcmp/gt boost,5250` is 5250 > boost.
 * The C lift below expresses the resulting hysteresis directly.
 *
 * Verified: 10000 random inputs vs the ROM emulator, 0 mismatches
 * (test_vfad_control_35BBC.py; the 0x5D800 state machine is verified separately
 * by test_alt_sensor_sm_5D800.py, 20000 inputs).
 */

#include <stdint.h>

#define RAM_BOOST   (*(volatile float *)0xFFFFB5B8)
#define RAM_CMD     (*(volatile uint8_t *)0xFFFFC234)
#define RAM_F754    (*(volatile uint16_t *)0xFFFFF754)

#define ROM_ON      (*(const float *)0x7A5AC)  /* 5250.0 */
#define ROM_HYST    (*(const float *)0x7A5B0)  /* 188.0  */

/* alternating_sensor_sm @0x5D800 — verified, see
 * docs/functions/alternating_sensor_sm_5D800.md */
extern uint8_t alternating_sensor_sm_5D800(uint8_t enable);
extern void setRegister_REG_BIT_VAL(uint16_t *reg, uint16_t mask, int enable);

void vfad_control_35BBC(void)
{
    float x = RAM_BOOST;
    uint8_t cmd;

    /* hysteresis: on >= 5250, off < 5062, hold old command in between */
    if (x >= ROM_ON)
        cmd = 1;
    else if (x < ROM_ON - ROM_HYST)   /* 5250 - 188 = 5062 */
        cmd = 0;
    else
        cmd = RAM_CMD;

    uint8_t out = alternating_sensor_sm_5D800(cmd);
    RAM_CMD = out;
    setRegister_REG_BIT_VAL(&RAM_F754, 0x0400, out == 1);
}
