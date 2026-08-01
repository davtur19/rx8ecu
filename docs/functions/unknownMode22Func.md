# unknownMode22Func @ 0x66AAA

_source: AI (Haiku) draft, unverified_

**Purpose:** OBD-II UDS Mode 22 (readDataByIdentifier) dispatcher. Looks up requested PID in a table, calls the corresponding handler, assembles response, and sends via CAN.

**Inputs:**
- r4: requested PID (u8)

**Outputs / side effects:**
- Calls appropriate handler function FUN_00066650 with PID index
- Assembles OBD response packet in RAM
- Transmits response via txCAN_EventBased (0x000099B0)
- May set flags/status in response buffer

**Calls:**
- FUN_00066650 (0x00066650): Handler for matched PID (called with index r4)
- FUN_000674b6 (0x000674B6): Setup/encoding function (called with r4=r3, r5=48 or r0=120)
- thunk_FUN_00052aec (0x00067654): Dispatch/completion thunk
- txCAN_EventBased (0x000099B0): Transmit CAN response packet

**Behavior:**
1. Initialize: r5=1 (search count), r14=0 (loop counter), r13=FUN_00066650
2. PID table at 0xFFFFDC03, stride 2 bytes (1 byte per entry):
   - Loop until matching PID found (r14 < r5):
     - Load byte at 0xFFFFDC03 + r14*2 → r2
     - Compare r2 == r4 (requested PID):
       - If match: call FUN_00066650(r14) → returns r0
       - Else: increment r14 and continue
3. If match found:
   - Jump to handler response assembly (0x66AE2+)
4. Handler path (if match):
   - Load byte at 0xFFFFDC05 → r0 (status/flags)
   - Test bit 6: if clear, return (exit)
   - Set bit 4 (0x10) in status → r0
   - Store r0 to 0xFFFFDC05
   - Write response header to 0xFFFFDBE0:
     - [0]: 0x03 (service code 0x22 + 0x40, positive response)
     - [1]: 0x7F (data identifier high byte or header)
     - [2]: read from 0xFFFFDC09 (PID identifier low byte)
     - [3]: 0x78 (separator or padding)
     - [4–7]: 0x00 (zeros / reserved)
   - Call FUN_000674b6(r4=3, r5=48) → assembles data bytes
   - Call thunk_FUN_00052aec(r4=127)
   - Load response length/pointer from 0x0004BB04
   - Jump to txCAN_EventBased (transmit)
5. No match path:
   - Return (0x66B32)

**Draft C:**
```c
#define PID_TABLE_ADDR 0xFFFFDC03
#define STATUS_ADDR 0xFFFFDC05
#define RESPONSE_ADDR 0xFFFFDBE0
#define PID_ID_ADDR 0xFFFFDC09
#define HANDLER_ADDR 0x00066650

void unknownMode22Func(uint8_t requested_pid) {
    // Search PID table
    for (uint8_t i = 0; i < 1; i++) {  // r5=1, only search 1 entry
        uint8_t table_pid = *(volatile uint8_t *)(PID_TABLE_ADDR + i*2);
        if (table_pid == requested_pid) {
            // Found match
            uint8_t *handler = (uint8_t *)HANDLER_ADDR;
            uint8_t result = ((uint8_t (*)(uint8_t))handler)(i);
            
            // Check status flag bit 6
            uint8_t status = *(volatile uint8_t *)STATUS_ADDR;
            if (!(status & 0x40)) {
                return;  // status check failed
            }
            
            // Assemble response
            status |= 0x10;  // set bit 4
            *(volatile uint8_t *)STATUS_ADDR = status;
            
            uint8_t response[8] = {
                0x03,
                0x7F,
                *(volatile uint8_t *)PID_ID_ADDR,
                0x78,
                0, 0, 0, 0
            };
            memcpy((uint8_t *)RESPONSE_ADDR, response, 8);
            
            // Call formatters and send
            ((void (*)(uint8_t, uint8_t))0x674B6)(3, 48);
            ((void (*)(uint8_t))0x67654)(127);
            txCAN_EventBased();
            return;
        }
    }
    // No match
    return;
}
```

**Notes:**
- PID table appears to have only 1 entry (r5=1), suggesting this may be a stub or partial implementation
- Stride of 2 bytes per entry suggests packed table (u8 PID + u8 padding or attribute)
- Response structure: [service_code, high_id, low_id, separator, data...]
- Status bits at 0xFFFFDC05: bit 6 = validity check, bit 4 = response flag
- UNKNOWN: full PID table size/contents, meaning of status bits, handler return values, FUN_000674b6/thunk behavior

**Confidence:** med (dispatcher structure clear, handler and transmission paths recovered, full response assembly uncertain)
