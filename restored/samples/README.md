# Restored Source Samples — RX-8 PCM (SH7055)

Questo progetto è un **campione dimostrativo** di "restored source": il codice
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
restored/samples/  (C astratto "come il vero sorgente", verificato  ← QUESTO
                    con lo stesso emulatore sui lift di c/)
```

---

## 1. Come si relaziona alla build byte-exact

| Livello | Cosa è | Ruolo |
|---|---|---|
| `src/60E1D400_annotated.s` | Assembly della ROM, riassemblato byte-exact da `tools/rom_rebuild.py` | **Verità di riferimento**. Se un modello C diverge, vince l'assembly. |
| `c/` | Lift C istruzione-per-istruzione (track A/B), verificati contro la ROM via `tools/sh2emu.py` | **Fonte di derivazione** di questo progetto. |
| `restored/samples/` | C astratto e leggibile, derivato dai lift, con stesso comportamento | **Modello leggibile verificato** — non byte-identico. |

Il "match-and-compile" (rendere questo C anche *byte-identico* alla ROM
compilandolo con un compilatore SH-2E) è l'**evoluzione futura**, già
abbozzata in `restored/experiments/match/` (fingerprinting del compilatore sul
prologo/epilogo e sulle istruzioni distintive della ROM). Il lavoro in questo
sottoprogetto è il prerequisito: prima di chiedere a un compilatore di riprodurre
byte-identico un pezzo di firmware, quel pezzo deve esistere come C pulito e
comportamentalmente corretto.

---

## 2. Campioni inclusi

| Restored name | ROM @ `60E1D400` | Lift di provenienza (`c/`) | Harness |
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
# dall'interno di restored/samples/
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

1. compila i sorgenti restored + `tests/host_oracle.c` con il `gcc` di sistema;
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

## 5. Problemi aperti e limiti noti

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
  nei campioni valgono i nomi restored + gli indirizzi ROM.

## 6. Prossimo passo

Chiusura del **match-and-compile**: usare i risultati del fingerprinting
(`restored/experiments/match/scripts/fingerprint.py`) per scegliere/tarare un
`sh-elf-gcc` (SH-2E) e verificare se i sorgenti restored, compilati con le
opzioni giuste, producono le stesse sequenze byte della ROM (`0x2304`,
`0x366B8`, `0x68780` family sono candidati ideali perché piccoli e già
verificati). Se il match non è byte-identico al primo colpo, le differenze
diventeranno la prossima lista di funzioni da rifinire.
