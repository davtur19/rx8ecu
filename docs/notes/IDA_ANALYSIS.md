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

## Final configuration: ELF big-endian (canonical)

### The canonical configuration (verified in session 2a784ade)

- The canonical IDA file is `/home/davide/ailocal/rx8ecu/tmp/ida/60E1D400_be.elf`: a 32-bit SuperH ELF **big-endian** (EM_SH=42, EI_DATA=2, e_entry=0x8B8) wrapping the **original non-word-swapped** ROM at vaddr 0x0, with 3 PT_LOAD segments:
  - ROM @ 0x0 (R+X, 0x80000)
  - RAM @ 0xFFFF6000 (R+W, 0x8000)
  - peripherals @ 0xFFFFF000 (R+W, 0x1000)
- Built by `tmp/ida/make_elf.py` (deterministic, with `assert` on sizes: ROM 0x80000, ELF header 52 bytes, 3 phdr 96 bytes, file 0x81000).
- Opened in IDA **without loader arguments** (no `-psh3` or other flags).

### Why it is better

- **Correct big-endian decoding** without workarounds: `0x20DC` = `sts.l macl, @-r15` (bytes `4f 12`), `0x2460` = `extu.w r4, r4`, `0x6C8` = `main_task_dispatcher`.
- Literals show the **real** values: `0x8D2` = `mov.l #(loc_FFFE+1), r0` with value `0x0000FFFF` (from the literal at 0x9B0) — no mental word-swap conversion needed.
- RAM and peripheral segments are mapped and readable in IDA.
- **2670 auto-created functions** at open (2689 total today: +18 defined by symbol re-import + 1 split `serial_queue_message`).

### Superseded configurations (historical)

| Config | Outcome |
|---|---|
| (a) `tmp/ida/60E1D400_bswap.bin` + `swap16.py` + loader arg `-psh3` | Worked, but: `mov.l` literals displayed **swapped** (real value = swap of the two 16-bit halves of the displayed value; `mov.w` 16-bit literals displayed correctly) and **RAM not mapped**. |
| (b) `-psh2` / `-psh2e` / `-psh` | Does not open the file. |
| (c) `-psh4` | Misdecodes (4-byte instructions). |
| (d) `-psh3 -B` / `-psh3 -b` | Worker crash. |

IDA's SH module is **little-endian only** and **has no FPU support**: opcodes `0xFxxx` remain undecipherable (121 affected functions, not resolvable).

### Vector table (bytes 0x0–0x3C, 32-bit BE addresses)

| Vector | Value | Role |
|---|---|---|
| 0 | `0x8B8` | Reset → `Manual_Reset` |
| 1 | `0xFFFFDFA0` | Initial SP |
| 2–3 | `0x8B8` / `0xFFFFDFA0` | PC/SP pairs |
| 4–13 | `0x8B4` | Exception trap: `bra loc_8B4` infinite loop — unexpected exceptions halt the CPU |
| 14–15 | `0xFFFFFFFF` | Unused |

### Symbol import (session 2a784ade, IDB `tmp/ida/60E1D400_be.elf.i64`)

- Source: `symbols/symbols_60E1D400_merged.csv` (**2790 rows**, columns `addr,end,name,source,flag`; addresses are file offsets = ELF vaddr, ROM at 0x0; no RAM entries in CSV, max 0x6C166).
- Pipeline: `define_code` → `define_func(addr,end)` → `rename`.
- Results (see `tmp/ida/reimport_report.txt`):
  - `define_code`: **2773 ok / 17 fail** (data regions `0x3EE68` and `0x69B9E..0x6C166`).
  - `define_func`: **2620 already existing + 18 newly defined + 152 failed** (= 2790 manifest items).
  - `rename`: **2767 ok / 23 fail** (expected: `calc_spark_advance` duplicate `0x01237C` vs `0x0121F0`; addresses in data regions).
- Manual gap: `main_task_dispatcher` (0x6C8) manually defined at 0x6C8–0x796 and renamed.
- Verified renames: `diag_security_access_sid27` (0x17D8), `eeprom_read_validate` (0x450).

### Manual name verification (see `tmp/ida/name_verify_report.txt`)

