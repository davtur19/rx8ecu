/*
 * =============================================================================
 * rx8_idle_speed_control.c  —  IDLE-SPEED STATE MACHINE + IACV DUTY RAMP
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x18054  (size 0x194 bytes, to 0x181E8)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_idle_speed_control.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + 20000 random
 *               vectors; every RAM side-effect compared byte-for-byte).
 * Lift (truth): c/idle_speed_control_18054.c (same address, same behaviour;
 *               re-verified against the 60E1D400.bin bytes here).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The PCM "idle speed control" task.  Despite being grouped with the PID
 * controllers, it contains NO Kp/Ki/Kd math: it is a fixed-step IACV duty
 * ramper plus a two-path mode/flag state machine for the idle air control
 * valve.  Every invocation bumps the u16 duty by +1 (saturating at 0xFFFF)
 * through the leaf add16bitSaturate @0x2460, clears the duty to 0 on the
 * idle-enable re-entry transition, and publishes a set of mode flags.
 *
 * ROM path (60E1D400.bin @0x18054), in brief:
 *
 *     push r8-r14/pr ; add #0xE4,r15       ; frame; r14=0, r12=1, r10=r9=0
 *     r7 = RAM[0xFFFFA428]                 ; engine-state / TPS-low byte
 *     stack[8]=RAM[0xFFFFAAE0]             ; mode select
 *     r4 = RAM[0xFFFFA979]                 ; AC compressor request
 *     r8 = RAM[0xFFFFA998]                 ; engine-running flag
 *     stack[12]=RAM[0xFFFFA978]            ; load compensation
 *     stack[24]=stack[20]=0                ; f24 (idle-active), f20 (feedback)
 *     stack[4] = RAM[0xFFFFA96C]           ; idle-enable (prev duty gate)
 *     stack[16]= RAM[0xFFFFA96A]           ; saved status (old)
 *     r13 = idle_en ; r11 = &RAM[0xFFFFA96E]  (duty word)
 *     if (state==0 && mode==1):            ; path A: AC/load idle
 *         stack[24]=1 ; RAM[0xFFFFA979]=0 ; RAM[0xFFFFA975]=2 ; goto store
 *     if (state==1 && ac==0 && !running):  ; path B: single-rotor no-load
 *         stack[20]=1 ; goto store
 *     else:                                ; fall-through
 *         if (ac==1) r9=1                  ; AC latch
 *         if (mode==0 && r9==1 && !running
 *             && check_pair_3ED3C(0x807C,0)==0) r10=1   ; status
 *         if (r10==0 && !load_comp && RAM[0xFFFFA970]==1) r13=1
 *         if (idle_en_orig==0 && r13==1) RAM[0xFFFFA96E]=0  ; re-entry kick
 *     store: RAM[0xFFFFA96B]=stack[24]     ; idle-active
 *            RAM[0xFFFFA968]=stack[20]     ; feedback
 *            RAM[0xFFFFA969]=r9            ; AC latch
 *            RAM[0xFFFFA96A]=r10           ; status
 *     duty = RAM[0xFFFFA96E]               ; (re-read after the kick write)
 *     fcmp/gt O2,fuelcut -> T = (fuelcut > O2)   ; -40.0 vs RAM[0xFFFFAA10]
 *     if (fuelcut > O2) { if (duty >= ROM16[0x78E44]) r13=0 }   ; thr 500
 *     else              { if (duty >= ROM16[0x78E42]) r13=0 }   ; thr 156
 *     RAM[0xFFFFA96C]=r13 ; RAM[0xFFFFA96E]=add16bitSaturate(duty,1)
 *     RAM[0xFFFFA970]=load_comp
 *     if (old_status==0 && RAM[0xFFFFA96A]==1) osTaskScheduler(0,2) ; @0x9668
 *
 * CALLING CONVENTION
 * ------------------
 * void task (no ABI arguments, no return value): everything flows through the
 * on-chip RAM window and the three shared leaves, which are declared extern
 * here exactly as in the lift:
 *
 *   check_pair_3ED3C @0x3ED3C : r4=addr, r5=fallback -> r0
 *       = RAM[addr] if RAM[addr]==~RAM[addr+1], else fallback & 0xFF.  On the
 *       fallback path the ROM also writes RAM[0xFFFFC6AC]=1 (via 0x3F050)
 *       before restoring SR — a side-effect the lift's comment does not call
 *       out but which this port mirrors (see the oracle's implementation).
 *       The stock byte pair at 0x807C/0x807D is 0x24/0x62 (never
 *       complementary), so the call ALWAYS takes the fallback -> returns 0
 *       and sets RAM[0xFFFFC6AC]=1; the status path is deterministic.
 *   add16bitSaturate @0x2460 : r4=a, r5=b -> r0 = min(a+b, 0xFFFF)
 *   osTaskScheduler  @0x9668 : r4=task, r5=slot, r6=sp; posts the idle task
 *       (slot 2 of the ROM's task table); performs no writes to the RAM
 *       cells this function publishes.
 *
 * FP EXACTNESS
 * ------------
 * The only floating-point work is a single `fcmp/gt` (ROM 0x1817A) selecting
 * the duty ceiling: T = (cal_o2_fuelcut > O2).  `fcmp/gt` is a strict
 * IEEE-754 comparison, so a NaN O2 makes the comparison false and selects the
 * high ceiling (156) — exactly what the C `>` yields.  No arithmetic, so no
 * rounding concerns.
 *
 * NOTE ON RAM[0xFFFFA428]: SENSOR_PIPELINE.md identifies it as the TPS
 * processed ADC (u16; this function reads its low byte); AUXILIARY_CONTROL_
 * SUBSYSTEM.md calls it the engine-state byte (0=running, 1=starting).  The
 * behaviour below is byte-exact regardless of interpretation.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- on-chip RAM window cells (0xFFFF6000..0xFFFFDFFF) ---- */
