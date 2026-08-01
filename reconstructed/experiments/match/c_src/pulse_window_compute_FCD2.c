/*
 * pulse_window_compute_FCD2 — ROM 0xFCD2 (20 B body; pool @0xFD54 non-contig).
 *   mov r5,r3 / sub r4,r3 / mov r3,r4 / cmp/pl r4 / bt/s .R / nop
 *   / mov.l @(pc),r3 ; 0x168 / add r3,r4 / rts / mov r4,r0
 * Semantics:  int d = b - a;  return d > 0 ? d : d + 0x168;
 */
#include <stdint.h>

int pulse_window_compute(int a, int b)
{
    register int d __asm__("r4");
    d = b - a;
    if (d > 0) return d;
    return d + 0x168;
}
