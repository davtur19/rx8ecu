# setSR_PARAM @ 0x2054

_source: AI (Haiku) draft, unverified_

**Purpose:** Conditionally update Status Register if current priority level is less than threshold.

**Inputs:**
- r4: address to store current SR value
- r5: new SR value (or threshold)

**Outputs / side effects:**
- SR: may be updated with r5
- Memory at r4: current SR value stored if condition met

**Calls:** none

**Behavior:**
1. Read SR into r0 via `stc sr,r0`
2. AND r0 with 0xF0 (extract interrupt priority bits)
3. Compare r0 with r5 (unsigned: cmp/hs)
4. If current priority >= r5, skip update; jump to exit
5. Store r0 at address r4
6. Move r0 into r5 (copy)
7. Load r5 into SR via `ldc r5,sr`

**Draft C:**
```c
void setSR_PARAM(uint32_t* sr_store, int new_sr) {
  int current_priority = getSR_raw() & 0xF0;
  if (current_priority >= new_sr) {
    return;  // current level already high enough, don't update
  }
  *sr_store = current_priority;
  ldc(new_sr);
}
```

**Confidence:** med - purpose is conditional SR update but exact semantics of comparison unclear (is it comparing priority levels or raw SR values?).
