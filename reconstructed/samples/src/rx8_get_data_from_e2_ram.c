/*
 * =============================================================================
 * rx8_get_data_from_e2_ram.c  —  EEPROM SHADOW -> WORKING-COPY COPY-OUT
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x36C1C
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_get_data_from_e2_ram.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random vectors,
 *               real ROM bytes @0x36C1C; r0, the full 30-byte destination
 *               block and the 32-byte primary/complement E2 shadows compared
 *               bit-exactly; 0 mismatches).
 * Lift (truth): c/getDataFromE2RAM.c  (getDataFromE2RAM @ 0x36C1C)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Boot-time / post-boot exposure of the validated EEPROM shadow to the
 * running firmware's "working copy" RAM.  Called after the boot load
 * (loadDatafromE2intoRAM @0x36BD6, see rx8_load_data_from_e2_into_ram.c)
 * has filled the shadow from FLASH: for every EEPROM region the firmware
 * keeps a cached copy of in low RAM, this function performs one
 * getFromE2_E2ADDR_RAMADDR_LEN(e2addr, dest, len) @0x39170 call that
 * validates the (value, ~value) complement pair and copies the value,
 * recovering from the FLASH backup on a corrupt pair (see the lift c/getFromE2.c).
 *
 * Disassembly of 60E1D400.bin @ 0x36C1C (registers after each mov):
 *
 *     2FE6   mov.l r14,@-r15           ; prologue: save callee-saved r14
 *     E601   mov   #0x01,r6            ; len = 1
 *     D52A   mov.l @(0x2A,PC),r5       ; r5 = 0xFFFFC2D8 (dest for E2[0x00])
 *     4F22   sts.l pr,@-r15
 *     DE28   mov.l @(0x28,PC),r14      ; r14 = 0x00039170 (getFromE2)
 *     4E0B   jsr   @r14                ; getFromE2(0x00, 0xFFFFC2D8, 1)
 *     E400   mov   #0x00,r4            ;   (delay) e2addr = 0x00
 *     ...    19 such jsr @r14 calls, each setting r4/e2addr, r6/len and
 *     ...    loading r5/dest (mov.l @(disp,PC) for the work bytes, mov.w for
 *     ...    the three CAN shadow bytes), exactly as mapped below:
 *
 *     EEPROM index -> destination map (verified from the literal pool):
 *       0x00 -> 0xFFFFC2D8 (1B)     0x0F -> 0xFFFFC2E7 (1B)
 *       0x02 -> 0xFFFFC2DC (4B)     0x10 -> 0xFFFFC242 (1B)
 *       0x06 -> 0xFFFFC2E0 (4B)     0x16 -> 0xFFFFC2EA (2B)
 *       0x0A -> 0xFFFFC2E4 (1B)     0x18 -> 0xFFFFC2EC (2B)
 *       0x0C -> 0xFFFFC2E5 (1B)     0x12 -> 0xFFFFC244 (1B)
 *       0x0D -> 0xFFFFC2E6 (1B)     0x13 -> 0xFFFFC2E8 (1B)
 *       0x0E -> 0xFFFFC243 (1B)     0x14 -> 0xFFFFC2E9 (1B)
 *       0x1A -> 0xFFFFC2EE (1B)     0x1C -> 0xFFFFC2F0 (1B)
 *       0x1B -> 0xFFFFC2EF (1B)     0x1D -> 0xFFFFC2F1 (1B)
 *       0x1E -> 0xFFFFC2F2 (1B)
 *
 *     4F26   lds.l @r15+,pr           ; epilogue
 *     000B   rts
 *     6EF6   extu.w r6,r14            ;   (delay slot = first pool word)
 *
 * LIFT DISCREPANCIES (documented)
 * ------------------------------
 *  1. CAN-shadow addressing.  The three CAN shadow bytes are loaded with
 *     `mov.w @(disp,PC),r5`, and mov.w SIGN-EXTENDS its 16-bit literal, so
 *     the effective destination addresses are 0xFFFFC243 / 0xFFFFC242 /
 *     0xFFFFC244 (on-chip RAM window), NOT the 0x0000C243/0x0000C242/
 *     0x0000C244 spellings used by the c/eeprom_immo.h macros in the lift.
 *     The reconstructed source below uses the ROM's sign-extended addresses;
 *     the writes are observed at 0xFFFFC2xx under the emulator (the E2
 *     working-copy shadow lives in that same page, so on the real MCU the
 *     two spellings alias the same physical RAM).  All other destinations
 *     are loaded with mov.l and match the lift exactly.
 *  2. Call order.  The lift lists the calls grouped by EEPROM index; the
 *     ROM's actual order is interleaved (0x00, 0x02, 0x06, 0x0A, 0x0C, 0x0D,
 *     0x0E, 0x0F, 0x10, 0x16, 0x18, 0x12, 0x13, 0x14, 0x1A..0x1E).  Every
 *     call touches a DISJOINT destination and a disjoint EEPROM range, so
 *     the order has no observable effect; the source below keeps the ROM's
 *     order verbatim.
 *
 * RETURN-VALUE / r0 SIDE CHANNEL
 * ------------------------------
 * The function takes no arguments and returns nothing (void).  r0 after the
 * call is a side channel holding getFromE2's return for the LAST (19th) call
 * — the error flag of EEPROM[0x1E] (1 = corrupt pair and failed SPI retry,
 * 0 = valid or recovered).  The harness compares that r0 too.
 *
 * HARDWARE ABSTRACTION (verification notes)
 * -----------------------------------------
 * getFromE2 @0x39170 saves/restores SR through the getSR/setSR pair
 * (0x3920 / 0x3934), polls the SPI-retry hook 0xC0A8 on a corrupt pair and
 * reads the FLASH backup word through the SPI bit-bang reader 0xBFCA.  The
 * real 0xBFCA busy-waits on peripheral status bits sh2emu cannot model, so
 * following the repo-established pattern (c/tests/test_getFromE2.py,
 * harness_load_data_from_e2_into_ram.py) the harness stubs all four helper
 * addresses (0x3920, 0x3934, 0xC0A8, 0xBFCA) in the RAM overlay and executes
 * the REAL getDataFromE2RAM bytes plus the REAL getFromE2 control flow.  The
 * host oracle mirrors the same stubs through its porting layer.  getFromE2's
 * retry test is `exts.b r0,r0; tst r0,r0`, so ANY nonzero stub return means
 * "retry failed" (error flag set, destination byte left untouched); 0 means
 * "recovered" and the byte is rebuilt from the FLASH stub and copied.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* 0x39170 — getFromE2_E2ADDR_RAMADDR_LEN(e2addr, ramaddr, len), lift
 * c/getFromE2.c.  Supplied by the porting layer of the host oracle
 * (tests/oracle_get_data_from_e2_ram.c) when this sample is compiled for
 * equivalence testing; the emulator harness executes the real ROM bytes. */
