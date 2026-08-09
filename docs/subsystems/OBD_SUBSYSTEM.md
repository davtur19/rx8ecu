# OBD-II Subsystem — RX-8 ECU (60E1D400)

**ISO-15031 (OBD-II / SAE J1979)** emissions diagnostics. Shares CAN transport + message framing with UDS (ISO-14229), but has its own service IDs and PID-based data access model.

Supported modes: **Mode 1** (SID 0x01) current data by PID · **Mode 2** (0x02) freeze frame · **Mode 3** (0x03) stored DTCs · **Mode 4** (0x04) clear DTCs · **Mode 5** (0x05) oxygen sensor monitoring · **Mode 6** (0x06) non-continuous tests · **Mode 7** (0x07) pending DTCs · **Mode 8** (0x08) component control · **Mode 9** (0x09) vehicle info.

## Architecture

UDS Dispatch Table @ **0x5F57C** — 12 bytes/entry, 1-indexed SID→handler mapping:

| SID | Handler |
|-----|---------|
| 0x01 | UDSMode01Handler @ 0x66258 |
| 0x02 | UDSMode02Handler @ 0x66314 |
| 0x03 | UDSMode03Handler @ 0x66AF4 |
| 0x04 | UDSMode04Handler @ 0x66B1A |
| 0x05 | UDSMode05Handler @ 0x66B44 |
| 0x06 | UDSMode06Handler @ 0x66C9C |
| 0x07 | UDSMode07Handler @ 0x66BFC |
| 0x08 | UDSMode08Handler @ 0x66C9C (shared with 0x06) |
| 0x09 | UDSMode09Handler @ 0x64BB0 |

## Mode 1: Show Current Data

### Entry Point: UDSMode01Handler @ 0x66258

```
UDSMode01Handler(request, response):
  pid = request[6]                        // PID byte
  if pid < 1 or pid > 63: return error    // PID out of range
  entry_addr = 0x5F6D8 + (pid - 1) * 32   // PID table
  word0 = *(uint16_t*)(entry_addr)        // entry type
  word1 = *(uint16_t*)(entry_addr + 2)    // handler ptr OR data address/offset
  if word0 == 0xFFFF:
    result = (*word1)(pid, response)      // direct handler
  else:
    // direct data copy: word0 = response byte count, word1 = lookup key/index
```

### PID Table Format @ 0x5F6D8

Each entry 32 bytes; first two words (4 bytes) determine the type:

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| +0 | u16 | type | `0xFFFF` = handler function; otherwise = PID response byte count |
| +2 | u16 | data | `0xFFFF` type: function pointer. Otherwise: data address/offset |
| +4..31 | - | pad | Reserved |

**Entry types**
1. **Handler** (type == `0xFFFF`): call handler at `data` (for example PID 0x0C RPM, 0x0D Speed).
2. **Direct data** (type != `0xFFFF`): response data looked up indirectly; `type` = byte count, `data` = lookup key/index (for example PIDs 0x00-0x0B group inquiry, 0x10-0x18 group data).

### Handler Functions (called from PID table)

| PID | Function | Address | Description |
|-----|----------|---------|-------------|
| 0x0C | getRPMOBDHandler | 0x55E7C | RPM (0-16383.75 rpm, A/4) |
| 0x0D | getSpeedOBDHandler | 0x55EA2 | Vehicle speed (0-255 km/h) |
| 0x0E | getTimingAdvOBDHandler | 0x55E66 | Timing advance (-64 to 63.5 deg) |
| 0x0F | getIATOBDHandler | 0x55E18 | Intake air temperature |
| 0x10-0x18 | group handlers | various | MAF airflow, throttle position |

## OBD Sensor Value Pipeline

```
Raw Sensor → Sensor Processing → Float RAM Value → OBD Getter (float→OBD-scaled uint16)
      → OBD CAN TX Buffer (0xFFFFCEAC-0xFFFFCEC7) → CAN TX (ID 0x240/0x250)
```

### Sensor RAM Addresses (intermediate float values)

| Address | Sensor | Unit | Range |
|---------|--------|------|-------|
| 0xFFFFAA10 | Engine Load | float (%) | 0..100 |
| 0xFFFFAE64 | RPM count | float | 0..16383 |
| 0xFFFFB140 | Vehicle Speed | float (km/h) | 0..255 |
| 0xFFFFC12C | Intake Air Temp 1 | float (°C) | -40..215 |
| 0xFFFFC130 | Intake Air Temp 2 | float (°C) | -40..215 |
| 0xFFFFA63C | Short-Term Fuel Trim | float (%) | -100..100 |
| 0xFFFF9F60 | Long-Term Fuel Trim (bank 1) | float (%) | -100..100 |
| 0xFFFF9F70 | MAF Air Flow | float (g/s) | 0..655 |

