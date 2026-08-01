/* wankel_leading_trailing_split_487DC.c
 *
 * ROM: 60E1D400  |  Address: 0x487DC  |  Size: 0x232 bytes (562 B)
 *       0x487DC..0x48C10 code (rts @0x48C0E, delay-slot pop r14); literal
 *       pools @0x488EA..0x488FC, @0x48A32..0x48A42, @0x48B76..0x48B86 and
 *       @0x48C62..0x48C6C; next function rotor_sync_timing_48C12 @0x48C12.
 *       VERIFIED vs ROM emulator (0 mismatches).
 *
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
 * (stock values 0..3), so CCD2 ends up a 0..3 state/selector value, NOT a
 * split angle.  The very next function rotor_sync_timing_48C12 decodes it
 * into the output pair (CCE2, CCE3): 0 -> (0,0), 1 -> (0,1), >=2 -> (1,0),
 * i.e. this whole call chain is a mode/state selector in the spark-control
 * area (0xFFFFCCEx is also read by leading_trailing_spark_control_2100A).
 * The A734/A738 lead vs trail split is therefore NOT applied here.
 *
 * Inputs (RAM reads):
 *   u8 gates @0xFFFFB560,B563,B565,B567,B569,B56B,B56D,B57C,B580,B582,B584,
 *     B586,B588 and @0xFFFFCC8C,CC8D,CCD3,CCD4,CCD5,CCD6,CCD7,CCDE
 *   (value,~value) u8 pairs @0xFFFF8750/8764/8768/876C/8770/8778/8780
 *     (read via verified leaf 0x3ED3C, default 0)
 *   u8 fault flag @0xFFFFC6AC  (side-effect output of the leaf on a bad pair)
 *   u8 output @0xFFFFCCD2      (read only via the "==1" gate checks below)
 * ROM constants: cal8 @0x7C27F..0x7C29B (thresholds, stock 0..3)
 * Outputs (RAM writes):
 *   u8 @0xFFFFCCD2  = the gated-max selector byte
 *   u8 @0xFFFFC6AC  = fault flag (only set to 1 on a bad redundant pair)
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches (c/tests/test_wankel_leading_trailing_split_487DC.py).
 */
#include <stdint.h>

/* ---- gate RAM bytes ---- */
#define RAM_B560      (*(volatile uint8_t *)0xFFFFB560)
#define RAM_B563      (*(volatile uint8_t *)0xFFFFB563)
#define RAM_B565      (*(volatile uint8_t *)0xFFFFB565)
#define RAM_B567      (*(volatile uint8_t *)0xFFFFB567)
#define RAM_B569      (*(volatile uint8_t *)0xFFFFB569)
#define RAM_B56B      (*(volatile uint8_t *)0xFFFFB56B)
#define RAM_B56D      (*(volatile uint8_t *)0xFFFFB56D)
#define RAM_B57C      (*(volatile uint8_t *)0xFFFFB57C)
#define RAM_B57E      (*(volatile uint8_t *)0xFFFFB57E)
#define RAM_B580      (*(volatile uint8_t *)0xFFFFB580)
#define RAM_B582      (*(volatile uint8_t *)0xFFFFB582)
#define RAM_B584      (*(volatile uint8_t *)0xFFFFB584)
#define RAM_B586      (*(volatile uint8_t *)0xFFFFB586)
#define RAM_B588      (*(volatile uint8_t *)0xFFFFB588)
#define RAM_CC8C      (*(volatile uint8_t *)0xFFFFCC8C)
#define RAM_CC8D      (*(volatile uint8_t *)0xFFFFCC8D)
#define RAM_CCD3      (*(volatile uint8_t *)0xFFFFCCD3)
#define RAM_CCD4      (*(volatile uint8_t *)0xFFFFCCD4)
#define RAM_CCD5      (*(volatile uint8_t *)0xFFFFCCD5)
#define RAM_CCD6      (*(volatile uint8_t *)0xFFFFCCD6)
#define RAM_CCD7      (*(volatile uint8_t *)0xFFFFCCD7)
#define RAM_CCDE      (*(volatile uint8_t *)0xFFFFCCDE)

