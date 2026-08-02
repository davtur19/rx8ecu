/*
 * =============================================================================
 * rx8_omp_task_0x1825E.c  —  OMP (OIL-METERING-PUMP) RTOS TASK  @0x1825E
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x1825E  (size 756 bytes; 0x1825E..0x1853E, single exit at
 *               0x1853A; the 0x18540..0x18556 literal pool follows)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_omp_task_0x1825E.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               pre-states; every RAM side-effect cell compared byte-for-byte,
 *               0 mismatches).
 * Lift (truth): c/omp_task_0x1825E.c  (same address, same behaviour — the
 *               ground truth for this port; verified there via
 *               c/tests/test_omp_task_0x1825E.py, 150000+ random inputs across
 *               5 seeds vs the same emulator, 0 mismatches).
 *
 * WHAT THIS IS
 * ------------
 * The top of the OMP stepper-motor control chain.  An RTOS task dispatched by
 * the OS task table @0x18024 once per scheduler tick.  No ABI return value and
 * no ABI arguments — its whole effect is on RAM.  Flow (see the lift header
 * for the fully annotated register map):
 *
 *   1. snapshot the dispatch flags (A968 A969 A96A A96B A998 A96C) onto the
 *      stack frame at entry — later reads of these are the SNAPSHOT, not the
 *      live bytes;
 *   2. hardware fault gate (RAM9ECD bit1): bit clear -> A976 = 0 (pump
 *      "inoperative"); bit set -> A976 = 1 and, on a 0->1 edge, A987 = 1;
 *   3. engine-on accumulation: A988 == 1 && A96C == 0 -> A989 = 1;
 *   4. idle reset: A968 == 0 -> clear A977 / A978;
 *   5. countdown: A97B != 0 -> A97B -= 1  (unsigned extu.b + cmp/pl, so
 *      0x80..0xFF DO count down — see lift header note);
 *   6. purge block when A97B == 1 && A968 == 1 && A982 == 1 (A97B already
 *      decremented): A974 = 0, A97F = 0, write port 807C = 0, A979 = 1;
 *      A977 == 1 -> A977 = 0, A983 = 1, read port 8078 (default 0) and
 *      write back value-1; A978 == 1 -> A978 = 0;
 *   7. countdown still active -> partial epilogue (A988 = A96C, return);
 *   8. mode dispatch (A97B == 0): A974 = A97F, then first-set wins:
 *        A998 == 1            -> 0x18C6C wave-reload leaf (inlined below)
 *        A968 == 1            -> omp_waveform_state_machine_18860(A985)
 *        A96A == 1 && !CD06   -> 0x18C08 diag+rotor leaf (inlined below)
 *        A96B == 1            -> 0x18C5C purge-wave leaf (inlined below)
 *        A969 == 1            -> rotor_sync_position_detector(A984)
 *   9. common tail: A96C == 1 && A987 == 1 -> write port 807A = A974;
 *      read port 807A (default 0x37); A989 == 1 -> A975 ramp AND its two
 *      followers (0x18464 cmp/eq #1 / 0x18466 bf/s 0x1851C — A989 != 1 jumps
 *      straight to the epilogue, none of this runs):
 *        read7a < CAL36, or (A974 >= CAL37 && A976 == 0) -> A975 = sat8(A975,1);
 *        A974 >= CAL37 && A976 == 1 && A975 > 0 -> A975--;
 *        then A975 == 0 -> write port 8078 = CAL35;
 *        A975 != 0 && != 4 -> A979 = 0, A982 = 0;
 *  10. full epilogue: A983 = A987 = A989 = 0; A985 = A968, A984 = A969,
 *      A986 = A96A, A988 = A96C.
 *
 * CALLING CONVENTION
 * ------------------
 * void rx8_omp_task_0x1825E(void) — entered with a plain `jsr` from the RTOS
 * (r15 = task stack); no register arguments, nothing returned (the lift's only
 * exits are `rts` at 0x1853A and the partial-epilogue `rts` at 0x1854E).  The
 * harness calls the emulator at 0x1825E with sr = 0xF0, exactly like the RTOS
 * dispatch.
 *
 * RAM FOOTPRINT (all 8-bit @0xFFFFxxxx unless noted; byte address = xxxx)
 * --------------------------------------------------------------------------
 *   reads  : A968, A969, A96A, A96B, A96C (dispatch flags, snapshotted),
 *            A974, A975, A976, A977, A978, A979, A97B, A97F, A980, A982,
 *            A983, A984, A985, A987, A988, A989, A998, A8F1, ECD (bit1),
 *            CD06; AA10 (f32 coolant temp, via the 0x18860 leaf); the
 *            complement-encoded port pairs 8078/8079, 807A/807B, 807C/807D;
 *            F746 (u16 stepper drive port, via the 0x18552 leaf); A97C/A97D/
 *            A97E/A98A/A98B/A98D (via the leaves).
 *   writes : A974, A975, A976, A977, A978, A979, A97B, A97F, A980, A981,
 *            A982, A983, A984, A985, A986, A987, A988, A989, A97C, A97D,
 *            A97E, A98A, A98B, A98D (all via leaves), C6AC (fault flag, via
 *            the 0x3ED3C leaf), B5F3 (diag-table writer 0x9668 footprint, via
 *            the 0x18C08 leaf), the port pairs 8078/8079, 807A/807B,
 *            807C/807D, and the u16 port F746 (via the 0x18552 leaf).
 *
 * CALIBRATION BYTES (ROM, stock bin — host oracle maps the 0x78000 page and
 * seeds them from the vector; harness verifies they match the ROM)
 * ----------------------------------------------------------------------
 *   CAL35 @0x78E35 = 0x02   (P8078 write value when A975 == 0)
 *   CAL36 @0x78E36 = 0x34   (A975 ramp "read7a" threshold)
 *   CAL37 @0x78E37 = 0x3C   (A975 ramp A974 threshold)
 *   Plus, for the 0x18860 leaf reached on the A968 dispatch arm:
 *   CAL_A @0x78E33 = 0x3C, CAL_B @0x78E34 = 0x3C (A97E cal bytes), and the
 *   f32 -40.0 @0x78E68 (sensor-validity cold threshold; in stock ROM both cal
 *   bytes are equal, so no cold correction is actually applied).
 *
 * CALLED LEAVES (run natively in the emulator as real ROM bytes; the sample
 * declares them extern and the oracle models them — exactly like the lift)
 * -------------------------------------------------------------------------
 *   0x3ED3C readValue_8bit_ADDRESS_VAL(addr, def)  — complementary-pair read:
 *            RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(def) with the C6AC
 *            fault flag set on mismatch (leaf 0x3F050).
 *   0x3EE58 updateMemoryAtAddress_8bit_ADDR_VAL(addr, val) — complement-
 *            encoded byte store: RAM8[a] = val, RAM8[a+1] = ~val.
 *   0x2478  addSaturate8Bit(a, b) = min(a + b, 255).
 *   0x18552 omp_stepper_waveform_driver(mode) — 4-phase stepper driver.
 *   0x18860 omp_waveform_state_machine_18860(mode) — waveform SM stage.
 *   0x189EE rotor_sync_position_detector(mode) — rotor-sync position detector.
 *
 * The three internal task leaves 0x18C6C / 0x18C5C / 0x18C08 are INLINED
 * below as static helpers (same choice as the lift; the emulator still runs
 * their real ROM bytes):
 *   - 0x18C6C: A974 > 7 -> wave(3), A97B = 0x10; A974 == 7 -> wave(4),
 *     A97B = 4; A974 < 7 -> wave(2), A97B = 0x10.
 *   - 0x18C5C: wave(6), A97B = 8.
 *   - 0x18C08: if A980 == 1: write port 807C = 1, diag store
 *     RAM8[0xFFFFB5F3] = 1 (via 0x9668), A980 = 2.  Then A974 == A8F1 ->
 *     A97B = 0x30, A980 = 1; else rotor_sync_position_detector(A984).
 *
 * Port-accessor address literals: the leaves take a u16 address, so this
 * sample passes the truncated 16-bit form (0x8078/0x807A/0x807C) of the
 * lift's full 0xFFFF80xx literals — the oracle model sign-extends back into
 * the on-chip window, identical to the ROM's mov.w literals.
 *
 * LIFT VS ROM DISCREPANCIES
 * -------------------------
 * None found vs the ROM.  One sample-vs-lift discrepancy was found and FIXED
 * here (the lift is untouched): the lift hoists the "A975 == 0 -> write port
 * 8078 = CAL35" and the "A975 != 0 && != 4 -> A979 = 0, A982 = 0" checks OUT
 * of the A989 == 1 block, so it writes P8078 even when the ramp is disabled.
 * The ROM gates ALL of it on A989 == 1 (0x18464 cmp/eq #1 / 0x18466 bf/s
 * 0x1851C skips the whole 0x1846A..0x1851A block).  This port reproduces the
 * ROM; the harness pins it down with the engine-on-accumulation edge vectors
 * (A989 == 0 + A975 == 0).  Two subtleties carried over from the lift that
 * the harness pins down with targeted edge vectors:
 *   - the countdown decrement is `A97B != 0` (extu.b + cmp/pl), so values
 *     0x80..0xFF count down too;
 *   - the 0x18860 leaf's cold/sensor split compares with the SH-2 `fcmp/gt`
 *     ((-40.0f > temp) is TRUE for temp < -40.0), i.e. NaN temps fall to the
 *     "cal B" (warm) arm — the harness drives the -40.0 boundary and NaN
 *     to pin this down.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- RAM cells (8-bit @ 0xFFFFxxxx unless noted) ---- */
