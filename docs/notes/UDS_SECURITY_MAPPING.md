# UDS Security Access — Mapping Subfunction → Level, seed_gen, key_validate

Progetto: rx8ecu — RE firmware Mazda RX-8 (ROM `roms/stock/60E1D400.bin`, SH-2E)
Obiettivo PLANS.md:155-156: chiudere il residuo documentato
(mapping UDS subfunction→level; seed_gen internals level≠3; key_validate middle-byte).

Stato: COMPILATO (2026-08-03). Tutti gli indirizzi verificati su ROM `60E1D400.bin`
con `tools/disasm_sh2e.py`. Test suite `c/tests/test_security_access.py`: EXIT=0, tutti PASS.

---

## 1. Mapping subfunction → level

### Tabella dispatch UDS (come la 0x27 arriva all'handler)

- Tabella dispatch @`0x5F57C`, 12 byte/entry: `[SID] [00 00 00] [handler LE32] [mask LE32]`.
  Referenziata dal literal @`0x6990C` (word BE `0x0005F57C`).
- Entry SID 0x27 @`0x5F5F4`: `27 00 00 00 00 05 84 A0 10 00 00 0E`
  → handler `0x584A0`, mask `0x1000000E`.

### Dispatch interno del handler `0x584A0` (SecurityAccess)

Ingresso: `r4` = buffer/len, `r5` = subfunction byte.

1. `r4 = extu.b r5`; `cmp/eq #0x01` — **solo subfunction == 1 prosegue**
   (≠1 → `0x5862C`, exit senza risposta). Fonte: `0x584A6`-`0x584B8`.
2. Legge il payload byte: `0x68BC0(SID=0x27, dst=r15, len=1)` → `[r15]`.
   Se `[r15]==0` → NRC `0x31` (`0x584EC`-`0x584F6`).
3. **La parità di `[r15]` seleziona l'operazione** (`0x584FE`-`0x58516`):
   - `[r15]` dispari → RequestSeed (`0x5851A`)
   - `[r15]` pari   → SendKey   (`0x58592`)
4. SendKey: in `0x58594` c'è un `cmp/eq #0x04` sullo stesso valore; il significato
   esatto del 4 non è chiuso (v. Sezione 6 — il C usa `SF_SEND_KEY=0x04`,
   librx8 usa `0x02`; entrambi pari, entrambi cadono nel ramo SendKey).

### Il "level" NON è derivato dalla subfunction linearmente

- `seed_gen` è chiamato **con livello fisso 3** in entrambi i rami:
  - RequestSeed: `0x58522`-`0x58524` `jsr @0x5699A; mov #0x03,r4`
  - SendKey: `0x585A2`-`0x585A4` `jsr @0x5699A; mov #0x03,r4`
- Il livello di controllo è l'**indice di tabella di `position_check`** (v. sotto):
  `0x58526`-`0x5852C` `jsr @0x56892; r4=[r15]` → `r12`; se `extu.b(r12)==3`
  → NRC `0x31` (`0x58530`-`0x5857E`).

### position_check `0x56892` — tabella lookup @`0x5FA90` (stride 6)

- Loop `i=0..3`: confronta `entry[i][1]` con il byte in ingresso (`0x568A8`-`0x568AC`).
  Entry (byte[1] → indice `i`):
  | indice | entry @0x5FA90+6i            | byte[1] | word @+4 (2º stadio) |
  |--------|------------------------------|---------|----------------------|
  | 0      | `00 00 00 00 00 00`          | `0x00`  | `0x0000`             |
  | 1      | `01 01 02 00 FF FD`          | `0x01`  | `0xFFFD`             |
  | 2      | `F1 F1 F2 00 FF FC`          | `0xF1`  | `0xFFFC`             |
  | 3      | `00 00 00 01 00 01`          | `0x00`  | `0x0001`             |
- 2º stadio (`0x568BC`-`0x568E0`): `word @0xFFFFD3F0  AND  word @(0x5FA94 + i*6)`;
  se risultato != 0 → ritorna `i`; altrimenti ritorna 3 (non-trovato).
  **La mask NON è una costante: è la word RAM @`0xFFFFD3F0`** (`mov.w @r1` con
  `r1=0xD3F0`, `0x568BC`).
- Ritorno: `0..2` = indice entry matchata, `3` = no-match/mask-clear.

**Risposta al residuo**: la subfunction UDS (0x01, e la parità di `[r15]`) non
mappa 1:1 a un livello; il livello usato per generare il seed è **fisso 3**, e il
livello di validazione è l'indice `0..2` della tabella `0x5FA90` (entry byte[1]
∈ {0x00, 0x01, 0xF1}).

---

## 2. seed_gen — path level≠3

### seed_gen `0x5699A` (entry), RAM: seed → `0xFFFFD211..213`, level → `0xFFFFD214`

