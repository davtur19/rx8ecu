# Esperimento: match-and-compile per il PCM RX-8 (SH-2E/SH7055)

Data: 2026-08-01 · ROM: `roms/stock/60E1D400.bin` (512 KB, big-endian, base 0x60000000)
Dir: `reconstructed/experiments/match/` (nuova; nessun file del repo modificato)

**Domanda:** è realistico riprodurre **byte-identiche** le funzioni della ROM
compilando C idiomatico con un cross-compilatore SH-2E?
**Risposta:** sì per funzioni piccole pure-math (con gcc/SHC sh2e + matching
versione+flag); no per la maggior parte del firmware. (Prove §10–§15.)

---

## 1. Stato toolchain

| Componente | Stato |
|---|---|
| `sh-elf` binutils 2.46 (as, ld, objcopy, objdump, readelf…) | ✅ `tools/toolchain/usr/bin` (ora `tools/toolchain.bak/usr/bin`, sessione concorrente; risolto dinamicamente dagli script) |
| `sh-elf-gcc` / gcc con backend SH | ❌ assente (`tools/`, PATH, `/usr/bin`) |
| Compilatori cross nei repo ufficiali | ❌ solo `aarch64-linux-gnu-gcc` / `riscv64-linux-gnu-gcc`; nessun gcc SH (`pacman -Ss sh4` → `sh4-elf-binutils`, `qemu-system-sh4`) |
| gcc host | ✅ `gcc 16.1.1` x86_64 (solo nativo) |
| clang / zig / tcc | ❌ assenti (clang/LLVM/Zig senza backend SuperH) |
| Rete | ⚠️ mirror HTTP 200 ma host Arch senza gcc-SH: solo build da sorgente (lunga, impatto) o binari non verificati. Non ho installato nulla. |

**Conclusione:** il back-end assembly (as/ld/objcopy byte-exact, §3) funziona, ma
**manca il compilatore C SH-2E** e non è installabile in modo sicuro/semplice.

---

## 2. Funzioni target: byte estratti dalla ROM

Estratte con `scripts/extract_rom.py` → `rom_hex/*.txt` (verificati con
`tools/disasm_sh2e.py` e `sh-elf-objdump`).

| Funzione | ROM | Lunghezza | Byte (body + literal) |
|---|---|---|---|
| `add16bitSaturate` | 0x2460 | 20 B + 4 B | `644d 655d 345c d503 3452 8f01 0009 6453 000b 6043` + `0000ffff` |
| `addSaturate8Bit` | 0x2478 | 22 B + 2 B | `644c 655c 345c 634d 9505 3353 8f01 0009 6453 000b 6043` + `00ff` |
| `addS32Saturate` | 0x2304 | 18 B + 2 B pad + 4 B | `354f 8f04 6053 d003 4511 e500 305e 000b 0009` + `0009` + `7fffffff` |
| `seed_mixer` | 0x366B8 | 164 B | (`rom_hex/seed_mixer_366B8.txt`; pool a +0x166/+0x168/+0x16C) |
| `calculateImmoSeed` | 0x3675C | 276 B | (`rom_hex/calculateImmoSeed_3675C.txt`) |

Nota layout: il pool di `seed_mixer` (0x0FE0, 0x001FC000, 0xFFE0301F) è dentro la
regione di `calculateImmoSeed` (pool interleaved, tipico raccolta pool SH).

---

## 3. Esperimento match (senza gcc: predizione codegen + round-trip binutils)

Due passi: (1) **predizione codegen** `sh-elf-gcc -m2e -O2` in `expected_gcc_sh2e/*.s`
(convenzioni SH-2: arg r4..r7, ret r0, `rts`+delay, prologo senza frame pointer,
pool PC-relative), (2) **round-trip** `sh-elf-as -isa=sh2e` + `sh-elf-objcopy -O binary`,
confronto byte con la ROM (`scripts/compare.py`).

| Funzione + file `.s` | Finestra | Byte uguali | Esito |
|---|---|---|---|
| `add16bitSaturate.O2.s` | 24 B | **24/24 (100%)** | ✅ **MATCH byte-identico** |
| `addSaturate8Bit.O2.s` | 24 B | **24/24 (100%)** | ✅ **MATCH byte-identico** |
| `addS32Saturate.addv.s` (idioma `addv`) | 24 B | **24/24 (100%)** | ✅ **MATCH byte-identico** |
| `addS32Saturate.plain.s` (`add`+branch) | 24 B | 0/14 (0%) | ❌ NON-match (atteso: gcc non emette `addv`) |
| `seed_mixer.reconstruction.s` (low-opt) | 164 B | **164/164 (100%)** | ✅ **MATCH byte-identico** |

Differenze NON-match (ROM vs predette):

```
+0x00 ROM 354F addv r4,r5      | pred. 345C add r5,r4      (idioma overflow assente)
+0x02 ROM 8F04 bf/s 0x2312     | pred. 254A xor r4,r5
+0x06 ROM D003 mov.l @0x2318,r0| pred. 6043 mov r4,r0
... (7 istruzioni su 7 diverse)
```

**Onestà metodologica:** i MATCH 100% sono stati scritti **a mano come assembly**
che rispecchia la ROM (parzialmente circolare): dimostra in modo rigoroso che
(a) i binutils riproducono byte-exact le funzioni (il back-end funziona) e
(b) la ROM è **consistente** con ciò che GCC emetterebbe — ma **non prova** che un
`gcc` reale generi quelle sequenze. Serve un `sh-elf-gcc` + matching versione/flag (§7).

---

## 4. Per-funzione: verdetto

| Funzione | Verdetto match-and-compile | Perché |
|---|---|---|
| `add16bitSaturate` | **Alto potenziale** (100% con codegen -O2) | C idiomatico `uint16_t+clamp`; ROM = pattern gcc: `extu.w`, `mov.l @(pc)` per 0xFFFF, `cmp/hs`+`bf/s`, `rts; mov r4,r0`. |
| `addSaturate8Bit` | **Alto potenziale** | Idem con `mov.w @(pc)` per 255 e `cmp/ge` (valore ≥0 dopo `extu.w`). |
| `addS32Saturate` | **NO per C idiomatico** (solo idioma `addv`) | ROM usa `addv`+`cmp/pz`+`addc`; gcc 2002-era non lo emette per C puro (serve `__builtin_add_overflow`=GCC5+, `-ftrapv`, o inline asm/intrinseco). C 64-bit → `__adddi3`/`__cmpdi2`. |
| `seed_mixer` | **NO con C -O2** | Codegen low-opt (`-O0`: store/reload byte su stack). Byte-exact solo ricostruendo il codegen (`.s`, non C). |
| `calculateImmoSeed` | **NO con C -O2** | Stesso stile low-opt (276 B), byte-field via stack, `mulu.w`+`sts macl`, pool interleaved. |

---

## 5. Fingerprinting del compilatore (evidenza dalla ROM)

`scripts/fingerprint.py` su tutte le **2789 funzioni** di `src/60E1D400_annotated.s`.

### 5.1 Prologo

| Prima istruzione | n | % |
|---|---|---|
| `mov.l r14,@-r15` (push callee-saved) | 912 | 32.7% |
| `sts.l pr,@-r15` (salva PR) | 521 | 18.7% |
| `mov.w @(pc)` / `mov.l @(pc)` (const da pool) | 490 / 374 | 17.6% / 13.4% |
| `mov reg,reg` | 152 | 5.4% |

Ordine salvataggi: **`mov.l r14` prima di `sts.l pr` = 935 (33.5%)** vs inverso = 33 (1.2%).
Frame pointer quasi assente (`mov r15,r14` in 1 funzione): frame con `add #imm,r15`.
→ Ordine **GCC SH standard** (callee-saved prima, PR ultimo), non Renesas puro
(`sts.l pr`-first = 1.2%).

### 5.2 Epilogo

