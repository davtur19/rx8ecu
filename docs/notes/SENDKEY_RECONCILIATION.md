# SendKey Cross-ROM Reachability Reconciliation

Status: **RESOLVED 2026-08-04 — verdict (b): SendKey body is dead code in all 9
public stock ROMs** (60E1D400 baseline + 8 aux images).

Scope: reconcile the discrepancy flagged in `docs/notes/REQUEST_SEED_EVIDENCE.md`
discrepancy (e) — the SendKey block (ROM `0x58592`-`0x58610` in 60E1D400) was
found **unreachable** in 60E1D400, contradicting the earlier "VERIFIED" SendKey
work.  This note extends that finding to a whole-family reachability scan.

---

## Method

- All 9 stock ROMs (`roms/stock/*.bin`, 512 KB each) are **flat images**: the
  annotated sources `src/*_annotated.s` are reassembled with `-Ttext=0x0`
  (byte-exact, `cmp`-verified — see `src/ANNOTATED_SOURCES.md`), so **file
  offset == virtual address** for every ROM.  No per-ROM base rebase was needed.
- **SendKey block location** per ROM: the 8-byte signature of the 60E1D400 block
  (`60 43 88 04 8f 3b 00 09` = `mov r4,r0; cmp/eq #0x04,r0; bf/s <fail>; nop`)
  was searched across each image.  Every image contains exactly one hit.
- **Whole-ROM incoming-branch scan**: for each image, the byte-exact annotated
  `.s` (symbolic `L_xxxxxx` branch targets) was scanned for every reference to
  the SendKey block label.  Direct branches (`bra/bsr/bt/bf/bt/s/bf/s`) counted
  separately from data refs.
- **Indirect-reference scan**: the 4-byte big-endian block address was searched
  as a literal (pool entries / jump tables) in each image.
- **Dispatch-structure check** per ROM: the handler entry dispatch (the
  `mov.w r0,@(4,r15)` + `cmp/eq #1,r0` prologue) and the `subfunc != 1` else
  path were disassembled and compared against the 60E1D400 baseline.
- Independent re-confirmation of the 60E1D400 claim (not re-reading prior
  results): the baseline scan reproduced the documented outcome exactly
  (single incoming `bf/s @0x58516`, abs-trick context, subfunc==1-only entry).

Scan tooling (transient, kept out of git): `tmp/sendkey_recon/scan_roms*.py`,
`verify_dispatch.py`, `ctx_s.py` (capstone SH-2 + annotated `.s`).

---

## ROM-by-ROM table

| ROM | handler (SID 0x27) | SendKey block | SendKey block VA | incoming branches | reachable? |
|-----|--------------------|---------------|------------------|-------------------|-----------|
| 60E0E500 | present | present (identical) | 0x056F3E | 1 × `bf/s` @0x56EC2 (abs-trick) | **no** (dead) |
| 60E0E700_N3YLEE | present | present (identical) | 0x057196 | 1 × `bf/s` @0x5711A (abs-trick) | **no** (dead) |
| 60E0FB00 | present | present (identical) | 0x056026 | 1 × `bf/s` @0x55FAA (abs-trick) | **no** (dead) |
| 60E0FC00 | present | present (identical) | 0x056026 | 1 × `bf/s` @0x55FAA (abs-trick) | **no** (dead) |
| 60E15120_N3J1E | present | present (identical) | 0x057B56 | 1 × `bf/s` @0x57ADA (abs-trick) | **no** (dead) |
| 60E1B900 | present | present (identical) | 0x0562BE | 1 × `bf/s` @0x56242 (abs-trick) | **no** (dead) |
| 60E1C500_N3J6EB | present | present (identical) | 0x057202 | 1 × `bf/s` @0x57186 (abs-trick) | **no** (dead) |
| **60E1D400** (baseline) | present | present (identical) | 0x058592 | 1 × `bf/s` @0x58516 (abs-trick) | **no** (dead) |
| 60E32000_N3M5E | present | present (identical) | 0x05D4D2 | 1 × `bf/s` @0x5D456 (abs-trick) | **no** (dead) |

Why unreachable in every image (three independent checks):

1. **Entry dispatch admits only `subfunc==1`.**  Every handler prologue is
   `mov.w r0,@(4,r15)` (save msg_len); `mov r4,r0` (r4 = subfunc after
   `extu.b r5,r4`); `cmp/eq #1,r0`; then `bt/s <body>` / `bra <else>`
   (60E1D400) or `bf/s <else>` (the other 8, structurally identical).
   `subfunc != 1` (including SendKey `0x04`) goes to the else path:
   `tst r4,r4` → `subfunc==0` → response helper call (60E1D400 pool 0x55386);
   `subfunc!=0` → **silent return** (epilogue `add #8/#20,r15; lds.l @r15+,pr;
   rts`).  Verified byte-level at e.g. 60E1D400 `0x5862C`, 60E0E500 `0x55982`,
   60E32000 `0x5D56C`.
