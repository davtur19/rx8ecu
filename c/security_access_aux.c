/**
 * security_access_aux.c — UDS Service 0x27 (SecurityAccess) — aux-bank entry dispatch
 *
 * ═══════════════════════════════════════════════════════════════════
 *  STATUS: DRAFT / UNVERIFIED (entry dispatch structure CONFIRMED
 *  [AUX-EVIDENCE], runtime values [AUX-TBD]).
 *  Address: per-bank (primary bank modelled: 60E0E500 @ 0x56E4C)
 *  2026-08-04: entry-dispatch comparison across the 9 stock images
 *  (docs/notes/AUX_HANDLERS_COMPARISON.md) — the SecurityAccess handler
 *  body is BYTE-IDENTICAL in all images; only code/data relocation and
 *  two data-table variants differ.  This file models the shared aux
 *  flow with the 60E0E500 layout as the primary bank and documents the
 *  per-bank deltas (VA tables, RAM addresses) in comments.
 *
 *  IMPORTANT — READ FIRST:
 *   * SID is 0x27 in EVERY aux image (and the baseline): the earlier
 *     "aux uses 0x3E" claim is REFUTED.  0x3E is the separate
 *     TesterPresent service (baseline handler @0x56F44) present in the
 *     dispatch table of every image.
 *   * Entry dispatch admits ONLY subfunc==1 into the RequestSeed flow;
 *     subfunc!=1 goes to the else path (subfunc==0 -> response helper,
 *     subfunc!=0 -> SILENT no-response).  The SendKey body (subfunc
 *     0x04) is DEAD CODE in all 9 public stock images (only incoming
 *     branch = never-taken abs-trick bf/s) — see
 *     docs/notes/SENDKEY_RECONCILIATION.md verdict (b).
 *   * This file is a source artifact; it is NOT wired into any harness
 *     (c/security_access.c is not compiled by make c-test either — the
 *     Python suites reference it as documentation).  Do not use it to
 *     answer real security-access requests until validated end-to-end.
 *   * The seed<->key TRANSFORM core (seed_key_related) and the secret
 *     "MazdA"/LFSR-init tables are identical in every image (data
 *     verified); only the RAM/table addresses relocate per bank.
 * ═══════════════════════════════════════════════════════════════════
 *
 * Structural C reconstruction of the SH-2 handler entry dispatch
 * (primary bank 60E0E500.bin, entry 0x56E4C; baseline 60E1D400 entry
 * 0x584A0 — same instructions at the same relative offsets).
 *
 * Reference:
 *   - docs/notes/AUX_HANDLERS_COMPARISON.md (this task's evidence)
 *   - docs/notes/REQUEST_SEED_EVIDENCE.md (baseline row-by-row evidence)
 *   - docs/notes/SENDKEY_RECONCILIATION.md (SendKey dead-code verdict)
 *   - c/security_access.c (baseline reconstruction, same style)
 */

#include <stdint.h>

