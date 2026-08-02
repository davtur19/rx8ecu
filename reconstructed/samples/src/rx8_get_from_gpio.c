/*
 * =============================================================================
 * rx8_get_from_gpio.c  —  GET FROM GPIO (SH7055 port read + A/B pattern scatter)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x70D0
 * Size        : 170 bytes (0x70D0..0x7178), plus in-line local leaf @0x720E.
 * Status      : VERIFIED — behavioural equivalence to the actual ROM bytes held
 *               by reconstructed/samples/tests/harness_get_from_gpio.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               return byte and every written port/pattern cell bit-exact;
 *               0 mismatches).
 * Lift (truth): c/getFromGPIO.c  (getFromGPIO @ 0x70D0)
 *
 * ABOUT THIS FUNCTION
 * -------------------
 * getFromGPIO routes the SH7055 GPIO ports that feed the actuator envelope
 * pattern generator.  It:
 *    1. saves SR / masks IRQs (0x3920),
 *    2. reconfigures port cells: 0xF002 &= 0x0B, 0xF000 = 0x80,
 *       0xF002 &= 0xFC, 0xF006 = 0xF0, 0xF001 = 0x04,
 *    3. scatters two 16-bit pattern words 0x4000 / 0x8000 into latch 0xF72C
 *       (set/clear pairs selected by the run-time input byte),
 *    4. gates back (0x3934) and returns the byte read at port 0xF005.
 *
 * The local leaf @0x720E (jsr indirect through 0x4BBC for the bit RMW, plus
 * 0x4C14 — a stream of nops, "2-op" placeholder) repates port 0xF004 (a busy
 * wait on bit 0x40), pokes 0xF003 (=0xFF) and toggles bit 0 of the 0xF764
 * latch, and passes the 0xF005 byte back up as the function result.
 *
 * Bit-setter 0x4BBC semantics (disassembly):
 *     mov.w @r4,r3  ; extu.w r6,r6 ; tst r6,r6 ; bf set
 *     (enable==0) ~r5 + r3 &= r5 : C L E A R mask bits
 *     (enable!=0) r3 |= r5        : S E T   mask bits
 *
 * CALLING CONVENTION
 * ------------------
 * `uint8_t rx8_get_from_gpio(uint8_t input)` — one byte arg, one byte return.
 * The host build replaces the two peripheral jsr leaves (0x3920/0x3944, pure
 * SR helpers) and 0x4C14 with no-ops; the 0x4BBC bit-set is implemented by the
 * mod16() helper.  0xF72C / 0xF764 are native 16-bit big-endian cells.
 *
 * RAM / MMIO CELLS (address, width; big-endian on the SH-2E)
 * ---------------------------------------------------------
 *   0xFFFFF000  u8  port dir/ctrl 0                  (write 0x80)
 *   0xFFFFF001  u8  port ctrl 1                      (write 0x04)
 *   0xFFFFF002  u8  port data/dir (input arg uses it on MC)  (RMW)
 *   0xFFFFF003  u8  port selector / pattern (leaf)   (write 0xFF)
 *   0xFFFFF004  u8  polled port status (repack |0x80 then |0x78 then
 *                   |0xB8, armed by bit 0x40 busy-wait)
 *   0xFFFFF005  u8  INPUT / OUTPUT byte  (<-- function result)
 *   0xFFFFF006  u8  port aux control                 (write 0xF0)
 *   0xFFFFF72C  u16 pattern scatter latch (0x4000 / 0x8000 set/clear)
 *   0xFFFFF764  u16 leaf RMW latch (bit 0 clear then set)
 *
 * DISCREPANCIES FOUND IN THE LIFT (c/getFromGPIO.c) — corrected here:
 *   1. The two "output A/B" helpers collapse to ONE 16-bit scatter latch
 *      (0xF72C) holding the 0x4000 | 0x8000 set/clear pair.
 *   2. Return value is the byte @0xF005, not a "re-read port" — 0xF004 is
 *      the busy/poll cell, 0xF002 is repacked with ((x & 0x0B) | 0x30).
 *   3. Control-register write ORDER (ROM) is F000=0x80, F006=0xF0, F001=0x04
 *      interleaved with the two F002 masks — the lift omitted F001/F006 and
 *      had wrong constant for the F002 masks.
 *   4. The leaf's 0xF764 "reset to 0xFF" in the lift is actually a bit-0
 *      clear-then-set RMW, and 0xF003 is written 0xFF (not left).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"       /* RX8_IO8 / RX8_IO16 fixed-address accessors */
#include "rx8_samples.h"

