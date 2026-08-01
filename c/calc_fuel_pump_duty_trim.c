/* calc_fuel_pump_duty_trim.c
 *
 * ROM: 60E1D400  |  Address: 0x135F6  |  Size: 92 bytes
 *
 * Fuel pump duty cycle trim calculation.
 * Called from engineControlCalculateTiming Phase 2.
 *
 * Computes the pump duty cycle trim based on operating mode (calibration byte
 * stored at ROM 0x6E430):
 *   Mode 0: Default — copies a calibration float to the output.
 *   Mode 1: Active trim — base + VAL_A + VAL_B  (front channel)
 *                         base + VAL_C + VAL_D  (rear channel)
 *   Mode 2: Safe mode — loads hardcoded values from ROM calibration constants.
 *
 * NOTE: The "mode" byte is stored in ROM (0x6E430), meaning it is a fixed
 * calibration-time selection, not a runtime variable.  The stock ROM uses mode 0.
 *
 * EMULATOR VERIFIED: All three modes tested against sh2emu.py.
 *
 * RAM address map (60E1D400, confirmed via literal pool analysis):
 *   0xFFFFA6F4 = base duty cycle (input, also used as temp output in mode 0)
 *   0xFFFFA6FC = VAL_A (mode 1 front comp 1)
 *   0xFFFFA70C = VAL_B (mode 1 front comp 2)
 *   0xFFFFA700 = VAL_C (mode 1 rear comp 1)
 *   0xFFFFA710 = VAL_D (mode 1 rear comp 2)
 *   0xFFFFA6E4 = front channel duty output
 *   0xFFFFA6E8 = rear channel duty output
 */

#include <stdint.h>

/* ========================================================================
 * RAM variables (confirmed addresses)
 * ======================================================================== */

/* Base duty cycle value (before trim). Read by all active modes. */
#define RAM_PUMP_BASE_DUTY      (*(volatile float *)0xFFFFA6F4)

/* Mode 1 compensation inputs */
#define RAM_COMP_VAL_A          (*(volatile float *)0xFFFFA6FC)   /* front comp 1 */
#define RAM_COMP_VAL_B          (*(volatile float *)0xFFFFA70C)   /* front comp 2 */
#define RAM_COMP_VAL_C          (*(volatile float *)0xFFFFA700)   /* rear comp 1 */
#define RAM_COMP_VAL_D          (*(volatile float *)0xFFFFA710)   /* rear comp 2 */

/* Outputs */
#define RAM_DUTY_FRONT          (*(volatile float *)0xFFFFA6E4)   /* front channel output */
#define RAM_DUTY_REAR           (*(volatile float *)0xFFFFA6E8)   /* rear channel output */

/* Mode 0 calibration constant source address */
#define RAM_MODE0_CAL_SRC       (*(volatile float *)0xFFFFA63C)   /* cal constant copied to output */

/* ========================================================================
 * Calibration ROM constants
 * ======================================================================== */

/* Mode selector byte (stored in ROM — fixed calibration parameter) */
#define CAL_MODE_BYTE           (*(const uint8_t *)0x0006E430)

/* Safe/default duty cycle values (loaded in mode 2) */
#define CAL_SAFE_FRONT          (*(volatile float *)0x0006E438)
#define CAL_SAFE_REAR           (*(volatile float *)0x0006E43C)

/* ========================================================================
 * calc_fuel_pump_duty_trim
 *
 * Compute fuel pump duty cycle trim based on the calibration mode byte.
 *
 * The mode byte at ROM 0x6E430 selects the trim strategy:
 *   0: Default — copy calibration float from RAM 0xFFFFA63C to base duty addr
 *   1: Active — compute trim as base + comp_A + comp_B (front) and
 *               base + comp_C + comp_D (rear), store to dedicated outputs
 *   2: Safe — store ROM calibration defaults to front and rear outputs
 * ======================================================================== */
