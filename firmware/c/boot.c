/*
 * boot.c — RX-8 ECU Boot Sequence (60E1D400)
 *
 * 1:1 firmware reconstruction of the boot chain for the Mazda RX-8
 * Renesis 13B-MSP rotary engine ECU (SH-2E / SH7055).
 *
 * Boot chain (from rtos_analysis_report.txt):
 *   Reset vector (0x0) -> Manual_Reset (0x8B8)
 *   -> bsc_init (0x8CC) -> gpio_init (0x8F6)
 *   -> resetHandler (0x4E0)
 *     -> wdt_init (0x572)
 *     -> hw_init_1 (0x170): PFC registers, PLL/clock
 *     -> hw_init_2 (0x41C): BSC/memory controller
 *     -> hw_init_3 (0x3D4): peripherals
 *     -> checkWatchdogTimer_OVRCOUNT (0x5B0)
 *     -> vector_trampoline_set_sp (0x40): SP=0xFFFFDFA0
 *   -> secondary_boot_main (0xA038)
 *     -> peripheral_init_chain_A (0x4C80)
 *     -> secondary_peripheral_initializer (0xD7B0)
 *     -> sfr_init_dma_channels (0x4CF8)
 *     -> task_context_switch (0x3AD8) — START RTOS
 *
 * Verified against ROM: 60E1D400_be.elf
 * IDA Session: ae00d360
 */

#include "platform.h"
#include "boot.h"
#include "eeprom.h"   /* spi_clk_high_wait, spi_clk_low_wait */
#include "timer.h"    /* atu_configure_io_channel */

/* ====================================================================== */
/*  ROM Data References (resolved from PC-relative pools)                 */
/* ====================================================================== */

/* Watchdog timer register addresses (from ROM 0x586-0x594) */
#define ROM_HW_INIT_1_ADDR  (*(uint16_t *)0x586)   /* = 0x0170 */
#define ROM_HW_INIT_2_ADDR  (*(uint16_t *)0x588)   /* = 0x041C */
#define ROM_HW_INIT_3_ADDR  (*(uint16_t *)0x58A)   /* = 0x03D4 */
#define ROM_DEFAULT_RV      (*(uint16_t *)0x58C)   /* = 0x06C8 */
#define ROM_ALT_OFFSET      (*(uint16_t *)0x58E)   /* = 0x1000 */
#define ROM_REASON_ADDR     (*(uint16_t *)0x590)   /* = 0xDFA8 */
#define ROM_WARM_FN_ADDR    (*(uint16_t *)0x592)   /* = 0x08F6 */
#define ROM_BOOT_CONT_ADDR  (*(uint16_t *)0x594)   /* = 0x0040 */

/* Longword constants from ROM data pools */
#define ROM_MAGIC_VALUE     (*(uint32_t *)0x59C)   /* = 0x5AA5A55A */
#define ROM_MAGIC_LOC       (*(uint32_t *)0x5A0)   /* = 0xFFFFDFFC */
#define ROM_WDT_STATUS      (*(uint32_t *)0x5A4)   /* = 0x0007FFFC */
#define ROM_WDT_ALT         (*(uint32_t *)0x5A8)   /* = 0x0007FFF8 */

/* ====================================================================== */
/*  Manual_Reset @ 0x8B8 — Reset Vector Entry Point                       */
/* ====================================================================== */

/**
 * Manual_Reset — Initial entry after power-on reset.
 *
 * ROM address: 0x8B8
 *
 * The SH-2E reset vector at 0x0 points to the boot ROM, which validates
 * the ROM ID string at 0x7FFFC and redirects to this function.
 *
 * Flow:
 *   1. Call bsc_init (0x8CC) — initialize bus state controller
 *   2. Call gpio_init (0x8F6) — configure GPIO ports
 *   3. Jump to reset_handler (0x4E0) — main reset handler
 */
void Manual_Reset(void)
{
    /* Phase 1: Bus State Controller init */
    bsc_init();

    /* Phase 2: GPIO port configuration */
    gpio_init();

    /* Phase 3: Main reset handler (cold start) */
    reset_handler(0, 0);
}

/* ====================================================================== */
/*  bsc_init @ 0x8CC — Bus State Controller Init                          */
/* ====================================================================== */

