/*
 * =============================================================================
 * rx8_get_speed_limit_cal.c  —  SPEED-LIMIT CALIBRATION GETTER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x49EFC            Size: 0x49FB8 - 0x49EFC = 0x0BC (188 bytes)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_get_speed_limit_cal.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random RAM-state
 *               vectors, comparing every side-effected register and flag cell;
 *               0 mismatches).
 * Lift (truth): c/getSpeedLimitCal.c  (getSpeedLimitCal @ 0x49EFC)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Periodically programs the three speed-limit threshold registers (0xFFFFCD4C
 * / 0xFFFFCD4D / 0xFFFFCD4E) and four associated status flags
 * (0xFFFFCD4F..0xFFFFCD52) from a small set of fixed calibration lookup
 * tables.  The "limit id" is derived at runtime from RAM by callee 0x49FC4
 * (NOT passed via ABI).  Disassembly of 60E1D400.bin @ 0x49EFC:
 *
 *    4F23  mov.l  r14,@-r15   ; prologue (r14, r13, r12, pr)
 *    4F23  mov.l  r13,@-r15
 *    4F23  mov.l  r12,@-r15
 *    4F22  sts.l  pr,@-r15
 *    B02B  bsr    0x49FC4     ; call lookup @0x49FC4 (limit id -> r0)
 *    0009  nop                 ;   (delay slot)
 *    D916  mov.w  @(0x16,pc),r12  ; r12 = 0x0080
 *    6D30  mov    r0,r5         ; r5  = limit id
 *    E300  mov    #0x00,r13
 *    6344  mov    r13,r4        ; r4  = 0  (default threshold A value)
 *    65EC  extu.b r5,r0
 *    CB70  cmp/eq #0x0A,r0            ; id == 10 ?
 *    8903  bt/s   0x49F44
 *    E040  mov    #0x40,r14
 *    ... (switch on the id, mapping it to a byte for register 0xFFFFCD4C) ...
 *    2620  mov.b  r4,@r2        ; RAM[0xFFFFCD4C] = threshold A (jsr delay)
 *    BJ.4  jsr    0x4A020       ;   config-B lookup (result -> r0)
 *    ... (switch B result -> 0xFFFFCD4D) ...
 *    2620  mov.b  r4,@r3        ; RAM[0xFFFFCD4D] = threshold B
 *    BJ.4  jsr    0x4A07E       ;   config-C lookup (result -> r0)
 *    ... (switch C result -> 0xFFFFCD4E) ...
 *    2620  mov.b  r4,@r3        ; RAM[0xFFFFCD4E] = threshold C
 *    BJ.4  jsr    0x4A106       ;   config-D lookup (result unused)
 *    95024 lds.l  @r15+,pr
 *    6E96  mov.l  @r15+,r12
 *    6E97  mov.l  @r15+,r13
 *    6E98  mov.l  @r15+,r14
 *    000B  rts                  ;   (delay slot)
 *
 * The INPUTS are RAM[0xFFFFD3D4] (u16 id-key), RAM[0xFFFFD3D0] (u32 B-key),
 * RAM[0xFFFFD3D6] (u8 C-key) and RAM[0xFFFFD3D7] (u8 D-key); the OUTPUT is the
 * seven committed cells listed in RAM SIDE EFFECTS.
 *
 * CALLING CONVENTION
 * ------------------
 * void rx8_get_speed_limit_cal(void): NORMAL ABI NO-ARG entry, no input
 * register, no meaningful return value.  Driven through sh2emu.call(0x49EFC,
 * ram) and verified by comparing the seven side-effected RAM cells.
 *
 * CALLEES (their ROM bytes are always executed by the emulator = ground
 * truth; the host sample below inlines their net RAM effects verbatim):
 *   1. lookup  @0x49FC4 — reads u16 RAM[0xFFFFD3D4], matches table @0x04ED90,
 *      returns the matching limit-id byte; writes flag RAM[0xFFFFCD4F].
 *      Non-match -> flag=1, id=10.
 *   2. configB @0x4A020 — reads u32 RAM[0xFFFFD3D0], matches table @0x04EDB0
 *      returning {0,1}; writes flag RAM[0xFFFFCD50].
 *   3. configC @0x4A07E — reads u8 RAM[0xFFFFD3D6], matches table @0x04EDC8
 *      returning {0,1,2}; on a no-match loads the ROM fall-back byte
 *      0x07C59C = 0x02.  Writes flag RAM[0xFFFFCD51].
 *   4. configD @0x4A106 — reads u8 RAM[0xFFFFD3D7], matches table @0x04EDD0;
 *      its result is unused (only the flag RAM[0xFFFFCD52] is produced).
 *
 * ADDRESS CONVENTION
 * ------------------
 * Every RAM address above is reached by the ROM through a `mov.w` literal,
 * which SIGN-EXTENDS the 16-bit word to 0xFFFFxxxx (same convention as
 * rx8_temperature_gauge_5aa5c and rx8_warning_light_5aade).  The disassembler
 * prints only the low 16 bits (0xCD4C, 0xD3D4, ...); the real effective
 * addresses are 0xFFFFCD4C, 0xFFFFD3D4, ... (on-chip RAM window).
 *
 * DISCREPANCIES FOUND IN THE LIFT (c/getSpeedLimitCal.c):
 * --------------------------------------------------------
 *   1. Parameter: the lift declares getSpeedLimitCal(uint8_t limit_id) and
 *      passes the id via ABI.  The ROM takes NO argument; the id is derived at
 *      runtime by lookup 0x49FC4 from RAM[0xFFFFD3D4].
 *   2. Callee shape: the lift posts three helpers; the ROM uses FOUR distinct
 *      table lookups (0x49FC4, 0x4A020, 0x4A07E, 0x4A106) and, as side
 *      effects, writes to FOUR status flags (0xFFFFCD4F..0xFFFFCD52) that the
 *      lift never produced.
 *   3. Third mapping: the lift's "case 2 -> 0x20" shape fits only the C lookup
 *      (whose result is {0,1,2}); the B lookup only ever returns {0,1}.
 *
 * RAM SIDE EFFECTS (cells the harness compares)
 * ---------------------------------------------
 *   RAM[0xFFFFCD4C] u8 = threshold A   (from the limit-id switch)
 *   RAM[0xFFFFCD4D] u8 = threshold B   (from config-B {0,1})
 *   RAM[0xFFFFCD4E] u8 = threshold C   (from config-C {0,1,2})
 *   RAM[0xFFFFCD4F] u8 = lookup@0x49FC4 flag (0 found, 1 fallback)
 *   RAM[0xFFFFCD50] u8 = config-B flag (0 / 1)
 *   RAM[0xFFFFCD51] u8 = config-C flag (0 / 1)
 *   RAM[0xFFFFCD52] u8 = config-D flag (0 / 1)
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h" /* RX8_IO8 / RX8_IO16 / RX8_IO32 */

