/*
 * dtc_debounce_monitor_43760.c  —  RX-8 PCM DTC debounce monitor (0x043760)
 *
 * Implements the counters/flag ladder used by fault detection to turn a
 * raw condition into a confirmed (debounced) DTC.  Called once per task
 * cycle from extended_control_dispatcher_3a764.
 *
 * RAM map (backup-RAM / fault area):
 *   input:   0xFFFFB3C8  byte  condition under test (1 = fault active)
 *   input:   0xFFFFC9E8  byte  monitor enable
 *   input:   0xFFFFD201  byte  reset request (1 = zero everything)
 *   output:  0xFFFFC9EF  byte  flag 1 (counter B confirmed)
 *   output:  0xFFFFC9F0  byte  flag 2 (counter C confirmed)
 *   state:   0xFFFFC9FE  word  counter A (primary debounce counter)
 *   state:   0xFFFFCA00  word  counter B (secondary path)
 *   state:   0xFFFFCA02  word  counter C (secondary path)
 *   state:   0xFFFFC9E4  float accumulated value (calibration gate)
 *   state:   0xFFFFAAF0  float runtime value (calibration gate)
 *
 * ROM calibration constants:
 *   0x0007D97C word  157   counter-A threshold
 *   0x0007D978 word   16   counter-B flag threshold
 *   0x0007D97A word    4   counter-C flag threshold
 *   0x0007D984 float 17000.0  upper accumulated-value gate
 *   0x0007D988 float   500.0  runtime-value gate
 *
 * Logic (as executed by the ROM, verified Track-A):
 *   if (reset)                       -> zero all counters/flags; return
 *   if (enable && cond &&
 *       counterA >= 157) {
 *       if (17000.0 > accum)         -> zero B and C (accum still below the
 *                                       high gate: keep debouncing)
 *       else if (500.0 > runtime)    -> path C: counterC++ (sat);
 *                                       flag2 set when counterC >= 4;
 *                                       counterB = 0
 *       else                         -> path B: counterB++ (sat);
 *                                       flag1 set when counterB >= 16;
 *                                       counterC = 0
 *   } else                           -> counterB = 0; counterC = 0
 *   if (cond)  counterA++ (saturating)
 *   else       counterA = 0
 *
 * The primary counter A counts consecutive cycles with the condition
 * active; once it crosses 157 the monitor starts one of the two secondary
 * counters, and each secondary counter must stay above its own threshold
 * to raise its confirmation flag.  The float gates select between the
 * secondary paths: with the accumulated value still below 17000.0 the
 * secondary counters are held at zero; otherwise the runtime value
 * (500.0) picks which secondary counter advances.
 *
 * Verified against ROM 60E1D400.bin (Track-A: emulator, see
 * c/tests/test_dtc_debounce_monitor_43760.py).
 */
#include <stdint.h>

#define RAM_COND         0xFFFFB3C8u   /* byte  condition input            */
#define RAM_ENABLE       0xFFFFC9E8u   /* byte  monitor enable             */
#define RAM_RESET        0xFFFFD201u   /* byte  reset request              */
#define RAM_FLAG1        0xFFFFC9EFu   /* byte  output flag 1              */
#define RAM_FLAG2        0xFFFFC9F0u   /* byte  output flag 2              */
#define RAM_CTR_A        0xFFFFC9FEu   /* word  primary counter            */
#define RAM_CTR_B        0xFFFFCA00u   /* word  secondary counter B        */
#define RAM_CTR_C        0xFFFFCA02u   /* word  secondary counter C        */
#define RAM_ACCUM        0xFFFFC9E4u   /* float accumulated value          */
#define RAM_RUNTIME      0xFFFFAAF0u   /* float runtime value              */

#define ROM_CTR_A_TH     0x0007D97Cu   /* word  157                        */
#define ROM_CTR_B_TH     0x0007D978u   /* word   16                        */
#define ROM_CTR_C_TH     0x0007D97Au   /* word    4                        */
#define ROM_GATE_HI      0x0007D984u   /* float 17000.0                    */
#define ROM_GATE_LO      0x0007D988u   /* float   500.0                    */

extern uint16_t add16bitSaturate(uint16_t a, uint16_t b);   /* 0x00002460 */

void dtc_debounce_monitor_43760(void)
{
    uint8_t  cond = *(volatile uint8_t *)RAM_COND;

    if (*(volatile uint8_t *)RAM_RESET == 0x01u) {
        *(volatile uint8_t  *)RAM_FLAG1 = 0x00u;
        *(volatile uint8_t  *)RAM_FLAG2 = 0x00u;
        *(volatile uint16_t *)RAM_CTR_A = 0x0000u;
        *(volatile uint16_t *)RAM_CTR_B = 0x0000u;
        *(volatile uint16_t *)RAM_CTR_C = 0x0000u;
        return;
    }

    if (*(volatile uint8_t *)RAM_ENABLE == 0x01u && cond == 0x01u &&
        *(volatile uint16_t *)RAM_CTR_A >= *(volatile uint16_t *)ROM_CTR_A_TH) {
        /* counter A has reached the debounce threshold: pick a path     */
        if (*(volatile float *)ROM_GATE_HI > *(volatile float *)RAM_ACCUM) {
            /* accumulated value still below the high gate: hold off     */
            *(volatile uint16_t *)RAM_CTR_B = 0x0000u;
            *(volatile uint16_t *)RAM_CTR_C = 0x0000u;
        } else if (*(volatile float *)ROM_GATE_LO > *(volatile float *)RAM_RUNTIME) {
            /* path C */
            if (*(volatile uint16_t *)RAM_CTR_C >= *(volatile uint16_t *)ROM_CTR_C_TH)
                *(volatile uint8_t *)RAM_FLAG2 = 0x01u;
            *(volatile uint16_t *)RAM_CTR_C =
                add16bitSaturate(*(volatile uint16_t *)RAM_CTR_C, 1u);
            *(volatile uint16_t *)RAM_CTR_B = 0x0000u;
        } else {
            /* path B */
            if (*(volatile uint16_t *)RAM_CTR_B >= *(volatile uint16_t *)ROM_CTR_B_TH)
                *(volatile uint8_t *)RAM_FLAG1 = 0x01u;
            *(volatile uint16_t *)RAM_CTR_B =
                add16bitSaturate(*(volatile uint16_t *)RAM_CTR_B, 1u);
            *(volatile uint16_t *)RAM_CTR_C = 0x0000u;
        }
    } else {
        *(volatile uint16_t *)RAM_CTR_B = 0x0000u;
        *(volatile uint16_t *)RAM_CTR_C = 0x0000u;
    }

    if (cond == 0x01u)
        *(volatile uint16_t *)RAM_CTR_A =
            add16bitSaturate(*(volatile uint16_t *)RAM_CTR_A, 1u);
    else
        *(volatile uint16_t *)RAM_CTR_A = 0x0000u;
}
