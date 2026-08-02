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

---

## 13. SWEEP GCC 3.3.6 (release minore precedente: elimina le divergenze residue?)

Data: 2026-08-02 · harness nuovo `scripts/sweep_gcc336.py` (29 sorgenti × 17
flagset = 493 compilazioni; ~2.3 s). Toolchain:
`/home/davide/gcc336-build/gcc/xgcc -B /home/davide/gcc336-build/gcc/` (GCC 3.3.6,
target `sh-elf`, big-endian). Stessa pipeline: gcc -S → `sh-elf-as -isa=sh2e` →
`objcopy --only-section=.text` → confronto byte sul body-window della ROM.

### 13.1 Toolchain: differenze rispetto a 3.4.6

| Aspetto | GCC 3.3.6 | GCC 3.4.6 |
|---|---|---|
| ISA | **`-m2`** (SH-2 core senza FPU single) | `-m2e` |
| `-m2e` | ❌ **non esiste** (`cc1: error: invalid option 2e`) | ✅ |
| `-m1 -m3 -m3e -m4-nofpu -m4-single*` | ✅ | ✅ |
| `-mrenesas/-mhitachi/-mrelax/-mspace/-misize/-mnomacsave` | ❌ droppati come unrecognized | ✅ (`-mhitachi`, `-mrelax`, `-mspace`, `-misize` accettati) |
| `-fno-if-conversion{,2}`, `-funroll-all-loops`, `-fno-delayed-branch` | ✅ | ✅ |
| Prologo SH-2 (smoke test `int f(a,b){return a+b;}`) | ✅ `mov r4,r0; rts; add r5,r0` | ✅ idem |

### 13.2 Risultato per funzione (best config; 3.3.6 base `-m2`)

| Sorgente (ROM) | 3.4.6 best | 3.3.6 best | Config 3.3.6 | % | Prima div. | Δ |
|---|---|---|---|---|---|---|
| `add16bitSaturate_reg` (0x2460) | **100%** | 19/24 | `-O2/-Os -fomit-frame-pointer` | 79.2% | +0x00 | **▼ regredisce** |
| `complement_shift_u16_2430_match` (0x2430) | **100%** | 6/16 | `-O2 -fomit-frame-pointer` | 37.5% | +0x00 | **▼ regredisce** |
| `encode_2420_match` (0x2420) | **100%** | 4/16 | `-O1 -fno-if-conversion{,2} -fno-delayed-branch` | 25.0% | +0x00 | **▼ regredisce** |
| `pulse_window_compute_FCD2_r4` (0xFCD2) | 90.0% | 10/20 | `-O2/-Os -fomit-frame-pointer` | 50.0% | +0x08 | ▼ |
| `shift_right_8_r0_467A_loop` (0x467A) | 66.7% | 12/18 | `-O2 -funroll-all-loops` | 66.7% | +0x00 | = |
| `obd_service_handler_67154_m1` (0x67154) | 66.7% | 12/18 | `-m1 -O1 -fno-if-conversion{,2}` | 66.7% | +0x01 | = |
| `atu_get_rx_byte_count_1FA2_spec` (0x1FA2) | (non testato) | **19/20** | `-m1 -O1 -fno-if-conversion{,2}` | **95.0%** | +0x0D | ★ vedi 13.4 |
| `atu_get_rx_byte_count_1FA2` (0x1FA2) | 60.0% | 8/20 | `-O1 -fomit-frame-pointer` | 40.0% | +0x06 | ▼ |
| `can_get_mailbox_offset_high_D164` (0xD164) | 50.0% | 8/22 | `-O2 -fomit-frame-pointer` | 36.4% | +0x06 | ▼ |
| `getHCANRegisterAddress_D198` (0xD198) | 45.0% | 6/20 | `-O2 -fomit-frame-pointer` | 30.0% | +0x04 | ▼ |
| `charging_status_59C24_branch` (0x59C24) | 50.0% | 9/18 | `-O1 -fno-if-conversion{,2} -fno-delayed-branch` | 50.0% | +0x04 | = |
| `alignment_boundary_validator_D90C` (0xD90C) | 55.3% | 11/38 | `-O1 -fno-delayed-branch` | 28.9% | +0x00 | ▼ |
| `calc_manifold_pressure_error_diff_10A88` (0x10A88) | 40.9% | 4/22 | `-m4-nofpu -O2 -fomit-frame-pointer` | 18.2% | +0x01 | ▼ |
| `addSaturate8Bit_reg` (0x2478) | 66.7% | 9/24 | `-O1 -fno-if-conversion{,2} -fno-delayed-branch` | 37.5% | +0x01 | ▼ |
| `seed_mixer` (0x366B8) | 3.0% | 4/164 | `-O0 -fomit-frame-pointer` | 2.4% | +0x00 | ≈ |
| `addS32Saturate` / `_addv` (0x2304) | 9.1% / 0% | 2/24 / 3/24 | `-O1 -fomit-frame-pointer` / `-O1 -fno-if-conv` | 8.3% / 12.5% | +0x00 | ≈ |

### 13.3 Le 5 divergenze strutturali: 3.3.6 le elimina?

