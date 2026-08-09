# evapRelated @ 0x224F6
**Purpose:** Orchestrate EVAP (evaporative emission control) system operations through a sequence of sub-function calls with interrupt management.
**Inputs:** System state (no explicit parameters; reads from various RAM locations in the called functions)
**Out:** EVAP solenoid/canister control writes (in the called functions) ; Purge valve control ; Fuel vapor pressure monitoring ; Fault logging (if applicable)
**Calls:** getSR @ 0x3920 (get status register / disable interrupts) ; FUN_0004a46c @ 0x4A46C (unknown, EVAP sub-operation 1) ; FUN_0002264a @ 0x2264A (unknown, EVAP sub-operation 2) ; FUN_000226f6 @ 0x226F6 (unknown, EVAP sub-operation 3) ; FUN_00022868 @ 0x22868 (unknown, EVAP sub-operation 4) ; FUN_00022ab0 @ 0x22AB0 (unknown, EVAP sub-operation 5) ; FUN_00022580 @ 0x22580 (unknown, EVAP sub-operation 6) ; FUN_000259a8 @ 0x259A8 (unknown, EVAP sub-operation 7) ; setSR @ 0x3934 (restore status register / restore interrupts)
Call getSR (save and disable interrupts) ; Save return value (SR) on stack ; Set r4 = 16 (operation code or timeout) ; Call FUN_0004a46c ; Save result on stack ; Call FUN_0002264a ; Call FUN_000226f6
; Call FUN_00022868 ; Call FUN_00022ab0 ; Call FUN_00022580 ; Call FUN_000259a8 ; Restore saved SR from stack into r4 ; Call setSR (restore interrupts) ; Return
**Draft C:**
```c
void evapRelated(void) {
  u32 sr = getSR();  // Disable interrupts
  // Perform EVAP operations in sequence
  evap_operation_1(16);  // FUN_0004a46c
  u32 result = evap_operation_1_result();
  evap_operation_2();    // FUN_0002264a
  evap_operation_3();    // FUN_000226f6
  evap_operation_4();    // FUN_00022868
  evap_operation_5();    // FUN_00022ab0
  evap_operation_6();    // FUN_00022580
  evap_operation_7();    // FUN_000259a8
  setSR(sr);  // Restore interrupts
}
```
**Status:** low ; Function is a coordinator/dispatcher; sub-function purposes are unknown ; Interrupt management (getSR/setSR) typical for automotive actuator sequences ; Parameter 16 (r4) passed to first operation; purpose unclear (timeout? event code?) ; EVAP purpose confirmed by function name; sub-operation details require deeper RE