- **level == 3** (`0x569B6` `cmp/eq #0x03`): `r13=r12=r14=0xFF`, salta al
  write-back (`0x569BC`-`0x569C2` → `0x56A8C`):
  `jsr @0x3920(r4=0x10)` (setSR/priorità), poi
  `[0xFFFFD214]=level`, `[0xFFFFD211]=0xFF`, `[0xFFFFD212]=0xFF`,
  `[0xFFFFD213]=0xFF`, `jsr @0x3934` (finalize).
  → **il seed del fast path (RequestSeed) è `FF FF FF`.**
- **level ≠ 3** (path entropia, `0x569C4`-`0x56A8A`):
  1. Stack frame: `r9 = r15+0x1C` (buffer 4 byte), `r10 = 0x55`, `r11 = 0x10`,
     `r2 = 0xF430` (`0x569CA`-`0x569E4`).
  2. Legge il **contatore a 32 bit free-running @`0xFFFFF430`** (`mov.l @r2,r6`,
     `0x569E6`-`0x569E8`) e lo copia come 4 byte in `r9[0..3]` con `shlr8`
     (`0x569EE`-`0x569FC`).
  3. `bsr @0x5687A(r4=4)`: confronta `4` con `byte @0xFFFFD20B`; ritorna 0 se uguali.
     (`0x56A00`-`0x56A02`; il check è "lo stato è il sentinel 4?").
  4. Se lo stato **non** è 4 (`r0!=0`): path XOR (`0x56A2C`-`0x56A40`):
     `r14 = b[2]^b[0]`, `r12 = b[1]^b[0]`, `r13 = b[3]^b[0]`.
  5. Se lo stato **è** 4 (`r0==0`): seed fisso `r14=0x55`, `r12=0xAA`, `r13=0x55`
     (`0x56A0C`-`0x56A12`, `mov.w 0x56A18 → 0x00AA`).
  6. Loop di retry `0x56A42`-`0x56A8A`, contatore `[r15]`, max `0x10` (16):
     - se `r14==0 && r12==0 && r13==0` → retry (rilegge il counter, `0x569E6`)
     - se `r14==FF && r12==FF && r13==FF` → retry
     - oltre 16 → `r13=r12=r14=0xFF` (fallback `FF FF FF`)
  7. Write-back comune a `0x56A8C`+ (come sopra).

**Risposta al residuo**: per level ≠ 3 il seed NON è LFSR/counter-rigido: deriva da
4 byte del contatore `0xFFFFF430` con XOR-mix (b2^b0, b1^b0, b3^b0), oppure
`55 AA 55` se `0xFFFFD20B == 4`, con retry su tutto-0/tutto-FF (max 16 → `FF FF FF`).
L'LFSR (init per-level @`0x5FAC5`, taps `0x909028`) è usato **solo nella key
transform** `seed_key_related` `0x56ADA`, non in seed_gen.

---

## 3. key_validate — origine del middle byte

### key_validate `0x56928` ("prediction") — tabella @`0x5FAA2`, stride 3

- Loop `i` su entry, confronta `entry[i][0]` vs `r4`, `[i][1]` vs `r5`,
  `[i][2]` vs `r6`; itera mentre `b0 < 5` (`0x5696E`-`0x56972`: `cmp/ge #5, b0`).
- Ritorno (`0x56976`-`0x5697A`): `movt r4` = `(b0 >= 5)` dell'ultima entry
  confrontata → **0 = match su entry valida (b0<5), 1 = nessun match**.
  Caller `0x58546`-`0x58548`: risultato != 0 → NRC `0x31`.

### Call site — origine dei tre byte (CHIAVE del residuo)

Call @`0x58538`-`0x58542` (ramo RequestSeed), dopo `position_check`:

| param | registro | origine                                  |
|-------|----------|------------------------------------------|
| b0    | r4       | `[r15+8]` = risultato `jsr @0x568E6`     |
| b1    | r5       | `r10`    = **stesso valore** (duplicato)  |
| b2    | r6       | `r12`    = risultato `position_check`     |

- `0x584D2`-`0x584D6`: `jsr @0x568E6` → `[r15+8] = r0`; `0x584DA`: `r10 = r0`.
- `0x568E6` legge **`byte @0xFFFFD20C` = SECURITY_STATE_2** (`mov.l 0x5690C,r3`).
- → **il "middle byte" non è un byte del seed/key: è SECURITY_STATE_2, lo stesso
  valore passato come b0 (duplicato).** Il C (righe 210-215) lo ricostruiva come
  `key_validate(state, subfunc, chk)` — il parametro centrale `subfunc` è errato.

### Tabella ROM @`0x5FAA2` (10 entry, verbatim)

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
Il loop si ferma alla prima entry con `b0 >= 5` → considera le prime 9 entry.

**Risposta al residuo**: i tre byte confrontati sono `(SECURITY_STATE_2,
SECURITY_STATE_2, position_check_result)`; il middle byte è SECURITY_STATE_2
duplicato. Il C `c/security_access.c` (righe 397-403) riporta solo 5 entry e con
le righe 3-4 **diverse dalla ROM** (v. Sezione 6).

---

## 4. diag_seed_generate_4E72C / diag_key_validate_4E78A

Nomi IDA **fuorvianti** — NON sono il seed/key di UDS 0x27:

- `0x4E72C` ("diag_seed_generate_4E72C"): loop FP `0x0B` (11) iterazioni su
  `0xFFFFCEF0+`, `fdiv`, scrive a `0xFFFFCF20`, flag `@0xFFFFA402` — è un
  **averaging/rolling-mean** (es. sensore), non un generatore di seed.
- `0x4E78A` ("diag_key_validate_4E78A"): legge byte `@0xCF82/@0xC020/@0xC01E/
  @0xCF81/@0xCFAC` e propaga flag a 1 (`0xCF81`, `0xCF82`, `0xCFAC`) in base a
  condizioni — è una **propagazione di flag diagnostici**, non un key validator.
- Le funzioni reali di SecurityAccess 0x27 sono: handler `0x584A0`,
  `seed_gen` `0x5699A`, `position_check` `0x56892`, `key_validate` `0x56928`,
  `data_copy` `0x56AC0`, `seed_key_related` `0x56ADA`, `unlock` `0x56720`.

---

## 5. Conferme web

Sorgente `github.com/ConnorRigby/rx8-ecu-dump` (`src/librx8.cpp`, `src/librx8.h`):

- `MAZDA_SBF_REQUEST_SEED = 0x01`, `MAZDA_SBF_CHECK_KEY = 0x02`
- `SEED_LENGTH = 3`
- Secret `MAZDA_KEY_SECRET` = `"MazdA"` (5 byte, coincide con ROM @`0x5FAC0`)
- Init LFSR level1 `0xc541a9` (= entry level1 @`0x5FAC8`), taps `0x909028`
- La key è calcolata come `compute_key(seed, level)` (Galois 24-bit, 64 clock,
  nibble-interleave) — **identico al `seed_key_related` `0x56ADA` della ROM**.

Nota discrepanza: librx8 manda `0x02` come byte SendKey; il C
`c/security_access.c` usa `SF_SEND_KEY = 0x04`. Nel dispatch ROM la decisione
seed/key è la **parità** del byte (dispari=seed, pari=key): entrambi i valori
sono pari, quindi entrambi cadono nel ramo SendKey; il `cmp/eq #0x04` a
`0x58594` rimane da chiarire (v. Sezione 6).

---

## 6. Residui dichiarati

Discrepanze C `c/security_access.c` vs ROM (da NON correggere nel file, solo
segnalate; il file è sotto test):

1. **key_validate table (righe 397-403) NON è verbatim ROM**:
   - riga 4: C `{0x01, 0x02, 0x00}` vs ROM `{0x02, 0x00, 0x01}` @`0x5FAAB`
   - riga 5: C `{0x01, 0x02, 0x01}` vs ROM `{0x02, 0x01, 0x01}` @`0x5FAAE`
   - il C ha 5 entry; la ROM ne ha 10 (loop finché b0<5 → 9 valide + terminatore).
2. **Middle byte key_validate (righe 210-215)**: il C passa `(state, subfunc,
   chk)`; la ROM passa `(SECURITY_STATE_2, SECURITY_STATE_2, chk)` — il
   parametro centrale non è la subfunction.
3. **position_check (righe 308-310)**:
   - `word_tab[2]` C = `0x0000` vs ROM `0xFFFC` (@`0x5FAA0`)
   - la mask C `0x61F2` è fabbricata dal literal pool `0x56CB0` (che è codice:
     `0x61F2` = `mov r9,r3`); la ROM legge la **word RAM @`0xFFFFD3F0`**.
4. **SF_SEND_KEY = 0x04** vs librx8 `MAZDA_SBF_CHECK_KEY = 0x02`; il `cmp/eq
   #0x04` a `0x58594` non è risolto (buffer/len vs subfunction: ambiguità sulla
   convention di `r4` in ingresso).
5. **seed_key_related(4, …) nel ramo SendKey (riga 236)**: la ROM passa
   `r4 = r12` (result data_copy/state), non 4.
6. `0x68BC0` e `0x688B4` (dispatch SID per-subfunction): struttura verificata
   solo a grandi linee; la convention esatta `r4`/`r5` dell'handler 0x584A0
   (buffer vs length) non è chiusa.

Storia: i residui 1-3 (key_validate table 10-entry, middle byte = SECURITY_STATE_2,
word_tab[2]=0xFFFC) sono stati **corretti e VERIFIED** nel C (commit `b483523`),
mentre il residuo 4 (SF_SEND_KEY=0x04 vs librx8 `0x02`) e i flussi di dettaglio
restano aperti.

Open item esplicito per PLANS.md:155-156: verificare se `0x584A0` riceve
`r5`=subfunction UDS o `r5`=primo byte payload (impatto su §1 e §6.4).
Stato attuale: il handler `0x584A0` è **strutturalmente ricostruito** e il core
(seed_gen, key_validate, position_check, seed_key_related/lfsr) è **VERIFIED**
(vedi `docs/functions/security_access_handler.md`); resta da confermare in
dettaglio il **flusso RequestSeed** (`c/security_access.c` ~riga 203-248).
