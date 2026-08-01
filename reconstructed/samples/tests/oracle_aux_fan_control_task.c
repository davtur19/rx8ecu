/* ============================================================================
 * oracle_aux_fan_control_task.c — host rig for rx8_aux_fan_control_task @0x1AED2
 * ============================================================================
 * Compile together with samples/src/rx8_aux_fan_control_task.c (the sample is
 * self-contained — the 0x23B0 filter leaf is inlined) and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *   aux <ff> <fe> <eps> <scale> <pon> <phy>
 *       <c008> <bc1c> <bd40> <bd38> <b5b8>
 *       <c104> <c108> <c10c> <c12c> <adc0> <a38c>
 *
 *   ff/fe/eps/scale/pon/phy : the 6 f32 calibration constants the ROM reads
 *                             at 0x78CFC / 0x76B30 / 0x32F64 / 0x2DDB0 /
 *                             0x7A18C / 0x7A190 (harness ships them inline
 *                             from the stock bin, exactly like the purge rig)
 *   c008..adc0              : f32 bit patterns of the 10 RAM float inputs
 *                             (0xFFFFC008 filtered boost, 0xFFFFBC1C filter
 *                             history, 0xFFFFBD40 delta prev, 0xFFFFBD38
 *                             error prev, 0xFFFFB5B8 pressure, 0xFFFFC104,
 *                             0xFFFFC108, 0xFFFFC10C, 0xFFFFC12C, 0xFFFFADC0)
 *   a38c                    : u8 pre-state of the fan flag @0xFFFFA38C
 *                                       -> <C008> <BD3C> <BD40> <BD38>
 *                                          <C0D8> <C0DC> <C0E0> <C108>
 *                                          <C104> <C10C>
 *                                          <A384> <A385> <A324> <A38C>
 *   (10 f32 cells + 4 u8 cells the task can write, in the ROM's write order)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the six ROM constant addresses, seeds every input
 * and prints the post-state cells.  It contains NO copy of the function logic
 * — that lives solely in the reconstructed source under test.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x0002D000  ROM 0x2DDB0 (15.625) + 0x2DDB8 (1e-5, error filter)
 *   0x00032000  ROM 0x32F64 (1e-5, boost filter)
 *   0x00076000  ROM 0x76B30 (0.5)
 *   0x00078000  ROM 0x78CFC (0.7)
 *   0x0007A000  ROM 0x7A18C (7000) + 0x7A190 (500)
 *   0xFFFFA000  RAM[0xFFFFA38C/0xFFFFA384/0xFFFFA385/0xFFFFA324] + 0xFFFFADC0
 *   0xFFFFB000  RAM[0xFFFFB5B8/0xFFFFBC1C/0xFFFFBD38/0xFFFFBD3C/0xFFFFBD40]
 *   0xFFFFC000  RAM[0xFFFFC008/0xFFFFC0D8/0xFFFFC0DC/0xFFFFC0E0/
 *                 0xFFFFC104/0xFFFFC108/0xFFFFC10C/0xFFFFC12C]
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

void rx8_aux_fan_control_task(void);

/* f32 bit-pattern <-> host float (endian-transparent). */
static uint32_t f2b(float f)
{
    uint32_t u;
    memcpy(&u, &f, 4);
    return u;
}

static float b2f(uint32_t u)
{
    float f;
    memcpy(&f, &u, 4);
    return f;
}

/* RAM / ROM cells (absolute SH-2 addresses). */
#define A_FF_FILT   0x00078CFCu   /* 0.7     */
#define A_FF_ERR    0x00076B30u   /* 0.5     */
#define A_EPS       0x00032F64u   /* 1e-5    */
#define A_SCALE     0x0002DDB0u   /* 15.625  */
#define A_P_ON      0x0007A18Cu   /* 7000    */
#define A_P_HY      0x0007A190u   /* 500     */

#define A_C008      0xFFFFC008u   /* boost input (f32, read+write) */
#define A_BC1C      0xFFFFBC1Cu   /* filter history (f32, read)    */
#define A_BD40      0xFFFFBD40u   /* delta prev (f32, read+write)  */
#define A_BD3C      0xFFFFBD3Cu   /* scaled delta (f32, write)     */
#define A_BD38      0xFFFFBD38u   /* error prev (f32, read+write)  */
#define A_B5B8      0xFFFFB5B8u   /* pressure input (f32, read)    */
#define A_C104      0xFFFFC104u
#define A_C108      0xFFFFC108u
#define A_C10C      0xFFFFC10Cu
#define A_C0D8      0xFFFFC0D8u
#define A_C0DC      0xFFFFC0DCu
#define A_C0E0      0xFFFFC0E0u
#define A_C12C      0xFFFFC12Cu
#define A_ADC0      0xFFFFADC0u
#define A_A38C      0xFFFFA38Cu   /* fan flag (u8, read+write)     */
#define A_A384      0xFFFFA384u   /* update latch (u8, write)      */
#define A_A385      0xFFFFA385u
#define A_A324      0xFFFFA324u

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

