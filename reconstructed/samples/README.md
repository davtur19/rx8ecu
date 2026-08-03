# Reconstructed Source Samples — RX-8 PCM (SH7055)

Questo progetto è un **campione dimostrativo** di "reconstructed source": il codice
C **astratto, idiomatico e leggibile** che *sarebbe stato* il sorgente originale
del firmware Mazda/Denso, ricostruito a partire dai lift verificati del progetto
`rx8ecu` e **dimostrato equivalente alla ROM** funzione per funzione.

Non è decompilazione istruzione-per-istruzione (quello è `c/`), né assembly
byte-exact (quello è `src/`): è un modello C leggibile, scritto con nomi
significativi, costanti nominate, strutture dati e un register-map condiviso,
**vincolato a mantenere lo stesso comportamento della ROM** per ogni input
possibile.

```
src/  (assembly annotato, byte-exact, rebuild con rom_rebuild.py)   ← LA VERITÀ
c/    (decompilazione C istruzione-per-istruzione, verificata con sh2emu.py)
reconstructed/samples/  (C astratto "come il vero sorgente", verificato  ← QUESTO
                    con lo stesso emulatore sui lift di c/)
```

---

## 1. Come si relaziona alla build byte-exact

| Livello | Cosa è | Ruolo |
|---|---|---|
| `src/60E1D400_annotated.s` | Assembly della ROM, riassemblato byte-exact da `tools/rom_rebuild.py` | **Verità di riferimento**. Se un modello C diverge, vince l'assembly. |
| `c/` | Lift C istruzione-per-istruzione (track A/B), verificati contro la ROM via `tools/sh2emu.py` | **Fonte di derivazione** di questo progetto. |
| `reconstructed/samples/` | C astratto e leggibile, derivato dai lift, con stesso comportamento | **Modello leggibile verificato** — non byte-identico. |

Il "match-and-compile" (rendere questo C anche *byte-identico* alla ROM
compilandolo con un compilatore SH-2E) è l'**evoluzione futura**, già
abbozzata in `reconstructed/experiments/match/` (fingerprinting del compilatore sul
prologo/epilogo e sulle istruzioni distintive della ROM). Il lavoro in questo
sottoprogetto è il prerequisito: prima di chiedere a un compilatore di riprodurre
byte-identico un pezzo di firmware, quel pezzo deve esistere come C pulito e
comportamentalmente corretto.

---

## 2. Campioni inclusi

| Reconstructed name | ROM @ `60E1D400` | Lift di provenienza (`c/`) | Harness |
|---|---|---|---|
| `rx8_add_s32_saturate` | `0x2304` | `addS32Saturate.c` (IDA mislabeled `fpu_compare_float`) | `tests/harness_add_s32.py` |
| `rx8_immo_seed_mixer` | `0x366B8` | `seed_mixer.c` (IDA-ai `bitwise_field_encoder_366B8`) | `tests/harness_seed_mixer.py` |
| `rx8_index_table_clear/step/step2/dec` | `0x68780` / `0x6879C` / `0x687C8` / `0x687F4` | `idx_table_helpers_68780.c` | `tests/harness_idx_table.py` |

Perché questi tre:

- **`rx8_add_s32_saturate` (0x2304)** — il classico helper di aritmetica
  saturante. Mostra come un'istruzione SH-2 (`addv`) diventi un idioma C
  portabile e ben definito, con le due clausole di saturazione che replicano
  esattamente il ramo di overflow della ROM.
- **`rx8_immo_seed_mixer` (0x366B8)** — primitiva crittografica
  dell'immobilizer. Mostra come una sequenza di bit-twiddling "magico" venga
  organizzata in passi nomati, costanti (`MIX_SWAP_LO`, `MIX_SWAP_HI`,
  `MIX_KEEP`, `MIX_FOLD_*`) e commenti sul *perché* (anti-replay),
  mantenendo intatta ogni singola operazione della ROM.
- **`rx8_index_table` (0x68780 family)** — famiglia di helper su tabella
  RAM indicizzata. Mostra l'uso di una **struttura dati** (`rx8_index_slot_t`),
  il register-map condiviso e la documentazione onesta di un valore magico
  non spiegato (`0x0464`, *unknown, matches ROM*), oltre al caveat reale
  dell'aritmetica puntatore a 32 bit che wrappa per indici ≥ 9.

---

## 3. Criteri di stile adottati

