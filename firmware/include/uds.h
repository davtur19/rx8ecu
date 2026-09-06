/*
 * uds.h — RX-8 ECU UDS (Unified Diagnostic Services) Subsystem Definitions
 *
 * 1:1 firmware reconstruction of the UDS diagnostic services for the
 * Mazda RX-8 Renesis 13B-MSP rotary engine ECU (SH-2E / SH7055).
 *
 * Dispatch table at 0x5F57C: 29 records × 12 bytes
 * Main handler at 0x697E8
 * Session gate at 0x5FA7D (29 bytes, one per SID)
 *
 * Source: uds_obd_analysis.md, IDA session ae00d360
 */

#ifndef UDS_H
#define UDS_H

#include <stdint.h>
#include "platform.h"

/* ====================================================================== */
/*  Dispatch Table Layout                                                  */
/* ====================================================================== */

#define UDS_DISPATCH_TABLE_BASE 0x5F57C
#define UDS_DISPATCH_ENTRY_SIZE 12
#define UDS_DISPATCH_MAX_SLOTS  29

/* Record layout: [+0]=SID [+1]=pad [+2..+3]=pad [+4..+7]=handler_addr [+8..+9]=pad [+A..+B]=flags */
#define UDS_DISP_SID_OFFSET     0x00
#define UDS_DISP_HANDLER_OFFSET 0x04
#define UDS_DISP_FLAGS_OFFSET   0x0A

/* ====================================================================== */
/*  Service IDs                                                            */
/* ====================================================================== */

#define UDS_SID_DIAG_SESSION    0x10
#define UDS_SID_ECU_RESET       0x11
#define UDS_SID_CLEAR_DTC       0x14
#define UDS_SID_READ_DTC_INFO   0x18
#define UDS_SID_READ_DATA_ID    0x22
#define UDS_SID_READ_MEM_ADDR   0x23
#define UDS_SID_SECURITY_ACCESS 0x27
#define UDS_SID_WRITE_DATA_ID   0x2E
#define UDS_SID_ROUTINE_CONTROL 0x31
#define UDS_SID_REQ_DOWNLOAD    0x34
#define UDS_SID_TRANSFER_DATA   0x36
#define UDS_SID_REQ_TRANS_EXIT  0x37
#define UDS_SID_TESTER_PRESENT  0x3E
#define UDS_SID_NEGATIVE_RESP   0x7F
#define UDS_SID_OBD_SVC1        0x01
#define UDS_SID_OBD_SVC2        0x02
#define UDS_SID_OBD_SVC3        0x03
#define UDS_SID_OBD_SVC4        0x04
#define UDS_SID_OBD_SVC6        0x06
#define UDS_SID_OBD_SVC7        0x07
#define UDS_SID_OBD_SVC9        0x09
#define UDS_SID_OBD_SVCA        0x0A

/* ====================================================================== */
/*  Session / Security                                                     */
/* ====================================================================== */

#define UDS_SESSION_DEFAULT     0x01
#define UDS_SESSION_PROGRAMMING 0x02
#define UDS_SESSION_EXTENDED    0x03

#define UDS_SECURITY_LOCKED     0x7F
#define UDS_SECURITY_LEVEL_1    0x5F
#define UDS_SECURITY_LEVEL_2    0x3F

/* ====================================================================== */
/*  Negative Response Codes                                                */
/* ====================================================================== */

#define UDS_NRC_SERVICE_NOT_SUPPORTED      0x11
#define UDS_NRC_SUB_NOT_SUPPORTED          0x12
#define UDS_NRC_INCORRECT_MSG_LEN          0x13
#define UDS_NRC_CONDITIONS_NOT_CORRECT     0x22
#define UDS_NRC_REQUEST_OUT_OF_RANGE       0x31
#define UDS_NRC_SECURITY_ACCESS_DENIED     0x33
#define UDS_NRC_INVALID_KEY                0x35
#define UDS_NRC_EXCEEDED_ATTEMPTS          0x36
#define UDS_NRC_REQUEST_PENDING            0x78