/* ===================================================================
 *  Per-bank relocation table (handler literal pools, REQUEST/AUX evidence)
 *  [AUX-EVIDENCE] — subroutine VAs per image (primary bank 60E0E500 in
 *  the #defines below):
 *
 *  role             60E0E500  60E0E700  60E0FB00/FC00  60E15120  60E1B900  60E1C500  60E1D400  60E32000
 *  uds_read_payload 0x67560   0x677B8   0x66A74        0x68184   0x66D0C   0x67830   0x68BC0   0x6E4B8
 *  state_check1     0x55212   0x5546A   0x54146        0x55E2A   0x543DE   0x554D6   0x56866   0x5B50E
 *  state_check2     0x55292   0x554EA   0x541C6        0x55EAA   0x5445E   0x55556   0x568E6   0x5B58E
 *  uds_error_resp   0x53D56   0x53FAE   0x52A5A        0x5496E   0x52CF2   0x5401A   0x553AA   0x59E22
 *  seed_gen         0x55346   0x5559E   0x5427A        0x55F5E   0x54512   0x5560A   0x5699A   0x5B642
 *  position_check   0x5523E   0x55496   0x54172        0x55E56   0x5440A   0x55502   0x56892   0x5B53A
 *  key_validate     0x552D4   0x5552C   0x54208        0x55EEC   0x544A0   0x55598   0x56928   0x5B5D0
 *  data_copy        0x5546C   0x556C4   0x543A0        0x56084   0x54638   0x55730   0x56AC0   0x5B768
 *  level_slot_res   0x55336   0x5558E   0x5426A        0x55F4E   0x54502   0x555FA   0x5698A   0x5B632
 *  seed_key_rel     0x55486   0x556DE   0x543BA        0x5609E   0x54652   0x5574A   0x56ADA   0x5B782
 *  unlock           0x550CC   0x55324   0x54000        0x55CE4   0x54298   0x55390   0x56720   0x5B3C8
 *  uds_fw_notify    0x53D0E   0x53F66   0x52A12        0x54926   0x52CAA   0x53FD2   0x55362   0x59DDA
 *  uds_resp_sub0    0x53D32   0x53F8A   0x52A36        0x5494A   0x52CCE   0x53FF6   0x55386   0x59DFE
 *  uds_send         0x67500   0x67758   0x66A14        0x68124   0x66CAC   0x677D0   0x68B60   0x6E458
 *
 *  RAM/data per bank (state bytes, seed RAM, tables, mask ptr):
 *  bank            state1       state2       seed base   level      pos table   key table   mask ptr
 *  60E0E500        0xFFFFD147   0xFFFFD148   0xFFFFD14D  0xFFFFD150 0x5E430     0x5E442     0xFFFFD32C
 *  60E0E700        0xFFFFD153   0xFFFFD154   0xFFFFD159  0xFFFFD15C 0x5E688     0x5E69A     0xFFFFD338
 *  60E0FB00/FC00   0xFFFFCFE3   0xFFFFCFE4   0xFFFFCFE9  0xFFFFCFEC 0x5D8DC     0x5D8EE     0xFFFFD1C8
 *  60E15120        0xFFFFD1CF   0xFFFFD1D0   0xFFFFD1D5  0xFFFFD1D8 0x5F054     0x5F066     0xFFFFD3B4
 *  60E1B900        0xFFFFCFE3   0xFFFFCFE4   0xFFFFCFE9  0xFFFFCFEC 0x5DB74     0x5DB86     0xFFFFD1C8
 *  60E1C500        0xFFFFD147   0xFFFFD148   0xFFFFD14D  0xFFFFD150 0x5E700     0x5E712     0xFFFFD32C
 *  60E1D400(base)  0xFFFFD20B   0xFFFFD20C   0xFFFFD211  0xFFFFD214 0x5FA90     0x5FAA2     0xFFFFD3F0
 *  60E32000        0xFFFFD24F   0xFFFFD250   0xFFFFD255  0xFFFFD258 0x65104     0x65116     0xFFFFD438
 * =================================================================== */

/* ---- Primary bank selection (60E0E500).  Re-point these macros to model
 *      another bank (values above). ---- */

/* Security state bytes (state_check1/state_check2 reads) */
#define AUX_SECURITY_STATE_1   (*(volatile uint8_t *)0xFFFFD147UL)
#define AUX_SECURITY_STATE_2   (*(volatile uint8_t *)0xFFFFD148UL)

/* Seed RAM area (3 bytes) + level byte written by seed_gen */
#define AUX_SEED_RAM_BASE      (*(volatile uint8_t *)0xFFFFD14DUL)
#define AUX_SEED_LEVEL         (*(volatile uint8_t *)0xFFFFD150UL)

/* position_check tables (data, verbatim ROM bytes) */
#define AUX_POSITION_TABLE     0x0005E430UL
#define AUX_POSITION_WORD_TAB  0x0005E434UL

/* 2nd-stage mask pointer: `mov.w <lit>,r1; mov.w @r1,r6` — sign-extended
 * 16-bit RAM pointer (60E0E500 lit 0xD32C -> 0xFFFFD32C).  The mask WORD
 * is runtime-written RAM => value not statically known [AUX-TBD].
 * [AUX-CORRECTION] baseline c/security_access.c `mask = 0x61F2` is a
 * misread: 0x61F2 @0x56CB0 is the instruction `mov.l @r15,r1`, not data. */
#define AUX_POSITION_MASK_PTR  0xFFFFD32CUL

/* key_validate table (10 x 3-byte, byte-identical in all banks) */
#define AUX_KEY_VALIDATE_TABLE 0x0005E442UL

/* Free-running entropy counter (identical VA in all banks) */
#define AUX_ENTROPY_COUNTER    (*(volatile uint32_t *)0xFFFFF430UL)

