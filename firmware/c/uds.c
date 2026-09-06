/*
 * uds.c — RX-8 ECU UDS (Unified Diagnostic Services) Subsystem (60E1D400)
 *
 * 1:1 firmware reconstruction of the UDS diagnostic services for the
 * Mazda RX-8 Renesis 13B-MSP rotary engine ECU (SH-2E / SH7055).
 *
 * Dispatch table at 0x5F57C: 29 records × 12 bytes (SID + handler dword + mask dword)
 * Main handler at 0x697E8: validates SID range, looks up dispatch, checks session gate
 * Session gate at 0x5FA7D: session-dependent SID permission (29 bytes, one per SID)
 *
 * Session mapping: bit7=allowed in default, bit6=allowed in programming, bit5=allowed in extended
 * Security level at 0xFFFFD20C: 0x7F=locked, 0x5F=level1, 0x3F=level2
 *
 * Flags word at 0xD206: bits 0-3 = session, bit28 = in-progress marker
 * Copy to/from RAM at 0xD208/0xD20A (shadow state)
 *
 * Source: uds_obd_analysis.md, IDA session ae00d360
 */

#include "platform.h"
#include "uds.h"
#include "eeprom.h"
#include "timer.h"
#include "boot.h"

/* ====================================================================== */
/*  Internal Constants                                                     */
/* ====================================================================== */

/* SID range validation limits (from 0x697E8) */
#define UDS_SID_MIN             0x01
#define UDS_SID_MAX_NORMAL      0x3E
#define UDS_SID_MAX_HIGH        0x87
#define UDS_SID_OBD_MIN         0xB1
#define UDS_SID_OBD_MAX         0xB8

/* Dispatch table stride */
#define DISPATCH_STRIDE         12

/* ====================================================================== */
/*  Internal State                                                         */
/* ====================================================================== */

/* UDS flags word: session bits 0-3, in-progress bit28 */
static uint32_t uds_flags = 0;

/* Shadow copies */
static uint8_t uds_session_shadow = 0;
static uint8_t uds_security_shadow = 0;

/* ====================================================================== */
/*  Initialization                                                         */
/* ====================================================================== */

/**
 * uds_init — Initialize UDS subsystem.
 *
 * Sets default session, locks security, initializes flags.
 */
void uds_init(void)
{
    uds_set_session(UDS_SESSION_DEFAULT);
    uds_set_security(UDS_SECURITY_LOCKED);

    uds_flags = 0;
    uds_session_shadow = UDS_SESSION_DEFAULT;
    uds_security_shadow = UDS_SECURITY_LOCKED;
}

/* ====================================================================== */
/*  Dispatch Table                                                         */
/* ====================================================================== */

/**
 * uds_dispatch_lookup — Look up SID in dispatch table.
 * ROM address: 0x697E8 (inline in main handler)
 *
 * @param sid  Service ID to look up
 * @return Handler function address (0 if not found)
 */
uint32_t uds_dispatch_lookup(uint8_t sid)
{
    volatile uint8_t *table = (volatile uint8_t *)(uintptr_t)UDS_DISPATCH_TABLE_BASE;

    for (uint8_t i = 0; i < UDS_DISPATCH_MAX_SLOTS; i++) {
        uint8_t entry_sid = table[i * DISPATCH_STRIDE + UDS_DISP_SID_OFFSET];

        if (entry_sid == sid) {
            /* Read handler address (4 bytes, big-endian SH-2) */
            uint32_t addr = 0;
            addr |= (uint32_t)table[i * DISPATCH_STRIDE + UDS_DISP_HANDLER_OFFSET] << 24;
            addr |= (uint32_t)table[i * DISPATCH_STRIDE + UDS_DISP_HANDLER_OFFSET + 1] << 16;
            addr |= (uint32_t)table[i * DISPATCH_STRIDE + UDS_DISP_HANDLER_OFFSET + 2] << 8;
            addr |= (uint32_t)table[i * DISPATCH_STRIDE + UDS_DISP_HANDLER_OFFSET + 3];
            return addr;
        }
    }

    return 0;  /* Not found */
}

/**
 * uds_session_gate — Check SID permission for current session.
 * ROM address: 0x5FA7D
 *
 * The session gate is a 29-byte table (one per dispatch slot).
 * Each byte encodes which sessions allow the corresponding SID:
 *   bit7 = allowed in default session (0x01)
 *   bit6 = allowed in programming session (0x02)
 *   bit5 = allowed in extended session (0x03)
 *
 * @param sid  Service ID to check
 * @return 1 if allowed, 0 if denied
 */
