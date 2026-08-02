# CAN/UDS Subsystem — RX-8 ECU (60E1D400)

## Overview

The RX-8 ECU firmware has a large multi-layered CAN (Controller Area Network) and UDS
(Unified Diagnostic Services) subsystem spanning approximately 149 functions across the ROM.
It supports:

- **Two CAN buses**: HS-CAN (diagnostics, UDS) and MS-CAN (accessories)
- **Proprietary broadcast messages**: CAN IDs 0x201-0x650 carry engine data
- **UDS/ISO-14229-1 diagnostics**: Via KWP2000 serial and CAN
- **OBD-II (ISO-15031)**: Standard emissions-related diagnostics
- **DTC handling**: Diagnostic Trouble Code storage, retrieval, and clearing

---

## Architecture Layers

```
┌──────────────────────────────────────────────────────────────┐
│                     Layer 3: UDS/OBD Services                │
│  (udsHandler, UDSMode*, obd_service_handler*, DTC handlers)  │
├──────────────────────────────────────────────────────────────┤
│                   Layer 2: CAN Message Layer                 │
│  (CANTX_Main, CANRX_Main, can_filter_apply, can_data_encode) │
├──────────────────────────────────────────────────────────────┤
│                Layer 1: CAN Hardware Interface               │
│  (CANControllerSetup, mailbox handlers, register access)     │
├──────────────────────────────────────────────────────────────┤
│              Layer 0: SH7055 CAN Controller (HCAN)           │
│  (HCAN registers @ 0xFFFFC000-0xFFFFCFFF, 16 mailboxes)     │
└──────────────────────────────────────────────────────────────┘
```

---

## CAN Mailbox Configuration Tables (60E1D400)

In 60E1D400, the CAN dispatch table (at 0x4E728 in [REDACTED]) maps to three
configuration tables:

- **CAN0 TX Primary**: `0x4EA60` (16 entries, used when `0xB5A4 == 1`)
- **CAN0 TX Alternate**: `0x4EB60` (16 entries, used when `0xB5A4 == 0`)
- **CAN1 RX**: `0x4EC60` (6 entries)

These are **mailbox configuration structures**, NOT runtime dispatch tables.
The 16-byte entries configure the HCAN mailboxes with CAN ID, DLC, direction,
and buffer addresses. Runtime dispatch is handled by direct function calls in
`CANTX_Main` (0xDDF0) and `secondary_system_controller` (0xDE8E).

The "handler address" in the 16-byte entry is actually a **mailbox data buffer
pointer** (pointing into the HCAN register space at 0xFFFFExxx), not a function
entry point. Verification showed these "addresses" fall inside unrelated code
functions in the ROM.

### Full CAN0 TX Mailbox Map

| Entry | CAN ID | MB | DLC | Dir | Buffer | Description |
|-------|--------|-----|-----|-----|--------|-------------|
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

### Full CAN1 RX Mailbox Map

| Entry | CAN ID | MB | DLC | Dir | Buffer | Description |
|-------|--------|-----|-----|-----|--------|-------------|
| 0 | 0x0212 | 1 | 7 | RX | 0x01BC28 | Unknown |
| 1 | 0x0216 | 2 | 8 | RX | 0x01BB20 | Unknown |
| 2 | 0x0430 | 4 | 7 | RX | 0x01C060 | Immobilizer / security |
| 3 | 0x04B0 | 5 | 8 | RX | 0x01BC08 | DSC/ESP data |
| 4 | 0x04C0 | 6 | 1 | RX | 0x01BC64 | Short message |
| 5 | 0x0047 | 7 | 8 | RX | 0x01C520 | Steering angle sensor |

---

## Layer 0: SH7055 HCAN Hardware

The Renesas SH7055 has a built-in HCAN (Hitachi CAN) controller with:

- **16 mailboxes** (each can be TX or RX)
- **Standard (11-bit) and extended (29-bit) ID support**
- **Mailbox 0-7**: Usually RX
- **Mailbox 8-15**: Usually TX

**Key registers** (accessed via `getHCANRegisterAddress` at 0xD198):
- `MCR` (Mode Control Register): Reset, HALT, operation modes
- `MBCR` (Mailbox Control Register)
- `M_BOCR` (Mailbox Configuration Registers)
- `M_BIDR` (Mailbox ID Registers)
- `M_BDSR` (Mailbox Data Segment Registers)

---

## Layer 1: CAN Hardware Interface Functions

### Initialization Chain

```
main_init → canSetup (0xDC8C) → CANControllerSetup (0x9878)
                                → canMessageSetup (0x2B320)
                                → canInitVals (0x2AFC8)
                                → hcan_init_and_status_check (0xD6A0)
```

**`CANControllerSetup`** (0x9878, equinox-name):
Full HCAN controller initialization at startup:
1. Configures pin function control for CAN TX/RX pins
2. Takes HCAN out of reset via MCR
3. Sets baud rate prescaler (via `set_MCR_bits2_3`, `set_MCR_bits5_7`)
4. Configures all 16 mailboxes with `setCANRegisters`
5. Sets RX mask filters
6. Enables mailbox interrupts (RX complete, TX acknowledge, error)

**`canMessageSetup`** (0x2B320, equinox-name):
Post-init CAN message configuration:
- Sets up periodic TX message timing
- Configures RX message filters by CAN ID
- Initializes message counters and timeout values

### Mailbox Operations

| Function | Address | Purpose |
|----------|---------|---------|
| `can_set_mailbox_mode_dlc` | 0xCDC4 | Set mailbox mode + DLC |
| `can_set_mailbox_ptr_control` | 0xCDFA | Set mailbox buffer pointer |
| `can_set_mailbox_id_mode` | 0xCE34 | Set CAN ID and format (std/ext) |
| `can_set_mailbox_rx_id` | 0xCF90 | Set RX acceptance filter ID |
| `can_enable_mailbox_int` | 0xCC6C | Enable mailbox interrupt |
| `can_disable_mailbox_int` | 0xCC84 | Disable mailbox interrupt |
| `can_get_rx_pending_flags` | 0xD0C0 | Read RX pending flags (MPR) |
| `can_get_tx_acknowledge_flags` | 0xD112 | Read TX acknowledge flags (MTACKR) |
| `baro_sensor_value` | 0xD144 | Barometric sensor value (formerly `can_clear_tx_acknowledge`) |
| `can_mailbox_read_data` | 0xCFD4 | Read raw data from mailbox |
| `can_mailbox_extract_msg_data` | 0xCFF6 | Extract and format message from buffer |
| `can_pack_tx_msg_copy` | 0xCEF4 | Copy message data into TX mailbox |
| `can_pack_tx_msg_write_verify` | 0xCF42 | Write + verify TX data integrity |
| `can_tx_abort_and_retry` | 0x9CC6 | Abort TX, re-send on failure |
| `can_register_read_write` | 0x9DD8 | Low-level register R/W wrapper |

