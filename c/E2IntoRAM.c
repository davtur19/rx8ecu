/*
 * E2IntoRAM  —  RX-8 PCM @ ROM 0x38F58 (60E1D400.bin)
 *
 * Boot-time load of EEPROM contents into the shadow RAM.  The EEPROM is not
 * read directly: the (value,~value) pairs are recovered from a FLASH backup
 * image, one 16-bit word per EEPROM byte-pair.  Each flash word at
 * 0x06000000 + ((half & 0xFF) << 16) holds the pair (high byte -> E2[2k],
 * low byte -> E2[2k+1]).
 *
 * For every half-word index k in [e2_addr>>1 .. (e2_addr+len-1)>>1] it stores:
 *    primary[2k]   = word >> 8        complement[2k]   = ~(word >> 8)
 *    primary[2k+1] = word & 0xFF      complement[2k+1] = ~(word & 0xFF)
 *
 * The SPI retry hook (0xC0A8) is polled twice first; if both calls return 1
 * the function aborts early returning 1.  Otherwise it returns 0.
 *
 * Original SH-2E listing (verified) — key structure:
 *   0x38F5A  mov r5,r0                ; r0 = length
 *   0x38F6E  mov.w r4,@r15            ; save e2_addr (word)
 *   0x38F70  mov.b r0,@(0x8,r15)      ; save length
 *   0x38F72  jsr getSR (r4=0x10)      ; saved @r15(0x14)
 *   0x38F7C  jsr 0xC0A8 (retry)       ; r13=1
 *   0x38F80  exts.b r0,r0 ; cmp/eq #1 ; r9 = r13 if both retries == 1
 *   0x38F9A  tst r9 ; bt/s continue
 *   setup:
 *   0x38FA4  mov.l @(0x126,pc),r5     ; 0xFFFFC502 (scratch)
 *   0x38FB0  extu.w r4,r4 ; shar r4   ; half_start = e2_addr >> 1
 *   0x38FB8  mov.w r3,@r5             ; 0xFFFFC502 = half_start
 *   0x38FBC  mov.b @(0x8,r15),r0      ; end = length + e2_addr - 1 (rounded)
 *   0x38FCA  shar r0 ; mov.w r0,@r2   ; 0xFFFFC504 = half_end
 *   0x38FE4  mov.l @(0x10A,pc),r8     ; 0xFFFFC2FE primary
 *   0x38FE8  mov.l @(0x10A,pc),r14    ; 0xFFFFC3FE complement
 *   loop (for half in half_start..half_end):
 *   0x38FF4  extu.b r12,r4 ; shll16   ; r4 = (half & 0xFF) << 16
 *   0x38FFA  jsr 0xBFCA (r4 += 0x06000000) ; word = flash_read(addr)
 *   0x39004  mov #0x1C,r0 ; mov.b r3,@r0,r15 ; scratch = word >> 8
 *   0x3900A  mov #0x18,r0 ; mov.b r4,@r0,r15 ; scratch = word & 0xFF
 *   0x39012  extu.w r4,r12            ; byte_idx = (half << 1) & 0xFFFF
 *   0x3901A  mov.b @r11,r3 ; mov.b r3,@r0,r5  ; primary[byte_idx]   = high
 *   0x39024  mov.b r3,@r0,r14         ; complement[byte_idx]   = ~high
 *   0x39030  mov.b r2,@r3             ; primary[byte_idx+1]   = low
 *   0x3903C  mov.b r2,@r3             ; complement[byte_idx+1] = ~low
 * Note: the disassembly contains a second, longer per-word path (0x39042..0x390F0)
 * that validates E2 data against two flash copies; it is unreachable because the
 * guard `tst r13,r13` always sees r13 = 1 (set in the delay slot of the first
 * 0xC0A8 call).  Only the direct-write path below executes.
 */
#include "eeprom_immo.h"

#define FLASH_WINDOW_BASE 0x06000000UL

uint8_t E2IntoRAM(uint16_t e2_addr, uint8_t length)
{
    uint8_t *primary   = (uint8_t *)E2_PRIMARY_BASE;
    uint8_t *complement = (uint8_t *)E2_COMPLEMENT_BASE;
    uint32_t saved_sr = getSR(0x10);
    uint8_t  result = 0;
    uint16_t half_start, half_end, half;

    /* Poll the SPI retry hook twice; if both report busy, give up now. */
    if (e2_retry() == 1 && e2_retry() == 1)
        result = 1;

    if (result != 0) {
        setSR(saved_sr);
        return result;
    }

    /* Half-word window covering [e2_addr, e2_addr + length).
     * end_raw = length + e2_addr - 1; T = (0 > end_raw) signed; then
     * end = (end_raw + T) >> 1 (asm uses cmp/gt + addc + shar). */
    uint32_t end_raw = (uint32_t)(uint8_t)length + (uint32_t)e2_addr - 1;
    uint8_t  t       = ((int32_t)end_raw < 0) ? 1 : 0;
    half_start = (uint16_t)(e2_addr >> 1);
    half_end   = (uint16_t)((end_raw + t) >> 1);

    for (half = half_start; half <= half_end; half++) {
        uint32_t flash_addr = FLASH_WINDOW_BASE + (((uint32_t)(half & 0xFF)) << 16);
        uint16_t word       = e2_flash_read(flash_addr);
        uint8_t  high       = (uint8_t)(word >> 8);  /* E2[2k]   */
        uint8_t  low        = (uint8_t)(word & 0xFF); /* E2[2k+1] */
        uint16_t byte_idx   = (uint16_t)(half << 1);

        primary[byte_idx]     = high;
        complement[byte_idx]  = (uint8_t)~high;
        primary[byte_idx + 1] = low;
        complement[byte_idx + 1] = (uint8_t)~low;
    }

    setSR(saved_sr);
    return result;
}
