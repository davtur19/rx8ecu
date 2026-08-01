/* ============================================================================
 * oracle_omp_rotor_overshoot_detector.c  —  host rig for rx8_omp_rotor_overshoot_detector
 * ============================================================================
 * Compile together with samples/src/rx8_omp_rotor_overshoot_detector.c and
 * pipe test vectors on stdin; one vector per line, whitespace-separated hex
 * tokens:
 *
 *     omp <cal38> <cal39> <cal3a> <a969> <a975> <a976> <a974> <a990> <a991>
 *         <a992> <a993> <a994> <a995> <p7a> <p7b> <c6ac>
 *                                             -> <a990> <a991> <a992> <a993>
 *                                                <a994> <a995> <c6ac>
 *
 *   cal38/cal39/cal3a : the 3 calibration bytes the ROM reads at 0x78E38..0x78E3A
 *   a969/a975/a976    : gate / fault inputs (RAM[0xFFFFA969/75/76])
 *   a974              : position target (RAM[0xFFFFA974], captured at entry)
 *   a990/a991         : latch-flag pre-states (RAM[0xFFFFA990/91])
 *   a992/a993         : trigger-flag pre-states (RAM[0xFFFFA992/93])
 *   a994/a995         : debounce-counter pre-states (RAM[0xFFFFA994/95])
 *   p7a/p7b           : idle/off port complementary pair (RAM[0xFFFF807A/7B])
 *   c6ac              : ADDRESS_VAL fault-flag pre-state (RAM[0xFFFFC6AC])
 *
 * The 7 printed bytes are the whole RAM side-effect set of the function
 * (A990/A991/A992/A993/A994/A995 always (re)written or latched, C6AC raised
 * by the 0x3ED3C port-accessor leaf on a broken pair).
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the ROM calibration table, seeds every byte and
 * prints the post-state bytes.  It contains NO copy of the 0x18CC0 logic —
 * that lives solely in the reconstructed source under test.  The two ROM
 * leaves the function jsr's (0x3ED3C readValue_8bit_ADDRESS_VAL, 0x2478
 * addSaturate8Bit) ARE modelled here, since the sample declares them extern
 * exactly like the lift does (c/omp_rotor_overshoot_detector_18CC0.c) and the
 * emulator runs the real bytes.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00078000  ROM calibration table (0x78E38..0x78E3A)
 *   0xFFFF8000  RAM[0xFFFF807A/7B] idle/off port pair
 *   0xFFFFA000  RAM[0xFFFFA969..A995] OMP cells
 *   0xFFFFC000  RAM[0xFFFFC6AC] ADDRESS_VAL fault flag
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_omp_rotor_overshoot_detector is not (yet) in rx8_samples.h — the shared
 * header is owned by the samples build.  The reconstructed source itself
 * carries the authoritative definition (src/rx8_omp_rotor_overshoot_detector.c);
 * this prototype mirrors it exactly. */
void rx8_omp_rotor_overshoot_detector(void);

#define A969   0xFFFFA969u   /* rotor-sync dispatch flag (gate)  */
#define A974   0xFFFFA974u   /* position target (captured entry) */
#define A975   0xFFFFA975u   /* OMP ramp value (gate)            */
#define A976   0xFFFFA976u   /* OMP fault-inoperative flag       */
#define A990   0xFFFFA990u   /* over-shoot latch                 */
#define A991   0xFFFFA991u   /* under-shoot latch                */
#define A992   0xFFFFA992u   /* over-shoot trigger               */
#define A993   0xFFFFA993u   /* under-shoot trigger              */
#define A994   0xFFFFA994u   /* over-shoot debounce counter      */
#define A995   0xFFFFA995u   /* under-shoot debounce counter     */
#define P7A    0xFFFF807Au   /* idle/off port byte 0             */
#define C6AC   0xFFFFC6ACu   /* ADDRESS_VAL fault flag           */

#define ROM_CAL_ADDR  0x00078E38u   /* 3 calibration bytes */
#define ROM_CAL_PAGE  0x00078000u   /* page backing them    */

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

/* 0x3ED3C leaf model (c/omp_rotor_overshoot_detector_18CC0.c header):
 * RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(default), C6AC fault flag set on
 * mismatch.  The address arrives as a u16 (0x807A) and lives in the on-chip
 * window at 0xFFFFxxxx, exactly as the ROM's sign-extended mov.w literal. */
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

int main(void)
{
    char line[256];

    map_page(ROM_CAL_PAGE);
    map_page(0xFFFF8000u);
    map_page(0xFFFFA000u);
    map_page(0xFFFFC000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long cal38, cal39, cal3a;
        unsigned long a969, a975, a976, a974;
        unsigned long a990, a991, a992, a993, a994, a995;
        unsigned long p7a, p7b, c6ac;
        int n = sscanf(line,
                       "omp %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                       &cal38, &cal39, &cal3a,
                       &a969, &a975, &a976, &a974,
                       &a990, &a991, &a992, &a993, &a994, &a995,
                       &p7a, &p7b, &c6ac);
        if (n != 16) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the ROM calibration table exactly as the stock bin has it. */
        *(volatile uint8_t *)(uintptr_t)(ROM_CAL_ADDR + 0) = (uint8_t)cal38;
        *(volatile uint8_t *)(uintptr_t)(ROM_CAL_ADDR + 1) = (uint8_t)cal39;
        *(volatile uint8_t *)(uintptr_t)(ROM_CAL_ADDR + 2) = (uint8_t)cal3a;

        /* Seed the input RAM cells + the flag/counter pre-states. */
        *(volatile uint8_t *)(uintptr_t)A969 = (uint8_t)a969;
        *(volatile uint8_t *)(uintptr_t)A975 = (uint8_t)a975;
        *(volatile uint8_t *)(uintptr_t)A976 = (uint8_t)a976;
        *(volatile uint8_t *)(uintptr_t)A974 = (uint8_t)a974;
        *(volatile uint8_t *)(uintptr_t)A990 = (uint8_t)a990;
        *(volatile uint8_t *)(uintptr_t)A991 = (uint8_t)a991;
        *(volatile uint8_t *)(uintptr_t)A992 = (uint8_t)a992;
        *(volatile uint8_t *)(uintptr_t)A993 = (uint8_t)a993;
        *(volatile uint8_t *)(uintptr_t)A994 = (uint8_t)a994;
        *(volatile uint8_t *)(uintptr_t)A995 = (uint8_t)a995;
        *(volatile uint8_t *)(uintptr_t)P7A        = (uint8_t)p7a;
        *(volatile uint8_t *)(uintptr_t)(P7A + 1)  = (uint8_t)p7b;
        *(volatile uint8_t *)(uintptr_t)C6AC       = (uint8_t)c6ac;

        rx8_omp_rotor_overshoot_detector();

        printf("%02X %02X %02X %02X %02X %02X %02X\n",
               *(volatile uint8_t *)(uintptr_t)A990,
               *(volatile uint8_t *)(uintptr_t)A991,
               *(volatile uint8_t *)(uintptr_t)A992,
               *(volatile uint8_t *)(uintptr_t)A993,
               *(volatile uint8_t *)(uintptr_t)A994,
               *(volatile uint8_t *)(uintptr_t)A995,
               *(volatile uint8_t *)(uintptr_t)C6AC);
    }
    return 0;
}
