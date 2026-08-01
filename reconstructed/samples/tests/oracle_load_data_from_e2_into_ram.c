/* ============================================================================
 * oracle_load_data_from_e2_into_ram.c — host rig for rx8_load_data_from_e2_into_ram
 * ============================================================================
 * Compile together with src/rx8_load_data_from_e2_into_ram.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     e2 <mode> <a> <b>
 *        mode 0: REAL retry hook (0xC0A8); a = 16-bit GPIO word @0xFFFFF738
 *                (bit 0x0800 SET -> retry returns 0 -> copy path; else abort)
 *        mode 1: STUBBED retry hook; a = 0 or 1 (the two polls' result)
 *        mode 2: STUBBED retry = 0 + half-index-varying flash stub (copy path)
 *        b     : flash word low byte (modes 0/1; sign-extended like the ROM's
 *                `mov #imm,r0` stub) and seed for the initial shadow fill
 *
 *   -> <ret> <c502> <c504> <prim:512hex> <comp:512hex>
 *
 * ret    : r0 after the call = E2IntoRAM return (1 abort / 0 copy)
 * c502   : 16-bit half_start scratch word @0xFFFFC502 (copy path only)
 * c504   : 16-bit half_end   scratch word @0xFFFFC504 (copy path only)
 * prim   : 256 primary   shadow bytes @0xFFFFC2FE (hex, 512 chars)
 * comp   : 256 complement shadow bytes @0xFFFFC3FE (hex, 512 chars)
 *
 * The oracle contains the porting layer ONLY (E2IntoRAM + hardware stubs,
 * faithful to c/E2IntoRAM.c); the function under test lives solely in
 * src/rx8_load_data_from_e2_into_ram.c.  It mmap()s the page backing the
 * EEPROM shadow + scratch (same trick as tests/host_oracle.c) so the C code
 * writes real memory at the ROM addresses.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0x36BD6 — boot loader wrapper (see rx8_load_data_from_e2_into_ram.c). */
void rx8_load_data_from_e2_into_ram(void);

/* ---- EEPROM shadow / scratch (verified addresses, c/eeprom_immo.h) ---- */
#define E2_PRIMARY_BASE    ((volatile uint8_t *)0xFFFFC2FE)
#define E2_COMPLEMENT_BASE ((volatile uint8_t *)0xFFFFC3FE)
#define E2_SCRATCH_BASE    ((volatile uint8_t *)0xFFFFC502)
#define E2_SHADOW_PAGE     ((uintptr_t)0xFFFFC000)   /* backs C2FE..C505 */

/* ---- hardware stubs (mirror the harness' RAM-overlay stubs) ---- */
static int      g_retry_val;     /* e2_retry() result: 0 or 1        */
static int      g_flash_mode;    /* 0 = const byte; 1 = 0x0600+half  */
static uint8_t  g_flash_const;   /* constant flash byte (modes 0/1)   */
static uint8_t  g_e2_ret;        /* last E2IntoRAM return value       */

/* ---- SPI / SR helper stubs (c/eeprom_immo.h externs) ---- */
uint32_t getSR(uint32_t arg);                 /* 0x3920 */
void     setSR(uint32_t val);                 /* 0x3934 */
int      e2_retry(void);                      /* 0xC0A8 */
uint16_t e2_flash_read(uint32_t flashaddr);   /* 0xBFCA */

uint32_t getSR(uint32_t arg)
{
    (void)arg;
    return 0xF0u;               /* SR & 0xF0 with the default SR = 0xF0 */
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
    if (g_flash_mode == 1) {
        uint32_t half = (flashaddr >> 16) & 0xFF;
        return (uint16_t)(0x0600u + half);   /* mov r4,r0; shlr16 r0 */
    }
    /* `mov #imm,r0` stub: an 8-bit immediate is SIGN-extended to 32 bits. */
    return (uint16_t)(int8_t)g_flash_const;
}

