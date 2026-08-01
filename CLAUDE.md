# rx8ecu

Full open-source RE of the Mazda RX-8 ECU (Denso; Renesas SH-2E, HD64F7055).
Goal: ROM map, read/flash/calibrate tools, eventually open clone firmware.

**Start here**: `docs/notes/KNOWLEDGE.md` — non-discoverable facts (keys, UDS quirks, EEPROM addresses).  
**Active RE work**: `docs/notes/ECU.md` — function labels, code cave map, CAN table, open items.  
**Current state**: the session notes (kept in private storage, not shipped) — where we left off, next step, Ghidra state.

## Notes layout

Three memory layers, aligned with episodic/semantic agent memory research:

| File | Layer | Purpose | When to read |
|---|---|---|---|
| `docs/notes/KNOWLEDGE.md` | Semantic | Non-discoverable facts: ECU ID, UDS quirks, keys, EEPROM | Every session |
| Session notes (private storage) | Episodic | Current task, last state, next step, Ghidra state, open questions | Every session |
| `docs/notes/<topic>.md` | Working | Topic notes created on demand (e.g. `ECU.md`, `TOOLS.md`) | When working that topic |
| `docs/notes/FINDINGS.md` | Archive | Chronological confirmed facts | When researching history |
| `docs/notes/ROM_CODE_MAP.md` | Reference | Full stock vs mod diff and function map | Deep RE reference |
| `docs/notes/FULL_ANALYSIS.md` | Reference | Pseudocode / C decompilation | Deep RE reference |
| `docs/notes/CAN_PROTOCOL.md` | Reference | Full CAN ID list and protocol details | CAN work |
| `PLANS.md` | Planning | Multi-step investigation plans | Long investigations |

**Rule**: `KNOWLEDGE.md` contains only facts that cannot be discovered by reading files or running tools.
Do not add procedural instructions, reminders, or tool usage guides — those cost tokens without benefit.

## Session memory rule

**At the end of every significant work session**, overwrite the session notes (kept in private storage):
- Active task (1 line)
- Last confirmed state (3–5 bullets, facts only)
- Ghidra state (program loaded, labels set)
- Next concrete step (1–2 items max)
- Open questions (max 3)

This is episodic memory — it replaces the previous entry, it is not a log.
Confirmed facts always go to `FINDINGS.md`, not the ephemeral session notes.

## Quick commands

```bash
python tools/denso_ck.py roms/stock/my_rom.bin              # verify checksum
python tools/denso_ck.py roms/stock/my_rom.bin -f           # fix checksum in-place
```

Live-ECU tooling is **private and not shipped** in this repo: the ROM dump tool
(`tools/uds/[REDACTED].py` in the private checkout — 32-bit Python, OBDX Pro VX)
and the LC-patch injector (`tools/[REDACTED].py`) have **no public
equivalent** here. See `docs/notes/DUMP_ALL.md` for the dump procedure and
`docs/notes/ECU.md` (§[REDACTED] LC Patch) for the injection description.

## Temp work

New artifacts go to `tmp/<topic>/` first. See `tmp/README.md` for the promotion table.
