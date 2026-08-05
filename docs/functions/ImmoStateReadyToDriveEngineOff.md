# ImmoStateReadyToDriveEngineOff @ 0x35978
**Purpose:** Manage immobilizer ready-to-drive state during engine-off period. Polls ADC keygen and manages state transitions and timeout counters.
**Inputs:** State flag from 0xFFFFC23A (1 = active check, 5 = timeout/wait) ; State/counter storage at 0xFFFFC224, 0xFFFFC228, 0xFFFFC22E
**Out:** Updates immobilizer state value at 0xFFFFC224 (polled value from ADC) ; Updates state byte at 0xFFFFC23A ; Writes timeout value 0x01F4 to 0xFFFFC228 ; Decrements counter at 0xFFFFC22E (with underflow to 0xFFFF)
**Calls:** Immo_Keygen_related_ADC (0x35F9C) - reads ADC immobilizer keygen value ; (indirect via branching) Additional diagnostic/timeout handlers
Check state flag at 0xFFFFC23A ; If state == 1: ; Loop polling Immo_Keygen_related_ADC until value stabilizes ; Write 0x01F4 timeout to 0xFFFFC228 ; If state == 5: ; Decrement counter at 0xFFFFC22E
(saturate at 0xFFFF) ; If counter reaches 0, trigger diagnostic/transition routine ; Update state byte accordingly
**Draft C:**
```c
void ImmoStateReadyToDriveEngineOff() {
    u8 state = *(u8*)0xFFFFC23A;
    if (state == 1) {
        u32 prevVal = *(u32*)0xFFFFC224;
        u32 currVal;
        do {
            currVal = Immo_Keygen_related_ADC();
            *(u32*)0xFFFFC224 = currVal;
        } while (currVal != prevVal);
        *(u16*)0xFFFFC228 = 0x01F4;  // timeout = 500ms
    } else if (state == 5) {
        i16 counter = *(i16*)0xFFFFC22E;
        counter--;
        if (counter < 0) counter = -1;  // saturate at 0xFFFF
        *(i16*)0xFFFFC22E = counter;
        if (counter == 0) {
            // transition/timeout handler
        }
    }
}
```
**Status:** med - State machine logic clear; exact state values and timeout semantics need verification.
**Uncertainties:** Complete state machine (only states 1, 5 identified) ; Whether timeout value 0x01F4 is milliseconds or cycles ; Exact stabilization/polling loop condition ; What triggers transition from state 1 to state 5
