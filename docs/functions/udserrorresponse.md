# udsErrorResponse @ 0x52A5A
**Purpose:** Construct and send a negative (error) UDS response. Build a 3-byte negative response frame: [0x7F, original_service, nrc_code]. Call setupForUdsResponse to transmit it.
**Inputs:** r4: Original UDS service ID (byte) ; r5: Negative Response Code (NRC) / fault code (byte)
**Out:** Constructs the negative response: [0x7F, r4, r5] ; Calls setupForUdsResponse(r4) to transmit it over CAN or serial ; Builds the response in a 3-byte stack buffer at r14
**Calls:** 0x66A14 (setupForUdsResponse): Transmits the error response. Called with r4=original service ID, r5=pointer to the 3-byte response, r6=3 (length).
Set r3=0x7F (negative response service ID) ; Set r6=3 (response length) ; Allocate 4 bytes on the stack (r14 points to the base) ; Store [0x7F, r4 (service), r5 (NRC)] at r14 ; Call setupForUdsResponse with
r4=r14 (buffer), r5=r14 (buffer), r6=3 ; Deallocate and return
**Draft C:**
```c
void udsErrorResponse(uint8_t service, uint8_t nrc) {
    uint8_t response[3];
    response[0] = 0x7F;        // Negative response SID
    response[1] = service;     // Original service
    response[2] = nrc;         // Negative response code
    setupForUdsResponse((uint8_t *)response);
}
```
**Status:** high ; The negative response structure (0x7F format) is standard UDS/KWP2000 ISO 14229. The purpose and format are unmistakable. The NRC codes match ISO 14229 (for example, ServiceNotSupported and SecurityAccessDenied).
