# SecurityAccess Handler (UDS Service 0x27)

**Handler address (60E1D400.bin):** `0x584A0`  
**Handler size:** ~426 bytes (from prologue at 0x584A0 to RTS at 0x58646)  
**UDS dispatch table entry:** `SID=0x27, handler=0x584A0, accessMask=0x1000000E`  
**Symbol names:** `Srv27_SecurityAccess` (Ghidra), `security_access_0x52180` (IDA-AI)  

## Overview

ISO 14229 UDS Service 0x27 (SecurityAccess) for the Mazda RX-8 PCM. Controls access
to privileged diagnostics (flashing, calibration, immobilizer programming) via a
seed/key challenge-response protocol.

Subfunction `0x01` (RequestSeed): ECU returns a pseudo-random 3-byte **seed**. The
tool computes a 3-byte **key** with a 24-bit Galois LFSR + shared secret and sends
it via subfunction `0x04` (SendKey). On match the ECU unlocks security.

## Call Tree

```
udsHandler (0x697E8)
  └─ dispatches via table @ 0x5F57C, stride=12
       └─ SID 0x27 → security_access_handler @ 0x584A0
            ├─ subfunc 0x01 (RequestSeed)
            │    ├─ state_check1 @ 0x56866      — reads 0xFFFFD20B
            │    ├─ state_check2 @ 0x568E6      — reads 0xFFFFD20C
            │    ├─ seed_gen @ 0x5699A           — generates 3-byte seed
            │    │    └─ lfsr_clock_core         — [inline] 64-round LFSR
            │    ├─ position_check @ 0x56892     — validates level via table @ 0x5FA90
            │    ├─ key_validate @ 0x56928       — pre-computes expected key, search table @ 0x5FAA2
            │    └─ data_copy @ 0x56AC0          — copies seed from RAM @ 0xFFFFD211
            │
             ├─ subfunc 0x04 (SendKey)  ⚠ UNREACHABLE in 60E1D400 (2026-08-04)
             │    ├─ data_copy @ 0x56AC0          — retrieve cached seed
             │    ├─ seed_gen @ 0x5699A           — re-generate seed (same level)
             │    ├─ seed_key_related @ 0x56ADA   — LFSR key validation (64 rounds)
             │    │    ├─ byte_shift_core         — 8-byte shift with carry propagation
             │    │    ├─ lfsr_state_update        — 3-byte LFSR XOR with taps
             │    │    └─ nibble_swap_output       — final key byte permutation
             │    └─ unlock @ 0x56720             — grant access on match
             │
             └─ subfunc != 1 → 0x5862C: subfunc==0 → resp via 0x55386;
                subfunc!=0 → NO response (silent)   [not NRC 0x12]
```

## UDS Dispatch Table Entry

At `0x5F57C + 10*12 = 0x5F5A4`:

```
Offset  Bytes     Field          Value         Description
------  -------- -------------- ------------- ---------------------------
 0      27        SID            0x27          SecurityAccess service ID
 1-3    00 00 00  (reserved)     0x000000      Padding / alignment
 4-7    00 05 84 A0  HandlerAddr 0x000584A0    Function pointer (big-endian)
 8-11   10 00 00 0E  AccessMask  0x1000000E    Session filter
```

The access mask `0x1000000E` allows sessions 2 (programming), 3 (extended), and
4 (safety).  Bit 28 (`0x10000000`) is a `seed_already_generated` flag — when set
the handler skips the session check on the SendKey path.

## Secret & LFSR Parameters

### Location

The shared secret and LFSR parameters are stored at a ROM offset that varies
across firmware builds (see table below).  The structure is identical in all
known stock ROMs:

```
Offset        Size  Content
------------- ----  -----------------------------------------------------
secret+0      5     ASCII shared secret (e.g. "MazdA")
secret+5      3     0xFF padding
secret+8      3     LFSR init value  (3 bytes, byte[2]=MSB → 24-bit)
secret+11     3     LFSR tap bits    (3 bytes, byte[2]=MSB → 24-bit)
```

### Per-ROM Secret Locations

| ROM ID         | Secret Offset | Secret   | Notes                       |
|----------------|---------------|----------|-----------------------------|
| 60E0E500       | 0x05E460      | `MazdA`  | Stock                       |
| 60E0E700_N3YLEE| 0x05E6B8      | `MazdA`  | Stock                       |
| 60E0FB00       | 0x05D90C      | `MazdA`  | Stock                       |
| 60E0FC00       | 0x05D90C      | `MazdA`  | Stock, equinox's RE target  |
| 60E15120_N3J1E | 0x05F084      | `MazdA`  | Stock                       |
| 60E1B900       | 0x05DBA4      | `MazdA`  | Stock                       |
| 60E1C500_N3J6EB| 0x05E730      | `MazdA`  | Stock                       |
| **60E1D400**   | **0x05FAC0**  | `MazdA`  | **This ROM**                |
| 60E32000_N3M5E | 0x065134      | `MazdA`  | Structurally distinct       |

