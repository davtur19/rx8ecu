/* calc_idle_speed_target.c
 *
 * ROM: 60E1D400  |  Address: 0x12F5E  |  Size: 274 bytes
 *
 * Idle speed target calculation — determines the target engine
 * speed for idle control based on engine operating conditions.
 *
 * The target RPM is computed from:
 *   - Coolant temperature (primary input)
 *   - Engine running state
 *   - Rotor enable status
 *   - Adaptive learning state
 *   - AC/load compensation flags
 *
 * This feeds into the idle speed control loop (idle_speed_control_18054)
 * which adjusts the IACV (Idle Air Control Valve) to achieve this target.
 */

#include <stdint.h>

/* ========================================================================
 * RAM variables
 * ======================================================================== */
#define RAM_ROTOR_A_STATUS          (*(volatile uint8_t *)0xFFFFA444)
#define RAM_ROTOR_B_STATUS          (*(volatile uint8_t *)0xFFFFA445)
#define RAM_ENGINE_RPM_RAW          (*(volatile uint16_t*)0xFFFFA424)
#define RAM_ENGINE_RUNNING_FLAG     (*(volatile uint8_t *)0xFFFFC600)
#define RAM_CLOSED_LOOP_ACTIVE      (*(volatile uint8_t *)0xFFFFAADA)
#define RAM_COOLANT_TEMP            (*(volatile float   *)0xFFFFC12C)
#define RAM_COOLANT_TEMP_ALT        (*(volatile float   *)0xFFFFC128)
#define RAM_IDLE_SPEED_ADAPTIVE     (*(volatile float   *)0xFFFFA680)
#define RAM_IDLE_SPEED_TARGET       (*(volatile float   *)0xFFFFA678)
#define RAM_TARGET_INC_FLAG         (*(volatile uint8_t *)0xFFFFA68F)
#define RAM_IDLE_STATE_FLAG_A       (*(volatile uint8_t *)0xFFFFA6A9)
#define RAM_IDLE_STATE_FLAG_B       (*(volatile uint8_t *)0xFFFFA6AA)

/* Calibration constants */
#define CAL_RPM_IDLE_THRESHOLD      (*(const uint16_t*)0x00072BC0)  /* RPM threshold for idle detection */

/* External helpers */
extern float sensor_range_check_3ED0C(float a, float b);
extern float fpu_mul_float(float a, float b);       /* 0x23E4, verified in test */
/* sensor_range_check @ 0x3ED0C: validates and normalizes sensor readings.
 *   if b == 0: return range constant (positive or negative based on a)
 *   else: return a / b
 */

/* ========================================================================
 * calc_idle_speed_target
 *
 * Computes the target idle speed as a function of coolant temperature
 * and engine state.
 *
 * Algorithm:
 *   1. Check engine running state and rotor enable
 *   2. If not running or rotor disabled: set target to 0 (fldi0)
 *   3. Check RPM above threshold and closed-loop status
 *   4. Compute target = sensor_range_check(coolant_temp_diff, some_ref)
 *      where coolant_temp_diff = COOLANT_TEMP_ALT - COOLANT_TEMP
 *   5. Apply adaptive learning (idle speed adaptive accumulator)
 *   6. Update state flags for persistence
 *
 * The idle target is stored to RAM_IDLE_SPEED_TARGET (0xFFFFA678).
 * ======================================================================== */
