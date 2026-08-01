/*
 * dtc_handler_61550.c  —  RX-8 PCM DTC detailed handler (0x061550)
 *
 * Per-DTC detailed processing for OBD diagnostics.  Arguments:
 *   r4 (dtc)    16-bit DTC code being processed
 *   r5 (mode)   sub-service selector: 1 = status, 2 = data, 3 = DTC list
 *
 * Dispatch (on mode):
 *   mode 3: dtc_handler_61712() derives a status value, the result is
 *           encoded onto the CAN bus (can_encode_handler_62334/62E5C) and,
 *           if accepted, a sequence of DTC-state helpers runs
 *           (dtc_handler_61818, dtc_handler_61994, can_encode_handler_62B74,
 *           dtc_handler_6193E(dtc,0x20), obd_service_handler_63B46,
 *           obd_service_handler_63A62, obd_service_handler_63AD4(1)).
 *   mode 1: obd_service_handler_63834() reads the status word; only entries
 *           with bit 7 set are further processed; same encode + service
 *           chain as mode 3 (plus obd_service_handler_63814 when bit7).
 *   mode 2: status read + encode + service chain (no bit7 gate).
 *
 * Every path ends with a common tail:
 *   - store the encoded result byte to 0xFFFFD6FC
 *   - store can_encode_handler_62DEC(status) to 0xFFFFD6FF
 *   - if the DTC currently addressed (word @ 0xFFFFD700) equals `dtc`,
 *     call can_encode_handler_62ABC(dtc, 0x20)
 *   - can_encode_handler_62B24(dtc, 0x20, status)
 *   - tail-call obd_service_handler_632D6()
 *
 * The 0xFFFFD6F8..0xFFFFD6FF block is the diag result/status scratch area
 * read by the OBD response builders.
 *
 * Verified against ROM 60E1D400.bin.
 */
#include <stdint.h>

#define DIAG_RESULT_BASE  0xFFFFD6F8u   /* result scratch block           */
#define DTC_ADDR_CURRENT  0xFFFFD700u   /* word: DTC currently addressed  */

/* called helpers (ROM addresses) */
extern uint8_t  dtc_handler_61712(uint16_t dtc);
extern uint8_t  can_encode_handler_62334(uint16_t dtc, uint8_t st, uint8_t mode);
extern uint8_t  can_encode_handler_62E5C(uint8_t enc);
extern void     dtc_handler_61818(uint16_t dtc, uint8_t st);
extern void     dtc_handler_61994(void);
extern void     can_encode_handler_62B74(uint16_t dtc);
extern void     dtc_handler_6193E(uint16_t dtc, uint8_t v);
extern void     obd_service_handler_63B46(uint8_t enc);
extern void     obd_service_handler_63A62(uint8_t mode);
extern void     obd_service_handler_63AD4(uint8_t v);
extern uint8_t  obd_service_handler_63834(uint16_t dtc);
extern void     obd_service_handler_63814(uint8_t st);
extern void     obd_service_handler_632F4(void);
extern uint8_t  can_encode_handler_62DEC(uint8_t st);
extern void     can_encode_handler_62ABC(uint16_t dtc, uint8_t v);
extern void     can_encode_handler_62B24(uint16_t dtc, uint8_t v, uint8_t st);
extern uint8_t  obd_service_handler_632D6(void);   /* tail-called          */

void dtc_handler_61550(uint16_t dtc, uint8_t mode)
{
    uint8_t st = 0;
    uint8_t enc = 0;

    switch (mode) {
    case 0x03u:
        st  = dtc_handler_61712(dtc);
        enc = can_encode_handler_62334(dtc, st, mode);
        if (can_encode_handler_62E5C(enc) == 0x01u) {
            dtc_handler_61818(dtc, st);
            dtc_handler_61994();
            can_encode_handler_62B74(dtc);
            dtc_handler_6193E(dtc, 0x20u);
            obd_service_handler_63B46(enc);
            obd_service_handler_63A62(mode);
            obd_service_handler_63AD4(0x01u);
        }
        obd_service_handler_632F4();
        break;

    case 0x01u:
        st  = obd_service_handler_63834(dtc);
        if ((st & 0x80u) != 0x80u)
            st = 0x00u;                    /* only bit-7 entries survive  */
        enc = can_encode_handler_62334(dtc, st, mode);
        if (can_encode_handler_62E5C(enc) == 0x01u) {
            if ((st & 0x80u) == 0x80u) {
                obd_service_handler_63814(st);
                obd_service_handler_63B46(enc);
            }
            obd_service_handler_63A62(mode);
        }
        obd_service_handler_632F4();
        break;

    case 0x02u:
    default:
        st  = obd_service_handler_63834(dtc);
        enc = can_encode_handler_62334(dtc, st, mode);
        if (can_encode_handler_62E5C(enc) == 0x01u)
            obd_service_handler_63A62(mode);
        obd_service_handler_632F4();
        break;
    }

    *(volatile uint8_t *)(DIAG_RESULT_BASE + 0x04u) = enc;   /* 0xFFFFD6FC */
    *(volatile uint8_t *)(DIAG_RESULT_BASE + 0x07u) =         /* 0xFFFFD6FF */
        can_encode_handler_62DEC(st);

    if (*(volatile uint16_t *)DTC_ADDR_CURRENT == (uint16_t)dtc)
        can_encode_handler_62ABC(dtc, 0x20u);

    can_encode_handler_62B24(dtc, 0x20u, st);
    obd_service_handler_632D6();             /* tail call (jmp @Rn)        */
}
