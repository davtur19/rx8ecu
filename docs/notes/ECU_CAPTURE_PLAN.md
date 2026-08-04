# ECU Capture Plan — UDS 0x27 handler (60E1D400 baseline)

Status: **PLAN (not executed)** · date 2026-08-04

References:
- `docs/notes/REQUEST_SEED_EVIDENCE.md` — RequestSeed row-by-row ROM evidence (CONFIRMED 2026-08-04)
- `docs/notes/SENDKEY_RECONCILIATION.md` — SendKey cross-ROM reachability verdict (b): dead code in all 9 stock images (RESOLVED 2026-08-04)

Scope: live, on-ECU validation (real stock ECU) of the ROM-derived behaviour of the
UDS security-access handler for SID 0x27 — in particular that subfunction `0x04`
(SendKey) produces **silence / no response** and that the SendKey flow **never
executes**. Companion doc to the two static-evidence notes above; this plan
documents *how* to confirm at runtime what they already prove in ROM.

---

## 1. Goal

Confirm at runtime, on a stock Mazda RX-8 ECU, that the SID 0x27 handler
(`security_access_handler` @ `0x584A0`, UDS dispatch table @ `0x5F57C` entry idx 10,
accessMask `0x1000000E`, dispatcher `0x697E8`-`0x69840`) behaves exactly as the ROM
evidence says:

(a) RequestSeed (subfunc `0x01`) answers as per REQUEST_SEED_EVIDENCE: positive
    response `[0x67, subfunc, 3 seed bytes]` (response builder `0x5864A` → send
    path `0x68B60`), with NRC set {0x12, 0x31} for the malformed / not-found cases.
(b) subfunc `0x04` (SendKey) → **silence** (no response frame on 0x7E8), i.e. the
    SendKey flow (`0x58592`-`0x58610`) never executes — the SENDKEY_RECONCILIATION
    verdict (b) at runtime.
(c) The msg_len gates behave as in ROM: `msg_len==0` → NRC `0x12` (`0x584E8`);
    `msg_len==1` is required for RequestSeed (else NRC `0x12` @ `0x58588` —
    discrepancy a); the SendKey body's `msg_len==4` gate (`cmp/eq #4` @ `0x58592`)
    is never even reached.

## 2. Hardware / setup

Diagnostic technology (from repo evidence):

- **UDS over HS-CAN** (CAN_PROTOCOL.md): HS-CAN OBD-II pins 6/14; bench connector
  pins **4S = CAN-L, 4V = CAN-H**. Tester request IDs `0x7E0` (physical, MB14) /
  `0x7DF` (broadcast, MB13); response `0x7E8` (MB15, buffer `0x0DE0C`).
- **No K-line / ISO 14230 evidence anywhere in the repo** — the RX-8 diagnostic
  bus is CAN-only per CAN_PROTOCOL.md; K-line paths are not expected. If a K-line
  adapter is considered anyway, that sub-setup is **[TBD]**.

Required:

- **Stock ECU**: Mazda RX-8 SH7055-based unit (IC430 per HARDWARE.md, N3J1 6-port
  MT); the ROM under test is the baseline `60E1D400` (flat image, file offset ==
  virtual address — REQUEST_SEED_EVIDENCE / SENDKEY_RECONCILIATION method sections).
- **Bench power-up (no car)** — fully documented in CONNECTOR_PINOUT.md and
  DUMP_ALL.md:
  - GND: pins **4A, 4J, 5D, 5O, 5R, 5T** → bench supply GND
  - +12V: pins **5AC, 5AF** (main-relay rail — feed directly, bypassing the relay),
    **4Q** (ignition switched), **5J** (constant power)
  - CAN: **4S** (L) / **4V** (H) → CAN interface
  - Do **not** drive **4E** (Main Relay enable — it is an ECU *output*)
- **CAN interface**: J2534 adapter (DUMP_ALL.md); the dump tooling runs on an
  OBDX Pro VX-class dongle (AGENTS.md). Exact adapter model for the capture run:
  **[TBD]** — reuse whatever produced the existing dumps.
