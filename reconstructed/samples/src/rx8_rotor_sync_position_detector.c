/*
 * =============================================================================
 * rx8_rotor_sync_position_detector.c  —  ROTOR-SYNC POSITION DETECTOR (OMP)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x189EE  (size 522 bytes; 0x189EE..0x18BF6)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_rotor_sync_position_detector.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               vectors; every RAM byte the function and its callee can touch
 *               compared byte-for-byte, 0 mismatches).
 * Lift (truth): c/rotor_sync_position_detector.c  (same address 0x189EE,
 *               same behaviour — the ground truth this port follows, with the
 *               discrepancy listed below).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Rotor-sync position detector for the OMP stepper chain (called from the OMP
 * chain driver 0x1825E with r4 = mode, 0 for a position-compare pass and any
 * other value for a pure state-machine pass).  It tracks the rotor position
 * RAM8[0xFFFFA974] against the previously stored position RAM8[0xFFFFA8F1]
 * through a 5-state machine on RAM8[0xFFFFA98B], then dispatches the verified
 * stepper waveform driver 0x18552 (wave) for the final state.  RAM8[0xFFFFA97C]
 * odd/even at entry selects the phase.  No ABI return value — the whole effect
 * is on RAM.
 *
 * Flow (registers mapped from the disassembly of 0x189EE..0x18BF6):
 *
 *   stage A (mode == 0 only, 0x18A2E..0x18A66) — compare A8F1 vs A974:
 *       A8F1 >  A974 -> A98B = 0
 *       A8F1 <  A974 -> A98B = 1
 *       A8F1 == A974 -> A98B = 2, flag = 1
 *
 *   stage B (state blocks on the current A98B, 0x18A98..0x18B44; odd =
 *   A97C & 1, captured at entry):
 *       state 0: A8F1 >= A974:  A8F1==A974 && !odd -> A98B=2, flag=1
 *                A8F1 <  A974:  !odd -> A98B=3
 *       state 1: A8F1 > A974:   !odd || A974==0 -> A98B=3
 *                A8F1 == A974:  !odd || A974==0: A974>=5 -> A98B=4
 *                                                else    -> A98B=2, flag=1
 *       state 2: A8F1 > A974 -> A98B=0;  A8F1 < A974 -> A98B=1
 *       state 3: A8F1 > A974 -> A98B=0;  A8F1 < A974 -> A98B=1;
 *                equal -> A98B=2, flag=1
 *       state 4: !odd: (A8F1-2) >= A974 -> A98B=3   (32-bit signed; the ROM
 *                     does `mov r6,r1; add #0xFE,r1; cmp/ge r14,r1`, so the
 *                     -2 can only go negative when A8F1 < 2)
 *                     A8F1 < 5 -> A98B=2, flag=1
 *       states 5..255: no action
 *
 *   stage C (tail on the final A98B, 0x18B46..0x18BE4; A97B always rewritten):
 *       state 0: wave(2), A97B = 0x10
 *       state 1: A974 >= 5 -> wave(3), A97B = 0x10
 *                else      -> wave(1), A97B = 8 (odd) else 0x30
 *       state 2: flag && A974 == 0 -> A97D = A97C, A97B = 4   (no wave)
 *                else              -> wave(4),   A97B = 4
 *       state 3: A97B = 0x30
 *       state 4: A974 >= 5 -> wave(3), A97B = 0x10
 *                else      -> wave(1), A97B = 8 (odd) else 0x30
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_rotor_sync_position_detector(uint8_t mode)` — r4 = mode, zero-
 * extended (`extu.b r4,r4` at 0x18A1A), so any 0..255 value is legal; no
 * meaningful return value.  Driven through the standard SH2.call() entry and
 * verified on RAM side effects, exactly like the other OMP-chain rigs.
 *
 * CALLEE (runs as REAL ROM bytes inside the emulator)
 * ---------------------------------------------------
 *   0x18552  omp_stepper_waveform_driver (bsr; r4 = mode 1/2/3/4) — the
 *            verified stepper waveform generator (774 B, lift
 *            c/omp_stepper_waveform_driver.c).  It advances the step register
 *            RAM8[0xFFFFA97C], conditionally writes RAM8[0xFFFFA97F], latches
 *            RAM8[0xFFFFA98A] = RAM8[0xFFFFA98D] = mode, and drives the four
 *            phase bits 0..3 of RAM16[0xFFFFF746] via the RMW leaf 0x4BBC
 *            (setRegister_REG_BIT_VAL: enable ? *reg |= mask : *reg &= ~mask),
 *            using the 9-entry pattern table copied from ROM 0x4ED5C.  The
 *            host oracle supplies a faithful model of it (the same one the
 *            emulator executes), exactly like readValue_8bit_ADDRESS_VAL in
 *            rx8_omp_rotor_overshoot_detector.c.
 *
 * CALIBRATION TABLES
 * ------------------
 * None.  The function reads no ROM constants; the only ROM table involved is
 * the wave callee's step-pattern block @0x4ED5C, which lives in the callee.
 *
 * RAM FOOTPRINT (byte address = xxxx @0xFFFFxxxx)
 * ------------------------------------------------------------------------
 *   reads : A8F1 old position, A974 new position (entry + stage C re-read),
 *           A98B state, A97C step (odd test at entry); plus the wave() reads
 *           of A97C/A97D/A974/A98A/A969/A96A/F746.
 *   writes: A98B state, A97B waveform byte (every non-default final state),
 *           A97D (state-2 flag copy, or the wave's mode-4 step write); plus
 *           the wave() writes of A97C/A97D/A97F/A98A/A98D/F746.
 *   all widths 8-bit except RAM16[0xFFFFF746] (the wave's 4-phase port RMW).
 *
 * DISCREPANCY FOUND IN THE LIFT (c/rotor_sync_position_detector.c)
 * -----------------------------------------------------------------
 *   State 4, `!odd` branch: the lift models the ROM's
 *       mov r6,r1      ; r1 = A8F1
 *       add #0xFE,r1   ; r1 = A8F1 - 2   (32-bit add, immediate sign-extends)
 *       cmp/ge r14,r1  ; T = (r1 >= A974) (SIGNED 32-bit compare)
 *   as `(int8_t)(A8F1 - 2) >= A974`.  The (int8_t) cast truncates A8F1 - 2 to
 *   a signed byte, so for A8F1 - 2 > 127 (i.e. A8F1 >= 130) it wraps negative
 *   and the write of A98B = 3 never fires.  The ROM holds the full 32-bit
 *   sum (only A8F1 0/1 go negative: -2/-1), so `(A8F1 - 2) >= A974` in plain
 *   int arithmetic is the correct model.  Verified directly against the ROM
 *   bytes with the emulator: A8F1 = 200, A974 = 150, state 4, even step ->
 *   ROM writes A98B = 3 (198 >= 150), where the lift's cast would not.  This
 *   sample follows the ROM; the state-4 line and this header document the fix.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- RAM cells (8-bit @ 0xFFFFxxxx) ---- */