### LFSR Parameter Values (ROM 60E1D400)

```
Address   Bytes             24-bit Value    Interpretation
--------  ----------------- --------------  ------------------------------
0x5FAC0   4D 61 7A 64 41    —               Secret = "MazdA"
0x5FAC5   FF FF FF          —               Padding / level-0 sentinel
0x5FAC8   C5 41 A9          0xC541A9        LFSR init (level 1) — == ECOMcat init
0x5FACB   A3 95 82          0xA39582        LFSR init (level 2) — NOT taps!
0x5FACE   FF FF 00          —               LFSR init (level 3/4) padding + table tail
```

**Important:** `0x5FAC5` is a **per-level LFSR INIT table**, indexed `base + level*3`
(3 bytes/level). Init read in address order (`entry[0]` = MSB); level 1 `C5 41 A9`
→ `0xC541A9`. Taps are **not** in this table — **hardcoded** in ROM code inside
`SeedKeyRelated` @0x56ADA (XOR constants 0x56C1E–0x56C38), bits {23,20,15,12,5,3}
= **0x909028**, identical to ECOMcat.

**RESOLVED (2026-08-01, commit `a84eaba`, emulator-verified):** stock LFSR **is**
the ECOMcat/Craig-Smith 24-bit Galois algorithm. Legacy vector `0x3B15E1` was
wrong; ROM-verified key for seed `0x45820A` / `"MazdA"` / level 1 is **`0xA07258`**
(levels 1–4 × 3 seeds validated vs `SeedKeyRelated` @0x56ADA). Remaining unknowns:
subfunction→level mapping, `seed_gen` internals for level≠3, `key_validate`
middle-byte source.

## LFSR Algorithm

### Existing Reference (mazda_security.py)

The known reference implements a 24-bit Galois LFSR:

```
State:  24-bit shift register (0xC541A9 init)
Taps:   0x909028 (bits 23,20,15,12,5,3)
Clocks: 64 total (32 for w1 + 32 for w2)
Input:  Two 32-bit words formed from secret + seed
Output: 3-byte key via nibble permutation
```

Phase 1 — `w1 = (s1 << 24) | (seed[0] << 16) | (seed[1] << 8) | seed[2]`  
Phase 2 — `w2 = (s5 << 24) | (s4 << 16) | (s3 << 8) | s2`

The final key bytes are extracted from the 24-bit state as:

```
key[0] = ((state >> 16) & 0x0F) | ((state & 0x0F) << 4)   ← nibble swap
key[1] = ((state >> 20) & 0x0F) | ((state >> 12) & 0x0F) << 4
key[2] = (state >> 4) & 0xFF
Result: byteswap(key) → [key[2], key[1], key[0]]
```

### ROM Implementation (SeedKeyRelated @ 0x56ADA)

The ROM's `SeedKeyRelated` is a byte-oriented implementation of the **same** ECOMcat
24-bit Galois LFSR (RESOLVED 2026-08-01, commit `a84eaba`): byte-wise 8-byte shift
+ 3-byte state shift, taps hardcoded at 0x56C1E–0x56C38 (bits {23,20,15,12,5,3} =
0x909028), `tools/mazda_security.py` bit-equivalent at level 1:

1. **8-byte buffer** = 3 seed bytes + 5 secret bytes  
2. **Three 24-bit states** (loaded from the per-level init table @0x5FAC5)
   stored in `r13/r9/r11`  
3. **64 rounds**, each round consisting of:
   - **8-byte right-shift** with carry propagation (byte-wise circular shift)
   - **3-byte LFSR state** right-shift with carry
   - Conditional XOR of state bytes with tap constants (`0x28`, `0x90`, `0x10` —
     the byte-wise view of taps `0x909028`)  
4. **Final comparison**: the processed buffer's high nibbles are compared against
   the user-provided key bytes

## Subfunction Handling

### Subfunction 0x01 — RequestSeed

> CONFIRMED 2026-08-04 — see `docs/notes/UDS_SECURITY_MAPPING.md §7.1` for the
> row-by-row ROM evidence. Corrections to the previous DRAFT:

