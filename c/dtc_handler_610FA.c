/*
 * dtc_handler_610FA.c  —  RX-8 PCM DTC handler dispatcher (0x0610FA)
 *
 * Reads the "current DTC index" register 0xFFFF8928, uses it to index the
 * DTC handler byte-code opcode table at 0xFFFF87DE (16 bytes per entry,
 * opcode is the first byte of the entry), and acts on the opcode:
 *
 *   opcode == 0x50  ("pending/completed" entry)  or
 *   opcode == 0x00  (empty entry)
 *        -> run can_encode_handler_62FAC(8), obd_service_handler_64258(),
 *           then tail-call obd_service_handler_63312()
 *
 *   any other opcode -> return immediately (the DTC entry is not in a
 *           servicable state).
 *
 * This is the dispatch entry point of the OBD Mode-03-style DTC reporting
 * pipeline; the heavier per-entry logic lives in dtc_handler_61D2A which
 * calls back into this function for every processed DTC.
 *
 * Verified against ROM 60E1D400.bin.
 */
#include <stdint.h>

#define DTC_CUR_INDEX  0xFFFF8928u   /* word: DTC index being serviced    */
#define DTC_OPCODES    0xFFFF87DEu   /* byte: handler byte-code opcodes   */
#define DTC_STRIDE     16u

/* called helpers (ROM addresses) */
extern void can_encode_handler_62FAC(uint8_t mode);
extern void obd_service_handler_64258(void);
extern void obd_service_handler_63312(void);   /* tail-called              */

void dtc_handler_610FA(void)
{
    uint16_t idx   = *(volatile uint16_t *)DTC_CUR_INDEX;
    uint8_t  op    = *(volatile uint8_t *)(DTC_OPCODES + (uint32_t)idx * DTC_STRIDE);

    if (op == 0x50u || op == 0x00u) {
        can_encode_handler_62FAC(0x08u);
        obd_service_handler_64258();
        obd_service_handler_63312();           /* tail call (jmp @Rn)      */
    }
}