#define RAM_A968 (*(volatile uint8_t *)0xFFFFA968u)  /* idle-state / dispatch */
#define RAM_A969 (*(volatile uint8_t *)0xFFFFA969u)  /* rotor-sync flag       */
#define RAM_A96A (*(volatile uint8_t *)0xFFFFA96Au)  /* diag/rotor flag       */
#define RAM_A96B (*(volatile uint8_t *)0xFFFFA96Bu)  /* purge-wave flag       */
#define RAM_A96C (*(volatile uint8_t *)0xFFFFA96Cu)  /* engine-running flag   */
#define RAM_A974 (*(volatile uint8_t *)0xFFFFA974u)  /* position / ramp cond  */
#define RAM_A975 (*(volatile uint8_t *)0xFFFFA975u)  /* ramp value            */
#define RAM_A976 (*(volatile uint8_t *)0xFFFFA976u)  /* OMP fault-inoperative */
#define RAM_A977 (*(volatile uint8_t *)0xFFFFA977u)  /* warm-cal latch        */
#define RAM_A978 (*(volatile uint8_t *)0xFFFFA978u)  /* cold-cal latch        */
#define RAM_A979 (*(volatile uint8_t *)0xFFFFA979u)  /* purge-active latch    */
#define RAM_A97B (*(volatile uint8_t *)0xFFFFA97Bu)  /* task countdown        */
#define RAM_A97F (*(volatile uint8_t *)0xFFFFA97Fu)  /* wave position output  */
#define RAM_A980 (*(volatile uint8_t *)0xFFFFA980u)  /* 0x18C08 diag state    */
#define RAM_A982 (*(volatile uint8_t *)0xFFFFA982u)  /* purge-enable latch    */
#define RAM_A983 (*(volatile uint8_t *)0xFFFFA983u)  /* cal-A purge latch     */
#define RAM_A984 (*(volatile uint8_t *)0xFFFFA984u)  /* rotor mode            */
#define RAM_A985 (*(volatile uint8_t *)0xFFFFA985u)  /* wave-SM mode          */
#define RAM_A986 (*(volatile uint8_t *)0xFFFFA986u)
#define RAM_A987 (*(volatile uint8_t *)0xFFFFA987u)  /* fault-latched flag    */
#define RAM_A988 (*(volatile uint8_t *)0xFFFFA988u)
#define RAM_A989 (*(volatile uint8_t *)0xFFFFA989u)  /* ramp-enable flag      */
#define RAM_A998 (*(volatile uint8_t *)0xFFFFA998u)  /* wave-reload flag      */
#define RAM_A8F1 (*(volatile uint8_t *)0xFFFFA8F1u)  /* rotor compare target  */
#define RAM_ECD  (*(volatile uint8_t *)0xFFFF9ECDu)  /* HW fault reg, bit1    */
#define RAM_CD06 (*(volatile uint8_t *)0xFFFFCD06u)  /* 0x18C08 gate          */
#define RAM_B5F3 (*(volatile uint8_t *)0xFFFFB5F3u)  /* 0x9668 diag-table     */