---

## Layer 2: CAN Message Layer — TX Path

### `CANTX_Main` (0xDDF0)

The **master CAN TX dispatch** function. Called periodically from the main loop.

**Flow (VERIFIED from 60E1D400 decompilation):**
```
CANTX_Main:
  1. Check 0xFFFFA40F counter >= 100 (0x64) → skip TX cycle
  2. Check flags at 0xA40A, 0xFFFFA410, 0xFFFFA411 → skip if any set
  3. Check 0xAAE0 == 0x01 AND 0xB5E8 != 0x01 → allow TX
  4. Call each TX function in sequence (with counter-based rate limiting):
     → can41TXPack (0x39348)               - CAN ID 0x041 (AC)
     → FUN_00029fd2 (0x29FD2)              - Counter: every 4 calls → sub-dispatches 0x201+0x203
     → counter_check_dispatch_2A242 (0x2A242)- CAN ID 0x215 (throttle)
     → can251TX_getAndPack (0x2AAB6)       - CAN ID 0x251 (throttle position)
     → [if 0xB5A4 == 1] can_tx_periodic_dispatch_2D402 (0x2D402) - CAN ID 0x231
     → mutex_trylock_4C85A (0x4C85A)       - Counter: every 25 calls → can240TX_pack (CAN 0x240)
     → message_queue_send_4C956 (0x4C956)  - Counter: every 25 calls → can250TX_pack (CAN 0x250)
     → incr_counter_saturated_299DA (0x299DA)- CAN RX 216 timeout
     → saturated_counter_dispatcher_33A36 (0x33A36)- CAN ID 0x620 (fan)
     → saturated_counter_dispatcher_33942 (0x33942)- CAN ID 0x630 (cooling fan)
     → can650TX_getAndPack (0x2C806)       - CAN ID 0x650 (catalyst/O2)
  5. Clear byte at 0xC241 (TX complete flag)
```

**Key corrections from earlier documentation:**
- `can201TX_getAndPack` is actually `FUN_00029fd2` (counter dispatcher, calls sub-handlers)
- `can203TX_getAndPack` is actually `counter_check_dispatch_2A242`
- `can240TX_pack` is actually `mutex_trylock_4C85A` (counter wrapper, calls `L_04c888` = can240TX_pack)
- `can250TX_pack` is actually `message_queue_send_4C956` (counter wrapper, calls `L_04c984` = can250TX_pack)
- `CANRX216TimeoutCount` is actually `incr_counter_saturated_299DA`
- `can620TX_getAndPack` is actually `saturated_counter_dispatcher_33A36`
- `can_message_setup_dispatcher_33974` is actually `saturated_counter_dispatcher_33942`

### TX Message Pack Functions

Each pack function reads sensor values from RAM, converts to CAN byte format,
and writes to a HCAN mailbox for transmission.

| CAN ID | Function | Address | Content |
|--------|----------|---------|---------|
| 0x041 | `can41TXPack` | 0x39348 | AC request, alternator |
| 0x201 | `can201TX_getAndPack` | 0x29B52 | Wheel speed, vehicle speed (ABS/ESP) |
| 0x203 | `can203TX_getAndPack` | 0x29DC2 | Engine torque, status (ABS/ESP) |
| 0x215 | `can215TXpack` (in `can251TX_getAndPack`) | 0x2A3E2 | Throttle position |
| 0x231 | `canPackandTx231` | 0x2D434 | RPM, engine load, coolant temp |
| 0x240 | `can240TX_pack` | 0x4C888 | Transmission / gear data |
| 0x250 | `can250TX_pack` | 0x4C984 | Injection pulse width, fuel |
| 0x420 | `can420TXPack` | 0x29A0C | Battery voltage, misc |
| 0x430 | (via `can430rx_unpack` as RX) | 0x33BCA | Immobilizer/security |
| 0x620 | `can620Pack` | 0x33A68 | Fan status, AC |
| 0x630 | `can630TX_getAndPack` | 0x32DE2 | Cooling fan data |
| 0x650 | `can650TX_getAndPack` | 0x2C806 | Catalyst / O2 sensor trim |

### `CAN_EmitLaunchStatus` (0x57BE8)

Reads bit 0x0400 from RAM word at 0xFFFFF754 (the **VFAD status bit** — stock F754
bit 0x0400 is the VFAD solenoid control bit, repurposed by the [REDACTED]
launch-control mod as its "launch active" flag), converts to a 0/1 byte, and
emits it via CAN. This is the [REDACTED] launch control CAN output.

---

## Layer 2: CAN Message Layer — RX Path

### CAN RX Dispatch: `secondary_system_controller` (0xDE8E)

In 60E1D400, the CAN RX dispatch is done by `secondary_system_controller` at 0xDE8E
(not a separate `CANHandler`/`CANRX_Main` pair as previously documented). This function
is called from the periodic task dispatcher and runs the RX handlers sequentially.

**NOTE**: In the [REDACTED] ROM, there may have been separate CANHandler/CANRX_Main
functions. In 60E1D400, the RX path is simplified into `secondary_system_controller`.

```
secondary_system_controller:
  Gate check: 0xAAE0==1, 0xB5E8!=1, 0xA410==0
  
  → CAN212RX_Main(0x2C0C4)   — CAN ID 0x212
  → lookup_table_indexed_29BE8  — general lookups
  → table_lookup_dispatch_29E9C (if 0xB5A4==0)
  → table_lookup_conditional_dispatch_33BA0 — CAN 0x430/0x4C0
  → CAN4B0RX_Main(0x2BE18)   — CAN ID 0x4B0
  → event_check_4C78C         — CAN ID 0x4B1
  → utility_bitfield_check_2C780 — CAN ID 0x4C0
  → CAN47RX_Main(0x3939C)    — CAN ID 0x47
```

