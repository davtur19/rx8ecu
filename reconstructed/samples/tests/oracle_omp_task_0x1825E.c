/* ============================================================================
 * oracle_omp_task_0x1825E.c  —  host rig for rx8_omp_task_0x1825E
 * ============================================================================
 * Compile together with samples/src/rx8_omp_task_0x1825E.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *   omp <cal35> <cal36> <cal37> <cala> <calb> <calt> <a968>..<a999 (50 bytes)>
 *       <a8f1> <c6ac> <ecd> <cd06> <p78h> <p78l> <p7ah> <p7al> <p7ch> <p7cl>
 *       <f746h> <f746l> <t0> <t1> <t2> <t3>
 *                                             -> 34 post-state bytes
 *
 *   cal35/36/37 : the ramp calibration bytes the ROM reads at 0x78E35..0x78E37
 *   cala/calb   : the 0x18860-leaf cal bytes @0x78E33/0x78E34
 *   calt        : raw IEEE-754 bits of the -40.0 cold threshold @0x78E68
 *   a968..a999  : the full A9xx RAM block (dispatch flags + ramp/state cells)
 *   a8f1/c6ac/ecd/cd06 : rotor compare / ADDRESS_VAL fault flag / hardware
 *                 fault register / 0x18C08 gate
 *   p78h/l, p7ah/l, p7ch/l : the complement-encoded port pairs @0xFFFF8078,
 *                 0xFFFF807A, 0xFFFF807C
 *   f746h/l     : u16 stepper drive port @0xFFFFF746
 *   t0..t3      : raw IEEE-754 bits of the f32 coolant temp @0xFFFFAA10
 *                 (read by the 0x18860 leaf only)
 *
 * The 34 printed bytes are the whole writable RAM side-effect set of the
 * function (the A974..A98D state block, the C6AC fault flag, the B5F3 diag
 * footprint, both bytes of each of the three complement-encoded port pairs,
 * and both bytes of the F746 stepper port).
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the RAM cells AND the ROM calibration page, seeds every byte
 * and prints the post-state bytes.  It contains NO copy of the 0x1825E logic
 * — that lives solely in the reconstructed source under test.
 *
 * Per-vector state reset: the mmap pages persist across vectors, so every
 * cell the task can write must be re-seeded each iteration.  B5F3 is
 * write-only from the task (only the inlined 0x18C08 diag-store leaf sets
 * RAM_B5F3 = 1 when A980 == 1), so it is re-seeded to 0 per vector below;
 * the emulator side starts each call from a fresh RAM dict (B5F3 = 0), so a
 * reset is the exact equivalent — the A980==1 diag edge vectors then drive
 * B5F3 0->1 on BOTH sides and the comparison still sees it.  The six ROM
 * leaves the task jsr's ARE modelled here, since the sample declares them
 * extern exactly like the lift does (c/omp_task_0x1825E.c) and the emulator
 * runs the real bytes:
 *
 *   0x3ED3C readValue_8bit_ADDRESS_VAL        — complementary-pair read
 *   0x3EE58 updateMemoryAtAddress_8bit_ADDR_VAL — complement-encoded store
 *   0x2478  addSaturate8Bit                    — saturating byte add
 *   0x18552 omp_stepper_waveform_driver        — 4-phase stepper driver
 *   0x18860 omp_waveform_state_machine_18860   — waveform SM stage
 *   0x189EE rotor_sync_position_detector       — rotor-sync position detector
 *
 * The first three are the "port accessor" leaf models (same source as
 * c/tests/test_omp_accessors.py); the last three are C ports of the Python
 * models in c/tests/test_omp_stepper_waveform_driver.py,
 * test_omp_waveform_state_machine_18860.py and
 * test_rotor_sync_position_detector.py (all three verified against the real
 * ROM bytes).  The 0x18860 model reads the coolant temp @0xFFFFAA10 and the
 * -40.0 cal @0x78E68 with native host floats, so the vector ships raw
 * big-endian f32 bits and the oracle assembles them host-endian — identical
 * numeric values on both sides (same convention as oracle_ssv_control.c).
 *
 * The inline 0x18552 model below carries three byte-exactness fixes over the
 * original (documented in full at the function; all mirror the standalone
 * src/rx8_omp_stepper_waveform_driver.c, which is verified against the same
 * emulator):
 *   - the new step is stored back to RAM[0xFFFFA97C] in every non-default
 *     mode branch, exactly where the ROM's `mov.b r0,@r14` does (the old
 *     model kept A97C at its pre-state 0);
 *   - the u16 F746 stepper port is read and written big-endian byte-wise
 *     (F746 = hi byte, F746+1 = lo byte), matching the SH-2 emulator the
 *     harness compares the two bytes against (index 33/34); the old model
 *     wrote a host u16, little-endian bytes 03 00 instead of 00 03;
 *   - a step >= 9 (mode-4 A97D source) is clamped to all-zero phases like
 *     the emulator's out-of-table 0x00 stack-frame reads.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00078000  ROM calibration table (0x78E33..0x78E68)
 *   0xFFFF8000  RAM[0xFFFF8078/7A/7C] OMP complement-encoded ports
 *   0xFFFF9000  RAM[0xFFFF9ECD] hardware fault register
 *   0xFFFFA000  RAM[0xFFFFA968..A999] OMP state block + 0xFFFFAA10 (f32)
 *   0xFFFFB000  RAM[0xFFFFB5F3] diag-table footprint
 *   0xFFFFC000  RAM[0xFFFFC6AC] fault flag + RAM[0xFFFFCD06] gate
 *   0xFFFFF000  RAM[0xFFFFF746] stepper drive port (u16)
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_omp_task_0x1825E is not (yet) in rx8_samples.h — the shared header is
 * owned by the samples build.  The reconstructed source itself carries the
 * authoritative definition (src/rx8_omp_task_0x1825E.c); this prototype
 * mirrors it exactly. */
