# getFromE2_E2ADDR_RAMADDR_LEN @ 0x39170 (60E1D400)

**Status: verified** against ROM via emulator (`test_getFromE2.py`).

## Purpose
Copies `len` bytes from the **on-chip E2PROM / flash EEPROM** controller to a RAM
buffer, validating each byte against its stored complement. Reads calibration /
configuration data from NVRAM into working RAM.

## ABI (SH-2E)
```
r4 = e2addr   (16-bit offset into EEPROM array)
r5 = ramaddr  (destination RAM address)
r6 = len      (byte count)
r0 = return   (0 = success, 1 = error — at least one byte was invalid)
```

## Memory-mapped hardware interface
The function talks to the E2PROM controller through two register windows in the
peripheral address space:

| Address range     | Role               |
|-------------------|--------------------|
| `0xFFFFC2FE + offset` | E2 data register (read/write byte) |
| `0xFFFFC3FE + offset` | E2 complement register (read/write byte) |

Each EEPROM location stores a **data byte** and its **bitwise complement**.  
A successful read-back is: `data == ~complement`.

Additionally the function references:
- `0x06000000` — flash memory base (used as fallback read in the retry path)

## Internal subroutines called

| Address | Role |
|---------|------|
| `0x3920` | `getSR(mask)` — save SR (interrupt flag) |
| `0x3934` | `setSR(sr)` — restore SR |
| `0xC0A8` | **retry handler** — invoked on complement mismatch |
| `0xBFCA` | **flash reader** — reads a 32-bit value from the flash mapping |

Both `0xC0A8` and `0xBFCA` are called only on the **error recovery** path (complement
mismatch); semantics under analysis — the emulated test stubs them to return 0.

## Behaviour

```
saved_sr = getSR(0x10)             // disable interrupts
error    = 0

while len > 0:
    offset = e2addr & 0xFFFF       // extu.w r10,r14

    data_byte = E2_DATA[offset]    // mov.b @(r0+r13) — r0=offset, r13=0xFFFFC2FE
    comp_byte = E2_COMP[offset]    // mov.b @(r0+r11) — r11=0xFFFFC3FE

    if data_byte == ~comp_byte:
        // **Fast path**: valid location, copy to RAM
        ramaddr[0] = E2_DATA[offset]
    else:
        // **Slow path**: complement mismatch — attempt recovery
        if retry_handler(offset) == 0:
            // Retry succeeded: read via flash mapping, write complement back
            raw  = flash_read(0x06000000 + ((offset & 0xFF) << 16))
            byte = (raw >> 8) & 0xFF  if offset is even
                 = raw & 0xFF         if offset is odd
            E2_COMP[offset] = byte     // write complement via mov.b @(r0+r11)
            ramaddr[0] = E2_DATA[offset]
        else:
            error = 1                  // retry also failed, flag error

    len--;  e2addr++;  ramaddr++

setSR(saved_sr)                      // restore interrupts
return error
```

**Key observations:**
- The odd/even split of `offset` selects which byte of the 32-bit flash word to use
  (`bt`/`bf` on `offset & 1` at 0x3920E).
- Error-odd path: `0x0B34` = **mov.b r3,@(r0,r11)** writes the complemented data back
  to the E2 complement register. (Was missing from the original emulator/disassembler,
  causing `NotImplementedError`.)

## C lift

`c/getFromE2.c` — abstracted as:

```c
int getFromE2_E2ADDR_RAMADDR_LEN(uint16_t e2addr, uint8_t *ramaddr, uint8_t len);
```

The C code models the hardware via external symbols (`e2_read_byte`,
`e2_read_complement`, `e2_write_byte`, `e2_retry`, `e2_flash_read`, `getSR`/`setSR`)
supplied by the porting layer.

## Verification

- **test_getFromE2.py**: 500 random cases via `sh2emu.py` (60E1D400.bin), E2
  data/complement RAM at the magic addresses, helper subroutines stubbed. Valid-data
  and error-path tests pass (stubbed retry).

## Dependencies
- `getSR` / `setSR` (core SH-2 SR access)
- On-chip E2PROM controller hardware (memory-mapped registers)
- Flash reader `@0xBFCA` and retry handler `@0xC0A8` (ROM subroutines)
