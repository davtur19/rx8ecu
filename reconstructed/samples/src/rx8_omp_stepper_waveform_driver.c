/*
 * =============================================================================
 * rx8_omp_stepper_waveform_driver.c  —  OMP STEPPER WAVEFORM DRIVER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x18552  (774 bytes; 0x18552..0x18842)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_omp_stepper_waveform_driver.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               pre-states; every RAM cell the function can touch compared
 *               byte-for-byte, 0 mismatches).
 * Lift (truth): c/omp_stepper_waveform_driver.c  (same address, same
 *               behaviour — the ground truth for this port; verified bit-exact
 *               vs the ROM emulator over 60000 random inputs in the c/ project).
 *
 * WHAT THIS IS
 * ------------
 * The OMP (oil-metering pump) stepper waveform generator, called from the OMP
 * chain driver 0x1825E.  It advances the stepper step register @0xFFFFA97C and
 * drives the 4-phase pattern of the new step onto the stepper drive port
 * 0xFFFFF746 (bits 0..3), using the 9-entry step-pattern table copied from ROM
 * 0x4ED5C (36 bytes, 9 steps x 4 phases) onto the stack at entry.
 *
 * CALLING CONVENTION
 * ------------------
 * Standard SH-2 ABI, `void omp_stepper_waveform_driver(uint8_t mode)`: the
 * mode arrives in r4 and is clamped to 8 bits by the ROM's `extu.b r4,r0`
 * before dispatch (the host port takes a uint8_t, so the clamp is implicit).
 * No ABI return value — the whole effect is on RAM, so the equivalence harness
 * compares RAM side-effects, not a register.
 *
 * MODE DISPATCH (register trace of 60E1D400.bin @ 0x18552, cf. the lift):
 *   0 -> step = (step + 1) & 7        ; then if step even AND A974 < 60
 *                                      ;   A97F = A974 + 1
 *   1 -> step == 8 : step = (A97D + 0xFF) & 7   (rotor-sync source)
 *         else     : step = (step + 0xFF) & 7
 *                    ; if A974 == 1 && A98A != 4 && (A969 == 1 || A96A == 1)
 *                    ;   A97F = 0
 *         ; then (both paths): if step even && A98A != 4 && A974 > 0
 *                    ;   A97F = (0xFF + A974) & 0xFF
 *   2 -> A98A == 4 || step odd:  step = ((step == 8 ? A97D : step) + 1) & 7
 *         else                :  step = (step + 2) & 7
 *         ; then if A974 < 60: A97F = A974 + 1
 *   3 -> A98A == 4 || step odd:
 *           step == 8 : step = (A97D + 0xFF) & 7
 *           else      : step = (step + 0xFF) & 7
 *                       ; if A974 == 1 && A98A != 4: A97F = 0
 *         else                : step = (step + 0xFE) & 7   (minus 2 mod 8)
 *                                ; if A974 > 0: A97F = (0xFF + A974) & 0xFF
 *   4 -> step == 8 : step = A97D
 *         step even : step = (step + 1) & 7;  A97D = step     (new step!)
 *         else      : step = 8
 *   6 -> step = 8
 *   default (5, 7..255): step unchanged
 *
 * TAIL (all modes, 0x18794..0x1882C):
 *   A98A = mode (latched at entry); A98D = mode (written before dispatch);
 *   A97F written iff a mode path produced a waveform byte; then the 4-phase
 *   port drive: for phase i in 0..3 the 16-bit port 0xFFFFF746 has bit
 *   (1 << i) SET when the i-th pattern byte of the current step == 1, else
 *   CLEARED, via the 0x4BBC RMW leaf.  Each port write is bracketed by a
 *   setSR_PARAM(0x2054)/setSR(0x2064) pair with value 0xE0 that saves and
 *   restores the old masked IPL — SR exits exactly as it entered.
 *
 * STEP PATTERN TABLE (ROM 0x4ED5C, copied to the stack frame at entry):
 *   step0: 1 0 0 1 | step1: 1 0 0 0 | step2: 1 1 0 0 | step3: 0 1 0 0
 *   step4: 0 1 1 0 | step5: 0 0 1 0 | step6: 0 0 1 1 | step7: 0 0 0 1
 *   step8: 0 0 0 0   (stop / idle)
 *
 * RAM FOOTPRINT (all @0xFFFFxxxx, byte address = xxxx):
 *   reads : A97C (u8) step register, A97D (u8) rotor-sync step source,
 *           A974 (u8) rotor position counter, A98A (u8) previously latched
 *           mode, A969 (u8) gate flag A, A96A (u8) gate flag B,
 *           F746 (u16) stepper drive port (read-modify-write via 0x4BBC).
 *   writes: A97C (u8) new step, A97D (u8, mode 4 even path only),
 *           A97F (u8, conditionally), A98A (u8) = mode, A98D (u8) = mode,
 *           F746 (u16) four pattern bits.
 *
 * INTERNAL CALLED LEAVES (run natively in the emulator as real ROM bytes;
 * the host oracle models them — see the oracle source):
 *   0x42B0  byte copy (36-byte pattern table ROM -> stack frame); this port
 *           does NOT call it — the table is a compile-time constant, so the
 *           copy is behaviourally inlined (STUBBED, cf. the lift which does
 *           the same).
 *   0x2054  setSR_PARAM(store, new_sr) — SR save/raise.  SR-only effect on
 *           cells this function never reads back; STUBBED (no RAM effect).
 *   0x2064  setSR(sr) — SR restore leaf (`rts` / delay `ldc r4,sr`).  SR-only
 *           effect; STUBBED (no RAM effect).
 *   0x4BBC  setRegister_REG_BIT_VAL(reg, mask, enable) — the 16-bit RMW that
 *           drives the port bits; declared extern below exactly like the lift
 *           and implemented on the host by the oracle.
 * No un-lifted leaf is reached, so nothing else is inlined.
 *
 * LIFT-vs-ROM DISCREPANCIES (fixed here; the ROM wins)
 * -----------------------------------------------------
 * 1. STEP WRITE-BACK: the lift (c/omp_stepper_waveform_driver.c) never writes
 *    the new step back to RAM[0xFFFFA97C] — it keeps `step` in a local for the
 *    pattern index and the ROM does `mov.b r0,@r14` (0xFFFFA97C) in EVERY
 *    non-default mode (0x1861A, 0x18652/0x1865A, 0x186DC/0x186E6, 0x18792/
 *    0x1872E/0x18752, 0x18770/0x18780/0x1878E, 0x18792).  The ROM emulator
 *    reads the new step back at A97C, so the lift's A97C would differ.  The
 *    c/ test never caught this because it compares the ROM against a Python
 *    model (test_omp_stepper_waveform_driver.py), not the lift C.  This port
 *    writes RAM_STEP = step exactly where the ROM does (per-case, before the
 *    tail; the default path 5/7..255 writes nothing).
 * 2. SR BRACKET: the lift's "SR is clamped back to its entry value, so SR is
 *    unchanged" holds — the ROM uses FOUR setSR_PARAM(0x2054)/setSR(0x2064)
 *    pairs storing at r15+0xC/+0x8/+0x4/+0x0, so SR exits at its entry value
 *    (with the RTOS entry SR = 0xF0 the emulator confirms SR = 0xF0 on exit;
 *    the c/ test pins this too).  The SR and 0x42B0 copy leaves are stubbed
 *    here (no effect on any compared RAM cell).
 * 3. PATTERN INDEX CLAMP: the ROM reads the 4-phase table as flat bytes
 *    `table[step * 4 + i]` from the 36-byte stack copy.  A step value >= 9
 *    (reachable only via the mode-4 A97D source or the default path, which
 *    preserve an arbitrary pre-state) reads PAST the table into the never-
 *    written stack frame — 0x00 in the emulator, so every phase byte is 0 and
 *    the port drive clears all four bits.  The lift's `STEP_PATTERN[step][i]`
 *    is out-of-bounds for those inputs (undefined behaviour on the host); the
 *    clamp below reproduces the emulator byte-exactly.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- RAM cells ---- */
