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
| 0x215 | counter-gated (0x2A242) | — (forwards CAN_TX_BUF_0215, packs no bytes) | MB3 (CAN0 TX cfg 0x4EA60, see CAN_PROTOCOL.md) | Throttle position (byte layout OPEN) |
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
| 0x7DF | `can_msg_parse_4657C` → `can_to_uds_bridge` | — | CAN0 | UDS broadcast request (response on 0x7E8; see CAN_PROTOCOL.md) |
| 0x7E0 | `can_msg_parse_4657C` → `can_to_uds_bridge` | — | CAN0 | UDS request → udsHandler |

### CAN → UDS Bridge (fully verified path)

```
CAN0 0x7E0 arrives
  → secondary_system_controller (0xDE8E)
      reads CAN data via placeCANRX
  → can_msg_parse_4657C (0x4657C)
      checks: active OBD session (obd_service_handler_6743C)
              CAN state [0xFFFFCD02]==1
              CAN enable [0xFFFFA110]==1
      monitors counter [0xFFFFCC36] vs ROM 0x7C396
      if conditions OK:
  → can_to_uds_bridge (0x60774)  r4=0x67 (SID), r5=1/2
  → uds_task_entry (0x696DC) → udsHandler (0x697E8)
  → response → CAN0 0x7E8 → can_tx_send_frame → HW transmission
```

### CAN Init

`canSetup` (0xDC8C): iterates CAN0/CAN1. Uses primary config table 0x4EA60 or
alternate 0x4EB60 (when [0xB5A4]==0). Calls `CANControllerSetup` (0x9878) for
each controller: enables mailbox interrupts, inits IRQ mask, sets mode/DLC,
pointer control, ID mode. Sets `[0xFFFFA410]=1` when both controllers are ready.

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

## RTOS — Cooperative Scheduler (session ae00d360)

The system is a **cooperative (non-preemptive) RTOS**: tasks run to completion.
Interrupts post to the task queue; they do not dispatch directly.

**4 priority levels:**

| Level | Bits | Role |
|---|---|---|
| 3 (maximum) | 0x60 | Critical engine control |
| 2 | 0x40 | Timing / sensor processing |
| 1 | 0x20 | I/O and communication |
| 0 (minimum) | 0x00 | Background tasks |

**Boot chain:**
```
resetHandler → secondary_boot_main → task_context_switch(0) → RTOS_init_entry (0x3E10)
  → task_queue_init (0x3964), task_table_scan_init (0x3EC0),
    task_dependency_handler (0x3F10), task_full_context_save → schedule
```

**Task queue:** 100 entries × 8 bytes at `0xFFFFD4E0`, write/read index at `0xFFFFDFB4`/`0xFFFFDFB6`.
Entry: `{source_byte, command_type, payload[6]}` — dispatched on `command_type & 0xF8`.

**Main loop** (`main_task_dispatcher` 0x6C8): loops `task_scheduler_dispatch` → `task_queue_pending_count` → `task_queue_get_next` → dispatch → `watchdogTimerRead`.

**Task table ROM** (`0x6873C`): 8-byte entries `{marker:2, args:2, func:4}`. Marker `0xFFFF` = direct call; otherwise dispatcher 0x5F34.

**Context switch**: `task_context_switch` (0x3AD8) saves SR/PR, stores SP → `[0xFFFF72D8]`; `task_full_context_save` (0x3BF4) saves r5/r8-r12/GBR/r13-MACH/r14-MACL + fr12-fr15 if type==4.

Full report: `tmp/ida/rtos_analysis_report.txt`

## Serial — ATU-based Protocol (session ae00d360)

**Primary physical bus:** ATU (Advanced Timer Unit) — timer-based serial, bit-banged or capture/compare. Registers: `0xFFFFE4xx` (custom peripheral). Baud rate configured at runtime via ATU timer settings (probably 10400 for ISO 9141).

**Secondary bus:** SCI4 — 115200/57600 baud, 8N1, used for flash programming or debug.

**Three logical channels** (sharing ATU hardware):

| Code | Handler | RX Buffer | Likely use |
|---|---|---|---|
| 0x88 | `serial_rx_handler_ch0` | 0xFEC | OBD/ISO 9141 (scan tool) |
| 0x90 | `serial_rx_handler_ch1` | 0xFF8 | Instrument cluster / sub-ECU |
| 0xC0 | `serial_rx_handler_ch2` | 0xFE4 | Body control / other |

**Frame format:** `[source][length][payload...]` with sync `0xAA` / ACK `0x55`.

**Dispatch**: `serial_dispatch` (0x338) → direct path (hw register write) if queue idle, otherwise queue path (`serial_queue_message` 0x47C) if busy.

Full report: `tmp/ida/serial_analysis_report.txt`

## Engine Control — 13B-MSP Rotary (session ae00d360)

The Renesis 13B-MSP is a 2-rotor rotary engine with:
- **Eccentric shaft position:** 20-tooth trigger wheel (3×6+1) with sync gap
- **Ignition:** 4 coils (2 per rotor) — leading + trailing spark
- **Fuel injection:** 4 injectors — primary (delivery) + secondary (enrichment)
- **OMP:** Oil Metering Port for apex seal lubrication

**10ms cycle** (`main_engine_cycle_10ms` 0x17F1C):
- Every 80ms (7/8 calls): idle speed, fuel pump, exhaust port, intake air, torque
- Every 10ms: OMP control (`omp_control_task_1825E`)

**Fuel pipeline** (`main_fuel_control_pipeline_22094`): 28 calls in sequence:
```
Sensors → calcCLorOLControl → manifold_pressure → sequential_fuel_injection
  → fuel_injection_duty_cycle → adaptive_ignition_table → ignition_timing_output
  → wankel_rotary_control → sensor_validation → combustion_control_loop
  → ignition_timing_safety_check
```

**Functions identified:** 141+ (43 rotary, 28 ignition, 50+ fuel injection, 35 crank/rotor).

Full report: `tmp/ida/engine_rotary_report.txt`

## EEPROM — External SPI (session ae00d360)

The ECU uses an **external SPI EEPROM chip** (NOT on-chip SH-2E). **SH-side SPI driver: NOT-FOUND** — `0xFFFFE4xx` is HCAN/ATU register space (not SPI GPIO); the clock helpers are init-only and the alleged SPI ops are RAM-only. The 93C56 is likely fed by the Denso companion ASIC; SH-side CS pin unknown. Bench probe of SOIC8 IC420 required (see FINDINGS.md 2026-09-08 firmware ROM-check resolution, commit 61c5780; KNOWLEDGE.md EEPROM Shadow).

**Staging buffers:**
- `0xFFFFC2FE`: 256 bytes EEPROM data staging
- `0xFFFFC3FE`: 256 bytes inverted copy for verification
- `0xFFFFDFE4`: RAM buffer A (8B + 0x55/0xAA status)
- `0xFFFFDFF0`: RAM buffer B

**Data categories** (16, dispatcher `0x37000`): security keys (0x01), DTC (0x02), config (0x03), fuel trim (0x04), adaptive learning (0x06), immobilizer (0x0E/0x0F).

**Commit flow:** disable interrupts → copy to staging → store inverted → re-enable → flag commit → dispatcher → priority check → verify.

**Size:** 256 B (ABLIC S-93C56C). Wear leveling via counter 0xFFFFCCF8.

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