int uds_session_gate(uint8_t sid)
{
    volatile uint8_t *gate = (volatile uint8_t *)(uintptr_t)0x5FA7D;
    uint8_t session = uds_get_session();

    /* Find the SID in the dispatch table to get its gate index */
    for (uint8_t i = 0; i < UDS_DISPATCH_MAX_SLOTS; i++) {
        volatile uint8_t *entry = (volatile uint8_t *)(uintptr_t)
            (UDS_DISPATCH_TABLE_BASE + (i * DISPATCH_STRIDE));

        if (entry[UDS_DISP_SID_OFFSET] == sid) {
            uint8_t mask = gate[i];

            /* Check session permission */
            switch (session) {
                case UDS_SESSION_DEFAULT:
                    return (mask & 0x80) != 0;  /* bit7 */
                case UDS_SESSION_PROGRAMMING:
                    return (mask & 0x40) != 0;  /* bit6 */
                case UDS_SESSION_EXTENDED:
                    return (mask & 0x20) != 0;  /* bit5 */
                default:
                    return 0;
            }
        }
    }

    return 0;  /* SID not in table */
}

/* ====================================================================== */
/*  Response Helpers                                                       */
/* ====================================================================== */

/**
 * uds_negative_response — Build negative response.
 * ROM address: 0x6980E
 *
 * @param sid      Original SID
 * @param nrc      Negative response code
 * @param response Output buffer
 * @return Response length (3 bytes)
 */
int uds_negative_response(uint8_t sid, uint8_t nrc, uint8_t *response)
{
    response[0] = UDS_SID_NEGATIVE_RESP;
    response[1] = sid;
    response[2] = nrc;
    return 3;
}

/**
 * Build positive response header.
 * Returns length of header written (2 bytes: SID+0x40, sub_func).
 */
static int build_positive_header(uint8_t sid, uint8_t sub_func,
                                 uint8_t *response)
{
    response[0] = sid + UDS_POS_RESPONSE_OFFSET;
    response[1] = sub_func;
    return 2;
}

/* ====================================================================== */
/*  Main Handler                                                           */
/* ====================================================================== */

/**
 * uds_handler — Main UDS request handler.
 * ROM address: 0x697E8, Size: ~250 bytes
 *
 * Flow:
 *   1. Validate SID range
 *   2. Look up handler in dispatch table (0x5F57C)
 *   3. Check session gate (0x5FA7D)
 *   4. Dispatch to handler function
 *   5. Build response
 *
 * @param request   Request buffer (SID + data)
 * @param req_len   Request length
 * @param response  Response buffer
 * @return Response length, or negative NRC on failure
 */
int uds_handler(const uint8_t *request, uint8_t req_len, uint8_t *response)
{
    if (req_len < 1) {
        return uds_negative_response(0, UDS_NRC_INCORRECT_MSG_LEN, response);
    }

    uint8_t sid = request[0];

    /* SID range validation */
    if ((sid < UDS_SID_MIN) ||
        (sid > UDS_SID_MAX_NORMAL && sid < UDS_SID_OBD_MIN) ||
        (sid > UDS_SID_OBD_MAX && sid < UDS_SID_MAX_HIGH) ||
        (sid > UDS_SID_MAX_HIGH && sid < UDS_SID_OBD_MIN) ||
        (sid > UDS_SID_OBD_MAX)) {
        return uds_negative_response(sid, UDS_NRC_SERVICE_NOT_SUPPORTED,
                                     response);
    }

    /* Tester present: always allowed, no dispatch needed */
    if (sid == UDS_SID_TESTER_PRESENT) {
        *(volatile uint8_t *)UDS_TESTER_PRESENT_ADDR = 1;
        response[0] = UDS_SID_TESTER_PRESENT + UDS_POS_RESPONSE_OFFSET;
        response[1] = (req_len > 1) ? request[1] : 0x00;
        return 2;
    }

    /* Look up handler in dispatch table */
    uint32_t handler = uds_dispatch_lookup(sid);
    if (handler == 0) {
        return uds_negative_response(sid, UDS_NRC_SERVICE_NOT_SUPPORTED,
                                     response);
    }

    /* Check session gate */
    if (!uds_session_gate(sid)) {
        return uds_negative_response(sid, UDS_NRC_CONDITIONS_NOT_CORRECT,
                                     response);
    }

    /* Dispatch to handler (function pointer cast) */
    typedef int (*handler_fn)(const uint8_t *, uint8_t, uint8_t *);
    handler_fn fn = (handler_fn)(uintptr_t)handler;

    int result = fn(request + 1, req_len - 1, response);

    return result;
}

