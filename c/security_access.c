/**
 * security_access.c — UDS Service 0x27 (SecurityAccess) handler
 *
 * ═══════════════════════════════════════════════════════════════════
 *  STATUS: VERIFIED core; RequestSeed flow CONFIRMED 2026-08-04.
 * Address: 0x584A0
 *  2026-08-04: RequestSeed sub-flow (r.191-255) CONFIRMED against ROM
 *  (docs/notes/REQUEST_SEED_EVIDENCE.md) — incl. entry dispatch (only
 *  subfunc==1 enters), msg_len==1 requirement, conditional seed path,
 *  and the finding that SendKey (0x58592) is UNREACHABLE in 60E1D400.
 *  2026-08-04: key_validate (10-entry table @0x5FAA2) e position_check
 *  (word_tab[2]=0xFFFC) verificati contro ROM; seed_gen VERIFIED
 *  2026-08-03 (test_seed_gen_5699A.py, 0 mismatch); lfsr/seed_key_related
 *  VERIFIED 2026-07-31.
 *
 *  IMPORTANT — READ FIRST:
 *   * The seed↔key TRANSFORM core (seed_key_related) has been corrected to
 *     match the stock ROM 60E1D400 algorithm and is VERIFIED (see the
 *     evidence block in seed_key_related).  For stock ECUs, use
 *     tools/mazda_security.py (ECOMcat) — it is bit-equivalent to the ROM
 *     at level 1 and reproduces all ROM-emulated reference vectors.
 *   * The UDS handler FLOW is confirmed against the ROM: key_validate,
 *     position_check, seed_gen, the state checks and the RequestSeed
 *     sub-flow are VERIFIED (see each block below and
 *     docs/notes/REQUEST_SEED_EVIDENCE.md).  Documented discrepancies
 *     (logic untouched, comments only): r4 = msg_len (not a pointer),
 *     ROM requires msg_len==1 for RequestSeed, the seed bytes are written
 *     conditionally (state2==chk -> {0,0,0}), and the SendKey body
 *     (0x58592-0x58610) is UNREACHABLE in this ROM build — the entry
 *     dispatch routes only subfunc==1 into the handler; subfunc!=1 falls
 *     to 0x5862C (subfunc==0 -> resp, else silent no-response).
 *     2026-08-04 reconciliation (docs/notes/SENDKEY_RECONCILIATION.md):
 *     the SendKey body is dead code in ALL 9 public stock ROMs (see
 *     "SendKey" note below); verdict (b) — no removal, kept as the
 *     ROM-accurate reconstruction of the shared-codebase remnant.
 *   * This file must NOT be used to answer real security-access requests
 *     on a stock ECU until the flow is validated against the ROM end-to-end
 *     and, ideally, real captures (the RequestSeed flow is now ROM-CONFIRMED
 *     2026-08-04, but real-ECU capture validation is still open; SendKey is
 *     dead code in all 9 public stock ROMs — see SENDKEY_RECONCILIATION.md).
 *   * docs/notes/UDS_SECURITY_MAPPING.md tracks the security-access open
 *     items (subfunction→level mapping, seed_gen internals, key_validate
 *     middle byte); the stock-LFSR core itself was solved 2026-07-31 —
 *     see tools/mazda_security.py docstring.
 * ═══════════════════════════════════════════════════════════════════
 *
 * Structural C reconstruction of the SH-2 handler at ROM 0x584A0
 * in 60E1D400.bin (stock Mazda RX-8 PCM).
 *
 * The UDS dispatch table at 0x5F57C routes SID 0x27 here:
 *   entry[10]: SID=0x27, handler=0x584A0, accessMask=0x1000000E
 *
 * This file covers:
 *   1. The main SecurityAccess dispatch (subfunction 0x01 = RequestSeed,
 *      subfunction 0x04 = SendKey).
 *   2. The seed-generation pipeline (seed_gen @ 0x5699A).
 *   3. The key-validation pipeline (SeedKeyRelated @ 0x56ADA).
 *   4. The 24-bit Galois LFSR core used for the seed↔key transform.
 *
 * Reference:
 *   - tools/mazda_security.py (ECOMcat / Craig Smith Car Hacking Handbook)
 *   - ROM data at 0x5FAC0: 5-byte secret "MazdA"
 *   - ROM data at 0x5FAC5: per-level LFSR INIT table (3 bytes per level)
 *   - docs/notes/UDS_SECURITY_MAPPING.md (subfunction→level mapping,
 *     seed_gen internals, key_validate middle byte — status updated there)
 */

#include <stdint.h>
#include <string.h>

/* ===================================================================
 *  Hardware register / memory-map definitions
 * =================================================================== */

/* Diagnostic session state (1=default, 2=programming, 3=extended, 4=safety) */
#define DIAG_SESSION        (*(volatile uint8_t  *)0xFFFFDE5CUL)

/* Security-unlocked flag — written by unlock() */
#define SECURITY_UNLOCKED   (*(volatile uint8_t  *)0xFFFFD0F2UL)

/* Security state byte 1 (read by state_check1) */
#define SECURITY_STATE_1    (*(volatile uint8_t  *)0xFFFFD20BUL)

/* Security state byte 2 (read by state_check2) */
#define SECURITY_STATE_2    (*(volatile uint8_t  *)0xFFFFD20CUL)

