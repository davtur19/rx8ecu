# dtcCodeTypeInit @ 0x5991E

**Purpose:** Initialize DTC (Diagnostic Trouble Code) data structures in RAM.
Out: Zeroes two RAM locations: 0xFFFFD0F8 (1 byte) and 0xFFFFD0FA (2 bytes)  Behavior: Set r4 = 0 ; Write byte 0 to 0xFFFFD0F8 ; Write word 0 to 0xFFFFD0FA
**Status:** high – simple init pattern, addresses in DTC RAM region (0xFFFFD0xx), equinox name reliable
