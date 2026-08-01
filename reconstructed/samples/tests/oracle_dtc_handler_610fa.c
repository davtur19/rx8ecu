/* ============================================================================
 * oracle_dtc_handler_610fa.c  —  host test rig for rx8_dtc_handler_610fa
 * ============================================================================
 * Piped on stdin, one vector per line, whitespace-separated hex tokens:
 *
 *     dtc <flag> <pad> <idx> <opcode> <sel> <b07> <b08> <b32>
 *          -> <long@87BC> <word@87D0> <b07'> <b08'> <b32'> <cksum>
 *
 *   flag/pad : the two bytes of the 16-bit cell at 0xFFFF87D0 in ROM order
 *              (flag is the HIGH byte of the cell VALUE, pad the low byte —
 *              same VALUE convention as oracle_obd_service_handler_63312.c).
 *   idx      : the 16-bit "current DTC index" word @0xFFFF8928.
 *   opcode   : the byte seeded at opcode-table[0xFFFF87DE + idx*16].
 *   sel      : the 16-bit active-row word @0xFFFF8D74 (row selector of 64258).
 *   b07/b08/b32 : the pre-state bytes at row p + 0x07 / 0x08 / 0x32.
 *
 * The oracle re-implements the caller-side set-up ONLY: it MAP_FIXEDs the
 * on-chip RAM pages backing the DTC region (0xFFFF8000..0xFFFFE000), seeds
 * the same state the emulator seeds, then calls the reconstructed dispatcher
 * under test and prints the post-state.  It contains NO copy of the dispatcher
 * logic — that lives solely in samples/src/rx8_dtc_handler_610fa.c.
 *
 * CALLEE MODELS: the dispatcher calls three ROM helpers
 *   can_encode_handler_62FAC(8) @0x62FAC, obd_service_handler_64258 @0x64258,
 *   obd_service_handler_63312   @0x63312.
 * The emulator side executes the REAL ROM bytes of those helpers; the oracle
 * must reproduce their RAM side effects bit-exactly so the C chain and the ROM
 * chain converge.  The harness only ever feeds byte@0xFFFF87D0 != 2, which
 * pins can_encode onto its simple flag!=2 path (the flag==2 branch runs a
 * deeper encoder sub-chain — 0x640BC/0x42B0/0x6429E — that is out of scope
 * here).  64258 and 63312 are tiny verified leaves; their models are verbatim
 * from c/obd_dtc_row_update_0x64258.c and samples/src/rx8_obd_service_handler_63312.c.
 *
 * ENDIANNESS / VALUE CELLS: the two 16-bit cells (0xFFFF87D0, 0xFFFF8D74,
 * 0xFFFF8928) and the 32-bit cell (0xFFFF87BC) are read/written by the ROM
 * as WORD/LONG loads — on the host they are seeded/read back through their
 * numeric VALUE (the C lift reads them the same way), so all comparisons go
 * through VALUES, never raw bytes.  The checksum deliberately covers only the
 * byte-accessed windows (opcode table + DTC rows), whose bytes are seeded
 * identically on both sides and therefore compare raw-for-raw.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

void rx8_dtc_handler_610fa(void);

/* ====================== callee side-effect models ====================== */

/* 0x2420 `encode()` leaf (c/math_primitives.c): x<<8 | ~x. */
static uint16_t enc8(uint8_t x)
{
    return (uint16_t)((x << 8) | (uint8_t)~x);
}

/* 0x62FAC — can_encode_handler_62FAC(8), flag@0xFFFF87D0 != 2 path only
 * (the harness never feeds 2).  Side effects observed from the ROM:
 *   if byte@0xFFFF87D0 != 1: word@0xFFFF87D0 = enc8(1) = 0x01FE
 *   long@0xFFFF87BC = 0x2430(0xFFFF) = 0xFFFF0000           (0x2430: x<<16|~x) */
void can_encode_handler_62FAC(uint8_t mode)
{
    (void)mode;     /* the ROM only stashes the mode byte; it does not gate
                     * the flag!=2 path */
    if (((*(volatile uint16_t *)(uintptr_t)0xFFFF87D0u >> 8) & 0xFFu) != 0x01u)
        *(volatile uint16_t *)(uintptr_t)0xFFFF87D0u = enc8(0x01u);
    *(volatile uint32_t *)(uintptr_t)0xFFFF87BCu = 0xFFFF0000u;
}

/* 0x64258 — obd_service_handler_64258(): active-row counter update, verbatim
 * from c/obd_dtc_row_update_0x64258.c (verified bit-exact there). */
