# intToUDS_SERVICE_DATA

**Address**: 0x058448 - 0x05846A
**Length**: 34 bytes (17 instructions)

## Disassembly

```asm
  0x58448:  2FE6    mov.l        r14,@-r15
  0x5844A:  635D    extu.w       r5,r3
  0x5844C:  4F22    sts.l        pr,@-r15
  0x5844E:  6053    mov          r5,r0
  0x58450:  7FFC    add          #0xFC,r15
  0x58452:  6EF3    mov          r15,r14
  0x58454:  4319    shlr8        r3
  0x58456:  E602    mov          #0x02,r6
  0x58458:  2E30    mov.b        r3,@r14
  0x5845A:  80E1    mov.b        r0,@(0x1,r14)
  0x5845C:  D30C    mov.l        @(0x18,pc),r3   ; 0x00068B60
  0x5845E:  430B    jsr          @r0
  0x58460:  65E3    mov          r14,r5
  0x58462:  7F04    add          #0x04,r15
  0x58464:  4F26    lds.l        @r15+,pr
  0x58466:  000B    rts          
  0x58468:  6EF6    mov.l        @r15+,r14
```