/* Seed data RAM area (3 bytes, written by seed generation) */
#define SEED_RAM_BASE       (*(volatile uint8_t  *)0xFFFFD211UL)

/* ===================================================================
 *  Constants from ROM literal pools
 * =================================================================== */

/* The 5-byte shared secret — offset varies per ROM build.
 *   60E1D400: 0x5FAC0  60E0FC00: 0x5D90C
 *   Stock: "MazdA"   [REDACTED]: vendor-family secret (capture-verified, tuned ECU;
 *   literal removed for privacy — see local notes).
 */
#define SECRET_ADDR         0x0005FAC0UL

/* Per-level LFSR INIT table — stored right after the secret, 3 bytes per
 * level (entry = base + level*3).  VERIFIED (SeedKeyRelated @0x56ADA,
 * 0x56B18-0x56B40): the ROM loads entry[2] into the LOW state byte and
 * entry[0] into the HIGH state byte, i.e.  init = entry[0]<<16|entry[1]<<8|entry[2].
 *   level 1 (0x5FAC8): C5 41 A9 -> init 0xC541A9  (== ECOMcat init)
 *   level 2 (0x5FACB): A3 95 82 -> init 0xA39582
 * The TAPS are NOT stored here — they are hardcoded in the ROM code as
 * 0x909028 (xor #8/#32/#16/#128/#16 @0x56C1E-0x56C38 + feedback OR 0x80
 * into bit 23 = bits {23,20,15,12,5,3}).  0xA39582 was previously misread
 * as "ROM taps differing from ECOMcat"; it is a level-2 INIT value.
 */
#define LFSR_PARAM_ADDR     0x0005FAC5UL

/* Verified Galois taps, identical in ROM code and ECOMcat reference. */
#define LFSR_TAPS           0x909028UL

/* Table for position_check() — ROM @0x5FA90, 6-byte stride (disasm
 * 0x5689E-0x568A2 computes i*2 + i*4 = i*6); entry byte[+1] compared. */
#define POSITION_TABLE_ADDR 0x0005FA90UL

/* ===================================================================
 *  UDS protocol constants
 * =================================================================== */

#define UDS_SID_SHIFT        0x40   /* Positive response = SID | 0x40 */
#define UDS_NRC_MASK         0x7F   /* Negative response prefix byte */

/* Service ID handled by this module (UDS SecurityAccess) */
#define SID_SECURITY_ACCESS  0x27

/* Negative Response Codes (NRC) */
#define NRC_GR               0x11   /* GeneralReject */
#define NRC_ROR              0x12   /* RequestOutOfRange */
#define NRC_SAD              0x33   /* SecurityAccessDenied */
#define NRC_IK               0x35   /* InvalidKey */
#define NRC_ENOA             0x36   /* ExceededNumberOfAttempts */
#define NRC_RTDNE            0x37   /* RequiredTimeDelayNotExpired */

/* SecurityAccess subfunctions */
#define SF_REQUEST_SEED      0x01
#define SF_SEND_KEY          0x04

/* ===================================================================
 *  Forward declarations of sub-functions called by the handler
 *  (These are separate ROM functions reconstructed in this file.)
 * =================================================================== */

static uint8_t  state_check1(void);
static uint8_t  state_check2(void);
static uint8_t  position_check(uint8_t level);
static void     seed_gen(uint8_t level);
static uint8_t  key_validate(uint8_t b0, uint8_t b1, uint8_t b2);
static uint8_t  data_copy(uint8_t dst[3]);
static uint8_t  seed_key_related(uint8_t level, const uint8_t seed[3],
                                 const uint8_t key[3]);
static void     unlock(uint8_t level);

/* UDS response helpers (reconstructed elsewhere) */
extern void     uds_error_response(uint8_t sid, uint8_t nrc);
extern void     uds_positive_response(uint8_t sid, const uint8_t *data,
                                      uint8_t len);

/* ===================================================================
 *  1.  Main SecurityAccess handler  (ROM 0x584A0)
 *
 *  Called from udsHandler dispatch (dispatcher 0x697E8-0x69840, CONFIRMED) with:
 *    r4 = message length (16-bit payload length EXCLUDING the SID byte;
 *         RequestSeed = 1, SendKey = 4)
 *    r5 = subfunction byte
 *  [REQSEED-EVIDENCE 2026-08-04] The first parameter of the C signature models
 *  this length — the ROM does NOT pass a buffer pointer.  Payload bytes are read
 *  via the UDS stack helper 0x68BC0 (call @0x584C8, r6=1 -> subfunction byte into
 *  [r15]; SendKey reads 3 key bytes @0x585C0 with r6=3).  The C reconstruction's
 *  msg_len = (msg[0]<<8)|msg[1] is semantically equivalent.
 *
 *  The message buffer format (Ghidra UDS frame):
 *    offset 0:    length (2 bytes big-endian)
 *    offset 2:    SID (1 byte)
 *    offset 3:    subfunction (1 byte)
 *    offset 4..:  data bytes
 * =================================================================== */

