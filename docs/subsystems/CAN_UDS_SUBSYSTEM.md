# CAN/UDS Subsystem — RX-8 ECU (60E1D400)

Multi-layered CAN (Controller Area Network) + UDS (ISO-14229-1) subsystem, ~149 functions.

- **Two CAN buses**: HS-CAN (diagnostics, UDS) and MS-CAN (accessories)
- **Proprietary broadcast**: CAN IDs 0x201–0x650 carry engine data
- **UDS/ISO-14229-1**: via KWP2000 serial and CAN (0x7DF/0x7E0/0x7E8)
- **OBD-II (ISO-15031)**: emissions diagnostics (SIDs under 0x10)
- **DTC handling**: storage, retrieval, clearing (EEPROM)

```
Layer 3  UDS/OBD Services    udsHandler, UDSMode*, obd_service_handler*, DTC handlers
Layer 2  CAN Message Layer   CANTX_Main (0xDDF0), secondary_system_controller (0xDE8E), filters
Layer 1  CAN HW Interface    CANControllerSetup, mailbox/register access
Layer 0  SH7055 HCAN         16 mailboxes, regs @0xFFFFC000-0xFFFFCFFF
```

## CAN Mailbox Configuration Tables (60E1D400)

Dispatch table (0x4E728 in J-line) maps to three **mailbox config** tables (16-byte entries: CAN ID, DLC, direction, buffer address):

- **CAN0 TX Primary**: `0x4EA60` (16 entries, used when `0xB5A4 == 1`)
- **CAN0 TX Alternate**: `0x4EB60` (16 entries, used when `0xB5A4 == 0`)
- **CAN1 RX**: `0x4EC60` (6 entries)

The 16-byte "handler" field is a **mailbox data buffer pointer** (into HCAN reg space 0xFFFFExxx), NOT a function pointer. Runtime dispatch is direct calls in `CANTX_Main`/`secondary_system_controller`.

### CAN0 TX Mailbox Map

| # | CAN ID | MB | DLC | Dir | Buffer | Description |
|---|--------|-----|-----|-----|--------|-------------|
| 0 | 0x0201 | 1 | 8 | TX | 0x01BB5C | Wheel speed (FR/FL/RR/RL × u16) |
| 1 | 0x0203 | 2 | 7 | TX | 0x01BB78 | Engine torque / status |
| 2 | 0x0215 | 3 | 8 | TX | 0x01BB9C | Throttle position |
| 3 | 0x0231 | 4 | 5 | TX | 0x01BCC4 | Engine data (RPM, load, coolant) |
| 4 | 0x0231 | 4 | 5 | TX | 0x01BB48 | Engine data (alt format) |
| 5 | 0x0420 | 5 | 7 | TX | 0x01BB0C | Battery voltage |
| 6 | 0x0620 | 6 | 7 | TX | 0x01C054 | Fan / AC status |
| 7 | 0x0630 | 7 | 8 | TX | 0x01C044 | Cooling fan data |
| 8 | 0x0650 | 8 | 1 | TX | 0x01BC68 | Catalyst / O2 trim |
| 9 | 0x0041 | 9 | 8 | TX | 0x01C518 | AC request / alternator |
| 10 | 0x0240 | 10 | 8 | TX | 0x01CEA4 | Transmission / gear |
| 11 | 0x0250 | 11 | 8 | TX | 0x01CEB8 | Injection pulse width |
| 12 | 0x04B1 | 12 | 8 | TX | 0x01CE90 | DSC request |
| 13 | 0x07DF | 13 | 8 | RX | 0x00DE04 | UDS broadcast request |
| 14 | 0x07E0 | 14 | 8 | RX | 0x00DE04 | UDS physical request |
| 15 | 0x07E8 | 15 | 8 | TX | 0x00DE0C | UDS response |

### CAN1 RX Mailbox Map

