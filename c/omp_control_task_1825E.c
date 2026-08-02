/* omp_control_task_1825E.c
 *
 * ROM: 60E1D400  |  Address: 0x1825E  |  Size: 756 bytes  |  VERIFIED vs ROM emulator
 *
 * OMP (oil-metering-pump) RTOS task — the top of the stepper-motor control
 * chain.  Runs once per scheduler tick; no realtime return value (single
 * pass, one exit at 0x1853A/0x1854E).  Flow:
 *
 *   1. snapshot dispatch flags RAM8[A968 A969 A96A A96B A998 A96C]
 *   2. hardware fault gate (RAM9ECD bit1): bit clear -> A976 = 0 (pump
 *      "inoperative"); bit set -> A976 = 1 and, on a 0->1 edge, A987 = 1
 *   3. engine-on accumulation: A988 == 1 && A96C == 0 -> A989 = 1
 *   4. idle reset: A968 == 0 -> clear A977 / A978
 *   5. countdown: A97B != 0 -> A97B -= 1  (cmp/pl on A97B only; A96C is NOT
 *      part of the condition — confirmed vs disasm)
 *   6. purge block when A97B == 1 && A968 == 1 && A982 == 1:
 *        A974 = 0, A97F = 0, write port 807C = 0, A979 = 1;
 *        A977 == 1 -> A977 = 0, A983 = 1, port 8078 read-verify-decrement
 *        A978 == 1 -> A978 = 0
 *   7. countdown still active -> partial epilogue (A988 = A96C, return)
 * 8. mode dispatch (A97B == 0): A974 = A97F, then first-set wins:
 *        A998 == 1            -> 0x18C6C (wave 3/4/2 + A97B reload)
 *        A968 == 1            -> omp_waveform_state_machine_18860(A985)
 *        A96A == 1 && !CD06   -> 0x18C08 (diag store + rotor sync)
 *        A96B == 1            -> 0x18C5C (wave 6 + A97B = 8)
 *        A969 == 1            -> rotor_sync_position_detector(A984)
 *   9. common tail: A96C == 1 && A987 == 1 -> write port 807A = A974;
 *      read port 807A (default 0x37, see FINDINGS.md — the stock pseudo-sketch
 *      "send idle/off write16(0x807A,0x37)" is wrong: 0x37 is the read
 *      accessor default, and the read is 8-bit);
 *      A989 == 1 -> A975 ramp:
 *        read7a < CAL36, or (A974 >= CAL37 && A976 == 0) -> A975 = sat8(A975,1);
 *        A974 >= CAL37 && A976 == 1 && A975 > 0 -> A975--
 *      then A975 == 0 -> write port 8078 = CAL35;
 *      A975 != 0 && != 4 -> A979 = 0, A982 = 0
 *  10. full epilogue: A983 = A987 = A989 = 0; A985 = A968, A984 = A969,
 *      A986 = A96A, A988 = A96C
 *
 * Cal bytes (ROM): CAL35 @0x78E35 = 0x02 (P8078 write value), CAL36 @0x78E36
 * = 0x34 (ramp r7 threshold), CAL37 @0x78E37 = 0x3C (ramp A974 threshold).
 *
 * Internal task leaves (run natively in the emulator, effects inlined here —
 * not lifted as C): 0x18C6C, 0x18C5C, 0x18C08 (see FINDINGS.md).
 *   - 0x18C6C: A974 > 7 -> wave(3), A97B = 0x10; A974 == 7 -> wave(4),
 *     A97B = 4; A974 < 7 -> wave(2), A97B = 0x10.
 *   - 0x18C5C: wave(6), A97B = 8.
 *   - 0x18C08: if A980 == 1: write port 807C = 1, diag store via 0x9668
 *     (verified: RAM8[0xFFFFB5F3] = 1), A980 = 2.  Then A974 == A8F1 ->
 *     A97B = 0x30, A980 = 1; else rotor_sync_position_detector(A984).
 *
 * Verified: 150000+ random + edge inputs across 5 seeds vs the ROM emulator,
 * 0 mismatches (test_omp_control_task_1825E.py).
 */
#include <stdint.h>