/* ====================================================================== */
/*  SID 0x10 — Session Control                                             */
/* ====================================================================== */

/**
 * obd_sid10_sessionControl — UDS SID 0x10 session control.
 * ROM address: 0x586C8, Size: 102 bytes
 *
 * Sub-function 0x01: defaultSession
 * Sub-function 0x02: programmingSession
 * Sub-function 0x03: extendedDiagnosticSession
 *
 * Transition logic:
 *   Any→Default: always allowed, security locked
 *   Default→Extended: allowed
 *   Extended→Programming: allowed (security must be unlocked first)
 *   Programming→Default: allowed (ECU reset follows)
 *
 * @param sub_func  Sub-function byte
 * @param data      Additional data (timing parameters)
 * @param data_len  Data length
 * @param response  Response buffer
 * @return Response length, or negative NRC
 */
int obd_sid10_sessionControl(uint8_t sub_func, const uint8_t *data,
                             uint8_t data_len, uint8_t *response)
{
    uint8_t current = uds_get_session();
    (void)data;
    (void)data_len;

    switch (sub_func) {
        case UDS_SESSION_DEFAULT:
            /* Any session → default: always allowed */
            uds_set_session(UDS_SESSION_DEFAULT);
            uds_set_security(UDS_SECURITY_LOCKED);
            break;

        case UDS_SESSION_EXTENDED:
            /* Default → extended: allowed */
            /* Programming → extended: not typical, allow */
            uds_set_session(UDS_SESSION_EXTENDED);
            break;

        case UDS_SESSION_PROGRAMMING:
            /* Extended → programming: only with security unlocked */
            if (current == UDS_SESSION_EXTENDED) {
                if (!uds_is_unlocked()) {
                    return uds_negative_response(UDS_SID_DIAG_SESSION,
                                                 UDS_NRC_SECURITY_ACCESS_DENIED,
                                                 response);
                }
                uds_set_session(UDS_SESSION_PROGRAMMING);
            } else {
                return uds_negative_response(UDS_SID_DIAG_SESSION,
                                             UDS_NRC_CONDITIONS_NOT_CORRECT,
                                             response);
            }
            break;

        default:
            return uds_negative_response(UDS_SID_DIAG_SESSION,
                                         UDS_NRC_SUB_NOT_SUPPORTED, response);
    }

    /* Apply timing parameters from request data.
     * data[0..1] = P2 server max (big-endian, ms)
     * data[2..4] = P2* server max (big-endian, ms)
     * ROM handler at 0x586C8 writes timing values to 0xD210/0xD212 */
    if (data_len >= 3) {
        uint16_t p2_max = ((uint16_t)data[1] << 8) | data[2];
        *(volatile uint16_t *)0xFFFFD210 = p2_max;
        if (data_len >= 5) {
            uint32_t p2_star_max = ((uint32_t)data[3] << 16) |
                                   ((uint32_t)data[4] << 8);
            *(volatile uint16_t *)0xFFFFD212 = (uint16_t)(p2_star_max / 10);
        }
    }

    return build_positive_header(UDS_SID_DIAG_SESSION, sub_func, response);
}

/* ====================================================================== */
/*  SID 0x27 — Security Access                                             */
/* ====================================================================== */

/**
 * obd_sid27_securityAccess — UDS SID 0x27 security access.
 * ROM address: 0x584A0, Size: 56 bytes
 *
 * Sub-function 0x01/0x03: requestSeed
 *   → Generate random seed, store in RAM
 *   → Return seed in response
 *
 * Sub-function 0x02/0x04: sendKey
 *   → Validate key against stored seed
 *   → If valid: unlock security level
 *
 * Seed/key algorithm: XOR + rotate (see eeprom.h for key table)
 *
 * @param sub_func  Sub-function byte
 * @param data      Seed/key data
 * @param data_len  Data length
 * @param response  Response buffer
 * @return Response length, or negative NRC
 */
