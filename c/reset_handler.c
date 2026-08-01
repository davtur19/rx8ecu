/*
 * reset_handler.c  —  RX-8 PCM @ ROM 0x4E0 (60E1D400), hand-reconstructed
 *                      Main reset and hardware initialization handler.
 *
 * This is the primary reset entry point after the boot ROM / vector table
 * redirect.  It is called by Manual_Reset (0x8B8) after basic BSC and GPIO
 * initialization.  It performs:
 *   - Hardware init (clock, memory controller, peripherals)
 *   - Cold vs warm start detection (magic value check)
 *   - Watchdog timer recovery
 *   - Reset cause determination
 *   - Final jump to the RTOS main initialization
 *
 * Parameter r4 = cold_start flag (0 = cold start, non-zero = warm start)
 * Parameter r5 = reset reason byte
 *
 * SH-2E calling convention: int args r4..r6, return r0.
 *
 * Original SH-2E (big-endian, ~146 bytes from 0x4E0):
 *
 *   ; Prologue
 *   0x4E0: add #-8,r15            ; allocate 8 bytes
 *   0x4E2: mov.l r4,@(4,r15)      ; save r4 (cold_start) at fp+4
 *   0x4E4: mov.b r5,@r15          ; save r5 (reason) at fp+0
 *
 *   ; First watchdog reset
 *   0x4E6: bsr 0x572              ; call resetWatchdog()
 *   0x4E8: mov #1,r14             ; r14 = 1 (default "not recovered" flag)
 *
 *   ; Call three hardware init functions
 *   0x4EA: mov.w 0x586,r2         ; r2 = hw_init_1 addr (0x0170)
 *   0x4EC: jsr @r2                ; hw_init_1()
 *   0x4EE: nop
 *   0x4F0: mov.w 0x588,r3         ; r3 = hw_init_2 addr (0x041C)
 *   0x4F2: jsr @r3                ; hw_init_2()
 *   0x4F4: nop
 *   0x4F6: mov.w 0x58a,r2         ; r2 = hw_init_3 addr (0x03D4)
 *   0x4F8: jsr @r2                ; hw_init_3()
 *   0x4FA: nop
 *
 *   ; Cold start check
 *   0x4FC: mov.l @(4,r15),r3      ; r3 = saved cold_start flag
 *   0x4FE: tst r3,r3              ; cold_start == 0 ?
 *   0x500: bf  0x556              ; if non-zero (warm), goto warm_path
 *
 *   ; Cold start path:
 *   0x502: mov.l 0x59c,r3         ; r3 = MAGIC_VALUE = 0x5AA5A55A
 *   0x504: mov.l 0x5a0,r1         ; r1 = &magic_location = 0xFFFFDFFC
 *   0x506: mov.l @r1,r2           ; r2 = *(uint32_t*)0xFFFFDFFC
 *   0x508: cmp/eq r3,r2           ; is magic correct?
 *   0x50A: bt  0x51a              ; if yes, skip watchdog recovery
 *
 *   ; Magic mismatch — potential watchdog-induced reset
 *   0x50C: bsr 0x5b0              ; call checkWatchdog(7)
 *   0x50E: mov #7,r4              ; r4 = 7 (WDT check code)
 *   0x510: mov r0,r4              ; r4 = result
 *   0x512: tst r4,r4              ; watchdog overflowed?
 *   0x514: bf  0x51a              ; if yes, skip (normal recovery)
 *   0x516: mov #0,r14             ; r14 = 0 (NO recovery — clear flag)
 *   0x518: mov.w 0x58c,r13        ; r13 = reset_vector_addr (0x06C8)
 *
 *   ; Check if we should attempt watchdog recovery
 *   0x51A: mov r14,r0             ; r0 = recovered flag
 *   0x51C: cmp/eq #1,r0           ; recovered == 1?
 *   0x51E: bf  0x562              ; if not, skip recovery
 *
 *   ; Watchdog recovery path (r14 == 1):
 *   0x520: mov.l 0x5a4,r4         ; r4 = 0x7FFFC
 *   0x522: mov.w 0x58e,r14        ; r14 = 0x1000 (alternate location offset?)
 *   0x524: mov.l @r4,r0           ; r0 = *(uint32_t*)0x7FFFC
 *   0x526: cmp/eq #-1,r0          ; == 0xFFFFFFFF?
 *   0x528: bt  0x532              ; if yes, check alternate
 *   0x52A: mov.l @r4,r0           ; r0 = *(uint32_t*)0x7FFFC (reload)
 *   0x52C: mov.l @r0,r0           ; r0 = **0x7FFFC
 *   0x52E: cmp/eq #-1,r0          ; == 0xFFFFFFFF?
 *   0x530: bf  0x546              ; if not, skip to alternate check
 *
 *   ; Read from alternate location
 *   0x532: bsr 0x5b0              ; call checkWatchdog(7) again
 *   0x534: mov #7,r4
 *   0x536: mov r0,r4
 *   0x538: tst r4,r4
 *   0x53A: bt  0x560              ; if watchdog OK, skip
 *   0x53C: mov.l @r14,r0          ; r0 = *(uint32_t*)0x1000
 *   0x53E: cmp/eq #-1,r0          ; == 0xFFFFFFFF?
 *   0x540: bt  0x532              ; if yes, retry watchdog check
 *   0x542: bra 0x54c              ; goto alternate_ok
 *   0x544: nop
 *
 *   ; Alternate location check
 *   0x546: mov.l @r14,r0          ; r0 = *(uint32_t*)0x1000
 *   0x548: cmp/eq #-1,r0          ; == 0xFFFFFFFF?
 *   0x54A: bt  0x550              ; if yes, skip
 *   0x54C: bra 0x562              ; goto finish
 *   0x54E: mov.l @r14,r13         ; r13 = *(uint32_t*)0x1000 (delay slot)
 *   0x550: mov.l 0x5a8,r2         ; r2 = 0x7FFF8
 *   0x552: bra 0x562              ; goto finish
 *   0x554: mov.l @r2,r13          ; r13 = *(uint32_t*)0x7FFF8 (delay slot)
 *
 *   ; Warm start path (r4 was non-zero)
 *   0x556: mov.b @r15,r1          ; r1 = saved reset reason
 *   0x558: mov.w 0x590,r3         ; r3 = 0xDFA8 (some addr)
 *   0x55A: mov.w 0x592,r2         ; r2 = 0x08F6 (gpio_init?)
 *   0x55C: jsr @r2                ; call r2 with params
 *   0x55E: mov.b r1,@r3           ; *(uint8_t*)0xDFA8 = reason
 *
 *   ; Finish (common path)
 *   0x560: mov.w 0x58c,r13        ; r13 = 0x06C8 (default reset vector)
 *   0x562: mov.l 0x59c,r3         ; r3 = MAGIC_VALUE = 0x5AA5A55A
 *   0x564: mov.l 0x5a0,r2         ; r2 = &magic_location
 *   0x566: mov.l r3,@r2           ; *(uint32_t*)0xFFFFDFFC = MAGIC_VALUE
 *   0x568: mov.w 0x594,r3         ; r3 = 0x0040 (vector_trampoline_set_sp)
 *   0x56A: jsr @r3                ; set SP = 0xFFFFDFA0, then jmp @r4 (tail jump)
 *   0x56C: mov r13,r4             ; r4 = r13 (delay slot) — chosen reset vector
 *
 *   ; Infinite loop (should not reach)
 *   0x56E: bra 0x56e              ; infinite loop
 *   0x570: nop
 *
 *   0x572: ... (resetWatchdog? subroutine — writes WDT magic 0x5A1F/0x5A00
 *          to SFR 0xEC12/0xEC10, then 0xA53C back to 0xEC10)
 *
 * Note: address 0x594 holds the value 0x0040 = vector_trampoline_set_sp:
 *   mov.l [0x48],r15  (SP = 0xFFFFDFA0)
 *   jmp @r4           (jump to the reset vector chosen below: 0x6C8 default,
 *                      [0x1000] = 0x12B4 app entry, or [0x7FFF8] = 0xD49C main entry)
 */
