/*
 * pulse_window_compute_FCD2_r4.c — 90% byte-match for ROM 0xFCD2 (20 B body).
 *
 * ROM:
 *   mov r5,r3 / sub r4,r3 / mov r3,r4 / cmp/pl r4 / bt.s .R / nop
 *   / mov.l @(pc),r3 ; 0x168 / add r3,r4 / rts / mov r4,r0
 *
 * Recipe (18/20 = 90.0%, 9/10 insn):
 *   xgcc -B ... -m2e -O1 -fomit-frame-pointer
 *
 * Why:
 *   - the inverted test `if (d <= 0) d += c` makes gcc 3.4.6 emit `bt.s`
 *     (branch-if-positive to the return) exactly like the ROM — the polarità
 *     del ramo che nella versione baseline era invertita (`bf.s`);
 *   - pinning the temporaries r3 (difference) / r4 (accumulator) and the
 *     empty-asm barrier reproduces `mov r5,r3 / sub r4,r3 / mov r3,r4`;
 *   - `c` pinned r3 loads 0x168 PC-relative and adds `add r3,r4`.
 *
 * Residual single-instruction divergence (structural, no 3.4.6 flag fixes it):
 *   ROM `mov.l @(pc),r3` vs gcc `mov.w @(pc),r3` — GCC 3.4.6's `broken_move`
 *   narrows any SImode constant in [-32768,32767] to a HImode pool load
 *   (`hi_const`), while the ROM compiler loaded 0x168 with `mov.l`.
 */
#include <stdint.h>

int pulse_window_compute(int a, int b)
{
    register int d __asm__("r4");
    register int c __asm__("r3");
    register int t __asm__("r3");
    t = b - a;
    __asm__ __volatile__("" : "=r"(d) : "0"(t));
    if (d <= 0) { c = 0x168; d = d + c; }
    __asm__ __volatile__("" : : "r"(d));
    return d;
}