1. **Header di ogni funzione/file** con: nome, indirizzo ROM, ROM di
   provenienza, stato (`VERIFIED — behavioural equivalence …`), e il link al
   lift in `c/` che è la fonte di verità.
2. **Nomi significativi** e costanti nominate (nessun numero magico in corpo:
   quando il valore non è spiegato dalla documentazione resta comunque una
   costante con nota `unknown, matches ROM`).
3. **Register map tipizzato** in `include/rx8_hw.h` — *solo* indirizzi
   documentati (con la fonte citata); ciò che non è documentato resta un
   puntatore esplicito nel codice campione con nota.
4. **Strutture dati** dove serve (`rx8_index_slot_t`, tipi espliciti
   `int32_t`/`uint16_t`/… per replicare le semantiche SH-2).
5. **Niente `goto`** salvo dove semanticamente necessario (nei campioni non
   ve ne è alcuno); loop/if naturali.
6. **Equivalenza comportamentale come legge**: non si "sistema" la semantica
   per renderla più elegante. Esempio reale: lo step 4 di `seed_mixer` è
   `(y << 21) | (y >> 3)`, un *fold*, non una rotazione standard — è stato
   preservato verbatim e documentato.
7. **Aritmetica bit-width esplicita**: operandi unsigned a 32/16/8 bit, cast
   espliciti, per replicare il comportamento del core SH-2E (wrap, zero/sign
   extension) anche su host little-endian a 64 bit.

---

## 4. Come si esegue / rigenera la verifica

Prerequisiti: `python3` con `tools/sh2emu.py` (nel repo, già in `sys.path`),
`cc` di sistema (host, nessun cross per l'equivalenza), ROM
`roms/stock/60E1D400.bin` (sola lettura).

```sh
# dall'interno di reconstructed/samples/
make build        # compila i sorgenti + l'oracolo host in /tmp/opencode
make test         # esegue i tre harness di equivalenza
make verify       # alias di test
make clean        # rimuove gli artefatti in /tmp/opencode
```

Oppure singolarmente, con N personalizzabile (default: 100000 / 20000):

```sh
python3 tests/harness_add_s32.py 100000
python3 tests/harness_seed_mixer.py 100000
python3 tests/harness_idx_table.py 20000
```

### Come funziona un harness (pattern Track-A, identico a `c/tests/verify_emu.py`)

1. compila i sorgenti reconstructed + `tests/host_oracle.c` con il `gcc` di sistema;
2. genera **N input random** (seed fisso, riproducibile) + vettori edge;
3. **simula la funzione sulla ROM** con `tools/sh2emu.py` (`cpu.call(entry, …)`)
   sugli stessi input;
4. **esegue il C astratto** sugli stessi input via oracolo host;
5. **confronta i risultati** — è richiesto il 100% di corrispondenza.

Per le funzioni su RAM (`rx8_index_table`) l'harness confronta gli **effetti
collaterali** (le tre word di slot) invece del valore di ritorno, seminando la
RAM nel dict sparso dell'emulatore e mappandola con `mmap(MAP_FIXED)` sul
host (stesso trucco dei companion `c/tests/test_*_49ED0.c`).

### Esito registrato (2026-08-01)

```
OK  addS32Saturate         host-C == emulated ROM @0x2304  (100000 random + 13 edge)
OK  seed_mixer             host-C == emulated ROM @0x366B8  (100000 random + 12 edge)
OK  idx_table family @0x68780 (clear/step/step2/dec)  (20000 random + 87 edge)
        + wrap pins (indici 9/0x7F/0xFF) verificati emulator-only
```

---

## 5. Validazione toolchain era-ROM (gcc 3.4.6)

Chiude sul **piano comportamentale** il cerchio
"ROM → C astratto → toolchain era-ROM (sh-elf **gcc 3.4.6**)". Non si
pretende byte-identità; si dimostra che lo **stesso** C astratto, compilato con
il compilatore dell'epoca (`-m2e -O1 -fomit-frame-pointer`,
`/home/davide/gcc346-build/gcc/xgcc`, binutils di sistema
`/usr/bin/sh-elf-*`), si comporta **identicamente** ai byte della ROM funzione
per funzione, nello **stesso** emulatore `tools/sh2emu.py`.

### Metodo

Per ogni funzione di `tests/verify_gcc346.py::FUNCS`:

1. si creano una volta gli stub minimi `stdint.h` / `math.h` in
   `/tmp/verify_gcc346/inc` (il gcc 3.4.6 è configurato `--without-headers`);
