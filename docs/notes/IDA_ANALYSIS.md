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