#include <stdint.h>

/* ------------------------------------------------------------------ */
/*  ROM data references                                                */
/* ------------------------------------------------------------------ */

/* Word tables: 16-bit absolute addresses of init functions */
#define HW_INIT_1_ADDR  (*(uint16_t *)0x586)   /* = 0x0170 */
#define HW_INIT_2_ADDR  (*(uint16_t *)0x588)   /* = 0x041C */
#define HW_INIT_3_ADDR  (*(uint16_t *)0x58A)   /* = 0x03D4 */
#define DEFAULT_RV_ADDR (*(uint16_t *)0x58C)   /* = 0x06C8 */
#define ALT_OFFSET      (*(uint16_t *)0x58E)   /* = 0x1000 */
#define REASON_ADDR     (*(uint16_t *)0x590)   /* = 0xDFA8 */
#define WARM_FN_ADDR    (*(uint16_t *)0x592)   /* = 0x08F6 */
#define BOOT_CONT_ADDR  (*(uint16_t *)0x594)   /* = 0x0040  (vector_trampoline_set_sp) */
#define WDT_RESET_ADDR  (0x572)                /* resetWatchdog? — verified bsr 0x572;
                                                *   literal @0x596 (=0x5A1F) is a WDT
                                                *   write magic, NOT a code address */

