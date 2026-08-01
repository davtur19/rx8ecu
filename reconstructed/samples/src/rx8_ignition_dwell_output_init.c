/*
 * =============================================================================
 * rx8_ignition_dwell_output_init.c  —  IGNITION DWELL OUTPUT INIT
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x8F62  (code 0x8F62..0x8FB0, literal pool 0x8FB4..0x8FCB)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_ignition_dwell_output_init.py
 *               (host-gcc + mmap vs tools/sh2emu.py over random + edge
 *               pre-states; bit-exact RAM + MMIO side effects incl. the
 *               sensor-ADC chain, the four channel control words and the
 *               0x94C8 tail-phase's dwell-limit word).
 * Lift (truth): c/ignitionDwellOutputInit.c  (ignitionDwellOutputInit @ 0x8F62)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Power-on initialisation of the per-channel ignition dwell output timers.
 * It primes the sensor ADC conversion chain (0x8FCC), then loops over the
 * four ignition channels (rotors x coils) — reading each channel's
 * control-register ADDRESS from a ROM table (base 0xDAB4, stride 0x18),
 * handing it to the per-channel init leaf @0xAA74, clearing two control
 * bytes per channel and zeroing one 32-bit dwell cell — before tail-calling
 * the next init phase @0x94C8 via `bra` (which pops PR off the stack and
 * returns to the real caller).  The ROM sequence (60E1D400.bin @ 0x8F62):
 *
 *     2FE6..2F86   mov.l r14..r8,@-r15         ; prologue
 *     4F22         sts.l pr,@-r15
 *     B02B  bsr    0x8FCC                      ; sensor_adc_convert_chain
 *     0009  nop                                ;   (delay slot)
 *     EE00  mov    #0,r14
 *     DB13  mov.l  @(0x4C,pc),r11              ; r11 = 0xFFFFA0C4 (u32 cell)
 *     E904  mov    #4,r9                       ; 4 channels
 *     DC0D  mov.l  @(0x34,pc),r12              ; r12 = 0x0000DAB4 (table)
 *     6AE3  mov    r14,r10                     ; r10 = 0 (loop counter)
 *     DD10  mov.l  @(0x40,pc),r13              ; r13 = 0xFFFFA0D8 (ctrl blk)
 *     D80D  mov.l  @(0x34,pc),r8               ; r8  = 0x0000AA74 (leaf)
 * .loop: E500   mov #0,r5
 *     480B  jsr    @r8                         ; channel_init(ctrl, value=0)
 *     64C2  mov.l  @r12,r4                     ;   (delay) ctrl = *(u32*)r12
 *     60E3  mov    r14,r0                      ; r0 = 0
 *     80D4  mov.b  r0,@(4,r13)                 ; *(u8*)(r13+4) = 0
 *     7A01  add    #1,r10
 *     80D5  mov.b  r0,@(5,r13)                 ; *(u8*)(r13+5) = 0
 *     63AC  extu.b r10,r3
 *     2B02  mov.l  r0,@r11                     ; *(u32*)r11 = 0 (NOT leaf ret)
 *     7D08  add    #8,r13
 *     7B04  add    #4,r11
 *     3393  cmp/ge r9,r3                       ; T = (r10 >= 4)
 *     8FF2  bf/s   .loop                       ;   while r10 < 4
 *     7C18  add    #24,r12                     ;   (delay) next table entry
 *     4F26..6DF6   lds.l @r15+,pr / mov.l @r15+,r8..r13  ; epilogue
 *     A28B  bra    0x94C8                      ; tail-call next phase
 *     6EF6  mov.l  @r15+,r14                   ;   (delay) restore r14
 *
 * DISCREPANCIES vs THE LIFT (corrected here):
 *   1. The control table is READ (mov.l @r12,r4), not a table of addresses:
 *      the lift's static `channel_ctl_tbl` {0xDAB4, 0xDACC, 0xDAE4, 0xDAFC}
 *      lists the table's LOCATION; the ROM uses the 32-bit CONTENTS at
 *      0xDAB4 (stride 0x18) = {0xFFFFF650, 0xFFFFF654, 0xFFFFF652,
 *      0xFFFFF656}.  These are MMIO control-register addresses; the
 *      channel-init leaf @0xAA74 zeroes the 16-bit word at each.
 *   2. The 32-bit dwell cell is set to 0, NOT to the channel-init return
 *      value: the ROM does `mov r14,r0` (r0 = 0) then `mov.l r0,@r11`.
 *      The lift's `*(uint32_t*)dwell_ram = result` stores the leaf return.
 *   3. There are TWO RAM pointers, not one: r13 = 0xFFFFA0D8 (stride 8,
 *      byte-clears at +4/+5) and r11 = 0xFFFFA0C4 (stride 4, u32 zero
 *      store).  The lift merged them into a single 0xFFFFA0C4/stride-8 ptr.
 *   4. The channel-init callee is @0xAA74 with signature (u32 ctrl_addr,
 *      u16 value): it writes `value` to the u16 at ctrl_addr (twice) and
 *      calls the SR helper leaves @0x2054 / @0x2064 (no RAM side effect).
 *      The lift's `init_channel_func(ctrl_word)` passed the word and stored
 *      its return value — neither matches the ROM.
 *   5. Loop count is confirmed 4 (r9 = 4; counter r10 runs 1..4 against
 *      `cmp/ge r9,r3`) — the lift's "4 iterations" is correct.
 *   6. The tail target is 0x94C8 (the dwell-limit word update; model in the
 *      test rig's rx8_ignition_dwell_next_phase).  The lift names it
 *      next_init_phase.  It is not noreturn in the emulated sense: it pops
 *      PR (== the caller's return address) off the stack and `rts`'s back.
 *
 * CALLING CONVENTION
 * ------------------
 * Entry is the normal ABI (no arguments, no meaningful return).  The ROM
 * body calls THREE functions: the sensor ADC chain @0x8FCC (bsr), the
 * per-channel init leaf @0xAA74 (jsr; r4 = ctrl addr, r5 = 0) and the tail
 * phase @0x94C8 (bra).  None is a tiny leaf, so this sample declares them
 * extern; the host test rig supplies faithful models (the harness runs the
 * REAL ROM bytes of all three on the emulator side, so the models must be
 * bit-exact — see oracle_ignition_dwell_output_init.c).
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* Control-register addresses read from the ROM table at 0xDAB4 (u32 entries,
 * stride 0x18).  The channel-init leaf @0xAA74 zeroes the u16 at each.
 * Role: *unknown, matches ROM* (MMIO 0xFFFFF65x). */