#define RAM_STEP  RX8_IO8(0xFFFFA97Cu)   /* u8 step register (advance source)  */
#define RAM_A97D  RX8_IO8(0xFFFFA97Du)   /* u8 rotor-sync step source          */
#define RAM_A974  RX8_IO8(0xFFFFA974u)   /* u8 rotor position counter          */
#define RAM_A98A  RX8_IO8(0xFFFFA98Au)   /* u8 previously latched mode         */
#define RAM_A98D  RX8_IO8(0xFFFFA98Du)   /* u8 mode (written at entry)         */
#define RAM_A97F  RX8_IO8(0xFFFFA97Fu)   /* u8 waveform byte (conditional)     */
#define RAM_A969  RX8_IO8(0xFFFFA969u)   /* u8 gate flag A                     */
#define RAM_A96A  RX8_IO8(0xFFFFA96Au)   /* u8 gate flag B                     */
#define RAM_F746  RX8_IO16(0xFFFFF746u)  /* u16 stepper drive port (RMW)       */

/* ---- step pattern table, ROM 0x4ED5C (36 bytes; the ROM copies it to the
 * stack frame at entry via the 0x42B0 byte-copy leaf — behaviourally inlined
 * here as a compile-time constant, matching the lift) ---- */
static const uint8_t RX8_STEP_PATTERN[9][4] = {
    {1, 0, 0, 1}, {1, 0, 0, 0}, {1, 1, 0, 0}, {0, 1, 0, 0}, {0, 1, 1, 0},
    {0, 0, 1, 0}, {0, 0, 1, 1}, {0, 0, 0, 1}, {0, 0, 0, 0},
};

/* 0x4BBC — verified leaf (c/setRegister_REG_BIT_VAL.c and the sample
 * rx8_set_register_reg_bit_val.c): 16-bit RMW, `enable ? *reg |= mask :
 * *reg &= ~mask` (enable truncated to 16 bits by `extu.w` before the test).
 * Modelled on the host by the oracle; the emulator runs the real ROM bytes. */
