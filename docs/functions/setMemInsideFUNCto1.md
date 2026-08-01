# setMemInsideFUNCto1 @ 0x3E3F0

## Location
- **Image:** 60E0FC00.bin
- **Address:** 0x3E3F0
- **End:** 0x3E3F8

## Purpose
Write 1 to a RAM fault/in-progress flag byte (0xFFFFC638). Used to
indicate that a function or subsystem is currently executing, or
to mark a memory location in a faulted state.

## C Implementation
`c/setMemInsideFUNCto1.c`

## Logic
```
*(uint8_t*)0xFFFFC638 = 1;
```

## Verification Status
- [x] Disassembly confirmed
- [x] C code written
- [ ] Emulator test (trivial function)