#define RAM_A8F1 (*(volatile uint8_t *)0xFFFFA8F1u)  /* old rotor position     */
#define RAM_A974 (*(volatile uint8_t *)0xFFFFA974u)  /* new rotor position     */
#define RAM_A98B (*(volatile uint8_t *)0xFFFFA98Bu)  /* state byte (machine)   */
#define RAM_A97C (*(volatile uint8_t *)0xFFFFA97Cu)  /* step register (odd?)   */
#define RAM_A97D (*(volatile uint8_t *)0xFFFFA97Du)  /* rotor-sync step source */
#define RAM_A97B (*(volatile uint8_t *)0xFFFFA97Bu)  /* waveform output byte   */

/* 0x18552 — verified stepper waveform driver (real ROM bytes in the emulator;
 * faithful host model supplied by the oracle). */
extern void omp_stepper_waveform_driver(uint8_t mode);

void rx8_rotor_sync_position_detector(uint8_t mode)
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
            /* ROM 0x18B30..0x18B3A: r1 = A8F1; add #0xFE; cmp/ge A974 — a
             * 32-bit SIGNED compare, so only A8F1 < 2 goes negative (the
             * lift's (int8_t) cast wrongly wraps A8F1 >= 130; see header). */
            if ((a8f1 - 2) >= a974)
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
