/*
 * can_get_mailbox_offset_high_D164_spec.c — specular rewrite (see atu_spec).
 */
#include <stdint.h>

unsigned can_get_mailbox_offset_high(uint8_t n, unsigned base)
{
    register unsigned b __asm__("r5") = base;
    register unsigned c __asm__("r3") = 32;
    register unsigned k __asm__("r4");
    if ((int)n < (int)c) k = b;
    else { k = 0x0200; k += b; }
    return k;
}