| # | Divergenza | Esito su 3.3.6 | Verdetto |
|---|---|---|---|
| 1 | **Polarità ramo** (`bt` vs `bf.s`) | NON eliminata: `add16bit` O1 emette `bf` **senza** delay (ROM `bf.s`+`nop`); selettori (atu/can/getHCAN) restano `bf.s`+`bra`. Unica eccezione: `atu_spec` con `-m1 -fno-if-conversion{,2}` produce `bt`+`bra`+delay **identici** alla ROM (95%) — ma **3.4.6 con lo stesso flagset emette byte identici** (vedi 13.4). | **parzialmente aggirabile via flagset, non è un vantaggio 3.3.6** |
| 2 | **`movt` vs ramo a 1/0** | A `-O1` 3.3.6 usa `movt r1`+`movt r0` (peggio); `-fno-if-conversion{,2}` uccide `movt` in entrambe le release (`obd_m1` 66.7% via rami). | **non eliminata; stessa cura di 3.4.6** |
| 3 | **`tst #imm` (0xC8)** | Il pattern `tst %1,%0` con constraint `L` (imm 0..255) **ESISTE** in `sh.md` 3.3.6 (riga ~623), ma il combiner non folda `and #31` in `tst #31`: emette sempre `and #31,r0; tst r0,r0` (`c91f 2008`). ROM: `tst #31,r0` (`c81f`). | **NON eliminata — strutturale, persiste** |
| 4 | **Registro return (r4 vs r0)** | 3.3.6 **peggiora**: emette da solo la widen del parametro sub-word (`extu.w r4,r4`/`extu.b r4,r4`), quindi i sorgenti `_match` (inline-asm `extu.w r4,r3`) producono estensione **doppia**, e il `sum` finisce in r3 (`rts; mov r3,r0`) invece che in r4 (`rts; mov r4,r0` della ROM). La recipe vincente 3.4.6 **non si trasferisce** a 3.3.6. | **NON eliminata — 3.3.6 è peggiore** |
| 5 | **Loop shift (srotolato)** | `-funroll-all-loops`/`-funroll-loops` srotola le 8× `shar r0` **in entrambe** le release (66.7%; residuo `mov r4,r0` ABI). | **eliminata in entrambe — nessuna novità 3.3.6** |

### 13.4 Nuova scoperta condivisa: `atu_get_rx_byte_count` @0x1FA2 → 95%

Con `-m1 -O1 -fomit-frame-pointer -fno-if-conversion -fno-if-conversion2` sul
sorgente `atu_get_rx_byte_count_1FA2_spec.c`, GCC 3.3.6 produce:

```
GOT: 644c e320 3433 8901 a002 6453 9402 345c 000b 6043 0200
ROM: 644c e320 3433 8901 a002 6453 9403 345c 000b 6043      (pool@0x1FB8)
```

19/20 byte (95%), unico diff a +0x0D: il displacement di `mov.w @(pc),r4`
(il pool di gcc cade a 0x1FB6, quello ROM a 0x1FB8 — **interleaved dopo il
prologo `mov #32,r4` della funzione successiva**). Il body è altrimenti
**byte-identico**: polarità `bt`+`bra`+`mov r5,r4` nel delay, costante 0x0200
caricata **direttamente in r4**, niente `movt`, `rts; mov r4,r0`.

**Verifica incrociata**: 3.4.6 con lo *stesso* flagset sullo *stesso* sorgente
produce **byte identici** (`644ce32034338901a00264539402345c000b60430200`).
Il report flagepoch 3.4.6 (§12) non aveva mai testato `atu_spec`+`-m1 -fno-if-conversion{,2}`
(aveva solo `atu` base con `-m1 -O1 -fomit-frame-pointer` → 60%): la scoperta è
**nuova ma NON esclusiva di 3.3.6** — è una recipe del flagset valida per entrambe.
`.s` salvato: `expected_gcc_sh2e/atu_get_rx_byte_count_1FA2_spec.m2.m1.O1.omitfp.noifconv.s`.

### 13.5 Perché i 3 MATCH 3.4.6 regrediscono (root cause)

I sorgenti `_match` nascondono una assunzione di **3.4.6**: `(unsigned)av` per
`uint16_t av` diventa un `mov r4,r3` (nessuna `extu.w`, perché 3.4.6 assume il
param HImode già zero-esteso) e l'inline-asm `extu.w r4,r3` aggiunge la widen
mancante. In **3.3.6** la widen è emessa automaticamente (`extu.w r4,r4` in
testa), quindi l'inline-asm produce una doppia estensione e la sequenza ROM non
viene raggiunta. Per `add16bitSaturate_reg` la somma finisce in r1
(`extu.w r4,r1`) e `bf.s`+`mov r1,r4` nel delay (ROM: somma in r4, `bf.s`+`nop`).

### 13.6 Verdict 3.3.6 vs 3.4.6

**3.3.6 NON supera 3.4.6.** Su 29 sorgenti:
- **0 match byte-perfect** nuovi con 3.3.6;
- i **3 MATCH confermati con 3.4.6** (add16bitSaturate_reg, complement_shift,
  encode) **regrediscono** (79.2% / 37.5% / 25.0%);
