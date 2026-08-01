# SetMemoryNotValid2 @ 0x3E5A8

## Location
- **Image:** 60E0FC00.bin
- **Address:** 0x3E5A8
- **End:** 0x3E5B0

## Purpose
Write 1 to a RAM fault/memory-invalid flag byte (0xFFFFC63A). Similar
to `setMemInsideFUNCto1`, but targets a different address. The "2"
suffix suggests multiple variants for different subsystems.

## C Implementation
`c/SetMemoryNotValid2.c`

## Logic
```
*(uint8_t*)0xFFFFC63A = 1;
```

## Verification Status
- [x] Disassembly confirmed
- [x] C code written
- [ ] Emulator test (trivial function)
