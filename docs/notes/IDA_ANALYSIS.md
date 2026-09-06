# IDA Reverse-Engineering Notes — 60E1D400

Findings from IDA session **9e761f30** on the 512 KB ECU ROM (Denso SH7055, N3J1-18-881L). Disassembly-only: **Hex-Rays is unavailable for SuperH**.

## Decode caveats (verified in session)

- ROM loaded as **SH-3** (`-psh3`) — closest processor to SH-2E that IDA opens. SH-2E/SH-2 fail to open; SH-4 misdecodes (4-byte instructions).
- File must be **word-swapped** (`tmp/ida/60E1D400_bswap.bin`) — the SH module is little-endian-only; code decodes correctly after swap.
- **32-bit literals are word-swapped**: real value = swap of displayed halves (e.g. displayed `0x5AA55A5A` = real `0x5AA5A55A`).
- **16-bit literals display correctly** (no swap).
- FPU opcodes (`0xFxxx`) are undecodable: 121 functions unimportable (IDA module limitation).
- 2669 functions imported from `symbols/symbols_60E1D400_merged.csv`.

# Core system architecture

## Boot sequence

```
Reset vector 0x0 → 0x8B8 Manual_Reset
  → bsc_init (0x8CC)
  → gpio_init (0x8F6)
  → main_init (0x4E0, arg2=0)
```

- `main_init` (0x4E0–0x572): `wdt_init` (0x572) → `hw_init_1` (0x170) → `hw_init_2` (0x41C) → `hw_init_3` (0x3D4) → recovery check `[0xFFFFDFFC]==0x5AA5A55A` → `checkWatchdogTimer_OVRCOUNT` (0x5B0) → optional `gpio_init` path (stores arg byte to `[0xFFFFDFA8]`) → writes `0x5AA5A55A` to `[0xFFFFDFFC]` → `vector_trampoline_set_sp` (0x40) with r13 = jump target (**0x6C8** normal, or `[0x1000]`/`[0x7FFF8]=0xD49C` recovery).
- `vector_trampoline_set_sp` (0x40): SP=0xFFFFDFA0, `jmp @r4`.
- `wdt_init` (0x572): WDT_RSTCSR=0x5A1F, WDT_TCSR=0x5A00, final TCSR write 0x0000.
- `hw_init_1` (0x170): PFC registers 0xFFFFE4xx config; jsr target 0x9C0 (real literal at 0x2BC).
- `checkWatchdogTimer_OVRCOUNT` (0x5B0): watchdog overrun check + task scheduler dispatch + `is_eeprom_valid` (0x624) + `validate_data_block_header` (0x636).

## Main loop: `main_task_dispatcher` (0x6C8–0x796, renamed from `sub_6C8`)

Boot jump target. Clears `[0xFFFFDFB8]`, then loops:

```
task_scheduler_dispatch (0x364)
  → task_queue_pending_count (0x3E0) → if pending:
      task_queue_get_next (0x3B0) → dispatch on task[1] & 0xF8
```

Loop ends with `watchdogTimerRead` (0x31C).

**Dispatch table (task[1] & 0xF8):**

| Key | Handler |
|---|---|
| 0x88 | `serial_rx_handler_ch0` (0x4C) |
| 0x90 | `serial_rx_handler_ch1` (0x64) |
| 0x98 | `serial_data_write_handler` (0x7C0) |
| 0xA0 | `exception_context_restore` (0x7C) |
| 0xA8 | `diag_transfer_806` (0x806) |
| 0xB0 | `serial_data_read_handler` (0x8A) |
| 0xC0 | `serial_rx_handler_ch2` (0xC0) |
| 0xC8 (task[0]==0xFF) | `fatal_error_infinite_loop` (0xD8) |

## Task queue (ring buffer)

- 100 entries × 8 bytes at 0xFFFFD4E0 (RAM).
- Write index `[0xFFFFDFB4]`, read index `[0xFFFFDFB6]`.
- `task_queue_pending_count` (0x3E0): (write − read) mod 100.
- `task_queue_get_next` (0x3B0): read index ×8 + base, increment mod 100.

## Serial message dispatch

- `serial_dispatch` (0x338): if `[0xFFFFDFA8]==0` → direct `loc_256` (0x256); else → `serial_queue_message` (0x47C).
- `loc_256` (0x256): copy r5 bytes r6→`[0xFFFFDFAC+2]`; classes 0xE0/0xD8 special (clear first byte); then PFC 0xFFFFE406 write.
- `serial_queue_message` (0x47C): spin-wait `[0xFFFFDFF8]==0xAA`, write to buffer 0xFFFFDFF0 (+0 first byte, +1 class+len, +2..+7 data, +8 status 0x55=used / 0xAA=free).

**Handlers:**

| Handler | Class | Bytes | Source |
|---|---|---|---|
| `serial_rx_handler_ch0` (0x4C) | 0x88 | 6 | 0xFEC — gated on `(task[1]&0xFFFFFF07)==0` |
| `serial_rx_handler_ch1` (0x64) | 0x90 | 6 | 0xFF8 |
| `serial_rx_handler_ch2` (0xC0) | 0xC0 | 6 | 0xFE4 |
| `serial_data_write_handler` (0x7C0) | 0x98 | — | `build_be32_from_bytes` (0xF4) of task+2 → `[0xFFFFDFA0]` |
| `serial_data_read_handler` (0x8A) | 0xB0 | — | `build_be32` + `calculate_checksum` (0x11A), dispatch with checksum byte |
| `diag_transfer_806` (0x806) | 0xA8 | — | `memset_ram_bounded` (0x87C) to diag buffer `[0xFFFFDFBC]` |
| `exception_context_restore` (0x7C) | 0xA0 | — | `[0xFFFFDFA4]=ctx`, SP=`[0xFFFFDFA0]`, jmp `vector_trampoline_set_sp` |
| `fatal_error_infinite_loop` (0xD8) | 0xC8 | — | SR |= 0xF0 (mask interrupts), infinite loop |

