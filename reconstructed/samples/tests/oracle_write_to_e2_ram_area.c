/* ============================================================================
 * oracle_write_to_e2_ram_area.c — host rig for rx8_write_to_e2_ram_area
 * ============================================================================
 * Compile together with src/rx8_write_to_e2_ram_area.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     e2 <index:4> <len:2> <pseed:2> <cseed:2> [<srchex>]
 *        index : uint16_t EEPROM-shadow index (r4)
 *        len   : uint8_t byte count (r6; extu.b loop counter)
 *        pseed : pre-fill seed for the 256-byte primary   shadow:
 *                primary[i]   = (pseed + 5*i) & 0xFF      @0xFFFFC2FE
 *        cseed : pre-fill seed for the 256-byte complement shadow:
 *                complement[i] = (cseed + 7*i) & 0xFF     @0xFFFFC3FE
 *        srchex: 2*len hex chars — the source bytes, placed at 0xFFFFD000
 *                (empty when len == 0; the token is then simply absent)
 *
 *   -> <r0> <prim:512hex> <comp:512hex>
 *
 * r0    : r0 after the call, reproduced from the ROM listing:
 *         len != 0 -> (index + len - 1) & 0xFFFF (last loop idx);
 *         len == 0 -> 0xF0 (getSR's return = SR & 0xF0).
 * prim  : 256 primary   shadow bytes @0xFFFFC2FE after the call (hex)
 * comp  : 256 complement shadow bytes @0xFFFFC3FE after the call (hex)
 *
 * The oracle contains the porting layer ONLY (getSR/setSR stubs faithful to
 * the ROM behaviour under the default SR = 0xF0); the function under test
 * lives solely in src/rx8_write_to_e2_ram_area.c.  It mmap()s the two pages
 * backing the E2 shadow (0xFFFFC000) and the source buffer (0xFFFFD000) so
 * the C code writes real memory at the ROM addresses.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

/* 0x39124 — EEPROM shadow write (see the sample source). */
void rx8_write_to_e2_ram_area(uint16_t index, const uint8_t *src, uint8_t length);

/* ---- RAM windows (verified addresses, c/eeprom_immo.h + the sample) ---- */
#define E2_PRIMARY_BASE    ((volatile uint8_t *)0xFFFFC2FE)   /* 256 B */
#define E2_COMPLEMENT_BASE ((volatile uint8_t *)0xFFFFC3FE)   /* 256 B */
#define E2_SHADOW_PAGE     ((uintptr_t)0xFFFFC000)            /* backs C2FE..C4FD */
#define SRC_BASE           ((uint8_t *)0xFFFFD000)            /* source buffer */
#define SRC_PAGE           ((uintptr_t)0xFFFFD000)

/* ---- getSR / setSR stubs (c/eeprom_immo.h externs; default SR = 0xF0) ---- */
uint32_t getSR(uint32_t arg);
void     setSR(uint32_t val);

uint32_t getSR(uint32_t arg)
{
    (void)arg;
    return 0xF0u;               /* SR & 0xF0 with the default SR = 0xF0 */
}

void setSR(uint32_t val)
{
    (void)val;                  /* ldc r4,sr — no observable RAM effect */
}

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
    char line[1024];
    size_t i;

    map_page(E2_SHADOW_PAGE);
    map_page(SRC_PAGE);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long index, len, pseed, cseed;
        char *tok, *srchex = NULL;
        size_t slen;

        tok = strtok(line, " \t\r\n");
        if (!tok || strcmp(tok, "e2") != 0) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        index = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        len   = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        pseed = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        cseed = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        tok   = strtok(NULL, " \t\r\n");       /* source hex (may be absent) */
        if (len != 0) {
            if (!tok) {
                fprintf(stderr, "missing srchex: %s", line);
                return 2;
            }
            srchex = tok;
            slen = strlen(srchex);
            if (slen != 2 * len) {
                fprintf(stderr, "bad srchex length: %s", line);
                return 2;
            }
            for (i = 0; i < len; i++) {
                unsigned v;
                if (sscanf(srchex + 2 * i, "%2x", &v) != 1) return 2;
                SRC_BASE[i] = (uint8_t)v;
            }
        }

        /* Pre-fill the shadows (deterministic, seed-driven) — untouched
         * bytes stay in the comparison and must match the emulator side. */
        for (i = 0; i < 256; i++) {
            E2_PRIMARY_BASE[i]    = (uint8_t)((pseed + 5 * i) & 0xFF);
            E2_COMPLEMENT_BASE[i] = (uint8_t)((cseed + 7 * i) & 0xFF);
        }

        rx8_write_to_e2_ram_area((uint16_t)index, SRC_BASE, (uint8_t)len);

        /* r0 side channel (formula from the ROM listing, verified on the
         * emulator): last loop idx for len != 0, else getSR's 0xF0. */
        unsigned long r0 = (len != 0) ? ((index + len - 1) & 0xFFFFUL) : 0xF0UL;

        printf("%04lX ", r0);
        for (i = 0; i < 256; i++) printf("%02X", E2_PRIMARY_BASE[i]);
        printf(" ");
        for (i = 0; i < 256; i++) printf("%02X", E2_COMPLEMENT_BASE[i]);
        printf("\n");
    }
    return 0;
}
