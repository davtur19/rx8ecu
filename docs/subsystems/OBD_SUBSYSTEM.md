# OBD-II Subsystem — RX-8 ECU (60E1D400)

## Overview

The RX-8 ECU firmware implements **ISO-15031 (OBD-II / SAE J1979)** diagnostic services for
emissions-related diagnostics. OBD-II shares the same transport layer as UDS (ISO-14229) and
uses the same CAN message framing, but has its own service IDs (SID) and PID-based data
access model.

The OBD subsystem supports:

- **Mode 1** (SID 0x01): Show current data — read live sensor values by PID
- **Mode 2** (SID 0x02): Show freeze frame data
- **Mode 3** (SID 0x03): Show stored DTCs
- **Mode 4** (SID 0x04): Clear/reset DTCs
- **Mode 5** (SID 0x05): Test results, oxygen sensor monitoring
- **Mode 6** (SID 0x06): Test results, non-continuously monitored
- **Mode 7** (SID 0x07): Show pending DTCs
- **Mode 8** (SID 0x08): Control operation of on-board component/system
- **Mode 9** (SID 0x09): Request vehicle information

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    UDS Dispatch Table (0x5F57C)                   │
│   SID -> handler mapping, 12 bytes/entry, 1-indexed              │
├──────────────────────────────────────────────────────────────────┤
│                ┌─ SID 0x01 → UDSMode01Handler (0x66258)          │
│                │                                                 │
│                │   ┌─────────────────────────────────────┐       │
│                │   │ UDSMode01Handler @ 0x66258           │       │
│                │   │ - Validates PID range (1..63)       │       │
│                │   │ - Looks up PID in table @ 0x5F6D8   │       │
│                │   │ - Calls per-PID data handler        │       │
│                │   │ - Formats response message (0x41+   │       │
│                │   │   PID + data bytes)                 │       │
│                │   └─────────────────────────────────────┘       │
│                │                                                 │
│                │   PID Table @ 0x5F6D8 (32 bytes/entry):         │
│                │   Entry[PID-1] → handler/data descriptor        │
│                │                                                 │
│                ├─ SID 0x02 → UDSMode02Handler (0x66314)          │
│                ├─ SID 0x03 → UDSMode03Handler (0x66AF4)          │
│                ├─ SID 0x04 → UDSMode04Handler (0x66B1A)          │
│                ├─ SID 0x05 → UDSMode05Handler (0x66B44)          │
│                ├─ SID 0x06 → UDSMode06Handler (0x66C9C)          │
│                ├─ SID 0x07 → UDSMode07Handler (0x66BFC)          │
│                ├─ SID 0x08 → UDSMode08Handler (0x66C9C)          │
│                └─ SID 0x09 → UDSMode09Handler (0x64BB0)          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Mode 1: Show Current Data

### Entry Point: UDSMode01Handler @ 0x66258

```
UDSMode01Handler(request, response):
  pid = request[6]                        // PID byte
  if pid < 1 or pid > 63: return error    // PID out of range
  
  // Use PID table at 0x5F6D8
  table_base = 0x5F6D8
  entry_addr = table_base + (pid - 1) * 32
  
  word0 = *(uint16_t*)(entry_addr)        // Handler type / flags
  word1 = *(uint16_t*)(entry_addr + 2)    // Data address or offset
  
  // Two entry types:
  if word0 == 0xFFFF:
    // Direct handler — word1 contains function pointer
    result = (*word1)(pid, response)
  else:
    // Data/pair — word0 and word1 define data to copy directly
    // into response
```

### PID Table Format @ 0x5F6D8

Each entry is 32 bytes. The first two words (4 bytes) determine the entry type:

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| +0     | u16  | type  | Entry type. `0xFFFF` = handler function; otherwise = PID response data count |
| +2     | u16  | data  | If type==0xFFFF: function pointer (handler address). Otherwise: data address or offset |
| +4..31 | -    | pad   | Reserved |

### PID Entry Types

1. **Handler entries** (type == 0xFFFF):
   - The handler at `data` is called to produce the PID response
   - Example: PID 0x0C (RPM), PID 0x0D (Speed)

