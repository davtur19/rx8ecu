/* ============================================================================
 * oracle_can_setup.c — host test rig for rx8_can_setup @0xDC8C
 * ============================================================================
 * Compile together with src/rx8_can_setup.c and pipe test vectors on stdin;
 * one vector per line, whitespace-separated hex tokens:
 *
 *     setup <cfg> <a40e> <a410> <a411>      -> <a40e> <a410> <a411>
 *
 *   cfg   : value of the ROM's config byte @0x0000B5A4 (host model: the
 *           function's `config` parameter — 0xB5A4 lies below mmap_min_addr)
 *   a40e  : pre-call retry counter  @0xFFFFA40E  (proves the ROM resets it)
 *   a410  : pre-call error flag A   @0xFFFFA410
 *   a411  : pre-call error flag B   @0xFFFFA411
 *
 * The oracle mirrors the emulator-side set-up of harness_can_setup.py: it
 * mmap()s the page that backs the three caller cells and re-implements ONLY
 * the two callee stubs (CANControllerSetup @0x9878 as a no-op, canMessageSetup
 * @0x2B320 as always-fail) — see rx8_can_setup.c header, discrepancy 5.  It
 * contains NO copy of the canSetup logic; that lives solely in
 * src/rx8_can_setup.c.
 *
 * NOTE: rx8_can_setup is declared here rather than in rx8_samples.h (which is
 * off-limits for this task) — the reconstructed name maps to the ROM function
 * at 0xDC8C (see rx8_can_setup.c).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0xDC8C — CAN controller init with retry (see rx8_can_setup.c). */
void rx8_can_setup(uint8_t config);

/* Callee stubs (see rx8_can_setup.c, discrepancy 5).  Non-static: they satisfy
 * the extern references from src/rx8_can_setup.c. */
void rx8_can_controller_setup(uint32_t channel, uint32_t base_addr,
                              uint32_t mode)
{
    (void)channel; (void)base_addr; (void)mode;   /* no-op: see header */
}

uint32_t rx8_can_message_setup(uint32_t channel, uint32_t base_addr,
                               uint32_t mode)
{
    (void)channel; (void)base_addr; (void)mode;
    return 1u;                                     /* always-fail: see header */
}

#define RETRY_ADDR 0xFFFFA40Eu
#define ERRFLAG    0xFFFFA410u
#define ERRCLR     0xFFFFA411u

static volatile uint8_t *retry_cell = (volatile uint8_t *)RETRY_ADDR;
static volatile uint8_t *errflag    = (volatile uint8_t *)ERRFLAG;
static volatile uint8_t *errclr     = (volatile uint8_t *)ERRCLR;

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
    char line[128];

    /* Back the page holding 0xFFFFA40E/410/411. */
    map_page(0xFFFFA000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long cfg, c1, c2, c3;

        if (sscanf(line, "setup %lx %lx %lx %lx", &cfg, &c1, &c2, &c3) == 4) {
            *retry_cell = (uint8_t)c1;
            *errflag    = (uint8_t)c2;
            *errclr     = (uint8_t)c3;
            rx8_can_setup((uint8_t)cfg);
            printf("%02X %02X %02X\n",
                   (unsigned)*retry_cell, (unsigned)*errflag, (unsigned)*errclr);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
