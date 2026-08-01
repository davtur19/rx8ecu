# can_message_setup_dispatcher_33974

**Address**: 0x033974 - 0x03399E
**Length**: 42 bytes (21 instructions)

## Disassembly

```asm
  0x33974:  D429    mov.l        @(0x52,pc),r4   ; 0xFFFFC044 = nan
  0x33976:  E500    mov          #0x00,r5
  0x33978:  9148    mov.w        @(0x90,pc),r1   ; 0xC04C
  0x3397A:  6053    mov          r5,r0
  0x3397C:  D228    mov.l        @(0x50,pc),r2   ; 0xFFFFC04D = nan
  0x3397E:  6320    mov.b        @r2,r3
  0x33980:  D22A    mov.l        @(0x54,pc),r2   ; 0x00009AE4
  0x33982:  2430    mov.b        r3,@r4
  0x33984:  8041    mov.b        r0,@(0x1,r4)
  0x33986:  8042    mov.b        r0,@(0x2,r4)
  0x33988:  8043    mov.b        r0,@(0x3,r4)
  0x3398A:  8044    mov.b        r0,@(0x4,r4)
  0x3398C:  8045    mov.b        r0,@(0x5,r4)
  0x3398E:  D325    mov.l        @(0x4A,pc),r3   ; 0xFFFFC04E = nan
  0x33990:  6030    mov.b        @r3,r0
  0x33992:  8046    mov.b        r0,@(0x6,r4)
  0x33994:  6010    mov.b        @r1,r0
  0x33996:  8047    mov.b        r0,@(0x7,r4)
  0x33998:  D423    mov.l        @(0x46,pc),r4   ; 0x0004E9D0
  0x3399A:  422B    jmp          @r2
  0x3399C:  0009    nop          
```