void calc_idle_speed_target(void)
{
    uint8_t  rotor_a;
    uint8_t  rotor_b;
    uint16_t rpm_raw;
    uint8_t  engine_running;
    uint8_t  closed_loop;
    float    coolant_temp_main;
    float    coolant_temp_alt;
    float    idle_target;
    float    adaptive_val;

    /* ---- Phase 1: Read inputs ---- */
    rotor_a        = RAM_ROTOR_A_STATUS;        /* 0xFFFFA444 */
    rotor_b        = RAM_ROTOR_B_STATUS;        /* 0xFFFFA445 */
    rpm_raw        = RAM_ENGINE_RPM_RAW;        /* 0xFFFFA424 */
    engine_running = RAM_ENGINE_RUNNING_FLAG;   /* 0xFFFFC600 */
    closed_loop    = RAM_CLOSED_LOOP_ACTIVE;    /* 0xFFFFAADA */

    /* ---- Phase 2: Check enable conditions ---- */
    if (engine_running != 0) {
        /* Engine not running — zero target */
        idle_target = 0.0f;  /* fr15 = fldi0 */
        goto store_target;
    }

    /* Check RPM above idle threshold */
    {
        uint16_t rpm_threshold = CAL_RPM_IDLE_THRESHOLD;
        if (rpm_raw < rpm_threshold) {
            /* RPM too low for idle control — zero target */
            idle_target = 0.0f;
            goto store_target;
        }
    }

    /* Check closed-loop active */
    if (closed_loop != 0) {
        /* Not in closed loop — zero target */
        idle_target = 0.0f;
        goto store_target;
    }

    /* ---- Phase 3: Compute idle target from coolant temperature ---- */
    {
        coolant_temp_main = RAM_COOLANT_TEMP;      /* 0xFFFFC12C */
        coolant_temp_alt  = RAM_COOLANT_TEMP_ALT;  /* 0xFFFFC128 */
        float temp_diff;
        
        /* Compute temperature difference */
        temp_diff = coolant_temp_alt - coolant_temp_main;  /* fr4 = fr4 - fr5 */

        /* Call sensor_range_check to normalize/validate the temperature signal */
        /* sensor_range_check_3ED0C(fr4=temp_diff, fr5=coolant_temp_main) */
        /* Returns a validated temperature-based idle speed target */
        idle_target = sensor_range_check_3ED0C(temp_diff, coolant_temp_main);
        
        /* Store to idle target register */
        RAM_IDLE_SPEED_TARGET = idle_target;  /* 0xFFFFA678 */
    }

store_target:
    /* ---- Phase 4: Persist state ---- */
    {
        uint8_t state_flag_a = RAM_IDLE_STATE_FLAG_A;  /* 0xFFFFA6A9 */
        uint8_t state_flag_b = RAM_IDLE_STATE_FLAG_B;  /* 0xFFFFA6AA */
        uint8_t inc_flag     = RAM_TARGET_INC_FLAG;    /* 0xFFFFA68F */
        
        /* If state_flag_a == 1 AND rotor_a == 0:
         *   target increment = read from calibration table at 0x72BBB
         *   write to RAM_TARGET_INC_FLAG
         * Else if state_flag_b == 1 AND rotor_b != 0:
         *   (continue from existing value)
         * Else:
         *   If inc_flag > 0: increment by 0xFF (saturation counter)
         */
        
        if (state_flag_a == 1 && rotor_a == 0) {
            /* Load increment value from calibration table */
            uint8_t inc_val = *(const uint8_t *)0x00072BBB;
            RAM_TARGET_INC_FLAG = inc_val;  /* write to 0xFFFFA68F */
        } else if (state_flag_b == 1 && rotor_b == 0) {
            /* CORRECTED (verified 0x1300C bf/s -> falls to 0x13010): the B branch
             * mirrors the A branch — state_flag_b==1 AND rotor_b==0 also stores
             * the calibration byte.  The original lift had `rotor_b != 0`, which
             * the disassembly does not support. */
            uint8_t inc_val = *(const uint8_t *)0x00072BBB;
            RAM_TARGET_INC_FLAG = inc_val;
        } else {
            /* Normal path: decrement the idle target counter (saturating at 0) */
            if (inc_flag > 0) {
                RAM_TARGET_INC_FLAG = inc_flag - 1;  /* add #0xFF == -1 */
            }
        }
    }

    /* ---- Phase 5: Adaptive idle speed learning ---- */
    {
        uint8_t count = RAM_TARGET_INC_FLAG;  /* 0xFFFFA68F */
        
        if (count > 0) {
            /* Apply adaptive learning (verified 0x13036..0x13040):
             *   new_adaptive = fpu_mul_float(0x23E4, fr4=adaptive, fr5=target)
             * The helper 0x23E4 is a real ROM FPU routine (replayed in the test
             * harness via a second emulator instance); it computes fr0 from the
             * two float args and the result is stored back to RAM_ADAPTIVE.
             */
            float idle_tgt  = RAM_IDLE_SPEED_TARGET;   /* 0xFFFFA678 */
            float adaptive  = RAM_IDLE_SPEED_ADAPTIVE;  /* 0xFFFFA680 */
            RAM_IDLE_SPEED_ADAPTIVE = fpu_mul_float(adaptive, idle_tgt);
        } else {
            /* Check if adaptive value needs to be zeroed */
            float val1 = *(volatile float *)0xFFFFA670;  /* 0xA670 */
            float val2 = *(volatile float *)0xFFFFA674;  /* 0xA674 */
            
            /* Only zero adaptive if both values are non-positive */
            if (!(0.0f < val1) && !(0.0f < val2)) {
                /* Both values <= 0 — zero adaptive */
                RAM_IDLE_SPEED_ADAPTIVE = 0.0f;  /* fr15 (which is 0) */
            }
        }
    }

    /* ---- Phase 6: Save rotor state flags ---- */
    RAM_IDLE_STATE_FLAG_A = rotor_a;  /* 0xFFFFA6A9 */
    RAM_IDLE_STATE_FLAG_B = rotor_b;  /* 0xFFFFA6AA */
}
