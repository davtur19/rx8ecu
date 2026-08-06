# RX-8 ECU — Hardware (PCB Analysis)

Active hardware RE notes. Non-discoverable facts: `KNOWLEDGE.md`. ROM/software: `ECU.md`.
IC list closed/authoritative (board fully inspected front+back).

Unit: N3J1 6-port MT ECU, PCB silk P/N **279721-3210** (board-level; differs from
Denso unit-level P/N 279700-3313 in `KNOWLEDGE.md` — likely board-only vs. full-unit
numbering, unconfirmed).

---

## IC inventory (19 total — 18 front, 1 back)

| Ref-des | Marking | Part | Function | Notes |
|---|---|---|---|---|
| **IC430** | `...7055F40`, date `SK 0545` | **Renesas/Hitachi SH7055** | Main CPU | Biggest chip on the board, under crystal X430 (10 MHz), above IC420 (EEPROM). Confirms `KNOWLEDGE.md`'s CPU fact from hardware. |
| **IC404** | `D151815-8551` / `SC515616MFC` / `263` / `QQDZ0542A` | Denso custom ASIC (`1518xx-xxxx` family) | Unknown — candidate: companion timing/waveform ASIC | Large QFP, notched corners. Distinct part from `151821-1280` (IC780) despite similar numbering. |
| **IC840** | Denso logo + `~151811-2870`, date `0605` | Denso ASIC, same `1518xx-xxxx` family | Unknown | In the driver row, between IC780 and IC300's former position. |
| **IC780** | `151821-1280`, lot `992K7 603 VB 99 MYS` | Denso custom ASIC, same family | Guess: ignition coil driver | Small power-SOP, 2 tab holes. Stacked at the same board location as IC701 (two separate chips). |
| **IC820** | `151821-1280`, lot `992K7 603 VB 99 MYS` (identical to IC780) | Denso custom ASIC, same family | Guess: ignition coil driver | Near crystal X430, paired with IC830. Earlier "comms/CAN-transceiver" guess was wrong — corrected. |
| **IC830** | `151821-1280`, lot `992K7 603 VB 99 MYS` (identical to IC780/IC820) | Denso custom ASIC, same family | Guess: ignition coil driver | Paired with IC820. Earlier "comms/CAN-transceiver" guess was wrong — corrected. |
| **IC020** | `1H28` / `SE585` + Denso logo | Denso ASIC, SOP24 | Unknown | Power-supply area, near D013/C023/L190/IC190. |
| **IC400** | `1H28` / `SE555` + Denso logo | Denso ASIC, SOP24 (one digit off IC020's `SE585` — easy to conflate, confirmed separate chip) | Sits inside a ~15-pair R/C filter cluster → analog front-end/mux guess | — |
| **IC640** | `F5041` / `61115` | **Fuji Electric F5041** — Intelligent Power MOSFET, SOP-8 | Solenoid/lamp/relay-fuse low-side driver — candidate: OMP metering oil pump or purge/VICS solenoid | Part confirmed via Fuji datasheet. 2 identical instances also at IC660 and IC850. |
| **IC660** | `F5041` / `61115` (identical to IC640) | **Fuji Electric F5041** — Intelligent Power MOSFET, SOP-8 | Solenoid/lamp/relay-fuse low-side driver | Same part as IC640/IC850. |
| **IC850** | `F5041` / `61115` (identical to IC640) | **Fuji Electric F5041** — Intelligent Power MOSFET, SOP-8 | Solenoid/lamp/relay-fuse low-side driver | Same part as IC640/IC660 — 3 identical solenoid/lamp drivers on the board. |
| **IC705** | `SPF0001` / `K5D03` | Sanken SPF0001 — power transistor array | Per-injector or per-coil low-side driver | — |
| **IC703** | `SPF0001` / `K5D03` | Sanken SPF0001 | Per-injector or per-coil low-side driver | — |
| **IC701** | `SPF0001` / `K5D03` | Sanken SPF0001 | Per-injector or per-coil low-side driver | 3rd identical driver — matches the original "3 identical drivers" hypothesis. Stacked with IC780 (separate chip). |
| **IC520** | `MC33186DH`, lot `KAV0550` | **NXP/Freescale MC33186** — automotive H-Bridge driver, 150 mΩ | Candidate: ETB (drive-by-wire throttle) motor driver, matches known `FUN_0x8F62` ETB loop in `ECU.md` | — |
| **IC420** | `S93C56` + `BD` logo, lot `V5Y 3369` | **ABLIC S-93C56C** — 256B EEPROM, 3-wire SPI | EEPROM (paired data, VIN pairing byte, LC checksum window per `KNOWLEDGE.md`) | Matches pre-existing `hardware/HARDWARE_NOTES.md` EEPROM location. |
| **IC905** (only IC on the backside) | `TD549A4`, lot `M4600` | Toshiba (TD-prefix), no exact public datasheet match | Unknown — likely Darlington/relay driver | Near C498/C303/R300/D335. |
| **IC675** | Toshiba logo (`T`) + `0551H` / `AX00-H` (final reading, confirmed twice by user) | Toshiba, exact P/N unresolved | Unknown | Near R820/C675, next to CN490 and the IC820/IC830 pair. Checked against markingcodes.com — no hits for this or other candidate readings (`NC00-H`, `AC00-H`). Likely too worn/glare-affected to be in any public database, or it's a fab/lot code rather than the searchable part number. |
| **IC190** | `3029012` / `452KPM5` | ST Microelectronics, SOP-8 — customer-specific part number (family `3029xxx` also seen assigned to Bosch), no functional datasheet found | Unknown | Near IC020/L190. |

`L190` (TDK, `1272`/`R2X`) is a filter/choke inductor, not an IC — originally mistaken for one.

---

## Connectors (right edge, back of board)

| Silk label | Pins | Notes |
|---|---|---|
| **CN400 "PBL"** | 13, single row | Matches equinox92's RX8club forum BOOT-mode pinout, confirmed against this exact connector via his reference photos (kept in private storage, not shipped): **WDT, FWE, MD1, TX, RX** labeled directly above their holes, anchored to R407/R408/T701–T704/C482/C420. (The apparent left/right pin numbering mismatch between his two reference photos is just component-side vs. solder-side view of the same through-hole row — not a real conflict.) Still confirm with a multimeter before applying any voltage for BOOT mode recovery. |
| **CN430 "NBD"** | ~13–14, single row | Adjacent to CN400, purpose unconfirmed. |
| **CN490 "MEP5"** | small header | Near IC675 and crystal X430, purpose unconfirmed. |

**SW480 + J405**: 3-pad test point block silkscreened `RST-OPEN` — reset configuration jumper, appears unpopulated (open) by default.

---

## Backside (solder side)

Board is populated on both sides. Back side is mostly discrete R/C networks (output-stage
filtering/pull-ups for the front-side driver ICs) plus:

- **IC905** — see inventory table above; the only IC on the backside.
- `R33`-marked SIP resistor packs (x2, near R030/R040/C020) — networks, not logic.
- **Jumper/config points**: J009, J010, J405, J420, J450, J456, J600, J601 (+ SW480/RST-OPEN on the
  front). On a PCB shared across 5 ECU variants (N3J1-18-881F/G/H/L/R per `KNOWLEDGE.md`), this many
  jumpers strongly suggests **hardware option-strapping** — worth comparing against a different
  variant board if one is ever available.
- Discrete transistors **T561, T570, T680, T705, T706, T730, T731, T671**, each paired with a nearby
  flyback diode — likely low-side switches for solenoids/relays/lamps.
- Dense R2xx/R4xx/C2xx/C4xx clusters sit directly behind IC400's front-side position — consistent
  with IC400 being an analog front-end.
- **T040/T150/T870**: discrete power transistors on the small heatsink bracket, top-left of the front side (not driver ICs, corrected from an early guess).

---

## Open items

1. Glare-free (angled/polarized light) re-shoot of IC675 for a full part number.
2. Multimeter continuity check on CN400 before applying voltage for BOOT mode.
3. IC400 (`SE555`) and IC020 (`SE585`) functions undocumented publicly — may need tracing copper to known signals.
4. Denso ASIC functions all unconfirmed guesses (IC404: timing ASIC; IC840, IC780/IC820/IC830 — 3 identical `151821-1280`: ignition coil driver) — need continuity tracing to the coil/injector connector pins. 3 identical instances is odd for "leading+trailing × 2 rotors" (4 coils).
5. `IC190` (`3029012`) and `IC675` — no functional identification, just manufacturer/package.