#define RAM_STATE_BYTE       RX8_IO8(0xFFFFA428)  /* engine-state / TPS low   */
#define RAM_MODE_SELECT      RX8_IO8(0xFFFFAAE0)  /* 0=normal, 1=AC/load      */
#define RAM_AC_REQUEST       RX8_IO8(0xFFFFA979)  /* AC compressor request    */
#define RAM_ENGINE_RUNNING   RX8_IO8(0xFFFFA998)  /* engine-running flag      */
#define RAM_LOAD_COMP        RX8_IO8(0xFFFFA978)  /* load-compensation flag   */
#define RAM_IDLE_ACTIVE_OUT  RX8_IO8(0xFFFFA96B)  /* out: idle-active (f24)   */
#define RAM_FEEDBACK_OUT     RX8_IO8(0xFFFFA968)  /* out: feedback (f20)      */
#define RAM_AC_LATCH_OUT     RX8_IO8(0xFFFFA969)  /* out: AC latch (r9)       */
#define RAM_STATUS_OUT       RX8_IO8(0xFFFFA96A)  /* in: old / out: status    */
#define RAM_IDLE_ENABLE_OUT  RX8_IO8(0xFFFFA96C)  /* in/out: idle-enable      */
#define RAM_IACV_DUTY        RX8_IO16(0xFFFFA96E) /* IACV duty (u16, ramped)  */
#define RAM_LEARN_COUNTER    RX8_IO8(0xFFFFA970)  /* learned/previous state   */
#define RAM_IACV_MODE_FLAG   RX8_IO8(0xFFFFA975)  /* set to 2 on path A       */
#define RAM_O2_VOLTAGE       (*(volatile float *)0xFFFFAA10) /* O2 (f32)      */