void security_access_handler(const uint8_t *msg, uint8_t subfunc)
{
    uint8_t  seed[3];
    uint8_t  resp_data[5];   /* 0x67 + subfunc + 3 seed bytes (ROM resp builder 0x5864A, r6=3) */
    uint8_t  state1;   /* SECURITY_STATE_1 — key_validate b0 (ROM 0x58538) */
    uint8_t  state;    /* SECURITY_STATE_2 — key_validate b1 (state arg of the old unlock() guess) */

    /* --- State reads at ROM handler 0x584A0 entry (CONFIRMED 2026-08-03) ---
     * The ROM unconditionally calls state_check1() @0x584CC and state_check2()
     * @0x584D2.  The old guess "if state_check1() != 0 -> NRC_GR (0x11)"
     * is WRONG — there is NO such guard:
     *   * disasm 0x584A0-0x58640: the only NRC literals emitted are
     *     {0x31, 0x12, 0x35, 0x22}.  NRC 0x11 (GR) never appears in the
     *     handler (mov #0x11,r5 is absent).
     *   * state_check1() @0x56866 just returns byte @0xFFFFD20B
     *     (SECURITY_STATE_1); its result is saved to the caller frame by the
     *     delay-slot `mov.b r0,@(0x08,r15)` @0x584D6, then consumed as the
     *     FIRST argument of the key_validate() call @0x58538-0x58540
     *     (RequestSeed path).  It gates nothing by itself.
     *   - state_check2() @0x568E6 returns byte @0xFFFFD20C (SECURITY_STATE_2),
     *     kept in r10 (@0x584DA) and used as key_validate() b1 + unlock() arg.
     *   - sh2emu probe over many {state1, state2, payload, subfunc} inputs:
     *     uds_error_response @0x553AA is reached only with r5 (NRC) in
     *     {0x31, 0x12, 0x35, 0x22}, never 0x11, for every SECURITY_STATE_1.
     * The two reads are kept (the ROM makes them) but they do NOT return
     * NRC_GR. */
    state1 = state_check1();
    state  = state_check2();

    /* --- Validate message length --- */
    uint16_t msg_len = (msg[0] << 8) | msg[1];
    if (msg_len == 0) {
        uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
        return;
    }

    /* --- Validate subfunction ---
     * ROM 0x584EC-0x584F8: the subfunction byte read via 0x68BC0 (=[r15]) is
     * tested with tst r5,r5 @0x584F0; == 0 -> NRC 0x31 (mov #0x31,r5 @0x584F8),
     * NOT 0x12.  (0x12 is used by the ROM only for the length checks.) */
    if (subfunc == 0) {
        uds_error_response(SID_SECURITY_ACCESS, 0x31);
        return;
    }

    /* --- Subfunction dispatch --- */

    if (subfunc == SF_REQUEST_SEED) {
        /* ---- Subfunction 0x01: RequestSeed ---- */

        /* [REQSEED-EVIDENCE] CONFIRMED 2026-08-04 against ROM 60E1D400
         * (see docs/notes/REQUEST_SEED_EVIDENCE.md).  Entry dispatch
         * 0x584B6-0x584BE (cmp/eq #0x01; bt/s 0x584C2) routes ONLY
         * subfunc==1 into this flow.  The old "absolute-value trick"
         * (abs_sub @0x584FE-0x58516) is REAL but vestigial: abs(1)&1==1
         * always resolves to RequestSeed, and there is NO "level must be
         * 1" guard (the ==1 check at 0x5851A-0x5851E is on msg_len, see
         * note below).  Documented discrepancies (logic untouched):
         *   (a) ROM requires msg_len == 1 here (0x5851A-0x5851E ->
         *       NRC 0x12 @0x58588); the C code only rejects msg_len == 0.
         *   (b) the seed bytes are written CONDITIONALLY at 0x5854C-0x58566:
         *       state2 == chk -> {0,0,0}; else -> seed_gen(chk) then
         *       data_copy(r13).  The C data_copy() below is unconditional.
         *   (c) the state reads above happen only in this branch in the
         *       ROM; the C code runs them for every subfunction (benign). */

        /* [REQSEED-EVIDENCE] The response frame [0x67, subfunc, 3 seed
         * bytes] is built by the ROM resp builder 0x5864A (mov #103,r3
         * = 0x67 @0x5864A; r6=3 copies) — the C code inlines it into
         * resp_data[].
         * seed_gen(3) == ROM 0x58522-0x58524 (jsr @0x5699A; delay-slot
         * mov #0x03,r4).  NOTE: in the ROM this first generation is a
         * side-effect finalization — when a seed is actually sent, the
         * ROM re-generates with seed_gen(chk) @0x5855E (see below). */
        resp_data[0] = 0x67;           /* SID | 0x40 = 0x67 */
        resp_data[1] = subfunc;        /* echo subfunction */

        /* Generate the 3-byte seed using LFSR level 3 (ROM 0x58522) */
        seed_gen(3);

        /* Validate the generated level via position_check.
         * [REQSEED-EVIDENCE] CONFIRMED: ROM 0x58526-0x5852A calls
         * 0x56892 with r4 = subfunc byte; 0x58530-0x58534: extu.b(r12);
         * cmp/eq #0x03,r0; bt/s 0x5857E; the ==3 (not-found) sentinel ->
         * NRC 0x31 @0x5857E (mov #0x31,r5). */
        uint8_t chk = position_check(subfunc);
        if (chk == 3) {
            /* Level validation failed */
            uds_error_response(SID_SECURITY_ACCESS, 0x31);
            return;
        }

        /* State/position cross-check — [REQSEED-EVIDENCE] CONFIRMED:
         * ROM 0x58538-0x58540 calls key_validate(b0,b1,b2) where
         *   b0 = [r15+8] = state_check1()  = SECURITY_STATE_1 (disasm 0x58538
         *        mov.b @(0x08,r15),r0; state_check1 result stored @0x584D6)
         *   b1 = r10      = state_check2() = SECURITY_STATE_2 (mov r0,r10 @0x584DA)
         *   b2 = r12      = position_check() result (mov r12,r6 @0x5853A)
         * and rejects with NRC 0x31 on a nonzero return (@0x58544-0x58548
         * extu.b r0,r4; tst r4,r4; bf/s 0x58574).  The old C wiring
         * (state, subfunc, chk) is corrected to (state1, state, chk). */
        if (key_validate(state1, state, chk) != 0) {
            uds_error_response(SID_SECURITY_ACCESS, 0x31);
            return;
        }

        /* [REQSEED-EVIDENCE] ROM 0x5854C-0x58566 does this CONDITIONALLY:
         *   state2 == chk (cmp/eq r9,r10 @0x5854E) -> zero-fill the 3 seed
         *   bytes (mov #0,r0; mov.b r0,@(0x02/0x01/0x00,r13) @0x58554-0x5855C);
         *   else -> seed_gen(chk) (jsr @0x5699A @0x5855E, delay mov r12,r4)
         *   then data_copy(r13) (jsr @0x56AC0 @0x58562, delay mov r13,r4).
         * The C data_copy() below is unconditional and copies the level-3
         * seed (discrepancy (b), documented above). */
        data_copy(&resp_data[2]);

        /* ROM 0x58568-0x5856E: mov #0x03,r6; mov r13,r5; bsr 0x5864A with
         * r4 = subfunc -> builds [0x67, subfunc, 3 bytes] and sends via
         * 0x68B60 (len 5). */
        uds_positive_response(SID_SECURITY_ACCESS, resp_data, 5);

    } else if (subfunc == SF_SEND_KEY) {
        /* ---- Subfunction 0x04: SendKey ---- */

        /* [SENDKEY-RECONCILIATION 2026-08-04] RESOLVED — verdict (b):
         * this branch is DEAD CODE in ALL 9 public stock ROMs (60E1D400
         * baseline + 8 aux; independent whole-ROM branch scan, see
         * docs/notes/SENDKEY_RECONCILIATION.md).  In every image the SendKey
         * body (60E1D400: 0x58592-0x58610; different VA per ROM) is present
         * with IDENTICAL structure (same 8-byte signature: mov r4,r0;
         * cmp/eq #0x04,r0; bf/s ...; nop) but is UNREACHABLE:
         *   - entry dispatch (60E1D400 0x584B6-0x584BE) routes only
         *     subfunc==1 into the handler body; subfunc!=1 falls to the
         *     else path (tst r4,r4: subfunc==0 -> resp via 0x55386;
         *     subfunc!=0 -> NO response, silent) in every image;
         *   - the ONLY incoming branch to the block in every image is the
         *     abs-trick even-branch bf/s (60E1D400 @0x58516; e.g. @0x5711A
         *     in 60E0E700, @0x55FAA in 60E0FB00/60E0FC00, @0x57186 in
         *     60E1C500, @0x56EC2 in 60E0E500, @0x57ADA in 60E15120,
         *     @0x56242 in 60E1B900, @0x5D456 in 60E32000), which can never
         *     be taken (subfunc==1 is odd -> subfunc&1==1 -> bf/s not
         *     taken).  No indirect refs (literal pools / jump tables) to the
         *     block in any image.
         * The earlier "VERIFIED" SendKey work (fd56201: SeedKeyRelated
         * @0x56ADA transform; 31bb0ac: flow aligned to the ROM body
         * msg_len==4 gate @0x58592, data_copy->level, seed_key_related,
         * unlock) verified the ALGORITHM/FLOW against the ROM body, not the
         * REACHABILITY of that body from the UDS dispatch.  The code below
         * is intentionally KEPT (no removal) as the ROM-accurate
         * reconstruction of a shared-codebase remnant.  Previous flag:
         * docs/notes/REQUEST_SEED_EVIDENCE.md discrepancy (e). */

        /* ROM 0x58592-0x58596: FIRST instruction of the SendKey path is
         * `mov r4,r0; cmp/eq #0x04,r0; bf/s 0x58610` — the message length
         * must be exactly 4 (subfunction + 3 key bytes), else NRC 0x12
         * @0x58610.  This check happens BEFORE the 3 key bytes are read
         * (0x68BC0 @0x585C0-0x585CC). */
        if (msg_len != 4) {
            uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
            return;
        }

        /* Retrieve the cached seed data.  ROM data_copy @0x56AC0 also returns
         * the seed LEVEL byte (delay-slot @0x56AD8 `mov.b @r2,r0`, r2 =
         * 0xFFFFD214, literal @0x56B5C); the handler keeps it in r12
         * (0x585A0 `mov r0,r12`) and passes it as the level to
         * seed_key_related (0x585D4/0x585D6 `mov r12,r4`) and to unlock
         * (0x585E2/0x585E4 `mov r12,r4`). */
        uint8_t level = data_copy(seed);

        /* Re-generate seed to compute expected key (ROM 0x585A2/0x585A4:
         * jsr @0x5699A with r4 = 3 — a side-effect finalization; the key is
         * computed from the PRE-copy seed buffer, as here). */
        seed_gen(3);

        /* Compare user-provided key against expected key.
         * NOTE: seed_key_related returns 0 on match (ROM convention). */
        uint8_t match = seed_key_related(level, seed, &msg[4]);

        if (match == 0) {
            /* Key matches — grant access */
            unlock(level);
            uint8_t ok_resp[2] = { 0x67, subfunc };
            uds_positive_response(SID_SECURITY_ACCESS, ok_resp, 2);
        } else {
            /* Key mismatch */
            uds_error_response(SID_SECURITY_ACCESS, NRC_IK);
        }

    } else {
        /* Unsupported subfunction
         * [REQSEED-EVIDENCE] NOTE: the ROM 0x5862C path for subfunc!=0
         * sends NO response at all (silent); for subfunc==0 it replies via
         * 0x55386.  The NRC_ROR below models the ISO/expected behaviour and
         * is unreachable in the C dispatch for the documented subfunctions. */
        uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
    }
}

