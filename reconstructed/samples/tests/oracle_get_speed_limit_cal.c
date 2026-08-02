/* ============================================================================
 * oracle_get_speed_limit_cal.c  —  host test rig for
 *                              rx8_get_speed_limit_cal @ 0x49EFC
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     spl <k0> <k34> <k36> <k37>
 *
 *   k0   : 32-bit config-B key  -> RAM[0xFFFFD3D0] (u32)
 *   k34  : 16-bit lookup-id key -> RAM[0xFFFFD3D4] (u16)
 *   k36  : u8  config-C key     -> RAM[0xFFFFD3D6]
 *   k37  : u8  config-D key     -> RAM[0xFFFFD3D7]
 *
 * The rig seeds those four RAM cells, calls rx8_get_speed_limit_cal() and
 * prints the seven committed cells as hex bytes (same token layout as the emu
 * comparison), in the order:
 *
 *    CD4C CD4D CD4E CD4F CD50 CD51 CD52
 *   (tha A thr B thr C | flag ia flagB flagC flagD)
 *
 * The oracle contains NO copy of the function logic — that lives solely in
 * src/rx8_get_speed_limit_cal.c.  It only mirrors the caller-side set-up: the
 * 0xFFFFC000 / 0xFFFFD000 pages are backed with mmap(MAP_FIXED) so the
 * volatile fixed-address pointers in the sample compile and fault-free on the
 * host, exactly like tests/host_oracle.c.  The two multi-byte input words are
 * seeded as explicit big-endian byte sequences (high byte first), mirroring the
 * SH-2E emulator's sparse-RAM overlay; the u8 cells are plain single bytes.
 *
 * NOTE on the addresses: the ROM reaches them with `mov.w` literals, which
 * SIGN-EXTEND the 16-bit words (0xCD4C, 0xD3D4, ...) to the on-chip RAM
 * window 0xFFFFxxxx — the same convention as oracle_temperature_gauge_5aa5c.c.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

void rx8_get_speed_limit_cal(void);

/* Observable / seeded addresses (see the sample header). */
#define SPD_KEY1   0xFFFFD3D4u   /* u16 lookup-id key */
#define SPD_KEY2   0xFFFFD3D0u   /* u32 config-B key  */
#define SPD_KEY3   0xFFFFD3D6u   /* u8  config-C key  */
#define SPD_KEY4   0xFFFFD3D7u   /* u8  config-D key  */
#define SPD_RA     0xFFFFCD4Cu   /* threshold A */
#define SPD_RB     0xFFFFCD4Du   /* threshold B */
#define SPD_RC     0xFFFFCD4Eu   /* threshold C */
#define SPD_FA     0xFFFFCD4Fu   /* flag A */
#define SPD_FB     0xFFFFCD50u   /* flag B */
#define SPD_FC     0xFFFFCD51u   /* flag C */
#define SPD_FD     0xFFFFCD52u   /* flag D */

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        fprintf(stderr,"mmap failed at %08lx\n",(unsigned long)addr); perror("mmap");
        exit(1);
    }
}

int main(void)
{
    char line[128];
    unsigned long k0, k34, k36, k37;

    map_page(SPD_KEY2);              /* 0xFFFFD000 page (inputs) */
    map_page(SPD_RA);                /* 0xFFFFC000 page (outputs) */

    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "spl %lx %lx %lx %lx", &k0, &k34, &k36, &k37) != 4) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        if (k34 > 0xFFFFu) { fprintf(stderr, "k0 out of range: %s", line); return 2; }
        if (k36 > 0xFFu)  { fprintf(stderr, "k36 out of range: %s", line); return 2; }
        if (k37 > 0xFFu)  { fprintf(stderr, "k37 out of range: %s", line); return 2; }

        /* Seed big-endian byte sequences (same layout as the emulator's
         * sparse-RAM overlay), then run the sample under test. */
        {
            volatile uint8_t *b = (volatile uint8_t *)(uintptr_t)SPD_KEY2;
            b[0] = (k0 >> 24) & 0xFF; b[1] = (k0 >> 16) & 0xFF;
            b[2] = (k0 >> 8) & 0xFF;  b[3] = k0 & 0xFF;
        }
        {
            volatile uint8_t *b = (volatile uint8_t *)(uintptr_t)SPD_KEY1;
            b[0] = (k34 >> 8) & 0xFF; b[1] = k34 & 0xFF;
        }
        *(volatile uint8_t *)(uintptr_t)SPD_KEY3 = (uint8_t)k36;
        *(volatile uint8_t *)(uintptr_t)SPD_KEY4 = (uint8_t)k37;

        rx8_get_speed_limit_cal();

        printf("%02X %02X %02X %02X %02X %02X %02X\n",
               *(volatile uint8_t *)(uintptr_t)SPD_RA,
               *(volatile uint8_t *)(uintptr_t)SPD_RB,
               *(volatile uint8_t *)(uintptr_t)SPD_RC,
               *(volatile uint8_t *)(uintptr_t)SPD_FA,
               *(volatile uint8_t *)(uintptr_t)SPD_FB,
               *(volatile uint8_t *)(uintptr_t)SPD_FC,
               *(volatile uint8_t *)(uintptr_t)SPD_FD);
    }
    return 0;
}