void rx8_omp_task_0x1825E(void);

/* ---- RAM cells (8-bit @ 0xFFFFxxxx unless noted) ---- */
#define A968   0xFFFFA968u   /* idle-state / dispatch flag (snapshot)  */
#define A969   0xFFFFA969u   /* rotor-sync dispatch flag               */
#define A96A   0xFFFFA96Au   /* diag/rotor dispatch flag               */
#define A96B   0xFFFFA96Bu   /* purge-wave dispatch flag               */
#define A96C   0xFFFFA96Cu   /* engine-running flag                    */
#define A974   0xFFFFA974u   /* position target / ramp condition       */
#define A975   0xFFFFA975u   /* ramp value                             */
#define A976   0xFFFFA976u   /* OMP fault-inoperative flag             */
#define A977   0xFFFFA977u   /* warm-cal latch                         */
#define A978   0xFFFFA978u   /* cold-cal latch                         */
#define A979   0xFFFFA979u   /* purge-active latch                     */
#define A97B   0xFFFFA97Bu   /* task countdown                         */
#define A97C   0xFFFFA97Cu   /* wave step (via leaves)                 */
#define A97D   0xFFFFA97Du   /* rotor-sync step source (via leaves)    */
#define A97E   0xFFFFA97Eu   /* cal discriminator (via 0x18860)        */
#define A97F   0xFFFFA97Fu   /* wave position output                   */
#define A980   0xFFFFA980u   /* 0x18C08 diag state                     */
#define A981   0xFFFFA981u   /* 0x18860 state machine                  */
#define A982   0xFFFFA982u   /* purge-enable latch                     */
#define A983   0xFFFFA983u   /* cal-A purge latch                      */
#define A984   0xFFFFA984u   /* rotor mode                             */
#define A985   0xFFFFA985u   /* wave-SM mode                           */
#define A986   0xFFFFA986u
#define A987   0xFFFFA987u   /* fault-latched flag                     */
#define A988   0xFFFFA988u
#define A989   0xFFFFA989u   /* ramp-enable flag                       */
#define A98A   0xFFFFA98Au   /* wave discriminator (via 0x18552)       */
#define A98B   0xFFFFA98Bu   /* rotor state (via 0x189EE)              */
#define A98D   0xFFFFA98Du   /* wave mode latch (via 0x18552)          */
#define A998   0xFFFFA998u   /* wave-reload dispatch flag              */
#define A8F1   0xFFFFA8F1u   /* rotor-sync compare target              */
#define ECD    0xFFFF9ECDu   /* hardware fault register (bit1 = OMP)   */
#define CD06   0xFFFFCD06u   /* 0x18C08 gate                           */
#define C6AC   0xFFFFC6ACu   /* ADDRESS_VAL fault flag                 */
#define B5F3   0xFFFFB5F3u   /* 0x9668 diag-table footprint           */
#define AA10   0xFFFFAA10u   /* f32 coolant temp (0x18860 leaf)        */
#define P78    0xFFFF8078u   /* ramp output port (complementary u16)   */
#define P7A    0xFFFF807Au   /* idle/off port (complementary u16)      */
#define P7C    0xFFFF807Cu   /* purge port (complementary u16)         */
#define F746   0xFFFFF746u   /* stepper drive port (u16)               */

