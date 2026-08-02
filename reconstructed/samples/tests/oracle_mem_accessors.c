/* ============================================================================
 * oracle_mem_accessors.c  —  host test rig for the redundant-RAM accessor
 * family of samples/src/rx8_mem_accessors.c
 * ============================================================================
 * Compile together with samples/src/rx8_mem_accessors.c (see
 * harness_mem_accessors.py for the exact command) and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     u8  <cell> <val2>   -> <r0> <cell>     updateMemoryAtAddress_8bit
 *     u16 <cell> <val4>   -> <r0> <cell>     updateMemoryAtAddress_16bit
 *     u32 <cell> <val8>   -> <r0> <cell>     updateMemoryAtAddress_32bit_ADDR_VAL
 *     r8  <cell> <dflt2>  -> <ret> <cell>    readValue_8bit_ADDRESS_VAL
 *     r16 <cell> <dflt4>  -> <ret> <cell>    readValue_16bit_ADDRESS_VAL
 *     r32 <cell> <dflt8>  -> <ret> <cell>    readValue_32bit_ADDRESS_VAL
 *     rf  <cell> <dflt8>  -> <ret> <cell>    readValue_float_DEFAULTVAL_ADDRESS
 *     v8  <cell>          -> <ret> <cell>    validateAddressCopy_8bit_ADDRESS
 *     v16 <cell>          -> <ret> <cell>    validateAddressCopy_16bit_ADDRESS
 *     vf  <cell>          -> <ret> <cell>    validateAddressCopy_float_ADDRESS
 *     v32 <cell>          -> <ret> <cell>    validateAddressCopy_32bit_ADDRESS
 *
 * <cell>  = exactly 16 hex digits = the 8-byte big-endian cell image
 *           (byte0 = address+0 ... byte7 = address+7), matching the SH-2E's
 *           big-endian cell layout.  <ret> is the lifted result width:
 *           %02X (u8 / 0/1), %04X (u16), %08X (u32 / float bits), %08X for the
 *           writes (their r0 is always 0).  The trailing <cell> is the 8-byte
 *           cell image AFTER the call, so the oracle also captures the
 *           checksum "scrub" side-effect of the two validate_32/float reads
 *           byte-for-byte.
 *
 * The oracle contains NO copy of the accessor logic — that lives solely in
 * src/rx8_mem_accessors.c.  The cell is held in a plain local buffer and
 * passed to the accessors; multi-byte cells are assembled/disassembled with
 * EXPLICIT big-endian byte packing so host endianness does not matter.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <string.h>

/* Declared locally: rx8_samples.h cannot be extended (parallel agents), and
 * this test rig only needs these eleven functions. */
void     updateMemoryAtAddress_8bit(uint16_t *addr, uint8_t val);
void     updateMemoryAtAddress_16bit(uint32_t *addr, uint16_t val);
void     updateMemoryAtAddress_32bit_ADDR_VAL(uint8_t *addr, uint32_t val);
uint8_t  readValue_8bit(const uint8_t *addr, uint8_t dflt);
uint16_t readValue_16bit(const uint16_t *addr, uint16_t dflt);
uint32_t readValue_32bit_ADDRESS_VAL(const uint8_t *addr, uint32_t dflt);
float    readValue_float_DEFAULTVAL_ADDRESS(const uint8_t *addr, float dflt);
int      validateAddressCopy_8bit_ADDRESS(const uint8_t *addr);
int      validateAddressCopy_16bit_ADDRESS(const uint8_t *addr);
int      validateAddressCopy_float_ADDRESS(uint8_t *addr);
int      validateAddressCopy_32bit_ADDRESS(uint8_t *addr);

static uint32_t f2b(float f)
{
    union { float f; uint32_t u; } x;
    x.f = f;
    return x.u;
}

static float b2f(uint32_t u)
{
    union { float f; uint32_t u; } x;
    x.u = u;
    return x.f;
}

