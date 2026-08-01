/*
 * setAlternatorWarningLight.c  —  RX-8 ECU alternator warning lamp control
 *
 * Address: 0x0275BC  |  Size: 74 bytes
 *
 * Sets the alternator warning light (dashboard lamp) based on several
 * fault/status conditions.  The light is ON if any of the following
 * conditions are true:
 *   - Alternator system in fault state (non-zero fault register)
 *   - Over-voltage fault flag set (==1)
 *   - Under-voltage fault flag set (==1)
 *   - Regulator fault flag set (==1)
 *   - Battery temp sensor fault flag set (==1)
 *
 * Otherwise the light is OFF.
 *
 * SH-2E asm (simplified):
 *   0x275BC:  mov.w  @(0x46,pc),r4  ; r4 = output flag addr
 *   0x275BE:  mov.w  @(0x46,pc),r2  ; r2 = fault status addr
 *   0x275C0:  mov.b  @r2,r3          ; r3 = fault status
 *   0x275C2:  tst    r3,r3           ; if non-zero
 *   0x275C4:  bt/s   0x275F8         ;   → set light ON
 *   0x275C6:  nop
 *   ... (check specific flags) ...
 *   0x275F8:  mov    #1,r3           ; light ON
 *   0x275FA:  bra    0x27602
 *   0x275FC:  mov.b  r3,@r4
 *   0x275FE:  mov    #0,r1           ; light OFF
 *   0x27600:  mov.b  r1,@r4
 *   0x27602:  rts
 *   0x27604:  nop
 *
 * Verified against ROM: c/tests/test_setAlternatorWarningLight.py
 */
#include <stdint.h>

/* 0x0275BC — set dash alternator warning lamp */
void setAlternatorWarningLight(void)
{
    volatile uint8_t *fault_status    = (volatile uint8_t *)0x0000B683;
    volatile uint8_t *overvoltage     = (volatile uint8_t *)0x0000B620;
    volatile uint8_t *undervoltage    = (volatile uint8_t *)0x0000B621;
    volatile uint8_t *reg_fault       = (volatile uint8_t *)0x0000B622;
    volatile uint8_t *batt_temp_fault = (volatile uint8_t *)0x0000C64B;
    volatile uint8_t *warning_lamp    = (volatile uint8_t *)0x0000B624;

    /* Fault conditions: any non-zero or ==1 triggers the lamp */
    if (*fault_status != 0 ||
        *overvoltage  == 1 ||
        *undervoltage == 1 ||
        *reg_fault    == 1 ||
        *batt_temp_fault == 1)
    {
        *warning_lamp = 1;  /* light ON */
    } else {
        *warning_lamp = 0;  /* light OFF */
    }
}
