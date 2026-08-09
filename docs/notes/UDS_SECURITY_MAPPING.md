# UDS Security Access — Mapping Subfunction → Level, seed_gen, key_validate

Project: rx8ecu — RE of Mazda RX-8 firmware (ROM `roms/stock/60E1D400.bin`, SH-2E)
Goal (PLANS.md:155-156): close the documented residual (UDS subfunction→level mapping; seed_gen internals for level≠3; key_validate middle byte).

Status: COMPILED (2026-08-03). Addresses verified on ROM `60E1D400.bin` with `tools/disasm_sh2e.py`. Test `c/tests/test_security_access.py`: EXIT=0, all PASS.
2026-08-04: seed-key cluster merge — this file is **canonical** for SecurityAccess (absorbed REQUEST_SEED_EVIDENCE, CROSS_VALIDATION_SEEDKEY, SENDKEY_RECONCILIATION; removed; unique facts in §7).

## 1. Mapping subfunction → level

### UDS dispatch table (how 0x27 reaches the handler)

- Dispatch table @`0x5F57C`, 12 bytes/entry: `[SID] [00 00 00] [handler LE32] [mask LE32]`. The literal @`0x6990C` references it (word BE `0x0005F57C`).
- Entry SID 0x27 @`0x5F5F4`: `27 00 00 00 00 05 84 A0 10 00 00 0E` → handler `0x584A0`, mask `0x1000000E`.

### Internal dispatch of handler `0x584A0` (SecurityAccess)

Input: `r4` = msg_len (16-bit, NOT a pointer), `r5` = subfunction byte (RESOLVED 2026-08-04 — dispatcher @`0x697E8`-`0x69840`; see §7.1).

1. `r4 = extu.b r5`; `cmp/eq #0x01` — **only subfunction == 1 proceeds** (≠1 → `0x5862C`, exit without response). Source: `0x584A6`-`0x584B8`.
2. It reads the payload byte: `0x68BC0(SID=0x27, dst=r15, len=1)` → `[r15]`. If `[r15]==0` → NRC `0x31` (`0x584EC`-`0x584F6`).
3. **The parity of `[r15]` selects the operation** (`0x584FE`-`0x58516`):
   - `[r15]` odd → RequestSeed (`0x5851A`)
   - `[r15]` even → SendKey (`0x58592`)
4. SendKey: a `cmp/eq #0x04` exists at `0x58594`; the SendKey branch is **dead code in 9/9 ROMs** (verdict (b), §7.3) — the `cmp/eq #0x04` is never reachable.

### The "level" is NOT derived from the subfunction linearly

- Code calls `seed_gen` **with fixed level 3** in both branches:
  - RequestSeed: `0x58522`-`0x58524` `jsr @0x5699A; mov #0x03,r4`
  - SendKey: `0x585A2`-`0x585A4` `jsr @0x5699A; mov #0x03,r4`
- The control level is the **table index of `position_check`**: `0x58526`-`0x5852C` `jsr @0x56892; r4=[r15]` → `r12`; if `extu.b(r12)==3` → NRC `0x31` (`0x58530`-`0x5857E`).

### position_check `0x56892` — table lookup @`0x5FA90` (stride 6)

- Loop `i=0..3`: compare `entry[i][1]` with the input byte (`0x568A8`-`0x568AC`). Entries (byte[1] → index `i`):
  | indice | entry @0x5FA90+6i            | byte[1] | word @+4 (2º stadio) |
  |--------|------------------------------|---------|----------------------|
  | 0      | `00 00 00 00 00 00`          | `0x00`  | `0x0000`             |
  | 1      | `01 01 02 00 FF FD`          | `0x01`  | `0xFFFD`             |
  | 2      | `F1 F1 F2 00 FF FC`          | `0xF1`  | `0xFFFC`             |
  | 3      | `00 00 00 01 00 01`          | `0x00`  | `0x0001`             |
