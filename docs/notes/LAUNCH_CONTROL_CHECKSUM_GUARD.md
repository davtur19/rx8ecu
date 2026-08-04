# Launch-Control Checksum Guard — Exhaustive Analysis

ROMs under analysis:

| ROM | File | md5 | Notes |
|-----|------|-----|-------|
| Stock | `rx8ecu/roms/stock/60E1D400.bin` | `5e4236d2…` | no LC code |

CPU: SH-2E (SH7055), big-endian. Code cave `0x6C800..0x6CC00` is all `0xFF` in
stock; a tuned variant injects its LC subsystem there.

---

## 1. Executive summary

The launch-control system in a tuned variant ends with a self-check on 17 EEPROM bytes
(`E2[0x80..0x90]`, shadowed to RAM at `0xFFFFC37E..0xFFFFC38E`). Their signed
byte sum, truncated to 8 bits, must equal **−23 (0xE9)**. If not, the LC output
word is written 0 and LC is silently disabled. These 17 bytes are **not**
computed or written by any code in the ROM; they live in the physical EEPROM /
flash-backup region (`0x06000000`), outside the 512 KB image, and are populated
by the flasher tool. The ROM only *copies* EEPROM → RAM shadow via stock
routines that are byte-identical between stock and tuned.

**Conclusion: the "writer" of the key bytes is the flasher tool, not ECU code.
A wrong key simply disables LC; there is no fallback/self-healing path.**

---

## 2. The guard function — `LC_ValidateChecksum17` @ `0x6CB44`

Tuned-only. Fully decoded (44 bytes, `0x6CB44..0x6CB6E`):

```
6CB44  4F22  sts.l pr,@-r15
6CB46  E111  mov   #0x11,r1          ; r1 = 17 (count)
6CB48  E000  mov   #0x00,r0          ; r0 = accumulator (32-bit)
6CB4A  9223  mov.w @0x6CB94,r2       ; r2 = 0xC37D → sign-extended 0xFFFFC37D
6CB4C  E301  mov   #0x01,r3
6CB4E  323C  add   r3,r2             ; base = 0xFFFFC37E
        .loop:                       ; 0x6CB50
6CB50  6420  mov.b @r2,r4            ; byte, sign-extended to 32-bit
6CB52  304C  add   r4,r0             ; accumulate
6CB54  4110  dt    r1                ; decrement-and-test
6CB56  8FFA  bf/s  0x6CB50           ; loop while r1 != 0
6CB58  0009  nop                     ; (delay slot)
6CB5A  600E  exts.b r0,r0            ; truncate sum to signed 8-bit
6CB5C  88E9  cmp/eq #-23,r0          ; must equal 0xE9
6CB5E  8F02  bf/s  0x6CB66
6CB60  0009  nop
6CB62  A002  bra   0x6CB6A
6CB64  0009  nop
6CB66  E000  mov   #0x00,r0          ; FAIL: r0 = 0
6CB68  2501  mov.w r0,@r5            ; write 16-bit 0 to caller's output
6CB6A  4F26  lds.l @r15+,pr
6CB6C  000B  rts
6CB6E  0009  nop
```

Literal pool `0x6CB94`: word `0xC37D` (the base before `+1`).

Pseudocode (r5 = output word pointer):

```c
if ((int8_t)sum_of_17_signed_bytes(0xFFFFC37E..0xFFFFC38E) != -23)
    *(uint16_t *)r5 = 0;      /* LC output zeroed → LC disabled */
```

Window = 17 bytes, big-endian byte reads at `0xFFFFC37E..0xFFFFC38E`
(byte 0..16). Verified by emulation: 16×`0x00` + `0xE9` passes; 17×`0xFF`
(sum −17) fails.

---

## 3. Call graph / where it's referenced

```
0x94C8 LC_HookClampEntry (tuned; diverges from stock)
   └─ jsr 0x6C88C  LC_ClampAndGateOutput        (literal @ 0x94F4 = 0x0006C88C)
        └─ jsr 0x6CB44  LC_ValidateChecksum17
             → on mismatch zeroes word at r5 (the clamp output)
```

- **Stock** `0x94C8` did `cmp/hi r6,r4` / `bf/s` + `mov.w r6,@r5` / `mov.w r4,@r5`
  at `0x94F0`/`0x94F2`; **tuned** replaced the two stores with `rts` at `0x94F0`
  and redirects through `0x6C88C`.
- Cave dispatcher `0x6C848`: calls `0x6C800` (conditions: clutch @ `0xFFFFC004`,
  RPM/MAP gating → writes `0xFFFFB770`), then `0xF192`, then `jmp 0x21CCE`.
- `0x6C800` gates, `0x6CA80` (`LC_GateCondition_RPMLoad`, called from `0x35BBC`),
  `0x6CB96` (writes r13/r14 bytes @r5 with an `E2` gate) — siblings in the cave.