### Per-ID RX Handlers

| Handler | Address | CAN ID | Mailbox | Purpose |
|---------|---------|--------|---------|---------|
| `CAN212RX_Main` | 0x2C0C4 | 0x212 | CAN1 MB1 | Unknown (steering angle?) |
| `CAN4B0RX_Main` | 0x2BE18 | 0x4B0 | CAN1 MB5 | DSC/ESP data |
| `CAN47RX_Main` | 0x3939C | 0x47 | CAN1 MB7 | Steering angle sensor |
| `event_check_4C78C` | 0x4C78C | 0x4B1 | CAN0 MB12 | DSC request secondary |
| `utility_bitfield_check_2C780` | 0x2C780 | 0x4C0 | CAN1 MB6 | Unknown (short msg) |

**Note**: CAN IDs 0x216, 0x430, 0x231 RX handlers are dispatched through the 
`lookup_table_indexed_29BE8` / `table_lookup_dispatch_29E9C` functions rather than
being directly called.

### RX Unpack Functions

Each unpack function extracts bytes from received CAN messages and updates RAM values:

| Function | Address | CAN ID | Purpose |
|----------|---------|--------|---------|
| `can216RXUnpack` | 0x29CE0 | 0x216 | Unpack RX data |
| `can212RXUnpack` | 0x2C60A | 0x212 | Unpack RX data |
| `can47RXunpack` | 0x393D0 | 0x47 | Steering angle, yaw rate |
| `can430rx_unpack` | 0x33BCA | 0x430 | Immobilizer |
| `can4B1RXUnpack` | 0x4C7B2 | 0x4B1 | DSC request |

### `can_filter_apply_49216` (0x49216)

The **big CAN filter/condition evaluator** (594 instructions). This function:
1. Reads RPM (0xB5B8), vehicle speed sensor (0xB600), acceleration (0xAA10)
2. Loads calibration constants from a table at 0x7C2E8+
3. Performs FPU comparisons against thresholds
4. Sets/clears flag bytes at RAM 0xCD2A-0xCD30 (diagnostic status flags)
5. Evaluates multi-condition branches for:
   - DSC/ESP intervention detection
   - Traction control status
   - Fuel cut events
   - Engine load conditions
6. Calls `add16bitSaturate` for counter updates

### `can_frame_parse_491AC` (0x491AC)

Validates incoming CAN frame timing by comparing timer values against thresholds
at 0x7C2B6, updating the timer at 0xCD28.

### `can_data_encoder_24614` (0x24614) — TX Encoder

The **TX bitfield encoder** (62 instructions, 124 bytes). Inverse of `can_data_decode_2468C`.
Packs individual boolean flag bytes from RAM into compressed CAN message format.
Uses FPU (`fldi0`/`fmov`) for float comparison and `floatToFP_16bit` conversion.
Reads sensor values from RAM and encodes them into a message buffer structure at 0xB4B0.
(Directly precedes the decoder at adjacent ROM address.)

### `can_data_decode_2468C` (0x2468C) — 901 instructions

The **largest CAN function** — a massive CAN RX data unpacker that decodes compressed
bitfield status from incoming CAN messages into individual boolean flag bytes.

**Architecture:**
1. **Load descriptor pointer**: r12 = 0xB4E8 (CAN message buffer descriptor in RAM)
2. **Read configuration**: Copies 7 word values from the descriptor (r12+1 through r12+7)
   to RAM 0xB53C-0xB544 for downstream use by other functions.
3. **Bitfield extraction**: Reads 7 consecutive source bytes from addresses 0xFFFFB596
   through 0xFFFFB59C. For each byte, tests every bit position (0x01, 0x02, 0x04, 0x08,
   0x10, 0x20, 0x40, 0x80) using the pattern `tst` → `movt` → `add #-1` → `neg` →
   `cmp/eq #1` → conditional `mov.b #1/#0` to output.
4. **Flag storage**: Outputs 47 boolean flag bytes to RAM 0xB55C-0xB58B.
5. **Conditional helpers**: When certain bit patterns are detected, calls one of 77 helper
   functions in region 0x250A6-0x2595C (simple data conversion/formatters).
6. **Shared helper**: `0x2595C` is called 7+ times with varying r5/r6 source/destination
   addresses for byte-level data conversion.
7. **Final store**: Writes the last decoded message byte pair to 0xB546-0xB54B.

**Dispatch context**: This function is one entry in a function pointer table at ROM
0x245F0 (8 entries: `0x24410`, `getSR(0x3920)`, `0x24440`, `setSR(0x3934)`,
`0x24514`, `can_data_decode_2468C`, `0x24D96`, `0x250F6`). The dispatcher calls each
function in sequence, creating a processing pipeline. Only referenced once in ROM
(at the table entry).

**Source bytes 0xFFFFB596-0xFFFFB59C**: Consecutive 7-byte region likely mapping
to CAN RX data buffer or digital input port registers. Each bit position encodes
a specific vehicle status indicator (engine state, switch inputs, fault flags).

---

## Layer 3a: UDS Diagnostic Services (ISO-14229-1)

### Entry Point

UDS diagnostic messages arrive via:
1. **Serial (KWP2000)**: Functions at 0x1572-0x1D98 (legacy)
2. **CAN**: CAN ID 0x7DF (broadcast), 0x7E0 (physical), response at 0x7E8

### `udsHandler` (0x697E8) — Main Service Dispatcher (VERIFIED)

This is the **central UDS dispatch function** — fully verified against raw ROM data.
It uses a table-driven dispatch:

**Parameters (from decompilation):**
- `param_1` = uint (SID byte, masked to lower byte with `& 0xff`)
- `param_2` = short (data length/flags)
- `param_3` = char (first byte of request data = SID)
  Called from `udsEntryPoint` (0x69702)

**Dispatch Table Structure (12 bytes per entry):**
```
Offset  Size  Description
  0      1    Service ID (SID) byte to match (0xFF = sentinel)
  1      3    Padding
  4      4    Pointer to handler function
  8      4    Access bitmask (ANDed with session check result)
```

