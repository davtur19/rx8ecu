/*
 * =============================================================================
 * rx8_consistency_check.c  —  TASK-CONSISTENCY / HEALTH-CHECK COUNTER
 *                              (per-task "I'm alive" watchdog)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3A28  (body 0x3A28..0x3AA2; `rts` at 0x3AA0 with the
 *               `mov.l @r15+,r14` pop in its delay slot; the literal pool
 *               lives at 0x3AA4..0x3AC0 — the doc's "124 bytes" spans both)
 *
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_consistency_check.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random
 *               vectors, fixed seed 0x60E1D400; every side-effected RAM cell
 *               and the ABI return value compared bit-exactly; 0 mismatches).
 *
 * Lift (truth): c/consistencyCheck.c  (consistencyCheck @ 0x3A28,
 *               ghidra-hand-xmap) and docs/functions/consistencyCheck.md.
 *
 * LIFT-LABEL VERIFICATION (performed, not assumed)
 * ------------------------------------------------
 * The IDA-AI label "consistencyCheck" was treated as a HYPOTHESIS only and
 * checked against the actual bytes.  It is CORRECT for this ROM.  The
 * disassembly of 0x3A28 matches the lift's task-health-check model
 * instruction-for-instruction:
 *
 *     0x3A2A  exts.b  r5,r7          ; r7 = (s8)task_id
 *     0x3A2E  shll2 / 0x3A32 shll    ; *8
 *     0x3A34  add     r3,r7          ; entry = table_base + task_id*8
 *     0x3A36  mov.l   @(0x4,r7),r6   ; counter_ptr (entry+4)
 *     0x3A38  mov.w   @r6,r2         ; cur  = *counter_ptr
 *     0x3A3A  mov.w   @(0x2,r6),r0   ; expected = *(counter_ptr+2)
 *     0x3A3C  cmp/eq  r0,r2          ; healthy  <=>  cur == expected
 *     0x3A42  mov    #0xFF,r2 / mov.w r2,@r6   ; healthy: *counter = 0xFFFF
 *     0x3A4A  shar x3 / add         ; bitmap ptr = 0xFFFF72E0 + (task_id>>3)
 *     0x3A58  mov.b  @(0x3D50,r2),r3; mask = bit_clear_masks[task_id&7]
 *     0x3A5C  and / mov.b @r1       ; *bitmap &= mask
 *     0x3A62  cmp/eq @r4,r14        ; task_id == ctx->current_task ?
 *     0x3A68  jsr    @0x3C80        ;   healthy+match: call HUDI handler
 *     0x3A70..0x3A82               ; mismatch: restore (cur==shadow) else +1
 *     0x3A92..0x3A9A               ; mismatch+match: ctx[6]=diag_table[*counter]
 *     0x3A9C  mov    #0x01,r0       ; return 1 (handled) / 0 otherwise
 *
 * WHAT THIS FUNCTION ACTUALLY DOES
 * --------------------------------
 * The scheduler calls it on every task switch (taskEndRoutine @0x3D58, jsr
 * at 0x3D80; FUN_00003490 @0x3490, jsr at 0x34D6 — both load r4 from the
 * same kernel context word 0xFFFF72B0) so each task's "I'm alive" counter
 * can be checked against its expected value.
 *
 *   - healthy (cur == expected): the counter is reset to -1 (0xFFFF), the
 *     task's bit is cleared in the pending-flags byte @0xFFFF72E0 +
 *     (task_id>>3), and — when the task is the currently executing one —
 *     handleHUDIException (0x3C80) is called to re-scan the exception block;
 *     return 1 (handled).  A non-current task just returns 0.
 *   - mismatch: the counter is restored from the table entry's shadow/save
 *     pair (cur == entry+2  ->  *counter = entry+0) or bumped by one;
 *     when the task is current, the diagnostic code for the new counter
 *     value is read from the u16 table @0xFFFF7234 into ctx+6 and the
 *     function returns 1; otherwise it returns 0.
 *
 * CALLING CONVENTION
 * ------------------
 * int32_t rx8_consistency_check(uint8_t *ctx, int8_t task_id)
 *   r4 = ctx  (kernel context block, real base 0xFFFF72B0)
 *   r5 = task_id (byte; the ROM sign-extends with `exts.b`)
 *   r0 = 1 if the task matched the current-task byte, 0 otherwise
 * The harness drives it through SH2.call(0x3A28, r4, r5, ram=...) and
 * compares the return value plus every side-effected RAM cell.
 *
 * RAM / MMIO CELLS
 * ----------------
 *   ctx+0x00  u8   current task byte (also written by the HUDI callee)
 *   ctx+0x06  u16  diagnostic field (diag-table result)
 *   ctx+0x10  u32  SR shadow (read/restored by the HUDI callee only; no
 *                  observable net effect)
 *   ctx+0x20  u32  entry-table base pointer
 *   ctx+0x24  u32  diag-table base pointer (used by the HUDI callee only;
 *                  the parent itself uses the literal 0xFFFF7234)
 *   entry+0   u16  shadow save value
 *   entry+2   u16  shadow expected value
 *   entry+4   u32  pointer to the 4-byte counter buffer
 *   buf+0     u16  counter value
 *   buf+2     u16  expected value
 *   0xFFFF72E0 u8  task bitmap / pending-flag bytes (index task_id>>3)
 *   0xFFFF7234 u16 diag lookup table (word-indexed by the counter value)
 *   (the HUDI callee additionally scans a 16-byte block at 0xFFFF72E0)
 *
 * CALIBRATION TABLES (ROM literal pool / static data, not RAM cals)
 * ---------------------------------------------------------------
 *   u8[8]  @0x3D50 = FE FD FB F7 EF DF BF 7F  bit-clear masks (bit_clear_masks)
 *   u32 @0x3AAC = 0xFFFF7234   diag-table base (parent)
 *   u32 @0x3AB0 = 0xFFFF72E0   bitmap base
 *   u32 @0x3AB8 = 0x00003D50   mask-table address
 *   u32 @0x3ABC = 0x00003C80   handleHUDIException callee
 *
 * INTERNAL CALLEE
 * ---------------
 * handleHUDIException @0x3C80 (bounded, no loops — runs as REAL ROM bytes
 * on the emulator side).  It scans four u32 words @0xFFFF72E0/0xE4/0xE8/0xEC
 * for the first non-zero word, picks the byte offset (0x0C/0x08/0x04/0x00)
 * and a base code (0x60/0x40/0x20/0x00), then walks the 16-bit/byte pair at
 * that offset to find the first set bit (codes 0x10/0x08 lanes + bit
 * position), writes the resulting code into ctx[0], and publishes
 * ctx[6] = diag_table[*counter] using ctx+0x24.  If all four words are
 * zero it short-circuits to ctx[0]=0xFF / ctx[6]=0xFFFF (the "no exception
 * pending" case — the only state this harness drives the callee with,
 * because on the healthy path the parent has already set *counter = 0xFFFF,
 * which makes the general diag-table index (0xFFFF) unbounded; see the
 * harness header).  The full scan model is implemented below and was
 * validated against the ROM bytes over 50000 isolated random vectors.
 *
 * LIFT-VS-ROM DISCREPANCIES (all documented, none behavioural)
 * ------------------------------------------------------------
 *   1. The lift's doc pseudocode (`consistencyCheck.md`) omits the actual
 *      `jsr @0x3C80` that the ROM executes on the healthy+match path and
 *      omits that the callee WRITES ctx[0] and ctx[6]; the lift C file does
 *      declare and call handleHUDIException(), so only the .md diagram is
 *      incomplete.
 *   2. The lift labels entry+0 as "save_value" and entry+2 as
 *      "expected_shadow"; the ROM's mismatch test compares the CURRENT
 *      counter against entry+2 (so entry+2 is really the *shadow expected*
 *      the counter is restored from) and restores entry+0 (the *shadow
 *      save*).  Semantics agree with the lift; only the naming is worth
 *      pinning.
 *   3. The lift says bitmap uses "8-bit stride"; the ROM uses task_id>>3
 *      (arithmetic shift of the sign-extended byte), i.e. 8 tasks per flag
 *      byte.  Confirmed.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* ---- context-block layout (r4; real kernel base 0xFFFF72B0) -------------- */
