/*
 * =============================================================================
 * rx8_wankel_leading_trailing_split_487dc.c  —  GATED LEAD/TRAIL SPLIT-STATE
 *                                                SELECTOR (spark-control area)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x487DC  (size 0x232 = 562 bytes; rts @0x48C0E with the delay-
 *               slot `mov.l @r15+,r14`; literal pools @0x488EA..0x488FC,
 *               0x48A32..0x48A42, 0x48B76..0x48B86 and 0x48C62..0x48C6C; next
 *               function rotor_sync_timing_48C12 @0x48C12).
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_wankel_leading_trailing_split_487dc.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               initial-RAM state vectors, comparing every side-effected RAM
 *               cell bit-exactly; 0 mismatches), in addition to the lift test
 *               c/tests/test_wankel_leading_trailing_split_487DC.py (100000
 *               random inputs x 5 seeds, 0 mismatches).
 * Lift (truth): c/wankel_leading_trailing_split_487DC.c  (same address; the
 *               ground truth for this port).
 *
 * WHAT THIS IS
 * ------------
 * Gated "split state" selector (IDA: wankel_leading_trailing_split).  Despite
 * the IDA name, this routine does NOT compute a split angle and does NOT touch
 * the per-rotor timing words A734/A738 (those are written identically by
 * calc_ignition_all_rotors_13C2C; see its lift).  It computes ONE byte,
 * u8@0xFFFFCCD2, as a gated running maximum over 29 calibration thresholds:
 *
 *   r14 = 0;
 *   if (readValue8(0xFFFF8768,0) == 1 && cal8[0x7C27F] > 0) r14 = cal8[0x7C27F];
 *   for each (gate, thresh) in the 28 tables below:
 *       if (gate_active && cal8[thresh] > r14) r14 = cal8[thresh];   // u8 max
 *   RAM8@0xFFFFCCD2 = r14;
 *
 * gate_active is either:
 *   * a plain RAM byte == 1 (the 0xFFFFB5xx / 0xFFFFCCxx gate bytes), or
 *   * readValue_8bit_ADDRESS_VAL(addr, 0) == 1 for the 7 redundant
 *     (value, ~value) byte pairs at 0xFFFF8750/8764/8768/876C/8770/8778/8780
 *     (verified leaf @0x3ED3C: returns RAM8[a] when RAM8[a] == ~RAM8[a+1],
 *     else sets the fault flag RAM8@0xFFFFC6AC = 1 via 0x3F050 and returns 0).
 *
 * The 29 thresholds cal8[0x7C27F..0x7C29B] are small calibration bytes
 * (stock values 0..3, see ROM CALIBRATION TABLE below), so CCD2 ends up a
 * 0..3 state/selector value, NOT a split angle.  The very next function
 * rotor_sync_timing_48C12 decodes it into the output pair (CCE2, CCE3):
 * 0 -> (0,0), 1 -> (0,1), >=2 -> (1,0), i.e. this whole call chain is a
 * mode/state selector in the spark-control area (0xFFFFCCEx is also read by
 * leading_trailing_spark_control_2100A).  The A734/A738 lead vs trail split
 * is therefore NOT applied here.
 *
 * CALLING CONVENTION
 * ------------------
 * void f(void): normal ABI entry (mov.l r14,@-r15 / sts.l pr,@-r15 prologue),
 * no input registers, no meaningful return value (r0 is an arbitrary
 * by-product of the last `cmp/eq`).  The function is driven through the
 * standard SH2.call() entry and verified by comparing the side-effected RAM
 * cells, exactly like the rx8_ssv_control / rx8_purge_control_state_update
 * rigs.
 *
 * CALLEE INLINING (net effects folded in; the real ROM bytes always run
 * inside the emulator — ground truth)
 * -------------------------------------------------------------------------
 * The ROM reaches the leaf readValue_8bit_ADDRESS_VAL @0x3ED3C through
 * `mov.l @lit,r13 ; jsr @r13` (lit @0x488FC) for each of the 7 redundant
 * pairs.  The leaf itself jsr's:
 *   1. 0x3920  — SR-mask sanity check (`stc SR,r0; and #0xF0; cmp/hi #0x10`).
 *      With the default SR=0xF0 this is a pure no-op (no RAM traffic).
 *   2. 0x3F050 — fault-flag write: `mov.b #1,@0xFFFFC6AC` (rts delay slot).
 *   3. 0x3934  — event latch: with r4 != 0 (the normal path) it returns
 *      immediately; only r4 == 0 can tail-jump to 0x3DB0, and the leaf only
 *      reaches this call with r4 = SR&0xF0 = 0xF0.  Never fires here.
 * Behaviourally the leaf is therefore exactly: return RAM8[a] when
 * RAM8[a] == ~RAM8[a+1], else set the fault flag and return the default.
 * This port inlines that net effect (see rx8_read_value_8bit below); the
 * emulator side runs the real jsr chain including 0x3F050.
 *
 * RAM CELLS READ (addresses + widths)
 * -----------------------------------
 *   u8 gate bytes @0xFFFFB560, B563, B565, B567, B569, B56B, B56D, B57C,
 *     B57E, B580, B582, B584, B586, B588            (plain == 1 gates)
 *   u8 gate bytes @0xFFFFCC8C, CC8D, CCD3, CCD4, CCD5, CCD6, CCD7, CCDE
 *                                                    (plain == 1 gates)
 *   u8 (value, ~value) pairs @0xFFFF8750, 8764, 8768, 876C, 8770, 8778, 8780
 *     and their complement twins @+1                  (leaf 0x3ED3C, def 0)
 *   u8 fault flag @0xFFFFC6AC      (pre-state; the leaf only ever SETS it)
 *   u8 output @0xFFFFCCD2          (pre-state; always overwritten below)
 *
 * RAM CELLS WRITTEN (addresses + widths)
 * --------------------------------------
 *   u8 @0xFFFFCCD2  = the gated-max selector byte (store @0x48C06)
 *   u8 @0xFFFFC6AC  = 1 when any redundant pair read by the leaf is bad
 *                     (never cleared here; a good pair leaves it untouched)
 *
 * ROM CALIBRATION TABLE
 * ---------------------
 *   cal8[0x7C27F..0x7C29B], 29 bytes, read with `mov.b @lit,rN; extu.b` (so
 *   the comparisons are unsigned).  Stock 60E1D400.bin values (byte-exact):
 *     0x7C27F: 03 03 03 02 03 02 02 03 01 01 03 03 03 03 03 03
 *     0x7C28F: 03 03 03 02 02 03 02 00 03 03 03 00 00
 *   The oracle mmap()s the ROM page and seeds these exact bytes from the ROM
 *   file (MAP_FIXED, same trick as oracle_ssv_control.c), so the
 *   reconstructed function reads them through the very same addresses the
 *   ROM fetches.
 *
 * DISCREPANCIES vs c/wankel_leading_trailing_split_487DC.c
 * --------------------------------------------------------
 * The lift itself matched the disassembly of 0x487DC-0x48C0E exactly.  One
 * modelling nuance was corrected in this port:
 *   1. Block 1 (0x487F4-0x487FA) tests cal[0x7C27F] with
 *      `mov.b @r3,r2; extu.b r2,r2; cmp/pl r2`.  The `extu.b` makes the
 *      compare run on the zero-extended byte (0..255), so the ROM condition
 *      is `(uint8_t)cal != 0` for EVERY byte value.  The c/ lift models it
 *      as `(int8_t)CAL_7C27F > 0` (a signed test, true only for 0x01..0x7F),
 *      which matches the ROM only for cal <= 0x7F.  The stock cal byte is
 *      0x03, so the two models are indistinguishable on real calibration
 *      data; this port follows the ROM (`CAL_7C27F != 0`).
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_hw.h"

/* ---- plain-byte gate RAM (== 1 enables the threshold) ---- */
#define RX8_GATE_B560    RX8_IO8(0xFFFFB560u)
#define RX8_GATE_B563    RX8_IO8(0xFFFFB563u)
#define RX8_GATE_B565    RX8_IO8(0xFFFFB565u)
#define RX8_GATE_B567    RX8_IO8(0xFFFFB567u)
#define RX8_GATE_B569    RX8_IO8(0xFFFFB569u)
#define RX8_GATE_B56B    RX8_IO8(0xFFFFB56Bu)
#define RX8_GATE_B56D    RX8_IO8(0xFFFFB56Du)
#define RX8_GATE_B57C    RX8_IO8(0xFFFFB57Cu)
#define RX8_GATE_B57E    RX8_IO8(0xFFFFB57Eu)
#define RX8_GATE_B580    RX8_IO8(0xFFFFB580u)
#define RX8_GATE_B582    RX8_IO8(0xFFFFB582u)
#define RX8_GATE_B584    RX8_IO8(0xFFFFB584u)
#define RX8_GATE_B586    RX8_IO8(0xFFFFB586u)
#define RX8_GATE_B588    RX8_IO8(0xFFFFB588u)
#define RX8_GATE_CC8C    RX8_IO8(0xFFFFCC8Cu)
#define RX8_GATE_CC8D    RX8_IO8(0xFFFFCC8Du)
#define RX8_GATE_CCD3    RX8_IO8(0xFFFFCCD3u)
#define RX8_GATE_CCD4    RX8_IO8(0xFFFFCCD4u)
#define RX8_GATE_CCD5    RX8_IO8(0xFFFFCCD5u)
#define RX8_GATE_CCD6    RX8_IO8(0xFFFFCCD6u)
#define RX8_GATE_CCD7    RX8_IO8(0xFFFFCCD7u)
#define RX8_GATE_CCDE    RX8_IO8(0xFFFFCCDEu)

