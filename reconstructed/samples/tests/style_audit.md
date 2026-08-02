# Style Audit — campioni C (`reconstructed/samples/src`)

Audit statico con compilatore host per individuare warning che potrebbero
nascondere UB o divergenze C-vs-ROM (conversioni implicite, shift oltre
larghezza, confronti/mix firmato-non firmato, aritmetica puntatore host 64-bit).

- Data: 2026-08-02
- Compilatore: `gcc` 16.1.1 20260728 (`/usr/bin/gcc`, `cc` → gcc)
- Comando per file:
  `gcc -Wall -Wextra -Wconversion -Wshadow -fsyntax-only -I reconstructed/samples/include <file>`
- Header: `include/rx8_hw.h` presente e trovato via `-I`; `src/rx8_samples.h`
  risolto dal `#include "..."` relativo alla directory del sorgente. Nessun
  header mancante, nessun errore di compilazione (rc=0 per tutti i 138 file).

## Riepilogo

| Metrica | Valore |
|---|---|
| File totali compilati | 138 |
| File puliti (0 warning) | 128 |
| File con warning | 10 |
| Warning totali | 18 |
| Warning per categoria | `-Wconversion` 8 · `-Wsign-conversion` 7 · `-Wint-to-pointer-cast` 3 |
| `-Wshadow` | 0 |
| `-Wunused-result` | 0 |
| Shift oltre larghezza | 0 |
| File validati Lotto 1 (14, `verify_gcc346.py::FUNCS`) con warning | **0** |

## Tabella warning per file

| File | n | Categorie | Esempi (riga:espressione) |
|---|---|---|---|
| `rx8_alternating_sensor_sm.c` | 1 | `-Wconversion` | 151: `LATCH_D385 = (SRC_D352 >> 8) & 0xFF` → `uint8_t` |
| `rx8_can_table_lookup_583e4.c` | 1 | `-Wsign-conversion` | 202: `accum += (uint32_t)(int32_t)(int8_t)e[2]` |
| `rx8_immo_bad_state_set.c` | 1 | `-Wconversion` | 84: `RX8_IO16(0xFFFFF754) &= ~0x0060u` (costante 0xFFFFFF9F → `uint16_t`) |
| `rx8_immo_state_ready_to_drive_engine_off.c` | 4 | `-Wsign-conversion`, `-Wconversion` | 188/195/196: somma 16-bit con `(int16_t)` e cast finale; 223: `&= ~0x0060u` |
| `rx8_purge_flow_decrement.c` | 1 | `-Wconversion` | 58: `RX8_IO8(...) -= 1u` (promozione a `unsigned int`, troncata a `uint8_t`) |
| `rx8_req_queue_69602.c` | 3 | `-Wint-to-pointer-cast` | 88/89/95: `(volatile uint32_t *)(0xFFFFDE40 + b*4)` |
| `rx8_set_immo_light.c` | 2 | `-Wconversion` | 161/162: `&= ~0x20u` / `&= ~0x40u` (0xFFFFFFDF / 0xFFFFFFBF → `uint16_t`) |
| `rx8_task_full_context_save.c` | 1 | `-Wconversion` | 182: `w32((uintptr_t)tcb + RX_TCB_SAVED_SP, sp)` (`unsigned long` → `uint32_t`) |
| `rx8_vfad_control_35bbc.c` | 2 | `-Wconversion`, `-Wsign-conversion` | 124: `(SRC_D352 >> 8) & 0xFF` → `uint8_t`; 176: `tmp &= ~0x0400u` (−1025 → `uint16_t`) |
| `rx8_vis_intake_control.c` | 2 | `-Wsign-conversion` | 168/174: `values + (uintptr_t)iy * cx` (`int` → `uintptr_t` 64-bit) |

## Top-5 warning più comuni

1. `-Wconversion` — conversione `int`/`unsigned` → tipo più stretto (8) —
   quasi tutte le maschere `&= ~const` su lvalue `uint16_t` (il complemento a
   32 bit viene troncato a 16) e i byte estratti con `& 0xFF`.
2. `-Wsign-conversion` — mix firmato/non firmato (7) — addizioni 16-bit con
   operandi `(int16_t)` + cast di chiusura, sign-extension `(int8_t)→(int32_t)`
   e indici puntatore da `int`.
3. `-Wint-to-pointer-cast` — intero → puntatore di dimensione diversa (3) —
   indirizzi fisici 0xFFFFxxxx (32 bit) castati a puntatore host (64 bit).