int obd_sid27_securityAccess(uint8_t sub_func, const uint8_t *data,
                             uint8_t data_len, uint8_t *response)
{
    (void)data;  /* Used in sendKey path only */

    switch (sub_func) {
        case UDS_SEC_SUB_REQ_SEED_1:
        case UDS_SEC_SUB_REQ_SEED_2: {
            /* Request seed: generate and return */
            if (data_len < 1) {
                return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                             UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }

            /* TODO: Implement seed generation from 0x584A0
             * ROM handler generates seed based on ECU serial number
             * and a pseudo-random counter. For now, use placeholder. */
            uint8_t seed[4] = {0x12, 0x34, 0x56, 0x78};

            int len = build_positive_header(UDS_SID_SECURITY_ACCESS,
                                            sub_func, response);
            response[len] = seed[0];
            response[len + 1] = seed[1];
            response[len + 2] = seed[2];
            response[len + 3] = seed[3];
            return len + 4;
        }

        case UDS_SEC_SUB_SEND_KEY_1:
        case UDS_SEC_SUB_SEND_KEY_2: {
            /* Send key: validate and unlock */
            if (data_len < 4) {
                return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                             UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }

            /* TODO: Implement key validation from 0x584A0
             * ROM handler computes expected key from stored seed
             * and compares with received key. Uses XOR + rotate. */
            int valid = 1;  /* Placeholder */

            if (valid) {
                /* Determine security level from sub-function */
                uint8_t level = (sub_func == UDS_SEC_SUB_SEND_KEY_1)
                                ? UDS_SECURITY_LEVEL_1
                                : UDS_SECURITY_LEVEL_2;
                uds_set_security(level);
                return build_positive_header(UDS_SID_SECURITY_ACCESS,
                                             sub_func, response);
            } else {
                return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                             UDS_NRC_INVALID_KEY, response);
            }
        }

        default:
            return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                         UDS_NRC_SUB_NOT_SUPPORTED, response);
    }
}

/* ====================================================================== */
/*  SID 0xB1 — ECU Reset                                                   */
/* ====================================================================== */

/**
 * obd_sidB1_ecuReset — UDS SID 0xB1 ECU reset.
 * ROM address: 0x57024, Size: 50 bytes
 *
 * @param sub_func  Reset type (0x01=hard, 0x02=keyOff)
 * @param response  Response buffer
 * @return Response length, or negative NRC
 */
int obd_sidB1_ecuReset(uint8_t sub_func, uint8_t *response)
{
    int len = build_positive_header(0xB1, sub_func, response);

    /* ROM handler at 0x57024: sends response, then triggers reset.
     * Sub-function determines reset type:
     *   0x01 = hard reset (watchdog)
     *   0x02 = key off reset
     * For now, return positive response.
     * The actual reset is triggered after the response is sent. */
    if (sub_func != 0x01 && sub_func != 0x02) {
        return uds_negative_response(0xB1, UDS_NRC_SUB_NOT_SUPPORTED, response);
    }

    return len;
}

/* ====================================================================== */
/*  SID 0x22 — Read Data By Identifier                                     */
/* ====================================================================== */

/**
 * obd_sid22_readDataByIdentifier — UDS SID 0x22 read data by ID.
 * ROM address: 0x588F2, Size: 210 bytes
 *
 * Supported DIDs (partial list from ROM analysis):
 *   0xF806: ECU software number
 *   0xF808: ECU serial number
 *   0xF80B: Calibration verification number
 *   0xF187: Spare part number
 *   0xF18A: Vehicle manufacturer ECU software number
 *   0xF190: VIN (17 bytes)
 *
 * @param data      DID list (2 bytes each)
 * @param data_len  Data length
 * @param response  Response buffer
 * @return Response length, or negative NRC
 */
