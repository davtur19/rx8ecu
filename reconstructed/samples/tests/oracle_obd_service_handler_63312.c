/* ============================================================================
 * oracle_obd_service_handler_63312.c  —  host test rig for
 *                                        rx8_obd_service_handler_63312 @0x63312
 * ============================================================================
 * Piped on stdin, one vector per line:
 *
 *     obd <flag> <pad>
 *
 *   flag : value of byte@0xFFFF87D0 (the OBD pending flag) in ROM semantics
 *   pad  : value of the neighbouring byte@0xFFFF87D1 (low byte of the cell)
 *
 * Output: one line per vector — the two bytes of the 16-bit cell at
 * 0xFFFF87D0 AFTER the call, in ROM (big-endian) order:
 *
 *     <b0> <b1>
 *
 * b0 is the pending-flag byte, b1 its neighbour.  The oracle re-implements
 * the caller-side setup only: it mmap()s the page that backs 0xFFFF87D0
 * (MAP_FIXED, so the emulator and the host C run against the same numeric
 * address), seeds the same cell VALUE, then calls the reconstructed function
 * under test.  It contains NO copy of the function logic — that lives solely
 * in samples/src/rx8_obd_service_handler_63312.c.
 *
 * The cell is seeded/checked through a uint16_t VALUE: byte@0xFFFF87D0 is the
 * high byte (>>8) of that value (big-endian ROM semantics) and the host build
 * stores the same value with native host endianness — so the printed bytes
 * are reconstructed from the value, matching the ROM's byte layout exactly
 * (same convention as c/tests/test_obd_service_handler_63312.c).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

extern void rx8_obd_service_handler_63312(void);

#define FLAG 0xFFFF87D0u

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

    /* Back the page holding the cell at 0xFFFF87D0 (page 0xFFFF8000). */
    map_page(0xFFFF8000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long flag, pad;

        if (sscanf(line, "obd %lx %lx", &flag, &pad) != 2) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Cell value with the flag byte as high byte, ROM (big-endian)
         * semantics — byte@FLAG = flag, byte@FLAG+1 = pad. */
        uint16_t seeded = (uint16_t)(((uint16_t)(flag & 0xFFu) << 8)
                                   | (pad & 0xFFu));
        *(volatile uint16_t *)FLAG = seeded;

        rx8_obd_service_handler_63312();

        uint16_t got = *(volatile uint16_t *)FLAG;
        printf("%02X %02X\n", (got >> 8) & 0xFF, got & 0xFF);
    }
    return 0;
}
