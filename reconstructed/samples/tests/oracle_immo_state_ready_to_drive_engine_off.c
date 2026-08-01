/* ============================================================================
 * oracle_immo_state_ready_to_drive_engine_off.c  —  host test rig for
 *                        rx8_immo_state_ready_to_drive_engine_off @0x364D8
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     immo <c28e> <c282> <c278> <c27c> <c288> <c28a> <c293> <c291> <f754>
 *          <c240> <c241> <c284> <c28d> <c238> <c296> <c28f> <c299> <c294>
 *          <c29a> <c2dc> <c2e0> <adca> <adcb> <adcc> <adcm> <c6ac>
 *
 * 26 fields, each the initial big-endian value of one RAM cell (see the
 * LOCS table below for addresses/widths; the 8-byte cells c238/adcm are one
 * hex number of 16 digits).  Per vector the rig seeds those cells, calls
 * rx8_immo_state_ready_to_drive_engine_off(), then prints the 26 resulting
 * cells in the same order.  The oracle contains NO copy of the function
 * logic — that lives solely in src/rx8_immo_state_ready_to_drive_engine_off.c.
 * It only mirrors the *caller-side* set-up: the 0xFFFFC000 / 0xFFFFF000 /
 * 0xFFFF9000 / 0xFFFF8000 pages are backed with mmap(MAP_FIXED) (same trick
 * as tests/host_oracle.c), so the volatile fixed-address pointers in the
 * sample compile and fault-free on the host.  This is exactly what the ROM
 * does on the SH-2E, where all addresses are plain on-chip RAM.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

/* rx8_samples.h does not declare the function under test; declare the
 * prototype here (same approach as oracle_div32_signed.c). */
void rx8_immo_state_ready_to_drive_engine_off(void);

/* The 26 side-effected / observed cells, in vector order.
 * (name, address, width-in-bytes) */
static const uint32_t LOCS[26][2] = {
    {0xFFFFC28E, 1},   /* c28e  immo state byte               */
    {0xFFFFC282, 2},   /* c282  general countdown (IMMO_TIMER) */
    {0xFFFFC278, 4},   /* c278  rolling code / keygen out      */
    {0xFFFFC27C, 2},   /* c27c  500-tick timer                */
    {0xFFFFC288, 2},   /* c288  mixer word                    */
    {0xFFFFC28A, 2},   /* c28a  mixer word 2                  */
    {0xFFFFC293, 1},   /* c293  mixer counter                 */
    {0xFFFFC291, 1},   /* c291  substate                      */
    {0xFFFFF754, 2},   /* f754  lamp status word              */
    {0xFFFFC240, 1},   /* c240  CAN TX data flag              */
    {0xFFFFC241, 1},   /* c241  CAN TX request                */
    {0xFFFFC284, 2},   /* c284  bad-state timeout             */
    {0xFFFFC28D, 1},   /* c28d  state/result code             */
    {0xFFFFC238, 8},   /* c238  CAN TX buffer (8 bytes)       */
    {0xFFFFC296, 1},   /* c296  CAN TX status                 */
    {0xFFFFC28F, 1},   /* c28f  CAN TX state                  */
    {0xFFFFC299, 1},   /* c299  TX pending flag               */
    {0xFFFFC294, 1},   /* c294  response byte                 */
    {0xFFFFC29A, 1},   /* c29a  good-state flag               */
    {0xFFFFC2DC, 4},   /* c2dc  pairing word 1 (keygen fallback) */
    {0xFFFFC2E0, 4},   /* c2e0  pairing word 2                */
    {0xFFFF9F1C, 2},   /* 9f1c  adc_a (keygen input)          */
    {0xFFFF9F1E, 2},   /* 9f1e  adc_b (keygen input)          */
    {0xFFFF9F00, 2},   /* 9f00  adc_c (keygen input)          */
    {0xFFFF869C, 8},   /* 869c  adc_read checksummed block    */
    {0xFFFFC6AC, 1},   /* c6ac  adc_read checksum-fail flag   */
};
#define NCELLS (int)(sizeof(LOCS) / sizeof(LOCS[0]))

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

int main(void)
{
    char line[512];

    /* Back the pages holding the observed cells: 0xFFFFC000 (state cells +
     * CAN frame + 0xFFFFC6AC), 0xFFFFF000 (lamp), 0xFFFF9000 (adc_a/b/c) and
     * 0xFFFF8000 (adc_read checksum block). */
    map_page(0xFFFFC000u);
    map_page(0xFFFFF000u);
    map_page(0xFFFF9000u);
    map_page(0xFFFF8000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long v[NCELLS];
        int i;

        if (sscanf(line, "immo %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                         "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                         "%lx %lx",
                   &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7],
                   &v[8], &v[9], &v[10], &v[11], &v[12], &v[13], &v[14],
                   &v[15], &v[16], &v[17], &v[18], &v[19], &v[20], &v[21],
                   &v[22], &v[23], &v[24], &v[25]) != NCELLS) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the 26 cells as big-endian bytes. */
        for (i = 0; i < NCELLS; i++) {
            uint32_t addr = LOCS[i][0];
            int w = (int)LOCS[i][1];
            uint64_t val = (uint64_t)v[i];
            int b;
            for (b = 0; b < w; b++) {
                *(volatile uint8_t *)(uintptr_t)(addr + b) =
                    (uint8_t)(val >> (8 * (w - 1 - b)));
            }
        }

        rx8_immo_state_ready_to_drive_engine_off();

        /* Print the 26 resulting cells (same widths). */
        for (i = 0; i < NCELLS; i++) {
            uint32_t addr = LOCS[i][0];
            int w = (int)LOCS[i][1];
            uint64_t val = 0;
            int b;
            for (b = 0; b < w; b++)
                val = (val << 8) | *(volatile uint8_t *)(uintptr_t)(addr + b);
            if (i) putchar(' ');
            printf("%0*llX", w * 2, (unsigned long long)val);
        }
        putchar('\n');
    }
    return 0;
}
