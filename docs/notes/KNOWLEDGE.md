# RX-8 ECU — Knowledge

Non-discoverable confirmed facts only. Load every session.
Active RE notes: `ECU.md`. Findings history: `FINDINGS.md`.

## ECU Identity

| Field | Value |
|---|---|
| Model | Mazda RX-8 S1, EU 6-port 231hp MT, 2004–2008 |
| VIN | [VIN redacted] |
| ECU P/N | N3J1-18-881L (Denso 279700-3313) |
| Live ROM | owner's personal dump (**private — not shipped** in this repo) |
| RE baseline | `60E1D400` — same N3J1 family, full docs in `docs/` |
| CPU | SH7055 (HD64F7055), SH-2E, 32-bit BE; flash 512 KB @ 0x000000; RAM 32 KB @ 0xFFFF6000 |
| EEPROM | ABLIC S-93C56C, 256 B, SPI bit-bang with GPIO |

All N3J1-18-881x variants (F/G/H/L/R) are pin-compatible and ROM-compatible.  
Series II (2009+) uses SH7058 — different CPU, not compatible.

---

## UDS Protocol Quirks

Non-standard. Wrong → silent failure or NRC.

| What | Correct | Wrong (and why) |
|---|---|---|
| Session open | `10 85` directly | NOT `10 01` first |
| TesterPresent | `3E 00` | NOT `3E 80` → NRC 0x12 |
| RMBA format | `23 [4B addr BE][2B len BE]` | no format byte (non-standard) |
| RMBA format — OPEN | `23 00 [3B addr][2B len]` (ConnorRigby dumper) vs `23 [4B addr][2B len]` above (matches RX8Man) — equivalent for addr < 0x01000000; whether the ECU accepts both is **unverified (bench open item)** — see `docs/hardware/RX8_OBD_UDS_Protocol.txt` and `community_tools/ConnorRigby_rx8-ecu-dump_AUDIT.md` | assume one is wrong |
| Pending response | `7F 23 78` before each RMBA = **normal** | not an error |
| Keepalive interval | every 10 s | S3server timeout ~30 s |

J2534: OBDX Pro VX. DLL is **32-bit only** → must use `py -3.11-32`.  
DLL path: `C:\Program Files (x86)\OBDX Pro\J2534\OBDX Pro VX\OBDXVX_J2534.dll`  
PCI byte stripped by DLL: `Data[4]` = first UDS byte in callbacks.

Flash reprogramming SIDs: 0x34→0x1A70, 0x36→0x1B8C, 0x37→0x1CB8. SecurityAccess first.

---

## Security Keys (5 bytes @ ROM 0x5FAC0)

| ROM variant | Key | Hex |
|---|---|---|
| Stock `60E1D400` | `"MazdA"` | `4D 61 7A 64 41` |

LFSR: init=`0xC541A9`, taps=`0x909028`. Per-level LFSR INIT table starts at
`0x5FAC8` in 60E1D400 (`0x5FAC5`–`0x5FAC7` is `FF FF FF` padding after the
5-byte secret) — **unchanged across all variants**.  
Tuned-ECU secret was capture-verified; its vectors removed for privacy (stock `MazdA` vectors in `tools/mazda_security.py` are the shipped, ROM-verified reference).
RESOLVED 2026-08-01 (commit `a84eaba`): `mazda_security.py` self-test + `test_security_access.py` pass — ROM-verified stock vector is seed `0x45820A` / `"MazdA"` / level 1 → `0xA07258` (12 ROM vectors).

If the ECU responds **NRC 7F2735 (InvalidKey)**: tool sends `"MazdA"`, ECU expects ROM's actual key. Fix: set correct 5-byte key for the ROM installed in the ECU.

> ⚠️ The legacy `docs/analysis/RX8_UDS_Security_Analysis.txt` (moved to private
> storage, no longer shipped) claimed fixed-key + static seed `0x55 0xAA 0x55`.  
> **Wrong.** Live captures confirm LFSR with random seeds. Ignore that doc on this point.

---

## EEPROM Shadow

- Hardware read: SOIC8 clip + CH341A, read as **93C56** (256 B) — NOT 93C86 (1 KB)
- First byte `0x55` = valid marker
- Copied to RAM `0xFFFFC000` at boot
- `0xFFFFC004` = `EEPROM_PairingByte` — non-zero = ECU paired
- LC checksum window: `0xFFFFC37E–0xFFFFC38E` (17 bytes, signed byte sum must = −23)
- **OPEN**: boot function that populates `0xFFFFC37E` not yet identified

---

## Cooling fans

Verified fan-control calibration tables (fan 1/2 enable + hysteresis @
`0x07793C–0x077950`, vehicle-speed cuts @ `0x077988`/`0x07798C`, tuned-ROM
fanmod evidence): see `docs/notes/COOLING_FANS.md`.