1. Read `SECURITY_STATE_1` (0xFFFFD20B, state_check1 @0x56866) and
   `SECURITY_STATE_2` (0xFFFFD20C, state_check2 @0x568E6) — reads only, **no** NRC
   gate (no NRC 0x11 anywhere in the handler; the previous "already unlocked →
   0x11" claim was wrong)
2. Validate message length: `msg_len == 0` → NRC 0x12; `msg_len != 1` → NRC 0x12
   (length is the payload length excluding the SID byte; passed in r4, not a pointer)
3. Validate subfunction ≠ 0 → NRC 0x31 (not 0x12)
4. Dispatch: only `subfunc == 0x01` enters this flow (entry `0x584B6`-`0x584BE`);
   the abs-trick at 0x584FE-0x58516 is present but vestigial for subfunc 0x01
5. Generate 3-byte seed via `seed_gen(3)` (ROM 0x58522) — side-effect finalization
6. Validate seed level via `position_check(subfunction)` (0x56892);
   sentinel `chk == 3` → NRC 0x31
7. Cross-check via `key_validate(state1, state2, chk)` (0x56928);
   non-zero result → NRC 0x31
8. Seed bytes written conditionally: `state2 == chk` → `{0,0,0}`; else
   `seed_gen(chk)` + `data_copy` (0x56AC0) into the response seed slot
9. Send positive response via resp builder 0x5864A: `[0x67, 0x01, seed0, seed1, seed2]`

### Subfunction 0x04 — SendKey

> **RESOLVED 2026-08-04 — verdict (b): dead code in ALL 9 public stock ROMs.**
> Cross-ROM scan (`docs/notes/UDS_SECURITY_MAPPING.md §7.3`): body present with
> identical structure in every stock image (60E1D400 `0x58592`-`0x58610`;
> 60E0E500 `0x56F3E`, 60E0E700 `0x57196`, 60E0FB00/60E0FC00 `0x56026`,
> 60E15120 `0x57B56`, 60E1B900 `0x562BE`, 60E1C500 `0x57202`, 60E32000
> `0x5D4D2`) but unreachable everywhere: entry dispatch admits only `subfunc==1`;
> the sole incoming branch is the never-taken abs-trick even-branch `bf/s`
> (`subfunc==1` is odd); no indirect refs. `subfunc!=1` → else path:
> `subfunc==0` → response, `subfunc!=0` → silent. Flow below kept as ROM-accurate
> reconstruction of a shared-codebase remnant (no removal).

1. Retrieve cached seed via `data_copy`
2. Re-generate seed via `seed_gen(3)`
3. Compare user-provided key against computed key via `seed_key_related(4, seed, key)`
4. On match: call `unlock(level)`, send positive response `[0x67, 0x04]`
5. On mismatch: send NRC 0x35 (InvalidKey)

### Negative Response Codes (NRC)

NRCs emitted by the handler body 0x584A0-0x58648 (whole-body literal scan):
**{0x12, 0x31, 0x22, 0x35}**. 0x11/0x33/0x36/0x37 are **not** emitted (0x11 was
wrongly claimed for "already unlocked"; the state reads gate nothing).

| NRC  | Meaning                        | Condition                                   |
|------|--------------------------------|---------------------------------------------|
| 0x12 | RequestOutOfRange              | msg_len == 0 or msg_len != 1 (RequestSeed) / msg_len != 4 (SendKey body) |
| 0x31 | RequestOutOfRange              | subfunc == 0, position_check sentinel (chk==3), key_validate != 0 |
| 0x22 | ConditionsNotCorrect           | SendKey body: seed level == 3, level mismatch |
| 0x35 | InvalidKey                     | SendKey body: computed key ≠ user key       |
| 0x11 | GeneralReject                  | NOT used by this handler (ISO-14229 spec only) |
| 0x33 | SecurityAccessDenied           | NOT used by this handler (ISO-14229 spec only) |
| 0x36 | ExceededNumberOfAttempts       | NOT used by this handler (ISO-14229 spec only) |
| 0x37 | RequiredTimeDelayNotExpired    | NOT used by this handler (ISO-14229 spec only) |

## RAM State Map

The SecurityAccess handler uses these RAM locations for state:

| Address      | Size | Name               | Description                             |
|--------------|------|--------------------|-----------------------------------------|
| 0xFFFFD20B   | 1    | SECURITY_STATE_1   | Non-zero = security already unlocked    |
| 0xFFFFD20C   | 1    | SECURITY_STATE_2   | Current security sub-state              |
| 0xFFFFD20E   | 2    | SECURITY_WORD      | Unlock word (written by unlock())       |
| 0xFFFFD210   | 1    | SECURITY_FLAG      | Unlock flag (0/1/2)                     |
| 0xFFFFD211   | 3    | SEED_DATA          | Generated seed bytes                    |
| 0xFFFFD214   | 3    | SEED_WORKING       | LFSR working state                      |
| 0xFFFFD0F2   | 1    | SECURITY_UNLOCKED  | Final unlock flag (1 = unlocked)        |
| 0xFFFFD0F3   | 1    | SECURITY_FLAGS     | Additional security flags               |

## Verification Status

| Component               | Status     | Notes                                    |
|-------------------------|------------|------------------------------------------|
| Handler dispatch        | Confirmed  | ROM table @ 0x5F57C, handler @ 0x584A0  |
| Subfunction dispatch    | Confirmed  | RFE/SUB matches ISO 14229                |
| Secret location         | Confirmed  | "MazdA" @ 0x5FAC0 (this ROM)            |
| LFSR init table         | Confirmed  | @ 0x5FAC5, per-level INIT, 3 bytes/level |
| Seed/key transform      | Verified   | 2026-07-31 — ECOMcat 24-bit Galois; vector 0xA07258 emulator-verified (level 1) |
| Seed generation         | Verified   | 2026-08-03 — `c/tests/test_seed_gen_5699A.py`, 0 mismatches (levels 0..5, retry-loop) |
| position_check          | Verified   | 2026-08-04 — word_tab[2]=0xFFFC; commit `b483523` |
| key_validate            | Verified   | 2026-08-04 — 10-entry table @0x5FAA2; commit `b483523` |
| seed_key_related/lfsr   | Verified   | 2026-07-31 — 12/12 keys + 400 random seeds |
| mazda_security.py       | Confirmed  | `tools/mazda_security.py` — bit-equivalent to ROM at level 1 |
| RequestSeed flow        | Confirmed  | 2026-08-04 — `docs/notes/UDS_SECURITY_MAPPING.md §7.1` (row-by-row; entry dispatch, msg_len==1, conditional seed path) |
| C reconstruction        | Confirmed  | Core VERIFIED + RequestSeed CONFIRMED 2026-08-04; SendKey reachability **RESOLVED 2026-08-04** — dead code in all 9 public stock ROMs (see below) |

**Open questions (core RESOLVED; no remaining items):**
1. ~~**subfunction→level mapping**~~ **RESOLVED** — `seed_gen` always called with
   fixed level 3; the controlling level is the `position_check` table index from
   the RequestSeed payload byte (`docs/notes/UDS_SECURITY_MAPPING.md` §1).
2. ~~**`seed_gen` (@0x5699A) internals for level≠3**~~ **RESOLVED** — entropy path
   (XOR-mix `b0^bN`, state==4 → `55AA55`, retry<=16 fallback `FFFFFF`) VERIFIED
   2026-08-03 via `c/tests/test_seed_gen_5699A.py` (0 mismatches). `c/security_access.c` §5.
3. ~~**`key_validate` middle-byte source**~~ **RESOLVED** — middle arg is
   **`SECURITY_STATE_2`** (state_check2 @0x568E6), held in r10; handler calls
   `key_validate(state1, state, chk)` (`c/security_access.c` ~232-240; commits
   `8e259f8`, `b483523`).

**RESOLVED 2026-08-04 — SendKey reachability:** **SendKey body is dead code in all
9 public stock ROMs** (60E1D400 + 8 aux). Cross-ROM scan (entry dispatch, incoming
branches, indirect refs): body present but unreachable everywhere — dispatch admits
only `subfunc==1`; only incoming branch is the never-taken abs-trick `bf/s`. The
earlier VERIFIED SendKey work (commits `fd56201`, `31bb0ac`) covered the algorithm
vs the ROM body, not dispatch reachability. Verdict (b): dead code, shared-codebase
remnant — kept in the C reconstruction, no removal. See
`docs/notes/UDS_SECURITY_MAPPING.md §7.3` (ROM-by-ROM table, per-ROM branch addrs)
and §7.1 discrepancy (e) for the original 60E1D400 finding.

## References

1. `tools/mazda_security.py` — ECOMcat-derived LFSR implementation
2. `c/security_access.c` — Structural C reconstruction
3. `c/tests/test_security_access.py` — Test suite with ROM cross-checks
4. `docs/notes/FINDINGS.md` — UDS dispatch table and security analysis
5. `c/can_uds_subsystem.c` — UDS subsystem container
6. ISO 14229-1:2020 — Road vehicles — Unified diagnostic services (UDS)
7. Craig Smith, "Car Hacker's Handbook" — Seed/key LFSR reference
8. `60E1D400.bin` @ 0x584A0 — SecurityAccess handler (`roms/stock/`)
9. `60E1D400.bin` @ 0x5FAC0 — Secret and LFSR parameter table
10. `60E1D400_annotated.s` lines 221647–222120 — SeedKeyRelated function
