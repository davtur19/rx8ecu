# getOLStatusforOBD @ 0x534B2
**Purpose:** OBD-II Mode 22 handler (unclear PID). Returns an engine operational/load status code based on multiple sensor flags and engine load thresholds.
**Inputs:** None (reads global flags and engine load)
**Out:** Returns u8 in r0 (status code: 1, 2, 4, 8, or 16) ; Reads multiple RAM globals for state flags and thresholds
**Calls:** None
Load engine load float from 0xA9FC (RAM) → fr4 ; Load status byte from 0xAE83 (RAM) → r5 ; Load flag byte from 0xAD88 (RAM) → r7 ; Load status byte from 0xAE82 (RAM) → r6 ; Check if r5 == 1: ; If yes,
check if r7 == 0: ; If r7 == 0, return 16 ; Else continue ; If no, check if r4 == 1: ; If yes, return 2 ; Check if r6 == 0: ; If yes, return 4 ; Load threshold from 0x6FC40 (ROM constant) → fr3
(threshold value) ; Compare fr4 (engine load) > fr3: ; If yes, return 1 ; If no, return 8
**Draft C:**
```c
uint8_t getOLStatusforOBD(void) {
    volatile float32 *eng_load_ptr = (volatile float32 *) 0xA9FC;
    volatile uint8_t *status1_ptr = (volatile uint8_t *) 0xAE83;
    volatile uint8_t *flag1_ptr = (volatile uint8_t *) 0xAD88;
    volatile uint8_t *status2_ptr = (volatile uint8_t *) 0xAE82;
    volatile float32 *threshold_ptr = (volatile float32 *) 0x6FC40;
    float32 eng_load = *eng_load_ptr;
    uint8_t status1 = *status1_ptr;
    uint8_t flag1 = *flag1_ptr;
    uint8_t status2 = *status2_ptr;
    float32 threshold = *threshold_ptr;
    if (status1 == 1) {
        if (flag1 == 0) {
            return 16;  // condition A
        }
    } else if (eng_load == 1) {
        return 2;  // condition B
    }
    if (status2 == 0) {
        return 4;  // condition C
    }
    if (eng_load > threshold) {
        return 1;  // condition D (high load)
    } else {
        return 8;  // condition E (low/normal load)
    }
}
```
**Status:** low (structure recovered, semantics unclear, RAM addresses unconfirmed, conditional logic may be misinterpreted due to extraction limits)
Notes: Purpose unclear from name; "OL" may refer to Open Loop (fuel control mode) status ; Returns discrete status codes (1, 2, 4, 8, 16) rather than bitfield ; Multiple RAM addresses suggest multiplex conditional logic ; Threshold at 0x6FC40 is likely engine load limit (e.g., 60% for open-loop transition) ; UNKNOWN: exact PID mapping, meaning of each status code, purpose of status1/status2/flag1