void calc_fuel_pump_duty_trim(void)
{
    uint8_t mode;

    /* ---- Read operating mode (from ROM calibration byte) ---- */
    mode = CAL_MODE_BYTE;

    /* ---- Mode 0: Default (copy calibration constant to output) ---- */
    if (mode == 0) {
        RAM_PUMP_BASE_DUTY = RAM_MODE0_CAL_SRC;
    }

    /* ---- Mode 1: Active trim ---- */
    if (mode == 1) {
        float base = RAM_PUMP_BASE_DUTY;

        /* Front channel: base + VAL_A + VAL_B */
        RAM_DUTY_FRONT = base + RAM_COMP_VAL_A + RAM_COMP_VAL_B;

        /* Rear channel: base + VAL_C + VAL_D */
        RAM_DUTY_REAR = base + RAM_COMP_VAL_C + RAM_COMP_VAL_D;
    }

    /* ---- Mode 2: Safe defaults from ROM calibration ---- */
    if (mode == 2) {
        RAM_DUTY_FRONT = CAL_SAFE_FRONT;
        RAM_DUTY_REAR  = CAL_SAFE_REAR;
    }
}

/* ========================================================================
 * NOTES:
 *
 * 1. MODE IS IN ROM — The mode byte is stored at 0x0006E430 (ROM),
 *    making it a fixed calibration-time selection.  The stock ROM
 *    value is 0x00 (mode 0).  Tuners could change this byte.
 *
 * 2. THREE MODES — The function implements three distinct strategies,
 *    selected by the mode byte.  Modes are NOT mutually exclusive in
 *    code (mode 0 path is independent of mode 1/2 checks), but in
 *    practice only one mode byte value is set.
 *
 * 3. STRUCTURAL TWIN — calc_evap_purge_duty (0x13652) is nearly
 *    identical, sharing the same code pattern (mode check → three
 *    paths with fmov.s/fadd sequences).
 *
 * 4. EMULATOR VERIFICATION — All three modes verified against
 *    sh2emu.py with known RAM values.  See test results:
 *      Mode 0: copies float from 0xFFFFA63C → 0xFFFFA6F4  ✓
 *      Mode 1: base + 10 + 5 = 65 @ front, base + 8 + 3 = 61 @ rear  ✓
 *      Mode 2: reads ROM defaults from 0x6E438/0x6E43C  ✓
 *
 * 5. UNITS — Duty cycle values are floats.  Likely 0-100 range
 *    (percent) or 0-1 (normalized), to be confirmed runtime.
 * ======================================================================== */

/* ========================================================================
 * NOTES:
 *
 * 1. MODE SELECTION — The mode byte at RAM_PUMP_MODE is checked
 *    sequentially in the ROM (not a switch/jump table).  Modes are
 *    not mutually exclusive in code — mode 0 only runs its path and
 *    falls through to mode 1 check.  In practice, the mode flag should
 *    have only one value at a time.
 *
 * 2. STRUCTURAL PARALLEL — calc_evap_purge_duty (0x13652) is nearly
 *    identical in structure (same mode checks, same three paths,
 *    same sequence of fmov.s/fadd instructions).  The two functions
 *    likely share a common code generation pattern or template.
 *
 * 3. UNITS — The duty cycle values are floats.  Likely range is
 *    0.0 to 1.0 (representing 0-100% PWM duty), or possibly
 *    0.0 to 100.0.  Need runtime confirmation.
 *
 * 4. ROTOR CHANNELS — "Front" and "Rear" channels may correspond
 *    to the two fuel pump stages (low speed / high speed) rather
 *    than per-rotor pump control.  The RX-8 has a single in-tank
 *    fuel pump with PWM speed control.
 *
 * 5. CALIBRATION CONSTANTS — The ROM address literals used for
 *    loading compensation values:
 *      CAL_LOAD_COMP_FRONT  → loaded from 0x???? (ROM address)
 *      CAL_RPM_COMP_FRONT   → loaded from 0x???? (ROM address)
 *      etc.
 *    These need to be confirmed by cross-referencing with
 *    cal_tables.csv and the actual ROM binary.
 *
 * 6. The function does not clamp the output — duty cycle limiting
 *    happens elsewhere (in calc_fuel_pump_control_output or the
 *    PWM generation function).
 * ======================================================================== */
