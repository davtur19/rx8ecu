/* aux_fan_control_task.c
 *
 * ROM: 60E1D400  |  Address: 0x1AED2  |  Size: 48 bytes  |  VERIFIED vs ROM emulator
 *
 * Boost-pressure auxiliary-fan task.  Wraps a chain of boost calculations
 * and a pressure hysteresis flag update in a getSR/setSR critical section
 * (SR bits are preserved across the whole chain).
 *
 * Steps, in execution order:
 *   1. getSR(0x10); saved SR restored at the end via setSR.
 *   2. 0x32F42:  RAM[0xFFFFC008] = firstOrderFilter(RAM[0xFFFFC008],
 *                  RAM[0xFFFFBC1C], 0.7, 1e-5)      ; boost low-pass filter
 *   3. 0x2DD6E (boost_delta_control):
 *        RAM[0xFFFFBD3C] = (RAM[0xFFFFC008] - RAM[0xFFFFBD40]) * 15.625
 *        RAM[0xFFFFBD40] = RAM[0xFFFFC008]          ; remember previous sample
 *   4. 0x2DD88 (boost_error_abs_calc):
 *        RAM[0xFFFFBD38] = firstOrderFilter(RAM[0xFFFFBD3C],
 *                            RAM[0xFFFFBD38], 0.5, 1e-5)
 *   5. 0x344FE: six float copies (register/global shuffle):
 *        C0D8<-C104  C0DC<-C108  C0E0<-C10C  C108<-C12C  C104<-B5B8  C10C<-ADC0
 *   6. 0x3488C: hysteresis on boost pressure RAM[0xFFFFB5B8] (f32):
 *        p >= 7000  -> flag = 1
 *        p <  6500  -> flag = 0
 *        6500 <= p < 7000 -> hold (no transition)
 *      (thresholds ROM[0x7A18C] = 7000, hysteresis ROM[0x7A190] = 500)
 *      Active paths call 0xC2E6(flag).
 *   7. 0xC2E6: only when the flag actually changes:
 *        RAM[0xFFFFA384] = 0xFF, RAM[0xFFFFA385] = 0, RAM[0xFFFFA324] = 0,
 *        RAM[0xFFFFA38C] = flag
 *   8. setSR(saved_SR).
 *
 * Verified: 6000 random float/byte inputs vs the ROM emulator, 0 mismatches
 * (test_aux_fan_control_task.py).
 */

#include <stdint.h>
#include <math.h>

#define RAM_BOOST_IN     (*(volatile float *)0xFFFFC008) /* filtered boost */
#define RAM_FILT_PREV    (*(volatile float *)0xFFFFBC1C) /* filter history */
#define RAM_DELTA_PREV   (*(volatile float *)0xFFFFBD40) /* last sample */
#define RAM_DELTA        (*(volatile float *)0xFFFFBD3C) /* scaled delta */
#define RAM_ERR_PREV     (*(volatile float *)0xFFFFBD38) /* error filter */
#define RAM_BOOST_P      (*(volatile float *)0xFFFFB5B8) /* pressure input */

#define RAM_C104         (*(volatile float *)0xFFFFC104)
#define RAM_C108         (*(volatile float *)0xFFFFC108)
#define RAM_C10C         (*(volatile float *)0xFFFFC10C)
#define RAM_C0D8         (*(volatile float *)0xFFFFC0D8)
#define RAM_C0DC         (*(volatile float *)0xFFFFC0DC)
#define RAM_C0E0         (*(volatile float *)0xFFFFC0E0)
#define RAM_C12C         (*(volatile float *)0xFFFFC12C)
#define RAM_ADC0         (*(volatile float *)0xFFFFADC0)

#define RAM_BOOST_FLAG   (*(volatile uint8_t *)0xFFFFA38C)
#define RAM_A384         (*(volatile uint8_t *)0xFFFFA384)
#define RAM_A385         (*(volatile uint8_t *)0xFFFFA385)
#define RAM_A324         (*(volatile uint8_t *)0xFFFFA324)

#define ROM_FF_FILTER    (*(const float *)0x78CFC)   /* 0.7   boost filter */
#define ROM_FF_ERROR     (*(const float *)0x76B30)   /* 0.5   error filter */
#define ROM_EPS          (*(const float *)0x32F64)   /* 1e-5  deadband */
#define ROM_DELTA_SCALE  (*(const float *)0x2DDB0)   /* 15.625 */
#define ROM_P_ON         (*(const float *)0x7A18C)   /* 7000  */
#define ROM_P_HY         (*(const float *)0x7A190)   /* 500   */

extern float firstOrderFilter(float sig, float sigprev, float ff, float min);

static void flag_transition(uint8_t flag)
{
    /* 0xC2E6: side effects only when the flag value changes. */
    if (RAM_BOOST_FLAG != flag) {
        RAM_A384 = 0xFF;
        RAM_A385 = 0;
        RAM_A324 = 0;
        RAM_BOOST_FLAG = flag;
    }
}

void aux_fan_control_task(void)
{
    /* step 2: boost low-pass filter */
    RAM_BOOST_IN = firstOrderFilter(RAM_BOOST_IN, RAM_FILT_PREV,
                                    ROM_FF_FILTER, ROM_EPS);

    /* step 3: delta control — scaled first difference */
    RAM_DELTA = (RAM_BOOST_IN - RAM_DELTA_PREV) * ROM_DELTA_SCALE;
    RAM_DELTA_PREV = RAM_BOOST_IN;

    /* step 4: error filter */
    RAM_ERR_PREV = firstOrderFilter(RAM_DELTA, RAM_ERR_PREV,
                                    ROM_FF_ERROR, ROM_EPS);

    /* step 5: float register swap */
    RAM_C0D8 = RAM_C104;
    RAM_C0DC = RAM_C108;
    RAM_C0E0 = RAM_C10C;
    RAM_C108 = RAM_C12C;
    RAM_C104 = RAM_BOOST_P;
    RAM_C10C = RAM_ADC0;

    /* steps 6+7: pressure hysteresis -> flag transition */
    float p = RAM_BOOST_P;
    if (p >= ROM_P_ON)
        flag_transition(1);
    else if (p < ROM_P_ON - ROM_P_HY)
        flag_transition(0);
    /* else: hold previous flag */
}
