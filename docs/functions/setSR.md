# setSR @ 0x3934
**Purpose:** Conditionally set the Status Register (SR) based on system state. It may invoke a privileged mode handler.
**Inputs:** r4: new SR value to load
**Out:** SR: may be updated with r4 ; Possible call to 0x3DB0 if certain conditions are met
**Calls:** 0x3DB0 (FUN_00003db0) - invoked if r4 != 0 AND some memory condition is false
Test r4 (if zero, jump to return at 0x3948) ; Load pointer 0xFFFF7638 into r5 ; Load the word at offset +24 from r5 into r6 ; Load the byte at offset +1 from r6 into r0 ; Compare r0 with 1 ; If equal, jump to
return at 0x3948 ; Otherwise, load address 0x3DB0 and jump (jmp @r6) with r4 loaded into SR in the delay slot ; Return with rts and ldc r4,sr in the delay slot
**Draft C:**
```c
void setSR(int sr_value) {
  if (sr_value == 0) {
    ldc(sr_value);
    return;
  }
  void* ptr = (void*)0xFFFF7638;
  void* offset_addr = *(void**)((uintptr_t)ptr + 24);
  int check = *(uint8_t*)((uintptr_t)offset_addr + 1);
  if (check == 1) {
    ldc(sr_value);
  } else {
    setStatusRegisterPrivileged(sr_value);  // at 0x3DB0
  }
}
```
**Status:** low - the memory structure layout is unknown; the purpose of the branch is unclear.