### OBD CAN TX Buffers

| Address | Content | CAN ID |
|---------|---------|--------|
| 0xFFFFCEAC..CEB3 | OBD bytes 0..7 | 0x240 |
| 0xFFFFCEB4..CEC7 | OBD bytes 0..19 | 0x250 |

### Entry Points for CAN TX

- **getOBDCANTXVars1** @ 0x4C8C2 — collects 8 bytes for CAN ID 0x240
- **getOBDCANTXVars2** @ 0x4C9C0 — collects 20 bytes for CAN ID 0x250

## OBD Getter Functions

Per-PID conversion functions — the core of the OBD data pipeline. Pattern: load float sensor val from RAM → load scale/offset constants → call shared `floatToOBDBounded` @ 0x24D0 → return uint16 for CAN packing.

```
uint16_t floatToOBDBounded(float sensor_val, float scale, float offset, uint16_t max_val)
{
    float tmp = (sensor_val - offset) / scale;
    int32_t result = (int32_t)(tmp + 0.5f);        // round to nearest
    if (result > max_val) result = max_val;         // clamp [0, max_val]
    if (result < 0)       result = 0;
    return (uint16_t)result;
}
```

**Arguments:** fr4 = `sensor_val` (raw float) · fr5 = `scale` · fr6 = `offset` · r5 = `max_val` (typically 0xFF).

**Formula:** `OBD_value = clamp((sensor_val - offset) / scale + 0.5, 0, max_val)`

### Per-PID Getter Reference

| Getter | Addr | Input (RAM float) | scale / offset | Result / formula & notes |
|--------|------|-------------------|----------------|--------------------------|
| getEngineLoadOBD | 0x55D9A | *0xFFFFAA10 | status-derived | Engine load % (0..100). Complex: status checks at 0xFFFFAE97, 0xFFFFAD9C, 0xFFFFAE96; handles sensor failure/limp |
| getIATOBD | 0x55E18 | *0xFFFFC12C pri, *0xFFFFC130 fallback | 0.39215684f / -40 | `clamp((iat1+40)/0.392157+0.5,0,255)`. °C + 40 offset; gain 9.999999e-06 |
| getRPMOBD | 0x55E7C | *0xFFFFAE64 | const / -1.0 | `clamp(((rpm_count-1)*100.0)/scale+0.5,0,65535)`. OBD value = RPM/4 |
| getSpeedOBD | 0x55EA2 | *0xFFFFB140 | const / 0 | `clamp(speed/scale+0.5,0,255)`. km/h |
| getMAFOBD | 0x55E66 | *0xFFFF9F70 | ~0.15625 / -100 | Direct map of MAF to PID 0x10 |
| getTimingAdvOBD | 0x55E7C | (shared with RPM) | - | Timing advance in deg × 2 (OBD standard) |
| getSTFTOBD | 0x55EEA | *0xFFFFA63C | 0.5 / -64 | `clamp((stft+64)*2+0.5,0,255)`. OBD: A=128→0%; % = (A-128)*100/128; range -64%→0, 0%→128, 63.5%→255 |
| getLTFTOBD | 0x55F02 | *0xFFFF9F60 | 1.0 / -40 | `clamp(ltft+40.5,0,255)`. Same % format; scale differs from STFT |
| getLambdaOBD | 0x55F7A | sensor (computed from commanded AFR) | multi-stage | `result = λ × 10000` (OBD: A/10000 = λ). Multiple FMUL stages |
| getThrottleOBD | 0x55F64 | *sensor_addr | - | Throttle position % (0..100) |

## Mode 2: Freeze Frame @ 0x467D0

```
FreezeFrameHandler(request, response):
  if emission_related_dtc_stored():
    if freeze_frame_valid():
      copy_snapshot_to_response(); return
  response_empty()
```

Freeze frame buffer holds pre-computed OBD-scaled values for all supported PIDs, captured atomically when the DTC was set.

## Mode 9: Vehicle Information @ 0x64BB0

```
UDSMode09Handler(request, response):
  subfunction = request[6]
  switch subfunction:
    0x01 → return VIN
    0x02 → return ECU name / calibration ID
    0x03 → return CVN (calibration verification number)
    0x04 → return in-use performance tracking data
    default → return supported PIDs list
```

## Data Flow: PID Request → CAN Response

```
OBD Scanner → CAN 0x7DF (broadcast) / 0x7E0 (functional)
  → CANRX_Main → udsHandler @ 0xDFD4 → UDSMode01Handler @ 0x66258
  → PID Table Lookup @ 0x5F6D8:
      Handler entry → call handler → floatToOBDBounded @ 0x24D0 → store @ 0xFFFFCEAC+
      Data entry   → copy pre-formatted response
  → Response → CAN 0x7E8 (tool response)
```

