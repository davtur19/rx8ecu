# Mazda RX-8 CAN Protocol

## Overview

The RX-8 uses **two CAN buses**:
- **HS-CAN** (OBD-II pins 6/14): ECU diagnostics, UDS
- **MS-CAN** (OBD-II pins 3/11): accessories (not used for ECU access)

Mazda RX-8 CAN messages are **proprietary broadcast** — they are NOT standard OBD2. A generic ELM327/OBD2 reader only sees 0x7DF/0x7E0/0x7E8 (UDS diagnostic). All engine-data messages use Mazda-specific IDs.

---

## CAN Controller Configuration Tables

In ROM 60E1D400, three CAN mailbox configuration tables exist:
- **CAN0 TX Config**: `0x4EA60` (primary), `0x4EB60` (alternate, used when 0xB5A4==0)
- **CAN1 RX Config**: `0x4EC60`

These tables configure the HCAN mailboxes (CAN ID, DLC, RX/TX direction). They are **not** runtime dispatch tables — the runtime dispatch is done by direct function calls.

### Entry Format (16 bytes)

```
Offset  Size  Endian Description
 0       2     BE    Reserved (0x0000)
 2       2     BE    CAN ID (11-bit, left-justified in 16-bit field)
 4       2     BE    Mailbox slot + direction flag (bit 7 of byte 4 = 1 for RX)
 6       1     -     DLC (data length code, 0-8)
 7       1     -     Reserved (0x00)
 8       2     -     Separator (0xFFFF)
10       2     BE    Buffer pointer low (data area offset)
12       1     -     Buffer pointer high
13       1     -     Reserved (0x00)
14       2     -     Reserved (0x0000)
```

### CAN0 TX Mailbox Configuration (0x4EA60)

| CAN ID | Mailbox | DLC | Dir | Buffer Ptr | Description |
|--------|---------|-----|-----|------------|-------------|
| 0x0201 | MB1     | 8   | TX  | 0x01BB5C   | RPM / vehicle speed / accel (field-verified — see "Field vs firmware") |
| 0x0203 | MB2     | 7   | TX  | 0x01BB78   | Engine torque / status |
| 0x0215 | MB3     | 8   | TX  | 0x01BB9C   | Throttle position |
| 0x0231 | MB4     | 5   | TX  | 0x01BCC4   | Engine state (RPM, load, coolant) — *field data differs* (gear selector / MT-AT split): OPEN, needs bench verification |
| 0x0231 | MB4     | 5   | TX  | 0x01BB48   | Engine state (alternate) |
| 0x0420 | MB5     | 7   | TX  | 0x01BB0C   | Coolant temp gauge + MIL/warning lamps (field-verified — see "Field vs firmware") |
| 0x0620 | MB6     | 7   | TX  | 0x01C054   | Fan/AC status |
| 0x0630 | MB7     | 8   | TX  | 0x01C044   | Cooling fan data |
| 0x0650 | MB8     | 1   | TX  | 0x01BC68   | Cruise-control lamps (field-verified — see "Field vs firmware") |
| 0x0041 | MB9     | 8   | TX  | 0x01C518   | KCM keyless/immobiliser response (field-verified — see "Field vs firmware") |
| 0x0240 | MB10    | 8   | TX  | 0x01CEA4   | Transmission / gear — *byte3 = coolant?* per field: OPEN, needs bench verification |
| 0x0250 | MB11    | 8   | TX  | 0x01CEB8   | Injection pulse width — *byte3 = IAT* per field: OPEN, needs bench verification |
| 0x04B1 | MB12    | 8   | TX? | 0x01CE90   | DSC request (bidirectional?) |
| 0x07DF | MB13    | 8   | RX  | 0x0DE04    | UDS broadcast request |
| 0x07E0 | MB14    | 8   | RX  | 0x0DE04    | UDS physical request |
| 0x07E8 | MB15    | 8   | TX  | 0x0DE0C    | UDS diagnostic response |

### CAN1 RX Mailbox Configuration (0x4EC60)

| CAN ID | Mailbox | DLC | Dir | Buffer Ptr | Description |
|--------|---------|-----|-----|------------|-------------|
| 0x0212 | MB1     | 7   | RX  | 0x01BC28   | ABS/DSC/brake lamps (field-verified — see "Field vs firmware") |
| 0x0216 | MB2     | 8   | RX  | 0x01BB20   | Unknown |
| 0x0430 | MB4     | 7   | RX  | 0x01C060   | Instrument cluster presence (field data; immo role unconfirmed — see "Field vs firmware") |
| 0x04B0 | MB5     | 8   | RX  | 0x01BC08   | DSC/ESP data (wheel speeds FL/FR/RL/RR) |
| 0x04C0 | MB6     | 1   | RX  | 0x01BC64   | Short message |
| 0x0047 | MB7     | 8   | RX  | 0x01C520   | KCM keyless/immobiliser request (field-verified — see "Field vs firmware") |