| # | CAN ID | MB | DLC | Dir | Buffer | Description |
|---|--------|-----|-----|-----|--------|-------------|
| 0 | 0x0212 | 1 | 7 | RX | 0x01BC28 | Unknown |
| 1 | 0x0216 | 2 | 8 | RX | 0x01BB20 | Unknown |
| 2 | 0x0430 | 4 | 7 | RX | 0x01C060 | Immobilizer / security |
| 3 | 0x04B0 | 5 | 8 | RX | 0x01BC08 | DSC/ESP data |
| 4 | 0x04C0 | 6 | 1 | RX | 0x01BC64 | Short message |
| 5 | 0x0047 | 7 | 8 | RX | 0x01C520 | Steering angle sensor |

## HCAN Hardware (Layer 0)

SH7055 built-in HCAN: 16 mailboxes (0–7 usually RX, 8–15 usually TX), standard (11-bit) + extended (29-bit) IDs. Key regs (via `getHCANRegisterAddress` 0xD198): `MCR`, `MBCR`, `M_BOCR`, `M_BIDR`, `M_BDSR`.

## CAN Hardware Interface (Layer 1)

```
main_init → canSetup (0xDC8C) → CANControllerSetup (0x9878)
                                → canMessageSetup (0x2B320)
                                → canInitVals (0x2AFC8)
                                → hcan_init_and_status_check (0xD6A0)
```

**`CANControllerSetup`** (0x9878): full HCAN init — configure TX/RX pins, release HCAN reset (MCR), baud prescaler (`set_MCR_bits2_3`, `set_MCR_bits5_7`), configure all 16 mailboxes (`setCANRegisters`), RX masks, mailbox interrupts.

**`canMessageSetup`** (0x2B320): post-init — periodic TX timing, RX filters by CAN ID, message counters/timeouts.

### Mailbox Operations

| Function | Address | Purpose |
|----------|---------|---------|
| can_set_mailbox_mode_dlc | 0xCDC4 | Set mailbox mode + DLC |
| can_set_mailbox_ptr_control | 0xCDFA | Set mailbox buffer pointer |
| can_set_mailbox_id_mode | 0xCE34 | Set CAN ID and format (std/ext) |
| can_set_mailbox_rx_id | 0xCF90 | Set RX acceptance filter ID |
| can_enable_mailbox_int | 0xCC6C | Enable mailbox interrupt |
| can_disable_mailbox_int | 0xCC84 | Disable mailbox interrupt |
| can_get_rx_pending_flags | 0xD0C0 | Read RX pending flags (MPR) |
| can_get_tx_acknowledge_flags | 0xD112 | Read TX acknowledge flags (MTACKR) |
| baro_sensor_value | 0xD144 | Barometric sensor value (formerly `can_clear_tx_acknowledge`) |
| can_mailbox_read_data | 0xCFD4 | Read raw data from mailbox |
| can_mailbox_extract_msg_data | 0xCFF6 | Extract/format message from buffer |
| can_pack_tx_msg_copy | 0xCEF4 | Copy data into TX mailbox |
| can_pack_tx_msg_write_verify | 0xCF42 | Write + verify TX data integrity |
| can_tx_abort_and_retry | 0x9CC6 | Abort TX, re-send on failure |
| can_register_read_write | 0x9DD8 | Low-level register R/W wrapper |

## TX Path (Layer 2)

### `CANTX_Main` (0xDDF0) — master TX dispatch (VERIFIED)

```
1. counter @0xFFFFA40F >= 100 (0x64) → skip cycle
2. flags @0xA40A, 0xFFFFA410, 0xFFFFA411 set → skip
3. 0xAAE0 == 1 AND 0xB5E8 != 1 → allow TX
4. sequential TX calls (counter-based rate limiting):
   can41TXPack (0x39348)                        - 0x041 (AC)
   FUN_00029fd2 (0x29FD2)                       - every 4 calls → 0x201+0x203
   counter_check_dispatch_2A242 (0x2A242)       - 0x215 (throttle)
   can251TX_getAndPack (0x2AAB6)                - 0x251 (throttle position)
   [if 0xB5A4==1] can_tx_periodic_dispatch_2D402 (0x2D402) - 0x231
   mutex_trylock_4C85A (0x4C85A)                - every 25 → can240TX_pack (0x240)
   message_queue_send_4C956 (0x4C956)           - every 25 → can250TX_pack (0x250)
   incr_counter_saturated_299DA (0x299DA)       - CAN RX 216 timeout
   saturated_counter_dispatcher_33A36 (0x33A36) - 0x620 (fan)
   saturated_counter_dispatcher_33942 (0x33942) - 0x630 (cooling fan)
   can650TX_getAndPack (0x2C806)                - 0x650 (catalyst/O2)
5. clear byte @0xC241 (TX complete)
```

