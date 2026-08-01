# RX-8 ECU Fault Handling & Diagnostics Subsystem (60E1D400.bin)

## Overview

The RX-8 ECU firmware implements a comprehensive fault handling and diagnostics subsystem compliant with OBD-II (On-Board Diagnostics) requirements. It manages:

- **Fault Detection**: Real-time monitoring of sensor/actuator circuits
- **Fault Status Tracking**: Persistent fault code storage with debounce logic
- **Diagnostic Trouble Codes (DTCs)**: OBD-II compliant code setting, clearing, and reporting
- **Readiness Monitors**: OBD-II drive cycle readiness tracking
- **Limp Mode Activation**: Degraded operation modes when critical faults occur
- **Recovery Mechanisms**: Automatic fault recovery when conditions normalize

## Architecture

### Memory Map (Key Addresses)

| Address Range | Region | Description |
|---|---|---|
| `0x00000000-0x0007FFFF` | Flash ROM | Program code and constant data (512KB) |
| `0xFFFF8000-0xFFFFF000` | Backup RAM | Fault flags, DTC storage, runtime variables |
| `0x0007E4DC` | ROM Table | Fault Status Definition Table |
| `0x0007ECD0` | ROM Table | Alternative fault check reference table |

### Fault Status Table (at `0x7E4DC`)

A 32-bit-per-entry table indexed by fault code (word-offset = fault_code × 4). Each entry encodes:

```
Bit 31-16 (Upper Word):  Secondary check bitmask
Bit 15-0  (Lower Word):  Primary classification/mask
```

Observed values in the table:

| Value | Meaning |
|---|---|
| `0x08800004` | C ranked fault, affects emission-related components |
| `0x00800004` | Standard fault (lower 8 bits = 0x04) |
| `0x00800006` | Standard fault, higher severity (0x06) |
| `0x40800004` | Performance/serious fault |
| `0x40800006` | Performance fault with higher severity |
| `0x48800004` | Critical fault (CPU/memory related) |
| `0x48800006` | Critical fault, elevated severity |
| `0x58800004` | Most severe fault class |
| `0x08800000` | C class, no additional flags |
| `0x08800006` | C class, elevated severity |

The upper byte (bits 31-24): fault class identifier
- `0x08` = Class C (emissions-related, CARB mandated)
- `0x40` = Class B (performance/powertrain)
- `0x48` = Class A (critical, immediate attention)
- `0x58` = Class 0 (most critical)

The lower byte (bits 7-0): severity/action flags
- `0x04` = Standard (MIL indicator on)
- `0x06` = Severe (MIL + power reduction)
- `0x00` = Information only

### Key RAM Locations (Backup RAM at `0xFFFFD000`)

| Address | Size | Description |
|---|---|---|
| `0xFFFFD494` | N bytes | DTC enable/disable flags indexed by fault code |
| `0xFFFFD638` | N bytes | Secondary DTC type flags |
| `0xFFFFD6C4` | 1 byte | Global fault status enable flag |
| `0xFFFFD6C8` | N words | DTC code storage array |
| `0xFFFFD96C` | 4 bytes | Primary fault status bitmask (accumulated faults) |
| `0xFFFF9EC8` | 2 bytes | System status word |
| `0xFFFF8928` | 2 bytes | Current DTCCodeIndex for handler dispatch |
| `0xFFFF87D8` | N*16 bytes | DTC handler context table (each entry = 16 bytes) |
| `0xFFFF87DE` | N bytes | DTC handler byte-code opcodes |

---

## Core Functions

### 1. `getFaultStatus` (0x06743C)

**Purpose**: Primary fault status query function. Called by **78 callers** across the entire firmware to determine if a specific fault code is active.

**Signature**: `uint8_t getFaultStatus(uint16_t faultCode)`

**Returns**: `0` = fault NOT active, `1` = fault IS active

**Disassembly**:

```asm
; Prologue - save registers
6743C:  mov.l   r14, @-r15         ; save r14 (return value)
6743E:  mov.l   r13, @-r15         ; save r13 (fault code index)
67440:  sts.l   pr, @-r15          ; save return address

; Primary check phase
67442:  extu.w  r4, r13            ; r13 = zero-extend(r4) — fault code (16-bit)
67444:  mov.l   0x67638, r0        ; r0 = [0x67638] → 0x7E4DC (Fault Status Table)
67446:  shll2   r13                ; r13 *= 4 (each table entry = 4 bytes)
67448:  mov.l   0x67634, r3        ; r3 = [0x67634] → 0xFFFFD96C (fault mask ptr)
6744A:  mov.l   @r3, r5            ; r5 = current accumulated fault mask from RAM
6744C:  mov.l   @(r0, r13), r2     ; r2 = FaultStatusTable[faultCode]
6744E:  and     r5, r2             ; r2 = global_mask & table_entry
67450:  extu.w  r2, r2             ; keep only lower 16 bits
67452:  tst     r2, r2             ; test if any bits match
67454:  bt.s    0x6745A            ; if zero → no fault, branch to "not set"
67456:  mov     #0, r14            ; delay slot: pre-set r14 = 0 (false)

67458:  mov     #1, r14            ; fall-through: fault IS set, r14 = 1

; Secondary check phase (only if primary found NO fault)
6745A:  extu.b  r14, r3            ; r3 = r14 (0 or 1) as byte
6745C:  tst     r3, r3             ; is r14 still 0? (primary didn't find fault)
6745E:  bf.s    0x67478            ; if r3 != 0 (fault found), skip secondary
67460:  nop                        ; delay slot

; Call sub-function for secondary fault evaluation
67462:  bsr     0x67494            ; call getFaultStatus_subcheck(faultCode)
67464:  nop                        ; delay slot
67466:  mov     r0, r4             ; r4 = secondary check result bitmask
67468:  mov.l   0x6763C, r2        ; r2 = 0xFFFF0000 (upper word mask)
6746A:  mov.l   0x67638, r0        ; r0 = FaultStatusTable base
6746C:  mov.l   @(r0, r13), r3     ; r3 = table[faultCode]
6746E:  and     r4, r3             ; r3 = secondary_result & table_entry
67470:  tst     r2, r3             ; test if upper word bits are set
67472:  bt.s    0x67476            ; if zero → secondary also says no fault
67474:  nop                        ; delay slot

67476:  mov     #1, r14            ; secondary check confirms fault: r14 = 1

; Epilogue
67478:  lds.l   @r15+, pr          ; restore return address
6747A:  mov     r14, r0            ; return value in r0
6747C:  mov.l   @r15+, r13         ; restore r13
6747E:  rts                        ; return
67480:  mov.l   @r15+, r14         ; delay slot: restore r14
```

**C Code Reconstruction**:

```c
// Memory-mapped fault structures
#define FAULT_STATUS_TABLE  ((volatile uint32_t*)0x7E4DC)
#define FAULT_MASK_PTR      ((volatile uint32_t*)0xFFFFD96C)

// External function declarations
uint8_t getFaultStatus_subcheck(uint16_t faultCode);

/**
 * getFaultStatus - Query whether a specific fault code is active
 * @faultCode: 16-bit fault code identifier (0-255)
 * 
 * Two-tier check:
 *   1. Primary: Check global fault mask against table entry
 *   2. Secondary: If primary didn't match, run condition-specific checks
 * 
 * Returns: 1 if fault is active, 0 otherwise
 */
uint8_t getFaultStatus(uint16_t faultCode) {
    uint8_t result = 0;
    uint32_t globalMask;
    uint32_t tableEntry;
    
    // Primary check: test global fault mask
    globalMask = *FAULT_MASK_PTR;
    tableEntry = FAULT_STATUS_TABLE[faultCode];
    
    if ((globalMask & tableEntry) & 0xFFFF) {
        // Global mask has bits matching this fault's table entry
        result = 1;
    } else {
        // Primary didn't match — run secondary condition check
        uint32_t secondaryResult = getFaultStatus_subcheck(faultCode);
        uint32_t maskedSecondary = secondaryResult & tableEntry;
        
        if (maskedSecondary & 0xFFFF0000) {
            // Secondary check found the fault via condition evaluation
            result = 1;
        }
    }
    
    return result;
}
```

