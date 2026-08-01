# can_rx_handler_49100

**Address**: 0x049100 - 0x04911E
**Length**: 30 bytes (15 instructions)

## Disassembly

```asm
  0x49100:  2FE6    mov.l        r14,@-r15
  0x49102:  4F22    sts.l        pr,@-r15
  0x49104:  DE26    mov.l        @(0x4C,pc),r14   ; 0x0003EEFE
  0x49106:  D425    mov.l        @(0x4A,pc),r4   ; 0xFFFF878C = nan
  0x49108:  4E0B    jsr          @r0
  0x4910A:  0009    nop          
  0x4910C:  9439    mov.w        @(0x72,pc),r4   ; 0x8788
  0x4910E:  4E0B    jsr          @r0
  0x49110:  0009    nop          
  0x49112:  9437    mov.w        @(0x6E,pc),r4   ; 0x878A
  0x49114:  4E0B    jsr          @r0
  0x49116:  0009    nop          
  0x49118:  4F26    lds.l        @r15+,pr
  0x4911A:  000B    rts          
  0x4911C:  6EF6    mov.l        @r15+,r14
```