void obd_service_handler_64258(void)
{
    uint16_t row = *(volatile uint16_t *)(uintptr_t)0xFFFF8D74u;
    uint8_t *p = (uint8_t *)(uintptr_t)(0xFFFF8930u + (uint32_t)row * 0x34u);
    p[0x32] = (uint8_t)(p[0x32] + p[0x07] + 0xFFu);
    p[0x07] = 0x01u;
    p[0x32] = (uint8_t)(p[0x32] + p[0x08] + 0xF9u);
    p[0x08] = 0x07u;
}

/* 0x63312 — obd_service_handler_63312(): pending-flag clear, verbatim from
 * samples/src/rx8_obd_service_handler_63312.c (verified bit-exact there). */
void obd_service_handler_63312(void)
{
    if (((*(volatile uint16_t *)(uintptr_t)0xFFFF87D0u >> 8) & 0xFFu) == 0x01u)
        *(volatile uint16_t *)(uintptr_t)0xFFFF87D0u = enc8(0x00u);    /* 0x00FF */
}

/* ========================== caller-side rig ============================ */

#define IDX_ADDR     0xFFFF8928u   /* word: current DTC index               */
#define OPCODES      0xFFFF87DEu   /* byte: handler byte-code opcode table  */
#define OPCODE_WIN   352u          /* 22 entries x 16-byte stride (bytes)   */
#define FLAG_CELL    0xFFFF87D0u   /* word: can_encode/63312 dispatch cell  */
#define LONG_CELL    0xFFFF87BCu   /* long: can_encode echo (0xFFFF0000)    */
#define SEL_WORD     0xFFFF8D74u   /* word: 64258 active-row index          */
#define TABLE_BASE   0xFFFF8930u   /* byte: OBD DTC table base (0x34 stride)*/
#define CKSUM_END    0xFFFFDEC0u   /* end of the byte-accessed DTC window   */

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

/* Byte checksum over the byte-accessed windows only (opcode table + DTC rows
 * up to CKSUM_END): catches ANY unexpected byte write on either side while
 * staying endianness-immune. */
static uint32_t checksum(void)
{
    uint32_t s = 0;
    for (uintptr_t a = OPCODES; a < OPCODES + OPCODE_WIN; a++)
        s += *(volatile uint8_t *)(uintptr_t)a;
    for (uintptr_t a = TABLE_BASE; a < CKSUM_END; a++)
        s += *(volatile uint8_t *)(uintptr_t)a;
    return s;
}

int main(void)
{
    char line[256];

    /* Pages 0xFFFF8000..0xFFFFD000 back the whole on-chip RAM window used
     * here (rows 0..0x1A4 keep p+0x32 <= 0xFFFFDEB2 < CKSUM_END). */
    for (uintptr_t page = 0xFFFF8000u; page <= 0xFFFFD000u; page += 0x1000u)
        map_page(page);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long flag, pad, idx, opcode, sel, b07, b08, b32;

        if (sscanf(line, "dtc %lx %lx %lx %lx %lx %lx %lx %lx",
                   &flag, &pad, &idx, &opcode, &sel, &b07, &b08, &b32) != 8) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Fresh zeroed state (unseeded bytes must read 0, like the emulator). */
        memset((void *)0xFFFF8000u, 0, 0xFFFFE000u - 0xFFFF8000u);

        /* Value-cells, ROM (big-endian) semantics: byte@+0 is the HIGH byte
         * of the cell VALUE (same convention as oracle_obd_service_handler_63312.c). */
        *(volatile uint16_t *)(uintptr_t)FLAG_CELL =
            (uint16_t)(((uint16_t)(flag & 0xFFu) << 8) | (pad & 0xFFu));
        *(volatile uint16_t *)(uintptr_t)IDX_ADDR = (uint16_t)idx;
        *(volatile uint16_t *)(uintptr_t)SEL_WORD = (uint16_t)sel;
        *(volatile uint8_t *)(uintptr_t)(OPCODES + (uint32_t)(idx & 0xFFFFu) * 16u) =
            (uint8_t)opcode;

        /* The active DTC row the 64258 helper will touch. */
        uint8_t *p = (uint8_t *)(uintptr_t)(TABLE_BASE
                                            + (uint32_t)(sel & 0xFFFFu) * 0x34u);
        p[0x07] = (uint8_t)b07;
        p[0x08] = (uint8_t)b08;
        p[0x32] = (uint8_t)b32;

        rx8_dtc_handler_610fa();

        printf("%08X %04X %02X %02X %02X %08X\n",
               (uint32_t)*(volatile uint32_t *)(uintptr_t)LONG_CELL,
               (uint16_t)*(volatile uint16_t *)(uintptr_t)FLAG_CELL,
               p[0x07], p[0x08], p[0x32],
               checksum());
    }
    return 0;
}