/* ---- ROM calibration bytes (host oracle maps the 0x78000 page and seeds
 * them from the stock bin) ---- */
#define ROM_CAL35 (*(const uint8_t *)0x00078E35u)    /* 0x02 P8078 write val  */
#define ROM_CAL36 (*(const uint8_t *)0x00078E36u)    /* 0x34 ramp r7 threshold*/
#define ROM_CAL37 (*(const uint8_t *)0x00078E37u)    /* 0x3C ramp A974 thr    */
#define ROM_CAL_A (*(const uint8_t *)0x00078E33u)    /* 0x3C (0x18860 leaf)   */
#define ROM_CAL_B (*(const uint8_t *)0x00078E34u)    /* 0x3C (0x18860 leaf)   */
#define ROM_CAL_T (*(const float    *)0x00078E68u)   /* -40.0f (0x18860 leaf) */

/* 0x3ED3C — verified leaf: RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(default),
 * fault flag RAM8[0xFFFFC6AC] set on mismatch.  Modelled on the host by the
 * oracle (the emulator runs the real ROM bytes). */
extern int8_t readValue_8bit_ADDRESS_VAL(uint16_t addr, uint8_t default_);
/* 0x3EE58 — verified leaf: complementary-encoded byte store,
 * RAM8[a] = val, RAM8[a+1] = ~val. */