**Session check:** A helper function at 0x4308 is called first with the current session
value from 0xFFFFDE5C. It returns a bitmask (e.g., 0x01=default, 0x02=programming,
0x04=extended, 0x08=safety). The access mask from the table entry is ANDed with
this bitmask; if nonzero, the handler is accessible.

**Session Access Mask Encoding:**
```
0x01 = Session 1 (default) only
0x02 = Session 2 (programming) only
0x04 = Session 3 (extended) only
0x05 = Sessions 1 + 3
0x06 = Sessions 2 + 3
0x0E = Sessions 2 + 3 + 4
0x0F = All sessions (1-4)
0x1000000F = All sessions + high-byte flag (e.g., seed/key already generated)
```

**Flow:**
```
udsHandler:
  1. Save r6->*r6 (first byte = SID) to stack
  2. Load session value from 0xFFFFDE5C
  3. Call session check function (0x4308) → returns session bitmask in r7
  4. Load dispatch table base (0x0005F57C from ROM data pool)
  5. Start loop with entry index r5 = 1 (skip entry 0?)
  6. For each entry:
     a. Compute offset = index * 12
     b. Read SID byte at table[offset]
     c. If SID == 0xFF, exit (no match)
     d. Compare with request SID
     e. If not match, increment index, continue
     f. If match:
        - Read handler ptr at table[offset+4]
        - Read access mask at table[offset+8]
        - If r7 & access_mask → call handler
        - Else return "access denied" (r13=2)
  7. Return r13 (0 = found+handled, 2 = no access)
```

**UDS Dispatch Table** (ROM 0x5F57C, 28 entries + 0xFF sentinel) — **✅ FULLY VERIFIED**:

| Idx | SID | ISO Name | Handler Address | Access | Notes |
|-----|-----|----------|-----------------|--------|-------|
| 0 | 0x01 | ReadData (OBD Mode 1) | 0x66258 | 0x01 | Always allowed |
| 1 | 0x02 | OBD sub-service 02 | 0x666C4 | 0x01 | OBD-related |
| 2 | 0x03 | OBD sub-service 03 | 0x66A34 | 0x01 | OBD-related |
| 3 | 0x04 | OBD sub-service 04 | 0x66B0C | 0x01 | OBD-related |
| 4 | 0x06 | OBD sub-service 06 | 0x67C98 | 0x01 | OBD-related |
| 5 | 0x07 | OBD sub-service 07 | 0x66C28 | 0x01 | OBD-related |
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
| 20 | 0x2F | InputOutputControlByIdentifier | 0x5C688 | 0x10000004 | Session 3 only |
| 21 | 0x31 | RoutineControl | 0x5E99C | 0x00000005 | Sessions 1+3 |
| 22 | 0x32 | (OEM 0x32) | 0x5EA60 | 0x00000005 | Sessions 1+3 |
| 23 | 0x33 | (OEM 0x33) | 0x5EB0A | 0x00000005 | Sessions 1+3 |
| 24 | 0x34 | RequestDownload | 0x5E1F8 | 0x00000002 | Session 2 only |
| 25 | 0x36 | TransferData | 0x5E270 | 0x00000002 | Session 2 only |
| 26 | 0x37 | RequestTransferExit | 0x5E2B0 | 0x00000002 | Session 2 only |
| 27 | 0xB1 | ManufacturerSpecific | 0x57024 | 0x0000000F | All sessions |

**Verification**: All 28 entries verified against raw ROM data at 0x5F57C.
Handlers are stored as big-endian 32-bit pointers (bytes 4-7). Access masks
are stored as big-endian 32-bit (bytes 8-11). Entry format:

```c
struct UDSDispatchEntry {
    uint8_t  sid;         // Service ID to match
    uint8_t  pad[3];      // Padding (zeros)
    uint32_t handler;     // Function pointer (BE32)
    uint32_t access_mask; // Session access mask (BE32)
};
// Followed by 0xFF sentinel byte
```

**Note:** Earlier analysis identified OBD Mode 1 handler at 0x6410C and
Mode 9 at 0x64BB0. These are WRONG for 60E1D400 — the verified dispatch
table shows 0x66258 and 0x66CFC respectively. The old addresses may be
correct for [REDACTED] ROM.

### UDS Common Infrastructure

| Function | Address | Purpose |
|----------|---------|---------|
| `udsSomething?` | 0x67590 | UDS entry point (calls udsHandler) |
| `setupForUdsResponse` | 0x66A14 | Initialize response frame buffer |
| `udsServiceResponse` | 0x66A74 | Send positive response (SID+0x40) |
| `udsResponseRelated??` | 0x52A12 | Parse incoming UDS request header |
| `udsErrorResponse` | 0x52A5A | Send negative response (0x7F + SID + NRC) |
| `UDSPositiveResponse_16bit` | 0x58294 | Build response with 16-bit data value |
| `intToUDS_SERVICE_DATA` | 0x58448 | Convert int to UDS data format |
| `byteToUDS_SERVICE_DATA` | 0x5846A | Convert byte to UDS format |
| `securityNotUnlocked` | 0x541F0 | Check bit 0 of security status at 0xFFFFD0F3 |
| `checkSubFunctionCurrentlyRunning??` | 0x54146 | Prevents reentrant service execution |
| `getDiagSessionSubFunction` | 0x540FE | Extract subfunction from request |
| `getMemoryFromRAMForUDS23` | 0x59FDC | Read RAM for Mode 23 response |
| `pack_for_OBD_response?` | 0x68858 | Final OBD response packing |

### UDS Negative Response Codes (NRCs)

The `udsErrorResponse` function packs:
```
Byte 0: 0x7F (NegativeResponse SI)
Byte 1: SID (Service ID that failed)
Byte 2: NRC (Negative Response Code)
```

Known NRCs used in this firmware (from code analysis):
- `0x10` - generalReject
- `0x11` - serviceNotSupported
- `0x12` - subFunctionNotSupported
- `0x13` - incorrectMessageLengthOrInvalidFormat
- `0x22` - conditionsNotCorrect
- `0x24` - requestSequenceError
- `0x31` - requestOutOfRange
- `0x33` - securityAccessDenied
- `0x35` - invalidKey
- `0x36` - exceedNumberOfAttempts
- `0x37` - requiredTimeDelayNotExpired
- `0x78` - requestCorrectlyReceived-ResponsePending