/* ===================================================================
 *  2.  state_check1  (ROM 0x56866)
 *
 *  Reads SECURITY_STATE_1 (0xFFFFD20B) and returns its value.
 *  Used to check if diagnostic mode / security is active.
 * =================================================================== */

static uint8_t state_check1(void)
{
    return SECURITY_STATE_1;
}

/* ===================================================================
 *  3.  state_check2  (ROM 0x568E6)
 *
 *  Reads SECURITY_STATE_2 (0xFFFFD20C) and returns its value.
 *  Used to check the current security access sub-state.
 * =================================================================== */

static uint8_t state_check2(void)
{
    return SECURITY_STATE_2;
}

/* ===================================================================
 *  4.  position_check  (ROM 0x56892)
 *
 *  VERIFIED 2026-08-04 — both tables match ROM verbatim (table 4x6 @0x5FA90
 *  with literal @0x56904, word_tab @0x5FA94 literal @0x56908); word_tab[2]
 *  corrected 0x0000 -> 0xFFFC from ROM bytes.
 *  [AUX-CORRECTION] the "mask word 0x61F2 @0x56CB0" is a misread: the
 *  literal at 0x56CB0 is an instruction (0x61F2 = mov.l @r15,r1), and the
 *  ROM loads the mask via a sign-extended 16-bit RAM pointer (lit 0xD3F0
 *  @0x568EC -> 0xFFFFD3F0; mov.w @r1,r6 @0x568C6), not as an immediate —
 *  runtime value [AUX-TBD]; see docs/notes/AUX_HANDLERS_COMPARISON.md
 *  "Correzione mask".
 *  Role: position level check with second-stage mask qualification.
 *
 *  ROM evidence (disasm 0x56892-0x568E4):
 *    - table base = 0x5FA90 (literal @0x56904), stride = i*2 + i*4 = i*6
 *      (shll/shll2/add at 0x5689E-0x568A2), so entries are 6 bytes apart.
 *    - loop index i runs 0..3; entry byte[+1] is compared against r4.
 *    - on match: a second stage ANDs the word at 0x5FA94 + i*6 (literal
 *      @0x56908) with the mask word loaded from RAM via sign-extended 16-bit
 *      pointer (lit 0xD3F0 @0x568EC -> 0xFFFFD3F0; mov.w @r1,r6 @0x568C6;
 *      runtime value [AUX-TBD]); if nonzero -> return i, else -> return 3.
 *      No match at all -> return 3.
 *  The first stage table below is the verbatim ROM bytes (4 entries x 6B).
 *  The current 3x5-byte table used before this fix was a byte-shifted
 *  misreading of the same data.
 *
 *  Returns:
 *    0..2  = matching entry index (second-stage mask bit set)
 *    3     = no match / mask clear (ROM's not-found sentinel)
 * =================================================================== */