## Scheduler / EEPROM

- `task_scheduler_dispatch` (0x364): counter `[0xFFFFDFB4]`, task table 0xFFFFD4E0 (8-byte entries); not busy → `diag_transfer_210` (0x210), busy → `eeprom_read_validate` (0x450); counter mod 100.
- `diag_transfer_210` (0x210): check PFC 0xFFFFE40E / 0xFFFFE41A bit 0x100, then call 0xACE (entry, 8, 0, 0xFFFFE4B0).
- `eeprom_read_validate` (0x450): if `[0xFFFFDFE4+8]==0x55` → copy 8 bytes to r4, mark 0xAA, return 1; else return −1.

## RAM map (verified)

| Address | Role |
|---|---|
| 0xFFFFD4E0 | Task queue ring buffer (100 × 8B) |
| 0xFFFFDFA0 | SP / current 32-bit value (serial write) |
| 0xFFFFDFA4 | Exception context pointer |
| 0xFFFFDFA8 | Busy flag (serial dispatch) / gpio arg byte |
| 0xFFFFDFAC | Direct dispatch buffer |
| 0xFFFFDFB4 | Task queue write index / scheduler counter |
| 0xFFFFDFB6 | Task queue read index |
| 0xFFFFDFB8 | Dispatcher flag |
| 0xFFFFDFBC | Diag buffer pointer |
| 0xFFFFDFE4 | EEPROM staging buffer (8B + status 0x55/0xAA) |
| 0xFFFFDFF0 | Serial queue buffer (8B + status) |
| 0xFFFFDFFC | Recovery cell (0x5AA5A55A) |
| 0xFEC / 0xFE4 / 0xFF8 | Serial RX buffers — **hypothesis**: region 0x400–0xFFF may be undocumented 4 KB internal RAM; zero-filled in flash image |

## CAN subsystem

The IDB already contains 130+ well-named CAN functions from the CSV import (CANControllerSetup 0x9878, canMessageSetup 0x2B320, can_filter_apply 0x49216, can_encode_handler_* ×40, ImmoGetCANData 0x36870, setImmoCANTXData 0x369B8, CANTX_Main 0xDDF0, canSetup 0xDC8C, etc.).

### RX path (verified)

- `can_rx_handler_49100` (0x49100): calls function at 0x3EEFE three times with r4 = 0xFFFF878C / 0xFFFF8788 / 0xFFFF878A (CAN RX registers)
- `can_frame_parse_491AC` (0x491AC): checks flags at 0xFFFFB56D/0xFFFFB56E/0xFFFFB567/0xFFFFB568 (==1), counters at 0xFFFFCD28/0xFFFFCCF8, config tables in ROM at 0x7C2AC/0x7C2B6
- `can_msg_parse_4657C` (0x4657C): CAN→UDS bridge. Uses readValue_8bit (0x3ED3C) and add16bitSaturate_ADD1_ADD2 (0x2460) — cross-validates the word-swap rule. Checks [0xFFFFCD02]==1, [0xFFFFA110]==1, counter comparisons vs ROM config 0x7C396/0x7C394, sets flag 0xFFFFCC34, final dispatch to 0x67740 with r4=0x67 (103), r5=1/2

### RAM cells used by CAN

| Address | Role |
|---|---|
| 0xFFFF8788 / 0xFFFF878A / 0xFFFF878C | CAN RX registers |
| 0xFFFFB567 / 0xFFFFB568 / 0xFFFFB56D / 0xFFFFB56E | CAN flags |
| 0xFFFFCC34 | CAN dispatch flag |
| 0xFFFFCD02 | CAN state byte |
| 0xFFFFCD28 | CAN counter |
| 0xFFFFCCF8 | CAN counter |
| 0xFFFFA110 | CAN enable flag |

## UDS/OBD subsystem

### Handler inventory

- 236 `obd_service_handler_*` functions, contiguous block 0x630A4 → 0x6C166, mostly small stubs (0x6–0x16C bytes). Full list in /tmp/opencode/obd_handlers.txt.
- UDS-related: uds_* = 7, dtc_* = 74 (30 general + 19 data_read + 25 handler), *security* = 11, *seed* = 5.

### SecurityAccess (verified)

- `diag_security_access_sid27` (0x17D8): SID 0x27, response SID 0x67, NRC prefix 0x7F, seed/key parity state machine. 4-byte seed at 0xFFFFD211–214 (`security_seed_copy`). Confirms docs/notes/UDS_SECURITY_MAPPING.md (seed 0xFFFFD211..213, level 0xFFFFD214).

### Sampled handlers (8 analyzed)

