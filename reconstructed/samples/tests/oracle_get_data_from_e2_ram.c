/* ============================================================================
 * oracle_get_data_from_e2_ram.c — host rig for rx8_get_data_from_e2_ram
 * ============================================================================
 * Compile together with src/rx8_get_data_from_e2_ram.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     e2 <retry> <flash> <seed> <p:64hex> <c:64hex>
 *        retry : byte loaded by the stubbed SPI-retry hook @0xC0A8
 *                (0 -> "recovered": corrupt pairs rebuilt from FLASH;
 *                 != 0 -> "retry failed": error flag, byte not copied)
 *        flash : 8-bit immediate loaded by the stubbed flash reader @0xBFCA;
 *                SIGN-extended to 32 bits like `mov #imm,r0`
 *        seed  : destination pre-fill seed: dest[0xFFFFC240+k] = (seed+3k)&0xFF
 *        p     : 32-byte EEPROM primary   shadow (E2[0x00..0x1F])    @0xFFFFC2FE
 *        c     : 32-byte EEPROM complement shadow (~E2)              @0xFFFFC3FE
 *
 *   -> <r0> <dest:60hex> <p:64hex> <c:64hex>
 *
 * r0   : r0 after the call = getFromE2's return for the LAST call
 *        (error flag of EEPROM[0x1E]: 1 = corrupt + failed retry)
 * dest : 30 destination bytes: 0xFFFFC242, 0xFFFFC243, 0xFFFFC244
 *        then 0xFFFFC2D8..0xFFFFC2F2 (the E2 working-copy block)
 * p,c  : the 32-byte primary/complement shadows AFTER the call
 *        (flash recovery rewrites the corrupt pair in place)
 *
 * The oracle contains the porting layer ONLY (getFromE2 + the getSR/setSR/
 * e2_retry/e2_flash_read stubs, faithful to c/getFromE2.c); the function
 * under test lives solely in src/rx8_get_data_from_e2_ram.c.  It mmap()s
 * the page backing the working-copy + E2 shadow RAM (same trick as
 * tests/oracle_load_data_from_e2_into_ram.c) so the C code writes real
 * memory at the ROM addresses.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0x36C1C — EEPROM shadow -> working-copy copy-out (see the sample source). */
void rx8_get_data_from_e2_ram(void);

/* ---- RAM windows (verified addresses, see c/eeprom_immo.h + the sample) ---- */
#define E2_WORK_PREFILL_BASE ((volatile uint8_t *)0xFFFFC240)   /* pre-fill C240..C2FD */
#define E2_WORK_CAN_BASE     ((volatile uint8_t *)0xFFFFC242)   /* CAN shadow C242..C244 */
#define E2_WORK_BASE         ((volatile uint8_t *)0xFFFFC2D8)   /* working copies C2D8..C2F2 */
#define E2_PRIMARY_BASE      ((volatile uint8_t *)0xFFFFC2FE)   /* 256-byte primary shadow */
#define E2_COMPLEMENT_BASE   ((volatile uint8_t *)0xFFFFC3FE)   /* 256-byte complement shadow */
#define E2_SHADOW_PAGE       ((uintptr_t)0xFFFFC000)            /* backs C240..C4FF */

/* ---- hardware stubs (mirror the harness' RAM-overlay stubs) ---- */
static int      g_retry_val;     /* e2_retry() result: 0 = recover, !=0 = fail */
static uint8_t  g_flash_const;   /* e2_flash_read() 8-bit imm (sign-extended)  */
static uint8_t  g_last_ret;      /* getFromE2 return of the last call (r0)     */

/* ---- getSR / setSR / e2_retry / e2_flash_read externs (c/eeprom_immo.h) ---- */
uint32_t getSR(uint32_t arg);
void     setSR(uint32_t val);
int      e2_retry(void);
uint16_t e2_flash_read(uint32_t flashaddr);

uint32_t getSR(uint32_t arg)
{
    (void)arg;
    return 0xF0u;               /* stub: SR & 0xF0 with the default SR = 0xF0 */
}