/* ---- ROM calibration page ---- */
#define ROM_CAL_PAGE  0x00078000u
#define ROM_CAL_A     0x00078E33u   /* u8  0x3C (0x18860 leaf)          */
#define ROM_CAL_B     0x00078E34u   /* u8  0x3C (0x18860 leaf)          */
#define ROM_CAL35     0x00078E35u   /* u8  0x02 (P8078 write value)     */
#define ROM_CAL36     0x00078E36u   /* u8  0x34 (ramp r7 threshold)     */
#define ROM_CAL37     0x00078E37u   /* u8  0x3C (ramp A974 threshold)   */
#define ROM_CAL_T     0x00078E68u   /* f32 -40.0 (0x18860 leaf)         */

/* 4-phase step pattern table, ROM 0x4ED5C (9 steps x 4 phases). */
static const uint8_t STEP_PATTERN[9][4] = {
    {1, 0, 0, 1}, {1, 0, 0, 0}, {1, 1, 0, 0}, {0, 1, 0, 0}, {0, 1, 1, 0},
    {0, 0, 1, 0}, {0, 0, 1, 1}, {0, 0, 0, 1}, {0, 0, 0, 0},
};

/* ---- the 34 post-state bytes the oracle prints ---- */
static const uintptr_t OUT[] = {
    A974, A975, A976, A977, A978, A979, A97B, A97C, A97D, A97E, A97F,
    A980, A981, A982, A983, A984, A985, A986, A987, A988, A989,
    A98A, A98B, A98D,
    C6AC, B5F3,
    P78, P78 + 1, P7A, P7A + 1, P7C, P7C + 1,
    F746, F746 + 1,
};
#define NOUT ((int)(sizeof OUT / sizeof OUT[0]))   /* 34 */

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
}

/* Assemble big-endian f32 bits (from the ROM file / vector) into a host
 * float — the numeric value is identical on both sides (see oracle header). */
static float be32_to_hostf(uint32_t bits)
{
    float v;
    memcpy(&v, &bits, sizeof v);
    return v;
}

/* ========================== ROM leaf models ============================== */

/* 0x3ED3C — RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(default); the C6AC
 * fault flag is set on mismatch (fault-flag leaf 0x3F050).  The address
 * arrives as a u16 (0x8078/0x807A/0x807C) and lives in the on-chip window at
 * 0xFFFFxxxx, exactly as the ROM's sign-extended mov.w literal. */
int8_t readValue_8bit_ADDRESS_VAL(uint16_t addr, uint8_t default_)
{
    uintptr_t a = 0xFFFF0000u | addr;
    uint8_t b0 = *(volatile uint8_t *)(uintptr_t)a;
    uint8_t b1 = *(volatile uint8_t *)(uintptr_t)(a + 1);
    if (b0 == (uint8_t)~b1)
        return (int8_t)b0;
    *(volatile uint8_t *)(uintptr_t)C6AC = 1;
    return (int8_t)default_;
}

