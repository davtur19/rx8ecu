# Auxiliary Bank UDS Handler — Entry-Dispatch Comparison

Status: **RESOLVED 2026-08-04** — all 9 images (60E1D400 baseline + 8 aux)
share a **byte-identical SecurityAccess (SID 0x27) handler body**; the only
per-image deltas are code/data relocations (handler VA, literal pool values,
RAM addresses, dispatch-table VA) plus two data-level table variants.

Comparison target: the UDS dispatch entry of the SecurityAccess handler
(reconstructed in `c/security_access.c` for the 60E1D400 baseline).

---

## Method

- All images are flat ROMs (`-Ttext=0x0`, file offset == VA; byte-exact
  reassembly, see `src/ANNOTATED_SOURCES.md`).
- Handler localised per image by scanning the shared 12-byte prologue
  `2F E6 60 43 2F D6 64 5C 2F C6 2F B6` (mov.l r14,@-r15; mov r4,r0;
  mov.l r13,@-r15; extu.b r5,r4; ...) immediately followed by the dispatch
  `81 F2 60 43 88 01 8D 02` (`mov.w r0,@(4,r15); mov r4,r0; cmp/eq #1,r0;
  bt/s`). Exactly **one** hit per image.
- SID confirmed independently from the **dispatch table** (16-bit SID word
  4 bytes before the handler literal, 12-byte stride) AND from the handler's
  `mov #0x27,r4` immediates (`E4 27`) passed to the UDS read/error/send
  helpers.
- Structural comparison via `tools/disasm_sh2e.py`; subroutine VAs read from
  each handler's literal pool at `entry+0x1F0` (14 words, positional mapping —
  identical code layout ⇒ identical role order; the baseline order was
  confirmed against `docs/notes/REQUEST_SEED_EVIDENCE.md` literal table).
- Data addresses (state bytes, seed RAM, tables, mask pointer) extracted by
  disassembling each per-ROM subroutine and reading its literal pool.

---

## Per-ROM table (entry-dispatch)

All offsets below are relative to the handler entry (identical body ⇒
identical offsets); NRC = negative response via `uds_error_response` with
`r4 = SID 0x27`.

| ROM | handler entry | dispatch-table entry (SID word) | SID | accessMask | msg_len gates | subfunc admission | SendKey block (unreachable) | resp builder | else path (subfunc!=1) |
|-----|---------------|---------------------------------|-----|------------|---------------|-------------------|------------------------------|--------------|------------------------|
| 60E0E500 | 0x56E4C | 0x5DF98 | **0x27** | 0x1000000E | ==0→NRC 0x12 (tst@+0x42); ==1 req (cmp@+0x7C); ==4 sendkey (cmp@+0xF2) | only subfunc==1 (bt/s @+0x1A); !=1 → else | 0x56F3E (bf/s @0x56EC2) | 0x56FF6 | 0x56FD8 |
| 60E0E700_N3YLEE | 0x570A4 | 0x5E1F0 | **0x27** | 0x1000000E | ==0→NRC 0x12 (@0x570E6); ==1 (@0x57120); ==4 (@0x57196) | only 1 (bt/s @0x570BE) | 0x57196 (bf/s @0x5711A) | 0x5724E | 0x57230 |
| 60E0FB00 | 0x55F34 | 0x5D3E4 | **0x27** | 0x1000000E | ==0→NRC 0x12 (@0x55F76); ==1 (@0x55FB0); ==4 (@0x56026) | only 1 (bt/s @0x55F4E) | 0x56026 (bf/s @0x55FAA) | 0x560DE | 0x560C0 |
| 60E0FC00 | 0x55F34 | 0x5D3E4 | **0x27** | 0x1000000E | ==0→NRC 0x12 (@0x55F76); ==1 (@0x55FB0); ==4 (@0x56026) | only 1 (bt/s @0x55F4E) | 0x56026 (bf/s @0x55FAA) | 0x560DE | 0x560C0 |
| 60E15120_N3J1E | 0x57A64 | 0x5EBBC | **0x27** | 0x1000000E | ==0→NRC 0x12 (@0x57AA6); ==1 (@0x57AE0); ==4 (@0x57B56) | only 1 (bt/s @0x57A7E) | 0x57B56 (bf/s @0x57ADA) | 0x57C0E | 0x57BF0 |
| 60E1B900 | 0x561CC | 0x5D67C | **0x27** | 0x1000000E | ==0→NRC 0x12 (@0x5620E); ==1 (@0x56248); ==4 (@0x562BE) | only 1 (bt/s @0x561E6) | 0x562BE (bf/s @0x56242) | 0x56376 | 0x56358 |
| 60E1C500_N3J6EB | 0x57110 | 0x5E268 | **0x27** | 0x1000000E | ==0→NRC 0x12 (@0x57152); ==1 (@0x5718C); ==4 (@0x57202) | only 1 (bt/s @0x5712A) | 0x57202 (bf/s @0x57186) | 0x572BA | 0x5729C |
| **60E1D400** (baseline) | 0x584A0 | 0x5F5F4 | **0x27** | 0x1000000E | ==0→NRC 0x12 (@0x584E2); ==1 (@0x5851C); ==4 (@0x58592) | only 1 (bt/s @0x584BA) | 0x58592 (bf/s @0x58516) | 0x5864A | 0x5862C |
| 60E32000_N3M5E | 0x5D3E0 | 0x64BCC | **0x27** | 0x1000000E | ==0→NRC 0x12 (@0x5D422); ==1 (@0x5D45C); ==4 (@0x5D4D2) | only 1 (bt/s @0x5D3FA) | 0x5D4D2 (bf/s @0x5D456) | 0x5D58A | 0x5D56C |

