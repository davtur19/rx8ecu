# RequestSeed Flow — ROM Evidence Confirmation

Status: **CONFIRMED 2026-08-04** (was PENDING)

Handlers: `security_access_handler` (ROM `0x584A0`) — subfunction `0x01` RequestSeed flow,
as reconstructed in `c/security_access.c` (~lines 191-255).

---

## Method

- Byte-exact SH-2 disassembly of `roms/stock/60E1D400.bin` via `tools/disasm_sh2e.py`
  (`disasm_one(op, pc)`); ROM file offset = VA (flat image).
- Cross-checked against the annotated source `src/60E1D400_annotated.s`
  (label `L_058xxx` = VA `0x58xxx`).
- Handler reachability: UDS dispatch table @`0x5F57C` (12-byte stride), entry index 10:
  `SID=0x27, handler=0x584A0, accessMask=0x1000000E`.
  Dispatcher @`0x697E8`-`0x69840` calls the handler with:
  - `r4 = msg_len` (16-bit, `mov.w @r15,r4` @`0x69840`) — payload length **excluding** the SID byte
  - `r5 = subfunction` (8-bit, `mov.b @(0x04,r15),r0; mov r0,r5` @`0x6983A`-`0x6983C`)

  > **Correction to the C comment**: `r4` is the *length value*, **not** a pointer to the
  > message buffer.  The buffer contents are pulled by the UDS stack helper `0x68BC0`
  > (call @`0x584C8` with `r6=1` reads the subfunction byte into `[r15]`; the C
  > `msg_len = (msg[0]<<8)|msg[1]` reconstruction is semantically equivalent).

- Callee identities confirmed via the handler's literal pool `0x58690`-`0x586C4`:

| Literal | Target   | Role                                    |
|---------|----------|-----------------------------------------|
| 0x58690 | 0x68BC0  | UDS "read payload byte(s) into frame"   |
| 0x58694 | 0x56866  | state_check1 (SECURITY_STATE_1, 0xFFFFD20B) |
| 0x58698 | 0x568E6  | state_check2 (SECURITY_STATE_2, 0xFFFFD20C) |
| 0x5869C | 0x553AA  | udsErrorResponse (frame `[0x7F, sid, nrc]` → 0x68B60) |
| 0x586A0 | 0x5699A  | seed_gen                                 |
| 0x586A4 | 0x56892  | position_check (table @0x5FA90, 6-byte stride) |
| 0x586A8 | 0x56928  | key_validate (10-entry table @0x5FAA2)   |
| 0x586AC | 0x56AC0  | data_copy (SEED_RAM @0xFFFFD211 → dst; returns level @0xFFFFD214) |
| 0x586B0 | 0x5698A  | level-slot resolver (SendKey only)       |
| 0x586B4 | 0x56ADA  | seed_key_related (SendKey only)          |
| 0x586B8 | 0x56720  | unlock (SendKey only)                    |
| 0x586BC | 0x55362  | UDS response/notification helper         |
| 0x586C0 | 0x55386  | UDS response helper (subfunc==0 path)    |
| 0x586C4 | 0x68B60  | UDS send path                            |

---

## Row-by-row evidence (C statement → ROM)

