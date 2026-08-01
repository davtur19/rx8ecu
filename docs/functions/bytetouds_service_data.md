# byteToUDS_SERVICE_DATA @ 0x55EEE

_source: AI (Haiku) draft, unverified_

**Purpose:**
Append a single byte to a UDS response data buffer. Increments a length counter and stores the byte at the current end of the response payload.

**Inputs:**
- r5: Byte value to append (byte)
- Implicit: Response buffer and length counter in RAM (likely at fixed address)

**Outputs / side effects:**
- Stores r5 (byte) at [buffer + length]
- Increments UDS response data length counter
- Updates response frame for CAN/serial transmission

**Calls:**
- 0x66A14 (setupForUdsResponse): Finalizes and transmits the response. Called with buffer pointer and length in r6=1.

**Behavior:**
1. Set r6=1 (single byte operation marker)
2. Allocate 4 bytes on stack (r3 points to base)
3. Store r5 at offset 3 (r3+3): the byte to append
4. Call setupForUdsResponse with r4=r15+3 (pointer to byte), r5=r15+3, r6=1
5. Deallocate and return

**Draft C:**
```c
void byteToUDS_SERVICE_DATA(uint8_t byte) {
    uint8_t buffer[1];
    buffer[0] = byte;
    
    // Call response handler to append this byte
    setupForUdsResponse((uint8_t *)buffer);
}
```

**Confidence:** med
- Purpose (append byte to response) is clear from single-byte handling
- Low confidence on exact buffer location; appears to use stack and setupForUdsResponse for final transmission
- Used extensively in response building sequences; typically called repeatedly to build multi-byte responses
- Interaction with setupForUdsResponse (which loops over dispatch table) suggests incremental response assembly

**Note:** Likely called in sequences like:
```
byteToUDS_SERVICE_DATA(0x40 + service_id)  // Positive response SID
byteToUDS_SERVICE_DATA(param1)              // Parameter 1
byteToUDS_SERVICE_DATA(param2)              // Parameter 2
```