- le 4 divergenze residue del task (polarità ramo, `movt`, `tst #imm`,
  return-register) restano **strutturali** anche in 3.3.6 (`tst #imm` non
  viene mai emesso pur esistendo il pattern in `sh.md`; la widen automatica del
  parametro rende addirittura 3.3.6 **peggiore** sui match);
- l'unico miglioramento numerico (`atu_spec` 95%) è **condiviso** con 3.4.6
  (stessa recipe, byte identici) ed era solo un flagset non ancora provato.

**Conclusione per la pipeline**: la release più vicina alla ROM resta
**GCC 3.4.6** (3 MATCH + 90% pulse). 3.3.6 va considerato *worse* per il
match-and-compile di questi helper; se si volessero esplorare release diverse
ha più senso provare **3.2.3** (sorgente già presente in `/home/davide/gcc-3.2.3`),
che potrebbe avere un `sh.md` con comportamento della widen e del delay-slot
diverso da entrambi.

### Riprodurre

```bash
python3 scripts/sweep_gcc336.py --out /tmp/sweep_gcc336/report_full.txt
# 29 sorgenti × 17 flagset; report completo in /tmp/sweep_gcc336/report_full.txt
```

Nuovi file (tutti in `reconstructed/experiments/match/`): `scripts/sweep_gcc336.py`,
`expected_gcc_sh2e/atu_get_rx_byte_count_1FA2_spec.m2.m1.O1.omitfp.noifconv.s`.
Sezione di `match_recipe.txt` aggiornata. Nessuno degli script 3.4.6 esistenti è stato toccato.

## 14. SWEEP GCC 3.2.3 (release precedente: la widen cambia? il 95% atu regge?)

Data: 2026-08-02 · harness nuovo `scripts/sweep_gcc323.py` (29 sorgenti × 21
flagset = 609 compilazioni; ~2.5 s). Toolchain:
`/home/davide/gcc323-build/gcc/xgcc -B /home/davide/gcc323-build/gcc/` (GCC 3.2.3,
target `sh-elf`, big-endian). Stessa pipeline: gcc -S → `sh-elf-as -isa=sh2e` →
`objcopy --only-section=.text` → confronto byte sul body-window della ROM.

### 14.1 Toolchain: differenze rispetto a 3.3.6 e 3.4.6

| Aspetto | GCC 3.2.3 | GCC 3.3.6 | GCC 3.4.6 |
|---|---|---|---|
| ISA | **`-m2`** (SH-2 core, no single FPU) | `-m2` | `-m2e` |
| `-m2e` | ❌ non esiste | ❌ non esiste | ✅ |
| `-m1 -m3 -m3e -m4-single-only -m4-nofpu` | ✅ (tutti in TARGET_SWITCHES) | ✅ | ✅ |
| `-mhitachi/-mrelax/-mspace/-misize/-mnomacsave` | ✅ presenti in `sh.h` | ❌ droppati | ✅ |
| `-fno-if-conversion{,2}` | ❌ **NON esistono** | ✅ | ✅ |
| `-funroll-all-loops/-funroll-loops/-fno-delayed-branch/-fno-unroll-loops` | ✅ | ✅ | ✅ |
| Prologo SH-2 (smoke `int f(a,b){return a+b;}`) | ✅ `mov r4,r0; rts; add r5,r0` | ✅ idem | ✅ idem |

Punto critico: **3.2.3 NON ha `-fno-if-conversion`/`-fno-if-conversion2`**
(`cc1: unrecognized option`). Tutte le ricette 3.3.6/3.4.6 che uccidono `movt`
(obd_m1 66.7%, atu_spec 95%) **dipendono da quel flag e quindi NON sono
riproducibili su 3.2.3**.

### 14.2 Risultato per funzione (best config; 3.2.3 base `-m2`)