The guard's failure path (`mov.w r0,@r5` with 0) is the *only* output: LC is
simply off. No flag is set, no error code stored, no warning light.

---

## 4. What the window actually is (EEPRom shadow)

`0xFFFFC37E - 0xFFFFC2FE = 0x80`. With the verified EEPROM shadow layout:

- **Primary** data shadow: `0xFFFFC2FE + idx` (`E2_PRIMARY_BASE`)
- **Complement** shadow: `0xFFFFC3FE + idx` (`~data`)
- The checksum window is therefore **`E2[0x80..0x90]`** (17 bytes, primary),
  complement at `0xFFFFC47E..0xFFFFC48E`.
- Confirmed by the reconstructed C in `c/` (`eeprom_immo.h`,
  `getFromE2.c`, `E2IntoRAM.c`, `loadDatafromE2intoRAM.c`) and by docs
  (`docs/functions/getFromE2_E2ADDR_RAMADDR_LEN.md`).
- The EEPROM used area for immo/working data ends near index `0x1E`;
  `E2[0x80..0x90]` is a dedicated region — a plausible *key* area.

Boot load (`loadDatafromE2intoRAM` @ `0x36BD6`) copies only the first 32 bytes;
the full shadow is (re)populated by the generic `E2IntoRAM` (`0x38F58`) /
`getFromE2` (`0x39170`) machinery at runtime.

---

## 5. Who writes the key bytes — definitive answer

**The flasher tool.** The ROM never writes `E2[0x80..0x90]` to specific values:

1. **No literal covers the window.** Exhaustive search of the tuned flash for
   32-bit literals `0xFFFFC37D..0xFFFFC38F` → zero hits. `0xFFFFC37D` appears
   only as the 16-bit word at the guard's own literal `0x6CB94`.
2. **No `mov.w` PC-relative read** of any 16-bit literal in `[0xC37D..0xC3FF]`
   except the guard itself.
3. **No direct/indexed byte/word/long store** to `0xFFFFC37E` exists.
4. The only store the window can receive is the generic **blank-fill** routine
   `0x3925A..0x392E8` (writes `0xFF` to the whole `0xFFFFC2FE..0xFFFFC3FD`
   shadow), which runs only when E2 is unprogrammed
   (`byte@0x0007A5B4 == 0xFF` AND `byte@0xFFFFC50D == 0xFF`). That fills the
   window with `0xFF` → sum −17 → LC disabled. It is the *opposite* of a key
   writer; it is the "EEPROM blank" initializer.
5. The real values come from the physical EEPROM / flash-backup image at
   `0x06000000 + ((half & 0xFF) << 16)` (one 16-bit word per E2 byte-pair), read
   via `e2_flash_read` (`0xBFCA`). That region is **outside the 512 KB ROM
   image** and is programmed by the flasher. The stock E2 copy routines
   (`0x36BD6`, `0x38F58`, `0x39170`, `0x3925A`) are **byte-identical** between
   stock and tuned — the tuned ROM adds no EEPROM-writing code at all.
6. `getFromE2`'s fallback path can *repair* a corrupted shadow byte from the
   flash backup, but it reproduces whatever the backup holds; it never
   synthesizes −23.

Consequently, for the tuned ROM to have working LC, the physical ECU must hold
17 bytes at E2 index `0x80..0x90` whose signed sum is −23. Setting/removing LC
is a **flashing operation on the EEPROM backup region**, not a code patch.

---

## 6. Stock vs tuned (diff summary)

| Region | Stock | Tuned |
|--------|-------|-------|
| `0x6C800..0x6CC00` | all `0xFF` | LC subsystem (guard `0x6CB44` present) |
| `0x94C0..0x94F8` hook | native clamp | `jsr 0x6C88C` (literal `0x94F4`) |
| `0x36BD6`, `0x38F58`, `0x39170`, `0x3925A` (E2 machinery) | identical | identical |
| Guard pattern `4f 22 e1 11 e0 00` | absent | present |

503 differing runs total; the only LC-relevant divergence is the hook + cave.

---

## 7. Test vectors (guard semantics)

- Pass: window = 16×`0x00`, `0xE9` → sum −23.
- Fail: window = 17×`0xFF` → sum −17.
- Truncation matters: `exts.b` at `0x6CB5A` means the comparison is against
  −23 **mod 256**; e.g. a true sum of +233 also passes.

---

## 8. References

- `docs/notes/ECU.md` (Path B; open item on boot initializer now resolved: it
  is the generic EEPROM shadow copy, `E2IntoRAM`/`getFromE2`).
- `docs/notes/KNOWLEDGE.md` line 73 (window + −23).
- `docs/functions/getFromE2_E2ADDR_RAMADDR_LEN.md`, `c/eeprom_immo.h`,
  `c/E2IntoRAM.c`, `c/getFromE2.c`, `c/loadDatafromE2intoRAM.c`.
- `tools/disasm_sh2e.py` (SH-2E disassembler used throughout).