Fixed gate addresses (identical offsets, shown for the baseline):

| gate | offset | 60E1D400 VA | NRC |
|------|--------|-------------|-----|
| msg_len == 0 (tst r4,r4) | +0x42 | 0x584E2 | 0x12 @0x5861A |
| subfunc == 0 (tst r5,r5) | +0x4C | 0x584F0 | 0x31 @0x5861C |
| msg_len == 1 (RequestSeed) | +0x7A | 0x5851A | 0x12 @0x58588 |
| position_check sentinel == 3 | +0x90 | 0x58530 | 0x31 @0x5857E |
| key_validate != 0 | +0xA6 | 0x58546 | 0x31 @0x58574 |
| SendKey msg_len == 4 | +0xF2 | 0x58592 | 0x12 @0x58610 |
| else path | +0x18C | 0x5862C | subfunc==0 → resp helper (0x55386); else silent |
| resp builder | +0x1AA | 0x5864A | [0x67, subfunc, n bytes] → uds_send |

---

## Subroutine VAs per ROM (handler literal pool @ entry+0x1F0)

| role | 60E0E500 | 60E0E700 | 60E0FB00/FC00 | 60E15120 | 60E1B900 | 60E1C500 | 60E1D400 | 60E32000 |
|------|----------|----------|---------------|----------|----------|----------|----------|----------|
| uds_read_payload | 0x67560 | 0x677B8 | 0x66A74 | 0x68184 | 0x66D0C | 0x67830 | 0x68BC0 | 0x6E4B8 |
| state_check1 | 0x55212 | 0x5546A | 0x54146 | 0x55E2A | 0x543DE | 0x554D6 | 0x56866 | 0x5B50E |
| state_check2 | 0x55292 | 0x554EA | 0x541C6 | 0x55EAA | 0x5445E | 0x55556 | 0x568E6 | 0x5B58E |
| uds_error_response | 0x53D56 | 0x53FAE | 0x52A5A | 0x5496E | 0x52CF2 | 0x5401A | 0x553AA | 0x59E22 |
| seed_gen | 0x55346 | 0x5559E | 0x5427A | 0x55F5E | 0x54512 | 0x5560A | 0x5699A | 0x5B642 |
| position_check | 0x5523E | 0x55496 | 0x54172 | 0x55E56 | 0x5440A | 0x55502 | 0x56892 | 0x5B53A |
| key_validate | 0x552D4 | 0x5552C | 0x54208 | 0x55EEC | 0x544A0 | 0x55598 | 0x56928 | 0x5B5D0 |
| data_copy | 0x5546C | 0x556C4 | 0x543A0 | 0x56084 | 0x54638 | 0x55730 | 0x56AC0 | 0x5B768 |
| level_slot_resolver | 0x55336 | 0x5558E | 0x5426A | 0x55F4E | 0x54502 | 0x555FA | 0x5698A | 0x5B632 |
| seed_key_related | 0x55486 | 0x556DE | 0x543BA | 0x5609E | 0x54652 | 0x5574A | 0x56ADA | 0x5B782 |
| unlock | 0x550CC | 0x55324 | 0x54000 | 0x55CE4 | 0x54298 | 0x55390 | 0x56720 | 0x5B3C8 |
| uds_fw_notify | 0x53D0E | 0x53F66 | 0x52A12 | 0x54926 | 0x52CAA | 0x53FD2 | 0x55362 | 0x59DDA |
| uds_resp_subfunc0 | 0x53D32 | 0x53F8A | 0x52A36 | 0x5494A | 0x52CCE | 0x53FF6 | 0x55386 | 0x59DFE |
| uds_send | 0x67500 | 0x67758 | 0x66A14 | 0x68124 | 0x66CAC | 0x677D0 | 0x68B60 | 0x6E458 |

