# udsErrorResponse

**Address**: 0x0553AA - 0x0553D0
**Length**: 38 bytes (19 instructions)

## Disassembly

```asm
  0x553AA:  E37F    mov          #0x7F,r3
  0x553AC:  2FE6    mov.l        r14,@-r15
  0x553AE:  6043    mov          r4,r0
  0x553B0:  4F22    sts.l        pr,@-r15
  0x553B2:  E603    mov          #0x03,r6
  0x553B4:  7FFC    add          #0xFC,r15
  0x553B6:  6EF3    mov          r15,r14
  0x553B8:  2E30    mov.b        r3,@r14
  0x553BA:  80E1    mov.b        r0,@(0x1,r14)
  0x553BC:  D315    mov.l        @(0x2A,pc),r3   ; 0x00068B60
  0x553BE:  6053    mov          r5,r0
  0x553C0:  80E2    mov.b        r0,@(0x2,r14)
  0x553C2:  430B    jsr          @r0
  0x553C4:  65E3    mov          r14,r5
  0x553C6:  E003    mov          #0x03,r0
  0x553C8:  7F04    add          #0x04,r15
  0x553CA:  4F26    lds.l        @r15+,pr
  0x553CC:  000B    rts          
  0x553CE:  6EF6    mov.l        @r15+,r14
```
