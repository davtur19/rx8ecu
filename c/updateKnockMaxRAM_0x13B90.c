/* updateKnockMaxRAM_0x13B90.c
 *
 * ROM: 60E1D400 | Address: 0x13B90 | Size: 0x3E (62) bytes per CSV range
 * 0x13B90..0x13BCE.  27 code instrs (0x13B90..0x13BCC, rts+delay at
 * 0x13BCA/0x13BCC) + mov.l literal pool @0x13BE0..0x13C28 (read by mov.l
 * at 0x13B92/0x13B9E/0x13BA2/0x13BAC/0x13BB4/0x13BC2, shared with the next
 * function calc_ignition_all_rotors_13C2C @0x13C2C).
 *
 * Entry  : 0x13B90 — matches the symbols CSV row.  Valid standalone prologue
 *           (sts.l pr,@-r15), rts+delay at 0x13BCA/0x13BCC.  The ONLY ROM
 *           reference to 0x13B90 is the function-pointer slot @0x147A0 inside
 *           the dispatcher engineControlCalculateTiming (0x14584) literal
 *           pool — dispatch slot 7 of Phase 1 (c/engineControlCalculateTiming.c
 *           line 211).  No code branches into the body from mid-function
 *           (all static branch targets found inside [0x13B90,0x13BCE) are
 *           intra-function or pool-data false positives), so the CSV address
 *           IS the real entry point.
 *
 * NAME DISCREPANCY (documented, decision): the ida-ai symbols row named this
 * entry calc_fuel_cutoff_logic, the merged CSV row (ghidra-hand-xmap) names
 * it updateKnockMaxRAM.  The dispatcher call order (knock subsystem phase 1,
 * right after getKnockControlActive) and the actual semantics (re-filtering a
 * stored max value and re-writing it into the checksummed f32 struct @0xFFFF8038)
 * support updateKnockMaxRAM.  DECISION: keep updateKnockMaxRAM (matches the
 * task + merged CSV); the ida-ai row is renamed to it in both CSVs.
 *
 * Range  : 0x13B90 .. 0x13BCE
 *
 * Literal pool:
 *   0x13BDA 0xFFFF8038         (checksummed f32 struct base: f32@+0,
 *                                u16 w0@+0, w1@+2, w2@+4, w3@+6)
 *   0x13BDC 0xFFFFA734         (f32 first-order-filter target — knock max)
 *   0x13BE0 0xFFFFA74A         (u8 enable gate, must be 1)
 *   0x13C14 f32 0.0            (ROM 0x00079870 — fallback/valid-slot value)
 *   0x13C18 -> 0x3EE0A         (timing_correction_3EE0A — checksummed f32 read:
 *                                valid struct -> returns f32@struct, else
 *                                returns the passed fallback and sets the
 *                                fault flag u8@0xFFFFC6AC via leaf 0x3F050)
 *   0x13C1C f32 0.0039         (ROM 0x00079874 — firstOrderFilter factor)
 *   0x13C20 f32 1e-5           (ROM 0x00013C20 — firstOrderFilter deadband)
 *   0x13C24 -> 0x23B0          (firstOrderFilter leaf, c/firstOrderFilter.c)
 *   0x13C28 -> 0x3EEB8         (cold_start_enrichment_3EEB8 — checksummed f32
 *                                write: f32@struct = v, u16@+4 = u16@+6 =
 *                                (u16)~(se16(hi)+se16(lo)); skips on NaN)
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   if (u8@0xFFFFA74A != 1) return;              ; bf/s 0x13BC8
 *   prev = timing_correction_3EE0A(0xFFFF8038, 0.0f);
 *        ; fr4 = f32@0x00079870 (0.0) in the jsr delay slot; returns the
 *        ; stored struct float on a valid checksum else 0.0 + fault flag
 *   fr0  = firstOrderFilter(fr4=f32@0xFFFFA734, fr5=prev, 0.0039f, 1e-5f);
 *        ; sig = f32@A734 (delay slot fmov.s @r3,fr4); snap to sig when
 *        ; |sig - filtered| <= 1e-5, bootstrap (return sig) if prev not finite
 *   out  = sub_13E6C(fr0);        ; bsr 0x13E6C (delay fmov fr0,fr4): the
 *        ; "correction_final_clamp_0x13E6C" helper (see c/calc_ignition_all_
 *        ; rotors_13C2C.c): saturate(v, table_select(f32@0xFFFFB5B8), 0.0f)
 *        ; using the 4/5-pt u8 tables @0x6B678/@0x6B664 and the status bytes
 *        ; u8@0xFFFFB5A4 / 0xFFFFBB55 / 0xFFFFBCA9 (threshold u8@0x00079838).
 *   fr4  = fr0;  fr4 = fr0;       ; fmov fr0,fr4 twice (0x13BBC/0x13BBE)
 *   cold_start_enrichment_3EEB8(0xFFFF8038, out);   ; jmp @0x13BC4 tail-call
 *        ; (delay lds.l @r15+,pr pops the entry pr so 0x3EEB8 returns straight
 *        ;  to our caller); writes the result back into the struct if not NaN
 *
 *   The tail-call runs 0x3EEB8 with OUR pr popped, so the whole chain is
 *   self-contained and deterministic under the emulator's default SR=0xF0
 *   (getSR/setSR leaves 0x3920/0x3934 never touch RAM on this path).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_updateKnockMaxRAM_0x13B90.py — 0 mismatches over 5 seeds x
 * default iterations (full post-call RAM overlay, byte-exact, r0 compared).
 */