int obd_sid22_readDataByIdentifier(const uint8_t *data, uint8_t data_len,
                                   uint8_t *response)
{
    if (data_len < 2 || (data_len % 2) != 0) {
        return uds_negative_response(UDS_SID_READ_DATA_ID,
                                     UDS_NRC_INCORRECT_MSG_LEN, response);
    }

    response[0] = UDS_SID_READ_DATA_ID + UDS_POS_RESPONSE_OFFSET;
    uint8_t idx = 1;

    for (uint8_t i = 0; i < data_len; i += 2) {
        uint16_t did = ((uint16_t)data[i] << 8) | data[i + 1];

        /* DID lookup table from ROM:0x588F2 dispatch */
        switch (did) {
            case 0xF806: {
                /* ECU software number — read from ROM at 0x5FF800 region */
                response[idx] = 0xF8; response[idx + 1] = 0x06;
                response[idx + 2] = 0x60;  /* SW major version */
                response[idx + 3] = 0xE1;
                response[idx + 4] = 0xD4;
                response[idx + 5] = 0x00;
                idx += 6;
                break;
            }
            case 0xF808: {
                /* ECU serial number — 4 bytes from EEPROM */
                response[idx] = 0xF8; response[idx + 1] = 0x08;
                response[idx + 2] = 0x00;
                response[idx + 3] = 0x00;
                response[idx + 4] = 0x00;
                response[idx + 5] = 0x00;
                idx += 6;
                break;
            }
            case 0xF187: {
                /* Spare part number — 4 bytes */
                response[idx] = 0xF1; response[idx + 1] = 0x87;
                response[idx + 2] = 0x00;
                response[idx + 3] = 0x00;
                response[idx + 4] = 0x00;
                response[idx + 5] = 0x00;
                idx += 6;
                break;
            }
            case 0xF190: {
                /* VIN — 17 bytes */
                response[idx] = 0xF1; response[idx + 1] = 0x90;
                /* Placeholder VIN */
                static const char vin[] = "JM1FE179X60000001";
                for (uint8_t j = 0; j < 17; j++) {
                    response[idx + 2 + j] = (uint8_t)vin[j];
                }
                idx += 19;
                break;
            }
            case 0xF193: {
                /* ECU manufacturing date — 2 bytes (BCD: year, month) */
                response[idx] = 0xF1; response[idx + 1] = 0x93;
                response[idx + 2] = 0x06;  /* Year: 2006 */
                response[idx + 3] = 0x04;  /* Month: April */
                idx += 4;
                break;
            }
            case 0xF18A: {
                /* Vehicle manufacturer ECU software number */
                response[idx] = 0xF1; response[idx + 1] = 0x8A;
                response[idx + 2] = 0x00;
                response[idx + 3] = 0x00;
                idx += 4;
                break;
            }
            case 0x0202: {
                /* Engine coolant temperature (from RAM 0xFFFFCA00) */
                response[idx] = 0x02; response[idx + 1] = 0x02;
                response[idx + 2] = *(volatile const uint8_t *)0xFFFFCA00;
                idx += 3;
                break;
            }
            case 0x010C: {
                /* Engine RPM (16-bit from RAM 0xFFFFCA02, 0.25 rpm/bit) */
                response[idx] = 0x01; response[idx + 1] = 0x0C;
                uint16_t rpm_raw = *(volatile const uint16_t *)0xFFFFCA02;
                response[idx + 2] = (uint8_t)(rpm_raw >> 8);
                response[idx + 3] = (uint8_t)(rpm_raw);
                idx += 4;
                break;
            }
            case 0x010D: {
                /* Vehicle speed (from RAM 0xFFFFCA04, km/h) */
                response[idx] = 0x01; response[idx + 1] = 0x0D;
                response[idx + 2] = *(volatile const uint8_t *)0xFFFFCA04;
                idx += 3;
                break;
            }
            case 0x0105: {
                /* Coolant temperature (scaled from RAM) */
                response[idx] = 0x01; response[idx + 1] = 0x05;
                response[idx + 2] = *(volatile const uint8_t *)0xFFFFCA00;
                idx += 3;
                break;
            }
            default:
                /* Unknown DID — return NRC for this DID */
                response[idx] = data[i];
                response[idx + 1] = data[i + 1];
                response[idx + 2] = UDS_NRC_REQUEST_OUT_OF_RANGE;
                idx += 3;
                break;
        }
    }

    return idx;
}

/* ====================================================================== */
/*  SID 0x23 — Read Memory By Address                                      */
/* ====================================================================== */

/**
 * obd_sid23_readMemoryByAddress — UDS SID 0x23 read memory.
 * ROM address: 0x57028
 *
 * @param data      Address/length format + address + length
 * @param data_len  Data length
 * @param response  Response buffer
 * @return Response length, or negative NRC
 */
int obd_sid23_readMemoryByAddress(const uint8_t *data, uint8_t data_len,
                                  uint8_t *response)
{
    (void)data;  /* TODO: implement address/length parsing */

    if (data_len < 3) {
        return uds_negative_response(UDS_SID_READ_MEM_ADDR,
                                     UDS_NRC_INCORRECT_MSG_LEN, response);
    }

    /* TODO: Implement memory read from 0x57028
     * Format byte encodes address/length byte counts.
     * Must validate address is in allowed range (see ECU memory map).
     * For now, return NRC. */

    return uds_negative_response(UDS_SID_READ_MEM_ADDR,
                                 UDS_NRC_REQUEST_OUT_OF_RANGE, response);
}