static void wr_f32(uint32_t addr, uint32_t bits)
{
    *(volatile float *)(uintptr_t)addr = b2f(bits);
}

static uint32_t rd_f32(uint32_t addr)
{
    return f2b(*(volatile float *)(uintptr_t)addr);
}

int main(void)
{
    char line[256];

    /* ROM constant pages (seeded per-vector, like the purge rig). */
    map_page(A_FF_FILT);
    map_page(A_FF_ERR);
    map_page(A_EPS);
    map_page(A_SCALE);
    map_page(A_P_ON);
    /* RAM pages backing every cell the task reads/writes. */
    map_page(A_C008);              /* 0xFFFFC000 page */
    map_page(A_B5B8);              /* 0xFFFFB000 page */
    map_page(A_ADC0);              /* 0xFFFFA000 page (covers A324..A38C) */

    while (fgets(line, sizeof line, stdin)) {
        unsigned long v[17];
        int n = sscanf(line,
                       "aux %lx %lx %lx %lx %lx %lx"
                       " %lx %lx %lx %lx %lx"
                       " %lx %lx %lx %lx %lx %lx",
                       &v[0], &v[1], &v[2], &v[3], &v[4], &v[5],
                       &v[6], &v[7], &v[8], &v[9], &v[10],
                       &v[11], &v[12], &v[13], &v[14], &v[15], &v[16]);
        if (n != 17) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Calibration constants exactly as the stock bin has them. */
        wr_f32(A_FF_FILT, (uint32_t)v[0]);
        wr_f32(A_FF_ERR,  (uint32_t)v[1]);
        wr_f32(A_EPS,     (uint32_t)v[2]);
        wr_f32(A_SCALE,   (uint32_t)v[3]);
        wr_f32(A_P_ON,    (uint32_t)v[4]);
        wr_f32(A_P_HY,    (uint32_t)v[5]);

        /* RAM float inputs + flag pre-state. */
        wr_f32(A_C008, (uint32_t)v[6]);
        wr_f32(A_BC1C, (uint32_t)v[7]);
        wr_f32(A_BD40, (uint32_t)v[8]);
        wr_f32(A_BD38, (uint32_t)v[9]);
        wr_f32(A_B5B8, (uint32_t)v[10]);
        wr_f32(A_C104, (uint32_t)v[11]);
        wr_f32(A_C108, (uint32_t)v[12]);
        wr_f32(A_C10C, (uint32_t)v[13]);
        wr_f32(A_C12C, (uint32_t)v[14]);
        wr_f32(A_ADC0, (uint32_t)v[15]);
        *(volatile uint8_t *)(uintptr_t)A_A38C = (uint8_t)v[16];

        /* The emulator gives each vector a fresh RAM overlay, so every cell
         * NOT seeded in the vector reads as 0.  The three latch bytes are
         * write-only inputs (only A38C is seeded) — zero them here, exactly
         * like the emulator's fresh-RAM view. */
        *(volatile uint8_t *)(uintptr_t)A_A384 = 0;
        *(volatile uint8_t *)(uintptr_t)A_A385 = 0;
        *(volatile uint8_t *)(uintptr_t)A_A324 = 0;

        rx8_aux_fan_control_task();

        /* Post-state: 10 f32 cells + 4 u8 cells (ROM write order). */
        printf("%08lX %08lX %08lX %08lX %08lX %08lX %08lX %08lX %08lX %08lX"
               " %02X %02X %02X %02X\n",
               (unsigned long)rd_f32(A_C008),
               (unsigned long)rd_f32(A_BD3C),
               (unsigned long)rd_f32(A_BD40),
               (unsigned long)rd_f32(A_BD38),
               (unsigned long)rd_f32(A_C0D8),
               (unsigned long)rd_f32(A_C0DC),
               (unsigned long)rd_f32(A_C0E0),
               (unsigned long)rd_f32(A_C108),
               (unsigned long)rd_f32(A_C104),
               (unsigned long)rd_f32(A_C10C),
               *(volatile uint8_t *)(uintptr_t)A_A384,
               *(volatile uint8_t *)(uintptr_t)A_A385,
               *(volatile uint8_t *)(uintptr_t)A_A324,
               *(volatile uint8_t *)(uintptr_t)A_A38C);
    }
    return 0;
}
