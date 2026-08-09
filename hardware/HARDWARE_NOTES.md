# RX-8 ECU Hardware Notes

## Main Board

| Component | Value |
|---|---|
| PCB P/N | 279721-3210 |
| Main CPU | Renesas SH7055 (SH-2E, 32-bit, big-endian) |
| ROM | 512 KB internal flash, `0x000000–0x07FFFF` |
| RAM | 32 KB, `0xFFFF6000–0xFFFFDFFF` |
| EEPROM | ABLIC S-93C56C, 256 bytes, SOIC8, SPI bit-bang |
| Secondary MCU | Unknown QFP near X430 crystal — likely DBW safety MCU |
| Supply | 12 V automotive |
| Connector | Single multi-row header (bottom edge) |

## ECU P/N Family (Series I, N3J1, same connector)

All variants below are pin-compatible and ROM-compatible (60E0xxxx / 60E1xxxx):

| P/N | Variant | Notes |
|---|---|---|
| N3J1-18-881L | EU 6-port 231 hp MT LHD | **Our ECU** |
| N3J1-18-881F | EU 6-port 231 hp AT | Same connector |
| N3J1-18-881G | EU 6-port 231 hp AT variant | Same connector |
| N3J1-18-881H | EU 6-port 231 hp MT variant | Same connector |
| N3J1-18-881R | EU 6-port 231 hp AT variant | Same connector |

Series II (2009+) uses SH7058 — different CPU, different ROM architecture, NOT compatible.
MX-5 NC with Denso ECU can use SH7055, but the connectors and ROM layout differ.

## EEPROM Read Procedure

1. ECU out of car (or carefully clip in-situ)
2. Locate IC420 (SOIC8, near top-right of PCB — see community photos)
3. CH341A programmer + SOIC8 clip
4. Read as 93C56 (256 bytes, 3-wire SPI) — NOT 93C86 (that is 1 KB)
5. Verify: first byte must be `0x55` (magic / valid marker)
6. Backup original before you write anything

Available EEPROM dumps are kept in private storage (not shipped):
- `se3p_ecm_eeprom.bin` — community reference
- `RX8_93c56_ECU_IC420_Read.bin` — confirmed IC420 read

## CAN / OBD Connector

- OBD-II pin 6: HS-CAN High
- OBD-II pin 14: HS-CAN Low
- OBD-II pin 3: MS-CAN High (accessories, not ECU)
- OBD-II pin 11: MS-CAN Low

## J2534 Adapter

- OBDX Pro VX (used and verified)
- DLL: `C:\Program Files (x86)\OBDX Pro\J2534\OBDX Pro VX\OBDXVX_J2534.dll`
- **32-bit DLL** — must use `py -3.11-32`
- Strips PCI byte: `Data[4]` is first UDS byte in callbacks