uint8_t getFromE2_E2ADDR_RAMADDR_LEN(uint16_t e2addr, uint8_t *ramaddr, uint8_t len);

/* Working copies of EEPROM bytes, populated from the validated shadow.
 * Addresses verified from the literal pool @0x36CC0..0x36D0A (see header:
 * the CAN bytes arrive sign-extended from mov.w, hence the 0xFFFFC2xx
 * spellings — a documented deviation from the c/eeprom_immo.h macros). */
#define E2_WORK_0x00  (*(volatile uint8_t  *)0xFFFFC2D8u) /* EEPROM[0x00]     */
#define E2_WORK_0x02  (*(volatile uint8_t  *)0xFFFFC2DCu) /* EEPROM[0x02..05] */
#define E2_WORK_0x06  (*(volatile uint8_t  *)0xFFFFC2E0u) /* EEPROM[0x06..09] */
#define E2_WORK_0x0A  (*(volatile uint8_t  *)0xFFFFC2E4u) /* EEPROM[0x0A]     */
#define E2_WORK_0x0C  (*(volatile uint8_t  *)0xFFFFC2E5u) /* EEPROM[0x0C]     */
#define E2_WORK_0x0D  (*(volatile uint8_t  *)0xFFFFC2E6u) /* EEPROM[0x0D]     */
#define E2_WORK_0x0F  (*(volatile uint8_t  *)0xFFFFC2E7u) /* EEPROM[0x0F]     */
#define E2_WORK_0x10  (*(volatile uint8_t  *)0xFFFFC242u) /* EEPROM[0x10] CAN shadow */
#define E2_WORK_0x12  (*(volatile uint8_t  *)0xFFFFC244u) /* EEPROM[0x12] CAN shadow */
#define E2_WORK_0x13  (*(volatile uint8_t  *)0xFFFFC2E8u) /* EEPROM[0x13]     */
#define E2_WORK_0x14  (*(volatile uint8_t  *)0xFFFFC2E9u) /* EEPROM[0x14]     */
#define E2_WORK_0x16  (*(volatile uint8_t  *)0xFFFFC2EAu) /* EEPROM[0x16..17] */
#define E2_WORK_0x18  (*(volatile uint8_t  *)0xFFFFC2ECu) /* EEPROM[0x18..19] */
#define E2_WORK_0x1A  (*(volatile uint8_t  *)0xFFFFC2EEu) /* EEPROM[0x1A]     */
#define E2_WORK_0x1B  (*(volatile uint8_t  *)0xFFFFC2EFu) /* EEPROM[0x1B]     */
#define E2_WORK_0x1C  (*(volatile uint8_t  *)0xFFFFC2F0u) /* EEPROM[0x1C]     */
#define E2_WORK_0x1D  (*(volatile uint8_t  *)0xFFFFC2F1u) /* EEPROM[0x1D]     */
#define E2_WORK_0x1E  (*(volatile uint8_t  *)0xFFFFC2F2u) /* EEPROM[0x1E]     */
#define E2_WORK_0x0E  (*(volatile uint8_t  *)0xFFFFC243u) /* EEPROM[0x0E] CAN shadow */