/* 0x3EE58 — complementary-encoded byte store: RAM8[a] = val, RAM8[a+1] =
 * ~val (a 16-bit word (val<<8)|(~val&0xFF) written big-endian). */
void updateMemoryAtAddress_8bit_ADDR_VAL(uint16_t addr, uint8_t val)
{
    uintptr_t a = 0xFFFF0000u | addr;
    *(volatile uint8_t *)(uintptr_t)a       = val;
    *(volatile uint8_t *)(uintptr_t)(a + 1) = (uint8_t)~val;
}

/* 0x2478 — saturating unsigned 8-bit add, min(a + b, 255). */
uint8_t addSaturate8Bit(uint8_t a, uint8_t b)
{
    unsigned sum = (unsigned)a + (unsigned)b;
    return sum >= 255u ? (uint8_t)255u : (uint8_t)sum;
}

/* 0x18552 — stepper waveform driver.  C port of the model in
 * c/tests/test_omp_stepper_waveform_driver.py (verified vs the real ROM
 * bytes).  Effect: A97C/A97D/A97F/A98A/A98D + the u16 F746 port drive.
 *
 * Two byte-exactness fixes over the original inline model (both mirror the
 * standalone src/rx8_omp_stepper_waveform_driver.c):
 *   1. A97C WRITE-BACK: the ROM does `mov.b r0,@r14` (r14 = 0xFFFFA97C) in
 *      EVERY non-default mode (0x1861A, 0x18652/0x1865A, 0x186DC/0x186E6,
 *      0x18792/0x1872E/0x18752, 0x18770/0x18780/0x1878E, 0x18792), so the
 *      new step is stored back to RAM[0xFFFFA97C] per mode branch, exactly
 *      where the real ROM stores it (the default path 5/7..255 writes
 *      nothing).
 *   2. F746 BYTE ORDER: the u16 stepper port lives big-endian in the SH-2
 *      emulator (F746 = hi byte, F746+1 = lo byte).  The original model
 *      read/wrote it as a host u16, which stores the bytes little-endian on
 *      this host (e.g. 0x0003 -> bytes 03 00 vs the emulator's 00 03); the
 *      harness compares the two bytes separately (OUT indices 33/34), so the
 *      read and write here are done byte-wise big-endian.
 *   3. STEP-PATTERN CLAMP: a step >= 9 (reachable only via the mode-4 A97D
 *      source, which preserves an arbitrary pre-state) reads past the 9-step
 *      table into the emulator's never-written stack frame — 0x00, so every
 *      phase clears its bit (same clamp as the standalone driver). */