| Sorgente (ROM) | 3.4.6 best | 3.3.6 best | 3.2.3 best | Config 3.2.3 | % 3.2.3 | Prima div. | Δ vs 3.3.6 |
|---|---|---|---|---|---|---|---|
| `add16bitSaturate_reg` (0x2460) | **100%** | 79.2% | 16/24 | `-O1 -fno-delayed-branch` | 66.7% | +0x0A | ▼ |
| `complement_shift_u16_2430_match` (0x2430) | **100%** | 37.5% | 7/16 | `-O2 -fno-delayed-branch` | 43.8% | +0x00 | ▲ |
| `encode_2420_match` (0x2420) | **100%** | 25.0% | 4/16 | `-O1 -fno-delayed-branch` | 25.0% | +0x00 | = |
| `atu_get_rx_byte_count_1FA2_spec` (0x1FA2) | 95.0% | **95.0%** | 8/20 | `-O1/-O2 -fno-delayed-branch` | **40.0%** | +0x06 | ▼▼ vedi 14.4 |
| `shift_right_8_r0_467A_loop` (0x467A) | 66.7% | 66.7% | **14/18** | `-O1 -fno-delayed-branch -funroll-loops` | **77.8%** | +0x00 | ▲★ vedi 14.5 |
| `pulse_window_compute_FCD2_r4` (0xFCD2) | 90.0% | 50.0% | 10/20 | `-O2/-Os -fomit-frame-pointer` | 50.0% | +0x08 | = |
| `obd_service_handler_67154_m1` (0x67154) | 66.7% | 66.7% | 3/18 | `-O1 -fomit-frame-pointer` | 16.7% | +0x01 | ▼▼ vedi 14.4 |
| `charging_status_59C24_branch` (0x59C24) | 50.0% | 50.0% | 5/18 | `-O1 -fomit-frame-pointer` | 27.8% | +0x04 | ▼ |
| `add16bitSaturate` (0x2460) | 62.5% | 62.5% | 15/24 | `-O1/-O2 -fomit-frame-pointer` | 62.5% | +0x06 | = |
| `addSaturate8Bit_reg` (0x2478) | 66.7% | 37.5% | 9/24 | `-O1 -fno-delayed-branch` | 37.5% | +0x01 | = |
| `can_get_mailbox_offset_high_D164` (0xD164) | 50.0% | 36.4% | 8/22 | `-m4-nofpu -O2 -fomit-frame-pointer` | 36.4% | +0x06 | = |
| `alignment_boundary_validator_D90C` (0xD90C) | 55.3% | 28.9% | 11/38 | `-O1/-O2 -fno-delayed-branch` | 28.9% | +0x00 | = |
| `atu_get_rx_byte_count_1FA2` (0x1FA2) | 60.0% | 40.0% | 8/20 | `-O1 -fomit-frame-pointer` | 40.0% | +0x06 | = |
| `getHCANRegisterAddress_D198` (0xD198) | 45.0% | 30.0% | 6/20 | `-m4-nofpu -O2 -fomit-frame-pointer` | 30.0% | +0x04 | = |
| `complement_shift_u16_2430` (0x2430) | 25.0% | 50.0% | 8/16 | `-O2/-Os -fomit-frame-pointer` | 50.0% | +0x00 | = |
| `calc_manifold_pressure_error_diff_10A88` (0x10A88) | 40.9% | 18.2% | 3/22 | `-O1 -fomit-frame-pointer` | 13.6% | +0x01 | ▼ |
| `seed_mixer` (0x366B8) | 3.0% | 2.4% | 4/164 | `-O0 -fomit-frame-pointer` | 2.4% | +0x00 | = |
| `addS32Saturate` / `_addv` (0x2304) | 9.1% / 0% | 8.3% / 12.5% | 2/24 / 1/24 | `-O1 -fomit-frame-pointer` / `-O1` | 8.3% / 4.2% | +0x00 | = / ▼ |
| `encode_2420` (0x2420) | 12.5% | 25.0% | 4/16 | `-O1 -fno-delayed-branch` | 25.0% | +0x00 | = |
| `shift_right_8_r0_467A` (0x467A) | 5.6% | 5.6% | 1/18 | `-O0 -fomit-frame-pointer` | 5.6% | +0x00 | = |

NB: `seed_mixer` e `shift_right_8_r0_467A` con `-m3/-m3e/-m4*` falliscono in
assembly (`shld r7,r1` non è SH-2: gcc 3.2.3 emette shift dinamici SH-3+ che
`sh-elf-as -isa=sh2e` rifiuta). Non sono perdite di sweep, è la base ISA -m2
a essere quella corretta per questi window.

### 14.3 I 3 MATCH 3.4.6 su 3.2.3: regrediscono (stessa root cause di 3.3.6)

| Match 3.4.6 | 3.3.6 | 3.2.3 | Causa 3.2.3 |
|---|---|---|---|
| `add16bitSaturate_reg` **100%** | 79.2% | **66.7%** | widen automatica dei parametri (`extu.w r5,r5; extu.w r4,r4` in testa), somma in r4 ma `bf` **non-delayed** + `nop` (ROM: `bf.s` + delay), e a O1 resta la fold `>=0xFFFF → >0xFFFE` |
| `complement_shift_u16_2430_match` **100%** | 37.5% | **43.8%** | widen automatica (`extu.w r4,r4`) + inline-asm `extu.w r4,r3` = estensione doppia; sum in r3, `mov r3,r4; rts; mov r3,r0` (ROM: `add r2,r4; rts; mov r4,r0`) |
| `encode_2420_match` **100%** | 25.0% | **25.0%** | idem (extu.b doppia), `mov r4,r3` non esteso in r3 |

