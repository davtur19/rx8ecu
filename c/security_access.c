/**
 * security_access.c — UDS Service 0x27 (SecurityAccess) handler
 *
 * ═══════════════════════════════════════════════════════════════════
 *  STATUS: DRAFT / UNVERIFIED structural reconstruction.
 *
 *  IMPORTANT — READ FIRST:
 *   * The seed↔key TRANSFORM core (seed_key_related) has been corrected to
 *     match the stock ROM 60E1D400 algorithm and is VERIFIED (see the
 *     evidence block in seed_key_related).  For stock ECUs, use
 *     tools/mazda_security.py (ECOMcat) — it is bit-equivalent to the ROM
 *     at level 1 and reproduces all ROM-emulated reference vectors.
 *   * The surrounding UDS handler FLOW (dispatch, subfunctions, seed
 *     generation, state checks, tables) remains a partially-guessed
 *     structural mapping of the ROM: function boundaries, argument orders
 *     and the tables' exact roles are NOT all confirmed.  Parts marked
 *     "DRAFT" below must not be trusted.
 *   * This file must NOT be used to answer real security-access requests
 *     on a stock ECU until the DRAFT parts are confirmed against the ROM
 *     (and, ideally, real captures).
 *   * docs/notes/RESUME.md lists the stock LFSR as an open issue; that
 *     entry is now out of date (the LFSR core was solved 2026-07-31 —
 *     see tools/mazda_security.py docstring).
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
 *   - docs/notes/RESUME.md (note: its "stock LFSR open issue" entry is now
 *     out of date — the LFSR core is solved)
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
static void     data_copy(uint8_t dst[3]);
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
 *  Called from udsHandler dispatch with:
 *    r4 = pointer to incoming UDS message buffer
 *    r5 = subfunction byte
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
    uint8_t  resp_data[4];
    uint8_t  state;

    /* --- NRC 0x11 check: is diagnostic mode active? ---
     * DRAFT: the old code guessed "if state_check1() != 0 -> return NRC_GR".
     * The ROM's exact guard conditions at the entry of 0x584A0 are not
     * confirmed; keep the check but flag it as unverified. */
    if (state_check1() != 0) {
        uds_error_response(SID_SECURITY_ACCESS, NRC_GR);
        return;
    }

    /* --- Validate message length --- */
    uint16_t msg_len = (msg[0] << 8) | msg[1];
    if (msg_len == 0) {
        uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
        return;
    }

    /* --- Validate subfunction --- */
    if (subfunc == 0) {
        uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
        return;
    }

    /* --- Subfunction dispatch --- */
    state = state_check2();

    if (subfunc == SF_REQUEST_SEED) {
        /* ---- Subfunction 0x01: RequestSeed ---- */

        /* DRAFT: the old "absolute-value trick" (abs_sub) and the
         * "level must be 1" guard were guesses; the outer subfunc check
         * above already guarantees 0x01 here.  Remaining flow is a
         * structural mapping of ROM 0x584A0, not confirmed in detail. */

        /* Level 1: set up response length + generate seed */
        resp_data[0] = 0x67;           /* SID | 0x40 = 0x67 */
        resp_data[1] = subfunc;        /* echo subfunction */

        /* Generate the 3-byte seed using LFSR level 3 */
        seed_gen(3);

        /* Validate the generated level via position_check */
        uint8_t chk = position_check(subfunc);
        if (chk == 3) {
            /* Level validation failed */
            uds_error_response(SID_SECURITY_ACCESS, NRC_ROR);
            return;
        }

        /* State/position cross-check — ROM 0x58538 calls key_validate with
         * three byte values (state byte, r10 value, position_check result)
         * and rejects with NRC 0x31 on a nonzero return.  The source of the
         * middle byte (ROM r10, a result of the helper called at 0x584D4)
         * is not confirmed, so this wiring is DRAFT: */
        if (key_validate(state, subfunc, chk) != 0) {
            uds_error_response(SID_SECURITY_ACCESS, 0x31);
            return;
        }

        /* Copy generated seed to response buffer */
        data_copy(&resp_data[2]);

        uds_positive_response(SID_SECURITY_ACCESS, resp_data, 5);

    } else if (subfunc == SF_SEND_KEY) {
        /* ---- Subfunction 0x04: SendKey ---- */

        /* Retrieve the cached seed data */
        data_copy(seed);

        /* Re-generate seed to compute expected key */
        seed_gen(3);

        /* Compare user-provided key against expected key.
         * NOTE: seed_key_related returns 0 on match (ROM convention). */
        uint8_t match = seed_key_related(4, seed, &msg[4]);

        if (match == 0) {
            /* Key matches — grant access */
            unlock(state);
            uint8_t ok_resp[2] = { 0x67, subfunc };
            uds_positive_response(SID_SECURITY_ACCESS, ok_resp, 2);
        } else {
            /* Key mismatch */
            uds_error_response(SID_SECURITY_ACCESS, NRC_IK);
        }

    } else {
        /* Unsupported subfunction */
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
 *  DRAFT — structure corrected to ROM, exact role partially understood.
 *
 *  ROM evidence (disasm 0x56892-0x568E4):
 *    - table base = 0x5FA90 (literal @0x56904), stride = i*2 + i*4 = i*6
 *      (shll/shll2/add at 0x5689E-0x568A2), so entries are 6 bytes apart.
 *    - loop index i runs 0..3; entry byte[+1] is compared against r4.
 *    - on match: a second stage ANDs the word at 0x5FA94 + i*6 (literal
 *      @0x56908) with the mask 0x61F2 (word @0x56CB0); if nonzero -> return
 *      i, else -> return 3.  No match at all -> return 3.
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
    /* Second stage word table @0x5FA94 (same stride) and mask @0x56CB0. */
    static const uint16_t word_tab[4] = { 0x0000, 0xFFFD, 0x0000, 0x0001 };
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
 *  5.  seed_gen  (ROM 0x5699A  — "random_forest")
 *
 *  Generates the 3-byte seed and writes it to 0xFFFFD211..3.
 *
 *  ROM evidence (disasm 0x5699A-0x56ABE):
 *    - level == 3 (the path the RequestSeed handler actually uses):
 *      r13 = r12 = r14 = word @0x56A14 = 0x00FF, then the write-back at
 *      0x56A8C: call 0x3920(0x10); write [0xFFFFD214]=level, [0xFFFFD211]
 *      =0xFF, [0xFFFFD212]=0xFF, [0xFFFFD213]=0xFF; call 0x3934(ret).
 *      => the seed produced by the RequestSeed fast path is FF FF FF.
 *    - level != 3: reads a 32-bit value @0xFFF430 (literal 0x56A16), stores
 *      4 bytes, calls 0x5687A(4) (state check), then runs a byte-shift loop
 *      (0x56A42-0x56A8A) with counters 0x55/0x10 — entropy collection.
 *      This path is only partially traced -> DRAFT.
 *  The old level-3 "return immediately" stub and the fabricated 64-iteration
 *  LFSR loop have been replaced by the ROM evidence above.
 * =================================================================== */

static void seed_gen(uint8_t level)
{
    /* --- Level-3 fast path (ROM 0x569B6-0x569C2, 0x56A8C-0x56ABE) --- */
    if (level == 3) {
        /* DRAFT: the ROM calls two helpers around the RAM writes:
         *   jsr 0x3920 (r4 = 0x10)   -> return value stored
         *   jsr 0x3934 (r4 = ret)    -> finalize
         * Their exact roles are not confirmed; the RAM writes below are. */
        *(uint8_t *)0xFFFFD214 = level;   /* ROM 0x56A9A (mov.b r0,@r3) */
        *(uint8_t *)0xFFFFD211 = 0xFF;    /* ROM 0x56A9C (r14 = 0x00FF) */
        *(uint8_t *)0xFFFFD212 = 0xFF;    /* ROM 0x56AA2 (r12 = 0x00FF) */
        *(uint8_t *)0xFFFFD213 = 0xFF;    /* ROM 0x56AA4 (r13 = 0x00FF) */
        return;
    }

    /* --- level != 3: entropy-collection path (DRAFT, partially traced) ---
     * ROM 0x569E6: r6 = *(uint32_t*)0xFFF430  (32-bit free-running counter)
     * ROM 0x569F0-0x569FC: store 4 bytes of r6 (shifted right by 8 each
     *   iteration) into a stack buffer.
     * ROM 0x56A00: bsr 0x5687A with r4 = 4 (state_check1-like helper).
     * ROM 0x56A42-0x56A8A: byte-shift loop with counters r10=0x55/r11=0x10
     *   and retry when the shifted-out bytes are all zero.
     * The exact byte-shift / feedback equations of this path are NOT fully
     * established; do not rely on this code for seed generation.
     */
    volatile uint32_t *entropy_ptr = (volatile uint32_t *)0xFFFFF430UL;
    (void)entropy_ptr;
    (void)level;   /* DRAFT: incomplete — see comment above */
    return;
}

/* ===================================================================
 *  6.  key_validate  (ROM 0x56928 — "prediction")
 *
 *  DRAFT — table corrected to ROM bytes; exact call semantics partially
 *  understood.
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
     * the full extent is not established -> DRAFT. */
    static const uint8_t table[5][3] = {
        { 0x00, 0x00, 0x00 },   /* ROM @0x5FAA2 */
        { 0x01, 0x00, 0x01 },
        { 0x01, 0x01, 0x01 },
        { 0x01, 0x02, 0x00 },
        { 0x01, 0x02, 0x01 },
    };

    for (int i = 0; i < 5; i++) {
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

static void data_copy(uint8_t dst[3])
{
    dst[0] = *(uint8_t *)0xFFFFD211;
    dst[1] = *(uint8_t *)0xFFFFD212;
    dst[2] = *(uint8_t *)0xFFFFD213;
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