2. **The only incoming branch to the block is the never-taken abs-trick
   `bf/s`.**  In every image the block is preceded by the same vestigial
   "absolute-value trick": `mov r5,r0; cmp/pz r0; bf/s ...; and #1,r0 ...;
   cmp/eq #1,r0; bf/s <SendKey block>`.  The branch is taken only when
   `subfunc & 1 == 0` (even subfunc); since only `subfunc==1` (odd) can reach
   it, it is never taken.  (Baseline addresses: `cmp/eq #1` @0x58514, `bf/s`
   @0x58516.)
3. **No indirect references.**  The block address appears nowhere as a literal
   (no pool entry / jump table) in any image, and the `.s` scan shows no data
   refs (`mov.l`/`.long`) to the block label — only the single `bf/s`.

Note: the other 8 images carry an additional `msg_len==1` / `subfunc==1`
re-check in the entry (e.g. 60E0E500 `0x5590A` / `0x55922`) — a slightly
different handler layout generation — but the subfunction admission rule is the
same (only 1).

---

## Previous "VERIFIED" SendKey work — what it covered

- **`fd56201`** (initial public release): the file header says the structural
  reconstruction was "DRAFT / UNVERIFIED", but the **seed↔key transform core**
  (`seed_key_related`, ROM `0x56ADA`) was marked VERIFIED against ROM 60E1D400
  — ECOMcat 24-bit Galois LFSR, vector `0xA07258` emulator-verified (level 1),
  12/12 keys + 400 random seeds (see `docs/functions/security_access_handler.md`
  verification table).  The C `SF_SEND_KEY` branch existed as part of the
  reconstruction.
- **`31bb0ac`** ("handler flow aligned to ROM"): the SendKey C branch was
  aligned to the **ROM body** at `0x58592`-`0x58610`: `msg_len==4` gate
  (`cmp/eq #4` @0x58592), `data_copy` returning the seed `level`
  (@0x56AC0, level byte @0xFFFFD214), `seed_key_related(level, seed, key)`,
  `unlock(level)` — all matched against the ROM body instructions.

What neither commit covered: **whether the ROM body at 0x58592 is itself
reachable from the UDS dispatch**.  The flow was verified against the body, and
the body is a faithful, identical shared-codebase remnant — but the body is
dead in every one of the 9 public stock images (and, per `src/ANNOTATED_SOURCES.md`,
the 10th private [REDACTED] dump belongs to the same family).

---

## Verdict

**(b) — definitive dead code (shared remnant across the whole family).**
The SendKey body is **present but unreachable in all 9 public stock ROMs**,
with identical structure.  It is the ROM-accurate reconstruction of a
shared-codebase remnant: the algorithms (SeedKeyRelated transform, data_copy →
level, unlock) are real and VERIFIED against the ROM body, but no stock image
dispatches subfunction `0x04` into the body.

Consequence (comments-only, no logic change — per this task):
`c/security_access.c` SendKey note extended with the verdict and per-ROM branch
addresses.  **No code removal**: the branch is kept as the reconstruction of the
ROM body, now explicitly documented as dead in every public stock ROM.

## Follow-up (optional)

- **Real-ECU capture** (live tooling, private) to confirm runtime behaviour of
  `subfunc==0x04` on a stock ECU — expected: NRC or silent no-response, never
  the SendKey flow; this would confirm the dead-code verdict at runtime.
- The aux-ROM handler entry carries extra `msg_len==1`/`subfunc==1` checks and
  a different response-SID constant (`#62`/0x3E vs 60E1D400 `#39`/0x27) on the
  else path — worth a dedicated per-family pass if the aux handlers are ever
  reconstructed in C (out of scope here).
- `docs/functions/security_access_handler.md` §Subfunction 0x04 updated to
  RESOLVED (see that file).

## References

- `docs/notes/REQUEST_SEED_EVIDENCE.md` — discrepancy (e) (the original flag).
- `docs/notes/FINDINGS.md` (2026-08-04 RequestSeed section, SendKey bullet).
- `docs/functions/security_access_handler.md` — SendKey section + verification
  table (updated to RESOLVED).
- `c/security_access.c` — SendKey note `[SENDKEY-RECONCILIATION]`.
- Commits: `fd56201` (SeedKeyRelated VERIFIED), `31bb0ac` (flow aligned to ROM
  body), `d4313d2` (SendKey flagged unreachable in 60E1D400), this work
  (cross-ROM scan → verdict (b)).