**Note**: The "Buffer Ptr" fields are mailbox data buffer offsets in RAM, not function pointers. They point into the HCAN mailbox register space (0xFFFFExxx).

---

## Run-time CAN Dispatch (60E1D400)

Unlike the configuration tables, the actual run-time dispatch is done by two functions:

### CAN TX: `CANTX_Main` (0xDDF0)

Called periodically from the main loop. Uses counter-based rate limiting:

```
CANTX_Main:
  Gate check: 0xA40F < 100, 0xA40A==0, 0xA410==0, 0xA411==0, 0xAAE0==1, 0xB5E8!=1

  [per-cycle] can41TXPack(0x39348)        → CAN ID 0x041 (KCM/immobiliser response - 8 bytes)
  [every 4]   FUN_00029fd2(0x29FD2)       → Sub-dispatches CAN 0x201+0x203 handlers
  [every N]   counter_check_dispatch_2A242 → CAN ID 0x215? (throttle)
  [per-cycle] can251TX_getAndPack(0x2AAB6) → CAN ID 0x251 (throttle position)
  [if flag]   can_tx_periodic_dispatch_2D402 → CAN ID 0x231 (engine data)
  [every 25]  mutex_trylock_4C85A(0x4C85A) → calls can240TX_pack(0x4C888) → CAN 0x240
  [every 25]  message_queue_send_4C956     → calls can250TX_pack(0x4C984) → CAN 0x250
  [per-cycle] incr_counter_saturated_299DA → CAN RX 216 timeout counter
  [per-cycle] saturated_counter_dispatcher_33A36 → CAN ID 0x620 (fan/AC)
  [per-cycle] saturated_counter_dispatcher_33942 → CAN ID 0x630 (cooling fan)
  [per-cycle] can650TX_getAndPack(0x2C806) → CAN ID 0x650 (cruise-control lamps)

  Clear flag at 0xC241
```

### CAN RX: `secondary_system_controller` (0xDE8E)

Called after CANTX_Main. Sequential dispatch:

```
secondary_system_controller:
  Gate check: 0xAAE0==1, 0xB5E8!=1, 0xA410==0

  CAN212RX_Main(0x2C0C4)        → CAN ID 0x212 (ABS/DSC/brake lamps, unpack to 0xBC28+)
  lookup_table_indexed_29BE8    → Unknown table lookup
  [if 0xB5A4==0] table_lookup_dispatch_29E9C → Various
  table_lookup_conditional_dispatch_33BA0 → CAN 0x430/0x4C0 (cluster presence + misc)
  CAN4B0RX_Main(0x2BE18)        → CAN ID 0x4B0 (DSC/ESP = wheel speeds, CAN1 MB5)
  event_check_4C78C             → CAN ID 0x4B1 (DSC request, CAN0 MB12)
  utility_bitfield_check_2C780  → CAN ID 0x4C0 (short DLC=1 msg)
  CAN47RX_Main(0x3939C)         → CAN ID 0x47 (KCM/immobiliser request, CAN1 MB7)
```

---

## Known Proprietary Broadcast IDs

> Description column: **field-verified meanings** (per
> `can_protocol/verification/field_vs_firmware.md` and
> `can_protocol/rx8club_thread_276101_CAN_map.txt`) replace
> earlier firmware-guess labels. DLC/dir/ID come from the firmware mailbox
> config and are unchanged. See "Field vs firmware" at the end of this file.