/* ---- outputs ---- */
#define RX8_SPLIT_STATE  RX8_IO8(0xFFFFCCD2u)   /* selector byte (output)   */
#define RX8_FAULT_FLAG   RX8_IO8(0xFFFFC6ACu)   /* fault flag (leaf output) */

/* ---- ROM calibration thresholds cal8[0x7C27F..0x7C29B] (stock 0..3).
 * The oracle maps the page and seeds the real ROM bytes, so these pointers
 * stay live on the host exactly as they are on the target. ---- */
#define CAL_7C27F   (*(const uint8_t *)0x0007C27Fu)
#define CAL_7C280   (*(const uint8_t *)0x0007C280u)
#define CAL_7C281   (*(const uint8_t *)0x0007C281u)
#define CAL_7C282   (*(const uint8_t *)0x0007C282u)
#define CAL_7C283   (*(const uint8_t *)0x0007C283u)
#define CAL_7C284   (*(const uint8_t *)0x0007C284u)
#define CAL_7C285   (*(const uint8_t *)0x0007C285u)
#define CAL_7C286   (*(const uint8_t *)0x0007C286u)
#define CAL_7C287   (*(const uint8_t *)0x0007C287u)
#define CAL_7C288   (*(const uint8_t *)0x0007C288u)
#define CAL_7C289   (*(const uint8_t *)0x0007C289u)
#define CAL_7C28A   (*(const uint8_t *)0x0007C28Au)
#define CAL_7C28B   (*(const uint8_t *)0x0007C28Bu)
#define CAL_7C28C   (*(const uint8_t *)0x0007C28Cu)
#define CAL_7C28D   (*(const uint8_t *)0x0007C28Du)
#define CAL_7C28E   (*(const uint8_t *)0x0007C28Eu)
#define CAL_7C28F   (*(const uint8_t *)0x0007C28Fu)
#define CAL_7C290   (*(const uint8_t *)0x0007C290u)
#define CAL_7C291   (*(const uint8_t *)0x0007C291u)
#define CAL_7C292   (*(const uint8_t *)0x0007C292u)
#define CAL_7C293   (*(const uint8_t *)0x0007C293u)
#define CAL_7C294   (*(const uint8_t *)0x0007C294u)
#define CAL_7C295   (*(const uint8_t *)0x0007C295u)
#define CAL_7C296   (*(const uint8_t *)0x0007C296u)
#define CAL_7C297   (*(const uint8_t *)0x0007C297u)
#define CAL_7C298   (*(const uint8_t *)0x0007C298u)
#define CAL_7C299   (*(const uint8_t *)0x0007C299u)
#define CAL_7C29A   (*(const uint8_t *)0x0007C29Au)
#define CAL_7C29B   (*(const uint8_t *)0x0007C29Bu)

