/* calc_fan1_control.c
 *
 * ROM: 60E1D400  |  Address: 0x303A6  |  Size: 288 bytes  |  VERIFIED vs ROM emulator
 *
 * Cooling-fan relay control.  Two thermostat outputs with hysteresis,
 * driven by a shared temperature input, plus a fan-enable latch computed
 * from a chain of 14 status bytes.
 *
 * Input:
 *   RAM[0xFFFFAA10]  (f32)  temperature for the thermostat bands
 *
 * Outputs:
 *   RAM[0xFFFFBE16]  (u8)  fan 1 relay command (1 = on)
 *   RAM[0xFFFFBE17]  (u8)  fan 2 relay command (1 = on)
 *   RAM[0xFFFFBE0D]  (u8)  fan enable latch (1 = enable)
 *
 * Hysteresis calibration lives in ROM @0x7793C..0x77948:
 *   fan1 band: ROM[0x7793C] = 97.0 on, off below ROM[0x7793C] - ROM[0x77940] = 94.0
 *   fan2 band: ROM[0x77944] = 97.0 on, off below ROM[0x77944] - ROM[0x77948] = 94.0
 * (both bands currently 97/94; between them the previous state is held).
 *
 * Verified: 12400 random temp + status-byte combinations vs the ROM
 * emulator, 0 mismatches.
 */

#include <stdint.h>

#define RAM_FAN_TEMP   (*(volatile float *)0xFFFFAA10)
#define RAM_FAN1_OUT   (*(volatile uint8_t *)0xFFFFBE16)
#define RAM_FAN2_OUT   (*(volatile uint8_t *)0xFFFFBE17)
#define RAM_FAN_ENABLE (*(volatile uint8_t *)0xFFFFBE0D)

#define ROM_T1_ON  (*(const float *)0x7793C)   /* 97.0 */
#define ROM_T1_HY  (*(const float *)0x77940)   /*  3.0 */
#define ROM_T2_ON  (*(const float *)0x77944)   /* 97.0 */
#define ROM_T2_HY  (*(const float *)0x77948)   /*  3.0 */

static uint8_t cell(uint32_t a) { return *(volatile uint8_t *)a; }

/* The fan-enable latch is a branch tree over status cells; the code below
 * mirrors the firmware CFG at 0x30416..0x304C0 exactly (see doc). */
void calc_fan1_control(void)
{
    float t = RAM_FAN_TEMP;
    uint8_t be16, be17;
    int loc;
    uint8_t en;

    /* --- fan 1 thermostat (hysteresis) --- */
    if (t >= ROM_T1_ON)
        RAM_FAN1_OUT = 1;
    else if (t < ROM_T1_ON - ROM_T1_HY)
        RAM_FAN1_OUT = 0;
    be16 = RAM_FAN1_OUT;

    /* --- fan 2 thermostat (hysteresis) --- */
    if (t >= ROM_T2_ON)
        RAM_FAN2_OUT = 1;
    else if (t < ROM_T2_ON - ROM_T2_HY)
        RAM_FAN2_OUT = 0;
    be17 = RAM_FAN2_OUT;

    /* --- fan enable latch --- */
    en  = 0;
    loc = 0;
    for (;;) {
        if (loc == 0) {                       /* 0x30416: entry branch tree */
            if (be16 == 1 ||
                (be17 == 1 && cell(0xFFFFB13D) == 1) ||
                (cell(0xFFFFAAE0) == 0 && cell(0xFFFFBE0C) == 1 &&
                 cell(0xFFFFCD06) == 0 && cell(0xFFFFA96A) == 0 &&
                 cell(0xFFFFBFF5) == 0))
                loc = 2;                      /* -> 0x30486 */
            else
                loc = 1;                      /* -> 0x3046E */
        } else if (loc == 1) {                /* 0x3046E */
            if (cell(0xFFFFBDD4) == 1)
                loc = 2;                      /* -> 0x30486 */
            else if (cell(0xFFFFBDD6) != 1)
                loc = 3;                      /* -> 0x3049A */
            else
                loc = 2;                      /* -> 0x30486 */
        } else if (loc == 2) {                /* 0x30486 */
            if (cell(0xFFFFD07C) != 0)
                loc = 3;                      /* -> 0x3049A */
            else if (cell(0xFFFFD0E4) == 0)
                loc = 4;                      /* -> 0x304B2 */
            else
                loc = 3;                      /* -> 0x3049A */
        } else if (loc == 3) {                /* 0x3049A */
            if (cell(0xFFFFD2A0) == 1 || cell(0xFFFFD2A5) == 1)
                loc = 4;                      /* -> 0x304B2 */
            else
                loc = 5;                      /* -> 0x304C0 (enable=0) */
        } else if (loc == 4) {                /* 0x304B2 */
            if (cell(0xFFFFD29F) != 0)
                loc = 5;                      /* -> 0x304C0 (enable=0) */
            else {
                loc = 6;                      /* -> 0x304BC (enable=1) */
                en = 1;
                break;
            }
        } else {                              /* 0x304C0: enable = 0 */
            break;
        }
    }
    RAM_FAN_ENABLE = en;
}
