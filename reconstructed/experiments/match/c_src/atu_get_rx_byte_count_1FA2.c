#include <stdint.h>
unsigned atu_get_rx_byte_count(uint8_t n, unsigned base)
{
    register unsigned b __asm__("r5") = base;
    register unsigned c __asm__("r3") = 32;
    register unsigned k __asm__("r4");
    if ((int)n >= (int)c) k = 0x0200 + b; else k = b;
    return k;
}