| ID | Mailbox | TX/RX | Content |
|----|---------|-------|---------|
| 0x041 | CAN0 MB9 | TX    | KCM keyless/immobiliser response (key-on chat; per-cycle idle frame) |
| 0x201 | CAN0 MB1 | TX    | RPM (u16 BE ÷4), vehicle speed (u16 BE (raw−10000)/100), accelerator (byte6 ÷2) |
| 0x203 | CAN0 MB2 | TX    | Engine torque, status |
| 0x212 | CAN1 MB1 | RX    | ABS/DSC/brake lamps (byte3 DSC-off, byte4 brake/handbrake+ABS, byte5 TCS) |
| 0x215 | CAN0 MB3 | TX    | Throttle position |
| 0x216 | CAN1 MB2 | RX    | Unknown (received by ECU) |
| 0x231 | CAN0 MB4 | TX    | Engine state / gear selector — *field data differs* (MT/AT DLC split): OPEN, needs bench verification |
| 0x240 | CAN0 MB10| TX    | Transmission / gear data — *byte3 = coolant?* per field: OPEN, needs bench verification |
| 0x250 | CAN0 MB11| TX    | Injection pulse width, fuel — *byte3 = IAT* per field: OPEN, needs bench verification |
| 0x420 | CAN0 MB5 | TX    | Coolant temp gauge (byte0 raw−40) + MIL/oil/batt/water warning lamps |
| 0x430 | CAN1 MB4 | RX    | Instrument cluster presence (immo role unconfirmed) |
| 0x47  | CAN1 MB7 | RX    | KCM keyless/immobiliser request (key-on chat) |
| 0x4B0 | CAN1 MB5 | RX    | Wheel speeds FL/FR/RL/RR (4× u16 (raw−10000)/100 km/h) |
| 0x4B1 | CAN0 MB12| RX    | DSC request |
| 0x4C0 | CAN1 MB6 | RX    | Unknown (short DLC=1) |
| 0x620 | CAN0 MB6 | TX    | Fan status, AC |
| 0x630 | CAN0 MB7 | TX    | Cooling fan data |
| 0x650 | CAN0 MB8 | TX    | Cruise-control lamps (1 byte: bit6 active, bit7 main) |
| 0x7DF | CAN0 MB13| RX    | UDS broadcast (OBD-II) |
| 0x7E0 | CAN0 MB14| RX    | UDS physical request |
| 0x7E8 | CAN0 MB15| TX    | UDS diagnostic response |

---

## Rotarytronics CAN Patch

A known third-party patch that modifies CAN frame content to make normally-hidden parameters visible to dataloggers:

- **0x630 handler** (`0x1C044` in the J-line variant): adds fan status byte
- **0x250 handler** (`0x1CEB8` in the J-line variant): adds injection pulse width byte

These handlers are **not** accessible via standard OBD2 — a custom CAN logger (e.g., OBDX Pro or Tactrix in raw CAN mode) is required to read them.

---

## OBD2 / UDS (Standard Diagnostic)

- ECU responds to 0x7DF (broadcast) and 0x7E0 (unicast)
- Physical response address: 0x7E8
- Mailbox config at 0x4EA60 entries 13-15
- All UDS communication goes through `udsHandler` (0x697E8) dispatched via table at 0x5F57C
- UDS entry point from CAN: `udsEntryPoint` (0x69702) → `udsHandler`
- Known DIDs (SID 0x22): `0xF190` VIN, `0xF18C` Calibration ID, `0xE611` Calibration
  Hex File (ASCII) — full DID/SID detail in `docs/hardware/RX8_OBD_UDS_Protocol.txt`.

---

## Field vs firmware (cross-check summary)

Cross-check of the firmware mailbox configuration (ID sets above, ROM 60E1D400)
against **field-observed** RX-8 HS-CAN frame decodes from public captures/blogs
(topolittle, Antipixel, rusEFI, majbthrd.kcd, Blackhurst, cham, jimkoeh, CC3301…).

**Bottom line:** the ID sets agree exactly; the disagreements are in the
*byte-level semantics* / frame purpose, not in which IDs exist. The firmware
table's earlier "Description" column was written from guesses about the mailbox
buffers, not from traced packing functions.

| Verdict | IDs |
|---------|-----|
| **AGREE** (9) | 0x203, 0x215 (loose), 0x620, 0x630, 0x4B0, 0x4C0, 0x7DF, 0x7E0, 0x7E8 |
| **DISAGREE** (7) | 0x201 (name), 0x420, 0x650, 0x041, 0x212, 0x430, 0x047 |
| **PARTIAL / byte-level** (3) | 0x231 (content / MT-AT split), 0x240 (byte3), 0x250 (byte3) |
| **UNKNOWN** (2) | 0x216, 0x4B1 |

Field-decoded meanings for the 7 disagreements are marked with confidence
tier **[A]** (≥2 independent sources; 0x041/0x047 confirmed on two cars). The 3
"PARTIAL" rows are **OPEN — need bench/Ghidra verification** (see the open
conflicts in the verification file).

Source: `can_protocol/verification/field_vs_firmware.md`
(+ `can_protocol/rx8club_thread_276101_CAN_map.txt`).