The key-transform helper `0x42B0` (used by key_validate) is at the **same VA
in every image** (code before the relocated regions is identical too).

---

## Data / RAM addresses per ROM

| ROM | state byte 1 | state byte 2 | seed RAM base (3B) | level byte | position table | key_validate table | 2nd-stage mask ptr (RAM, runtime-written) |
|-----|--------------|--------------|--------------------|------------|----------------|--------------------|-------------------------------------------|
| 60E0E500 | 0xFFFFD147 | 0xFFFFD148 | 0xFFFFD14D | 0xFFFFD150 | 0x5E430 | 0x5E442 | 0xFFFFD32C |
| 60E0E700 | 0xFFFFD153 | 0xFFFFD154 | 0xFFFFD159 | 0xFFFFD15C | 0x5E688 | 0x5E69A | 0xFFFFD338 |
| 60E0FB00/FC00 | 0xFFFFCFE3 | 0xFFFFCFE4 | 0xFFFFCFE9 | 0xFFFFCFEC | 0x5D8DC | 0x5D8EE | 0xFFFFD1C8 |
| 60E15120 | 0xFFFFD1CF | 0xFFFFD1D0 | 0xFFFFD1D5 | 0xFFFFD1D8 | 0x5F054 | 0x5F066 | 0xFFFFD3B4 |
| 60E1B900 | 0xFFFFCFE3 | 0xFFFFCFE4 | 0xFFFFCFE9 | 0xFFFFCFEC | 0x5DB74 | 0x5DB86 | 0xFFFFD1C8 |
| 60E1C500 | 0xFFFFD147 | 0xFFFFD148 | 0xFFFFD14D | 0xFFFFD150 | 0x5E700 | 0x5E712 | 0xFFFFD32C |
| 60E1D400 | 0xFFFFD20B | 0xFFFFD20C | 0xFFFFD211 | 0xFFFFD214 | 0x5FA90 | 0x5FAA2 | 0xFFFFD3F0 |
| 60E32000 | 0xFFFFD24F | 0xFFFFD250 | 0xFFFFD255 | 0xFFFFD258 | 0x65104 | 0x65116 | 0xFFFFD438 |

Data-table contents (verbatim ROM bytes):

- **position_check table** (4×6, stride 6) — byte-identical everywhere:
  `00 00 00 00 00 00 | 01 01 02 00 FF FD | F1 F1 F2 00 FF FC | 00 00 00 01 00 01`.
