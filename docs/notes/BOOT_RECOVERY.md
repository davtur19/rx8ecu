# BOOT-mode recovery flash — procedure

Renesas BOOT-mode recovery for a bricked N3J1-18-881L ECU, per equinox92's guide
(captured in this repo's credits/provenance — see `CREDITS.md`) + this board's
confirmed CN400 pinout (`docs/notes/HARDWARE.md`).

---

## 1. ROM file to flash

**Recommended**: use the stock ROM for the 2004 **EU 6-Port MT** J-line variant
(matching this ECU); the owner's live-ECU dump is private and not shipped in
the public repo.
Evidence:

| Check | Result |
|---|---|
| ROM-ID → variant | 2004 **EU 6-Port MT** (J-line; the owner's ECU) |
| Matches board identity | N3J1-18-881L / Denso 279700-3313 (per `docs/notes/KNOWLEDGE.md`) |
| File size | 524288 bytes = exactly 512 KB (correct for SH7055 internal flash) |
| Checksum (`tools/denso_ck.py`) | Sum `0xA1BE79C2` + diff → `0xB8E72B98` = stored value. **OK — valid.** |

If you want to instead restore *whatever was actually in the ECU before it bricked* rather than
generic stock image, that's only possible if a full ROM dump was taken beforehand — check if one
exists before assuming stock. Otherwise use the matching stock ROM for this car.

EEPROM is untouched by a ROM-only flash, and a saved EEPROM dump of it already
exists (kept in private storage, not shipped) — no need to re-read it first, but don't overwrite it.

---

## 2. Jig hardware — using ESP32-WROOM-D / Pi Pico / Pro Mini 328P (5V/16MHz)

CN400 needs 5 signals: WDT (PWM), FWE (pull-up), MD1 (pull-down), TX, RX. None of these need
a purpose-built adapter — split the job across what you already have:

### Final confirmed wiring (2026-07-08, per labeled photo + matching schematic of this exact CN400)

**CN400 pin numbers**: pin 1 at one end, pin 13 at the other — **WDT=3, FWE=6, MD1=8, TX=9,
RX=10**. This is the confirmed numbering; supersedes an earlier equinox-derived guess of
WDT=3/FWE=5/MD1=7/TX=8/RX=9 recorded previously in this file (was off by one on FWE/MD1/TX/RX).

- **CN400 pin 3 (WDT)** → Pro Mini (5V/16MHz variant) digital pin, running:
  ```cpp
  void setup() { pinMode(9, OUTPUT); tone(9, 150); } // 150 Hz, 50% duty
  void loop() {}
  ```
  This is the only signal that needs active generation.
- **CN400 pin 6 (FWE)** → 5V through a 1k–10k resistor (passive pull-up, no Pro Mini pin needed).
- **CN400 pin 8 (MD1)** → GND through a 1k–10k resistor (passive pull-down, no Pro Mini pin needed).
- **CN400 pin 9 (TX, ECU→PC)** → serial adapter RX, via a 1k inline resistor.
- **CN400 pin 10 (RX, PC→ECU)** → serial adapter TX, via a 1k inline resistor.
- **GND** common across Pro Mini, serial adapter, and ECU.

Pro Mini only drives one pin now (WDT) — the earlier 3-pin sketch (FWE/MD1 also GPIO-driven) is
superseded by this simpler passive-resistor version, confirmed correct by the schematic above.

### TX/RX → dedicated USB-serial adapter

- Adapter **RX** → CN400 **pin 9** (ECU TX) — via a 1k inline resistor.
- Adapter **TX** → CN400 **pin 10** (ECU RX) — via a 1k inline resistor.
- If the adapter has a 3.3V/5V level-select jumper, set it to **5V** to match the SH7055's native
  logic level exactly (keep the 1k resistors anyway as basic protection).
- COM port from this adapter is what FDT connects to.

### Landmarks on this exact board (from `docs/notes/HARDWARE.md`)
CN400 "PBL", 13-pin single row, back edge — WDT/FWE/MD1/TX/RX silk-labeled directly above their
holes, anchored near R407/R408/T701–T704/C482/C420. **Verify pin identity with a multimeter before
applying any voltage** — don't trust the silkscreen alone on first contact.

---

## 3. FDT (Flash Development Toolkit) steps

1. New workspace → device: **"7055"** kernel.
   - If FDT throws error **16184 "0.18um device"**, the chip is the revised `HD64F7055S` →
     re-create the workspace choosing **Generic BOOT Device** instead.
2. Select the COM port for whichever adapter is doing TX/RX.
3. Connection type: **BOOT mode**.
4. Add the matching stock ROM (local copy) as the download file.
5. Power sequence: MD1 low + WDT running **before** power-up, then power the ECU (battery, ignition,
   ground per RX-8 wiring) — MD1 must be sampled low at reset for BOOT mode to latch.
6. FDT → Connect. If it doesn't sync, check the WDT square wave is actually running first (MCU
   resets in a loop otherwise, which looks like a silent connect failure).
7. Download File. Let it finish — do not power-cycle mid-write.
8. If FDT offers a post-write verify/readback option, use it.

---

## 4. Safety checklist

- [ ] Multimeter-confirm CN400 pin identity before connecting anything live.
- [ ] EEPROM backup exists (saved dump in private storage) — confirmed, don't need a new one.
- [ ] ROM file size = 524288 bytes and checksum OK — confirmed for the matching stock ROM
      (the owner's live dump is private and not shipped in the repo).
- [ ] WDT square wave running before ECU power-up, not after.
- [ ] Don't interrupt power or the serial link mid-download.
