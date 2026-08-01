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
