# memory_match_accumulate_583E4 @ 0x583E4
**Purpose:** Scan a memory/data structure array of 36 entries (6 bytes each). Sum the fields that match the filter criteria. Return the masked result.
**Inputs:** r4: mask value (u8, for AND-ing result) ; r5: filter value (u8, compared against structure offset +3) ; r6: accumulator start (u8, usually 0)
**Out:** r0: accumulated sum (masked by r4) ; Reads 36 entries from structured memory region @ 0x0005DEBE ; Returns AND(sum, r4)
**Calls:** None (all reads are direct memory access)
Save r14, r13, r12, r9, r8 to stack ; Initialize: ; r7 = 0x0005DEBE (data array base) ; r14 = r7 (structure pointer, incremented by 6) ; r13 = 0 (entry counter) ; r12 = 0 (accumulator) ; r6 = r6 (copy
of mask) ; Load reference data: ; r3 = word @ 0xD1C8 (filter constant?) ; r8 = address 0xFFFFCFFE (comparison pointer) ; r9 = word @ (filter address) (filter data?) ; For each of 36 entries (r13 = 0
to 35): ; a. Load word from structure @ r7 (offset 0) ; b. Load word from mirror @ r8 (redundancy check? offset 0) ; c. Compare: if words equal, continue; else skip to next ; d. Load byte @ r6+3,
compare to r5 (filter byte) ; e. If filter fails, skip entry ; f. Load u16 @ r14+4, test bits with r9 (bitmask check) ; g. If bits set, load byte @ r7+2, add to r12 (accumulate) ; h. Increment counter
r13, advance pointers (+6 each) ; Return AND(r12, r4)
**Draft C:**
```c
typedef struct {
  u16 signature;    // +0: compared to reference @ 0xD1C8
  u8  reserved1;    // +1
  u8  filter;       // +3: compared to input filter
  u16 flags;        // +4: tested against bitmask @ 0xFFFFCFFE
  u8  value;        // +6: accumulated into sum
} StructEntry;
u8 memory_match_accumulate_583E4(u8 mask, u8 filter_val) {
  const StructEntry *array = (StructEntry *)0x0005DEBE;
  const u16 *ref_sig = (u16 *)0xD1C8;
  const u16 *bitmask = (u16 *)0xFFFFCFFE;
  u8 sum = 0;
  for (int i = 0; i < 36; i++) {
    // Redundancy check (mirrored data?)
    if (array[i].signature != *ref_sig) {
      continue;  // Skip invalid entry
    }
    // Filter check
    if (array[i].filter != filter_val) {
      continue;  // Skip non-matching filter
    }
    // Bit test against mask
    if ((array[i].flags & *bitmask) == 0) {
      continue;  // Skip if bits not set
    }
    // Accumulate value
    sum += array[i].value;
  }
  return sum & mask;
}
```
**Status:** med — 36-entry loop, accumulation and masking clear; reference/filter comparisons definite; bit-test logic inferred.
**Uncertainties:** Exact layout (6 B/entry suggests offsets +3/+4/+6, partly speculative)? What the 0xFFFFCFFE redundancy check verifies? Bitmask semantics? r4 = field selector or result mask? Other array bases besides 0x0005DEBE?
