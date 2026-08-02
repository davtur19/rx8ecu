/*
 * setImmoCANTXData_369B8  —  RX-8 PCM @ ROM 0x369B8 (60E1D400.bin)
 * (old name: message_queue_state_dispatcher_369B8)
 *
 * Builds an 8-byte immobilizer CAN TX frame at 0xFFFFC238 and raises the
 * TX request flags.  The message id byte selects the payload layout
 * (verified at 0x369C0..0x36AA0):
 *
 *   id 0x09  -> buf[1] = slot byte from 0xFFFFC290 (1..4 select a 32-bit
 *               key word at 0xFFFFC24C/0x250/0x254/0x258 whose middle 3
 *               bytes land in buf[2..4]; 0xFF -> buf[1]=0xFF, buf[2..4]=0;
 *               anything else leaves buf[1..4] untouched)
 *   id 0x07  -> buf[1..4] = the 32-bit rolling key 0xFFFFC278 (MSB first)
 *   id 0x01/0x81 -> buf[1] = *0xFFFFC294, buf[2..4] = 0
 *   id 0xC6/0xC8 -> buf[1..4] = 0
 *   other    -> buf[1..4] untouched (only buf[0] = id)
 *
 * Common epilogue (0x36AA0): buf[5..7] = 0; 0xC241 = 1 (TX request);
 * 0xFFFFC296 = 0; 0xFFFFC28F = 0; 0xFFFFC299 = 1 (TX pending).
 */
#include "eeprom_immo.h"

void setImmoCANTXData_369B8(uint8_t cmd)
{
    volatile uint8_t *buf = IMMO_CAN_TX_BUF;   /* 0xFFFFC238, 8 bytes */

    buf[0] = cmd;
    switch (cmd) {
    case 0x09: {
        uint8_t sel = IMMO_WAIT_STATE;         /* 0xFFFFC290 */
        uint32_t *src = 0;
        switch (sel) {
        case 1:  src = (uint32_t *)0xFFFFC24C; break;
        case 2:  src = (uint32_t *)0xFFFFC250; break;
        case 3:  src = (uint32_t *)0xFFFFC254; break;
        case 4:  src = (uint32_t *)0xFFFFC258; break;
        case 0xFF:
            buf[1] = sel;
            buf[2] = buf[3] = buf[4] = 0;
            goto epilogue;                    /* 0x36A6A -> 0x36AA0 */
        default:
            goto epilogue;                    /* 0x36A58: buf[1..4] unchanged */
        }
        {
            uint32_t v = *src;
            buf[1] = sel;
            buf[2] = (uint8_t)(v >> 16);      /* 0x36A7C */
            buf[3] = (uint8_t)(v >> 8);       /* 0x36A82 */
            buf[4] = ((volatile uint8_t *)src)[3]; /* 0x36A86 */
        }
        break;
    }
    case 0x07: {
        uint32_t v = IMMO_KEYGEN_ADC;         /* 0xFFFFC278 */
        buf[1] = (uint8_t)(v >> 24);          /* 0x36A6E..0x36A76 */
        buf[2] = (uint8_t)(v >> 16);
        buf[3] = (uint8_t)(v >> 8);
        buf[4] = (uint8_t)v;
        break;
    }
    case 0x01:
    case 0x81:
        buf[1] = IMMO_RESP_BYTE;              /* 0xFFFFC294 */
        buf[2] = buf[3] = buf[4] = 0;
        break;
    case 0xC6:
    case 0xC8:
        buf[1] = buf[2] = buf[3] = buf[4] = 0;
        break;
    default:
        break;                                /* buf[1..4] untouched */
    }
epilogue:
    buf[5] = buf[6] = buf[7] = 0;
    CAN_TX_REQ = 1;                           /* 0xC241 */
    IMMO_CAN_TX_STATUS = 0;                   /* 0xFFFFC296 */
    IMMO_CAN_TX_STATE  = 0;                   /* 0xFFFFC28F */
    IMMO_CAN_TX_PENDING = 1;                  /* 0xFFFFC299 */
}
