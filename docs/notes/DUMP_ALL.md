# Dump-everything-first procedure (read-only, before any flash)

Goal: full backup of ROM + EEPROM (+ anything dumpable) from the physical ECU, before any BOOT-mode flash. No writes in this phase.

## Step -1 — EEPROM chip read first (before any bench power-up)

First move: needs **zero** car infrastructure — no cluster, wheel-speed sim, CAN, or bench power. Direct chip-level read of IC420 with SOIC8 clip + CH341A.

- **Location**: IC420, front side, directly adjacent to IC430 (SH7055 CPU) — `docs/notes/HARDWARE.md`.
- **Part**: ABLIC S-93C56C, 256 bytes, 3-wire (Microwire), confirmed marking `S93C56` + `BD`.
- **Critical**: ECU must be **completely unpowered** during the clip read. IC420's CS/CLK/DI/DO lines are normally bit-banged by the SH7055 (IC430) over GPIO. If powered, the CPU may drive those lines and fight the CH341A, so the read can corrupt.
- **Tool/settings**: CH341A + SOIC8 test clip, **93C56 (256 byte)** organization — same settings as the existing saved EEPROM dump. Clip orientation: pin-1 dot to clip's marked pin 1.
- **Verify**: first byte `0x55` (valid marker, per `docs/notes/KNOWLEDGE.md`). Save as a new file (do not overwrite) and diff — same ECU → byte-for-byte match.

Only after this — and only if you still want the live ROM — move to Step 0.

## Step 0 — does it still talk on the bus?

**Cluster / wheel-speed simulator**: likely only for a *running-engine* bench (tach, DSC/TCS cal, to clear "implausible speed" faults) — not for a plain memory read. A UDS dump just needs the CPU to boot and answer diagnostics. It logs DTCs for missing sensors, but that does not block RMBA reads. Try without the cluster first.

**Bench power-up (no car)** — full pin map in `docs/notes/CONNECTOR_PINOUT.md`:
- Ground: pins **4A, 4J, 5D, 5O, 5R, 5T** → bench supply GND
- +12V: pins **5AC, 5AF** (main relay rail — bypass relay, feed directly), **4Q** (ignition switched), **5J** (constant power)
- CAN: pin **4S** = CAN-L, pin **4V** = CAN-H → J2534 adapter
- Leave **4E** (Main Relay enable — an ECU output) disconnected/floating.

Expect DTCs for missing sensors/actuators — harmless for a read-only session.

Not tried yet. It decides the whole strategy:

```bash
# tool private, not shipped; run from the private checkout
py -3.11-32 tools/uds/<dump_tool>.py roms/stock/<new_dump_name>.bin
```

Watch the first log lines:
- `[1/5] Sessione programmazione 0x85 ...` → if the ECU replies `50 ...`, the ECU is **alive and runs code** — full, clean 512KB ROM dump, no hardware jig needed.
- If `10 85` times out / no CAN → ECU **silent on the bus** → BOOT-mode path (`docs/notes/BOOT_RECOVERY.md`'s jig, used **read-only** this time, no Download File).

Answers whether the ECU is actually "bricked" or just has a bad tune/config while the base CPU/comms stack is fine.

## Path A — ECU responds over UDS

- **ROM**: dumps all 512KB live. Verify `python tools/denso_ck.py roms/stock/<new_dump_name>.bin` after.
- **EEPROM (shadow copy)**: live ECU mirrors EEPROM → RAM `0xFFFFC000` at boot (`docs/notes/KNOWLEDGE.md`); same RMBA reads that RAM window. Good corroboration, but a RAM copy, not the raw chip — still worth a physical clip read for a true bit-exact backup.

## Path B — ECU silent, no bus response

- **ROM**: only through Renesas BOOT mode + FDT, with the jig in `docs/notes/BOOT_RECOVERY.md` (Pro Mini for WDT/FWE/MD1, ESP32 HW-394 with EN grounded for TX/RX). Use FDT **read/upload**, not Download File; do not select Erase or Program.
  - **Unknown on first connect**: whether Renesas ID-code protection is enabled. If so, FDT may offer only a full-chip erase — this ECU cannot be non-destructively dumped through BOOT mode. Do not erase/program to find out — stop if FDT asks for an ID code you do not have.
- **EEPROM**: BOOT mode does not touch IC420 — read it directly regardless of CPU state (SOIC8 clip + CH341A, as 93C56, `hardware/HARDWARE_NOTES.md` §EEPROM Read Procedure).

## Anything else worth dumping?

Per the closed IC inventory in `docs/notes/HARDWARE.md` (19 ICs, user-verified complete), only two chips are conventional non-volatile stores:
- **IC430** SH7055 — internal flash ROM.
- **IC420** ABLIC S-93C56C — 256B EEPROM.

Everything else (Denso ASICs IC404/IC840/IC780/IC820/IC830/IC020/IC400, Fuji F5041 ×3, Sanken SPF0001 ×3, NXP MC33186DH, Toshiba IC905/IC675) is driver/logic silicon with no known non-volatile store.

One 2-minute check: **IC190** (`3029012`, ST SOP-8, function unresolved). SOP-8 is the common package for small serial EEPROMs — trace its 8 pins for an SPI/I2C-like pattern before you rule it out. Not urgent.

## Existing backups on disk (do not overwrite)

- Saved IC420 EEPROM read (private storage) — prior read.
- `se3p_ecm_eeprom.bin` (private storage) — community reference, not this ECU.
- The matching stock ROM for this variant (**private, not shipped**) — and **not necessarily what's currently in this physical ECU** if tuned/modified.