/* ---- redundant (value,~value) pair RAM (read via leaf 0x3ED3C) ---- */
#define RAM_8750      (*(volatile uint8_t *)0xFFFF8750)
#define RAM_8764      (*(volatile uint8_t *)0xFFFF8764)
#define RAM_8768      (*(volatile uint8_t *)0xFFFF8768)
#define RAM_876C      (*(volatile uint8_t *)0xFFFF876C)
#define RAM_8770      (*(volatile uint8_t *)0xFFFF8770)
#define RAM_8778      (*(volatile uint8_t *)0xFFFF8778)
#define RAM_8780      (*(volatile uint8_t *)0xFFFF8780)

/* ---- outputs ---- */
#define RAM_CCD2      (*(volatile uint8_t *)0xFFFFCCD2)   /* selector byte */
#define RAM_C6AC      (*(volatile uint8_t *)0xFFFFC6AC)   /* fault flag */

/* ---- ROM calibration thresholds (0x7C27F..0x7C29B, stock 0..3) ---- */
#define CAL_7C27F     (*(const uint8_t *)0x0007C27F)
#define CAL_7C280     (*(const uint8_t *)0x0007C280)
#define CAL_7C281     (*(const uint8_t *)0x0007C281)
#define CAL_7C282     (*(const uint8_t *)0x0007C282)
#define CAL_7C283     (*(const uint8_t *)0x0007C283)
#define CAL_7C284     (*(const uint8_t *)0x0007C284)
#define CAL_7C285     (*(const uint8_t *)0x0007C285)
#define CAL_7C286     (*(const uint8_t *)0x0007C286)
#define CAL_7C287     (*(const uint8_t *)0x0007C287)
#define CAL_7C288     (*(const uint8_t *)0x0007C288)
#define CAL_7C289     (*(const uint8_t *)0x0007C289)
#define CAL_7C28A     (*(const uint8_t *)0x0007C28A)
#define CAL_7C28B     (*(const uint8_t *)0x0007C28B)
#define CAL_7C28C     (*(const uint8_t *)0x0007C28C)
#define CAL_7C28D     (*(const uint8_t *)0x0007C28D)
#define CAL_7C28E     (*(const uint8_t *)0x0007C28E)
#define CAL_7C28F     (*(const uint8_t *)0x0007C28F)
#define CAL_7C290     (*(const uint8_t *)0x0007C290)
#define CAL_7C291     (*(const uint8_t *)0x0007C291)
#define CAL_7C292     (*(const uint8_t *)0x0007C292)
#define CAL_7C293     (*(const uint8_t *)0x0007C293)
#define CAL_7C294     (*(const uint8_t *)0x0007C294)
#define CAL_7C295     (*(const uint8_t *)0x0007C295)
#define CAL_7C296     (*(const uint8_t *)0x0007C296)
#define CAL_7C297     (*(const uint8_t *)0x0007C297)
#define CAL_7C298     (*(const uint8_t *)0x0007C298)
#define CAL_7C299     (*(const uint8_t *)0x0007C299)
#define CAL_7C29A     (*(const uint8_t *)0x0007C29A)
#define CAL_7C29B     (*(const uint8_t *)0x0007C29B)

/* ---- verified leaf @0x3ED3C readValue_8bit_ADDRESS_VAL(addr, default):
 * returns RAM8[addr] when RAM8[addr] == ~RAM8[addr+1], else sets the
 * fault flag RAM8@0xFFFFC6AC = 1 (0x3F050) and returns default.
 * Called here with default = 0 and only compared == 1. ---- */
static uint8_t readValue8_0x3ED3C(uint32_t addr, uint8_t def)
{
    uint8_t b0 = *(volatile uint8_t *)addr;
    uint8_t b1 = *(volatile uint8_t *)(addr + 1);
    if (b0 == (uint8_t)~b1)
        return b0;
    RAM_C6AC = 1;
    return def;
}

/* ---- plain-byte gate + threshold (u8 max bump), mirrors one ROM block ---- */
static uint8_t gate_max(uint8_t cur, uint8_t gate, uint8_t thresh)
{
    if (gate == 1 && thresh > cur)
        return thresh;
    return cur;
}

