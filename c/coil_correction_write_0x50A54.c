/* coil_correction_write_0x50A54.c
 *
 * ROM: 60E1D400  |  Address: 0x50A54  |  Size: 0x98 bytes (0x50A54..0x50AEC)
 *       code 0x50A54..0x50AEA; literal pool @0x50B60..0x50B90 (shared with the
 *       following diag_enable_check_0x50AEC, which reuses the same pool) and
 *       no per-function data; end of function is the epilogue @0x50AE4..0x50AEA,
 *       next function diag_enable_check_0x50AEC @0x50AEC.
 *       VERIFIED vs ROM emulator (0 mismatches, c/tests/test_coil_correction_
 *       write_0x50A54.py).
 *
 * Old IDA name: "spark_plug_monitor_0x50A54" — NOT supported by the lift.  It
 * monitors neither spark plugs nor ignition coils directly; it reads a
 * shared diagnostic counter (u16@0xFFFFCFE6) and a timing-correction
 * structure (float+checksum @0xFFFF86A4), localizes it with a ROM look-up
 * table, and — under a set of enable flags — conditionally writes a value
 * into the (checksummed) cold-start-correction structure held at
 * 0xFFFF86AC (the same structure that timing_correction_3EE0A's sibling
 * cold_start_enrichment_3EEB8 maintains).  Full semantics below.
 *
 * Semantics (execution order):
 *   1. r14 = u16@0xFFFFCF6E            (a shared counter/period, big-endian)
 *   2. timing = timing_correction_3EE0A(0xFFFF86A4, fr4=0.0)  [callee]
 *        - the callee validates the checksummed structure at 0xFFFF86A4:
 *          u16 w0@+0, w1@+2, w2@+4, w3@+6; check = (u16)~(w0+w1).
 *          If (w2 == check) or (w3 == check) it returns the stored float
 *          f32@0xFFFF86A4; otherwise it returns the passed float (0.0) and
 *          calls the fault-flag leaf 0x3F050 (RAM8@0xFFFFC6AC = 1) and the
 *          task-check/dispatch leaves.
 *   3. idx = fpu_sub_float(desc@0x6BAE8, fr4=timing)   [callee; ROM 2D curve]
 *        - 9-point curve x=[10..90] f32 -> u16 (3303..548); returns the
 *          interpolated index in r0.
 *      u16@0xFFFFD0B4 = (u16)idx
 *   4. if (u8@0xFFFFD201 == 1):
 *        cold_start_enrichment_3EEB8(0xFFFF86AC, fr4=0.0)  [callee: writes
 *          f32@0xFFFF86AC = 0.0, u16@0xFFFF86B0 = (u16)~(hi+lo of 0.0 bits)=0x0000,
 *          u16@0xFFFF86B2 = 0x0000, plus task leaves]; return.
 *   5. else if (u8@0xFFFFD07C == 1 AND u16@0xFFFFCFE6 <= u16@0xFFFFD0B4):
 *        delta = f32@0xFFFFD01C - f32@0xFFFFD024
 *        cold_start_enrichment_3EEB8(0xFFFF86AC, fr4=delta); return.
 *   6. else 0x50AA8 gate:
 *        if ( (u8)u16@0xFFFFCFC1 > (u8)ROM8@0x7D959            [39]
 *             AND u16@0xFFFFCFE6 >  u16@0xFFFFCFE4
 *             AND (u8)u16@0xFFFFD034 == 0 ):
 *              cold_start_enrichment_3EEB8(0xFFFF86AC, fr4=delta); return;
 *   7. default: no write, return.
 *
 * Inputs (RAM reads):  CFE6 (u16), D201 (u8), D07C (u8), D0B4 (u16),
 *   CFC1 (u8), CFE4 (u16), D034 (u8), D01C (f32), D024 (f32); timing/cold
 *   structs at 0xFFFF86A4 (w0..w3 + f32) and, for writes, the 0xFFFF86AC
 *   cold-start struct.  ROM constants:  curve desc @0x6BAE8 counts
 *   f32 axis @0x7D4B4 / u16 values @0x7D4D8; gate byte@0x7D959 (stock 39);
 *   f32 0xFFFF86A4 mask? none — all inputs RAM.
 * Outputs (RAM writes):  u16@0xFFFFD0B4 (curve index); optionally the
 *   cold-start-correction struct @0xFFFF86AC (+0 f32, +4/+6 u16 checksum
 *   words); and via the callees the fault flag u8@0xFFFFC6AC (on a bad
 *   timing-correction checksum).
 *
 * Callees are NOT inlined here — they are lifted in the ROM and their exact
 * float/NaN/RAM side effects are reproduced by the test harness with the
 * emulator-in-model trick (a second CPU instance runs the real helper bytes;
 * see c/tests/coil_correction_write_0x50A54.py).  The C lift only declares the
 * observable effect of each and transcribes the straight-line flow.
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>

#define RAM_CFE6  (*(volatile uint16_t *)0xFFFFCFE6)   /* big-endian counter  */
#define RAM_D201  (*(volatile uint8_t  *)0xFFFFD201)   /* enable flag 1 */
#define RAM_D07C  (*(volatile uint8_t  *)0xFFFFD07C)   /* enable flag 2 */
#define RAM_D0B4  (*(volatile uint16_t *)0xFFFFD0B4)   /* curve index out (u16) */
#define RAM_CFC1  (*(volatile uint8_t  *)0xFFFFCFC1)
#define RAM_CFE4  (*(volatile uint16_t *)0xFFFFCFE4)
#define RAM_D034  (*(volatile uint8_t  *)0xFFFFD034)
#define RAM_D01C  (*(volatile float    *)0xFFFFD01C)   /* correction f32 base */
#define RAM_D024  (*(volatile float    *)0xFFFFD024)   /* correction f32 base */
#define ROM_7D959 (*(const uint8_t     *)0x0007D959)   /* gate threshold (stock 39) */

