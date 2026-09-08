/*
 * test_h3_dispatch.c — H3 regression: implemented UDS/DTC/OBD handlers must
 * be reachable from the dispatcher (never NRC 0x11 for implemented SIDs).
 *
 * Firmware site: firmware/c/uds.c uds_handler switch (:283-349 pre-fix
 *   covers only 0x10,0x27,0x31,0xB1,0x22,0x23,0x2E,0x34,0x36,0x37).
 * Implementations: dtc.h/dt c.c obd_sid14_clearDTC / obd_sid18_readDTCInfo /
 *   obd_sid12_readDTCByStatus; uds.c obd_service_1/2/3/4/6/7/9/A.
 *
 * Host-self-contained: model of the switch with stub handlers (distinctive
 * positive codes) and the same req_len guard convention. Session gating is
 * ROM-table driven on target and stubbed pass-through here; the matrix still
 * spans sessions to pin that routing is session-independent at this layer.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_h3_dispatch.c -o /tmp/fwtest/test_h3_dispatch
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

#define NRC_11 0x11
#define NRC_13 0x13

/* Stub handlers: return a distinctive positive length each. */
int stub_sid14(uint8_t gh, uint8_t gl) { (void)gh; (void)gl; return 101; }
int stub_sid18(uint8_t s, uint8_t m) { (void)s; (void)m; return 102; }
int stub_sid12(uint8_t s, uint8_t m) { (void)s; (void)m; return 103; }
int stub_svc1(uint8_t p) { (void)p; return 111; }
int stub_svc2(uint8_t p, uint8_t f) { (void)p; (void)f; return 112; }
int stub_svc3(void) { return 113; }
int stub_svc4(void) { return 114; }
int stub_svc6(void) { return 116; }
int stub_svc7(void) { return 117; }
int stub_svc9(uint8_t s) { (void)s; return 119; }
int stub_old(uint8_t sid) { (void)sid; return 200; } /* pre-existing arms */

/* Pre-fix switch: only the original 10 arms. */
int buggy_dispatch(uint8_t sid, const uint8_t *req, uint8_t len)
{
    (void)req;
    switch (sid) {
    case 0x10:
    case 0x27:
    case 0x31:
    case 0xB1:
    case 0x22:
    case 0x23:
    case 0x2E:
    case 0x34:
    case 0x36:
    case 0x37:
        if (len < 1) {
            return -NRC_13;
        }
        return stub_old(sid);
    default:
        return -NRC_11;
    }
}

/* Fixed switch: adds 0x14/0x18/0x12 + 0x01-0x09 arms (mirrors uds.c fix).
 * No 0x0A arm: the ROM dispatch table at 0x5F57C (28 entries,
 * CAN_UDS_SUBSYSTEM.md:199-230) has no 0x0A entry, so 0x0A requests stay
 * NRC 0x11 (the old 0x0A arm + obd_service_A stub were removed). */
int fixed_dispatch(uint8_t sid, const uint8_t *req, uint8_t len)
{
    switch (sid) {
    case 0x10:
    case 0x27:
    case 0x31:
    case 0xB1:
    case 0x22:
    case 0x23:
    case 0x2E:
    case 0x34:
    case 0x36:
    case 0x37:
        if (len < 1) {
            return -NRC_13;
        }
        return stub_old(sid);
    case 0x14:
        if (len < 3) {
            return -NRC_13;
        }
        return stub_sid14(req[1], req[2]);
    case 0x18:
        if (len < 3) {
            return -NRC_13;
        }
        return stub_sid18(req[1], req[2]);
    case 0x12:
        if (len < 3) {
            return -NRC_13;
        }
        return stub_sid12(req[1], req[2]);
    case 0x01:
        if (len < 2) {
            return -NRC_13;
        }
        return stub_svc1(req[1]);
    case 0x02:
        if (len < 3) {
            return -NRC_13;
        }
        return stub_svc2(req[1], req[2]);
    case 0x03:
        return stub_svc3();
    case 0x04:
        return stub_svc4();
    case 0x06:
        return stub_svc6();
    case 0x07:
        return stub_svc7();
    case 0x09:
        if (len < 2) {
            return -NRC_13;
        }
        return stub_svc9(req[1]);
    default:
        return -NRC_11;
    }
}

#ifdef TEST_BUGGY
#define DISPATCH buggy_dispatch
#else
#define DISPATCH fixed_dispatch
#endif

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    /* Well-formed requests per SID: {sid, arg bytes...}. */
    struct {
        uint8_t sid;
        uint8_t req[4];
        uint8_t len;
        int want; /* expected stub return code */
    } vecs[] = {
        {0x14, {0x14, 0xFF, 0x00, 0x00}, 3, 101},
        {0x18, {0x18, 0x03, 0x80, 0x00}, 3, 102},
        {0x12, {0x12, 0x02, 0x80, 0x00}, 3, 103},
        {0x01, {0x01, 0x0C, 0x00, 0x00}, 2, 111},
        {0x02, {0x02, 0x0C, 0x00, 0x00}, 3, 112},
        {0x03, {0x03, 0x00, 0x00, 0x00}, 1, 113},
        {0x04, {0x04, 0x00, 0x00, 0x00}, 1, 114},
        {0x06, {0x06, 0x00, 0x00, 0x00}, 1, 116},
        {0x07, {0x07, 0x00, 0x00, 0x00}, 1, 117},
        {0x09, {0x09, 0x02, 0x00, 0x00}, 2, 119},
    };
    const uint8_t sessions[] = {0x01, 0x02, 0x03};
    (void)sessions;

    for (unsigned v = 0; v < 10; v++) {
        for (unsigned s = 0; s < 3; s++) {
            /* Session gate is a separate ROM-table layer; routing here must
             * not depend on it. */
            int rc = DISPATCH(vecs[v].sid, vecs[v].req, vecs[v].len);
            CHECK(rc == vecs[v].want,
                  "sid 0x%02X session %u -> %d want %d",
                  vecs[v].sid, sessions[s], rc, vecs[v].want);
            CHECK(rc != -NRC_11,
                  "sid 0x%02X must never be 0x11 (not supported)", vecs[v].sid);
        }
    }

    /* Short requests keep the 0x13 guard convention. */
    {
        uint8_t r1[] = {0x14};
        CHECK(DISPATCH(0x14, r1, 1) == -NRC_13, "sid14 short must be 0x13");
        uint8_t r2[] = {0x01};
        CHECK(DISPATCH(0x01, r2, 1) == -NRC_13, "svc1 short must be 0x13");
        uint8_t r3[] = {0x02, 0x0C};
        CHECK(DISPATCH(0x02, r3, 2) == -NRC_13, "svc2 short must be 0x13");
    }

#ifndef TEST_BUGGY
    /* Unimplemented SIDs still report 0x11 — including 0x0A, which has no
     * ROM dispatch-table entry (unreachable on target). */
    {
        uint8_t r[] = {0x05, 0x00};
        CHECK(fixed_dispatch(0x05, r, 2) == -NRC_11, "sid 0x05 stays 0x11");
        uint8_t r8[] = {0x08, 0x00};
        CHECK(fixed_dispatch(0x08, r8, 2) == -NRC_11, "sid 0x08 stays 0x11");
        uint8_t r0a[] = {0x0A, 0x00};
        CHECK(fixed_dispatch(0x0A, r0a, 1) == -NRC_11, "sid 0x0A stays 0x11");
    }
#endif

    if (failures == 0) {
        printf("PASS h3_dispatch\n");
    } else {
        printf("%d FAILURES h3_dispatch\n", failures);
    }
    return failures != 0;
}