extern void rx8_set_register_reg_bit_val(uint16_t *reg, uint16_t mask, int enable);

/* 0x18552 — OMP stepper waveform driver (mode dispatch + 4-phase port drive). */
void rx8_omp_stepper_waveform_driver(uint8_t mode)
{
    uint8_t step = RAM_STEP;                /* r5: captured at entry          */
    uint8_t a97d = RAM_A97D;                /* r12                            */
    uint8_t a974 = RAM_A974;                /* r6 address, read at each use   */
    uint8_t a98a = RAM_A98A;                /* r9: captured at entry          */
    int      wf_ok = 0;
    uint8_t  wf = 0;
    int      i;

    RAM_A98D = mode;                        /* 0x18580: latched at entry      */

    switch (mode) {
    case 0:                                 /* 0x18614: advance by 1          */
        step = (uint8_t)((step + 1) & 7);
        RAM_STEP = step;                    /* 0x1861A mov.b r0,@r14         */
        if ((step & 1) == 0 && a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 1:                                 /* 0x18642: rotor-sync advance    */
        if (step == 8) {
            step = (uint8_t)((a97d + 0xFF) & 7);    /* A97D source           */
            RAM_STEP = step;                /* 0x18652 (delay slot)          */
        } else {
            step = (uint8_t)((step + 0xFF) & 7);    /* decrement mod 8        */
            RAM_STEP = step;                /* 0x1865A                       */
            if (a974 == 1 && a98a != 4 &&
                (RAM_A969 == 1 || RAM_A96A == 1)) {
                wf_ok = 1;
                wf = 0;
            }
        }
        if ((step & 1) == 0 && a98a != 4 && a974 > 0) {
            wf_ok = 1;
            wf = (uint8_t)(0xFF + a974);    /* 0x186B4: low byte of 0xFF+A974 */
        }
        break;
    case 2:                                 /* 0x186B8                        */
        if (a98a == 4 || (step & 1) == 1) {
            step = (step == 8) ? (uint8_t)((a97d + 1) & 7)
                               : (uint8_t)((step + 1) & 7);
        } else {
            step = (uint8_t)((step + 2) & 7);
        }
        RAM_STEP = step;                    /* 0x186DC / 0x186E6             */
        if (a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 3:                                 /* 0x186FC                        */
        if (a98a == 4 || (step & 1) == 1) {
            if (step == 8) {
                step = (uint8_t)((a97d + 0xFF) & 7);
                RAM_STEP = step;            /* 0x18792 (via 0x1871A delay)   */
            } else {
                step = (uint8_t)((step + 0xFF) & 7);
                RAM_STEP = step;            /* 0x1872E                       */
                if (a974 == 1 && a98a != 4) {
                    wf_ok = 1;
                    wf = 0;
                }
            }
        } else {
            step = (uint8_t)((step + 0xFE) & 7);    /* decrement by 2 mod 8  */
            RAM_STEP = step;                /* 0x18752                       */
            if (a974 > 0) {
                wf_ok = 1;
                wf = (uint8_t)(0xFF + a974);
            }
        }
        break;
    case 4:                                 /* 0x18766                        */
        if (step == 8) {
            step = a97d;
            RAM_STEP = step;                /* 0x18770 mov.b r12,@r14        */
        } else if ((step & 1) == 0) {
            step = (uint8_t)((step + 1) & 7);
            RAM_STEP = step;                /* 0x18780                       */
            RAM_A97D = step;                /* 0x18786 (re-read, then store) */
        } else {
            step = 8;
            RAM_STEP = step;                /* 0x1878E mov.b r1,@r14         */
        }
        break;
    case 6:                                 /* 0x18790                        */
        step = 8;
        RAM_STEP = step;                    /* 0x18792                       */
        break;
    default:                                /* 0x185C2: modes 5, 7..255       */
        break;                              /* step unchanged, NOT re-stored  */
    }

    RAM_A98A = mode;                        /* 0x18796                        */
    if (wf_ok)
        RAM_A97F = wf;

    /* 4-phase port drive, 0x187A8..0x1882C: pattern byte == 1 -> set bit.
     * (The ROM brackets every call with setSR_PARAM(0x2054)/setSR(0x2064)
     * pairs holding value 0xE0 — SR-only, stubbed here, see the header.)
     * NOTE: the ROM indexes the 36-byte table as `table[step * 4 + i]`; a
     * step >= 9 (only reachable via the mode-4 A97D source or the default
     * path) reads past the copied table into the never-written stack frame,
     * which is 0x00 on the emulator — reproduced by the clamp below. */
    for (i = 0; i < 4; i++) {
        uint8_t phase = (step <= 8) ? RX8_STEP_PATTERN[step][i] : 0;
        rx8_set_register_reg_bit_val((uint16_t *)&RAM_F746,
                                     (uint16_t)(1u << i), phase == 1);
    }
}