/* Longword constants */
#define MAGIC_VALUE         (*(uint32_t *)0x59C)   /* = 0x5AA5A55A */
#define MAGIC_LOCATION_PTR  (*(uint32_t *)0x5A0)   /* = 0xFFFFDFFC */
#define WDT_STATUS_ADDR     (*(uint32_t *)0x5A4)   /* = 0x0007FFFC */
#define WDT_STATUS_ALT      (*(uint32_t *)0x5A8)   /* = 0x0007FFF8 */

/* ------------------------------------------------------------------ */
/*  Function pointer types                                             */
/* ------------------------------------------------------------------ */

typedef void (*void_fn_void)(void);
typedef void (*void_fn_word)(uint16_t);
typedef void (*void_fn_byte)(uint8_t);

/* ------------------------------------------------------------------ */
/*  External declarations                                              */
/* ------------------------------------------------------------------ */

/**
 * checkWatchdogTimer_OVRCOUNT  —  Check if the watchdog timer overflowed.
 * @param count  Number of times to test (retry count)
 * @return  Non-zero if watchdog overflow detected, 0 otherwise.
 * Defined at ROM 0x5B0.
 */
extern int checkWatchdogTimer_OVRCOUNT(int count);

/* ------------------------------------------------------------------ */
/*  Reset handler                                                      */
/* ------------------------------------------------------------------ */

/**
 * reset_handler  —  Main reset entry point.
 *
 * Called from Manual_Reset after BSC and GPIO init.  Determines whether
 * this is a cold start (full init) or warm start (recovery), runs the
 * hardware initialization sequence, checks the watchdog for overflow,
 * and finally stores the magic "boot OK" value before jumping to the
 * next boot stage.
 *
 * @param cold_start  0 = cold start (full initialization)
 *                    1 = warm start (skip some checks)
 * @param reason      Reset reason byte (e.g. from RSTSRC register)
 *
 * @return This function does not return — it either jumps to the boot
 *         continuation or infinite-loops on catastrophic failure.
 */
