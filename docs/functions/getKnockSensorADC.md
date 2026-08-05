# getKnockSensorADC @ 0xC3CE

**Note:** 0xC3CE (60E0FC00) / part of `knockRelatedInit` (60E1D400)
## Purpose
Read knock sensor raw ADC, copy to output buffer, apply first-order IIR low-pass filter when RPM is within the 200-2000 RPM band, and validate RPM reference against a 10000 RPM fault limit.

## C Implementation
`c/getKnockSensorADC.c`

## Call Graph
```
getKnockSensorADC
  └── firstOrderFilter @ 0x23B0
```

## RAM Map
| Address | Size | Type | Description |
|---------|------|------|-------------|
| 0xFFFF9F80 | 4 | float | RPM reference |
| 0xFFFF9F0E | 2 | uint16_t | Knock sensor raw ADC |
| 0xFFFFA37A | 2 | uint16_t | ADC output copy |
| 0xFFFFA374 | 4 | float | Filter state (previous output) |
| 0xFFFFA378 | 2 | uint16_t | Filtered integer output |
| 0xFFFFA386 | 1 | uint8_t | Fault byte (0=OK, 1=RPM fault) |

## ROM Calibration
| Address | Value | Description |
|---------|-------|-------------|
| 0x00078EE4 | 200.0 | Low-RPM threshold for filter activation |
| 0x00078EE8 | 2000.0 | High-RPM threshold for filter deactivation |
| 0x00078EEC | 0.004 | First-order IIR filter coefficient |
| 0x00078EA4 | 10000.0 | RPM fault limit |

## Logic
1. Copy KNOCK_ADC_RAW to KNOCK_ADC_OUT
2. If 200 <= RPM < 2000:
   - Apply `firstOrderFilter(raw_float, prev_state, 0.004, 1.0)`
   - Store filtered float state back
   - Convert to uint16 and store to filtered output
3. If RPM >= 10000 → fault byte = 1 (RPM reference out of range)

## Verification Status
- [ ] Verified against emulator (test needs full FPU emulation)
- [x] Logic analyzed from disassembly
- [x] C code written