#define CC_CTX_BASE      0xFFFF72B0u
#define CC_CTX_CURRENT   (RX8_IO8(CC_CTX_BASE + 0x00))   /* current task byte */
#define CC_CTX_DIAG      (RX8_IO16(CC_CTX_BASE + 0x06))  /* diagnostic field  */
#define CC_CTX_SR        (RX8_IO32(CC_CTX_BASE + 0x10))  /* SR shadow (callee)*/
#define CC_CTX_TABLE     (RX8_IO32(CC_CTX_BASE + 0x20))  /* entry table base  */
#define CC_CTX_DIAGPTR   (RX8_IO32(CC_CTX_BASE + 0x24))  /* callee diag base  */

/* ---- fixed peripheral / table addresses (ROM literal pool) --------------- */
#define CC_BITMAP_BASE   0xFFFF72E0u   /* task pending-flags byte region      */
#define CC_DIAG_BASE     0xFFFF7234u   /* u16 diag table (parent literal)     */

/* ---- bit-clear mask table @0x3D50 (one mask per bit position) ------------ */
static const uint8_t CC_BIT_CLEAR[8] = {
    0xFE, 0xFD, 0xFB, 0xF7, 0xEF, 0xDF, 0xBF, 0x7F
};

/* ---- big-endian u32 assembly: the ROM reads the 16-byte exception block
 * with `mov.l @(r0,r3)` on the big-endian SH-2E, so the host model assembles
 * the four bytes high-first (same trick as rx8_get_maf_sensor_value.c) to
 * see the same value the BE CPU does regardless of host endianness. ------- */
