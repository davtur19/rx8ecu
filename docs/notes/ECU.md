# RX-8 ECU — Notes

Active RE work. Non-discoverable facts: `KNOWLEDGE.md`. Confirmed discoveries: `FINDINGS.md`.

## Launch-Control Patch

**Code cave**: `0x6C7FE–0x6CBFA` — stock = all `0xFF`; a tuned variant injects SH-2E code here.

**Hook at `0x94C8`** (`LC_HookClampEntry`): 16 bytes changed → redirects stock throttle clamp to `LC_ClampAndGateOutput`.

**Patch at `0x35BBC`** (`LC_GateWrapper`): jump → `LC_GateCondition_RPMLoad` at `0x6CA80`.

ROM immobilizer at `0x35D90` — **unchanged** between stock and tuned. No-start = EEPROM data, not ROM immo.

### Two separate control paths

**Path A — CAN launch signal** (not the kill):
```
LC_GateWrapper (0x35BBC)
  → LC_GateCondition_RPMLoad (0x6CA80)   [MAP > 10 kPa AND RPM > 5250]
  → LC_SetStatusBit0400 (0x35BF2)         [sets bit 0x0400 in 0xFFFFF754]
  → CAN_EmitLaunchStatus (0x57BE8)        [broadcasts launch-active on CAN]
```

**Path B — engine kill**:
```
LC_HookClampEntry (0x94C8)
  → LC_ClampAndGateOutput (0x6C88C)
  → LC_ValidateChecksum17 (0x6CB44)       [reads 17 bytes @ RAM 0xFFFFC37E–0xFFFFC38E]
```
Wrong ECU → checksum fails (sum ≠ −23) → output forced to 0 → throttle = 0 → stall.

### LC activation (correct ECU)
- Clutch IN (`0xFFFFC004` bit 0, EEPROM-derived) + throttle > 70% → LC arms
- RPM targets: 5100 (stationary), 8300 (rolling < 9 km/h), 9300 (full active)

### Inject into stock
Private injector `tools/<lc_patch>.py` (**not shipped**) injects the cave code into `60E1D400.bin`, NOPs out `LC_ValidateChecksum17`, fixes checksum.

## Ghidra Function Labels

| Address | Name |
|---|---|
| `0x6C800` | `LC_SelectTargetRpm` |
| `0x6C88C` | `LC_ClampAndGateOutput` |
| `0x6CB44` | `LC_ValidateChecksum17` |
| `0x6CA80` | `LC_GateCondition_RPMLoad` |
| `0x94C8`  | `LC_HookClampEntry` |
| `0x35BF2` | `LC_SetStatusBit0400` |
| `0x35BBC` | `LC_GateWrapper` |
| `0x4BBC`  | `BitSetClear_Helper` |
| `0x57BE8` | `CAN_EmitLaunchStatus` |
| `0x583E4` | `memory_match_accumulate_583E4` |
| `0x5846A` | `CAN_WriteChannel` |

## RAM Labels

| Address | Label | Notes |
|---|---|---|
| `0xFFFFC37E` | `LC_ChecksumWindow_Start` | First of 17 EEPROM bytes; signed sum = −23 |
| `0xFFFFF754` | `LC_StatusWord_F754` | Bit `0x0400` = launch active |
| `0xFFFFB770` | `LC_RPM_TargetFloat` | Output of LC_SelectTargetRpm |
| `0xFFFFB774` | `LC_StateByte` | Hysteresis (0=off, 1=active) |
| `0xFFFFAA40` | `MAP_kPa_Float` | MAP sensor kPa (float) |
| `0xFFFFB5B8` | `RPM_Float_B5B8` | Engine RPM float; threshold 5250 |
| `0xFFFFC004` | `EEPROM_PairingByte` | Non-zero = paired |
| `0xFFFFA0D4` | (throttle) | ETB commanded throttle angle, uint16 0–65535 |

## CAN Subsystem — Full Reverse Engineering (2026-09-05)

Two buses: HS-CAN (CAN0, OBD-II pins 6/14) and MS-CAN (CAN1, pins 3/11).

### CAN TX Path

`CANTX_Main` (0xDDF0) — periodic, gate-controlled by 6 RAM flags:
- `[0xA40F]<100`, `[0xA40A]==0`, `[0xA410]==0`, `[0xA411]==0`, `[0xAAE0]==1`, `[0xB5E8]!=1`

All TX pack functions follow the same pattern:
1. Read computed values from RAM staging area
2. Pack bytes into local 8-byte buffer
3. JMP to `can_tx_send_frame` (0x9AE4) — tail call with mailbox config table entry

