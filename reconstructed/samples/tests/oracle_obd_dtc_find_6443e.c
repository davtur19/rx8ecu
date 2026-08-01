/* ============================================================================
 * oracle_obd_dtc_find_6443e.c  —  host test rig for rx8_obd_dtc_find_6443e
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     dtc <r4> <currow> <b06hex42> <b08hex42>
 *          -> <retval> <region-cksum>
 *
 *   <r4>         search key as seen by the ROM leaf (full 32-bit word; the
 *                leaf only uses the low 8 bits).
 *   <currow>     the 16-bit "current row" word @0xFFFF8D74.
 *   <b06hex42>   the 21 byte-0x06 column bytes as a 42-char hex string.
 *   <b08hex42>   the 21 byte-0x08 column bytes as a 42-char hex string.
 *
 * The oracle re-implements the caller-side set-up ONLY: it mmap()s the page
 * backing the DTC table (0xFFFF8930, 21 rows x 0x34) and the row-index word
 * (0xFFFF8D74), seeds the table, calls the reconstructed leaf, then prints
 * the 32-bit return value and a checksum of the whole DTC-table region
 * (0xFFFF8930..0xFFFF8D73).  The leaf performs no writes on the DTC state
 * (only r14/macl stack pushes), so the post-call region checksum is compared
 * against the seed checksum to prove that property.
 *
 * NOTE on endianness (see rx8_hw.h): on this little-endian host a 16-bit word
 * stored/loaded through *(uint16_t*) round-trips the same numeric value as on
 * the big-endian target, but its two BYTES are in the opposite order.  The
 * region checksum therefore covers only the byte-accessed table rows and
 * deliberately excludes the currow word bytes (their numeric value is still
 * verified through the return value).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_hw.h"

#define DTC_CURROW_ADDR 0xFFFF8D74u
/* Checksum window: the 21 table rows only (no byte-order-ambiguous words). */
#define DTC_CKSUM_LEN (RX8_DTC_TABLE_ROWS * RX8_DTC_TABLE_STRIDE)

int32_t rx8_obd_dtc_find_6443e(uint32_t r4);

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

static uint32_t region_checksum(void)
{
    uint32_t s = 0;
    for (uint32_t a = RX8_DTC_TABLE_BASE; a < RX8_DTC_TABLE_BASE + DTC_CKSUM_LEN; a++)
        s += *(volatile uint8_t *)(uintptr_t)a;
    return s;
}

static uint8_t hexbyte(const char h[2])
{
    char t[3] = { h[0], h[1], '\0' };
    return (uint8_t)strtoul(t, NULL, 16);
}

int main(void)
{
    char line[512];

    /* Page 0xFFFF8000 covers both the DTC table (0xFFFF8930..0xFFFF8D73)
     * and the currow word (0xFFFF8D74). */
    map_page(0xFFFF8000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long r4, currow;
        char b06[128], b08[128];

        if (sscanf(line, "dtc %lx %lx %127s %127s", &r4, &currow, b06, b08) != 4
            || strlen(b06) != RX8_DTC_TABLE_ROWS * 2
            || strlen(b08) != RX8_DTC_TABLE_ROWS * 2) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Fresh rows (bytes not listed here — incl. the dead +0x07 read — are 0). */
        for (uint32_t i = 0; i < DTC_CKSUM_LEN; i++)
            *(volatile uint8_t *)(uintptr_t)(RX8_DTC_TABLE_BASE + i) = 0;
        *(volatile uint8_t *)(uintptr_t)DTC_CURROW_ADDR = 0;
        *(volatile uint8_t *)(uintptr_t)(DTC_CURROW_ADDR + 1) = 0;

        for (uint32_t i = 0; i < RX8_DTC_TABLE_ROWS; i++) {
            uint8_t *p = (uint8_t *)(uintptr_t)(RX8_DTC_TABLE_BASE + i * RX8_DTC_TABLE_STRIDE);
            p[0x06] = hexbyte(b06 + 2 * i);
            p[0x08] = hexbyte(b08 + 2 * i);
        }
        *(volatile uint16_t *)DTC_CURROW_ADDR = (uint16_t)currow;

        printf("%08X %08X\n",
               (uint32_t)rx8_obd_dtc_find_6443e((uint32_t)r4),
               region_checksum());
    }
    return 0;
}