2. si compila il sorgente `src/rx8_*.c` con la recipe
   `-m2e -O1 -fomit-frame-pointer` (`-m2e` per l'FPU con singola precisione);
3. si linka a base fissa `0x4000` con un linker script banale, tirando dentro
   gli helper `libgcc.a` 3.4.6 (`___sdivsi3`/`___udivsi3`/`___ashlsi3`/
   `___lshrsi3`/`___ashrsi3`/`___ashiftrt_r4_8`) a cui le famiglie intere L-2
   (div/shift) compilano — il core SH-2E non ha divisione hardware né shift a
   conteggio variabile;
4. `sh-elf-objcopy --only-section=.text` estrae un blob di solo codice;
5. il blob viene caricato nel dict `ram` sparso dell'emulatore a `0x4000`;
6. si generano **N vettori seedati** (resi in `make_rng`) + un piccolo set di
   edge per le funzioni a saturazione/bordo;
7. si esegue la **ROM reale** a `ADDR_ROM` e il **blob gcc-3.4.6** a `0x4000`
   sugli stessi vettori e si confrontano `r0` (per `float` anche i registri
   `fr`; per la famiglia RAM gli effetti collaterali dello slot);
8. dove un oracle host è disponibile (`tests/oracle_*.c`, `host_oracle.c`) si
   confronta anche **host-C vs blob**.

### Comando

```sh
cd reconstructed/samples
python3 tests/verify_gcc346.py          # N default per funzione
make verify-gcc346                       # target Makefile (stesso runner)
```

### Esito (2026-08-03) — set pure-math completo

Le righe Lotto 1 (i 13 leaf a Lotto 1 + la famiglia `index_table`) sono state:
via `verify_gcc346.py` / `verify_gcc346_fast.py`, re-fuzzate con `fuzz_14funcs.py` (TARGET_N `100000`/funzione) e coperte anche dagli sweep exhaustive
`verify_complement_exhaustive.py` (~tutti i valori `u16` per le rutine complemento).
Le righe Lotto 2 coprono tutte le nuove funzioni float/interp/memcpy/div-mod/fixed-point registrate dai
`verify_*.py` in `tests/` (ognuna con semplici edge + random seedato). **0 mismatch su tutte.**

| Funzione | ROM @ | tipo | harness | n_test | mismatch |
|---|---|---|---|---|---|
| `rx8_add_s32_saturate` | 0x2304 | int32×2→r0 | verify_gcc346 / fuzz_14funcs | 4000 | 0 |
| `rx8_immo_seed_mixer` | 0x366B8 | uint32×2→r0 | verify_gcc346 / verify_immo_exhaustive | 4000 | 0 |
| `rx8_add16bit_saturate` | 0x2460 | u16×2→r0 | verify_gcc346 | 4000 | 0 |
| `rx8_add_saturate_8bit` | 0x2478 | u8×2→r0 | verify_gcc346 | 4000 | 0 |
| `rx8_multiply32_saturating` | 0x231C | int32×2→r0 | verify_gcc346 | 20000 | 0 |
| `rx8_complement_shift_u16` | 0x2430 | u16→r0 | verify_gcc346 / complement_exhaustive | 4000 | 0 |
| `rx8_complement_shift_u32` | 0x2440 | fr4/fr5/fr6→r0 | verify_gcc346 / complement_exhaustive | 4000 | 0 |
| `rx8_complement_shift_u8` | 0x2420 | u8→r0 | verify_complement_exhaustive | 4000 | 0 |
| `rx8_index_table` (clear/step/step2/dec) | 0x68780 | family RAM (idx→slot) | verify_gcc346 / verify_idxtable_all | 5000 | 0 |
| `rx8_div32_signed` | 0x3FE8 | r0/r1→r0 (div, wrap su INT32_MIN/-1) | verify_gcc346 | 4000 | 0 |
| `rx8_div32_unsigned` | 0x409C | r0/r1→r0 (div) | verify_gcc346 | 4000 | 0 |
| `rx8_shift_left_logical` | 0x4308 | r0/r1→r0 (shl, cnt clamp) | verify_gcc346 | 4000 | 0 |
| `rx8_shift_right_arithmetic` | 0x43C8 | r0/r1→r0 (sra, cnt clamp) | verify_gcc346 | 4000 | 0 |
| `rx8_shift_right_logical` | 0x44E0 | r0/r1→r0 (srl, cnt clamp) | verify_gcc346 | 4000 | 0 |
| `rx8_shift_right_8` | 0x467A | r0→r0 (sra 8) | verify_gcc346 | 4000 | 0 |
| `rx8_manifold_pressure_error_10A88` | 0x10A88 | int Q16.16→r0 | verify_10A88 | 4000 | 0 |
| `rx8_set_register_reg_bit_val` | 0x4BBC | ptr RAM-cell→r0 | verify_setregbit | 3000 | 0 |
| `rx8_memcpy_bytewise` | 0x42B0 | ptr (void, non-ABI)→dst | verify_memcpy | 3000 | 0 |
| `rx8_checksum_complement_add` | 0x2034 | ptr (u16)→r0 | verify_checksum | 4000 | 0 |
| `rx8_invert_and_return_8bit` | 0x2044 | ptr (u8)→r0 | verify_invert8 | 3000 | 0 |
| `rx8_bytepack8` (converter) | 0x552FE | ptr (u8)→r0 | verify_bytepack | 3000 | 0 |
| `rx8_bytepack16` (inverter) | 0x5530C | ptr (u16)→r0 | verify_bytepack | 3000 | 0 |
| `rx8_delay_loop_n8` | 0x239C | int (u16)→r0=0 | verify_delayloop | 3000 | 0 |
| `rx8_first_order_filter` | 0x23B0 | float (IIR+deadband)→fr0 | verify_firstorder | 4000 | 0 |
| `rx8_min_value` | 0x23F4 | float→fr0 | verify_float_a / verify_saturates2 | 4000 | 0 |
| `rx8_saturate` | 0x2404 | float→fr0 | verify_float_a / verify_saturates2 | 4000 | 0 |
| `rx8_saturate_low` | 0x23E4 | float→fr0 | verify_float_b / verify_saturates2 | 3000 | 0 |
| `rx8_subtract_absolute` | 0x23DC | float→fr0 | verify_float_b / verify_saturates2 | 3000 | 0 |
| `rx8_float_to_int` | 0x24D0 | float (ftrc)→r0 | verify_float_b | 3000 | 0 |
| `rx8_float_to_fp_16bit` (fp16) | 0x24C0 | float (esaustivo u16×4)→fr0 | verify_float_fp16 | 20000 | 0 |
| `rx8_interpolate_u8` | 0x26B0 | table u8 (i,t)→fr | verify_interp8 | 3000 | 0 |
| `rx8_interpolate_u16` | 0x26D0 | table u16 (i,t)→fr | verify_interp16 | 3000 | 0 |
| `rx8_interpolate_s8` | 0x26F4 | table s8 (i,t)→fr | verify_interp_s8 | 3000 | 0 |
| `rx8_interpolate_s16` | 0x2690 | table s16 (i,t)→fr | verify_interp_s16 | 3000 | 0 |
| `rx8_interpolate_f32` | 0x2678 | table f32 (i,t)→fr | verify_interp_f32 | 3000 | 0 |
| `rx8_data_lookup` | 0x2624 | table f32 (i,t)→r0/fr0 | verify_datalookup | ~1000 | 0 |
| `rx8_bitfield_extract_merge` | 0x48C8 | float→r0 + RAM buf | verify_bitfield | 3000 | 0 |
| `rx8_float_to_fixed_16bit` | 0x2490 | float→fixed16 | verify_mathprims | 4000 | 0 |
| `rx8_fixed_point_to_float_8bit` | 0x2500 | fixed8→float | verify_mathprims | 4000 | 0 |
| `rx8_fixed_point_scaling` | 0x2510 | int (frac) | verify_mathprims | 4000 | 0 |
| `rx8_math_min_max_49ed0` | 0x49ED0 | RAM (flag)→r0 | verify_saturates2 | 4000 | 0 |

**Nota**: `verify_gcc346_fast.py` è lo stesso set Lotto 1 in parallel (multiprocessing),
`verify_idxtable_all.py` copre l'intera famiglia `0x68774..0x68820` (wrapper `clr`,
`clear/step/step2/dec` + `step3` extra). `verify_cross_rom.py` re-verifica `immo_seed_mixer`
e `idx_table` su altre ROM (spostate del prologo) — 0 mismatch.