static uint32_t rx8_be32(uint32_t a)
{
    return ((uint32_t)RX8_IO8(a) << 24) | ((uint32_t)RX8_IO8(a + 1) << 16) |
           ((uint32_t)RX8_IO8(a + 2) << 8) | (uint32_t)RX8_IO8(a + 3);
}

/* ---- 0x3C80 — handleHUDIException (net effect; runs as real ROM bytes on
 * the emulator side).  See the header for the exact scan semantics.  Only
 * the "no exception pending" state (REG block all-zero -> ctx[0]=0xFF,
 * ctx[6]=0xFFFF) is driven by the harness, but the full model is kept so the
 * oracle is general; it was validated over 50000 isolated random vectors. - */
static void rx8_handle_hudi_exception(uint8_t *ctx)
{
    uint32_t w0 = rx8_be32(CC_BITMAP_BASE + 0x00u);
    uint32_t w1 = rx8_be32(CC_BITMAP_BASE + 0x04u);
    uint32_t w2 = rx8_be32(CC_BITMAP_BASE + 0x08u);
    uint32_t w3 = rx8_be32(CC_BITMAP_BASE + 0x0Cu);
    uint32_t off;
    uint16_t code;

    /* first non-zero u32 picks the byte offset and the base code */
    if (w3) {
        off = 0x0Cu; code = 0x60u;
    } else if (w2) {
        off = 0x08u; code = 0x40u;
    } else if (w1) {
        off = 0x04u; code = 0x20u;
    } else if (w0) {
        off = 0x00u; code = 0x00u;
    } else {
        /* all four words zero: no exception pending */
        ctx[0] = 0xFFu;
        RX8_IO16((uintptr_t)ctx + 0x06) = 0xFFFFu;
        return;
    }

    {
        uint8_t  A = RX8_IO8(CC_BITMAP_BASE + off);
        uint8_t  B = RX8_IO8(CC_BITMAP_BASE + off + 1);
        uint8_t  C = RX8_IO8(CC_BITMAP_BASE + off + 2);
        uint8_t  D = RX8_IO8(CC_BITMAP_BASE + off + 3);
        uint16_t W = (uint16_t)(((uint16_t)C << 8) | D);
        uint8_t  scan;

        /* 0x3CCA/0x3CD4: u16 at off+2 non-zero -> +0x10 lane, then D else C;
         * else B else A, with a +0x08 lane when the first candidate wins. */
        if (W != 0u) {
            code = (uint16_t)(code + 0x10u);
            if (D != 0u) { scan = D; code = (uint16_t)(code + 0x08u); }
            else         { scan = C; }
        } else {
            if (B != 0u) { scan = B; code = (uint16_t)(code + 0x08u); }
            else         { scan = A; }
        }

        /* 0x3CE8..0x3D20: tst cascade — highest set bit adds its position */
        if      (scan & 0x80u) code = (uint16_t)(code + 7u);
        else if (scan & 0x40u) code = (uint16_t)(code + 6u);
        else if (scan & 0x20u) code = (uint16_t)(code + 5u);
        else if (scan & 0x10u) code = (uint16_t)(code + 4u);
        else if (scan & 0x08u) code = (uint16_t)(code + 3u);
        else if (scan & 0x04u) code = (uint16_t)(code + 2u);
        else if (scan & 0x02u) code = (uint16_t)(code + 1u);
        /* bit 0 only: no add */
    }

    /* 0x3D24..0x3D38: publish the code, then diag = *entry[code].counter_ptr
     * word-indexed into the ctx+0x24 table -> ctx[6]. */
    ctx[0] = (uint8_t)code;
    {
        uint32_t table = *(uint32_t *)(uintptr_t)(ctx + 0x20);
        uint32_t entry = table + (uint32_t)code * 8u;
        uint32_t cptr  = RX8_IO32(entry + 0x04u);
        uint16_t cval  = RX8_IO16(cptr);
        uint16_t *diag = *(uint16_t **)(uintptr_t)(ctx + 0x24);
        RX8_IO16((uintptr_t)ctx + 0x06) = diag[cval];
    }
}

