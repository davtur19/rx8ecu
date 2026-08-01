# getFaultStatus @ 0x6743C

## Location
- **Image:** 60E1D400.bin
- **Address:** 0x6743C
- **End:** 0x67482

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