/* ===================================================================
 *  UDS protocol constants (same as baseline)
 * =================================================================== */

#define SID_SECURITY_ACCESS    0x27    /* CONFIRMED in every image */
#define NRC_ROR                0x12    /* RequestOutOfRange */
#define NRC_GR_31              0x31    /* subfunc==0 / position / key-validate reject */
#define SF_REQUEST_SEED        0x01
#define SF_SEND_KEY            0x04

/* ===================================================================
 *  Forward declarations
 * =================================================================== */

static uint8_t  aux_state_check1(void);
static uint8_t  aux_state_check2(void);
static uint8_t  aux_position_check(uint8_t level);
static void     aux_seed_gen(uint8_t level);
static uint8_t  aux_data_copy(uint8_t dst[3]);

/* Shared-codebase helpers (identical algorithm in every image; VAs per bank
 * in the table above).  These are reconstructed in c/security_access.c for
 * the baseline; the aux images call the same-shaped functions at the
 * relocated VAs. */
extern uint8_t  aux_key_validate(uint8_t b0, uint8_t b1, uint8_t b2);
extern uint8_t  aux_seed_key_related(uint8_t level, const uint8_t seed[3],
                                     const uint8_t key[3]);
extern void     aux_unlock(uint8_t level);
extern void     uds_error_response(uint8_t sid, uint8_t nrc);
extern void     uds_positive_response(uint8_t sid, const uint8_t *data,
                                      uint8_t len);

/* ===================================================================
 *  1.  SecurityAccess handler — aux entry dispatch (60E0E500 @0x56E4C)
 *
 *  Called from the UDS dispatcher with:
 *    r4 = message length (16-bit payload length EXCLUDING the SID byte;
 *         RequestSeed = 1, SendKey = 4)  [AUX-EVIDENCE 0x56E60]
 *    r5 = subfunction byte
 *
 *  Entry dispatch (byte-identical in all 9 images; VAs for 60E0E500):
 *    0x56E60 mov.w r0,@(0x04,r15)   save msg_len
 *    0x56E64 cmp/eq #0x01,r0        subfunc == 1 ?
 *    0x56E66 bt/s 0x56E6E          -> RequestSeed flow
 *    0x56E6A bra  0x56FD8          -> else path (subfunc != 1)
 *
 *  msg_len gates (identical offsets):
 *    +0x42 tst r4,r4   ; ==0 -> NRC 0x12        (0x56E8E)
 *    +0x4C tst r5,r5   ; ==0 -> NRC 0x31        (0x56E9C)
 *    +0x7A cmp/eq #1   ; msg_len==1 required    (0x56EC8 -> NRC 0x12)
 *    +0xF2 cmp/eq #4   ; SendKey msg_len==4     (0x56F40 -> NRC 0x12)
 *
 *  Response shape: [0x67, subfunc, 3 seed bytes] (resp builder @0x56FF6,
 *  `mov #0x67,r3`, r6=3 copies) -> uds_send(0x67500, r4=0x27).
 * =================================================================== */