extern void updateMemoryAtAddress_8bit_ADDR_VAL(uint16_t addr, uint8_t val);
/* 0x2478 — verified saturating byte add: min(a + b, 255). */
extern uint8_t addSaturate8Bit(uint8_t a, uint8_t b);
/* 0x18552 — verified stepper waveform driver. */
extern void omp_stepper_waveform_driver(uint8_t mode);
/* 0x18860 — verified waveform state-machine stage of the OMP chain. */
extern void omp_waveform_state_machine_18860(uint8_t mode);
/* 0x189EE — verified rotor-sync position detector. */
extern void rotor_sync_position_detector(uint8_t mode);

/* ---- internal task leaves, inlined (see header for exact semantics) ---- */

/* 0x18C6C — wave-reload leaf (A998 dispatch arm). */
static void omp_wave_reload_18C6C(void)
{
    if (RAM_A974 > 7) {
        omp_stepper_waveform_driver(3);
        RAM_A97B = 0x10;
    } else if (RAM_A974 == 7) {
        omp_stepper_waveform_driver(4);
        RAM_A97B = 4;
    } else {
        omp_stepper_waveform_driver(2);
        RAM_A97B = 0x10;
    }
}

/* 0x18C5C — purge-wave leaf (A96B dispatch arm). */
static void omp_wave_purge_18C5C(void)
{
    omp_stepper_waveform_driver(6);
    RAM_A97B = 8;
}

/* 0x18C08 — diag-store + rotor-sync leaf (A96A && !CD06 dispatch arm). */
static void omp_diag_rotor_18C08(void)
{
    if (RAM_A980 == 1) {
        updateMemoryAtAddress_8bit_ADDR_VAL(0x807C, 1);
        RAM_B5F3 = 1;                    /* 0x9668 diag-table store */
        RAM_A980 = 2;
    }
    if (RAM_A974 == RAM_A8F1) {
        RAM_A97B = 0x30;
        RAM_A980 = 1;
    } else {
        rotor_sync_position_detector(RAM_A984);
    }
}

