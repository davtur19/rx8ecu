/*
 * =============================================================================
 * rx8_get_from_e2.c  —  EEPROM SHADOW -> RAM COPY WITH COMPLEMENT VALIDATION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x39170
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_get_from_e2.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random vectors,
 *               real ROM bytes @0x39170; r0, the 256-byte destination window
 *               and the 256-byte primary/complement E2 shadows compared
 *               bit-exactly; 0 mismatches).
 * Lift (truth): c/getFromE2.c  (getFromE2_E2ADDR_RAMADDR_LEN @ 0x39170)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The generic "read len bytes from the on-chip EEPROM shadow into a RAM
 * buffer" helper of the EEPROM subsystem.  Every EEPROM location is stored as
 * a (value, ~value) pair; each byte is validated (`d == ~c`) before it is
 * copied, and a corrupt pair is either rebuilt from the FLASH backup (via the
 * SPI-retry hook + flash reader) or — if the SPI retry also fails — flagged in
 * the return value with the destination byte left untouched.  The boot-time
 * copy-out rx8_get_data_from_e2_ram @0x36C1C is built entirely on 19 calls to
 * this function (see samples/src/rx8_get_data_from_e2_ram.c), which also
 * proves the real calling convention used by the firmware.
 *
 * CALLING CONVENTION (SH-2E, full ABI — not a leaf)
 * -------------------------------------------------
 *     in  r4 = e2addr  (16-bit offset into the EEPROM shadow)
 *         r5 = ramaddr (destination RAM address)
 *         r6 = len     (byte count; the ROM loop-condition is `extu.b r9` +
 *                       `tst`, so len is effectively unsigned 8-bit)
 *     out r0 = error flag (0 = every byte valid or recovered from FLASH,
 *                          1 = at least one corrupt pair whose SPI retry
 *                          also failed — that byte is NOT copied)
 * The function uses the stack (saves r14..r8 + pr, 44 bytes) and makes four
 * `jsr` calls (getSR/setSR/retry/flash), so it is entered through the normal
 * ABI; the harness drives it with the plain `cpu.call(0x39170, r4, r5, r6)`.
 *
 * RAM CELLS (addresses verified from the literal pool @0x391EC..0x39208):
 *   r13 = 0xFFFFC2FE  E2 primary   shadow base (256 bytes, value byte)   [R/W]
 *   r11 = 0xFFFFC3FE  E2 complement shadow base (256 bytes, ~value)      [R/W]
 *   r8  = 0x06000000  flash-mapped backup window base (reads via 0xBFCA)
 *   r10 = e2addr, r12 = ramaddr, r9 = len, r14 = idx = e2addr & 0xFFFF
 *   stack @r15: [r15+0] saved_sr (u32), [r15+4] saved idx (u32, retry path),
 *               [r15+8] error flag (u8)
 *
 * CAL TABLES : none (no lookup tables; the only external data is the flash
 *              backup window 0x06000000 + ((idx>>1)&0xFF)<<16).
 *
 * CALLEES (all four are stubbed in the harness RAM overlay; the ROM bytes of
 *         the recovery path around them are executed for real):
 *   +--------+----------------------------------------+-----------------------+
 *   | addr   | role                                   | stub (host + emu)     |
 *   +--------+----------------------------------------+-----------------------+
 *   | 0x3920  | getSR(0x10): raise IPL, return old    | mov #0xF0,r0; rts;nop |
 *   | 0x3934  | setSR(saved_sr): restore IPL          | rts; nop              |
 *   | 0xC0A8  | e2_retry(): SPI retry poll            | mov #retry,r0;rts;nop |
 *   | 0xBFCA  | e2_flash_read(addr): SPI bit-bang     | mov #flash,r0;rts;nop |
 *   +--------+----------------------------------------+-----------------------+
 *   The real 0xBFCA busy-waits on peripheral status bits of 0xFFFFF024 that
 *   sh2emu cannot model, so it can never terminate there; stubbing it with an
 *   8-bit immediate (SIGN-extended to 32 bits, exactly like `mov #imm,r0`)
 *   makes the flash value observable and the host/emulator comparison exact.
 *
 * DISASSEMBLY / CROSS-CHECK (60E1D400.bin @ 0x39170, registers after each mov)
 * --------------------------------------------------------------------------
 *     2FE6  mov.l  r14,@-r15           ; prologue: callee-saved r14..r8 + pr
 *     2FD6  mov.l  r13,@-r15
 *     2FC6  mov.l  r12,@-r15
 *     6C53  mov    r5,r12              ; r12 = ramaddr
 *     D31C  mov.l  @(0x1C,pc),r3       ; r3 = 0x00003920 (getSR)
 *     2FB6  mov.l  r11,@-r15
 *     2FA6  mov.l  r10,@-r15
 *     6A43  mov    r4,r10              ; r10 = e2addr
 *     2F96  mov.l  r9,@-r15
 *     6963  mov    r6,r9               ; r9  = len
 *     2F86  mov.l  r8,@-r15
 *     4F22  sts.l  pr,@-r15
 *     7FF4  add    #-12,r15
 *     430B  jsr    @r3                 ; saved_sr = getSR(0x10)
 *     E410  mov    #0x10,r4            ;   (delay) r4 = 0x10
 *     2F02  mov.l  r0,@r15             ; saved_sr -> [r15]
 *     D81C  mov.l  @(0x1C,pc),r8       ; r8 = 0x06000000 (flash window)
 *     E000  mov    #0x00,r0
 *     DB1A  mov.l  @(0x1A,pc),r11      ; r11 = 0xFFFFC3FE (complement base)
 *     DD19  mov.l  @(0x19,pc),r13      ; r13 = 0xFFFFC2FE (data base)
 *     A04A  bra    0x39230             ; -> loop condition
 *     80F8  mov.b  r0,@(0x08,r15)      ;   (delay) error_flag = 0
 *     ...   loop body @0x3919C: idx = extu.w r10,r14; d = data[idx];
 *           c = comp[idx]; valid if (extu.b d) == (extu.b ~c); see the C.
 *     ...   retry path @0x391BC: jsr 0xC0A8; `exts.b r0,r0; tst r0,r0` so ANY
 *           nonzero stub return means "retry failed" (byte not copied).
 *     ...   recovery @0x391CA: flash_addr = 0x06000000 + ((idx>>1)&0xFF)<<16
 *           (shar; extu.b; shll16; add r8 — the add rides the jsr delay slot);
 *           raw = e2_flash_read(flash_addr); even idx -> (raw>>8)&0xFF,
 *           odd idx -> raw&0xFF (bf/s 0x39210 on `tst #1,idx`); then
 *           data[idx] = val, comp[idx] = ~val (0x0B34 mov.b r3,@(r0,r11)),
 *           *ramaddr = data[idx].
 *     ...   retry-failed @0x39226: error_flag = 1 (byte left untouched).
 *     ...   loop tail @0x3922A: r9--, r10++, r12++.
 *     639C  extu.b r9,r3               ; loop cond @0x39230: (len & 0xFF) != 0
 *     D32A  mov.l  @(0x2A,pc),r3       ; r3 = 0x00003934 (setSR)
 *     430B  jsr    @r3                 ; setSR(saved_sr)
 *     64F2  mov.l  @r15,r4             ;   (delay) r4 = saved_sr
 *     84F8  mov.b  @(0x08,r15),r0      ; r0 = error_flag
 *     7F0C  add    #0x0C,r15
 *     4F26  lds.l  @r15+,pr
 *     ...   mov.l  @r15+,r8..r13
 *     000B  rts
 *     6EF6  mov.l  @r15+,r14           ;   (delay) r14 restored
 *
 * DISCREPANCIES / NOTES vs c/getFromE2.c
 * --------------------------------------
 *  1. `len` width.  The lift signature uses uint8_t len; the ROM actually
 *     decrements the full 32-bit r9 and tests `extu.b r9` each iteration, so
 *     it is *effectively* uint8_t for every in-range caller.  A hypothetical
 *     r6 = 0x100 would run zero iterations on both the ROM and the C model —
 *     the harness constrains len to 0..255.
 *  2. getSR stub value.  The harness stubs getSR@0x3920 with `mov #0xF0,r0`
 *     (an 8-bit immediate, so the register actually holds 0xFFFFFFF0); the
 *     host stub returns 0xF0.  The saved value is consumed ONLY by the
 *     no-op setSR stub (0x3934 = rts;nop), so the two sides are observably
 *     identical (r0/dest/shadows compared, not SR).
 *  3. Recovery write-back.  The ROM writes `data[idx] = val`, re-reads it
 *     (mov.b @r4,r3, sign-extended), writes `comp[idx] = low-byte(~r3)`, then
 *     re-reads `data[idx]` again for `*ramaddr`.  The C models the final
 *     copy as a volatile re-read of `data[idx]`; with no concurrent
 *     interference the result is `val` on both sides.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"
#include "rx8_samples.h"

/* 0x39170 — getFromE2_E2ADDR_RAMADDR_LEN(e2addr, ramaddr, len), lift
 * c/getFromE2.c.  The four helpers below are the porting layer: they are
 * supplied by the host oracle (tests/oracle_get_from_e2.c) when this sample
 * is compiled for equivalence testing, and by the RAM-overlay stubs on the
 * emulator side (tests/harness_get_from_e2.py). */
