# setTimingArrayValuesForOutput @ 0x10F04
**Purpose:** Set the ignition timing array output values based on the input mode. Scale and normalize the float values.
**Inputs:** r4: pointer to the timing output struct with the mode byte at offset 0, and the mode-dependent byte at offset 8
**Out:** Writes 4-byte values at offsets 24 and 40 in r4 (scaled timing values, likely in TDC counts or degrees) ; Floating-point computation with constants -5.0 and 65536.0
**Calls:** None (self-contained float math)
Read the byte at r4+0 (mode) ; Branch based on mode: ; Mode 0: Copy 32-bit values from fixed addresses 0xFFFFBC58 → offset 40, 0xFFFFBC5C → offset 24 ; Mode 1: ; a. Load constants: fr5 = -5.0, fr4 =
65536.0 ; b. Read the byte at r4+8 (sub-mode) ; c. Branch based on sub-mode (0, 1, or other): ; Sub-mode 0: Read the float from 0xA794, add -5.0, multiply by 65536.0, convert to int32, store at r4+40 ;
Sub-mode 1: Read the float from 0xA798, same math, store at r4+40 ; Other: Read the float from 0xA790, same math, store at r4+24 ; d. All paths: read float 0xA790, add -5.0, multiply 65536.0, int32 → r4+24 ;
Mode other: return (no operation)
**Draft C:**
```c
struct timing_array {
  uint8_t mode;           // offset 0
  uint8_t _pad[7];
  uint8_t submode;        // offset 8
  // ...
  uint32_t value1;        // offset 24 (timing TDC or degrees)
  uint32_t value2;        // offset 40 (timing TDC or degrees)
};
void setTimingArrayValuesForOutput(timing_array *arr) {
  if (arr->mode == 0) {
    arr->value2 = *(uint32_t *)0xFFFFBC58;
    arr->value1 = *(uint32_t *)0xFFFFBC5C;
  } else if (arr->mode == 1) {
    float scale = 65536.0f;
    float offset = -5.0f;
    float *src_ptr = NULL;
    if (arr->submode == 0) src_ptr = (float *)0xA794;
    else if (arr->submode == 1) src_ptr = (float *)0xA798;
    else src_ptr = (float *)0xA790;
    arr->value2 = (int32_t)((*src_ptr + offset) * scale);
    arr->value1 = (int32_t)((*(float *)0xA790 + offset) * scale);
  }
}
```
**Status:** high ; Branch structure and data flow are clear ; Float addresses and computation constants are visible in the code ; The sub-mode logic branch pattern is consistent
