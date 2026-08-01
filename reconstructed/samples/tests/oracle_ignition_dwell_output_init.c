/* ============================================================================
 * oracle_ignition_dwell_output_init.c  —  host test rig for
 *                                        rx8_ignition_dwell_output_init @0x8F62
 * ============================================================================
 * Compile together with src/rx8_ignition_dwell_output_init.c (see
 * harness_ignition_dwell_output_init.py) and pipe test vectors on stdin; one
 * vector per line, 82 space-separated hex bytes:
 *
 *     dwl <a0c4..a0ff (60)> <f626> <f627> <f630 u16> <f650 u16> <f652 u16>
 *         <f654 u16> <f656 u16> <f66c u16> <9f68 f32 y> <9f80 f32 x>
 *                                 -> 74 space-separated hex bytes
 *
 *   a0c4..a0ff : pre-state of RAM 0xFFFFA0C4..0xFFFFA0FF (the four 32-bit
 *                dwell cells, the 0x94C8 dwell-limit word pair at
 *                0xFFFFA0D4/0xFFFFA0D6 and the four 8-byte per-channel
 *                control blocks)
 *   f626/f627  : pre-state of the sensor-chain MMIO bytes 0xFFFFF626/627
 *   f630 u16   : pre-state of MMIO word 0xFFFFF630
 *   f650..f656 : pre-state of the four channel control words (u16 each)
 *   f66c u16   : pre-state of MMIO word 0xFFFFF66C
 *   9f68 f32 y : pre-state of the tail-phase lookup input y (0xFFFF9F68)
 *   9f80 f32 x : pre-state of the tail-phase lookup input x (0xFFFF9F80)
 *
 * The oracle re-implements the caller-side set-up only: it mmap()s the pages
 * backing the cells, seeds the pre-state and prints the post-state (same
 * trick as host_oracle.c).  It ALSO carries the faithful models of the three
 * ROM callees the reconstructed source declares extern — the emulator side
 * of the harness runs the REAL ROM bytes of all three (0x8FCC / 0xAA74 /
 * 0x94C8, the latter including its 2-D u16 lookup @0x213C), so these models
 * must be bit-exact.  See the harness header for the model inventory.
 *
 * FUSED FP: the tail-phase lookup's combines are the ROM's `fmac` (one
 * rounding on a*b+c).  tools/sh2emu.py computes that as ts((double)a*b + c);
 * this oracle uses the identical double-precision-then-single expression via
 * rx8_fmacf() below (verified bit-identical to fmaf() over 3e6 random floats
 * and to the emulator by construction; keeps the build free of -lm).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

/* rx8_ignition_dwell_output_init is not (yet) in rx8_samples.h — the shared
 * header is owned by the samples build.  The reconstructed source itself
 * carries the authoritative definition (src/rx8_ignition_dwell_output_init.c);
 * this prototype mirrors it exactly. */
void rx8_ignition_dwell_output_init(void);

/* ----------------------------------------------------------------------------
 * Faithful models of the three ROM callees (see header comment).
 * ------------------------------------------------------------------------- */

/* Fused multiply-add exactly as tools/sh2emu.py's `ts(f0*fm + fn)`: exact
 * double product + double add, one final rounding to single. */
static inline float rx8_fmacf(float a, float b, float c)
{
    return (float)((double)a * (double)b + (double)c);
}

/* 1-D axis search of ROM helper 0x2624 (verified; see c/2DLookup.c). */
static void rx8_axis_search(const float *ax, int n, float x, int *pi, float *pt)
{
    if (!(x < ax[n - 1]))        { *pi = n - 1; *pt = 0.0f; }
    else if (x < ax[0])          { *pi = 0;     *pt = 0.0f; }
    else {
        int k = 0;
        while (k + 1 < n && !(ax[k] <= x && x < ax[k + 1])) k++;
        *pi = k;
        *pt = (x - ax[k]) / (ax[k + 1] - ax[k]);
    }
}

/* The 2-D u16 lookup @0x213C (ThreeDLookup_FP_16bit, c/3dLookup.c) over the
 * REAL ROM descriptor @0x6C1C0: 9 x 9 axis of RPM (1000..9000) x load
 * (6.5..16.5), 81 u16 cells (row-major [y][x]) @0x7CB20.  The data below is
 * copied verbatim from 60E1D400.bin (harness asserts it at startup). */