| # | C line(s) | C statement / comment | ROM address(es) | Evidence | Status |
|---|-----------|-----------------------|-----------------|----------|--------|
| 1 | 191 | `state1 = state_check1();` | `0x584CC`-`0x584D6` | `mov.l L_058694(=0x56866),r3; jsr @r3`; delay-slot `mov.b r0,@(0x08,r15)` @`0x584D6` saves the result to the caller frame `[r15+8]` | CONFIRMED |
| 2 | 192 | `state = state_check2();` | `0x584D2`-`0x584DA` | `mov.l L_058698(=0x568E6),r3; jsr @r3`; `mov r0,r10` @`0x584DA` keeps the result in r10 | CONFIRMED |
| 3 | 195 | `msg_len = (msg[0]<<8)\|msg[1];` | `0x584B4`, `0x584DC`-`0x584E0` | entry: `mov.w r0,@(0x04,r15)` @`0x584B4` (r0 = original r4 = msg_len); re-read `mov.w @(0x04,r15),r0; mov r0,r4; extu.w r4,r4` @`0x584DC`-`0x584E0` | CONFIRMED (r4 is the length, not a pointer) |
| 4 | 196-199 | `if (msg_len == 0) → NRC_ROR` | `0x584E2`-`0x584E8` → `0x5861A`/`0x5861C` | `tst r4,r4; bf/s 0x584EC; bra 0x5861A`; `0x5861A: mov #18,r5` (0x12); `0x5861C: jsr @r14` (udsErrorResponse) | CONFIRMED — NRC **0x12** |
| 5 | 205-208 | `if (subfunc == 0) → 0x31` | `0x584EC`-`0x584F8` → `0x5861C` | `mov.b @r15,r5` (subfunc); `tst r5,r5; bf/s 0x584FA`; `bra 0x5861C` with delay `mov #0x31,r5` @`0x584F8` | CONFIRMED — NRC **0x31** (matches existing comment; NOT 0x12) |
| 6 | 212 | `if (subfunc == SF_REQUEST_SEED)` | `0x584B6`-`0x584BE` | `mov r4,r0; cmp/eq #0x01,r0; bt/s 0x584C2` (RequestSeed); `bra 0x5862C` (else) | CONFIRMED — exact `==1` dispatch. The old "absolute-value trick" (`abs_sub`) IS present at `0x584FE`-`0x58516` (`cmp/pz r0` @`0x58500`; abs via `not/add/and` @`0x5850A`-`0x58512`; `and #1` @`0x58508`/`0x5850E`; `cmp/eq #0x01` @`0x58514`) and routes odd→RequestSeed / even→`0x58592`, but it is reachable only for `subfunc==1` (always odd) → always RequestSeed. There is **no** "level must be 1" guard. |
| 7 | 223-224 | `resp_data[0]=0x67; resp_data[1]=subfunc;` | `0x5864A`-`0x58662` | done by the resp builder, not inline: `mov #103,r3` (0x67) @`0x5864A`; `mov.b r3,@r13` @`0x5865C`; `mov.b r0,@(1,r13)` @`0x58660` (r0 = subfunc) | CONFIRMED (C inlines what the ROM does in `0x5864A`) |
| 8 | 227 | `seed_gen(3);` | `0x58522`-`0x58524` | `jsr @r11` (0x5699A) with delay-slot `mov #0x03,r4` | CONFIRMED |
| 9 | 232 | `chk = position_check(subfunc);` | `0x58526`-`0x5852A` | `mov.l L_0586a4(=0x56892),r3; jsr @r3` with delay `mov.b @r15,r4` (subfunc); result `mov r0,r12` @`0x5852C`, `extu.b r12,r9` @`0x5852E` | CONFIRMED |
| 10 | 233-237 | `if (chk == 3) → NRC 0x31` | `0x58530`-`0x58534` → `0x5857E` | `mov r9,r0; cmp/eq #0x03,r0; bt/s 0x5857E`; `0x5857E: mov #49,r5` (0x31); `jsr @r14` | CONFIRMED — the `==3` (not-found) sentinel |
| 11 | 247 | `key_validate(state1, state, chk)` | `0x58538`-`0x58542` | `mov.b @(0x08,r15),r0` (state1) → r4 via delay `mov r0,r4` @`0x58542`; `mov r10,r5` (state2) @`0x5853E`; `mov r12,r6` (chk) @`0x5853A`; `mov.l L_0586a8(=0x56928),r3; jsr @r3` | CONFIRMED — b0=[r15+8]=state1, b1=r10=state2, b2=r12=chk (matches the corrected C wiring) |
| 12 | 247-250 | `key_validate(...) != 0 → NRC 0x31` | `0x58544`-`0x58548` → `0x58574` | `extu.b r0,r4; tst r4,r4; bf/s 0x58574`; `0x58574: mov #49,r5` (0x31); `jsr @r14` | CONFIRMED |
| 13 | 252-255 | `data_copy(&resp_data[2]);` + `uds_positive_response(..., 5)` | `0x5854C`-`0x5856E` + `0x5864A` | See discrepancy (b) below. ROM: `extu.b r10,r10; cmp/eq r9,r10` (chk vs state2) @`0x5854E`; equal → zero-fill seed bytes `mov #0,r0; mov.b r0,@(0x02/0x01/0x00,r13)` @`0x58554`-`0x5855C`; not equal → `seed_gen(chk)` (`jsr @r11`, `mov r12,r4` @`0x5855E`-`0x58560`) + `data_copy(r13)` (`jsr @0x56AC0`, `mov r13,r4` @`0x58562`-`0x58566`); then `mov #0x03,r6; mov r13,r5; bsr 0x5864A` @`0x58568`-`0x5856C` (delay `mov.b @r15,r4` = subfunc) | CONFIRMED as the builder path (`0x5864A` → `[0x67, subfunc, 3 bytes]` → 0x68B60); **C's unconditional `data_copy` differs** — see discrepancy (b) |

