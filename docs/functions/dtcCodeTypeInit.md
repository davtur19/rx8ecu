# dtcCodeTypeInit @ 0x5991E
_source: AI (Haiku) draft, unverified_

**Purpose:** Initialize DTC (Diagnostic Trouble Code) data structures in RAM.

**Inputs:** None

**Outputs / side effects:**
- Zeroes two RAM locations: 0xFFFFD0F8 (1 byte) and 0xFFFFD0FA (2 bytes)

**Calls:** None

**Behavior:**
1. Set r4 = 0
2. Write byte 0 to 0xFFFFD0F8
3. Write word 0 to 0xFFFFD0FA
4. Return

**Draft C:**
```c
void dtcCodeTypeInit(void) {
  *(uint8_t*)0xFFFFD0F8 = 0;
  *(uint16_t*)0xFFFFD0FA = 0;
}
```

**Confidence:** high – simple init pattern, addresses in DTC RAM region (0xFFFFD0xx), equinox name reliable
