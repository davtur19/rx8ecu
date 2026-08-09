# Fix `xtrct` in `tools/sh2emu.py` — APPLICATO ✅
**Stato:** la patch `reconstructed/samples/tests/fix_xtrct.patch` applicata a
`tools/sh2emu.py` (riga 274) e verificata.

- `tools/sh2emu.py`: semantica corretta `XTRCT`.
- `tools/tests/test_emulator_families.py:348`: `0xCCDD1234` → `0x5678AABB`.
- `test_emulator_families.py`: **83 checks, 0 failures, exit 0**.
- `run_all_verify.py --with-slow`: **RESULT: ALL OK** (31 harness, 0 falliti, 0 mismatch, exit 0). Vedi `VERIFY_SUMMARY.md`.
- Monkeypatch `xtrct` negli harness: rimasti (ridondanti ma innocui, semantica identica al fix).
---
## 1. Il bug
`tools/sh2emu.py`, `SH2._exec`, **riga 270**, gruppo opcode `0x2xxx`:
```python
# ATTUALE (SBAGLIATA):
if nib == 0xD: r[n] = ((r[n] << 16) | (r[m] >> 16)) & MASK; return  # xtrct

# CORRETTA (nella patch):
if nib == 0xD: r[n] = ((r[m] << 16) | (r[n] >> 16)) & MASK; return  # xtrct
```
La decodifica (`n = (op >> 8) & 0xF`, `m = (op >> 4) & 0xF`) è già giusta
(`XTRCT Rm,Rn` = `0010nnnnmmmm1101`). È **solo** il corpo ad avere i ruoli dei
registri **invertiti tra i due shift a 16 bit**.
## 2. Semantica ufficiale (confermata)
**Renesas SH-2E Software Manual, Rev. 2.00 (REJ09B0316-0200), §7.2.68 XTRCT:**
"Extracts the middle 32 bits from the 64 bits of coupled general registers Rm
and Rn, and stores the 32 bits in Rn."
```
Operation:
  temp = (R[m] << 16) & 0xFFFF0000;
  R[n] = (R[n] >> 16) & 0x0000FFFF;
  R[n] |= temp;

Esempio del manuale:
  XTRCT R0,R1 ; R0=H'01234567 R1=H'89ABCDEF  ->  R1 = H'456789AB
```
In formule: `R[n] = ((R[m] << 16) & 0xFFFF0000) | ((R[n] >> 16) & 0x0000FFFF)`.

**Corroborazione — gcc 3.4.6** (`config/sh/sh.md`, commento: "patterns found
in expansions of DImode shifts by 16"):
```scheme
(define_insn "xtrct_left"   ... (ior (ashift op1 16) (lshiftrt op2 16))
  "xtrct %1,%0")   ; op0 (=dest) == op2
(define_insn "xtrct_right"  ... (ior (lshiftrt op1 16) (ashift op2 16))
  "xtrct %2,%0")   ; op0 (=dest) == op1
```
Stessa semantica: shift-left da **Rm**, shift-right da **Rn**.
## 3. Verifica
1. **Prova numerica**: per `0x240D` = `xtrct r0,r4` con `r0=0x12345678`,
   `r4=0xAABBCCDD`: attuale → `0xCCDD1234` (SBAGLIATO); corretto →
   `0x5678AABB` ✓. (`test_emulator_families.py:348` asseriva `0xCCDD1234`;
   aggiornato a `0x5678AABB` — ora passa.)
2. **Gap già noto**: `tests/verify_gcc346.py` (righe 81-100) monkeypatcha
   `SH2._exec` con la stessa formula (`_xtrct_fixed`); il fix è la *promozione*
   di quel monkeypatch in `sh2emu.py`.
3. **Codegen gcc 3.4.6**: `rx8_multiply32_saturating` (`-m2e -O1
   -fomit-frame-pointer`) emette `0x2??D` (`xtrct`) per lo shift-right a 64 bit
   (`product >> 16`); i percorsi ROM NON eseguono mai `xtrct` → la ROM fa da
   oracolo, il blob esercita l'istruzione.
4. **Patched senza monkeypatch** (§5): ROM-vs-blob-vs-oracolo-host = **0
   mismatch su 2012 casi** (12 edge + 2000 random seed `0x231C`); controllo
   negativo (semantica sbagliata reinstallata) → mismatch > 0.
## 4. Applicazione
```bash
cd /home/davide/ailocal/rx8ecu
patch -p1 < reconstructed/samples/tests/fix_xtrct.patch   # applicato pulito
git diff tools/sh2emu.py                                   # ispezione
```
2026-08-03 con `patch -p1` (hunk con fuzz 2, offset 4 righe, per la modifica
float preesistente). **Unico file toccato: `tools/sh2emu.py`** (riga 274).
**Test aggiornato (già fatto):**
```bash
tools/tests/test_emulator_families.py:348
    check(cpu.r[4] == 0x5678AABB, ...)   # era 0xCCDD1234 (buggato)
```
## 5. Test
```bash
python3 tools/tests/test_emulator_families.py   # 83 checks, 0 failures, exit 0
cd reconstructed/samples
python3 tests/run_all_verify.py --with-slow --json tests/_verify_aggregate.json
#   RESULT: ALL OK (31 harness, 0 falliti, 0 mismatch, exit 0)
```
**Monkeypatch ridondanti**: ora che `sh2emu.py` è corretto, i `_xtrct_fixed`
negli harness (verify_gcc346, verify_gcc346_fast, fuzz_14funcs, verify_bitfield,
verify_bytepack, verify_cross_rom, verify_float_a, verify_idxtable_all) sono
semanticamente identici al fix → innocui. Nessuno rimosso; run completo 0 mismatch.
Rimozione = pulizia futura, non bloccante.

**Verifica "senza monkeypatch"**: con `verify_gcc346.py` che applica
`SH2._exec = _xtrct_fixed`, il ramo `xtrct` veniva intercettato prima
dell'emulatore. Per provare che la patch regge da sola:
```python
# dopo l'import di verify_gcc346:
verify_gcc346.SH2._exec = verify_gcc346._SH2_exec_orig   # nativo, niente patch
```
oppure il mini-test in `/tmp` — `bash /tmp/opencode/xtrct/run_mini_test.sh`
(patched: 0 mismatch / buggy: mismatch).
Il mini-test copia `sh2emu.py` in `/tmp`, applica la patch, ricompila il blob
gcc-3.4.6 di `rx8_multiply32_saturating` e confronta ROM vs blob vs oracolo host
con **2000 vettori random seed 0x231C + 12 edge**, senza monkeypatch.