uint32_t getSR(uint32_t arg);
void     setSR(uint32_t val);
int      e2_retry(void);
uint16_t e2_flash_read(uint32_t flashaddr);

#define RX8_E2_FLASH_WINDOW 0x06000000u  /* flash-mapped backup base (r8) */

uint8_t rx8_get_from_e2(uint16_t e2addr, uint8_t *ramaddr, uint8_t len)
{
    uint32_t saved_sr  = getSR(0x10);   /* jsr 0x3920: raise IPL, return old */
    uint8_t  error_flag = 0;            /* mov #0,r0 ; mov.b r0,@(8,r15)    */

    while (len != 0) {                  /* extu.b r9 ; tst ; bf/s @0x39230  */
        uint16_t idx = e2addr;          /* extu.w r10,r14                    */
        uint8_t d = RX8_IO8(RX8_E2_DATA_BASE + idx);        /* mov.b @(r0,r13),r3 */
        uint8_t c = RX8_IO8(RX8_E2_COMPLEMENT_BASE + idx);  /* mov.b @(r0,r11),r2 */

        if (d == (uint8_t)~c) {         /* extu.b/not/extu.b ; cmp/eq r2,r3  */
            *ramaddr = d;               /* mov.b r3,@r12: valid pair: copy   */
        } else {                        /* bf/s -> 0x391BC (mismatch)         */
            int ret = e2_retry();       /* jsr 0xC0A8; exts.b r0,r0; tst r0  */
            if (ret == 0) {
                /* SPI retry "clean": rebuild the pair from the FLASH backup.
                 * One 16-bit word covers two EEPROM bytes (even/high). */
                uint32_t flash_addr = RX8_E2_FLASH_WINDOW +
                                      (((uint32_t)((idx >> 1) & 0xFF)) << 16);
                uint16_t raw = e2_flash_read(flash_addr);  /* jsr 0xBFCA    */
                uint8_t  val = (idx & 1) ? (uint8_t)(raw & 0xFF)      /* odd  */
                                        : (uint8_t)((raw >> 8) & 0xFF); /* even */
                RX8_IO8(RX8_E2_DATA_BASE + idx) = val;          /* mov.b r5,@r4 */
                RX8_IO8(RX8_E2_COMPLEMENT_BASE + idx) = (uint8_t)~val;
                                                    /* 0x0B34 mov.b r3,@(r0,r11) */
                *ramaddr = RX8_IO8(RX8_E2_DATA_BASE + idx);     /* mov.b @r4,r2 */
            } else {
                error_flag = 1;         /* mov #1,r0 ; mov.b r0,@(8,r15)     */
            }
        }

        len--;                          /* add #-1,r9                         */
        e2addr++;                       /* add #1,r10                         */
        ramaddr++;                      /* add #1,r12                         */
    }

    setSR(saved_sr);                    /* jsr 0x3934                         */
    return error_flag;                  /* mov.b @(8,r15),r0                  */
}
