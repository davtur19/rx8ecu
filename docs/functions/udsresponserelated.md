# udsResponseRelated @ 0x52A12

_source: AI (Haiku) draft, unverified_

**Purpose:**
Build or prepare a UDS response structure on the stack and dispatch to a handler (FUN_00067646). Likely stage data for negative or conditional UDS responses.

**Inputs:**
- r4: UDS service byte or response code (byte, zero-extended)
- r5: Secondary parameter (word, zero-extended to r4 slot)

**Outputs / side effects:**
- Creates a 16-byte stack structure with:
  - Offset 0: r4 (service/code)
  - Offset 4: r5 (parameter 1)
  - Offset 8: r5 again (parameter 2, duplicated)
  - Offset 12: 0 (null)
- Calls FUN_00067646 with pointer to this structure
- Returns (caller cleans stack)

**Calls:**
- 0x67646 (FUN_00067646): Handler. Takes r4=pointer to 16-byte structure.

**Behavior:**
1. Allocate 16 bytes on stack (r14 points to base)
2. Store r4 (zero-extended) at offset 0
3. Zero-extend r5 to 32-bit, store at offsets 4 and 8
4. Store 0 at offset 12
5. Call FUN_00067646 with r4=pointer to structure
6. Deallocate and return

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

**Confidence:** med
- Stack frame allocation and parameter setup are clear
- Purpose of FUN_00067646 unknown; could be response validation or sending
- Parameter duplication (r5 stored twice) suggests it may be used twice or is intentional data padding