static uint8_t position_check(uint8_t level)
{
    /* ROM @0x5FA90 — 4 entries x 6 bytes (stride 6), byte[1] compared. */
    static const uint8_t table[4][6] = {
        { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 },
        { 0x01, 0x01, 0x02, 0x00, 0xFF, 0xFD },
        { 0xF1, 0xF1, 0xF2, 0x00, 0xFF, 0xFC },
        { 0x00, 0x00, 0x00, 0x01, 0x00, 0x01 },
    };
    /* Second stage word table @0x5FA94 (same stride) + mask.  The ROM loads
     * the mask via a sign-extended 16-bit RAM pointer (lit 0xD3F0 @0x568EC
     * -> 0xFFFFD3F0; mov.w @r1,r6 @0x568C6), NOT as an immediate — the word
     * 0x61F2 @0x56CB0 is an instruction (misread).  Mask value is
     * runtime-written RAM: the 0x61F2 constant below is a placeholder
     * [AUX-TBD]; see docs/notes/AUX_HANDLERS_COMPARISON.md "Correzione
     * mask". */
    static const uint16_t word_tab[4] = { 0x0000, 0xFFFD, 0xFFFC, 0x0001 };  /* @0x5FA94+i*6; i=2 -> 0x5FAA0 = 0xFFFC (ROM) */
    static const uint16_t mask       = 0x61F2;

    for (int i = 0; i < 4; i++) {
        if (table[i][1] == level) {
            /* Second stage (ROM 0x568BC-0x568E0): return i only if the
             * per-entry word has a bit in common with the mask. */
            if ((word_tab[i] & mask) != 0)
                return i;
            return 3;
        }
    }
    return 3;  /* not found */
}

