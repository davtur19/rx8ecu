/*
 * =============================================================================
 * rx8_set_sr.c  —  STATUS REGISTER WRITE (setSR / IPL RESTORE)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3934
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_set_sr.py (host-gcc vs
 *               tools/sh2emu.py over random SR values, on both the fast path
 *               and the OS-detour path), in addition to the existing
 *               c/tests/test_setSR_getSR.py entry (20000 random, 0 errors).
 * Lift (truth): c/setSR.c  (same address; hand-annotated Ghidra RE by
 *               equinox311, program 60E1D400).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * setSR is the single most-called leaf in the firmware (166 call sites).  It is
 * the SR-restore half of the interrupt-masking critical-section layer that
 * protects every redundant-memory access in the ECU: a caller raises the IPL
 * with getSR (0x3920) / setSR_PARAM (0x2054), does exclusive work, then hands
 * the saved SR value back to setSR to restore it.  Getting the write behaviour
 * exactly right pins down the layer for all 166 callers.
 *
 * ROM PATH (bytes at 0x3934..0x394A, SH-2 big-endian)
 * ----------------------------------------------------
 *     0x3934: 2448  tst   r8,r4           ; T = (r4 & r8) == 0
 *     0x3936: 8B07  bf    0x3948          ; (r8 == 0 at the call sites -> never taken)
 *     0x3938: D504  mov.l @(0x394C),r5    ; r5 = *(0x394C) = 0xFFFF72B0 (kernel struct ptr)
 *     0x393A: 5656  mov.l @(24,r5),r6     ; r6 = *(r5 + 24)   (kernel state block)
 *     0x393C: 8461  mov.b @(1,r6),r0      ; r0 = *(r6 + 1)    (scheduler-initialized flag)
 *     0x393E: 8801  cmp/eq #1,r0          ; T = (flag == 1)
 *     0x3940: 8902  bt    0x3948          ; flag == 1 -> fast path
 *     0x3942: D603  mov.l @(0x3950),r6    ; r6 = *(0x3950) = 0x3DB0 (OS task-switch)
 *     0x3944: 462B  jmp   @r6             ; tail-call the OS task-switch handler
 *     0x3946: 440E  ldc   r4,sr           ; (jmp delay slot) SR = r4
 *     0x3948: 000B  rts                   ; return
 *     0x394A: 440E  ldc   r4,sr           ; (rts delay slot) SR = r4
 *
 * The `ldc r4,sr` ALWAYS executes — either in the delay slot of the `rts`, or
 * in the delay slot of the `jmp` to the OS handler.  The observable contract is
 * therefore simply:  SR := r4.  The OS-detour only decides whether the ROM does
 * task-switch bookkeeping first; it never changes the SR outcome (verified
 * in-emulator: the 0x3DB0 early-exit path leaves SR untouched).
 *
 * HARDWARE NOTE
 * -------------
 * On the SH-2, `ldc Rn,SR` is privileged and writes the full 32-bit value into
 * SR; this firmware runs privileged at all times.  Bits 7-4 hold the interrupt
 * priority level (IPL 0-15); bits 1 (T) and 2 (S) are the condition-code and
 * saturation sticky bits.  On real silicon an `ldc` can only RAISE the hardware
 * interrupt mask — the software convention (getSR/setSR_PARAM) layers the
 * raise-only guarantee on top.  For the emulator and this host model SR is a
 * plain 32-bit register: `ldc` writes it verbatim (no bit masking).
 *
 * The host model below keeps SR in a file-scoped variable (the target has no
 * C-visible SR — `ldc` is the only writer).  The test hooks rx8_sr_read /
 * rx8_sr_write / rx8_set_sr_scheduler_flag exist purely for the equivalence
 * harness; on the target this function compiles to the single `ldc r4,sr`.
 * =============================================================================
 */
#include <stdint.h>
#include <stdbool.h>
#include "rx8_samples.h"

/* ------------------------------------------------------------------ */
/*  Host model of the SH-2 Status Register (SR).                       */
/*  Power-on reset default per the SH7055 hardware manual: IPL = 15,   */
/*  MD = 1, BL = 1, RB = 1  ->  0x000000F0.                            */
/* ------------------------------------------------------------------ */
static uint32_t _rx8_sr = 0x000000F0u;

void rx8_sr_write(uint32_t sr_value)
{
    _rx8_sr = sr_value;
}

uint32_t rx8_sr_read(void)
{
    return _rx8_sr;
}

/* ------------------------------------------------------------------ */
/*  OS scheduler flag — in the ROM this is a byte inside a kernel      */
/*  structure anchored at 0xFFFF72B0:  flag = *((*(0xFFFF72B0)) + 24)  */
/*  + 1.  For host testing it is modelled as a simple boolean (default: */
/*  scheduler up -> the ROM takes the fast path).                      */
/* ------------------------------------------------------------------ */
static bool _scheduler_initialized = true;

void rx8_set_sr_scheduler_flag(bool initialized)
{
    _scheduler_initialized = initialized;
}

/* ------------------------------------------------------------------ */
/*  rx8_set_sr — write a value to the Status Register (restore IPL).   */
/*  SR := r4 unconditionally; the branch below only mirrors the ROM's  */
/*  OS-detour decision (tail-call to 0x3DB0 when restoring IPL 0       */
/*  before the RTOS is up).  Both arms converge on the same `ldc`.     */
/* ------------------------------------------------------------------ */
void rx8_set_sr(uint32_t sr_value)
{
    if (sr_value == 0u && !_scheduler_initialized) {
        /* r4 == 0 + scheduler not yet started: the ROM tail-calls the OS
         * task-switch handler at 0x3DB0 (jmp @r6).  The `ldc r4,sr` in its
         * delay slot fires first, so SR still ends up 0. */
        rx8_sr_write(sr_value);
        return;
    }
    /* Common path — SR = r4 (`ldc r4,sr`, delay slot of the rts). */
    rx8_sr_write(sr_value);
}
