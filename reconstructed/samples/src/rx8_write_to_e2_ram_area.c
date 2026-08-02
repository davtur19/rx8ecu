/*
 * =============================================================================
 * rx8_write_to_e2_ram_area.c  —  EEPROM SHADOW-RAM WRITE (value + ~value pair)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x39124   (extent 0x39124..0x3916F, per symbols/60E1D400_merged
 *               `writeToE2RAMArea_INDEX_ADDR_LEN`; 0x038F58..0x39124 is the
 *               preceding bulk_data_write_with_bounds_38F58 helper)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_write_to_e2_ram_area.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random vectors,
 *               real ROM bytes @0x39124; r0 + full 256-byte primary/complement
 *               E2 shadows compared bit-exactly; 0 mismatches).
 * Lift (truth): c/writeToE2RAMArea.c  (writeToE2RAMArea @ 0x39124)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The E2 (external EEPROM, ABLIC S-93C56C) working shadow lives in RAM at
 * 0xFFFFC2FE with its integrity complement shadow at 0xFFFFC3FE; every
 * EEPROM byte is stored as the (value, ~value) pair and readers accept a
 * byte only when byte == ~complement.  writeToE2RAMArea is the generic
 * in-RAM writer for that scheme: it copies `length` bytes from `src` into
 * the primary shadow at `index`, writing each byte's read-back complement
 * into the parallel shadow.  Callers include updateE2RAMBasedOnInput
 * @0x36D0C (see rx8_immo_update_related.c) which first mutates the working
 * copies and then commits them here.
 *
 * REAL DISASSEMBLY of 60E1D400.bin @ 0x39124 (verified from the ROM bytes):
 *
 *     2FE6  mov.l  r14,@-r15       ; prologue: save callee-saved regs
 *     6E63  mov    r6,r14          ; r14 = length (r6)
 *     D330  mov.l  @(0x30,PC),r3   ; r3 = 0x00003920 (getSR)  [pool @0x391EC]
 *     2FD6  mov.l  r13,@-r15       ; save r13
 *     2FC6  mov.l  r12,@-r15       ; save r12
 *     6D43  mov    r4,r13          ; r13 = index (r4)
 *     4F22  sts.l  pr,@-r15        ; save PR
 *     6C53  mov    r5,r12          ; r12 = src (r5)
 *     7FFC  add    #0xFC,r15       ; leave room for the saved SR
 *     430B  jsr    @r3             ; getSR(0x10)   [delay: mov #0x10,r4]
 *     D731  mov.l  @(0x31,PC),r7   ; r7 = 0xFFFFC3FE (complement base)
 *     D62F  mov.l  @(0x2F,PC),r6   ; r6 = 0xFFFFC2FE (primary base)
 *     A00A  bra    0x39156         ; jump to the loop test
 *     2F02  mov.l  r0,@r15         ;   [delay] save SR at [r15]
 *     loop:
 *     60DD  extu.w r13,r0          ; idx = index & 0xFFFF
 *     62C4  mov.b  @r12+,r2        ; b = *src++
 *     7EFF  add    #0xFF,r14       ; length--
 *     6503  mov    r0,r5
 *     356C  add    r6,r5           ; r5 = primary + idx
 *     2520  mov.b  r2,@r5          ; primary[idx] = b
 *     7D01  add    #0x01,r13       ; index++
 *     6350  mov.b  @r5,r3          ; r3 = primary[idx] READ BACK
 *     6337  not    r3,r3           ; r3 = ~primary[idx]
 *     0734  mov.b  r3,@(r0,r7)     ; complement[idx] = ~primary[idx]
 *     62EC  extu.b r14,r2          ; loop test: length (u8) != 0
 *     2228  tst    r2,r2
 *     8FF2  bf/s   0x39142         ; loop while length != 0
 *     0009  nop                    ;   [delay]
 *     D32B  mov.l  @(0x2B,PC),r3   ; r3 = 0x00003934 (setSR)  [pool @0x3920C]
 *     430B  jsr    @r3             ; setSR(saved_sr) [delay: mov.l @r15,r4]
 *     7F04  add    #0x04,r15
 *     4F26  lds.l  @r15+,pr        ; epilogue
 *     6CF6  mov.l  @r15+,r12
 *     6DF6  mov.l  @r15+,r13
 *     000B  rts
 *     6EF6  mov.l  @r15+,r14       ;   [delay] restore r14
 *
 * CALLING CONVENTION (SH-2E, normal ABI — NOT a leaf: jsr to helpers)
 * --------------------------------------------------------------------
 *     in  r4 = index (u16; extu.w-masked per iteration)
 *     in  r5 = src   (pointer to the bytes to store)
 *     in  r6 = length (u8; extu.b loop counter)
 *     out void; r0 = side channel (see below)
 * The function builds a real stack frame and calls getSR@0x3920 /
 * setSR@0x3934, so the harness enters it with the plain `cpu.call()`
 * (which seeds r4/r5/r6, gives it a stack at 0xFFFFDF00 and returns r0),
 * and the REAL getSR/setSR ROM bytes run inside the call — no stubbing is
 * needed (unlike the SPI helpers 0xC0A8/0xBFCA, which busy-wait on
 * peripheral bits sh2emu cannot model and ARE stubbed elsewhere).
 *
 * r0 SIDE CHANNEL
 * ---------------
 * The function returns nothing; the r0 left behind is an artifact:
 *   - length != 0: r0 = (index + length - 1) & 0xFFFF (last loop idx,
 *     because setSR never touches r0);
 *   - length == 0: r0 = 0xF0 (getSR's return = SR & 0xF0 with the default
 *     SR = 0xF0), the loop body never runs.
 * The harness compares that r0 too, computed from the inputs in the oracle
 * (this formula is read off the ROM listing, not off the C below).
 *
 * LIFT DISCREPANCIES (documented; the lift's C behaviour is correct)
 * -----------------------------------------------------------------
 *  1. Instruction listing.  The c/writeToE2RAMArea.c comment block prints
 *     addresses/displacements that do not match the real bytes (AI-drafted
 *     listing): e.g. it shows `mov.l @(0x60,pc),r3 ; 0x3920 getSR` at
 *     0x39128, while the real instruction is `D330 mov.l @(0x30,PC),r3`
 *     (same pool value 0x00003920 at 0x391EC), and it omits the r13/r12/PR
 *     saves and the getSR call entirely.  The C body of the lift — the
 *     loop, the read-back complement and the getSR/setSR envelope — matches
 *     the real code; the listing is only approximate.
 *  2. Index width.  The lift reads `uint16_t index` with a 32-bit counter
 *     in the ROM (r13, `add #1` full-width) and `extu.w` per iteration; the
 *     C's uint16_t wrap is bit-exact with the masked writes.
 *  3. Read-back complement.  complement[idx] is the complement of the value
 *     READ BACK from primary[idx] (`mov.b @r5,r3` after the store), not of
 *     the source byte — equal unless a hardware write filter intervenes.
 *  4. Older docs/functions/writeToE2RAMArea_INDEX_ADDR_LEN.md (0x385C4,
 *     `_source: AI draft, unverified`) is superseded by the verified lift
 *     c/writeToE2RAMArea.c and by the symbol 0x39124 in
 *     symbols/60E1D400_merged.csv.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* 0x3920 — getSR(arg): returns SR & 0xF0 (never takes the ldc path when
 * arg <= SR&0xF0).  0x3934 — setSR(val): writes SR (r4 != 0 path).
 * Both are real ROM code that terminates cleanly under the emulator; the
 * host oracle supplies its own stubs through the porting layer. */
uint32_t getSR(uint32_t arg);
void     setSR(uint32_t val);

void rx8_write_to_e2_ram_area(uint16_t index, const uint8_t *src, uint8_t length)
{
    volatile uint8_t *primary    = (volatile uint8_t *)RX8_E2_DATA_BASE;
    volatile uint8_t *complement = (volatile uint8_t *)RX8_E2_COMPLEMENT_BASE;
    uint32_t saved_sr = getSR(0x10);          /* disable interrupts */

    while (length != 0) {
        uint16_t idx = index;                 /* extu.w r13,r0          */
        uint8_t  b   = *src++;                /* mov.b @r12+,r2         */
        length--;                             /* add #0xFF,r14          */
        index++;                              /* add #0x01,r13          */
        primary[idx]   = b;                   /* mov.b r2,@r5           */
        complement[idx] = (uint8_t)~primary[idx]; /* read-back, not, store */
    }

    setSR(saved_sr);
}
