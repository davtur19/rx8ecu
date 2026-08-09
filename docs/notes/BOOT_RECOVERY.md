# BOOT-mode recovery flash — procedure

Renesas BOOT-mode recovery repairs a bricked N3J1-18-881L ECU. The procedure follows equinox92's guide (credits/provenance — see `CREDITS.md`) and this board's confirmed CN400 pinout (`docs/notes/HARDWARE.md`).

## 1. ROM file to flash

**Recommended**: stock ROM for the 2004 **EU 6-Port MT** J-line variant (matching this ECU); the owner's live-ECU dump is private, not shipped.

| Check | Result |
|---|---|
| ROM-ID → variant | 2004 **EU 6-Port MT** (J-line; owner's ECU) |
| Matches board identity | N3J1-18-881L / Denso 279700-3313 (per `docs/notes/KNOWLEDGE.md`) |
| File size | 524288 bytes = exactly 512 KB (correct for SH7055 internal flash) |
| Checksum (`tools/denso_ck.py`) | Sum `0xA1BE79C2` + diff → `0xB8E72B98` = stored value. **OK — valid.** |

You can restore the exact ECU contents only if you took a full ROM dump beforehand. Otherwise use the matching stock ROM for this car.

A ROM-only flash does not touch the EEPROM. A saved EEPROM dump already exists (private). Do not overwrite it.

## 2. Jig hardware — ESP32-WROOM-D / Pi Pico / Pro Mini 328P (5V/16MHz)

CN400 needs 5 signals: WDT (PWM), FWE (pull-up), MD1 (pull-down), TX, RX. No purpose-built adapter is needed.

### Final confirmed wiring (2026-07-08, per labeled photo + schematic of this exact CN400)

**CN400 pins**: pin 1 at one end, pin 13 at the other — **WDT=3, FWE=6, MD1=8, TX=9, RX=10**. This supersedes the earlier equinox-derived guess (WDT=3/FWE=5/MD1=7/TX=8/RX=9; off by one on FWE/MD1/TX/RX).

- **CN400 pin 3 (WDT)** → Pro Mini (5V/16MHz) digital pin:
  ```cpp
  void setup() { pinMode(9, OUTPUT); tone(9, 150); } // 150 Hz, 50% duty — only active signal
  void loop() {}
  ```
- **CN400 pin 6 (FWE)** → 5V through a 1k–10k resistor (passive pull-up).
- **CN400 pin 8 (MD1)** → GND through a 1k–10k resistor (passive pull-down).
- **CN400 pin 9 (TX, ECU→PC)** → serial adapter RX, through a 1k inline resistor.
- **CN400 pin 10 (RX, PC→ECU)** → serial adapter TX, through a 1k inline resistor.
- **GND** common across Pro Mini, serial adapter, ECU.

The Pro Mini drives one pin (WDT). The earlier 3-pin sketch (FWE/MD1 GPIO) is superseded by this passive version (confirmed by schematic).

### TX/RX → dedicated USB-serial adapter

- Adapter **RX** → CN400 **pin 9** (ECU TX), through a 1k inline resistor.
- Adapter **TX** → CN400 **pin 10** (ECU RX), through a 1k inline resistor.
- 3.3V/5V jumper → **5V** (SH7055 native logic level; keep 1k resistors as protection).
- FDT connects to the COM port of this adapter.

### Landmarks on this exact board (from `docs/notes/HARDWARE.md`)
CN400 "PBL", 13-pin single row, back edge. Silk labels WDT/FWE/MD1/TX/RX sit above their holes, anchored near R407/R408/T701–T704/C482/C420. **Verify pin identity with a multimeter before applying any voltage.**

## 3. FDT (Flash Development Toolkit) steps

1. Create a new workspace → device: **"7055"** kernel. If FDT throws error **16184 "0.18um device"**, the chip is `HD64F7055S` → re-create with **Generic BOOT Device**.
2. Select the COM port for the TX/RX adapter.
3. Connection type: **BOOT mode**.
4. Add the matching stock ROM as the download file.
5. Power sequence: set MD1 low and start WDT **before** power-up, then power the ECU (battery, ignition, ground per RX-8 wiring) — MD1 must be sampled low at reset for BOOT mode.
6. FDT → Connect. If no sync, check that the WDT square wave runs first. Otherwise the MCU resets in a loop — the connect fails silently.
7. Download File. Do not power-cycle mid-write.
8. Use the post-write verify/readback option if offered.

## 4. Safety checklist

- [ ] Confirm CN400 pin identity with a multimeter before connecting anything live.
- [ ] EEPROM backup exists (saved dump in private storage) — confirmed, no new one needed.
- [ ] ROM file size = 524288 bytes, checksum OK — confirmed for the matching stock ROM.
- [ ] WDT square wave runs before ECU power-up.
- [ ] Do not interrupt power or the serial link mid-download.