#include <stdint.h>

/* 0x3EE0A — timing_correction_3EE0A (checksummed f32 read, RAM side effect:
 *   fault flag u8@0xFFFFC6AC on invalid checksum).  Returns the stored float
 *   when u16@(addr+4) or u16@(addr+6) == (u16)~(u16@addr + u16@(addr+2)),
 *   else the passed fallback. */
extern float timing_correction_3EE0A(uintptr_t addr, float fallback);

/* 0x23B0 — firstOrderFilter (pure FPU leaf, see c/firstOrderFilter.c):
 *   fr4=sig, fr5=sigprev, fr6=ff, fr7=min.  Bootstraps on non-finite sigprev;
 *   otherwise filtered = sig + (1-ff)*(sigprev-sig), snapping to sig when
 *   |sig - filtered| <= min. */
extern float firstOrderFilter(float sig, float sigprev, float ff, float min);

/* 0x13E6C — sub_13E6C (see c/calc_ignition_all_rotors_13C2C.c note 4):
 *   saturate(v, table_select(f32@0xFFFFB5B8), 0.0f) via table1D_lookup 0x2068
 *   and the clamp leaf 0x2404.  Reads the status bytes B5A4/BB55/BCA9. */
extern float sub_13E6C(float v);

/* 0x3EEB8 — cold_start_enrichment_3EEB8 (checksummed f32 write):
 *   f32@addr = v; u16@(addr+4) = u16@(addr+6) = (u16)~(se16(hi)+se16(lo)) of
 *   the f32 bits; skips everything when v is NaN (fcmp/eq fr15,fr15). */
extern void cold_start_enrichment_3EEB8(uintptr_t addr, float v);

/* ---- RAM globals (mov.l/mov.w literals -> 0xFFFFxxxx) ---- */
#define GATE_A74A (*(volatile uint8_t *)0xFFFFA74A)  /* u8 enable gate (==1) */
#define T_A734    (*(volatile float   *)0xFFFFA734)  /* f32 filter target */
#define STRUCT    (uintptr_t)0xFFFF8038              /* checksummed f32 struct */

/* ROM constants */
#define ROM_FF   (*(volatile float *)0x00079874)  /* f32 0.0039 (filter factor) */
#define ROM_MIN  (*(volatile float *)0x00013C20)  /* f32 1e-5 (filter deadband) */

void updateKnockMaxRAM_0x13B90(void)
{
    if (GATE_A74A != 1)              /* cmp/eq #1,r0 ; bf/s 0x13BC8 */
        return;

    /* 0x13B9E..0x13BA6: read the stored knock max from the checksummed struct */
    float prev = timing_correction_3EE0A(STRUCT, 0.0f);   /* jsr @0x3EE0A */

    /* 0x13BA8..0x13BB6: first-order filter of the new knock max @A734 toward
     * the stored previous value (factor 0.0039, deadband 1e-5). */
    float v = firstOrderFilter(T_A734, prev, ROM_FF, ROM_MIN);  /* jsr @0x23B0 */

    /* 0x13BBA: 0x13E6C — table-clamp the filtered value (bounded above by 0). */
    float out = sub_13E6C(v);        /* bsr 0x13E6C */

    /* 0x13BC0..0x13BC6: write the result back into the checksummed struct
     * (tail call, our pr already popped by the delay slot). */
    cold_start_enrichment_3EEB8(STRUCT, out);   /* jmp @0x3EEB8 */
}