`can_tx_send_frame` (0x9AE4): disables interrupts, resolves mailbox via
`can_get_mailbox_offset_high`, writes CAN ID to mailbox, copies data via
`eeprom_write_verify_bytes`, sets ready bit, restores interrupts.

### CAN TX ID → Handler Map (Verified)

| CAN ID | Rate Limiter | Pack Function | Config Table | Target |
|---|---|---|---|---|
| 0x041 | (direct) | `can41TXPack` (0x39348) | dword_4E9F0 | KCM/Immobiliser response |
| 0x201 | every 4 cycles | `can_tx_rate_limit_0x201` (0x29FD2) | dword_4E930 | Engine torque |
| 0x203 | every 4 cycles | `can_tx_rate_limit_0x203` → `can203pack` (0x2A274) | dword_4E970 | Engine status |
| 0x231 | every 4 cycles | `can_tx_rate_limit_0x231` → `canPackandTx231` (0x2D434) | dword_4E990 | Torque request (conditional [0xB5A4]==1) |
| 0x240 | every 25 cycles | `can_tx_rate_limit_0x240` → `can240TX_pack` (0x4C888) | dword_4EA00 | OBD data |
| 0x250 | every 25 cycles | `can_tx_rate_limit_0x250` → `can250TX_pack` (0x4C984) | dword_4EA10 | OBD data |
| 0x251 | every 2 cycles | `can251TX_getAndPack` (0x2AAB6) | — | Engine data |
| 0x420 | (direct) | `can420TXPack` (0x29A0C) | dword_4E9B0 | Coolant/MIL |
| 0x620 | every 25 cycles | `can_tx_rate_limit_0x620` → `can620TX_pack` (0x33A68) | dword_4E9D0 | TCM data |
| 0x630 | every 25 cycles | `can_tx_rate_limit_0x630` → `can630TX_dispatch` (0x33974) | dword_4E9E0 | TCM data |
| 0x650 | every 12 cycles | `can650TX_getAndPack` (0x2C806) | — | Cluster data |

### CAN RX Path

`secondary_system_controller` (0xDE8E) — gate: `[0xAAE0]==1`, `[0xB5E8]!=1`, `[0xA410]==0`.
Dispatches RX handlers; all use `placeCANRX` (0x99C4) which reads HW mailbox via
PFC 0xFFFFE40E/0xFFFFE41A, retries up to 5x, copies data via `can_pack_tx_msg_copy`.

| CAN ID | Handler | Unpack Function | Bus | Notes |
|---|---|---|---|---|
| 0x047 | `can47RX_Main` (0x3939C) | — | CAN1 | KCM/immobiliser request |
| 0x212 | `CAN212RX_Main` (0x2C0C4) | `can212RXUnpack` (0x2C60A) | CAN1 | ABS/DSC/brake lamps |
| 0x216 | timeout check | `incr_counter_saturated_299DA` | CAN1 | Brake data timeout |
| 0x430 | `can430_4C0RX_dispatch` (0x33BA0) | — | CAN1 | Cluster presence |
| 0x4B0 | `loc_2BE18` | `can4B0RX_unpack` (0x2BE6E) | CAN1 | DSC wheel speeds |
| 0x4B1 | `can4B1RX_event_check` (0x4C78C) | — | CAN1 | DSC request |
| 0x4C0 | `can4C0RX_short` (0x2C780) | — | CAN1 | Short message |
| 0x7E0 | `can_msg_parse_4657C` → `can_to_uds_bridge` | — | CAN0 | UDS request → udsHandler |

### CAN → UDS Bridge (path completo verificato)

```
CAN0 0x7E0 arriva
  → secondary_system_controller (0xDE8E)
      legge dati CAN via placeCANRX
  → can_msg_parse_4657C (0x4657C)
      checks: sessione OBD attiva (obd_service_handler_6743C)
              stato CAN [0xFFFFCD02]==1
              enable CAN [0xFFFFA110]==1
      monitora contatore [0xFFFFCC36] vs ROM 0x7C396
      se condizioni OK:
  → can_to_uds_bridge (0x60774)  r4=0x67 (SID), r5=1/2
  → uds_task_entry (0x696DC) → udsHandler (0x697E8)
  → risposta → CAN0 0x7E8 → can_tx_send_frame → trasmissione HW
```

### CAN Init

`canSetup` (0xDC8C): itera CAN0/CAN1. Usa tabella config primaria 0x4EA60 o
alternativa 0x4EB60 (quando [0xB5A4]==0). Chiama `CANControllerSetup` (0x9878) per
ogni controller: abilita mailbox interrupts, init IRQ mask, imposta mode/DLC,
pointer control, ID mode. Set `[0xFFFFA410]=1` quando entrambi i controller pronti.