/* ---- fixed machine addresses (mov.w literals, sign-extended to 0xFFFF..) - */
#define SPD_KEY1_ADDR   0xFFFFD3D4u  /* u16 lookup-id key  (lit pool @0x4A0D2) */
#define SPD_KEY2_ADDR   0xFFFFD3D0u  /* u32 config-B key   (lit pool @0x4A0D6) */
#define SPD_KEY3_ADDR   0xFFFFD3D6u  /* u8  config-C key   (lit pool @0x4A0DA) */
#define SPD_KEY4_ADDR   0xFFFFD3D7u  /* u8  config-D key   (lit pool @0x4A166) */
#define SPD_REG_A_ADDR  0xFFFFCD4Cu  /* u8  threshold A    (lit pool @0x49FBE) */
#define SPD_REG_B_ADDR  0xFFFFCD4Du  /* u8  threshold B    (lit pool @0x49FC0) */
#define SPD_REG_C_ADDR  0xFFFFCD4Eu  /* u8  threshold C    (lit pool @0x49FC2) */
#define SPD_FLAG_A_ADDR 0xFFFFCD4Fu  /* u8  flag - lookup  (lit pool @0x4A0CE) */
#define SPD_FLAG_B_ADDR 0xFFFFCD50u  /* u8  flag - configB(lit pool @0x4A0D4) */
#define SPD_FLAG_C_ADDR 0xFFFFCD51u  /* u8  flag - configC(lit pool @0x4A0D8) */
#define SPD_FLAG_D_ADDR 0xFFFFCD52u  /* u8  flag - configD(lit pool @0x4A162) */