/* machine addresses are sign-extended on the SH-2E (mov.w/mov.l pools @0x717A..0x71AA) */
#define RX8_GPIO_P0      0xFFFFF000u   /* u8  port dir/ctrl 0              */
#define RX8_GPIO_P1      0xFFFFF001u   /* u8  port control 1               */
#define RX8_GPIO_DDR     0xFFFFF002u   /* u8  port data/dir (RMW)          */
#define RX8_GPIO_PSEL    0xFFFFF003u   /* u8  selector/pattern (leaf)      */
#define RX8_GPIO_STAT    0xFFFFF004u   /* u8  poll status cell             */
#define RX8_GPIO_DATA    0xFFFFF005u   /* u8  INPUT/OUTPUT (result)        */
#define RX8_GPIO_AUX     0xFFFFF006u   /* u8  port aux control             */
#define RX8_GPIO_F72C    0xFFFFF72Cu   /* u16 pattern scatter latch        */
#define RX8_GPIO_F764    0xFFFFF764u   /* u16 leaf RMW latch               */

/* 0x4BBC — set or clear the mask bits in a 16-bit cell (enable !=0 : set). */
static void mod16(uint32_t reg, uint16_t mask, unsigned enable)
{
    volatile uint16_t *w = (volatile uint16_t *)(uintptr_t)reg;
    if (enable != 0)
        *w = (uint16_t)(*w | mask);
    else
        *w = (uint16_t)(*w & (uint16_t)~mask);
}

uint8_t rx8_get_from_gpio(uint8_t input)
{
    uint8_t x;

    /* ---- port setup (order per ROM disassembly) ---- */
    x = RX8_IO8(RX8_GPIO_DDR);
    RX8_IO8(RX8_GPIO_DDR) = (uint8_t)(x & 0x0Bu);   /* &= 0x0B */

    RX8_IO8(RX8_GPIO_P0) = 0x80;                      /* F000 = 0x80 */

    x = RX8_IO8(RX8_GPIO_DDR);
    RX8_IO8(RX8_GPIO_DDR) = (uint8_t)(x & 0xFCu);    /* &= 0xFC */

    RX8_IO8(RX8_GPIO_AUX) = 0xF0;                     /* F006 = 0xF0 */
    RX8_IO8(RX8_GPIO_P1)  = 0x04;                     /* F001 = 0x04 */

    /* ---- scatter 0x4000 / 0x8000 by selector ---- */
    if (input == 0) {
        mod16(RX8_GPIO_F72C, 0x4000u, 0);             /* clear 0x4000 */
        mod16(RX8_GPIO_F72C, 0x8000u, 0);             /* clear 0x8000 */
    } else if (input == 1) {
        mod16(RX8_GPIO_F72C, 0x4000u, 1);             /* set   0x4000 */
        mod16(RX8_GPIO_F72C, 0x8000u, 0);             /* clear 0x8000 */
    } else {
        mod16(RX8_GPIO_F72C, 0x4000u, 0);             /* clear 0x4000 */
        mod16(RX8_GPIO_F72C, 0x8000u, 1);             /* set   0x8000 */
    }

    /* ---- common repack of the DDR port + local leaf ---- */
    x = RX8_IO8(RX8_GPIO_DDR);
    RX8_IO8(RX8_GPIO_DDR) = (uint8_t)((x & 0x0Bu) | 0x30u);  /* &0x0B|0x30 */

    /* leaf: clear bit 0 of 0xF764 */
    mod16(RX8_GPIO_F764, 0x0001u, 0);

    /* repack 0xF004, poke 0xF003 = 0xFF, mark bit 0x40 */
    uint8_t s = RX8_IO8(RX8_GPIO_STAT);
    RX8_IO8(RX8_GPIO_STAT) = (uint8_t)((s & 0x87u) | 0x80u);

    RX8_IO8(RX8_GPIO_PSEL) = 0xFFu;                  /* r2 = selector -> */
    /*                                              F003 = 0xFF       */

    s = RX8_IO8(RX8_GPIO_STAT);
    RX8_IO8(RX8_GPIO_STAT) = (uint8_t)((s & 0x7Fu) | 0x78u);

    /* busy wait until bit 0x40 of 0xF004 is set (the value we just wrote) */
    while ((RX8_IO8(RX8_GPIO_STAT) & 0x40u) == 0u) {
        /* spin: ROM polls 0xF004 */
    }

    uint8_t result = RX8_IO8(RX8_GPIO_DATA);         /* read 0xF005 */

    s = RX8_IO8(RX8_GPIO_STAT);
    RX8_IO8(RX8_GPIO_STAT) = (uint8_t)((s & 0xBFu) | 0xB8u);

    /* leaf tail: set bit 0 of 0xF764 back */
    mod16(RX8_GPIO_F764, 0x0001u, 1);

    return result;
}