- 0x630A4: session-state machine on RAM 0xFFFF87D2, dispatches to sub-handlers 0x67F54/0x67FFE/0x68358
- 0x6402A: 0x444-byte table init at 0xFFFF8930 (21 rows × 0x34, marker 0xA3)
- 0x64E54: gated chain calling 0x630A4/0x60734/0x6072E
- 0x66020: flag OR
- 0x675E6: 2-iteration mask check vs ROM table 0x7E734
- 0x682DA: indexed byte store, stride 40
- 0x691B2: sub-function byte dispatcher on 0x00/0x10/0x20/0x30 → sub-handlers 0x69200/0x69224/0x69262/0x692A4, common tail 0x69602, debounce threshold 0xF, counters 6/7/0xA
- 0x6C166: is DATA, not code (mislabeled function in CSV)

### RAM cells used by UDS/OBD

| Address | Role |
|---|---|
| 0xFFFF87D2 / 0xFFFF87C4 | Session state (0x630A4) |
| 0xFFFF8930 / 0xFFFF8D74 / 0xFFFF8D78 | Table init (0x6402A) |
| 0xFFFF8EA4 / 0xFFFF8EA6 | Flags (0x66020) |
| 0xFFFF8FC0 / 0xFFFF8ECE | Indexed store (0x682DA) |
| 0xFFFFDE0C–0xFFFFDE34 | Status struct + 0xFFFFDE18 (0x691B2 cluster) |
| 0xFFFFDFB0–0xFFFFDFC6 | SID 0x27 state |
| 0xFFFFC660 / 0xFFFFC688 / 0xFFFFC69A / 0xFFFFC69B | uds_* layer |
| 0xFFFFD211–214 | Security seed |

### Open items

- Dispatch mechanism for the 236 handlers NOT found: zero code xrefs (except 2), no data_refs, no literal refs, no byte-pattern hits. Hypothesis: runtime-built RAM table or base+offset arithmetic.
- Whether 0x10/0x20/0x30 in 0x691B2 are UDS sub-functions or OBD monitor-status selectors.
- uds_protocol_3e1f8 only partially decoded (IDA boundary issue in 0x3xxxx area).

## Configurazione finale: ELF big-endian (canonica)

### La configurazione canonica (verificata in sessione 2a784ade)

- Il file IDA canonico è `/home/davide/ailocal/rx8ecu/tmp/ida/60E1D400_be.elf`: un ELF SuperH a 32 bit **big-endian** (EM_SH=42, EI_DATA=2, e_entry=0x8B8) che incapsula la ROM **originale non word-swappata** a vaddr 0x0, con 3 segmenti PT_LOAD:
  - ROM @ 0x0 (R+X, 0x80000)
  - RAM @ 0xFFFF6000 (R+W, 0x8000)
  - periferiche @ 0xFFFFF000 (R+W, 0x1000)
- Costruito da `tmp/ida/make_elf.py` (deterministico, con `assert` sulle dimensioni: ROM 0x80000, header ELF 52 byte, 3 phdr 96 byte, file 0x81000).
- Aperto in IDA **senza argomenti loader** (nessun `-psh3` o altro flag).

### Perché è migliore

- **Decodifica big-endian corretta** senza workaround: `0x20DC` = `sts.l macl, @-r15` (byte `4f 12`), `0x2460` = `extu.w r4, r4`, `0x6C8` = `main_task_dispatcher`.
- I literal mostrano i valori **reali**: `0x8D2` = `mov.l #(loc_FFFE+1), r0` con valore `0x0000FFFF` (dal literal a 0x9B0) — nessuna conversione mentale word-swap.
- I segmenti RAM e periferiche sono mappati e leggibili in IDA.
- **2670 funzioni auto-create** all'apertura (2689 totali oggi: +18 definite dal re-import simboli +1 split `serial_queue_message`).

### Configurazioni superate (storico)

| Config | Esito |
|---|---|
| (a) `tmp/ida/60E1D400_bswap.bin` + `swap16.py` + loader arg `-psh3` | Funzionava, ma: literal `mov.l` visualizzati **swappati** (valore reale = swap delle due metà 16-bit del valore visualizzato; i literal `mov.w` a 16-bit visualizzati correttamente) e **RAM non mappata**. |
| (b) `-psh2` / `-psh2e` / `-psh` | Non aprono il file. |
| (c) `-psh4` | Misdecodifica (istruzioni a 4 byte). |
| (d) `-psh3 -B` / `-psh3 -b` | Crash del worker. |

Il modulo SH di IDA è **solo little-endian** e **senza supporto FPU**: gli opcode `0xFxxx` restano indecodificabili (121 funzioni interessate, non risolvibile).

### Tabella dei vettori (byte 0x0–0x3C, indirizzi BE a 32 bit)

| Vettore | Valore | Ruolo |
|---|---|---|
| 0 | `0x8B8` | Reset → `Manual_Reset` |
| 1 | `0xFFFFDFA0` | SP iniziale |
| 2–3 | `0x8B8` / `0xFFFFDFA0` | Coppie PC/SP |
| 4–13 | `0x8B4` | Trap di eccezione: `bra loc_8B4` loop infinito — eccezioni inattese bloccano la CPU |
| 14–15 | `0xFFFFFFFF` | Non usati |

### Import simboli (sessione 2a784ade, IDB `tmp/ida/60E1D400_be.elf.i64`)