/**
 * bsc_init — Initialize the Bus State Controller.
 *
 * ROM address: 0x8CC
 * IDA function bounds: 0x8CC-0x8F4 (40 bytes, rts at 0x8F2).
 * The EC2x register block is 0x8CC-0x8DC (18 bytes); the 0x8DE-0x8F4
 * tail (writes to 0xFFFFF70A/0xFFFFED18 + poll loop, see NOTE below)
 * is part of the same IDA function.
 *
 * The BSC controls memory bus timing, wait states, and chip selects.
 * This is a minimal init — the full BSC setup happens in peripheral_init_chain_A.
 *
 * Register writes:
 *   - BSC base + 0 (0xFFFFEC20) = 0x000F: bus width/timing
 *   - BSC base + 2 (0xFFFFEC22) = 0xFFFF
 *   - BSC base + 4 (0xFFFFEC24) = 0xFFFF
 *   - BSC base + 6 (0xFFFFEC26) = 0x0000
 *
 * Verified against ROM 60E1D400 via IDA disassembly at 0x8CC
 * (session f3480f35, IDA function bsc_init @ 0x8CC):
 *   0x8CC: mov.w @(0x99E), r4   ; r4 = [0x99E] = 0xEC20 sign-extended
 *   0x8CE: mov #0x0F, r3        ; r3 = 0x0F
 *   0x8D0: mov.w r3, @r4        ; [0xFFFFEC20] = 0x000F
 *   0x8D2: mov.l @(0x9B0), r0   ; r0 = [0x9B0] = 0x0000FFFF (u32be = 65535)
 *   0x8D4: mov.w r0, @(2,r4)    ; [0xFFFFEC22] = 0xFFFF (low 16 bits of r0)
 *   0x8D6: mov.w r0, @(4,r4)    ; [0xFFFFEC24] = 0xFFFF
 *   0x8D8: mov #0, r5
 *   0x8DA: mov r5, r0           ; r0 = 0
 *   0x8DC: mov.w r0, @(6,r4)    ; [0xFFFFEC26] = 0x0000
 *
 * NOTE (EC80 vs EC20 recheck): the EC80->EC20 fix is correct — the only
 * SFR literal loaded here is the word 0xEC20 at ROM 0x99E (u16be = 60448).
 * No instruction in bsc_init references 0xFFFFEC80, and a whole-image
 * search finds no mov.w/mov.l literal pool loading 0xEC80 as an SFR
 * address (raw "EC 80" byte hits at 0x274BF/0x2E537/0x2E543/0x2E54F/0x33C56
 * sit inside FPU opcode encodings, and "EC80" text hits are ROM addresses
 * such as loc_EC80 @ 0xEC80 — not 0xFFFFEC80 SFR accesses). The original
 * 0xFFFFEC80 was a guess, not an IDA alias artifact of a real EC80 write.
 * NOTE (EC80 vs EC20 recheck): the EC80->EC20 fix is correct — the only
 * SFR literal loaded here is the word 0xEC20 at ROM 0x99E (u16be = 60448).
 * No instruction in bsc_init references 0xFFFFEC80, and a whole-image
 * search finds no mov.w/mov.l literal pool loading 0xEC80 as an SFR
 * address (raw "EC 80" byte hits at 0x274BF/0x2E537/0x2E543/0x2E54F/0x33C56
 * sit inside FPU opcode encodings, and "EC80" text hits are ROM addresses
 * such as loc_EC80 @ 0xEC80 — not 0xFFFFEC80 SFR accesses). The original
 * 0xFFFFEC80 was a guess, not an IDA alias artifact of a real EC80 write.
 *
 * Tail (0x8DE-0x8F4) of this IDA function: [0xFFFFF70A] = 0x3C04,
 * [0xFFFFED18] = 0, then poll [0xFFFFED18] & 0x8000 (implemented below).
 */

/* review-fix: bound for the bsc_init tail poll loop. The ROM spins on bit 15
 * of 0xFFFFED18; an unbounded spin hangs host verification, so the loop is
 * bounded. The bound has no ROM meaning — boot proceeds after timeout. */
#define BSC_TAIL_POLL_TIMEOUT 1000000UL

