/*
 * =============================================================================
 * rx8_omp_waveform_state_machine_18860.c  —  OMP WAVEFORM STATE MACHINE
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x18860  (398 bytes; code 0x18860..0x189EC, rts @0x189EA with
 *               `mov.l @r15+,r14` in its delay slot; the state-2 literal pool
 *               lives at 0x18A42..0x18A5C)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_omp_waveform_state_machine_18860.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + 20000 random
 *               pre-states; every RAM byte the function can touch compared
 *               byte-for-byte, 0 mismatches).
 * Lift (truth): c/omp_waveform_state_machine_18860.c  (same address, same
 *               behaviour; the ROM bytes were executed for real in
 *               c/tests/test_omp_waveform_state_machine_18860.py over 60000
 *               random inputs).
 *
 * WHAT THIS IS
 * ------------
 * Waveform state-machine stage of the OMP (oil-metering pump) stepper chain,
 * called from omp_task_0x1825E with the mode byte in r4.  A 4-state machine on
 * RAM8[0xFFFFA981] (the state byte persists across calls):
 *
 *   state 0 (mode == 0 only): clear A981 and A982.              (0x18878)
 *
 *   A981 == 1  (gate + cal select, 0x18880..0x188DE):
 *       if A968 == 1:  sensor-validity gate on the complementary port
 *       bytes via readValue_8bit_ADDRESS_VAL (0x3ED3C):
 *           P8078 pair invalid or == 0  -> cal A (r14)
 *           P8078 ok, P807C pair != 1   -> cal A
 *           P8078 ok, P807C == 1:
 *               fcmp/gt gives (-40.0 > temp)  -> temp < -40.0 -> cal A,
 *               else (temp >= -40.0, incl. NaN/+inf)            -> cal B
 *       A97E = the cal byte (CAL_A 0x78E33 / CAL_B 0x78E34; both 0x3C in
 *       stock ROM, so no cold correction is actually applied), A977 = cal-B
 *       flag (r9), A978 = cal-A flag (r14), A981 -> 2.
 *       NOTE: the -40.0 threshold is a SENSOR-VALIDITY split, not a
 *       cold-weather calibration.
 *
 *   A981 == 0  (step drive, 0x188E0..0x18962):
 *       A97C == 5 -> A97B = 0x80, A981 = 1
 *       A97C == 4 -> A97B = 0x30, wave(0); A974 < 60 -> A97F = A974+1
 *       else      -> A97B = 0x10, wave(2)
 *
 *   A981 == 2  (timing adjust, 0x18964..0x189DC):
 *       if A977 == 1 or A978 == 1:
 *           even A97C -> A97B = 0x30, wave(1); then RE-READ A97C (the wave
 *                        driver may have advanced it): if A97C == 5 (post-wave)
 *                        && A97E <= 1: A982 = 1, A97F = 0, A97E = 0,
 *                        A97B = sat8(A97B, 0x30)
 *           odd  A97C -> A97B = 8, wave(1); A97E > 0 -> A97E -= 1
 *
 * The state blocks are sequential with a FRESH A981 read before each one
 * (exactly like the ROM), so e.g. mode == 0 clearing A981 to 0 lets the
 * step-drive block run in the same call.
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_omp_waveform_state_machine_18860(uint8_t mode)` — one ABI argument
 * (r4, the mode byte, `extu.b`-masked to 8 bits at 0x18862), no return value
 * (plain `rts`).  Driven through the standard SH2.call() entry; equivalence is
 * judged on the RAM side-effects, not a return value.
 *
 * CALLED LEAVES (all executed for REAL by the emulator harness; declared
 * extern here and modelled on the host by the oracle — same convention as the
 * sibling rx8_omp_rotor_overshoot_detector.c):
 *   0x3ED3C readValue_8bit_ADDRESS_VAL(addr, default) — returns s8(RAM8[a])
 *     when RAM8[a] == ~RAM8[a+1] (complementary pair), else s8(default) AND
 *     writes RAM8[0xFFFFC6AC] = 1 (via leaf 0x3F050).
 *   0x18552 omp_stepper_waveform_driver(mode) — the verified stepper waveform
 *     driver (modes 0, 1, 2 are used here; RAM effects: A97C step, A97D,
 *     A97F (conditional), A98A/A98D = mode, F746 4-phase port RMW).
 *   0x2478  addSaturate8Bit(a, b) = min(a + b, 255).
 *
 * DISCREPANCY vs c/omp_waveform_state_machine_18860.c (corrected here)
 * --------------------------------------------------------------------
 * The lift's extern comment for 0x3ED3C documents only
 * `RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(default)`.  The ACTUAL leaf also
 * sets the fault flag RAM8[0xFFFFC6AC] = 1 on a broken complementary pair
 * (disassembly: 0x3ED64 jsr 0x3F050 with r13 = s8(default); 0x3F050 stores
 * 0x01 to 0xFFFFC6AC).  The emulator harness executes the real leaf bytes, so
 * the host model reproduces the C6AC write and the harness compares C6AC
 * byte-for-byte.  No other lift-vs-ROM discrepancy was found (every branch of
 * the disassembly 0x18860..0x189EC was re-traced against the lift before
 * writing this sample).
 *
 * CALIBRATION CONSTANTS (ROM)
 * ---------------------------
 *   0x78E33 u8   cal-A byte          (= 0x3C in stock ROM)
 *   0x78E34 u8   cal-B byte          (= 0x3C in stock ROM)
 *   0x78E68 f32  sensor-validity temperature threshold  (= -40.0)
 * The host oracle mmap()s the ROM page 0x78000 at the same virtual address
 * (file offset == virtual address) and seeds the real stock bytes, so both
 * sides read identical values.
 *
 * RAM FOOTPRINT (all @0xFFFFxxxx; byte address = xxxx):
 *   reads : A981 (state), A968 (gate), A97C (step), A974 (rotor pos), A97E,
 *           A977/A978 (cal flags), A97B (sat8 addend), port pairs
 *           8078/8079 + 807C/807D (complementary u16 via 0x3ED3C),
 *           AA10 (f32 coolant temp), and — through the wave driver leaf —
 *           A97C/A97D/A974/A98A/A969/A96A/F746.
 *   writes: A981, A982, A97E, A977, A978 (state block), A97B, A97F (step
 *           drive), C6AC (via the port-accessor leaf on a broken pair), and —
 *           through the wave driver leaf — A97C, A97D, A98A, A98D, F746.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- OMP state-machine cells (8-bit @ 0xFFFFxxxx) ---- */