2. **Direct data entries** (type != 0xFFFF):
   - The response data is looked up indirectly via a group mechanism
   - `type` = expected response byte count
   - `data` = lookup key/index
   - Example: PIDs 0x00-0x0B (group inquiry), 0x10-0x18 (group data)

### Handler Functions (called from PID table)

| PID | Function | Address | Description |
|-----|----------|---------|-------------|
| 0x0C | getRPMOBDHandler | 0x55E7C | RPM (0-16383.75 rpm, A/4) |
| 0x0D | getSpeedOBDHandler | 0x55EA2 | Vehicle speed (0-255 km/h) |
| 0x0E | getTimingAdvOBDHandler | 0x55E66 | Timing advance (-64 to 63.5 deg) |
| 0x0F | getIATOBDHandler | 0x55E18 | Intake air temperature |
| 0x10-0x18 | group handlers | various | MAF airflow, throttle position, etc. |

---

## OBD Sensor Value Pipeline

OBD sensor values undergo a multi-stage pipeline from raw sensor input to CAN TX:

```
Raw Sensor → Sensor Processing Pipeline → Float RAM Value
                                     ↓
                          OBD Getter Function
                          (float → OBD-scaled uint16)
                                     ↓
                          OBD CAN TX Buffer
                          (0xFFFFCEAC-0xFFFFCEC7)
                                     ↓
                          CAN TX (ID 0x240/0x250)
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
| 0xFFFFCEAC | OBD byte 0 (PID group header) | 0x240 |
| 0xFFFFCEAD | OBD byte 1 | 0x240 |
| 0xFFFFCEAE | OBD byte 2 | 0x240 |
| 0xFFFFCEAF | OBD byte 3 | 0x240 |
| 0xFFFFCEB0 | OBD byte 4 | 0x240 |
| 0xFFFFCEB1 | OBD byte 5 | 0x240 |
| 0xFFFFCEB2 | OBD byte 6 | 0x240 |
| 0xFFFFCEB3 | OBD byte 7 | 0x240 |
| 0xFFFFCEB4 | OBD byte 0 | 0x250 |
| ... | ... | ... |
| 0xFFFFCEC7 | OBD byte 19 | 0x250 |

### Entry Points for CAN TX

- **getOBDCANTXVars1** @ 0x4C8C2 — Collects 8 bytes for CAN ID 0x240
- **getOBDCANTXVars2** @ 0x4C9C0 — Collects 20 bytes for CAN ID 0x250

---

## OBD Getter Functions

These are the individual sensor-to-OBD-value conversion functions. They form the core
of the OBD data pipeline.

### Conversion Pipeline

Each getter follows the same pattern:

1. Load float sensor value from RAM address
2. Load scale factor and offset constants
3. Call shared conversion function `floatToOBDBounded` @ 0x24D0
4. Return uint16 result for packing into CAN buffer

### Shared Conversion Function: floatToOBDBounded @ 0x24D0

```
uint16_t floatToOBDBounded(float sensor_val, float scale, float offset, uint16_t max_val)
{
    // Apply offset and scaling
    float tmp = (sensor_val - offset) / scale;

    // Round to nearest integer (add 0.5 and truncate)
    int32_t result = (int32_t)(tmp + 0.5f);

    // Clamp to [0, max_val]
    if (result > max_val) result = max_val;
    if (result < 0)       result = 0;

    return (uint16_t)result;
}
```

**Arguments:**
- fr4 = `sensor_val` — raw float from sensor RAM
- fr5 = `scale` — divisor applied after offset subtraction
- fr6 = `offset` — subtracted from sensor value first
- r5  = `max_val` — upper clamp bound (typically 0xFF)

**Formula:** `OBD_value = clamp((sensor_val - offset) / scale + 0.5, 0, max_val)`

### Per-PID Getter Reference

#### getEngineLoadOBD @ 0x55D9A
```
input:  float engine_load = *(float*)0xFFFFAA10
scale:  float (computed indirectly via flags/sensor status)
offset: float (computed from sensor status)
result: uint16_t — Engine load % (0..100)
notes:  Complex function with status checks at 0xFFFFAE97, 0xFFFFAD9C, 0xFFFFAE96.
        Handles sensor failure/limp modes.