void rx8_get_data_from_e2_ram(void)
{
    getFromE2_E2ADDR_RAMADDR_LEN(0x00, (uint8_t *)&E2_WORK_0x00, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x02, (uint8_t *)&E2_WORK_0x02, 4);
    getFromE2_E2ADDR_RAMADDR_LEN(0x06, (uint8_t *)&E2_WORK_0x06, 4);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0A, (uint8_t *)&E2_WORK_0x0A, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0C, (uint8_t *)&E2_WORK_0x0C, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0D, (uint8_t *)&E2_WORK_0x0D, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0E, (uint8_t *)&E2_WORK_0x0E, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0F, (uint8_t *)&E2_WORK_0x0F, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x10, (uint8_t *)&E2_WORK_0x10, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x16, (uint8_t *)&E2_WORK_0x16, 2);
    getFromE2_E2ADDR_RAMADDR_LEN(0x18, (uint8_t *)&E2_WORK_0x18, 2);
    getFromE2_E2ADDR_RAMADDR_LEN(0x12, (uint8_t *)&E2_WORK_0x12, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x13, (uint8_t *)&E2_WORK_0x13, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x14, (uint8_t *)&E2_WORK_0x14, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1A, (uint8_t *)&E2_WORK_0x1A, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1B, (uint8_t *)&E2_WORK_0x1B, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1C, (uint8_t *)&E2_WORK_0x1C, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1D, (uint8_t *)&E2_WORK_0x1D, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1E, (uint8_t *)&E2_WORK_0x1E, 1);
}