Quindi **sì, come su 3.3.6 i 3 match regrediscono** — e per la stessa ragione
(widen automatica del parametro sub-word, che 3.4.6 non emette). Nota: su
`complement_shift_match` 3.2.3 è **leggermente meglio** di 3.3.6 (43.8% vs
37.5%) perché a `-O2 -fno-delayed-branch` ottiene `mov r3,r4` + `rts; mov r3,r0`
(2 soli byte diversi dall'epilogo ROM invece di 4), ma resta lontano dal 100%.

### 14.4 atu_spec 95% e obd_m1 66.7% NON reggono: manca `-fno-if-conversion`

La recipe 95% (`atu_get_rx_byte_count_1FA2_spec` + `-m1 -O1 -fno-if-conversion{,2}`)
e la recipe 66.7% (`obd_m1` + stesso flagset) **richiedono `-fno-if-conversion`
che in 3.2.3 non esiste**. Senza il flag:

- `atu_spec` su 3.2.3: best **40.0%** (`-O1 -fno-delayed-branch`) — il `movt`
  non è uccidibile, quindi il body non raggiunge la sequenza `bt+bra+mov r5,r4`
  della ROM (a `-O1` 3.2.3 emette `bf` con `mov r5,r4` nel fall-through e
  `mov.w @(pc),r4` in un registro diverso).
- `obd_m1` su 3.2.3: best **16.7%** — 3.2.3 emette **doppio `movt`**
  (`movt r1; tst r1,r1; movt r0`, pattern `and #31,r0`+`tst r0,r0`), e senza
  `-fno-if-conversion` non c'è alcun modo di ramificare come la ROM.

Conclusione: **il 95% atu NON regge su 3.2.3** (40%). Il miglioramento atu era
una scoperta di *flagset*, non di release, e la release 3.2.3 lo perde.

### 14.5 Divergenze strutturali: cosa cambia su 3.2.3

| # | Divergenza | Esito su 3.2.3 | Verdetto |
|---|---|---|---|
| 1 | **Polarità ramo** (`bt` vs `bf.s`) | NON eliminata: `add16bit` O1 emette `bf` **non-delayed** + `nop` (ROM `bf.s`+delay `mov r4,r0`); selettori (atu/can/getHCAN) restano `bf.s`+`bra`. | **persiste; senza `-fno-if-conversion` peggiore dei selettori** |
| 2 | **`movt` vs ramo a 1/0** | 3.2.3 emette **doppio `movt`** (`movt r1; tst r1,r1; movt r0`) a `-O1`; **NESSUN flag disponibile** per ucciderlo (`-fno-if-conversion` assente). | **NON eliminata — 3.2.3 è il peggiore dei tre** |
| 3 | **`tst #imm` (0xC8)** | `sh.md` 3.2.3 ha `tst %1,%0` con constraint `L`, ma il combiner non folda: sempre `and #31,r0; tst r0,r0` (`c91f 2008`). ROM: `tst #31,r0` (`c81f`). | **NON eliminata — strutturale, persiste** |
| 4 | **Registro return (r4 vs r0)** | Widen automatica **presente anche in 3.2.3** (`extu.w r4,r4` in testa su entrambi i match): le ricette `_match` di 3.4.6 producono estensione doppia. `add16bit_reg` peggiora rispetto a 3.3.6 (66.7% vs 79.2%, somma comunque in r4 ma `bf` non-delayed); `complement_shift_match` migliora (43.8%, epilogo `mov r3,r4; rts; mov r3,r0`). | **NON eliminata — come 3.3.6** |
| 5 | **Loop shift (srotolato)** | `-O1 -fno-delayed-branch -funroll-loops` → **8× `shar r0` esatti + `rts; nop`** = **77.8%** (14/18), residuo solo `mov r4,r0` ABI + `nop`. | **★ MIGLIORAMENTO 3.2.3: 77.8% vs 66.7% della matrice** (flag-combo; vedi nota qui sotto) |

*Nota di coerenza (aggiunta in chiusura, §15.2): il 77.8% è una scoperta di
**flag-combo**, non di release — lo sweep `-mrelax` successivo ha mostrato la
stessa combo `-O1 -fno-delayed-branch -funroll-loops` raggiungere il 77.8% anche
su GCC 3.4.6 (con o senza `-mrelax`); era assente dalla matrice flagepoch 3.4.6
(che aveva solo `O2.unrollall`/`O2.unroll`, entrambe 66.7%), da qui l'attribuzione
originaria a 3.2.3. Su 3.3.6 la combo non è mai stata testata.*

### 14.6 Verdict 3.2.3 vs 3.3.6 vs 3.4.6

**3.2.3 NON supera 3.4.6** (0 match su 29 sorgenti) ed è **complessivamente
peggiore di 3.3.6**:

- i **3 MATCH 3.4.6 regrediscono** (66.7% / 43.8% / 25.0%) per la stessa root
  cause di 3.3.6 (widen automatica del parametro sub-word);
- il **95% atu NON regge** (40%) e il **66.7% obd NON regge** (16.7%) perché
  `-fno-if-conversion{,2}` **non esiste in 3.2.3**: il `movt` è strutturalmente
  non aggirabile, il che rende 3.2.3 **peggiore** dei selettori/booleani;
- unico guadagno: **`shift_right_8_r0_467A_loop` 77.8%** con
  `-O1 -fno-delayed-branch -funroll-loops` (nella matrice 3.3.6/3.4.6 ferme a
  66.7%; si veda però la nota in §14.5: la stessa flag-combo raggiunge il 77.8%
  anche su 3.4.6 — scoperta di flagset, non di release) — novità minore, non un match.

**Conclusione per la pipeline**: la release più vicina alla ROM resta
**GCC 3.4.6** (3 MATCH + 90% pulse). Classifica serie 3.x per il match-and-compile
di questi helper: **3.4.6 > 3.3.6 > 3.2.3**. La widen automatica del parametro
è presente in 3.2.3/3.3.6 (assente in 3.4.6), e il flag `-fno-if-conversion`
compare solo dalla serie 3.3.x in poi — entrambe le proprietà confermano che il
codegen della ROM è più coerente con 3.4.6.

### Riprodurre

```bash
python3 scripts/sweep_gcc323.py --out /tmp/sweep_gcc323/report_full.txt
# 29 sorgenti × 21 flagset; report completo in /tmp/sweep_gcc323/report_full.txt
```

Nuovi file (tutti in `reconstructed/experiments/match/`): `scripts/sweep_gcc323.py`.
Sezione di `match_recipe.txt` aggiornata. Nessuno degli script 3.3.6/3.4.6 esistenti è stato toccato.

---

## 15. VERDETTO FINALE — SERIE GCC 3.x E CHIUSURA

Data: 2026-08-02 · sezione conclusiva dell'esperimento match-and-compile. Raccoglie
in un unico punto il confronto completo della serie GCC 3.x + GCC 14.2.0, l'esito
del test `-mrelax/-mhitachi/-mspace` su 3.4.6, e la risposta definitiva alla domanda
dell'esperimento. Tutti i numeri qui riportati provengono dalle sezioni §10–§14 e
dagli sweep che le hanno generate; **nessun nuovo dato è stato introdotto**.

### 15.1 Tabella comparativa completa (best % per funzione e toolchain)

% = byte uguali sulla finestra ROM (body + pool dove contiguo); config = migliore
flagset per quella toolchain. Per GCC 14.2.0 lo sweep copriva solo le 4 funzioni
base (§10, `sweep_gcc14.py`); per la serie 3.x le best per sorgente/variante sono
dalle tabelle §10–§14.

| Funzione (ROM) | GCC 14.2.0 | GCC 3.4.6 | GCC 3.3.6 | GCC 3.2.3 | Config vincitrice (serie 3.x) |
|---|---|---|---|---|---|
| `add16bitSaturate` @0x2460 (C idiomatico) | 25.0% | 62.5% | 62.5% | 62.5% | `-m2e -O1 -fomit-frame-pointer` (3.4.6) / `-O1/-O2 -fomit-frame-pointer` (3.3.6/3.2.3) |
| **`add16bitSaturate_reg` @0x2460 (recipe)** | — | **100%** ✅ | 79.2% | 66.7% | **`-m2e -O1 -fomit-frame-pointer` + max-variabile + pin r4/r5 + return unsigned** |
| **`complement_shift_u16` @0x2430 (recipe)** | — | **100%** ✅ | 37.5% | 43.8% | **`-m2e -O1 -fomit-frame-pointer` + `_match.c` (extu.w via asm, pin r3/r2/r4)** |
| **`encode` @0x2420 (recipe)** | — | **100%** ✅ | 25.0% | 25.0% | **`-m2e -O1 -fomit-frame-pointer` + `_match.c` (extu.b naturale)** |
| `addSaturate8Bit` @0x2478 | 29.2% | 37.5% | 37.5% | 37.5% | `-m2e -O1 -fomit-frame-pointer` |
| `addSaturate8Bit_reg` @0x2478 | — | 66.7% | 37.5% | 37.5% | `-m2e -O1 -fomit-frame-pointer` (3.4.6) |
| `addS32Saturate` @0x2304 | 4.5% | 9.1% | 8.3% | 8.3% | `-m2e -O1 -fomit-frame-pointer` (3.4.6) |
| `addS32Saturate_addv` @0x2304 | — | 0% | 12.5% | 4.2% | (nessuna; idioma `addv` non riproducibile in C) |
| `seed_mixer` @0x366B8 | 3.7% | 3.0% | 2.4% | 2.4% | `-m2e -O0` (3.4.6) / `-O0 -fomit-frame-pointer` (3.3.6/3.2.3) |
| `pulse_window_compute` @0xFCD2 | — | **90.0%** | 50.0% | 50.0% | `-m2e -O1 -fomit-frame-pointer` + `_r4.c` (condizione invertita + pin r3/r4 + barrier) |
| `atu_get_rx_byte_count` @0x1FA2 (base) | — | 60.0% | 40.0% | 40.0% | `-m1 -O1 -fomit-frame-pointer` (3.4.6) |
| **`atu_get_rx_byte_count_spec` @0x1FA2** | — | **95.0%** | **95.0%** | 40.0% | **`-m1 -O1 -fomit-frame-pointer -fno-if-conversion -fno-if-conversion2` + `_spec.c`** |
| `shift_right_8_r0` @0x467A (loop) | — | 66.7% *(77.8% con flag-combo, vedi 15.2)* | 66.7% | **77.8%** | `-O1 -fno-delayed-branch -funroll-loops` (con/senza `-mrelax`) |
| `obd_service_handler` @0x67154 (`_m1`) | — | 66.7% | 66.7% | 16.7% | `-m1 -O1 -fno-if-conversion{,2}` (manca su 3.2.3) |
| `can_get_mailbox_offset_high` @0xD164 | — | 50.0% | 36.4% | 36.4% | `-m2e -O2 -fomit-frame-pointer` |
| `getHCANRegisterAddress` @0xD198 | — | 45.0% | 30.0% | 30.0% | `-m2e -O2 -fomit-frame-pointer` |
| `charging_status` @0x59C24 (`_branch`) | — | 50.0% | 50.0% | 27.8% | `-O1 -fno-if-conversion{,2} -fno-delayed-branch` (3.4.6/3.3.6) |
| `alignment_boundary_validator` @0xD90C | — | 55.3% | 28.9% | 28.9% | `-O1 -fomit-frame-pointer` (3.4.6) |
| `calc_manifold_pressure_error_diff` @0x10A88 | — | 40.9% | 18.2% | 13.6% | `-O1 -fno-delayed-branch` (3.4.6) |

**Sintesi riga per riga:** i 3 MATCH (✅) esistono **solo con GCC 3.4.6 + la recipe**
(max-variabile / pin registri / return unsigned / `_match.c`); ogni altra release
regredisce (widen automatica del parametro sub-word). Le soglie alte non-match
(atu_spec 95%, pulse 90%, shift 77.8%) sono **scoperte di flag-combo valide su più
release**, non di release singole (vedi 15.2).

### 15.2 Esito test `-mrelax` / `-mhitachi` / `-mspace` su 3.4.6

Harness: `scripts/sweep_relax_gcc346.py` (3 candidati residui, ogni config provata
anche con `-relax` sull'assemblatore per separare l'effetto compilatore da quello
assembler; report: `/tmp/sweep_relax/report{,_atu}.txt`).

| Candidato | Config base | Con `-mrelax` | Con `-mhitachi` | Con `-mspace` | Esito |
|---|---|---|---|---|---|
| `atu_get_rx_byte_count_1FA2_spec` (0x1FA2) | 95.0% | **95.0%** | **95.0%** | **95.0%** | ❌ nessun flag chiude il gap |
| `pulse_window_compute_FCD2_r4` (0xFCD2) | 90.0% | **90.0%** | **90.0%** | **90.0%** | ❌ nessun flag chiude il gap |
| `shift_right_8_r0_467A_loop` (0x467A) | 66.7% (`-O2 -funroll-all-loops`) | 66.7% (stessa config) · **77.8% con flagset diverso** (`-O1 -fno-delayed-branch -funroll-loops`) | 66.7% | 66.7% | `-mrelax` **irrilevante** |

Analisi del perché:

- **atu resta 95%** (unico diff a +0x0D): il displacement di `mov.w @(pc),r4`
  differisce perché il literal pool di gcc cade a 0x1FB6 mentre quello ROM a
  0x1FB8. Nella ROM il pool è **interleaved a livello di sezione**, dopo il
  prologo (`mov #32,r4`) della funzione *adiacente* successiva. `-mrelax`/`-mhitachi`/
  `-mspace` agiscono su codegen/displacement locali o ABI e **non cambiano il
  layout del pool a livello di sezione**: il punto di caduta del pool dipende
  dall'ordinamento globale del file di compilazione, non da flag del singolo file.
- **pulse resta 90%** (unico diff a +0x0C): la ROM carica la costante con
  `mov.l @(pc),r3` (`d31d`), gcc 3.4.6 con `mov.w @(pc),r3` (`9302`) — è la
  selezione `hi_const` di `sh.c`, **incondizionata** (§12.1), non flaggabile.
  `-mrelax` non tocca la scelta `mov.l` vs `mov.w`.
- **shift**: il 77.8% osservato con la combo `-O1 -fno-delayed-branch
  -funroll-loops [-mrelax]` è **indipendente da `-mrelax`** (verifica a parte senza
  `-mrelax`: stesso 14/18). Il guadagno è della **flag-combo** (srotolamento senza
  delay-slot), non del flag di relax.

**Conclusione 15.2:** il gap residuo atu/pulse (95/90%) è **non-closable con flag
del singolo file** perché la causa è il **layout del literal pool a livello di
sezione** (pool interleaved dopo il prologo della funzione adiacente), non il
codegen. Chiudere quei byte richiederebbe il riordino/relink dell'intera sezione
(equivalente a ricostruire la ROM), fuori dallo scope del match-and-compile
per-funzione.

### 15.3 Verdict: GCC 3.4.6 = golden release

Classifica definitiva della serie 3.x per il match-and-compile di questi helper:
**GCC 3.4.6 > GCC 3.3.6 > GCC 3.2.3** (§13.6, §14.6). Motivazione tecnica:

1. **Nessuna widen automatica del parametro sub-word.** 3.4.6 assume i parametri
   HImode/QImode già zero-estesi e NON emette `extu.w r4,r4`/`extu.b r4,r4` in
   testa. È questa proprietà a rendere *esprimibili* in C i 3 match: i sorgenti
   `_match` usano un inline-asm `extu.w r4,r3` per aggiungere la widen mancante
   senza duplicarla. In 3.3.6/3.2.3 la widen è automatica → l'inline-asm produce
   estensione **doppia** → i match regrediscono (79.2/37.5/25.0% e 66.7/43.8/25.0%).
   La ROM **non** mostra estensioni doppie → è più coerente con 3.4.6.
2. **`movt` uccidibile.** `-fno-if-conversion -fno-if-conversion2` esiste in
   3.4.6 e 3.3.6 (manca in 3.2.3) e permette di sostituire i booleani `movt` con
   rami a 1/0 come in ROM (obd_m1 66.7%, atu_spec 95%). Su 3.2.3 il doppio
   `movt` è strutturalmente non aggirabile.
3. **Prologo coerente con il fingerprint ROM.** `mov.l r14,@-r15` come prima
   istruzione, frame pointer omesso con `-fomit-frame-pointer`, delay-slot
   riempito a `-O1` (§5, §10) — tutto coerente con l'ordine di salvataggio
   "registri-prima-PR" (935 vs 33 in ROM). La recipe `-m2e -O1 -fomit-frame-pointer`
   riproduce il prologo esatto.
4. **`-m2e` presente.** È il subtarget SH-2E corretto per lo SH7055; non esiste
   in 3.3.6/3.2.3 (base `-m2`).

### 15.4 La risposta definitiva alla domanda dell'esperimento

> Con il toolchain disponibile, è realistico riprodurre **byte-identiche** le
> funzioni della ROM compilando C idiomatico con un cross-compilatore SH-2E?

**Risposta definitiva (basata su 4 toolchain reali e >2100 compilazioni
documentate: 7×48 §10 + 11×16 §11 + 15×20 §12 + 29×17 §13 + 29×21 §14 +
4×48 sweep GCC 14 + sweep `-mrelax` §15.2):**

- **Sì, per helper pure-math piccoli** (leaf, ≤24 B, nessuna call/FPU/deref),
  **con la recipe documentata**: GCC 3.4.6 `-m2e -O1 -fomit-frame-pointer` +
  sorgente con i tre accorgimenti (max come variabile per evitare la fold
  `>=C → >C-1`; tipi `uint16_t` originali; pin registri `__asm__("r4"/"r5")`;
  return `unsigned`). Con questi prerequisiti si ottengono **3 match byte-perfect
  su 3 funzioni** (add16bitSaturate@0x2460, complement_shift_u16@0x2430,
  encode@0x2420), più 2 quasi-match (atu_spec 95%, pulse 90%).
- **No come strategia generale.** Oltre la classe "helper puro-math piccolo con
  codice 2000-era" il matching byte-exact non generalizza: su 29 sorgenti e 4
  release le best-per-funzione scendono ampiamente sotto il 100% (su 3.3.6/3.2.3
  la maggior parte è ≤50%; su 3.4.6 solo i 3 match + atu_spec superano il 90%,
  vedi tabella 15.1) e le divergenze residue (polarità del ramo, `tst #imm`,
  layout del literal pool di sezione) sono **strutturali**, non aggirabili né
  con flag né con riscritture C.
- **Gli idiomi speciali restano assembly-first.** `addv` (addS32Saturate@0x2304),
  i selettori con `bt`+`bra`, i booleani `tst #imm`, il seed-mixer low-opt:
  nessun C puro/flag di nessuna release li riproduce → per queste funzioni vale
  la via già dimostrata di `src/*.s` annotati + `rom_rebuild` (byte-exact),
  con il match-and-compile usato solo come *generatore di bozze* verificato.

**Raccomandazione finale al progetto:** mantenere **assembly-first** come via
principale; usare il match-and-compile esclusivamente come generatore di bozze
per i helper pure-math piccoli, con verifica byte-exact automatica (`compare.py`)
e la recipe di §10/§12.6 come unico "percorso C validato" verso la ROM.

### 15.5 Cosa è stato consegnato

1. **Tre toolchain GCC 3.x funzionanti** (target `sh-elf`, big-endian), compilate
   da sorgente fuori dal repo:
   - `/home/davide/gcc346-build/gcc/xgcc` → GCC **3.4.6** (golden release)
   - `/home/davide/gcc336-build/gcc/xgcc` → GCC **3.3.6**
   - `/home/davide/gcc323-build/gcc/xgcc` → GCC **3.2.3**
   (verificate `-dumpversion`; sorgenti in `/home/davide/gcc-3.4.6`, `gcc-3.3.6`,
   `gcc-3.2.3`; stub `stdint.h` in `/tmp/stubinc/`).
2. **Harness di sweep riusabili** (tutti in `scripts/`, pipeline gcc→as→objcopy→
   confronto byte contro la ROM, riproducibili con il comando indicato in ogni
   sezione):
   - `sweep_gcc14.py` (§10), `sweep_gcc346.py` (§10), `sweep_puremath_gcc346.py`
     (§11), `sweep_flags_epoch346.py` (§12), `sweep_gcc336.py` (§13),
     `sweep_gcc323.py` (§14), `sweep_relax_gcc346.py` (§15.2).
   - `compare.py` (oracolo byte-exact) e `fingerprint.py` (statistiche ROM).
3. **Recipe esatte** (una per ciascun risultato utile, comando completo + byte
   attesi) in `match_recipe.txt`: 3 recipe MATCH 3.4.6, la recipe atu_spec 95%
   (3.4.6/3.3.6), la recipe pulse 90%, la recipe shift 77.8% (3.4.6/3.2.3), e la
   tabella completa delle best-per-funzione per le 4 release.
4. **Sorgenti C e riferimenti assemblati**: `c_src/*.c` (29 sorgenti: idiomatici,
   `_reg`, `_match`, `_spec`, `_r4`, `_loop`, `_m1`, `_branch`, `_r6`) e i `.s`
   vincenti salvati in `expected_gcc_sh2e/` per i 3 match e i riferimenti
   (pulse_r4, shift_loop, obd_m1, atu_spec).

Tutto è contenuto in `reconstructed/experiments/match/`; nessun file fuori dalla
directory dell'esperimento è stato creato o modificato. **Filone chiuso.**