- **Tester software**: the live-ECU tool is **private, not shipped** —
  `tools/uds/[REDACTED].py` (32-bit Python) — run from the private checkout. This
  plan adds documentation only, no new tooling to this repo.
- **Vehicle vs bench**: bench is the documented, preferred route (no car, no
  cluster; a plain UDS session needs only power + CAN — the cluster/wheel-sim rig
  is only for running-engine setups, per DUMP_ALL.md). In-vehicle capture:
  optional **[TBD]**.
- **Optional capture aid**: raw CAN logger / candump-style capture to timestamp
  responses and silence windows **[TBD]** — the tester's own log may suffice.

## 3. Procedure

Preconditions:

- ECU fully unpowered before wiring; power up only after all 6 grounds + 3 × +12V
  are connected (CONNECTOR_PINOUT.md).
- ECU must be in **normal run mode** (UDS stack up): TC-1 is the liveness probe —
  a positive response proves the CPU boots and the dispatcher `0x697E8` is live.
  If TC-1 times out with no other UDS traffic, the ECU may be in BOOT mode or
  mispowered — see Risks (bootloader).
- Run each test case as a single isolated request; log request timestamp and any
  frames on 0x7E8. **Silence = no frame on 0x7E8 within the timeout window**
  (suggest ≥ 1 s; exact value [TBD] from the tester's UDS session timeout).
- Repower between *classes* of cases if any 0x27 request may have mutated the
  security state (SECURITY_STATE_2 @ `0xFFFFD20C` — possible per discrepancy b).

Test-case table (payload = CAN data bytes on ID 0x7E0; `msg_len` excludes the SID
byte, per the dispatcher's `r4` convention @ `0x69840`):

| TC | Request payload (0x7E0) | subfunc | msg_len | Expected (ROM evidence) | ROM refs | PASS / FAIL |
|----|--------------------------|---------|---------|-------------------------|----------|-------------|
| 1  | `27 01` | 0x01 | 1 | Positive `[0x7E8] 67 01 s0 s1 s2`; 3 seed bytes, or `{0,0,0}` if state2==chk | entry `0x584B6`; `seed_gen(3)` `0x58522`; cond. copy `0x5854C`-`0x58566`; builder `0x5864A` | PASS: any `67 01 xx xx xx` within timeout |
| 2  | `27` | (none) | 0 | NRC `[0x7E8] 7F 27 12` | `0x584E2`-`0x584E8` → `0x5861A`/`0x5861C` | PASS: `7F 27 12` |
| 3  | `27 01 00` | 0x01 | 2 | NRC `[0x7E8] 7F 27 12` (msg_len != 1 — discr a) | `0x5851A`-`0x5851E` → `0x58588` | PASS: `7F 27 12` |
| 4  | `27 00` | 0x00 | 1 | A response is emitted via helper `0x55386` (else path, subfunc==0); exact frame **[TBD]** — do **not** expect `7F 27 31` (that NRC is in the subfunc==1-only body @ `0x584F8`) | else path `0x5862C`; pool `0x586C0` | PASS: any frame on 0x7E8 (not silence) |
| 5  | `27 02` | 0x02 | 1 | **Silence** (subfunc != 1 → else; != 0 → silent return) | `0x5862C` | PASS: no frame on 0x7E8 |
| 6  | `27 04` | 0x04 | 1 | **Silence** — SendKey never runs | `0x5862C`; body `0x58592` unreachable (single incoming `bf/s @0x58516`, never taken) | PASS: no frame on 0x7E8 |
| 7  | `27 04 k0 k1 k2` | 0x04 | 4 | **Silence** — even at the SendKey body's exact `msg_len==4` gate the body is not entered | entry `0x5862C` vs body gate `cmp/eq #4` @ `0x58592` | PASS: no frame on 0x7E8 |
| 8  | `27 04 k0 k1 k2 k3` | 0x04 | 5 | **Silence** — silence is msg_len-independent on the else path | `0x5862C` | PASS: no frame on 0x7E8 |
| 9  | `27 01` × N (repeats) | 0x01 | 1 | Observe seed across requests: `{0,0,0}` possible when state2==chk (discr b); seeds are LFSR-nondeterministic — assert structure, not values | `0x5854E` (cmp chk vs state2) | PASS: no crash; each reply `67 01` + 3 bytes (zero or non-zero) |
| 10 | `27 FF` (optional probe) | 0xFF | 1 | **Silence** (odd subfunc != 1 → else; != 0 → silent) | `0x584B6`, `0x5862C` | PASS: no frame on 0x7E8 |

Note: the only NRC literals in the whole handler body `0x584A0`-`0x58648` are
{0x12, 0x31, 0x22, 0x35}; 0x22/0x35 live in the dead SendKey body. **Seeing any
NRC 0x22/0x35, or any frame at all in response to a 0x02/0x04 request, is a FAIL
of the dead-code verdict** — it would indicate a reachable SendKey path in this
build.

## 4. Expected results

Derived strictly from REQUEST_SEED_EVIDENCE.md and SENDKEY_RECONCILIATION.md
(addresses cited):

| # | Expected observation | Evidence / ROM ref |
|---|----------------------|--------------------|
| E1 | `27 01` / msg_len==1 → `67 01` + 3 bytes (seed from `seed_gen(3)` @ `0x58522`, or `{0,0,0}`) | builder `0x5864A` → send `0x68B60`; conditional path `0x5854C`-`0x58566` |
| E2 | `27 01` / msg_len==0 → NRC `0x12` | `0x584E8` → `0x5861A` |
| E3 | `27 01` / msg_len==2 → NRC `0x12` (msg_len != 1) | `0x5851A`-`0x5851E` → `0x58588` |
| E4 | `27 00` → a response (helper `0x55386`), NOT NRC `0x31` | else path `0x5862C`; the subfunc==0 NRC 0x31 is at `0x584F8`, inside the subfunc==1-only body |
| E5 | `27 02` / `27 04` (any msg_len) → **silence**, never a `67 04` frame, never NRC 0x22/0x35 | else path `0x5862C`; SendKey body `0x58592`-`0x58610` has a single incoming `bf/s @0x58516` (abs-trick, never taken) |
| E6 | NRC 0x31 only if `position_check` returns the ==3 sentinel (`chk==3`, `0x5857E`) or `key_validate(...) != 0` (`0x58574`) — neither expected on a healthy stock unit | `0x58530`-`0x58534`, `0x58544`-`0x58548` |
| E7 | Repeated `27 01`: seed may collapse to `{0,0,0}` if state2==chk after the first request | `0x5854E` (chk vs state2 compare) |

Live discriminability of the 5 documented discrepancies (REQUEST_SEED_EVIDENCE):

| Discr | Discriminable on the wire? | How |
|-------|----------------------------|-----|
| (a) `msg_len==1` exact check missing in C | **YES** | TC-3: msg_len==2 must yield `7F 27 12` |
| (b) Seed bytes written conditionally (zero-fill if state2==chk) | **YES** (probabilistic) | TC-9: `{0,0,0}` seed when state2==chk |
| (c) State reads unconditional in C | NO (internal; already CONFIRMED in ROM) | not observable — ROM-evidence only |
| (d) Calling convention: `r4` = msg_len value, not pointer | NO (internal; already CONFIRMED) | not observable — ROM-evidence only |
| (e) SendKey unreachable (dead code) | **YES** | TC-5..8/10: silence for every 0x02/0x04 (and 0xFF) request |

## 5. Success criteria

The capture is "validated" when **all** of:

1. Every test case in §3 lands in its expected set: exact NRC frames for TC-2/TC-3,
   a response for TC-1/TC-4, and **confirmed silence** (no 0x7E8 frame within the
   timeout window) for TC-5, 6, 7, 8, 10.
2. **Zero SendKey executions detected**: no response frame of any kind for any
   request with subfunc `0x02`/`0x04` (no positive `67 04`, no `7F` error frame,
   no data frame), and no NRC `0x22`/`0x35` anywhere on the bus (those literals
   exist only in the dead body) — i.e. never a response carrying seed-key-related
   material.
3. TC-9 shows the structural seed contract holds: every RequestSeed reply is
   `67 01` + exactly 3 bytes; if `{0,0,0}` is ever observed, discrepancy (b) is
   confirmed live.
4. `7F 27 12` observed for **both** TC-2 (msg_len==0) and TC-3 (msg_len==2) —
   discrepancy (a) confirmed live.
5. If 1-4 pass: verdict — SENDKEY_RECONCILIATION verdict (b) (SendKey dead code
   in 60E1D400) is **runtime-CONFIRMED**; the two evidence notes are updated after
   the run (not by this plan).

## 6. Risks / notes

- **Bootloader / BOOT mode**: if the ECU does not answer TC-1, it may be in BOOT
  mode (or mispowered). The BOOT-mode path (`docs/notes/BOOT_RECOVERY.md` jig) runs
  different code — the UDS handler under test is only valid in normal run mode.
  Verify power wiring first; do **not** flash anything for this capture.
- **Tester safety**: never drive pin **4E** (Main Relay enable — open-drain ECU
  output); only feed the documented power pins. Keep the unpowered-before-wiring
  discipline from DUMP_ALL.md.
- **Bench DTCs**: bench power-up without cluster/sensors sets a pile of DTCs
  (DUMP_ALL.md) — harmless for UDS responses; do not clear them mid-capture
  (clearing via 0x14 is out of scope, **[TBD]** if needed).
- **Timing / silence definition**: "silent" must be defined against the tester's
  UDS session timeout (suggest ≥ 1 s; exact value **[TBD]**); log timestamps. The
  else path still runs the framework epilogue (`0x58622` → `0x55362` notification)
  — internal only, no CAN frame.
- **Seed nondeterminism**: RequestSeed seeds come from the 24-bit Galois LFSR
  (`seed_key_related`, `0x56ADA`) — assert *structure* (3 bytes; zero-fill allowed
  per discr b), never exact values.
- **9-image family**: baseline `60E1D400` is the capture target. The other 8 aux
  images carry the same dead-code structure (SENDKEY_RECONCILIATION ROM-by-ROM
  table) but differ in entry layout (extra `msg_len==1`/`subfunc==1` checks) and
  in the else-path response-SID constant (`#62`/0x3E vs `#39`/0x27) — per the
  reconciliation follow-up. A full family capture would need per-ROM passes (out
  of scope); one clean baseline capture confirms the verdict class for all 9.
- **Private tooling**: the live tester (`tools/uds/[REDACTED].py`, OBDX Pro VX,
  32-bit Python) is private, not shipped — run the capture from the private
  checkout. This plan adds documentation only, no code.
- **Session/security state**: 0x27 security state (SECURITY_STATE_2 @ `0xFFFFD20C`)
  can be mutated by a RequestSeed (discr b). Run TC-9 (repeats) last, or repower
  between classes, so an early RequestSeed cannot bias later silent-case results.

## References

- `docs/notes/REQUEST_SEED_EVIDENCE.md` (CONFIRMED 2026-08-04)
- `docs/notes/SENDKEY_RECONCILIATION.md` (RESOLVED 2026-08-04, verdict (b))
- `docs/notes/CAN_PROTOCOL.md` (HS-CAN; IDs 0x7E0/0x7DF/0x7E8; MB13-15; dispatcher `0x697E8`)
- `docs/notes/CONNECTOR_PINOUT.md` / `docs/notes/DUMP_ALL.md` (bench power + CAN wiring, J2534)
- `docs/notes/HARDWARE.md` (unit, SH7055 IC430)
- `docs/notes/BOOT_RECOVERY.md` (fallback path if the ECU is silent)
