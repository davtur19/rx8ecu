/* omp_waveform_state_machine_18860.c
 *
 * ROM: 60E1D400  |  Address: 0x18860  |  Size: 398 bytes  |  VERIFIED vs ROM emulator
 *
 * Waveform state machine stage of the OMP chain (formerly mislabeled as an
 * "injection timing control" stage; called from 0x1825E).  A 4-state machine
 * (RAM8[0xFFFFA981]) that:
 *
 *   state 0:  (mode == 0 only) clear A981 and A982.
 *
 *   state 1:  if RAM8[A968] == 1, gate on the redundant port bytes
 *             readValue_8bit_ADDRESS_VAL(0xFFFF8078/0xFFFF807C, 0):
 *               - if val8078 == 0, or val807C != 1:  cold-weather cal A
 *               - else compare RAM_AA10 (f32 coolant temp) against
 *                 ROM 0x78E68 = -40.0:  temp < -40.0 -> cal A, else cal B
 *             A97E = cal byte (both 0x3C in stock ROM) and the discriminator
 *             is latched: A977 = (cal B) / A978 = (cal A).  A981 -> 2.
 *
 *   state 0 step block:  drive the stepper via omp_stepper_waveform_driver:
 *               A97C == 5 -> A97B = 0x80, A981 -> 1
 *               A97C == 4 -> A97B = 0x30, wave(0); A974 > 60 -> A97F = A974+1
 *               else      -> A97B = 0x10, wave(2)
 *
 *   state 2:  if A977 == 1 or A978 == 1:
 *               even A97C -> A97B = 0x30, wave(1); if A97C == 5 (after wave)
 *                            and A97E <= 1: A982 = 1, A97F = 0, A97E = 0,
 *                            A97B = sat8(A97B, 0x30)
 *               odd  A97C -> A97B = 8, wave(1); A97E > 0 -> A97E -= 1
 *
 * Calls the verified leaves 0x3ED3C (readValue_8bit_ADDRESS_VAL), 0x18552
 * (omp_stepper_waveform_driver) and 0x2478 (addSaturate8Bit, min(a+b,255)).
 *
 * Verified: 60000 random inputs vs the ROM emulator, 0 mismatches
 * (test_omp_waveform_state_machine_18860.py).
 */
#include <stdint.h>

#define RAM_A981 (*(volatile uint8_t *)0xFFFFA981)
#define RAM_A982 (*(volatile uint8_t *)0xFFFFA982)
#define RAM_A97E (*(volatile uint8_t *)0xFFFFA97E)
#define RAM_A97B (*(volatile uint8_t *)0xFFFFA97B)
#define RAM_A97F (*(volatile uint8_t *)0xFFFFA97F)
#define RAM_A977 (*(volatile uint8_t *)0xFFFFA977)
#define RAM_A978 (*(volatile uint8_t *)0xFFFFA978)
#define RAM_A968 (*(volatile uint8_t *)0xFFFFA968)
#define RAM_A97C (*(volatile uint8_t *)0xFFFFA97C)
#define RAM_A974 (*(volatile uint8_t *)0xFFFFA974)
#define RAM_AA10 (*(volatile float *)0xFFFFAA10)

#define ROM_CAL_A (*(const uint8_t *)0x78E33)  /* 0x3C */
#define ROM_CAL_B (*(const uint8_t *)0x78E34)  /* 0x3C */
#define ROM_CAL_T (*(const float *)0x78E68)    /* -40.0 */

/* 0x3ED3C — verified: RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(default) */
extern int8_t readValue_8bit_ADDRESS_VAL(uint16_t addr, uint8_t default_);
/* 0x18552 — verified stepper waveform driver (modes 0,1,2 used here) */
extern void omp_stepper_waveform_driver(uint8_t mode);
/* 0x2478 — verified saturating byte add: min(a+b, 255) */
extern uint8_t addSaturate8Bit(uint8_t a, uint8_t b);

void omp_waveform_state_machine_18860(uint8_t mode)
{
    if (mode == 0) {                 /* 0x18874: state reset */
        RAM_A981 = 0;
        RAM_A982 = 0;
    }

    if (RAM_A981 == 1) {             /* 0x18884..0x188DE: gate + cal select */
        uint8_t r9 = 0, r14 = 0;
        if (RAM_A968 == 1) {
            if ((uint8_t)readValue_8bit_ADDRESS_VAL(0xFFFF8078, 0) != 0) {
                if ((uint8_t)readValue_8bit_ADDRESS_VAL(0xFFFF807C, 0) == 1) {
                    if (ROM_CAL_T > RAM_AA10)  /* fcmp/gt: (-40.0 > temp) */
                        r14 = 1;               /* temp < -40.0 -> cal A */
                    else
                        r9 = 1;                /* temp >= -40.0 -> cal B */
                } else
                    r14 = 1;
            } else
                r14 = 1;
            RAM_A97E = (r9 == 1) ? ROM_CAL_B : ROM_CAL_A;
        }
        RAM_A977 = r9;               /* cal-B flag (temp >= -40.0) */
        RAM_A978 = r14;              /* cal-A flag (cold / gate fail) */
        RAM_A981 = 2;
    }

    if (RAM_A981 == 0) {             /* 0x188E0..0x1895E: step drive */
        switch (RAM_A97C) {
        case 5:
            RAM_A97B = 0x80;
            RAM_A981 = 1;
            break;
        case 4:
            RAM_A97B = 0x30;
            omp_stepper_waveform_driver(0);
            if (RAM_A974 < 60)          /* cmp/ge r1,r2: T=(A974>=60), bt skips */
                RAM_A97F = (uint8_t)(RAM_A974 + 1);
            break;
        default:
            RAM_A97B = 0x10;
            omp_stepper_waveform_driver(2);
            break;
        }
    }

    if (RAM_A981 == 2) {             /* 0x18964..0x189DC: timing adjust */
        if (RAM_A977 == 1 || RAM_A978 == 1) {
            if ((RAM_A97C & 1) == 0) {           /* even step */
                RAM_A97B = 0x30;
                omp_stepper_waveform_driver(1);
                if (RAM_A97C == 5 && RAM_A97E <= 1) {
                    RAM_A982 = 1;
                    RAM_A97F = 0;
                    RAM_A97E = 0;
                    RAM_A97B = addSaturate8Bit(RAM_A97B, 0x30);
                }
            } else {                              /* odd step */
                RAM_A97B = 8;
                omp_stepper_waveform_driver(1);
                if (RAM_A97E > 0)
                    RAM_A97E = (uint8_t)(RAM_A97E + 0xFF);  /* -1 mod 256 */
            }
        }
    }
}