#define RAM_A968 (*(volatile uint8_t *)0xFFFFA968)
#define RAM_A969 (*(volatile uint8_t *)0xFFFFA969)
#define RAM_A96A (*(volatile uint8_t *)0xFFFFA96A)
#define RAM_A96B (*(volatile uint8_t *)0xFFFFA96B)
#define RAM_A96C (*(volatile uint8_t *)0xFFFFA96C)
#define RAM_A974 (*(volatile uint8_t *)0xFFFFA974)
#define RAM_A975 (*(volatile uint8_t *)0xFFFFA975)
#define RAM_A976 (*(volatile uint8_t *)0xFFFFA976)
#define RAM_A977 (*(volatile uint8_t *)0xFFFFA977)
#define RAM_A978 (*(volatile uint8_t *)0xFFFFA978)
#define RAM_A979 (*(volatile uint8_t *)0xFFFFA979)
#define RAM_A97B (*(volatile uint8_t *)0xFFFFA97B)
#define RAM_A97C (*(volatile uint8_t *)0xFFFFA97C)
#define RAM_A97D (*(volatile uint8_t *)0xFFFFA97D)
#define RAM_A97E (*(volatile uint8_t *)0xFFFFA97E)
#define RAM_A97F (*(volatile uint8_t *)0xFFFFA97F)
#define RAM_A980 (*(volatile uint8_t *)0xFFFFA980)
#define RAM_A981 (*(volatile uint8_t *)0xFFFFA981)
#define RAM_A982 (*(volatile uint8_t *)0xFFFFA982)
#define RAM_A983 (*(volatile uint8_t *)0xFFFFA983)
#define RAM_A984 (*(volatile uint8_t *)0xFFFFA984)
#define RAM_A985 (*(volatile uint8_t *)0xFFFFA985)
#define RAM_A986 (*(volatile uint8_t *)0xFFFFA986)
#define RAM_A987 (*(volatile uint8_t *)0xFFFFA987)
#define RAM_A988 (*(volatile uint8_t *)0xFFFFA988)
#define RAM_A989 (*(volatile uint8_t *)0xFFFFA989)
#define RAM_A98A (*(volatile uint8_t *)0xFFFFA98A)
#define RAM_A98D (*(volatile uint8_t *)0xFFFFA98D)
#define RAM_A998 (*(volatile uint8_t *)0xFFFFA998)
#define RAM_A8F1 (*(volatile uint8_t *)0xFFFFA8F1)
#define RAM_ECD  (*(volatile uint8_t *)0xFFFF9ECD)
#define RAM_CD06 (*(volatile uint8_t *)0xFFFFCD06)
#define RAM_C6AC (*(volatile uint8_t *)0xFFFFC6AC)   /* fault flag leaf 0x3F050 */
#define RAM_B5F3 (*(volatile uint8_t *)0xFFFFB5F3)   /* diag table writer 0x9668 */

#define ROM_CAL35 (*(const uint8_t *)0x78E35)        /* 0x02 P8078 write value */
#define ROM_CAL36 (*(const uint8_t *)0x78E36)        /* 0x34 ramp r7 threshold */
#define ROM_CAL37 (*(const uint8_t *)0x78E37)        /* 0x3C ramp A974 threshold */

/* 0x3ED3C — verified: RAM8[a] == ~RAM8[a+1] ? s8(RAM8[a]) : s8(default),
 * fault flag RAM8[0xFFFFC6AC] set on mismatch. */
extern int8_t readValue_8bit_ADDRESS_VAL(uint16_t addr, uint8_t default_);
/* 0x3EE58 — verified: complementary-encoded byte store, RAM8[a] = val,
 * RAM8[a+1] = ~val. */
extern void updateMemoryAtAddress_8bit_ADDR_VAL(uint16_t addr, uint8_t val);
/* 0x18552 — verified stepper waveform driver. */
extern void omp_stepper_waveform_driver(uint8_t mode);
/* 0x18860 — verified waveform state machine stage of the OMP chain. */
extern void omp_waveform_state_machine_18860(uint8_t mode);
/* 0x189EE — verified rotor-sync position detector. */
extern void rotor_sync_position_detector(uint8_t mode);
/* 0x2478 — verified saturating byte add: min(a+b, 255). */
extern uint8_t addSaturate8Bit(uint8_t a, uint8_t b);

/* ---- internal task leaves, inlined (see header for exact semantics) ---- */

static void omp_wave_reload_18C6C(void)
{
    if (RAM_A974 > 7) {
        omp_stepper_waveform_driver(3);
        RAM_A97B = 0x10;
    } else if (RAM_A974 == 7) {
        omp_stepper_waveform_driver(4);
        RAM_A97B = 4;
    } else {
        omp_stepper_waveform_driver(2);
        RAM_A97B = 0x10;
    }
}

static void omp_wave_purge_18C5C(void)
{
    omp_stepper_waveform_driver(6);
    RAM_A97B = 8;
}