| Delay slot di `rts` | n | % |
|---|---|---|
| `mov.l` (restore/return) | 989 | 43.1% |
| `nop` | 611 | 26.6% |
| `mov.b` / `mov` / `mov.w` | 220/133/86 | 9.6/5.8/3.7% |
| `fmov.s` | 205 | 8.9% |

→ Delay slot riempito nel **~73% dei `rts`** (`rts; mov.l @r15+,r14`), tratto GCC/SHC
scheduling (-O1/-O2).

### 5.3 Istruzioni distintive

- `mul.l` 3593 · `mac.l` 262 · `mulu.w` 63 · `muls.w` 15 → moltipliche SH standard.
- `div0s`/`div1` 370; `div32_signed` (0x3FE8) = loop **srotolato** a 32 passi
  (`div1`+`rotcl`) libreria Renesas/Hitachi; 0x493C tabella header `0x0013/0xFFFF` +
  coppie `0x0000/0x0001`.
- `addv` 14 / `subv` 6 → **non** GCC standard (pochi helper, es. `addS32Saturate@0x2304`).
- FPU SH-2E pesante (`fmov.s` 10263, `fcmp/gt` 1576) → SH7055 con FPU.
- Stringhe: `Copyright 1999 Hitachi,Ltd.Hitachi Vehicle Operating System for SH-2`
  (0x3B28), `Copr.DENSO2000SSW-N3J1EM000.HEX` (0x6CE33) → RTOS Hitachi (HiVeOS) + Denso (~2000).

### 5.4 Regioni a ottimizzazione mista

Funzioni immo (0x366xx–0x369xx) a **bassa ottimizzazione**; helper 0x2304/0x2460/0x2478
codegen -O2 stringente. Il 1.2% prologhi `sts.l pr`-first = codice vendor compilato a parte.

---

## 6. Ipotesi compilatore (motivata)

> **ROM prodotta con toolchain SuperH GCC-derivato Renesas/Hitachi (SHC, basato su
> GCC 3.x), target SH-2E (SH7055), big-endian, -O1/-O2 con delay-slot attivo e frame
> pointer omesso, librerie di divisione Renesas/Hitachi, alcuni pezzi in asm
> (addv, seed-mixer).**

Evidenza: ordine prologo registri→PR (935 vs 33) ed epilogo con restore in delay;
convenzioni r4..r7/r0 + `extu.w/b`; scelta literal (`mov #imm`/`mov.w`/`mov.l` da pool);
pool PC-relative interleaved; div srotolata + tabella `0x0013/0xFFFF`; era 2000–2003 +
RTOS Hitachi → SHC (gcc-derivato) o `gcc 2.95.x/3.x` (`sh-elf-gcc -m2e`). Separazione
SHC-puro vs GCC puro nominale (SHC = GCC-3.x modificato).

---

## 7. Valutazione onesta della fattibilità

**Verdetto: parzialmente promettente, con vincoli severi.**

1. **Funzioni pure-math piccole (-O2): realistico.** Le due saturating-add hanno
   codegen "da manuale" e il modello predetto coincide 100%. Con un `sh-elf-gcc` vero
   basterebbe provare versioni (2.95.x, 3.4.x, 4.x) e flag (`-m2e -O2
   [−fomit-frame-pointer] [−m4-nofpu]`). Stesso per gli altri helper piccoli.
2. **Idiomi speciali: NO con C puro.** `addS32Saturate` richiede `addv` (asm/builtin);
   la divisione richiede la libreria Renesas. Serve transcodifica manuale o replica libreria.
3. **Regioni low-opt/complesse (immo, scheduler, OBD): irrealistico a livello byte.** Servono
   il C sorgente esatto, lo stesso compilatore+versione e lo stesso livello di ottimizzazione.
4. **Cosa servirebbe per proseguire:** un GCC `sh-elf`/`sh2e` (build da sorgente
   `gcc 3.4.x`/`4.x`, `--target=sh-elf --with-cpu=sh2e`, big-endian; ~30–60 min), o lo
   SHC Renesas, o un prebuilt verificato; un harness di **version/flag sweeping**
   automatico (riusando `scripts/compare.py` come oracolo); confronto a parità di
   *offset relativo* (indirizzi normalizzati tramite linker script).
5. **Raccomandazione:** mantenere **assembly-first** (`src/*.s` + `rom_rebuild`) come percorso
   principale (già byte-exact). Match-and-compile solo come *generatore di bozze* per
   funzioni piccole pure-math, con verifica byte-exact automatica.

## 8. File creati (solo in `reconstructed/experiments/match/`)

```
reconstructed/experiments/match/
├── REPORT.md                        (questo)
├── rom_hex/                         byte esatti ROM delle 5 funzioni
│   ├── add16bitSaturate_2460.txt
│   ├── addSaturate8Bit_2478.txt
│   ├── addS32Saturate_2304.txt
│   ├── seed_mixer_366B8.txt
│   └── calculateImmoSeed_3675C.txt
├── c_src/                           C idiomatico (saturating-add verificate;
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
    ├── extract_rom.py                estrae i byte ROM (read-only)
    ├── compare.py                    assemble .s → confronto byte-exact ROM
    └── fingerprint.py                statistiche prologo/epilogo/istruzioni
```

## 9. Riproducibilità

```bash
python3 scripts/extract_rom.py      # (ri)genera rom_hex/*.txt
python3 scripts/compare.py          # assemble + confronta (sh-elf binutils da
                                    #  tools/toolchain o toolchain.bak o PATH)
python3 scripts/fingerprint.py      # statistiche compilatore su src/*.s
```

Nulla fuori da `reconstructed/experiments/match/` creato/modificato.

---

## 10. SWEEP con GCC 3.4.6 (era ROM)

Data: 2026-08-01 · `gcc 3.4.6 sh-elf` (`/home/davide/gcc346-build/gcc/xgcc`), l'era della
ROM (2000–2003, fingerprint §5).

| Componente | Dettaglio |
|---|---|
| Compilatore | `xgcc -B …/gcc/`, 3.4.6, target `sh-elf`, default big-endian (`-mb`), subtarget `-m2e`/`-m3`/`-m4-nofpu` |
| as / objcopy | `/usr/bin/sh-elf-as -isa=sh2e` / `sh-elf-objcopy -O binary --only-section=.text` |
| stdint | stub `/tmp/stubinc/stdint.h` (`-nostdinc -I/tmp/stubinc`) |
| Harness | `scripts/sweep_gcc346.py` (da `sweep_gcc14.py`; parse hex robusto per `rom_hex/*.txt`) |

Matrice: funzione × subtarget × `-O`(-O0/-O1/-O2/-Os) × opzioni (default/
`-fno-delayed-branch`/`-fomit-frame-pointer`/`-fno-omit-frame-pointer`) = **192 combinazioni/funzione**.
Report: `/tmp/sweep_gcc346/report_full.txt`.

| Funzione | Migliore config | Bytes | % | Insn | Prima div. | Esito |
|---|---|---|---|---|---|---|
| `add16bitSaturate` (C idiomatico) | `-m2e -O1 -fomit-frame-pointer` | 15/24 | 62.5% | 6/12 | +0x06 | diff |
| `addSaturate8Bit` (C idiomatico) | `-m2e -O1 -fomit-frame-pointer` | 9/24 | 37.5% | 4/12 | +0x06 | diff |
| `addS32Saturate` (C a 64-bit) | `-m2e -O1 -fomit-frame-pointer` | 2/22 | 9.1% | 0/11 | +0x00 | diff |
| `seed_mixer` (C low-opt) | `-m2e -O0` | 5/164 | 3.0% | 0/82 | +0x00 | diff |
| **`add16bitSaturate_reg`** (variante) | **`-m2e -O1 -fomit-frame-pointer`** | **24/24** | **100%** | **12/12** | — | ✅ **MATCH byte-perfect** |
| `addSaturate8Bit_reg` (variante) | `-m2e -O1 -fomit-frame-pointer` | 16/24 | 66.7% | 6/12 | +0x01 | diff |
| `addS32Saturate_addv` (inline asm `addv`) | — | 0/22 | 0% | 0/11 | +0x00 | diff |