/* ====================================================================== */
/*  SID 0x2E — Write Data By Identifier                                    */
/* ====================================================================== */

/**
 * obd_sid2E_writeDataByIdentifier — UDS SID 0x2E write data by ID.
 * ROM address: 0x5798E, Size: 246 bytes
 *
 * @param data      DID + data to write
 * @param data_len  Data length
 * @param response  Response buffer
 * @return Response length, or negative NRC
 */
int obd_sid2E_writeDataByIdentifier(const uint8_t *data, uint8_t data_len,
                                    uint8_t *response)
{
    if (data_len < 3) {
        return uds_negative_response(UDS_SID_WRITE_DATA_ID,
                                     UDS_NRC_INCORRECT_MSG_LEN, response);
    }

    uint16_t did = ((uint16_t)data[0] << 8) | data[1];

    /* TODO: Implement DID write from 0x5798E
     * ROM handler has a DID write table with ~8 entries.
     * Each entry: (DID, handler_addr, max_data_length).
     * Writable DIDs may include:
     *   0xF806: ECU software number (programming session only)
     *   0xF190: VIN (extended session, security unlocked)
     * For now, return NRC for all DIDs. */
    (void)did;

    return uds_negative_response(UDS_SID_WRITE_DATA_ID,
                                 UDS_NRC_REQUEST_OUT_OF_RANGE, response);
}

/* ====================================================================== */
/*  SID 0x31 — Routine Control                                             */
/* ====================================================================== */

/**
 * obd_sid31_routineControl — UDS SID 0x31 routine control.
 * ROM address: 0x5A9C0
 *
 * Sub-function 0x01: startRoutine
 * Sub-function 0x02: stopRoutine
 * Sub-function 0x03: requestRoutineResults
 *
 * @param sub_func  Sub-function byte
 * @param data      Routine ID + parameters
 * @param data_len  Data length
 * @param response  Response buffer
 * @return Response length, or negative NRC
 */
int obd_sid31_routineControl(uint8_t sub_func, const uint8_t *data,
                             uint8_t data_len, uint8_t *response)
{
    if (data_len < 2) {
        return uds_negative_response(UDS_SID_ROUTINE_CONTROL,
                                     UDS_NRC_INCORRECT_MSG_LEN, response);
    }

    uint16_t routine_id = ((uint16_t)data[0] << 8) | data[1];

    switch (sub_func) {
        case 0x01: {  /* startRoutine */
            switch (routine_id) {
                case 0xFF00: {
                    /* ECU reset routine — same as SID 0xB1 */
                    int len = build_positive_header(UDS_SID_ROUTINE_CONTROL,
                                                    sub_func, response);
                    response[len] = 0xFF;
                    response[len + 1] = 0x00;
                    /* ROM:0x5A9C0: triggers watchdog reset after response */
                    return len + 2;
                }
                case 0xF000: {
                    /* Erase memory — programming session only */
                    if (!uds_is_programming()) {
                        return uds_negative_response(UDS_SID_ROUTINE_CONTROL,
                            UDS_NRC_CONDITIONS_NOT_CORRECT, response);
                    }
                    int len = build_positive_header(UDS_SID_ROUTINE_CONTROL,
                                                    sub_func, response);
                    response[len] = 0xF0;
                    response[len + 1] = 0x00;
                    return len + 2;
                }
                case 0xF001: {
                    /* Check programming dependencies */
                    int len = build_positive_header(UDS_SID_ROUTINE_CONTROL,
                                                    sub_func, response);
                    response[len] = 0xF0;
                    response[len + 1] = 0x01;
                    response[len + 2] = 0x00;  /* OK */
                    return len + 3;
                }
                default:
                    return uds_negative_response(UDS_SID_ROUTINE_CONTROL,
                        UDS_NRC_REQUEST_OUT_OF_RANGE, response);
            }
        }
        case 0x02:  /* stopRoutine */
        case 0x03: {  /* requestRoutineResults */
            switch (routine_id) {
                case 0xFF00: {
                    int len = build_positive_header(UDS_SID_ROUTINE_CONTROL,
                                                    sub_func, response);
                    response[len] = 0xFF;
                    response[len + 1] = 0x00;
                    return len + 2;
                }
                default:
                    return uds_negative_response(UDS_SID_ROUTINE_CONTROL,
                        UDS_NRC_REQUEST_OUT_OF_RANGE, response);
            }
        }
        default:
            return uds_negative_response(UDS_SID_ROUTINE_CONTROL,
                                         UDS_NRC_SUB_NOT_SUPPORTED, response);
    }
}

