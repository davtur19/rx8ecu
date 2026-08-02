/* ============================================================================
 * oracle_omp_stepper_waveform_driver.c  —  host rig for
 * rx8_omp_stepper_waveform_driver @ 0x18552
 * ============================================================================
 * Compile together with samples/src/rx8_omp_stepper_waveform_driver.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     step <mode> <step0> <a97d0> <a9740> <a98a0> <a9690> <a96a0> <a97f0>
 *          <a98d0> <f7460>
 *                                             -> <step> <a97d> <a97f> <a98a>
 *                                                <a98d> <f746>
 *
 *   mode   : dispatch mode (u8; ROM clamps r4 to 8 bits)
 *   step0  : step register pre-state      (RAM[0xFFFFA97C])
 *   a97d0  : rotor-sync step source       (RAM[0xFFFFA97D])
 *   a9740  : rotor position counter       (RAM[0xFFFFA974])
 *   a98a0  : previously latched mode      (RAM[0xFFFFA98A])
 *   a9690  : gate flag A                  (RAM[0xFFFFA969])
 *   a96a0  : gate flag B                  (RAM[0xFFFFA96A])
 *   a97f0  : waveform-byte pre-state      (RAM[0xFFFFA97F], conditional write)
 *   a98d0  : mode-store pre-state         (RAM[0xFFFFA98D], always overwritten)
 *   f7460  : stepper drive port pre-state (RAM[0xFFFFF746], u16 RMW)
 *
 * The 6 printed words are the whole RAM side-effect set of the function:
 * A97C/A97D/A97F/A98A/A98D (u8) and F746 (u16).
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells, seeds every byte and prints the post-state.  It
 * contains NO copy of the 0x18552 logic — that lives solely in the
 * reconstructed source under test.  The 0x4BBC leaf the function jsr's
 * (setRegister_REG_BIT_VAL) IS modelled here, since the sample declares it
 * extern exactly like the lift does (c/omp_stepper_waveform_driver.c) and the
 * emulator runs the real bytes.  The three SR/stack-only leaves the ROM calls
 * (0x42B0 byte copy, 0x2054 setSR_PARAM, 0x2064 setSR) are stubbed in the
 * reconstruction (no effect on the compared RAM cells), so no model is needed.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0xFFFFA000  RAM[0xFFFFA969..A98D] OMP stepper cells (u8)
 *   0xFFFFF000  RAM[0xFFFFF746] stepper drive port (u16)
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_omp_stepper_waveform_driver is not (yet) in rx8_samples.h — the shared
 * header is owned by the samples build.  The reconstructed source itself
 * carries the authoritative definition (src/rx8_omp_stepper_waveform_driver.c);
 * this prototype mirrors it exactly. */
void rx8_omp_stepper_waveform_driver(uint8_t mode);

#define STEP_ADDR   0xFFFFA97Cu   /* u8 step register (advance source)  */
#define A97D_ADDR   0xFFFFA97Du   /* u8 rotor-sync step source          */
#define A974_ADDR   0xFFFFA974u   /* u8 rotor position counter          */
#define A98A_ADDR   0xFFFFA98Au   /* u8 previously latched mode         */
#define A98D_ADDR   0xFFFFA98Du   /* u8 mode store                      */
#define A97F_ADDR   0xFFFFA97Fu   /* u8 waveform byte (conditional)     */
#define A969_ADDR   0xFFFFA969u   /* u8 gate flag A                     */
#define A96A_ADDR   0xFFFFA96Au   /* u8 gate flag B                     */
#define F746_ADDR   0xFFFFF746u   /* u16 stepper drive port (RMW)       */

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

/* 0x4BBC leaf model (c/setRegister_REG_BIT_VAL.c; the sample
 * rx8_set_register_reg_bit_val.c): 16-bit RMW — `enable ? *reg |= mask :
 * *reg &= ~mask`, with the enable flag truncated to 16 bits by the ROM's
 * `extu.w r6,r6` before the tst/bf (this call site only ever passes 0/1). */
void rx8_set_register_reg_bit_val(uint16_t *reg, uint16_t mask, int enable)
{
    uint16_t tmp = *reg;
    enable &= 0xFFFF;
    if (enable) {
        tmp |= mask;
    } else {
        tmp &= ~mask;
    }
    *reg = tmp;
}

int main(void)
{
    char line[256];

    map_page(STEP_ADDR);
    map_page(F746_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long mode, step0, a97d0, a9740, a98a0, a9690, a96a0;
        unsigned long a97f0, a98d0, f7460;
        int n = sscanf(line,
                       "step %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                       &mode, &step0, &a97d0, &a9740, &a98a0, &a9690, &a96a0,
                       &a97f0, &a98d0, &f7460);
        if (n != 10) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed every input cell + distinguishable stale pre-states for the
         * conditionally/always-written cells. */
        *(volatile uint8_t *)(uintptr_t)STEP_ADDR = (uint8_t)step0;
        *(volatile uint8_t *)(uintptr_t)A97D_ADDR = (uint8_t)a97d0;
        *(volatile uint8_t *)(uintptr_t)A974_ADDR = (uint8_t)a9740;
        *(volatile uint8_t *)(uintptr_t)A98A_ADDR = (uint8_t)a98a0;
        *(volatile uint8_t *)(uintptr_t)A969_ADDR = (uint8_t)a9690;
        *(volatile uint8_t *)(uintptr_t)A96A_ADDR = (uint8_t)a96a0;
        *(volatile uint8_t *)(uintptr_t)A97F_ADDR = (uint8_t)a97f0;
        *(volatile uint8_t *)(uintptr_t)A98D_ADDR = (uint8_t)a98d0;
        *(volatile uint16_t *)(uintptr_t)F746_ADDR = (uint16_t)f7460;

        rx8_omp_stepper_waveform_driver((uint8_t)mode);

        printf("%02X %02X %02X %02X %02X %04X\n",
               *(volatile uint8_t *)(uintptr_t)STEP_ADDR,
               *(volatile uint8_t *)(uintptr_t)A97D_ADDR,
               *(volatile uint8_t *)(uintptr_t)A97F_ADDR,
               *(volatile uint8_t *)(uintptr_t)A98A_ADDR,
               *(volatile uint8_t *)(uintptr_t)A98D_ADDR,
               *(volatile uint16_t *)(uintptr_t)F746_ADDR);
    }
    return 0;
}