void omp_stepper_waveform_driver(uint8_t mode)
{
    uint8_t step = *(volatile uint8_t *)(uintptr_t)A97C;
    uint8_t a97d = *(volatile uint8_t *)(uintptr_t)A97D;
    uint8_t a974 = *(volatile uint8_t *)(uintptr_t)A974;
    uint8_t a98a = *(volatile uint8_t *)(uintptr_t)A98A;
    int      wf_ok = 0;
    uint8_t  wf = 0;

    *(volatile uint8_t *)(uintptr_t)A98D = mode;   /* latched at entry */

    switch (mode) {
    case 0:
        step = (uint8_t)((step + 1) & 7);
        *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x1861A */
        if ((step & 1) == 0 && a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 1:
        if (step == 8) {
            step = (uint8_t)((a97d + 0xFF) & 7);
            *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x18652 */
        } else {
            step = (uint8_t)((step + 0xFF) & 7);
            *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x1865A */
            if (a974 == 1 && a98a != 4 &&
                (*(volatile uint8_t *)(uintptr_t)A969 == 1 ||
                 *(volatile uint8_t *)(uintptr_t)A96A == 1)) {
                wf_ok = 1;
                wf = 0;
            }
        }
        if ((step & 1) == 0 && a98a != 4 && a974 > 0) {
            wf_ok = 1;
            wf = (uint8_t)(0xFF + a974);
        }
        break;
    case 2:
        if (a98a == 4 || (step & 1) == 1) {
            step = (step == 8) ? (uint8_t)((a97d + 1) & 7)
                               : (uint8_t)((step + 1) & 7);
        } else {
            step = (uint8_t)((step + 2) & 7);
        }
        *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x186DC / 0x186E6 */
        if (a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 3:
        if (a98a == 4 || (step & 1) == 1) {
            if (step == 8) {
                step = (uint8_t)((a97d + 0xFF) & 7);
                *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x18792 */
            } else {
                step = (uint8_t)((step + 0xFF) & 7);
                *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x1872E */
                if (a974 == 1 && a98a != 4) {
                    wf_ok = 1;
                    wf = 0;
                }
            }
        } else {
            step = (uint8_t)((step + 0xFE) & 7);
            *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x18752 */
            if (a974 > 0) {
                wf_ok = 1;
                wf = (uint8_t)(0xFF + a974);
            }
        }
        break;
    case 4:
        if (step == 8) {
            step = a97d;
            *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x18770 */
        } else if ((step & 1) == 0) {
            step = (uint8_t)((step + 1) & 7);
            *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x18780 */
            *(volatile uint8_t *)(uintptr_t)A97D = step;
        } else {
            step = 8;
            *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x1878E */
        }
        break;
    case 6:
        step = 8;
        *(volatile uint8_t *)(uintptr_t)A97C = step;   /* 0x18792 */
        break;
    default:
        break;                       /* modes 5, 7..255: step unchanged */
    }

    *(volatile uint8_t *)(uintptr_t)A98A = mode;
    if (wf_ok)
        *(volatile uint8_t *)(uintptr_t)A97F = wf;

    /* 4-phase port drive: pattern byte == 1 -> set bit, else clear.  The
     * u16 port is assembled/read big-endian (F746 = hi byte, F746+1 = lo
     * byte) to match the SH-2 emulator; a step >= 9 clears all four bits
     * exactly like the emulator's out-of-table 0x00 reads. */
    {
        uint16_t port =
            (uint16_t)((uint16_t)(*(volatile uint8_t *)(uintptr_t)F746) << 8) |
            (uint16_t)(*(volatile uint8_t *)(uintptr_t)(F746 + 1));
        int i;
        for (i = 0; i < 4; i++) {
            uint8_t phase = (step <= 8) ? STEP_PATTERN[step][i] : 0;
            if (phase == 1)
                port |= (uint16_t)(1u << i);
            else
                port &= (uint16_t)~(1u << i);
        }
        *(volatile uint8_t *)(uintptr_t)F746       = (uint8_t)(port >> 8);
        *(volatile uint8_t *)(uintptr_t)(F746 + 1) = (uint8_t)(port & 0xFF);
    }
}

/* 0x18860 — waveform state-machine stage.  C port of the model in
 * c/tests/test_omp_waveform_state_machine_18860.py, except that the two
 * ADDRESS_VAL port reads go through readValue_8bit_ADDRESS_VAL above (the
 * Python task-level test pre-computed the C6AC effect separately; here the
 * fault flag is raised exactly like the real ROM bytes). */
void omp_waveform_state_machine_18860(uint8_t mode)
{
    if (mode == 0) {                 /* state reset */
        *(volatile uint8_t *)(uintptr_t)A981 = 0;
        *(volatile uint8_t *)(uintptr_t)A982 = 0;
    }

    if (*(volatile uint8_t *)(uintptr_t)A981 == 1) {
        uint8_t r9 = 0, r14 = 0;
        if (*(volatile uint8_t *)(uintptr_t)A968 == 1) {
            if ((uint8_t)readValue_8bit_ADDRESS_VAL(0x8078, 0) != 0) {
                if ((uint8_t)readValue_8bit_ADDRESS_VAL(0x807C, 0) == 1) {
                    if (*(const float *)(uintptr_t)ROM_CAL_T >
                        *(volatile float *)(uintptr_t)AA10)   /* fcmp/gt */
                        r14 = 1;        /* temp < -40.0 -> cal A */
                    else
                        r9 = 1;         /* temp >= -40.0 -> cal B */
                } else
                    r14 = 1;
            } else
                r14 = 1;
            *(volatile uint8_t *)(uintptr_t)A97E =
                (r9 == 1) ? *(const uint8_t *)(uintptr_t)ROM_CAL_B
                          : *(const uint8_t *)(uintptr_t)ROM_CAL_A;
        }
        *(volatile uint8_t *)(uintptr_t)A977 = r9;
        *(volatile uint8_t *)(uintptr_t)A978 = r14;
        *(volatile uint8_t *)(uintptr_t)A981 = 2;
    }

    if (*(volatile uint8_t *)(uintptr_t)A981 == 0) {
        switch (*(volatile uint8_t *)(uintptr_t)A97C) {
        case 5:
            *(volatile uint8_t *)(uintptr_t)A97B = 0x80;
            *(volatile uint8_t *)(uintptr_t)A981 = 1;
            break;
        case 4:
            *(volatile uint8_t *)(uintptr_t)A97B = 0x30;
            omp_stepper_waveform_driver(0);
            if (*(volatile uint8_t *)(uintptr_t)A974 < 60)
                *(volatile uint8_t *)(uintptr_t)A97F =
                    (uint8_t)(*(volatile uint8_t *)(uintptr_t)A974 + 1);
            break;
        default:
            *(volatile uint8_t *)(uintptr_t)A97B = 0x10;
            omp_stepper_waveform_driver(2);
            break;
        }
    }

    if (*(volatile uint8_t *)(uintptr_t)A981 == 2) {
        if (*(volatile uint8_t *)(uintptr_t)A977 == 1 ||
            *(volatile uint8_t *)(uintptr_t)A978 == 1) {
            if ((*(volatile uint8_t *)(uintptr_t)A97C & 1) == 0) {
                *(volatile uint8_t *)(uintptr_t)A97B = 0x30;
                omp_stepper_waveform_driver(1);
                if (*(volatile uint8_t *)(uintptr_t)A97C == 5 &&
                    *(volatile uint8_t *)(uintptr_t)A97E <= 1) {
                    *(volatile uint8_t *)(uintptr_t)A982 = 1;
                    *(volatile uint8_t *)(uintptr_t)A97F = 0;
                    *(volatile uint8_t *)(uintptr_t)A97E = 0;
                    *(volatile uint8_t *)(uintptr_t)A97B =
                        addSaturate8Bit(
                            *(volatile uint8_t *)(uintptr_t)A97B, 0x30);
                }
            } else {
                *(volatile uint8_t *)(uintptr_t)A97B = 8;
                omp_stepper_waveform_driver(1);
                if (*(volatile uint8_t *)(uintptr_t)A97E > 0)
                    *(volatile uint8_t *)(uintptr_t)A97E =
                        (uint8_t)(*(volatile uint8_t *)(uintptr_t)A97E - 1);
            }
        }
    }
}

/* 0x189EE — rotor-sync position detector.  C port of the model in
 * c/tests/test_rotor_sync_position_detector.py (verified vs the real ROM
 * bytes); identical to the lift c/rotor_sync_position_detector.c. */
void rotor_sync_position_detector(uint8_t mode)
{
    int a8f1 = *(volatile uint8_t *)(uintptr_t)A8F1;
    int a974 = *(volatile uint8_t *)(uintptr_t)A974;
    int odd = *(volatile uint8_t *)(uintptr_t)A97C & 1;
    int flag = 0;
    uint8_t state = *(volatile uint8_t *)(uintptr_t)A98B;

    /* stage A: mode == 0 position compare */
    if (mode == 0) {
        if (a8f1 > a974) {
            state = 0;
        } else if (a8f1 == a974) {
            state = 2;
            flag = 1;
        } else {
            state = 1;
        }
        *(volatile uint8_t *)(uintptr_t)A98B = state;
    }

    /* stage B: state blocks */
    switch (state) {
    case 0:
        if (a8f1 >= a974) {
            if (a8f1 == a974 && !odd) {
                *(volatile uint8_t *)(uintptr_t)A98B = 2;
                flag = 1;
            }
        } else {
            if (!odd)
                *(volatile uint8_t *)(uintptr_t)A98B = 3;
        }
        break;
    case 1:
        if (a8f1 > a974) {
            if (!odd || a974 == 0)
                *(volatile uint8_t *)(uintptr_t)A98B = 3;
        } else if (a8f1 == a974) {
            if (!odd || a974 == 0) {
                if (a974 >= 5)
                    *(volatile uint8_t *)(uintptr_t)A98B = 4;
                else {
                    *(volatile uint8_t *)(uintptr_t)A98B = 2;
                    flag = 1;
                }
            }
        }
        break;
    case 2:
        if (a8f1 > a974)
            *(volatile uint8_t *)(uintptr_t)A98B = 0;
        else if (a8f1 < a974)
            *(volatile uint8_t *)(uintptr_t)A98B = 1;
        break;
    case 3:
        if (a8f1 > a974)
            *(volatile uint8_t *)(uintptr_t)A98B = 0;
        else if (a8f1 < a974)
            *(volatile uint8_t *)(uintptr_t)A98B = 1;
        else {
            *(volatile uint8_t *)(uintptr_t)A98B = 2;
            flag = 1;
        }
        break;
    case 4:
        if (!odd) {
            if ((int8_t)(a8f1 - 2) >= a974)   /* add #0xFE sign-extends */
                *(volatile uint8_t *)(uintptr_t)A98B = 3;
            if (a8f1 < 5) {
                *(volatile uint8_t *)(uintptr_t)A98B = 2;
                flag = 1;
            }
        }
        break;
    default:
        break;                       /* states 5..255: no action */
    }

    /* stage C: tail dispatch on the final state */
    state = *(volatile uint8_t *)(uintptr_t)A98B;
    a974 = *(volatile uint8_t *)(uintptr_t)A974;
    switch (state) {
    case 0:
        omp_stepper_waveform_driver(2);
        *(volatile uint8_t *)(uintptr_t)A97B = 0x10;
        break;
    case 1:
        if (a974 >= 5) {
            omp_stepper_waveform_driver(3);
            *(volatile uint8_t *)(uintptr_t)A97B = 0x10;
        } else {
            omp_stepper_waveform_driver(1);
            *(volatile uint8_t *)(uintptr_t)A97B = (odd ? 8 : 0x30);
        }
        break;
    case 2:
        if (flag && a974 == 0) {
            *(volatile uint8_t *)(uintptr_t)A97D =
                *(volatile uint8_t *)(uintptr_t)A97C;
        } else {
            omp_stepper_waveform_driver(4);
        }
        *(volatile uint8_t *)(uintptr_t)A97B = 4;
        break;
    case 3:
        *(volatile uint8_t *)(uintptr_t)A97B = 0x30;
        break;
    case 4:
        if (a974 >= 5) {
            omp_stepper_waveform_driver(3);
            *(volatile uint8_t *)(uintptr_t)A97B = 0x10;
        } else {
            omp_stepper_waveform_driver(1);
            *(volatile uint8_t *)(uintptr_t)A97B = (odd ? 8 : 0x30);
        }
        break;
    default:
        break;
    }
}

int main(void)
{
    char line[4096];

    map_page(ROM_CAL_PAGE);
    map_page(0xFFFF8000u);
    map_page(0xFFFF9000u);
    map_page(0xFFFFA000u);
    map_page(0xFFFFB000u);
    map_page(0xFFFFC000u);
    map_page(0xFFFFF000u);

    while (fgets(line, sizeof line, stdin)) {
        /* 72 tokens: 6 cal + 50 A9xx bytes + 16 (a8f1 c6ac ecd cd06 ports
         * f746 temp).  Parsed with strtok_r — a 72-arg sscanf would be
         * unreadable. */
        char *save = NULL;
        unsigned long cal35, cal36, cal37, cala, calb, calt;
        unsigned long a[50];
        unsigned long a8f1, c6ac0, ecd, cd06;
        unsigned long p78h, p78l, p7ah, p7al, p7ch, p7cl;
        unsigned long f746h, f746l, t0, t1, t2, t3;
        int i;

#define NXT() strtoul(strtok_r(NULL, " \t\n", &save), NULL, 16)

        if (strtok_r(line, " \t\n", &save) == NULL ||
            strcmp(line, "omp") != 0) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        cal35 = NXT(); cal36 = NXT(); cal37 = NXT();
        cala  = NXT(); calb  = NXT(); calt  = NXT();
        for (i = 0; i < 50; i++)
            a[i] = NXT();
        a8f1 = NXT(); c6ac0 = NXT(); ecd = NXT(); cd06 = NXT();
        p78h = NXT(); p78l = NXT();
        p7ah = NXT(); p7al = NXT();
        p7ch = NXT(); p7cl = NXT();
        f746h = NXT(); f746l = NXT();
        t0 = NXT(); t1 = NXT(); t2 = NXT(); t3 = NXT();

        /* Seed the ROM calibration page (stock bytes shipped by the harness;
         * verified there to equal the actual ROM contents). */
        *(volatile uint8_t *)(uintptr_t)ROM_CAL35 = (uint8_t)cal35;
        *(volatile uint8_t *)(uintptr_t)ROM_CAL36 = (uint8_t)cal36;
        *(volatile uint8_t *)(uintptr_t)ROM_CAL37 = (uint8_t)cal37;
        *(volatile uint8_t *)(uintptr_t)ROM_CAL_A  = (uint8_t)cala;
        *(volatile uint8_t *)(uintptr_t)ROM_CAL_B  = (uint8_t)calb;
        *(volatile float *)(uintptr_t)ROM_CAL_T    =
            be32_to_hostf((uint32_t)calt);

        /* Seed the A9xx RAM block + the loose cells. */
        for (i = 0; i < 50; i++)
            *(volatile uint8_t *)(uintptr_t)(A968 + i) = (uint8_t)a[i];
        *(volatile uint8_t *)(uintptr_t)A8F1 = (uint8_t)a8f1;
        *(volatile uint8_t *)(uintptr_t)C6AC = (uint8_t)c6ac0;
        *(volatile uint8_t *)(uintptr_t)ECD  = (uint8_t)ecd;
        *(volatile uint8_t *)(uintptr_t)CD06 = (uint8_t)cd06;
        *(volatile uint8_t *)(uintptr_t)B5F3 = 0;   /* reset per vector; see
                                                    * header — B5F3 is
                                                    * write-only from the task
                                                    * and the emulator starts
                                                    * it at 0 every call */
        *(volatile uint8_t *)(uintptr_t)P78      = (uint8_t)p78h;
        *(volatile uint8_t *)(uintptr_t)(P78 + 1)  = (uint8_t)p78l;
        *(volatile uint8_t *)(uintptr_t)P7A      = (uint8_t)p7ah;
        *(volatile uint8_t *)(uintptr_t)(P7A + 1)  = (uint8_t)p7al;
        *(volatile uint8_t *)(uintptr_t)P7C      = (uint8_t)p7ch;
        *(volatile uint8_t *)(uintptr_t)(P7C + 1)  = (uint8_t)p7cl;
        *(volatile uint8_t *)(uintptr_t)F746      = (uint8_t)f746h;
        *(volatile uint8_t *)(uintptr_t)(F746 + 1) = (uint8_t)f746l;
        *(volatile float *)(uintptr_t)AA10 =
            be32_to_hostf(((uint32_t)t0 << 24) | ((uint32_t)t1 << 16)
                          | ((uint32_t)t2 << 8) | (uint32_t)t3);

        rx8_omp_task_0x1825E();

        for (i = 0; i < NOUT; i++) {
            printf("%02X%s", *(volatile uint8_t *)(uintptr_t)OUT[i],
                   (i + 1 < NOUT) ? " " : "\n");
        }
    }
    return 0;
}