#define RAM_A981 (*(volatile uint8_t *)0xFFFFA981u)  /* 4-state machine state */
#define RAM_A982 (*(volatile uint8_t *)0xFFFFA982u)  /* wave-latch flag       */
#define RAM_A97E (*(volatile uint8_t *)0xFFFFA97Eu)  /* cal byte / countdown  */
#define RAM_A97B (*(volatile uint8_t *)0xFFFFA97Bu)  /* stepper command byte  */
#define RAM_A97F (*(volatile uint8_t *)0xFFFFA97Fu)  /* waveform byte         */
#define RAM_A977 (*(volatile uint8_t *)0xFFFFA977u)  /* cal-B flag (latch)    */
#define RAM_A978 (*(volatile uint8_t *)0xFFFFA978u)  /* cal-A flag (latch)    */
#define RAM_A968 (*(volatile uint8_t *)0xFFFFA968u)  /* gate flag             */
#define RAM_A97C (*(volatile uint8_t *)0xFFFFA97Cu)  /* step register         */
#define RAM_A974 (*(volatile uint8_t *)0xFFFFA974u)  /* rotor position        */
#define RAM_AA10 (*(volatile float    *)0xFFFFAA10u) /* coolant temp (f32)    */

/* ---- ROM calibration constants (oracle maps page 0x78000 + seeds stock
 * bytes; on the little-endian host the f32 is byte-assembled from the ROM
 * file so these pointers carry the exact same values the ROM fetches) ---- */
