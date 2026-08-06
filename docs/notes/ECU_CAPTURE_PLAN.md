# ECU Capture Plan — UDS 0x27 handler (60E1D400 baseline)

Status: **PLAN (not executed)** · 2026-08-04 · 6 external references reviewed (§7)

References: `docs/notes/UDS_SECURITY_MAPPING.md` §7 (RequestSeed ROM evidence CONFIRMED 2026-08-04; SendKey cross-ROM verdict (b): dead code in all 9 stock images, RESOLVED 2026-08-04).

Scope: live on-ECU validation of UDS security-access handler SID 0x27 — subfunction `0x04` (SendKey) produces **silence / no response**, SendKey flow **never executes**. Companion to the static-evidence notes.

## 1. Goal

Confirm at runtime, on a stock RX-8 ECU, that SID 0x27 handler (`security_access_handler` @ `0x584A0`, UDS dispatch table @ `0x5F57C` entry idx 10, accessMask `0x1000000E`, dispatcher `0x697E8`-`0x69840`) behaves as the ROM evidence says:

- (a) RequestSeed (subfunc `0x01`): positive response `[0x67, subfunc, 3 seed bytes]` (builder `0x5864A` → send `0x68B60`); NRC set {0x12, 0x31} for malformed/not-found.
- (b) subfunc `0x04` (SendKey) → **silence** (no frame on 0x7E8); SendKey flow (`0x58592`-`0x58610`) never executes — verdict (b).
- (c) msg_len gates: `msg_len==0` → NRC `0x12` (`0x584E8`); `msg_len==1` required for RequestSeed (else NRC `0x12` @ `0x58588` — discr a); SendKey `msg_len==4` gate (`cmp/eq #4` @ `0x58592`) never reached.

## 2. Hardware / setup

- **UDS over HS-CAN**: OBD-II pins 6/14; bench pins **4S = CAN-L, 4V = CAN-H**. Requests `0x7E0` (physical, MB14) / `0x7DF` (broadcast, MB13); response `0x7E8` (MB15, buffer `0x0DE0C`). No K-line / ISO 14230 evidence anywhere.
- **Stock ECU**: RX-8 SH7055 (IC430 per HARDWARE.md, N3J1 6-port MT); ROM under test = baseline `60E1D400` (flat image).
- **Bench power-up (no car)** — CONNECTOR_PINOUT.md / DUMP_ALL.md: GND **4A, 4J, 5D, 5O, 5R, 5T**; +12V **5AC, 5AF** (main-relay rail, bypass), **4Q**, **5J**; CAN **4S**/L **4V**/H. Do **not** drive **4E**.
- **CAN interface**: J2534 adapter; exact one for capture run **[TBD]** — reuse what produced existing dumps.
- **Tester software**: live-ECU tool **private, not shipped** — `tools/uds/<dump_tool>.py` (32-bit Python), private checkout. This plan adds documentation only.
- **Vehicle vs bench**: bench is the documented, preferred route. In-vehicle: optional **[TBD]**.
- **Optional**: raw CAN logger/candump to timestamp responses and silence windows **[TBD]**.

## 3. Procedure

Preconditions: ECU unpowered before wiring; power after 6 grounds + 3 × +12V. ECU in **normal run mode** — TC-1 is the liveness probe (positive response proves dispatcher `0x697E8` live). Run each test case isolated; log request timestamp and any 0x7E8 frames. **Silence = no 0x7E8 frame within timeout** (≥ 1 s; exact **[TBD]**). Repower between *classes* if a 0x27 request may have mutated security state (SECURITY_STATE_2 @ `0xFFFFD20C`).

