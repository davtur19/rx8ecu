/* ============================================================================
 * oracle_rotor_sync_position_detector.c  —  host rig for
 * rx8_rotor_sync_position_detector @0x189EE
 * ============================================================================
 * Compile together with samples/src/rx8_rotor_sync_position_detector.c and
 * pipe test vectors on stdin; one vector per line, whitespace-separated hex
 * tokens:
 *
 *     rsync <mode> <a8f1> <a974> <a98b> <a97c> <a97d> <a97b> <a98a> <a969>
 *           <a96a> <a97f> <a98d> <f746> <s1..s8>
 *                            -> <a98b> <a97b> <a97d> <a97c> <a97f> <a98a>
 *                               <a98d> <f746> <s1..s8>
 *
 *   mode  : r4 entry argument (0 = position-compare pass, any other = pure
 *           state-machine pass)
 *   a8f1  : RAM8[0xFFFFA8F1] old rotor position (read)
 *   a974  : RAM8[0xFFFFA974] new rotor position (read, entry + stage C; also
 *           read by the wave callee)
 *   a98b  : RAM8[0xFFFFA98B] state pre-state (read/written)
 *   a97c  : RAM8[0xFFFFA97C] step register (read for odd/even; the wave callee
 *           reads/writes it)
 *   a97d  : RAM8[0xFFFFA97D] rotor-sync step source (wave callee; written on
 *           the state-2 flag copy or the wave mode-4 path)
 *   a97b  : RAM8[0xFFFFA97B] waveform byte pre-state (overwritten)
 *   a98a  : RAM8[0xFFFFA98A] latched mode pre-state (wave callee)
 *   a969/a96a : RAM8[0xFFFFA969/0xFFFFA96A] wave gate flags (wave callee)
 *   a97f  : RAM8[0xFFFFA97F] waveform byte pre-state (wave callee)
 *   a98d  : RAM8[0xFFFFA98D] mode store pre-state (wave callee)
 *   f746  : RAM16[0xFFFFF746] stepper port pre-state (wave callee RMW)
 *   s1..s8: sentinel bytes that must survive the call untouched (they pin the
 *           store count and width):
 *             s1 = 0xFFFFA97A  s2 = 0xFFFFA97E  s3 = 0xFFFFA980
 *             s4 = 0xFFFFA989  s5 = 0xFFFFA98C  s6 = 0xFFFFA98E
 *             s7 = 0xFFFFF745  s8 = 0xFFFFF748
 *
 * The 16 printed tokens are the whole RAM side-effect set of the call
 * (A98B/A97B/A97D/A97C/A97F/A98A/A98D/F746) plus the untouched sentinels.
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the cells, seeds every byte and prints the post-state.  It
 * contains NO copy of the 0x189EE logic — that lives solely in the
 * reconstructed source under test.  The ROM callee 0x18552 (wave, bsr'd with
 * r4 = 1/2/3/4) IS modelled here, since the sample declares it extern exactly
 * like the lift does (c/rotor_sync_position_detector.c) and the emulator runs
 * the real bytes; the model is the verified lift of that callee
 * (c/omp_stepper_waveform_driver.c), including the RMW leaf 0x4BBC.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0xFFFFA000  RAM[0xFFFFA8F1..A98E] (all rotor-sync + wave cells)
 *   0xFFFFF000  RAM[0xFFFFF745..F748] (port + sentinels)
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_rotor_sync_position_detector is not (yet) in rx8_samples.h — the shared
 * header is owned by the samples build.  The reconstructed source itself
 * carries the authoritative definition (src/rx8_rotor_sync_position_detector.c);
 * this prototype mirrors it exactly. */
void rx8_rotor_sync_position_detector(uint8_t mode);

/* ---- the wave callee's own RAM cells (same addresses as the sample) ---- */
#define W_STEP  (*(volatile uint8_t  *)0xFFFFA97Cu)  /* step register   */
#define W_A97D  (*(volatile uint8_t  *)0xFFFFA97Du)  /* rotor-sync step */
#define W_A974  (*(volatile uint8_t  *)0xFFFFA974u)  /* rotor position  */
#define W_A98A  (*(volatile uint8_t  *)0xFFFFA98Au)  /* latched mode    */
#define W_A98D  (*(volatile uint8_t  *)0xFFFFA98Du)  /* mode store      */
#define W_A97F  (*(volatile uint8_t  *)0xFFFFA97Fu)  /* waveform byte   */
#define W_A969  (*(volatile uint8_t  *)0xFFFFA969u)  /* gate flag A     */
#define W_A96A  (*(volatile uint8_t  *)0xFFFFA96Au)  /* gate flag B     */
#define W_F746  (*(volatile uint16_t *)0xFFFFF746u)  /* 4-phase port    */