- **position word_tab** (2nd stage, `pos_table+4 + i*6`):
  - `{0x0000, 0xFFFD, 0xFFFC, 0x0001}` — 60E0E500, 60E0E700, 60E15120,
    60E1C500, 60E1D400, 60E32000;
  - `{0x0000, 0xFFFF, 0xFFFE, 0x0001}` — **60E0FB00, 60E0FC00, 60E1B900**
    (variant; behaviourally equivalent for the mask test, see findings).
- **key_validate table** (10×3 @ key table base) — byte-identical everywhere
  (verified 60E0E500, 60E0FB00, 60E1D400, 60E32000):
  `00 00 00 01 00 01 01 01 01 01 02 00 01 02 01 01 03 00 02 03 02 02 04 00 01 04 01 01 05 03`.
- **secret "MazdA" + per-level LFSR init** — present in every image, e.g.
  `60E0E500 @0x5E460`, `60E0FB00 @0x5D90C`, `60E1D400 @0x5FAC0`,
  `60E32000 @0x65134`; identical init bytes `FF FF FF | C5 41 A9 | A3 95 82`
  (level 1 = 0xC541A9, level 2 = 0xA39582 — same as baseline).
- **free-running entropy counter** `0xFFFFF430` — same VA in every image
  (loaded as sign-extended 16-bit literal `0xF430`).

---

## Structural findings

1. **SID 0x3E claim for aux is REFUTED — every aux image dispatches the
   SecurityAccess handler with SID 0x27, mask 0x1000000E**, identical to the
   baseline (dispatch-table SID word `0x2700` verified at 0x5DF98 / 0x5E1F0 /
   0x5D3E4 / 0x5EBBC / 0x5D67C / 0x5E268 / 0x5F5F4 / 0x64BCC; handler body
   passes `#0x27` to every UDS read/error/send helper).  SID **0x3E is the
   separate TesterPresent service** (baseline handler @0x56F44) present in the
   dispatch table of every image — the earlier "aux = 0x3E" note in
   `docs/notes/SENDKEY_RECONCILIATION.md` (§Follow-up) was a misreading.
2. **The handler code body (entry .. entry+0x1E8) is byte-identical across
   all 9 images** (sha256 `147f610c…`, 0 bytes differ vs baseline).  Entry
   dispatch (`mov.w r0,@(4,r15)`; `cmp/eq #1,r0`; `bt/s` → RequestSeed;
   `bra` → else), the vestigial abs-trick, all msg_len gates, the conditional
   seed write-back, the response builder and the else path are the *same
   instructions* at the *same relative offsets*.
3. **Subfunction admission is `subfunc==1` only, in every image.**  The else
   path (`entry+0x18C`) is identical: `tst r4,r4` → `subfunc==0` → response
   helper (`uds_resp_subfunc0`); `subfunc!=0` → **silent no-response**.
   SendKey (`subfunc==0x04`) is unreachable in all 9 (only incoming branch =
   the never-taken abs-trick `bf/s`; see `docs/notes/SENDKEY_RECONCILIATION.md`
   verdict (b)).
4. **msg_len gates are identical**: `==0 → NRC 0x12`, `==1 → NRC 0x12`
   (RequestSeed), `==4 → NRC 0x12` (SendKey body), plus `subfunc==0 → NRC
   0x31`, `position_check==3 → NRC 0x31`, `key_validate!=0 → NRC 0x31`.
   NRC 0x11 never appears.
5. **Per-image relocation model**: the only real differences are (a) handler /
   subroutine / dispatch-table VAs (code moved between builds), (b) RAM
   addresses for state bytes, seed RAM and the position_check 2nd-stage mask
   pointer, (c) the two data-table variants (word_tab), and (d) the helper
   `0x42B0`/counter `0xFFFFF430` being build-invariant.