- 2nd stage (`0x568BC`-`0x568E0`): `word @0xFFFFD3F0  AND  word @(0x5FA94 + i*6)`; if != 0 → return `i`; otherwise 3 (not found). **The mask is NOT constant: it is the RAM word @`0xFFFFD3F0`** (`mov.w @r1` with `r1=0xD3F0`, `0x568BC`).
- Return: `0..2` = matched entry, `3` = no-match/mask-clear.

**Answer to the residual**: the subfunction does not map 1:1 to a level; the level for the seed is **fixed at 3**; the validation level is the index `0..2` of `0x5FA90` (entry byte[1] ∈ {0x00, 0x01, 0xF1}).

## 2. seed_gen — path level≠3

### seed_gen `0x5699A` (entry), RAM: seed → `0xFFFFD211..213`, level → `0xFFFFD214`

- **level == 3** (`0x569B6` `cmp/eq #0x03`): `r13=r12=r14=0xFF`, jump to the write-back (`0x569BC`-`0x569C2` → `0x56A8C`): `jsr @0x3920(r4=0x10)` (setSR/priority), then `[0xFFFFD214]=level`, `[0xFFFFD211]=0xFF`, `[0xFFFFD212]=0xFF`, `[0xFFFFD213]=0xFF`, `jsr @0x3934` (finalize). → **the fast-path (RequestSeed) seed is `FF FF FF`.**
- **level ≠ 3** (entropy path, `0x569C4`-`0x56A8A`):
  1. Stack frame: `r9 = r15+0x1C` (buffer 4 byte), `r10 = 0x55`, `r11 = 0x10`, `r2 = 0xF430` (`0x569CA`-`0x569E4`).
  2. It reads the **free-running counter @`0xFFFFF430`** (`mov.l @r2,r6`, `0x569E6`-`0x569E8`) and copies it as 4 bytes into `r9[0..3]` with `shlr8` (`0x569EE`-`0x569FC`).
  3. `bsr @0x5687A(r4=4)`: compare `4` with `byte @0xFFFFD20B`; return 0 if equal (`0x56A00`-`0x56A02`; "is the state the sentinel 4?").
  4. State **not** 4 (`r0!=0`): XOR path (`0x56A2C`-`0x56A40`): `r14 = b[2]^b[0]`, `r12 = b[1]^b[0]`, `r13 = b[3]^b[0]`.
  5. State **is** 4 (`r0==0`): fixed seed `r14=0x55`, `r12=0xAA`, `r13=0x55` (`0x56A0C`-`0x56A12`, `mov.w 0x56A18 → 0x00AA`).
  6. Retry loop `0x56A42`-`0x56A8A`, counter `[r15]`, max `0x10` (16): if `r14==0 && r12==0 && r13==0` → retry (re-read the counter, `0x569E6`); if `r14==FF && r12==FF && r13==FF` → retry; past 16 → `r13=r12=r14=0xFF` (fallback `FF FF FF`).
  7. Common write-back `0x56A8C`+ (see above).

**Answer to the residual**: for level ≠ 3 the seed derives from 4 bytes of the counter `0xFFFFF430` with XOR-mix (b2^b0, b1^b0, b3^b0), or `55 AA 55` if `0xFFFFD20B == 4`, with retry on all-0/all-FF (max 16 → `FF FF FF`). Code uses the LFSR (per-level init @`0x5FAC5`, taps `0x909028`) **only in the key transform** `seed_key_related` `0x56ADA`, not in seed_gen.

## 3. key_validate — origin of the middle byte

### key_validate `0x56928` ("prediction") — table @`0x5FAA2`, stride 3

- Loop over entries: compare `entry[i][0]` vs `r4`, `[i][1]` vs `r5`, `[i][2]` vs `r6`; it iterates while `b0 < 5` (`0x5696E`-`0x56972`: `cmp/ge #5, b0`).
- Return (`0x56976`-`0x5697A`): `movt r4` = `(b0 >= 5)` of the last entry → **0 = valid match (b0<5), 1 = no match**. Caller `0x58546`-`0x58548`: result != 0 → NRC `0x31`.

### Call site — origin of the three bytes (KEY of the residual)

Call @`0x58538`-`0x58542` (RequestSeed branch), after `position_check`:

| param | registro | origine                                  |
|-------|----------|------------------------------------------|
| b0    | r4       | `[r15+8]` = risultato `jsr @0x568E6`     |
| b1    | r5       | `r10`    = **stesso valore** (duplicato)  |
| b2    | r6       | `r12`    = risultato `position_check`     |

- `0x584D2`-`0x584D6`: `jsr @0x568E6` → `[r15+8] = r0`; `0x584DA`: `r10 = r0`.
- `0x568E6` reads **`byte @0xFFFFD20C` = SECURITY_STATE_2** (`mov.l 0x5690C,r3`).
- → **the "middle byte" is not a seed/key byte: it is SECURITY_STATE_2, the same value as b0 (duplicated).** The C (lines 210-215) reconstructed `key_validate(state, subfunc, chk)` — the central `subfunc` parameter is wrong.

### ROM table @`0x5FAA2` (10 entries, verbatim)

```
@0x5FAA2: 00 00 00   b0<5
@0x5FAA5: 01 00 01
@0x5FAA8: 01 01 01
@0x5FAAB: 02 00 01
@0x5FAAE: 02 01 01
@0x5FAB1: 03 00 02
@0x5FAB4: 03 02 02
@0x5FAB7: 04 00 01
@0x5FABA: 04 01 01
@0x5FABD: 05 03 03   b0==5 → termina il loop
```
The loop stops at the first entry with `b0 >= 5` → first 9 entries.

**Answer to the residual**: the three compared bytes are `(SECURITY_STATE_2, SECURITY_STATE_2, position_check_result)`; the middle byte is a duplicated SECURITY_STATE_2. The C `c/security_access.c` (lines 397-403) reports only 5 entries, with rows 3-4 **different from the ROM** (see Section 6).

## 4. diag_seed_generate_4E72C / diag_key_validate_4E78A

IDA names are **misleading** — they are NOT the UDS 0x27 seed/key:

- `0x4E72C` ("diag_seed_generate_4E72C"): FP loop `0x0B` (11) iterations over `0xFFFFCEF0+`, `fdiv`, writes to `0xFFFFCF20`, flag `@0xFFFFA402` — **averaging/rolling-mean**, not a seed generator.
- `0x4E78A` ("diag_key_validate_4E78A"): reads `@0xCF82/@0xC020/@0xC01E/@0xCF81/@0xCFAC`, propagates flags to 1 (`0xCF81`, `0xCF82`, `0xCFAC`) — **diagnostic flag propagation**, not a key validator.
- The real SecurityAccess 0x27 functions: handler `0x584A0`, `seed_gen` `0x5699A`, `position_check` `0x56892`, `key_validate` `0x56928`, `data_copy` `0x56AC0`, `seed_key_related` `0x56ADA`, `unlock` `0x56720`.

## 5. Web confirmations

Source `github.com/ConnorRigby/rx8-ecu-dump` (`src/librx8.cpp`, `src/librx8.h`):

- `MAZDA_SBF_REQUEST_SEED = 0x01`, `MAZDA_SBF_CHECK_KEY = 0x02`
- `SEED_LENGTH = 3`
- Secret `MAZDA_KEY_SECRET` = `"MazdA"` (5 bytes, matches ROM @`0x5FAC0`)
- Init LFSR level1 `0xc541a9` (= entry level1 @`0x5FAC8`), taps `0x909028`
- Key = `compute_key(seed, level)` (Galois 24-bit, 64 clock, nibble-interleave) — **identical to `seed_key_related` `0x56ADA`**.

Discrepancy: librx8 sends `0x02` as SendKey; the C uses `SF_SEND_KEY = 0x04`. In the ROM dispatch the seed/key decision is the **parity** of the byte (odd=seed, even=key): both even → SendKey branch; the `cmp/eq #0x04` at `0x58594` is unreachable (dead code, §7.3).

## 6. Declared residuals

C discrepancies in `c/security_access.c` vs ROM (do NOT fix them in the file, only report them):

