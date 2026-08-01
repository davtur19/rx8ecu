/* atu2_edge_capture_config_6F3A.c
 *
 * ROM: 60E1D400  |  Address: 0x6F3A  |  Size: 134 bytes (to 0x6FC2)
 *
 * ATU2 edge-capture configuration leaf.  Takes r4 (32-bit): r4 == 0 selects
 * the "enable" sequence, any other value the "disable" sequence.  Performs
 * byte read-modify-writes on a set of SFRs; the two branches differ only in
 * the value written to 0xFFFFF818 (0x0B vs 0x0A) and 0xFFFFF838 (0x4B vs
 * 0x4A); everything else is the common tail.
 *
 * Addresses (mov.w sign-extended: 0xF818→0xFFFFF818, 0xF72E→0xFFFFF72E,
 * 0xF839→0xFFFFF839; derived: r13=r1+0x20=0xFFFFF838, r7=r14+0x40=
 * 0xFFFFF76E, r5=r6+s8(0xE0)=0xFFFFF839-0x20=0xFFFFF819; 0xFFFF9F27 from
 * mov.l literal):
 *
 *   if (r4 == 0):
 *     [0xFFFFF819] &= 0xDF
 *     [0xFFFFF818] = 0x0B
 *     [0xFFFFF76E] = ([0xFFFFF76E] & 0x7F) | 0x80
 *     [0xFFFFF819] = ([0xFFFFF819] & 0xAF) | 0x80
 *     [0xFFFFF839] &= 0xDF
 *     [0xFFFFF838] = 0x4B
 *   else:
 *     [0xFFFFF819] &= 0xDF
 *     [0xFFFFF818] = 0x0A
 *     [0xFFFFF76E] = ([0xFFFFF76E] & 0x7F) | 0x80
 *     [0xFFFFF819] = ([0xFFFFF819] & 0xAF) | 0x80
 *     [0xFFFFF839] &= 0xDF
 *     [0xFFFFF838] = 0x4A
 *   # common tail (both branches):
 *   [0xFFFFF72E] = ([0xFFFFF72E] & 0x7F) | 0x80
 *   [0xFFFFF839] = ([0xFFFFF839] & 0xAF) | 0x80
 *   [0xFFFF9F27] = 0x01
 *
 * Return r0 not meaningful — lift returns void.
 *
 * Verified against ROM emulator: c/tests/test_atu2_edge_capture_config_6F3A.py
 * Host C companion:             c/tests/test_atu2_edge_capture_config_6F3A.c
 */
#include <stdint.h>

/* 0x6F3A — configure ATU2 edge capture registers (r4 == 0 → enable) */
void atu2_edge_capture_config_6F3A(uint32_t r4)
{
    volatile uint8_t *p818 = (volatile uint8_t *)0xFFFFF818;
    volatile uint8_t *p838 = (volatile uint8_t *)0xFFFFF838;
    volatile uint8_t *p919 = (volatile uint8_t *)0xFFFFF819;
    volatile uint8_t *p76E = (volatile uint8_t *)0xFFFFF76E;
    volatile uint8_t *p839 = (volatile uint8_t *)0xFFFFF839;
    volatile uint8_t *p72E = (volatile uint8_t *)0xFFFFF72E;
    volatile uint8_t *p9F27 = (volatile uint8_t *)0xFFFF9F27;

    if (r4 == 0) {
        *p919 = (uint8_t)(*p919 & 0xDF);
        *p818 = 0x0B;
        *p76E = (uint8_t)((*p76E & 0x7F) | 0x80);
        *p919 = (uint8_t)((*p919 & 0xAF) | 0x80);
        *p839 = (uint8_t)(*p839 & 0xDF);
        *p838 = 0x4B;
    } else {
        *p919 = (uint8_t)(*p919 & 0xDF);
        *p818 = 0x0A;
        *p76E = (uint8_t)((*p76E & 0x7F) | 0x80);
        *p919 = (uint8_t)((*p919 & 0xAF) | 0x80);
        *p839 = (uint8_t)(*p839 & 0xDF);
        *p838 = 0x4A;
    }
    *p72E = (uint8_t)((*p72E & 0x7F) | 0x80);
    *p839 = (uint8_t)((*p839 & 0xAF) | 0x80);
    *p9F27 = 0x01;
}