6. **Correction — position_check 2nd-stage mask**: the baseline C
   (`c/security_access.c` `mask = 0x61F2`, comment "mask word 0x61F2 @0x56CB0")
   is not what the ROM does: the mask is loaded **indirectly** via a
   sign-extended 16-bit RAM pointer (`mov.w <lit>,r1; mov.w @r1,r6`), e.g.
   baseline `0xD3F0 → 0xFFFFD3F0`, and the literal at 0x56CB0 (`0x61F2 =
   mov.l @r15,r1`) is an *instruction*, not data.  The mask word is
   runtime-written RAM ⇒ not statically visible; it is behaviourally
   irrelevant for the actual word_tab entries (`0xFFFD/0xFFFC` are dense →
   the AND is always nonzero for levels 1/2).

---

## Per-ROM peculiarities

- **60E0FB00 == 60E0FC00**: same handler entry (0x55F34), same dispatch-table
  VA (0x5D3E4), same subroutine pool (identical literal values), same RAM
  region (0xFFFFCFEx) and same word_tab variant — these two images differ only
  outside the security area.
- **60E0FB00 / 60E0FC00 / 60E1B900**: RAM window 0xFFFFCFE3..0xFFFFCFEC and
  word_tab variant `{0, 0xFFFF, 0xFFFE, 1}` (vs baseline `{0, 0xFFFD,
  0xFFFC, 1}`); mask ptr 0xFFFFD1C8.
- **60E0E500 == 60E1C500**: RAM window 0xFFFFD147..0xFFFFD150, mask ptr
  0xFFFFD32C (but different table VAs 0x5E430 vs 0x5E700).
- **60E32000**: security code relocated deepest (entry 0x5D3E0, tables
  0x65104/0x65116, mask ptr 0xFFFFD438).
- All 9: `"MazdA"` secret + identical LFSR init ⇒ same seed↔key algorithm
  (seed_key_related / ECOMcat core) — confirmed at data level for E500, FB00,
  D400, E32000 (spot-checked).

---

## Relationship to the C reconstructions

- `c/security_access.c` (baseline, 60E1D400): VERIFIED for the RequestSeed
  flow; SendKey kept as documented dead code; position_check mask constant
  `0x61F2` is a **known misread** (see finding 6) — not corrected here (out of
  scope; logic untouched rule).
- `c/security_access_aux.c` (NEW, this task): models the *shared* aux entry
  dispatch using the 60E0E500 layout as the primary bank (clearest structure,
  full RequestSeed flow confirmed), with per-bank deltas in comments
  (RAM addresses, subroutine VAs, word_tab variants) and the mask loaded from
  the per-ROM RAM pointer.  `[AUX-EVIDENCE]` marks points confirmed with VA;
  `[AUX-TBD]` marks runtime-only values (mask word value, `DIAG_SESSION`
  semantics).  **Not wired into any harness**: `c/security_access.c` is not
  compiled by `make c-test` either (only referenced by the Python
  `c/tests/test_security_access.py` / `test_security_statecheck.py`), so the
  aux file stays a source artifact.

---

## Open / TBD items

- Exact runtime value of the position_check mask word (RAM @ per-ROM pointer);
  behaviourally irrelevant for the stock tables.
- `DIAG_SESSION` (0xFFFFDE5C) usage in the aux images was not re-verified —
  the aux handler flow does not gate on it in the entry dispatch.
- Live-ECU capture (private tooling) to confirm `subfunc==0x04` behaviour
  (expected: no response / NRC, never the SendKey flow).

## References

- `docs/notes/REQUEST_SEED_EVIDENCE.md` — baseline handler literal table,
  gate/VA evidence, discrepancies (a)-(e).
- `docs/notes/SENDKEY_RECONCILIATION.md` — SendKey dead-code verdict (all 9
  images) + the now-refuted "0x3E" follow-up note.
- `c/security_access.c` — baseline reconstruction.
- `c/security_access_aux.c` — this task's aux entry-dispatch reconstruction.
- Scan tooling (transient, kept out of git): `tmp/aux_handlers/`.