/* ===================================================================
 *  5.  seed_gen  (ROM 0x5699A  — old IDA label "random_forest")
 *
 *  Generates the 3-byte seed and writes it to 0xFFFFD211..3.
 *
 *  ROM evidence (disasm 0x5699A-0x56ABE), VERIFIED 2026-08-03 against the
 *  ROM via tools/sh2emu.py — c/tests/test_seed_gen_5699A.py, 0 mismatches
 *  over >= 5000 randomized cases + directed retry-loop cases (levels 0..5,
 *  sentinel @0xFFFFD20B == 4 and != 4).  Semantics per
 *  docs/notes/UDS_SECURITY_MAPPING.md §2:
 *    - level == 3 (the path the RequestSeed handler actually uses):
 *      r13 = r12 = r14 = word @0x56A14 = 0x00FF, then the write-back at
 *      0x56A8C: call 0x3920(0x10); write [0xFFFFD214]=level, [0xFFFFD211]
 *      =0xFF, [0xFFFFD212]=0xFF, [0xFFFFD213]=0xFF; call 0x3934(ret).
 *      => the seed produced by the RequestSeed fast path is FF FF FF.
 *    - level != 3 (entropy path, 0x569C4-0x56A8A):
 *      read 32-bit free-running counter @0xFFFFF430 (mov.l @r2,r6), copy to
 *      4 little-endian stack bytes b0..b3 (shlr8 x3); bsr 0x5687A(r4=4)
 *      returns 0 iff byte @0xFFFFD20B == 4.  state == 4 -> fixed seed
 *      55 AA 55 (r14=0x55, r12=0xAA, r13=0x55); state != 4 -> XOR-mix
 *      r14=b2^b0, r12=b1^b0, r13=b3^b0.  Retry loop 0x56A42-0x56A8A,
 *      max 0x10 (16): all-0/all-FF seeds are re-collected; after 16 retries
 *      the seed falls back to FF FF FF.  Common write-back at 0x56A8C.
 *  The old level-3 "return immediately" stub and the fabricated 64-iteration
 *  LFSR loop have been replaced by the ROM evidence above.
 * =================================================================== */

static void seed_gen(uint8_t level)
{
    uint8_t r14, r12, r13;

    /* --- Level-3 fast path (ROM 0x569B6-0x569C2, 0x56A8C-0x56ABE) --- */
    if (level == 3) {
        /* ROM calls two helpers around the RAM writes:
         *   jsr 0x3920 (r4 = 0x10)   -> getSR, return value kept at [r15+4]
         *   jsr 0x3934 (r4 = ret)    -> setSR (finalize)
         * They manage the SH-2 status register; the RAM writes below are the
         * observable seed/level outputs. */
        r14 = r12 = r13 = 0xFF;
    } else {
        /* --- level != 3: entropy path (ROM 0x569C4-0x56A8A) --- */
        uint8_t state = *(volatile uint8_t *)0xFFFFD20BUL;
        int     retry = 0;

        for (;;) {
            /* 1. counter @0xFFFFF430 as 4 little-endian bytes (ROM 0x569E6-
             *    0x569FC).  Volatile re-read: on the real ECU the counter
             *    free-runs between retries; in the emulator it is static. */
            uint32_t counter = *(volatile uint32_t *)0xFFFFF430UL;
            uint8_t  b0 = (uint8_t)(counter & 0xFF);
            uint8_t  b1 = (uint8_t)((counter >> 8) & 0xFF);
            uint8_t  b2 = (uint8_t)((counter >> 16) & 0xFF);
            uint8_t  b3 = (uint8_t)((counter >> 24) & 0xFF);

            /* 2. bsr 0x5687A(r4=4): 0 iff state sentinel == 4.
             * 3. state == 4 -> fixed 55 AA 55, else XOR-mix (0x56A0C-0x56A40). */
            if (state == 4) {
                r14 = 0x55; r12 = 0xAA; r13 = 0x55;
            } else {
                r14 = b2 ^ b0;
                r12 = b1 ^ b0;
                r13 = b3 ^ b0;
            }

            /* 4. Retry loop (0x56A42-0x56A8A): count at [r15], max 0x10;
             *    after 16 retries (17th recompute) force FF FF FF. */
            retry++;
            if (retry > 16) {
                r14 = r12 = r13 = 0xFF;   /* fallback */
                break;
            }
            if ((r14 == 0 && r12 == 0 && r13 == 0) ||
                (r14 == 0xFF && r12 == 0xFF && r13 == 0xFF))
                continue;                  /* retry: jump back to counter read */
            break;
        }
    }

    /* --- Common write-back (ROM 0x56A8C-0x56ABE) --- */
    *(uint8_t *)0xFFFFD214 = level;   /* ROM 0x56A9A (mov.b r0,@r3) */
    *(uint8_t *)0xFFFFD211 = r14;     /* ROM 0x56A9C (mov.b r14,@r2) */
    *(uint8_t *)0xFFFFD212 = r12;     /* ROM 0x56AA2 (mov.b r12,@r1) */
    *(uint8_t *)0xFFFFD213 = r13;     /* ROM 0x56AA4 (mov.b r13,@r3) */
}

