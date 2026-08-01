/* omp_stepper_waveform_driver.c
 *
 * ROM: 60E1D400  |  Address: 0x18552  |  Size: 774 bytes  |  VERIFIED vs ROM emulator
 *
 * OMP (oil-metering pump) stepper waveform generator, called from the OMP chain
 * driver 0x1825E.  Advances the stepper step register and drives the 4-phase
 * pattern for the new step onto port 0xFFFFF746 (bits 0..3), using the 9-entry
 * step pattern table copied from ROM 0x4ED5C (36 bytes, 9 x 4-phase).
 *
 * Mode dispatch (r4 = mode, clamped to 8 bits):
 *   0 -> step = (step + 1) & 7            ; if new step even AND rotor pos < 60
 *                                          ;   A97F = rotor_pos + 1
 *   1 -> if step == 8: step = (A97D-1)&7  ; rotor-sync source
 *         else:        step = (step-1)&7
 *                     ; if rotor_pos == 1 && latched != 4 && (A969||A96A == 1)
 *                     ;   A97F = 0
 *         ; then (both paths): if step even && latched != 4 && rotor_pos > 0
 *                     ;   A97F = (0xFF + rotor_pos) & 0xFF
 *   2 -> if latched == 4 || step odd:  step = (src+1) & 7  (src = A97D if step==8)
 *         else:                        step = (step+2) & 7
 *         ; if rotor_pos < 60: A97F = rotor_pos + 1
 *   3 -> if latched == 4 || step odd:
 *           if step == 8: step = (A97D-1)&7
 *           else:         step = (step-1)&7
 *                        ; if rotor_pos == 1 && latched != 4: A97F = 0
 *         else:          step = (step-2)&7
 *                        ; if rotor_pos > 0: A97F = (0xFF + rotor_pos) & 0xFF
 *   4 -> if step == 8: step = A97D
 *         elif step even: step = (step+1)&7; A97D = step
 *         else:           step = 8
 *   6 -> step = 8
 *   default (5,7..255): step unchanged
 *
 * Tail (all modes): A98A = mode (latched); A98D = mode (written at entry);
 * A97F write iff a mode path produced one; then the 4-phase port drive:
 * for phase i in 0..3, bit mask {1,2,4,8} on RAM16[0xFFFFF746] is SET if the
 * i-th pattern byte of the current step == 1, else CLEARED (0x4BBC RMW).
 * The port writes are bracketed by setSR_PARAM(0x2054)/setSR(0x2064) pairs with
 * value 0xE0 — SR is clamped back to its entry value, so SR is unchanged.
 *
 * Pattern table 0x4ED5C (step -> 4 phase bytes):
 *   step0: 1 0 0 1 | step1: 1 0 0 0 | step2: 1 1 0 0 | step3: 0 1 0 0
 *   step4: 0 1 1 0 | step5: 0 0 1 0 | step6: 0 0 1 1 | step7: 0 0 0 1
 *   step8: 0 0 0 0   (stop/idle)
 *
 * Inputs:
 *   RAM[0xFFFFA97C] (u8)  step register (advance source)
 *   RAM[0xFFFFA97D] (u8)  rotor-sync step source
 *   RAM[0xFFFFA974] (u8)  rotor position counter
 *   RAM[0xFFFFA98A] (u8)  previously latched mode
 *   RAM[0xFFFFA969] (u8)  gate flag A
 *   RAM[0xFFFFA96A] (u8)  gate flag B
 *   RAM[0xFFFFF746] (u16) stepper drive port (read-modify-write)
 *
 * Outputs:
 *   RAM[0xFFFFA97C] (u8)  new step
 *   RAM[0xFFFFA97D] (u8)  = new step (mode 4 even path only)
 *   RAM[0xFFFFA97F] (u8)  waveform byte (conditionally written)
 *   RAM[0xFFFFA98A] (u8)  = mode
 *   RAM[0xFFFFA98D] (u8)  = mode
 *   RAM[0xFFFFF746] (u16) drive port (4 pattern bits)
 *
 * Verified: 60000 random inputs (modes 0..6 + defaults, step/A97D in 0..8,
 * other bytes + port fully random) vs the ROM emulator, 0 mismatches
 * (test_omp_stepper_waveform_driver.py).
 */
#include <stdint.h>

