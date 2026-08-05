# udsServiceResponse @ 0x66A74
**Purpose:** Similar to setupForUdsResponse but dispatches to FUN_00066768 instead. Likely an alternative or parallel UDS response handler dispatcher for a different set of services.
**Inputs:** r4: UDS service ID or response index (byte, zero-extended) ; r7 (implicit): Loop counter initialization (always 1)
**Out:** Calls response service handler at 0x66768 up to 2 times ; Modifies response buffer or ECU state
**Calls:** 0x66768 (FUN_00066768): Handler callback. Called with r4=loop index (0 or 1).
**Behavior:** Load dispatch table at 0xFFFFDC03 ; Initialize r14=0 ; Loop: Check dispatch table[r14] against r4 ; If match, call FUN_00066768(r14) ; Increment r14, loop while r14 < r7 (r7=1, so 2 max iterations)
**Draft C:**
```c
void udsServiceResponse(uint8_t serviceID) {
    uint8_t *dispatchTable = (uint8_t *)0xFFFFDC03;
    void (*handler)(uint8_t) = (void *)0x66768;
    for (uint8_t i = 0; i < 1; i++) {
        if (dispatchTable[i * 2] == serviceID) {
            handler(i);
        }
    }
}
```
**Status:** high ; Structure identical to setupForUdsResponse (0x66A14) ; Different handler function suggests different UDS service layer or alternative flow ; Shared dispatch table (0xFFFFDC03) indicates these are related service groups
