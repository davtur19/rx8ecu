# arbitrateFuelCut @ 0xE2D8
**Purpose:** Evaluate multiple fault/protection conditions and determine if fuel cut should be applied (bit 0) or secondary protection (bit 1).
**Inputs:** None (reads global flags only)
**Out:** r0: Fuel cut arbitration result written to 0xA430 ; Bit 0: Fuel cut enabled (from first condition set) ; Bit 1: Secondary protection (from second condition set)
**Calls:** None (purely conditional flag checks)
Initialize r4 = 0 (result accumulator). First condition set** (13 checks, each reads a byte flag): Check flags at: 0xA444, 0xA4A4, 0xA9D4, 0xC89C, 0xCB41, 0xBCB6, 0xCB42, 0xC945, 0xCC8A, 0xCC8B,
0xCC8C, 0xCC8D, 0xC1EC. If ANY of these flags == 1 (or for 0xC1EC, just non-zero), set r4 = 1 (fuel cut enabled). Second condition set** (13 checks, similar): Check flags at: 0xA445, 0xA4A5,
0xA9D4, 0xC89C, 0xCB41, 0xBCB7, 0xCB43, 0xC945, 0xCC8A, 0xCC8B, 0xCC8C, 0xCC8D, 0xC1EC. If ANY of these flags == 1 (or 0xC1EC non-zero), set bit 1: r4 |= 2. Write the result r4 to 0xA430.
**Draft C:**
```c
void arbitrateFuelCut(void) {
    uint8_t result = 0;
    // First set of conditions — fuel cut enable
    uint8_t cond_set1[] = {
        *(uint8_t *)0xA444, *(uint8_t *)0xA4A4, *(uint8_t *)0xA9D4,
        *(uint8_t *)0xC89C, *(uint8_t *)0xCB41, *(uint8_t *)0xBCB6,
        *(uint8_t *)0xCB42, *(uint8_t *)0xC945, *(uint8_t *)0xCC8A,
        *(uint8_t *)0xCC8B, *(uint8_t *)0xCC8C, *(uint8_t *)0xCC8D
    };
    for (int i = 0; i < 12; i++) {
        if (cond_set1[i] == 1) {
            result |= 0x01;
            break;
        }
    }
    if (*(uint8_t *)0xC1EC != 0) {
        result |= 0x01;
    }
    // Second set of conditions — secondary protection
    uint8_t cond_set2[] = {
        *(uint8_t *)0xA445, *(uint8_t *)0xA4A5, *(uint8_t *)0xA9D4,
        *(uint8_t *)0xC89C, *(uint8_t *)0xCB41, *(uint8_t *)0xBCB7,
        *(uint8_t *)0xCB43, *(uint8_t *)0xC945, *(uint8_t *)0xCC8A,
        *(uint8_t *)0xCC8B, *(uint8_t *)0xCC8C, *(uint8_t *)0xCC8D
    };
    for (int i = 0; i < 12; i++) {
        if (cond_set2[i] == 1) {
            result |= 0x02;
            break;
        }
    }
    if (*(uint8_t *)0xC1EC != 0) {
        result |= 0x02;
    }
    *(volatile uint16_t *)0xA430 = result;
}
```
**Status:** med ; Clear overall structure (two condition sets, bitwise accumulation) ; Uncertainties: ; Exact semantics of each individual flag (fault type, enable status) ; Whether all 13 checks are OR'd or if there is additional logic ; Meaning of 0xA430 result bits in fuel control pipeline ; Some addresses appear in both sets (0xA9D4, 0xC89C, 0xCB41, 0xC945, 0xCC8A–D, 0xC1EC); may indicate shared conditions
