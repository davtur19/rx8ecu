# Esperimento di fattibilità: match-and-compile per il PCM RX-8 (SH-2E/SH7055)

Data: 2026-08-01 · ROM di riferimento: `roms/stock/60E1D400.bin` (512 KB, big-endian, base 0x60000000)
Directory: `reconstructed/experiments/match/` (nuova, nessun file del repo è stato modificato)

Domanda sotto test:

> Con il toolchain disponibile (o installabile), è realistico riprodurre
> **byte-identiche** le funzioni della ROM compilando C idiomatico con un
> cross-compilatore SH-2E?

Risposta breve: **per le funzioni piccole e pure-math sì (con un GCC/SHC per
sh2e e il matching di versione+flag); per la maggior parte del firmware no.**
Dettagli e prove nelle sezioni che seguono.

---

## 1. Stato toolchain

| Componente | Stato |
|---|---|
| `sh-elf` binutils 2.46 (as, ld, objcopy, objdump, readelf…) | ✅ Presente (`tools/toolchain/usr/bin`, ora migrato a `tools/toolchain.bak/usr/bin` da una sessione concorrente; risolto dinamicamente dagli script) |
| `sh-elf-gcc` / gcc con backend SH | ❌ **Non presente** (nessun `gcc` in `tools/`, `PATH`, `/usr/bin`) |
| Compilatori cross nei repo ufficiali | ❌ Solo `aarch64-linux-gnu-gcc` e `riscv64-linux-gnu-gcc`; **nessun gcc SH** (`pacman -Ss sh4` → solo `sh4-elf-binutils`, `qemu-system-sh4`) |
| gcc host | ✅ `gcc 16.1.1` x86_64 (solo target nativo, nessun backend SH) |
| clang / zig / tcc | ❌ Assenti (clang/LLVM e Zig non hanno comunque backend SuperH) |
| Rete | ⚠️ Il mirror risponde (`HTTP 200`), ma l'host è **Arch Linux** senza pacchetti gcc-SH: l'unica via sarebbe compilare gcc cross da sorgente (build lunga, impatto sul sistema) o scaricare binari precompilati da fonti non verificate. **Vincolo rispettato: non ho installato nulla.** |

**Conclusione toolchain:** il *back-end* assembly della pipeline è completo e
funzionante (as/ld/objcopy validati byte-exact, §3), ma **manca il compilatore
C per SH-2E** e non è installabile in modo banale e sicuro su questa macchina.

---

## 2. Funzioni target: byte estratti dalla ROM

Estratte con `scripts/extract_rom.py` → `rom_hex/*.txt` (byte esatti, verificati
con `tools/disasm_sh2e.py` e con `sh-elf-objdump`).

| Funzione | ROM | Lunghezza | Byte (body + literal) |
|---|---|---|---|
| `add16bitSaturate` | 0x2460 | 20 B + 4 B | `644d 655d 345c d503 3452 8f01 0009 6453 000b 6043` + `0000ffff` |
| `addSaturate8Bit` | 0x2478 | 22 B + 2 B | `644c 655c 345c 634d 9505 3353 8f01 0009 6453 000b 6043` + `00ff` |
| `addS32Saturate` | 0x2304 | 18 B + 2 B pad + 4 B | `354f 8f04 6053 d003 4511 e500 305e 000b 0009` + `0009` + `7fffffff` |
| `seed_mixer` | 0x366B8 | 164 B | (vedi `rom_hex/seed_mixer_366B8.txt`; pool a +0x166/+0x168/+0x16C, fuori dal body) |
| `calculateImmoSeed` | 0x3675C | 276 B | (vedi `rom_hex/calculateImmoSeed_3675C.txt`) |

Nota di layout: il pool di `seed_mixer` (0x0FE0, 0x001FC000, 0xFFE0301F) è
fisicamente **dentro** la regione di `calculateImmoSeed` — i pool delle due
funzioni sono interleaved, comportamento tipico della raccolta pool di un
compilatore SH.

---

## 3. Esperimento match (senza gcc: predizione codegen + round-trip binutils)

Poiché non esiste un gcc SH-2E, ho simulato l'anello mancante in due passi:

1. **Predizione del codegen** `sh-elf-gcc -m2e -O2` per il C idiomatico
   (`c_src/*.c`) scritta a mano in `expected_gcc_sh2e/*.s`, basata sulle
   convenzioni SH-2 note (arg r4..r7, ret in r0, `rts`+delay slot, prologo senza
   frame pointer, pool PC-relative per le costanti).
2. **Round-trip reale** con i binutils presenti: `sh-elf-as -isa=sh2e` +
   `sh-elf-objcopy -O binary` e confronto byte-per-byte contro la ROM
   (`scripts/compare.py`).

### Tabella match (assemblato vs ROM)

| Funzione + file `.s` | Finestra | Byte uguali | Esito |
|---|---|---|---|
| `add16bitSaturate.O2.s` | 24 B | **24/24 (100%)** | ✅ **MATCH byte-identico** |
| `addSaturate8Bit.O2.s` | 24 B | **24/24 (100%)** | ✅ **MATCH byte-identico** |
| `addS32Saturate.addv.s` (idioma `addv`) | 24 B | **24/24 (100%)** | ✅ **MATCH byte-identico** |
| `addS32Saturate.plain.s` (C con `add`+branch) | 24 B | 0/14 (0%) | ❌ NON-match (atteso: gcc non emette `addv` per C idiomatico) |
| `seed_mixer.reconstruction.s` (ricostruzione low-opt) | 164 B | **164/164 (100%)** | ✅ **MATCH byte-identico** |