void setSR(uint32_t val)
{
    (void)val;                  /* ldc r4,sr — no observable RAM effect */
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

/* ---- getFromE2_E2ADDR_RAMADDR_LEN @0x39170, faithful to the lift c/getFromE2.c ---- */
uint8_t getFromE2_E2ADDR_RAMADDR_LEN(uint16_t e2addr, uint8_t *ramaddr, uint8_t len)
{
    volatile uint8_t *primary    = E2_PRIMARY_BASE;
    volatile uint8_t *complement = E2_COMPLEMENT_BASE;
    uint32_t saved_sr = getSR(0x10);
    uint8_t  error_flag = 0;

    while (len != 0) {
        uint16_t idx = e2addr;
        uint8_t  d   = primary[idx];
        uint8_t  c   = complement[idx];

        if (d == (uint8_t)~c) {
            *ramaddr = d;                   /* valid pair: copy */
        } else {
            int ret = e2_retry();           /* jsr 0xC0A8 */
            if (ret == 0) {
                /* Recover from the FLASH backup: word per byte pair. */
                uint32_t flash_addr = 0x06000000UL +
                                      (((uint32_t)((idx >> 1) & 0xFF)) << 16);
                uint16_t raw = e2_flash_read(flash_addr);   /* jsr 0xBFCA */
                uint8_t  val = (idx & 1) ? (uint8_t)(raw & 0xFF)
                                         : (uint8_t)((raw >> 8) & 0xFF);
                primary[idx]    = val;      /* restore data */
                complement[idx] = (uint8_t)~val;  /* and complement */
                *ramaddr = primary[idx];
            } else {
                error_flag = 1;             /* retry failed */
            }
        }

        len--;                              /* add #0xFF,r9 */
        e2addr++;                           /* add #0x01,r10 */
        ramaddr++;                          /* add #0x01,r12 */
    }

    setSR(saved_sr);
    g_last_ret = error_flag;
    return error_flag;
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
    char line[512];

    map_page(E2_SHADOW_PAGE);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long retry, flash, seed;
        char ptok[80], ctok[80];
        uint8_t p[32], c[32];
        size_t i, k;

        if (sscanf(line, "e2 %lx %lx %lx %64s %64s",
                   &retry, &flash, &seed, ptok, ctok) != 5) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        if (strlen(ptok) != 64 || strlen(ctok) != 64) {
            fprintf(stderr, "bad shadow length: %s", line);
            return 2;
        }
        for (i = 0; i < 32; i++) {
            unsigned v;
            if (sscanf(ptok + 2 * i, "%2x", &v) != 1) return 2;
            p[i] = (uint8_t)v;
            if (sscanf(ctok + 2 * i, "%2x", &v) != 1) return 2;
            c[i] = (uint8_t)v;
        }

        /* Set up the stubs for this vector. */
        g_retry_val  = (retry != 0) ? 1 : 0;
        g_flash_const = (uint8_t)flash;

        /* Destination pre-fill (deterministic, seed-driven) — the error path
         * leaves these untouched, so the pre-fill is part of the comparison. */
        for (k = 0; k < 0xBE; k++) {        /* 0xFFFFC240..0xFFFFC2FD */
            E2_WORK_PREFILL_BASE[k] = (uint8_t)((seed + 3 * k) & 0xFF);
        }
        /* E2 shadows (primary + complement) for E2[0x00..0x1F]. */
        for (i = 0; i < 32; i++) {
            E2_PRIMARY_BASE[i]    = p[i];
            E2_COMPLEMENT_BASE[i] = c[i];
        }

        g_last_ret = 0;
        rx8_get_data_from_e2_ram();         /* <-- the code under test */

        /* Emit: r0 + 30 dest bytes (CAN shadow, then working-copy block)
         * + the 32-byte primary/complement shadows after the call. */
        printf("%02X ", (unsigned)g_last_ret);
        for (i = 0; i < 3; i++) printf("%02X", E2_WORK_CAN_BASE[i]);
        for (k = 0; k < 0x1B; k++) printf("%02X", E2_WORK_BASE[k]);
        printf(" ");
        for (i = 0; i < 32; i++) printf("%02X", E2_PRIMARY_BASE[i]);
        printf(" ");
        for (i = 0; i < 32; i++) printf("%02X", E2_COMPLEMENT_BASE[i]);
        printf("\n");
    }
    return 0;
}