- Fonte: `symbols/symbols_60E1D400_merged.csv` (**2790 righe**, colonne `addr,end,name,source,flag`; gli indirizzi sono offset di file = vaddr ELF, ROM a 0x0; nessuna entry RAM nel CSV, max 0x6C166).
- Pipeline: `define_code` → `define_func(addr,end)` → `rename`.
- Risultati (vedi `tmp/ida/reimport_report.txt`):
  - `define_code`: **2773 ok / 17 fail** (regioni dati `0x3EE68` e `0x69B9E..0x6C166`).
  - `define_func`: **2620 già esistenti + 18 nuove definite + 152 fallite** (= 2790 items del manifest).
  - `rename`: **2767 ok / 23 fail** (attesi: `calc_spark_advance` duplicato `0x01237C` vs `0x0121F0`; indirizzi in regioni dati).
- Gap manuale: `main_task_dispatcher` (0x6C8) definita a mano 0x6C8–0x796 e rinominata.
- Rinominazioni verificate: `diag_security_access_sid27` (0x17D8), `eeprom_read_validate` (0x450).

### Verifica nomi manuali (vedi `tmp/ida/name_verify_report.txt`)

Solo **4 nomi** della vecchia sessione NON sono nel CSV (il CSV è stato costruito da IDB + ghidra + c-lift):

- `serial_queue_message` (0x47C) — era confluita in `serial_dispatch` 0x338 come chunk tail-jump; ridefinita con bounds esatti (0x338 size 0x2c + 0x47C size 0x56), poi rinominata.
- `main_task_dispatcher` (0x6C8)
- `f_2DLookup` (0x2068)
- `f_3dLookup` (0x20DC)

Tutti e 4 verificati **CORRETTI** contro il disassembly:

- 0x47C: attende il byte sync `0xAA`, dispatch su tipo messaggio `0xE0`/`0xD8`, copia il payload, ritorna ACK `0x55`.
- 0x6C8: dispatch su task-type mascherato `0xF8`.
- 0x2068: `axis_search_float_array` + jump table + `fmac` = lookup mappa 2D.
- 0x20DC: `table2d_axis_resolve` + jump table + `fmac` a due stadi = lookup mappa 3D.

**Nessuna correzione** e nessuna terminologia pistoni (Renesis 13B-MSP rotativo).

### RAM ora importabile

Il segmento RAM dell'ELF (0xFFFF6000–0xFFFFDFFF) rende importabili i simboli di `symbols/RAM_VARIABLES.csv` (**1613 indirizzi** 0xFFFF00B1–0xFFFFFFFF) come simboli dati.

**Nota**: gli indirizzi **sotto 0xFFFF6000 NON sono coperti** dal segmento RAM.

---

## Analisi RTOS — Task Scheduler (sessione ae00d360)

### Modello di scheduling

Il scheduler è **cooperativo (non preemptive)**: i task girano fino al completamento e
cedono il controllo esplicitamente. Nessun cambio di contesto forzato da timer interrupt.
Le interruzioni postano nella coda task, non eseguono dispatch diretto.

**4 livelli di priorità** (dal `task_priority_scheduler` 0x3C80):

| Livello | Bits | Ruolo |
|---|---|---|
| 3 (massimo) | 0x60 | Engine control critico |
| 2 | 0x40 | Timing / elaborazione sensori |
| 1 | 0x20 | I/O e comunicazione |
| 0 (minimo) | 0x00 | Task di background |

### Ciclo di vita del task

```
Reset → Manual_Reset (0x8B8) → resetHandler (0x4E0)
  → secondary_boot_main (0xA038)
    → task_context_switch (0x3AD8, r4=0)  ← avvia RTOS
      → jmp 0x3E10 (RTOS_init_entry)
        → task_queue_init (0x3964)
        → task_table_scan_init (0x3EC0)
        → task_dependency_handler (0x3F10)
        → task_set_current_ptr (0x3AC0)
        → task_full_context_save (0x3BF4) → schedule
```

### Task queue (ring buffer)

- 100 entry × 8 byte a `0xFFFFD4E0` (RAM)
- Write index `[0xFFFFDFB4]` (u16), read index `[0xFFFFDFB6]` (u16)
- `task_queue_pending_count` (0x3E0): `(write - read) mod 100`
- `task_queue_get_next` (0x3B0): legge entry, incrementa read mod 100

Entry format (8 byte):
| Offset | Size | Descrizione |
|---|---|---|
| 0 | 1 | Source/origin byte |
| 1 | 1 | Command type code (dispatched su `& 0xF8`) |
| 2-7 | 6 | Payload / parametri |

### Main loop — `main_task_dispatcher` (0x6C8)

Pulisce `[0xFFFFDFB8]`, poi cicla:
1. `task_scheduler_dispatch` (0x364) — processa EEPROM/diag
2. `task_queue_pending_count` (0x3E0)
3. Se pending == 0 → idle path
4. `task_queue_get_next` (0x3B0)
5. Dispatch su `task[1] & 0xF8`

### Task table (ROM a 0x6873C)

Entry a 8 byte: `{uint16_t marker, uint16_t arg_count, uint32_t func_ptr}`

| Entry | Marker | Args | Funzione |
|---|---|---|---|
| 0 | 0x0002 | 3 | `uds_task_entry` (0x696DC) |
| 1 | 0x0001 | 4 | 0x689E6 |
| 2 | 0x0003 | 3 | 0x61ACE |
| 3 | 0x0003 | 2 | 0x661BC |
| 4 | 0x0003 | 2 | 0x563B2 |
| 5 | 0x0003 | 1 | 0x625C8 |
| 6 | 0x0003 | 0 | 0x65430 |

`marker == 0xFFFF` → chiamata diretta; altrimenti → dispatcher 0x5F34 con marker come chiave.

### Context switch

