/*
 * =============================================================================
 * rx8_knock_function_init.c  —  KNOCK DETECTION SUBSYSTEM INIT
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xC31C  (42 bytes: 0xC31C..0xC345)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_knock_function_init.py
 *               (host-gcc + mmap vs tools/sh2emu.py over random + edge
 *               pre-states; bit-exact RAM side effects incl. the two float
 *               thresholds, the scaling float and both flag bytes).
 * Lift (truth): c/knockFunctionInit.c  (knockFunctionInit @ 0x00C31C, 42 bytes)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Power-on initialisation of the knock detection subsystem, run after the ATU
 * waveform generator and knock-related I/O are configured.  It arms the two
 * 16-bit knock-threshold references, installs the knock scaling factor, and
 * clears the knock-status flag bytes.  The ROM sequence (60E1D400.bin @
 * 0xC31C) is:
 *
 *     4F22  sts.l  pr,@-r15            ; prologue
 *     B012  bsr    0xC346              ; atu2_tior2c_waveform_init (ATU2 timer)
 *     0009  nop                        ;   (delay slot)
 *     B051  bsr    0xC3C8              ; knockRelatedInit (knock filter/thresholds)
 *     0009  nop                        ;   (delay slot)
 *     D41F  mov.l  @(0x1F,pc),r4       ; r4 = 0x0000AC08   (threshold value)
 *     D31F  mov.l  @(0x1F,pc),r3       ; r3 = 0xFFFFA37A   (threshold ref B)
 *     2341  mov.w  r4,@r3              ; *(u16*)0xFFFFA37A = 0xAC08   (WORD)
 *     D21F  mov.l  @(0x1F,pc),r2       ; r2 = 0xFFFFA378   (threshold ref A)
 *     2241  mov.w  r4,@r2              ; *(u16*)0xFFFFA378 = 0xAC08   (WORD)
 *     C71F  mova   0xC3B0,r0           ; r0 = ADDRESS of the literal pool
 *     E400  mov    #0x00,r4            ; r4 = 0
 *     D317  mov.l  @(0x17,pc),r3       ; r3 = 0xFFFFA38C   (knock flag A)
 *     F308  fmov.s @r0,fr3             ; fr3 = *(float*)0xC3B0  (ROM const!)
 *     D11E  mov.l  @(0x1E,pc),r1       ; r1 = 0xFFFFA374   (knock scale float)
 *     F13A  fmov.s fr3,@r1             ; *(float*)0xFFFFA374 = fr3  (4 bytes)
 *     2340  mov.b  r4,@r3              ; *(u8*)0xFFFFA38C = 0        (BYTE)
 *     D21E  mov.l  @(0x1E,pc),r2       ; r2 = 0xFFFFA325   (knock flag B)
 *     4F26  lds.l  @r15+,pr            ; epilogue
 *     000B  rts
 *     2240  mov.b  r4,@r2              ; *(u8*)0xFFFFA325 = 0 (BYTE, delay slot)
 *
 * DISCREPANCY vs THE LIFT (corrected here):
 *   c/knockFunctionInit.c writes `*knock_scale = 0.0f` ("value ~0.0f") — the
 *   lift's only substantive error.  The ROM does NOT write 0.0f: the float is
 *   read from the function's own literal pool at 0xC3B0 (mova @ 0xC330 loads
 *   the ADDRESS, then `fmov.s @r0,fr3` dereferences it), and those bytes are
 *   47 2C 08 00 = 44040.0f.  This sample therefore stores 44040.0f, which the
 *   harness pins bit-exactly (a 0.0f store fails every vector).
 *
 * OTHER VERIFIED NUANCES (all match the lift):
 *   - The two threshold references are 16-bit `mov.w` stores — each also
 *     clears its adjacent high byte (0xFFFFA379 / 0xFFFFA37B, sentinel-pinned).
 *   - The scale float is a 4-byte `fmov.s` store at 0xFFFFA374 (the two u16
 *     thresholds at 0xFFFFA378 / 0xFFFFA37A sit immediately after it).
 *   - Both knock flag writes are `mov.b` (byte) — neighbours survive.
 *
 * CALLING CONVENTION
 * ------------------
 * Entry is the normal ABI (no arguments, no meaningful return).  The two
 * sub-calls run BEFORE the register writes in the ROM; their internals write
 * other RAM (e.g. knockRelatedInit fills 0xFFFFA360..0xFFFFA37E) but the
 * function under test neither reads nor depends on any of that — so on the
 * host they are provided as stubs by the test rig (same convention as
 * rx8_crank_sensor_init.c's tail-call stub), and the harness compares only
 * the five writes this function performs plus their store-width sentinels.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* Knock threshold references (16-bit, written with `mov.w`).  Role: *unknown,
 * matches ROM* (c/knockFunctionInit.c; "knock threshold refs"). */
#define RX8_KNOCK_THRESH_1_ADDR 0xFFFFA37Au  /* written first in the ROM   */
#define RX8_KNOCK_THRESH_2_ADDR 0xFFFFA378u
/* Knock threshold scaling factor (float, written with `fmov.s`, 4 bytes).
 * Role: *unknown, matches ROM* — NOTE the ROM constant is 44040.0f, not 0.0f
 * (see header: corrected vs the lift). */
#define RX8_KNOCK_SCALE_ADDR    0xFFFFA374u
/* Knock-status flag bytes (8-bit, written with `mov.b`).  Role: *unknown,
 * matches ROM*. */
#define RX8_KNOCK_FLAG_A_ADDR   0xFFFFA38Cu
#define RX8_KNOCK_FLAG_B_ADDR   0xFFFFA325u

/* Sub-functions invoked by the ROM before the register writes: the ATU2
 * compare-output set-up (0xC346) and the knock filter/threshold init
 * (0xC3C8).  Defined by the test rig on the host; on the target they are the
 * real ROM functions. */
extern void atu2_tior2c_waveform_init(void);
extern void knockRelatedInit(void);

/* 0xC31C — initialise the knock detection subsystem. */
void rx8_knock_function_init(void)
{
    atu2_tior2c_waveform_init();
    knockRelatedInit();

    RX8_IO16(RX8_KNOCK_THRESH_1_ADDR) = 0xAC08u;
    RX8_IO16(RX8_KNOCK_THRESH_2_ADDR) = 0xAC08u;

    /* ROM: `mova 0xC3B0,r0` + `fmov.s @r0,fr3` + `fmov.s fr3,@r1` — the
     * 44040.0f constant lives in this function's own literal pool. */
    *(volatile float *)(uintptr_t)RX8_KNOCK_SCALE_ADDR = 44040.0f;

    RX8_IO8(RX8_KNOCK_FLAG_A_ADDR) = 0x00u;
    RX8_IO8(RX8_KNOCK_FLAG_B_ADDR) = 0x00u;
}
