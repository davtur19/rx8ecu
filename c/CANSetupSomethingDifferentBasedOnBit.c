/*
 * CANSetupSomethingDifferentBasedOnBit.c  —  RX-8 ECU CAN channel setup
 *
 * Address: 0x00E074  |  Size: 96 bytes
 *
 * Initialises multiple CAN message channels across two register blocks.
 * Loops through 16 high-priority channels, then 6 additional channels,
 * calling an init function for each channel where the byte at offset 4
 * (in the channel descriptor) is zero (channel unused/uninitialised).
 *
 * Function: init_can_message_channels (file name kept from the original
 * ghidra-hand placeholder label).
 *
 * Channel descriptors are 0x10 (16) bytes apart in two tables:
 *   Table A: 16 entries starting at 0x4E960  (priority channels)
 *   Table B:  6 entries starting at 0x4EC60  (extended channels)
 *
 * Verified against ROM: c/tests/test_CANSetupSomethingDifferentBasedOnBit.py
 */
#include <stdint.h>

/* External CAN channel init function */
extern void can_channel_init(uint32_t desc_addr);

/* 0x00E074 — initialise CAN message channels */
void init_can_message_channels(void)
{
    /* Table A: 16 high-priority channels */
    uint32_t base_a = 0x0004E960;
    for (int i = 0; i < 16; i++) {
        uint32_t desc_addr = base_a + (uint32_t)i * 0x10;
        volatile uint8_t *init_flag = (volatile uint8_t *)desc_addr;
        /* Check byte at offset 4 — not offset 0 */
        volatile uint8_t *flag = (volatile uint8_t *)(desc_addr + 4);
        if (*flag == 0) {
            can_channel_init(desc_addr);
        }
    }

    /* Table B: 6 extended channels */
    uint32_t base_b = 0x0004EC60;
    for (int i = 0; i < 6; i++) {
        uint32_t desc_addr = base_b + (uint32_t)i * 0x10;
        volatile uint8_t *flag = (volatile uint8_t *)(desc_addr + 4);
        if (*flag == 0) {
            can_channel_init(desc_addr);
        }
    }
}