static unsigned hexval(char c)
{
    if (c >= '0' && c <= '9') return (unsigned)(c - '0');
    if (c >= 'a' && c <= 'f') return (unsigned)(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return (unsigned)(c - 'A' + 10);
    return 0xFF;
}

/* Parse a 16-digit big-endian cell image into buf[0..7]. */
static int parse_cell(const char *s, uint8_t buf[8])
{
    int i;
    if (strlen(s) != 16)
        return -1;
    for (i = 0; i < 8; i++) {
        unsigned hi = hexval(s[2 * i]);
        unsigned lo = hexval(s[2 * i + 1]);
        if (hi > 15 || lo > 15)
            return -1;
        buf[i] = (uint8_t)((hi << 4) | lo);
    }
    return 0;
}

static void print_cell(const uint8_t buf[8])
{
    int i;
    for (i = 0; i < 8; i++)
        printf("%02X", buf[i]);
}

int main(void)
{
    char line[128];

    while (fgets(line, sizeof line, stdin)) {
        char op[8];
        char cell[32];
        unsigned long a = 0;
        uint8_t buf[8];
        if (sscanf(line, "%7s %16s %lx", op, cell, &a) < 2) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        if (parse_cell(cell, buf) != 0) {
            fprintf(stderr, "bad cell: %s\n", cell);
            return 2;
        }

        if (op[0] == 'u' && op[1] == '8') {
            updateMemoryAtAddress_8bit((uint16_t *)buf, (uint8_t)a);
            printf("00000000 "); print_cell(buf); printf("\n");
        } else if (op[0] == 'u' && op[1] == '1' && op[2] == '6') {
            updateMemoryAtAddress_16bit((uint32_t *)buf, (uint16_t)a);
            printf("00000000 "); print_cell(buf); printf("\n");
        } else if (op[0] == 'u' && op[1] == '3' && op[2] == '2') {
            updateMemoryAtAddress_32bit_ADDR_VAL(buf, (uint32_t)a);
            printf("00000000 "); print_cell(buf); printf("\n");
        } else if (op[0] == 'r' && op[1] == '8') {
            uint8_t r = readValue_8bit(buf, (uint8_t)a);
            printf("%02X ", (unsigned)r); print_cell(buf); printf("\n");
        } else if (op[0] == 'r' && op[1] == '1' && op[2] == '6') {
            uint16_t r = readValue_16bit((const uint16_t *)buf, (uint16_t)a);
            printf("%04X ", (unsigned)r); print_cell(buf); printf("\n");
        } else if (op[0] == 'r' && op[1] == '3' && op[2] == '2') {
            uint32_t r = readValue_32bit_ADDRESS_VAL(buf, (uint32_t)a);
            printf("%08lX ", (unsigned long)r); print_cell(buf); printf("\n");
        } else if (op[0] == 'r' && op[1] == 'f') {
            float r = readValue_float_DEFAULTVAL_ADDRESS(buf, b2f((uint32_t)a));
            printf("%08lX ", (unsigned long)f2b(r)); print_cell(buf); printf("\n");
        } else if (op[0] == 'v' && op[1] == '8') {
            int r = validateAddressCopy_8bit_ADDRESS(buf);
            printf("%02X ", (unsigned)r); print_cell(buf); printf("\n");
        } else if (op[0] == 'v' && op[1] == '1' && op[2] == '6') {
            int r = validateAddressCopy_16bit_ADDRESS(buf);
            printf("%02X ", (unsigned)r); print_cell(buf); printf("\n");
        } else if (op[0] == 'v' && op[1] == 'f') {
            int r = validateAddressCopy_float_ADDRESS(buf);
            printf("%02X ", (unsigned)r); print_cell(buf); printf("\n");
        } else if (op[0] == 'v' && op[1] == '3' && op[2] == '2') {
            int r = validateAddressCopy_32bit_ADDRESS(buf);
            printf("%02X ", (unsigned)r); print_cell(buf); printf("\n");
        } else {
            fprintf(stderr, "bad op: %s\n", op);
            return 2;
        }
    }
    return 0;
}
