/* ============================================================================
 * oracle_omp_waveform_state_machine_18860.c  —  host rig for
 *     rx8_omp_waveform_state_machine_18860 @0x18860
 * ============================================================================
 * Compile together with samples/src/rx8_omp_waveform_state_machine_18860.c
 * and pipe test vectors on stdin; one vector per line, whitespace-separated
 * hex tokens:
 *
 *     ompw <mode> <a981> <a982> <a97e> <a97b> <a97f> <a977> <a978> <a968>
 *          <a97c> <a97d> <a974> <a98a> <a98d> <a969> <a96a> <f746>
 *          <p78> <p79> <p7c> <p7d> <aa10> <c6ac>
 *                                       -> <a981> <a982> <a97e> <a97b> <a97f>
 *                                          <a977> <a978> <a97c> <a97d> <a98a>
 *                                          <a98d> <f746> <c6ac>
 *
 *   mode  : r4 argument (ROM `extu.b`-masked to 8 bits)
 *   a981  : RAM8[0xFFFFA981] state byte
 *   a982  : RAM8[0xFFFFA982] latch flag
 *   a97e  : RAM8[0xFFFFA97E] cal byte / countdown
 *   a97b  : RAM8[0xFFFFA97B] stepper command byte
 *   a97f  : RAM8[0xFFFFA97F] waveform byte
 *   a977  : RAM8[0xFFFFA977] cal-B flag
 *   a978  : RAM8[0xFFFFA978] cal-A flag
 *   a968  : RAM8[0xFFFFA968] gate flag
 *   a97c  : RAM8[0xFFFFA97C] step register
 *   a97d  : RAM8[0xFFFFA97D] rotor-sync step source (wave driver input)
 *   a974  : RAM8[0xFFFFA974] rotor position
 *   a98a  : RAM8[0xFFFFA98A] previously latched mode (wave driver input)
 *   a98d  : RAM8[0xFFFFA98D] wave-mode latch (wave driver output)
 *   a969  : RAM8[0xFFFFA969] gate flag A (wave driver input)
 *   a96a  : RAM8[0xFFFFA96A] gate flag B (wave driver input)
 *   f746  : RAM16[0xFFFFF746] stepper drive port (wave driver RMW)
 *   p78/p79 : complementary port pair RAM[0xFFFF8078/79] (0x3ED3C)
 *   p7c/p7d : complementary port pair RAM[0xFFFF807C/7D] (0x3ED3C)
 *   aa10  : raw IEEE-754 single-precision bits of RAM32[0xFFFFAA10] (temp)
 *   c6ac  : RAM8[0xFFFFC6AC] ADDRESS_VAL fault flag pre-state
 *
 * The 13 printed bytes are the whole RAM side-effect set of the function
 * (A981/A982/A97E/A97B/A97F/A977/A978 always (re)written on their paths,
 * A97C/A97D/A98A/A98D/F746 via the wave driver leaf, C6AC raised by the
 * 0x3ED3C port-accessor leaf on a broken complementary pair).
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the ROM calibration page, seeds every byte and
 * prints the post-state bytes.  It contains NO copy of the 0x18860 logic —
 * that lives solely in the reconstructed source under test.  The three ROM
 * leaves the function jsr's / bsr's (0x3ED3C readValue_8bit_ADDRESS_VAL,
 * 0x18552 omp_stepper_waveform_driver, 0x2478 addSaturate8Bit) ARE modelled
 * here, since the sample declares them extern exactly like the lift does
 * (c/omp_waveform_state_machine_18860.c) and the emulator runs the real bytes.
 *
 * The f32 calibration threshold @0x78E68 is stored in the ROM file as
 * big-endian bytes; the file is big-endian and the host is little-endian, so
 * it is byte-assembled to a numeric value before being stored at the mapped
 * address — a raw pointer read would byte-swap it.  The value is validated by
 * the harness against the ROM.  $RX8_ROM_PATH (set by the harness) points at
 * roms/stock/60E1D400.bin.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00078000  ROM calibration page (0x78E33/0x78E34 cal bytes, f32 @0x78E68)
 *   0xFFFF8000  RAM[0xFFFF8078/79, 0xFFFF807C/7D] port pairs
 *   0xFFFFA000  RAM[0xFFFFA968..A98D] OMP cells + f32 @0xFFFFAA10
 *   0xFFFFC000  RAM[0xFFFFC6AC] ADDRESS_VAL fault flag
 *   0xFFFFF000  RAM[0xFFFFF746] stepper drive port (u16)
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_omp_waveform_state_machine_18860 is not (yet) in rx8_samples.h — the
 * shared header is owned by the samples build.  The reconstructed source
 * itself carries the authoritative definition (src/rx8_omp_waveform_state_machine_18860.c);
 * this prototype mirrors it exactly. */