void wankel_leading_trailing_split_487DC(void)
{
    uint8_t r14 = 0;

    /* Block 1 (0x487E8): readValue8(0xFFFF8768,0) == 1 AND cal[0x7C27F] > 0
     * (cmp/pl, signed) -> r14 = cal[0x7C27F]. */
    if (readValue8_0x3ED3C(0xFFFF8768, 0) == 1 && (int8_t)CAL_7C27F > 0)
        r14 = CAL_7C27F;

    /* Blocks 2..7 (0x48804..0x488B6): plain byte gates B563..B56B */
    r14 = gate_max(r14, RAM_B563, CAL_7C280);
    r14 = gate_max(r14, RAM_B565, CAL_7C281);
    r14 = gate_max(r14, RAM_B567, CAL_7C282);
    r14 = gate_max(r14, RAM_B569, CAL_7C283);
    r14 = gate_max(r14, RAM_B56D, CAL_7C284);
    r14 = gate_max(r14, RAM_B56B, CAL_7C285);

    /* Block 8 (0x488B8): readValue8(0xFFFF876C,0) -> cal[0x7C286] */
    r14 = gate_max(r14, readValue8_0x3ED3C(0xFFFF876C, 0), CAL_7C286);

    /* Blocks 9..11 (0x488D8..0x4896A): plain byte gates CCD6,CCD7,CCDE */
    r14 = gate_max(r14, RAM_CCD6, CAL_7C287);
    r14 = gate_max(r14, RAM_CCD7, CAL_7C288);
    r14 = gate_max(r14, RAM_CCDE, CAL_7C289);

    /* Block 12 (0x4896C): readValue8(0xFFFF8750,0) -> cal[0x7C28A] */
    r14 = gate_max(r14, readValue8_0x3ED3C(0xFFFF8750, 0), CAL_7C28A);

    /* Block 13 (0x4898C): plain byte gate B57C -> cal[0x7C28B] */
    r14 = gate_max(r14, RAM_B57C, CAL_7C28B);

    /* Blocks 14..17 (0x489AA..0x48A28): readValue8 gates -> 0x7C28C..0x7C28F */
    r14 = gate_max(r14, readValue8_0x3ED3C(0xFFFF8780, 0), CAL_7C28C);
    r14 = gate_max(r14, readValue8_0x3ED3C(0xFFFF8764, 0), CAL_7C28D);
    r14 = gate_max(r14, readValue8_0x3ED3C(0xFFFF8770, 0), CAL_7C28E);
    r14 = gate_max(r14, readValue8_0x3ED3C(0xFFFF8778, 0), CAL_7C28F);

    /* Block 18 (0x48A2A): plain byte gate B560 -> cal[0x7C290] */
    r14 = gate_max(r14, RAM_B560, CAL_7C290);

    /* Blocks 19..29 (0x48A82..0x48C04): B588, CCD3,CCD4,CCD5, B584,B586,
     * B57E,B580,B582, CC8C, CC8D -> 0x7C291..0x7C29B */
    r14 = gate_max(r14, RAM_B588, CAL_7C291);
    r14 = gate_max(r14, RAM_CCD3, CAL_7C292);
    r14 = gate_max(r14, RAM_CCD4, CAL_7C293);
    r14 = gate_max(r14, RAM_CCD5, CAL_7C294);
    r14 = gate_max(r14, RAM_B584, CAL_7C295);
    r14 = gate_max(r14, RAM_B586, CAL_7C296);
    r14 = gate_max(r14, RAM_B57E, CAL_7C297);
    r14 = gate_max(r14, RAM_B580, CAL_7C298);
    r14 = gate_max(r14, RAM_B582, CAL_7C299);
    r14 = gate_max(r14, RAM_CC8C, CAL_7C29A);
    r14 = gate_max(r14, RAM_CC8D, CAL_7C29B);

    /* 0x48C06: RAM8@0xFFFFCCD2 = r14, then epilogue (rts @0x48C0E). */
    RAM_CCD2 = r14;
}
