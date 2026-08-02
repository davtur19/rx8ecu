/* ====================================================================
 * atu_fpu_control_wrapper — FPU control sequence wrapper
 *
 * Address:  0x70AC (ROM 60E1D400)
 * Size:     36 bytes
 * Source:   ida-ai
 * Callers:  7 callers (getVehicleStatusInputs, FUN_00006796,
 *           FUN_0002c1dc, writeOilPressureLight, writeOilPressureGauge,
 *           FUN_0003c466, FUN_0003f180)
 *
 * This function performs the FPU activation/control sequence:
 * 1. Reads/modifies SR (Status Register) to enable FPU
 * 2. Sets a bit in the FPU control register
 * 3. Executes an FPU NOP (synchronization barrier)
 *
 * Calling convention (SH-2E):
 *   No arguments (uses implicit stack for temporary storage)
 *   Calls sub-functions via register-indirect jsr
 *
 * Sub-functions called:
 *   setSR_PARAM    (0x2054): Modify SR with mask, save old SR to stack
 *   setRegister_REG_BIT_VAL (0x4BBC): Set/clear bit in memory-mapped register
 *   loadStatusRegister_ADDR (0x2064): raw SR write (ldc r4,sr)
 *
 * The sequence:
 *   old_sr = setSR_PARAM(stack_tmp, 0xE0)
 *   setRegister_REG_BIT_VAL(0xFFFFF74E, 0x100, 1)
 *   loadStatusRegister_ADDR(old_sr)
 * ==================================================================== */

#include <stdint.h>

/* Sub-function declarations */
extern void setSR_PARAM(uint32_t *save_addr, uint16_t mask);
extern void setRegister_REG_BIT_VAL(uint16_t *reg_addr, uint16_t bit_val, uint32_t size);
extern void loadStatusRegister_ADDR(uint32_t old_sr);

void atu_fpu_control_wrapper(void)
{
    uint32_t old_sr;

    /* Step 1: Modify SR with mask 0x00E0.
     * The mask 0x00E0 selects bits 5-7 of SR, which control:
     *   - Bit 5: FPU error flag / mode select
     *   - Bit 6: FPU enable (FD bit in SH-2E)
     *   - Bit 7: IMASK bit 2 (interrupt priority)
     * setSR_PARAM saves the old SR value to the stack temporary. */
    setSR_PARAM(&old_sr, 0x00E0);

    /* Step 2: Set bit 8 (0x0100) in the FPU control register at address 0xFFFFF74E.
     * The third argument (size=1) indicates a word (16-bit) operation.
     * This likely enables a specific FPU feature or mode. */
    setRegister_REG_BIT_VAL((uint16_t *)0xFFFFF74E, 0x0100, 1);

    /* Step 3: raw SR write (0x2064, formerly labelled fpu_nop_stub).
     * Unconditionally writes the saved SR value back (ldc r4,sr).
     * The argument is the old SR value saved in step 1. */
    loadStatusRegister_ADDR(old_sr);
}
