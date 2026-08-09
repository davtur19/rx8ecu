# setSR_PARAM @ 0x2054

**Purpose:** Conditionally update the Status Register if the current priority level is less than the threshold.
In: r4: address to store the current SR value ; r5: new SR value (or threshold)  Out: SR: may be updated with r5 ; Memory at r4: current SR value stored if the condition is met  Behavior: Read SR into r0 with `stc sr,r0` ; AND r0 with 0xF0 (extract interrupt priority bits) ; Compare r0 with r5 (unsigned: cmp/hs) ; If current priority >= r5, skip update; jump to exit ; Store r0 at address r4 ; Move r0 into r5 (copy) ; Load r5 into SR with `ldc r5,sr`
Note: if (SR_prio & 0xF0) < r5: store SR to [r4], load r5 into SR (ldc r5,sr).
**Status:** med - purpose is conditional SR update but the exact semantics of the comparison are unclear (does it compare priority levels or raw SR values?).
