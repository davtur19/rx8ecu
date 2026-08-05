# Dump-everything-first procedure (read-only, before any flash)

Goal: full backup of ROM + EEPROM (+ anything else dumpable) from the physical ECU, before any BOOT-mode flash. No writes in this phase.

---

## Step -1 — EEPROM chip read first (before any bench power-up)

First move: needs **zero** car infrastructure — no cluster, wheel-speed sim, CAN, or bench power. Direct chip-level read of IC420 via SOIC8 clip + CH341A.

- **Location**: IC420, front side, directly adjacent to IC430 (SH7055 CPU) — see `docs/notes/HARDWARE.md`.
- **Part**: ABLIC S-93C56C, 256 bytes, 3-wire (Microwire), confirmed marking `S93C56` + `BD` logo.
- **Critical**: ECU must be **completely unpowered** during the clip read. IC420's CS/CLK/DI/DO lines are normally bit-banged by the SH7055 (IC430) over GPIO — if the ECU has any power, the CPU may actively drive those lines and fight the CH341A, corrupting the read.
- **Tool/settings**: CH341A + SOIC8 test clip, software set to **93C56 (256 byte)** organization — same settings that produced the existing saved EEPROM dump (private storage), which is why that one came out valid. Clip orientation: match pin-1 dot to the clip's marked pin 1.
- **Verify**: first byte should read `0x55` (valid marker, per `docs/notes/KNOWLEDGE.md`). Save as a new file (don't overwrite the existing dump) and diff — same ECU → byte-for-byte match; a difference is useful info either way.

Only after this — and only if you still want the live ROM too — move to Step 0.

---

## Step 0 — does it still talk on the bus? (decides everything below)

**Note on the instrument cluster / wheel-speed simulator**: very likely only needed for a *running-engine* bench setup (tach display, DSC/TCS calibration, clearing "implausible speed" faults) — not for a plain memory read. A UDS session to dump ROM just needs the CPU to boot and answer diagnostics; it will log DTCs for the "missing" cluster/wheel sensors but that shouldn't block RMBA reads. Try without the cluster first; only add the rig if the ECU refuses to leave a limp/fault state that blocks the dump.

**Bench power-up (no car needed)** — full pin map in `docs/notes/CONNECTOR_PINOUT.md`, minimum wiring:
- Ground: pins **4A, 4J, 5D, 5O, 5R, 5T** → bench supply GND
- +12V: pins **5AC, 5AF** (main relay power rail — bypasses relay, feed directly), **4Q** (ignition switched), **5J** (constant power)
- CAN: pin **4S** = CAN-L, pin **4V** = CAN-H → J2534 adapter
- Leave **4E** (Main Relay enable — an ECU output) disconnected/floating.

Expect a pile of DTCs for the missing sensors/actuators — harmless for a read-only session.

Not tried yet. This single test picks the whole strategy:

```bash
# tool is private, not shipped in the public repo (no public equivalent);
# will NOT resolve in a public clone; run it from the private checkout instead
py -3.11-32 tools/uds/<dump_tool>.py roms/stock/<new_dump_name>.bin
```

Watch the first log lines:
- `[1/5] Sessione programmazione 0x85 ...` → if the ECU replies `50 ...`, it's **alive and running code** — CPU boots far enough to run the UDS stack. Let it finish; full, clean 512KB ROM dump, no hardware jig needed.
- If `10 85` times out / no CAN traffic at all → ECU is **silent on the bus** → BOOT-mode path (`docs/notes/BOOT_RECOVERY.md`'s jig, used **read-only** this time, no Download File step).

This directly answers whether it's actually "bricked" (non-responsive) or just has a bad tune/config while the base CPU/comms stack is fine.

---

## Path A — ECU responds over UDS

- **ROM**: the command dumps all 512KB live. Verify with `python tools/denso_ck.py roms/stock/<new_dump_name>.bin` after.
- **EEPROM (shadow copy)**: the live ECU mirrors EEPROM → RAM `0xFFFFC000` at boot (`docs/notes/KNOWLEDGE.md`), so the same RMBA mechanism can read that RAM window — active EEPROM contents without touching the board. Good corroboration, but it's a RAM copy, not the raw chip — still worth a physical clip read for a true bit-exact backup (no removal needed, ECU can stay assembled).

## Path B — ECU silent, no bus response

- **ROM**: only via Renesas BOOT mode + FDT, using the jig in `docs/notes/BOOT_RECOVERY.md` (Pro Mini for WDT/FWE/MD1, ESP32 HW-394 with EN grounded for TX/RX). Use FDT's **read/upload** function, not Download File — do not select Erase or Program.
  - **Unknown to check on first connect**: whether Renesas ID-code protection is enabled. If so, FDT may refuse to read without a matching ID and offer only a full-chip erase — that would mean this ECU can't be non-destructively dumped via BOOT mode. Don't erase/program to find out — stop and reassess if FDT asks for an ID code you don't have.
- **EEPROM**: BOOT mode doesn't touch IC420 — read it directly regardless of CPU state (SOIC8 clip + CH341A, read as 93C56, `hardware/HARDWARE_NOTES.md` §EEPROM Read Procedure). Works whether the ECU boots or not — direct chip read.

---

## Anything else worth dumping?

Per the closed IC inventory in `docs/notes/HARDWARE.md` (19 ICs, user-verified complete), only two chips are conventional non-volatile stores:
- **IC430** SH7055 — internal flash ROM (covered above).
- **IC420** ABLIC S-93C56C — 256B EEPROM (covered above).

Everything else (Denso ASICs IC404/IC840/IC780/IC820/IC830/IC020/IC400, Fuji F5041 ×3, Sanken SPF0001 ×3, NXP MC33186DH, Toshiba IC905/IC675) is driver/logic silicon with no known user-accessible non-volatile store — nothing to dump.

One 2-minute check before ruling out completely: **IC190** (`3029012`, ST SOP-8, function unresolved). SOP-8 is the common package for small serial EEPROMs — trace its 8 pins for an SPI/I2C-like pattern (CS/CLK/DI/DO or SCL/SDA) before assuming it's not memory. Not urgent; flagged since its function was never nailed down.

---

## Existing backups already on disk (don't overwrite)

- Saved IC420 EEPROM read (private storage) — prior IC420 read, undated relative to this ECU/session.
- `se3p_ecm_eeprom.bin` (private storage) — community reference, not this ECU.
- The matching stock ROM for this exact variant (**private, not shipped in the repo**) — and **not necessarily what's currently in this physical ECU** if it's been tuned/modified; that's exactly what Step 0's live dump (or BOOT-mode read) will tell you.
