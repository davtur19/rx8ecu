/*
 * boot.h — RX-8 ECU Boot Sequence Definitions
 *
 * Boot chain: Reset vector (0x0) -> Manual_Reset (0x8B8)
 *   -> bsc_init (0x8CC) -> gpio_init (0x8F6)
 *   -> resetHandler/main_init (0x4E0)
 *   -> wdt_init (0x572) -> hw_init_1 (0x170) -> hw_init_2 (0x41C)
 *   -> hw_init_3 (0x3D4)
 *   -> checkWatchdogTimer_OVRCOUNT (0x5B0)
 *   -> vector_trampoline_set_sp (0x40): SP=0xFFFFDFA0
 *   -> secondary_boot_main (0xA038)
 *
 * Source: rtos_analysis_report.txt, reset_handler.c, boot_entry.c
 */

#ifndef BOOT_H
#define BOOT_H

#include <stdint.h>

/* ====================================================================== */
/*  Boot Sequence Function Addresses (ROM)                                */
/* ====================================================================== */

/* Phase 1: Reset vector and early hardware */
#define ADDR_MANUAL_RESET       0x8B8   /* Manual_Reset entry point */
#define ADDR_BSC_INIT           0x8CC   /* Bus State Controller init */
#define ADDR_GPIO_INIT          0x8F6   /* GPIO port configuration */

/* Phase 2: Main reset handler and hardware init */
#define ADDR_RESET_HANDLER      0x4E0   /* resetHandler / main_init */
#define ADDR_WDT_INIT           0x572   /* Watchdog timer init */
#define ADDR_HW_INIT_1          0x170   /* Clock/PLL/SPI init */
#define ADDR_HW_INIT_2          0x41C   /* Memory controller / EEPROM buf init */
#define ADDR_HW_INIT_3          0x3D4   /* Peripheral init / task queue ptrs */

/* Phase 3: Watchdog check and vector trampoline */
#define ADDR_CHECK_WDT_OVR      0x5B0   /* checkWatchdogTimer_OVRCOUNT */
#define ADDR_VECTOR_TRAMP       0x40    /* vector_trampoline_set_sp: SP=0xFFFFDFA0 */

/* Phase 4: Secondary boot and RTOS */
#define ADDR_SECONDARY_BOOT     0xA038  /* secondary_boot_main */
#define ADDR_PERIPH_CHAIN_A     0x4C80  /* peripheral_init_chain_A */
#define ADDR_PERIPH_INIT_SEC    0xD7B0  /* secondary_peripheral_initializer */
#define ADDR_SFR_DMA_INIT       0x4CF8  /* sfr_init_dma_channels */
#define ADDR_TASK_CTX_SWITCH    0x3AD8  /* task_context_switch: START RTOS */

/* ====================================================================== */
/*  Hardware Register Values (from analysis)                               */
/* ====================================================================== */

/* WDT register values */
#define WDT_RSTCSR_VALUE    0x5A1F  /* Magic to acknowledge WDT reset */
#define WDT_TCSR_VALUE      0x5A00  /* Magic to clear WDT timer */
#define WDT_FEED_VALUE      0xA53C  /* Feed value to stop WDT */

/* SPI initial state (hw_init_1 at 0x170) */
#define SPI_CLK_HIGH        0x01    /* Clock bit set */
#define SPI_CLK_LOW         0x00    /* Clock bit cleared */

/* ====================================================================== */
/*  Boot Function Prototypes                                              */
/* ====================================================================== */

/**
 * Manual_Reset — Initial reset entry point.
 * ROM address: 0x8B8
 * Calls: bsc_init(0x8CC), gpio_init(0x8F6)
 * Then jumps to reset_handler(0x4E0)
 */
void Manual_Reset(void);

/**
 * bsc_init — Bus State Controller initialization.
 * ROM address: 0x8CC
 * Configures memory bus timing and wait states.
 */
void bsc_init(void);

/**
 * gpio_init — GPIO port configuration.
 * ROM address: 0x8F6
 * Configures port function registers (PFC) for all ports.
 * Sets port direction, function select, and pull-up enables.
 * Writes to registers at 0xFFFFF720-0xFFFFF778.
 */
void gpio_init(void);

/**
 * reset_handler — Main reset and hardware initialization.
 * ROM address: 0x4E0
 * @param cold_start  0 = cold start (full init), non-zero = warm start
 * @param reason      Reset reason byte
 *
 * Calls: wdt_init(0x572), hw_init_1(0x170), hw_init_2(0x41C), hw_init_3(0x3D4)
 * Checks warm boot magic (0x5AA5A55A) at 0xFFFFDFFC.
 * Jumps to vector_trampoline_set_sp (0x40) with chosen reset vector.
 */
void reset_handler(int cold_start, uint8_t reason);

/**
 * wdt_init — Watchdog timer initialization.
 * ROM address: 0x572
 * Writes WDT_RSTCSR = 0x5A1F, WDT_TCSR = 0x5A00, then feeds 0xA53C.
 */
void wdt_init(void);

/**
 * hw_init_1 — Clock, PLL, and SPI initialization.
 * ROM address: 0x170
 * Calls spi_set_clk_high_wait, configures SPI registers,
 * calls atu_configure_io_channel, then spi_set_clk_low_wait.
 */
void hw_init_1(void);

/**
 * hw_init_2 — Memory controller and EEPROM buffer initialization.
 * ROM address: 0x41C
 * Clears EEPROM RAM buffer at 0xFFFFDFE4 (8 bytes).
 * Sets sync byte 0xAA at 0xFFFFDFF8.
 * Clears remaining buffer bytes.
 */
void hw_init_2(void);

/**
 * hw_init_3 — Peripheral and task queue pointer initialization.
 * ROM address: 0x3D4
 * Sets task queue write index (0xFFFFDFB4) = 0.
 * Sets task queue read index (0xFFFFDFB6) = 0.
 */
void hw_init_3(void);

/**
 * checkWatchdogTimer_OVRCOUNT — Check if watchdog timer overflowed.
 * ROM address: 0x5B0
 * @param count  Number of times to test (retry count)
 * @return Non-zero if watchdog overflow detected, 0 otherwise.
 */
int checkWatchdogTimer_OVRCOUNT(int count);

/**
 * vector_trampoline_set_sp — Set SP and jump to reset vector.
 * ROM address: 0x40
 * Sets SP = 0xFFFFDFA0, then jumps to the address in r4.
 * @param reset_vector  Address to jump to after setting SP.
 */
void vector_trampoline_set_sp(uint32_t reset_vector);

#endif /* BOOT_H */