**Totali**: **44 funzioni distinte validate** (17 leaf Lotto 1 — incl. i 4 leaf
`index_table` — + 27 Lotto 2), somma vettori (default di `n_test`, solo i
`verify_*`) **≈179k confronti**, `0 mismatch` su tutte. Con le sweep exhaustive
(`u16` reverse/complement, `raw` u16 ×4 per fp16, `immo` su 2^16 key_word × seed
specifici) e i fuzz (`fuzz_14funcs` 100k/funzione, `fuzz_l2` 50k/funzione) il
volume reale supera largamente il mezzo milione — **claim: set pure-math completo
a 0 mismatch.**

### Semantica documentata (note riepilogo)

- **`0x10A88` Q16.16**: `d = b-a; return d > -0x1E0000 ? d : d+0x01680000` (deadband
  -30°..360° del MAP error diff, fix-point a 16 bit di frazione).
- **Complemento**: famiglie 8/16/32-bit "value+ones-complement" pack; 0x2440 usa
  convenzione float `fr4/fr5/fr6`→`r0`.
- **`rx8_data_lookup` (i,t)**: lookup 2D con interpol su array f32 in RAM; firma
  non-ABI `r0=n, r1=axis, fr0=x`→`r0=idx, fr0=t`.
- **`rx8_memcpy_bytewise`**: `void` non-ABI (copia bytewise, src/dst su reglist
  interni così come chiamata dalla ROM `0x44B0` in linea).