Only **4 names** from the old session are NOT in the CSV (the CSV was built from IDB + ghidra + c-lift):

- `serial_queue_message` (0x47C) — was merged into `serial_dispatch` 0x338 as a chunk tail-jump; redefined with exact bounds (0x338 size 0x2c + 0x47C size 0x56), then renamed.
- `main_task_dispatcher` (0x6C8)
- `f_2DLookup` (0x2068)
- `f_3dLookup` (0x20DC)

All 4 verified **CORRECT** against the disassembly:

- 0x47C: waits for sync byte `0xAA`, dispatches on message type `0xE0`/`0xD8`, copies payload, returns ACK `0x55`.
- 0x6C8: dispatches on masked task-type `0xF8`.
- 0x2068: `axis_search_float_array` + jump table + `fmac` = 2D map lookup.
- 0x20DC: `table2d_axis_resolve` + jump table + `fmac` two-stage = 3D map lookup.

**No corrections** needed and no piston terminology (Renesis 13B-MSP rotary).

### RAM now importable

The ELF RAM segment (0xFFFF6000–0xFFFFDFFF) makes the symbols in `symbols/RAM_VARIABLES.csv` (**1613 addresses** 0xFFFF00B1–0xFFFFFFFF) importable as data symbols.

**Note**: addresses **below 0xFFFF6000 are NOT covered** by the RAM segment.

---

## RTOS Analysis — Task Scheduler (session ae00d360)

### Scheduling model

The scheduler is **cooperative (non-preemptive)**: tasks run to completion and
yield control explicitly. No context switch is forced by timer interrupts.
Interrupts post to the task queue; they do not dispatch directly.

**4 priority levels** (from `task_priority_scheduler` 0x3C80):

| Level | Bits | Role |
|---|---|---|
| 3 (maximum) | 0x60 | Critical engine control |
| 2 | 0x40 | Timing / sensor processing |
| 1 | 0x20 | I/O and communication |
| 0 (minimum) | 0x00 | Background tasks |

### Task lifecycle

```
Reset → Manual_Reset (0x8B8) → resetHandler (0x4E0)
  → secondary_boot_main (0xA038)
    → task_context_switch (0x3AD8, r4=0)  ← starts RTOS
      → jmp 0x3E10 (RTOS_init_entry)
        → task_queue_init (0x3964)
        → task_table_scan_init (0x3EC0)
        → task_dependency_handler (0x3F10)
        → task_set_current_ptr (0x3AC0)
        → task_full_context_save (0x3BF4) → schedule
```

### Task queue (ring buffer)

- 100 entries × 8 bytes at `0xFFFFD4E0` (RAM)
- Write index `[0xFFFFDFB4]` (u16), read index `[0xFFFFDFB6]` (u16)
- `task_queue_pending_count` (0x3E0): `(write - read) mod 100`
- `task_queue_get_next` (0x3B0): reads entry, increments read mod 100

Entry format (8 bytes):
| Offset | Size | Description |
|---|---|---|
| 0 | 1 | Source/origin byte |
| 1 | 1 | Command type code (dispatched on `& 0xF8`) |
| 2-7 | 6 | Payload / parameters |

### Main loop — `main_task_dispatcher` (0x6C8)

Clears `[0xFFFFDFB8]`, then loops:
1. `task_scheduler_dispatch` (0x364) — processes EEPROM/diag
2. `task_queue_pending_count` (0x3E0)
3. If pending == 0 → idle path
4. `task_queue_get_next` (0x3B0)
5. Dispatch on `task[1] & 0xF8`

### Task table (ROM at 0x6873C)

8-byte entries: `{uint16_t marker, uint16_t arg_count, uint32_t func_ptr}`

| Entry | Marker | Args | Function |
|---|---|---|---|
| 0 | 0x0002 | 3 | `uds_task_entry` (0x696DC) |
| 1 | 0x0001 | 4 | 0x689E6 |
| 2 | 0x0003 | 3 | 0x61ACE |
| 3 | 0x0003 | 2 | 0x661BC |
| 4 | 0x0003 | 2 | 0x563B2 |
| 5 | 0x0003 | 1 | 0x625C8 |
| 6 | 0x0003 | 0 | 0x65430 |

