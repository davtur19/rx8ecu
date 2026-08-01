/* ============================================================================
 * oracle_calc_intake_pressure_pid_output.c — host rig for
 * rx8_calc_intake_pressure_pid_output
 * ============================================================================
 * Compile together with samples/src/rx8_calc_intake_pressure_pid_output.c and
 * pipe test vectors on stdin; one vector per line, whitespace-separated hex
 * tokens (floats shipped as raw IEEE-754 single-precision bits so the round
 * trip through the pipe is exact on both sides):
 *
 *     pid <db> <rt> <corr> <chi> <en>
 *         <rpm> <tgt> <err> <cl> <idle> <fc> <lam> <alt> <dflt> <clo>
 *                                             -> <out>
 *
 *   db, rt, corr, chi : float bits of the ROM calibration constants the
 *                       function reads at 0x12600 (deadband), 0x12608 (rpm
 *                       threshold), 0x6E3D8 (-5.0 correction) and 0x6E3F0
 *                       (65.0 clamp high) — shipped inline so the oracle's
 *                       mapped ROM pages carry exactly the stock ROM values
 *   en                : byte of the calibration flag at 0x6E3D4
 *   rpm, tgt, err     : float bits of RAM[0xFFFFB5B8 / 0xFFFFA790 / 0xFFFFBCE4]
 *   cl, idle, fc      : byte inputs RAM[0xFFFFAADA / 0xFFFFCE58 / 0xFFFFBC36]
 *   lam, alt, dflt    : float bits RAM[0xFFFFA9B8 / 0xFFFFA9A8 / 0xFFFFA640]
 *   clo               : float bits RAM[0xFFFFA658] (clamp low)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the two ROM calibration pages, seeds every byte and
 * prints the post-state float bits at RAM[0xFFFFA63C].  It contains NO copy of
 * the function logic — that lives solely in the reconstructed source under
 * test.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00012000  ROM cal table (0x12600 deadband, 0x12608 rpm threshold)
 *   0x0006E000  ROM cal table (0x6E3D4 enable, 0x6E3D8 corr, 0x6E3F0 clamp hi)
 *   0xFFFFA000  RAM[0xFFFFA63C/40/58/90/A9A8/A9B8/AADA]
 *   0xFFFFB000  RAM[0xFFFFB5B8 rpm, 0xFFFFBC36 fuel cut, 0xFFFFBCE4 error]
 *   0xFFFFC000  RAM[0xFFFFCE58 idle flag]
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_calc_intake_pressure_pid_output is not (yet) in rx8_samples.h — the
 * shared header is owned by the samples build.  The reconstructed source
 * itself carries the authoritative definition
 * (src/rx8_calc_intake_pressure_pid_output.c); this prototype mirrors it. */
void rx8_calc_intake_pressure_pid_output(void);

#define ROM_DB_ADDR       0x00012600u   /* float 1e-5 deadband              */
#define ROM_RT_ADDR       0x00012608u   /* float 2000.0 rpm threshold       */
#define ROM_EN_ADDR       0x0006E3D4u   /* u8    enable flag (== 0 stock)   */
#define ROM_CORR_ADDR     0x0006E3D8u   /* float -5.0 correction            */
#define ROM_CHI_ADDR      0x0006E3F0u   /* float 65.0 clamp high            */
#define RAM_RPM_ADDR      0xFFFFB5B8u   /* float engine speed               */
#define RAM_TARGET_ADDR   0xFFFFA790u   /* float intake pressure target     */
#define RAM_ERROR_ADDR    0xFFFFBCE4u   /* float intake pressure error      */
#define RAM_CL_ACTIVE     0xFFFFAADAu   /* u8    closed-loop active         */
#define RAM_IDLE_FLAG     0xFFFFCE58u   /* u8    idle/overrun flag          */
#define RAM_FUEL_CUT      0xFFFFBC36u   /* u8    fuel-cut active            */
#define RAM_LAMBDA_ADDR   0xFFFFA9B8u   /* float lambda status              */
#define RAM_ALT_REF       0xFFFFA9A8u   /* float alternate reference        */
#define RAM_DEFAULT_REF   0xFFFFA640u   /* float default reference          */
#define RAM_CLAMP_LO      0xFFFFA658u   /* float clamp low                  */
#define RAM_PID_OUTPUT    0xFFFFA63Cu   /* float written result             */

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

    map_page(ROM_DB_ADDR);
    map_page(ROM_EN_ADDR);
    map_page(RAM_RPM_ADDR);
    map_page(RAM_CL_ACTIVE);
    map_page(RAM_IDLE_FLAG);

    while (fgets(line, sizeof line, stdin)) {
        char *tok;
        unsigned long db, rt, corr, chi, en;
        unsigned long rpm, tgt, err, cl, idle, fc, lam, alt, dflt, clo;
        uint32_t u;
        float f;

        tok = strtok(line, " \t\r\n");
        if (!tok) {
            continue;                       /* blank line */
        }
        if (strcmp(tok, "pid") != 0) {
            fprintf(stderr, "bad opcode: %s\n", tok);
            return 2;
        }
        db   = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        rt   = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        corr = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        chi  = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        en   = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        rpm  = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        tgt  = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        err  = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        cl   = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        idle = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        fc   = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        lam  = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        alt  = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        dflt = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        clo  = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);

        /* Seed the ROM calibration pages with the shipped (stock) values. */
        u = (uint32_t)db;  memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)ROM_DB_ADDR   = f;
        u = (uint32_t)rt;  memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)ROM_RT_ADDR   = f;
        *(volatile uint8_t *)(uintptr_t)ROM_EN_ADDR   = (uint8_t)en;
        u = (uint32_t)corr; memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)ROM_CORR_ADDR = f;
        u = (uint32_t)chi;  memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)ROM_CHI_ADDR  = f;

        /* Seed the input RAM cells. */
        u = (uint32_t)rpm; memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)RAM_RPM_ADDR    = f;
        u = (uint32_t)tgt; memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)RAM_TARGET_ADDR = f;
        u = (uint32_t)err; memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)RAM_ERROR_ADDR  = f;
        *(volatile uint8_t *)(uintptr_t)RAM_CL_ACTIVE   = (uint8_t)cl;
        *(volatile uint8_t *)(uintptr_t)RAM_IDLE_FLAG   = (uint8_t)idle;
        *(volatile uint8_t *)(uintptr_t)RAM_FUEL_CUT    = (uint8_t)fc;
        u = (uint32_t)lam; memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)RAM_LAMBDA_ADDR = f;
        u = (uint32_t)alt; memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)RAM_ALT_REF     = f;
        u = (uint32_t)dflt; memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)RAM_DEFAULT_REF = f;
        u = (uint32_t)clo; memcpy(&f, &u, sizeof f);
        *(volatile float   *)(uintptr_t)RAM_CLAMP_LO    = f;

        rx8_calc_intake_pressure_pid_output();

        f = *(volatile float *)(uintptr_t)RAM_PID_OUTPUT;
        memcpy(&u, &f, sizeof u);
        printf("%08X\n", (unsigned)u);
    }
    return 0;
}
