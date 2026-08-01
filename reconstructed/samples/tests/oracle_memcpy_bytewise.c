/* ============================================================================
 * oracle_memcpy_bytewise.c  —  host test rig for rx8_memcpy_bytewise @0x42B0
 * ============================================================================
 * Piped on stdin, one vector per line:
 *
 *     cpy <count> <src> <dst> <srchex|'-'>
 *
 *   count   : decimal number of bytes to copy
 *   src,dst : hex RAM addresses the caller hands the function
 *   srchex  : hex of the `count` source bytes, or '-' when count == 0
 *
 * Output: one line per vector — the hex dump of the destination window
 * (count + TAIL bytes: the copied range plus a 0xA5-prefilled tail that must
 * remain untouched).
 *
 * The oracle re-implements the caller-side setup only: it mmap()s the pages
 * that back the src/dst addresses (MAP_FIXED, so the emulator and the host C
 * run against the same numeric pointers), seeds the same memory image, then
 * calls the reconstructed function under test.  It contains NO copy of the
 * function logic — that lives solely in samples/src/rx8_memcpy_bytewise.c.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* The reconstructed function under test.  rx8_samples.h is shared between
 * all samples and must not be edited by any single reconstruction agent. */
extern void rx8_memcpy_bytewise(uint8_t *dst, const uint8_t *src,
                                uint32_t count);

#define TAIL     16u        /* untouched tail verified after each copy */
#define PATTERN  0xA5u      /* prefill value for the destination window */

/* MAP_FIXED bookkeeping: src and dst may share a page (overlap vectors), so
 * never remap (and thereby wipe) a base that is already mapped. */
static uintptr_t g_mapped[16];
static int g_nmapped = 0;

static void map_once(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);

    for (int i = 0; i < g_nmapped; i++) {
        if (g_mapped[i] == base) {
            return;              /* already backed, keep its contents */
        }
    }
    /* Two pages: covers any misalignment plus the TAIL window in one page. */
    void *p = mmap((void *)base, (size_t)(2 * (uintptr_t)page),
                   PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
    if (g_nmapped < (int)(sizeof g_mapped / sizeof g_mapped[0])) {
        g_mapped[g_nmapped++] = base;
    }
}

static int hexval(int c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int main(void)
{
    char line[8192];

    while (fgets(line, sizeof line, stdin)) {
        char op[16];
        unsigned long count, src, dst;
        char srchex[2048];

        if (sscanf(line, "%15s %lu %lx %lx %2047s",
                   op, &count, &src, &dst, srchex) != 5
            || strcmp(op, "cpy") != 0) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        if (count > 4096) {
            fprintf(stderr, "count too large: %lu\n", count);
            return 2;
        }

        map_once(src);
        map_once(dst);

        uint8_t *s = (uint8_t *)(uintptr_t)src;
        uint8_t *d = (uint8_t *)(uintptr_t)dst;

        /* Seed the memory image: src bytes first, then the 0xA5 prefill of
         * the destination window.  The harness mirrors this exact order on
         * the emulator side, so overlapping src/dst regions start from the
         * same initial image on both sides. */
        if (strcmp(srchex, "-") != 0) {
            size_t n = strlen(srchex);
            if (n != (size_t)count * 2) {
                fprintf(stderr, "src hex length mismatch: %s", line);
                return 2;
            }
            for (size_t i = 0; i < (size_t)count; i++) {
                int hi = hexval((unsigned char)srchex[2 * i]);
                int lo = hexval((unsigned char)srchex[2 * i + 1]);
                if (hi < 0 || lo < 0) {
                    fprintf(stderr, "bad hex in: %s", line);
                    return 2;
                }
                s[i] = (uint8_t)((hi << 4) | lo);
            }
        }
        for (unsigned long i = 0; i < count + TAIL; i++) {
            d[i] = PATTERN;
        }

        rx8_memcpy_bytewise(d, s, (uint32_t)count);

        for (unsigned long i = 0; i < count + TAIL; i++) {
            printf("%02X", d[i]);
        }
        printf("\n");
    }
    return 0;
}