### ✅ MATCH byte-perfect: `add16bitSaturate` @0x2460

```bash
/home/davide/gcc346-build/gcc/xgcc -B /home/davide/gcc346-build/gcc/ \
  -nostdinc -I /tmp/stubinc -c c_src/add16bitSaturate_reg.c \
  -m2e -O1 -fomit-frame-pointer
# poi: sh-elf-as -isa=sh2e + sh-elf-objcopy --only-section=.text
```

Produce esattamente i 24 byte: `644d 655d 345c d503 3452 8f01 0009 6453 000b 6043 0000ffff`
(dissasembly identico, pool incluso; `.s` in `expected_gcc_sh2e/add16bitSaturate_reg.m2e.-O1.omitfp.s`).

Il sorgente vincente (`c_src/add16bitSaturate_reg.c`) differisce dall'idiomatico in 3
accorgimenti motivati dal codegen ROM:
1. **`max` come variabile** (`register unsigned max`) — evita la fold `sum>=0xFFFF → sum>0xFFFE`
   (ROM: un solo literal 0xFFFF + `cmp/hs`);
2. **registri ancorati r4/r5** (`register …__asm__("r4"/"r5")`) — riproduce l'allocazione ROM
   (somma r4, costante r5, clamp `mov r5,r4`);
3. **return `unsigned`** — epilogo `rts; mov r4,r0` senza `extu.w r4,r0`.

Senza il punto 2 (solo 1+3) si arriva comunque al 62.5% con la stessa struttura di ramo
(`bf.s`+`cmp/hs`+`mov`), ma la somma finisce in r0/r1.

### Confronto divergenze: GCC 3.4.6 vs GCC 14.2.0

1. **add16bitSaturate**: stessa divergenza strutturale di gcc14 (fold `>=0xFFFF→>0xFFFE`),
   ma 3.4.6 è più vicino: `bf.s` con delay riempito, no frame pointer, primi 6 byte a `-O1
   -fomit-frame-pointer`. **gcc14 → 25%, gcc 3.4.6 → 62.5%; `_reg` → 100%.**
2. **addSaturate8Bit**: 3.4.6 usa `extu.b` (param `uint8_t`) mentre ROM fa `extu.w` + `cmp/ge`
   signed su 16 bit → originali erano `uint16_t`. Con `_reg` 66.7%, resta ordine+regalloc del
   `mov` e delay-slot.
3. **addS32Saturate**: 3.4.6 non emette `addv` per C puro; con inline asm materializza T
   (`movt`+`tst`)+`subc/sub`, ROM ramifica su T (`bf/s`)+`mov #0,r5; addc r5,r0` → 0%.
4. **seed_mixer**: low-opt come ROM ma prologo/allocazione/ordine diversi → **3.0%** (gcc14 3.7%).

### Verdict

- **`add16bitSaturate` MATCHA** con 3.4.6 `-m2e -O1 -fomit-frame-pointer` (+ max-variabile,
  pin r4/r5): prima prova con un compilatore reale d'epoca — l'ipotesi "GCC 3.x Renesas-derivato"
  (§6) è ora supportata da match empirico.
- **Generalizzabilità:** alta per helper piccoli pure-math **se** tipi originali (`uint16_t`),
  confronto contro **variabile** (evita fold), registri r4..r7. L'8-bit è a una copia-`extu.w` di
  distanza. **Non generalizza** a idiomi speciali (`addv`) o low-opt complesso (immo).
- 0 match per `addS32Saturate`, `seed_mixer`: resta l'approccio assembly-first.

### Riprodurre

```bash
python3 scripts/sweep_gcc346.py --out /tmp/sweep_gcc346/report_full.txt
# 7 funzioni × 48 config; ~2 s
```

Nuovi file: `scripts/sweep_gcc346.py`, `c_src/add16bitSaturate_reg.c`,
`c_src/addSaturate8Bit_reg.c`, `c_src/addS32Saturate_addv.c`,
`expected_gcc_sh2e/add16bitSaturate_reg.m2e.-O1.omitfp.s`. `sweep_gcc14.py` intatto.

---

## 11. SWEEP ESTESO: 11 candidati pure-math con GCC 3.4.6

Data: 2026-08-01 · harness `scripts/sweep_puremath_gcc346.py`, pipeline gcc 3.4.6 →
`sh-elf-as` → `objcopy` → confronto byte.

**Selezione:** marker `! --- <name> 0x..-0x..` in `src/60E1D400_annotated.s` (confini
autorevoli; i range del CSV non allineano) → **28 candidati** pure-math leaf (≤90 B, nessuna
call/FPU/deref, solo r0–r7+pc, ≥1 istruz. ALU), di cui 11 qui. Il filtro `rts`-leaf stretto
trovava solo 7 candidati banalmente costanti.

| Funzione | ROM | Migliore config | Bytes | % | Insn | Prima div. | Causa |
|---|---|---|---|---|---|---|---|
| `alignment_boundary_validator` | 0xD90C | `-O1 -fomit-frame-pointer` | 21/38 | 55.3% | 9/19 | +0x00 | registri/ordine; ramo ok (bf.s) |
| `atu_get_rx_byte_count` | 0x1FA2 | `-O1 -fomit-frame-pointer` | 11/20 | 55.0% | 5/10 | +0x06 | `bt`/`bra`+delay vs `bf.s`; const r1 vs r4 |
| `can_get_mailbox_offset_high` | 0xD164 | `-O2 -fomit-frame-pointer` | 11/22 | 50.0% | 5/11 | +0x06 | idem atu |
| `getHCANRegisterAddress` | 0xD198 | `-O2 -fomit-frame-pointer` | 9/20 | 45.0% | 4/10 | +0x04 | `bt.s` vs `bf.s`; `mov r5,r2` extra |
| `charging_status` | 0x59C24 | `-O2 -fomit-frame-pointer` | 6/18 | 33.3% | 2/8 | +0x04 | `movt` (booleano) vs ramo 1/0 |
| `calc_manifold_pressure_error_diff` | 0x10A88 | `-O2 -fomit-frame-pointer` | 7/22 | 31.8% | 1/11 | +0x01 | primo literal `mov.l` r2 vs r6 |
| `complement_shift_u16` | 0x2430 | `-O1 -fomit-frame-pointer` | 4/16 | 25.0% | 1/8 | +0x00 | gcc ritorna r0, ROM calcola r4 |
| `obd_service_handler` | 0x67154 | `-O2 -fomit-frame-pointer` | 3/18 | 16.7% | 0/8 | +0x01 | `and #31` vs `tst #31`+`movt` |
| `pulse_window_compute` | 0xFCD2 | `-O2 -fomit-frame-pointer` | 3/20 | 15.0% | 0/10 | +0x00 | add cond.: registro/ordine |
| `encode` | 0x2420 | `-O1 -fomit-frame-pointer` | 2/16 | 12.5% | 0/7 | +0x00 | come complement_shift (8-bit) |
| `shift_right_8_r0` | 0x467A | `-O0 -fomit-frame-pointer` | 1/18 | 5.6% | 0/9 | +0x00 | gcc loop/`shar`; ROM 8×`shar` srotolato |

**Esito: 0 match byte-perfect su 11** (best 55.3%). Match unico resta `add16bitSaturate_reg`.

### Pattern di divergenza ricorrenti

1. **Polarità ramo:** selettori (`atu`/`mbox`/`getHCAN`) ROM `bt`/`bt.s`+`bra` con
   `mov r5,r4` nel delay del `bra`, gcc 3.4.6 `bf.s` con `mov r5,r4` nel delay e la costante
   0x0200 in r1 (`mov.w @(pc),r1`+`mov r5,r4`+`add r1,r4`) invece che direttamente in r4.
   Prima divergenza sistematica a +0x06.
