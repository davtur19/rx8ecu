/* ============================================================================
 * oracle_calc_decel_fuel_cut_445aa.c  —  host rig for
 *                              rx8_calc_decel_fuel_cut_445aa @0x445AA
 * ============================================================================
 * Compile together with samples/src/rx8_calc_decel_fuel_cut_445aa.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens
 * (floats shipped as raw IEEE-754 single-precision bits so the round trip
 * through the pipe is exact on both sides):
 *
 *     dcl <fen> <cdis> <tclosed> <t50>
 *         <th> <spd> <thr88> <ovr> <den> <mode> <acc> <cab8> <sc>
 *                                             -> <cab5> <caac>
 *
 *   fen, cdis : bytes of the ROM calibration flags at 0x7B3DC / 0x7B3DD
 *   tclosed   : float bits of the ROM calibration f32 at 0x7B418 (0.01)
 *   t50       : float bits of the ROM calibration f32 at 0x7B41C (50.0)
 *               (shipped inline so the oracle's mapped ROM page carries exactly
 *               the stock 60E1D400.bin values the emulator reads)
 *   th, spd   : float bits of RAM[0xFFFFCA30 / 0xFFFFCA38]
 *   thr88     : float bits of RAM[0xFFFFCA88] (throttle-position threshold)
 *   ovr       : RAM[0xFFFFCABB] override flag
 *   den       : RAM[0xFFFFCAB9] decel-fuel-cut enable
 *   mode      : RAM[0xFFFFCAB4] fuel-cut mode
 *   acc       : RAM[0xFFFFCAAC] hysteresis accumulator (pre-state)
 *   cab8      : RAM[0xFFFFCAB8] decel permission flag #2
 *   sc        : RAM[0xFFFFCAB6] secondary-cut flag
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the RAM cells AND the ROM calibration page, seeds every byte and
 * prints the two post-state bytes (fuel-cut flag RAM[0xFFFFCAB5], accumulator
 * RAM[0xFFFFCAAC]).  It contains NO copy of the function logic — that lives
 * solely in the reconstructed source under test.
 *
 * Endianness: the host is little-endian; every float is moved into place with
 * memcpy() of the numeric bit pattern (the same value the ROM stores
 * big-endian on the SH-2E), so the compare inside the function sees exactly
 * the value the emulator compares.  The two output cells are plain u8 bytes
 * and compare numerically.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x0007B000  ROM calibration page (0x7B3DC/0x7B3DD flags, 0x7B418/0x7B41C f32)
 *   0xFFFFC000  RAM[0xFFFFCA30/38/88 f32, 0xFFFFCAB4..0xFFFFCABB bytes]
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_calc_decel_fuel_cut_445aa is not (yet) in rx8_samples.h — the shared
 * header is owned by the samples build.  The reconstructed source itself
 * carries the authoritative definition (src/rx8_calc_decel_fuel_cut_445aa.c);
 * this prototype mirrors it. */
void rx8_calc_decel_fuel_cut_445aa(void);

#define ROM_FEN_ADDR       0x0007B3DCu   /* u8    feature enable (== 0x01)   */
#define ROM_CDIS_ADDR      0x0007B3DDu   /* u8    feature disable (== 0x00)  */
#define ROM_TCLOSED_ADDR   0x0007B418u   /* float throttle-closed threshold  */
#define ROM_T50_ADDR       0x0007B41Cu   /* float secondary RPM threshold    */
#define RAM_THROTTLE_ADDR  0xFFFFCA30u   /* float throttle position          */
#define RAM_SPEED_ADDR     0xFFFFCA38u   /* float engine speed / over-run    */
#define RAM_THR_ADDR       0xFFFFCA88u   /* float throttle-position threshold*/
#define RAM_OVERRIDE_ADDR  0xFFFFCABBu   /* u8    override flag              */
#define RAM_DEN_ADDR       0xFFFFCAB9u   /* u8    decel-fuel-cut enable      */
#define RAM_MODE_ADDR      0xFFFFCAB4u   /* u8    fuel-cut mode              */
#define RAM_ACCUM_ADDR     0xFFFFCAACu   /* u8    hysteresis accumulator     */
#define RAM_CAB8_ADDR      0xFFFFCAB8u   /* u8    decel permission #2        */
#define RAM_SC_ADDR        0xFFFFCAB6u   /* u8    secondary-cut flag         */
#define RAM_FLAG_ADDR      0xFFFFCAB5u   /* u8    fuel-cut flag (output)     */

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

static float bits2f(uint32_t u)
{
    float f;
    memcpy(&f, &u, sizeof f);           /* LE host: numeric value preserved */
    return f;
}

int main(void)
{
    char line[256];

    map_page(ROM_FEN_ADDR);
    map_page(RAM_THROTTLE_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        char *tok;
        unsigned long fen, cdis, tclosed, t50;
        unsigned long th, spd, thr88, ovr, den, mode, acc, cab8, sc;

        tok = strtok(line, " \t\r\n");
        if (!tok) {
            continue;                   /* blank line */
        }
        if (strcmp(tok, "dcl") != 0) {
            fprintf(stderr, "bad opcode: %s\n", tok);
            return 2;
        }
        fen    = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        cdis   = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        tclosed = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        t50    = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        th     = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        spd    = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        thr88  = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        ovr    = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        den    = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        mode   = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        acc    = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        cab8   = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        sc     = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);

        /* Seed the ROM calibration page with the shipped (stock) values. */
        *(volatile uint8_t *)(uintptr_t)ROM_FEN_ADDR   = (uint8_t)fen;
        *(volatile uint8_t *)(uintptr_t)ROM_CDIS_ADDR  = (uint8_t)cdis;
        *(volatile float   *)(uintptr_t)ROM_TCLOSED_ADDR = bits2f((uint32_t)tclosed);
        *(volatile float   *)(uintptr_t)ROM_T50_ADDR     = bits2f((uint32_t)t50);

        /* Seed the input RAM cells. */
        *(volatile float   *)(uintptr_t)RAM_THROTTLE_ADDR = bits2f((uint32_t)th);
        *(volatile float   *)(uintptr_t)RAM_SPEED_ADDR    = bits2f((uint32_t)spd);
        *(volatile float   *)(uintptr_t)RAM_THR_ADDR      = bits2f((uint32_t)thr88);
        *(volatile uint8_t *)(uintptr_t)RAM_OVERRIDE_ADDR = (uint8_t)ovr;
        *(volatile uint8_t *)(uintptr_t)RAM_DEN_ADDR      = (uint8_t)den;
        *(volatile uint8_t *)(uintptr_t)RAM_MODE_ADDR     = (uint8_t)mode;
        *(volatile uint8_t *)(uintptr_t)RAM_ACCUM_ADDR    = (uint8_t)acc;
        *(volatile uint8_t *)(uintptr_t)RAM_CAB8_ADDR     = (uint8_t)cab8;
        *(volatile uint8_t *)(uintptr_t)RAM_SC_ADDR       = (uint8_t)sc;

        rx8_calc_decel_fuel_cut_445aa();

        printf("%02X %02X\n",
               *(volatile uint8_t *)(uintptr_t)RAM_FLAG_ADDR,
               *(volatile uint8_t *)(uintptr_t)RAM_ACCUM_ADDR);
    }
    return 0;
}