**Corrected names** (TLA names misleading): `can201TX_getAndPack` = `FUN_00029fd2`; `can203TX_getAndPack` = `counter_check_dispatch_2A242`; `can240TX_pack` = `mutex_trylock_4C85A` (calls `L_04c888`); `can250TX_pack` = `message_queue_send_4C956` (calls `L_04c984`); `CANRX216TimeoutCount` = `incr_counter_saturated_299DA`; `can620TX_getAndPack` = `saturated_counter_dispatcher_33A36`; `can_message_setup_dispatcher_33974` = `saturated_counter_dispatcher_33942`.

### TX Message Pack Functions

| CAN ID | Function | Address | Content |
|--------|----------|---------|---------|
| 0x041 | can41TXPack | 0x39348 | AC request, alternator |
| 0x201 | can201TX_getAndPack | 0x29B52 | Wheel speed, vehicle speed |
| 0x203 | can203TX_getAndPack | 0x29DC2 | Engine torque, status |
| 0x215 | can215TXpack | 0x2A3E2 | Throttle position |
| 0x231 | canPackandTx231 | 0x2D434 | RPM, load, coolant temp |
| 0x240 | can240TX_pack | 0x4C888 | Transmission / gear |
| 0x250 | can250TX_pack | 0x4C984 | Injection pulse width, fuel |
| 0x420 | can420TXPack | 0x29A0C | Battery voltage, misc |
| 0x620 | can620Pack | 0x33A68 | Fan status, AC |
| 0x630 | can630TX_getAndPack | 0x32DE2 | Cooling fan data |
| 0x650 | can650TX_getAndPack | 0x2C806 | Catalyst / O2 trim |

### `CAN_EmitLaunchStatus` (0x57BE8)
Reads bit 0x0400 from 0xFFFFF754 (VFAD solenoid bit, repurposed by a launch-control mod as "launch active") → 0/1 byte, emits via CAN.

## RX Path (Layer 2)

### Dispatch: `secondary_system_controller` (0xDE8E)
In 60E1D400 the CAN RX dispatch is `secondary_system_controller` (not a separate CANHandler/CANRX_Main pair; those may exist in other J-line variants — 0xDBF6 was previously/mistakenly used).

```
Gate: 0xAAE0==1, 0xB5E8!=1, 0xA410==0
→ CAN212RX_Main (0x2C0C4)                     - 0x212
→ lookup_table_indexed_29BE8                  - general lookups
→ table_lookup_dispatch_29E9C                 - (if 0xB5A4==0)
→ table_lookup_conditional_dispatch_33BA0     - 0x430/0x4C0
→ CAN4B0RX_Main (0x2BE18)                     - 0x4B0
→ event_check_4C78C                           - 0x4B1
→ utility_bitfield_check_2C780                - 0x4C0
→ CAN47RX_Main (0x3939C)                      - 0x47
```

### Per-ID RX Handlers

| Handler | Address | CAN ID | Mailbox | Purpose |
|---------|---------|--------|---------|---------|
| CAN212RX_Main | 0x2C0C4 | 0x212 | CAN1 MB1 | Unknown (steering angle?) |
| CAN4B0RX_Main | 0x2BE18 | 0x4B0 | CAN1 MB5 | DSC/ESP data |
| CAN47RX_Main | 0x3939C | 0x47 | CAN1 MB7 | Steering angle sensor |
| event_check_4C78C | 0x4C78C | 0x4B1 | CAN0 MB12 | DSC request secondary |
| utility_bitfield_check_2C780 | 0x2C780 | 0x4C0 | CAN1 MB6 | Unknown (short msg) |

