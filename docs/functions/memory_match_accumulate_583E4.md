# memory_match_accumulate_583E4 @ 0x583E4

_source: AI (Haiku) draft, unverified_

**Purpose:** Scan memory/data structure array (36 entries of 6 bytes each) and sum fields matching filter criteria. Returns masked result.

**Inputs:**
- r4: mask value (u8, for AND-ing result)
- r5: filter value (u8, compared against structure offset +3)
- r6: accumulator start (u8, usually 0)

**Outputs / side effects:**
- r0: accumulated sum (masked by r4)
- Reads 36 entries from structured memory region @ 0x0005DEBE
- Returns AND(sum, r4)

**Calls:**
- None (all reads are direct memory access)

**Behavior:**
1. Save r14, r13, r12, r9, r8 to stack
2. Initialize:
   - r7 = 0x0005DEBE (data array base)
   - r14 = r7 (structure pointer, incremented by 6)
   - r13 = 0 (entry counter)
   - r12 = 0 (accumulator)
   - r6 = r6 (copy of mask)
3. Load reference data:
   - r3 = word @ 0xD1C8 (filter constant?)
   - r8 = address 0xFFFFCFFE (comparison pointer)
   - r9 = word @ (filter address) (filter data?)
4. For each of 36 entries (r13 = 0 to 35):
   a. Load word from structure @ r7 (offset 0)
   b. Load word from mirror @ r8 (redundancy check? offset 0)
   c. Compare: if words equal, continue; else skip to next
   d. Load byte @ r6+3, compare to r5 (filter byte)
   e. If filter fails, skip entry
   f. Load u16 @ r14+4, test bits with r9 (bitmask check)
   g. If bits set, load byte @ r7+2, add to r12 (accumulate)
   h. Increment counter r13, advance pointers (+6 each)
5. Return AND(r12, r4)

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

**Confidence:** med
- Loop structure over 36 fixed entries is clear
- Accumulation and masking semantics clear
- Reference data and filter comparisons are definite
- Bit test logic inferred from bitmask operations

**Uncertainties:**
- What is the exact structure layout? (36 entries of 6 bytes strongly suggests this, but offsets +3, +4, +6 are partly speculative)
- What does the redundancy check (comparing against 0xFFFFCFFE) actually verify?
- What is the semantic meaning of the bitmask filter @ 0xFFFFCFFE?
- Is r4 (mask) a field selector or a result bit mask?
- Are there multiple array bases or only 0x0005DEBE?
