# setupForUdsResponse @ 0x66A14
**Purpose:** Iterate over UDS response handlers/builders indexed by a selector. Dispatch to multiple callback functions (pack_for_OBD_response?) based on the input service ID/index.
**Inputs:** r4: UDS service ID or response builder index (byte, zero-extended) ; r7 (implicit): Loop counter initialization (always 1)
**Out:** Calls up to 2 response builder functions through function pointers ; Constructs UDS response packet data (the called functions modify the global buffer)
**Calls:** 0x6670C (pack_for_OBD_response?): Callback at r13. Called with r4=loop index (0 or 1). Builds response data for a positive UDS response.
Load the dispatch table at 0xFFFFDC03 (2-byte entries per index) ; Initialize r14=0 (loop counter) ; Loop: Check dispatch table[r14] against r4 (service ID) ; If a match is found, call the handler at 0x6670C with
r4=loop index ; Increment r14, continue while r14 < r7 (r7=1, so max 2 iterations) ; Return to the caller
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
**Status:** med ; Loop structure and dispatch logic are clear ; The exact purpose of pack_for_OBD_response is unknown; it is inferred from the name ; It could iterate response builders or multiple UDS services in parallel ; The r7=1 limit suggests only 2 dispatch table entries are checked