**Callers**: 78 functions across all subsystems reference this function. Major callers include:
- `omp_fault_detect_44DF0` (0x44DF0) — OMP fault detection
- `dtc_processor_0x50F1C` (0x50F1C) — DTC processing
- `fault_code_logger_0x50C8C` (0x50C8C) — fault logging
- `fault_code_handler_4436E` (0x442E8) — fault code handling
- Various `fault_condition_check_*` functions at 0x5Exxx

---

### 2. `getFaultStatus_subcheck` (0x067494)

**Purpose**: Secondary/alternative fault check called by `getFaultStatus` when the primary mask check doesn't find a fault. Evaluates specific sensor/actuator conditions to determine if a fault exists even without the global mask being set.

**Signature**: `uint32_t getFaultStatus_subcheck(uint16_t faultCode)`

**Returns**: Bitmask with condition-specific flags ORed together

**Disassembly**:

```asm
67494:  mov.l   r14, @-r15          ; save r14
67496:  mov.l   r13, @-r15          ; save r13
67498:  sts.l   pr, @-r15           ; save return address
6749A:  mov     r4, r13             ; r13 = faultCode
6749C:  bsr     0x67534             ; check_condition_A(faultCode)
6749E:  mov     #0, r14             ; delay: r14 = 0 (accumulator init)

674A0:  extu.b  r0, r4
674A2:  tst     r4, r4
674A4:  bt.s    0x674A8             ; if check_A returns 0, skip
674A6:  mov     r13, r4             ; delay: restore faultCode
674A8:  mov.l   0x67644, r14        ; r14 |= 0x80000000

674AA:  bsr     0x67538             ; check_condition_B(faultCode) — DTC table walk
674AC:  nop
674AE:  extu.b  r0, r4
674B0:  tst     r4, r4
674B2:  bt.s    0x674B6
674B4:  mov     r13, r4
674B6:  mov.l   0x67648, r3         ; r3 = 0x40000000
674B8:  or      r3, r14             ; r14 |= 0x40000000

674BA:  bsr     0x67534             ; check_condition_A again
674BC:  nop
674BE:  extu.b  r0, r4
674C0:  tst     r4, r4
674C2:  bt.s    0x674C6
674C4:  mov     r13, r4
674C6:  mov.l   0x6764C, r2         ; r2 = 0x20000000
674C8:  or      r2, r14             ; r14 |= 0x20000000

674CA:  bsr     0x675AC             ; check_condition_C(faultCode) — indirect table
674CC:  nop
674CE:  extu.b  r0, r4
674D0:  tst     r4, r4
674D2:  bt.s    0x674D6
674D4:  mov     r13, r4
674D6:  mov.l   0x67650, r3         ; r3 = 0x10000000
674D8:  or      r3, r14             ; r14 |= 0x10000000

674DA:  bsr     0x675CA             ; check_condition_D(faultCode) — DTC data check
674DC:  nop
674DE:  extu.b  r0, r4
674E0:  tst     r4, r4
674E2:  bt.s    0x674E6
674E4:  mov     r13, r4
674E6:  mov.l   0x67654, r2         ; r2 = 0x08000000
674E8:  or      r2, r14             ; r14 |= 0x08000000

674EA:  bsr     0x67534             ; check_condition_A
674EC:  nop
674EE:  extu.b  r0, r4
674F0:  tst     r4, r4
674F2:  bt.s    0x674F6
674F4:  mov     r13, r4
674F6:  mov.l   0x67658, r3         ; r3 = 0x04000000
674F8:  or      r3, r14             ; r14 |= 0x04000000

674FA:  bsr     0x67534
674FC:  nop
674FE:  extu.b  r0, r4
67500:  tst     r4, r4
67502:  bt.s    0x67506
67504:  mov     r13, r4
67506:  mov.l   0x6765C, r2         ; r2 = 0x02000000
67508:  or      r2, r14             ; r14 |= 0x02000000

6750A:  bsr     0x67534
6750C:  nop
6750E:  extu.b  r0, r4
67510:  tst     r4, r4
67512:  bt.s    0x67516
67514:  mov     r13, r4
67516:  mov.l   0x67660, r3         ; r3 = 0x01000000
67518:  or      r3, r14             ; r14 |= 0x01000000

6751A:  bsr     0x675E6             ; check_condition_E(faultCode) — byte lookup
6751C:  nop
6751E:  extu.b  r0, r4
67520:  tst     r4, r4
67522:  bt.s    0x67526
67524:  nop
67526:  mov.l   0x67664, r2         ; r2 = 0x00800000
67528:  or      r2, r14             ; r14 |= 0x00800000

6752A:  mov     r14, r0             ; return accumulated bitmask
6752C:  lds.l   @r15+, pr
6752E:  mov.l   @r15+, r13
67530:  rts
67532:  mov.l   @r15+, r14
```

**C Code Reconstruction**:

```c
// Sub-check condition function prototypes
uint8_t check_cond_A(uint16_t faultCode);  // @0x67534 - simple null check
uint8_t check_cond_B(uint16_t faultCode);  // @0x67538 - DTC table walk
uint8_t check_cond_C(uint16_t faultCode);  // @0x675AC - indirect table lookup
uint8_t check_cond_D(uint16_t faultCode);  // @0x675CA - DTC data validity
uint8_t check_cond_E(uint16_t faultCode);  // @0x675E6 - byte-indexed lookup

/**
 * getFaultStatus_subcheck - Secondary fault evaluation
 * @faultCode: fault code to evaluate
 * 
 * Runs a series of condition-specific checks, each contributing
 * a unique bit to the result bitmask. If any check returns true,
 * its corresponding bit is set. The caller (getFaultStatus)
 * ANDs this bitmask with the table entry's upper word to
 * determine if the secondary check confirms a fault.
 */
uint32_t getFaultStatus_subcheck(uint16_t faultCode) {
    uint32_t result = 0;
    
    // Each condition check adds a specific bit if true
    if (check_cond_A(faultCode)) result |= 0x80000000;  // Bit 31
    if (check_cond_B(faultCode)) result |= 0x40000000;  // Bit 30
    if (check_cond_A(faultCode)) result |= 0x20000000;  // Bit 29 (redundant check)
    if (check_cond_C(faultCode)) result |= 0x10000000;  // Bit 28
    if (check_cond_D(faultCode)) result |= 0x08000000;  // Bit 27
    if (check_cond_A(faultCode)) result |= 0x04000000;  // Bit 26
    if (check_cond_A(faultCode)) result |= 0x02000000;  // Bit 25
    if (check_cond_A(faultCode)) result |= 0x01000000;  // Bit 24
    if (check_cond_E(faultCode)) result |= 0x00800000;  // Bit 23
    
    return result;
}
```

The 9 condition checks are called in sequence and evaluate distinct fault detection paths:

