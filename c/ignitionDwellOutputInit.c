/*
 * ignitionDwellOutputInit.c  —  RX-8 ECU ignition dwell time init
 *
 * Address: 0x008F62  |  Size: 80 bytes
 *
 * Initialises the per-channel ignition dwell output timers.  Calls the
 * sensor ADC conversion chain first, then loops over 4 ignition channels
 * (rotors × coils) and initialises each channel's control registers.
 *
 * Algorithm:
 *   1. Call sensor_adc_convert_chain (0x08FCC) — prime ADC for sensors
 *   2. Loop 4 times (r9 = 4 iterations):
 *      - Read channel control word from table (base 0xDAB4, stride 0x18)
 *      - Call channel init function with control word
 *      - Clear byte at offset 4 in channel control struct (coil off)
 *      - Clear byte at offset 5 in channel control struct
 *      - Zero-initialise the channel's RAM pointer
 *      - Advance pointers by channel stride
 *   3. Tail-call to next init phase at 0x094C8 (via BRA)
 *
 * Verified against ROM: c/tests/test_ignitionDwellOutputInit.py
 */
#include <stdint.h>

/* External functions */
extern void sensor_adc_convert_chain(void);
extern uint32_t init_channel_func(uint32_t ctrl_word);

/* 0x008F62 — initialise ignition dwell output for all channels */
void ignitionDwellOutputInit(void)
{
    /* Per-channel control table lives at 0xDAB4, 0x18 bytes per entry */
    static const uint32_t channel_ctl_tbl[4] = {
        0x0000DAB4, 0x0000DACC, 0x0000DAE4, 0x0000DAFC
    };

    /* RAM struct base for dwell control — each channel 8 bytes */
    volatile uint8_t *dwell_ram = (volatile uint8_t *)0xFFFFA0C4;

    sensor_adc_convert_chain();

    for (int i = 0; i < 4; i++) {
        uint32_t ctrl_word = channel_ctl_tbl[i]; /* read from PC-relative table */

        /* NOTE: In the SH-2E the table reads are PC-relative mov.l
         * instructions from the literal pool at 0x8F78–0x8F80.
         * The loop counter is r10 (0..3), stride 0x18 in the table. */

        uint32_t result = init_channel_func(ctrl_word);

        /* Clear the output-enable and fault bits for this channel */
        dwell_ram[4] = 0;   /* coil off */
        dwell_ram[5] = 0;   /* fault clear */

        /* Store init result to channel RAM pointer */
        *(volatile uint32_t *)dwell_ram = result;

        dwell_ram += 8;     /* next channel register block */
    }

    /* Tail-call to next init phase */
    extern void next_init_phase(void) __attribute__((noreturn));
    next_init_phase();
}