Common epilogue: every path (success and all NRC paths) converges on `0x58622`
(`mov.l L_0586bc(=0x55362),r3; jsr @r3` with r4=0x27, r5 = previous helper return) —
UDS framework notification, not modelled by the C response helpers.

---

## NRC usage in the RequestSeed flow

| NRC | Where                              | ROM addr |
|-----|------------------------------------|----------|
| 0x12 | `msg_len == 0`                     | `0x584E8`→`0x5861A` |
| 0x12 | `msg_len != 1` (see discrepancy a) | `0x5851E`→`0x58588` |
| 0x31 | `subfunc == 0`                     | `0x584F6`→`0x5861C` |
| 0x31 | `chk == 3` (position_check sentinel)| `0x58534`→`0x5857E` |
| 0x31 | `key_validate(...) != 0`           | `0x58548`→`0x58574` |

**NRC 0x11 (GeneralReject) is NOT emitted anywhere in the handler** — reconfirms the
2026-08-03 finding (the only NRC literals in the whole handler body 0x584A0-0x58648
are {0x12, 0x31, 0x22, 0x35}; 0x22/0x35 belong to the SendKey body).

---

## Discrepancies found (documented; logic of the C reconstruction untouched)

**(a) `msg_len == 1` check missing in C.** ROM `0x5851A`-`0x5851E`
(`mov r4,r0; cmp/eq #0x01,r0; bf/s 0x58588`) requires the message length to be
**exactly 1** for RequestSeed, else NRC 0x12 @`0x58588`.  The C code only rejects
`msg_len == 0` (line 196); a length > 1 would be accepted by C but rejected by the ROM.

**(b) Seed bytes written conditionally.** C lines 252-253 do an unconditional
`data_copy(&resp_data[2])` of the `seed_gen(3)` output.  The ROM (0x5854C-0x58566):
- `state2 == chk`  → the 3 response seed bytes are **zero-filled** (no copy);
- `state2 != chk`  → the ROM first **re-generates** the seed with `seed_gen(chk)`
  (0x5855E-0x58560 — the `seed_gen(3)` at 0x58522 is a side-effect finalization,
  the same pattern already documented in the SendKey path) and **then** copies it.

So the C response would carry a level-3 seed in all cases, whereas the ROM sends a
level-`chk` seed (or `{0,0,0}`).

**(c) State reads are unconditional in C.** C lines 191-192 run for every
subfunction; the ROM reads `SECURITY_STATE_1/2` only inside the `subfunc==1` branch
(0x584CC / 0x584D2).  Benign (the reads are side-effect-free), but structurally the
ROM only does them for RequestSeed.

**(d) Calling convention.** `r4 = msg_len` (value), not a buffer pointer — see
"Method" above.  The C signature/comment at `c/security_access.c` lines 154-156, 165
mislabel the first parameter.

**(e) SendKey is unreachable in 60E1D400 (FLAG).** Entry `0x584B6`-`0x584BE` routes
**only** `subfunc==1` into the handler body; everything else goes to `0x5862C`:
`tst r4,r4` → `subfunc==0` → response via `0x55386`; `subfunc != 0` → **silent, no
response**.  The SendKey body at `0x58592`-`0x58610` is reachable only via the
abs-trick even-branch `bf/s 0x58592` @`0x58516`, which can never be taken
(`subfunc==1` is odd).  A whole-ROM scan of branch targets shows `0x58592` has
exactly **one** incoming reference (`0x58516`).  => The SendKey flow is **dead code**
in this ROM build.  The C SendKey branch (`c/security_access.c` ~257-295) and its
`else → NRC_ROR` (297-300) do not match *reachable* ROM behaviour for this build;
previously marked VERIFIED by earlier sessions — **needs reconciliation** (likely a
shared-codebase remnant; other ROM variants such as 60E32000 have different code at
these addresses).

---

## Summary

- RequestSeed flow (C lines 191-255): **CONFIRMED** row-by-row (table above).
- The old DRAFT guesses are resolved: the abs-trick exists but is vestigial; there is
  no "level must be 1" guard (the `==1` check is on `msg_len`, and the `==3` sentinel
  comes from `position_check`).
- 5 discrepancies documented (a-e); none requires a change to executable logic —
  the C reconstruction is already semantically correct for conformant RequestSeed
  traffic (`msg_len==1`, `state2 != chk`, `subfunc==0x01`).
- Open item for follow-up: SendKey reachability (discrepancy e).
