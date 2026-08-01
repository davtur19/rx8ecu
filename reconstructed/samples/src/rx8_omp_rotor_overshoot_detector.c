/*
 * =============================================================================
 * rx8_omp_rotor_overshoot_detector.c  —  OMP ROTOR OVER/UNDER-SHOOT DETECTOR
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x18CC0  (size 252 bytes; 0x18CC0..0x18DBC)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_omp_rotor_overshoot_detector.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + random vectors;
 *               every RAM byte the function can touch compared byte-for-byte,
 *               0 mismatches).
 * Lift (truth): c/omp_rotor_overshoot_detector_18CC0.c  (same address, same
 *               behaviour — the ground truth for this port; also in
 *               c/verified_addrs.txt, verified bit-exact via tools/sh2emu.py
 *               in c/tests/test_omp_rotor_overshoot_detector_18CC0.py).
 *
 * WHAT THIS IS
 * ------------
 * A single-pass RTOS companion task to omp_control_task_1825E (OS task table
 * @0x18000: 0x1802C -> 0x18CC0, see docs/notes/RESUME.md:45).  No ABI return
 * value — its whole effect is on RAM.  Flow (see the lift header for the fully
 * annotated register map):
 *
 *   1. ALWAYS read the idle/off port 0x807A via the leaf 0x3ED3C
 *      (readValue_8bit_ADDRESS_VAL) — a broken complementary pair raises the
 *      C6AC fault flag every tick, BEFORE any gating below.
 *   2. gate (A969 == 1 && A975 == 0): rotor-sync flag set + OMP ramp idle:
 *        A976 == 0 (OMP pump fault / inoperative):
 *            if A974 > sat8(r, CAL38)                  -> A992 = 1
 *        A976 != 0 (healthy):
 *            band = (r > CAL38) ? r - CAL38 : 0
 *            if A974 < band                            -> A993 = 1
 *      (A974 is captured at entry, stack-saved; CAL38 = ROM8[0x78E38].)
 *   3. latch flags once the debounce counters pass their thresholds (the
 *      counters are read PRE-increment, exactly like the ROM):
 *        A992 == 1 && A994 >= CAL39 -> A990 = 1
 *        A993 == 1 && A995 >= CAL3A -> A991 = 1
 *   4. debounce counters (sat8 increment while the trigger flag is set, hard
 *      reset to 0 the moment it clears):
 *        A992 == 1 -> A994 = sat8(A994, 1)   else A994 = 0
 *        A993 == 1 -> A995 = sat8(A995, 1)   else A995 = 0
 *
 * Interpretation: a rotor-position over/under-shoot detector companion to the
 * OMP stepper chain.  A992/A993 latch the position-error direction against the
 * idle/off port 0x807A; A994/A995 saturate while the condition persists and
 * raise the latched flags A990/A991 past CAL39/CAL3A.
 *
 * CALIBRATION BYTES (ROM, stock bin)
 * ----------------------------------
 *   CAL38 @0x78E38 = 0x01 (sat8 addend / band width)
 *   CAL39 @0x78E39 = 0x3E (62,  A994 debounce threshold)
 *   CAL3A @0x78E3A = 0x7D (125, A995 debounce threshold)
 *
 * CALLED LEAVES (lifted; run natively in the emulator — NOT inlined here,
 * exactly like the lift): the two externs below are implemented on the host
 * by the oracle as tiny verified models:
 *   0x3ED3C readValue_8bit_ADDRESS_VAL(addr, default) — s8(byte) on a valid
 *     complementary pair, else C6AC fault flag + s8(default).
 *   0x2478  addSaturate8Bit(a, b) = min(a + b, 255).
 * No un-lifted leaf is reached, so nothing else is inlined.
 *
 * RAM FOOTPRINT (all 8-bit @0xFFFFxxxx, byte address = xxxx):
 *   reads : A969 gate, A975 gate, A976 fault, A974 position (entry), A994,
 *           A995, port 0x807A/0x807B (complementary u16).
 *   writes: A992, A993 (trigger flags), A990, A991 (latched flags), A994,
 *           A995 (debounce counters); C6AC via the port-accessor leaf.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- RAM cells (8-bit @ 0xFFFFxxxx) ---- */