### Security Access (SID 0x27)

The `UDSService27Function` (0x55F34) implements seed/key authentication:
1. Subfunction 0x01 (requestSeed) → returns 4-byte seed
2. Subfunction 0x02 (sendKey) → validates key
3. LFSR-based algorithm with parameters stored at 0x5FAC8
4. Security key constant: 5 ASCII bytes (stock = `"MazdA"`, at 0x5FAC0)
5. On success, sets unlocked status in RAM 0xFFFFD0F2

---

## Layer 3b: OBD-II Services (ISO-15031)

### OBD Mode 1: Current Data (SID 0x01)

The UDS dispatch table points to the handler at **0x66258**. (Note: earlier analysis
identified 0x6410C, but the verified dispatch table at 0x5F57C shows 0x66258.)

**Note on OBD PID helpers**: The OBD PID conversion helper functions previously
documented at 0x53530-0x53A62 are addresses from the [REDACTED] ROM. In 60E1D400,
the code layout differs and these specific addresses do not correspond to named
OBD helper functions. The region 0x53000-0x54000 contains utility functions
(memcpy, string ops, bitfield ops) rather than OBD-specific helpers. The actual
OBD PID processing is embedded within the per-service handler functions called
from the Mode 1 dispatcher.

### OBD Mode 9: Vehicle Information (SID 0x09)

Handled at **0x66CFC** (from UDS dispatch table). (Earlier documentation said
0x64BB0, but the verified table shows 0x66CFC.)

---

## Layer 3c: Diagnostic Trouble Codes (DTC)

### DTC Storage System

DTCs are stored in EEPROM via the E2PROM controller, accessed through
`getFromE2_E2ADDR_RAMADDR_LEN` (0x39170). Each DTC has:
- **Code**: 2 bytes (e.g., P0100 = 0x0100)
- **Status**: 1 byte (bitfield: testFailed, pending, confirmed, sinceCleared, etc.)
- **Snapshot**: Freeze-frame data (RPM, load, coolant temp, etc.)

### DTC Handler Functions

| Function | Address | Description |
|----------|---------|-------------|
| `dtc_handler_610FA` | 0x610FA | Main DTC handler dispatch |
| `dtc_code_set_46780` | 0x46780 | Set a DTC (mark as failed) |
| `dtc_code_clear_467AA` | 0x467AA | Clear a specific DTC |
| `dtc_pending_clear_46682` | 0x46682 | Clear pending DTCs |
| `dtc_snapshot_store_467BE` | 0x467BE | Store freeze-frame data with DTC |
| `obd_freeze_frame_467D0` | 0x467D0 | Retrieve freeze frame by DTC |
| `dtc_processor_0x50F1C` | 0x50F1C | DTC state machine processing |
| `dtcCodeTypeInit` | 0x5BB6A | Initialize DTC code type table |
| `writeDTCCodeType` | 0x5BD2E | Write DTC code type to storage |
| `dtc_snapshot_manager_3b3bc` | 0x3B3BC | Manage DTC snapshot storage |

### Specific DTC Monitors

| Function | Address | DTC | Description |
|----------|---------|-----|-------------|
| `dtc_p0100_maf_46DA0` | 0x46DA0 | P0100 | MAF sensor circuit |
| `dtc_p0110_iat_46DC2` | 0x46DC2 | P0110 | IAT sensor circuit |
| `dtc_p0120_tps_46DCA` | 0x46DCA | P0120 | Throttle position sensor |
| `dtc_p0130_o2_46DD2` | 0x46DD2 | P0130 | O2 sensor circuit |
| `dtc_p0300_misfire_46E44` | 0x46E44 | P0300 | Random misfire |
| `dtc_misfire_detection_468D6` | 0x468D6 | P0300+ | Misfire detection algorithm |
| `dtc_p0400_egr_47058` | 0x47058 | P0400 | EGR system |
| `dtc_p0500_speed_47066` | 0x47066 | P0500 | Vehicle speed sensor |
| `dtc_p0600_pwr_471A2` | 0x471A2 | P0600 | Internal control module |
| `dtc_p0700_trans_4725E` | 0x4725E | P0700 | Transmission control |
| `dtc_fuel_system_reset_45740` | 0x45740 | — | Fuel system DTC reset |
| `dtc_o2_circuit_fault_45F54` | 0x45F54 | P0130-07 | O2 circuit faults |
| `dtc_catalyst_efficiency_45FAC` | 0x45FAC | P0420 | Catalyst efficiency |
| `dtc_cat_system_monitor_45FFC` | 0x45FFC | P0420 | Catalyst monitor |

### UDS DTC Services (SIDs 0x14, 0x19)

| Function | Address | Description |
|----------|---------|-------------|
| `diag_read_dtc_4E16E` | 0x4E16E | Read DTC information |
| `diag_clear_dtc_4E1C6` | 0x4E1C6 | Clear DTCs |
| `dtcRelated` | 0x62002 | Main DTC handling |
| `dtc_debounce_monitor_43760` | 0x43760 | DTC debounce timing |
| `obd_set_dtc_codes_4394E` | 0x4394E | OBD DTC code setting |
| `obd_readiness_monitor_474FA` | 0x474FA | OBD readiness flags |
| `obd_persistence_4750A` | 0x4750A | DTC persistent storage |

---

## Layer 3d: KWP2000/ISO-14230 Legacy Serial Diagnostics

These functions at 0x1500-0x1D00 are the **original serial/UART diagnostic protocol**
that predates CAN-based UDS in this firmware family. They implement the
KWP2000 (Keyword Protocol 2000) over SCI (Serial Communication Interface).

