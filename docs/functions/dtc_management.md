# DTC Management Subsystem @ 60E1D400.bin

Consolidated documentation of the RX-8 PCM diagnostic-trouble-code (DTC)
management functions. All six functions below are Track-A verified: the
actual ROM bytes were executed in the SH-2E emulator (`tools/sh2emu.py`) against
random RAM states and checked against the C lifts in `c/`.

| Function | Address | Role |
|---|---|---|
| `dtcRelated` | 0x062002 | Build/filter DTC code lists by type + enable gate |
| `dtc_handler_610FA` | 0x0610FA | DTC handler dispatcher (opcode 0x50/0x00 → service chain) |
| `dtc_handler_61550` | 0x061550 | Per-DTC detailed processing (modes 1/2/3) |
| `dtc_code_set` / `dtc_code_clear` | 0x046780 / 0x0467AA | Checksum-protected DTC state-word storage |
| `dtc_debounce_monitor_43760` | 0x043760 | Confirmation counter ladder (debounce) |

Verified: `c/tests/test_dtcRelated.py` (500 states), `test_dtc_handler_610FA.py`
(200), `test_dtc_handler_61550.py` (200), `test_dtc_code_set_clear.py` (500),
`test_dtc_debounce_monitor_43760.py` (500) — all pass.

## Shared RAM map (diagnostics area)

| Address | Size | Meaning |
|---|---|---|
| 0xFFFF87D8 | 21 × 16 B | DTC handler context table (code word @+0, type byte @+6) |
| 0xFFFF87DE | 21 × 16 B | DTC handler byte-code opcode table (opcode = first byte) |
| 0xFFFF8920 | word | DTC control word (non-zero ⇒ DTC subsystem inactive) |
| 0xFFFF8928 | word | Current DTC index (the DTC being serviced) |
| 0xFFFF875C/0xFFFF875E | word ×2 | DTC state words (checksum-protected pairs) |
| 0xFFFF8788 | byte | DTC-present / enable flag |
| 0xFFFF8D74 | word | 64258 service-entry selector (0 ⇒ entry 0xFFFF8930) |
| 0xFFFF8930 | 0x34 × N | OBD service-entry array (pending marker @+7, +8, counter @+0x32) |
| 0xFFFF8D7C | byte table | Per-DTC mode dispatch table (indexed by dtc × 2) |
| 0xFFFF8E98/0xFFFF8E9A | word ×2 | Running sums updated by 62ABC path 0 (via 0x648B4) |
| 0xFFFFD6F8..0xFFFFD6FF | 8 B | Diag result/status scratch (0xFFFFD6FC = encoded result, 0xFFFFD6FF = status) |
| 0xFFFFD700 | word | DTC currently addressed by the OBD request |

Checksum convention: every byte is stored with its bitwise complement in the
adjacent byte (16-bit pair); `readValue_8bit_ADDRESS_VAL` @0x3ED3C validates
`b[0] == ~b[1]` (else default), `updateMemoryAtAddress_8bit_ADDR_VAL` @0x3EE58
writes `val<<8 | ~val`.

## dtcRelated @ 0x062002

Scans the 21-entry context table and appends the 16-bit DTC code of every
entry whose type byte (entry+6) matches the selector to the caller's word
array (r6).  Matches are written **consecutively** (packed: out[0], out[1],
... in scan order — the running count doubles as the output index,
`r12 = out + 2·count`).  The entry whose index equals the current-DTC-index
word @0xFFFF8928 is skipped.  Optional enable gate (r5):
0 = none, 1 = `tableA[code]@0x7E220 == 1`, 2 = `tableB[code]@0x7E2AC == 1`,
any other value disqualifies the entry.

Type dispatch: `0x00 → ==0`, `0x60 → 1..0x3F`, `0x80 → bit7`,
`0xC0/0xC1/0x50 → exact`, `0xF0 → (1..0x3F) or bit7`, `0x70 → 0x81..0xBF`,
else no match.  Returns count in r0.

Note: the earlier draft (docs/functions/dtcRelated.md) referenced a
different address (0x5FEB6) and tables (0x0007C9FC/0x0007CA88) — superseded
by this verified version. See dtcRelated.md.

## dtc_handler_610FA @ 0x0610FA