void rx8_omp_waveform_state_machine_18860(uint8_t mode);

#define A981   0xFFFFA981u   /* 4-state machine state         */
#define A982   0xFFFFA982u   /* wave-latch flag               */
#define A97E   0xFFFFA97Eu   /* cal byte / countdown          */
#define A97B   0xFFFFA97Bu   /* stepper command byte          */
#define A97F   0xFFFFA97Fu   /* waveform byte                 */
#define A977   0xFFFFA977u   /* cal-B flag                    */
#define A978   0xFFFFA978u   /* cal-A flag                    */
#define A968   0xFFFFA968u   /* gate flag                     */
#define A97C   0xFFFFA97Cu   /* step register                 */
#define A97D   0xFFFFA97Du   /* rotor-sync step source        */
#define A974   0xFFFFA974u   /* rotor position                */
#define A98A   0xFFFFA98Au   /* previously latched mode       */
#define A98D   0xFFFFA98Du   /* wave-mode latch               */
#define A969   0xFFFFA969u   /* gate flag A                   */
#define A96A   0xFFFFA96Au   /* gate flag B                   */
#define F746   0xFFFFF746u   /* stepper drive port (u16)      */
#define P78    0xFFFF8078u   /* port pair A byte 0            */
#define P7C    0xFFFF807Cu   /* port pair C byte 0            */
#define AA10   0xFFFFAA10u   /* coolant temp (f32)            */
#define C6AC   0xFFFFC6ACu   /* ADDRESS_VAL fault flag        */

#define ROM_CAL_PAGE  0x00078000u   /* page holding 0x78E33/34/68 */

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

/* 0x3ED3C leaf model (c/omp_waveform_state_machine_18860.c header + the
 * discrepancy note in rx8_omp_waveform_state_machine_18860.c):
 * RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(default), with C6AC fault flag set
 * on mismatch.  The address arrives as a u16 (0x8078/0x807C) and lives in the
 * on-chip window at 0xFFFFxxxx, exactly as the ROM's sign-extended mov.w
 * literal. */
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

/* 0x2478 leaf model: saturating unsigned 8-bit add, min(a + b, 255). */
uint8_t addSaturate8Bit(uint8_t a, uint8_t b)
{
    unsigned sum = (unsigned)a + (unsigned)b;
    return sum >= 255u ? (uint8_t)255u : (uint8_t)sum;
}

/* 0x18552 omp_stepper_waveform_driver model — faithful port of the verified
 * lift c/omp_stepper_waveform_driver.c (itself checked against the ROM by
 * c/tests/test_omp_stepper_waveform_driver.py over 60000 inputs).  Modes 0, 1
 * and 2 are the ones the state machine drives; the full dispatch is kept for
 * fidelity.  Reads A97C/A97D/A974/A98A/A969/A96A at entry, writes A98D at
 * entry, then A97C (new step) + A98A / (A97F iff wf_ok) at the tail, and
 * finally RMWs the four pattern bits onto RAM16[0xFFFFF746] (0x4BBC 16-bit
 * RMW, one per phase). */
