/* ============================================================================
 * oracle_calc_fan1_control.c — host rig for rx8_calc_fan1_control
 * ============================================================================
 * Compile together with samples/src/rx8_calc_fan1_control.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     fan1 <t1on> <t1hy> <t2on> <t2hy> <t_bits>
 *          <be16> <be17> <be0d>
 *          <b13d> <aae0> <be0c> <cd06> <a96a> <bff5> <bdd4> <bdd6>
 *          <d07c> <d0e4> <d2a0> <d2a5> <d29f>
 *                                          -> <be16> <be17> <be0d>
 *
 *   t1on/t1hy/t2on/t2hy : raw bits of the four hysteresis calibration
 *            floats the ROM reads at 0x7793C/0x77940/0x77944/0x77948 (the
 *            harness ships the values verbatim from the stock bin)
 *   t_bits : raw IEEE-754 single-precision bits of the temperature input
 *            (RAM[0xFFFFAA10]) — passed as bits so float->hex round-trips
 *            exactly on both sides of the pipe (NaN/Inf included)
 *   be16/be17/be0d : pre-state of the three RAM output cells (the function
 *            holds the relays between the hysteresis thresholds)
 *   b13d..d29f : pre-state of the 13 fan-enable status cells
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the RAM cells AND the ROM calibration table, seeds every
 * byte and prints the three post-state bytes.  It contains NO copy of the
 * function logic — that lives solely in the reconstructed source under test.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00077000  ROM calibration floats (0x7793C..0x77948)
 *   0xFFFFA000  RAM[0xFFFFAA10] temp + RAM[0xFFFFAAE0/0xFFFFA96A] status
 *   0xFFFFB000  RAM[0xFFFFBE16/17/0D] fan cells + status 0xFFFFB13D/
 *              0xFFFFBE0C/0xFFFFBFF5/0xFFFFBDD4/0xFFFFBDD6
 *   0xFFFFC000  RAM[0xFFFFCD06] status
 *   0xFFFFD000  RAM[0xFFFFD07C/0xFFFFD0E4/0xFFFFD2A0/0xFFFFD2A5/0xFFFFD29F]
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0x303A6 — cooling-fan relay control (see rx8_calc_fan1_control.c); not in
 * rx8_samples.h (owned by the samples build), so prototype it here. */
void rx8_calc_fan1_control(void);

#define ROM_TABLE_BASE    0x00077000u   /* page of the cal floats below    */
#define ROM_T1_ON_ADDR    0x0007793Cu
#define ROM_T1_HY_ADDR    0x00077940u
#define ROM_T2_ON_ADDR    0x00077944u
#define ROM_T2_HY_ADDR    0x00077948u
#define FAN_TEMP_ADDR     0xFFFFAA10u   /* f32 temperature input           */
#define FAN1_OUT_ADDR     0xFFFFBE16u   /* u8 fan 1 relay command          */
#define FAN2_OUT_ADDR     0xFFFFBE17u   /* u8 fan 2 relay command          */
#define FAN_EN_ADDR       0xFFFFBE0Du   /* u8 fan enable latch             */

/* 13 status cells of the enable-latch branch tree, in vector order. */
static const uint32_t STATUS_ADDRS[13] = {
    0xFFFFB13Du, 0xFFFFAAE0u, 0xFFFFBE0Cu, 0xFFFFCD06u, 0xFFFFA96Au,
    0xFFFFBFF5u, 0xFFFFBDD4u, 0xFFFFBDD6u, 0xFFFFD07Cu, 0xFFFFD0E4u,
    0xFFFFD2A0u, 0xFFFFD2A5u, 0xFFFFD29Fu,
};

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

static void wrf32(uint32_t addr, uint32_t bits)
{
    /* Materialise the float from its raw bit pattern in HOST byte order.
     * The ROM stores/loads big-endian, but the reconstructed C reads the
     * cell as a native-endian float, so the host memory image must carry
     * the native byte order of the bit pattern (memcpy = exact value). */
    float v;
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)addr = v;
}

int main(void)
{
    char line[256];

    map_page(ROM_TABLE_BASE);
    map_page(FAN_TEMP_ADDR);
    map_page(FAN1_OUT_ADDR);
    map_page(0xFFFFCD06u);
    map_page(0xFFFFD000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long t, t1on, t1hy, t2on, t2hy;
        unsigned long be16, be17, be0d;
        unsigned long s[13];
        char op[8];
        int i, n = sscanf(line,
                          "%7s %lx %lx %lx %lx %lx %lx %lx %lx"
                          " %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                          op, &t1on, &t1hy, &t2on, &t2hy,
                          &t, &be16, &be17, &be0d,
                          &s[0], &s[1], &s[2], &s[3], &s[4], &s[5], &s[6],
                          &s[7], &s[8], &s[9], &s[10], &s[11], &s[12]);
        if (n != 22 || strcmp(op, "fan1") != 0) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the ROM calibration floats exactly as the stock bin has them. */
        wrf32(ROM_T1_ON_ADDR, (uint32_t)t1on);
        wrf32(ROM_T1_HY_ADDR, (uint32_t)t1hy);
        wrf32(ROM_T2_ON_ADDR, (uint32_t)t2on);
        wrf32(ROM_T2_HY_ADDR, (uint32_t)t2hy);

        /* Seed the temperature input and all RAM pre-states. */
        wrf32(FAN_TEMP_ADDR, (uint32_t)t);
        *(volatile uint8_t *)(uintptr_t)FAN1_OUT_ADDR = (uint8_t)be16;
        *(volatile uint8_t *)(uintptr_t)FAN2_OUT_ADDR = (uint8_t)be17;
        *(volatile uint8_t *)(uintptr_t)FAN_EN_ADDR   = (uint8_t)be0d;
        for (i = 0; i < 13; i++) {
            *(volatile uint8_t *)(uintptr_t)STATUS_ADDRS[i] = (uint8_t)s[i];
        }

        rx8_calc_fan1_control();

        printf("%02X %02X %02X\n",
               *(volatile uint8_t *)(uintptr_t)FAN1_OUT_ADDR,
               *(volatile uint8_t *)(uintptr_t)FAN2_OUT_ADDR,
               *(volatile uint8_t *)(uintptr_t)FAN_EN_ADDR);
    }
    return 0;
}