CAN IDs 0x216, 0x430, 0x231 RX dispatched via `lookup_table_indexed_29BE8`/`table_lookup_dispatch_29E9C`, not directly called.

### RX Unpack Functions

| Function | Address | CAN ID | Purpose |
|----------|---------|--------|---------|
| can216RXUnpack | 0x29CE0 | 0x216 | Unpack RX data |
| can212RXUnpack | 0x2C60A | 0x212 | Unpack RX data |
| can47RXunpack | 0x393D0 | 0x47 | Steering angle, yaw rate |
| can430rx_unpack | 0x33BCA | 0x430 | Immobilizer |
| can4B1RXUnpack | 0x4C7B2 | 0x4B1 | DSC request |

### Filter / Encode / Decode

- **`can_filter_apply_49216`** (0x49216, 594 instr): big CAN filter/condition evaluator. Reads RPM (0xB5B8), VSS (0xB600), accel (0xAA10); cal constants @0x7C2E8+; FPU compares vs thresholds; sets/clears flag bytes @0xCD2A-0xCD30; evaluates DSC/ESP intervention, traction, fuel-cut, engine-load branches; calls `add16bitSaturate`.
- **`can_frame_parse_491AC`** (0x491AC): validates incoming frame timing vs thresholds @0x7C2B6, updates timer @0xCD28.
- **`can_data_encoder_24614`** (0x24614, 62 instr): TX bitfield encoder (inverse of decoder). Packs boolean flag bytes from RAM into compressed CAN format; FPU + `floatToFP_16bit`; buffer struct @0xB4B0.
- **`can_data_decode_2468C`** (0x2468C, 901 instr): largest CAN function — RX bitfield unpacker. 1) r12 = 0xB4E8 descriptor; copies 7 words to 0xB53C-0xB544. 2) Reads bytes 0xFFFFB596-0xFFFFB59C; per bit `tst→movt→add #-1→neg→cmp/eq #1→mov.b #1/#0`. 3) Outputs 47 flag bytes to 0xB55C-0xB58B. 4) On bit patterns calls 1 of 77 helpers (region 0x250A6-0x2595C; `0x2595C` called 7+ times). 5) Stores last decoded pair to 0xB546-0xB54B. One entry in fn-ptr table @0x245F0 (8 entries), referenced only there. Source bytes = CAN RX buffer / digital-input regs, each bit a vehicle status indicator.

## UDS Diagnostic Services (Layer 3a, ISO-14229-1)

Arrival: serial KWP2000 (0x1572-0x1D98, legacy) or CAN (0x7DF broadcast / 0x7E0 physical; response 0x7E8).

### `udsHandler` (0x697E8) — table-driven dispatcher (VERIFIED)

Called from `udsEntryPoint` (0x69702). Params: `param_1` = SID (& 0xff), `param_2` = length/flags, `param_3` = first byte = SID.

Dispatch table: 12 bytes/entry — `{sid(1) pad(3) handler_ptr(4) access_mask(4)}`, 0xFF sid sentinel. Session check helper @0x4308 reads session from 0xFFFFDE5C → bitmask (0x01 default, 0x02 programming, 0x04 extended, 0x08 safety); access mask ANDed → nonzero = accessible. Loop starts at index 1; r13 = 0 found/handled, 2 = no access.

Session mask encoding: 0x01=S1, 0x02=S2, 0x04=S3, 0x05=S1+3, 0x06=S2+3, 0x0E=S2+3+4, 0x0F=all, 0x1000000F=all+seed/key-generated flag.

**UDS Dispatch Table** @0x5F57C (28 entries + 0xFF sentinel) — **FULLY VERIFIED**:

| Idx | SID | ISO Name | Handler | Access | Notes |
|-----|-----|----------|---------|--------|-------|
| 0 | 0x01 | ReadData (OBD Mode 1) | 0x66258 | 0x01 | Always allowed |
| 1 | 0x02 | OBD sub 02 | 0x666C4 | 0x01 | OBD |
| 2 | 0x03 | OBD sub 03 | 0x66A34 | 0x01 | OBD |
| 3 | 0x04 | OBD sub 04 | 0x66B0C | 0x01 | OBD |
| 4 | 0x06 | OBD sub 06 | 0x67C98 | 0x01 | OBD |
| 5 | 0x07 | OBD sub 07 | 0x66C28 | 0x01 | OBD |
| 6 | 0x09 | Vehicle Info (OBD Mode 9) | 0x66CFC | 0x01 | Always allowed |
| 7 | 0x28 | CommunicationControl | 0x5C432 | 0x01 | Always allowed |
| 8 | 0x85 | ControlDTCSetting | 0x5E680 | 0x01 | Always allowed |
| 9 | 0x10 | DiagnosticSessionControl | 0x586C8 | 0x1000000F | All sessions |
| 10 | 0x27 | SecurityAccess | 0x584A0 | 0x1000000E | Sessions 2-4 |
| 11 | 0x3E | TesterPresent | 0x56F44 | 0x1000000F | All sessions |
| 12 | 0x11 | ECUReset | 0x5B990 | 0x0000000E | Sessions 2-4 |
| 13 | 0x21 | ReadDataByLocalID (OEM) | 0x5BE50 | 0x1000000F | All sessions |
| 14 | 0x22 | ReadDataByIdentifier | 0x57224 | 0x1000000F | All sessions |
| 15 | 0x23 | ReadMemoryByAddress | 0x5C18C | 0x00000006 | Sessions 2+3 |
| 16 | 0x3B | WriteData (OEM) | 0x5E2F0 | 0x0000000E | Sessions 2-4 |
| 17 | 0x18 | ReadDiagnosticInfo | 0x587EC | 0x00000005 | Sessions 1+3 |
| 18 | 0x12 | ReadFailureCodeData | 0x5BAD0 | 0x00000001 | Always allowed |
| 19 | 0x14 | ClearDiagnosticInformation | 0x562E8 | 0x10000005 | Sessions 1+3 |
| 20 | 0x2F | InputOutputControlByIdentifier | 0x5C688 | 0x10000004 | Session 3 |
| 21 | 0x31 | RoutineControl | 0x5E99C | 0x00000005 | Sessions 1+3 |
| 22 | 0x32 | (OEM 0x32) | 0x5EA60 | 0x00000005 | Sessions 1+3 |
| 23 | 0x33 | (OEM 0x33) | 0x5EB0A | 0x00000005 | Sessions 1+3 |
| 24 | 0x34 | RequestDownload | 0x5E1F8 | 0x00000002 | Session 2 |
| 25 | 0x36 | TransferData | 0x5E270 | 0x00000002 | Session 2 |
| 26 | 0x37 | RequestTransferExit | 0x5E2B0 | 0x00000002 | Session 2 |
| 27 | 0xB1 | ManufacturerSpecific | 0x57024 | 0x0000000F | All sessions |

```c
struct UDSDispatchEntry { uint8_t sid; uint8_t pad[3]; uint32_t handler; uint32_t access_mask; };
// bytes 4-7 = big-endian handler ptr; bytes 8-11 = big-endian access mask; 0xFF sentinel after table
```

**Correction**: OBD Mode 1 = 0x66258 (not 0x6410C), Mode 9 = 0x66CFC (not 0x64BB0); old addresses belong to another ROM variant.

### UDS Common Infrastructure

| Function | Address | Purpose |
|----------|---------|---------|
| udsSomething? | 0x67590 | UDS entry (calls udsHandler) |
| setupForUdsResponse | 0x66A14 | Init response frame buffer |
| udsServiceResponse | 0x66A74 | Positive response (SID+0x40) |
| udsResponseRelated?? | 0x52A12 | Parse request header |
| udsErrorResponse | 0x52A5A | Negative response (0x7F+SID+NRC) |
| UDSPositiveResponse_16bit | 0x58294 | Response with 16-bit data |
| intToUDS_SERVICE_DATA | 0x58448 | int → UDS format |
| byteToUDS_SERVICE_DATA | 0x5846A | byte → UDS format |
| securityNotUnlocked | 0x541F0 | Check bit 0 @0xFFFFD0F3 |
| checkSubFunctionCurrentlyRunning?? | 0x54146 | Prevent reentrant execution |
| getDiagSessionSubFunction | 0x540FE | Extract subfunction |
| getMemoryFromRAMForUDS23 | 0x59FDC | Read RAM for Mode 23 |
| pack_for_OBD_response? | 0x68858 | Final OBD response packing |