- **`rx8_first_order_filter` (0x23B0)**: IIR a 1 polo + deadband single-precision,
  confronto `flds/sts/and` sul pattern `0x7F800000` (con robustezza a finiti).
- **`fp16` (0x24C0)**: `raw & 0xFFFF → (float)raw` poi `fmac = mult*raw+off`; harness
  esaustivo su **tutti i 65536 valori `u16` di `raw` × 4 coppie (mult,off)** (~262k
  vettori sweep) + edge canonici e random seedato.
- **div/mod**: `div32_signed` wrap su `INT32_MIN/-1`→INT32_MIN; `mod32_signed`
  `B==0` → diag `0x44E` su `0xFFFF7304`; `INT_MIN % −1 → 0` (wrap, come la ROM).

### Nota: convenzione non-ABI delle funzioni L-2 (r0/r1)

Le nuove funzioni (`rx8_div32_*`, `rx8_shift_*`) sono chiamate dalla ROM con
**convenzione non-standard**: operandi in `r0`/`r1`, risultato in `r0` (sono
codice leaf; la convention è documentata in `docs/functions/*.md`). Il lato
ROM viene quindi pilotato con un driver dedicato (`call_regs` nell'harness,
lo stesso stub già usato da `harness_div32_signed.py` / `harness_shift_right_8.py`),
mentre il **blob gcc-3.4.6** dello stesso C usa l'ABI standard `r4/r5` ed è
pilotato da `cpu.call(r4=, r5=)`: due convenzioni di ingresso diverse, stessi
input semantici, confronto su `r0`.

### Nota: workaround di un gap dell'emulatore (`xtrct`)

Durante la validazione è emerso un **bug di `tools/sh2emu.py`** nell'istruzione
`xtrct`: i due shift hanno i ruoli dei registri di origine/destinazione
invertiti. I percorsi ROM di *queste* funzioni non eseguono mai `xtrct`, ma il
gcc 3.4.6 lo emette per lo shift-right-a-64-bit / estrazione di
`rx8_multiply32_saturating`, quindi il lato blob ne ha bisogno. L'harness
**monkeypatcha** il metodo `SH2._exec` (applicandolo una volta, prima di
qualsiasi chiamata, su entrambi i lati) con la semantica corretta dal
reference manual Renesas SH-2 (`0010nnnnmmmm1101`, destinatario n = bit 11-8):

```
R[n] = ((R[m] << 16) & 0xFFFF0000) | ((R[n] >> 16) & 0x0000FFFF)
```

La correzione va **promossa in `tools/sh2emu.py`** (fuori dall'ambito di
questo file), così da non dipendere dal patch dell'harness.

