# setupForUdsResponse @ 0x66A14

_source: AI (Haiku) draft, unverified_

**Purpose:**
Iterate over UDS response handlers/builders indexed by a selector. Dispatches to multiple callback functions (pack_for_OBD_response?) based on input service ID/index.

**Inputs:**
- r4: UDS service ID or response builder index (byte, zero-extended)
- r7 (implicit): Loop counter initialization (always 1)

**Outputs / side effects:**
- Calls up to 2 response builder functions via function pointers
- Constructs UDS response packet data (called functions modify global buffer)

**Calls:**
- 0x6670C (pack_for_OBD_response?): Callback at r13. Called with r4=loop index (0 or 1). Builds response data for positive UDS response.

**Behavior:**
1. Load dispatch table at 0xFFFFDC03 (2-byte entries per index)
2. Initialize r14=0 (loop counter)
3. Loop: Check dispatch table[r14] against r4 (service ID)
4. If match found, call handler at 0x6670C with r4=loop index
5. Increment r14, continue while r14 < r7 (r7=1, so max 2 iterations)
6. Return to caller

**Draft C:**
```c
void setupForUdsResponse(uint8_t serviceID) {
    uint8_t *dispatchTable = (uint8_t *)0xFFFFDC03;
    void (*handler)(uint8_t) = (void *)0x6670C;
    
    for (uint8_t i = 0; i < 1; i++) {
        if (dispatchTable[i * 2] == serviceID) {
            handler(i);
        }
    }
}
```

**Confidence:** med
- Loop structure and dispatch logic are clear
- Exact purpose of pack_for_OBD_response unknown; inferred from name
- Could be iterating response builders or multiple UDS services in parallel
- r7=1 limit suggests only 2 dispatch table entries checked