### NRCs
`udsErrorResponse` packs `[0x7F, SID, NRC]`. NRCs in this firmware: 0x10 generalReject · 0x11 serviceNotSupported · 0x12 subFunctionNotSupported · 0x13 incorrectMessageLengthOrInvalidFormat · 0x22 conditionsNotCorrect · 0x24 requestSequenceError · 0x31 requestOutOfRange · 0x33 securityAccessDenied · 0x35 invalidKey · 0x36 exceedNumberOfAttempts · 0x37 requiredTimeDelayNotExpired · 0x78 responsePending.

### Security Access (SID 0x27) — `UDSService27Function` (0x55F34)
Subfn 0x01 returns 4-byte seed; 0x02 validates key. LFSR algorithm, params @0x5FAC8. Security key: 5 ASCII bytes at 0x5FAC0 (stock `"MazdA"`). On success sets unlocked @0xFFFFD0F2.

## OBD-II Services (Layer 3b, ISO-15031)

Mode 1 (SID 0x01) handler @0x66258; Mode 9 (SID 0x09) @0x66CFC. PID conversion helpers previously documented at 0x53530-0x53A62 are **from another ROM variant** — in 60E1D400 region 0x53000-0x54000 holds utility functions (memcpy, string, bitfield); OBD PID processing is embedded in per-service handlers.

## DTC (Layer 3c)

DTCs stored in EEPROM via `getFromE2_E2ADDR_RAMADDR_LEN` (0x39170): Code (2 bytes, e.g. P0100=0x0100), Status (1 byte bitfield: testFailed/pending/confirmed/sinceCleared), Snapshot (freeze-frame: RPM, load, coolant).

| Function | Address | Description |
|----------|---------|-------------|
| dtc_handler_610FA | 0x610FA | Main DTC handler dispatch |
| dtc_code_set_46780 | 0x46780 | Set a DTC (mark failed) |
| dtc_code_clear_467AA | 0x467AA | Clear a DTC |
| dtc_pending_clear_46682 | 0x46682 | Clear pending DTCs |
| dtc_snapshot_store_467BE | 0x467BE | Store freeze-frame w/ DTC |
| obd_freeze_frame_467D0 | 0x467D0 | Retrieve freeze-frame by DTC |
| dtc_processor_0x50F1C | 0x50F1C | DTC state machine |
| dtcCodeTypeInit | 0x5BB6A | Init DTC code type table |
| writeDTCCodeType | 0x5BD2E | Write DTC code type |
| dtc_snapshot_manager_3b3bc | 0x3B3BC | Manage snapshots |

| Function | Address | DTC | Description |
|----------|---------|-----|-------------|
| dtc_p0100_maf_46DA0 | 0x46DA0 | P0100 | MAF circuit |
| dtc_p0110_iat_46DC2 | 0x46DC2 | P0110 | IAT circuit |
| dtc_p0120_tps_46DCA | 0x46DCA | P0120 | Throttle position |
| dtc_p0130_o2_46DD2 | 0x46DD2 | P0130 | O2 circuit |
| dtc_p0300_misfire_46E44 | 0x46E44 | P0300 | Random misfire |
| dtc_misfire_detection_468D6 | 0x468D6 | P0300+ | Misfire algorithm |
| dtc_p0400_egr_47058 | 0x47058 | P0400 | EGR |
| dtc_p0500_speed_47066 | 0x47066 | P0500 | Vehicle speed |
| dtc_p0600_pwr_471A2 | 0x471A2 | P0600 | Internal module |
| dtc_p0700_trans_4725E | 0x4725E | P0700 | Transmission |
| dtc_fuel_system_reset_45740 | 0x45740 | — | Fuel system DTC reset |
| dtc_o2_circuit_fault_45F54 | 0x45F54 | P0130-07 | O2 circuit faults |
| dtc_catalyst_efficiency_45FAC | 0x45FAC | P0420 | Catalyst efficiency |
| dtc_cat_system_monitor_45FFC | 0x45FFC | P0420 | Catalyst monitor |