| Function | Address | Description |
|----------|---------|-------------|
| `diag_start_session_handler` | 0x1572 | Session start (1-7) |
| `diag_read_memory_by_addr` | 0x15CC | Read memory by address |
| `diag_send_status_frame` | 0x1648 | Send status response |
| `diag_transfer_data_handler` | 0x1678 | Transfer data handler |
| `diag_send_negative_response` | 0x174E | Send NACK |
| `diag_send_security_key_resp` | 0x175C | Security key response |
| `diag_request_download_sid10` | 0x1770 | Request download (old) |
| `diag_security_access_sid27` | 0x17D8 | Security access SID 27 |
| `diag_tester_present_sid3E` | 0x1908 | Tester present SID 3E |
| `diag_ecu_reset_sid11` | 0x1970 | ECU reset SID 11 |
| `diag_read_data_sid22` | 0x19DA | Read data SID 22 |
| `diag_write_timing_sid3B` | 0x1A42 | Write timing SID 3B |
| `diag_request_download_sid34` | 0x1A70 | Request download SID 34 |
| `diag_transfer_data_sid36` | 0x1B8C | Transfer data SID 36 |
| `diag_transfer_exit_sid37` | 0x1CB8 | Transfer exit SID 37 |
| `diag_custom_cmd_B1` | 0x1D00 | Custom command 0xB1 |

These early functions operate on SCI channel directly (likely SCI5 on the SH7055),
using buffers at 0xFFFFD3F0 (KWP session context).

---

## CAN Message Format

### Standard Proprietary Messages

All proprietary CAN messages use **11-bit standard IDs**. Frame format:
```
Byte 0-7: Data bytes (0-8, per message definition)
Byte  DLC: 8 for most messages
```

### CAN ID 0x250 Example (Injection Pulse Width)

From `can250TX_pack` at 0x4C984 and `getOBDCANTXVars2` at 0x4C9C0:
```
Byte 0-1: Injection pulse width (μs, big-endian u16)
Byte 2-3: Fuel correction (u16)
Byte 4-5: Lambda value (scaled u16)
Byte 6-7: Fuel pressure (scaled u16)
```

### CAN ID 0x231 Example (Engine Status)

From `canPackandTx231` at 0x2D434:
```
Byte 0-1: Engine RPM (u16, RPM * 4)
Byte 2:   Engine load (%)
Byte 3:   Coolant temperature (°C + 40)
Byte 4:   Intake air temperature (°C + 40)
Byte 5:   Throttle position (%)
Byte 6-7: Vehicle speed (u16, km/h)
```

### CAN ID 0x201 Example (Wheel Speed / ABS)

From `can201TX_getAndPack` at 0x29B52:
```
Byte 0-1: Front left wheel speed (u16)
Byte 2-3: Front right wheel speed (u16)
Byte 4-5: Rear left wheel speed (u16)
Byte 6-7: Rear right wheel speed (u16)
```

### UDS Diagnostic Messages

Diagnostic request CAN frame (11-bit IDs):
```
ID 0x7DF: Broadcast request (OBD-II)
ID 0x7E0: Physical request (ECU specific)
Data: [PCI] [SID] [Subfunction] [Data bytes...]
```

Diagnostic response CAN frame:
```
ID 0x7E8: Physical response
Data: [PCI] [SID+0x40 or 0x7F] [Data bytes...]
```

PCI (Protocol Control Information):
- SingleFrame (SF): 0x00-0x07 = length 0-7, 0x08-0xFF = length (for 8-byte CAN)
- FirstFrame (FF): 0x10 + length high nibble
- ConsecutiveFrame (CF): 0x20 + sequence number
- FlowControl (FC): 0x30 + flow status (0=CTS, 1=Wait, 2=Overflow)

---

## RAM Map for CAN/UDS Variables

| Address | Size | Description |
|---------|------|-------------|
| 0xFFFFA40F | byte | CAN TX throttle counter |
| 0xFFFFA410 | byte | CAN TX inhibit flag 1 |
| 0xFFFFA411 | byte | CAN TX inhibit flag 2 |
| 0xFFFFA40A | byte | CAN TX gate flag |
| 0xFFFFAAE0 | byte | CAN TX enable flag |
| 0xFFFFB5A4 | byte | CAN periodic TX mode flag |
| 0xFFFFB5E8 | byte | CAN TX inhibit flag 3 |
| 0xFFFFC241 | byte | CAN TX cycle complete flag |
| 0xFFFFCD2A | u16 | CAN time counter 1 |
| 0xFFFFCD28 | u16 | CAN time counter 2 |
| 0xFFFFCD2C-0xCD30 | byte[5] | Diagnostic status flags |
| 0xFFFFCCF4-0xCCFF | byte[12] | CAN timer control flags |
| 0xFFFFCCFA | byte | CAN RX valid flag |
| 0xFFFFCCFB-0xCCFC | byte[2] | CAN filter result flags |
| 0xFFFFCCFD-0xCCFF | byte[3] | CAN diagnostic status |
| 0xFFFFDE5C | byte | Current diagnostic session type |
| 0xFFFFD0F2 | byte | Security unlocked status |
| 0xFFFFD0F3 | byte | Security access flags |
| 0xFFFFD3F0 | byte[?] | KWP session context |
| 0xFFFFF754 | u16 | SSV/VFAD solenoid status bits (bit 0x0400 = VFAD status, repurposed by the [REDACTED] launch-control mod as "launch active") |
| 0xFFFF878C | u32 | CAN message buffer pointer |

---

## Call Graph Summary