Reads current DTC index @0xFFFF8928, indexes the opcode table @0xFFFF87DE,
and acts on the opcode:

- `0x50` (pending/completed) or `0x00` (empty) → run
  `can_encode_handler_62FAC(8)`, `obd_service_handler_64258()` (marks the
  pending service entry: byte +7 = 1, +8 = 7, bumps counter @+0x32), then
  tail-call `obd_service_handler_63312()`.
- any other opcode → return immediately (entry not in a serviceable state).

## dtc_handler_61550 @ 0x061550

Per-DTC detailed processing.  r4 = DTC code, r5 = mode:
1 = status, 2 = data, 3 = DTC list.

- mode 3: `dtc_handler_61712(dtc)` derives a status; encode via
  `can_encode_handler_62334` / `62E5C`; if accepted, DTC-state helpers run
  (`dtc_handler_61818`, `61994`, `can_encode_handler_62B74`,
  `dtc_handler_6193E(dtc,0x20)`, `obd_service_handler_63B46/63A62/63AD4`).
- mode 1: `obd_service_handler_63834` reads status; only entries with bit 7
  set continue (plus `63814` when bit7); same encode + service chain.
- mode 2: status read + encode + service chain (no bit-7 gate).

Common tail for every path: store encoded result to 0xFFFFD6FC, store
`can_encode_handler_62DEC(status)` to 0xFFFFD6FF; if the DTC currently
addressed (word @0xFFFFD700) equals r4, call `can_encode_handler_62ABC(dtc,0x20)`;
then `can_encode_handler_62B24(dtc,0x20,status)` and tail-call
`obd_service_handler_632D6()`.

## dtc_code_set / dtc_code_clear @ 0x046780 / 0x0467AA

- `dtc_code_set` (0x046780): if `readValue_8bit_ADDRESS_VAL(0xFFFF8788, 1) == 1`,
  writes checksum-encoded 0 to state words 0xFFFF875C and 0xFFFF875E.
- `dtc_code_clear` (0x0467AA): unconditionally writes 0 to the same two words.

## dtc_debounce_monitor_43760 @ 0x043760

Confirmation counter ladder, called once per task cycle from
`extended_control_dispatcher_3a764`.

RAM: cond @0xFFFFB3C8, enable @0xFFFFC9E8, reset @0xFFFFD201, flag1 @0xFFFFC9EF,
flag2 @0xFFFFC9F0, counters A/B/C @0xFFFFC9FE/0xFFFFCA00/0xFFFFCA02,
accum float @0xFFFFC9E4, runtime float @0xFFFFAAF0.
Calibration: 0x7D97C=157 (counter-A threshold), 0x7D978=16 (flag1), 0x7D97A=4
(flag2), 0x7D984=17000.0f, 0x7D988=500.0f.

Logic (verified): reset → zero all; `enable && cond && counterA >= 157` →
`if 17000.0f > accum` zero B/C; `elif 500.0f > runtime` path C (counterC++,
flag2 at >=4, B=0); else path B (counterB++, flag1 at >=16, C=0).  Else B=C=0.
Then `cond ? counterA++ : counterA = 0` (saturating).
Emulator note: `fcmp/gt Fm,Fn` sets T = (FRn > FRm) (sh2emu.py:110) — the
nested gate above matches that ordering.

## Callers

- 0x0610FA is called from `dtc_handler_61D2A` for every processed DTC and
  from the Mode-03-style reporting pipeline.
- 0x061550 is called from the UDS/OBD service handlers (Mode 19/0x03-ish).
- `callgraph.csv` is stale (built from 60E0FC00); use
  `symbols_60E1D400_merged.csv` and `/tmp/opencode/find_refs.py` instead.

## References

- C lifts: `c/dtcRelated.c`, `c/dtc_handler_610FA.c`,
  `c/dtc_handler_61550.c`, `c/dtc_code_set.c`,
  `c/dtc_debounce_monitor_43760.c`
- Tests: `c/tests/test_dtcRelated.py`, `test_dtc_handler_610FA.py`,
  `test_dtc_handler_61550.py`, `test_dtc_code_set_clear.py`,
  `test_dtc_debounce_monitor_43760.py`, `smoke_dtc_functions.py`
- Context: `docs/subsystems/FAULT_DIAGNOSTICS_SUBSYSTEM.md`