#define RAM_A969 (*(volatile uint8_t *)0xFFFFA969u)  /* rotor-sync dispatch flag */
#define RAM_A974 (*(volatile uint8_t *)0xFFFFA974u)  /* position target (entry)  */
#define RAM_A975 (*(volatile uint8_t *)0xFFFFA975u)  /* OMP ramp value           */
#define RAM_A976 (*(volatile uint8_t *)0xFFFFA976u)  /* OMP fault-inoperative    */
#define RAM_A990 (*(volatile uint8_t *)0xFFFFA990u)  /* over-shoot latch         */
#define RAM_A991 (*(volatile uint8_t *)0xFFFFA991u)  /* under-shoot latch        */
#define RAM_A992 (*(volatile uint8_t *)0xFFFFA992u)  /* over-shoot trigger       */
#define RAM_A993 (*(volatile uint8_t *)0xFFFFA993u)  /* under-shoot trigger      */
#define RAM_A994 (*(volatile uint8_t *)0xFFFFA994u)  /* over-shoot debounce ctr  */
#define RAM_A995 (*(volatile uint8_t *)0xFFFFA995u)  /* under-shoot debounce ctr */

/* ---- ROM calibration bytes (the oracle maps the page and seeds the real
 * bytes from the stock bin, so these pointers stay live on the host exactly
 * as they are on the target) ---- */
#define ROM_CAL38 (*(const uint8_t *)0x00078E38u)    /* 0x01 band width          */
#define ROM_CAL39 (*(const uint8_t *)0x00078E39u)    /* 0x3E A994 threshold      */
#define ROM_CAL3A (*(const uint8_t *)0x00078E3Au)    /* 0x7D A995 threshold      */

/* 0x3ED3C — verified leaf: RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(default),
 * fault flag RAM8[0xFFFFC6AC] set on mismatch.  Modelled on the host by the
 * oracle (the emulator runs the real ROM bytes). */
extern int8_t readValue_8bit_ADDRESS_VAL(uint16_t addr, uint8_t default_);
/* 0x2478 — verified saturating byte add: min(a + b, 255). */
extern uint8_t addSaturate8Bit(uint8_t a, uint8_t b);

/* 0x18CC0 — OMP rotor over/under-shoot detector (single pass, RAM-only effect). */
void rx8_omp_rotor_overshoot_detector(void)
{
    uint8_t a974 = RAM_A974;                 /* r10: captured at entry */
    int8_t r = readValue_8bit_ADDRESS_VAL(0x807A, 0x37);
    uint8_t a992 = 0, a993 = 0;

    /* gate: rotor-sync flag set, OMP ramp idle */
    if (RAM_A969 == 1 && RAM_A975 == 0) {
        if (RAM_A976 == 0) {
            /* OMP fault path: over-shoot when A974 exceeds the raised band
             * sat8(port, CAL38). */
            if (a974 > addSaturate8Bit((uint8_t)r, ROM_CAL38))
                a992 = 1;
        } else {
            /* healthy path: under-shoot when A974 sits below the lowered band
             * (port - CAL38, floored at 0). */
            uint8_t band = ((uint8_t)r > ROM_CAL38) ? (uint8_t)r - ROM_CAL38 : 0;
            if (a974 < band)
                a993 = 1;
        }
    }

    RAM_A992 = a992;
    RAM_A993 = a993;

    /* latch flags once the debounce counters pass their thresholds (the
     * counters are read pre-increment, exactly like the ROM). */
    if (a992 == 1 && RAM_A994 >= ROM_CAL39)
        RAM_A990 = 1;
    if (a993 == 1 && RAM_A995 >= ROM_CAL3A)
        RAM_A991 = 1;

    /* debounce counters: saturating increment while active, hard reset to 0. */
    RAM_A994 = a992 == 1 ? addSaturate8Bit(RAM_A994, 1) : 0;
    RAM_A995 = a993 == 1 ? addSaturate8Bit(RAM_A995, 1) : 0;
}
