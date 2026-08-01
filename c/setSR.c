/*
 * setSR  —  RX-8 PCM status-register restore @ ROM 0x3934
 *
 * Function name from the hand-annotated Ghidra RE by equinox311 (program 60E1D400).
 * 166 callers — the single most-called leaf in the firmware.
 *
 * Original SH-2 (big-endian):
 *     0x3934: tst   r4,r4              ; T = (r4 == 0)
 *     0x3936: bf    0x3948             ; if r4 != 0, skip the OS-state check
 *     0x3938: mov.l 0x394c,r5          ; r5 = *(0x394c)  (= 0xFFFF72B0, a kernel struct ptr)
 *     0x393A: mov.l @(24,r5),r6        ; r6 = *(r5 + 24)  (= kernel state block)
 *     0x393C: mov.b @(1,r6),r0         ; r0 = *(r6 + 1)   (= scheduler-initialized flag)
 *     0x393E: cmp/eq #1,r0             ; T = (flag == 1)
 *     0x3940: bt    0x3948             ; if flag == 1, also skip the callback
 *     0x3942: mov.l 0x3950,r6          ; r6 = *(0x3950)  (= 0x3DB0, OS task-switch handler)
 *     0x3944: jmp   @r6                ; call OS handler (delay slot: ldc r4,sr)
 *     0x3946: ldc   r4,sr              ; (delay-slot of jmp) SR = r4  (r4 == 0 here)
 *     0x3948: rts                      ; return
 *     0x394A: ldc   r4,sr              ; (delay-slot of rts) SR = r4
 *
 * Semantics: write r4 to the Status Register.  When r4 == 0 AND the real-time OS
 * scheduler has not yet been initialized (flag at an offset within a kernel structure
 * anchored at 0xFFFF72B0), an OS task-switch callback (0x3DB0) is invoked first.
 * The `ldc r4,sr` always executes — either in the delay slot of the `jmp` (which then
 * branches to the OS handler), or in the delay slot of `rts`.  The effect is always
 * SR := r4, with a possible detour through the scheduler when restoring to IPL 0 before
 * the OS is fully up.
 *
 * Hardware note: on SH-2, `ldc Rn,SR` is a privileged instruction that writes the full
 * 32-bit value into SR.  In this firmware the CPU runs in privileged mode at all times.
 * Bits 7–4 hold the interrupt-priority level (IPL, 0–15); bits 1 (T) and 2 (S) are the
 * condition-code and saturation sticky bits respectively.  Writing SR with an IPL lower
 * than the current hardware mask is a no-op on real silicon (the mask can only rise via
 * `ldc`), so the extra protection in getSR/setSR_PARAM is a software convention layered
 * on top of HW behaviour.
 *
 * Track A: verified via tools/sh2emu.py with SR modelled as a plain register —
 * stc/ldc read/write self.sr.  The callback at 0x3DB0 is NOT reproduced (it is an OS
 * task-switch that is irrelevant to the SR-setting behaviour when r4 != 0, and when
 * r4 == 0 in test context the pre-initialised flag is set so the fast path is taken).
 * See c/tests/test_setSR_getSR.py.
 */
#include <stdint.h>

/* ------------------------------------------------------------------ */
/*  Platform abstraction: the real function uses `ldc r4,sr`.          */
/*  These three accessors are the only functions that touch SR, so we  */
/*  keep the SR as a file-scoped variable when the C code runs on the  */
/*  host.  On real hardware the compiler should inline `ldc` via an    */
/*  intrinsic or inline asm.                                           */
/* ------------------------------------------------------------------ */
static uint32_t _sr = 0x000000F0;       /* power-on reset default */

static inline uint32_t read_sr(void)
{
    return _sr;
}

static inline void write_sr(uint32_t v)
{
    _sr = v;
}

/* ------------------------------------------------------------------ */
/*  OS scheduler flag access — the physical address 0xFFFF72B0 points  */
/*  to a kernel structure in SH-2 peripheral / RAM space.  For host    */
/*  testing we model it as a simple boolean.                           */
/* ------------------------------------------------------------------ */
static int _scheduler_initialized = 1;   /* default: skip the callback */

void setSR_scheduler_flag(int initialized)
{
    _scheduler_initialized = initialized;
}


/* ------------------------------------------------------------------ */
/*  setSR — write value to Status Register (restore IPL)              */
/* ------------------------------------------------------------------ */
void setSR(uint32_t sr_value)
{
    if (sr_value == 0 && !_scheduler_initialized) {
        /*
         * r4 == 0 + scheduler not yet up → real ROM calls 0x3DB0
         * (OS task-switch) before the ldc.  The ldc still fires
         * (delay slot), so SR ends up as 0 either way.
         */
        write_sr(sr_value);          /* ldc r4,sr */
        /* In the ROM this jumps to 0x3DB0 which does scheduling work */
        return;
    }
    /* Common path — r4 != 0, or scheduler already initialized */
    write_sr(sr_value);              /* ldc r4,sr (delay slot of rts) */
}