```

#### getIATOBD @ 0x55E18
```
input:  float iat1 = *(float*)0xFFFFC12C
        float iat2 = *(float*)0xFFFFC130
        uint16_t default_val = 0xFF
scale:  0.39215684f (128/326.4? — converts °C to OBD scale)
offset: -40.0°C
result: uint16_t — IAT in °C + 40 offset (OBD standard)
formula: result = clamp((iat1 - (-40)) / 0.392157 + 0.5, 0, 255)
notes:  Uses iat1 as primary sensor, iat2 as fallback.
        Multiplies by 0.00001 (9.999999e-06) — possibly a sensitivity gain.
```

#### getRPMOBD @ 0x55E7C
```
input:  float rpm_count = *(float*)0xFFFFAE64
scale:  computed from constants
offset: -1.0 (subtract 1 from count before scaling)
result: uint16_t — RPM (OBD = value / 4)
formula: result = clamp(((rpm_count - 1.0) * 100.0) / scale + 0.5, 0, 65535)
notes:  rpm_count is likely in actual RPM (float), the *100.0 and subsequent
        division produce the OBD-scaled value where A = RPM/4.
```

#### getSpeedOBD @ 0x55EA2
```
input:  float speed = *(float*)0xFFFFB140
scale:  computed from constants
offset: 0.0 (no offset)
result: uint16_t — Vehicle speed in km/h
formula: result = clamp(speed / scale + 0.5, 0, 255)
```

#### getMAFOBD @ 0x55E66
```
input:  float maf = *(float*)0xFFFF9F70
scale:  ~0.15625 (6.4 g/s per count?)
offset: -100.0
result: uint16_t — MAF airflow (g/s * 100 or scaled)
notes:  Direct mapping of MAF sensor to OBD PID 0x10.
```

#### getTimingAdvOBD @ 0x55E7C (shared with getRPMOBD)
```
input:  float timing = *(float*)0xFFFF9F70 (or similar)
result: uint16_t — Timing advance in degrees * 2 (OBD standard)
```

#### getSTFTOBD @ 0x55EEA
```
input:  float stft = *(float*)0xFFFFA63C
scale:  0.5
offset: -64.0
result: uint16_t — Short-term fuel trim (OBD scale: 128 = 0%)
formula: result = clamp((stft - (-64.0)) / 0.5 + 0.5, 0, 255)
        = clamp((stft + 64) * 2 + 0.5, 0, 255)
notes:  OBD fuel trim: byte value A → actual % = (A - 128) * 100/128
        So A = 128 + % * 1.28. With offset -64 and scale 0.5:
        result = (STFT + 64) * 2 → when STFT=%: A = 2*% + 128
        This maps to OBD range: -64% → 0 (A=0), 0% → 128 (A=128), 63.5% → 255 (A=255)
```

#### getLTFTOBD @ 0x55F02
```
input:  float ltft = *(float*)0xFFFF9F60
scale:  1.0
offset: -40.0
result: uint16_t — Long-term fuel trim
formula: result = clamp((ltft - (-40.0)) / 1.0 + 0.5, 0, 255)
        = clamp(ltft + 40.5, 0, 255)
notes:  LTFT stored in same % format as STFT. Scale = 1.0 means different
        calibration than STFT. Offset -40 shifts the range.
```

#### getLambdaOBD @ 0x55F7A
```
input:  float lambda = *(float*)sensor (computed from commanded AFR)
scale:  multiple stages
result: uint16_t — Commanded air-fuel equivalence ratio λ
formula: result = lambda_value * 10000 (OBD standard: A/10000 = λ)
notes:  Complex floating-point math with multiple FMUL operations.
        Reads raw commanded AFR, converts to lambda ratio.
```

#### getThrottleOBD @ 0x55F64
```
input:  float throttle_pos = *(float*)sensor_addr
result: uint16_t — Throttle position % (0..100)
```

---

## Mode 2: Freeze Frame @ 0x467D0

Freeze frame stores a snapshot of sensor values when a DTC is set. Handler:
```
FreezeFrameHandler(request, response):
  if emission_related_dtc_stored():
    if freeze_frame_valid():
      copy_snapshot_to_response()
      return
  response_empty()