/* ---- E2IntoRAM @0x38F58, faithful to the lift c/E2IntoRAM.c ---- */
uint8_t E2IntoRAM(uint16_t e2_addr, uint8_t length)
{
    volatile uint8_t *primary    = E2_PRIMARY_BASE;
    volatile uint8_t *complement = E2_COMPLEMENT_BASE;
    uint32_t saved_sr = getSR(0x10);
    uint8_t  result = 0;

    /* Poll the SPI retry hook twice; if both report busy, give up now. */
    if (e2_retry() == 1 && e2_retry() == 1)
        result = 1;

    if (result != 0) {
        setSR(saved_sr);
        g_e2_ret = result;
        return result;
    }

    /* Half-word window covering [e2_addr, e2_addr + length). */
    uint32_t end_raw = (uint32_t)(uint8_t)length + (uint32_t)e2_addr - 1;
    uint8_t  t       = ((int32_t)end_raw < 0) ? 1 : 0;
    uint16_t half_start = (uint16_t)(e2_addr >> 1);
    uint16_t half_end   = (uint16_t)((end_raw + t) >> 1);

    /* Scratch half-window (0xFFFFC502 = half_start, 0xFFFFC504 = half_end). */
    *(volatile uint16_t *)(E2_SCRATCH_BASE)     = half_start;
    *(volatile uint16_t *)(E2_SCRATCH_BASE + 2) = half_end;

    for (uint16_t half = half_start; half <= half_end; half++) {
        uint32_t flash_addr = 0x06000000UL + (((uint32_t)(half & 0xFF)) << 16);
        uint16_t word       = e2_flash_read(flash_addr);
        uint8_t  high       = (uint8_t)(word >> 8);   /* E2[2k]   */
        uint8_t  low        = (uint8_t)(word & 0xFF); /* E2[2k+1] */
        uint16_t byte_idx   = (uint16_t)(half << 1);

        primary[byte_idx]     = high;
        complement[byte_idx]  = (uint8_t)~high;
        primary[byte_idx + 1] = low;
        complement[byte_idx + 1] = (uint8_t)~low;
    }

    setSR(saved_sr);
    g_e2_ret = result;
    return result;
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
    char line[256];

    map_page(E2_SHADOW_PAGE);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long mode, a, b;
        size_t i;

        if (sscanf(line, "e2 %lx %lx %lx", &mode, &a, &b) != 3) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        if (mode == 0) {            /* real retry hook: bit 0x0800 of 0xFFFFF738 */
            g_retry_val  = ((a & 0x0800UL) == 0) ? 1 : 0;
            g_flash_mode = 0;
            g_flash_const = (uint8_t)b;
        } else if (mode == 1) {     /* stubbed retry: a = 0 or 1 */
            g_retry_val  = (int)(a != 0);
            g_flash_mode = 0;
            g_flash_const = (uint8_t)b;
        } else {                    /* mode 2: half-index-varying flash word */
            g_retry_val  = 0;
            g_flash_mode = 1;
            g_flash_const = (uint8_t)b;
        }

        /* Initial shadow: deterministic (seed b) primary + complement pairs. */
        for (i = 0; i < 256; i++) {
            uint8_t v = (uint8_t)((b + 7 * i) & 0xFF);
            E2_PRIMARY_BASE[i] = v;
            E2_COMPLEMENT_BASE[i] = (uint8_t)~v;
        }
        *(volatile uint16_t *)(E2_SCRATCH_BASE)     = 0;
        *(volatile uint16_t *)(E2_SCRATCH_BASE + 2) = 0;

        g_e2_ret = 0;
        rx8_load_data_from_e2_into_ram();   /* <-- the code under test */

        printf("%02X %04X %04X ",
               (unsigned)g_e2_ret,
               (unsigned)*(volatile uint16_t *)(E2_SCRATCH_BASE),
               (unsigned)*(volatile uint16_t *)(E2_SCRATCH_BASE + 2));
        for (i = 0; i < 256; i++) printf("%02X", E2_PRIMARY_BASE[i]);
        printf(" ");
        for (i = 0; i < 256; i++) printf("%02X", E2_COMPLEMENT_BASE[i]);
        printf("\n");
    }
    return 0;
}
