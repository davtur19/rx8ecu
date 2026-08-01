/*
 * getSpeedLimitCal.c  —  RX-8 ECU speed limit calibration table
 *
 * Address: 0x049EFC  |  Size: 188 bytes
 *
 * Maps a speed-limit ID value to a configuration byte for three
 * different speed limit threshold registers.  Uses a PC-relative
 * literal pool for the threshold values.  The ID is passed as an
 * 8-bit value; depending on the ID, different limit values are
 * written to registers at 0xCD4C, 0xCD4D, and 0xCD4E.
 *
 * Speed Limit ID → Value mapping (first register):
 *   0x0A (=10):  0x80  (128 km/h limit)
 *   0x01:        0x40  (64 km/h)
 *   0x02:        0x20  (32 km/h)
 *   0x06:        0x10  (16 km/h)
 *   0xF1:        0x08  (8 km/h)
 *   0xF0:        0x04  (4 km/h)
 *   0x05:        0x02  (2 km/h)
 *   other:       0x00  (no limit)
 *
 * The function calls calibration subroutines that process each value
 * and writes updated values to subsequent registers based on return
 * codes (0, 1, 2).
 *
 * Verified against ROM: c/tests/test_getSpeedLimitCal.py
 */
#include <stdint.h>

/* External calibration helpers */
extern uint32_t cal_lookup_sub_a(uint8_t val, uint8_t limit_id);
extern uint32_t cal_lookup_sub_b(uint8_t val, uint8_t limit_id);
extern uint32_t cal_lookup_sub_c(uint8_t val, uint8_t limit_id);

/* 0x049EFC — compute speed limit calibration values */
void getSpeedLimitCal(uint8_t limit_id)
{
    volatile uint8_t *limit_reg_a = (volatile uint8_t *)0x0000CD4C;
    volatile uint8_t *limit_reg_b = (volatile uint8_t *)0x0000CD4D;
    volatile uint8_t *limit_reg_c = (volatile uint8_t *)0x0000CD4E;
    uint8_t val_a, val_b, val_c;
    uint32_t ret;

    /* Map limit ID to first value */
    switch (limit_id) {
        case 0x0A: val_a = 0x80; break;
        case 0x01: val_a = 0x40; break;
        case 0x02: val_a = 0x20; break;
        case 0x06: val_a = 0x10; break;
        case 0xF1: val_a = 0x08; break;
        case 0xF0: val_a = 0x04; break;
        case 0x05: val_a = 0x02; break;
        default:   val_a = 0x00; break;
    }

    *limit_reg_a = val_a;
    ret = cal_lookup_sub_a(val_a, limit_id);

    /* Map return value to second register value */
    switch (ret & 0xFF) {
        case 0x00: val_b = 0x80; break;
        case 0x01: val_b = 0x40; break;
        default:   val_b = 0x00; break;
    }

    *limit_reg_b = val_b;
    ret = cal_lookup_sub_b(val_b, limit_id);

    /* Map return value to third register value */
    switch (ret & 0xFF) {
        case 0x00: val_c = 0x80; break;
        case 0x01: val_c = 0x40; break;
        case 0x02: val_c = 0x20; break;
        default:   val_c = 0x00; break;
    }

    *limit_reg_c = val_c;
    cal_lookup_sub_c(val_c, limit_id);
}
