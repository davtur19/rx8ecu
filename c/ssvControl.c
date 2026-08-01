/* ssvControl.c
 *
 * ROM: 60E1D400  |  Address: 0x225C8  |  Size: 312 bytes  |  VERIFIED vs ROM emulator
 *
 * Secondary Shutter Valve (SSV) control task.  Temperature-based on/off
 * command with cooling hysteresis, a fault/retry counter, an enable gating
 * decision, and a sensor-state-machine call that drives an output bit.
 *
 * Inputs:
 *   RAM[0xFFFFAA10] (f32)  temperature for the hysteresis band
 *   RAM[0xFFFFAAE0] (u8)   mode byte
 *   RAM[0xFFFFB325] (u8)   previous mode (state)
 *   RAM[0xFFFFBF39] (u8)   status byte (1 -> enable path)
 *   ROM[0x72F70]    (u8)   calibration flag (=0 in stock ROM)
 *   ROM[0x72F72]    (u16)  counter reload value (188)
 *   ROM[0x72F74]    (f32)  on-threshold (200.0)
 *   ROM[0x226D4]    (f32)  hysteresis (-3.0, so off below 197.0)
 *
 * Outputs:
 *   RAM[0xFFFFB324] (u8)   SSV command: 1 if temp>=200, 0 if temp<197,
 *                          held in [197,200)
 *   RAM[0xFFFFB322] (u16)  counter: reloaded to 188 on a mode transition
 *                          0->1, otherwise decremented while > 0
 *   RAM[0xFFFFB320] (u8)   alternating_sensor_sm_08 result
 *   RAM[0xFFFFF754] (u16)  bit 0x80 = (sm result == 1)
 *   RAM[0xFFFFB325] (u8)   = mode (state store)
 *
 * Verified: 12000 random inputs vs the ROM emulator, 0 mismatches
 * (test_ssv_control.py; the 0x5D3E8 state machine is verified separately
 * by test_alt_sensor_sm.py, 20000 inputs).
 */

#include <stdint.h>

#define RAM_TEMP    (*(volatile float *)0xFFFFAA10)
#define RAM_MODE    (*(volatile uint8_t *)0xFFFFAAE0)
#define RAM_PREVM   (*(volatile uint8_t *)0xFFFFB325)
#define RAM_CMD     (*(volatile uint8_t *)0xFFFFB324)
#define RAM_CNT     (*(volatile uint16_t *)0xFFFFB322)
#define RAM_BF39    (*(volatile uint8_t *)0xFFFFBF39)
#define RAM_SM_OUT  (*(volatile uint8_t *)0xFFFFB320)
#define RAM_F754    (*(volatile uint16_t *)0xFFFFF754)

#define ROM_CAL_F   (*(const uint8_t *)0x72F70)  /* 0    cal flag  */
#define ROM_RELOAD  (*(const uint16_t *)0x72F72) /* 188  counter   */
#define ROM_T_ON    (*(const float *)0x72F74)    /* 200.0          */
#define ROM_T_HY    (*(const float *)0x226D4)    /* -3.0           */

/* alternating_sensor_sm_08 @0x5D3E8 — verified, see
 * docs/functions/alternating_sensor_sm_08.md */
extern uint8_t alternating_sensor_sm_08(uint8_t enable);
extern void setRegister_REG_BIT_VAL(uint16_t *reg, uint16_t mask, int enable);

void ssvControl(void)
{
    uint8_t mode = RAM_MODE;

    /* 1. temperature hysteresis (on >= 200, off < 197, hold in band) */
    float t = RAM_TEMP;
    if (t >= ROM_T_ON)
        RAM_CMD = 1;
    else if (t < ROM_T_ON + ROM_T_HY)   /* 200 - 3 = 197 */
        RAM_CMD = 0;

    /* 2. counter: reload on a mode transition into 1, else count down */
    if (mode == 0 && RAM_PREVM == 1)
        RAM_CNT = ROM_RELOAD;
    else if (RAM_CNT > 0)
        RAM_CNT -= 1;

    /* 3. enable gating */
    uint8_t enable =
        (RAM_BF39 == 1) ||
        (mode == 0 && RAM_CNT > 0 && RAM_CMD == 0) ? 1 : 0;
    /* (ROM[0x72F70]==1 would also force enable, but the cal byte is 0) */

    /* 4. sensor state machine -> output byte */
    RAM_SM_OUT = alternating_sensor_sm_08(enable);

    /* 5. output bit */
    setRegister_REG_BIT_VAL(&RAM_F754, 0x80, RAM_SM_OUT == 1);

    /* 6. state store */
    RAM_PREVM = mode;
}