/* ====================================================================== */
/*  RAM Addresses                                                          */
/* ====================================================================== */

#define UDS_SESSION_LEVEL_ADDR  0xFFFFDE5C
#define UDS_SECURITY_LEVEL_ADDR 0xFFFFD20C
#define UDS_SESSION_TIMER_ADDR  0xFFFFD210
#define UDS_TESTER_PRESENT_ADDR 0xFFFFD214

#define UDS_POS_RESPONSE_OFFSET 0x40

/* ====================================================================== */
/*  Security Access Sub-functions                                          */
/* ====================================================================== */

#define UDS_SEC_SUB_REQ_SEED_1  0x01
#define UDS_SEC_SUB_SEND_KEY_1  0x02
#define UDS_SEC_SUB_REQ_SEED_2  0x03
#define UDS_SEC_SUB_SEND_KEY_2  0x04

/* ====================================================================== */
/*  Function Prototypes                                                    */
/* ====================================================================== */

void uds_init(void);

/**
 * uds_handler — Main UDS request handler.
 * ROM address: 0x697E8
 */
int uds_handler(const uint8_t *request, uint8_t req_len, uint8_t *response);

uint32_t uds_dispatch_lookup(uint8_t sid);
int uds_session_gate(uint8_t sid);
int uds_negative_response(uint8_t sid, uint8_t nrc, uint8_t *response);

/* SID handlers */
int obd_sid10_sessionControl(uint8_t sub_func, const uint8_t *data,
                             uint8_t data_len, uint8_t *response);
int obd_sid27_securityAccess(uint8_t sub_func, const uint8_t *data,
                             uint8_t data_len, uint8_t *response);
int obd_sidB1_ecuReset(uint8_t sub_func, uint8_t *response);
int obd_sid22_readDataByIdentifier(const uint8_t *data, uint8_t data_len,
                                   uint8_t *response);
int obd_sid23_readMemoryByAddress(const uint8_t *data, uint8_t data_len,
                                  uint8_t *response);
int obd_sid2E_writeDataByIdentifier(const uint8_t *data, uint8_t data_len,
                                    uint8_t *response);
int obd_sid31_routineControl(uint8_t sub_func, const uint8_t *data,
                             uint8_t data_len, uint8_t *response);
int obd_sid34_requestDownload(const uint8_t *data, uint8_t data_len,
                              uint8_t *response);
int obd_sid36_transferData(uint8_t block_seq, const uint8_t *data,
                           uint8_t data_len, uint8_t *response);
int obd_sid37_requestTransferExit(uint8_t *response);

/* OBD-II service handlers */
int obd_service_1(uint8_t pid, uint8_t *response);
int obd_service_2(uint8_t pid, uint8_t frame, uint8_t *response);
int obd_service_3(uint8_t *response);
int obd_service_4(uint8_t *response);
int obd_service_6(uint8_t *response);
int obd_service_7(uint8_t *response);
int obd_service_9(uint8_t sub_func, uint8_t *response);
int obd_service_A(uint8_t *response);

/* ====================================================================== */
/*  Inline RAM Accessors                                                   */
/* ====================================================================== */

static inline uint8_t uds_get_session(void)
{
    return *(volatile uint8_t *)UDS_SESSION_LEVEL_ADDR;
}

static inline void uds_set_session(uint8_t session)
{
    *(volatile uint8_t *)UDS_SESSION_LEVEL_ADDR = session;
}

static inline uint8_t uds_get_security(void)
{
    return *(volatile uint8_t *)UDS_SECURITY_LEVEL_ADDR;
}

static inline void uds_set_security(uint8_t level)
{
    *(volatile uint8_t *)UDS_SECURITY_LEVEL_ADDR = level;
}

static inline int uds_is_unlocked(void)
{
    return (uds_get_security() != UDS_SECURITY_LOCKED);
}

static inline int uds_is_programming(void)
{
    return (uds_get_session() == UDS_SESSION_PROGRAMMING);
}

static inline int uds_is_extended(void)
{
    return (uds_get_session() == UDS_SESSION_EXTENDED);
}

#endif /* UDS_H */