- `task_context_switch` (0x3AD8): valida task_id, salva SR/PR, store SP → `[0xFFFF72D8]`, carica SR da `[0x4B04]`, SP da `[0x4938]`
- `task_full_context_save` (0x3BF4): salva r5, PR, r8-r12, GBR, r13, MACH, r14, MACL; se type==4: anche fr12-fr15
- Stack layout full save (partenza SP=0xFFFFDF00):
  ```
  0xFFFFDEFC: r5       0xFFFFDEE0: r12
  0xFFFFDEF8: PR       0xFFFFDEDC: GBR
  0xFFFFDEF4: pad      0xFFFFDED8: r13
  0xFFFFDEF0: r8       0xFFFFDED4: MACH
  0xFFFFDEEC: r9       0xFFFFDED0: r14
  0xFFFFDEE8: r10      0xFFFFDECC: MACL
  0xFFFFDEE4: r11      [se type==4: fr12/fr13/fr14/fr15]
  ```

### Timer tick

- Fonte primaria: ATU (Advanced Timer Unit), canali configurati in `atu_timer_init` (0x10AC)
- Interrupt timer postano nella coda, non eseguono dispatch diretto
- Watchdog (WDT): `wdt_init` (0x572), usato per reset di sistema, non scheduling
- Idle loop: `0xA06E` (loop infinito dopo avvio RTOS)

### Funzioni RTOS verificate (28/28)

| Funzione | Indirizzo | Note |
|---|---|---|
| `main_task_dispatcher` | 0x6C8 | Loop principale, dispatch su task[1]&0xF8 |
| `task_scheduler_dispatch` | 0x364 | Queue scheduler, EEPROM/diag |
| `task_queue_get_next` | 0x3B0 | Prossima entry dal ring buffer |
| `task_queue_pending_count` | 0x3E0 | (write-read) mod 100 |
| `task_queue_init` | 0x3964 | Azzera queue, init slot a -1 |
| `task_context_switch` | 0x3AD8 | Save/restore SR/SP, jmp RTOS init |
| `task_full_context_save` | 0x3BF4 | Full callee-saved register save |
| `task_context_save_enter` | 0x3238 | ISR/switch entry, salva r2-r7 + FPU |
| `task_priority_scheduler` | 0x3C80 | Selezione livello priorità |
| `task_completion_handler` | 0x3D58 | Completamento task + consistency check |
| `task_table_scan_init` | 0x3EC0 | Itera task, imposta stato inactive |
| `task_dependency_handler` | 0x3F10 | Decrementa contatori, abilita dipendenti |
| `task_ready_check` | 0x3FB0 | Valida indice, check ready bitmask |
| `task_handler_run_by_index` | 0x5F34 | Marker dispatch, queue management |
| `task_handler_init_and_run` | 0x6034 | Init + run per startup tasks |
| `task_execute_by_index` | 0x3854 | Counter gating, dependency check |
| `task_scheduler` | 0xAB06 | Scheduler superiore (timer-based) |
| `task_state_mapper` | 0xAC94 | Mappa stato ECU → task state code |
| `task_scheduler_check_and_sync` | 0xAECC | Rotor position sync |
| `task_loader_dispatcher` | 0xBA56 | Loader/task dispatch |
| `task_msg_dispatch_conditional` | 0xC2E6 | Conditional message dispatch |
| `main_periodic_task` | 0xDD76 | CAN setup + PCM init sequence |
| `task_flag_run_A` | 0x3588 | OR flag 0x10000, chiama handler, clear |
| `task_flag_run_C` | 0x35EE | OR flag 0x8000, chiama handler, clear |
| `wdt_init` | 0x572 | Watchdog timer init |
| `eeprom_read_validate` | 0x450 | Read + valida EEPROM staging |
| `diag_transfer_210` | 0x210 | Check PFC, chiama 0xACE |

---

## Analisi Seriale — Protocollo Comunicazione (sessione ae00d360)

### Bus fisico

L'ECU RX-8 usa DUE interfacce seriali distinte:

**A) ATU-Based Serial (interfaccia diagnostica primaria)**
- Hardware: SH-2 Advanced Timer Unit (ATU) canali configurati per I/O
- Registri: range 0xFFFFE4xx (periferica custom, NON standard UART)
- `0xFFFFE406`: Status register (bit 0x200 = busy, bit 0x80 = ready)
- `0xFFFFE40A`: Data register (TX/RX)
- `0xFFFFE40E`: RX status register (bit 0x100 = dati disponibili, bit 0x60 = status)
- `0xFFFFE41A`: Error/clear register (bit 0x100 = errore)
- `0xFFFFE4B0`/`0xFFFFE4B8`: Buffer registers
- Implementazione seriale basata su TIMER (bit-banged o capture/compare)

**B) SCI4 (interfaccia secondaria)**
- Hardware: SH-2 Serial Communication Interface canale 4
- Registri: `0xFFFFF020`–`0xFFFFF025`
- Baud rate: 115200 (`sci4_init_8n1_115200`) e 57600 (`sci4_init_8n1_57600_verify`)
- Formato: 8N1
- Probabilmente usata per flash programming o debug

La interfaccia diagnostica primaria (ATU) **NON ha baud rate fisso** in ROM.
Il baud rate è determinato dalla configurazione ATU a runtime.

### Tre canali logici

