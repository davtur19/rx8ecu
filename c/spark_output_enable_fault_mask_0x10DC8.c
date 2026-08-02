/* spark_output_enable_fault_mask_0x10DC8.c
 *
 * ROM: 60E1D400  |  Address: 0x10DC8  |  Size: 0x168 bytes (0x10DC8..0x10F30)
 *       reachable code 0x10DC8..0x10F2C; literal pools @0x10E6A..0x10E8A and
 *       @0x10F30..0x10F46; next function @0x10F48.
 *       VERIFIED vs ROM emulator (0 mismatches,
 *       c/tests/test_spark_output_enable_fault_mask_0x10DC8.py).
 *
 * Fault/enable-gated spark output bitmask (pure leaf, no callee calls).
 * Called with r4 = u8 rotor/ignition status code from the spark timing
 * pipeline (callers 0x144FC-area inside the rotor-sequence dispatcher and
 * 0x14730 inside the all-rotor timings dispatch, both `jsr` the function
 * pointer 0x10DC8).  The status code only special-cases 0, 6, 12, 18.
 *
 * Semantics (execution order; all flag bytes compared as ==1 or !=0 after
 * extu.b, per the mov.w 16-bit literals that sign-extend to 0xFFFFxxxx):
 *   1. r5 = 0 (delay-slot mov r6,r5).
 *      If RAM8 A9D9 == 1: A5DE = 0.
 *   2. Fault latch: r5 = 15 iff any of C63C, A798, BC94, BC95 == 1, or
 *      the CAN TX flag C240 == 0; else r5 stays 0.
 *   3. If A9DA == 1 (enable path): A9D9 = 0, A5DE = 0, then OR the four
 *      channel flags into r5: A9D8 -> bit2(4), A9D6 -> bit3(8),
 *      A9D7 -> bit0(1), A9D5 -> bit1(2).
 *   4. Else (A9DA != 1): the 0x10EB0 "re-arm" block runs iff A5DE == 1 or
 *      (A9D9 == 0 and r4 is 6 or 18); it ORs A9D8->4, A9D6->8 and sets
 *      A5DE = 1.  Then the 0x10EEA block runs iff A9D9 == 0 or r4 == 0 or
 *      r4 == 12; it ORs A9D7->1, A9D5->2 and clears A9D9 = 0 (delay-slot
 *      write on the A9D5 branch, executed on both paths).
 *   5. Output: RAM16 A5D8 = r5; if BC96 == 1 then RAM16 A5DA = 1,
 *      RAM16 A5DC = 4 (return r0 = 1), else A5DA = A5DC = 0
 *      (return r0 = the BC96 byte read).
 *
 * RAM inputs:  A9D9, A9DA, A5DE, A9D5..A9D8 (u8 flags), C63C, A798, BC94,
 *   BC95, C240 (CAN TX flag), BC96 (u8 enable/return source).
 * RAM outputs: A5DE, A9D9 (u8), A5D8, A5DA, A5DC (u16).
 * r4 input:  u8 status code (0/6/12/18 special).
 * Return:    r0 = 1 when BC96 == 1, else the BC96 byte value.
 *
 * NOTE on the low 16-bit addresses: ROM reaches C63C / C240 via `mov.w`
 * literals that sign-extend to 0xFFFFC63C / 0xFFFFC240 — the same physical
 * bytes as 0x0000C63C / 0x0000C240 on the SH-2 (the immo lifts use the
 * 0x0000xxxx alias for C240/C241).
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>

#define RAM_A9D9   (*(volatile uint8_t *)0xFFFFA9D9)   /* fault latch / state flag */
#define RAM_A9DA   (*(volatile uint8_t *)0xFFFFA9DA)   /* enable path selector */
#define RAM_A5DE   (*(volatile uint8_t *)0xFFFFA5DE)   /* re-arm latch */
#define RAM_A9D8   (*(volatile uint8_t *)0xFFFFA9D8)   /* channel flag -> bit2 */
#define RAM_A9D6   (*(volatile uint8_t *)0xFFFFA9D6)   /* channel flag -> bit3 */
#define RAM_A9D7   (*(volatile uint8_t *)0xFFFFA9D7)   /* channel flag -> bit0 */
#define RAM_A9D5   (*(volatile uint8_t *)0xFFFFA9D5)   /* channel flag -> bit1 */
#define RAM_C63C   (*(volatile uint8_t *)0xFFFFC63C)   /* fault flag */
#define RAM_A798   (*(volatile uint8_t *)0xFFFFA798)   /* enable flag */
#define RAM_BC94   (*(volatile uint8_t *)0xFFFFBC94)   /* fault flag */
#define RAM_BC95   (*(volatile uint8_t *)0xFFFFBC95)   /* fault flag */
#define RAM_C240   (*(volatile uint8_t *)0xFFFFC240)   /* CAN TX flag */
#define RAM_BC96   (*(volatile uint8_t *)0xFFFFBC96)   /* output-enable flag */