static const float RX8_DWELL_AXIS_X[9] = {
    1000.0f, 2000.0f, 3000.0f, 4000.0f, 5000.0f,
    6000.0f, 7000.0f, 8000.0f, 9000.0f
};
static const float RX8_DWELL_AXIS_Y[9] = {
    6.5f, 7.75f, 9.0f, 10.25f, 11.5f, 12.75f, 14.0f, 15.25f, 16.5f
};
static const uint16_t RX8_DWELL_CELLS[81] = {
    1895, 1500, 1188,  890,  712,  595,  510,  445,  395,
    1688, 1332, 1168,  890,  712,  595,  510,  445,  395,
    1520, 1208, 1055,  890,  712,  595,  510,  445,  395,
    1395, 1105,  965,  880,  712,  595,  510,  445,  395,
    1292, 1020,  895,  818,  712,  595,  510,  445,  395,
    1208,  958,  840,  760,  708,  595,  510,  445,  395,
    1105,  895,  785,  712,  662,  595,  510,  445,  395,
     938,  845,  742,  678,  625,  590,  510,  445,  395,
     812,  782,  702,  640,  595,  560,  510,  445,  395,
};

static uint16_t rx8_dwell_lookup_fp16(float x, float y)
{
    const int cx = 9, cy = 9;
    int ix, iy, ix1, iy1;
    float tx, ty, c00, c10, c01, c11, row0, row1, interp;

    rx8_axis_search(RX8_DWELL_AXIS_X, cx, x, &ix, &tx);
    rx8_axis_search(RX8_DWELL_AXIS_Y, cy, y, &iy, &ty);
    ix1 = ix + 1 < cx ? ix + 1 : ix;
    iy1 = iy + 1 < cy ? iy + 1 : iy;

    c00 = (float)RX8_DWELL_CELLS[iy  * cx + ix];
    c10 = (float)RX8_DWELL_CELLS[iy  * cx + ix1];
    c01 = (float)RX8_DWELL_CELLS[iy1 * cx + ix];
    c11 = (float)RX8_DWELL_CELLS[iy1 * cx + ix1];
    row0 = rx8_fmacf(tx, c10 - c00, c00);
    row1 = rx8_fmacf(tx, c11 - c01, c01);
    interp = rx8_fmacf(ty, row1 - row0, row0);
    return (uint16_t)(int32_t)interp;   /* ftrc: trunc toward zero, 16-bit */
}

/* 0x8FCC — sensor_adc_convert_chain.  Twelve ordered read-modify-writes on
 * the ADC MMIO cells 0xFFFFF626/627/630/66C (two of the RMW pairs depend on
 * the previous write to the same cell, so the order matters and is kept).
 * The two sub-calls (0x2054 / 0x2064) only clamp/set SR and the stack buffer
 * — no side effect on the compared cells. */
void rx8_sensor_adc_convert_chain(void)
{
    uint8_t b;
    uint16_t w;

    b = RX8_IO8(0xFFFFF627);  RX8_IO8(0xFFFFF627) = (uint8_t)((b & 0xF8) | 0x01);
    w = RX8_IO16(0xFFFFF630); RX8_IO16(0xFFFFF630) = (uint16_t)(w & 0xFFFE);
    w = RX8_IO16(0xFFFFF66C); RX8_IO16(0xFFFFF66C) = (uint16_t)(w & 0xFEFF);
    b = RX8_IO8(0xFFFFF626);  RX8_IO8(0xFFFFF626) = (uint8_t)((b & 0xF8) | 0x01);
    w = RX8_IO16(0xFFFFF630); RX8_IO16(0xFFFFF630) = (uint16_t)(w & 0xFFFB);
    w = RX8_IO16(0xFFFFF66C); RX8_IO16(0xFFFFF66C) = (uint16_t)(w & 0xFBFF);
    b = RX8_IO8(0xFFFFF627);  RX8_IO8(0xFFFFF627) = (uint8_t)((b & 0x8F) | 0x10);
    w = RX8_IO16(0xFFFFF630); RX8_IO16(0xFFFFF630) = (uint16_t)(w & 0xFFFD);
    w = RX8_IO16(0xFFFFF66C); RX8_IO16(0xFFFFF66C) = (uint16_t)(w & 0xFDFF);
    b = RX8_IO8(0xFFFFF626);  RX8_IO8(0xFFFFF626) = (uint8_t)((b & 0x8F) | 0x10);
    w = RX8_IO16(0xFFFFF630); RX8_IO16(0xFFFFF630) = (uint16_t)(w & 0xFFF7);
    w = RX8_IO16(0xFFFFF66C); RX8_IO16(0xFFFFF66C) = (uint16_t)(w & 0xF7FF);
}

/* 0xAA74 — per-channel init leaf.  Writes `value` to the u16 at ctrl_addr
 * (the ROM stores it twice — same cell, so one store is behaviourally
 * identical here) and calls the SR helpers 0x2054/0x2064 (no RAM effect). */