4. `-Wshadow` — 0.
5. `-Wunused-result` — 0.

## Rischio — quale warning può indicare divergenza C-vs-ROM

Nessuno dei 14 file del Lotto 1 già validati (`s32_saturate`, `immo_seed_mixer`,
`add16bit_saturate`, `add_saturate_8bit`, `multiply32_saturating`,
`complement_shift_u16/u32`, `index_table`, `div32_signed/unsigned`,
`shift_left_logical/right_arithmetic/right_logical/right_8`) emette warning:
**l'equivalenza già dimostrata non è a rischio**. Tutti i 10 file con warning
sono candidati futuri non ancora validati.

Livelli di rischio:

- **Benigni (semantica corretta per costruzione)**:
  - `immo_bad_state_set`, `set_immo_light`, `vfad_control_35bbc:176`,
    `immo_state_ready_to_drive_engine_off:223` — idioma `&= ~mask` su lvalue
    `uint16_t`: il valore troncato (`0xFF9F`, `0xFFDF`, …) è esattamente la
    maschera voluta; i bit alti del complemento sono irrilevanti.
  - `alternating_sensor_sm:151`, `vfad_control_35bbc:124` — `(x >> 8) & 0xFF`
    è già limitato a [0,255] prima del cast a `uint8_t`.
  - `purge_flow_decrement:58` — il decremento è protetto da `> 0u`, nessun
    underflow.
  - `immo_state_ready_to_drive_engine_off:188/195/196` — i cast `(uint16_t)`
    di chiusura replicano il wrap a 16 bit della ROM; i warning derivano solo
    dalle promozioni intermedie.
- **Sottili ma documentati (da rivalidare quando verranno promossi)**:
  - `can_table_lookup_583e4:202` — sign-extension `mov.b` `(int8_t)e[2]` è
    annotata nel commento (0x58408/0x58414) e il cast `(uint32_t)(int32_t)`
    riproduce l'add a 32 bit della ROM. OK finché l'annotazione è corretta.
- **Divergenza host-vs-ROM possibile (da sistemare prima della validazione)**:
  - `task_full_context_save:182` — `(uintptr_t)tcb` tronca a `uint32_t` un
    puntatore host: l'indirizzo del TCB dipende dall'heap dell'host, non
    dall'indirizzo ROM. Vale solo se `tcb` è garantito sotto 4 GiB (es. mmap a
    indirizzo fisso) o se il modello passa l'indirizzo come `uint32_t`.
  - `vis_intake_control:168/174` — `(uintptr_t)iy` con `iy` firmato: se `iy < 0`
    l'indice diventa enorme su host 64-bit mentre la ROM wrappa a 32 bit.
    Rischio reale solo per indici fuori range; verificare il clamp di
    `axis_search` prima di validare.
  - `req_queue_69602:88/89/95` — pattern atteso del progetto (indirizzi fisici
    mmap-ati come in `rx8_hw.h`); l'aritmetica è a 32 bit e l'equivalenza si
    regge sul valore numerico, non sul puntatore. Nessuna azione urgente.

## Raccomandazioni

1. **Makefile**: il target `%.o` di `reconstructed/samples/Makefile` già usa
   `-Wall -Wextra -Wpedantic`. Aggiungere `-Wconversion -Wshadow` al gate
   **dopo** i fix sotto (oggi genererebbero 18 warning di rumore su 10 file).
   Non necessario per `host_oracle` (compila solo i 3 sorgenti del Lotto 1,
   tutti puliti).
2. **Fix uniformi nei 10 file** (nessuna semantica cambiata):
   - maschere: `(uint16_t)~0x0060u` esplicite (o costanti positive tipo
     `0xFF9Fu`) in `immo_bad_state_set`, `immo_state_ready_to_drive_engine_off`,
     `set_immo_light`, `vfad_control_35bbc`;
   - `req_queue_69602`: `(uintptr_t)(REQ_VALUES + b * 4)` per rendere il
     widening a 64 bit esplicito e intenzionale;
   - `task_full_context_save`: passare `tcb` come `uint32_t` (indirizzo fisico)
     invece di puntatore host, oppure `assert` su `(uintptr_t)tcb < 0x100000000`;
   - `vis_intake_control`: `values + (size_t)(int32_t)iy * (size_t)cx` e
     documentare il clamp di `axis_search`.
3. **Nessun file da escludere**: zero shift oltre larghezza, zero
   unused-result, zero shadow — i warning sono tutti di conversione, in gran
   parte benigni e concentrati su candidati non ancora validati.