`marker == 0xFFFF` → direct call; otherwise → dispatcher 0x5F34 with marker as key.

### Context switch

- `task_context_switch` (0x3AD8): validates task_id, saves SR/PR, stores SP → `[0xFFFF72D8]`, loads SR from `[0x4B04]`, SP from `[0x4938]`
- `task_full_context_save` (0x3BF4): saves r5, PR, r8-r12, GBR, r13, MACH, r14, MACL; if type==4: also fr12-fr15
- Stack layout full save (starting SP=0xFFFFDF00):
  ```
  0xFFFFDEFC: r5       0xFFFFDEE0: r12
  0xFFFFDEF8: PR       0xFFFFDEDC: GBR
  0xFFFFDEF4: pad      0xFFFFDED8: r13
  0xFFFFDEF0: r8       0xFFFFDED4: MACH
  0xFFFFDEEC: r9       0xFFFFDED0: r14
  0xFFFFDEE8: r10      0xFFFFDECC: MACL
  0xFFFFDEE4: r11      [if type==4: fr12/fr13/fr14/fr15]
  ```

### Timer tick

- Primary source: ATU (Advanced Timer Unit), channels configured in `atu_timer_init` (0x10AC)
- Timer interrupts post to the queue; they do not dispatch directly
- Watchdog (WDT): `wdt_init` (0x572), used for system reset, not scheduling
- Idle loop: `0xA06E` (infinite loop after RTOS startup)

### RTOS functions verified (28/28)

| Function | Address | Notes |
|---|---|---|
| `main_task_dispatcher` | 0x6C8 | Main loop, dispatch on task[1]&0xF8 |
| `task_scheduler_dispatch` | 0x364 | Queue scheduler, EEPROM/diag |
| `task_queue_get_next` | 0x3B0 | Next entry from ring buffer |
| `task_queue_pending_count` | 0x3E0 | (write-read) mod 100 |
| `task_queue_init` | 0x3964 | Clears queue, inits slots to -1 |
| `task_context_switch` | 0x3AD8 | Save/restore SR/SP, jmp RTOS init |
| `task_full_context_save` | 0x3BF4 | Full callee-saved register save |
| `task_context_save_enter` | 0x3238 | ISR/switch entry, saves r2-r7 + FPU |
| `task_priority_scheduler` | 0x3C80 | Priority level selection |
| `task_completion_handler` | 0x3D58 | Task completion + consistency check |
| `task_table_scan_init` | 0x3EC0 | Iterates tasks, sets state to inactive |
| `task_dependency_handler` | 0x3F10 | Decrements counters, enables dependents |
| `task_ready_check` | 0x3FB0 | Validates index, checks ready bitmask |
| `task_handler_run_by_index` | 0x5F34 | Marker dispatch, queue management |
| `task_handler_init_and_run` | 0x6034 | Init + run for startup tasks |
| `task_execute_by_index` | 0x3854 | Counter gating, dependency check |
| `task_scheduler` | 0xAB06 | Upper-level scheduler (timer-based) |
| `task_state_mapper` | 0xAC94 | Maps ECU state → task state code |
| `task_scheduler_check_and_sync` | 0xAECC | Rotor position sync |
| `task_loader_dispatcher` | 0xBA56 | Loader/task dispatch |
| `task_msg_dispatch_conditional` | 0xC2E6 | Conditional message dispatch |
| `main_periodic_task` | 0xDD76 | CAN setup + PCM init sequence |
| `task_flag_run_A` | 0x3588 | OR flag 0x10000, calls handler, clear |
| `task_flag_run_C` | 0x35EE | OR flag 0x8000, calls handler, clear |
| `wdt_init` | 0x572 | Watchdog timer init |
| `eeprom_read_validate` | 0x450 | Read + validate EEPROM staging |
| `diag_transfer_210` | 0x210 | Check PFC, calls 0xACE |

---

## Serial Analysis — Communication Protocol (session ae00d360)

### Physical bus

The RX-8 ECU uses TWO distinct serial interfaces:

**A) ATU-Based Serial (primary diagnostic interface)**
- Hardware: SH-2 Advanced Timer Unit (ATU) channels configured for I/O
- Registers: range 0xFFFFE4xx (custom peripheral, NOT standard UART)
- `0xFFFFE406`: Status register (bit 0x200 = busy, bit 0x80 = ready)
- `0xFFFFE40A`: Data register (TX/RX)
- `0xFFFFE40E`: RX status register (bit 0x100 = data available, bit 0x60 = status)
- `0xFFFFE41A`: Error/clear register (bit 0x100 = error)
- `0xFFFFE4B0`/`0xFFFFE4B8`: Buffer registers
- TIMER-based serial implementation (bit-banged or capture/compare)

**B) SCI4 (secondary interface)**
- Hardware: SH-2 Serial Communication Interface channel 4
- Registers: `0xFFFFF020`–`0xFFFFF025`
- Baud rate: 115200 (`sci4_init_8n1_115200`) and 57600 (`sci4_init_8n1_57600_verify`)
- Format: 8N1
- Probably used for flash programming or debug

The primary diagnostic interface (ATU) does **NOT have a fixed baud rate** in ROM.
The baud rate is determined by ATU configuration at runtime.

### Three logical channels

| Cmd code | Handler | Channel | RX Buffer | Description |
|---|---|---|---|---|
| 0x88 | `serial_rx_handler_ch0` | ch0 | 0xFEC | Primary diagnostics |
| 0x90 | `serial_rx_handler_ch1` | ch1 | 0xFF8 | Secondary diagnostics |
| 0xC0 | `serial_rx_handler_ch2` | ch2 | 0xFE4 | Tertiary diagnostics |
| 0xB0 | `serial_data_read_handler` | — | — | Data read request |
| 0x98 | `serial_data_write_handler` | — | — | Data write request |
| 0xA8 | `diag_transfer_806` | — | — | Diagnostic transfer |
| 0xA0 | `exception_context_restore` | — | — | Exception handling |

The three channels (ch0/ch1/ch2) are LOGICAL channels, not separate UARTs.
They share ATU hardware but are distinguished by different command codes and different RX buffers.

### Serial frame format

```
[Source/origin][Length][Payload...][Checksum]
```

- Sync protocol: `0xAA` = slot ready, `0x55` = message written (ACK)
- Direct TX buffer at `0xFFFFDFAC`
- Queue buffer at `0xFFFFDFF0` (sync byte at offset 8)

### Serial dispatch (0x338)

`serial_dispatch` routes messages to TWO paths:

1. **Direct path** (`loc_256`, 0x256): if `[0xFFFFDFA8]==0` → copies payload directly to hardware
2. **Queue path** (`serial_queue_message`, 0x47C): if busy → waits for sync 0xAA, formats, writes 0x55

### Helper functions

| Function | Address | Role |
|---|---|---|
| `build_be32_from_bytes` | 0xF4 | Builds 32-bit BE value from 4 bytes |
| `calculate_checksum` | 0x11A | Additive checksum with carry folding |
| `write_verify_bytes` | 0xAE8 | Write bytes with read-back verification |
| `atu_wait_and_transfer` | 0x1168 | Waits for ATU ready, transfers data |
| `atu_channel_transfer` | 0x1116 | Checks ATU RX status, reads data |
| `serial_comm_init_490B0` | 0x490B0 | Init serial communication parameters |

---

## Rotary Engine Analysis — Engine Control (session ae00d360)

### Eccentric shaft position

The Renesis 13B-MSP uses a 3×6+1 (20-tooth) trigger wheel on the eccentric shaft
with a synchronization gap (missing tooth) for rotor sync.

**Primary RAM cells:**

| Address | Role |
|---|---|
| 0xFFFF9F94 | crank (main position state byte) |
| 0xFFFF9F95 | State machine (max 0x24) |
| 0xFFFF9FBC | Crank timing accumulator (float) |
| 0xFFFF9FC1 | Sync state: 0=idle, 1=searching, 2=partial, 3=synced |
| 0xFFFF9FC2 | Tooth counter (saturates at 0xFF) |
| 0xFFFF9FCB | Gap detection flag |
| 0xFFFFA1E0 | Rotor sync result moving average |

**Primary functions:**