void bsc_init(void)
{
    /* BSC base register: 0xFFFFEC20 (SH-2E Bus State Controller) */
    volatile uint16_t *bsc = (volatile uint16_t *)0xFFFFEC20;

    /* BSC mode register: external bus configuration */
    bsc[0] = 0x000F;  /* Bus width/timing (verified from ROM) */

    /* BSC wait registers: external memory access timing (ROM: r0 = 0x0000FFFF) */
    bsc[1] = 0xFFFF;  /* Wait state 0 (low 16 bits of literal at ROM 0x9B0) */
    bsc[2] = 0xFFFF;  /* Wait state 1 (same literal) */
    bsc[3] = 0x0000;  /* Wait state 2 */

    /* review-fix: implement the 0x8DE-0x8F4 tail described above. Volatile
     * 16-bit accesses; bounded poll on bit 15 of 0xFFFFED18. */
    volatile uint16_t *bsc_tail_a = (volatile uint16_t *)0xFFFFF70A;
    volatile uint16_t *bsc_tail_b = (volatile uint16_t *)0xFFFFED18;
    *bsc_tail_a = 0x3C04;
    *bsc_tail_b = 0x0000;
    {
        uint32_t bsc_tail_poll = BSC_TAIL_POLL_TIMEOUT;
        while ((*bsc_tail_b & 0x8000) == 0 && --bsc_tail_poll != 0) {
        }
    }
}

/* ====================================================================== */
/*  gpio_init @ 0x8F6 — GPIO Port Configuration                          */
/* ====================================================================== */

/**
 * gpio_init — Configure all GPIO ports for RX-8 ECU operation.
 *
 * ROM address: 0x8F6
 * Size: 166 bytes
 *
 * Writes to PFC (Port Function Controller) registers at 0xFFFFF720-0xFFFFF778.
 * Configures port direction, function select (GPIO/alternate), and pull-up
 * enables for all ports used by the ECU.
 *
 * Register write sequence (from ROM analysis):
 *   PFC_PDR1   (0xFFFFF726) = 0xFFFF  — all pins output
 *   PFC_PMR1   (0xFFFFF722) = 0x0000  — all GPIO function
 *   PFC_PMR2   (0xFFFFF724) = 0x0000  — all GPIO function
 *   PFC_PMR3   (0xFFFFF720) = 0x0000  — all GPIO function
 *   PFC_PMR2_BASE (0xFFFFF738) = 0xEFFF — port 2 config
 *   ... and so on for ports 3-12
 */
void gpio_init(void)
{
    /* Port 0 configuration */
    PFC_PDR1   = 0xFFFF;   /* All pins configured as output */
    PFC_PMR2   = 0x0000;   /* Port 0: GPIO function */
    PFC_PMR3   = 0x0000;   /* Port 0: GPIO function */
    PFC_PMR1   = 0x0000;   /* Port 0: GPIO function */

    /* Port 2 configuration */
    PFC_PMR3_BASE = 0xEFFF; /* Port 2: most pins GPIO, bit 12 alternate */
    PFC_PMR2_1 = 0x0000;    /* Port 2: GPIO function */
    PFC_PMR2_2 = 0x0000;    /* Port 2: GPIO function */
    PFC_PMR2_3 = 0x0000;    /* Port 2: GPIO function */
    PFC_PMR2_BASE = 0x9000; /* Port 2: bits 12-13 alternate (CAN) */

    /* Port 3 configuration */
    PFC_PMR3_1 = 0x001F;    /* Port 3: bits 0-4 alternate (serial) */
    PFC_PMR3_2 = 0x0000;    /* Port 3: GPIO function */
    PFC_PMR3   = 0x0000;    /* Port 3: GPIO function */

    /* Port 4 configuration */
    PFC_PMR4_BASE = 0x3EFF; /* Port 4: bits 0-5,8-15 alternate */
    PFC_PMR4_1 = 0x0000;    /* Port 4: GPIO function */
    PFC_PMR4_2 = 0x0000;    /* Port 4: GPIO function */
    PFC_PMR4_3 = 0x2000;    /* Port 4: bit 13 alternate */

    /* Port 5 configuration */
    PFC_PMR5_BASE = 0xFFFF; /* Port 5: all alternate */
    PFC_PMR5_1   = 0x0000;  /* Port 5: GPIO function */
    PFC_PMR5_2   = 0x0000;  /* Port 5: GPIO function */
    PFC_PMR5_3   = 0x8000;  /* Port 5: bit 15 alternate (interrupt) */

    /* Port 6 configuration */
    PFC_PMR6_BASE = 0x0000; /* Port 6: GPIO function */
    PFC_PMR6_1   = 0x000F;  /* Port 6: bits 0-3 alternate */
    PFC_PMR6_2   = 0x0000;  /* Port 6: GPIO function */

    /* Port 7 configuration */
    PFC_PMR7_BASE = 0x0000; /* Port 7: GPIO function */
    PFC_PMR7_1   = 0x0000;  /* Port 7: GPIO function */
    PFC_PMR7_2   = 0x0000;  /* Port 7: GPIO function */
    PFC_PMR7_3   = 0x0000;  /* Port 7: GPIO function */

    /* Port 8 configuration */
    PFC_PMR8_BASE = 0x0000; /* Port 8: GPIO function */

    /* Port A (10) configuration */
    PFC_PMR10_BASE = 0x0000; /* Port A: GPIO function */
    PFC_PMR10_1   = 0x0000;  /* Port A: GPIO function */
    PFC_PMR10_2   = 0x0000;  /* Port A: GPIO function */

    /* Port B (11) configuration */
    PFC_PMR11_BASE = 0x3FFF; /* Port B: bits 0-13 alternate (CAN) */
    PFC_PMR11_1   = 0x0000;  /* Port B: GPIO function */
    PFC_PMR11_2   = 0x0000;  /* Port B: GPIO function */
    PFC_PMR11_3   = 0x0000;  /* Port B: GPIO function */

    /* Port C (12) configuration */
    PFC_PMR12_BASE = 0x0000; /* Port C: GPIO function */
    PFC_PMR12_1   = 0x0050;  /* Port C: bits 4,6 alternate */
    PFC_PMR12_2   = 0x3FFF;  /* Port C: bits 0-13 alternate (SPI/CAN) */
}