### Limiti
- Il set validato è **composizione di funzioni pure** (leaf + poche rutine con
  side-effect RAM deterministico: `index_table`, `setregbit`, `math_min_max`,
  `memcpy`, `bytepack`, `checksum`/`invert` su buffer). Le funzioni con
  **stato/MMIO/loop lungo** (check `float_validity` @0x46CC, delayloop sui
  domain estremi `n→0xFFFF`) sono coperte solo nei limiti d'emulatore: per
  `delay_loop_n8` il domain `.eff` è `0..0xFFFF`, mentre valori `≥0x10000`
  sarebbero runaway (il blob tronca, la ROM gira all'infinito) → gestiti
  solo lato emulatore con budget di step.
- La firma `float` usa la convenzione ROM `fr4/fr5/fr6`; il confronto del
  valore è su `r0` (ritorno int/uint delle funzioni validate) o sui registri
  `fr` per le leaf che restituiscono float (`first_order_filter`, `min_value`,
  `saturate`, `interp_*`, `fixed_point_to_float`).
- Gli artefatti del builder (`blob bin`, `.o/.elf`, oracoli host) vanno in
  `/tmp` e **non** sono committati.

---

## 6. Problemi aperti e limiti noti

- **`rx8_index_table`: scopo della tabella e soglia `0x0464` sconosciuti**
  (match ROM). Stride `0x46C` suggerisce slot grandi usati da altro codice non
  ancora ricostruito.
- **`rx8_immo_seed_mixer` step 4**: il *fold* `(y << 21) | (y >> 3)` non è una
  rotazione standard; il perché è ignoto (match ROM). La funzione è verificata
  come funzione pura; l'intero flusso dell'immobilizer
  (`ImmoKeyExpander_365D6`, `ImmoGetSeed_3664E`) non è ri-simulato qui.
- **Indici `≥ 9` nella tabella**: l'aritmetica puntatore a 32 bit wrappa sotto
  `mmap_min_addr` sul host → verificati solo lato emulatore. Uso realistico:
  indici 0..8 (match della nota FINDINGS).
- **Endianness**: il target è big-endian, il host little-endian. Gli harness
  confrontano *valori numerici* (le word vengono scritte/lette con lo stesso
  layout), quindi l'equivalenza è dimostrata; una futura build byte-exact dovrà
  gestire l'accesso BE esplicito.
- **Nomi IDA-ai** (`fpu_compare_float`, `bitwise_field_encoder_366B8`,
  `obd_service_handler_68780`) sono etichette auto-generate, spesso fuorvianti;
  nei campioni valgono i nomi reconstructed + gli indirizzi ROM.

## 7. Prossimo passo — stato chiuso

Il **cerchio comportamentale** della toolchain era-ROM è **chiuso** per tutto il
set pure-math (sezione 5): il C astratto, compilato con `gcc 3.4.6`
(`-m2e -O1 -fomit-frame-pointer`), è equivalente ai byte della ROM nello stesso
emulatore per **44 funzioni distinte, ≈179k confronti default, 0 mismatch**
(claim §5). Sono saliti a bordo: i leaf float/saturate (saturates2, float_ab),
le interpolazioni u8/u16/s8/s16/f32, la famiglia fixed-point `0x2490/0x2500/0x2510`,
`fp16` 0x24C0 (esaustivo), `data_lookup`, `memcpy`, `div/mod` signed, e le rutine
pointer/RAM (`bytepack`, `checksum`, `invert`, `setregbit`, `bitfield`,
`math_min_max`, `index_table` a Lotto 1).

Punti residui noti (stato aperto):

1. **Fix `xtrct` (emulatore) APPLICATO (commit `099bf8b`)**: il bug a ruoli
   invertiti in `tools/sh2emu.py` è corretto (`R[n] = (R[m]<<16) | (R[n]>>16)`),
   con `tools/tests/test_emulator_families.py:348` aggiornato (83 checks, 0
   failure). I monkeypatch `xtrct` rimasti sugli harness sono ridondanti ma
   innocui.
2. **Stabilità della ROM a 9 multi-step**: il multi-step a 9 è ancora da
   stabilizzare (note in `docs/`), non rientra in questo README.
3. **`rx8_check_float_validity` @0x46CC resta esclusa** dal set: la ROM non è
   una foglia — prima del check esegue la pipeline float→fixed 0x48C8→0x4740→0x481C
   e scrive RAM a 0xFFFF768C, mentre il C è un branch-through puro
   (divergenza documentata da `harness_check_float_validity.py`).
4. **Integrare il CI**: `make verify-gcc346` nel gate di regressione (richiede
   i binari `gcc 3.4.6` + `sh-elf` binutils presenti sull'host).
5. Chiusura del **match-and-compile byte-exact**: usare il fingerprinting
   (`reconstructed/experiments/match/scripts/fingerprint.py`) per tarare
   un `sh-elf-gcc` che produca le stesse sequenze byte della ROM (`0x2304`,
   `0x366B8`, `0x68780` family). Ora che la correttezza comportamentale è
   dimostrata su questa catena, le differenze byte esatte diventano la prossima
   lista da rifinire.
