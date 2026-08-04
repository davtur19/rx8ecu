# AGENTS.md

Work from confirmed evidence. Confirmed facts → `docs/notes/FINDINGS.md`.
Before editing any binary: verify checksum, assert expected bytes, write to `tmp/` first.
Before using Ghidra MCP: confirm it's running and the correct program is loaded.

## Project orientation

- **Start here**: `docs/notes/KNOWLEDGE.md` — non-discoverable facts (keys, UDS quirks, EEPROM addresses).
- **Active RE work**: `docs/notes/ECU.md` — function labels, code cave map, CAN table, open items.
- **Current state**: the session notes (kept in private storage, not shipped) — where we left off, next step, Ghidra state.

## Notes layout

Three memory layers:

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

**Rule**: `KNOWLEDGE.md` contains only facts that cannot be discovered by reading files or running tools. No procedural instructions, reminders, or tool-usage guides.

## Session memory rule

**At the end of every significant work session**, overwrite the session notes (kept in private storage, not shipped):
- Active task (1 line)
- Last confirmed state (3–5 bullets, facts only)
- Ghidra state (program loaded, labels set)
- Next concrete step (1–2 items max)
- Open questions (max 3)

Episodic memory: replaces the previous entry, not a log. Confirmed facts go to `FINDINGS.md`, not session notes.

## Quick commands

```bash
python tools/denso_ck.py roms/stock/my_rom.bin              # verify checksum
python tools/denso_ck.py roms/stock/my_rom.bin -f           # fix checksum in-place
```

Live-ECU tooling is **private and not shipped** in this repo: the ROM dump tool
(32-bit Python, OBDX Pro VX) and the LC-patch injector have **no public
equivalent** here. Dump procedure: `docs/notes/DUMP_ALL.md`; LC-patch injection:
`docs/notes/ECU.md`.

## Temp work

New artifacts go to `tmp/<topic>/` first. See `tmp/README.md` for the promotion table.

## Verifica rapida

Rituale su ogni file modificato (`c/*.c`, `c/tests/*`, `tools/*.py`, `symbols/*.csv`):
`fn → changed → all → make test`. `fastverify.py` è read-only (artefatti in `/tmp`),
auto-rileva la repo root, exit 0/1/2 (ok / failure / env-error):

```bash
python3 ../.opencode/fastverify.py fn <nome|0xADDR|rom.bin>   # ~0.4 s — verifica la funzione modificata
python3 ../.opencode/fastverify.py changed                    # test dei file modificati (git status + mtime)
python3 ../.opencode/fastverify.py all                        # famiglie + test C host (continue-on-fail) + changed
make test                                                     # gate finale (~21 s) prima del commit
```
