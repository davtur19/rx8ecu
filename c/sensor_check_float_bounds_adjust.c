/**
 * sensor_check_float_bounds_adjust @ 0xE0DE (60E1D400)
 *
 * Purpose:
 *   Compare a sensor float value against a threshold and adjust a
 *   byte-rate counter. If the float exceeds threshold, load a new
 *   byte from a fault table; otherwise, decrement the counter
 *   (with wraparound via 0xFF subtraction = -1 unsigned).
 *
 * This is implemented as a rate-limiter / debounce counter for
 * sensor fault detection.
 *
 * Logic:
 *   float sensor_val = *(float*)threshold_ram_addr;
 *   float threshold   = *(float*)rom_threshold_addr;
 *
 *   if (threshold > sensor_val) {
 *       uint8_t fault_byte = *(uint8_t*)fault_table_addr;
 *       *(uint8_t*)counter_addr = fault_byte;
 *   } else {
 *       uint8_t counter = *(uint8_t*)counter_addr;
 *       if (counter != 0) {
 *           counter = counter + 0xFF;  // effectively -1 in unsigned wrap
 *           *(uint8_t*)counter_addr = counter;
 *       }
 *   }
 *
 * ROM:
 *   0x6CF8C  float   Threshold value
 *   0x6CF88  uint8_t Fault/init value for counter
 *
 * RAM:
 *   0xFFFFA400  uint8_t  Counter/debounce byte
 *   0xFFFFB600  float    Sensor value to check
 *   (exact addresses depend on ROM image; low 16 bits loaded
 *    from PC-relative pool, upper bits implied as 0xFFFF)
 */

#include <stdint.h>

#define THRESHOLD      (*(const float *)     0x0006CF8C)
#define FAULT_INIT     (*(const uint8_t *)   0x0006CF88)
#define SENSOR_VALUE   (*(volatile float *)  0xFFFFB600)
#define COUNTER        (*(volatile uint8_t *)0xFFFFA400)

void sensor_check_float_bounds_adjust(void)
{
    float sensor_val = SENSOR_VALUE;

    if (THRESHOLD > sensor_val) {
        /* Exceeded threshold — load fault init value into counter */
        COUNTER = FAULT_INIT;
    } else {
        uint8_t cnt = COUNTER;
        if (cnt != 0) {
            /* Decrement counter (0xFF = -1 in unsigned wrap) */
            cnt += 0xFF;  /* equivalent to cnt -= 1 */
            COUNTER = cnt;
        }
    }
}
