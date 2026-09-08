/*
 * test_small_fixes.c — SMALL-batch regression:
 *   (a) obd_sid12 accepts only sub-functions 2/4 (ROM subs per
 *       IDA_ANALYSIS.md:751), else NRC 0x12 — the old `sub_func < 2` gate
 *       admitted 3, 5..255;
 *   (b) SID 0x34 validator demands exactly addr_bytes==3 && size_bytes==3
 *       (the code's own ROM contract, uds.c data_len+1==8), else NRC 0x13 —
 *       the old 1..4 range truncated 4-byte values to 24 bits;
 *   (c) no 0x0A dispatch arm: the ROM dispatch table at 0x5F57C (28 entries,
 *       CAN_UDS_SUBSYSTEM.md:199-230) has no 0x0A entry, so 0x0A requests
 *       fall through to NRC 0x11 (the old case arm + UDS_SID_OBD_SVCA
 *       constant + obd_service_A stub are removed).
 *
 * Firmware sites: firmware/c/dtc.c obd_sid12_readDTCByStatus,
 *   firmware/c/uds.c obd_sid34_requestDownload + uds_handler dispatch,
 *   firmware/include/uds.h (constant/prototype removal).
 *
 * Host-self-contained: gate/dispatch models mirroring the firmware.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_small_fixes.c -o /tmp/fwtest/test_small_fixes
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

#define NRC_11 0x11
#define NRC_12 0x12
#define NRC_13 0x13

/* (a) SID 0x12 sub-function gate model. */
static int model_sid12_gate(uint8_t sub)
{
#ifdef TEST_BUGGY
    return (sub < 2) ? -NRC_12 : 0;
#else
    return (sub != 2 && sub != 4) ? -NRC_12 : 0;
#endif
}

/* (b) SID 0x34 addr/size-width validator model. */
static int model_c2_validate(uint8_t addr_bytes, uint8_t size_bytes)
{
#ifdef TEST_BUGGY
    return (addr_bytes >= 1 && addr_bytes <= 4 &&
            size_bytes >= 1 && size_bytes <= 4) ? 0 : -NRC_13;
#else
    return (addr_bytes == 3 && size_bytes == 3) ? 0 : -NRC_13;
#endif
}

/* (c) Dispatch model for 0x0A. Fixed: no arm → NRC 0x11. Buggy: arm → ok. */
static int model_dispatch_0a(void)
{
#ifdef TEST_BUGGY
    return 120; /* old obd_service_A stub return */
#else
    return -NRC_11;
#endif
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    /* (a) Only subs 2 and 4 pass. */
    CHECK(model_sid12_gate(2) == 0, "sid12 sub 2 must pass");
    CHECK(model_sid12_gate(4) == 0, "sid12 sub 4 must pass");
    CHECK(model_sid12_gate(0) == -NRC_12, "sid12 sub 0 must be 0x12");
    CHECK(model_sid12_gate(1) == -NRC_12, "sid12 sub 1 must be 0x12");
    CHECK(model_sid12_gate(3) == -NRC_12, "sid12 sub 3 must be 0x12");
    CHECK(model_sid12_gate(5) == -NRC_12, "sid12 sub 5 must be 0x12");
    CHECK(model_sid12_gate(255) == -NRC_12, "sid12 sub 255 must be 0x12");

    /* (b) Only 3+3 passes; 1/2/4-byte widths are cleanly rejected. */
    CHECK(model_c2_validate(3, 3) == 0, "c2 3+3 must pass");
    CHECK(model_c2_validate(1, 3) == -NRC_13, "c2 addr 1 must be 0x13");
    CHECK(model_c2_validate(2, 2) == -NRC_13, "c2 2+2 must be 0x13");
    CHECK(model_c2_validate(4, 4) == -NRC_13, "c2 4+4 must be 0x13");
    CHECK(model_c2_validate(3, 4) == -NRC_13, "c2 size 4 must be 0x13");
    CHECK(model_c2_validate(4, 3) == -NRC_13, "c2 addr 4 must be 0x13");
    CHECK(model_c2_validate(0, 3) == -NRC_13, "c2 addr 0 must be 0x13");

    /* (c) 0x0A unreachable → NRC 0x11. */
    CHECK(model_dispatch_0a() == -NRC_11, "0x0A must be NRC 0x11");

    if (failures == 0) {
        printf("PASS small_fixes\n");
    } else {
        printf("%d FAILURES small_fixes\n", failures);
    }
    return failures != 0;
}
