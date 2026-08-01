# Main harness connector — pinout (bench power-up subset)

Source: `RX8_Sel_pinout.pdf` (moved to private storage, not shipped) + `Rx8_Pin_Out_2048x2048.PNG` (Adaptronic Select
S1 RX-8 install docs — lists factory function per pin, cross-referenced against their own
replacement assignment). Same physical connector across all N3J1-18-881x variants.
Pin naming: `<block 1-5><letter>`, view from loom side of plug.

---

## Pins needed to power the ECU on the bench (no car, no relay box)

| Pin(s) | Factory function | Bench wiring |
|---|---|---|
| **4A, 4J, 5D, 5O, 5R, 5T** | Ground (×6, all "shared with both ECUs" in the Adaptronic doc = present in stock harness too) | Tie all together → bench supply **GND** |
| **5AC, 5AF** | Power from Main Relay (this is the ECU's actual logic/CPU supply rail — normally only live once the main relay has closed) | Bench: feed **+12V** directly here — bypasses the relay, simulates "relay already closed" |
| **4Q** | Ignition switch +12V | Bench: **+12V** (can be same rail as 5AC/5AF) |
| **5J** | Constant power (battery-side keep-alive, not relay-switched) | Bench: **+12V**, same rail is fine |
| **4S** | CAN low | To J2534 adapter CAN-L |
| **4V** | CAN high | To J2534 adapter CAN-H |

That's it for a UDS session: 6 grounds commoned, +12V into 5AC/5AF + 4Q + 5J, CAN-H/L to the
adapter. No main relay, no DBW relay, no starter signal needed just to talk UDS and dump ROM/EEPROM
shadow.

**Do not drive anything into 4E** ("Main Relay enable") — it's an ECU *output* (normally
low-side-switches the main relay coil to ground to self-latch power). Leave it disconnected/floating;
forcing voltage into it risks shorting an open-drain driver.

## Not needed for a read-only bench session (documented for completeness)
- **4C / 5H** — Drive-By-Wire relay power/control. Only matters if you need the ETB to be live
  (e.g. throttle-related DTCs clear or actuator tests) — skip for a plain ROM/EEPROM dump.
- **5A** — Starter signal, irrelevant off-car.
- Everything else (injectors, ignition outputs, O2 heaters, AFM, TPS, knock, CAS, solenoids, A/C,
  etc.) — sensor/actuator I/O, not required for the CPU to boot and answer UDS. Expect DTCs to set
  for all the "missing" sensors; harmless for a read-only session.

---

## Full connector reference

Complete factory-function-per-pin table (injectors, ignition outputs, sensors, CAS, O2, DBW, etc.)
is in `RX8_Sel_pinout.pdf` (moved to private storage, not shipped) — it's kept there, no need to duplicate the whole
thing here. Useful later for: understanding the coil-driver chips found on the board
(`docs/notes/HARDWARE.md` — IC780/IC820/IC830 guessed as ignition drivers; PDF confirms 4 ignition
outputs exist: 2AA/2AD front leading/trailing, 2Z/2AC rear leading/trailing — so the board's 3×
identical `151821-1280` chips are NOT a 1:1 per-coil match, worth revisiting) and for any future
full harness/bench rebuild.