```
main_init (0xD4B6)
  └─ canSetup (0xDC8C)
       ├─ CANControllerSetup (0x9878)
       │    ├─ getHCANRegisterAddress (0xD198)
       │    ├─ setCANRegisters (0xCC9C)
       │    ├─ set_MCR_bits2_3 (0xCB9C)
       │    └─ ...
       └─ canMessageSetup (0x2B320)
            ├─ canInitVals (0x2AFC8)
            └─ canRX_216_stubs? (0x29BB8)

someMainFunction (0x11540)
  └─ CANHandler (0x2A9BA)
       ├─ CANTX_Main (0xDDF0)  [TX path]
       │    ├─ can41TXPack (0x39348)
       │    ├─ can201TX_getAndPack (0x29B52)
       │    │    ├─ can201Pack (0x29B84)
       │    │    └─ getCAN201Values (0x29BC4)
       │    │         └─ stubCAN201Byte2_3 (0x29C1C)
       │    ├─ can203TX_getAndPack (0x29DC2)
       │    │    ├─ can203pack (0x29DF4)
       │    │    └─ getEngineTorqueMetricsForCAN (0x29E28)
       │    │         ├─ torqueCaltoCAN203_byte4 (0x29E92)
       │    │         └─ can203EngineStatusPack (0x29ED4)
       │    ├─ can251TX_getAndPack (0x2A3E2)  [throttle]
       │    │    └─ can215TXpack (0x2A414)
       │    ├─ can_tx_periodic_dispatch_2D402 (0x2D402)
       │    ├─ can240TX_pack (0x4C888)
       │    ├─ can250TX_pack (0x4C984)
       │    ├─ CANRX216TimeoutCount (0x299DA)
       │    ├─ can620TX_getAndPack (0x33A36)
       │    ├─ can_message_setup_dispatcher_33974 (0x33942)
       │    └─ can650TX_getAndPack (0x2C806)
       │
       └─ CANRX_Main (0xDBF6)  [RX path]
            ├─ CAN216RX_Main (0x29768)
            │    ├─ can216RXUnpack (0x29CE0)
            │    └─ can216RXParse? (0x298A4)
            ├─ CAN231TX_Main (0x29A1C)  [acknowledge reception]
            │    ├─ can231SetupTx (0x29A46)
            │    └─ can231TxPack (0x29A6E)
            ├─ CAN4B0RX_Main (0x2BE18)
            ├─ CAN212RX_Main (0x2C0C4)
            │    └─ can212RXUnpack (0x2C60A)
            ├─ CAN4C0RX_Main (0x2C0AC)
            ├─ CAN430RX_Main (0x33040)
            │    └─ can430rx_unpack (0x33BCA)
            ├─ ImmoMain (0x35202)  [immobilizer]
            ├─ CAN47RX_Main (0x3883C)
            │    └─ can47RXunpack (0x393D0)
            └─ CAN4B1RX_Main (0x4AF00)
                 └─ can4B1RXUnpack (0x4C7B2)

udsSomething? (0x67590)  [UDS entry]
  └─ udsHandler (0x697E8)  [UDS dispatch table]
       ├─ [SID 0x01] UDSMode1Function (0x6410C)  [OBD Mode 1]
       │    ├─ getEngineLoadforOBD?? (0x53530)
       │    ├─ getCoolantTempforOBD?? (0x53590)
       │    ├─ getSTFTforOBD?? (0x535A6)
       │    ├─ getLTFTforOBD??? (0x535CC)
       │    ├─ getRPMforOBD?? (0x535EA)
       │    ├─ getVehicleSpeedForOBD?? (0x53600)
       │    ├─ getIgnLeadingOBD (0x53614)
       │    ├─ getIATOBD (0x53678)
       │    ├─ getMAFOBD?? (0x5368E)
       │    └─ getThrottlePlatePosForOBD?? (0x536B6)
       ├─ [SID 0x09] OBDMode9Fuction (0x64BB0)
       ├─ [SID 0x10] UDSMode10Func (0x5615C)
       ├─ [SID 0x11] UDSService11Function? (0x59744)
       ├─ [SID 0x22] UDSService22Function (0x54B04)
       ├─ [SID 0x23] UDSMode23Function (0x59F40)
       │    └─ getMemoryFromRAMForUDS23 (0x59FDC)
       ├─ [SID 0x27] UDSService27Function (0x55F34)  [Security]
       ├─ [SID 0x28] UDSMode28Func (0x5A1E6)
       ├─ [SID 0x2F] udsService2FFunc (0x5A43C)
       ├─ [SID 0x31] udsMode31Func (0x5C750)
       ├─ [SID 0x33] UDSMode33Func (0x5C8BE)
       ├─ [SID 0x34] UDSMode34Func (0x5BFAC)
       ├─ [SID 0x36] UDSMode36Function? (0x5C024)
       ├─ [SID 0x37] UDSService37Function (0x5C064)
       ├─ [SID 0x85] UDSMode85Func (0x5C434)
       └─ [SID 0xB1] UDSServiceB1Function (0x54904)

DTC Infrastructure:
  dtcRelated (0x62002)
    ├─ dtc_code_set_46780 (0x46780)
    ├─ dtc_snapshot_store_467BE (0x467BE)
    ├─ obd_freeze_frame_467D0 (0x467D0)
    ├─ dtc_debounce_monitor_43760 (0x43760)
    ├─ dtc_o2_circuit_fault_45F54 (0x45F54)
    ├─ dtc_o2_response_time_45F9C (0x45F9C)
    ├─ dtc_catalyst_efficiency_45FAC (0x45FAC)
    ├─ dtc_p0100_maf_46DA0 (0x46DA0)
    ├─ dtc_p0120_tps_46DCA (0x46DCA)
    ├─ dtc_p0130_o2_46DD2 (0x46DD2)
    ├─ dtc_p0300_misfire_46E44 (0x46E44)
    ├─ dtc_misfire_detection_468D6 (0x468D6)
    ├─ dtc_p0500_speed_47066 (0x47066)
    └─ dtc_p0600_pwr_471A2 (0x471A2)
```

---

## Key Findings

### 1. CAN Dispatch is Table-Driven with Two Paths

Unlike the KWP2000 serial handler which is a flat series of if-else branches,
the CAN layer has two distinct dispatchers:
- **`CANTX_Main`**: Sequential call chain (not table-driven) — each TX pack function
  is called in order every cycle
- **`CANRX_Main`**: Table-driven dispatch by CAN ID — each RX function handles
  one CAN ID

### 2. UDS Has TWO Protocol Stacks

The firmware contains **both**:
- **KWP2000 (ISO-14230)** over SCI serial: Functions at 0x1572-0x1D98
  (older protocol, uses physical serial SCI channel)
- **UDS (ISO-14229-1)** over CAN: Functions at 0x6410C-0x697E8
  (newer protocol, uses CAN IDs 0x7DF/0x7E0/0x7E8)

Both stacks are compiled in, likely for compatibility with different
diagnostic tools.

### 3. UDS Handler Uses 12-Byte Dispatch Table Entries

The `udsHandler` dispatch table has entries of the form:
```c
struct UDSDispatchEntry {
    uint8_t  sid;         // Service ID to match
    uint8_t  pad[3];      // Padding (zero)
    uint32_t handler;     // Function pointer
    uint8_t  access_flags;// Required session type mask
    uint8_t  pad2[3];     // Padding
};
```

### 4. Security Access Key at Fixed ROM Location

The 5-byte security key constant is at 0x5FAC0 in 60E1D400:
- Stock: `"MazdA"`
- [REDACTED]: vendor-family secret (removed for privacy)
- [REDACTED]: `"[REDACTED]"`