/* ---- 0x3A28  task-consistency health-check counter ----------------------- */
int32_t rx8_consistency_check(uint8_t *ctx, int8_t task_id)
{
    int32_t  idx     = task_id;                 /* exts.b r5            */
    uint32_t uidx    = (uint32_t)idx;
    uint32_t table   = *(uint32_t *)(uintptr_t)(ctx + 0x20);
    uint32_t entry   = table + uidx * 8u;
    uint16_t *counter = (uint16_t *)(uintptr_t)RX8_IO32(entry + 0x04u);
    uint16_t cur      = counter[0];             /* mov.w @r6,r2         */
    uint16_t expected = counter[1];             /* mov.w @(2,r6),r0     */

    if (cur == expected) {
        /* healthy: reset the counter to -1 and clear the task's flag bit */
        counter[0] = 0xFFFFu;                   /* mov #0xFF; mov.w      */
        {
            uint8_t *bitmap = (uint8_t *)(uintptr_t)
                              (CC_BITMAP_BASE + (uint32_t)(idx >> 3));
            *bitmap &= CC_BIT_CLEAR[uidx & 7u];
        }
        if ((uint8_t)uidx == ctx[0]) {
            /* current task: re-scan the HUDI exception block */
            rx8_handle_hudi_exception(ctx);     /* jsr @0x3C80          */
            return 1;
        }
        return 0;
    }

    /* mismatch: restore from the shadow pair or bump by one */
    {
        uint16_t shadow = RX8_IO16(entry + 0x02u);
        uint16_t save   = RX8_IO16(entry + 0x00u);
        if (cur == shadow)
            counter[0] = save;                  /* 0x3A78               */
        else
            counter[0] = (uint16_t)(cur + 1u);  /* 0x3A80               */
    }

    if ((uint8_t)uidx == ctx[0]) {
        /* current task: publish the diag code for the new counter value */
        uint16_t cval = counter[0];             /* mov.w @r6,r0         */
        RX8_IO16((uintptr_t)ctx + 0x06) =
            RX8_IO16(CC_DIAG_BASE + (uint32_t)cval * 2u);
        return 1;
    }
    return 0;
}
