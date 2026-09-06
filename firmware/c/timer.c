/*
 * timer.c — RX-8 ECU ATU Timer Module
 *
 * 1:1 firmware reconstruction of the ATU (Advanced Timer Unit) timer
 * subsystem used for serial communication timing and capture/compare.
 *
 * The ATU provides timer channels for:
 *   - Serial communication timing (bit-bang baud rate generation)
 *   - Input capture for crank/ignition events
 *   - Compare output for injector/ignition coil control
 *
 * Timer interrupts post to the RTOS task queue (cooperative scheduling).
 * The WDT is used for system reset, not the scheduling tick.
 *
 * ATU timer block is at 0xFFFFF700 (SH-2E).
 * Channel registers are spaced 0x10 apart.
 *
 * Source: rtos_analysis_report.txt (timer/tick section)
 */

#include "platform.h"
#include "timer.h"

/* ====================================================================== */
/*  ATU Channel Configuration (for serial I/O)                            */
/* ====================================================================== */

/* Channel register offsets (relative to ATU_BASE) */
#define CH_REG_STRIDE   0x10    /* Bytes per channel register set */

/* Channel 0: serial RX timing */
#define CH0_TCR     0x00    /* Timer control */
#define CH0_TIOR    0x04    /* I/O control */
#define CH0_TIER    0x08    /* Interrupt enable */
#define CH0_TGR     0x0C    /* General register (compare/capture) */

/* Channel 1: serial TX timing */
#define CH1_TCR     0x10
#define CH1_TIOR    0x14
#define CH1_TIER    0x18
#define CH1_TGR     0x1C

/* Channel 2: extra timing */
#define CH2_TCR     0x20
#define CH2_TIOR    0x24
#define CH2_TIER    0x28
#define CH2_TGR     0x2C

/* ====================================================================== */
/*  Timer Read/Write Helpers                                              */
/* ====================================================================== */

static inline uint16_t timer_read16(uint16_t offset)
{
    return *(volatile uint16_t *)(uintptr_t)(ATU_BASE + offset);
}

static inline void timer_write16(uint16_t offset, uint16_t value)
{
    *(volatile uint16_t *)(uintptr_t)(ATU_BASE + offset) = value;
}

/* ====================================================================== */
/*  ATU Timer Init (called by serial_init)                                */
/* ====================================================================== */

/**
 * atu_timer_init — Initialize ATU timer channels for serial communication.
 *
 * Sets up the ATU prescaler and channel modes.
 * Configures the prescaler to divide by 4 (1 MHz tick from 4 MHz clock).
 * All channels start in timer mode (free-running).
 *
 * ROM address: part of hw_init_1 sequence
 */
void atu_timer_init(void)
{
    /* Stop all timers before configuration */
    timer_write16(ATU_TSTR_OFFSET, 0x0000);

    /* Configure prescaler: divide by 4 for 1 MHz tick */
    timer_write16(ATU_TSTR_OFFSET, ATU_PRESCALER_DIV4);

    /* Channel 0: Timer mode, no prescaler override */
    timer_write16(CH0_TCR, 0x0000);

    /* Channel 1: Timer mode */
    timer_write16(CH1_TCR, 0x0000);

    /* Channel 2: Timer mode */
    timer_write16(CH2_TCR, 0x0000);
}

/* ====================================================================== */
/*  ATU Capture/Compare Init (called by serial_init)                      */
/* ====================================================================== */

/**
 * atu_capture_compare_init — Initialize ATU capture/compare channels.
 *
 * Configures input capture on channel 0 for serial RX.
 * Configures output compare on channel 1 for serial TX.
 * Enables interrupt on capture/compare match.
 *
 * ROM address: part of hw_init_1 sequence
 */
void atu_capture_compare_init(void)
{
    /* Channel 0: Input capture on rising edge (RX) */
    timer_write16(CH0_TIOR, 0x0004);   /* Capture on rising edge */

    /* Channel 1: Output compare, set pin on match (TX) */
    timer_write16(CH1_TIOR, 0x0001);   /* Output compare, pin=LOW on match */

    /* Channel 2: Timer mode, no I/O */
    timer_write16(CH2_TIOR, 0x0000);

    /* Enable interrupt on channel 0 capture (RX byte received) */
    timer_write16(CH0_TIER, 0x0001);

    /* Enable interrupt on channel 1 compare (TX byte sent) */
    timer_write16(CH1_TIER, 0x0001);

    /* Channel 2: no interrupt */
    timer_write16(CH2_TIER, 0x0000);
}

/* ====================================================================== */
/*  ATU Configure I/O Channel                                             */
/* ====================================================================== */

/**
 * atu_configure_io_channel — Configure ATU channel for serial I/O.
 *
 * Configures the specified ATU channel for serial I/O mode.
 * Sets up GPIO pins for TX/RX.
 *
 * ROM address: part of hw_init_1
 * @param channel  Channel number (0-2)
 */
void atu_configure_io_channel(uint8_t channel)
{
    if (channel > 2) return;

    uint16_t tior_offset = CH0_TIOR + (channel * CH_REG_STRIDE);

    /* Default: no I/O (timer only) */
    timer_write16(tior_offset, 0x0000);
}

/* ====================================================================== */
/*  Hardware Init for Serial Timers                                       */
/* ====================================================================== */

/**
 * hardware_init_serial_timers — Initialize serial communication timers.
 *
 * ROM address: 0xB6BC
 *
 * Configures ATU timers for serial communication.
 * Sets up registers at 0xFFFFF74E, 0xFFFFF72C.
 * Configures interrupt controller registers.
 */
void hardware_init_serial_timers(void)
{
    /* Configure ATU channel 0 for serial timing */
    timer_write16(0x004E, 0x0000);  /* Timer control */
    timer_write16(0x002C, 0x0000);  /* Timer mode */

    /* Configure interrupt controller */
    intc_reg_write(0x0008);  /* INTC enable */
    intc_reg_write(0x000A);  /* INTC config */
    intc_reg_write(0x000E);  /* INTC priority */
}