/* ====================================================================== */
/*  SID 0x34 — Request Download                                            */
/* ====================================================================== */

/**
 * obd_sid34_requestDownload — UDS SID 0x34 request download.
 * ROM address: 0x56862
 *
 * @param data      Compression/encryption format + address + size
 * @param data_len  Data length
 * @param response  Response buffer
 * @return Response length, or negative NRC
 */
int obd_sid34_requestDownload(const uint8_t *data, uint8_t data_len,
                              uint8_t *response)
{
    (void)data;  /* TODO: implement format/address/size parsing */

    if (data_len < 1) {
        return uds_negative_response(UDS_SID_REQ_DOWNLOAD,
                                     UDS_NRC_INCORRECT_MSG_LEN, response);
    }

    /* Must be in programming session */
    if (!uds_is_programming()) {
        return uds_negative_response(UDS_SID_REQ_DOWNLOAD,
                                     UDS_NRC_CONDITIONS_NOT_CORRECT, response);
    }

    /* TODO: Implement download request from 0x56862
     * ROM handler validates memory range, sets up download state.
     * For now, return NRC. */

    return uds_negative_response(UDS_SID_REQ_DOWNLOAD,
                                 UDS_NRC_REQUEST_OUT_OF_RANGE, response);
}

/* ====================================================================== */
/*  SID 0x36 — Transfer Data                                               */
/* ====================================================================== */

/**
 * obd_sid36_transferData — UDS SID 0x36 transfer data.
 * ROM address: 0x57A5C
 *
 * @param block_seq  Block sequence counter
 * @param data       Transfer data
 * @param data_len   Data length
 * @param response   Response buffer
 * @return Response length, or negative NRC
 */
int obd_sid36_transferData(uint8_t block_seq, const uint8_t *data,
                           uint8_t data_len, uint8_t *response)
{
    (void)data;  /* TODO: implement data transfer to flash/RAM */

    if (data_len < 1) {
        return uds_negative_response(UDS_SID_TRANSFER_DATA,
                                     UDS_NRC_INCORRECT_MSG_LEN, response);
    }

    /* Must be in programming session */
    if (!uds_is_programming()) {
        return uds_negative_response(UDS_SID_TRANSFER_DATA,
                                     UDS_NRC_CONDITIONS_NOT_CORRECT, response);
    }

    /* TODO: Implement data transfer from 0x57A5C
     * ROM handler writes data to flash/RAM at specified address.
     * Validates block sequence counter.
     * For now, return positive response only. */

    return build_positive_header(UDS_SID_TRANSFER_DATA, block_seq, response);
}

/* ====================================================================== */
/*  SID 0x37 — Request Transfer Exit                                       */
/* ====================================================================== */

/**
 * obd_sid37_requestTransferExit — UDS SID 0x37 transfer exit.
 * ROM address: 0x57506
 *
 * @param response  Response buffer
 * @return Response length, or negative NRC
 */
int obd_sid37_requestTransferExit(uint8_t *response)
{
    /* Must be in programming session */
    if (!uds_is_programming()) {
        return uds_negative_response(UDS_SID_REQ_TRANS_EXIT,
                                     UDS_NRC_CONDITIONS_NOT_CORRECT, response);
    }

    /* TODO: Implement transfer exit from 0x57506
     * ROM handler finalizes download, verifies checksum.
     * For now, return positive response. */

    return build_positive_header(UDS_SID_REQ_TRANS_EXIT, 0x00, response);
}

/* ====================================================================== */
/*  OBD-II Service Handlers (Stubs)                                        */
/* ====================================================================== */

/**
 * obd_service_1 — OBD-II Service 1: current data.
 * ROM address: 0x59D84
 *
 * PIDs supported: 0x00, 0x01-0x0C, 0x0D, 0x05, 0x0F, 0x11, 0x14
 * Each PID reads from engine RAM at known addresses.
 */