void rx8_ignition_dwell_channel_init(uint32_t ctrl_addr, uint16_t value)
{
    RX8_IO16(ctrl_addr) = value;    /* mov.w r0,@r2  (r0 = value)  */
    RX8_IO16(ctrl_addr) = value;    /* mov.w r0,@r3  (same cell)   */
}

/* 0x94C8 — next init phase.  y = f32[0xFFFF9F68], x = f32[0xFFFF9F80]
 * (fmov.s loads), result = lookup @0x213C (u16), then:
 *   sum = result + (u16)@0xFFFFA0D6;  (u16)@0xFFFFA0D4 = min(0xFFFF, sum). */
void rx8_ignition_dwell_next_phase(void)
{
    float y = 0.0f, x = 0.0f;
    memcpy(&y, (const void *)(uintptr_t)0xFFFF9F68, 4);
    memcpy(&x, (const void *)(uintptr_t)0xFFFF9F80, 4);

    uint16_t res = rx8_dwell_lookup_fp16(x, y);          /* extu.w r0,r0  */
    uint32_t sum = (uint32_t)res
                 + (uint32_t)RX8_IO16(0xFFFFA0D6);       /* add r3,r4     */
    RX8_IO16(0xFFFFA0D4) = sum > 0xFFFFu ? 0xFFFFu
                                          : (uint16_t)sum;   /* cmp/hi+sel  */
}

/* ----------------------------------------------------------------------------
 * Test rig: seed, call, dump.
 * ------------------------------------------------------------------------- */
#define RAM_BASE_ADDR   0xFFFFA0C4u   /* 60 bytes: 0xFFFFA0C4..0xFFFFA0FF */
#define FLT_Y_ADDR      0xFFFF9F68u   /* 4 bytes: tail-phase lookup input y */
#define FLT_X_ADDR      0xFFFF9F80u   /* 4 bytes: tail-phase lookup input x */

/* MMIO cells, in vector order (14 bytes). */
static const uintptr_t MMIO_ADDRS[14] = {
    0xFFFFF626u, 0xFFFFF627u,
    0xFFFFF630u, 0xFFFFF631u,
    0xFFFFF650u, 0xFFFFF651u,
    0xFFFFF652u, 0xFFFFF653u,
    0xFFFFF654u, 0xFFFFF655u,
    0xFFFFF656u, 0xFFFFF657u,
    0xFFFFF66Cu, 0xFFFFF66Du,
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

int main(void)
{
    char line[2048];

    /* Pages: 0xFFFFA000 (RAM cells), 0xFFFF9000 (lookup float inputs) and
     * 0xFFFFF000 (MMIO cells) — all above mmap_min_addr on this host. */
    map_page(RAM_BASE_ADDR);
    map_page(FLT_Y_ADDR);
    map_page(0xFFFFF000u);

    while (fgets(line, sizeof line, stdin)) {
        char *tok;
        unsigned long t[82];
        size_t k;

        tok = strtok(line, " \t\r\n");
        if (!tok || strcmp(tok, "dwl") != 0) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        for (k = 0; k < 82; k++) {
            tok = strtok(NULL, " \t\r\n");
            if (!tok) {
                fprintf(stderr, "short vector: %s", line);
                return 2;
            }
            t[k] = strtoul(tok, NULL, 16);
        }

        /* Seed RAM cells 0xFFFFA0C4..0xFFFFA0FF (60 bytes). */
        for (k = 0; k < 60; k++) {
            *(volatile uint8_t *)(uintptr_t)(RAM_BASE_ADDR + k) = (uint8_t)t[k];
        }
        /* Seed the MMIO cells (14 bytes, vector order). */
        for (k = 0; k < 14; k++) {
            *(volatile uint8_t *)(uintptr_t)MMIO_ADDRS[k] = (uint8_t)t[60 + k];
        }
        /* Seed the two lookup float inputs (big-endian bytes). */
        for (k = 0; k < 4; k++) {
            *(volatile uint8_t *)(uintptr_t)(FLT_Y_ADDR + k) = (uint8_t)t[74 + k];
            *(volatile uint8_t *)(uintptr_t)(FLT_X_ADDR + k) = (uint8_t)t[78 + k];
        }

        rx8_ignition_dwell_output_init();

        /* Dump the 74 output bytes: RAM cells then MMIO cells. */
        for (k = 0; k < 60; k++) {
            printf("%02X ", (unsigned)*(volatile uint8_t *)(uintptr_t)(RAM_BASE_ADDR + k));
        }
        for (k = 0; k < 14; k++) {
            printf("%02X%c", (unsigned)*(volatile uint8_t *)(uintptr_t)MMIO_ADDRS[k],
                   k == 13 ? '\n' : ' ');
        }
    }
    return 0;
}