### RAM Gate Flags

| Address | Purpose |
|---|---|
| 0xFFFFA40F | Boot counter (must be <100 for CANTX_Main) |
| 0xFFFFA40A | Must be 0 for CANTX_Main |
| 0xFFFFA410 | CAN0 init complete (set by canSetup) |
| 0xFFFFA411 | CAN1 init complete |
| 0xFFFFAAE0 | System enable (must be 1 for TX+RX) |
| 0xFFFFB5E8 | Inhibit (must be !=1 for TX+RX) |
| 0xFFFFC241 | TX gate (cleared at end of CANTX_Main) |

### ROM Config Tables

| Address | Entries | Description |
|---|---|---|
| 0x4EA60 | 16×16B | CAN0 TX mailbox config (primary) |
| 0x4EB60 | 16×16B | CAN0 TX mailbox config (alternate, [0xB5A4]==0) |
| 0x4EC60 | 6×16B | CAN1 RX mailbox config |

### Low-Level CAN Helpers

| Address | Name | Purpose |
|---|---|---|
| 0xD198 | `getHCANRegAddr` | PFC base + offset → HCAN register |
| 0xD164 | `can_get_mailbox_offset_high` | Read mailbox status/offset |
| 0xD1AC | `can_get_mailbox_config` | Get mailbox config word |
| 0xCC6C | `can_enable_mailbox_int` | Enable per-mailbox interrupt |
| 0xCD12 | `can_init_mailbox_irq_mask` | Init IRQ mask register |
| 0xCDC4 | `can_set_mailbox_mode_dlc` | Set mode + DLC |
| 0xCDF0 | `can_set_mailbox_ptr_control` | Set pointer + flow control |
| 0xCE34 | `can_set_mailbox_id_mode` | Set ID acceptance mode |
| 0xCC9C | `setCANRegisters` | Write config entry to HW regs |
| 0xCF42 | `can_pack_tx_msg_write_verify` | Actual CAN HW write |
| 0x3920 | `diag_getsr_3920` | Disable interrupts, save SR |
| 0x3934 | `diag_setsr_3934` | Restore SR |

### Immo/CAN Interaction

`immo_state_machine_entry` (0x35D62): 6-state FSM (0=defaults, 1=waiting,
2=key-seen, 3=timer, 4=valid→sets [0xA40F]=100, 5=invalid). Calls
`ImmoGetCANData` (0x36870) reads 0xFFFFC238..C23F, `setImmoCANTXData` (0x369B8)
writes back for TX.

Full report: `tmp/ida/can_analysis_report.txt`

## RTOS — Cooperative Scheduler (sessione ae00d360)

Il sistema è un **RTOS cooperativo (non preemptive)**: i task girano fino al completamento.
Le interruzioni postano nella coda task, non eseguono dispatch diretto.

**4 livelli di priorità:**

| Livello | Bits | Ruolo |
|---|---|---|
| 3 (massimo) | 0x60 | Engine control critico |
| 2 | 0x40 | Timing / elaborazione sensori |
| 1 | 0x20 | I/O e comunicazione |
| 0 (minimo) | 0x00 | Task di background |

**Catena di avvio:**
```
resetHandler → secondary_boot_main → task_context_switch(0) → RTOS_init_entry (0x3E10)
  → task_queue_init (0x3964), task_table_scan_init (0x3EC0),
    task_dependency_handler (0x3F10), task_full_context_save → schedule
```

**Task queue:** 100 entry × 8 byte a `0xFFFFD4E0`, write/read index a `0xFFFFDFB4`/`0xFFFFDFB6`.
Entry: `{source_byte, command_type, payload[6]}` — dispatch su `command_type & 0xF8`.

**Main loop** (`main_task_dispatcher` 0x6C8): cicla `task_scheduler_dispatch` → `task_queue_pending_count` → `task_queue_get_next` → dispatch → `watchdogTimerRead`.

**Task table ROM** (`0x6873C`): entry a 8 byte `{marker:2, args:2, func:4}`. Marker `0xFFFF` = chiamata diretta; altrimenti dispatcher 0x5F34.

**Context switch**: `task_context_switch` (0x3AD8) salva SR/PR, store SP → `[0xFFFF72D8]`; `task_full_context_save` (0x3BF4) salva r5/r8-r12/GBR/r13-MACH/r14-MACL + fr12-fr15 se type==4.

Full report: `tmp/ida/rtos_analysis_report.txt`

## Seriale — Protocollo ATU-based (sessione ae00d360)

**Bus fisico primario:** ATU (Advanced Timer Unit) — timer-based serial, bit-banged o capture/compare. Registri: `0xFFFFE4xx` (periferica custom). Baud rate configurato a runtime via ATU timer settings (probabilmente 10400 per ISO 9141).