1. **key_validate table (lines 397-403) is NOT verbatim ROM**:
   - row 4: C `{0x01, 0x02, 0x00}` vs ROM `{0x02, 0x00, 0x01}` @`0x5FAAB`
   - row 5: C `{0x01, 0x02, 0x01}` vs ROM `{0x02, 0x01, 0x01}` @`0x5FAAE`
   - the C has 5 entries; the ROM has 10 (loop until b0<5 → 9 valid + terminator).
2. **key_validate middle byte (lines 210-215)**: the C passes `(state, subfunc, chk)`; the ROM `(SECURITY_STATE_2, SECURITY_STATE_2, chk)`.
3. **position_check (lines 308-310)**:
   - `word_tab[2]` C = `0x0000` vs ROM `0xFFFC` (@`0x5FAA0`)
   - the C mask `0x61F2` comes from the literal pool `0x56CB0` (code: `0x61F2` = `mov r9,r3`); the ROM reads the **RAM word @`0xFFFFD3F0`**.
4. **SF_SEND_KEY = 0x04** vs librx8 `0x02`. **RESOLVED (2026-08-04, §7.3)**: the SendKey body is **dead code in 9/9 ROMs** — the `cmp/eq #0x04` at `0x58594` is never reachable. The `r4` convention closed by §7.1: `r4` = msg_len, `r5` = subfunction.
5. **seed_key_related(4, …) in the SendKey branch (line 236)**: the ROM passes `r4 = r12` (result of data_copy/state), not 4. **RESOLVED (2026-08-04, §7.3)**: dead branch in 9/9 ROMs — the C keeps the body as a reconstruction of the shared-codebase remnant.
6. `0x68BC0` and `0x688B4` (per-subfunction SID dispatch): structure verified in broad terms. **RESOLVED (2026-08-04, §7.1)**: dispatcher `0x697E8`-`0x69840` → `r4` = msg_len (16-bit, `mov.w @r15,r4` @`0x69840`), `r5` = subfunction (8-bit @`0x6983A`-`0x6983C`).

History: residuals 1-3 (10-entry key_validate, middle byte = SECURITY_STATE_2, word_tab[2]=0xFFFC) **fixed and VERIFIED** in the C (commit `b483523`); residual 4 and detail flows open.
Status: handler `0x584A0` **structurally reconstructed**, core (seed_gen, key_validate, position_check, seed_key_related/lfsr) **VERIFIED** (`docs/functions/security_access_handler.md`); RequestSeed flow **ROM-CONFIRMED 2026-08-04** (evidence in §7.1).

## 7. Consolidated evidence (2026-08-04, merge of the 3 note clusters)

The REQUEST_SEED_EVIDENCE, CROSS_VALIDATION_SEEDKEY, SENDKEY_RECONCILIATION notes are absorbed into this file (unique facts below) and removed from the repo (`git rm`).

### 7.1 RequestSeed flow — row-by-row ROM evidence

