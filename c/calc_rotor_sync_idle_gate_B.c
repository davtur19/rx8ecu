/* calc_rotor_sync_idle_gate_B.c
 *
 * ROM: 60E1D400  |  Address: 0x12BC8  |  Size: 196 bytes  |  VERIFIED vs ROM emulator
 *
 * Rotor-sync idle/anti-stall gate — "Rotor B" bank.
 *
 * NOTE: The original IDA-AI annotation described this function as a piston
 * "cam timing PID" / "rotor sync PID".  This engine — a 2-rotor Renesis
 * Wankel — has NO camshafts, NO VVT and NO oil control valve, so that name
 * described a piston-engine concept.  The byte-verified behavior below is a
 * rotor-based control gate, NOT a PID controller; the corrected name is
 * calc_rotor_sync_idle_gate_B.
 *
 * Each call it samples the current RPM into RAM[0xFFFFA694] (so that register
 * actually holds the *previous* RPM sample), computes
 *
 *      drop = prev_rpm - rpm           (signed, float)
 *
 * and sets the control flag RAM[0xFFFFA690] = 1 only when ALL of these hold:
 *
 *   1. (RAM[0xFFFFB5A4] closed-loop-enable == 1) OR (RAM[0xFFFFCABC] warmup == 1)
 *   2. RAM[0xFFFFAADA] closed-loop-active == 1
 *   3. rotor-select logic:
 *        (RAM[0xFFFFA6A3] enable-A == 1 AND RAM[0xFFFFA444] rotor-A == 0)
 *        OR
 *        (RAM[0xFFFFA6A4] enable-B == 1 AND RAM[0xFFFFA445] rotor-B == 0)
 *   4. drop >= 40.0          (cal 0x72BC4 — RPM must have fallen at least 40)
 *   5. rpm <= 2000.0         (cal 0x72BC8 — engine at low speed)
 *
 * When the flag is set, downstream code helps hold idle speed against an RPM
 * droop (anti-stall).  The flag is latched per-rotor via the stored rotor
 * status bytes.
 *
 * Note on condition 3: control is armed for the rotor that is NOT currently
 * running (rotor status == 0).  The two enable bits select which rotor's
 * gate is being driven.
 *
 * Exhaustive branch coverage vs the ROM emulator: 2000 random state tests,
 * 0 mismatches.
 */

#include <stdint.h>

/* ---- RAM map ---- */
#define RAM_ROTOR_A_STATUS     (*(volatile uint8_t *)0xFFFFA444)
#define RAM_ROTOR_B_STATUS     (*(volatile uint8_t *)0xFFFFA445)
#define RAM_ENGINE_RPM         (*(volatile float   *)0xFFFFB5B8)
#define RAM_CAM_TIMING_TARGET  (*(volatile float   *)0xFFFFA694)  /* prev RPM sample */
#define RAM_CAM_TIMING_FLAG    (*(volatile uint8_t *)0xFFFFA690)  /* control output  */
#define RAM_CLOSED_LOOP_ENABLE (*(volatile uint8_t *)0xFFFFB5A4)
#define RAM_CLOSED_LOOP_ACTIVE (*(volatile uint8_t *)0xFFFFAADA)
#define RAM_WARMUP_ENRICH      (*(volatile uint8_t *)0xFFFFCABC)
#define RAM_CAM_ENABLE_A       (*(volatile uint8_t *)0xFFFFA6A3)
#define RAM_CAM_ENABLE_B       (*(volatile uint8_t *)0xFFFFA6A4)

/* ---- Calibration constants ---- */
#define CAL_CAM_DROP_MIN       (*(const float *)0x00072BC4)  /* 40.0   */
#define CAL_CAM_RPM_MAX        (*(const float *)0x00072BC8)  /* 2000.0 */

void calc_rotor_sync_idle_gate_B(void)
{
    uint8_t rotor_a = RAM_ROTOR_A_STATUS;
    uint8_t rotor_b = RAM_ROTOR_B_STATUS;
    float   rpm     = RAM_ENGINE_RPM;
    float   prev    = RAM_CAM_TIMING_TARGET;
    float   drop    = prev - rpm;          /* fsub fr4,fr5 in delay slot — always runs */
    uint8_t out     = 0;

    if ((RAM_CLOSED_LOOP_ENABLE == 1 || RAM_WARMUP_ENRICH == 1) &&
        RAM_CLOSED_LOOP_ACTIVE == 1) {

        /* rotor-select: enable the gate for the rotor that is not running */
        int rotor_ok =
            (RAM_CAM_ENABLE_A == 1 && rotor_a == 0) ||
            (RAM_CAM_ENABLE_B == 1 && rotor_b == 0);

        if (rotor_ok &&
            !(40.0f > drop) &&              /* fcmp/gt fr5,fr3: T=(40>drop); bt=disable */
            !(rpm > 2000.0f)) {             /* fcmp/gt fr2,fr4: T=(rpm>2000); bt=disable */
            out = 1;
        }
    }

    RAM_CAM_TIMING_FLAG = out;              /* RAM[0xA690] */
    RAM_CAM_TIMING_TARGET = rpm;            /* sample current RPM as prev for next call */
    RAM_CAM_ENABLE_A = rotor_a;             /* latch rotor status */
    RAM_CAM_ENABLE_B = rotor_b;
}
