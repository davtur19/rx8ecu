# Main harness connector — pinout (bench power-up subset)

Source: `RX8_Sel_pinout.pdf` (private storage, not shipped) + `Rx8_Pin_Out_2048x2048.PNG` (Adaptronic Select S1 RX-8 install docs). The same connector fits all N3J1-18-881x variants. Pin naming: `<block 1-5><letter>`, view from loom side.

## Pins needed to power the ECU on the bench (no car, no relay box)

| Pin(s) | Factory function | Bench wiring |
|---|---|---|
| **4A, 4J, 5D, 5O, 5R, 5T** | Ground (×6, shared with both ECUs) | All → bench supply **GND** |
| **5AC, 5AF** | Power from Main Relay (ECU logic/CPU rail, live once relay closes) | **+12V** direct (bypasses relay, simulates "relay closed") |
| **4Q** | Ignition switch +12V | **+12V** (same rail as 5AC/5AF ok) |
| **5J** | Constant power (battery keep-alive) | **+12V** |
| **4S** | CAN low | To J2534 adapter CAN-L |
| **4V** | CAN high | To J2534 adapter CAN-H |

A UDS session needs: 6 grounds commoned, +12V into 5AC/5AF+4Q+5J, CAN-H/L to the adapter. No main relay, DBW relay, or starter signal is needed.

**Do not drive 4E** ("Main Relay enable") — it is an ECU *output* (low-side-switches the relay coil to self-latch). Leave it floating. Any forced voltage can short the open-drain driver.

## Not needed for a read-only bench session
- **4C / 5H** — Drive-By-Wire relay power/control. Only if the ETB must be live (throttle DTC clears/actuator tests).
- **5A** — Starter signal, irrelevant off-car.
- Other sensor/actuator I/O — not required to boot/answer UDS. Expect DTCs for "missing" sensors; they are harmless for a read-only session.

## Full connector reference

Full factory-function-per-pin table in `RX8_Sel_pinout.pdf` (private storage) — not duplicated. It is useful for: coil-driver chips (`docs/notes/HARDWARE.md` — IC780/IC820/IC830 guessed ignition drivers; PDF confirms 4 ignition outputs: 2AA/2AD front leading/trailing, 2Z/2AC rear leading/trailing — so the 3× identical `151821-1280` chips are NOT a 1:1 per-coil match) and future full-harness rebuild.