LFSR polynomial parameters at 0x5FAC8.

### 5. CAN Message Timing Uses a Gated Counter

`CANTX_Main` checks a counter at 0xFFFFA40F that must be < 100 for TX to proceed.
Various enable flags (0xA40A, 0xFFFFA410, 0xFFFFA411) can gate TX entirely.
This allows the ECU to stop CAN traffic during critical operations or fault states.

### 6. CAN Filter Uses FPU-Based Condition Evaluation

The `can_filter_apply_49216` function uses the FPU extensively — reading RPM,
vehicle speed, acceleration as floats, comparing against thresholds, and setting
diagnostic flags. This is unusual for a filter function but makes sense for
DSC/ESP condition monitoring where hysteresis and scaling are needed.

---

## Relationship Diagram

```
┌─────────────────────────────────────────────┐
│                 CAN Bus                      │
│  IDs: 0x041, 0x201, 0x203, 0x215, 0x231,   │
│  0x240, 0x250, 0x420, 0x620, 0x650 (TX)    │
│  IDs: 0x212, 0x216, 0x430, 0x47, 0x4B0,    │
│  0x4B1, 0x4C0 (RX)                          │
│  IDs: 0x7DF, 0x7E0, 0x7E8 (UDS Diagnostic)  │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│           CAN Hardware Layer                 │
│  HCAN Controller (mailbox 0-15)             │
│  can_set_mailbox_*, can_pack_tx_*, etc.     │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│          CAN Message Layer                   │
│  ┌─────────┐       ┌───────────┐            │
│  │CANTX_Main│       │CANRX_Main │            │
│  │ (0xDDF0) │       │ (0xDBF6)  │            │
│  └────┬────┘       └─────┬─────┘            │
│       │                  │                   │
│  ┌────▼────┐       ┌─────▼─────┐            │
│  │TX Packs │       │RX Unpacks │            │
│  │per ID   │       │per ID     │            │
│  └─────────┘       └───────────┘            │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│     UDS / OBD / DTC Service Layer            │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │      udsHandler (0x697E8)            │    │
│  │      ┌────┬────┬────┬────┬────┐      │    │
│  │      │SID │SID │SID │SID │SID │      │    │
│  │      │0x01│0x10│0x27│0x34│... │      │    │
│  │      └─┬──┴─┬──┴─┬──┴─┬──┴─┬─┘      │    │
│  │        │    │    │    │    │          │    │
│  │  ┌─────▼──┐ │ ┌──▼──┐ │ ┌──▼───┐     │    │
│  │  │OBD Mode│ │ │Secur│ │ │Flash │     │    │
│  │  │1  (PID)│ │ │Access│ │ │Prog  │     │    │
│  │  └────────┘ │ └─────┘ │ └──────┘     │    │
│  └──────────────────────────────────────┘    │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │      DTC Subsystem                    │    │
│  │  dtc_code_set → snapshot_store →     │    │
│  │  dtc_debounce_monitor → dtcRelated   │    │
│  │  obd_freeze_frame                    │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

---

## Verification Summary (July 2026)

### What Was Verified

| Component | Status | Notes |
|-----------|--------|-------|
| UDS Dispatch Table @ 0x5F57C | ✅ VERIFIED | All 28 entries + 0xFF sentinel, addresses match documentation |
| `udsHandler` @ 0x697E8 | ✅ VERIFIED | Central UDS dispatch, reads table, checks session access |
| `CANTX_Main` @ 0xDDF0 | ✅ VERIFIED | Counter-based rate limiting, corrected function names |
| `secondary_system_controller` @ 0xDE8E | ✅ VERIFIED | Actual CAN RX dispatch (not `CANRX_Main` at 0xDBF6 as previously thought) |
| Security key "MazdA" @ 0x5FAC0 | ✅ VERIFIED | 5-byte ASCII key, LFSR params at 0x5FAC8 |
| CAN Config Table @ 0x4EA60 | ✅ VERIFIED | 16-entry mailbox configuration (NOT runtime dispatch) |
| CAN Config Table Alt @ 0x4EB60 | ✅ VERIFIED | Alternate mailbox config |
| CAN1 RX Config @ 0x4EC60 | ✅ VERIFIED | 6-entry CAN1 mailbox config |

### What Was Corrected

1. **CAN RX dispatch**: Previously documented as `CANRX_Main` at 0xDBF6. Actual function is `secondary_system_controller` at 0xDE8E. Several RX handler addresses were from [REDACTED] ROM, not 60E1D400.

2. **OBD handler addresses**: Previously documented as 0x6410C (Mode 1) and 0x64BB0 (Mode 9). Verified UDS dispatch table shows 0x66258 and 0x66CFC respectively.

3. **CAN TX function names**: Several TLAs (three-letter acronyms) in the TX chain were misleading. The actual function names (`mutex_trylock_4C85A`, `message_queue_send_4C956`, etc.) better describe their counter-based dispatch behavior.

4. **CAN config table interpretation**: The 16-byte table entries are mailbox configuration structures (buffer pointers, not function pointers). The "handler" fields point to mailbox data buffer areas, not code.

### What Remains to Be Verified

- **OBD PID helper functions**: The specific conversion helpers (RPM→OBD, temp→OBD, etc.) are at different addresses in 60E1D400 vs [REDACTED]. Their exact locations need tracing through the Mode 1 dispatcher.
- **DTC handler dispatch**: The `dtcRelated` (0x62002) function and its sub-handlers need full decompilation verification.
- **KWP2000 serial protocol**: The legacy serial diagnostics at 0x1572-0x1D98 need verification against the CAN-based UDS stack.

## Files Referenced

- **ROM binary**: `roms/stock/60E1D400.bin`
- **Symbol table**: `symbols/symbols_60E1D400_merged.csv`
- **IDA symbols**: `symbols/symbols_60E1D400_ida.csv`
- **Call graph**: `symbols/callgraph.csv`
- **CAN protocol notes**: `docs/notes/CAN_PROTOCOL.md`
- **Function docs**: `docs/functions/*.md`
- **All findings**: `docs/notes/FINDINGS.md`
- **Verification script**: `tools/verify_uds_table2.py` (not shipped; generated during analysis)