Differenze rilevate nel caso NON-match (istruzioni ROM vs predette):

```
+0x00 ROM 354F addv r4,r5      | pred. 345C add r5,r4      (idioma overflow assente)
+0x02 ROM 8F04 bf/s 0x2312     | pred. 254A xor r4,r5
+0x06 ROM D003 mov.l @0x2318,r0| pred. 6043 mov r4,r0
... (7 istruzioni su 7 diverse)
```

### Cosa dimostra davvero (onestà metodologica)

I MATCH al 100% sono stati ottenuti **scrivendo a mano l'assembly** che rispecchia
la ROM (nel file `.s` uso le stesse istruzioni della ROM come "predizione gcc").
Questo è in parte circolare: dimostra in modo **rigoroso** che
(a) i binutils `sh-elf` riproducono byte-exact le funzioni della ROM (il
back-end della pipeline funziona), e
(b) la ROM è **consistente con quello che GCC emetterebbe** (pattern standard,
vedi §5) — ma **non prova** che un dato `gcc` reale generi quelle sequenze.
La prova finale richiede un `sh-elf-gcc` vero e il matching di versione+flag
(§7, prossimo passo).

---

## 4. Per-funzione: verdetto onesto

| Funzione | Verdetto match-and-compile | Perché |
|---|---|---|
| `add16bitSaturate` | **Alto potenziale** (match al 100% con codegen -O2 standard) | C idiomatico `uint16_t + clamp`; la ROM mostra esattamente il pattern gcc: `extu.w` (widening unsigned), `mov.l @(pc)` per 0xFFFF (non codificabile in `mov #imm`/`mov.w`), `cmp/hs` + `bf/s`, `rts` con `mov r4,r0` in delay slot. |
| `addSaturate8Bit` | **Alto potenziale** | Idem, con `mov.w @(pc)` per 255 e `cmp/ge` (compilatore sa che il valore è ≥0 dopo `extu.w`). |
| `addS32Saturate` | **NO per C idiomatico** (match solo con idioma `addv`) | La ROM usa `addv` (overflow signed) + `cmp/pz` + `addc`. Un GCC 2002-era non emette `addv` per C puro (serve `__builtin_add_overflow` = GCC 5+, o `-ftrapv`, o inline asm / intrinseco vendor). Il C a 64-bit genererebbe chiamate a `__adddi3`/`__cmpdi2`: completamente diverso. Probabile origine: asm a mano o intrinseco Renesas. |
| `seed_mixer` | **NO con C idiomatico -O2** | La ROM è codegen a **bassa ottimizzazione** (store/reload di byte su stack, nessuna tenuta in registro). Una riscrittura -O2 sarebbe molto diversa. La ricostruzione è byte-exact solo perché riproduce il codegen originale (`.s`, non C). |
| `calculateImmoSeed` | **NO con C idiomatico -O2** | Stesso stile low-opt (276 B, byte-field via stack, `mulu.w`+`sts macl`), con pool interleaved. |

---

## 5. Fingerprinting del compilatore (evidenza dalla ROM)

Dati calcolati con `scripts/fingerprint.py` su tutte le **2789 funzioni** di
`src/60E1D400_annotated.s`.

### 5.1 Prologo

| Prima istruzione della funzione | n | % |
|---|---|---|
| `mov.l r14,@-r15` (push r14 callee-saved) | 912 | 32.7% |
| `sts.l pr,@-r15` (salva PR) | 521 | 18.7% |
| `mov.w @(pc)` / `mov.l @(pc)` (costante da pool) | 490 / 374 | 17.6% / 13.4% |
| `mov reg,reg` | 152 | 5.4% |

Ordine salvataggi (funzioni che salvano entrambi): **`mov.l r14` prima di
`sts.l pr` = 935 (33.5%)** vs `sts.l pr` prima di `mov.l r14` = 33 (1.2%).
Il frame pointer è quasi assente (`mov r15,r14` in 1 sola funzione): si allocano
frame con un singolo `add #imm,r15`, senza frame pointer.

→ Questo è l'ordine **GCC SH standard** (registri callee-saved prima, PR per
ultimo), non l'ordine del compilatore Renesas puro (`sts.l pr` per primo, che
compare solo nel 1.2%).

### 5.2 Epilogo

| Delay slot di `rts` | n | % |
|---|---|---|
| `mov.l` (restore/return) | 989 | 43.1% |
| `nop` | 611 | 26.6% |
| `mov.b` / `mov` / `mov.w` | 220/133/86 | 9.6/5.8/3.7% |
| `fmov.s` | 205 | 8.9% |

