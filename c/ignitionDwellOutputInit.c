/* ignitionDwellOutputInit.c
 *
 * ROM: 60E1D400  |  Address: 0x8F62  |  Size: 0x6A bytes (code 0x8F62..0x8FB0;
 *       literal pool @0x8FB2..0x8FCB; next function sensor_adc_convert_chain
 *       @0x8FCC).
 *       VERIFIED vs ROM emulator (0 mismatches, c/tests/test_ignitionDwellOutputInit.py).
 *
 * Ignition dwell output init.  First stage of the ignition sensor/task chain
 * (0x8F62 -> 0x94C8 get_ignition_dwell_time; trampoline 0x9148 also reaches
 * 0x94C8).  Primes the coil-output peripheral register block, then for each of
 * the 4 coil channels (rotors x coils) zeroes the channel control word, and
 * finally tail-calls the dwell-time lookup.
 *
 * Semantics (execution order):
 *   1. sensor_adc_convert_chain @0x8FCC — primes the coil-output peripheral
 *      block (RAM 0xFFFFF600..0xFFFFF680): calls setSR_PARAM @0x2054(stack,
 *      0xE0) which restores SR to 0xF0, then read-modify-writes:
 *        u8 @0xFFFFF627  <- (x & 0xF8) | 1
 *        u16@0xFFFFF630  &= 0xFFFE
 *        u16@0xFFFFF66C  &= 0xFEFF
 *        u8 @0xFFFFF626  <- (x & 0xF8) | 1
 *      and finally ldc SR @0x2064(u32@stack) restoring SR to its entry value.
 *   2. Loop over 4 channels i = 0..3 (cfg table @0xDAB4, stride 0x18; pointer
 *      loaded into r8 from pool @0x8FB8):
 *        cfg = u32@(0x0000DAB4 + i*0x18)          (0xFFFFF650/654/652/656)
 *        call @0xAA74(cfg, 0) — setSR_PARAM @0x2054 + @0x2064, then zeroes
 *          u16@cfg twice (2x u16 = 4 bytes at the cfg address).
 *        u8 @(0xFFFFA0D8 + i*8 + 4) = 0           (coil on/off byte)
 *        u8 @(0xFFFFA0D8 + i*8 + 5) = 0           (fault byte)
 *        u32@(0xFFFFA0C4 + i*4)     = 0           (dwell output word)
 *   3. Tail-call (bra) get_ignition_dwell_time @0x94C8 — reads RPM
 *      (f32@0xFFFF9F80), battery voltage (f32@0xFFFF9F68) and dwell offset
 *      (u16@0xFFFFA0D6); writes the saturated dwell time u16@0xFFFFA0D4.
 *
 * Inputs (RAM reads):  9F80 (RPM), 9F68 (battV), A0D6 (offset) via the 0x94C8
 *   tail call; 0xFFFFF626/627/630/66C read-modify-write by the 0x8FCC callee.
 *   ROM: cfg table 0xDAB4, callee addresses 0x8FCC / 0xAA74 (indirect via pool
 *   @0x8FB8) / 0x2054 / 0x2064.
 * Outputs (RAM writes): A0C4..A0D3 (4x u32 zero), A0DC/A0DD, A0E4/A0E5,
 *   A0EC/A0ED, A0F4/A0F5 (u8 zero), A0D4 (u16 dwell via 0x94C8), and the
 *   0xFFFFF6xx peripheral block via the 0x8FCC / 0xAA74 callee chain.
 *
 * The callees (0x8FCC, 0xAA74, 0x94C8) are deliberately NOT inlined: the
 * harness executes them in a second emulator instance (emulator-in-model, same
 * trick as c/calc_spark_lead_trail_split_19220.c) so their full RAM side
 * effects and SR handling match the ROM exactly.
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>

#define ROM_CFG_TBL ((const uint32_t *)0x0000DAB4)   /* 4 channel config words, stride 0x18 */

#define RAM_A0C4_ARR ((volatile uint32_t *)0xFFFFA0C4)  /* per-channel dwell word (4x u32) */
#define RAM_A0D8_ARR ((volatile uint8_t  *)0xFFFFA0D8)  /* per-channel control block (4x u8[8]) */

/* ---- callees (executed by the harness in a second emulator instance) ---- */
extern void sensor_adc_convert_chain_0x8FCC(void);              /* 0x8FCC */
extern void ignition_channel_setup_0xAA74(uint32_t cfg);        /* 0xAA74(cfg, r5=0) */
extern void get_ignition_dwell_time_0x94C8(void);               /* 0x94C8 (tail-call) */

/* 0x008F62 — initialise ignition dwell output for all channels */
void ignitionDwellOutputInit(void)
{
    sensor_adc_convert_chain_0x8FCC();

    for (int i = 0; i < 4; i++) {
        uint32_t cfg = ROM_CFG_TBL[i * 6];   /* u32@(0xDAB4 + i*0x18) */
        ignition_channel_setup_0xAA74(cfg);
        RAM_A0D8_ARR[i * 8 + 4] = 0;         /* coil on/off byte */
        RAM_A0D8_ARR[i * 8 + 5] = 0;         /* fault byte */
        RAM_A0C4_ARR[i] = 0;                 /* dwell output word */
    }

    get_ignition_dwell_time_0x94C8();        /* tail-call (bra 0x94C8) */
}