| Function | Address | Role |
|---|---|---|
| `crank_position_state_machine` | 0x789E | Eccentric shaft position state machine |
| `crank_timing_update` | 0x7814 | Updates base timing on tooth events |
| `crank_sync_acquire` | 0x7AAA | Acquires synchronization |
| `crank_tooth_validate` | 0x7AD6 | Validates individual tooth events |
| `crank_gap_detect` | 0x7E60 | Detects the gap (6th event) |
| `rotor_position_synchronization` | 0xAF10 | Rotor position synchronization |

### Ignition timing — leading and trailing spark

The Renesis 13B-MSP uses 4 ignition coils (2 per rotor):
- **Leading spark**: first spark, near TDC
- **Trailing spark**: after leading, retarded for emissions

| Function | Address | Role |
|---|---|---|
| `ignition_timing_output_1E6B6` | 0x1E6B6 | Main ignition timing output |
| `wankel_rotary_control_1E820` | 0x1E820 | Wankel-specific control with correction |
| `ignition_timing_calc_E7F8` | 0xE7F8 | Core ignition timing calculation |
| `outputPerRotorIgnitionDwell` | 0x11218 | Per-rotor dwell output |
| `ignitionDwellOutputInit` | 0x8F62 | Hardware dwell output init |
| `ignition_advance_limiter` | 0xE38C | Ignition advance limiter |
| `adaptive_ignition_table_213D0` | 0x213D0 | Adaptive ignition table |
| `calc_ignition_all_rotors_13C2C` | 0x13C2C | Ignition calculation for both rotors |
| `ignition_timing_safety_check_1FAEA` | 0x1FAEA | Timing safety check |

**Ignition RAM:**

| Address | Role |
|---|---|
| 0xFFFFB0E8 | Filtered ignition timing |
| 0xFFFFB104 | Leading timing delta |
| 0xFFFFB108 | Trailing timing delta |
| 0xFFFFB12C | engine_ctrl_state (engine state word) |

### Fuel injection — 4 injectors

The Renesis has 4 injectors:
- **Primary**: fire into intake port (main delivery)
- **Secondary**: fire for enrichment (high load, cold start)

| Function | Address | Role |
|---|---|---|
| `sequential_fuel_injection_211DC` | 0x211DC | Sequential injection control |
| `calc_fuel_injection_all_rotors` | 0x13D3C | Injection calculation for both rotors |
| `fuel_injector_multiplexed_control` | 0x101CA | Multiplexed injector control |
| `fuel_inject_pulse_per_rotor` | 0xFBB6 | Per-rotor pulse calculation |
| `fuel_injector_pulse_calc` | 0x10620 | Core pulse length calculation |
| `rpm_limiter_fuel_cutoff` | 0xC508 | RPM fuel cutoff limiter |
| `calc_fuel_trims_adaptive` | 0x117B4 | Adaptive fuel trim |
| `calc_fuel_trim_correction_map` | 0x136F0 | Fuel trim correction map |
| `rotary_fuel_enrichment_controller` | 0x14C2C | Rotary-specific enrichment control |
| `fuel_pressure_calc_with_interpolation` | 0xE6D8 | Fuel pressure calculation |

**Fuel RAM:**

| Address | Role |
|---|---|
| 0xFFFFA73C | Rotor B injection value |
| 0xFFFFA740 | Injection enable flag |
| 0xFFFFA744 | Rotor A injection value |
| 0xFFFFA56C | fuel_cut_flag (fuel cut active) |
| 0xFFFF9F38 | Fuel rate float value |
| 0xFFFF9F96 | if_engine_run (engine running flag) |

### OMP (Oil Metering Port)

The OMP injects oil into intake ports for lubricating the rotor apex seals.

| Function | Address | Role |
|---|---|---|
| `omp_control_task_1825E` | 0x1825E | Main OMP control task |
| `omp_stepper_waveform_driver` | 0x18552 | Stepper waveform driver |
| `omp_waveform_state_machine_18860` | 0x18860 | 4-state waveform state machine |
| `rotor_sync_position_detector` | 0x189EE | Rotor sync position detector |

**OMP RAM:**

