# BYTE-PERFECT C sources — strict-pure tier sweep (gcc 3.4.6)

Date: 2026-08-10 · ROM: roms/stock/60E1D400.bin (bytes identical in all stock bins)
Compiler: /home/davide/gcc346/bin/sh-elf-gcc 3.4.6 · base recipe:
`sh-elf-gcc -nostdinc -I /tmp/stubinc -S <src>.c -m2e -O1 -fomit-frame-pointer`
then `sh-elf-as -isa=sh2e` + `sh-elf-objcopy -O binary --only-section=.text`.

| addr   | name                        | span | cmdline                                             | verdict       |
|--------|-----------------------------|------|-----------------------------------------------------|---------------|
| 0x2034 | checksum_complement_add     | 14   | base (-m2e -O1 -fomit-frame-pointer)                | BYTE-IDENTICAL |
| 0x2044 | diag_invertandreturn        | 14   | base                                                | BYTE-IDENTICAL |
| 0x2420 | math_complement_2420        | 16   | base (known)                                        | BYTE-IDENTICAL |
| 0x2430 | complement_shift_u16        | 16   | base (known)                                        | BYTE-IDENTICAL |
| 0x2460 | add16bitSaturate            | 24   | base (known)                                        | BYTE-IDENTICAL |
| 0x3EE58| updateMemoryAtAddress_8bit  | 16   | base                                                | BYTE-IDENTICAL |
| 0x3EE68| updateMemoryAtAddress_16bit | 16   | base                                                | BYTE-IDENTICAL |

Notes per source (see file headers):
- 0x3EE58/0x3EE68: store-variant siblings of the known 0x2420/0x2430 matches;
  `extu.w` inline asm for the 16-bit sibling (gcc 3.4.6 HImode widen asymmetry).
- 0x2034/0x2044: `mov.l/mov.w @r4` load + `not/~` complement-subtract helpers;
  r3/r0 register pins fix the `not` BEFORE the shift (gcc 3.4.6 schedules `not`
  first otherwise); 0x2044 needs `(int16_t)*(int16_t*)` load to avoid the
  automatic `extu.w r3,r3` widen.

Verdict key: BYTE-IDENTICAL = 100% of ROM window bytes reproduced.