- Method: byte-exact disasm `tools/disasm_sh2e.py` + `src/60E1D400_annotated.s` (flat image: file offset == VA). **Status CONFIRMED 2026-08-04**.
- **Convention RESOLVED** (closes §6.6): dispatcher @`0x697E8`-`0x69840` calls the handler with `r4` = **msg_len** (16-bit, `mov.w @r15,r4` @`0x69840`) and `r5` = **subfunction** (8-bit, `mov.b @(0x04,r15),r0; mov r0,r5` @`0x6983A`-`0x6983C`). The C `msg_len = (msg[0]<<8)|msg[1]` is semantically equivalent.
- **Callee identities** from the handler literal pool @`0x58690`-`0x586C4`: 0x68BC0 (read payload), 0x56866 (state_check1 @0xFFFFD20B), 0x568E6 (state_check2 @0xFFFFD20C), 0x553AA (udsErrorResponse `[0x7F,sid,nrc]` → 0x68B60), 0x5699A (seed_gen), 0x56892 (position_check), 0x56928 (key_validate), 0x56AC0 (data_copy, SEED_RAM @0xFFFFD211 → dst, return level @0xFFFFD214), 0x5698A (level-slot resolver, SendKey), 0x56ADA (seed_key_related), 0x56720 (unlock), 0x55362 (UDS response/notification helper), 0x55386 (response helper, subfunc==0 path), 0x68B60 (UDS send).
- **Response builder `0x5864A`**: `mov #103,r3` (0x67) @`0x5864A`; `resp = [0x67, subfunc, 3 seed bytes]` → send `0x68B60`.
- **Common epilogue** `0x58622`: `jsr @0x55362` (r4=0x27, r5=helper return) — UDS framework notification, not modeled by the C.
- **NRC table** (the only NRC literals in the whole body 0x584A0-0x58648: {0x12, 0x31, 0x22, 0x35}; 0x22/0x35 in the dead SendKey body; **NRC 0x11 NEVER emitted**):

  | NRC | Condizione            | ROM addr                    |
  |-----|-----------------------|-----------------------------|
  | 0x12 | `msg_len == 0`        | `0x584E8` → `0x5861A`       |
  | 0x12 | `msg_len != 1` (discr a) | `0x5851E` → `0x58588`     |
  | 0x31 | `subfunc == 0`        | `0x584F6` → `0x5861C`       |
  | 0x31 | `chk == 3` (position_check sentinel) | `0x58534` → `0x5857E` |
  | 0x31 | `key_validate(...) != 0` | `0x58548` → `0x58574`    |

- **C vs ROM discrepancies (documented; C logic NOT touched)**:
  - **(a) `msg_len == 1` check missing in the C**: ROM `0x5851A`-`0x5851E` `cmp/eq #0x01`; `msg_len != 1` → NRC 0x12 @`0x58588`. The C rejects only `==0`.
  - **(b) Conditional seed write**: ROM `0x5854C`-`0x58566` — `state2 == chk` → the 3 response bytes are **zero-filled** (no copy); `state2 != chk` → regenerate with `seed_gen(chk)` (@`0x5855E`-`0x58560`; the `seed_gen(3)` @`0x58522` is only side-effect finalization) and **then** copy. The C does unconditional `data_copy`.
  - **(c) Unconditional state reads in the C**: the ROM reads SECURITY_STATE_1/2 only in the `subfunc==1` branch (benign, side-effect-free).
  - **(d) Calling convention**: `r4` = msg_len (value), not a pointer.
  - **(e) SendKey unreachable in 60E1D400** → §7.3 (dead in 9/9).
- The abs-trick (`abs_sub` @`0x584FE`-`0x58516`) EXISTS but is **vestigial**: odd→RequestSeed / even→SendKey, but reachable only for `subfunc==1` (always odd) → always RequestSeed. **No "level must be 1" guard exists**: the `==1` test is on `msg_len`, the `==3` sentinel comes from `position_check`.

### 7.2 Cross-validation community

- **Status CONFIRMED-CROSS 2026-08-04** vs ConnorRigby/rx8-ecu-dump `src/librx8.cpp` `calculateKey()`, commit `5c784eccd5d399c8593cecd13a6fcf0dcd973ae1` (main v0.9.0, 2022-11-05, Apache-2.0, reference only — no code copied).
- Identical transform: **24-bit Galois LFSR**, init `0xC541A9` (= level-1 entry @`0x5FAC8`), taps `0x909028` (bit {23,20,15,12,5,3}; community mask `0xEF6FD7` clears {3,5,12,15,20}), 64 clock (32+32), stream LSB-first `seed[0..2] + "MazdA"` (phase1: seed[0]|seed[1]<<8|seed[2]<<16|secret[0]<<24; phase2: secret[4]<<24|secret[3]<<16|secret[2]<<8|secret[1]), key extraction nibble-interleave `[b2,b1,b0]`.
- **No XOR**: the secret feeds the LFSR as an input stream (byte 0 in phase 1, bytes 1-4 in phase 2), not XORed with the seed.
- **Vectors: 0 divergences** — 100 000 random clocks (0 mismatches), 400 random seeds (0), 3 ROM level-1 vectors (45820A→A07258, CBFED4→75491A, 123456→86CA06). Levels 2-4: init table @`0x5FAC5` (level1 C5 41 A9, level2 A3 95 82, …) — only the ROM-derived model covers them (12/12); community hardcodes level-1.
- Live capture: rnd-ash wiki, bench RX-8 **ICM** (0x720→0x728) `27 01` → `67 01 46 4E 7F` — **not PCM** (0x7E0→0x7E8) and captured with a tuning tool (**VersaTuner**), so its seed/key pair **is not evidence of the stock PCM key**. Expected PCM: same transform (to verify live on a stock PCM; no PCM capture available).
- NRC: community {0x22, 0x35, 0x36} in the diag/programming path (0x81/0x85 + bootloader); our handler run-mode {0x12, 0x31, 0x22, 0x35} — a handler/session difference, not a transform difference.
- Artifacts: `tools/mazda_security.py` (compute_key, 400 seed), `c/security_access.c` (lfsr_clock, seed_key_related), `c/tests/test_security_access.py` (12/12 ROM vectors), `c/tests/test_seed_gen_5699A.py` (0 mismatches), `tools/tests/test_cross_seedkey.py` (cross-validation).