#define RAM_A5D8   (*(volatile uint16_t *)0xFFFFA5D8)  /* output bitmask */
#define RAM_A5DA   (*(volatile uint16_t *)0xFFFFA5DA)  /* output word */
#define RAM_A5DC   (*(volatile uint16_t *)0xFFFFA5DC)  /* output word */

uint32_t spark_output_enable_fault_mask_0x10DC8(uint32_t r4_in)
{
    uint8_t  r4 = (uint8_t)(r4_in & 0xFF);   /* 0x10E94/0x10EDA extu.b r4 */
    uint16_t r5 = 0;                         /* 0x10DD8 mov r6,r5 (r6 = 0) */

    /* ---- 0x10DD0: A9D9 == 1 clears the re-arm latch ---- */
    if (RAM_A9D9 == 1)
        RAM_A5DE = 0;

    /* ---- 0x10DDC fault latch: any fault or !CAN_TX -> all bits ---- */
    if (RAM_C63C == 1 || RAM_A798 == 1 || RAM_BC94 == 1 || RAM_BC95 == 1
        || RAM_C240 == 0) {
        r5 = 15;
    }

    /* ---- 0x10E18 enable-path dispatch on A9DA ---- */
    if (RAM_A9DA == 1) {
        RAM_A9D9 = 0;                        /* 0x10E24 */
        RAM_A5DE = 0;                        /* 0x10E26 */
        if (RAM_A9D8 == 1) r5 |= 4;          /* 0x10E2E */
        if (RAM_A9D6 == 1) r5 |= 8;          /* 0x10E3E */
        if (RAM_A9D7 == 1) r5 |= 1;          /* 0x10E4E */
        if (RAM_A9D5 == 1) r5 |= 2;          /* 0x10E5E */
    } else {
        /* ---- 0x10E8C re-arm block (0x10EB0) ---- */
        uint8_t a9d9 = RAM_A9D9;
        if (RAM_A5DE == 1 || (a9d9 == 0 && (r4 == 6 || r4 == 18))) {
            if (RAM_A9D8 == 1) r5 |= 4;      /* 0x10EB6 */
            if (RAM_A9D6 == 1) r5 |= 8;      /* 0x10EC6 */
            RAM_A5DE = 1;                    /* 0x10ED0 */
        }
        /* ---- 0x10ED2 clear-latch block (0x10EEA) ---- */
        if (RAM_A9D9 == 0 || r4 == 0 || r4 == 12) {
            if (RAM_A9D7 == 1) r5 |= 1;      /* 0x10EF0 */
            if (RAM_A9D5 == 1) r5 |= 2;      /* 0x10F00 */
            RAM_A9D9 = 0;                    /* 0x10F04 delay slot */
        }
    }

    /* ---- 0x10F0A outputs ---- */
    RAM_A5D8 = r5;                           /* mov.w r5,@r3 */
    if (RAM_BC96 == 1) {
        RAM_A5DA = 1;                        /* 0x10F20 */
        RAM_A5DC = 4;                        /* 0x10F26 */
        return 1;                            /* 0x10F1E mov #1,r0 */
    }
    RAM_A5DA = 0;                            /* 0x10F28 */
    RAM_A5DC = 0;                            /* 0x10F2A */
    return RAM_BC96;                         /* r0 still holds BC96 byte */
}