/* ===================================================================
 *  6.  key_validate  (ROM 0x56928 — "prediction")
 *
 *  VERIFIED 2026-08-04 — table extent established from ROM bytes: 10
 *  entries (stride 3) from 0x5FAA2; the loop terminates when b0 >= 5
 *  (the 11th "entry" starts with 0x4D = 'M' of the "MazdA" string at
 *  0x5FAC0).  Literal 0x0005FAA2 confirmed at 0x56A20; helper @0x42B0.
 *
 *  ROM evidence (disasm 0x56928-0x56988):
 *    - table base = 0x5FAA2 (literal @0x56A20); entries are 3-byte triples,
 *      indexed by index*3; a helper (0x42B0) copies each entry locally.
 *    - each entry (b0, b1, b2) is compared against three byte arguments in
 *      r4/r5/r6; the loop iterates while the last entry's b0 < 5.
 *    - returns 0 when a matching entry with b0 < 5 is found, nonzero
 *      otherwise; the caller (0x58546-0x58548) branches to the error path
 *      (NRC 0x31) when the result is nonzero.
 *  NOTE: the return polarity is the OPPOSITE of what this function's old
 *  comment claimed ("1 if a matching entry was found").
 * =================================================================== */

static uint8_t key_validate(uint8_t b0, uint8_t b1, uint8_t b2)
{
    /* Table at 0x5FAA2 — first 5 entries, verbatim ROM bytes.
     * The ROM table continues beyond these 5 entries (b0 < 5 loop bound);
     * extent established from ROM bytes -> VERIFIED. */
    static const uint8_t table[10][3] = {   /* ROM @0x5FAA2, 10 entry, stride 3 */
        { 0x00, 0x00, 0x00 }, { 0x01, 0x00, 0x01 }, { 0x01, 0x01, 0x01 },
        { 0x01, 0x02, 0x00 }, { 0x01, 0x02, 0x01 }, { 0x01, 0x03, 0x00 },
        { 0x02, 0x03, 0x02 }, { 0x02, 0x04, 0x00 }, { 0x01, 0x04, 0x01 },
        { 0x01, 0x05, 0x03 },
    };

    for (int i = 0; i < 10 && table[i][0] < 5; i++) {
        if (table[i][0] == b0 && table[i][1] == b1 && table[i][2] == b2)
            return 0;   /* match with b0 < 5 -> valid (ROM 0x56976, caller errors on nonzero) */
    }
    return 1;           /* no match -> caller raises NRC 0x31 (ROM 0x58574) */
}

/* ===================================================================
 *  7.  data_copy  (ROM 0x56AC0 — "svm_compute")
 *
 *  Copies the 3-byte seed from SEED_RAM_BASE (0xFFFFD211..3) into
 *  the provided output buffer.
 * =================================================================== */

static uint8_t data_copy(uint8_t dst[3])
{
    dst[0] = *(uint8_t *)0xFFFFD211;
    dst[1] = *(uint8_t *)0xFFFFD212;
    dst[2] = *(uint8_t *)0xFFFFD213;
    /* ROM 0x56AC0-0x56AD8: the rts delay-slot @0x56AD8 (`mov.b @r2,r0`, r2 =
     * 0xFFFFD214 loaded @0x56ACC, literal pool @0x56B5C) returns the seed
     * LEVEL byte stored by seed_gen.  The handler keeps it in r12 (0x585A0)
     * and passes it as the level to seed_key_related / unlock. */
    return *(uint8_t *)0xFFFFD214;
}

/* ===================================================================
 *  8.  seed_key_related  (ROM 0x56ADA — "SeedKeyRelated")
 *
 *  The main LFSR-based key transform.  VERIFIED against ROM 60E1D400
 *  (2026-07-31): this C implementation is the direct port of the
 *  bit-identical model in tools/mazda_security.py (ECOMcat), which was
 *  cross-checked against a ROM-disassembly-derived reference emulated
 *  with sh2emu:
 *    - levels 1..4 x seeds {45820A, CBFED4, 123456} : 12/12 keys match
 *    - 400 random seeds (level 1)                   : 0 mismatches
 *    - 3/3 real-world [REDACTED] captures (vendor-family secret)
 *  Stock vector: seed 0x45820A / 'MazdA' / level 1 -> key 0xA07258.
 *  (The legacy vector 0x3B15E1 had no ROM support and was wrong.)
 *
 *  Parameters:
 *    level  — security level; selects the per-level INIT state from the
 *             ROM table at LFSR_PARAM_ADDR (0x5FAC5, 3 bytes/level).
 *    seed   — pointer to 3-byte seed
 *    key    — pointer to 3-byte user-provided key
 *
 *  Returns (ROM convention, verified at the dispatch @0x58538):
 *    0  if the computed key matches the user-provided key
 *    1  otherwise  (caller rejects with NRC 0x31)
 *
 *  Algorithm (24-bit Galois LFSR, ROM code at 0x56B18-0x56C46):
 *    1. Build the 64-bit LSB-first input stream:
 *         byte0..2 = seed, byte3..7 = 5-byte secret ("MazdA")
 *       (== ECOMcat compute_key's w1/w2 packing, which is bit-identical)
 *    2. Initialize state24 from the per-level INIT table entry:
 *         state = entry[0]<<16 | entry[1]<<8 | entry[2]
 *    3. Clock the LFSR 64 times (bits 0..63 of the stream).  The tap
 *       XORs are hardcoded in ROM at 0x56C1E-0x56C38 as xor #8/#32 on the
 *       low byte, xor #16/#128 on the mid byte, xor #16 on the high byte,
 *       plus OR 0x80 feedback into bit 23:
 *         taps = bits {23,20,15,12,5,3} = 0x909028
 *       (identical to ECOMcat; the old 0x28/0x90/0x10 constants here were
 *       fabricated and are removed)
 *    4. Extract the 3 key bytes by nibble interleave:
 *         k0 = ((s1 & 0x0F) << 4) | ((s0 & 0xF0) >> 4)
 *         k1 = (s1 & 0xF0)        | ((s2 & 0xF0) >> 4)
 *         k2 = ((s0 & 0x0F) << 4) |  (s2 & 0x0F)
 *       with s0/s1/s2 = low/mid/high bytes of the final state24.
 * =================================================================== */