__attribute__((noreturn))
void reset_handler(int cold_start, uint8_t reason)
{
    int recovered = 1;        /* r14: default "recovered" flag */
    uint32_t rv = DEFAULT_RV_ADDR;  /* r13: reset vector, passed to boot continuation */

    /* ------------------------------------------------------------------ */
    /*  Step 1: Reset the watchdog timer                                  */
    /* ------------------------------------------------------------------ */

    {
        void_fn_void fn = (void_fn_void)(uintptr_t)WDT_RESET_ADDR;
        fn();                           /* resetWatchdog() */
    }

    /* ------------------------------------------------------------------ */
    /*  Step 2: Hardware initialization                                   */
    /* ------------------------------------------------------------------ */

    {
        void_fn_void hw1 = (void_fn_void)(uintptr_t)(uint16_t)HW_INIT_1_ADDR;
        void_fn_void hw2 = (void_fn_void)(uintptr_t)(uint16_t)HW_INIT_2_ADDR;
        void_fn_void hw3 = (void_fn_void)(uintptr_t)(uint16_t)HW_INIT_3_ADDR;
        hw1();      /* Clock/PLL init */
        hw2();      /* BSC/memory controller init */
        hw3();      /* Peripheral init */
    }

    /* ------------------------------------------------------------------ */
    /*  Step 3: Cold start detection                                      */
    /* ------------------------------------------------------------------ */

    if (cold_start == 0) {
        /* Cold start: check the magic value at 0xFFFFDFFC.
         * If it does not match 0x5AA5A55A, this might be a
         * watchdog-induced reset. */
        volatile uint32_t *magic_loc = (volatile uint32_t *)(uintptr_t)MAGIC_LOCATION_PTR;

        if (*magic_loc != MAGIC_VALUE) {
            /* Magic mismatch — check if watchdog caused the reset */
            int wdt_ovf = checkWatchdogTimer_OVRCOUNT(7);  /* bsr 0x5B0 */
            if (wdt_ovf == 0) {
                /* No watchdog overflow — this is a genuine cold start */
                recovered = 0;
            }
        }
    }

    /* ------------------------------------------------------------------ */
    /*  Step 4: Watchdog recovery check                                   */
    /* ------------------------------------------------------------------ */

    if (recovered == 1) {
        /* Warm start or watchdog recovery: check reset cause
         * by reading from 0x7FFFC and 0x7FFF8. */
        volatile uint32_t *wdt_status = (volatile uint32_t *)(uintptr_t)WDT_STATUS_ADDR;
        volatile uint32_t *alt_status  = (volatile uint32_t *)(uintptr_t)WDT_STATUS_ALT;

        uint32_t val = *wdt_status;

        if (val == 0xFFFFFFFF) {
            /* Try reading the alternate source */
            val = *wdt_status;           /* reload */
            val = *(volatile uint32_t *)(uintptr_t)val;

            if (val == 0xFFFFFFFF) {
                /* Alternate read also invalid — retry watchdog check
                 * and try the alternate address at 0x1000 */
                while (1) {
                    int wdt_ovf2 = checkWatchdogTimer_OVRCOUNT(7);
                    if (wdt_ovf2 != 0) {
                        break;          /* watchdog overflowed — OK */
                    }
                    uint32_t alt_val = *(volatile uint32_t *)(uintptr_t)(uint16_t)ALT_OFFSET;
                    if (alt_val != 0xFFFFFFFF) {
                        rv = alt_val;
                        break;
                    }
                }
            } else {
                /* Value read from 0x7FFC is valid,
                 * but we also need the alternate check */
                uint32_t alt_val = *(volatile uint32_t *)(uintptr_t)(uint16_t)ALT_OFFSET;
                if (alt_val != 0xFFFFFFFF) {
                    rv = alt_val;
                } else {
                    rv = *alt_status;   /* read from 0x7FFF8 */
                }
            }
        } else {
            /* Direct value from 0x7FFFC was not 0xFFFFFFFF,
             * but we should also check if the alternate location
             * holds a valid reset vector */
            uint32_t alt_val = *(volatile uint32_t *)(uintptr_t)(uint16_t)ALT_OFFSET;
            if (alt_val == 0xFFFFFFFF) {
                rv = *alt_status;       /* read from 0x7FFF8 */
            } else {
                rv = alt_val;
            }
        }

        /* The reset vector determined from recovery logic is in r13.
         * It is passed to the boot continuation. */
        goto finish;
    } else {
        /* Cold start: write the reason byte to a known location */
        volatile uint8_t *reason_store = (volatile uint8_t *)(uintptr_t)(uint16_t)REASON_ADDR;
        *reason_store = reason;

        rv = DEFAULT_RV_ADDR;           /* r13 = default reset vector */
    }
finish:
    /* ------------------------------------------------------------------ */
    /*  Step 5: Store magic value and jump to boot continuation           */
    /* ------------------------------------------------------------------ */

    {
        volatile uint32_t *magic_loc = (volatile uint32_t *)(uintptr_t)MAGIC_LOCATION_PTR;
        *magic_loc = MAGIC_VALUE;       /* Mark boot as valid */
    }

    /* Jump to boot continuation */
    {
        void_fn_word boot_fn = (void_fn_word)(uintptr_t)(uint16_t)BOOT_CONT_ADDR;
        boot_fn((uint16_t)rv);          /* pass reset vector as parameter */
    }

    /* ------------------------------------------------------------------ */
    /*  Step 6: Infinite loop (safety — should not reach)                 */
    /* ------------------------------------------------------------------ */

    while (1) {
        /* wait for watchdog reset */
    }
}