| Codice cmd | Handler | Canale | RX Buffer | Descrizione |
|---|---|---|---|---|
| 0x88 | `serial_rx_handler_ch0` | ch0 | 0xFEC | Diagnostica principale |
| 0x90 | `serial_rx_handler_ch1` | ch1 | 0xFF8 | Diagnostica secondaria |
| 0xC0 | `serial_rx_handler_ch2` | ch2 | 0xFE4 | Diagnostica terziaria |
| 0xB0 | `serial_data_read_handler` | — | — | Richiesta lettura dati |
| 0x98 | `serial_data_write_handler` | — | — | Richiesta scrittura dati |
| 0xA8 | `diag_transfer_806` | — | — | Transfer diagnostico |
| 0xA0 | `exception_context_restore` | — | — | Gestione eccezioni |

I tre canali (ch0/ch1/ch2) sono canali LOGICI, non UART separati.
Condividono hardware ATU ma sono distinti da codici comando diversi e buffer RX diversi.

### Formato frame seriale

```
[Source/origin][Length][Payload...][Checksum]
```

- Sync protocol: `0xAA` = slot pronto, `0x55` = messaggio scritto (ACK)
- Buffer direct TX a `0xFFFFDFAC`
- Buffer queue a `0xFFFFDFF0` (sync byte a offset 8)

### Dispatch seriale (0x338)

`serial_dispatch` instrada messaggi su DUE path:

1. **Direct path** (`loc_256`, 0x256): se `[0xFFFFDFA8]==0` → copia payload direttamente a hardware
2. **Queue path** (`serial_queue_message`, 0x47C): se busy → attende sync 0xAA, formatta, scrivi 0x55

### Helper functions

| Funzione | Indirizzo | Ruolo |
|---|---|---|
| `build_be32_from_bytes` | 0xF4 | Costruisce valore 32-bit BE da 4 byte |
| `calculate_checksum` | 0x11A | Checksum additivo con carry folding |
| `write_verify_bytes` | 0xAE8 | Scrivi byte con verifica read-back |
| `atu_wait_and_transfer` | 0x1168 | Attende ATU ready, trasferisce dati |
| `atu_channel_transfer` | 0x1116 | Check ATU RX status, legge dati |
| `serial_comm_init_490B0` | 0x490B0 | Init parametri comunicazione seriale |

---

## Analisi Motore Rotario — Engine Control (sessione ae00d360)

### Posizione eccentric shaft

Il Renesis 13B-MSP usa una ruota trigger a 3×6+1 (20 denti) sull'albero eccentrico
con gap di sincronizzazione (dente mancante) per il sync del rotore.

**RAM principali:**

| Indirizzo | Ruolo |
|---|---|
| 0xFFFF9F94 | crank (state byte posizione principale) |
| 0xFFFF9F95 | Stato macchina (max 0x24) |
| 0xFFFF9FBC | Accumulatore timing crank (float) |
| 0xFFFF9FC1 | Sync state: 0=idle, 1=searching, 2=partial, 3=synced |
| 0xFFFF9FC2 | Contatore denti (satura a 0xFF) |
| 0xFFFF9FCB | Flag rilevamento gap |
| 0xFFFFA1E0 | Media mobile risultato sync rotore |

**Funzioni principali:**

| Funzione | Indirizzo | Ruolo |
|---|---|---|
| `crank_position_state_machine` | 0x789E | State machine posizione eccentric shaft |
| `crank_timing_update` | 0x7814 | Aggiorna timing base su eventi denti |
| `crank_sync_acquire` | 0x7AAA | Acquisisce sincronizzazione |
| `crank_tooth_validate` | 0x7AD6 | Valida singoli eventi denti |
| `crank_gap_detect` | 0x7E60 | Rileva il gap (6° evento) |
| `rotor_position_synchronization` | 0xAF10 | Sincronizzazione posizione rotore |

### Ignition timing — Leading e trailing spark

Il Renesis 13B-MSP usa 4 bobine di accensione (2 per rotore):
- **Leading spark**: prima scintilla, vicino a TDC
- **Trailing spark**: dopo leading, ritardata per emissioni

| Funzione | Indirizzo | Ruolo |
|---|---|---|
| `ignition_timing_output_1E6B6` | 0x1E6B6 | Output principale timing accensione |
| `wankel_rotary_control_1E820` | 0x1E820 | Controllo specifico Wankel con correzione |
| `ignition_timing_calc_E7F8` | 0xE7F8 | Calcolo core timing accensione |
| `outputPerRotorIgnitionDwell` | 0x11218 | Output dwell per singolo rotore |
| `ignitionDwellOutputInit` | 0x8F62 | Init hardware dwell output |
| `ignition_advance_limiter` | 0xE38C | Limitatore anticipo accensione |
| `adaptive_ignition_table_213D0` | 0x213D0 | Tabella accensione adattiva |
| `calc_ignition_all_rotors_13C2C` | 0x13C2C | Calcolo accensione entrambi i rotori |
| `ignition_timing_safety_check_1FAEA` | 0x1FAEA | Safety check timing |

**RAM ignition:**

| Indirizzo | Ruolo |
|---|---|
| 0xFFFFB0E8 | Timing accensione filtrato |
| 0xFFFFB104 | Delta timing leading |
| 0xFFFFB108 | Delta timing trailing |
| 0xFFFFB12C | engine_ctrl_state (word stato engine) |

### Fuel injection — 4 iniettori

Il Renesis ha 4 iniettori:
- **Primary**: sparano per intake port (erogazione principale)
- **Secondary**: sparano per arricchimento (alto carico, avvio a freddo)

