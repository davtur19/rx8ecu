# Cross-validation: seed/key implementation vs community (MazdA / LFSR 0xc541a9)

Status: **CONFIRMED-CROSS** · date 2026-08-04 · method: byte-for-byte reimplementation comparison
(our VERIFIED code vs community source, run on shared vectors + fixed random seeds + live capture seed).

## 1. What was cross-validated

Our seed/key implementation (VERIFIED against stock ROM 60E1D400):

- `tools/mazda_security.py` — `compute_key()`, `_clock()` (24-bit Galois LFSR, ECOMcat / Car Hacking Handbook).
- `c/security_access.c` — `lfsr_clock()`, `seed_key_related()` (direct port of ROM routine @0x56ADA).
- `c/tests/test_seed_gen_5699A.py` — seed **generation** path (`seed_gen` @0x5699A), verified against ROM bytes.

was compared against the community implementation:

- **ConnorRigby/rx8-ecu-dump**, `src/librx8.cpp` `RX8::calculateKey()`.
- URL: https://github.com/ConnorRigby/rx8-ecu-dump · commit `5c784eccd5d399c8593cecd13a6fcf0dcd973ae1`
  (main, v0.9.0, 2022-11-05). Apache-2.0; reference only, no code copied into this repo.
- The C++ is itself a decompiler-style port of the same stock ROM routine (variable names
  `v8/v9/v10/v12/v13/v14`, `mucked_value`).

And against the live capture seed **0x464E7F** (rnd-ash wiki, bench RX-8 ICM:
`27 01` → `67 01 46 4E 7F`; §7.1 of ECU_CAPTURE_PLAN.md).

## 2. Community algorithm extracted (source: `src/librx8.cpp`, commit 5c784ec)

| Element | Community (ConnorRigby) | Ours (VERIFIED) | Equal? |
|---|---|---|---|
| LFSR type | 24-bit Galois | 24-bit Galois | ✅ |
| Init state | `0xc541a9` hardcoded | `0xC541A9` (level-1 entry, ROM table @0x5FAC8) | ✅ |
| Taps | mask `0xEF6FD7` clears {3,5,12,15,20}, feedback OR into bit 23 ⇒ bits {23,20,15,12,5,3} = `0x909028` | `0x909028` (hardcoded in ROM @0x56C1E-0x56C38) | ✅ |
| Phase-1 input (32 bits, LSB-first) | `or_ed_seed` = seed[0] \| seed[1]<<8 \| seed[2]<<16 \| secret[0]<<24 | `w1` (same packing) | ✅ |
| Phase-2 input (32 bits, LSB-first) | `secret[4]<<24 \| secret[3]<<16 \| secret[2]<<8 \| secret[1]` | `w2` (same packing) | ✅ |
| Clocks | 32 + 32 = 64 | 64 (stream = seed[0..2]+secret[0..4]) | ✅ |
| Secret | `MAZDA_KEY_SECRET {0x4d,0x61,0x7a,0x64,0x41}` = "MazdA" | "MazdA" (ROM @0x5FAC0) | ✅ |
| Key extraction | `b0,b1,b2` nibble interleave, returned `[b2,b1,b0]` | nibble interleave `[b2,b1,b0]` | ✅ |
| Seed format | 3 bytes (`SEED_LENGTH=3`, asserts `length == SEED_LENGTH+1`) | 3 bytes (`seed_gen` → D211..D213) | ✅ |
| SendKey subfunc | `MAZDA_SBF_CHECK_KEY 0x02` | run-mode handler: subfunc 0x02/0x04 SendKey body dead in this build (see REQUEST_SEED_EVIDENCE); `seed_key_related` used with level | ⚠️ stage difference |
| Sessions | `10 81`/`10 85`/`10 87` | `10 81`/`10 85` documented; session-0x87 gating matches rnd-ash | ✅ |
| NRC | {0x22 cond-not-correct, 0x35 invalid-key, 0x36 exceeded-attempts} (UDS.cpp) | {0x22, 0x31, 0x35} literals in handler body; 0x22/0x35 in dead SendKey body; 0x31 on position_check/key_validate fail | ⚠️ handler-level (see §5) |

The C++ inline LFSR formula was decoded and transcribed 1:1 into
`tools/tests/test_cross_seedkey.py::community_clock()` (original source kept in the docstring);
`community_calculateKey()` reproduces `calculateKey()` exactly.

## 3. Vectors and results (run: `python3 tools/tests/test_cross_seedkey.py`)

