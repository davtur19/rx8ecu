# getFaultStatus @ 0x6743C

## Purpose
Check the fault status for a given fault channel index. Returns 1 if a fault is active/pending, 0 otherwise. This is a critical query function with 78+ callers across the ECU firmware.

## C Implementation
`c/getFaultStatus.c`

## Call Graph
```
getFaultStatus
  └── getFaultEvalState @ 0x67494  (secondary check)
       ├── sub_67534
       ├── sub_67538
       ├── sub_675AC
       ├── sub_675CA
       └── sub_675E6
```

## RAM Map
| Address | Size | Type | Description |
|---------|------|------|-------------|
| 0xFFFFD96C | 4 | uint32_t | Fault enable mask (runtime-configurable) |

## ROM Table
| Address | Description |
|---------|-------------|
| 0x0007E4DC | Fault status table (per-channel entries, 32-bit each) |

## Logic
1. Load fault enable mask from RAM (0xFFFFD96C)
2. Load fault table entry from ROM (0x0007E4DC + channel * 4)
3. If (entry & enable_mask) has low 16 bits non-zero → immediate fault, return 1
4. Otherwise, call `getFaultEvalState(channel)` for extended evaluation
5. If (entry & eval_result) has upper 16 bits non-zero → confirmed fault, return 1
6. Return 0 (no fault)

## Callers
This function is called from approximately 78 locations in the firmware,
including sensor monitoring tasks, DTC evaluation, and subsystem health checks.

## Verification Status
- [ ] Verified against emulator (needs getFaultEvalState stubs)
- [x] Logic analyzed from disassembly
- [x] C code written

## Note: earlier location @ 0x652F0 (doc merged from docs/functions/getfaultstatus.md)
- An earlier/variant implementation of the same two-path fault query lives at **0x652F0** (referenced as `getFaultStatus??` by `sourceOf10kReset.md` and `symbols/callgraph.csv`, ~40 callers incl. can216RXFaultEval, getCAN47RXStatus).
- Different concrete addresses than the 0x6743C version:
  - ROM fault table at **0x0007CCB8** (word entries, indexed by DTC index) — vs 0x0007E4DC here
  - RAM fault flags buffer at **0xFFFFD740** (word) — vs 0xFFFFD96C here
  - Helper **sub_65348 @ 0x65348** (takes r4 index, returns candidate in r0; per CATALOG_MASTER.csv this region overlaps `getFaultEvalState` 0x65336–0x65348) — vs getFaultEvalState @ 0x67494 here
- Same two-path structure: AND table entry with flags; if zero, call helper and re-check with **0xFFFF0000** mask; non-zero → fault active.
- Draft C of the 0x652F0 version (dtcIndex word → `faultTable[dtcIndex] & flags`, alt-path via sub_65348) was in the deleted doc; status was "med" (helper purpose and two-path rationale unconfirmed).
