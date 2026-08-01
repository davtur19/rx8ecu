# RX-8 ECU — Notes

Active RE work. Non-discoverable facts: `KNOWLEDGE.md`. Confirmed discoveries: `FINDINGS.md`.

---

## [REDACTED] LC Patch ([REDACTED] vs 60E1D400)

**Code cave**: `0x6C7FE–0x6CBFA` — stock = all `0xFF`; [REDACTED] injected SH-2A code here.

**Hook at `0x94C8`** (`LC_HookClampEntry`): 16 bytes changed → redirects stock throttle clamp to `LC_ClampAndGateOutput`.

**Patch at `0x35BBC`** (`LC_GateWrapper`): jump → `LC_GateCondition_RPMLoad` at `0x6CA80`.

ROM immobilizer at `0x35D90` — **unchanged** between stock and [REDACTED]. No-start = EEPROM data, not ROM immo.

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
The private injector `tools/[REDACTED].py` (**not shipped** — not present in
this public repo; it lives in the private checkout only) injects the cave from
`[REDACTED]` (private, not shipped) into `60E1D400.bin`,
NOPs out `LC_ValidateChecksum17`, fixes checksum.

---

## Ghidra Function Labels ([REDACTED])

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
| `0x583E4` | `CAN_TableLookup` |
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

---

## CAN Dispatch Table ([REDACTED])

Location: `0x4E728` (copy at `0x4E828`). Entry = 16 bytes.  
Handler ptr formula: `(b[12] << 16) | int.from_bytes(b[10:12], 'big')`

| CAN ID | Handler | Notes |
|---|---|---|
| 0x0201 | 0x1BB5C | Wheel speed / vehicle speed |
| 0x0231 | 0x1BCC4/0x1BB48 | Engine state |
| 0x0250 | 0x1CEB8 | Injection pulse width (Rotarytronics patch target) |
| 0x0630 | 0x1C044 | Fan status (Rotarytronics patch target) |
| 0x7DF/0x7E0 | 0x0DE04 | OBD2 UDS handler |

All RX-8 broadcast IDs (0x201, 0x203, 0x215, 0x231, 0x240, 0x250, 0x420, 0x630, 0x650)
are proprietary — not visible via standard OBD2. See `docs/notes/CAN_PROTOCOL.md` for full list.

---

## Open Investigation Items

1. **Boot initializer for `0xFFFFC37E`**: which function copies EEPROM → RAM at that offset? Not found.
2. **LC_HookClampEntry caller**: confirmed = `FUN_0x8F62` (ETB control loop). Its zeroed output = throttle clamp.
3. **0x7FFF4 second checksum**: algorithm unknown. Not verified at ECU runtime — low priority.
4. **[REDACTED] full function map**: live ECU ROM. CAN table located, most functions unnamed.
5. **Modified stock functions outside cave**: `0x1038`, `0x109C`, `0x121F0`, `0x1237C` — semantic roles not fully confirmed.

---

## DENSO Checksum

Additive sum of BE dwords over ROM range. Descriptor at `0x7FB80`:  
`[lo_addr:4][hi_addr:4][diff:4]` — range lo=`0x2000`, hi=`0x7DAFF`; target = `sum + diff = 0x5AA5A55A`; diff stored at `0x7FB88`.

Second word at `0x7FFF4`: different algo, unknown, NOT verified at ECU runtime — ignore for now.

Tool: `python tools/denso_ck.py <rom.bin>` (verify) / `-f` (fix in-place) / `-o <out>` (fix to copy).
