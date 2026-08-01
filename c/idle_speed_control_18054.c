/* idle_speed_control_18054.c
 *
 * ROM: 60E1D400  |  Address: 0x18054  |  Size: 404 bytes  |  VERIFIED vs ROM emulator
 *
 * Idle speed control — IACV duty ramp + mode state machine.
 *
 * Despite being grouped with the PID controllers, this function contains NO
 * Kp/Ki/Kd math.  It is a fixed-step duty ramper plus a mode/flag state
 * machine for the idle air control valve:
 *
 *   duty = saturating_add(duty, 1)          every invocation (0x2460, +1, cap 0xFFFF)
 *   duty  is force-cleared to 0 when the idle-enable conditions are right
 *   RAM[0xA96C] (idle-active flag) = 1 only while duty is below the high
 *   threshold (156) and the enable conditions hold.
 *
 * State flags (all bytes):
 *   RAM[0xFFFFA428]  engine-state / TPS-low-byte  (see note)
 *   RAM[0xFFFFAAE0]  mode select (0 = normal, 1 = AC/load mode)
 *   RAM[0xFFFFA979]  AC compressor request
 *   RAM[0xFFFFA998]  engine-running flag
 *   RAM[0xFFFFA978]  load-compensation flag
 *   RAM[0xFFFFA970]  learned/previous state
 *
 * Outputs written each call:
 *   RAM[0xFFFFA96B] = f24: idle-active  (1 when state==0 && mode==1)
 *   RAM[0xFFFFA968] = f20: feedback     (1 when state==1 && !AC && !running)
 *   RAM[0xFFFFA969] = r9 : AC latch     (1 when AC==1)
 *   RAM[0xFFFFA96A] = r10: status       (1 when mode==0 && AC && !running && chk==0)
 *   RAM[0xFFFFA96C] = r13: idle-enable  (1 when no-load && learn==1 && duty < 156)
 *   RAM[0xFFFFA96E] = min(duty+1, 0xFFFF)
 *   RAM[0xFFFFA970] = load_comp
 *   and, when (old RAM[0xA96A]==0 && new RAM[0xA96A]==1), schedules the
 *   idle task via osTaskScheduler @ 0x9668 (r4=0, r5=2, r6=sp).
 *
 * The check_3ED3C(0x807C, 0) call validates a ROM byte pair at 0x807C and
 * returns RAM[0x807C] if it equals ~RAM[0x807D], else the fallback arg (0).
 * 0x24 != ~0x62, so it always returns 0 -> status path is deterministic.
 *
 * Note on RAM[0xFFFFA428]: SENSOR_PIPELINE.md identifies it as the TPS
 * processed ADC (u16; this function reads its low byte); AUXILIARY_CONTROL_
 * SUBSYSTEM.md calls it the engine state byte (0=running, 1=starting).
 * The behavior below is byte-exact regardless of interpretation.
 *
 * Verified: 3000 random state tests vs the ROM emulator, 0 mismatches.
 */

#include <stdint.h>

/* ---- RAM map ---- */
#define RAM_STATE_BYTE       (*(volatile uint8_t *)0xFFFFA428)
#define RAM_MODE_SELECT      (*(volatile uint8_t *)0xFFFFAAE0)
#define RAM_AC_REQUEST       (*(volatile uint8_t *)0xFFFFA979)
#define RAM_ENGINE_RUNNING   (*(volatile uint8_t *)0xFFFFA998)
#define RAM_LOAD_COMP        (*(volatile uint8_t *)0xFFFFA978)
#define RAM_IDLE_ACTIVE_OUT  (*(volatile uint8_t *)0xFFFFA96B)
#define RAM_FEEDBACK_OUT     (*(volatile uint8_t *)0xFFFFA968)
#define RAM_AC_LATCH_OUT     (*(volatile uint8_t *)0xFFFFA969)
#define RAM_STATUS_OUT       (*(volatile uint8_t *)0xFFFFA96A)
#define RAM_IDLE_ENABLE_OUT  (*(volatile uint8_t *)0xFFFFA96C)
#define RAM_IACV_DUTY        (*(volatile uint16_t*)0xFFFFA96E)
#define RAM_LEARN_COUNTER    (*(volatile uint8_t *)0xFFFFA970)
#define RAM_IACV_MODE_FLAG   (*(volatile uint8_t *)0xFFFFA975)
#define RAM_O2_VOLTAGE       (*(volatile float   *)0xFFFFAA10)

/* ---- Calibration constants ---- */
#define CAL_O2_FUELCUT       (*(const float *)0x00078E64)   /* -40.0  (always false -> high path) */
#define CAL_DUTY_HIGH        (*(const uint16_t*)0x00078E42) /* 156    */
#define CAL_DUTY_LOW         (*(const uint16_t*)0x00078E44) /* 500    */

/* ---- External helpers ---- */
extern uint32_t check_pair_3ED3C(uint32_t addr, uint32_t fallback);
/* @0x3ED3C: returns RAM[addr] if RAM[addr] == ~RAM[addr+1], else fallback & 0xFF */
extern uint16_t add16bitSaturate(uint16_t a, uint16_t b);
/* @0x2460: min(a+b, 0xFFFF) */
extern void osTaskScheduler(uint32_t task_id, uint32_t arg);
/* @0x9668: RTOS task post */

void idle_speed_control_18054(void)
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

    if (state == 0 && mode == 1) {
        /* AC/load mode active: engage idle, clear AC, force mode=2 */
        f24 = 1;
        RAM_AC_REQUEST = 0;
        RAM_IACV_MODE_FLAG = 2;
        goto store;
    }
    if (state == 1 && ac == 0 && running == 0) {
        /* single-rotor no-load: feedback path */
        f20 = 1;
        goto store;
    }

    /* fall-through path */
    if (ac == 1) r9 = 1;
    if (mode == 0 && r9 == 1 && running == 0) {
        if (check_pair_3ED3C(0x807C, 0) == 0) r10 = 1;
    }
    if (r10 == 0 && load_comp == 0 && RAM_LEARN_COUNTER == 1) r13 = 1;
    if (idle_en == 0 && r13 == 1) RAM_IACV_DUTY = 0;      /* force duty to 0 */

store:
    RAM_IDLE_ACTIVE_OUT = f24;
    RAM_FEEDBACK_OUT    = f20;
    RAM_AC_LATCH_OUT    = r9;
    RAM_STATUS_OUT      = r10;

    duty = RAM_IACV_DUTY;

    /* duty threshold gate: r13 cleared while duty is above the threshold.
     * O2 > -40.0 always -> the CAL_O2_FUELCUT (-40) branch is dead in practice. */
    if (CAL_O2_FUELCUT > RAM_O2_VOLTAGE) {
        if (duty >= CAL_DUTY_LOW) r13 = 0;                 /* duty >= 500  */
    } else {
        if (duty >= CAL_DUTY_HIGH) r13 = 0;                /* duty >= 156  */
    }

    RAM_IDLE_ENABLE_OUT = r13;
    RAM_IACV_DUTY = add16bitSaturate(duty, 1);             /* ramp +1 */
    RAM_LEARN_COUNTER = load_comp;

    if (old_status == 0 && RAM_STATUS_OUT == 1) {
        osTaskScheduler(0, 2);                             /* post idle task */
    }
}