## Key Function Reference

| Address | Function | Description |
|---------|----------|-------------|
| 0x24D0 | floatToOBDBounded | Core float→uint16 OBD converter |
| 0x5F57C | udsDispatchTable | UDS SID→handler dispatch table |
| 0x5F6D8 | obdPidTable | PID→handler/data lookup table |
| 0x55D9A | getEngineLoadOBD | Engine load % getter |
| 0x55E14 | getCoolantTempOBD | Coolant temp getter (trivial stub, returns 0) |
| 0x55E18 | getIATOBD | Intake air temp getter |
| 0x55E66 | getMAFOBD / getTimingAdvOBD | MAF/timing advance getter |
| 0x55E7C | getRPMOBD | RPM getter |
| 0x55EA2 | getSpeedOBD | Vehicle speed getter |
| 0x55EEA | getSTFTOBD | Short-term fuel trim getter |
| 0x55F02 | getLTFTOBD | Long-term fuel trim getter |
| 0x55F64 | getThrottleOBD | Throttle position getter |
| 0x55F7A | getCommandedLambdaOBD | Commanded lambda getter |
| 0x4C8C2 | getOBDCANTXVars1 | Assemble CAN 0x240 OBD frame |
| 0x4C9C0 | getOBDCANTXVars2 | Assemble CAN 0x250 OBD frame |
| 0x3ED7C | readU16WithComplement | RAM read with complement validation |
| 0x467D0 | FreezeFrameHandler | Freeze frame snapshot handler |
| 0x64BB0 | UDSMode09Handler | Vehicle info handler |
| 0x66258 | UDSMode01Handler | Mode 1 main handler |
| 0x66372 | UDSMode01DefaultHandler | Default PID response path |
| 0x663BC | UDSMode01AlternateHandler | Alternate PID response path |
| 0x670B4 | obdCheckPIDSupported | PID support bitfield check |
| 0x670E6 | obdGetPIDTableEntry | Computes PID table entry address |

## OBD Response CAN IDs

| CAN ID | Direction | Content |
|--------|-----------|---------|
| 0x7DF | RX (broadcast) | OBD scan tool request (Mode 1/2/9) |
| 0x7E0 | RX (functional) | OBD scan tool request (addressed to ECU) |
| 0x7E8 | TX | OBD response to scan tool |
| 0x240 | TX (periodic) | Current data snapshot (8 bytes) |
| 0x250 | TX (periodic) | Extended data snapshot (20 bytes) |

## Constants Reference

| Address | Value | Usage |
|---------|-------|-------|
| 0x24F8 | 0x00FF | Max clamp value (255) for conversion |
| 0x24FC | 0x3F000000 | 0.5f rounding constant (floatToOBDBounded) |
| 0x55F34 | 0x42C80000 | 100.0f % scale factor |
| 0x55F38 | 0x3EC8C8C8 | 0.39215684f IAT conversion scale |
| 0x55F44 | 0xC2200000 | -40.0f temperature offset |
| 0x55F48 | 0xC2C80000 | -100.0f negative offset |
| 0x55F4C | 0x3F480000 | 0.78125f fuel trim conversion? |
| 0x55F58 | 0xC2800000 | -64.0f STFT offset |
| 0x55F5C | 0x3F000000 | 0.5f STFT scale |

## RAM Variable Mapping (Sensor Values)

Refer to `SENSOR_PIPELINE.md` for the complete mapping. OBD getter inputs:

```
0xFFFF9F60 — LTFT bank 1 (float, %)
0xFFFF9F70 — MAF airflow (float, g/s)
0xFFFFA63C — STFT (float, %)
0xFFFFAA10 — Engine load (float, %)
0xFFFFAD9C — Sensor valid / status flag (byte)
0xFFFFAE64 — RPM count (float)
0xFFFFAE96 — Sensor status register (byte)
0xFFFFAE97 — Sensor validity flags (byte)
0xFFFFB140 — Vehicle speed (float, km/h)
0xFFFFC12C — IAT sensor 1 (float, °C)
0xFFFFC130 — IAT sensor 2 (float, °C)
0xFFFFCEAC — OBD CAN TX buffer start
0xFFFFCEC7 — OBD CAN TX buffer end
```

## Notes

1. Not all PID handlers fully decompiled — some branches (failure/limp modes) depend on status registers set by other runtime subsystems.
2. `getCoolantTempOBD` @ 0x55E14 is a trivial stub returning 0; coolant temp OBD data may route through a different path.
3. Conversion constants for some getters differ from theoretical OBD standard values — manufacturer-specific calibration adjustments.
4. UDS Mode 22 (DID-based) handlers @ 0x630A4+ are separate from the OBD PID handlers and serve proprietary diagnostic data requests.