void aux_security_access_handler(const uint8_t *msg, uint8_t subfunc)
{
    uint8_t  seed[3];
    uint8_t  resp_data[5];   /* 0x67 + subfunc + 3 seed bytes */
    uint8_t  state1;         /* AUX_SECURITY_STATE_1 */
    uint8_t  state;          /* AUX_SECURITY_STATE_2 */

    /* --- State reads (only inside the subfunc==1 branch in the ROM;
     *     kept unconditional here for C convenience, benign [REQSEED-EVIDENCE]) */
    state1 = aux_state_check1();
    state  = aux_state_check2();

    uint16_t msg_len = (msg[0] << 8) | msg[1];

    /* --- msg_len == 0 -> NRC 0x12 (ROM 0x56E8E -> 0x56FC6) --- */
    if (msg_len == 0) {
        uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
        return;
    }

    /* --- subfunc == 0 -> NRC 0x31 (ROM 0x56E9C -> 0x56FC8, mov #0x31) --- */
    if (subfunc == 0) {
        uds_error_response(SID_SECURITY_ACCESS, NRC_GR_31);
        return;
    }

    /* --- Entry dispatch: ONLY subfunc==1 enters (ROM 0x56E62-0x56E6A).
     *     The abs-trick (0x56EAA-0x56EC4) is real but vestigial:
     *     abs(1)&1==1 always resolves to RequestSeed; its even-branch
     *     bf/s (0x56EC2 -> 0x56F3E) is never taken. --- */
    if (subfunc == SF_REQUEST_SEED) {

        /* ---- Subfunction 0x01: RequestSeed ---- */

        /* msg_len must be exactly 1 (ROM 0x56EC6-0x56ECA -> NRC 0x12
         * @0x56F34).  [AUX-EVIDENCE] identical in all 9 images. */
        if (msg_len != 1) {
            uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
            return;
        }

        /* Response header: [0x67, subfunc, ...] (resp builder 0x56FF6,
         * mov #103,r3 = 0x67 @0x56FF6; r6=3 copies) */
        resp_data[0] = 0x67;
        resp_data[1] = subfunc;

        /* seed_gen(3) — side-effect finalization (ROM 0x56ECE-0x56ED0:
         * jsr @r11(seed_gen) with delay mov #0x03,r4).  [AUX-EVIDENCE]
         * level-3 fast path writes FF FF FF into the seed RAM. */
        aux_seed_gen(3);

        /* position_check(subfunc) — level admission (ROM 0x56ED4-0x56EDA:
         * jsr position_check, r4 = subfunc byte; result -> r12/r9). */
        uint8_t chk = aux_position_check(subfunc);
        if (chk == 3) {
            /* not-found sentinel -> NRC 0x31 (ROM 0x56EDE-0x56EE0 -> 0x56F2A) */
            uds_error_response(SID_SECURITY_ACCESS, NRC_GR_31);
            return;
        }

        /* key_validate(state1, state, chk) — state/position cross-check
         * (ROM 0x56EE4-0x56EEC, b0=[r15+8]=state1, b1=r10=state2,
         * b2=r12=chk); nonzero return -> NRC 0x31 (0x56EF2-0x56EF4 ->
         * 0x56F20).  [AUX-EVIDENCE] the 10-entry table @0x5E442 is
         * byte-identical to the baseline @0x5FAA2. */
        if (aux_key_validate(state1, state, chk) != 0) {
            uds_error_response(SID_SECURITY_ACCESS, NRC_GR_31);
            return;
        }

        /* Conditional seed write-back (ROM 0x56EF8-0x56F14):
         *   state2 == chk  -> response seed bytes zero-filled {0,0,0};
         *   state2 != chk  -> seed_gen(chk) then data_copy(r13).
         * [AUX-EVIDENCE] identical conditional structure in all 9 images. */
        if (state == chk) {
            resp_data[2] = resp_data[3] = resp_data[4] = 0;
        } else {
            aux_seed_gen(chk);
            aux_data_copy(&resp_data[2]);
        }

        /* Send [0x67, subfunc, 3 bytes] (ROM 0x56F14-0x56F1A:
         * mov #0x03,r6; bsr resp_builder with r4=subfunc) */
        uds_positive_response(SID_SECURITY_ACCESS, resp_data, 5);

    } else if (subfunc == SF_SEND_KEY) {
        /* ---- Subfunction 0x04: SendKey — DEAD CODE in all 9 images ----
         * [AUX-EVIDENCE / SENDKEY-RECONCILIATION] verdict (b): the body
         * (60E0E500 0x56F3E-0x56FBE; baseline 0x58592-0x58610) is present
         * byte-identically but UNREACHABLE — the only incoming branch is
         * the never-taken abs-trick even-branch bf/s (0x56EC2), and the
         * entry dispatch routes subfunc!=1 to the else path.  Kept below
         * as the ROM-accurate reconstruction of the shared remnant. */

        /* msg_len == 4 (subfunc + 3 key bytes), else NRC 0x12 (0x56F40-
         * 0x56F42 -> 0x56FBC). */
        if (msg_len != 4) {
            uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
            return;
        }

        /* data_copy -> returns seed LEVEL (ROM 0x56F46-0x56F4C) */
        uint8_t level = aux_data_copy(seed);

        /* side-effect finalization seed_gen(3) (ROM 0x56F4E-0x56F50) */
        aux_seed_gen(3);

        /* level==3 shortcut -> NRC 0x22 (ROM 0x56F52-0x56F56 -> 0x56FB2);
         * else level_slot_resolver vs subfunc slot check -> NRC 0x22
         * (0x56F5A-0x56F68), key bytes read via uds_read_payload r6=3
         * (0x56F6C-0x56F74), seed_key_related (0x56F7E), match -> unlock
         * + resp builder r6=0; mismatch -> NRC 0x35 (0x56F90).  VAs are
         * the relocated analogues of the baseline SendKey body. */
        uint8_t match = aux_seed_key_related(level, seed, &msg[4]);
        if (match == 0) {
            aux_unlock(level);
            uint8_t ok_resp[2] = { 0x67, subfunc };
            uds_positive_response(SID_SECURITY_ACCESS, ok_resp, 2);
        } else {
            uds_error_response(SID_SECURITY_ACCESS, 0x35);   /* InvalidKey */
        }

    } else {
        /* ---- subfunc != 1 else path (ROM 0x56FD8-0x56FF4) ----
         * [AUX-EVIDENCE] identical in all 9 images:
         *   tst r4,r4 ; subfunc==0 -> uds_resp_subfunc0 (0x53D32) with
         *                            r4=0x27  [response helper];
         *   subfunc!=0 -> NO response at all (silent return).
         * The NRC_ROR below models ISO/expected behaviour and is
         * UNREACHABLE for conformant traffic. */
        uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
    }
}

