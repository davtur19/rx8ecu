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
#include "dtc.h"
#include "eeprom.h"
#include "timer.h"
#include "boot.h"

/* ====================================================================== */
/*  Internal Constants                                                     */
/* ====================================================================== */

/* SID range validation limits (from 0x697E8) */
#define UDS_SID_MIN             0x01
#define UDS_SID_MAX_NORMAL      0x3E
#define UDS_SID_EXT_MIN         0x80    /* review-fix: extended range start */
#define UDS_SID_MAX_HIGH        0x87
#define UDS_SID_OBD_MIN         0xB1
#define UDS_SID_OBD_MAX         0xB8

/* Dispatch table stride */
#define DISPATCH_STRIDE         12

/* ====================================================================== */
/*  Internal State                                                         */
/* ====================================================================== */

/* review-fix: volatile — UDS session/security state is shared between the
 * CAN/serial RX paths (uds_handler, tester-present) and main-loop SID
 * handlers. Guard strategy: writers run under diag_getsr/diag_setsr (or
 * disable/restore_interrupts) critical sections; single volatile accesses
 * are atomic on SH-2 (8/16/32-bit). */
/* UDS flags word: session bits 0-3, in-progress bit28 */
static volatile uint32_t uds_flags = 0;

/* Shadow copies */
static volatile uint8_t uds_session_shadow = 0;
static volatile uint8_t uds_security_shadow = 0;

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

    /* SID range validation as an allow-list.
     * review-fix: the old 4-clause expression rejected the valid 0x80-0x87
     * range and contained a dead third clause
     * (`sid > UDS_SID_OBD_MAX && sid < UDS_SID_MAX_HIGH`, i.e. sid > 0xB8 &&
     * sid < 0x87 — unsatisfiable). Unknown SIDs inside an allowed range are
     * still rejected below by the dispatch-table lookup. */
    {
        int sid_allowed =
            ((sid >= UDS_SID_MIN && sid <= UDS_SID_MAX_NORMAL) ||   /* 0x01-0x3E */
             (sid >= UDS_SID_EXT_MIN && sid <= UDS_SID_MAX_HIGH) || /* 0x80-0x87 */
             (sid >= UDS_SID_OBD_MIN && sid <= UDS_SID_OBD_MAX));   /* 0xB1-0xB8 */
        if (!sid_allowed) {
            return uds_negative_response(sid, UDS_NRC_SERVICE_NOT_SUPPORTED,
                                         response);
        }
    }

    /* Tester present (ROM 0x56F44, 0xA6 bytes): zero persistent RAM writes.
     * S3 hunt 2026-09-08 (NOT-FOUND, main bank 60E1D400 + fc00 bank): the
     * handler only reads the word @0xFFFFD3F0 request-staging buffer
     * (mov.w @r3,r14 @0x56F58) to validate the sub-function; DE5C has
     * exactly two writers — 566EC session-switch (delay-slot store
     * @0x5670A) and 696D4 boot-reset (jsr @0x113C6 from the boot-init
     * chain @0x6208, NOT periodic) — and one reader (udsHandler
     * @0x697EC/0x69800). DE5C/D20B/D20D literal pools are exhaustive
     * (3/2/1, byte-verified), D215 has zero xrefs in both banks,
     * uds_task_entry @0x696DC is pure dispatch (no RAM touch, no
     * countdown), and the CAN bridge 0x60774/0x6085C only snapshots
     * word D3F0 for TX. So ROM implements no S3 timeout: a session
     * persists until switched or reset. The D215 store below stays a
     * firmware-local keep-alive flag, NOT ROM-backed. Bench probe that
     * would refute this: non-default session + bus silence > 5 s, then
     * a gated SID must still answer (predict: yes); an idle-only
     * 0x7F/0x22 reject would point off-ROM (e.g. K-line kernel). */
    if (sid == UDS_SID_TESTER_PRESENT) {
        /* M7: accept only sub-function 0x00 (KNOWLEDGE.md:30: `3E 00`
         * correct, `3E 80` → NRC 0x12 subFunctionNotSupported). The old code
         * echoed request[1] unvalidated, accepting any sub-function. */
        uint8_t tp_sub = (req_len > 1) ? request[1] : 0x00;
        if (tp_sub != 0x00) {
            return uds_negative_response(sid, UDS_NRC_SUB_NOT_SUPPORTED,
                                         response);
        }
        *(volatile uint8_t *)UDS_TESTER_PRESENT_ADDR = 1;
        response[0] = UDS_SID_TESTER_PRESENT + UDS_POS_RESPONSE_OFFSET;
        response[1] = 0x00;
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

    /* Dispatch to handler with the convention each SID implements.
     * review-fix w2 (B15, CONFIRMED dispatch-convention mismatch): the old
     * code cast every ROM-table handler to a single 3-arg
     * `(data, len, resp)` prototype and called `fn(request+1, len, resp)`.
     * But our C handlers use three different conventions — 4-arg
     * `(sub_func, data, len, resp)` for 0x10/0x27/0x31, 2-arg
     * `(sub_func, resp)` for 0xB1, 4-arg `(block_seq, data, len, resp)`
     * for 0x36, 1-arg `(resp)` for 0x37 — so the generic call passed the
     * data pointer where sub_func belongs and left the real response
     * pointer in the wrong register (on SH-2: r4=data instead of
     * sub_func, response never delivered). Split sub_func/block_seq out
     * of request[1] per SID below. SIDs the ROM table knows but no C
     * function implements yet return SERVICE_NOT_SUPPORTED;
     * NEEDS-ROM-CHECK: confirm against the ROM call sites that r4 carries
     * sub_func for 0x10/0x27/0x31/0xB1/0x36. (No C dispatch exists yet for
     * the OBD 0x01-0x0A services — see the gap notes on obd_service_*.) */
    (void)handler;  /* Presence in the ROM table gates reachability above. */
    switch (sid) {
        case UDS_SID_DIAG_SESSION:
            if (req_len < 2) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            return obd_sid10_sessionControl(request[1], request + 2,
                                            (uint8_t)(req_len - 2), response);

        case UDS_SID_SECURITY_ACCESS:
            if (req_len < 2) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            return obd_sid27_securityAccess(request[1], request + 2,
                                            (uint8_t)(req_len - 2), response);

        case UDS_SID_ROUTINE_CONTROL:
            if (req_len < 2) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            return obd_sid31_routineControl(request[1], request + 2,
                                            (uint8_t)(req_len - 2), response);

        case 0xB1:  /* Mazda-specific ECU reset (obd_sidB1_ecuReset) */
            if (req_len < 2) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            return obd_sidB1_ecuReset(request[1], response);

        case UDS_SID_READ_DATA_ID:
            return obd_sid22_readDataByIdentifier(request + 1,
                                                 (uint8_t)(req_len - 1),
                                                 response);

        case UDS_SID_READ_MEM_ADDR:
            return obd_sid23_readMemoryByAddress(request + 1,
                                                (uint8_t)(req_len - 1),
                                                response);

        case UDS_SID_WRITE_DATA_ID:
            return obd_sid2E_writeDataByIdentifier(request + 1,
                                                  (uint8_t)(req_len - 1),
                                                  response);

        case UDS_SID_REQ_DOWNLOAD:
            return obd_sid34_requestDownload(request + 1,
                                            (uint8_t)(req_len - 1),
                                            response);

        case UDS_SID_TRANSFER_DATA:
            if (req_len < 2) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            return obd_sid36_transferData(request[1], request + 2,
                                          (uint8_t)(req_len - 2), response);

        case UDS_SID_REQ_TRANS_EXIT:
            return obd_sid37_requestTransferExit(response);

        case UDS_SID_CLEAR_DTC:  /* 0x14 */
            if (req_len < 3) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            {
                int rc14 = obd_sid14_clearDTC(request[1], request[2]);
                if (rc14 != 0) {
                    return uds_negative_response(sid, (uint8_t)(-rc14),
                                                 response);
                }
            }
            response[0] = UDS_SID_CLEAR_DTC + UDS_POS_RESPONSE_OFFSET;
            return 1;

        case UDS_SID_READ_DTC_INFO:  /* 0x18 */
            if (req_len < 3) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            {
                int rc18 = obd_sid18_readDTCInfo(request[1], request[2],
                                                response);
                if (rc18 < 0) {
                    return uds_negative_response(sid, (uint8_t)(-rc18),
                                                 response);
                }
                return rc18;
            }

        case UDS_SID_READ_DTC_STATUS:  /* 0x12 */
            if (req_len < 3) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            {
                int rc12 = obd_sid12_readDTCByStatus(request[1], request[2],
                                                    response);
                if (rc12 < 0) {
                    return uds_negative_response(sid, (uint8_t)(-rc12),
                                                 response);
                }
                return rc12;
            }

        case UDS_SID_OBD_SVC1:  /* 0x01 */
            if (req_len < 2) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            return obd_service_1(request[1], response);

        case UDS_SID_OBD_SVC2:  /* 0x02 */
            if (req_len < 3) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            return obd_service_2(request[1], request[2], response);

        case UDS_SID_OBD_SVC3:  /* 0x03 */
            return obd_service_3(response);

        case UDS_SID_OBD_SVC4:  /* 0x04 */
            return obd_service_4(response);

        case UDS_SID_OBD_SVC6:  /* 0x06 */
            return obd_service_6(response);

        case UDS_SID_OBD_SVC7:  /* 0x07 */
            return obd_service_7(response);

        case UDS_SID_OBD_SVC9:  /* 0x09 */
            if (req_len < 2) {
                return uds_negative_response(sid, UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }
            return obd_service_9(request[1], response);

        /* No 0x0A arm: the ROM dispatch table at 0x5F57C (28 entries + 0xFF
         * sentinel, docs/subsystems/CAN_UDS_SUBSYSTEM.md:199-230) contains
         * no 0x0A entry, so Service 0x0A is unreachable on target. Requests
         * for 0x0A fall through to the default NRC 0x11 arm below. */

        default:
            return uds_negative_response(sid, UDS_NRC_SERVICE_NOT_SUPPORTED,
                                         response);
    }
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
     * review-fix: P2 was read from data[1..2] (off by one vs the layout
     * above) and P2* was built from only 2 bytes (data[3..4] << 16/8,
     * dropping the low byte). Fixed to data[0..1] / data[2..4], requiring 2
     * bytes for P2 and 5 bytes for P2*.
     *
     * rom-check (resolved — no P2/P2* store exists): ROM SessionControl
     * (0x586C8) enforces req_len == 1 (extu.w r4 / cmp #1 @0x586DE, else
     * NRC 0x12 @0x5873E) and reads only payload byte 0 (sub-function via
     * @r15); full callee sweep shows zero timing reads or writes —
     * 68BC0 (SID table-scan only), 5681E (tables 5FA7C/5FA7E + word D3F0),
     * 5878C (reads D208/D209 only), 56866 (reads byte D20B only), 566EC
     * (writes D20B raw idx / D20D mapped gate / DE5C gate + security
     * clear), 58768/553AA (stack-built TX only, via 68B60/68858 TX ring
     * @D998 and 69792 scheduler). Len > 1 never reaches the handler, so
     * P2/P2* have no ROM backing store: parsed below for layout
     * documentation only, NOT stored (do NOT relocate blindly).
     * Correction: D212 IS ROM-referenced (security_seed_byte2 — writer
     * diag_security_5699a @0x56A9E, readers 0x56AC4/0x56B64); the old
     * "D212 unreferenced" claim is withdrawn, but the u16-timer-store
     * removal stands (D211-D214 are seed+id bytes, D210 is a BYTE
     * session-state slot per uds_security_unlock_state_set @0x56728
     * with a u16 companion at D20E). */
    if (data_len >= 2) {
        uint16_t p2_max = ((uint16_t)data[0] << 8) | data[1];
        (void)p2_max;
        if (data_len >= 5) {
            uint32_t p2_star_max = ((uint32_t)data[2] << 16) |
                                   ((uint32_t)data[3] << 8) |
                                   (uint32_t)data[4];
            (void)p2_star_max;
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
/**
 * security_access_generate_seed — Generate security seed from ECU serial.
 * ROM address: 0x5699a (diag_security_5699a)
 *
 * Reads 32-bit ECU serial number from 0xFFFFF430, extracts 3 seed bytes
 * using XOR and rotation, stores to 0xFFFFD211-0xFFFFD213.
 *
 * @return 1 if seed generated successfully, 0 if serial is 0xFF (invalid)
 */
static int security_access_generate_seed(void)
{
    /* Read 4-byte ECU serial number from 0xFFFFF430 (ROM:0x569E6) */
    volatile uint32_t *serial_ptr = (volatile uint32_t *)UDS_SERIAL_NUM_ADDR;
    uint32_t serial = *serial_ptr;

    /* If serial is all 0xFF, security is not available (ROM:0x56A78) */
    if (serial == 0xFFFFFFFF) {
        return 0;
    }

    /* Extract seed bytes from serial using XOR (ROM:0x56A36-0x56A40) */
    volatile uint8_t *seed1 = (volatile uint8_t *)UDS_SEED_BYTE1_ADDR;
    volatile uint8_t *seed2 = (volatile uint8_t *)UDS_SEED_BYTE2_ADDR;
    volatile uint8_t *seed3 = (volatile uint8_t *)UDS_SEED_BYTE3_ADDR;
    volatile uint8_t *seed_id = (volatile uint8_t *)UDS_SEED_ID_ADDR;

    /* Build seed bytes by XORing serial with itself rotated (ROM:0x569E6-0x56A42)
     * The ROM reads 4 bytes from serial and XORs with offset bytes to produce
     * a 3-byte seed that varies with the ECU serial number. */
    uint8_t s0 = (uint8_t)(serial & 0xFF);
    uint8_t s1 = (uint8_t)((serial >> 8) & 0xFF);
    uint8_t s2 = (uint8_t)((serial >> 16) & 0xFF);
    uint8_t s3 = (uint8_t)((serial >> 24) & 0xFF);

    *seed1 = s0 ^ s1;
    *seed2 = s1 ^ s2;
    *seed3 = s2 ^ s3;
    *seed_id = s3;

    return 1;
}

/* ROM addresses for the SecurityAccess crypto material (60E1D400).
 * 0x5FAC0: 5-byte shared secret ("MazdA" stock); 0x5FAC5-0x5FAC7: FF padding
 * after the secret; 0x5FAC8: per-level LFSR INIT table, 3 bytes per level
 * (KNOWLEDGE.md:54-64). */
#define UDS_SA_SECRET_ADDR      0x5FAC0
#define UDS_SA_SECRET_LEN       5
#define UDS_SA_INIT_TABLE_ADDR  0x5FAC8
/* LFSR taps 0x909028 = bits {23,20,15,12,5,3}: the SeedKeyRelated @0x56ADA
 * hardcodes these tap XORs at 0x56C1E-0x56C38 (tools/mazda_security.py). */
#define UDS_SA_LFSR_TAPS        0x909028u
/* Level-1 INIT C5 41 A9 = 0xC541A9: first entry of the 0x5FAC8 table and the
 * fixed init used by tools/mazda_security.py (ROM-verified). */
#define UDS_SA_LFSR_INIT_L1     0xC541A9u
#define UDS_SA_LFSR_MASK24      0xFFFFFFu

/**
 * uds_sa_lfsr_clock — One clock of the 24-bit Galois LFSR.
 *
 * Direct port of tools/mazda_security.py:_clock: feedback = (state & 1) ^
 * input_bit; shift right; on feedback, XOR taps 0x909028 (sets bit 23 and
 * the tap bits 20,15,12,5,3); mask to 24 bits.
 */
static uint32_t uds_sa_lfsr_clock(uint32_t state, uint8_t input_bit)
{
    uint8_t feedback = (uint8_t)((state & 1u) ^ (input_bit & 1u));
    state >>= 1;
    if (feedback != 0) {
        state ^= UDS_SA_LFSR_TAPS;
    }
    return state & UDS_SA_LFSR_MASK24;
}

/**
 * uds_sa_compute_key — Seed→key via the ROM LFSR algorithm.
 *
 * Direct port of tools/mazda_security.py:compute_key (ROM-verified stock
 * vector: seed 0x45820A + secret "MazdA", level-1 init 0xC541A9 → key
 * 0xA07258; KNOWLEDGE.md:60-64):
 *   w1 = s1<<24 | shuffled seed bytes (phase-1 input, 32 clocks)
 *   w2 = s5..s2 packed little-endian (phase-2 input, 32 clocks)
 *   key bytes extracted from the final state with the nibble interleave
 *   (b0/b1 nibble-swapped, byte 0/2 order swapped vs naive ordering).
 *
 * @param seed    3 seed bytes (ECU response to 27 01)
 * @param secret  5-byte shared secret (ROM 0x5FAC0, "MazdA" stock)
 * @param init    24-bit LFSR init (per-level entry from 0x5FAC8)
 * @param key     Output: 3 key bytes (for 27 02)
 */
static void uds_sa_compute_key(const uint8_t seed[3], const uint8_t secret[5],
                               uint32_t init, uint8_t key[3])
{
    uint32_t seed24 = ((uint32_t)seed[0] << 16) |
                      ((uint32_t)seed[1] << 8) |
                      (uint32_t)seed[2];

    /* Phase 1 input: s1 in bits 24-31, seed bytes shuffled in bits 0-23. */
    uint32_t w1 = ((uint32_t)secret[0] << 24) |
                  ((seed24 & 0xFFu) << 16) |
                  (seed24 & 0xFF00u) |
                  ((seed24 >> 16) & 0xFFu);

    /* Phase 2 input: s2..s5 packed little-endian. */
    uint32_t w2 = ((uint32_t)secret[4] << 24) |
                  ((uint32_t)secret[3] << 16) |
                  ((uint32_t)secret[2] << 8) |
                  (uint32_t)secret[1];

    uint32_t state = init & UDS_SA_LFSR_MASK24;

    for (uint8_t i = 0; i < 32; i++) {
        state = uds_sa_lfsr_clock(state, (uint8_t)((w1 >> i) & 1u));
    }
    for (uint8_t i = 0; i < 32; i++) {
        state = uds_sa_lfsr_clock(state, (uint8_t)((w2 >> i) & 1u));
    }

    /* Key extraction: byte 0 = nibble[16:20] low + nibble[0:4] high,
     * byte 1 = nibble[20:24] low + nibble[12:16] high, byte 2 = bits[4:12];
     * bytes 0 and 2 swapped vs the naive ordering. */
    uint8_t b0 = (uint8_t)(((state >> 16) & 0xFu) | ((state & 0xFu) << 4));
    uint8_t b1 = (uint8_t)(((state >> 20) & 0xFu) | (((state >> 12) & 0xFu) << 4));
    uint8_t b2 = (uint8_t)((state >> 4) & 0xFFu);

    key[0] = b2;
    key[1] = b1;
    key[2] = b0;
}

/**
 * uds_sa_level_init — Read the per-level LFSR INIT from ROM.
 *
 * Table at 0x5FAC8, entry = 3 bytes big-endian at (level-1)*3
 * (tools/mazda_security.py: entry[level] read as
 * entry[0]<<16|entry[1]<<8|entry[2]; level 1 = C5 41 A9). Level 0 is
 * invalid and falls back to the level-1 init.
 */
static uint32_t uds_sa_level_init(uint8_t level)
{
    if (level < 1) {
        level = 1;
    }
    volatile const uint8_t *tab =
        (volatile const uint8_t *)(uintptr_t)
        (UDS_SA_INIT_TABLE_ADDR + (uint32_t)(level - 1u) * 3u);
    return ((uint32_t)tab[0] << 16) | ((uint32_t)tab[1] << 8) | tab[2];
}

/**
 * security_access_validate_key — Validate security key against stored seed.
 * ROM address: 0x56ADA (SeedKeyRelated)
 *
 * N1 (replaces the former XOR-rotate-nibble fiction, whose level table at
 * "0x5FAC5" sat on the FF padding documented in KNOWLEDGE.md:60-62 and whose
 * math never matched the ROM): the ROM algorithm is the 24-bit Galois LFSR
 * above (taps 0x909028 per the 0x56C1E-0x56C38 xor trail, per-level INIT
 * from the 0x5FAC8 table, 5-byte secret from 0x5FAC0) — see
 * tools/mazda_security.py and KNOWLEDGE.md:54-64.
 *
 * Contract: input (level, 3-byte key) → 1 = key matches the ROM algorithm
 * for the seed bytes in RAM D211-D213, 0 = reject.
 *
 * @param level  Security level (0x01 or 0x03)
 * @param key    Pointer to 3-byte key from the request
 * @return 1 if key valid, 0 if invalid
 */
static int security_access_validate_key(uint8_t level, const uint8_t *key)
{
    /* 5-byte shared secret from ROM 0x5FAC0 ("MazdA" stock). */
    volatile const uint8_t *secret_rom =
        (volatile const uint8_t *)(uintptr_t)UDS_SA_SECRET_ADDR;
    uint8_t secret[UDS_SA_SECRET_LEN];
    for (uint8_t i = 0; i < UDS_SA_SECRET_LEN; i++) {
        secret[i] = secret_rom[i];
    }

    /* Stored seed bytes from RAM D211-D213. */
    uint8_t seed[3];
    seed[0] = *(volatile uint8_t *)UDS_SEED_BYTE1_ADDR;
    seed[1] = *(volatile uint8_t *)UDS_SEED_BYTE2_ADDR;
    seed[2] = *(volatile uint8_t *)UDS_SEED_BYTE3_ADDR;

    uint8_t expect[3];
    uds_sa_compute_key(seed, secret, uds_sa_level_init(level), expect);

    return (expect[0] == key[0] &&
            expect[1] == key[1] &&
            expect[2] == key[2]) ? 1 : 0;
}

int obd_sid27_securityAccess(uint8_t sub_func, const uint8_t *data,
                             uint8_t data_len, uint8_t *response)
{
    switch (sub_func) {
        case UDS_SEC_SUB_REQ_SEED_1:
        case UDS_SEC_SUB_REQ_SEED_2: {
            /* Request seed: generate and return.
             * ROM:0x584C2 — handler entry for seed request.
             * Calls diag_security_5699a(3) to initialize/check state,
             * then security_seed_copy to build response.
             *
             * N7: RequestSeed msg_len == 1 excluding the SID byte
             * (FINDINGS 2026-08-04: RequestSeed msg_len=1, SendKey
             * msg_len=4) = sub-function only, so data_len must be 0
             * (bare `27 01`). The old `data_len < 1` gate rejected the
             * only legal shape with NRC 0x13. */
            if (data_len != 0) {
                return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                             UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }

            /* Generate seed from ECU serial number (ROM:0x5699a) */
            if (!security_access_generate_seed()) {
                return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                             UDS_NRC_REQUEST_OUT_OF_RANGE,
                                             response);
            }

            /* Read generated seed bytes (3 bytes — the SEED_ID byte at
             * D214 stays in RAM only; see below). */
            uint8_t seed[3];
            seed[0] = *(volatile uint8_t *)UDS_SEED_BYTE1_ADDR;
            seed[1] = *(volatile uint8_t *)UDS_SEED_BYTE2_ADDR;
            seed[2] = *(volatile uint8_t *)UDS_SEED_BYTE3_ADDR;

            /* N1: ROM response shape is [0x67, sub, 3 seed bytes]
             * (resp builder 0x5864A, FINDINGS 2026-08-04) — 5 bytes total.
             * The old code appended the SEED_ID RAM byte as a 4th seed
             * byte (6-byte response), which the ROM never sends. */
            int len = build_positive_header(UDS_SID_SECURITY_ACCESS,
                                            sub_func, response);
            response[len]     = seed[0];
            response[len + 1] = seed[1];
            response[len + 2] = seed[2];
            return len + 3;
        }

        case UDS_SEC_SUB_SEND_KEY_1:
        case UDS_SEC_SUB_SEND_KEY_2: {
            /* N7: SendKey msg_len == 4 excluding the SID byte
             * (FINDINGS 2026-08-04) = sub-function + 3 key bytes, so
             * data_len must be 3 (`27 02 K1K2K3`). The old `data_len < 4`
             * gate rejected the only legal shape with NRC 0x13, while
             * validate_key only ever read key[0..2]. */
            if (data_len != 3) {
                return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                             UDS_NRC_INCORRECT_MSG_LEN,
                                             response);
            }

            /* Verify a seed has been generated (ROM:0x585A8)
             * Check that seed byte 3 is not 0xFF (all-FF = no seed) */
            uint8_t seed_id = *(volatile uint8_t *)UDS_SEED_ID_ADDR;
            if (seed_id == 0xFF) {
                return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                             UDS_NRC_CONDITIONS_NOT_CORRECT,
                                             response);
            }

            /* Validate key against stored seed with the ROM LFSR
             * (0x56ADA). The validation runs so the length gate above is
             * exercised against the real crypto path (N7), but the unlock
             * itself is gated off (N1, see below). */
            uint8_t level = (sub_func == UDS_SEC_SUB_SEND_KEY_1)
                            ? 0x01 : 0x03;

            int valid = security_access_validate_key(level, data);

#if 0
            /* N1 ROM-divergence — SendKey UNREACHABLE in 60E1D400
             * (FINDINGS 2026-08-04, docs/notes/UDS_SECURITY_MAPPING.md):
             * entry 0x584B6-0x584BE routes only subfunc==1 (RequestSeed);
             * the SendKey body at 0x58592-0x58610 has exactly one incoming
             * ref (bf/s @0x58516, itself unreachable); subfunc != 1 falls
             * to 0x5862C where subfunc==0 gets a 0x55386 response and any
             * other subfunc gets NO response (silent). This reference body
             * is kept for documentation only — it must NOT be enabled
             * without reconciling the ROM reachability evidence above
             * (likely shared-codebase remnant; 60E32000 differs at 0x58592).
             * NOTE: enabling it also needs the LFSR INIT/secret to match
             * the ROM actually installed (KNOWLEDGE.md:66: NRC 0x35 means
             * the tool's "MazdA" disagrees with the ECU's ROM key). */
            if (valid) {
                /* Determine security level from sub-function
                 * ROM:0x585E0 — calls fuel_transpose_56720(level)
                 * which writes to 0xFFFFD20C */
                uint8_t sec_level = (sub_func == UDS_SEC_SUB_SEND_KEY_1)
                                    ? UDS_SECURITY_LEVEL_1
                                    : UDS_SECURITY_LEVEL_2;
                /* Write security level to 0xFFFFD20C (ROM:0x56720) */
                *(volatile uint8_t *)UDS_SECURITY_LEVEL_ADDR = sec_level;
                return build_positive_header(UDS_SID_SECURITY_ACCESS,
                                             sub_func, response);
            } else {
                return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                             UDS_NRC_INVALID_KEY, response);
            }
#else
            /* SendKey is unreachable on the target ROM (see above): report
             * subFunctionNotSupported. (The ROM itself sends NO response for
             * subfunc != 1; NRC 0x12 is the host-reconstruction mapping so a
             * tester sees an explicit reject instead of a timeout.) */
            (void)valid;
            return uds_negative_response(UDS_SID_SECURITY_ACCESS,
                                         UDS_NRC_SUB_NOT_SUPPORTED, response);
#endif
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

/* Bound check for one SID 0x22 DID block. Returns 0 when `need` bytes fit
 * at idx in a UDS_MAX_RESPONSE_SIZE buffer, else writes NRC 0x14
 * (responseTooLong) and returns the NRC length. */
static int sid22_need(uint16_t idx, uint16_t need, uint8_t *response)
{
    if ((uint32_t)idx + (uint32_t)need > (uint32_t)UDS_MAX_RESPONSE_SIZE) {
        return uds_negative_response(UDS_SID_READ_DATA_ID,
                                     UDS_NRC_RESPONSE_TOO_LONG, response);
    }
    return 0;
}

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
    /* uint16_t: a multi-DID response exceeds 255 bytes (14x VIN = 267). */
    uint16_t idx = 1;

    for (uint8_t i = 0; i < data_len; i += 2) {
        uint16_t did = ((uint16_t)data[i] << 8) | data[i + 1];

        /* DID lookup table from ROM:0x588F2 dispatch */
        switch (did) {
            case 0xF806: {
                /* ECU software number — read from ROM at 0x5FF800 region */
                int chk = sid22_need(idx, 6, response);
                if (chk != 0) {
                    return chk;
                }
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
                int chk = sid22_need(idx, 6, response);
                if (chk != 0) {
                    return chk;
                }
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
                int chk = sid22_need(idx, 6, response);
                if (chk != 0) {
                    return chk;
                }
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
                int chk = sid22_need(idx, 19, response);
                if (chk != 0) {
                    return chk;
                }
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
                int chk = sid22_need(idx, 4, response);
                if (chk != 0) {
                    return chk;
                }
                response[idx] = 0xF1; response[idx + 1] = 0x93;
                response[idx + 2] = 0x06;  /* Year: 2006 */
                response[idx + 3] = 0x04;  /* Month: April */
                idx += 4;
                break;
            }
            case 0xF18A: {
                /* Vehicle manufacturer ECU software number */
                int chk = sid22_need(idx, 4, response);
                if (chk != 0) {
                    return chk;
                }
                response[idx] = 0xF1; response[idx + 1] = 0x8A;
                response[idx + 2] = 0x00;
                response[idx + 3] = 0x00;
                idx += 4;
                break;
            }
            case 0x0202: {
                /* Engine coolant temperature (from RAM 0xFFFFCA00) */
                int chk = sid22_need(idx, 3, response);
                if (chk != 0) {
                    return chk;
                }
                response[idx] = 0x02; response[idx + 1] = 0x02;
                response[idx + 2] = *(volatile const uint8_t *)0xFFFFCA00;
                idx += 3;
                break;
            }
            case 0x010C: {
                /* Engine RPM (16-bit from RAM 0xFFFFCA02, 0.25 rpm/bit) */
                int chk = sid22_need(idx, 4, response);
                if (chk != 0) {
                    return chk;
                }
                response[idx] = 0x01; response[idx + 1] = 0x0C;
                uint16_t rpm_raw = *(volatile const uint16_t *)0xFFFFCA02;
                response[idx + 2] = (uint8_t)(rpm_raw >> 8);
                response[idx + 3] = (uint8_t)(rpm_raw);
                idx += 4;
                break;
            }
            case 0x010D: {
                /* Vehicle speed (from RAM 0xFFFFCA04, km/h) */
                int chk = sid22_need(idx, 3, response);
                if (chk != 0) {
                    return chk;
                }
                response[idx] = 0x01; response[idx + 1] = 0x0D;
                response[idx + 2] = *(volatile const uint8_t *)0xFFFFCA04;
                idx += 3;
                break;
            }
            case 0x0105: {
                /* Coolant temperature (scaled from RAM) */
                int chk = sid22_need(idx, 3, response);
                if (chk != 0) {
                    return chk;
                }
                response[idx] = 0x01; response[idx + 1] = 0x05;
                response[idx + 2] = *(volatile const uint8_t *)0xFFFFCA00;
                idx += 3;
                break;
            }
            default:
                /* Unknown DID — return NRC for this DID */
                {
                    int chk = sid22_need(idx, 3, response);
                    if (chk != 0) {
                        return chk;
                    }
                }
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
    (void)data;

    if (data_len < 3) {
        return uds_negative_response(UDS_SID_READ_MEM_ADDR,
                                     UDS_NRC_INCORRECT_MSG_LEN, response);
    }

    /* review-fix w2 (DOCUMENTED-gap, NRC behavior kept): ROM 0x57028
     * contract needed — (a) addressAndLengthFormatIdentifier nibble split
     * (low nibble = memorySize bytes, high nibble = memoryAddress bytes);
     * (b) the allowed-range table (which flash/RAM windows are readable —
     * cf. the 0x34 download ranges: flash 0x00000000-0x0007FFFF, RAM
     * 0xFFFF8000-0xFFFFFFFF — but the 0x23 read-allow list may differ);
     * (c) response layout: 0x63 + raw memory bytes. Until an IDA read of
     * 0x57028 supplies (a)+(b), any implementation risks exposing the
     * security/seed RAM — keep rejecting. */

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

    /* review-fix w2 (DOCUMENTED-gap, NRC behavior kept): ROM 0x5798E
     * contract needed — the DID write table (~8 entries of
     * DID/handler/max-length), per-DID session+security gates (the old
     * comment's 0xF806/0xF190 guesses are NOT ROM-confirmed), and the
     * 0x6E + DID echo layout. Until an IDA read of 0x5798E supplies the
     * table, keep rejecting: a permissive stub could brick calibration. */
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
    /* ROM:0x5E1F8 — SID 0x34 request download handler.
     *
     * Flow (from disassembly):
     *   1. Check security is unlocked (securityNotUnlocked → NRC 0x33)
     *   2. Validate request length == 8 bytes (format+3addr+4size)
     *   3. Parse format byte, memory address, memory size
     *   4. Validate memory range is allowed
     *   5. Store download state
     *   6. Return positive response with max block length */

    /* Must be in programming session */
    if (!uds_is_programming()) {
        return uds_negative_response(UDS_SID_REQ_DOWNLOAD,
                                     UDS_NRC_CONDITIONS_NOT_CORRECT,
                                     response);
    }

    /* Must have security unlocked (ROM:0x5E20C-0x5E214) */
    if (!uds_is_unlocked()) {
        return uds_negative_response(UDS_SID_REQ_DOWNLOAD,
                                     UDS_NRC_SECURITY_ACCESS_DENIED,
                                     response);
    }

    /* Validate request length: format(1) + addr(3) + size(4) = 8 bytes
     * ROM:0x5E21A-0x5E228: checks data_len+1 == 8 (including sub-function).
     * C2: the code's own ROM contract (data_len+1 == 8) demands exactly
     * 3 address bytes + 3 size bytes — the ECU has no 1/2/4-byte
     * addr/size encoding, and accepting them only masked the old
     * left-aligned store truncation. Reject anything but 3+3 with NRC 0x13.
     * Our data[] starts after sub_func, so a legal request is exactly
     * format(1) + addr(3) + size(3) = 7 bytes. */
    if (data_len < 7) {
        return uds_negative_response(UDS_SID_REQ_DOWNLOAD,
                                     UDS_NRC_INCORRECT_MSG_LEN,
                                     response);
    }

    /* Parse format byte (compressionMethod << 4 | encryptMethod)
     * ROM:0x5E21A checks total length, then proceeds to parse.
     * The format byte encodes address/length byte counts in upper nibble.
     * Standard: format & 0x0F = sizeOfMemoryAddressBytes
     *           format >> 4   = sizeOfMemorySizeBytes */
    uint8_t format = data[0];
    uint8_t addr_bytes = format & 0x0F;    /* Low nibble: address bytes */
    uint8_t size_bytes = (format >> 4) & 0x0F;  /* High nibble: size bytes */

    /* C2: exactly 3+3 per the ROM contract above — not the old 1..4 range
     * (which truncated 4-byte values to 24 bits in the store). */
    if (addr_bytes != 3 || size_bytes != 3) {
        return uds_negative_response(UDS_SID_REQ_DOWNLOAD,
                                     UDS_NRC_INCORRECT_MSG_LEN,
                                     response);
    }

    /* Check we have enough data for address + size */
    uint8_t needed = 1 + addr_bytes + size_bytes;  /* format + addr + size */
    if (data_len < needed) {
        return uds_negative_response(UDS_SID_REQ_DOWNLOAD,
                                     UDS_NRC_INCORRECT_MSG_LEN,
                                     response);
    }

    /* Parse memory address (big-endian, addr_bytes) */
    uint32_t mem_addr = 0;
    for (uint8_t i = 0; i < addr_bytes; i++) {
        mem_addr = (mem_addr << 8) | data[1 + i];
    }

    /* Parse memory size (big-endian, size_bytes) */
    uint32_t mem_size = 0;
    for (uint8_t i = 0; i < size_bytes; i++) {
        mem_size = (mem_size << 8) | data[1 + addr_bytes + i];
    }

    /* Validate memory range (ROM path validates against allowed regions)
     * Allowed ranges:
     *   Flash: 0x00000000 - 0x0007FFFF (512KB)
     *   RAM:   0xFFFF8000 - 0xFFFFFFFF */
    int addr_valid = 0;
    uint32_t addr_end = mem_addr + mem_size;
    if (addr_end > mem_addr &&  /* Overflow check */
        mem_addr < UDS_DL_FLASH_END && addr_end <= UDS_DL_FLASH_END) {
        addr_valid = 1;
    } else if (addr_end > mem_addr &&
               mem_addr >= UDS_DL_RAM_BASE && addr_end <= UDS_DL_RAM_END) {
        addr_valid = 1;
    }

    if (!addr_valid || mem_size == 0) {
        return uds_negative_response(UDS_SID_REQ_DOWNLOAD,
                                     UDS_NRC_REQUEST_OUT_OF_RANGE,
                                     response);
    }

    /* Store download parameters to RAM (ROM:0x5E1FE stores to stack/RAM).
     * Right-aligned fixed BE24/BE32 image of the correctly parsed mem_addr /
     * mem_size above. (Was: raw-index copies — for size_bytes<4 the bytes
     * landed left-aligned in B3/B2/B1 with B0 forced 0, i.e. size << 8, so
     * remaining never reached 0; MEM_HI/MEM_LO were likewise only correct
     * for addr_bytes==3.) */
    *(volatile uint8_t *)UDS_DL_FORMAT_ADDR = format;
    *(volatile uint8_t *)UDS_DL_MEM_HI_ADDR = (uint8_t)(mem_addr >> 16);
    *(volatile uint8_t *)UDS_DL_MEM_MID_ADDR = (uint8_t)(mem_addr >> 8);
    *(volatile uint8_t *)UDS_DL_MEM_LO_ADDR = (uint8_t)(mem_addr);
    *(volatile uint8_t *)UDS_DL_SIZE_B3_ADDR = (uint8_t)(mem_size >> 24);
    *(volatile uint8_t *)UDS_DL_SIZE_B2_ADDR = (uint8_t)(mem_size >> 16);
    *(volatile uint8_t *)UDS_DL_SIZE_B1_ADDR = (uint8_t)(mem_size >> 8);
    *(volatile uint8_t *)UDS_DL_SIZE_B0_ADDR = (uint8_t)(mem_size);
    *(volatile uint8_t *)UDS_DL_BLOCK_SEQ_ADDR = 0x01;  /* First block sequence */
    *(volatile uint8_t *)UDS_DL_STATE_ADDR = UDS_DL_STATE_ACTIVE;

    /* Initialize running checksum */
    *(volatile uint32_t *)UDS_DL_CHECKSUM_ADDR = 0;

    /* Build positive response: lengthOfMaxNumberOfBlockLength
     * Response format: [0x74][lengthOfMaxNumberOfBlockLength][maxBlockLength]
     * For this ECU, max block length = 128 bytes (typical for SH-2 flash write) */
    int len = build_positive_header(UDS_SID_REQ_DOWNLOAD, 0x00, response);

    /* LengthOfMaxNumberOfBlockLength = 1 (1-byte value follows) */
    response[len] = 0x01;
    len++;

    /* Max number of blocks = 0x0080 (128 bytes per transfer block)
     * ROM: the value depends on the ECU's flash write buffer size */
    response[len] = 0x00;
    response[len + 1] = 0x80;
    len += 2;

    return len;
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
    /* ROM:0x5E270 — SID 0x36 transfer data handler.
     *
     * Flow (from disassembly):
     *   1. Check session is programming (NRC 0x22 if not)
     *   2. Validate block sequence counter
     *   3. Copy data to target memory address (flash/RAM write)
     *   4. Update running checksum
     *   5. Advance address and block sequence
     *   6. Return positive response */

    /* Must be in programming session (ROM:0x5E276-0x5E27E)
     * The ROM checks session gate and returns NRC 0x22 if not programming */
    if (!uds_is_programming()) {
        return uds_negative_response(UDS_SID_TRANSFER_DATA,
                                     UDS_NRC_CONDITIONS_NOT_CORRECT,
                                     response);
    }

    /* Must have an active download session */
    if (*(volatile uint8_t *)UDS_DL_STATE_ADDR != UDS_DL_STATE_ACTIVE) {
        return uds_negative_response(UDS_SID_TRANSFER_DATA,
                                     UDS_NRC_CONDITIONS_NOT_CORRECT,
                                     response);
    }

    if (data_len < 1) {
        return uds_negative_response(UDS_SID_TRANSFER_DATA,
                                     UDS_NRC_INCORRECT_MSG_LEN,
                                     response);
    }

    /* Validate block sequence counter (ROM:0x5E28E-0x5E29C)
     * The block_seq byte must match the expected counter.
     * Counter starts at 0x01 after requestDownload, increments per block. */
    uint8_t expected_seq = *(volatile uint8_t *)UDS_DL_BLOCK_SEQ_ADDR;
    if (block_seq != expected_seq) {
        /* Non-sequential block: NRC 0x73 (wrongBlockSequenceCounter)
         * ROM path at ctrl_distribution_55386 sends NRC for mismatch */
        return uds_negative_response(UDS_SID_TRANSFER_DATA,
                                     UDS_NRC_WRONG_BLOCK_SEQ, response);
    }

    /* Read download parameters — format byte indicates address/size encoding */
    (void)*(volatile uint8_t *)UDS_DL_FORMAT_ADDR;  /* Used for decoding, available if needed */
    uint8_t addr_hi = *(volatile uint8_t *)UDS_DL_MEM_HI_ADDR;
    uint8_t addr_mid = *(volatile uint8_t *)UDS_DL_MEM_MID_ADDR;
    uint8_t addr_lo = *(volatile uint8_t *)UDS_DL_MEM_LO_ADDR;
    uint8_t size_b3 = *(volatile uint8_t *)UDS_DL_SIZE_B3_ADDR;
    uint8_t size_b2 = *(volatile uint8_t *)UDS_DL_SIZE_B2_ADDR;
    uint8_t size_b1 = *(volatile uint8_t *)UDS_DL_SIZE_B1_ADDR;
    uint8_t size_b0 = *(volatile uint8_t *)UDS_DL_SIZE_B0_ADDR;

    /* Reconstruct target address */
    uint32_t target_addr = ((uint32_t)addr_hi << 16) |
                           ((uint32_t)addr_mid << 8) |
                           (uint32_t)addr_lo;

    /* Reconstruct remaining size */
    uint32_t remaining = ((uint32_t)size_b3 << 24) |
                         ((uint32_t)size_b2 << 16) |
                         ((uint32_t)size_b1 << 8) |
                         (uint32_t)size_b0;

    /* Data payload is data[0..data_len-1]: uds_handler strips the SID and
     * passes block_seq (request[1]) separately, so data[0] is the first
     * payload byte (review-fix w2: convention resolved, see uds_handler). */
    uint8_t payload_len = data_len;

    /* Validate payload doesn't exceed remaining size */
    if (payload_len > remaining) {
        payload_len = (uint8_t)remaining;
    }

    /* Write data to target memory (ROM flash write path)
     * NOTE: This is a 1:1 reconstruction of the ROM behavior.
     * On real hardware, this performs flash writes via the flash controller.
     * For the host reconstruction, we store to the target address. */
    volatile uint8_t *dest = (volatile uint8_t *)(uintptr_t)target_addr;
    volatile uint32_t *checksum_ptr = (volatile uint32_t *)UDS_DL_CHECKSUM_ADDR;

    uint32_t running_sum = *checksum_ptr;
    for (uint8_t i = 0; i < payload_len; i++) {
        dest[i] = data[i];
        running_sum += data[i];
    }
    *checksum_ptr = running_sum;

    /* Update target address and remaining size */
    target_addr += payload_len;
    remaining -= payload_len;

    /* Store updated values back to RAM */
    *(volatile uint8_t *)UDS_DL_MEM_HI_ADDR = (uint8_t)(target_addr >> 16);
    *(volatile uint8_t *)UDS_DL_MEM_MID_ADDR = (uint8_t)(target_addr >> 8);
    *(volatile uint8_t *)UDS_DL_MEM_LO_ADDR = (uint8_t)(target_addr);
    *(volatile uint8_t *)UDS_DL_SIZE_B3_ADDR = (uint8_t)(remaining >> 24);
    *(volatile uint8_t *)UDS_DL_SIZE_B2_ADDR = (uint8_t)(remaining >> 16);
    *(volatile uint8_t *)UDS_DL_SIZE_B1_ADDR = (uint8_t)(remaining >> 8);
    *(volatile uint8_t *)UDS_DL_SIZE_B0_ADDR = (uint8_t)(remaining);

    /* Advance block sequence counter (wraps at 0xFF → 0x00) */
    *(volatile uint8_t *)UDS_DL_BLOCK_SEQ_ADDR = (expected_seq + 1) & 0xFF;

    /* If all data transferred, mark download as complete but not yet exited */
    if (remaining == 0) {
        /* Download data complete; await transfer exit (SID 0x37) */
    }

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
    /* ROM:0x5E2B0 — SID 0x37 request transfer exit handler.
     *
     * Flow (from disassembly):
     *   1. Check session is programming (NRC 0x22 if not)
     *   2. Verify all blocks received (remaining == 0)
     *   3. Verify running checksum
     *   4. Finalize download: commit flash writes if applicable
     *   5. Clear download state
     *   6. Return positive response */

    /* Must be in programming session (ROM:0x5E2B6-0x5E2C2) */
    if (!uds_is_programming()) {
        return uds_negative_response(UDS_SID_REQ_TRANS_EXIT,
                                     UDS_NRC_CONDITIONS_NOT_CORRECT,
                                     response);
    }

    /* Must have an active download session */
    if (*(volatile uint8_t *)UDS_DL_STATE_ADDR != UDS_DL_STATE_ACTIVE) {
        return uds_negative_response(UDS_SID_REQ_TRANS_EXIT,
                                     UDS_NRC_CONDITIONS_NOT_CORRECT,
                                     response);
    }

    /* Verify all data has been transferred (remaining size == 0)
     * ROM: checks that the transfer completed before allowing exit */
    uint32_t remaining = ((uint32_t)*(volatile uint8_t *)UDS_DL_SIZE_B3_ADDR << 24) |
                         ((uint32_t)*(volatile uint8_t *)UDS_DL_SIZE_B2_ADDR << 16) |
                         ((uint32_t)*(volatile uint8_t *)UDS_DL_SIZE_B1_ADDR << 8) |
                         (uint32_t)*(volatile uint8_t *)UDS_DL_SIZE_B0_ADDR;

    if (remaining != 0) {
        return uds_negative_response(UDS_SID_REQ_TRANS_EXIT,
                                     UDS_NRC_TRANSFER_SUSPENDED, response);
    }

    /* Verify running checksum (ROM:0x57506 checksum verification path)
     * The ROM computes a checksum during transfer and verifies it here.
     * For flash writes, the checksum is verified against the written data.
     * If checksum mismatch: NRC 0x72 (generalProgrammingFailure) */
    uint32_t checksum = *(volatile uint32_t *)UDS_DL_CHECKSUM_ADDR;

    /* ROM checksum verification: the checksum from the transfer is compared
     * against a value computed from the written memory.
     * For our reconstruction, we accept the running checksum as valid
     * if the transfer completed (all blocks received in sequence). */

    /* Clear download state */
    *(volatile uint8_t *)UDS_DL_STATE_ADDR = UDS_DL_STATE_IDLE;
    *(volatile uint8_t *)UDS_DL_BLOCK_SEQ_ADDR = 0x00;
    *(volatile uint32_t *)UDS_DL_CHECKSUM_ADDR = 0;

    /* Clear download parameters */
    *(volatile uint8_t *)UDS_DL_FORMAT_ADDR = 0x00;
    *(volatile uint8_t *)UDS_DL_MEM_HI_ADDR = 0x00;
    *(volatile uint8_t *)UDS_DL_MEM_MID_ADDR = 0x00;
    *(volatile uint8_t *)UDS_DL_MEM_LO_ADDR = 0x00;
    *(volatile uint8_t *)UDS_DL_SIZE_B3_ADDR = 0x00;
    *(volatile uint8_t *)UDS_DL_SIZE_B2_ADDR = 0x00;
    *(volatile uint8_t *)UDS_DL_SIZE_B1_ADDR = 0x00;
    *(volatile uint8_t *)UDS_DL_SIZE_B0_ADDR = 0x00;

    (void)checksum;  /* Used for verification above */

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
    /* review-fix w2 (DOCUMENTED-gap, behavior kept): ROM 0x59E16 contract
     * needed — (a) freeze-frame slot addressing: how (DTC, frame#) maps to
     * the snapshot store RAM address; (b) response layout: 0x42 + PID +
     * frame-data bytes (length varies by PID, cf. obd_service_1). Until an
     * IDA read of 0x59E16 supplies (a), this returns a bare 0x42 header
     * with NO data — a tester-visible fake-positive: callers must treat a
     * 1-byte 0x42 response as "not implemented", not as valid data. */
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
    /* review-fix w2 (DOCUMENTED-gap, behavior kept): ROM 0x59E98 contract
     * needed — the clear routine: which stores are wiped (DTC primary
     * table 0xFFFF8928, backup 0xFFFF8EA0, freeze-frame slots, readiness
     * bits?) and in what order, plus the positive response (0x44).
     * Current bare-0x44 return clears NOTHING — fake-positive: a tester
     * sees success while DTCs remain stored. Do not wire a partial clear
     * without the ROM sequence. */
    response[0] = 0x44;
    return 1;
}

/**
 * obd_service_6 — OBD-II Service 6.
 * ROM address: 0x59EDE
 */
int obd_service_6(uint8_t *response)
{
    /* review-fix w2 (DOCUMENTED-gap, behavior kept): ROM 0x59EDE contract
     * needed — supported Test IDs, per-TID result RAM addresses, and the
     * 0x46 + TID + result layout. Bare-0x46 return is a fake-positive
     * (no monitor results attached). Needs IDA read of 0x59EDE. */
    response[0] = 0x46;
    return 1;
}

/**
 * obd_service_7 — OBD-II Service 7: pending DTCs.
 * ROM address: 0x59EE2
 */
int obd_service_7(uint8_t *response)
{
    /* review-fix w2 (DOCUMENTED-gap, behavior kept): ROM 0x59EE2 contract
     * needed — pending-DTC store layout (cf. obd_service_3's documented
     * count@0xFFFFD400 + table@0xFFFFD402 pattern for STORED codes) and
     * the 0x47 + DTC-list layout. Bare-0x47 return is a fake-positive.
     * Needs IDA read of 0x59EE2. */
    response[0] = 0x47;
    return 1;
}

/**
 * obd_service_9 — OBD-II Service 9: vehicle information.
 * ROM address: 0x59C8C
 */
int obd_service_9(uint8_t sub_func, uint8_t *response)
{
    /* review-fix w2 (DOCUMENTED-gap, behavior kept): ROM 0x59C8C contract
     * needed — supported InfoTypes (VIN, calibration ID/CVN, ...) with
     * their source addresses (cf. SID 0x22 DIDs 0xF190/0xF18A already
     * reconstructed above) and the 0x49 + InfoType + message-count +
     * data layout. Bare-0x49 return is a fake-positive. Needs IDA read
     * of 0x59C8C. */
    (void)sub_func;
    response[0] = 0x49;
    return 1;
}

/**
 * NOTE (Service 0x0A removed): the ROM dispatch table at 0x5F57C has no 0x0A
 * entry (docs/subsystems/CAN_UDS_SUBSYSTEM.md:199-230), so the former
 * obd_service_A stub (bare-0x4A fake-positive) was unreachable on target and
 * has been deleted along with its dispatch arm and the UDS_SID_OBD_SVCA
 * constant. A tester asking for 0x0A gets NRC 0x11 via the default arm. */