static void omp_diag_rotor_18C08(void)
{
    if (RAM_A980 == 1) {
        updateMemoryAtAddress_8bit_ADDR_VAL(0xFFFF807C, 1);
        RAM_B5F3 = 1;                    /* 0x9668 diag-table store */
        RAM_A980 = 2;
    }
    if (RAM_A974 == RAM_A8F1) {
        RAM_A97B = 0x30;
        RAM_A980 = 1;
    } else {
        rotor_sync_position_detector(RAM_A984);
    }
}

void omp_control_task_1825E(void)
{
    uint8_t a968, a969, a96a, a96b, a96c, a998;

    /* step 1: snapshot dispatch flags onto the stack frame (0x18270..0x18294) */
    a968 = RAM_A968;                 /* [r15+4]  */
    a969 = RAM_A969;                 /* [r15+0xC] */
    a96b = RAM_A96B;                 /* [r15+0]  */
    a96a = RAM_A96A;                 /* [r15+8]  */
    a998 = RAM_A998;                 /* [r15+0x10] */
    a96c = RAM_A96C;                 /* r10 */

    /* step 2: hardware fault gate (0x1829A..0x182B2) */
    if ((RAM_ECD & 2) == 0) {
        RAM_A976 = 0;
    } else {
        uint8_t old = RAM_A976;
        RAM_A976 = 1;
        if (old == 0)
            RAM_A987 = 1;
    }

    /* step 3: engine-on accumulation */
    if (RAM_A988 == 1 && a96c == 0)
        RAM_A989 = 1;

    /* step 4: idle-state reset */
    if (a968 == 0) {
        RAM_A977 = 0;
        RAM_A978 = 0;
    }

    /* step 5: countdown decrement */
    if (RAM_A97B != 0)
        RAM_A97B = (uint8_t)(RAM_A97B - 1);

    /* step 6: purge block */
    if (RAM_A97B == 1 && a968 == 1 && RAM_A982 == 1) {
        int8_t v;
        RAM_A974 = 0;
        RAM_A97F = 0;
        updateMemoryAtAddress_8bit_ADDR_VAL(0xFFFF807C, 0);
        RAM_A979 = 1;
        if (RAM_A977 == 1) {
            RAM_A977 = 0;
            RAM_A983 = 1;
            v = readValue_8bit_ADDRESS_VAL(0xFFFF8078, 0);
            if ((uint8_t)v != 0)
                updateMemoryAtAddress_8bit_ADDR_VAL(0xFFFF8078, (uint8_t)((uint8_t)v - 1));
        }
        if (RAM_A978 == 1)
            RAM_A978 = 0;
    }

    /* step 7: countdown still active -> partial epilogue */
    if (RAM_A97B != 0) {
        RAM_A988 = a96c;
        return;
    }

    /* step 8: mode dispatch */
    RAM_A974 = RAM_A97F;
    if (a998 == 1) {
        omp_wave_reload_18C6C();
    } else if (a968 == 1) {
        omp_waveform_state_machine_18860(RAM_A985);
    } else if (a96a == 1 && RAM_CD06 == 0) {
        omp_diag_rotor_18C08();
    } else if (a96b == 1) {
        omp_wave_purge_18C5C();
    } else if (a969 == 1) {
        rotor_sync_position_detector(RAM_A984);
    }

    /* step 9: common tail (0x184C8..0x18516) */
    if (a96c == 1 && RAM_A987 == 1)
        updateMemoryAtAddress_8bit_ADDR_VAL(0xFFFF807A, RAM_A974);
    {
        uint8_t read7a = (uint8_t)readValue_8bit_ADDRESS_VAL(0xFFFF807A, 0x37);
        if (RAM_A989 == 1) {
            if (read7a < ROM_CAL36 ||
                (RAM_A974 >= ROM_CAL37 && RAM_A976 == 0))
                RAM_A975 = addSaturate8Bit(RAM_A975, 1);   /* 0x2478 */
            else if (RAM_A974 >= ROM_CAL37 && RAM_A976 == 1 && RAM_A975 != 0)
                RAM_A975 = (uint8_t)(RAM_A975 - 1);
        }
    }
    if (RAM_A975 == 0)
        updateMemoryAtAddress_8bit_ADDR_VAL(0xFFFF8078, ROM_CAL35);
    else if (RAM_A975 != 4) {
        RAM_A979 = 0;
        RAM_A982 = 0;
    }

    /* step 10: full epilogue (0x1851C..0x1853C) */
    RAM_A983 = 0;
    RAM_A987 = 0;
    RAM_A989 = 0;
    RAM_A985 = a968;
    RAM_A984 = a969;
    RAM_A986 = a96a;
    RAM_A988 = a96c;
}