/* step pattern table, ROM 0x4ED5C (copied to the wave's stack frame at entry) */
static const uint8_t STEP_PATTERN[9][4] = {
    {1, 0, 0, 1}, {1, 0, 0, 0}, {1, 1, 0, 0}, {0, 1, 0, 0}, {0, 1, 1, 0},
    {0, 0, 1, 0}, {0, 0, 1, 1}, {0, 0, 0, 1}, {0, 0, 0, 0},
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

/* 0x4BBC leaf model (c/omp_stepper_waveform_driver.c header): 16-bit RMW —
 * enable ? *reg |= mask : *reg &= ~mask.  Inlined here (it is a 2-call leaf
 * inside the wave driver, not an independent branch point). */
static void set_register_reg_bit_val(volatile uint16_t *reg, uint16_t mask,
                                     int enable)
{
    if (enable)
        *reg |= mask;
    else
        *reg &= (uint16_t)~mask;
}

/* 0x18552 — host model of the verified stepper waveform driver (lift
 * c/omp_stepper_waveform_driver.c): advances the step register and drives
 * the 4-phase pattern for the new step onto port F746. */
void omp_stepper_waveform_driver(uint8_t mode)
{
    uint8_t step = W_STEP;
    uint8_t a97d = W_A97D;
    uint8_t a974 = W_A974;
    uint8_t a98a = W_A98A;
    int      wf_ok = 0;
    uint8_t  wf = 0;
    int      i;

    W_A98D = mode;                        /* latched at entry (0x18580) */

    switch (mode) {
    case 0:                               /* advance by 1 */
        step = (uint8_t)((step + 1) & 7);
        if ((step & 1) == 0 && a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 1:                               /* rotor-sync advance */
        if (step == 8) {
            step = (uint8_t)((a97d + 0xFF) & 7);   /* A97D source */
        } else {
            step = (uint8_t)((step + 0xFF) & 7);   /* decrement mod 8 */
            if (a974 == 1 && a98a != 4 &&
                (W_A969 == 1 || W_A96A == 1)) {
                wf_ok = 1;
                wf = 0;
            }
        }
        if ((step & 1) == 0 && a98a != 4 && a974 > 0) {
            wf_ok = 1;
            wf = (uint8_t)(0xFF + a974);
        }
        break;
    case 2:                               /* 0x186B8 */
        if (a98a == 4 || (step & 1) == 1) {
            step = (step == 8) ? (uint8_t)((a97d + 1) & 7)
                               : (uint8_t)((step + 1) & 7);
        } else {
            step = (uint8_t)((step + 2) & 7);
        }
        if (a974 < 60) {
            wf_ok = 1;
            wf = (uint8_t)(a974 + 1);
        }
        break;
    case 3:                               /* 0x186FC */
        if (a98a == 4 || (step & 1) == 1) {
            if (step == 8) {
                step = (uint8_t)((a97d + 0xFF) & 7);
            } else {
                step = (uint8_t)((step + 0xFF) & 7);
                if (a974 == 1 && a98a != 4) {
                    wf_ok = 1;
                    wf = 0;
                }
            }
        } else {
            step = (uint8_t)((step + 0xFE) & 7);   /* decrement by 2 mod 8 */
            if (a974 > 0) {
                wf_ok = 1;
                wf = (uint8_t)(0xFF + a974);
            }
        }
        break;
    case 4:                               /* 0x18766 */
        if (step == 8) {
            step = a97d;
        } else if ((step & 1) == 0) {
            step = (uint8_t)((step + 1) & 7);
            W_A97D = step;
        } else {
            step = 8;
        }
        break;
    case 6:                               /* 0x18790 */
        step = 8;
        break;
    default:                              /* modes 5,7..255: step unchanged */
        break;
    }

    W_STEP = step;
    W_A98A = mode;
    if (wf_ok)
        W_A97F = wf;

    /* 4-phase port drive: pattern byte == 1 -> set bit i of F746. */
    for (i = 0; i < 4; i++) {
        set_register_reg_bit_val(&W_F746, (uint16_t)(1u << i),
                                 STEP_PATTERN[step][i] == 1);
    }
}

/* ---- rotor-sync cells (same addresses as the sample) ---- */
#define A8F1   0xFFFFA8F1u   /* old rotor position  (read)       */
#define A974   0xFFFFA974u   /* new rotor position  (read)       */
#define A98B   0xFFFFA98Bu   /* state                (r/w)       */
#define A97C   0xFFFFA97Cu   /* step register        (r; wave)   */
#define A97D   0xFFFFA97Du   /* rotor-sync source    (r; wave)   */
#define A97B   0xFFFFA97Bu   /* waveform byte        (write)     */
#define A98A   0xFFFFA98Au   /* latched mode         (wave)      */
#define A969   0xFFFFA969u   /* gate flag A          (wave)      */
#define A96A   0xFFFFA96Au   /* gate flag B          (wave)      */
#define A97F   0xFFFFA97Fu   /* waveform byte        (wave)      */
#define A98D   0xFFFFA98Du   /* mode store           (wave)      */
#define F746   0xFFFFF746u   /* stepper port  u16    (wave RMW)  */

/* sentinels pinning the store count and width */
#define S1     0xFFFFA97Au   /* left  of A97B */
#define S2     0xFFFFA97Eu   /* A97D..A97F gap */
#define S3     0xFFFFA980u   /* right of A97F */
#define S4     0xFFFFA989u   /* left  of A98A */
#define S5     0xFFFFA98Cu   /* right of A98B */
#define S6     0xFFFFA98Eu   /* right of A98D */
#define S7     0xFFFFF745u   /* left  of F746  */
#define S8     0xFFFFF748u   /* right of F746  */

int main(void)
{
    char line[256];

    map_page(0xFFFFA000u);                 /* all rotor-sync + wave cells */
    map_page(0xFFFFF000u);                 /* port F746 + sentinels        */

    while (fgets(line, sizeof line, stdin)) {
        unsigned long mode, a8f1, a974, a98b, a97c, a97d, a97b, a98a;
        unsigned long a969, a96a, a97f, a98d, f746;
        unsigned long s[8];
        int n = sscanf(line,
                       "rsync %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx"
                       " %lx %lx %lx %lx %lx %lx %lx %lx",
                       &mode, &a8f1, &a974, &a98b, &a97c, &a97d, &a97b, &a98a,
                       &a969, &a96a, &a97f, &a98d, &f746,
                       &s[0], &s[1], &s[2], &s[3], &s[4], &s[5], &s[6], &s[7]);
        if (n != 21) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the input RAM cells + the wave callee's inputs + sentinels. */
        *(volatile uint8_t  *)(uintptr_t)A8F1 = (uint8_t)a8f1;
        *(volatile uint8_t  *)(uintptr_t)A974 = (uint8_t)a974;
        *(volatile uint8_t  *)(uintptr_t)A98B = (uint8_t)a98b;
        *(volatile uint8_t  *)(uintptr_t)A97C = (uint8_t)a97c;
        *(volatile uint8_t  *)(uintptr_t)A97D = (uint8_t)a97d;
        *(volatile uint8_t  *)(uintptr_t)A97B = (uint8_t)a97b;
        *(volatile uint8_t  *)(uintptr_t)A98A = (uint8_t)a98a;
        *(volatile uint8_t  *)(uintptr_t)A969 = (uint8_t)a969;
        *(volatile uint8_t  *)(uintptr_t)A96A = (uint8_t)a96a;
        *(volatile uint8_t  *)(uintptr_t)A97F = (uint8_t)a97f;
        *(volatile uint8_t  *)(uintptr_t)A98D = (uint8_t)a98d;
        *(volatile uint16_t *)(uintptr_t)F746 = (uint16_t)f746;
        *(volatile uint8_t  *)(uintptr_t)S1   = (uint8_t)s[0];
        *(volatile uint8_t  *)(uintptr_t)S2   = (uint8_t)s[1];
        *(volatile uint8_t  *)(uintptr_t)S3   = (uint8_t)s[2];
        *(volatile uint8_t  *)(uintptr_t)S4   = (uint8_t)s[3];
        *(volatile uint8_t  *)(uintptr_t)S5   = (uint8_t)s[4];
        *(volatile uint8_t  *)(uintptr_t)S6   = (uint8_t)s[5];
        *(volatile uint8_t  *)(uintptr_t)S7   = (uint8_t)s[6];
        *(volatile uint8_t  *)(uintptr_t)S8   = (uint8_t)s[7];

        rx8_rotor_sync_position_detector((uint8_t)mode);

        printf("%02X %02X %02X %02X %02X %02X %02X %04X"
               " %02X %02X %02X %02X %02X %02X %02X %02X\n",
               *(volatile uint8_t  *)(uintptr_t)A98B,
               *(volatile uint8_t  *)(uintptr_t)A97B,
               *(volatile uint8_t  *)(uintptr_t)A97D,
               *(volatile uint8_t  *)(uintptr_t)A97C,
               *(volatile uint8_t  *)(uintptr_t)A97F,
               *(volatile uint8_t  *)(uintptr_t)A98A,
               *(volatile uint8_t  *)(uintptr_t)A98D,
               *(volatile uint16_t *)(uintptr_t)F746,
               *(volatile uint8_t  *)(uintptr_t)S1,
               *(volatile uint8_t  *)(uintptr_t)S2,
               *(volatile uint8_t  *)(uintptr_t)S3,
               *(volatile uint8_t  *)(uintptr_t)S4,
               *(volatile uint8_t  *)(uintptr_t)S5,
               *(volatile uint8_t  *)(uintptr_t)S6,
               *(volatile uint8_t  *)(uintptr_t)S7,
               *(volatile uint8_t  *)(uintptr_t)S8);
    }
    return 0;
}