#define RAM_STEP (*(volatile uint8_t *)0xFFFFA97C)
#define RAM_A97D (*(volatile uint8_t *)0xFFFFA97D)
#define RAM_A974 (*(volatile uint8_t *)0xFFFFA974)
#define RAM_A98A (*(volatile uint8_t *)0xFFFFA98A)
#define RAM_A98D (*(volatile uint8_t *)0xFFFFA98D)
#define RAM_A97F (*(volatile uint8_t *)0xFFFFA97F)
#define RAM_A969 (*(volatile uint8_t *)0xFFFFA969)
#define RAM_A96A (*(volatile uint8_t *)0xFFFFA96A)
#define RAM_F746 (*(volatile uint16_t *)0xFFFFF746)

/* step pattern table, ROM 0x4ED5C (copied to the stack frame at entry) */
static const uint8_t STEP_PATTERN[9][4] = {
    {1, 0, 0, 1}, {1, 0, 0, 0}, {1, 1, 0, 0}, {0, 1, 0, 0}, {0, 1, 1, 0},
    {0, 0, 1, 0}, {0, 0, 1, 1}, {0, 0, 0, 1}, {0, 0, 0, 0},
};

/* setRegister_REG_BIT_VAL @0x4BBC (r4 = reg, r5 = mask, r6 = enable):
 * RMW: enable ? *reg |= mask : *reg &= ~mask  (16-bit) */
extern void setRegister_REG_BIT_VAL(uint16_t *reg, uint16_t mask, int enable);

void omp_stepper_waveform_driver(uint8_t mode)
{
    uint8_t step = RAM_STEP;
    uint8_t a97d = RAM_A97D;
    uint8_t a974 = RAM_A974;
    uint8_t a98a = RAM_A98A;
    int      wf_ok = 0;
    uint8_t  wf = 0;
    int      i;

    RAM_A98D = mode;                        /* 0x18580: latched at entry */

    switch (mode) {
    case 0:                                 /* 0x18614: advance by 1 */
        step = (step + 1) & 7;
        if ((step & 1) == 0 && a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 1:                                 /* 0x18642: rotor-sync advance */
        if (step == 8) {
            step = (a97d + 0xFF) & 7;       /* A97D source */
        } else {
            step = (step + 0xFF) & 7;       /* decrement mod 8 */
            if (a974 == 1 && a98a != 4 &&
                (RAM_A969 == 1 || RAM_A96A == 1)) {
                wf_ok = 1;
                wf = 0;
            }
        }
        if ((step & 1) == 0 && a98a != 4 && a974 > 0) {
            wf_ok = 1;
            wf = (uint8_t)(0xFF + a974);    /* 0x186B4 */
        }
        break;
    case 2:                                 /* 0x186B8 */
        if (a98a == 4 || (step & 1) == 1) {
            step = (step == 8) ? (uint8_t)((a97d + 1) & 7)
                               : (uint8_t)((step + 1) & 7);
        } else {
            step = (uint8_t)((step + 2) & 7);
        }
        if (a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 3:                                 /* 0x186FC */
        if (a98a == 4 || (step & 1) == 1) {
            if (step == 8) {
                step = (uint8_t)((a97d + 0xFF) & 7);
            } else {
                step = (uint8_t)((step + 0xFF) & 7);
                if (a974 == 1 && a98a != 4) {
                    wf_ok = 1;
                    wf = 0;
                }
            }
        } else {
            step = (uint8_t)((step + 0xFE) & 7);    /* decrement by 2 mod 8 */
            if (a974 > 0) {
                wf_ok = 1;
                wf = (uint8_t)(0xFF + a974);
            }
        }
        break;
    case 4:                                 /* 0x18766 */
        if (step == 8) {
            step = a97d;
        } else if ((step & 1) == 0) {
            step = (uint8_t)((step + 1) & 7);
            RAM_A97D = step;
        } else {
            step = 8;
        }
        break;
    case 6:                                 /* 0x18790 */
        step = 8;
        break;
    default:                                /* 0x185C2: modes 5,7..255 */
        break;                              /* step unchanged */
    }

    RAM_A98A = mode;                        /* 0x18796 */
    if (wf_ok)
        RAM_A97F = wf;

    /* 4-phase port drive, 0x187A8..0x1882C: pattern byte == 1 -> set bit */
    for (i = 0; i < 4; i++) {
        setRegister_REG_BIT_VAL(&RAM_F746, (uint16_t)(1u << i),
                                STEP_PATTERN[step][i] == 1);
    }
}
