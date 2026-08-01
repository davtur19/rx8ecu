/* purge_control_state_update.c
 *
 * ROM: 60E1D400  |  Address: 0xF544  |  Size: 112 bytes  |  VERIFIED vs ROM emulator
 *
 * EVAP purge control state update — selects the purge flow target byte.
 *
 * Called from the periodic task layer.  Reads the purge enable/trigger byte
 * (via 0x104C8, a leaf that returns RAM[0xFFFFBED0]) and, depending on it and
 * on the purge "flow demand" byte RAM[0xFFFF9F94], picks a small calibration
 * value stored in the ROM (currently 1/0/0/0) to write into
 * RAM[0xFFFFA4B1]; the result is then copied to the counter byte
 * RAM[0xFFFFA4B0] that purge_flow_decrement() counts down.
 *
 *   u8 v = read_trigger();                     // 0x104C8 -> RAM[0xBED0]
 *   RAM[0xFFFFA4B3] = RAM[0xFFFF9F94];         // latch flow demand
 *   if (v == 1) {
 *       u8 t = RAM[0xFFFFA4B3];
 *       if (t <= ROM[0x792FC])      out = ROM[0x792FE];  // (<= 4)  -> 1
 *       else if (t <= ROM[0x792FD]) out = ROM[0x792FF];  // (<= 10) -> 0
 *       else                        out = ROM[0x79300];  // (> 10)  -> 0
 *       RAM[0xFFFFA4B1] = out;
 *   } else {
 *       RAM[0xFFFFA4B1] = (RAM[0xFFFFCE6E] == 1) ? ROM[0x79301] : 0;
 *   }
 *   RAM[0xFFFFA4B0] = RAM[0xFFFFA4B1];          // publish to counter
 *
 * The ROM bytes at 0x792FC..0x79301 are calibration constants; in the stock
 * bin they are 04 0A 01 00 00 00, i.e. threshold 4 -> output 1, threshold
 * 10 -> output 0, else 0.  The CE6E branch output byte (ROM[0x79301]) is 0.
 *
 * Note: the trigger read 0x104C8 is modeled as an external call in C but is
 * executed for real in the emulator-based test.
 *
 * Verified: 10000 random states vs the ROM emulator, 0 mismatches.
 */

#include <stdint.h>

#define RAM_PURGE_FLOW       (*(volatile uint8_t *)0xFFFFA4B0)
#define RAM_PURGE_FLOW_STATE (*(volatile uint8_t *)0xFFFFA4B1)
#define RAM_PURGE_DEMAND     (*(volatile uint8_t *)0xFFFFA4B3)
#define RAM_FLOW_DEMAND      (*(volatile uint8_t *)0xFFFF9F94)
#define RAM_ALT_TRIGGER      (*(volatile uint8_t *)0xFFFFCE6E)

#define ROM_THR_LOW   (*(const uint8_t *)0x000792FC)   /* 4  */
#define ROM_THR_HIGH  (*(const uint8_t *)0x000792FD)   /* 10 */
#define ROM_OUT_LOW   (*(const uint8_t *)0x000792FE)   /* 1  */
#define ROM_OUT_MID   (*(const uint8_t *)0x000792FF)   /* 0  */
#define ROM_OUT_HIGH  (*(const uint8_t *)0x00079300)   /* 0  */
#define ROM_OUT_ALT   (*(const uint8_t *)0x00079301)   /* 0  */

extern uint8_t read_purge_trigger(void);
/* @0x104C8: returns RAM[0xFFFFBED0] (mov.w literal 0xBED0) */

void purge_control_state_update(void)
{
    uint8_t v, t, out;

    v = read_purge_trigger() & 0xFF;
    RAM_PURGE_DEMAND = RAM_FLOW_DEMAND;          /* latch flow demand */
    if (v == 1) {
        t = RAM_PURGE_DEMAND;
        if (t <= ROM_THR_LOW)      out = ROM_OUT_LOW;   /* <= 4  -> 1 */
        else if (t <= ROM_THR_HIGH) out = ROM_OUT_MID;  /* <= 10 -> 0 */
        else                        out = ROM_OUT_HIGH; /* > 10  -> 0 */
        RAM_PURGE_FLOW_STATE = out;
    } else {
        RAM_PURGE_FLOW_STATE = (RAM_ALT_TRIGGER == 1) ? ROM_OUT_ALT : 0;
    }
    RAM_PURGE_FLOW = RAM_PURGE_FLOW_STATE;       /* publish to counter */
}