/* ===================================================================
 *  2.  aux_state_check1  (60E0E500 @0x55212; baseline 0x56866)
 *
 *  Reads AUX_SECURITY_STATE_1 and returns its value.
 *  [AUX-EVIDENCE] `mov.l <lit>,r3; rts; mov.b @r3,r0` — byte read of the
 *  per-bank state byte (60E0E500 0xFFFFD147).
 * =================================================================== */

static uint8_t aux_state_check1(void)
{
    return AUX_SECURITY_STATE_1;
}

/* ===================================================================
 *  3.  aux_state_check2  (60E0E500 @0x55292; baseline 0x568E6)
 *
 *  Reads AUX_SECURITY_STATE_2 (60E0E500 0xFFFFD148).
 * =================================================================== */

static uint8_t aux_state_check2(void)
{
    return AUX_SECURITY_STATE_2;
}

/* ===================================================================
 *  4.  aux_position_check  (60E0E500 @0x5523E; baseline 0x56892)
 *
 *  [AUX-EVIDENCE] structure identical to baseline: table base
 *  (60E0E500 0x5E430) with stride i*2+i*4=i*6, byte[+1] compared against
 *  the level; on match, second stage ANDs the word at word_tab_base
 *  (0x5E434) + i*6 with the RAM-resident mask; nonzero -> return i,
 *  else -> 3.  No match -> 3.
 *
 *  [AUX-CORRECTION] the mask is NOT the constant 0x61F2 (baseline C
 *  comment was a misread of an instruction).  The ROM loads a
 *  sign-extended 16-bit RAM pointer (`mov.w <lit>,r1; mov.w @r1,r6`:
 *  60E0E500 lit 0xD32C -> 0xFFFFD32C) and reads the mask word from RAM.
 *  The mask value is runtime-written => [AUX-TBD]; behaviourally
 *  irrelevant for the stock tables (0xFFFD/0xFFFC are dense -> the AND
 *  is always nonzero for levels 1/2).
 *
 *  word_tab data variants:
 *    {0x0000,0xFFFD,0xFFFC,0x0001} — E500/E700/15120/C500/D400/E32000
 *    {0x0000,0xFFFF,0xFFFE,0x0001} — FB00/FC00/B900  (per-bank tables)
 *
 *  Returns: 0..2 matching entry index; 3 = not-found/mask-clear.
 * =================================================================== */

static uint8_t aux_position_check(uint8_t level)
{
    /* ROM @0x5E430 — 4 entries x 6 bytes, byte[1] compared (verbatim bytes,
     * identical in every bank). */
    static const uint8_t table[4][6] = {
        { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 },
        { 0x01, 0x01, 0x02, 0x00, 0xFF, 0xFD },
        { 0xF1, 0xF1, 0xF2, 0x00, 0xFF, 0xFC },
        { 0x00, 0x00, 0x00, 0x01, 0x00, 0x01 },
    };
    /* Second-stage word table @0x5E434+i*6 — primary bank (60E0E500). */
    static const uint16_t word_tab[4] = { 0x0000, 0xFFFD, 0xFFFC, 0x0001 };
    /* Mask: RAM-resident word @ AUX_POSITION_MASK_PTR (runtime value
     * [AUX-TBD]; see header correction note). */
    uint16_t mask = *(volatile uint16_t *)AUX_POSITION_MASK_PTR;

    for (int i = 0; i < 4; i++) {
        if (table[i][1] == level) {
            if ((word_tab[i] & mask) != 0)
                return i;
            return 3;
        }
    }
    return 3;
}

