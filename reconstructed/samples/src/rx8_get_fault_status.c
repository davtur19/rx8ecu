/*
 * =============================================================================
 * rx8_get_fault_status.c  —  FAULT-CHANNEL STATUS GETTER (PRIMARY + SECONDARY)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x6743C
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_get_fault_status.py
 *               (host-gcc vs tools/sh2emu.py over random + edge vectors, real
 *               ROM tables from this .bin, backup-RAM seeds on both sides;
 *               0 mismatches).
 * Lift (truth): c/getFaultStatus.c  (getFaultStatus @ 0x6743C)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The primary fault-query interface of the diagnostics subsystem — the docs
 * (docs/subsystems/FAULT_DIAGNOSTICS_SUBSYSTEM.md) count 78 call sites.  A
 * fault channel index is tested against a per-channel 32-bit ROM table entry
 * ANDed with a runtime RAM enable mask; only when that primary test fails is
 * the (much heavier) secondary evaluator rx8_get_fault_eval_state @0x67494
 * consulted.  Disassembly of 60E1D400.bin @ 0x6743C:
 *
 *     2FE6   mov.l  r14,@-r15
 *     2FD6   mov.l  r13,@-r15
 *     4F22   sts.l  pr,@-r15
 *     6D4D   extu.w r4,r13            ; channel & 0xFFFF
 *     D07C   mov.l  0x67638,r0        ; r0 = 0x0007E4DC (fault table)
 *     4D08   shll2  r13               ; * 4
 *     D37A   mov.l  0x67634,r3        ; r3 = 0xFFFFD96C (enable mask)
 *     6532   mov.l  @r3,r5            ; r5 = enable_mask
 *     02DE   mov.l  @(r0,r13),r2      ; r2 = entry = table[channel]
 *     2259   and    r5,r2
 *     622D   extu.w r2,r2             ; keep low 16 bits
 *     2228   tst    r2,r2
 *     8D01   bt/s   .prim0            ; (delay) r14 = 0
 *     EE00   mov    #0x00,r14
 *     EE01   mov    #0x01,r14         ; primary hit -> r14 = 1
 * .prim0: 63EC extu.b r14,r3
 *     2338   tst    r3,r3
 *     8F0B   bf/s   .done             ; primary hit -> skip secondary
 *     0009   nop
 *     B017   bsr    0x67494           ; rx8_get_fault_eval_state(channel)
 *     0009   nop
 *     6403   mov    r0,r4             ; r4 = eval bitmask
 *     D274   mov.l  0x6763C,r2        ; r2 = 0xFFFF0000
 *     D073   mov.l  0x67638,r0        ; r0 = 0x0007E4DC
 *     03DE   mov.l  @(r0,r13),r3      ; r3 = entry (re-read)
 *     2349   and    r4,r3
 *     2328   tst    r2,r3             ; (entry & eval) & 0xFFFF0000 ?
 *     8D01   bt/s   .done
 *     0009   nop
 *     EE01   mov    #0x01,r14         ; secondary hit -> r14 = 1
 * .done: 4F26 lds.l @r15+,pr
 *     60E3   mov    r14,r0
 *     6DF6   mov.l  @r15+,r13
 *     000B   rts
 *     6EF6   mov.l  @r15+,r14         ;   (delay slot)
 *
 * CALLING CONVENTION
 * ------------------
 * Plain SH-2 ABI: r4 = uint16_t channel (upper 16 bits ignored via extu.w),
 * result returned in r0 as 0/1.  The function is read-only w.r.t. RAM: the
 * only memory traffic is the enable-mask read @0xFFFFD96C, the ROM table read
 * @0x0007E4DC + channel*4 (also re-read for the secondary check) and the
 * callee's own RAM reads.
 *
 * RAM
 * ---
 * 0xFFFFD96C  uint32_t  fault enable mask (runtime-configurable; seeded by
 *                       the harness and mirrored by the oracle via the same
 *                       MAP_FIXED trick as tests/host_oracle.c).
 *
 * CALLEE (NOT MODELLED HERE)
 * --------------------------
 * rx8_get_fault_eval_state @ 0x67494 ("getFaultStatus_subcheck" in the docs)
 * runs nine condition checks (0x67534 stub, 0x67538 DTC-list walk, 0x675AC
 * indirect table, 0x675CA DTC-data check, 0x675E6 byte-indexed check) and
 * ORs their bits into a 32-bit bitmask.  It is far from a tiny leaf (it
 * recursively reads several ROM tables and backup-RAM flags), so this sample
 * only DECLARES it; the host-side model lives in
 * reconstructed/samples/tests/oracle_get_fault_status.c and mirrors the ROM
 * semantics bit-for-bit (all five stub/constant paths included).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* Fault enable mask (runtime-configurable) — on-chip RAM, read once. */
#define RX8_FAULT_ENABLE_MASK_ADDR  0xFFFFD96Cu
/* Per-channel fault status table — ROM, 32-bit entries at channel*4.
 * For channel up to 0xFFFF the word read stays inside the 512 KiB ROM
 * (0x7E4DC + 0xFFFF*4 = 0xBE4D8 < 0x80000), exactly like the ROM's
 * mov.l @(r0,r13) which wraps to whatever ROM byte the CPU sees. */
#define RX8_FAULT_TABLE_ADDR        0x0007E4DCu

/* Secondary fault evaluator @0x67494 — see header note (modelled on the host
 * in oracle_get_fault_status.c). */
extern uint32_t rx8_get_fault_eval_state(uint16_t channel);

/* Big-endian u32 read: the SH-2E (and the ROM fault table / RAM enable mask
 * it reads) is big-endian, so on the little-endian host a native uint32_t
 * dereference would byte-swap the word (same idiom as rom_u16 in
 * rx8_get_maf_sensor_value.c — explicit byte assembly yields the identical
 * value on the BE target and the LE host oracle). */
static uint32_t be32_load(uint32_t addr)
{
    const volatile uint8_t *p = (const volatile uint8_t *)(uintptr_t)addr;
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
         | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

uint8_t rx8_get_fault_status(uint16_t channel)
{
    const uint32_t entry = be32_load(RX8_FAULT_TABLE_ADDR
                                     + ((channel & 0xFFFFu) * 4u));
    const uint32_t enable_mask = be32_load(RX8_FAULT_ENABLE_MASK_ADDR);

    /* Primary check: any of the low 16 bits of (entry & enable_mask) set? */
    if ((entry & enable_mask) & 0xFFFFu) {
        return 1;
    }

    /* Secondary check: any of the UPPER 16 bits of (entry & eval) set? */
    if ((entry & rx8_get_fault_eval_state(channel)) & 0xFFFF0000u) {
        return 1;
    }

    return 0;
}