| Function | Address | Description |
|----------|---------|-------------|
| diag_read_dtc_4E16E | 0x4E16E | Read DTC info |
| diag_clear_dtc_4E1C6 | 0x4E1C6 | Clear DTCs |
| dtcRelated | 0x62002 | Main DTC handling |
| dtc_debounce_monitor_43760 | 0x43760 | DTC debounce timing |
| obd_set_dtc_codes_4394E | 0x4394E | OBD DTC code setting |
| obd_readiness_monitor_474FA | 0x474FA | OBD readiness flags |
| obd_persistence_4750A | 0x4750A | DTC persistent storage |

## KWP2000/ISO-14230 Legacy Serial (Layer 3d)

Original serial/UART protocol predating CAN-UDS; over SCI (likely SCI5), buffers @0xFFFFD3F0.

| Function | Address | Description |
|----------|---------|-------------|
| diag_start_session_handler | 0x1572 | Session start (1-7) |
| diag_read_memory_by_addr | 0x15CC | Read memory by address |
| diag_send_status_frame | 0x1648 | Send status response |
| diag_transfer_data_handler | 0x1678 | Transfer data |
| diag_send_negative_response | 0x174E | Send NACK |
| diag_send_security_key_resp | 0x175C | Security key response |
| diag_request_download_sid10 | 0x1770 | Request download (old) |
| diag_security_access_sid27 | 0x17D8 | Security access SID 27 |
| diag_tester_present_sid3E | 0x1908 | Tester present SID 3E |
| diag_ecu_reset_sid11 | 0x1970 | ECU reset SID 11 |
| diag_read_data_sid22 | 0x19DA | Read data SID 22 |
| diag_write_timing_sid3B | 0x1A42 | Write timing SID 3B |
| diag_request_download_sid34 | 0x1A70 | Request download SID 34 |
| diag_transfer_data_sid36 | 0x1B8C | Transfer data SID 36 |
| diag_transfer_exit_sid37 | 0x1CB8 | Transfer exit SID 37 |
| diag_custom_cmd_B1 | 0x1D00 | Custom command 0xB1 |

## CAN Message Formats

Standard 11-bit IDs; DLC 8 for most. Examples:

**0x250 (injection pulse width; `can250TX_pack` 0x4C984 / `getOBDCANTXVars2` 0x4C9C0):**
```
B0-1 Inject PW (μs, BE u16)   B2-3 Fuel correction (u16)
B4-5 Lambda (scaled u16)      B6-7 Fuel pressure (scaled u16)
```
**0x231 (engine status; `canPackandTx231` 0x2D434):**
```
B0-1 RPM (u16, RPM*4)  B2 load(%)  B3 coolant(°C+40)  B4 IAT(°C+40)  B5 TPS(%)  B6-7 VSS(u16, km/h)
```
**0x201 (wheel speed; `can201TX_getAndPack` 0x29B52):**
```
B0-1 FL  B2-3 FR  B4-5 RL  B6-7 RR (all u16)
```

**UDS diagnostic frames** (11-bit): req `0x7DF` broadcast / `0x7E0` physical, data `[PCI][SID][Subf][Data...]`; res `0x7E8`, `[PCI][SID+0x40|0x7F][Data...]`.
PCI: SF 0x00-0x07 (len), FF 0x10+len-high, CF 0x20+seq, FC 0x30+flow (0 CTS/1 Wait/2 Overflow).

## RAM Map