### 7.3 SendKey — dead code in 9/9 ROM (verdict (b))

- **Status RESOLVED 2026-08-04 — verdict (b): the SendKey body is dead code in ALL 9 public stock ROMs** (baseline + 8 aux). Scan: flat image ⇒ file offset == VA; 8-byte signature `60 43 88 04 8f 3b 00 09` (= `mov r4,r0; cmp/eq #0x04,r0; bf/s <fail>; nop`) — exactly 1 hit per image.
- **Per-ROM table** (SID 0x27 handler present; body identical; only incoming = the `bf/s` abs-trick never taken):

  | ROM | SendKey block VA | incoming |
  |-----|------------------|----------|
  | 60E0E500 | 0x056F3E | 1× `bf/s` @0x56EC2 |
  | 60E0E700_N3YLEE | 0x057196 | 1× `bf/s` @0x5711A |
  | 60E0FB00 | 0x056026 | 1× `bf/s` @0x55FAA |
  | 60E0FC00 | 0x056026 | 1× `bf/s` @0x55FAA |
  | 60E15120_N3J1E | 0x057B56 | 1× `bf/s` @0x57ADA |
  | 60E1B900 | 0x0562BE | 1× `bf/s` @0x56242 |
  | 60E1C500_N3J6EB | 0x057202 | 1× `bf/s` @0x57186 |
  | **60E1D400** (baseline) | 0x058592 | 1× `bf/s` @0x58516 |
  | 60E32000_N3M5E | 0x05D4D2 | 1× `bf/s` @0x5D456 |

- **Why unreachable (3 independent checks)**: (1) the entry dispatch admits only `subfunc==1` (`cmp/eq #1`; ≠1 → else: `tst r4,r4` → subfunc==0 → response helper 0x55386; subfunc≠0 → silent return); (2) the only incoming branch = the `bf/s` abs-trick (taken only if `subfunc & 1 == 0`; subfunc==1 is odd → never taken); (3) no indirect reference (the block address never appears as a literal in any image).
- The 8 aux ROMs have an **extra `msg_len==1`/`subfunc==1` re-check** at entry (for example 60E0E500 `0x5590A`/`0x55922`) and response-SID `#62`/0x3E on the else-path (vs baseline `#39`/0x27) — slightly different layout, identical admission rule.
- **Consequence**: `c/security_access.c` keeps the SendKey branch as a faithful reconstruction of the ROM body (NO code removal). An extended comment carries the verdict + VAs.
- Commit history: `fd56201` (SeedKeyRelated VERIFIED — vector 0xA07258 emulator-verified, level 1, 12/12 keys + 400 seeds), `31bb0ac` (handler flow aligned to the ROM body @0x58592-0x58610: gate `msg_len==4` @0x58592, data_copy→level, seed_key_related, unlock), `d4313d2` (SendKey flagged unreachable in 60E1D400), then cross-ROM scan → verdict (b).