| Funzione | Indirizzo | Ruolo |
|---|---|---|
| `sequential_fuel_injection_211DC` | 0x211DC | Controllo iniezione sequenziale |
| `calc_fuel_injection_all_rotors` | 0x13D3C | Calcolo iniezione entrambi i rotori |
| `fuel_injector_multiplexed_control` | 0x101CA | Controllo multiplexato iniettori |
| `fuel_inject_pulse_per_rotor` | 0xFBB6 | Calcolo impulso per rotore |
| `fuel_injector_pulse_calc` | 0x10620 | Calcolo core lunghezza impulso |
| `rpm_limiter_fuel_cutoff` | 0xC508 | Limite RPM fuel cutoff |
| `calc_fuel_trims_adaptive` | 0x117B4 | Fuel trim adattivo |
| `calc_fuel_trim_correction_map` | 0x136F0 | Mappa correzione fuel trim |
| `rotary_fuel_enrichment_controller` | 0x14C2C | Controllo arricchimento specifico rotario |
| `fuel_pressure_calc_with_interpolation` | 0xE6D8 | Calcolo pressione carburante |

**RAM fuel:**

| Indirizzo | Ruolo |
|---|---|
| 0xFFFFA73C | Valore iniezione rotore B |
| 0xFFFFA740 | Flag enable iniezione |
| 0xFFFFA744 | Valore iniezione rotore A |
| 0xFFFFA56C | fuel_cut_flag (fuel cut attivo) |
| 0xFFFF9F38 | Valore fuel rate float |
| 0xFFFF9F96 | if_engine_run (flag engine in esecuzione) |

### OMP (Oil Metering Port)

L'OMP inietta olio nelle porte di aspirazione per la lubrificazione degli anelli
apicali del rotore.

| Funzione | Indirizzo | Ruolo |
|---|---|---|
| `omp_control_task_1825E` | 0x1825E | Task principale controllo OMP |
| `omp_stepper_waveform_driver` | 0x18552 | Driver waveform stepper |
| `omp_waveform_state_machine_18860` | 0x18860 | State machine waveform 4 stati |
| `rotor_sync_position_detector` | 0x189EE | Detector posizione sync rotore |

**RAM OMP:**

| Indirizzo | Ruolo |
|---|---|
| 0xFFFFA968..A96C | Stato OMP (5 byte) |
| 0xFFFFA97B | Contatore decremento OMP |
| 0xFFFF807C | Registro output OMP |

### Main engine cycle (10ms task)

**Funzione**: `main_engine_cycle_10ms` @ 0x17F1C (size 0x60)

Catena di chiamata:
```
read_prev_rotor_pair_status (0x11794)
  → idle_control_priority_task (0x1AA18)
  → priority_task_dispatch_2B070 (0x2B070)
  → main_engine_cycle_10ms (0x17F1C)  ← QUESTA FUNZIONE
  → obd_service_handler_69624 (0x69624)
```

Logica timer:
- Contatore 0xFFFFA964 incrementa ogni chiamata 10ms (ciclo 0-7)
- Subset task girano ogni 80ms (counter < 8, 7/8 chiamate)
- OMP control gira ogni 10ms indipendentemente

Subset task (ogni 80ms):
1. `idle_speed_control_18054` — controllo velocità idle
2. `fuel_pump_control_0x17510` — relay pompa carburante
3. `exhaust_port_control` (0x17700) — timing porta scarico
4. `intake_air_control_0x177A6` — controllo aria aspirata
5. `torque_calc_with_damping` (0x17952) — calcolo coppia

Sempre (ogni 10ms): `omp_control_task_1825E`

### Fuel control pipeline (28 chiamate)

**Funzione**: `main_fuel_control_pipeline_22094` @ 0x22094

Sequenza:
```
Sensor Inputs → calcCLorOLControl → manifold_pressure_calc
  → sequential_fuel_injection → fuel_injection_duty_cycle
  → adaptive_ignition_table → ignition_timing_output
  → wankel_rotary_control → sensor_validation
  → combustion_control_loop → ignition_timing_safety_check
```

### Statistiche sintesi

- Funzioni specifiche rotario identificate: 43+
- Funzioni accensione: 28
- Funzioni iniezione: 50+
- Funzioni posizione crank/eccentric shaft: 35+
- RAM address identificati: 45+
- Sottosistemi mappati: 5 (posizione, accensione, iniezione, OMP, ciclo 10ms)

---

## EEPROM — Analisi Esterna SPI (sessione ae00d360)

### Architettura hardware

L'ECU RX-8 usa un **chip EEPROM SPI esterno** (NON on-chip SH-2E).
L'interfaccia SPI è bit-banged usando pin GPIO mappati through il CAN controller register space.

**CHIAVE**: L'on-chip EEPROM SH-2E/SH7055 (tipicamente 2KB a 0xFFFFF000-0xFFFFF7FF)
NON è usato per storage persistente. Tutte le operazioni EEPROM passano per chip SPI esterno.

### SPI Register Map

| Indirizzo | Nome | Ruolo |
|---|---|---|
| 0xFFFFE401 | SPI_CLK_DATA_CTRL | Bit 0: clock out, Bit 3: transfer status |
| 0xFFFFE402 | SPI_CONTROL | SPI control register |
| 0xFFFFE404 | SPI_CONFIG | SPI configuration |
| 0xFFFFE406 | SPI_DATA_0 | SPI data register 0 |
| 0xFFFFE40A | SPI_DATA_2 | SPI data/config register 2 |
| 0xFFFFE414 | SPI_CHANNEL_CONFIG | SPI channel configuration |
| 0xFFFFE4B0 | SPI_BUFFER_0 | SPI buffer register 0 |
| 0xFFFFE4B8 | SPI_BUFFER_1 | SPI buffer register 1 |