/* ---- callees (verified ROM subroutines), emulator-in-model ---
 * float timing_correction_3EE0A():  argued with r4=0xFFFF86A4 and fr4=0.0.
 *   Validates the checksummed config struct @0xFFFF86A4 (u16 w0..w3, f32).
 *   On a valid checksum returns the stored float, else returns 0.0 and sets
 *   the fault flag RAM8@0xFFFFC6AC = 1 (via the i_flag leaf 0x3F050) plus the
 *   task-check/dispatch leaves.   (callee address 0x3EE0A)
 *
 * uint16_t fpu_curve_index_0x20C4():  approximated with r4=desc 0x6BAE8 and
 *   r4 float = the timing value; runs a 2D f32-axis / u16-value interpolation
 *   and returns the interpolated index in r0.  (address 0x20C4)
 *
 * void cold_start_enrichment_0x3EEB8(uintptr_t addr, float fr4): writes
 *   f32@addr = fr4, u16@addr+4 = (u16)~( (bits>>0) + (bits>>16) ),
 *   u16@addr+6 = same checksum (verified constant behaviour for x==x),
 *   then dispatches the task-check leaves.  (address 0x3EEB8)
 */
extern float    timing_correction_3EE0A(void);           /* 0x3EE0A */
extern uint16_t fpu_curve_index_0x20C4(void);            /* 0x20C4 */
extern void     cold_start_enrichment_3EEB8(float fr4);  /* 0x3EEB8 */

void coil_correction_write_0x50A54(void)
{
    uint16_t cfe = RAM_CFE6;

    /* 1..3: curve index -> D0B4 */
    (void)timing_correction_3EE0A();   /* validates struct; sets fault flag on bad checksum */
    uint16_t idx = fpu_curve_index_0x20C4();
    RAM_D0B4 = idx;

    /* 4: D201 == 1 -> zero cold-start correction */
    if (RAM_D201 == 1) {
        cold_start_enrichment_3EEB8(0.0f);
        return;
    }

    /* 5: D07C == 1 and cfe <= D0B4(now idx) -> write delta */
    if (RAM_D07C == 1 && !(cfe > RAM_D0B4)) {
        cold_start_enrichment_3EEB8(RAM_D01C - RAM_D024);
        return;
    }

    /* 6: gate (late) -> write delta */
    if ((uint8_t)RAM_CFC1 > ROM_7D959 &&
        cfe > RAM_CFE4 &&
        (uint8_t)RAM_D034 == 0) {
        cold_start_enrichment_3EEB8(RAM_D01C - RAM_D024);
        return;
    }

    /* 7: default */
}