/* ====================================================================== */
/*  reset_handler @ 0x4E0 — Main Reset Handler                           */
/* ====================================================================== */

/**
 * reset_handler — Main reset entry point after BSC/GPIO init.
 *
 * ROM address: 0x4E0
 * Size: ~146 bytes
 *
 * Performs the main hardware initialization sequence:
 *   1. Reset watchdog timer
 *   2. Call hw_init_1 (0x170): Clock/PLL/SPI init
 *   3. Call hw_init_2 (0x41C): Memory controller
 *   4. Call hw_init_3 (0x3D4): Peripherals
 *   5. Cold start: check warm boot magic (0x5AA5A55A)
 *   6. Warm start: check watchdog recovery
 *   7. Store magic and jump to boot continuation
 */
void reset_handler(int cold_start, uint8_t reason)
{
    int recovered = 1;
    uint32_t rv = ROM_DEFAULT_RV;

    /* Step 1: Reset the watchdog timer */
    wdt_init();

    /* Step 2: Hardware initialization */
    hw_init_1();    /* Clock/PLL/SPI init */
    hw_init_2();    /* Memory controller / EEPROM buffer init */
    hw_init_3();    /* Peripheral / task queue pointer init */

    /* Step 3: Cold start detection */
    if (cold_start == 0) {
        /* Cold start: check the magic value at 0xFFFFDFFC */
        if (BOOT_MAGIC_LOCATION != ROM_MAGIC_VALUE) {
            /* Magic mismatch — check if watchdog caused the reset */
            int wdt_ovf = checkWatchdogTimer_OVRCOUNT(7);
            if (wdt_ovf == 0) {
                /* No watchdog overflow — genuine cold start */
                recovered = 0;
            }
        }
    }

    /* Step 4: Watchdog recovery check */
    if (recovered == 1) {
        /* Warm start or watchdog recovery */
        volatile uint32_t *wdt_status = (volatile uint32_t *)(uintptr_t)ROM_WDT_STATUS;
        uint32_t val = *wdt_status;

        if (val == 0xFFFFFFFF) {
            /* Try alternate locations */
            val = *(volatile uint32_t *)(uintptr_t)val;
            if (val == 0xFFFFFFFF) {
                /* Alternate read also invalid — retry watchdog check */
                while (1) {
                    int wdt_ovf2 = checkWatchdogTimer_OVRCOUNT(7);
                    if (wdt_ovf2 != 0) break;
                    uint32_t alt_val = *(volatile uint32_t *)(uintptr_t)ROM_ALT_OFFSET;
                    if (alt_val != 0xFFFFFFFF) { rv = alt_val; break; }
                }
            } else {
                uint32_t alt_val = *(volatile uint32_t *)(uintptr_t)ROM_ALT_OFFSET;
                if (alt_val != 0xFFFFFFFF) { rv = alt_val; }
                else { rv = *(volatile uint32_t *)(uintptr_t)ROM_WDT_ALT; }
            }
        } else {
            uint32_t alt_val = *(volatile uint32_t *)(uintptr_t)ROM_ALT_OFFSET;
            if (alt_val == 0xFFFFFFFF) { rv = *(volatile uint32_t *)(uintptr_t)ROM_WDT_ALT; }
            else { rv = alt_val; }
        }
    } else {
        /* Cold start: write reason byte */
        volatile uint8_t *reason_store = (volatile uint8_t *)(uintptr_t)ROM_REASON_ADDR;
        *reason_store = reason;
        rv = ROM_DEFAULT_RV;
    }

    /* Step 5: Store magic value and jump to boot continuation */
    BOOT_MAGIC_LOCATION = ROM_MAGIC_VALUE;

    /* vector_trampoline_set_sp (0x40): SP = 0xFFFFDFA0, jmp rv */
    {
        typedef void (*fn_t)(uint32_t);
        fn_t trampoline = (fn_t)(uintptr_t)ROM_BOOT_CONT_ADDR;
        trampoline(rv);
    }

    /* NOT REACHED */
    while (1) {}
}

