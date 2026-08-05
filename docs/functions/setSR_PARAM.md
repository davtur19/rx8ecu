# setSR_PARAM @ 0x2054

**Purpose:** Conditionally update Status Register if current priority level is less than threshold.
In: r4: address to store current SR value ; r5: new SR value (or threshold)  Out: SR: may be updated with r5 ; Memory at r4: current SR value stored if condition met  Behavior: Read SR into r0 via `stc sr,r0` ; AND r0 with 0xF0 (extract interrupt priority bits) ; Compare r0 with r5 (unsigned: cmp/hs) ; If current priority >= r5, skip update; jump to exit ; Store r0 at address r4 ; Move r0 into r5 (copy) ; Load r5 into SR via `ldc r5,sr`
Note: if (SR_prio & 0xF0) < r5: store SR to [r4], load r5 into SR (ldc r5,sr).
**Status:** med - purpose is conditional SR update but exact semantics of comparison unclear (is it comparing priority levels or raw SR values?).
