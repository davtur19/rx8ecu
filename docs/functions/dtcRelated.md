# dtcRelated @ 0x062002

**Track-A verification:** emulator (500 random states × 8 type selectors × 4 enable modes) — `c/tests/test_dtcRelated.py`

## Overview

This function scans the 21-entry DTC handler context table @0xFFFF87D8 (16 B/entry). It appends
the 16-bit DTC code of every entry whose type byte (entry+6) matches the requested
type selector to a caller-supplied word array. It returns the count in r0.

**Matches are written consecutively (packed):** out[0], out[1], ... in scan order;
the running count doubles as the output index (`r12 = out + 2·count` @0x6207A–0x62088).
The output array is *not* indexed by DTC entry number.

## Inputs

- r4: DTC type selector (0x00, 0x60, 0x80, 0xC0, 0xC1, 0x50, 0xF0, 0x70)
- r5: enable gate — 0 = none; 1 = `tableA[code]@0x7E220 == 1`;
  2 = `tableB[code]@0x7E2AC == 1`; any other value disqualifies the entry
- r6: caller-supplied word array (packed output)

## Outputs

- r0: number of matching DTC codes written to the array

## Logic

```c
uint8_t dtcRelated(uint8_t type, uint8_t enable, uint16_t *out)
{
    uint16_t cur_idx = *(volatile uint16_t *)0xFFFF8928; /* DTC being serviced */
    uint8_t  count = 0;

    for (i = 0; i < 21; i++) {
        if (i == cur_idx)                /* skip the DTC being serviced */
            continue;
        flag = (0xFFFF87D8 + 16*i)[6];   /* type byte */
        code = *(uint16_t *)(0xFFFF87D8 + 16*i);

        if (enable) {
            if (enable == 1) ok = (rom[0x7E220 + code] == 1);
            else if (enable == 2) ok = (rom[0x7E2AC + code] == 1);
            if (!ok) continue;
        }

        switch (type) {
        case 0x00: ok = (flag == 0x00);                    break;
        case 0x60: ok = (1 <= flag && flag <= 0x3F);       break;
        case 0x80: ok = (flag & 0x80);                     break;
        case 0xC0: ok = (flag == 0xC0);                    break;
        case 0xC1: ok = (flag == 0xC1);                    break;
        case 0x50: ok = (flag == 0x50);                    break;
        case 0xF0: ok = (1 <= flag && flag <= 0x3F) || (flag & 0x80); break;
        case 0x70: ok = (0x81 <= flag && flag <= 0xBF);    break;
        default:   ok = 0;                                 break;
        }
        if (ok) { out[count] = code; count++; }   /* packed output */
    }
    return count;
}
```

## Key disassembly details

- Prologue (0x62002–0x6201A): r11 = 0 (loop index), r10 = 1, r9 = 0x0080
  (bit-7 mask), r2 = 0xFFFF8928 (current index pointer), r12 = r6 (out).
- Loop head (0x6201C–0x6202C): `mov.w @r2,r3`; sign-extend/zero-extend with a
  stack round-trip + `extu.w`; `cmp/eq r3,r11`; `bf/s` → process, else
  `bra 0x62168` (skip).
- Store (0x62134–0x62168): `r12 = out + 2·count` (`extu.w r7,r12; shll r12;
  add r6,r12`), `mov.w r13,@r12`, `count++`.
- The ROM tables are byte arrays indexed by the 16-bit DTC code:
  tableA @0x0007E220 (property/class byte), tableB @0x0007E2AC (enable byte).

## Verification

- [x] Disassembly confirmed against capstone (see `disasm_sh2e.py`)
- [x] C code written (`c/dtcRelated.c`)
- [x] Emulator test: 500 random states; type + enable dispatch vs the ROM
  executable bytes; it catches the packed-output indexing (out[i] → out[count])

## Supersedes

The earlier draft of this file (address 0x5FEB6, tables 0x0007C9FC /
0x0007CA88) was based on the 60E0FC00 build and is **not valid** for
60E1D400.bin.  Consolidated context: `dtc_management.md`.
