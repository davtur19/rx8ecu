/* ============================================================================
 * oracle_get_from_e2.c — host rig for rx8_get_from_e2 @0x39170
 * ============================================================================
 * Compile together with src/rx8_get_from_e2.c and pipe test vectors on stdin;
 * one vector per line, whitespace-separated hex tokens:
 *
 *     e2 <e2addr> <len> <retry> <flash> <seed> <p:512hex> <c:512hex>
 *        e2addr : 16-bit EEPROM offset passed in r4 (harness constrains 0..255)
 *        len    : byte count passed in r6 (harness constrains 0..255)
 *        retry  : byte loaded by the stubbed SPI-retry hook @0xC0A8
 *                 (0 -> "recovered": corrupt pairs rebuilt from FLASH;
 *                  != 0 -> "retry failed": error flag, byte not copied)
 *        flash  : 8-bit immediate loaded by the stubbed flash reader @0xBFCA;
 *                 SIGN-extended to 32 bits like `mov #imm,r0`
 *        seed   : destination pre-fill seed: dest[0xFFFFA000+k] = (seed+3k)&0xFF
 *        p      : 256-byte EEPROM primary   shadow (E2[0x00..0xFF]) @0xFFFFC2FE
 *        c      : 256-byte EEPROM complement shadow (~E2)           @0xFFFFC3FE
 *
 *   -> <r0> <dest:512hex> <p:512hex> <c:512hex>
 *
 * r0   : r0 after the call = getFromE2's return (error flag: 1 = a corrupt
 *        pair whose SPI retry also failed, 0 = all valid or recovered)
 * dest : 256 destination bytes @0xFFFFA000 (pre-filled from seed; the error
 *        path leaves its byte untouched, so the pre-fill is part of the check)
 * p,c  : the 256-byte primary/complement shadows AFTER the call
 *        (flash recovery rewrites the corrupt pair in place)
 *
 * The oracle contains the porting layer ONLY (getSR/setSR/e2_retry/
 * e2_flash_read stubs, faithful to the c/getFromE2.c helper semantics); the
 * function under test lives solely in src/rx8_get_from_e2.c.  It mmap()s the
 * pages backing the destination window and the E2 shadow (same trick as
 * tests/oracle_get_data_from_e2_ram.c) so the C code writes real memory at
 * the ROM addresses.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_hw.h"
#include "rx8_samples.h"

/* 0x39170 — EEPROM shadow -> RAM copy with complement validation. */
uint8_t rx8_get_from_e2(uint16_t e2addr, uint8_t *ramaddr, uint8_t len);

/* ---- RAM windows (verified addresses, see c/eeprom_immo.h + the sample) ---- */
#define DEST_BASE          ((volatile uint8_t *)0xFFFFA000)   /* dest window  */
#define E2_SHADOW_PAGE     ((uintptr_t)0xFFFFC000)            /* backs C2FE..C4FD */
#define E2_PRIMARY_BASE    ((volatile uint8_t *)0xFFFFC2FE)   /* 256-byte primary */
#define E2_COMPLEMENT_BASE ((volatile uint8_t *)0xFFFFC3FE)   /* 256-byte complement */

/* ---- hardware stubs (mirror the harness' RAM-overlay stubs) ---- */
static int      g_retry_val;    /* e2_retry() result: 0 = recover, !=0 = fail */
static uint8_t  g_flash_const;  /* e2_flash_read() 8-bit imm (sign-extended)  */

uint32_t getSR(uint32_t arg)
{
    (void)arg;
    return 0xF0u;               /* stub: the emulator stub is `mov #0xF0,r0`
                                   (sign-extends to 0xFFFFFFF0); the value is
                                   consumed only by the no-op setSR stub */
}

void setSR(uint32_t val)
{
    (void)val;                  /* stub @0x3934 = rts; nop: no observable effect */
}

int e2_retry(void)
{
    return g_retry_val;
}

uint16_t e2_flash_read(uint32_t flashaddr)
{
    (void)flashaddr;
    /* `mov #imm,r0` stub: an 8-bit immediate is SIGN-extended to 32 bits,
     * so the 16-bit word the caller sees is (uint16_t)(int8_t)const. */
    return (uint16_t)(int8_t)g_flash_const;
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
    char line[4096];

    map_page(0xFFFFA000);       /* destination window */
    map_page(E2_SHADOW_PAGE);   /* E2 primary + complement shadows */

    while (fgets(line, sizeof line, stdin)) {
        unsigned long e2addr, len, retry, flash, seed;
        char ptok[1024], ctok[1024];
        uint8_t p[256], c[256];
        size_t i, k;

        if (sscanf(line, "e2 %lx %lx %lx %lx %lx %512s %512s",
                   &e2addr, &len, &retry, &flash, &seed, ptok, ctok) != 7) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        if (strlen(ptok) != 512 || strlen(ctok) != 512) {
            fprintf(stderr, "bad shadow length: %s", line);
            return 2;
        }
        for (i = 0; i < 256; i++) {
            unsigned v;
            if (sscanf(ptok + 2 * i, "%2x", &v) != 1) return 2;
            p[i] = (uint8_t)v;
            if (sscanf(ctok + 2 * i, "%2x", &v) != 1) return 2;
            c[i] = (uint8_t)v;
        }

        /* Set up the stubs for this vector. */
        g_retry_val   = (retry != 0) ? 1 : 0;
        g_flash_const = (uint8_t)flash;

        /* Destination pre-fill (deterministic, seed-driven) — the error path
         * leaves its byte untouched, so the pre-fill is part of the check. */
        for (k = 0; k < 256; k++) {
            DEST_BASE[k] = (uint8_t)((seed + 3 * k) & 0xFF);
        }
        /* E2 shadows (primary + complement) for E2[0x00..0xFF]. */
        for (i = 0; i < 256; i++) {
            E2_PRIMARY_BASE[i]    = p[i];
            E2_COMPLEMENT_BASE[i] = c[i];
        }

        unsigned r0 = rx8_get_from_e2((uint16_t)e2addr,
                                      (uint8_t *)DEST_BASE, (uint8_t)len);

        /* Emit: r0 + 256 dest bytes + 256 primary + 256 complement. */
        printf("%02X ", r0);
        for (k = 0; k < 256; k++) printf("%02X", DEST_BASE[k]);
        printf(" ");
        for (i = 0; i < 256; i++) printf("%02X", E2_PRIMARY_BASE[i]);
        printf(" ");
        for (i = 0; i < 256; i++) printf("%02X", E2_COMPLEMENT_BASE[i]);
        printf("\n");
    }
    return 0;
}