/* ---- 0x3ED3C — readValue_8bit_ADDRESS_VAL(addr, default): returns RAM8[a]
 * when RAM8[a] == ~RAM8[a+1], else sets the fault flag RAM8@0xFFFFC6AC = 1
 * (via the 0x3F050 leaf) and returns the default.  Called here with default
 * = 0 and only ever compared == 1.  The emulator runs the REAL ROM bytes of
 * this leaf (plus its 0x3920 / 0x3F050 / 0x3934 sub-leaves) on its side. ---- */
static uint8_t rx8_read_value_8bit(uint32_t addr, uint8_t def)
{
    uint8_t b0 = RX8_IO8(addr);
    uint8_t b1 = RX8_IO8(addr + 1u);
    if (b0 == (uint8_t)~b1)
        return b0;
    RX8_FAULT_FLAG = 1u;
    return def;
}

/* ---- one ROM gate block: `extu.b r14,r1; mov.b @lit,r3; extu.b r3,r3;
 * cmp/ge r3,r1; bt/s skip` -> update r14 when gate == 1 AND thresh > r14
 * (both u8, so the max is unsigned). ---- */
static uint8_t rx8_gate_max(uint8_t cur, uint8_t gate, uint8_t thresh)
{
    if (gate == 1u && thresh > cur)
        return thresh;
    return cur;
}

