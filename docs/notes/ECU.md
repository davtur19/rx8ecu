# RX-8 ECU — Notes

Active RE work. Non-discoverable facts: `KNOWLEDGE.md`. Confirmed discoveries: `FINDINGS.md`.

---

## CAN Dispatch Table ([REDACTED])

Location: `0x4E728` (copy at `0x4E828`). Entry = 16 bytes.  
Handler ptr formula: `(b[12] << 16) | int.from_bytes(b[10:12], 'big')`

| CAN ID | Handler | Notes |
|---|---|---|
| 0x0201 | 0x1BB5C | RPM / vehicle speed / accel (field-verified; see CAN_PROTOCOL.md "Field vs firmware") |
| 0x0231 | 0x1BCC4/0x1BB48 | Engine state / gear selector — field data differs (MT/AT split): OPEN |
| 0x0250 | 0x1CEB8 | Injection pulse width (Rotarytronics patch target) — byte3 = IAT per field: OPEN |
| 0x0630 | 0x1C044 | Fan status (Rotarytronics patch target) |
| 0x7DF/0x7E0 | 0x0DE04 | OBD2 UDS handler |

All RX-8 broadcast IDs (0x201, 0x203, 0x215, 0x231, 0x240, 0x250, 0x420, 0x630, 0x650)
are proprietary — not visible via standard OBD2. See `docs/notes/CAN_PROTOCOL.md` for full list.

---

## DENSO Checksum

Additive sum of BE dwords over ROM range. Descriptor at `0x7FB80`:  
`[lo_addr:4][hi_addr:4][diff:4]` — range lo=`0x2000`, hi=`0x7DAFF`; target = `sum + diff = 0x5AA5A55A`; diff stored at `0x7FB88`.

Second word at `0x7FFF4`: different algo, unknown, NOT verified at ECU runtime — ignore for now.

Tool: `python tools/denso_ck.py <rom.bin>` (verify) / `-f` (fix in-place) / `-o <out>` (fix to copy).