| Case | Count | Ours vs community | vs ROM-verified |
|---|---|---|---|
| LFSR clock equivalence (`_clock` vs `community_clock`, random state+bit) | 100 000 | 0 mismatches | — |
| ROM-verified level-1 vectors (init 0xC541A9): seeds 45820A, CBFED4, 123456 | 3 | 3/3 match | 3/3 → A07258, 75491A, 86CA06 |
| ROM reference model levels 1-4 (per-level init table @0x5FAC5) | 12 | (community is level-1 fixed init — not comparable at L2-4) | 12/12 |
| Fixed pseudo-random seeds (RNG seed 0xC541A9) | 400 | 0 mismatches | — |
| Live capture seed **0x464E7F** | 1 | both → **0xFAFDD8** | — |

## 4. Analysis

**Verdict: CONFIRMED-CROSS.** Both implementations compute the **same transformation** on every input: 24-bit Galois LFSR, init `0xC541A9`, taps `0x909028` (bits {23,20,15,12,5,3}), 64 clocks over the LSB-first stream `seed[0..2] + "MazdA"`, nibble-interleave key extraction returned as `[b2,b1,b0]`.

- **Stage coverage:** both implement the **key-computation** stage only (our `seed_key_related` @0x56ADA; community `calculateKey`). Seed **generation** stays on the ECU in both models: community `getSeed()` just copies the 3 bytes of `67 01 s0 s1 s2`; our `seed_gen` @0x5699A models the ECU's own entropy loop (counter XOR / 0x55-AA-55 sentinel / level-3 FF-FF-FF), verified against ROM. So: **request-seed = ECU (unmodeled on the community side), key = identical in both.**
- **No divergence** in taps, endianness, init state, iterations, or extraction — bit-identical (0 divergent cases out of 100 000 + 400 + 3 + 1).
- **Capture 0x464E7F:** both compute key **0xFAFDD8**. The capture carries only the seed (no key), so it cannot *discriminate* the two implementations — but it's a live-ECU input on which they agree, and it fixes an expected `27 02 FA FD D8` for a future live capture (ECU_CAPTURE_PLAN.md). NOTE: observed on the **ICM** (0x720→0x728), same platform diag stack, not the PCM (0x7E0→0x7E8); the PCM is expected to use the same transform (same ROM family, same secret/LFSR data verified in 9 images).

## 5. Nuances kept on record (not transform divergences)

- **Levels 2-4:** the ROM uses a per-level init table (@0x5FAC5: level1 C5 41 A9, level2 A3 95 82, …).
  Community hardcodes level-1 `0xc541a9`; our `compute_key` is likewise fixed-init. Only our
  ROM-derived reference model covers levels 2-4 (12/12). The transform core is the same; only the
  INIT state differs per level.
- **NRC:** community sees {0x22, 0x35, 0x36} in its working diag/programming-session path (0x81/0x85
  + bootloader). Our run-mode handler body contains literals {0x12, 0x31, 0x22, 0x35}; 0x22/0x35 live
  in the **dead** SendKey body in this build, and 0x31 is the run-mode reject (position_check /
  key_validate fail). This is a handler/session-level difference, not a key-transform difference —
  consistent with the community tool working outside the normal run-mode handler.
- **"MazdA" XOR?** No XOR constant: the secret is fed as an LFSR input stream (byte 0 in phase 1,
  bytes 1-4 in phase 2), not XORed with the seed.

## 6. Implications for the abstract C

- `c/security_access.c::seed_key_related` / `tools/mazda_security.py::compute_key` are **confirmed by
  an independent third-party implementation** (no shared ancestry: community ported the C++ from the
  same ROM family independently and it is byte-identical on all tested inputs).
- The abstract C needs no change. `lfsr_clock`'s taps constant `0x909028` and init `0xC541A9`
  (level 1) are double-confirmed (ROM disassembly + community source).
- A future live PCM capture `27 01` → `67 01 <s0 s1 s2>` → `27 02 <k0 k1 k2>` can now be validated
  end-to-end against the expected key (both implementations agree on every seed).

## 7. References

- Community source: https://github.com/ConnorRigby/rx8-ecu-dump · `src/librx8.cpp` `calculateKey`,
  `src/librx8.h` (`MAZDA_KEY_SECRET`, `SEED_LENGTH`, subfuncs 0x01/0x02), `src/UDS.cpp` (NRC map),
  commit `5c784eccd5d399c8593cecd13a6fcf0dcd973ae1` (main, v0.9.0, 2022-11-05).
- Live capture seed: rnd-ash wiki `27 01` → `67 01 46 4E 7F` — cited in `docs/notes/ECU_CAPTURE_PLAN.md` §7.1.
- Our verified tests: `c/tests/test_security_access.py` (12/12 ROM vectors, ROM_VECTORS table;
  compute_key level-1), `c/tests/test_seed_gen_5699A.py` (seed_gen, 0 mismatches),
  `tools/mazda_security.py` (provenance + 400 random seeds).
- Artifact: `tools/tests/test_cross_seedkey.py` (this cross-validation).