Test cases (payload = CAN data bytes on 0x7E0; `msg_len` excludes the SID byte, per dispatcher's `r4` convention @ `0x69840`):

| TC | Request payload (0x7E0) | subfunc | msg_len | Expected (ROM evidence) | ROM refs | PASS / FAIL |
|----|--------------------------|---------|---------|-------------------------|----------|-------------|
| 1  | `27 01` | 0x01 | 1 | Positive `[0x7E8] 67 01 s0 s1 s2`; 3 seed bytes, or `{0,0,0}` if state2==chk | entry `0x584B6`; `seed_gen(3)` `0x58522`; cond. copy `0x5854C`-`0x58566`; builder `0x5864A` | PASS: any `67 01 xx xx xx` within timeout |
| 2  | `27` | (none) | 0 | NRC `[0x7E8] 7F 27 12` | `0x584E2`-`0x584E8` → `0x5861A`/`0x5861C` | PASS: `7F 27 12` |
| 3  | `27 01 00` | 0x01 | 2 | NRC `[0x7E8] 7F 27 12` (msg_len != 1 — discr a) | `0x5851A`-`0x5851E` → `0x58588` | PASS: `7F 27 12` |
| 4  | `27 00` | 0x00 | 1 | A response via helper `0x55386` (else path, subfunc==0); exact frame **[TBD]** — do **not** expect `7F 27 31` (NRC in subfunc==1-only body @ `0x584F8`) | else path `0x5862C`; pool `0x586C0` | PASS: any frame (not silence) |
| 5  | `27 02` | 0x02 | 1 | **Silence** (subfunc != 1 → else; != 0 → silent return) | `0x5862C` | PASS: no frame on 0x7E8 |
| 6  | `27 04` | 0x04 | 1 | **Silence** — SendKey never runs | `0x5862C`; body `0x58592` unreachable (single incoming `bf/s @0x58516`, never taken) | PASS: no frame on 0x7E8 |
| 7  | `27 04 k0 k1 k2` | 0x04 | 4 | **Silence** — even at the SendKey body's `msg_len==4` gate | entry `0x5862C` vs body gate `cmp/eq #4` @ `0x58592` | PASS: no frame on 0x7E8 |
| 8  | `27 04 k0 k1 k2 k3` | 0x04 | 5 | **Silence** — msg_len-independent on else path | `0x5862C` | PASS: no frame on 0x7E8 |
| 9  | `27 01` × N (repeats) | 0x01 | 1 | Observe seed across requests: `{0,0,0}` possible when state2==chk (discr b); seeds LFSR-nondeterministic — assert structure, not values | `0x5854E` (cmp chk vs state2) | PASS: no crash; each reply `67 01` + 3 bytes |
| 10 | `27 FF` (optional) | 0xFF | 1 | **Silence** (subfunc != 1 → else; != 0 → silent) | `0x584B6`, `0x5862C` | PASS: no frame on 0x7E8 |

Note: only NRC literals in the whole handler body `0x584A0`-`0x58648` are {0x12, 0x31, 0x22, 0x35}; 0x22/0x35 live in the dead SendKey body. **Any NRC 0x22/0x35, or any frame to a 0x02/0x04 request, is a FAIL of the dead-code verdict.**

## 4. Expected results

Derived from UDS_SECURITY_MAPPING.md §7.1/§7.3:

| # | Expected observation | Evidence / ROM ref |
|---|----------------------|--------------------|
| E1 | `27 01` / msg_len==1 → `67 01` + 3 bytes (seed from `seed_gen(3)` @ `0x58522`, or `{0,0,0}`) | builder `0x5864A` → send `0x68B60`; conditional path `0x5854C`-`0x58566` |
| E2 | `27 01` / msg_len==0 → NRC `0x12` | `0x584E8` → `0x5861A` |
| E3 | `27 01` / msg_len==2 → NRC `0x12` (msg_len != 1) | `0x5851A`-`0x5851E` → `0x58588` |
| E4 | `27 00` → a response (helper `0x55386`), NOT NRC `0x31` | else path `0x5862C`; subfunc==0 NRC 0x31 at `0x584F8`, inside subfunc==1-only body |
| E5 | `27 02` / `27 04` (any msg_len) → **silence**, never `67 04`, never NRC 0x22/0x35 | else path `0x5862C`; SendKey body `0x58592`-`0x58610` single incoming `bf/s @0x58516` (never taken) |
| E6 | NRC 0x31 only if `position_check` returns ==3 sentinel (`0x5857E`) or `key_validate(...) != 0` (`0x58574`) — neither expected on a healthy stock unit | `0x58530`-`0x58534`, `0x58544`-`0x58548` |
| E7 | Repeated `27 01`: seed may collapse to `{0,0,0}` if state2==chk | `0x5854E` (chk vs state2 compare) |

Live discriminability of the 5 documented discrepancies (UDS_SECURITY_MAPPING §7.1):

| Discr | Discriminable on the wire? | How |
|-------|----------------------------|-----|
| (a) `msg_len==1` exact check missing in C | **YES** | TC-3: msg_len==2 must yield `7F 27 12` |
| (b) Seed bytes written conditionally (zero-fill if state2==chk) | **YES** (probabilistic) | TC-9: `{0,0,0}` seed when state2==chk |
| (c) State reads unconditional in C | NO (internal; CONFIRMED in ROM) | not observable |
| (d) Calling convention: `r4` = msg_len value, not pointer | NO (internal; CONFIRMED) | not observable |
| (e) SendKey unreachable (dead code) | **YES** | TC-5..8/10: silence for every 0x02/0x04 (and 0xFF) request |

## 5. Success criteria

All:
1. Every test case lands in its expected set: exact NRC for TC-2/TC-3, a response for TC-1/TC-4, **confirmed silence** for TC-5..8/10.
2. **Zero SendKey executions**: no response frame for any subfunc `0x02`/`0x04`; no NRC `0x22`/`0x35` anywhere on the bus.
3. TC-9 structural seed contract: every RequestSeed reply is `67 01` + exactly 3 bytes; `{0,0,0}` → discrepancy (b) confirmed live.
4. `7F 27 12` for **both** TC-2 (msg_len==0) and TC-3 (msg_len==2) — discrepancy (a) confirmed live.
5. If 1–4 pass: UDS_SECURITY_MAPPING §7.3 verdict (b) (SendKey dead code in 60E1D400) is **runtime-CONFIRMED**.

## 6. Risks / notes

- **BOOT mode**: if TC-1 times out, ECU may be in BOOT mode (or mispowered) — 0x27 handler only valid in normal run mode. Verify power first; **do not flash** for this capture.
- **Tester safety**: never drive pin **4E**; only feed documented power pins. Unpowered-before-wiring discipline (DUMP_ALL.md).
- **Bench DTCs**: harmless for UDS; don't clear mid-capture (0x14 out of scope, **[TBD]**).
- **Timing / silence**: "silent" against the tester's UDS timeout (≥ 1 s; exact **[TBD]**); log timestamps. The else path runs the framework epilogue (`0x58622` → `0x55362`) — internal only, no CAN frame.
- **Seed nondeterminism**: RequestSeed seeds from 24-bit Galois LFSR (`seed_key_related`, `0x56ADA`) — assert *structure* (3 bytes; zero-fill allowed per discr b), never exact values.
- **9-image family**: baseline `60E1D400` target; other 8 aux images share the dead-code structure (UDS_SECURITY_MAPPING §7.3) but differ in entry layout and else-path response-SID (`#62`/0x3E vs `#39`/0x27). One clean baseline capture confirms the verdict class for all 9.
- **Private tooling**: live tester (`tools/uds/<dump_tool>.py`, OBDX Pro VX, 32-bit Python) private, not shipped.
- **Session/security state**: `SECURITY_STATE_2` @ `0xFFFFD20C` can be mutated by RequestSeed (discr b). Run TC-9 last, or repower between classes.

## 7. External captures / references

Reviewed 2026-08-04 (curl + GitHub REST API + indexed web search). **No public raw CAN captures (.asc/.blf/.csv/candump .log) of PCM 0x27 exchanges found.**

### 7.1 Live 0x27 exchange (bench RX-8 ICM) — rnd-ash wiki
- https://github.com/rnd-ash/rx8-reverse-engineering/wiki (pages: "Instrument cluster", "RX8 CANBUS", "powertrain control module") — ISO-TP trace of live KWP2000-over-CAN bench sessions, 2006 S1 RX-8 (231 PS).
- ICM (0x720→0x728): `27 01` → `67 01 46 4E 7F` — **3-byte seed**; SecurityAccess **only in session 0x87**; Mazda NRC quirk: `0x22` used instead of `0x80`. PCM diag IDs confirmed: 0x7E0/0x7E8.
- **TODO (futuro)**: catturare il seed di una **PCM stock** (0x7E0→0x7E8) come cross-validation live. La cattura ICM esistente (rnd-ash wiki §7.1) proviene da un tool di tuning (**VersaTuner**), quindi **non è evidence della chiave stock PCM** e non è presentata come già cross-validata.

### 7.2 Working seed-key ROM-dump implementation — ConnorRigby/rx8-ecu-dump
- https://github.com/ConnorRigby/rx8-ecu-dump (`src/UDS.*`, `src/librx8.cpp/.h`, `src/main.cpp`) — C++ J2534 (Tactrix) tool, 500 kbit CAN, full RX-8 PCM diag flow.
- Sessions `10 81`/`10 85`; SecurityAccess `27 01` → seed (3 bytes); key = 24-bit LFSR, secret `"MazdA"` `{0x4d,0x61,0x7a,0x64,0x41}`, state `0xc541a9`; SendKey `27 02 <k0 k1 k2>` expects `67 02`; then `0x34` RequestDownload / `0x36` TransferData; bootloader-mode entry for flash writes. NRC map: `0x22` cond-not-correct, `0x35` invalid-key, `0x36` exceeded-attempts.
- Cross-validates (i) 3-byte seed in `67 01`, (ii) NRC semantics of {0x12, 0x31, 0x22, 0x35}, (iii) working SendKey subfunc **0x02, not 0x04** — consistent with subfunc 0x04 → silence in run-mode handler. Caveat: tool path runs in diag/programming session (0x81/0x85 + bootloader), **outside** normal run-mode handler. No license — reference only.

### 7.3 Public stock ROM dumps (incl. byte-identical baseline) — equinox311/Mazda_RX8_PCM_ReverseEngineering
- https://github.com/equinox311/Mazda_RX8_PCM_ReverseEngineering — `Stock_ROMs/` (9 ROMs incl. `60E1D400.bin`), `Data_binaries/` (`60E0FC00.bin`, `RX8_93c56_ECU_IC420_Read.bin`, `ram_capture.bin`, `se3p_ecm_eeprom.bin`), `Ghidra_Archives/`.
- Verified 2026-08-04: external `Stock_ROMs/60E1D400.bin` **byte-identical** to baseline — md5 `5e4236d29b7c05820240fa076dffdd40`, 524288 B. `ram_capture.bin` = live RAM capture (output of a security-access session).
- Reuse: `ram_capture.bin` / EEPROM dumps diffable against future live capture. No license stated.

### 7.4 Community reflash tool (binary) — Rx8Man
- https://github.com/Rx8Man/Rx8Man/releases (v1.21 2026-05-28; v1.20, 1.05, 1.04) — closed-source Windows read/reflash via Tactrix J2534.
- Carries the default "MazdA" security key + mazdaEdit key; reads/writes engine ROM over CAN. No source, no published logs.

### 7.5 rx8club — Open Source S1 RX-8 ECU RE, Data Logging & Tuning (guide thread)
- https://www.rx8club.com/series-i-engine-tuning-forum-63/open-source-s1-rx-8-ecu-reverse-engineering-data-logging-tuning-users-guide-276137/ (2025-01-12) — Cloudflare-gated; verified via indexed snippets.
- ROM read/write via Tactrix + RX8Man; supported ROMs incl. **60E1D400 — N3J1EM 6 Port MT**; BOOT mode via Renesas FDT; security-key discussion (default "MazdA"); ELM327/OBDLink not true J2534.

### 7.6 rx8club — ECU Technical exploration (thread)
- https://www.rx8club.com/new-member-forum-197/ecu-technical-exploration-272570/ (2021-03) — Cloudflare-gated; verified via indexed snippets.
- OBD-II/CAN/UDS primer with raw CAN frames on 0x7E0/0x7E8 (VIN request `7E0#02 09 02 …`); bench-ECU ROM dump via Renesas AUD interface; FDT SCI header (CN400); OBD-II pins 6/14. No 0x27 frames (dump route is AUD/FDT, not UDS).

### 7.7 Supplementary tooling / defs / negative results
- `stratomancer/rx8-s1-canbus` (2026-04) — Python KWP2000/ISO-TP monitor on 0x7E0/0x7E8; PID tables; no 0x27 handling.
- `equinox311/RX8Defs` (RomRaider defs) and `Rx8Man/RX8Defs` (ECUFlash XML) — table/logger defs only.
- `equinox311/RX8_vehicle_CAN_Logs` — **empty placeholder** (2022-05-14, zero files): a gap this capture run could fill.
- Signal-level CAN DBs (not diagnostic): `majbthrd/MazdaCANbus` `rx8.kcd`, `topolittle/RX8-CAN-BUS`, `Antipixel/RX8-Dash`, Racelogic "Mazda RX-8 2003-2012" DB.
- Commercial ECU-file shops (ECULinks, c4ip.ru, e85.eu, chiptuning-files-service.com) list 60E0FC00 / 60E1D400 (Denso EGI 279700-3303, SH7055) — paid/torrent access, no captures.

### 7.8 Reuse for validation
- **NRC semantics**: 7.2's map {0x22, 0x35, 0x36} pins our ROM-only literals {0x12, 0x31, 0x22, 0x35}; any 0x02/0x04 reply with 0x22/0x35 disproves the dead-code verdict.
- **Seed format**: 7.1 and 7.2 both confirm `67 01` + exactly 3 bytes → TC-1/TC-9 pass criteria align.
- **Session gating**: 7.1 (ICM) and 7.2 (PCM) both require session 0x87 for SecurityAccess; TC set is run-mode-only — "silence" (TC-5..8/10) consistent only if the ECU stays in run mode; a session change to 0x87 may alter behavior (**[TBD]**).

Search log (2026-08-04): DuckDuckGo HTML (partial, bot-gated), GitHub repo-search API, indexed web search — query classes: "RX-8 ECU 0x27 seed key capture/log", "Mazda RX-8 diagnostic CAN log UDS/KWP2000 seed key", "rx8ecu", "60E1D400"/"60E0FC00", GitHub repo search `rx8`, `rx8 can`, `rx8 capture`. GitHub code search skipped (needs auth token).

## References

- `docs/notes/UDS_SECURITY_MAPPING.md` §7 (RequestSeed evidence CONFIRMED; SendKey verdict (b) RESOLVED — ex REQUEST_SEED_EVIDENCE / SENDKEY_RECONCILIATION / CROSS_VALIDATION_SEEDKEY, merged)
- `docs/notes/CAN_PROTOCOL.md` (HS-CAN; IDs 0x7E0/0x7DF/0x7E8; MB13-15; dispatcher `0x697E8`)
- `docs/notes/CONNECTOR_PINOUT.md` / `docs/notes/DUMP_ALL.md` (bench power + CAN wiring, J2534)
- `docs/notes/HARDWARE.md` (unit, SH7055 IC430)
- `docs/notes/BOOT_RECOVERY.md` (fallback if the ECU is silent)