/* ===================================================================
 *  5.  aux_seed_gen  (60E0E500 @0x55346; baseline 0x5699A)
 *
 *  Generates the 3-byte seed and writes it to the per-bank seed RAM
 *  (60E0E500 0xFFFFD14D..0xFFFFD14F, level byte 0xFFFFD150).
 *
 *  [AUX-EVIDENCE] structure identical to the baseline VERIFIED function
 *  (docs/notes/UDS_SECURITY_MAPPING.md, c/security_access.c §5):
 *    - level==3 fast path -> FF FF FF (60E0E500 @0x55362 cmp/eq #3 ->
 *      0x55438 write-back);
 *    - level!=3 entropy path: 32-bit counter @0xFFFFF430 (lit 0xF430
 *      sign-extended; 60E0E500 0x55392), 4 LE bytes, helper bsr 0x55226
 *      (baseline 0x5687A) returns 0 iff state byte == 4; state==4 ->
 *      55 AA 55, else XOR-mix b2^b0 / b1^b0 / b3^b0; retry loop max 16
 *      with FF FF FF fallback;
 *    - common write-back (60E0E500 0x55438-0x55454, helpers 0x3920/0x3934):
 *      [level]=r0, [base+0]=r14, [base+1]=r12, [base+2]=r13.
 * =================================================================== */

static void aux_seed_gen(uint8_t level)
{
    uint8_t r14, r12, r13;

    if (level == 3) {
        r14 = r12 = r13 = 0xFF;
    } else {
        uint8_t state = AUX_SECURITY_STATE_1;
        int     retry = 0;

        for (;;) {
            uint32_t counter = AUX_ENTROPY_COUNTER;
            uint8_t  b0 = (uint8_t)(counter & 0xFF);
            uint8_t  b1 = (uint8_t)((counter >> 8) & 0xFF);
            uint8_t  b2 = (uint8_t)((counter >> 16) & 0xFF);
            uint8_t  b3 = (uint8_t)((counter >> 24) & 0xFF);

            if (state == 4) {
                r14 = 0x55; r12 = 0xAA; r13 = 0x55;
            } else {
                r14 = b2 ^ b0;
                r12 = b1 ^ b0;
                r13 = b3 ^ b0;
            }

            retry++;
            if (retry > 16) {
                r14 = r12 = r13 = 0xFF;
                break;
            }
            if ((r14 == 0 && r12 == 0 && r13 == 0) ||
                (r14 == 0xFF && r12 == 0xFF && r13 == 0xFF))
                continue;
            break;
        }
    }

    AUX_SEED_LEVEL        = level;
    AUX_SEED_RAM_BASE     = r14;
    *(volatile uint8_t *)0xFFFFD14EUL = r12;
    *(volatile uint8_t *)0xFFFFD14FUL = r13;
}

/* ===================================================================
 *  6.  aux_data_copy  (60E0E500 @0x5546C; baseline 0x56AC0)
 *
 *  Copies the 3 seed bytes from the per-bank seed RAM into dst and
 *  returns the seed LEVEL byte (ROM 60E0E500 reads 0xFFFFD14D/0x14E/
 *  0x14F and returns the word @0xFFFFD150).
 * =================================================================== */

static uint8_t aux_data_copy(uint8_t dst[3])
{
    dst[0] = AUX_SEED_RAM_BASE;
    dst[1] = *(volatile uint8_t *)0xFFFFD14EUL;
    dst[2] = *(volatile uint8_t *)0xFFFFD14FUL;
    return AUX_SEED_LEVEL;
}

/* ===================================================================
 *  7.  aux_key_validate / aux_seed_key_related / aux_unlock
 *
 *  Identical algorithms in every image (10-entry table @per-bank base,
 *  secret "MazdA" + LFSR init identical; data verified for 60E0E500,
 *  60E0FB00, 60E1D400, 60E32000).  The baseline implementations in
 *  c/security_access.c (§6/§8/§9) apply verbatim with the per-bank
 *  table/secret addresses from the header table.  Declared extern here
 *  [AUX-EVIDENCE]; not re-inlined (shared core, out of entry-dispatch
 *  scope).
 * =================================================================== */