static uint32_t lfsr_clock(uint32_t state, uint32_t input_bit)
{
    /* One Galois clock.  feedback = msb of the *shifted-out* LSB of the
     * previous state XOR the input bit; on feedback, bit 23 is set and
     * the tap bits are XORed.  (== ECOMcat _clock) */
    uint32_t feedback = (state & 1) ^ input_bit;
    state >>= 1;
    if (feedback)
        state ^= LFSR_TAPS;      /* 0x909028 = 0x800000|0x100000|0x8000|0x1000|0x20|0x08 */
    return state & 0xFFFFFFUL;
}

static uint8_t seed_key_related(uint8_t level, const uint8_t seed[3],
                                const uint8_t key[3])
{
    /* --- Step 1: 64-bit LSB-first stream = seed + secret --- */
    const uint8_t *secret = (const uint8_t *)SECRET_ADDR;
    uint8_t stream[8];
    stream[0] = seed[0];
    stream[1] = seed[1];
    stream[2] = seed[2];
    memcpy(&stream[3], secret, 5);

    /* --- Step 2: per-level init from ROM table @0x5FAC5 --- */
    const uint8_t *params = (const uint8_t *)LFSR_PARAM_ADDR;
    const uint8_t *entry  = &params[level * 3];
    uint32_t state = ((uint32_t)entry[0] << 16) |
                     ((uint32_t)entry[1] <<  8) |
                     (uint32_t)entry[2];

    /* --- Step 3: 64 Galois clocks, LSB-first --- */
    for (int i = 0; i < 64; i++)
        state = lfsr_clock(state, (stream[i >> 3] >> (i & 7)) & 1);

    /* --- Step 4: nibble-interleave key extraction --- */
    uint8_t s0 = (uint8_t)(state & 0xFF);
    uint8_t s1 = (uint8_t)((state >> 8) & 0xFF);
    uint8_t s2 = (uint8_t)((state >> 16) & 0xFF);

    uint8_t computed[3];
    computed[0] = (uint8_t)(((s1 & 0x0F) << 4) | ((s0 & 0xF0) >> 4));
    computed[1] = (uint8_t)((s1 & 0xF0) | ((s2 & 0xF0) >> 4));
    computed[2] = (uint8_t)(((s0 & 0x0F) << 4) | (s2 & 0x0F));

    /* Return 0 on match (ROM convention — caller rejects on nonzero). */
    if (computed[0] == key[0] && computed[1] == key[1] && computed[2] == key[2])
        return 0;
    return 1;
}

/* ===================================================================
 *  9.  unlock  (ROM 0x56720 — "matrix_transpose")
 *
 *  Grants security access by writing the unlock state and calling
 *  seed_gen to finalize.
 *
 *  Parameters:
 *    level  — the security level to set
 *
 *  ROM flow:
 *    1. Write level byte to 0xFFFFD20C (SECURITY_STATE_2)
 *    2. Call seed_gen(3) — finalizes state
 *    3. Based on level, set specific memory-mapped flags:
 *       level 0: write 0 to 0xFFFFD210, write specific word to 0xFFFFD20E
 *       level 1: write 1 to 0xFFFFD210
 *       level 2: write 2 to 0xFFFFD210
 *       level 3: write 0 to 0xFFFFD20E
 *    4. Call a finalization function (setSR at 0x3934 via literal pool)
 * =================================================================== */

static void unlock(uint8_t level)
{
    /* Step 1: write level to SECURITY_STATE_2 */
    SECURITY_STATE_2 = level;

    /* Step 2: call seed_gen(3) to finalize state */
    seed_gen(3);

    /* Step 3: set unlock flags based on level */
    volatile uint8_t *flag_addr  = (volatile uint8_t *)0xFFFFD210;
    volatile uint16_t *word_addr = (volatile uint16_t *)0xFFFFD20E;

    switch (level) {
    case 0:
        *word_addr = 0xFFF4;  /* from mov.w literal pool */
        *flag_addr = 0;
        break;
    case 1:
        *flag_addr = 1;
        break;
    case 2:
        *flag_addr = 2;
        break;
    case 3:
        *word_addr = 0;
        *flag_addr = 1;
        break;
    default:
        break;
    }

    /* Step 4: Write SECURITY_UNLOCKED flag */
    SECURITY_UNLOCKED = 1;
}