| Address | Role |
|---|---|
| 0xFFFFA968..A96C | OMP state (5 bytes) |
| 0xFFFFA97B | OMP decrement counter |
| 0xFFFF807C | OMP output register |

### Main engine cycle (10ms task)

**Function**: `main_engine_cycle_10ms` @ 0x17F1C (size 0x60)

Call chain:
```
read_prev_rotor_pair_status (0x11794)
  → idle_control_priority_task (0x1AA18)
  → priority_task_dispatch_2B070 (0x2B070)
  → main_engine_cycle_10ms (0x17F1C)  ← THIS FUNCTION
  → obd_service_handler_69624 (0x69624)
```

Timer logic:
- Counter 0xFFFFA964 increments every 10ms call (cycle 0-7)
- Subset tasks run every 80ms (counter < 8, 7/8 calls)
- OMP control runs every 10ms independently

Subset tasks (every 80ms):
1. `idle_speed_control_18054` — idle speed control
2. `fuel_pump_control_0x17510` — fuel pump relay
3. `exhaust_port_control` (0x17700) — exhaust port timing
4. `intake_air_control_0x177A6` — intake air control
5. `torque_calc_with_damping` (0x17952) — torque calculation

Always (every 10ms): `omp_control_task_1825E`

### Fuel control pipeline (28 calls)

**Function**: `main_fuel_control_pipeline_22094` @ 0x22094

Sequence:
```
Sensor Inputs → calcCLorOLControl → manifold_pressure_calc
  → sequential_fuel_injection → fuel_injection_duty_cycle
  → adaptive_ignition_table → ignition_timing_output
  → wankel_rotary_control → sensor_validation
  → combustion_control_loop → ignition_timing_safety_check
```

### Summary statistics

- Rotary-specific functions identified: 43+
- Ignition functions: 28
- Fuel injection functions: 50+
- Crank/eccentric shaft position functions: 35+
- RAM addresses identified: 45+
- Subsystems mapped: 5 (position, ignition, injection, OMP, 10ms cycle)

---

## EEPROM — External SPI Analysis (session ae00d360)

### Hardware architecture

The RX-8 ECU uses an **external SPI EEPROM chip** (NOT on-chip SH-2E).
The SPI interface is bit-banged using GPIO pins mapped through the CAN controller register space.

**KEY**: The on-chip SH-2E/SH7055 EEPROM (typically 2KB at 0xFFFFF000-0xFFFFF7FF)
is NOT used for persistent storage. All EEPROM operations go through the external SPI chip.

### SPI Register Map

| Address | Name | Role |
|---|---|---|
| 0xFFFFE401 | SPI_CLK_DATA_CTRL | Bit 0: clock out, Bit 3: transfer status |
| 0xFFFFE402 | SPI_CONTROL | SPI control register |
| 0xFFFFE404 | SPI_CONFIG | SPI configuration |
| 0xFFFFE406 | SPI_DATA_0 | SPI data register 0 |
| 0xFFFFE40A | SPI_DATA_2 | SPI data/config register 2 |
| 0xFFFFE414 | SPI_CHANNEL_CONFIG | SPI channel configuration |
| 0xFFFFE4B0 | SPI_BUFFER_0 | SPI buffer register 0 |
| 0xFFFFE4B8 | SPI_BUFFER_1 | SPI buffer register 1 |

### SPI functions

| Function | Address | Role |
|---|---|---|
| `spi_set_clk_high_wait` | 0x9C0 | Set clock HIGH, waits for transfer complete |
| `spi_set_clk_low_wait` | 0x9DE | Set clock LOW, waits for data ready |
| `spi_eeprom_read` | 0x49700 | Init SPI EEPROM read operation |
| `spi_eeprom_write` | 0x496BA | Write with wear-leveling |
| `spi_eeprom_verify` | 0x49778 | Verify EEPROM data integrity |
| `flash_program` | 0x497B0 | Flash programming with verification |
| `flash_erase` | 0x4988C | Flash block erase |
| `flash_checksum` | 0x4990C | Flash memory checksum |

### EEPROM Memory Map

**RAM staging:**

