# udsResponseRelated @ 0x52A12
**Purpose:** Build or prepare a UDS response structure on the stack. Dispatch it to a handler (FUN_00067646). This likely stages data for negative or conditional UDS responses.
**Inputs:** r4: UDS service byte or response code (byte, zero-extended) ; r5: Secondary parameter (word, zero-extended to the r4 slot)
**Out:** Creates a 16-byte stack structure with: ; Offset 0: r4 (service/code) ; Offset 4: r5 (parameter 1) ; Offset 8: r5 again (parameter 2, duplicated) ; Offset 12: 0 (null) ; Calls FUN_00067646 with a pointer to this structure ; Returns (the caller cleans the stack)
**Calls:** 0x67646 (FUN_00067646): Handler. Takes r4=pointer to the 16-byte structure.
Allocate 16 bytes on the stack (r14 points to the base) ; Store r4 (zero-extended) at offset 0 ; Zero-extend r5 to 32-bit, store it at offsets 4 and 8 ; Store 0 at offset 12 ; Call FUN_00067646 with r4=pointer
to the structure ; Deallocate and return
**Draft C:**
```c
void udsResponseRelated(uint8_t service, uint16_t param) {
    struct UDS_Response {
        uint32_t service;
        uint32_t param1;
        uint32_t param2;
        uint32_t padding;
    } resp;
    resp.service = (uint32_t)service;
    resp.param1 = (uint32_t)param;
    resp.param2 = (uint32_t)param;
    resp.padding = 0;
    FUN_00067646(&resp);
}
```
**Status:** med ; The stack frame allocation and parameter setup are clear. The purpose of FUN_00067646 is unknown; it could be response validation or sending. The parameter duplication (r5 stored twice) suggests it may be used twice or is intentional data padding.