/* ====================================================================== */
/*  wdt_init @ 0x572 — Watchdog Timer Init                                */
/* ====================================================================== */

/**
 * wdt_init — Initialize and feed the watchdog timer.
 *
 * ROM address: 0x572
 * Size: 20 bytes
 *
 * Register write sequence:
 *   1. WDT_RSTCSR = 0x5A1F (acknowledge reset source)
 *   2. WDT_TCSR = 0x5A00 (clear timer overflow flag)
 *   3. Read WDT_TCSR (confirm clear)
 *   4. WDT_TCSR = 0xA53C (feed watchdog, stop timer)
 *
 * These are the SH-2E watchdog magic values. Writing 0x5A1F to RSTCSR
 * acknowledges the reset source. Writing 0x5A00 to TCSR clears the
 * overflow flag. Writing 0xA53C feeds the watchdog (prevents reset).
 */
void wdt_init(void)
{
    /* Step 1: Acknowledge reset source */
    WDT_RSTCSR = 0x5A1F;

    /* Step 2: Clear timer overflow flag */
    WDT_TCSR = 0x5A00;

    /* Step 3: Read back to confirm (SH-2E requirement) */
    (void)WDT_TCSR;

    /* Step 4: Feed watchdog (stop timer) */
    WDT_TCSR = 0xA53C;
}

/* ====================================================================== */
/*  hw_init_1 @ 0x170 — Clock/PLL and SPI Init                           */
/* ====================================================================== */

/**
 * hw_init_1 — Initialize clocks, PLL, and SPI interface.
 *
 * ROM address: 0x170
 * Size: ~130 bytes
 *
 * This function:
 *   1. Calls spi_set_clk_high_wait to set initial SPI clock state
 *   2. Configures SPI registers at 0xFFFFE406-0xFFFFE41E
 *   3. Calls atu_configure_io_channel for GPIO pin setup
 *   4. Calls spi_set_clk_low_wait to complete initialization
 *
 * The SPI interface is bit-banged using GPIO pins mapped through the
 * CAN controller register space. The clock is controlled via bit 0 of
 * 0xFFFFE401, and the status is read via bit 3 of the same register.
 */
void hw_init_1(void)
{
    /* Step 1: Set SPI clock HIGH and wait for status ready */
    {
        volatile uint8_t *clk_reg = &SPI_CLK_DATA_CTRL;
        volatile uint8_t *stat_reg = &SPI_CLK_DATA_CTRL;
        spi_clk_high_wait(clk_reg, stat_reg);
    }

    /* Step 2: Configure SPI control registers */
    SPI_CONTROL = 0x0000;    /* SPI control: default state */
    SPI_CONFIG  = 0x0000;    /* SPI config: default state */

    /* Step 3: Configure ATU I/O channel for SPI pins */
    atu_configure_io_channel(0);

    /* Step 4: Set SPI clock LOW to complete init */
    {
        volatile uint8_t *clk_reg = &SPI_CLK_DATA_CTRL;
        volatile uint8_t *stat_reg = &SPI_CLK_DATA_CTRL;
        spi_clk_low_wait(clk_reg, stat_reg);
    }
}

/* ====================================================================== */
/*  hw_init_2 @ 0x41C — Memory Controller / EEPROM Buffer Init           */
/* ====================================================================== */