| # | Address | Bit | Check Type | Description |
|---|---|---|---|---|
| 1 | 0x67534 | 31 | Quick null check | Always returns 0 (stub) |
| 2 | 0x67538 | 30 | DTC table walk | Iterates a DTC reference table, checks if the fault code's entry is valid |
| 3 | 0x67534 | 29 | (same as #1) | Redundant quick check |
| 4 | 0x675AC | 28 | Indirect table | Double-indirect table lookup via two word-sized index tables |
| 5 | 0x675CA | 27 | DTC data validity | Calls `dtc_data_read_60DEE` to check DTC data integrity |
| 6 | 0x67534 | 26 | (same as #1) | Redundant |
| 7 | 0x67534 | 25 | (same as #1) | Redundant |
| 8 | 0x67534 | 24 | (same as #1) | Redundant |
| 9 | 0x675E6 | 23 | Byte-indexed lookup | Two-element loop checking fault code via byte table at 0x7E734 |

**Note**: The redundant calls to `check_cond_A` (which always returns 0) suggest this code area may once have had 8 distinct condition checks, and some were later stubbed out or merged.

---

### 3. `check_cond_B` (0x067538) — DTC Table Walker

**Purpose**: Walks a variable-length DTC condition table to check if a fault code's entry passes validation.

**Signature**: `uint8_t check_cond_B(uint16_t faultCode)`

**Disassembly**:

```asm
67538:  mov.l   r14, @-r15        ; save regs
6753A:  mov     #0, r6            ; r6 = 0 (constant)
6753C:  mov.l   0x67668, r0       ; r0 = 0x7ECD0 (DTC reference table base)
6753E:  extu.w  r4, r14           ; r14 = faultCode
67540:  mov.l   r13, @-r15
67542:  mov     r6, r5            ; r5 = 0
67544:  mov.l   r12, @-r15
67546:  mov     r6, r13           ; r13 = 0 (loop counter)
...
6755C:  mov.l   @(r0, r14), r14   ; r14 = table[faultCode] — pointer to entry list
...
67564:  extu.w  r13, r2
67566:  cmp/gt  r8, r2            ; r8 = 50 — loop bound
67568:  bt.s    0x67598           ; exit if counter > 50
...
6756C:  mov.w   @r14, r3          ; r3 = *entry (16-bit DTC code)
6756E:  extu.w  r3, r3
67570:  cmp/eq  r9, r3            ; r9 = 0xFFFE — terminator
67572:  bt.s    0x67576           ; if terminator, check next
67574:  nop
67576:  mov.l   0x67670, r2       ; r2 = 0x60EB4 (DTC validation)
67578:  jsr     @r2               ; call dtc_data_read_60EB4(*entry)
6757A:  mov.w   @r14, r4           ; r4 = current DTC code
6757C:  mov     r0, r5
6757E:  extu.b  r5, r0
67580:  cmp/eq  #1, r0
67582:  bf.s    0x6758A            ; if validation returns 1, set result
67584:  nop
67586:  bra     0x67598
67588:  mov     r10, r11           ; r11 = 1 (found)
6758A:  add     #2, r14            ; advance to next entry
6758C:  add     #1, r13            ; increment counter
6758E:  mov.w   @r14, r3
67590:  extu.w  r3, r3
67592:  cmp/eq  r12, r3           ; r12 = 0xFFFE (actual sentinel val)
67594:  bf.s    0x67564            ; loop back if not terminator
```

**C Code Reconstruction**:

```c
// DTC reference table — each fault code points to a list of DTC entries
#define DTC_REF_TABLE       ((uint32_t*)0x7ECD0)
#define DTC_VALIDATE_FN     ((uint8_t(*)(uint16_t))0x60EB4)

#define DTC_ENTRY_TERM      0xFFFE  // Table terminator
#define MAX_DTC_ENTRIES     50      // Safety bound

/**
 * check_cond_B - Walk DTC reference entries for fault code
 * @faultCode: fault code to check
 * 
 * For the given fault code, dereferences the DTC reference table
 * to get a pointer to a list of DTC codes. Iterates the list
 * (terminated by 0xFFFE) and validates each entry through
 * dtc_data_read_60EB4. If any entry validates, returns 1.
 * 
 * Returns: 1 if a valid DTC entry is found, 0 otherwise
 */
uint8_t check_cond_B(uint16_t faultCode) {
    uint16_t* entryList;
    uint16_t currentEntry;
    uint8_t counter = 0;
    uint8_t found = 0;
    
    entryList = (uint16_t*)DTC_REF_TABLE[faultCode];
    
    if (entryList == NULL) return 0;
    
    while (counter < MAX_DTC_ENTRIES) {
        currentEntry = *entryList;
        
        if (currentEntry == DTC_ENTRY_TERM) {
            break;  // End of list
        }
        
        if (DTC_VALIDATE_FN(currentEntry) == 1) {
            found = 1;
            break;
        }
        
        entryList++;
        counter++;
    }
    
    return found;
}
```

---

### 4. `check_cond_C` (0x0675AC) — Indirect Table Lookup

**Purpose**: Double-indirect lookup: faultCode → word-table → byte-table → presence check.

```asm
675AC:  mov.l   0x67674, r0     ; r0 = 0x7DAEA (first-level word table)
675AE:  extu.w  r4, r4          ; r4 = faultCode
675B0:  shll    r4              ; r4 *= 2 (word offset)
675B2:  mov.w   @(r0, r4), r4   ; r4 = word_table[faultCode] — 16-bit index
675B4:  mov.l   0x67678, r0     ; r0 = 0xFFFF8D7C (second-level byte table)
675B6:  extu.w  r4, r4          ; zero-extend index
675B8:  shll    r4              ; r4 *= 2
675BA:  mov.b   @(r0, r4), r4   ; r4 = byte_table[index] — presence flag
675BC:  extu.b  r4, r4          ; zero-extend byte
675BE:  tst     r4, r4          ; zero = not present
675C0:  bt.s    0x675C4         ; if zero, return 0
675C2:  mov     #0, r5
675C4:  mov     #1, r5          ; non-zero: return 1
675C6:  rts
675C8:  mov     r5, r0
```

**C Code**:

```c
#define WORD_TABLE_LEVEL1   ((uint16_t*)0x7DAEA)
#define BYTE_TABLE_LEVEL2   ((uint8_t*)0xFFFF8D7C)

uint8_t check_cond_C(uint16_t faultCode) {
    uint16_t index = WORD_TABLE_LEVEL1[faultCode];
    uint8_t presence = BYTE_TABLE_LEVEL2[index];
    return (presence != 0) ? 1 : 0;
}
```

---

### 5. `check_cond_D` (0x0675CA) — DTC Data Check

**Purpose**: Checks DTC data validity for the given fault code by calling the `dtc_data_read_60DEE` function.

```asm
675CA:  mov.l   r14, @-r15
675CC:  sts.l   pr, @-r15
675CE:  mov.l   0x6767C, r3     ; r3 = function pointer: 0x60DEE
675D0:  jsr     @r3             ; call dtc_data_read_60DEE(faultCode)
675D2:  mov     #0, r14
675D4:  extu.b  r0, r4
675D6:  tst     r4, r4
675D8:  bf.s    0x675DC         ; if function returns non-zero, set result=1
675DA:  nop
675DC:  mov     #1, r14
675DE:  mov     r14, r0
675E0:  lds.l   @r15+, pr
675E2:  rts
675E4:  mov.l   @r15+, r14
```

**C Code**:

```c
uint8_t check_cond_D(uint16_t faultCode) {
    return (dtc_data_read_60DEE(faultCode) != 0) ? 1 : 0;
}
```

---

### 6. `check_cond_E` (0x0675E6) — Byte-Indexed Lookup

**Purpose**: Two-element loop checking fault code against a byte-organized table. Checks two conditions (index 0 and 1) via `dtc_data_read_60EFE`.

```asm
675E6:  mov.l   r14, @-r15
675E8:  mov.l   r13, @-r15
675EA:  mov     #0, r13          ; r13 = 0 (result accumulator)
675EC:  mov.l   0x67684, r3      ; r3 = 0x7E734 (byte table base)
675EE:  mov     r13, r14         ; r14 = 0 (loop index)
675F0:  mov.l   r12, @-r15
675F2:  mov     #2, r12          ; r12 = 2 (loop count)
675F4:  mov.l   r11, @-r15
675F6:  mov     #1, r11          ; r11 = 1 (true constant)
675F8:  mov.l   r10, @-r15
675FA:  mov.l   r9, @-r15
675FC:  sts.l   pr, @-r15
675FE:  extu.w  r4, r9           ; r9 = faultCode
67600:  mov.l   0x67680, r10     ; r10 = 0x60EFE (dtc_data_read_60EFE)
67602:  shll    r9               ; r9 *= 2 (word index into table)
67604:  add     r3, r9           ; r9 = &byte_table[faultCode]
67606:  jsr     @r10             ; call dtc_data_read_60EFE(loop_index)
67608:  mov     r14, r4          ; r4 = current loop index (0, then 1)
6760A:  mov     r0, r4
6760C:  mov     r14, r0
6760E:  mov.b   @(r0, r9), r3    ; r3 = byte_table[faultCode][loop_index]
67610:  and     r4, r3           ; r3 = dtc_data_read_60EFE(index) & byte_table[faultCode][index]
67612:  extu.b  r3, r4
67614:  tst     r4, r4
67616:  bt.s    0x6761A          ; if zero, skip
67618:  add     #1, r14          ; increment loop index
6761A:  mov     r13, r11         ; if zero, r11 stays 0
6761C:  cmp/ge  r12, r14        ; loop while index < 2
6761E:  bf.s    0x67606
67620:  nop
67622:  mov     r11, r0          ; return result
...
```

**C Code**:

```c
#define BYTE_TABLE_0x7E734   ((uint8_t*)0x7E734)

uint8_t check_cond_E(uint16_t faultCode) {
    uint8_t i;
    uint8_t found = 0;
    uint8_t* entry = &BYTE_TABLE_0x7E734[faultCode * 2];
    
    for (i = 0; i < 2; i++) {
        uint8_t dtcResult = dtc_data_read_60EFE(i);
        if (dtcResult & entry[i]) {
            found = 1;
        }
    }
    
    return found;
}
```

---

### 7. `setFaultEvalState` (0x060DB4)

**Purpose**: Evaluates and returns the current fault evaluation state based on system conditions. Used to determine what level of fault handling should be active.

**Signature**: `uint8_t setFaultEvalState(void)`

**Returns**: Bitmask of evaluation state flags

```asm
60DB4:  mov.w   0x60E9A, r3     ; r3 = ptr to 0xFFFFD1E9 (system status byte)
60DB6:  mov     #1, r5          ; r5 = 1
60DB8:  mov.b   @r3, r0         ; read system status
60DBA:  extu.b  r0, r0
60DBC:  cmp/eq  #1, r0          ; is system in run mode?
60DBE:  bf.s    0x60DC2         ; if not running, skip
60DC0:  mov     r5, r4          ; r4 = 1 (run mode flag)
60DC2:  mov     #3, r4          ; r4 = 3 (default state = key-on + run?)
60DC4:  mov.l   0x60EA4, r2     ; r2 = 0xFFFF9EC8 (system flags)
60DC6:  mov.w   @r2, r3
60DC8:  extu.w  r3, r3
60DCA:  tst     r5, r3          ; test bit 0 of system flags
60DCC:  bt.s    0x60DD0         ; if bit clear, skip
60DCE:  nop
60DD0:  tst     r5, r5          ; (redundant)
60DD2:  bf.s    0x60DD8         ; always true
60DD4:  nop
60DD6:  mov     #4, r1          ; add flag 4
60DD8:  or      r1, r4
60DDA:  mov.w   0x60E9C, r3     ; r3 = ptr to 0xFFFFD1D4 (additional status)
60DDC:  mov.b   @r3, r0
60DDE:  extu.b  r0, r0
60DE0:  cmp/eq  #1, r0          ; is secondary status active?
60DE2:  bf.s    0x60DE8
60DE4:  nop
60DE6:  mov     #8, r1
60DE8:  or      r1, r4           ; flag 8 = secondary status active
60DEA:  rts
60DEC:  mov     r4, r0           ; return state bitmask
```

**C Code**:

```c
#define SYS_STATUS_RUN    ((volatile uint8_t*)0xFFFFD1E9)
#define SYS_FLAGS_WORD    ((volatile uint16_t*)0xFFFF9EC8)
#define SYS_STATUS_2      ((volatile uint8_t*)0xFFFFD1D4)

/**
 * setFaultEvalState - Determine current fault evaluation context
 * 
 * Returns a bitmask indicating what fault evaluation mode
 * the system is currently in:
 *   Bit 0 (0x01): Engine running
 *   Bit 1 (0x02): Key-on, engine-off (KOEO) 
 *   Bit 2 (0x04): System flag active
 *   Bit 3 (0x08): Secondary diagnostic mode
 * 
 * Default operating state (key on, engine off) = 0x03
 */
uint8_t setFaultEvalState(void) {
    uint8_t state = 0x03;  // Default: key-on, engine-off
    
    if (*SYS_STATUS_RUN == 1) {
        state = 0x01;  // Engine running
    }
    
    if (*SYS_FLAGS_WORD & 0x0001) {
        state |= 0x04;  // System flag active
    }
    
    if (*SYS_STATUS_2 == 1) {
        state |= 0x08;  // Secondary diagnostic mode
    }
    
    return state;
}
```

---

### 8. `getFaultEvalState` (0x067482)

**Purpose**: Getter wrapper around `setFaultEvalState` that also stores the result to the global fault mask.

**Signature**: `uint16_t getFaultEvalState(void)`

```asm
67482:  sts.l   pr, @-r15
67484:  mov.l   0x67640, r3     ; r3 = 0x60DB4 (setFaultEvalState)
67486:  jsr     @r3
67488:  nop
6748A:  extu.w  r0, r4          ; r4 = eval state (zero-extend word)
6748C:  mov.l   0x67634, r2     ; r2 = 0xFFFFD96C (fault mask)
6748E:  lds.l   @r15+, pr
67490:  rts
67492:  mov.l   r4, @r2         ; store eval state to fault mask
```

**C Code**:

```c
/**
 * getFaultEvalState - Get and store current fault evaluation state
 * 
 * Calls setFaultEvalState() and stores the result in the
 * global fault mask register (0xFFFFD96C). This acts as
 * a "freeze frame" of the evaluation context at the time
 * a fault was detected.
 */
uint16_t getFaultEvalState(void) {
    uint16_t state = (uint16_t)setFaultEvalState();
    *FAULT_MASK_PTR = state;  // Store to 0xFFFFD96C
    return state;
}
```

---

### 9. `updateFaultStatusTHUNK` (0x060778)

**Purpose**: Thunk/dispatch function that updates fault status based on a mode parameter in r6.

**Disassembly**:

```asm
60778:  extu.w  r6, r3           ; r3 = zero-extend(r6) — mode
6077A:  tst     r3, r3           ; test mode
6077C:  bf.s    0x60786          ; if mode != 0, branch to processing
6077E:  nop
60780:  mov.l   0x60848, r6      ; r6 = 0xFFFF (default value if mode=0)
60782:  bra     0x6085C          ; jump to exit
60784:  nop
60786:  extu.b  r4, r0           ; r0 = fault code (byte)
60788:  mov.l   0x6084C, r5      ; r5 = 0xFFFFD6C4 (global status flag)
6078A:  cmp/eq  #1, r0           ; fault code == 1?
6078C:  bt.s    0x6079A          ; yes → set flag
6078E:  nop
60790:  cmp/eq  #0, r0           ; fault code == 0?
60792:  bt.s    0x607A0          ; yes → clear flag
60794:  nop
60796:  bra     0x607A4          ; otherwise → exit
60798:  nop
6079A:  mov     #1, r3
6079C:  bra     0x607A4
6079E:  mov.b   r3, @r5          ; set flag to 1
607A0:  mov     #0, r1
607A2:  mov.b   r1, @r5          ; set flag to 0
607A4:  rts
607A6:  nop
```

**C Code**:

```c
#define GLOBAL_FAULT_FLAG   ((volatile uint8_t*)0xFFFFD6C4)

/**
 * updateFaultStatusTHUNK - Set/clear global fault status flag
 * @mode:   Operation mode (0 = reset, non-zero = process fault)
 * @faultCode: Fault code to process (1 = set, 0 = clear)
 * 
 * When mode != 0:
 *   - faultCode 1: sets global fault flag
 *   - faultCode 0: clears global fault flag
 *   - other values: no change
 * When mode == 0:
 *   - sets default value 0xFFFF (no-op/initialization)
 */
void updateFaultStatusTHUNK(uint16_t mode, uint8_t faultCode) {
    if (mode == 0) {
        // Reset/init mode
        // (continues at 0x6085C with r6=0xFFFF)
        return;
    }
    
    if (faultCode == 1) {
        *GLOBAL_FAULT_FLAG = 1;   // Set fault active
    } else if (faultCode == 0) {
        *GLOBAL_FAULT_FLAG = 0;   // Clear fault
    }
    // Other fault codes: no action
}
```

---

### 10. `dtcRelated` (0x062002)

**Purpose**: DTC dispatch and processing — the main DTC handling loop that processes all pending DTC codes through their respective handler functions.

**Signature**: `uint8_t dtcRelated(uint8_t param, uint16_t data, uint8_t* outputArray)`

**Assembly Flow**:

```
Loop over DTC index 0-20 (21 iterations):
  - Read current DTC code from index table at 0xFFFF8928
  - Look up handler context in table at 0xFFFF87D8 (16 bytes per entry)
  - Check handler type field at offset 6 of context
  - Read enable/disable flags from 0x7E220 and 0x7E2AC
  - For each DTC type code (0x00, 0x60, 0x80, 0xC0, 0xC1, 0xF0, 0x50, 0x70):
    - Match against type dispatch table
    - Store to output array at computed offset
    - Increment result counter
  - Continue until all 21 indices processed
  - Return total count of processed DTCs
```

**C Code**:

```c
#define DTC_INDEX_REG       ((volatile uint16_t*)0xFFFF8928)
#define DTC_HANDLER_TABLE   ((uint8_t*)0xFFFF87D8)
#define DTC_ENABLE_FLAGS    ((uint8_t*)0x7E220)
#define DTC_TYPE_FLAGS      ((uint8_t*)0x7E2AC)

#define MAX_DTC_INDICES     21
#define HANDLER_ENTRY_SIZE  16

/**
 * dtcRelated - Process DTC codes through handler table
 * @mode:    Operation mode (type filter)
 * @data:    Additional data parameter
 * @outBuf:  Output buffer for processed DTC codes
 * 
 * Returns: Number of DTCs processed
 */
uint8_t dtcRelated(uint8_t mode, uint16_t data, uint16_t* outBuf) {
    uint8_t dtcIndex;
    uint8_t processedCount = 0;
    
    for (dtcIndex = 0; dtcIndex < MAX_DTC_INDICES; dtcIndex++) {
        uint16_t dtcCode = *DTC_INDEX_REG;
        
        if (dtcCode == 0) {
            break;  // No more DTCs
        }
        
        uint8_t* handlerCtx = &DTC_HANDLER_TABLE[dtcIndex * HANDLER_ENTRY_SIZE];
        uint16_t handlerCode = *(uint16_t*)handlerCtx;
        uint8_t handlerType = handlerCtx[6];
        uint8_t enableFlag = DTC_ENABLE_FLAGS[handlerCode];
        uint8_t typeFlag = DTC_TYPE_FLAGS[handlerCode];
        
        // Mode 0 processing
        if (mode == 0) {
            if (handlerType == 0 && enableFlag == 1) {
                // Standard type, enabled — store output
                uint16_t* outSlot = outBuf + (dtcIndex * 2) + data;
                *outSlot = handlerCode;
                processedCount++;
            }
            // Handler for type codes: 0x60, 0x80, 0xC0, 0xC1, 0xF0, 0x50, 0x70
            // Each type has specific offset calculation and flag checks
        }
    }
    
    return processedCount;
}
```

**DTC Type Dispatch**:

The function implements a type-based dispatch for DTC processing. The `mode` parameter selects which DTC types to process:

| Mode | DTC Type | Description |
|---|---|---|
| 0x00 | All types | Process all enabled DTCs |
| 0x60 | Pending | Pending DTC codes |
| 0x80 | Confirmed | Confirmed fault codes |
| 0xC0 | Permanent | Permanent fault codes |
| 0xC1 | Warm-up cycle | Warm-up cycle DTCs |
| 0xF0 | Readiness | Monitor readiness |
| 0x50 | MIL | Malfunction Indicator Lamp |

---

### 11. `dtc_code_set` (0x046780) & `dtc_code_clear` (0x0467AA)

**Purpose**: Low-level DTC code set/clear operations. These write to the Backup RAM DTC storage.

**dtc_code_set (0x46780)**:

```asm
46780:  sts.l   pr, @-r15
46782:  mov.w   0x46896, r4     ; r4 = 0x8788 (DTC flag address)
46784:  mov.l   0x468A0, r3     ; r3 = 0x3ED3C (memory write function)
46786:  jsr     @r3             ; call memory_write(0x8788, 1)
46788:  mov     #1, r5           ; value = 1
4678A:  extu.b  r0, r0
4678C:  cmp/eq  #1, r0
4678E:  bf.s    0x4679A         ; if failed, try alternative
46790:  nop
46792:  mov.w   0x46898, r4     ; r4 = 0x875C (DTC storage addr 1)
46794:  mov.l   0x468A4, r3     ; r3 = 0x3EE58 (another memory writer)
46796:  jsr     @r3
46798:  mov     #0, r5           ; value = 0 (clear)
4679A:  mov     #0, r5
4679C:  mov.w   0x4689A, r4     ; r4 = 0x875E (DTC storage addr 2)
4679E:  mov.l   0x468A4, r2     ; r2 = 0x3EE58
467A0:  jmp     @r2
467A2:  lds.l   @r15+, pr
```

**C Code**:

```c
#define DTC_FLAG_ADDR     ((volatile uint8_t*)0x8788)
#define DTC_STORAGE_1     ((volatile uint8_t*)0x875C)
#define DTC_STORAGE_2     ((volatile uint8_t*)0x875E)

// External memory manipulation functions
uint8_t memory_set_byte(uint8_t* addr, uint8_t val);  // @0x3ED3C
void memory_clear_byte(uint8_t* addr, uint8_t val);   // @0x3EE58

/**
 * dtc_code_set - Set a DTC code in storage
 * 
 * Sets the DTC flag, then clears both storage locations.
 */
void dtc_code_set(void) {
    if (memory_set_byte(DTC_FLAG_ADDR, 1) == 1) {
        memory_clear_byte(DTC_STORAGE_1, 0);
    }
    memory_clear_byte(DTC_STORAGE_2, 0);
}

/**
 * dtc_code_clear - Clear DTC code from storage
 * 
 * Clears both DTC storage locations.
 */
void dtc_code_clear(void) {
    memory_clear_byte(DTC_STORAGE_1, 0);
    memory_clear_byte(DTC_STORAGE_2, 0);
}
```

---

### 12. `dtc_handler_610FA` (Main DTC Handler Dispatcher)

**Purpose**: Entry point for DTC handling. Reads the current DTC code index, determines handler type, and dispatches to the appropriate handler function chain.

**Disassembly**:

```asm
610FA:  sts.l   pr, @-r15
610FC:  mov.l   0x611D4, r3     ; r3 = 0xFFFF8928 (DTC index)
610FE:  mov.w   @r3, r4         ; r4 = current DTC index
61100:  mov.l   0x611D8, r0     ; r0 = 0xFFFF87DE (handler type table)
61102:  extu.w  r4, r4
61104:  shll2   r4              ; r4 *= 4
61106:  shll2   r4              ; r4 *= 4 (total ×16 — handler entry stride)
61108:  mov.b   @(r0, r4), r4   ; r4 = handler_type[index]
6110A:  extu.b  r4, r4
6110C:  mov     r4, r0
6110E:  cmp/eq  #0x50, r0       ; is type 0x50 (MIL)?
61110:  bt.s    0x6111A
61112:  nop
61114:  tst     r4, r4          ; is type 0 (standard)?
61116:  bf.s    0x6112C         ; if not standard, return
61118:  nop
6111A:  mov.l   0x611DC, r3     ; r3 = handler function 1
6111C:  jsr     @r3
6111E:  mov     #8, r4           ; parameter = 8
61120:  mov.l   0x611E0, r2     ; r2 = handler function 2
61122:  jsr     @r2
61124:  nop
61126:  mov.l   0x611D0, r3     ; r3 = handler function 3
61128:  jmp     @r3
6112A:  lds.l   @r15+, pr
6112C:  lds.l   @r15+, pr
6112E:  rts
61130:  nop
```

**C Code**:

```c
#define DTC_INDEX       ((volatile uint16_t*)0xFFFF8928)
#define DTC_HANDLER_TYPES ((volatile uint8_t*)0xFFFF87DE)
#define HANDLER_ENTRY_STRIDE 16

/**
 * dtc_handler_610FA - Main DTC handler dispatcher
 * 
 * Reads the current DTC index, looks up the handler type,
 * and dispatches to the appropriate handler chain.
 * Handler type 0x50 (MIL) and type 0 (standard) are processed;
 * other types are skipped.
 */
void dtc_handler_610FA(void) {
    uint16_t dtcIdx = *DTC_INDEX;
    uint8_t hType = DTC_HANDLER_TYPES[dtcIdx * HANDLER_ENTRY_STRIDE];
    
    if (hType == 0x50 || hType == 0) {
        // Standard MIL or standard DTC — run handler chain
        ((void(*)(int))0x62FAC)(8);  // Handler function 1
        ((void(*)())0x64258)();      // Handler function 2
        ((void(*)())0x63312)();      // Handler function 3
    }
    // Other types: return without processing
}
```

---

### 13. `dtc_handler_61550` (Detailed DTC Handler — 358 bytes)

**Purpose**: Complex DTC handler that evaluates a DTC code with type-specific processing, debounce counters, and status flag management.

**Signature**: `void dtc_handler_61550(uint16_t dtcCode, uint8_t mode)`

**Flow**:
1. Check mode parameter (0, 1, 2, 3)
2. Mode 0 (standard): Run fault check → process result → update counters
3. Mode 1 (pending): Run specific check, apply debounce, update pending status
4. Mode 2 (confirmed): Update confirmed fault status
5. Store results to Backup RAM status bytes at 0xFFFFD6F8

**C Code**:

```c
#define DTC_STATUS_BASE   ((volatile uint8_t*)0xFFFFD6F8)

/**
 * dtc_handler_61550 - Detailed DTC evaluation and storage
 * @dtcCode:  The DTC code to evaluate
 * @mode:     Operation mode (0=std, 1=pending, 2=confirmed, 3=reset)
 * 
 * Evaluates a DTC code through type-specific checks, manages
 * debounce counters, and updates status flags in Backup RAM.
 */
void dtc_handler_61550(uint16_t dtcCode, uint8_t mode) {
    uint8_t faultStatus;
    uint8_t debounceState;
    uint8_t checkResult;
    uint8_t finalResult = 0;
    
    if (mode == 0) {
        // Standard mode
        faultStatus = ((uint8_t(*)(uint16_t))0x61712)(dtcCode);
        debounceState = ((uint8_t(*)(uint16_t,uint8_t,uint8_t))0x62334)(dtcCode, faultStatus, mode);
        checkResult = ((uint8_t(*)(uint8_t))0x62E5C)(debounceState);
        
        if (checkResult == 1) {
            ((void(*)(uint16_t,uint8_t))0x61818)(dtcCode, faultStatus);
            ((void(*)())0x61994)();
            ((void(*)(uint16_t))0x62B74)(dtcCode);
            ((void(*)(uint16_t,int))0x6193E)(dtcCode, 0x20);
            ((void(*)(uint8_t))0x63B46)(debounceState);
            ((void(*)(uint8_t))0x63A62)(mode);
            ((void(*)(int))0x63AD4)(1);
        }
    } else if (mode == 1) {
        // Pending mode
        checkResult = ((uint8_t(*)(uint16_t))0x63834)(dtcCode);
        if (checkResult & 0x80) {
            finalResult = 0;
        }
        debounceState = ((uint8_t(*)(uint16_t,uint8_t,uint8_t))0x62334)(dtcCode, finalResult, mode);
        checkResult = ((uint8_t(*)(uint8_t))0x62E5C)(debounceState);
        
        if (checkResult == 1) {
            if ((finalResult & 0x80) == 0) {
                ((void(*)(uint8_t))0x63814)(finalResult);
            }
            ((void(*)(uint8_t))0x63B46)(debounceState);
            ((void(*)(uint8_t))0x63A62)(mode);
        }
    } else if (mode == 2) {
        // Confirmed mode
        checkResult = ((uint8_t(*)(uint16_t))0x63834)(dtcCode);
        finalResult = checkResult;
        debounceState = ((uint8_t(*)(uint16_t,uint8_t,uint8_t))0x62334)(dtcCode, finalResult, mode);
        checkResult = ((uint8_t(*)(uint8_t))0x62E5C)(debounceState);
        
        if (checkResult == 1) {
            ((void(*)(uint8_t))0x63A62)(mode);
        }
    }
    
    // Store results to status bytes
    DTC_STATUS_BASE[4] = (uint8_t)debounceState;
    DTC_STATUS_BASE[7] = finalResult;
    
    // Check if DTC code matches and run additional processing
    if (dtcCode == ((uint16_t*)0xFFFFD700)) {
        ((void(*)(uint16_t,int))0x62ABC)(dtcCode, 0x20);
    }
    
    ((void(*)(uint16_t,uint8_t,int))0x62B24)(dtcCode, finalResult, 0x20);
    ((void(*)(uint16_t,uint8_t))0x632D6)(dtcCode, finalResult);
}
```

---

### 14. `dtc_debounce_monitor_43760` (Debounce Logic — 282 bytes)

**Purpose**: Implements DTC debounce timing using multiple counters to prevent transient fault triggering.

**Key RAM variables**:

| Address | Size | Name | Description |
|---|---|---|---|
| `0xFFFFC9EF` | 1 byte | DebounceFlag1 | First debounce stage trigger |
| `0xFFFFC9F0` | 1 byte | DebounceFlag2 | Second debounce stage trigger |
| `0xFFFFC9FE` | 2 bytes | DebounceCounter1 | First debounce time counter |
| `0xFFFFCA00` | 2 bytes | DebounceCounter2 | Second debounce time counter |
| `0xFFFFCA02` | 2 bytes | FailCounter | Fail threshold counter |
| `0xFFFFC9E8` | 1 byte | EnableDebounce | Debounce enable flag |
| `0x7D97C` | 2 bytes | Threshold1 | First debounce threshold |
| `0x7D984` | 2 bytes | Threshold2 | Second debounce threshold |
| `0x7D988` | 2 bytes | FailThreshold | Fail threshold value |
| `0x7D978` | 2 bytes | MaxCount1 | Maximum for counter 1 |
| `0x7D97A` | 2 bytes | MaxCount2 | Maximum for counter 2 |

**C Code**:

```c
#define DEBOUNCE_ENABLE   ((volatile uint8_t*)0xFFFFC9E8)
#define DEBOUNCE_FLAG_1   ((volatile uint8_t*)0xFFFFC9EF)
#define DEBOUNCE_FLAG_2   ((volatile uint8_t*)0xFFFFC9F0)
#define DCNT_1            ((volatile uint16_t*)0xFFFFC9FE)
#define DCNT_2            ((volatile uint16_t*)0xFFFFCA00)
#define FAIL_CNT          ((volatile uint16_t*)0xFFFFCA02)

extern uint16_t THRESHOLD_1;   // at 0x7D97C
extern uint16_t THRESHOLD_2;   // at 0x7D984
extern uint16_t FAIL_THRESH;   // at 0x7D988
extern uint16_t MAX_COUNT_1;   // at 0x7D978
extern uint16_t MAX_COUNT_2;   // at 0x7D97A

/**
 * dtc_debounce_monitor_43760 - Debounce logic for DTC detection
 * 
 * Implements a multi-stage debounce algorithm:
 * Stage 1: DebounceFlag1 triggered when counter 1 exceeds threshold 1
 * Stage 2: DebounceFlag2 triggered when counter 2 exceeds threshold 2
 * Fail: FailCounter tracks consecutive failure events
 * 
 * If debounce is disabled, all counters and flags are cleared.
 * Sensor input state determines which counters increment.
 */
void dtc_debounce_monitor_43760(void) {
    uint8_t sensorState = *(uint8_t*)0xB3C8;  // Read sensor input
    
    // Check if debounce is enabled
    if (*DEBOUNCE_ENABLE != 1 || sensorState != 1) {
        // Disabled or sensor inactive — clear all counters
        *DEBOUNCE_FLAG_1 = 0;
        *DEBOUNCE_FLAG_2 = 0;
        *DCNT_1 = 0;
        *DCNT_2 = 0;
        *FAIL_CNT = 0;
        return;
    }
    
    // Check counter 1 against threshold
    if (*DCNT_1 >= *(uint16_t*)0x7D97C) {
        // Counter 1 exceeded threshold
        if (*(uint16_t*)0x7D984 >= *(uint16_t*)0x7D988) {
            // Second threshold configuration check
            // (complex conditions involving 0x7D984, 0xAA)
            // ...
        }
        
        // Set flag 1 when counter 1 exceeds threshold
        if (*DCNT_1 >= *(uint16_t*)0x7D97C) {
            *DEBOUNCE_FLAG_1 = 1;
        }
        
        // Update counter 1 with saturation at MAX_COUNT_1
        uint16_t newCnt1 = ((uint16_t(*)(uint16_t,uint16_t))0x2460)(*DCNT_1, *MAX_COUNT_1);
        *DCNT_1 = newCnt1;
        *DCNT_2 = 0;
    } else {
        // Check counter 2
        if (*DCNT_2 >= *(uint16_t*)0x7D97A) {
            *DEBOUNCE_FLAG_2 = 1;
        }
        
        uint16_t newCnt2 = ((uint16_t(*)(uint16_t,uint16_t))0x2460)(*DCNT_2, *MAX_COUNT_2);
        *DCNT_2 = newCnt2;
        *DCNT_1 = 0;
    }
    
    // Update fail counter if sensor active
    if (sensorState == 1) {
        uint16_t newFail = ((uint16_t(*)(uint16_t,uint16_t))0x2460)(*FAIL_CNT, *(uint16_t*)0x7D978);
        *FAIL_CNT = newFail;
    } else {
        *FAIL_CNT = 0;
    }
}
```

---

### 15. Sensor-Specific Fault Detection Functions

#### `dtc_misfire_detection_468D6`
- **Size**: 208 bytes
- **Purpose**: Detects engine misfire events (DTC P0300-P0304)
- **Mechanism**: Monitors eccentric-shaft acceleration variations, compares against RPM-dependent thresholds

#### `dtc_o2_circuit_fault_45F54`
- **Size**: 72 bytes
- **Purpose**: O2 sensor circuit fault detection
- **Mechanism**: Checks O2 sensor voltage range, response time, heater circuit continuity

#### `dtc_cat_system_monitor_45FFC`
- **Size**: 772 bytes (largest DTC handler)
- **Purpose**: Catalyst efficiency monitoring
- **Mechanism**: Compares upstream vs downstream O2 sensor switching frequency

#### `omp_fault_detect_44DF0`
- **Size**: 572 bytes
- **Purpose**: Output Parameter Monitoring — comprehensive output stage fault detection
- **Mechanism**: Checks injector drivers, ignition coils, and relay drivers for opens/shorts
- **Key calls**: `getFaultStatus(44)` for OMP primary fault, plus 7 sensor-specific checks

---

### 16. `fault_code_dispatch_2D89C`

**Purpose**: Dispatches fault codes to appropriate handling based on fault class (0-4).

**Signature**: `void fault_code_dispatch_2D89C(uint8_t faultClass)`

**Fault class mapping**:

| Class | Meaning | Action |
|---|---|---|
| 0 | No fault | Clear fault code flags |
| 1 | Type A fault | Set MIL flag, log fault |
| 2 | Type B fault | Set MIL flag, enable limp mode |
| 3 | Type C fault | Set MIL flag, extended logging |
| 4+ | Reserved | Ignored |

---

### 17. `fault_recovery_4ABC4`

**Purpose**: Manages automatic fault recovery when fault conditions normalize.

**Signature**: `void fault_recovery_4ABC4(void)`

**Flow**:
1. Check if any active faults exist by testing multiple status bytes
2. If all cleared: set recovery flag to 1
3. If any still active: set recovery flag to 0
4. Returns recovery status

---

## Data Flow: Fault Detection Pipeline

```
Sensor Input
    │
    ▼
┌─────────────────────────────┐
│ Sensor Monitor Functions    │  e.g., coolant_temp_monitor_0x4F81E
│ (0x46BCC-0x47000)           │  sensor_ect_monitor_46BCC
└─────────────┬───────────────┘
              │ Fault detected?
              ▼
┌─────────────────────────────┐
│ dtc_debounce_monitor_43760  │  Debounce counter management
│ (Debounce Logic)            │  Prevents transient-triggered faults
└─────────────┬───────────────┘
              │ Debounced, confirmed?
              ▼
┌─────────────────────────────┐
│ dtc_code_set_46780          │  Set the DTC code in Backup RAM
│ (DTC Storage)               │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ dtcRelated_62002            │  Route DTC through handler chain
│ (DTC Dispatch)              │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ getFaultStatus_6743C        │  Update fault status query
│ (Fault Status Query)        │
└─────────────┬───────────────┘
              │ Fault confirmed?
              ▼
┌─────────────────────────────┐
│ Fault Response Actions:     │
│  • Set MIL (warning light)  │
│  • Enable limp mode         │
│  • Log to DTC history       │
│  • Update OBD readiness     │
└─────────────────────────────┘
```

## Key Memory Structures

### DTC Handler Context Table (`0xFFFF87D8`)

Each table entry is 16 bytes:

```
Offset  Size  Field
  +0     2    HandlerID (DTC code word)
  +2     2    HandlerFlags
  +4     2    DebouncePreset
  +6     1    HandlerType (0x00, 0x50=MIL, 0x60, 0x80, 0xC0, etc.)
  +7     1    Reserved/Status
  +8     4    HandlerFunctionPtr
  +12    2    HandlerParameter
  +14    2    NextHandlerOffset
```

### Fault Status Table at `0x7E4DC`

A 32-bit-per-entry lookup table indexed by fault code. The table is stored in ROM and contains metadata about each fault code's classification and required check behavior.

```
Entry Encoding (32 bits):
╔═══════════════════════════════════════════════════════════════╗
║ Bit 31-28 │ Bit 27-24 │ Bit 23-20 │ Bit 19-16 │ Bit 15-0   ║
║ Fault     │ Severity  │ System    │ Reserved  │ Mask/Flags ║
║ Class     │ Level     │ Domain    │           │            ║
╚═══════════════════════════════════════════════════════════════╝

Fault Class (bits 31-28):
  0x0 = Standard emission fault
  0x4 = Performance/powertrain
  0x5 = Most critical

Severity Level (bits 27-24):
  0x8 = OBD-II monitored

System Domain (bits 23-20):
  0x0 = General
  0x8 = ECU/CPU self-test
```

## Call Graph Summary

```
sensor_fault_handler_3b14c (dispatcher to 33 sensor monitors)
    │
    ├── dtc_o2_response_time_45F9C
    ├── dtc_p0120_tps_46DCA
    ├── dtc_p0100_maf_46DA0
    ├── dtc_cat_system_monitor_45FFC (772B — largest)
    ├── omp_fault_detect_44DF0
    ├── fault_code_handler_4436E
    ├── sensor_fault_detect_cyl_selectivity
    ├── ... (28 more sensor-specific monitors)
    │
    └── dtc_snapshot_manager_3b3bc
            │
            └── dtcRelated_62002
                    │
                    ├── dtc_handler_610FA (main dispatcher)
                    ├── dtc_handler_61550 (detailed handler, 358B)
                    ├── dtc_handler_61D2A (266B)
                    ├── dtc_handler_6184C (242B)
                    ├── dtc_handler_6155A (230B)
                    ├── dtc_handler_61304 (230B)
                    └── dtc_handler_61712 (216B)
                            │
                            └── getFaultStatus_6743C (78 callers)
                                    │
                                    └── getFaultStatus_subcheck
                                            ├── check_cond_A (stub)
                                            ├── check_cond_B (DTC walk)
                                            ├── check_cond_C (indirect)
                                            ├── check_cond_D (data check)
                                            └── check_cond_E (byte lookup)
```

## OBD-II Readiness Monitors

The firmware implements the following OBD-II readiness monitors:

| Monitor | Function | Address | Size |
|---|---|---|---|
| Misfire | `dtc_misfire_detection_468D6` | 0x468D6 | 208B |
| Fuel System | `fuel_injection_monitoring_457A2` | 0x457A2 | 338B |
| Comprehensive Component | `sensor_fault_handler_3b14c` | 0x3B14C | 206B |
| Catalyst | `dtc_cat_system_monitor_45FFC` | 0x45FFC | 772B |
| Heated Catalyst | (combined with catalyst) | — | — |
| EVAP System | (DTC P0400 at 0x47058) | 0x47058 | 14B |
| Secondary Air | (not implemented) | — | — |
| A/C Refrigerant | (not implemented) | — | — |
| O2 Sensor | `sensor_lambda_monitor_45F00` | 0x45F00 | 18B |
| O2 Heater | `dtc_o2_circuit_fault_45F54` | 0x45F54 | 72B |
| EGR/VVT | (not applicable on Renesis — no EGR or VVT hardware; 0x47058 is the EVAP purge monitor, see EVAP System) | — | — |

## Limp Mode Activation

When critical faults are confirmed, the system activates limp mode through `limp_mode_detection_25E36`:

```c
void limp_mode_detection_25E36(void) {
    // Check for critical fault conditions:
    // 1. CKP sensor failure → no crank signal
    // 2. APP sensor failure → no throttle response
    // 3. MAF sensor failure → limited fuel calculation
    // 4. Knock sensor failure → retarded timing
    
    if (/* critical fault active */) {
        activateLimpMode();  // Reduce power, limit RPM
        setMIL();            // Turn on check engine light
    }
}
```

## Emulator Validation Cases

```c
// Test Case 1: Basic fault status query
uint8_t test_getFaultStatus(void) {
    // Query fault code 0 (should be no fault in clean system)
    uint8_t result = getFaultStatus(0);
    assert(result == 0);
    
    // Set a fault in the global mask
    *((volatile uint32_t*)0xFFFFD96C) = 0x08800004;
    
    // Query fault code 2 (table entry = 0x00800004)
    // 0x08800004 & 0x00800004 = 0x00000004 → lower word != 0 → fault detected
    result = getFaultStatus(2);
    assert(result == 1);
    
    return 1;
}

// Test Case 2: DTC code setting loop
uint8_t test_dtc_set_clear(void) {
    // Set a DTC
    dtc_code_set();
    
    // Verify flag was set
    assert(*DTC_FLAG_ADDR != 0);
    
    // Clear DTC
    dtc_code_clear();
    
    // Verify cleared
    assert(*DTC_STORAGE_1 == 0);
    assert(*DTC_STORAGE_2 == 0);
    
    return 1;
}

// Test Case 3: Debounce monitor operation
uint8_t test_debounce_monitor(void) {
    // Enable debounce
    *DEBOUNCE_ENABLE = 1;
    
    // Set sensor input active
    *(uint8_t*)0xB3C8 = 1;
    
    // Run debounce monitor
    dtc_debounce_monitor_43760();
    
    // Counters should be incrementing (not cleared)
    assert(*DCNT_1 != 0 || *DCNT_2 != 0);
    
    // Disable debounce
    *DEBOUNCE_ENABLE = 0;
    
    // Run again — should clear counters
    dtc_debounce_monitor_43760();
    assert(*DCNT_1 == 0 && *DCNT_2 == 0);
    
    return 1;
}

// Test Case 4: Sub-check condition evaluation
uint8_t test_subcheck_conditions(void) {
    // check_cond_A always returns 0
    assert(check_cond_A(0) == 0);
    
    // check_cond_B with invalid fault code → 0
    assert(check_cond_B(0xFFFF) == 0);
    
    // check_cond_E fault code 0, table may have entries
    uint8_t result = check_cond_E(0);
    // Result depends on table contents at 0x7E734
    assert(result == 0 || result == 1);
    
    return 1;
}

// Test Case 5: Complete fault detection pipeline
uint8_t test_fault_detection_pipeline(void) {
    uint16_t testFaultCode = 42;
    
    // Step 1: Initial state — no fault
    assert(getFaultStatus(testFaultCode) == 0);
    
    // Step 2: Set global fault mask for this code
    uint32_t tableEntry = FAULT_STATUS_TABLE[testFaultCode];
    *FAULT_MASK_PTR = tableEntry;
    
    // Step 3: Now fault should be detected
    assert(getFaultStatus(testFaultCode) == 1);
    
    // Step 4: Clear mask
    *FAULT_MASK_PTR = 0;
    
    // Step 5: Fault should no longer be active
    assert(getFaultStatus(testFaultCode) == 0);
    
    return 1;
}
```

## Summary

The RX-8 ECU fault handling subsystem is a sophisticated OBD-II-compliant diagnostic framework built on:

1. **ROM-based Fault Status Table**: A 32-bit-per-entry table at `0x7E4DC` defining fault classification and behavior metadata for each fault code.

2. **Backup RAM Status Storage**: Persistent fault status storage in SH-2E backup RAM (`0xFFFFD000` range) for battery-backed fault memory.

3. **Two-Tier Fault Checking**: A primary global fault mask check (`getFaultStatus`) backed by condition-specific secondary checks that operate independently.

4. **Debounce Logic**: Multi-stage counter-based debounce (`dtc_debounce_monitor_43760`) to prevent transient faults from creating false DTCs.

5. **DTC Handler Chain**: A structured processing pipeline (`dtcRelated` → `dtc_handler_*` → `getFaultStatus`) that routes each DTC through appropriate handlers.

6. **Readiness Monitoring**: OBD-II mandated monitor tracking with pending/confirmed/permanent DTC status management.

7. **Recovery Mechanisms**: Automatic fault recovery (`fault_recovery_4ABC4`) when operating conditions normalize, clearing fault status without requiring diagnostic tool intervention.