#define ROM_CAL_A (*(const uint8_t *)0x00078E33u)    /* 0x3C  */
#define ROM_CAL_B (*(const uint8_t *)0x00078E34u)    /* 0x3C  */
#define ROM_CAL_T (*(const float    *)0x00078E68u)   /* -40.0 */

/* 0x3ED3C — verified leaf: RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(default),
 * fault flag RAM8[0xFFFFC6AC] set on mismatch (see header discrepancy note).
 * Modelled on the host by the oracle (the emulator runs the real ROM bytes). */
extern int8_t readValue_8bit_ADDRESS_VAL(uint16_t addr, uint8_t default_);
/* 0x18552 — verified stepper waveform driver (modes 0,1,2 used here). */
extern void omp_stepper_waveform_driver(uint8_t mode);
/* 0x2478 — verified saturating byte add: min(a + b, 255). */
extern uint8_t addSaturate8Bit(uint8_t a, uint8_t b);

/* 0x18860 — OMP waveform state machine (void, one r4 arg, no return). */
void rx8_omp_waveform_state_machine_18860(uint8_t mode)
{
    if (mode == 0) {                 /* 0x18878: state reset (mode 0 only) */
        RAM_A981 = 0;
        RAM_A982 = 0;
    }

    if (RAM_A981 == 1) {             /* 0x18880..0x188DE: gate + cal select */
        uint8_t r9 = 0, r14 = 0;     /* cal-B flag / cal-A flag */
        if (RAM_A968 == 1) {
            if ((uint8_t)readValue_8bit_ADDRESS_VAL(0x8078u, 0) != 0) {
                if ((uint8_t)readValue_8bit_ADDRESS_VAL(0x807Cu, 0) == 1) {
                    /* fcmp/gt fr3(-40.0),fr2(temp): T = (-40.0 > temp), so
                     * cal A iff temp < -40.0 (NaN/+inf -> not taken -> cal B) */
                    if (ROM_CAL_T > RAM_AA10)
                        r14 = 1;     /* temp < -40.0 -> cal A */
                    else
                        r9 = 1;      /* temp >= -40.0 -> cal B */
                } else
                    r14 = 1;
            } else
                r14 = 1;
            RAM_A97E = (r9 == 1) ? ROM_CAL_B : ROM_CAL_A;
        }
        RAM_A977 = r9;
        RAM_A978 = r14;
        RAM_A981 = 2;
    }

    if (RAM_A981 == 0) {             /* 0x188E0..0x18962: step drive */
        switch (RAM_A97C) {
        case 5:
            RAM_A97B = 0x80;
            RAM_A981 = 1;
            break;
        case 4:
            RAM_A97B = 0x30;
            omp_stepper_waveform_driver(0);
            /* cmp/ge r1(60),r2(A974): T = (A974 >= 60), bt skips the write */
            if (RAM_A974 < 60)
                RAM_A97F = (uint8_t)(RAM_A974 + 1);
            break;
        default:
            RAM_A97B = 0x10;
            omp_stepper_waveform_driver(2);
            break;
        }
    }

    if (RAM_A981 == 2) {             /* 0x18964..0x189DC: timing adjust */
        if (RAM_A977 == 1 || RAM_A978 == 1) {
            if ((RAM_A97C & 1) == 0) {           /* even step */
                RAM_A97B = 0x30;
                omp_stepper_waveform_driver(1);
                /* A97C is RE-READ after the wave call (the driver may have
                 * advanced the step register); A97E <= 1 test is cmp/gt
                 * (A97E > 1) -> skip, i.e. proceed when A97E <= 1. */
                if (RAM_A97C == 5 && RAM_A97E <= 1) {
                    RAM_A982 = 1;
                    RAM_A97F = 0;
                    RAM_A97E = 0;
                    RAM_A97B = addSaturate8Bit(RAM_A97B, 0x30);
                }
            } else {                              /* odd step */
                RAM_A97B = 8;
                omp_stepper_waveform_driver(1);
                if (RAM_A97E > 0)
                    RAM_A97E = (uint8_t)(RAM_A97E + 0xFFu);  /* -1 mod 256 */
            }
        }
    }
}
