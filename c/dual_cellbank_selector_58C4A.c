/* dual_cellbank_selector_58C4A.c
 *
 * ROM: 60E1D400  |  Address: 0x58C4A  |  Size: 0x48 bytes (code 0x58C4A..0x58C90,
 *       literal pool 0x58D20..0x58D58; next function @0x58C92).
 *       VERIFIED vs ROM emulator (0 mismatches, c/tests/test_dual_cellbank_selector_58C4A.py).
 *
 * Old IDA name: "spark_plug_lead_0x58C4A" (ida-ai).  NOT supported by the lift:
 * there is no spark-advance / ignition-timing / plug-work computation anywhere in
 * the body (the only leaf float work, in the 0x58C9E/0x58D58 path, converts legacy
 * float calibrations down to single word values for the cell banks).  The function
 * is a flag selector that initialises two 32-bit checksummed-cell banks (bases
 * 0xFFFF903C and 0xFFFF904C) on one of two conditions, and otherwise does nothing
 * but refresh a redundant 8-bit cell.
 *
 * Semantics (execution order):
 *   1. prev = RAM8@0xFFFFD26C.
 *   2. Call leaf 0x58C38 ("intake_port_0x58C38"): it reads the redundant pair
 *      RAM8[0xFFFF8FF2]/[0xFFFF8FF3] via the verified 0x3ED3C
 *      readValue_8bit_ADDRESS_VAL(addr=0xFFFF8FF2, dflt=0) and stores the trusted
 *      byte to RAM8@0xFFFFD26C; on a broken pair it also sets the fault flag
 *      RAM8@0xFFFFC6AC = 1 (side effect of 0x3F050 inside the accessor).
 *  3. sel = RAM8@0xFFFFD201.
 *     If sel == 1: reset both 32-bit cell banks to {1,0,0,0} via the verified
 *     write_port_u32_inv helper 0x3EE68 at bank bases 0xFFFF903C (callee 0x58C98
 *     -> 0x59A52) and 0xFFFF904C (callee 0x58D1C -> 0x59A52).
 *  4. Else if prevValue == 0 && updated RAM8@0xFFFFD26C == 1 (a 0->1 rising edge
 *     of the refreshed cell): recompute both banks via 0x58C9E ("oil_circulation")
 *     and 0x58D58; each cell value is a single word derived by leaf 0x2490
 *     (float->u16) from the f32 calibrations at 0xFFFFC760/0xFFFFC764 (bank A) and
 *     0xFFFFC768/0xFFFFC76C (bank B), with the 3rd cell fixed to 0xFFFF and the
 *     4th to 0.
 *  5. Otherwise: no cell writes (only the pair cell 0xFFFFD26C was refreshed).
 *
 * RAM reads:  D26C (u8, before & after refresh), D201 (u8 selector), the redundant
 *   pair 0xFFFF8FF2/3 (via 0x3ED3C), and — only on the rising-edge path — the four
 *   f32 at 0xFFFFC760..0xFFFFC76C.
 * RAM writes:  D26C (refreshed value), C6AC (fault, on broken pair), and the two
 *   cell banks 0xFFFF903C..0xFFFF904B and 0xFFFF904C..0xFFFF905B.
 *
 * Callees are NOT inlined; each is reproduced in the test harness by running the
 * actual ROM bytes in a second emulator instance (cpu2.call pattern), so the
 * float rounding, the 0x3ED3C validation and the 0x3EE68 cell encoding all match
 * the machine exactly.
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>

#define RAM_D201     (*(volatile uint8_t *)0xFFFFD201) /* selector / flag */
#define RAM_D26C     (*(volatile uint8_t *)0xFFFFD26C) /* refreshed cell (read+write) */

#define RAM_C760     (*(volatile float *)0xFFFFC760)   /* bank-A cell source (u16 from 0x2490) */
#define RAM_C764     (*(volatile float *)0xFFFFC764)
#define RAM_C768     (*(volatile float *)0xFFFFC768)   /* bank-B cell source */
#define RAM_C76C     (*(volatile float *)0xFFFFC76C)

/* The two 32-bit checksummed-cell banks written by the selected path. */
#define BANK_A       (*(volatile uint32_t *)0xFFFF903C)
#define BANK_B       (*(volatile uint32_t *)0xFFFF904C)

/* ---- not-yet-lifted callees (executed by the in-model emulator, never inlined) ---- */
extern void refresh_redundant_byte_0x58C38(void); /* leaf: 0x3ED3C refresh D26C + C6AC fault */
extern void cellbankA_reset_0x58C98(void);        /* 0x58C98 -> 0x59A52(base 0xFFFF903C) */
extern void cellbankB_reset_0x58D1C(void);        /* 0x58D1C -> 0x59A52(base 0xFFFF904C) */
extern void cellbankA_recalc_0x58C9E(void);       /* 0x58C9E -> float-derived bank A cells */
extern void cellbankB_recalc_0x58D58(void);       /* 0x58D58 -> float-derived bank B cells */

void dual_cellbank_selector_58C4A(void)
{
    uint8_t sel, prev;

    prev = RAM_D26C;               /* 0x58C50 mov.b @r1(=FFFFD26C),r3 -> local */
    refresh_redundant_byte_0x58C38();   /* 0x58C52 bsr 0x58C38 (writes D26C & maybe C6AC) */

    sel = RAM_D201;                /* 0x58C56 mov.w @(0x58D24),r2 ; mov.b @r2,r0 */

    if (sel == 1) {                /* 0x58C5C cmp/eq #1,r0 ; bf/s 0x58C6C */
        cellbankA_reset_0x58C98(); /* 0x58C62 bsr 0x58C98 -> 0x59A52(0xFFFF903C) */
        cellbankB_reset_0x58D1C(); /* 0x58C68 bra 0x58D1C  -> 0x59A52(0xFFFF904C) */
        return;
    }

    if (prev == 0 && RAM_D26C == 1) {  /* 0x58C6C tst r3 / cmp/eq#1,D26C */
        cellbankA_recalc_0x58C9E(); /* 0x58C80 bsr 0x58C9E */
        cellbankB_recalc_0x58D58(); /* 0x58C86 bra 0x58D58 */
        return;
    }
}