| Address | Size | Description |
|---------|------|-------------|
| 0xFFFFA40F | byte | CAN TX throttle counter |
| 0xFFFFA410/0xFFFFA411 | byte | CAN TX inhibit flags 1/2 |
| 0xFFFFA40A | byte | CAN TX gate flag |
| 0xFFFFAAE0 | byte | CAN TX enable flag |
| 0xFFFFB5A4 | byte | CAN periodic TX mode flag |
| 0xFFFFB5E8 | byte | CAN TX inhibit flag 3 |
| 0xFFFFC241 | byte | CAN TX cycle complete flag |
| 0xFFFFCD2A/0xFFFFCD28 | u16 | CAN time counters 1/2 |
| 0xFFFFCD2C-0xCD30 | byte[5] | Diagnostic status flags |
| 0xFFFFCCF4-0xCCFF | byte[12] | CAN timer control flags |
| 0xFFFFCCFA | byte | CAN RX valid flag |
| 0xFFFFCCFB-0xCCFC | byte[2] | CAN filter result flags |
| 0xFFFFCCFD-0xCCFF | byte[3] | CAN diagnostic status |
| 0xFFFFDE5C | byte | Current diagnostic session |
| 0xFFFFD0F2 | byte | Security unlocked status |
| 0xFFFFD0F3 | byte | Security access flags |
| 0xFFFFD3F0 | byte[\?] | KWP session context |
| 0xFFFFF754 | u16 | SSV/VFAD status (bit 0x0400 = VFAD, mod: launch active) |
| 0xFFFF878C | u32 | CAN message buffer pointer |

## Key Findings

1. **Two dispatch paths**: `CANTX_Main` = sequential call chain per cycle; CAN RX = `secondary_system_controller` table-driven by CAN ID.
2. **Two protocol stacks compiled in**: KWP2000 over SCI (0x1572-0x1D98) and UDS over CAN (0x7DF/0x7E0/0x7E8), for tool compatibility.
3. **UDS handler dispatch table**: 12-byte entries `{sid, pad3, handler ptr, access mask}`, 0xFF sentinel, @0x5F57C.
4. **Security key** "MazdA" (5 ASCII) @0x5FAC0; LFSR params @0x5FAC8.
5. **TX gated counter**: `CANTX_Main` requires `0xFFFFA40F < 100`; flags 0xA40A/0xFFFFA410/0xFFFFA411 can inhibit TX (ECU stops traffic in fault states).
6. **CAN filter uses FPU** (`can_filter_apply_49216`) — FPU reads of RPM/VSS/accel vs thresholds for DSC/ESP condition monitoring.

## Verification Summary (July 2026)

| Component | Status | Notes |
|-----------|--------|-------|
| UDS Dispatch Table @0x5F57C | VERIFIED | 28 entries + 0xFF sentinel |
| udsHandler @0x697E8 | VERIFIED | Central dispatch, session access check |
| CANTX_Main @0xDDF0 | VERIFIED | Counter rate-limiting, corrected names |
| secondary_system_controller @0xDE8E | VERIFIED | Actual RX dispatch (not CANRX_Main @0xDBF6) |
| Security key "MazdA" @0x5FAC0 | VERIFIED | 5-byte ASCII, LFSR @0x5FAC8 |
| CAN Config Table @0x4EA60/0x4EB60/0x4EC60 | VERIFIED | Mailbox config (NOT runtime dispatch) |

### Corrected
1. **CAN RX dispatch**: `secondary_system_controller` @0xDE8E (was `CANRX_Main` @0xDBF6); several RX handler addresses were from another ROM variant.
2. **OBD handlers**: 0x66258 (Mode 1), 0x66CFC (Mode 9) — not 0x6410C/0x64BB0.
3. **CAN TX names**: TLA names were misleading; actual names describe counter dispatch (`mutex_trylock_4C85A`, `message_queue_send_4C956`, etc.).
4. **CAN config tables**: 16-byte entries are mailbox config (buffer pointers), not function pointers.

### Remaining to Verify
- OBD PID conversion helpers (addresses differ across ROM variants; need tracing through Mode 1 dispatcher).
- DTC handler dispatch (`dtcRelated` 0x62002 + sub-handlers) — full decompilation.
- KWP2000 serial stack vs CAN-UDS.

## Files Referenced
- ROM `roms/stock/60E1D400.bin` · Symbols `symbols/symbols_60E1D400_merged.csv` / `_ida.csv` · Call graph `symbols/callgraph.csv`
- `docs/notes/CAN_PROTOCOL.md` · `docs/functions/*.md` · `docs/notes/FINDINGS.md`