/* ---- 0x487DC  gated lead/trail split-state selector ---------------------- */
void rx8_wankel_leading_trailing_split_487dc(void)
{
    uint8_t r14 = 0;

    /* Block 1 (0x487E8): readValue8(0xFFFF8768,0) == 1 AND cal[0x7C27F] > 0
     * (`mov.b @r3,r2; extu.b r2,r2; cmp/pl` — see the header discrepancy note:
     * the ROM condition is `(uint8_t)cal != 0`, NOT the lift's signed test). */
    if (rx8_read_value_8bit(0xFFFF8768u, 0) == 1u && CAL_7C27F != 0u)
        r14 = CAL_7C27F;

    /* Blocks 2..7 (0x48804..0x488B6): plain byte gates B563..B56B */
    r14 = rx8_gate_max(r14, RX8_GATE_B563, CAL_7C280);
    r14 = rx8_gate_max(r14, RX8_GATE_B565, CAL_7C281);
    r14 = rx8_gate_max(r14, RX8_GATE_B567, CAL_7C282);
    r14 = rx8_gate_max(r14, RX8_GATE_B569, CAL_7C283);
    r14 = rx8_gate_max(r14, RX8_GATE_B56D, CAL_7C284);
    r14 = rx8_gate_max(r14, RX8_GATE_B56B, CAL_7C285);

    /* Block 8 (0x488B8): readValue8(0xFFFF876C,0) -> cal[0x7C286] */
    r14 = rx8_gate_max(r14, rx8_read_value_8bit(0xFFFF876Cu, 0), CAL_7C286);

    /* Blocks 9..11 (0x488D8..0x4896A): plain byte gates CCD6,CCD7,CCDE */
    r14 = rx8_gate_max(r14, RX8_GATE_CCD6, CAL_7C287);
    r14 = rx8_gate_max(r14, RX8_GATE_CCD7, CAL_7C288);
    r14 = rx8_gate_max(r14, RX8_GATE_CCDE, CAL_7C289);

    /* Block 12 (0x4896C): readValue8(0xFFFF8750,0) -> cal[0x7C28A] */
    r14 = rx8_gate_max(r14, rx8_read_value_8bit(0xFFFF8750u, 0), CAL_7C28A);

    /* Block 13 (0x4898C): plain byte gate B57C -> cal[0x7C28B] */
    r14 = rx8_gate_max(r14, RX8_GATE_B57C, CAL_7C28B);

    /* Blocks 14..17 (0x489AA..0x48A28): readValue8 gates -> 0x7C28C..0x7C28F */
    r14 = rx8_gate_max(r14, rx8_read_value_8bit(0xFFFF8780u, 0), CAL_7C28C);
    r14 = rx8_gate_max(r14, rx8_read_value_8bit(0xFFFF8764u, 0), CAL_7C28D);
    r14 = rx8_gate_max(r14, rx8_read_value_8bit(0xFFFF8770u, 0), CAL_7C28E);
    r14 = rx8_gate_max(r14, rx8_read_value_8bit(0xFFFF8778u, 0), CAL_7C28F);

    /* Block 18 (0x48A2A): plain byte gate B560 -> cal[0x7C290] */
    r14 = rx8_gate_max(r14, RX8_GATE_B560, CAL_7C290);

    /* Blocks 19..29 (0x48A82..0x48C04): B588, CCD3,CCD4,CCD5, B584,B586,
     * B57E,B580,B582, CC8C, CC8D -> 0x7C291..0x7C29B */
    r14 = rx8_gate_max(r14, RX8_GATE_B588, CAL_7C291);
    r14 = rx8_gate_max(r14, RX8_GATE_CCD3, CAL_7C292);
    r14 = rx8_gate_max(r14, RX8_GATE_CCD4, CAL_7C293);
    r14 = rx8_gate_max(r14, RX8_GATE_CCD5, CAL_7C294);
    r14 = rx8_gate_max(r14, RX8_GATE_B584, CAL_7C295);
    r14 = rx8_gate_max(r14, RX8_GATE_B586, CAL_7C296);
    r14 = rx8_gate_max(r14, RX8_GATE_B57E, CAL_7C297);
    r14 = rx8_gate_max(r14, RX8_GATE_B580, CAL_7C298);
    r14 = rx8_gate_max(r14, RX8_GATE_B582, CAL_7C299);
    r14 = rx8_gate_max(r14, RX8_GATE_CC8C, CAL_7C29A);
    r14 = rx8_gate_max(r14, RX8_GATE_CC8D, CAL_7C29B);

    /* 0x48C06: RAM8@0xFFFFCCD2 = r14, then epilogue (rts @0x48C0E). */
    RX8_SPLIT_STATE = r14;
}