/* 0x1825E — OMP control task (void, no ABI args / no return value). */
void rx8_omp_task_0x1825E(void)
{
    uint8_t a968, a969, a96a, a96b, a96c, a998;

    /* step 1: snapshot dispatch flags onto the stack frame (0x18270..0x18294) */
    a968 = RAM_A968;
    a969 = RAM_A969;
    a96b = RAM_A96B;
    a96a = RAM_A96A;
    a998 = RAM_A998;
    a96c = RAM_A96C;

    /* step 2: hardware fault gate (0x1829A..0x182B2) */
    if ((RAM_ECD & 2) == 0) {
        RAM_A976 = 0;
    } else {
        uint8_t old = RAM_A976;
        RAM_A976 = 1;
        if (old == 0)
            RAM_A987 = 1;
    }

    /* step 3: engine-on accumulation */
    if (RAM_A988 == 1 && a96c == 0)
        RAM_A989 = 1;

    /* step 4: idle-state reset */
    if (a968 == 0) {
        RAM_A977 = 0;
        RAM_A978 = 0;
    }

    /* step 5: countdown decrement (extu.b + cmp/pl: unsigned != 0) */
    if (RAM_A97B != 0)
        RAM_A97B = (uint8_t)(RAM_A97B - 1);

    /* step 6: purge block */
    if (RAM_A97B == 1 && a968 == 1 && RAM_A982 == 1) {
        int8_t v;
        RAM_A974 = 0;
        RAM_A97F = 0;
        updateMemoryAtAddress_8bit_ADDR_VAL(0x807C, 0);
        RAM_A979 = 1;
        if (RAM_A977 == 1) {
            RAM_A977 = 0;
            RAM_A983 = 1;
            v = readValue_8bit_ADDRESS_VAL(0x8078, 0);
            if ((uint8_t)v != 0)
                updateMemoryAtAddress_8bit_ADDR_VAL(
                    0x8078, (uint8_t)((uint8_t)v - 1));
        }
        if (RAM_A978 == 1)
            RAM_A978 = 0;
    }

    /* step 7: countdown still active -> partial epilogue */
    if (RAM_A97B != 0) {
        RAM_A988 = a96c;
        return;
    }

    /* step 8: mode dispatch (first-set wins) */
    RAM_A974 = RAM_A97F;
    if (a998 == 1) {
        omp_wave_reload_18C6C();
    } else if (a968 == 1) {
        omp_waveform_state_machine_18860(RAM_A985);
    } else if (a96a == 1 && RAM_CD06 == 0) {
        omp_diag_rotor_18C08();
    } else if (a96b == 1) {
        omp_wave_purge_18C5C();
    } else if (a969 == 1) {
        rotor_sync_position_detector(RAM_A984);
    }

    /* step 9: common tail (0x184C8..0x1851A) — the whole ramp block plus the
     * A975-based P8078 write and A979/A982 clear is gated on A989 == 1
     * (ROM 0x18464 cmp/eq #1 / 0x18466 bf/s 0x1851C); when A989 != 1 the
     * task jumps straight to the epilogue and none of it runs. */
    if (a96c == 1 && RAM_A987 == 1)
        updateMemoryAtAddress_8bit_ADDR_VAL(0x807A, RAM_A974);
    {
        uint8_t read7a = (uint8_t)readValue_8bit_ADDRESS_VAL(0x807A, 0x37);
        if (RAM_A989 == 1) {
            if (read7a < ROM_CAL36 ||
                (RAM_A974 >= ROM_CAL37 && RAM_A976 == 0))
                RAM_A975 = addSaturate8Bit(RAM_A975, 1);   /* 0x2478 */
            else if (RAM_A974 >= ROM_CAL37 && RAM_A976 == 1 && RAM_A975 != 0)
                RAM_A975 = (uint8_t)(RAM_A975 - 1);
            if (RAM_A975 == 0)
                updateMemoryAtAddress_8bit_ADDR_VAL(0x8078, ROM_CAL35);
            else if (RAM_A975 != 4) {
                RAM_A979 = 0;
                RAM_A982 = 0;
            }
        }
    }

    /* step 10: full epilogue (0x1851C..0x1853C) */
    RAM_A983 = 0;
    RAM_A987 = 0;
    RAM_A989 = 0;
    RAM_A985 = a968;
    RAM_A984 = a969;
    RAM_A986 = a96a;
    RAM_A988 = a96c;
}