/* ---- byte-assembled 16/32-bit reads (host is little-endian) -------------- */
static uint16_t spd_u16(uint32_t a)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)a;
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

static uint32_t spd_u32(uint32_t a)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)a;
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
         | ((uint32_t)p[2] << 8)  | (uint32_t)p[3];
}

/* ---- lookup @0x49FC4 — u16 id-key -> limit id (table 0x04ED90) ----------- */
static uint8_t spd_lookup_id(void)
{
    uint16_t key = spd_u16(SPD_KEY1_ADDR);

    static const uint16_t k[7] = {
        0x3041, 0x3031, 0x3032, 0x3036, 0x4631, 0x4630, 0x3035 };
    static const uint8_t  v[7] = {
        0x0A, 0x01, 0x02, 0x06, 0xF1, 0xF0, 0x05 };
    int i;

    for (i = 0; i < 7; i++) {
        if (key == k[i]) { RX8_IO8(SPD_FLAG_A_ADDR) = 0; return v[i]; }
    }
    RX8_IO8(SPD_FLAG_A_ADDR) = 1;   /* sentinel / no-match -> flag 1        */
    return 0x0A;                    /* default id 0x0A (10)                  */
}

/* ---- configB @0x4A020 — u32 -> {0,1} (table 0x04EDB0) -------------------- */
static uint32_t spd_config_b(void)
{
    uint32_t k = spd_u32(SPD_KEY2_ADDR);

    if (k == 0x31334820u) { RX8_IO8(SPD_FLAG_B_ADDR) = 0; return 0; }
    if (k == 0x31335320u) { RX8_IO8(SPD_FLAG_B_ADDR) = 0; return 1; }
    RX8_IO8(SPD_FLAG_B_ADDR) = 1;   /* sentinel row (v = 0xFF)               */
    return 0;
}

/* ---- configC @0x4A07E — u8 -> {0,1,2} (table 0x04EDC8) ------------------- */
static uint32_t spd_config_c(void)
{
    uint8_t k = RX8_IO8(SPD_KEY3_ADDR);

    if (k == 0x4E) { RX8_IO8(SPD_FLAG_C_ADDR) = 0; return 0x00; }
    if (k == 0x35) { RX8_IO8(SPD_FLAG_C_ADDR) = 0; return 0x01; }
    if (k == 0x36) { RX8_IO8(SPD_FLAG_C_ADDR) = 0; return 0x02; }
    RX8_IO8(SPD_FLAG_C_ADDR) = 1;   /* no-match sentinel                    */
    return 0x02;                    /* ROM fall-back byte 0x07C59C = 0x02   */
}

/* ---- configD @0x4A106 — u8; result unused, only flag written ------------- */
static void spd_config_d(void)
{
    uint8_t k = RX8_IO8(SPD_KEY4_ADDR);
    RX8_IO8(SPD_FLAG_D_ADDR) = (k == 0x30) ? 0 : 1;
}

/* ---- 0x49EFC speed-limit calibration getter ------------------------------ */
void rx8_get_speed_limit_cal(void)
{
    uint32_t id, r;
    uint8_t  a, b, c;

    id = spd_lookup_id();   /* r0 of bsr 0x49FC4 */

    /* Map the limit id to threshold A (the switch of the body). */
    switch (id) {
        case 0x0A: a = 0x80; break;
        case 0x01: a = 0x40; break;
        case 0x02: a = 0x20; break;
        case 0x06: a = 0x10; break;
        case 0xF1: a = 0x08; break;
        case 0xF0: a = 0x04; break;
        case 0x05: a = 0x02; break;
        default:   a = 0x00; break;
    }
    RX8_IO8(SPD_REG_A_ADDR) = a;

    r = spd_config_b();                      /* {0,1} */
    b = (r == 0) ? 0x80 : (r == 1) ? 0x40 : 0x00;
    RX8_IO8(SPD_REG_B_ADDR) = b;

    r = spd_config_c();                      /* {0,1,2} */
    c = (r == 0) ? 0x80 : (r == 1) ? 0x40 : (r == 2) ? 0x20 : 0x00;
    RX8_IO8(SPD_REG_C_ADDR) = c;

    spd_config_d();                          /* only flag 0xFFFFCD52 */
}