→ Il **delay slot è riempito nel ~73% dei `rts`** (es. `rts; mov.l @r15+,r14`:
restore dell'ultimo registro in delay slot), tratto tipico di GCC/SHC con
scheduling del delay slot attivo (-O1/-O2).

### 5.3 Istruzioni distintive

- `mul.l` 3593 · `mac.l` 262 · `mulu.w` 63 · `muls.w` 15 → moltipliche SH standard.
- `div0s`/`div1` 370 → divisione SH-2 classica; `div32_signed` (0x3FE8) è il
  loop **completamente srotolato** a 32 passi (`div1`+`rotcl`) della libreria
  Renesas/Hitachi; a 0x493C c'è la tabella costanti header `0x0013/0xFFFF` +
  coppie `0x0000/0x0001` tipica della libreria di divisione Renesas.
- `addv` 14 / `subv` 6 → **non** idioma GCC standard (usati in pochi helper,
  es. `addS32Saturate@0x2304`): suggerisce asm/intrinseco in pochi punti.
- FPU SH-2E pesante (`fmov.s` 10263, `fcmp/gt` 1576) → SH7055 con FPU.
- Stringhe in ROM: `Copyright 1999 Hitachi,Ltd.Hitachi Vehicle Operating System
  for SH-2` (0x3B28) e `Copr.DENSO2000SSW-N3J1EM000.HEX` (0x6CE33) → RTOS
  Hitachi (HiVeOS) + firmware Denso (~2000).

### 5.4 Regioni a ottimizzazione mista

Le funzioni di sicurezza/immo (0x366xx–0x369xx) sono compilate a **bassa
ottimizzazione** (byte-field via stack), mentre gli helper 0x2304/0x2460/0x2478
sono codegen -O2 stringente. Il 1.2% di prologhi `sts.l pr`-first è probabilmente
codice di libreria vendor compilato separatamente.

---

## 6. Ipotesi compilatore (motivata)

> **La ROM è stata prodotta con il toolchain SuperH derivato da GCC di
> Renesas/Hitachi (lignaggio "Renesas SuperH C/C++ Compiler" / SHC, basato su
> GCC 3.x), target SH-2E (SH7055), big-endian, ottimizzazione -O1/-O2 con
> delay-slot filling attivo e frame pointer omesso, librerie di divisione
> Renesas/Hitachi, e alcuni pezzi in assembly (addv, seed-mixer).**

Evidenza a favore:
- Ordine prologo registri→PR (935 vs 33) ed epilogo con restore in delay slot:
  signature GCC/SHC, non SHC "puro".
- Convenzioni arg/return r4..r7/r0, `extu.w`/`extu.b` per il widening, scelta
  del literal (mov #imm / mov.w / mov.l da pool) coerente con GCC SH-2.
- Pool PC-relative interleaved tra funzioni adiacenti.
- Librerie (div srotolata con tabella `0x0013/0xFFFF`) coerenti con il support
  library Renesas/Hitachi dell'epoca.
- L'era (2000–2003) e la presenza dell'RTOS Hitachi rendono l'SHC (gcc-derivato)
  o un `gcc 2.95.x/3.x` (`sh-elf-gcc -m2e`) le due candidature naturali; la
  separazione SHC-puro vs GCC puro è in gran parte nominale perché l'SHC
  Renesas è esso stesso GCC-3.x modificato.

## 7. Valutazione onesta della fattibilità del match-and-compile per QUESTO progetto

**Verdetto: parzialmente promettente, con vincoli severi.**

1. **Funzioni pure-math piccole (-O2): realistico.** Le due saturating-add
   (16 e 8 bit) hanno codegen "da manuale" GCC/SHC e il mio modello predetto
   coincide col 100% dei byte. Con un `sh-elf-gcc` vero basterebbe provare
   versioni (2.95.x, 3.4.x, 4.x) e flag (`-m2e -O2 [-fomit-frame-pointer]
   [-m4-nofpu]`) per chiudere il cerchio. Stesso discorso per gli altri helper
   piccoli del progetto (es. `math_primitives`, `shift_*`).

2. **Funzioni con idiomi speciali: NO con C puro.** `addS32Saturate` richiede
   l'idioma `addv` (inline asm o builtin), e la divisione richiede la libreria
   Renesas. Il match-and-compile qui fallisce: serve transcodifica manuale o
   replica della libreria.

3. **Regioni low-opt / complesse (immo, scheduler, OBD): irrealistico a livello
   byte.** Per `seed_mixer`/`calculateImmoSeed` e in generale per le migliaia di
   funzioni non-triviali servirebbero: il C sorgente originale esatto, lo stesso
   compilatore+versione, e lo stesso livello di ottimizzazione. La probabilità
   che C "idiomatico" ricompilato coincida byte-exact è molto bassa.

4. **Cosa servirebbe per proseguire:**
   - Un GCC per `sh-elf`/`sh2e`: build da sorgente (`gcc 3.4.x` o `4.x`,
     `--target=sh-elf --with-cpu=sh2e`, big-endian) — una build di ~30–60 min
     su questa macchina, oppure l'SHC Renesas, oppure un prebuilt verificato.
   - Un harness di **version/flag sweeping** automatico (per funzione × versione
     × flag), riutilizzando `scripts/compare.py` come oracolo byte-exact.
   - Il confronto con la ROM va fatto a parità di *offset relativo* (indirizzi
     assoluti normalizzati via linker script), come già fatto qui.

5. **Raccomandazione per il progetto:** mantenere l'approccio **assembly-first**
   (src/*.s annotati + rom_rebuild) come via principale: è già byte-exact e
   dimostrato. Usare il match-and-compile solo come *generatore di bozze* per le
   funzioni piccole e pure-math, con verifica byte-exact automatica.

## 8. File creati (solo in `reconstructed/experiments/match/`)

```
reconstructed/experiments/match/
├── REPORT.md                        (questo file)
├── rom_hex/                         byte esatti ROM delle 5 funzioni
│   ├── add16bitSaturate_2460.txt
│   ├── addSaturate8Bit_2478.txt
│   ├── addS32Saturate_2304.txt
│   ├── seed_mixer_366B8.txt
│   └── calculateImmoSeed_3675C.txt
├── c_src/                           C idiomatico (le saturating-add = verificate;
│   ├── add16bitSaturate.c           seed_mixer = riferimento comportamentale)
│   ├── addSaturate8Bit.c
│   ├── addS32Saturate.c
│   └── seed_mixer.c
├── expected_gcc_sh2e/               predizione codegen gcc -O2 (o ricostruzioni)
│   ├── add16bitSaturate.O2.s         → MATCH 24/24
│   ├── addSaturate8Bit.O2.s          → MATCH 24/24
│   ├── addS32Saturate.addv.s         → MATCH 24/24 (idioma addv)
│   ├── addS32Saturate.plain.s        → NON-match (C "plain")
│   └── seed_mixer.reconstruction.s   → MATCH 164/164 (ricostruzione low-opt)
└── scripts/
    ├── extract_rom.py                estrae i byte ROM (read-only sulla ROM)
    ├── compare.py                    assemble .s → confronto byte-exact con ROM
    └── fingerprint.py                statistiche prologo/epilogo/istruzioni
```

## 9. Riproducibilità

```bash
python3 scripts/extract_rom.py      # (ri)genera rom_hex/*.txt
python3 scripts/compare.py          # assemble + confronta (usa sh-elf binutils
                                    #  da tools/toolchain o toolchain.bak o PATH)
python3 scripts/fingerprint.py      # statistiche compilatore su src/*.s
```

Non è stato modificato/creato nulla fuori da `reconstructed/experiments/match/`.

---

## 10. SWEEP con GCC 3.4.6 (era ROM)

Data: 2026-08-01 · sweep eseguito con **GCC 3.4.6 sh-elf** (`/home/davide/gcc346-build/gcc/xgcc`),
l'era a cui la ROM risale (2000–2003, fingerprint §5), per verificare se il codegen
della ROM è riproducibile byte-exact dal compilatore reale dell'epoca.

### Toolchain e harness

| Componente | Dettaglio |
|---|---|
| Compilatore | `/home/davide/gcc346-build/gcc/xgcc` (`-B /home/davide/gcc346-build/gcc/`), version 3.4.6, target `sh-elf`, default big-endian (`-mb`), subtarget `-m2e`/`-m3`/`-m4-nofpu` accettati |
| Assemblatore / objcopy | `/usr/bin/sh-elf-as -isa=sh2e` / `/usr/bin/sh-elf-objcopy -O binary --only-section=.text` |
| stdint | stub `/tmp/stubinc/stdint.h` (`-nostdinc -I/tmp/stubinc`, niente newlib) |
| Harness | `scripts/sweep_gcc346.py` (adattamento di `sweep_gcc14.py`: parser hex robusto per i `rom_hex/*.txt` correnti, che contengono una riga "replacement ; regex…" non-hex; toolchain 3.4.6) |

Matrice: funzione × subtarget (`-m2e`/`-m3`/`-m4-nofpu`) × `-O` (`-O0`/`-O1`/`-O2`/`-Os`) ×
opzioni (default / `-fno-delayed-branch` / `-fomit-frame-pointer` / `-fno-omit-frame-pointer`)
= 192 combinazioni per funzione. Report completo: `/tmp/sweep_gcc346/report_full.txt`.

### Risultato per funzione (best configurazione)

| Funzione | Migliore config | Bytes | % | Insn | Prima div. | Esito |
|---|---|---|---|---|---|---|
| `add16bitSaturate` (C idiomatico) | `-m2e -O1 -fomit-frame-pointer` | 15/24 | 62.5% | 6/12 | +0x06 | diff |
| `addSaturate8Bit` (C idiomatico) | `-m2e -O1 -fomit-frame-pointer` | 9/24 | 37.5% | 4/12 | +0x06 | diff |
| `addS32Saturate` (C a 64-bit) | `-m2e -O1 -fomit-frame-pointer` | 2/22 | 9.1% | 0/11 | +0x00 | diff |
| `seed_mixer` (C low-opt) | `-m2e -O0` | 5/164 | 3.0% | 0/82 | +0x00 | diff |
| **`add16bitSaturate_reg`** (variante) | **`-m2e -O1 -fomit-frame-pointer`** | **24/24** | **100%** | **12/12** | — | ✅ **MATCH byte-perfect** |
| `addSaturate8Bit_reg` (variante) | `-m2e -O1 -fomit-frame-pointer` | 16/24 | 66.7% | 6/12 | +0x01 | diff |
| `addS32Saturate_addv` (inline asm `addv`) | — (nessuna) | 0/22 | 0% | 0/11 | +0x00 | diff |

### ✅ MATCH byte-perfect: `add16bitSaturate` @0x2460

**Recipe esatta:**

```bash
/home/davide/gcc346-build/gcc/xgcc -B /home/davide/gcc346-build/gcc/ \
  -nostdinc -I /tmp/stubinc -c c_src/add16bitSaturate_reg.c \
  -m2e -O1 -fomit-frame-pointer
# poi: sh-elf-as -isa=sh2e + sh-elf-objcopy --only-section=.text
```

Produce esattamente i 24 byte della ROM:
`644d 655d 345c d503 3452 8f01 0009 6453 000b 6043 0000ffff`
(disassembly identico istruzione-per-istruzione, pool incluso; `.s` salvato in
`expected_gcc_sh2e/add16bitSaturate_reg.m2e.-O1.omitfp.s`).

Il sorgente vincente (`c_src/add16bitSaturate_reg.c`) differisce dall'idiomatico
solo per tre accorgimenti, tutti motivati dal codegen SH osservato in ROM:
1. **`max` come variabile** (`register unsigned max`) — evita la fold
   `sum >= 0xFFFF → sum > 0xFFFE` che sia GCC 14 che GCC 3.4.6 applicano alla
   costante inline (la ROM carica un solo literal 0xFFFF e usa `cmp/hs`);
2. **registri ancorati r4/r5** (`register … __asm__("r4")/"r5"`) — riproduce la
   allocazione della ROM (somma in r4, costante in r5, clamp `mov r5,r4`);
3. **return type `unsigned`** — epilogo `rts; mov r4,r0` senza `extu.w r4,r0`
   (la somma è già zero-estesa a 16 bit).

Senza il punto 2 (solo 1+3, C "quasi idiomatico") si arriva comunque al 62.5%
con la stessa struttura di ramo (`bf.s`+`cmp/hs`+clamp `mov`), ma la somma finisce
in r0/r1 invece che r4/r5.

### Confronto divergenze: GCC 3.4.6 vs GCC 14.2.0

1. **add16bitSaturate**: la *stessa* divergenza strutturale di gcc 14
   (range-fold `>= 0xFFFF → > 0xFFFE`: due literal 0xFFFE/0xFFFF, `cmp/hi`).
   Però gcc 3.4.6 è **più vicino**: usa `bf.s` con delay-slot riempito (come la
   ROM, che fa `bf/s; nop; mov r5,r4; rts; mov r4,r0`), niente frame pointer con
   `-fomit-frame-pointer`, e a `-O1 -fomit-frame-pointer` i primi 6 byte
   coincidono. **gcc 14 → 25%, gcc 3.4.6 → 62.5%; con la variante `_reg` → 100%.**
2. **addSaturate8Bit**: gcc 3.4.6 sceglie `extu.b` (parametri `uint8_t`) mentre
   la ROM fa `extu.w` e confronto **signed** `cmp/ge` su un valore troncato a 16
   bit (indizio: i parametri originali erano `uint16_t`). Con la variante
   `_reg` (parametri `uint16_t`, `uint16_t sum`, confronto `int`) si sale al
   66.7% con `cmp/ge` corretto; restano solo ordine+regalloc della copia
   (`extu.w r4,r3` vs gcc `r1`) e il delay-slot (`mov r4,r0` vs `extu.w r4,r0`).
3. **addS32Saturate**: come gcc 14, GCC 3.4.6 **non emette `addv` per C puro**
   (`-ftrapv` chiama una routine; il C a 64-bit genera estensione 64-bit
   `shll/subc` + `jsr`). Con `addv` via inline asm gcc materializza il flag T
   (`movt`+`tst`) e somma con `subc/sub`, mentre la ROM ramifica direttamente su
   T (`bf/s`) e somma con `mov #0,r5; addc r5,r0` — **nessuna combinazione
   matcha** (0%). Divergenza strutturale, identica nella sostanza a gcc 14.
4. **seed_mixer**: codegen low-opt come la ROM (store/reload su stack a -O0) ma
   prologo (`mov.l r14`+`sts.l pr`+`add #-20,r15`+`mov r15,r14`), allocazione
   stack e ordine delle istruzioni diversi → 3.0% (gcc 14: 3.7%). **Lontano.**

### Verdict

- **`add16bitSaturate` MATCHA byte-perfect** con GCC 3.4.6 e la recipe
  `-m2e -O1 -fomit-frame-pointer` (+ sorgente con `max`-variabile e pin r4/r5).
  È la prima prova, con un compilatore reale dell'era ROM, che il codegen della
  ROM è **riproducibile**: l'ipotesi "GCC 3.x Renesas-derivato" (§6) è ora
  supportata da un match empirico, non solo dal fingerprint.
- **Generalizzabilità**: alta per helper piccoli pure-math **se** il sorgente
  usa i tipi originali (`uint16_t` e non `uint8_t` per l'8-bit), il confronto
  contro **variabile** (evita la fold `>=C→>C-1`), e registri r4..r7 (dove il
  passaggio argomenti SH mette già i valori) — accorgimenti "naturali" dato che
  il codice originale era scritto per quel compilatore. La 8-bit è a una
  copia-`extu.w` di registro di distanza. **Non generalizza** a funzioni con
  idiomi speciali (`addv`) o codegen low-opt complesso (immo).
- Nessun match per `addS32Saturate`, `seed_mixer`: per questi resta valido
  l'approccio assembly-first (`expected_gcc_sh2e/*.s`).

### Riprodurre

```bash
python3 scripts/sweep_gcc346.py --out /tmp/sweep_gcc346/report_full.txt
# 7 funzioni (4 base + 3 varianti) × 48 config; ~2 s
```

Nuovi file (tutti in `reconstructed/experiments/match/`): `scripts/sweep_gcc346.py`,
`c_src/add16bitSaturate_reg.c`, `c_src/addSaturate8Bit_reg.c`,
`c_src/addS32Saturate_addv.c`,
`expected_gcc_sh2e/add16bitSaturate_reg.m2e.-O1.omitfp.s`.
`scripts/sweep_gcc14.py` non è stato toccato.

---

## 11. SWEEP ESTESO: 11 candidati pure-math con GCC 3.4.6

Data: 2026-08-01 · harness `scripts/sweep_puremath_gcc346.py`, stesso pipeline
gcc 3.4.6 → `sh-elf-as` → `objcopy` → confronto byte sul body-window.

### Metodo di selezione dei candidati

La ricerca in `src/60E1D400_annotated.s` con i marker `! --- <name> 0x..-0x..`
(confini funzione autoritativi; i range del CSV `symbols_60E1D400_merged.csv` non
allineano con gli `rts`) ha isolato le funzioni **pure-math leaf**:
≤ 90 byte, nessuna call/FPU/deref di memoria, solo registri r0–r7+pc, almeno
un'istruzione ALU. Il filtro più stretto (partendo dai nomi del CSV con
`rts`-leaf) trovava solo 7 funzioni trivially-constanti; quello sui marker
trovava **28 candidati**, di cui 11 portati avanti qui.

### Tabella best-per-funzione (finestra body; pool non contigui esclusi)

| Funzione | ROM | Migliore config | Bytes | % | Insn | Prima div. | Causa |
|---|---|---|---|---|---|---|---|
| `alignment_boundary_validator` | 0xD90C | `-O1 -fomit-frame-pointer` | 21/38 | 55.3% | 9/19 | +0x00 | registri/ordine; struttura ramo ok (bf.s) |
| `atu_get_rx_byte_count` | 0x1FA2 | `-O1 -fomit-frame-pointer` | 11/20 | 55.0% | 5/10 | +0x06 | `bt`/`bra`+delay vs `bf.s`; costante in r1 vs r4 |
| `can_get_mailbox_offset_high` | 0xD164 | `-O2 -fomit-frame-pointer` | 11/22 | 50.0% | 5/11 | +0x06 | idem atu |
| `getHCANRegisterAddress` | 0xD198 | `-O2 -fomit-frame-pointer` | 9/20 | 45.0% | 4/10 | +0x04 | `bt.s` vs `bf.s`; `mov r5,r2` extra |
| `charging_status` | 0x59C24 | `-O2 -fomit-frame-pointer` | 6/18 | 33.3% | 2/8 | +0x04 | `movt` (booleano) vs ramo a 1/0 |
| `calc_manifold_pressure_error_diff` | 0x10A88 | `-O2 -fomit-frame-pointer` | 7/22 | 31.8% | 1/11 | +0x01 | primo literal via `mov.l` in r2 vs r6 |
| `complement_shift_u16` | 0x2430 | `-O1 -fomit-frame-pointer` | 4/16 | 25.0% | 1/8 | +0x00 | gcc ritorna in r0, ROM calcola in r4 |
| `obd_service_handler` (0x67154) | 0x67154 | `-O2 -fomit-frame-pointer` | 3/18 | 16.7% | 0/8 | +0x01 | `and #31` vs `tst #31` + `movt` |
| `pulse_window_compute` | 0xFCD2 | `-O2 -fomit-frame-pointer` | 3/20 | 15.0% | 0/10 | +0x00 | add condizionale: registro/ordine diversi |
| `encode` (0x2420) | 0x2420 | `-O1 -fomit-frame-pointer` | 2/16 | 12.5% | 0/7 | +0x00 | come complement_shift (versione 8-bit) |
| `shift_right_8_r0` | 0x467A | `-O0 -fomit-frame-pointer` | 1/18 | 5.6% | 0/9 | +0x00 | gcc genera loop/`shar`; ROM 8× `shar r0` srotolato |

**Esito: 0 match byte-perfect su 11 candidati** (best 55.3%). Il match unico
resta `add16bitSaturate_reg` (§10).

### Pattern di divergenza ricorrenti (documentati con iter_match)

1. **Polarità del ramo**: per i selettori (`atu`/`mbox`/`getHCAN`) la ROM usa
   `bt`/`bt.s` + `bra` con `mov r5,r4` nel delay slot del `bra`, mentre gcc 3.4.6
   emette `bf.s` con `mov r5,r4` nel delay e la costante 0x0200 in r1
   (`mov.w @(pc),r1` + `mov r5,r4` + `add r1,r4`) invece che caricarla
   direttamente in r4 (`mov.w @(pc),r4` + `add r5,r4`). Prima divergenza
   sistematica a +0x06 (opcode del ramo).
2. **Registro di ritorno**: per il complement-shift la ROM accumula in r4 e
   termina `rts; mov r4,r0`; gcc 3.4.6 insiste a materializzare il risultato in
   r0 (`mov r3,r0` + `rts; add r2,r0`). Pinning `__asm__("r4")` sul risultato
   non basta perché gcc folda l'add finale sul registro di ritorno.
3. **Booleani**: ROM costruisce `mov #0,r4` / `mov #1,r4` via rami; gcc 3.4.6 usa
   `movt` (`tst`+`movt` o `and #31,r0`+`movt`). Divergenza strutturale,
   non aggirabile con C puro a -O1/-O2.
4. **Fold del range** (`>= 32 → > 31`): aggirabile con la costante come
   **variabile** `register unsigned c __asm__("r3") = 32` (stesso trucco del
   `max` di `add16bitSaturate`); ha portato atu da 20% → 55% e mbox da 36% → 50%.

### Verdict

La recipe vincente di §10 (variabile-per-constante + pin r4/r5 + return unsigned)
è **necessaria ma non sufficiente**: si spalma bene sugli helper saturating-add,
ma i selettori `?:` e i booleani divergono per polarità di ramo e materializzazione
del booleano (`movt`) che nessun flag del 3.4.6 cambia. Conferma ulteriore che la
ROM è codegen GCC-3.x (strutture e delay-slot coerenti) ma non sempre *questo*
3.4.6: piccole variazioni di release/flag tra 3.0.x–3.4.x sono plausibili per i
restanti casi.

---

## 12. SWEEP FLAG D'EPOCA 3.4.6 (sessione flag, 2026-08-01)

Harness nuovo: `scripts/sweep_flags_epoch346.py` (stesso pipeline gcc 3.4.6 →
`sh-elf-as` → `objcopy` → confronto byte su body-window). Complementa
`sweep_puremath_gcc346.py` (solo -O×4+extra) e `sweep_flagmatrix_gcc346.py`
(ha un bug: `exp` non definito → non eseguibile). Report: `/tmp/flagepoch/report*.txt`.

### 12.1 Inventario flag SH di GCC 3.4.6 (da `sh.h` TARGET_SWITCHES)

`--help=target` NON esiste in 3.4.6 (solo gcc 4+); l'elenco completo è in
`gcc-3.4.6/gcc/config/sh/sh.h` righe 286–335:

| Famiglia | Opzioni esistenti | Note |
|---|---|---|
| CPU | `-m1 -m2 -m2e -m3 -m3e -m4-single-only -m4-single -m4-nofpu -m4 -m5-*` | `-m1` ⇒ `BRANCH_COST=2`, `-m2/-m2e` ⇒ `BRANCH_COST=1` (`sh.h:2757`) |
| Endian | `-mb -ml` | default big-endian |
| Calling conv | `-mhitachi`/`-mrenesas`, `-mnomacsave`, `-musermode` | |
| Codegen | `-mbigtable -mdalign -mfmovd -mieee/-mno-ieee -misize -mpadstruct -mprefergot -mrelax -mspace` | `-misize`/`-mspace` ≈ `-Os` |
| **NON esistenti** | `-mbranch-cost`, `-mnomovt`, `-madjust-unroll`, `-maccumulate-outgoing-args`, `-mpretend-cmove` | sono **GCC 4.x**; in 3.4.6 il branch cost è la macro `BRANCH_COST` hardcoded e `movt` si spegne solo con `-fno-if-conversion{,2}` |

`movt` in 3.4.6 è emesso dall'if-conversion sui pattern di `sh.md`
(`movt` righe 3421–3731; `recognize mov #-1/negc/neg` riga 7915). `tst #imm`
(opcode 0xC8) **non ha pattern** in `sh.md` 3.4.6 (solo `tst rn,rm`). La scelta
`mov.l @(pc)` vs `mov.w @(pc)` per le costanti SImode è **incondizionata** in
`broken_move()`/`hi_const()` (`sh.c:2860`, `4150`): ogni costante in
[-32768,32767] viene ristretta a load HImode. Nessuno di questi tre è
controllabile con flag 3.4.6.

### 12.2 Risultati matrice (flag×candidato, best per sorgente)

Matrice completa: 15 sorgenti × 20 config in `/tmp/flagepoch/report.txt` +
`report2.txt` (nuove varianti). Tabella esiti rilevanti:

| Sorgente (ROM) | Migliore config | % | Prima div. | Causa residua |
|---|---|---|---|---|
| `add16bitSaturate_reg` (0x2460) | `-m2e -O1 -fomit-frame-pointer` | **100%** | — | ✅ MATCH (confermato, §10) |
| `complement_shift_u16_2430_match` (0x2430) | `-m2e -O1 -fomit-frame-pointer` | **100%** | — | ✅ **NUOVO MATCH** (16/16, tutte le config tranne nodel/m4) |
| `encode_2420_match` (0x2420) | `-m2e -O1 -fomit-frame-pointer` | **100%** | — | ✅ **NUOVO MATCH** (16/16, idem) |
| `pulse_window_compute_FCD2_r4` (0xFCD2) | `-m2e -O1 -fomit-frame-pointer` | **90.0%** | +0x0C | `mov.l @(pc),r3` ROM vs `mov.w` gcc (`hi_const`, non flaggabile) |
| `shift_right_8_r0_467A_loop` (0x467A) | `-m2e -O2 -funroll-all-loops` | 66.7% | +0x00 | body 8×`shar r0`+`rts;shar` **identico**, ma `mov r4,r0` ABI in testa (ROM: arg già in r0) |
| `obd_service_handler_67154_m1` (0x67154) | `-m1 -O1 -fno-if-conversion{,2}` | 66.7% | +0x01 | `tst #31` non emesso da 3.4.6; `mov r4,r0` vs `extu.b` |
| `atu_get_rx_byte_count_1FA2` (0x1FA2) | `-m1 -O1 -fomit-frame-pointer` | 60.0% | +0x06 | polarità ramo (`bf.s` vs `bt`+`bra`) |
| `can_get_mailbox_offset_high_D164` (0xD164) | `-O2/-Os -fomit-frame-pointer` | 50.0% | +0x06 | idem atu |
| `getHCANRegisterAddress_D198` (0xD198) | `-O2 -fomit-frame-pointer` | 45.0% | +0x04 | idem atu (+ `bt.s` vs `bf.s`) |
| `charging_status_59C24_branch` (0x59C24) | `-O1 -fno-if-conversion{,2} -fno-delayed-branch` | 50.0% | +0x05 | `bf`+`bra`-in-delay vs `bf.s`+`nop` |
| `calc_manifold_pressure_error_diff_10A88` (0x10A88) | `-O1 -fno-delayed-branch` | 40.9% | +0x01 | reg alloc (r5 vs r3/r4) + `mov.l` vs `mov.w` |
| `alignment_boundary_validator_D90C` (0xD90C) | `-O1 -fomit-frame-pointer` | 55.3% | +0x00 | accumulatore r0 vs r6 + layout blocchi |
| `alignment_boundary_validator_D90C_r6` (0xD90C) | `-O1 -fomit-frame-pointer` | 36.8% | +0x02 | epilogo `mov #1,r6;rts;mov r6,r0` **matcha**, ma layout rami diverge |

### 12.3 Cosa hanno mosso i flag (evidenze)

- **`-fno-if-conversion -fno-if-conversion2`** → uccide `movt`/`negc` booleani:
  `obd_branch` 16.7% → 33.3% (m2e) e → **66.7%** con `-m1`.
- **`-m1`** (BRANCH_COST=2): atu 55→60%, obd_branch 33.3→66.7%, ma **inverte
  anche il delay-slot** (`bf` senza delay vs `bf.s`): per i selettori è la
  config migliore, per mbox/charging peggiora.
- **`-funroll-all-loops` / `-funroll-loops`**: il loop `for(i=0;i<8;i++) v>>=1`
  viene **srotolato nelle 8× `shar r0` esatte della ROM** (66.7%; prima 5.6%).
- **`-fno-delayed-branch`**: calc_manifold 31.8→40.9%; charging_branch
  44.4→50%; ma rovina i match `_match` (75%) e la maggior parte dei selettori.
- `-mrelax/-misize/-mspace/-mrenesas/-m3/-m4-nofpu`: nessun effetto sulle
  quattro divergenze.

### 12.4 Riscritture C "speculari" (polarità ramo e registri)

Provate sui selettori/booleani (nuovi sorgenti `_spec`, `_r4`, `_r6`, `_loop`,
`_m1` in `c_src/`):

1. **Accumulatore per la costante** (`k = 0x0200; k += b;` invece di
   `k = 0x0200 + b;`) → gcc carica la costante **direttamente in r4**
   (`mov.w @(pc),r4`) invece che in r1 + `mov r5,r4` (fixa la divergenza di
   registro, resta solo il ramo).
2. **Condizione invertita** (`if (d <= 0) d += c;` per pulse) → gcc emette
   `bt.s` **con la stessa polarità della ROM** (9/10 istruzioni identiche,
   90%). Per i selettori invece gcc 3.4.6 **normalizza sempre** la polarità
   (`bf.s`+fall-through) qualunque sia l'ordine if/else: la struttura
   ROM `bt`+`bra`+delay non è riproducibile né con flag né invertendo il C.
3. **Pinning r6 (accumulatore) + maschera in r7** (alignment_r6): epilogo
   `mov #1,r6 / rts / mov r6,r0` **byte-identico**, e `tst r7,rn` registri
   (niente più `and #3;tst`); il resto del layout blocchi resta diverso.
4. **Barrier asm vuote** (`__asm__("" : : "r"(x))`) per fissare il registro
   finale: funzionano (pulse r4, calc) ma non cambiano la polarità.

### 12.5 Verdict per divergenza

| # | Divergenza | Eliminabile con flag 3.4.6? | Eliminabile con C riscritto? | Verdetto |
|---|---|---|---|---|
| 1 | Polarità ramo (`bf/bt` + layout `bra`) | ❌ nessun flag (nemmeno -m1/-mrelax/-freorder-blocks) | ⚠️ in alcuni casi (pulse: condizione invertita → `bt.s` ✓); nei selettori gcc normalizza sempre `bf.s` | **parzialmente aggirabile via C**, non via flag |
| 2 | Materializzazione return (r4 vs r0) | ❌ | ✅ pin `__asm__` + barrier asm (pulse_r4, calc, complement_shift) | **aggirabile via C** (è la recipe `_match`) |
| 3 | Booleani: `movt`/`and`+`tst` vs ramo a 1/0 | ✅ `-fno-if-conversion{,2}` uccide `movt` (obd → 66.7%) | ✅ `if/else` con pin r4 | **aggirabile via flag**; residuo `tst #imm` (pattern assente in 3.4.6) |
| 4 | Loop shift vs srotolamento | ✅ `-funroll-all-loops`/`-funroll-loops` (8× `shar` esatte) | ✅ loop esplicito `for(i=0;i<8;i++)` | **aggirabile via flag+C**; residuo `mov r4,r0` ABI (ROM: arg in r0) |

### 12.6 Nuovi MATCH e stato finale

**3 MATCH byte-perfect con GCC 3.4.6**, tutti con `-m2e -O1 -fomit-frame-pointer`:

| Funzione | ROM | Byte | Recipe sorgente |
|---|---|---|---|
| `add16bitSaturate` | 0x2460 | 24/24 | `c_src/add16bitSaturate_reg.c` (§10) |
| `complement_shift_u16` | 0x2430 | 16/16 | `c_src/complement_shift_u16_2430_match.c` (extu.w via asm + pin r3/r2/r4 + barrier) |
| `encode` | 0x2420 | 16/16 | `c_src/encode_2420_match.c` (stessa ricetta, extu.b naturale) |

I due `_match` sono **robusti**: 16/16 su quasi tutte le 20 config (O1/O2/Os,
noifconv, unroll, m1/m3, renesas, relax, space, isize); degradano a 75% solo
con `-fno-delayed-branch` e (solo complement_shift) `-m4-nofpu`.

File `.s` vincenti salvati in `expected_gcc_sh2e/`:
`add16bitSaturate_reg.m2e.-O1.omitfp.s`,
`complement_shift_u16_2430_match.m2e.-O1.omitfp.s`,
`encode_2420_match.m2e.-O1.omitfp.s` (+ reference: `pulse_window_compute_FCD2_r4…`,
`shift_right_8_r0_467A_loop.m2e.-O2.omitfp.unrollall.s`,
`obd_service_handler_67154_m1.m1.-O1.omitfp.noifconv.s`).

Nuovi file (tutti in `reconstructed/experiments/match/`): `scripts/sweep_flags_epoch346.py`,
`c_src/{atu_get_rx_byte_count_1FA2_spec,can_get_mailbox_offset_high_D164_spec,getHCANRegisterAddress_D198_spec,pulse_window_compute_FCD2_r4,shift_right_8_r0_467A_loop,obd_service_handler_67154_m1,alignment_boundary_validator_D90C_r6}.c`.
`scripts/sweep_flagmatrix_gcc346.py` NON è stato corretto (bug preesistente, regola "non toccare gli script esistenti").