int obd_service_1(uint8_t pid, uint8_t *response)
{
    response[0] = 0x41;  /* Positive response = SID + 0x40 */
    response[1] = pid;

    switch (pid) {
        case 0x00: {
            /* PIDs supported [01-20] — bitmask */
            response[2] = 0x80;  /* PID 00: bit31 */
            response[3] = 0x08;  /* PID 05: bit03, PID 0D: bit05 */
            response[4] = 0x10;  /* PID 0C: bit12 */
            response[5] = 0x01;  /* PID 11: bit17 */
            return 6;
        }
        case 0x01: {
            /* Monitor status since DTCs cleared */
            response[2] = 0x00;
            response[3] = 0x00;
            response[4] = 0x00;
            response[5] = 0x00;
            return 6;
        }
        case 0x05: {
            /* Engine coolant temperature: (A - 40) °C */
            uint8_t ect = *(volatile const uint8_t *)0xFFFFCA00;
            response[2] = ect;
            return 3;
        }
        case 0x0C: {
            /* Engine RPM: ((A*256)+B) / 4 */
            uint16_t rpm_raw = *(volatile const uint16_t *)0xFFFFCA02;
            response[2] = (uint8_t)(rpm_raw >> 8);
            response[3] = (uint8_t)(rpm_raw & 0xFF);
            return 4;
        }
        case 0x0D: {
            /* Vehicle speed: A km/h */
            response[2] = *(volatile const uint8_t *)0xFFFFCA04;
            return 3;
        }
        case 0x11: {
            /* Throttle position: A*100/255 % */
            response[2] = *(volatile const uint8_t *)0xFFFFCA06;
            return 3;
        }
        case 0x14: {
            /* O2 sensor voltages: bank 1 sensor 1 */
            response[2] = *(volatile const uint8_t *)0xFFFFCA08;
            response[3] = *(volatile const uint8_t *)0xFFFFCA09;
            return 4;
        }
        default:
            /* PID not supported — return NRC */
            response[0] = 0x7F;
            response[1] = 0x01;
            response[2] = 0x12;  /* subFunctionNotSupported */
            return 3;
    }
}

/**
 * obd_service_2 — OBD-II Service 2: freeze frame data.
 * ROM address: 0x59E16
 */
int obd_service_2(uint8_t pid, uint8_t frame, uint8_t *response)
{
    /* TODO: Implement OBD-II service 2 from 0x59E16 */
    (void)pid;
    (void)frame;
    response[0] = 0x42;
    return 1;
}

/**
 * obd_service_3 — OBD-II Service 3: stored DTCs.
 * ROM address: 0x59E42
 *
 * Reads DTC list from EEPROM/DTC storage.
 * Returns 0x43 + DTC pairs (3 bytes each) + 1 status byte.
 */
int obd_service_3(uint8_t *response)
{
    response[0] = 0x43;  /* Positive response */

    /* ROM:0x59E42: reads DTC count from RAM at 0xFFFFD400,
     * then iterates DTC table at 0xFFFFD402.
     * Each DTC: 3 bytes (high, mid, low) + 1 status byte.
     * For now, return count=0 (no DTCs). */
    response[1] = 0x00;  /* Number of DTCs */

    return 2;
}

/**
 * obd_service_4 — OBD-II Service 4: clear DTCs.
 * ROM address: 0x59E98
 */
int obd_service_4(uint8_t *response)
{
    /* TODO: Implement OBD-II service 4 from 0x59E98 */
    response[0] = 0x44;
    return 1;
}

/**
 * obd_service_6 — OBD-II Service 6.
 * ROM address: 0x59EDE
 */
int obd_service_6(uint8_t *response)
{
    /* TODO: Implement OBD-II service 6 from 0x59EDE */
    response[0] = 0x46;
    return 1;
}

/**
 * obd_service_7 — OBD-II Service 7: pending DTCs.
 * ROM address: 0x59EE2
 */
int obd_service_7(uint8_t *response)
{
    /* TODO: Implement OBD-II service 7 from 0x59EE2 */
    response[0] = 0x47;
    return 1;
}

/**
 * obd_service_9 — OBD-II Service 9: vehicle information.
 * ROM address: 0x59C8C
 */
int obd_service_9(uint8_t sub_func, uint8_t *response)
{
    /* TODO: Implement OBD-II service 9 from 0x59C8C */
    (void)sub_func;
    response[0] = 0x49;
    return 1;
}

/**
 * obd_service_A — OBD-II Service A: pending DTCs.
 * ROM address: 0x59F26
 */
int obd_service_A(uint8_t *response)
{
    /* TODO: Implement OBD-II service A from 0x59F26 */
    response[0] = 0x4A;
    return 1;
}