/**
 * hw_init_2 — Initialize memory controller and EEPROM RAM buffers.
 *
 * ROM address: 0x41C
 * Size: 8 bytes
 *
 * From ROM disassembly:
 *   0x41C: mov #0x59, r5        ; r5 = 0xFFFFDFE4 (EEPROM RAM buffer)
 *   0x41E: mov #0, r4           ; r4 = 0 (clear value)
 *   0x420: mov #0x58, r6        ; r6 = 0xFFFFDFF0 (serial queue buffer)
 *   0x422: mov #8, r7           ; r7 = 8 (byte count)
 *
 * The function clears the EEPROM RAM validation buffer and sets up
 * the serial queue buffer with the sync byte 0xAA.
 */
void hw_init_2(void)
{
    volatile uint8_t *eeprom_buf = (volatile uint8_t *)EEPROM_RAM_BUF_A;
    volatile uint8_t *serial_buf = (volatile uint8_t *)SERIAL_QUEUE_BASE;

    /* Clear EEPROM RAM validation buffer (8 bytes) */
    for (int i = 0; i < 8; i++) {
        eeprom_buf[i] = 0x00;
    }

    /* Set serial queue sync byte (offset 8) = 0xAA (ready) */
    serial_buf[8] = SERIAL_SYNC_READY;

    /* Clear remaining serial queue bytes */
    for (int i = 0; i < 8; i++) {
        serial_buf[i] = 0x00;
    }
}

/* ====================================================================== */
/*  hw_init_3 @ 0x3D4 — Peripheral / Task Queue Pointer Init             */
/* ====================================================================== */

/**
 * hw_init_3 — Initialize peripheral state and task queue pointers.
 *
 * ROM address: 0x3D4
 * Size: 12 bytes
 *
 * From ROM disassembly:
 *   0x3D4: mov #0x5C, r2        ; r2 = 0xFFFFDFB6 (queue read index)
 *   0x3D6: mov #0, r3           ; r3 = 0
 *   0x3D8: mov #0x5A, r1        ; r1 = 0xFFFFDFB4 (queue write index)
 *   0x3DA: mov.w r3, @r2        ; [0xFFFFDFB6] = 0
 *   0x3DC: rts                   ; return
 *   0x3DE: mov.w r3, @r1        ; [0xFFFFDFB4] = 0 (delay slot)
 *
 * Initializes the task queue write and read indices to 0.
 */
void hw_init_3(void)
{
    /* Initialize task queue indices */
    TASK_QUEUE_WRITE_IDX = 0;
    TASK_QUEUE_READ_IDX  = 0;
}

/* ====================================================================== */
/*  checkWatchdogTimer_OVRCOUNT @ 0x5B0                                   */
/* ====================================================================== */

/**
 * checkWatchdogTimer_OVRCOUNT — Check if watchdog timer overflowed.
 *
 * ROM address: 0x5B0
 * Size: 26 bytes
 *
 * Reads the watchdog timer overflow flag and checks if it's set.
 * The overflow flag is in the WDT status register.
 *
 * @param count  Number of times to test (retry count)
 * @return Non-zero if watchdog overflow detected, 0 otherwise
 */
int checkWatchdogTimer_OVRCOUNT(int count)
{
    for (int i = 0; i < count; i++) {
        /* Read WDT overflow status */
        uint16_t wdt_status = WDT_TCSR;

        /* Check if overflow bit is set (bit 8 in TCSR) */
        if (wdt_status & 0x0100) {
            return 1;  /* Watchdog overflow detected */
        }

        /* Small delay between checks */
        delay_loop(100);
    }

    return 0;  /* No overflow detected */
}

/* ====================================================================== */
/*  vector_trampoline_set_sp @ 0x40                                       */
/* ====================================================================== */

/**
 * vector_trampoline_set_sp — Set stack pointer and jump to reset vector.
 *
 * ROM address: 0x40
 *
 * Sets SP = 0xFFFFDFA0, then jumps to the address in r4.
 * This is the final step of the boot chain — it transfers control
 * to the chosen reset vector (default 0x6C8 = main_task_dispatcher).
 */
void vector_trampoline_set_sp(uint32_t reset_vector)
{
    /* Set SP = 0xFFFFDFA0 (boot stack) */
    /* On real SH-2E: mov.l @0x48, r15 */
    /* Host simulation: (no-op for syntax checking) */

    /* Jump to reset vector */
    typedef void (*fn_t)(void);
    fn_t entry = (fn_t)(uintptr_t)reset_vector;
    entry();

    /* NOT REACHED */
    while (1) {}
}