| Range | Size | Role |
|---|---|---|
| 0xFFFFC2FE–0xFFFFC3FE | 256 bytes | EEPROM data staging buffer |
| 0xFFFFC3FE–0xFFFFC4FE | 256 bytes | Inverted copy for verification |
| 0xFFFFDFE4 | 8 bytes + status | RAM buffer A (0x55=valid, 0xAA=consumed) |
| 0xFFFFDFF0 | 8 bytes + status | RAM buffer B |

**Control structures:**

| Address | Name | Role |
|---|---|---|
| 0xFFFFC297 | eeprom_busy_flag | Operation in progress |
| 0xFFFFC29B | eeprom_write_pending | Write pending |
| 0xFFFFC2D1 | eeprom_commit_request | Commit request |
| 0xFFFFC2D2 | eeprom_commit_done | Commit completed |
| 0xFFFFC2F8 | eeprom_commit_status | Status per category |

### EEPROM data categories

| Category | Offset | Size | Probable purpose |
|---|---|---|---|
| 0x01 | 0x0A | 2 | Security keys / immobilizer data |
| 0x02 | 0x02 | 8 | DTC codes |
| 0x03 | 0x00 | 2 | Configuration parameters |
| 0x04 | 0x0C | 6 | Learned values (fuel trim, etc.) |
| 0x05 | 0x12 | 2 | Security access level |
| 0x06 | 0x0E | 2 | Adaptive learning data |
| 0x07 | 0x16 | 4 | ECU identification |
| 0x09 | 0x0C | 8 | Calibration data |
| 0x0E | 0x0C | 2 | Service interval data |
| 0x0F | 0x0E | 2 | Immobilizer sync data |
| 0xFF | 0x00 | 32 | EEPROM reset/initialization |

### EEPROM commit flow

1. `diag_getsr_3920` — disables interrupts
2. Copies data to staging buffer (`eeprom_atomic_ram_copy`)
3. Saves inverted copy for verification
4. `diag_setsr_3934` — re-enables interrupts
5. Sets commit request flag (`0xFFFFC2D1 = 1`)
6. Calls `eeprom_commit_dispatcher` with category
7. Priority check (`eeprom_priority_check`)
8. Waits for completion
9. Verifies status

### Estimated EEPROM size

- Staging buffer: 256 bytes
- Verification buffer: 256 bytes
- Control structures: ~100 bytes
- **Estimated size**: 256 bytes (ABLIC S-93C56C)

### Wear leveling

- Counter 0xFFFFCCF8 increments on every write
- Resets to 0 when write is not permitted
- Suggests wear-leveling across multiple EEPROM blocks

---

## DTC (Diagnostic Trouble Codes) — Complete Analysis

### Format and storage

**Primary table**: 21 entries × 52 bytes (stride 0x34) at `0xFFFF8928`
- Slot counter at `0xFFFF8D6C` (byte)
- 52-byte record layout (verified from `obd_service_handler_6459C`):
  - `+0x00`: internal DTC code (word, 0x02–0x4C)
  - `+0x06`: status byte (bit 7=confirmed, bit 6=failed)
  - `+0x07`: severity (0x80=confirmed, 0xC0=confirmed+failed)
  - `+0x0A`: freeze-frame / snapshot (40 bytes of sensor data)

**Backup table**: 8 entries × 40 bytes (stride 0x28) at `0xFFFF8EA0`
- Counter at `0xFFFF8FB8` (word)
- 40-byte record: DTC code +0x00, validity marker 0xA7 at +0x27
- Empty slots: 0xFFFF at +0x00 and +0x20

**Handler context table**: 21 entries × 16 bytes (stride 0x10) at `0xFFFF87D8`
- Region checksum: guards `0xFFFF8920/0x8924`, 15-byte sum per entry = 0xA5

**Severity lookup**: ROM table at `0x7E2AC` (32 bytes), indices 6–7 disabled, rest enabled.

### DTC codes

Internal codes (0x02–0x4C) are mapped to OBD P-codes via dispatch table at `0x5F7F8`: pairs `(DTC_code, severity)`, stride 2 bytes, 28 total types (severity 1=low, 2=high). Terminator 0xFF.

### SET path (fault detection)

