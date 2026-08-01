# can_message_handler_24588

**Address**: 0x024588 - 0x024596
**Length**: 14 bytes (7 instructions)

## Disassembly

```asm
  0x24588:  4F22    sts.l        pr,@-r15
  0x2458A:  D318    mov.l        @(0x30,pc),r3   ; 0x00024614
  0x2458C:  430B    jsr          @r0
  0x2458E:  0009    nop          
  0x24590:  D217    mov.l        @(0x2E,pc),r2   ; 0x00024410
  0x24592:  422B    jmp          @r2
  0x24594:  4F26    lds.l        @r15+,pr
```