### Funzioni SPI

| Funzione | Indirizzo | Ruolo |
|---|---|---|
| `spi_set_clk_high_wait` | 0x9C0 | Set clock HIGH, attende transfer complete |
| `spi_set_clk_low_wait` | 0x9DE | Set clock LOW, attende data ready |
| `spi_eeprom_read` | 0x49700 | Init operazione lettura SPI EEPROM |
| `spi_eeprom_write` | 0x496BA | Scrittura con wear-leveling |
| `spi_eeprom_verify` | 0x49778 | Verifica integrità dati EEPROM |
| `flash_program` | 0x497B0 | Programmazione flash con verifica |
| `flash_erase` | 0x4988C | Cancellazione blocco flash |
| `flash_checksum` | 0x4990C | Checksum flash memory |

### EEPROM Memory Map

**RAM staging:**

| Range | Size | Ruolo |
|---|---|---|
| 0xFFFFC2FE–0xFFFFC3FE | 256 byte | EEPROM data staging buffer |
| 0xFFFFC3FE–0xFFFFC4FE | 256 byte | Copia invertita per verifica |
| 0xFFFFDFE4 | 8 byte + status | RAM buffer A (0x55=valid, 0xAA=consumed) |
| 0xFFFFDFF0 | 8 byte + status | RAM buffer B |

**Strutture controllo:**

| Indirizzo | Nome | Ruolo |
|---|---|---|
| 0xFFFFC297 | eeprom_busy_flag | Operazione in corso |
| 0xFFFFC29B | eeprom_write_pending | Scrittura pending |
| 0xFFFFC2D1 | eeprom_commit_request | Richiesta commit |
| 0xFFFFC2D2 | eeprom_commit_done | Commit completato |
| 0xFFFFC2F8 | eeprom_commit_status | Status per categoria |

### EEPROM data categories

| Categoria | Offset | Size | Scopo probabile |
|---|---|---|---|
| 0x01 | 0x0A | 2 | Security keys / dati immobilizer |
| 0x02 | 0x02 | 8 | DTC codes |
| 0x03 | 0x00 | 2 | Parametri configurazione |
| 0x04 | 0x0C | 6 | Valori appresi (fuel trim, ecc.) |
| 0x05 | 0x12 | 2 | Livello security access |
| 0x06 | 0x0E | 2 | Dati adaptive learning |
| 0x07 | 0x16 | 4 | Identificazione ECU |
| 0x09 | 0x0C | 8 | Dati calibrazione |
| 0x0E | 0x0C | 2 | Dati service interval |
| 0x0F | 0x0E | 2 | Sync data immobilizer |
| 0xFF | 0x00 | 32 | Reset/inizializzazione EEPROM |

### EEPROM commit flow

1. `diag_getsr_3920` — disabilita interruzioni
2. Copia dati a staging buffer (`eeprom_atomic_ram_copy`)
3. Salva copia invertita per verifica
4. `diag_setsr_3934` — riabilita interruzioni
5. Set flag commit request (`0xFFFFC2D1 = 1`)
6. Chiama `eeprom_commit_dispatcher` con categoria
7. Priority check (`eeprom_priority_check`)
8. Attendi completamento
9. Verifica status

### Dimensione EEPROM stimata

- Staging buffer: 256 byte
- Verification buffer: 256 byte
- Strutture controllo: ~100 byte
- **Dimensione stimata**: 2KB (2048 byte) minimo
- Più probabilmente **2KB (256×8)** o **4KB (512×8)**

### Wear leveling

- Contatore 0xFFFFCCF8 incrementa ad ogni scrittura
- Reset a 0 quando scrittura non permessa
- Suggerisce wear-leveling across multipli blocchi EEPROM

---

## DTC (Diagnostic Trouble Codes) — Placeholder

> Analisi DTC in corso. Il sottosistema DTC è già parzialmente documentato in
> `docs/functions/dtc_management.md` e `docs/functions/dtcRelated.md`.
>
> Funzioni verificate: dtcRelated@0x62002, dtc_handler_610FA@0x610FA,
> dtc_handler_61550@0x61550, dtc_code_set/clear@0x46780/0x467AA,
> dtc_debounce_monitor_43760@0x43760.
>
> Vedi anche: `FINDINGS.md` sezione "DTC Management subsystem — Track-A verified".

---

## RAM import — Risultati (sessione ae00d360)

Da `symbols/RAM_VARIABLES.csv` (1613 indirizzi):
- Importabili (RAM+Periph): 1569
- Saltati (gap non mappato): 44 (range 0xFFFF0000–0xFFFF5FFF)
- Collisioni pre-esistenti: 404
- **Nuovi import questa sessione: 1165**
- **Totali globals in IDA ora: 2028** (range 0xFFFF6000–0xFFFFFFFF)

Metodo: tutti i nuovi simboli creati come `unsigned char` (1 byte).
Verifica spot-check: 0xFFFFDFA0 flag_gate ✓, 0xFFFFDFB8 ram_dfb8 ✓, 0xFFFFDFFC warm_boot_magic ✓.