2. **Registro di ritorno:** complement-shift accumula in r4, `rts; mov r4,r0`; gcc materializza
   in r0 (`mov r3,r0`+`rts; add r2,r0`). Pinning `__asm__("r4")` non basta (gcc folda l'add).
3. **Booleani:** ROM `mov #0,r4`/`mov #1,r4` tramite rami; gcc `movt` (`tst`+`movt` o `and #31,r0`).
   Non aggirabile con C puro a -O1/-O2.
4. **Fold del range** (`>=32 → >31`): aggirabile con costante come **variabile** `register
   unsigned c __asm__("r3")=32`; atu 20%→55%, mbox 36%→50%.

### Verdict

La recipe di §10 (variabile-const + pin r4/r5 + return unsigned) è **necessaria ma non
sufficiente**: si spalma su saturating-add, ma i selettori `?:` e i booleani divergono per
polarità e `movt` (nessun flag 3.4.6 li cambia). Conferma che la ROM è GCC-3.x ma non sempre
*questo* 3.4.6: variazioni release/flag 3.0.x–3.4.x plausibili.

---

## 12. SWEEP FLAG D'EPOCA 3.4.6 (sessione flag, 2026-08-01)

Harness `scripts/sweep_flags_epoch346.py` (stesso pipeline). Complementa
`sweep_puremath_gcc346.py` (solo -O×4+extra); `sweep_flagmatrix_gcc346.py` ha un bug
(`exp` non definito) non eseguibile. Report: `/tmp/flagepoch/report*.txt`.

### 12.1 Inventario flag SH di GCC 3.4.6 (`sh.h` TARGET_SWITCHES)

`--help=target` non esiste in 3.4.6; elenco in `gcc-3.4.6/gcc/config/sh/sh.h` righe 286–335.

| Famiglia | Opzioni esistenti | Note |
|---|---|---|
| CPU | `-m1 -m2 -m2e -m3 -m3e -m4-single-only -m4-single -m4-nofpu -m4 -m5-*` | `-m1`⇒`BRANCH_COST=2`, `-m2/-m2e`⇒`1` (`sh.h:2757`) |
| Endian | `-mb -ml` | default big-endian |
| Calling conv | `-mhitachi`/`-mrenesas`, `-mnomacsave`, `-musermode` | |
| Codegen | `-mbigtable -mdalign -mfmovd -mieee/-mno-ieee -misize -mpadstruct -mprefergot -mrelax -mspace` | `-misize`/`-mspace`≈`-Os` |
| **NON esistenti** | `-mbranch-cost`, `-mnomovt`, `-madjust-unroll`, `-maccumulate-outgoing-args`, `-mpretend-cmove` | sono **GCC 4.x**; branch cost = macro `BRANCH_COST`, `movt` si spegne solo con `-fno-if-conversion{,2}` |

`movt` emesso da if-conversion (`sh.md` righe 3421–3731; `mov #-1/negc/neg` riga 7915). `tst #imm`
(0xC8) **non ha pattern** in `sh.md` 3.4.6 (solo `tst rn,rm`). Scelta `mov.l @(pc)` vs `mov.w @(pc)`
per SImode è **incondizionata** (`broken_move()`/`hi_const()`, `sh.c:2860,4150`): ogni costante in
[-32768,32767] restretta a load HImode. Nessuno dei tre controllabile con flag 3.4.6.

### 12.2 Risultati matrice (flag×candidato, best per sorgente)

Matrice: 15 sorgenti × 20 config in `/tmp/flagepoch/report.txt` + `report2.txt`.

| Sorgente (ROM) | Migliore config | % | Prima div. | Causa residua |
|---|---|---|---|---|
| `add16bitSaturate_reg` (0x2460) | `-m2e -O1 -fomit-frame-pointer` | **100%** | — | ✅ MATCH (§10) |
| `complement_shift_u16_2430_match` (0x2430) | `-m2e -O1 -fomit-frame-pointer` | **100%** | — | ✅ **NUOVO MATCH** (16/16, tutte le config tranne nodel/m4) |
| `encode_2420_match` (0x2420) | `-m2e -O1 -fomit-frame-pointer` | **100%** | — | ✅ **NUOVO MATCH** (16/16) |
| `pulse_window_compute_FCD2_r4` (0xFCD2) | `-m2e -O1 -fomit-frame-pointer` | **90.0%** | +0x0C | `mov.l @(pc),r3` ROM vs `mov.w` gcc (`hi_const`) |
| `shift_right_8_r0_467A_loop` (0x467A) | `-m2e -O2 -funroll-all-loops` | 66.7% | +0x00 | body 8×`shar r0`+`rts;shar` identico, ma `mov r4,r0` ABI in testa |
| `obd_service_handler_67154_m1` (0x67154) | `-m1 -O1 -fno-if-conversion{,2}` | 66.7% | +0x01 | `tst #31` non emesso; `mov r4,r0` vs `extu.b` |
| `atu_get_rx_byte_count_1FA2` (0x1FA2) | `-m1 -O1 -fomit-frame-pointer` | 60.0% | +0x06 | polarità ramo |
| `can_get_mailbox_offset_high_D164` (0xD164) | `-O2/-Os -fomit-frame-pointer` | 50.0% | +0x06 | idem atu |
| `getHCANRegisterAddress_D198` (0xD198) | `-O2 -fomit-frame-pointer` | 45.0% | +0x04 | idem atu (+ `bt.s`) |
| `charging_status_59C24_branch` (0x59C24) | `-O1 -fno-if-conversion{,2} -fno-delayed-branch` | 50.0% | +0x05 | `bf`+`bra`-in-delay vs `bf.s`+`nop` |
| `calc_manifold_pressure_error_diff_10A88` (0x10A88) | `-O1 -fno-delayed-branch` | 40.9% | +0x01 | reg alloc + `mov.l` vs `mov.w` |
| `alignment_boundary_validator_D90C` (0xD90C) | `-O1 -fomit-frame-pointer` | 55.3% | +0x00 | accumulatore r0 vs r6 + layout |
| `alignment_boundary_validator_D90C_r6` (0xD90C) | `-O1 -fomit-frame-pointer` | 36.8% | +0x02 | epilogo `mov #1,r6;rts;mov r6,r0` matcha, layout rami diverge |

### 12.3 Cosa hanno mosso i flag

- **`-fno-if-conversion{,2}`** → uccide `movt`/`negc`: `obd_branch` 16.7%→33.3% (m2e) e →**66.7%** con `-m1`.
- **`-m1`** (BRANCH_COST=2): atu 55→60%, obd_branch →66.7%, ma inverte il delay-slot (`bf` vs `bf.s`);
  per i selettori è la migliore, per mbox/charging peggiora.
- **`-funroll-all-loops`/`-funroll-loops`**: `for(i=0;i<8;i++) v>>=1` srotolato nelle 8× `shar r0`
  esatte (66.7%; prima 5.6%).
- **`-fno-delayed-branch`**: calc 31.8→40.9%, charging 44.4→50%; rovina i `_match` (75%).
- `-mrelax/-misize/-mspace/-mrenesas/-m3/-m4-nofpu`: nessun effetto sulle quattro divergenze.

### 12.4 Riscritture C "speculari"

1. **Accumulatore costante** (`k=0x0200; k+=b;`): gcc carica la costante **direttamente in r4**
   (`mov.w @(pc),r4`) invece di r1+`mov r5,r4` (fixa la divergenza di registro).
2. **Condizione invertita** (`if(d<=0) d+=c;` per pulse): `bt.s` **stessa polarità ROM**
   (9/10 istruzioni, 90%). Per i selettori gcc normalizza sempre `bf.s`+fall-through: struttura
   `bt`+`bra`+delay non riproducibile né con flag né invertendo il C.
3. **Pinning r6 + maschera in r7** (alignment_r6): epilogo `mov #1,r6/rts/mov r6,r0` byte-identico,
   `tst r7,rn` registri; resto layout blocchi diverge.
4. **Barrier asm vuote** (`__asm__(""::"r"(x))`) per fissare il registro finale: funzionano
   (pulse r4, calc) ma non cambiano la polarità.

### 12.5 Verdict per divergenza

| # | Divergenza | Flag 3.4.6? | C riscritto? | Verdetto |
|---|---|---|---|---|
| 1 | Polarità ramo (`bf/bt`+`bra`) | ❌ nessun flag | ⚠️ alcuni (pulse ✓); selettori normalizza sempre | **parzialmente via C**, non via flag |
| 2 | Return (r4 vs r0) | ❌ | ✅ pin `__asm__`+barrier | **via C** (recipe `_match`) |
| 3 | Booleani `movt` vs ramo | ✅ `-fno-if-conversion{,2}` (obd→66.7%) | ✅ `if/else`+pin r4 | **via flag**; residuo `tst #imm` |
| 4 | Loop shift vs srotolamento | ✅ `-funroll-*-loops` (8×`shar`) | ✅ loop esplicito | **via flag+C**; residuo `mov r4,r0` ABI |

### 12.6 Nuovi MATCH e stato finale

**3 MATCH byte-perfect con GCC 3.4.6**, tutti `-m2e -O1 -fomit-frame-pointer`:

| Funzione | ROM | Byte | Recipe |
|---|---|---|---|
| `add16bitSaturate` | 0x2460 | 24/24 | `add16bitSaturate_reg.c` (§10) |
| `complement_shift_u16` | 0x2430 | 16/16 | `complement_shift_u16_2430_match.c` (extu.w asm + pin r3/r2/r4 + barrier) |
| `encode` | 0x2420 | 16/16 | `encode_2420_match.c` (stessa ricetta, extu.b naturale) |

I `_match` sono robusti: 16/16 su quasi tutte le 20 config; degradano a 75% solo con
`-fno-delayed-branch` e (complement_shift) `-m4-nofpu`.

File `.s` vincenti in `expected_gcc_sh2e/`: `add16bitSaturate_reg.m2e.-O1.omitfp.s`,
`complement_shift_u16_2430_match.m2e.-O1.omitfp.s`, `encode_2420_match.m2e.-O1.omitfp.s`
(reference: `pulse_window_compute_FCD2_r4…`, `shift_right_8_r0_467A_loop.m2e.-O2.omitfp.unrollall.s`,
`obd_service_handler_67154_m1.m1.-O1.omitfp.noifconv.s`).

Nuovi file: `scripts/sweep_flags_epoch346.py`, `c_src/{atu_…spec,can_…spec,getHCAN…spec,
pulse_window_compute_FCD2_r4,shift_right_8_r0_467A_loop,obd_service_handler_67154_m1,
alignment_boundary_validator_D90C_r6}.c`. `sweep_flagmatrix_gcc346.py` NON corretto (bug preesistente).

---

## 13. SWEEP GCC 3.3.6 (release minore precedente)

Data: 2026-08-02 · harness `scripts/sweep_gcc336.py` (29 sorgenti × 17 flagset = 493; ~2.3 s).
Toolchain `/home/davide/gcc336-build/gcc/xgcc` (GCC 3.3.6, `sh-elf`, big-endian). Pipeline identica.

### 13.1 Toolchain: differenze vs 3.4.6

| Aspetto | GCC 3.3.6 | GCC 3.4.6 |
|---|---|---|
| ISA | **`-m2`** (SH-2 no single-FPU) | `-m2e` |
| `-m2e` | ❌ non esiste | ✅ |
| `-m1 -m3 -m3e -m4-nofpu -m4-single*` | ✅ | ✅ |
| `-mrenesas/-mhitachi/-mrelax/-mspace/-misize/-mnomacsave` | ❌ unrecognized | ✅ |
| `-fno-if-conversion{,2}`, `-funroll-all-loops`, `-fno-delayed-branch` | ✅ | ✅ |
| Prologo SH-2 (`int f(a,b){return a+b;}`) | ✅ `mov r4,r0; rts; add r5,r0` | ✅ idem |

### 13.2 Risultato per funzione (best; 3.3.6 base `-m2`)

| Sorgente (ROM) | 3.4.6 | 3.3.6 | Config 3.3.6 | % | Prima div. | Δ |
|---|---|---|---|---|---|---|
| `add16bitSaturate_reg` (0x2460) | **100%** | 19/24 | `-O2/-Os -fomit-frame-pointer` | 79.2% | +0x00 | **▼ regredisce** |
| `complement_shift_u16_2430_match` (0x2430) | **100%** | 6/16 | `-O2 -fomit-frame-pointer` | 37.5% | +0x00 | **▼ regredisce** |
| `encode_2420_match` (0x2420) | **100%** | 4/16 | `-O1 -fno-if-conversion{,2} -fno-delayed-branch` | 25.0% | +0x00 | **▼ regredisce** |
| `pulse_window_compute_FCD2_r4` (0xFCD2) | 90.0% | 10/20 | `-O2/-Os -fomit-frame-pointer` | 50.0% | +0x08 | ▼ |
| `shift_right_8_r0_467A_loop` (0x467A) | 66.7% | 12/18 | `-O2 -funroll-all-loops` | 66.7% | +0x00 | = |
| `obd_service_handler_67154_m1` (0x67154) | 66.7% | 12/18 | `-m1 -O1 -fno-if-conversion{,2}` | 66.7% | +0x01 | = |
| `atu_get_rx_byte_count_1FA2_spec` (0x1FA2) | (non testato) | **19/20** | `-m1 -O1 -fno-if-conversion{,2}` | **95.0%** | +0x0D | ★ 13.4 |
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

| # | Divergenza | Esito 3.3.6 | Verdetto |
|---|---|---|---|
| 1 | Polarità ramo (`bt` vs `bf.s`) | NON eliminata; `atu_spec` con `-m1 -fno-if-conversion{,2}` produce `bt`+`bra` identici (95%) — ma 3.4.6 con lo stesso flagset emette byte identici (13.4). | **parzialmente via flagset, non vantaggio 3.3.6** |
| 2 | `movt` vs ramo | A -O1 `movt r1`+`movt r0` (peggio); `-fno-if-conversion{,2}` uccide `movt` in entrambe. | **non eliminata; stessa cura 3.4.6** |
| 3 | `tst #imm` (0xC8) | Pattern `tst %1,%0` constraint `L` ESISTE (`sh.md` ~623) ma il combiner non folda `and #31`→`tst #31`: sempre `and #31,r0; tst r0,r0` (`c91f 2008`). ROM `tst #31,r0` (`c81f`). | **NON eliminata — strutturale** |
| 4 | Return (r4 vs r0) | 3.3.6 **peggiora**: widen automatica param (`extu.w r4,r4`), i `_match` producono estensione **doppia**, sum in r3 (`rts; mov r3,r0`). Recipe 3.4.6 non si trasferisce. | **NON eliminata — 3.3.6 peggiore** |
| 5 | Loop shift | `-funroll-*-loops` srotola 8×`shar` in entrambe (66.7%; residuo `mov r4,r0` ABI). | **eliminata in entrambe** |

### 13.4 Nuova scoperta condivisa: `atu_get_rx_byte_count` @0x1FA2 → 95%

Con `-m1 -O1 -fomit-frame-pointer -fno-if-conversion -fno-if-conversion2` su
`atu_get_rx_byte_count_1FA2_spec.c`, GCC 3.3.6 produce:

```
GOT: 644c e320 3433 8901 a002 6453 9402 345c 000b 6043 0200
ROM: 644c e320 3433 8901 a002 6453 9403 345c 000b 6043      (pool@0x1FB8)
```

19/20 (95%), unico diff +0x0D: displacement di `mov.w @(pc),r4` (pool gcc 0x1FB6, ROM 0x1FB8 —
interleaved dopo il prologo `mov #32,r4` della funzione successiva). Body altrimenti byte-identico.
**Verifica incrociata:** 3.4.6 con lo stesso flagset/sorgente produce byte identici
(`644ce32034338901a00264539402345c000b60430200`). Il report flagepoch §12 non aveva mai testato
`atu_spec`+quel flagset → scoperta **nuova ma NON esclusiva di 3.3.6** (recipe flagset valida per entrambe).
`.s` salvato: `expected_gcc_sh2e/atu_get_rx_byte_count_1FA2_spec.m2.m1.O1.omitfp.noifconv.s`.

### 13.5 Perché i 3 MATCH 3.4.6 regrediscono (root cause)

I `_match` assumono 3.4.6: `(unsigned)av` per `uint16_t` = `mov r4,r3` (no `extu.w`, param HImode
già zero-esteso) e l'inline-asm `extu.w r4,r3` aggiunge la widen mancante. In **3.3.6** la widen è
automatica (`extu.w r4,r4` in testa) → estensione doppia → sequenza ROM mai raggiunta. Per
`add16bitSaturate_reg` la somma finisce in r1 e `bf.s`+`mov r1,r4` (ROM: somma r4, `bf.s`+`nop`).

### 13.6 Verdict 3.3.6 vs 3.4.6

**3.3.6 NON supera 3.4.6.** Su 29 sorgenti: **0 match byte-perfect** nuovi; i **3 MATCH 3.4.6
regrediscono** (79.2/37.5/25.0%); le 4 divergenze residue restano **strutturali** (la widen
automatica rende 3.3.6 **peggiore** sui match); l'unico miglioramento (atu_spec 95%) è
**condiviso** con 3.4.6 (era un flagset non ancora provato).

**Conclusione:** release più vicina alla ROM resta **GCC 3.4.6** (3 MATCH + 90% pulse). 3.3.6 =
*worse* per questi helper; provare **3.2.3** (sorgente in `/home/davide/gcc-3.2.3`).

### Riprodurre

```bash
python3 scripts/sweep_gcc336.py --out /tmp/sweep_gcc336/report_full.txt
# 29 sorgenti × 17 flagset
```

Nuovi file: `scripts/sweep_gcc336.py`, `expected_gcc_sh2e/atu_get_rx_byte_count_1FA2_spec.m2.m1.O1.omitfp.noifconv.s`.
Sezione `match_recipe.txt` aggiornata.

---

## 14. SWEEP GCC 3.2.3 (release precedente)

Data: 2026-08-02 · harness `scripts/sweep_gcc323.py` (29 sorgenti × 21 flagset = 609; ~2.5 s).
Toolchain `/home/davide/gcc323-build/gcc/xgcc` (GCC 3.2.3, `sh-elf`, big-endian).

### 14.1 Toolchain: differenze

| Aspetto | GCC 3.2.3 | GCC 3.3.6 | GCC 3.4.6 |
|---|---|---|---|
| ISA | **`-m2`** | `-m2` | `-m2e` |
| `-m2e` | ❌ | ❌ | ✅ |
| `-m1 -m3 -m3e -m4-single-only -m4-nofpu` | ✅ | ✅ | ✅ |
| `-mhitachi/-mrelax/-mspace/-misize/-mnomacsave` | ✅ | ❌ droppati | ✅ |
| `-fno-if-conversion{,2}` | ❌ **NON esistono** | ✅ | ✅ |
| `-funroll-all-loops/-funroll-loops/-fno-delayed-branch/-fno-unroll-loops` | ✅ | ✅ | ✅ |
| Prologo SH-2 | ✅ `mov r4,r0; rts; add r5,r0` | ✅ | ✅ |

Punto critico: **3.2.3 NON ha `-fno-if-conversion{,2}`** (`cc1: unrecognized option`). Tutte le
ricette che uccidono `movt` (obd_m1 66.7%, atu_spec 95%) **dipendono da quel flag** → non riproducibili.

### 14.2 Risultato per funzione (best; 3.2.3 base `-m2`)

| Sorgente (ROM) | 3.4.6 | 3.3.6 | 3.2.3 best | Config 3.2.3 | % | Prima div. | Δ vs 3.3.6 |
|---|---|---|---|---|---|---|---|
| `add16bitSaturate_reg` (0x2460) | **100%** | 79.2% | 16/24 | `-O1 -fno-delayed-branch` | 66.7% | +0x0A | ▼ |
| `complement_shift_u16_2430_match` (0x2430) | **100%** | 37.5% | 7/16 | `-O2 -fno-delayed-branch` | 43.8% | +0x00 | ▲ |
| `encode_2420_match` (0x2420) | **100%** | 25.0% | 4/16 | `-O1 -fno-delayed-branch` | 25.0% | +0x00 | = |
| `atu_get_rx_byte_count_1FA2_spec` (0x1FA2) | 95.0% | **95.0%** | 8/20 | `-O1/-O2 -fno-delayed-branch` | **40.0%** | +0x06 | ▼▼ 14.4 |
| `shift_right_8_r0_467A_loop` (0x467A) | 66.7% | 66.7% | **14/18** | `-O1 -fno-delayed-branch -funroll-loops` | **77.8%** | +0x00 | ▲★ 14.5 |
| `pulse_window_compute_FCD2_r4` (0xFCD2) | 90.0% | 50.0% | 10/20 | `-O2/-Os -fomit-frame-pointer` | 50.0% | +0x08 | = |
| `obd_service_handler_67154_m1` (0x67154) | 66.7% | 66.7% | 3/18 | `-O1 -fomit-frame-pointer` | 16.7% | +0x01 | ▼▼ 14.4 |
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

NB: `seed_mixer` e `shift_right_8_r0_467A` con `-m3/-m3e/-m4*` falliscono in assembly
(`shld r7,r1` non SH-2: gcc 3.2.3 emette shift SH-3+ che `sh-elf-as -isa=sh2e` rifiuta). Non è
perdita di sweep; base `-m2` corretta per questi window.

### 14.3 I 3 MATCH 3.4.6 su 3.2.3: regrediscono (stessa root cause 3.3.6)

| Match 3.4.6 | 3.3.6 | 3.2.3 | Causa 3.2.3 |
|---|---|---|---|
| `add16bitSaturate_reg` **100%** | 79.2% | **66.7%** | widen automatica (`extu.w r5,r5;extu.w r4,r4` in testa), somma r4 ma `bf` non-delayed+`nop` (ROM `bf.s`+delay), a O1 fold `>=0xFFFF` |
| `complement_shift_u16_2430_match` **100%** | 37.5% | **43.8%** | widen auto + inline-asm = estensione doppia; sum r3, `mov r3,r4;rts;mov r3,r0` (ROM `add r2,r4;rts;mov r4,r0`) |
| `encode_2420_match` **100%** | 25.0% | **25.0%** | idem (extu.b doppia), `mov r4,r3` non esteso |

Su `complement_shift_match` 3.2.3 è leggermente meglio di 3.3.6 (43.8% vs 37.5%): a `-O2
-fno-delayed-branch` ottiene `mov r3,r4;rts;mov r3,r0` (2 byte diversi dall'epilogo invece di 4).

### 14.4 atu_spec 95% e obd_m1 66.7% NON reggono: manca `-fno-if-conversion`

- `atu_spec` su 3.2.3: best **40.0%** (`-O1 -fno-delayed-branch`) — `movt` non uccidibile, body non
  raggiunge la sequenza `bt+bra+mov r5,r4` (a O1 emette `bf` con `mov r5,r4` nel fall-through).
- `obd_m1` su 3.2.3: best **16.7%** — **doppio `movt`** (`movt r1;tst r1,r1;movt r0`), senza
  `-fno-if-conversion` nessun modo di ramificare come ROM.

**Conclusione:** il 95% atu NON regge su 3.2.3 (40%). Miglioramento atu era scoperta di *flagset*,
non di release.

### 14.5 Divergenze strutturali: cosa cambia su 3.2.3

| # | Divergenza | Esito 3.2.3 | Verdetto |
|---|---|---|---|
| 1 | Polarità ramo | NON eliminata; `add16bit` O1 `bf` non-delayed+`nop` (ROM `bf.s`+delay); selettori `bf.s`+`bra`. | **persiste; senza `-fno-if-conversion` peggiore** |
| 2 | `movt` vs ramo | **doppio `movt`** a `-O1`; nessun flag per ucciderlo. | **NON eliminata — peggiore dei tre** |
| 3 | `tst #imm` (0xC8) | `sh.md` ha il pattern ma il combiner non folda: `and #31,r0;tst r0,r0`. ROM `tst #31,r0`. | **NON eliminata — strutturale** |
| 4 | Return (r4 vs r0) | Widen automatica presente; `_match` producono estensione doppia. `add16bit_reg` 66.7% (vs 79.2% 3.3.6, `bf` non-delayed); `complement_shift_match` 43.8% (`mov r3,r4;rts;mov r3,r0`). | **NON eliminata — come 3.3.6** |
| 5 | Loop shift | `-O1 -fno-delayed-branch -funroll-loops` → **8× `shar r0` esatti + `rts; nop`** = **77.8%** (14/18), residuo `mov r4,r0` ABI+nop. | **★ MIGLIORAMENTO: 77.8% vs 66.7%** (flag-combo) |

*Nota di coerenza (§15.2): il 77.8% è scoperta **flag-combo**, non di release — lo sweep
`-mrelax` ha mostrato la stessa combo raggiungere il 77.8% anche su 3.4.6 (con/senza `-mrelax`);
assente dalla matrice flagepoch 3.4.6 (solo `O2.unrollall`/`O2.unroll` = 66.7%). Su 3.3.6 mai testata.*

### 14.6 Verdict 3.2.3 vs 3.3.6 vs 3.4.6

**3.2.3 NON supera 3.4.6** (0 match su 29) ed è complessivamente **peggiore di 3.3.6**:
- i **3 MATCH 3.4.6 regrediscono** (66.7/43.8/25.0%) — widen automatica;
- il **95% atu NON regge** (40%) e **66.7% obd NON regge** (16.7%) — `-fno-if-conversion{,2}` assente,
  `movt` strutturalmente non aggirabile → 3.2.3 peggiore sui selettori/booleani;
- unico guadagno **`shift_right_8_r0_467A_loop` 77.8%** (`-O1 -fno-delayed-branch -funroll-loops`;
  matrice 3.3.6/3.4.6 a 66.7% — ma stessa flag-combo raggiunge 77.8% anche su 3.4.6, §15.2).
  Scoperta di flag-combo, non di release.

**Conclusione per la pipeline:** release più vicina alla ROM resta **GCC 3.4.6** (3 MATCH + 90% pulse).
Classifica serie 3.x: **3.4.6 > 3.3.6 > 3.2.3**. Widena automatica in 3.2.3/3.3.6 (assente 3.4.6);
`-fno-if-conversion` solo da 3.3.x → codegen ROM più coerente con 3.4.6.

### Riprodurre

```bash
python3 scripts/sweep_gcc323.py --out /tmp/sweep_gcc323/report_full.txt
# 29 sorgenti × 21 flagset
```

Nuovi file: `scripts/sweep_gcc323.py`. Sezione `match_recipe.txt` aggiornata.

---

## 15. VERDETTO FINALE — SERIE GCC 3.x E CHIUSURA

Data: 2026-08-02 · confronto completo serie GCC 3.x + GCC 14.2.0 + test `-mrelax/-mhitachi/-mspace`
su 3.4.6. Numeri da §10–§14; **nessun nuovo dato introdotto**.

### 15.1 Tabella comparativa (best % per funzione e toolchain)

% = byte uguali sulla finestra ROM (body+pool dove contiguo); config = migliore flagset. GCC 14.2.0
copriva solo le 4 funzioni base (§10, `sweep_gcc14.py`).

| Funzione (ROM) | GCC 14.2.0 | GCC 3.4.6 | GCC 3.3.6 | GCC 3.2.3 | Config vincitrice (serie 3.x) |
|---|---|---|---|---|---|
| `add16bitSaturate` @0x2460 (C idiomatico) | 25.0% | 62.5% | 62.5% | 62.5% | `-m2e -O1 -fomit-frame-pointer` (3.4.6) / `-O1/-O2 -fomit-frame-pointer` (3.3.6/3.2.3) |
| **`add16bitSaturate_reg` @0x2460 (recipe)** | — | **100%** ✅ | 79.2% | 66.7% | **`-m2e -O1 -fomit-frame-pointer` + max-var + pin r4/r5 + return unsigned** |
| **`complement_shift_u16` @0x2430 (recipe)** | — | **100%** ✅ | 37.5% | 43.8% | **`-m2e -O1 -fomit-frame-pointer` + `_match.c`** |
| **`encode` @0x2420 (recipe)** | — | **100%** ✅ | 25.0% | 25.0% | **`-m2e -O1 -fomit-frame-pointer` + `_match.c`** |
| `addSaturate8Bit` @0x2478 | 29.2% | 37.5% | 37.5% | 37.5% | `-m2e -O1 -fomit-frame-pointer` |
| `addSaturate8Bit_reg` @0x2478 | — | 66.7% | 37.5% | 37.5% | `-m2e -O1 -fomit-frame-pointer` (3.4.6) |
| `addS32Saturate` @0x2304 | 4.5% | 9.1% | 8.3% | 8.3% | `-m2e -O1 -fomit-frame-pointer` (3.4.6) |
| `addS32Saturate_addv` @0x2304 | — | 0% | 12.5% | 4.2% | (nessuna; `addv` non riproducibile in C) |
| `seed_mixer` @0x366B8 | 3.7% | 3.0% | 2.4% | 2.4% | `-m2e -O0` (3.4.6) |
| `pulse_window_compute` @0xFCD2 | — | **90.0%** | 50.0% | 50.0% | `-m2e -O1 -fomit-frame-pointer` + `_r4.c` |
| `atu_get_rx_byte_count` @0x1FA2 (base) | — | 60.0% | 40.0% | 40.0% | `-m1 -O1 -fomit-frame-pointer` (3.4.6) |
| **`atu_get_rx_byte_count_spec` @0x1FA2** | — | **95.0%** | **95.0%** | 40.0% | **`-m1 -O1 -fomit-frame-pointer -fno-if-conversion{,2}` + `_spec.c`** |
| `shift_right_8_r0` @0x467A (loop) | — | 66.7% *(77.8% flag-combo)* | 66.7% | **77.8%** | `-O1 -fno-delayed-branch -funroll-loops` |
| `obd_service_handler` @0x67154 (`_m1`) | — | 66.7% | 66.7% | 16.7% | `-m1 -O1 -fno-if-conversion{,2}` (manca su 3.2.3) |
| `can_get_mailbox_offset_high` @0xD164 | — | 50.0% | 36.4% | 36.4% | `-m2e -O2 -fomit-frame-pointer` |
| `getHCANRegisterAddress` @0xD198 | — | 45.0% | 30.0% | 30.0% | `-m2e -O2 -fomit-frame-pointer` |
| `charging_status` @0x59C24 (`_branch`) | — | 50.0% | 50.0% | 27.8% | `-O1 -fno-if-conversion{,2} -fno-delayed-branch` (3.4.6/3.3.6) |
| `alignment_boundary_validator` @0xD90C | — | 55.3% | 28.9% | 28.9% | `-O1 -fomit-frame-pointer` (3.4.6) |
| `calc_manifold_pressure_error_diff` @0x10A88 | — | 40.9% | 18.2% | 13.6% | `-O1 -fno-delayed-branch` (3.4.6) |

**Sintesi:** i 3 MATCH esistono **solo con GCC 3.4.6 + recipe**; ogni altra release regredisce
(widen automatica). Le soglie alte non-match (95/90/77.8%) sono **scoperte di flag-combo** valide su
più release (15.2).

### 15.2 Esito test `-mrelax` / `-mhitachi` / `-mspace` su 3.4.6

Harness `scripts/sweep_relax_gcc346.py` (3 candidati residui; ogni config anche con `-relax`
sull'assembler; report `/tmp/sweep_relax/report{,_atu}.txt`).

| Candidato | Base | `-mrelax` | `-mhitachi` | `-mspace` | Esito |
|---|---|---|---|---|---|
| `atu_…_1FA2_spec` | 95.0% | **95.0%** | **95.0%** | **95.0%** | ❌ nessun flag chiude il gap |
| `pulse_window_compute_FCD2_r4` | 90.0% | **90.0%** | **90.0%** | **90.0%** | ❌ nessun flag chiude il gap |
| `shift_right_8_r0_467A_loop` | 66.7% (O2-unrollall) | 66.7% · **77.8% con flagset diverso** | 66.7% | 66.7% | `-mrelax` **irrilevante** |

Perché:
- **atu 95%** (diff +0x0D): displacement `mov.w @(pc),r4` differisce perché pool gcc 0x1FB6 vs ROM
  0x1FB8, **interleaved a livello di sezione** dopo il prologo (`mov #32,r4`) della funzione adiacente.
  `-mrelax/-mhitachi/-mspace` non cambiano il layout del pool (dipende dall'ordinamento globale del file).
- **pulse 90%** (+0x0C): ROM `mov.l @(pc),r3` (`d31d`), gcc `mov.w @(pc),r3` (`9302`) — selezione
  `hi_const` di `sh.c`, **incondizionata** (§12.1).
- **shift**: il 77.8% con `-O1 -fno-delayed-branch -funroll-loops [-mrelax]` è **indipendente da
  `-mrelax`** (stesso 14/18 senza): guadagno della **flag-combo** (srotolamento senza delay-slot).

**Conclusione 15.2:** il gap residuo atu/pulse (95/90%) è **non-closable con flag del singolo file**:
causa = **layout del literal pool a livello di sezione**, non codegen. Chiudere quei byte richiede il
riordino/relink dell'intera sezione (equivalente a ricostruire la ROM), fuori dallo scope.

### 15.3 Verdict: GCC 3.4.6 = golden release

Classifica serie 3.x: **GCC 3.4.6 > GCC 3.3.6 > GCC 3.2.3** (§13.6, §14.6). Motivo tecnico:
1. **Nessuna widen automatica del param sub-word.** 3.4.6 assume HImode/QImode già zero-estesi, non
   emette `extu.w r4,r4` in testa → i 3 match *esprimibili* in C (inline-asm `extu.w r4,r3` senza
   duplicarla). In 3.3.6/3.2.3 widen automatica → estensione doppia → match regrediscono. La ROM
   non mostra estensioni doppie → coerente con 3.4.6.
2. **`movt` uccidibile.** `-fno-if-conversion{,2}` esiste in 3.4.6/3.3.6 (manca 3.2.3) e sostituisce i
   booleani `movt` con rami 1/0 (obd_m1 66.7%, atu_spec 95%). Su 3.2.3 il doppio `movt` non aggirabile.
3. **Prologo coerente col fingerprint ROM.** `mov.l r14,@-r15` prima istruzione, no frame pointer con
   `-fomit-frame-pointer`, delay riempito a `-O1` (§5, §10) — "registri-prima-PR" (935 vs 33). Recipe
   `-m2e -O1 -fomit-frame-pointer` riproduce il prologo esatto.
4. **`-m2e` presente** — subtarget SH-2E corretto per SH7055; manca in 3.3.6/3.2.3 (base `-m2`).

### 15.4 La risposta definitiva

> Con il toolchain disponibile, è realistico riprodurre **byte-identiche** le funzioni della ROM
> compilando C idiomatico con un cross-compilatore SH-2E?

**Risposta definitiva** (4 toolchain reali, >2100 compilazioni: 7×48 §10 + 11×16 §11 + 15×20 §12 +
29×17 §13 + 29×21 §14 + 4×48 sweep GCC 14 + `-mrelax` §15.2):

- **Sì, per helper pure-math piccoli** (leaf, ≤24 B, no call/FPU/deref), **con la recipe**:
  GCC 3.4.6 `-m2e -O1 -fomit-frame-pointer` + max-variabile (evita fold `>=C→>C-1`) + tipi `uint16_t`
  originali + pin `__asm__("r4"/"r5")` + return `unsigned` → **3 match byte-perfect**
  (add16bitSaturate@0x2460, complement_shift_u16@0x2430, encode@0x2420), + 2 quasi-match
  (atu_spec 95%, pulse 90%).
- **No come strategia generale.** Oltre "helper pure-math piccolo, codice 2000-era" non generalizza:
  su 29 sorgenti/4 release le best scendono ampiamente sotto 100% (su 3.3.6/3.2.3 la maggior parte
  ≤50%; su 3.4.6 solo i 3 match + atu_spec >90%). Le divergenze residue (polarità ramo, `tst #imm`,
  layout pool di sezione) sono **strutturali**, non aggirabili né con flag né con C riscritto.
- **Idiomi speciali restano assembly-first.** `addv` (addS32Saturate@0x2304), selettori `bt`+`bra`,
  booleani `tst #imm`, seed-mixer low-opt: nessun C/flag li riproduce → vale `src/*.s` + `rom_rebuild`
  (byte-exact), con match-and-compile come *generatore di bozze* verificato.

**Raccomandazione finale:** mantenere **assembly-first** come percorso principale; match-and-compile solo
come generatore di bozze per helper piccoli, con verifica byte-exact automatica (`compare.py`) e la
recipe di §10/§12.6 come unico "percorso C validato".

### 15.5 Cosa è stato consegnato

1. **Tre toolchain GCC 3.x** (target `sh-elf`, big-endian, build da sorgente fuori repo):
   `/home/davide/gcc346-build/gcc/xgcc` (3.4.6, golden), `gcc336-build` (3.3.6), `gcc323-build` (3.2.3).
   Sorgenti in `/home/davide/gcc-{3.4.6,3.3.6,3.2.3}`; stub `stdint.h` in `/tmp/stubinc/`.
2. **Harness sweep riusabili** (in `scripts/`, pipeline gcc→as→objcopy→confronto byte):
   `sweep_gcc14.py`(§10), `sweep_gcc346.py`(§10), `sweep_puremath_gcc346.py`(§11),
   `sweep_flags_epoch346.py`(§12), `sweep_gcc336.py`(§13), `sweep_gcc323.py`(§14),
   `sweep_relax_gcc346.py`(§15.2); `compare.py` (oracolo), `fingerprint.py` (statistiche ROM).
3. **Recipe esatte** in `match_recipe.txt`: 3 recipe MATCH 3.4.6, atu_spec 95% (3.4.6/3.3.6),
   pulse 90%, shift 77.8% (3.4.6/3.2.3), + tabella best-per-funzione per le 4 release.
4. **Sorgenti C e riferimenti assemblati**: `c_src/*.c` (29: idiomatici, `_reg`, `_match`, `_spec`,
   `_r4`, `_loop`, `_m1`, `_branch`, `_r6`) e i `.s` vincenti in `expected_gcc_sh2e/` per i 3 match
   e i riferimenti (pulse_r4, shift_loop, obd_m1, atu_spec).

Tutto in `reconstructed/experiments/match/`; nessun file fuori modificato. **Filone chiuso.**