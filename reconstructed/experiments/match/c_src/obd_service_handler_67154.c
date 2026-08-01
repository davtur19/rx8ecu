/*
 * obd_service_handler_67154 — ROM 0x67154 (18 bytes, no pool).
 *   extu.b r4,r0 / tst #31,r0 / bf/s .L / nop / bra .R / mov #0,r4
 *   / mov #1,r4 / rts / mov r4,r0
 * Semantics:  (a & 31) != 0  →  1/0
 */
#include <stdint.h>

unsigned obd_service_handler_67154(uint8_t a)
{
    return (a & 31) != 0;
}
