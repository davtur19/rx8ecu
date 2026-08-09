# pack_for_OBD_response @ 0x6670C
**Purpose:** Helper utility. It packs bytes from a source buffer into a response buffer. It performs length and bounds checking. OBD-II Mode 22 response formatters use this helper.
**Inputs:** r4: count (number of bytes to pack) ; r5: source buffer pointer ; r6: (implicit, used in bounds checks)
**Out:** Populates output buffer at offset from base pointer r14 ; Updates response length counter at r14+0 (word) ; Returns nothing (void)
**Calls:** None
Save r12, r13, r14, macl (callee-save regs) ; Initialize: ; r13 = 0 (loop counter) ; r7 = 0 (unused or secondary counter) ; r12 = 0x0465 (max response length limit, likely 1125 bytes) ; r14 =
0xFFFFD76C + (r4 * 0x046C) (compute output buffer base for this response type) ; Check sign of r6 (count from r4): ; If negative, jump to exit ; Loop (while r13 < r4): ; Load word at offset in r14
(current length) → r3, r2 ; Compare r3 == r2 (sanity check): ; If equal, skip byte write and continue to bounds check ; Else: load byte from r5 → r1, write to r14+6+length → output ; Increment length
at r14 by 1 ; Check if length >= r12 (max): ; If yes, reset length to 0 and break ; Increment loop counter r7 ; Move to next source byte r5++ ; Restore regs and return
**Draft C:**
```c
void pack_for_OBD_response(uint8_t count, uint8_t *src, ???) {
    #define RESP_BASE 0xFFFFD76C
    #define RESP_STRUCT_SIZE 0x046C
    #define RESP_DATA_OFFSET 6
    #define MAX_RESP_LEN 0x0465  // 1125 bytes
    uint8_t *resp = (uint8_t *)(RESP_BASE + (count * RESP_STRUCT_SIZE));
    uint16_t *resp_len = (uint16_t *)resp;
    for (uint8_t i = 0; i < count; i++) {
        if (*resp_len >= MAX_RESP_LEN) {
            *resp_len = 0;
            break;
        }
        resp[RESP_DATA_OFFSET + *resp_len] = src[i];
        (*resp_len)++;
    }
}
```
**Status:** med — loop and buffer management recovered; response-format semantics unclear.
Notes: part of the OBD-II response assembly pipeline; stride 0x046C (1132 B per response type); bounds check caps at 1125 B; data written at offset 6 (6-byte header: PID, status...). UNKNOWN: buffer layout, r6 meaning, response-type enumeration.