#define RX8_DWELL_CTRL_0_ADDR  0xFFFFF650u
#define RX8_DWELL_CTRL_1_ADDR  0xFFFFF654u
#define RX8_DWELL_CTRL_2_ADDR  0xFFFFF652u
#define RX8_DWELL_CTRL_3_ADDR  0xFFFFF656u
/* 32-bit dwell cell, zeroed per channel (r11 = 0xFFFFA0C4, stride 4). */
#define RX8_DWELL_CELL_ADDR    0xFFFFA0C4u
/* 8-byte per-channel control block, bytes +4/+5 cleared (r13 = 0xFFFFA0D8,
 * stride 8). */
#define RX8_DWELL_CTRL_BLK_ADDR 0xFFFFA0D8u

/* Callees (see header): sensor ADC chain @0x8FCC, per-channel init leaf
 * @0xAA74 (writes `value` to the u16 at ctrl_addr) and next init phase
 * @0x94C8.  Defined by the test rig on the host; on the target they are the
 * real ROM functions. */
extern void rx8_sensor_adc_convert_chain(void);
extern void rx8_ignition_dwell_channel_init(uint32_t ctrl_addr, uint16_t value);
extern void rx8_ignition_dwell_next_phase(void);

/* 0x8F62 — initialise the ignition dwell outputs for all four channels. */
void rx8_ignition_dwell_output_init(void)
{
    /* Control-register addresses (ROM table @0xDAB4, stride 0x18). */
    static const uint32_t ctrl_tbl[4] = {
        RX8_DWELL_CTRL_0_ADDR, RX8_DWELL_CTRL_1_ADDR,
        RX8_DWELL_CTRL_2_ADDR, RX8_DWELL_CTRL_3_ADDR
    };
    volatile uint32_t *dwell_cell =
        (volatile uint32_t *)(uintptr_t)RX8_DWELL_CELL_ADDR;
    volatile uint8_t *ctrl_blk =
        (volatile uint8_t *)(uintptr_t)RX8_DWELL_CTRL_BLK_ADDR;

    rx8_sensor_adc_convert_chain();

    for (int i = 0; i < 4; i++) {
        /* Per-channel init leaf @0xAA74: r4 = ctrl addr, r5 = value (0);
         * it zeroes the u16 at the control-register address. */
        rx8_ignition_dwell_channel_init(ctrl_tbl[i], 0);

        /* Clear the per-channel control bytes (+4 = coil off, +5 = fault). */
        ctrl_blk[4] = 0;
        ctrl_blk[5] = 0;

        /* Zero the 32-bit dwell cell.  The ROM stores literal 0 here, NOT
         * the leaf's return value (see header discrepancy #2). */
        *dwell_cell = 0;

        ctrl_blk += 8;    /* next 8-byte control block   */
        dwell_cell += 1;  /* next 32-bit dwell cell      */
    }

    /* Tail-call to the next init phase @0x94C8 (`bra`; pops PR and
     * returns to the real caller). */
    rx8_ignition_dwell_next_phase();
}