void omp_stepper_waveform_driver(uint8_t mode)
{
    static const uint8_t pat[9][4] = {
        {1, 0, 0, 1}, {1, 0, 0, 0}, {1, 1, 0, 0}, {0, 1, 0, 0}, {0, 1, 1, 0},
        {0, 0, 1, 0}, {0, 0, 1, 1}, {0, 0, 0, 1}, {0, 0, 0, 0},
    };
    uint8_t step = *(volatile uint8_t *)(uintptr_t)A97C;
    uint8_t a97d = *(volatile uint8_t *)(uintptr_t)A97D;
    uint8_t a974 = *(volatile uint8_t *)(uintptr_t)A974;
    uint8_t a98a = *(volatile uint8_t *)(uintptr_t)A98A;
    uint8_t a969 = *(volatile uint8_t *)(uintptr_t)A969;
    uint8_t a96a = *(volatile uint8_t *)(uintptr_t)A96A;
    int wf_ok = 0;
    uint8_t wf = 0;
    int i;

    *(volatile uint8_t *)(uintptr_t)A98D = mode;    /* latched at entry */

    switch (mode) {
    case 0:
        step = (uint8_t)((step + 1) & 7);
        if ((step & 1) == 0 && a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 1:
        if (step == 8) {
            step = (uint8_t)((a97d + 0xFF) & 7);
        } else {
            step = (uint8_t)((step + 0xFF) & 7);
            if (a974 == 1 && a98a != 4 && (a969 == 1 || a96a == 1)) {
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
        if (a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 3:
        if (a98a == 4 || (step & 1) == 1) {
            if (step == 8) {
                step = (uint8_t)((a97d + 0xFF) & 7);
            } else {
                step = (uint8_t)((step + 0xFF) & 7);
                if (a974 == 1 && a98a != 4) {
                    wf_ok = 1;
                    wf = 0;
                }
            }
        } else {
            step = (uint8_t)((step + 0xFE) & 7);
            if (a974 > 0) {
                wf_ok = 1;
                wf = (uint8_t)(0xFF + a974);
            }
        }
        break;
    case 4:
        if (step == 8) {
            step = a97d;
        } else if ((step & 1) == 0) {
            step = (uint8_t)((step + 1) & 7);
            *(volatile uint8_t *)(uintptr_t)A97D = step;
        } else {
            step = 8;
        }
        break;
    case 6:
        step = 8;
        break;
    default:                                /* modes 5, 7..255 */
        break;
    }

    *(volatile uint8_t *)(uintptr_t)A97C = step;
    *(volatile uint8_t *)(uintptr_t)A98A = mode;
    if (wf_ok)
        *(volatile uint8_t *)(uintptr_t)A97F = wf;

    /* 4-phase port drive: bit (1<<i) set iff pattern[step][i] == 1, else
     * cleared — a 16-bit RMW per phase, exactly the 0x4BBC calls of the ROM. */
    {
        uint16_t port = *(volatile uint16_t *)(uintptr_t)F746;
        for (i = 0; i < 4; i++) {
            if (pat[step & 0x0Fu][i] == 1)
                port = (uint16_t)(port | (uint16_t)(1u << i));
            else
                port = (uint16_t)(port & (uint16_t)~(1u << i));
        }
        *(volatile uint16_t *)(uintptr_t)F746 = port;
    }
}

/* Seed the ROM calibration page with the actual stock-60E1D400.bin constants.
 * The file is big-endian, so the f32 is assembled by hand and stored as a
 * host-endian numeric value; the reconstructed source then reads it back
 * through the very same (mapped) virtual address the ROM fetches. */
static void seed_rom_cal(int fd)
{
    unsigned char b[4];
    uint32_t bits;
    float v;

    if (pread(fd, b, 1, 0x78E33) != 1) { perror("pread 0x78E33"); exit(2); }
    *(volatile uint8_t *)(uintptr_t)0x78E33u = b[0];
    if (pread(fd, b, 1, 0x78E34) != 1) { perror("pread 0x78E34"); exit(2); }
    *(volatile uint8_t *)(uintptr_t)0x78E34u = b[0];
    if (pread(fd, b, 4, 0x78E68) != 4) { perror("pread 0x78E68"); exit(2); }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)0x78E68u = v;
}

int main(void)
{
    const char *rom_path = getenv("RX8_ROM_PATH");
    char line[512];
    int romfd;

    if (!rom_path)
        rom_path = "../../../roms/stock/60E1D400.bin";
    romfd = open(rom_path, O_RDONLY);
    if (romfd < 0) {
        perror(rom_path);
        return 2;
    }

    map_page(ROM_CAL_PAGE);
    seed_rom_cal(romfd);
    map_page(0xFFFF8000u);
    map_page(0xFFFFA000u);
    map_page(0xFFFFC000u);
    map_page(0xFFFFF000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long mode;
        unsigned long a981, a982, a97e, a97b, a97f, a977, a978, a968;
        unsigned long a97c, a97d, a974, a98a, a98d, a969, a96a;
        unsigned long f746, p78, p79, p7c, p7d, aa10, c6ac;

        if (sscanf(line,
                   "ompw %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &mode,
                   &a981, &a982, &a97e, &a97b, &a97f, &a977, &a978, &a968,
                   &a97c, &a97d, &a974, &a98a, &a98d, &a969, &a96a,
                   &f746, &p78, &p79, &p7c, &p7d, &aa10, &c6ac)
            != 23) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the input RAM cells + pre-states. */
        *(volatile uint8_t *)(uintptr_t)A981  = (uint8_t)a981;
        *(volatile uint8_t *)(uintptr_t)A982  = (uint8_t)a982;
        *(volatile uint8_t *)(uintptr_t)A97E  = (uint8_t)a97e;
        *(volatile uint8_t *)(uintptr_t)A97B  = (uint8_t)a97b;
        *(volatile uint8_t *)(uintptr_t)A97F  = (uint8_t)a97f;
        *(volatile uint8_t *)(uintptr_t)A977  = (uint8_t)a977;
        *(volatile uint8_t *)(uintptr_t)A978  = (uint8_t)a978;
        *(volatile uint8_t *)(uintptr_t)A968  = (uint8_t)a968;
        *(volatile uint8_t *)(uintptr_t)A97C  = (uint8_t)a97c;
        *(volatile uint8_t *)(uintptr_t)A97D  = (uint8_t)a97d;
        *(volatile uint8_t *)(uintptr_t)A974  = (uint8_t)a974;
        *(volatile uint8_t *)(uintptr_t)A98A  = (uint8_t)a98a;
        *(volatile uint8_t *)(uintptr_t)A98D  = (uint8_t)a98d;
        *(volatile uint8_t *)(uintptr_t)A969  = (uint8_t)a969;
        *(volatile uint8_t *)(uintptr_t)A96A  = (uint8_t)a96a;
        *(volatile uint16_t *)(uintptr_t)F746 = (uint16_t)f746;
        *(volatile uint8_t *)(uintptr_t)P78         = (uint8_t)p78;
        *(volatile uint8_t *)(uintptr_t)(P78 + 1)   = (uint8_t)p79;
        *(volatile uint8_t *)(uintptr_t)P7C         = (uint8_t)p7c;
        *(volatile uint8_t *)(uintptr_t)(P7C + 1)   = (uint8_t)p7d;
        *(volatile uint32_t *)(uintptr_t)AA10       = (uint32_t)aa10;
        *(volatile uint8_t *)(uintptr_t)C6AC        = (uint8_t)c6ac;

        rx8_omp_waveform_state_machine_18860((uint8_t)mode);

        printf("%02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %04X %02X\n",
               *(volatile uint8_t *)(uintptr_t)A981,
               *(volatile uint8_t *)(uintptr_t)A982,
               *(volatile uint8_t *)(uintptr_t)A97E,
               *(volatile uint8_t *)(uintptr_t)A97B,
               *(volatile uint8_t *)(uintptr_t)A97F,
               *(volatile uint8_t *)(uintptr_t)A977,
               *(volatile uint8_t *)(uintptr_t)A978,
               *(volatile uint8_t *)(uintptr_t)A97C,
               *(volatile uint8_t *)(uintptr_t)A97D,
               *(volatile uint8_t *)(uintptr_t)A98A,
               *(volatile uint8_t *)(uintptr_t)A98D,
               *(volatile uint16_t *)(uintptr_t)F746,
               *(volatile uint8_t *)(uintptr_t)C6AC);
    }
    return 0;
}
