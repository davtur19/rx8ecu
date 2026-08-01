/* rotor_sync_position_detector.c
 *
 * ROM: 60E1D400  |  Address: 0x189EE  |  Size: 522 bytes  |  VERIFIED vs ROM emulator
 *
 * Rotor-sync position detector for the OMP stepper chain (called from 0x1825E).
 * Tracks the rotor position (RAM8[0xFFFFA974]) against the previously stored
 * position (RAM8[0xFFFFA8F1]) through a 5-state machine on RAM8[0xFFFFA98B],
 * then dispatches the stepper waveform driver 0x18552 (wave) for the final
 * state.  A97C odd/even at entry selects the phase.
 *
 *   stage A (mode == 0 only): compare A8F1 vs A974:
 *       A8F1 > A974 -> A98B = 0
 *       A8F1 < A974 -> A98B = 1
 *       A8F1 == A974 -> A98B = 2, flag = 1
 *
 *   stage B (state blocks on current A98B; odd = A97C & 1):
 *       state 0: A8F1 >= A974:  A8F1==A974 && !odd -> A98B=2, flag=1
 *                A8F1 <  A974:  !odd -> A98B=3
 *       state 1: A8F1 > A974:   !odd || A974==0 -> A98B=3
 *                A8F1 == A974:  !odd || A974==0: A974>=5 -> A98B=4
 *                                                else    -> A98B=2, flag=1
 *       state 2: A8F1 > A974 -> A98B=0;  A8F1 < A974 -> A98B=1
 *       state 3: A8F1 > A974 -> A98B=0;  A8F1 < A974 -> A98B=1;
 *                equal -> A98B=2, flag=1
 *       state 4: !odd: (A8F1-2) >= A974 -> A98B=3   (add #0xFE sign-extends)
 *                     A8F1 < 5 -> A98B=2, flag=1
 *
 *   stage C (tail on final A98B; A97B is always rewritten):
 *       state 0: wave(2), A97B = 0x10
 *       state 1: A974 >= 5 -> wave(3), A97B = 0x10
 *                else      -> wave(1), A97B = 8 (odd) else 0x30
 *       state 2: flag && A974 == 0 -> A97D = A97C, A97B = 4   (no wave)
 *                else              -> wave(4),   A97B = 4
 *       state 3: A97B = 0x30
 *       state 4: A974 >= 5 -> wave(3), A97B = 0x10
 *                else      -> wave(1), A97B = 8 (odd) else 0x30
 *
 * Inputs:  RAM8[A8F1] old position, RAM8[A974] new position, RAM8[A98B] state,
 *          RAM8[A97C] step, plus the wave() inputs (A97D/A98A/A969/A96A/A97F,
 *          RAM16[FFFFF746] port).
 * Outputs: RAM8[A98B] state, RAM8[A97B] waveform byte, RAM8[A97D] (state-2
 *          copy), plus all wave() effects.
 *
 * Verified: 60000 random inputs vs the ROM emulator, 0 mismatches
 * (test_rotor_sync_position_detector.py).
 */
#include <stdint.h>

#define RAM_A8F1 (*(volatile uint8_t *)0xFFFFA8F1)
#define RAM_A974 (*(volatile uint8_t *)0xFFFFA974)
#define RAM_A98B (*(volatile uint8_t *)0xFFFFA98B)
#define RAM_A97C (*(volatile uint8_t *)0xFFFFA97C)
#define RAM_A97D (*(volatile uint8_t *)0xFFFFA97D)
#define RAM_A97B (*(volatile uint8_t *)0xFFFFA97B)

/* 0x18552 — verified stepper waveform driver */
extern void omp_stepper_waveform_driver(uint8_t mode);

void rotor_sync_position_detector(uint8_t mode)
{
    int a8f1 = RAM_A8F1;
    int a974 = RAM_A974;
    int odd = RAM_A97C & 1;         /* r12/r8: 1 if A97C odd at entry */
    int flag = 0;                   /* r13: set by the equal-state transitions */
    uint8_t state = RAM_A98B;

    /* stage A: mode == 0 position compare (0x18A2E..0x18A66) */
    if (mode == 0) {
        if (a8f1 > a974) {
            state = 0;
        } else if (a8f1 == a974) {
            state = 2;
            flag = 1;
        } else {
            state = 1;
        }
        RAM_A98B = state;
    }

    /* stage B: state blocks (0x18A98..0x18B44) */
    switch (state) {
    case 0:
        if (a8f1 >= a974) {
            if (a8f1 == a974 && !odd) {
                RAM_A98B = 2;
                flag = 1;
            }
        } else {
            if (!odd)
                RAM_A98B = 3;
        }
        break;
    case 1:
        if (a8f1 > a974) {
            if (!odd || a974 == 0)
                RAM_A98B = 3;
        } else if (a8f1 == a974) {
            if (!odd || a974 == 0) {
                if (a974 >= 5)
                    RAM_A98B = 4;
                else {
                    RAM_A98B = 2;
                    flag = 1;
                }
            }
        }
        break;
    case 2:
        if (a8f1 > a974)
            RAM_A98B = 0;
        else if (a8f1 < a974)
            RAM_A98B = 1;
        break;
    case 3:
        if (a8f1 > a974)
            RAM_A98B = 0;
        else if (a8f1 < a974)
            RAM_A98B = 1;
        else {
            RAM_A98B = 2;
            flag = 1;
        }
        break;
    case 4:
        if (!odd) {
            if ((int8_t)(a8f1 - 2) >= a974)   /* add #0xFE sign-extends */
                RAM_A98B = 3;
            if (a8f1 < 5) {
                RAM_A98B = 2;
                flag = 1;
            }
        }
        break;
    default:
        break;                       /* states 5..255: no action */
    }

    /* stage C: tail dispatch on the final state (0x18B46..0x18BE4) */
    state = RAM_A98B;
    a974 = RAM_A974;
    switch (state) {
    case 0:
        omp_stepper_waveform_driver(2);
        RAM_A97B = 0x10;
        break;
    case 1:
        if (a974 >= 5) {
            omp_stepper_waveform_driver(3);
            RAM_A97B = 0x10;
        } else {
            omp_stepper_waveform_driver(1);
            RAM_A97B = (odd ? 8 : 0x30);
        }
        break;
    case 2:
        if (flag && a974 == 0) {
            RAM_A97D = RAM_A97C;    /* copy step to rotor-sync source */
        } else {
            omp_stepper_waveform_driver(4);
        }
        RAM_A97B = 4;
        break;
    case 3:
        RAM_A97B = 0x30;
        break;
    case 4:
        if (a974 >= 5) {
            omp_stepper_waveform_driver(3);
            RAM_A97B = 0x10;
        } else {
            omp_stepper_waveform_driver(1);
            RAM_A97B = (odd ? 8 : 0x30);
        }
        break;
    default:
        break;
    }
}