/* ---- calibration constants (literal pool of this function) ---- */
#define CAL_O2_FUELCUT       (*(const float   *)0x00078E64)   /* -40.0 */
#define CAL_DUTY_HIGH        (*(const uint16_t*)0x00078E42)   /*  156  */
#define CAL_DUTY_LOW         (*(const uint16_t*)0x00078E44)   /*  500  */

/* ---- shared leaves called via jsr (emulator runs the real ROM bytes) ----
 * check_pair_3ED3C  @0x3ED3C : returns RAM[addr] if RAM[addr]==~RAM[addr+1],
 *                    else fallback & 0xFF (and RAM[0xFFFFC6AC]=1 on that
 *                    fallback path — mirrored by the oracle's helper).
 * add16bitSaturate  @0x2460  : min(a+b, 0xFFFF).
 * osTaskScheduler   @0x9668  : post idle task (no writes to the cells here). */
extern uint32_t check_pair_3ED3C(uint32_t addr, uint32_t fallback);
extern uint16_t add16bitSaturate(uint16_t a, uint16_t b);
extern void     osTaskScheduler(uint32_t task_id, uint32_t arg);

/* 0x18054 — idle-speed state machine + IACV duty ramp. */
void rx8_idle_speed_control(void)
{
    uint8_t  state      = RAM_STATE_BYTE;
    uint8_t  mode       = RAM_MODE_SELECT;
    uint8_t  ac         = RAM_AC_REQUEST;
    uint8_t  running    = RAM_ENGINE_RUNNING;
    uint8_t  load_comp  = RAM_LOAD_COMP;
    uint8_t  idle_en    = RAM_IDLE_ENABLE_OUT;
    uint8_t  old_status = RAM_STATUS_OUT;
    uint8_t  f24 = 0, f20 = 0, r9 = 0, r10 = 0;
    uint8_t  r13 = idle_en;
    uint16_t duty;

    if (state == 0u && mode == 1u) {
        /* AC/load mode active: engage idle, clear AC, force mode=2. */
        f24 = 1;
        RAM_AC_REQUEST = 0;
        RAM_IACV_MODE_FLAG = 2;
        goto store;
    }
    if (state == 1u && ac == 0u && running == 0u) {
        /* single-rotor no-load: feedback path. */
        f20 = 1;
        goto store;
    }

    /* fall-through path */
    if (ac == 1u) r9 = 1;
    if (mode == 0u && r9 == 1u && running == 0u) {
        if (check_pair_3ED3C(0x807C, 0) == 0u) r10 = 1;
    }
    if (r10 == 0u && load_comp == 0u && RAM_LEARN_COUNTER == 1u) r13 = 1;
    if (idle_en == 0u && r13 == 1u) RAM_IACV_DUTY = 0;   /* re-entry kick */

store:
    RAM_IDLE_ACTIVE_OUT = f24;
    RAM_FEEDBACK_OUT    = f20;
    RAM_AC_LATCH_OUT    = r9;
    RAM_STATUS_OUT      = r10;

    duty = RAM_IACV_DUTY;                    /* re-read: kick may have cleared */

    /* duty-ceiling gate: r13 is cleared while duty is above the ceiling
     * selected by the O2 comparison (fcmp/gt: fuelcut > O2, strict — so a
     * NaN O2 keeps the high ceiling 156).  Stock cal: -40.0 / 156 / 500. */
    if (CAL_O2_FUELCUT > RAM_O2_VOLTAGE) {
        if (duty >= CAL_DUTY_LOW) r13 = 0;               /* duty >= 500  */
    } else {
        if (duty >= CAL_DUTY_HIGH) r13 = 0;              /* duty >= 156  */
    }

    RAM_IDLE_ENABLE_OUT = r13;
    RAM_IACV_DUTY = add16bitSaturate(duty, 1);           /* ramp +1 */
    RAM_LEARN_COUNTER = load_comp;

    if (old_status == 0u && RAM_STATUS_OUT == 1u) {
        osTaskScheduler(0, 2);                           /* post idle task */
    }
}
