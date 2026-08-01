# UDSPositiveResponse_16bit

**Address**: 0x058294 - 0x0582C0
**Length**: 44 bytes (22 instructions)

## Disassembly

```asm
  0x58294:  2FE6    mov.l        r14,@-r15
  0x58296:  E462    mov          #0x62,r4
  0x58298:  D34E    mov.l        @(0x9C,pc),r3   ; 0x00068B60
  0x5829A:  E603    mov          #0x03,r6
  0x5829C:  4F22    sts.l        pr,@-r15
  0x5829E:  7FFC    add          #0xFC,r15
  0x582A0:  6EF3    mov          r15,r14
  0x582A2:  65E3    mov          r14,r5
  0x582A4:  2E40    mov.b        r4,@r14
  0x582A6:  D44A    mov.l        @(0x94,pc),r4   ; 0xFFFFD226 = nan
  0x582A8:  6041    mov.w        @r4,r0
  0x582AA:  600D    extu.w       r0,r0
  0x582AC:  4019    shlr8        r0
  0x582AE:  80E1    mov.b        r0,@(0x1,r14)
  0x582B0:  8441    mov.b        @(0x1,r4),r0
  0x582B2:  80E2    mov.b        r0,@(0x2,r14)
  0x582B4:  430B    jsr          @r0
  0x582B6:  E422    mov          #0x22,r4
  0x582B8:  7F04    add          #0x04,r15
  0x582BA:  4F26    lds.l        @r15+,pr
  0x582BC:  000B    rts          
  0x582BE:  6EF6    mov.l        @r15+,r14
```