**Bus secondario:** SCI4 — 115200/57600 baud, 8N1, usato per flash programming o debug.

**Tre canali logici** (condividono hardware ATU):

| Codice | Handler | Buffer RX | Uso probabile |
|---|---|---|---|
| 0x88 | `serial_rx_handler_ch0` | 0xFEC | OBD/ISO 9141 (scan tool) |
| 0x90 | `serial_rx_handler_ch1` | 0xFF8 | Instrument cluster / sub-ECU |
| 0xC0 | `serial_rx_handler_ch2` | 0xFE4 | Body control / altro |

**Frame format:** `[source][length][payload...]` con sync `0xAA` / ACK `0x55`.

**Dispatch**: `serial_dispatch` (0x338) → direct path (hw register write) se queue idle, oppure queue path (`serial_queue_message` 0x47C) se busy.

Full report: `tmp/ida/serial_analysis_report.txt`

## Engine Control — Rotario 13B-MSP (sessione ae00d360)

Il Renesis 13B-MSP è un motore rotario a 2 rotori con:
- **Posizione eccentric shaft:** ruota trigger 20 denti (3×6+1) con gap sync
- **Accensione:** 4 bobine (2 per rotore) — leading + trailing spark
- **Iniezione:** 4 iniettori — primary (erogazione) + secondary (arricchimento)
- **OMP:** Oil Metering Port per lubrificazione anelli apicali

**Ciclo 10ms** (`main_engine_cycle_10ms` 0x17F1C):
- Ogni 80ms (7/8 chiamate): idle speed, fuel pump, exhaust port, intake air, torque
- Ogni 10ms: OMP control (`omp_control_task_1825E`)

**Fuel pipeline** (`main_fuel_control_pipeline_22094`): 28 chiamate in sequenza:
```
Sensori → calcCLorOLControl → manifold_pressure → sequential_fuel_injection
  → fuel_injection_duty_cycle → adaptive_ignition_table → ignition_timing_output
  → wankel_rotary_control → sensor_validation → combustion_control_loop
  → ignition_timing_safety_check
```

**Funzioni identificate:** 141+ (43 rotary, 28 ignition, 50+ fuel injection, 35 crank/rotor).

Full report: `tmp/ida/engine_rotary_report.txt`

## EEPROM — SPI Esterno (sessione ae00d360)

L'ECU usa un **chip EEPROM SPI esterno** (NON on-chip SH-2E). Interfaccia SPI bit-banged via GPIO through CAN controller register space (`0xFFFFE4xx`).

**Staging buffers:**
- `0xFFFFC2FE`: 256 byte EEPROM data staging
- `0xFFFFC3FE`: 256 byte copia invertita per verifica
- `0xFFFFDFE4`: RAM buffer A (8B + 0x55/0xAA status)
- `0xFFFFDFF0`: RAM buffer B

**Data categories** (16, dispatcher `0x37000`): security keys (0x01), DTC (0x02), config (0x03), fuel trim (0x04), adaptive learning (0x06), immobilizer (0x0E/0x0F).

**Commit flow:** disabilita interrupts → copia a staging → store invertito → riabilita → flag commit → dispatcher → priority check → verifica.

**Dimensione stimata:** 2-4 KB. Wear leveling via contatore 0xFFFFCCF8.

Full report: `tmp/ida/eeprom_analysis_report.txt`

## Open Investigation Items

1. **Boot initializer for `0xFFFFC37E`**: what function copies EEPROM → RAM at that offset? Not found.
2. **`0x8F62` = `ignitionDwellOutputInit`** (verified: ignition-dwell chain; tail-calls `getIgnitionDwellTime`@0x94C8). Dwell PWM init.
3. **0x7FFF4 second checksum**: algorithm unknown; NOT verified at ECU runtime — low priority.
4. **Live-ECU full function map**: CAN table located, most functions unnamed.
5. **Modified stock functions outside cave**: `0x1038`, `0x109C`, `0x121F0`, `0x1237C` — roles not fully confirmed.

## DENSO Checksum

Additive sum of BE dwords over ROM range. Descriptor @`0x7FB80`: `[lo_addr:4][hi_addr:4][diff:4]` — range lo=`0x2000`, hi=`0x7DAFF`; target = `sum + diff = 0x5AA5A55A`; diff stored @`0x7FB88`.

Second word @`0x7FFF4`: different algo, unknown, NOT verified at runtime — ignore.

Tool: `python tools/denso_ck.py <rom.bin>` (verify) / `-f` (fix in-place) / `-o <out>` (fix to copy).