```

The freeze frame buffer contains pre-computed OBD-scaled values for all supported
PIDs, captured atomically at the moment the DTC was set.

---

## Mode 9: Vehicle Information @ 0x64BB0

Mode 9 provides vehicle identification and calibration info. Handler structure:
```
UDSMode09Handler(request, response):
  subfunction = request[6]
  switch subfunction:
    0x01 → return VIN (vehicle identification number)
    0x02 → return ECU name / calibration ID
    0x03 → return CVN (calibration verification number)
    0x04 → return in-use performance tracking data
    default → return supported PIDs list
```

---

## Data Flow: PID Request → CAN Response

```
OBD Scanner → CAN 0x7DF (broadcast) or 0x7E0 (functional)
  │
  ▼
CAN RX Mailbox → CANRX_Main → udsHandler @ 0xDFD4
  │
  ▼
UDS Dispatcher → UDSMode01Handler @ 0x66258
  │
  ▼
PID Table Lookup @ 0x5F6D8:
  │
  ├── Handler entry → call PID-specific handler
  │     │
  │     └──→ floatToOBDBounded @ 0x24D0
  │           convert float sensor → uint16 OBD value
  │           store in OBD CAN TX buffer @ 0xFFFFCEAC+
  │
  └── Data entry → copy pre-formatted response
  │
  ▼
Response → CAN 0x7E8 (tool response)
```

---

## Key Function Reference

| Address | Function | Description |
|---------|----------|-------------|
| 0x24D0 | floatToOBDBounded | Core float→uint16 OBD converter |
| 0x5F57C | udsDispatchTable | UDS SID→handler dispatch table |
| 0x5F6D8 | obdPidTable | PID→handler/data lookup table |
| 0x55D9A | getEngineLoadOBD | Engine load % getter |
| 0x55E14 | getCoolantTempOBD | Coolant temp getter (stub) |
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
| 0x670B4 | obdCheckPIDSupported | Checks PID support bitfield |
| 0x670E6 | obdGetPIDTableEntry | Computes table entry address |

---

## OBD Response CAN IDs

| CAN ID | Direction | Content |
|--------|-----------|---------|
| 0x7DF | RX (broadcast) | OBD scan tool request (Mode 1/2/9) |
| 0x7E0 | RX (functional) | OBD scan tool request (addressed to ECU) |
| 0x7E8 | TX | OBD response to scan tool |
| 0x240 | TX (periodic) | Current data snapshot (8 bytes) |
| 0x250 | TX (periodic) | Extended data snapshot (20 bytes) |

---

## Constants Reference

| Address | Value | Usage |
|---------|-------|-------|
| 0x24F8 | 0x00FF | Max clamp value (255) for conversion |
| 0x24FC | 0x3F000000 | 0.5f — rounding constant for floatToOBDBounded |
| 0x55F34 | 0x42C80000 | 100.0f — % scale factor |
| 0x55F38 | 0x3EC8C8C8 | 0.39215684f — IAT conversion scale |
| 0x55F44 | 0xC2200000 | -40.0f — temperature offset |
| 0x55F48 | 0xC2C80000 | -100.0f — negative offset |
| 0x55F4C | 0x3F480000 | 0.78125f — fuel trim conversion? |
| 0x55F58 | 0xC2800000 | -64.0f — STFT offset |
| 0x55F5C | 0x3F000000 | 0.5f — STFT scale |

---

## RAM Variable Mapping (Sensor Values)

Refer to `SENSOR_PIPELINE.md` for the complete sensor variable mapping.
OBD-relevant RAM addresses that serve as inputs to the getter functions:

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

---

## Notes

1. Not all PID handlers were fully decompiled — some branches (especially failure/limp
   modes) rely on status register values that are set by other runtime subsystems.

2. The `getCoolantTempOBD` function at 0x55E14 is a trivial stub returning 0.
   Coolant temperature OBD data may be routed through a different path.

3. The conversion constants for some getters differ from the theoretical OBD
   standard values, suggesting manufacturer-specific calibration adjustments.

4. The UDS Mode 22 (DID-based) handlers at 0x630A4+ are separate from the OBD
   PID handlers and serve proprietary diagnostic data requests.
