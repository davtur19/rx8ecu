# getFromGPIO @ 0x70AC
_source: AI (Haiku) draft, unverified_

**Purpose:** Read GPIO input state after configuring pins for input mode; handle port setup, DDR (data direction register) writes, and multiplexing.

**Inputs:**
- r4: GPIO pin identifier (0=low, 1=high, or port+pin encoded)

**Outputs / side effects:**
- r0: GPIO input state (1 or 0 based on pin logic level)
- Port registers modified: DDR set to input, control bits cleared, multiplexing configured
- SR saved/restored; interrupts disabled during register access

**Calls:**
1. `getSR` (0x00003920) – save SR, disable interrupts (arg r4=0x00B0)
2. `setRegister_REG_BIT_VAL` (0x00004BBC) – write port control bits via r4=port_reg, r5=value, r6=?

**Behavior:**
1. Save SR, disable interrupts
2. Store GPIO pin argument in local stack
3. Configure port directions and multiplexing (via three setRegister calls):
   - Clear bits in port F002h DDR (and #11 mask)
   - Write 0x0080 to port F000h
   - Clear bits in port F002h (and #252 mask)
   - Add 0x70 to offset (112 decimal), write to F006h
   - Write 0x04 to F001h control
4. Test GPIO pin argument (bit test or value cmp):
   - If r4 == 0: call setRegister twice with r5=0x4000 and r5=0x8000 (clear both bits?)
   - If r4 == 1: call setRegister with r5=0x4000 only, set bit to 1
5. Read GPIO input state via port register
6. Restore SR, return r0

_Note: Port F000-F006 is SH7055 GPIO peripheral; DDR controls input/output direction._

**Confidence:** low – GPIO port mapping unverified; exact multiplexing purpose unclear.

**Uncertainties:**
- what GPIO pins are being read (sensor input? button state?)
- why three different port addresses (F000, F001, F002, F006) are configured
- exact meaning of r5 values (0x4000, 0x8000) – are they bitmasks or data values?
- whether function returns raw pin state or processed input
