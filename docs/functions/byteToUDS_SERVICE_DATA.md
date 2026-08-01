# byteToUDS_SERVICE_DATA

**Address**: 0x05846A - 0x058486
**Length**: 28 bytes (14 instructions)

## Disassembly

```asm
  0x5846A:  E601    mov          #0x01,r6
  0x5846C:  D208    mov.l        @(0x10,pc),r2   ; 0x00068B60
  0x5846E:  4F22    sts.l        pr,@-r15
  0x58470:  7FFC    add          #0xFC,r15
  0x58472:  63F3    mov          r15,r3
  0x58474:  7303    add          #0x03,r3
  0x58476:  2350    mov.b        r5,@r3
  0x58478:  65F3    mov          r15,r5
  0x5847A:  420B    jsr          @r0
  0x5847C:  7503    add          #0x03,r5
  0x5847E:  7F04    add          #0x04,r15
  0x58480:  4F26    lds.l        @r15+,pr
  0x58482:  000B    rts          
  0x58484:  0009    nop          
```