```
fault condition detection (0x271B8 / 0x2817C / 0x28E10)
  → detection gate (0x25E36)
  → debounce counter (0x43760: configurable thresholds)
  → dtc_set_flag (0x46780): checks enable flag [0xFFFF8788]==1,
    writes set flag to [0xFFFF875C], clears [0xFFFF875E]
  → dtc_freezeframe_store (0x467BE): captures snapshot at +0x0A of record
  → dtc_state_machine (0x61550): state transitions (set/confirm/clear/aging)
  → obd_service_handler_63814: persists state change in RAM table
```

### CLEAR path (SID 0x14 → `obd_sid14_clearDTC` @ `0x562E8`)

- Scanner sends `[SID=0x14][group_hi][group_lo]`
- Group `0xFF00` = clears ALL DTCs
- Other → NRC 0x31 (requestOutofRange)
- Sequence: `obd_service_handler_68BC0` → compares `0xFF00` → `histogram_0x563CE` (reset) → confirms → positive response
- Low-level clear: `dtc_clear_flag` (0x467AA) clears 0xFFFF875C/0x875E

### READ path (SID 0x18 → `obd_sid18_readDTCInfo` @ `0x587EC`)

- Sub-function `0x03`: reportNumberOfDTCByStatusMask → DTC count by status mask
- Sub-function `0xFF` (mask 0x00): clear-then-report
- `dtc_find_worst_priority` (0x6115A): iterates 20 slots, compares severity (lower byte = higher priority), returns worst code + severity + status
- SID 0x12 (`0x5BAD0`): readDTCByStatusMask — sub 2/4, encodes DTC list via `writeDTCCodeType` (0x5BD2E)

### Freeze-frame / Snapshot

- `dtc_snapshot_manager` (0x3B3BC): captures RPM (0xFFFFB5B8 float), MAP, coolant temperature, other sensors
- Store in 0xFFFFC5C4, 0xFFFFC5B6, 0xFFFFC12C
- OBD Mode 0x02: handler 0x0666C4, reads freeze-frame from +0x0A of 52-byte record

### EEPROM

- External chip: **ABLIC S-93C56C**, 256 bytes via SPI bit-bang (GPIO)
- Shadow RAM: `0xFFFFC000` (256 bytes, copied at boot)
- Staging buffer: `0xFFFFC2FE–0xFFFFC3FE`
- Boot: EEPROM 256B → RAM, region validators verify checksum (sum == 0xA5), invalid regions → reinitialize from defaults
- DTC write path: RAM staging → EEPROM staging → SPI write → verify

### Managed RAM

| Address | Role |
|---|---|
| 0xFFFF875C / 0xFFFF875E | Set/clear flag pair |
| 0xFFFF876C | Clear fault logger flag |
| 0xFFFF8788 | DTC enable flag (redundant checksum) |
| 0xFFFF87A0 | Fault counter (redundant pair) |
| 0xFFFF87B4 | DTC processing lock |
| 0xFFFF8920 | Current active DTC code |
| 0xFFFF8D70 | Current DTC slot index |
| 0xFFFFD7CC | Sub-handler state buffer |
| 0xFFFFD6D0 | Encoded output buffer |
| 0xFFFFD6C8 | DTC read buffer (8 bytes) |
| 0xFFFFC9DC–0xFFFFC9E1 | DTC event flags (CAN SID 0x1B trigger) |

### Renamed functions

78 functions renamed in the DTC subsystem: 24 core infrastructure, 5 set/clear, 11 monitor, 10 fault-specific, 10 additional. See `tmp/ida/dtc_analysis_report.txt` for the full table.

---

## RAM import — Results (session ae00d360)

From `symbols/RAM_VARIABLES.csv` (1613 addresses):
- Importable (RAM+Periph): 1569
- Skipped (unmapped gap): 44 (range 0xFFFF0000–0xFFFF5FFF)
- Pre-existing collisions: 404
- **New imports this session: 1165**
- **Total globals in IDA now: 2028** (range 0xFFFF6000–0xFFFFFFFF)

Method: all new symbols created as `unsigned char` (1 byte).
Spot-check verification: 0xFFFFDFA0 flag_gate ✓, 0xFFFFDFB8 ram_dfb8 ✓, 0xFFFFDFFC warm_boot_magic ✓.
