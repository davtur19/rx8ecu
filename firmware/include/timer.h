/*
 * timer.h — RX-8 ECU ATU Timer Definitions
 *
 * The ATU (Advanced Timer Unit) provides timer channels for:
 *   - Serial communication timing (bit-bang baud rate)
 *   - Input capture for crank/ignition events
 *   - Compare output for injector/ignition coil control
 *
 * Timer interrupts post to the RTOS task queue (cooperative scheduling).
 * The WDT is used for system reset, not the scheduling tick.
 *
 * Source: rtos_analysis_report.txt (timer/tick section)
 */

#ifndef TIMER_H
#define TIMER_H

#include <stdint.h>
#include "platform.h"

/* ====================================================================== */
/*  ATU Channel Configuration                                             */
/* ====================================================================== */

/* ATU timer register base */
#define ATU_TIMER_BASE      0xFFFFF700  /* ATU register block */
#define ATU_CHANNEL_STRIDE  16          /* Bytes per channel */

/* ATU prescaler / clock divider */
#define ATU_PRESCALER_DISABLE   0x0000
#define ATU_PRESCALER_DIV4      0x0001
#define ATU_PRESCALER_DIV16     0x0002
#define ATU_PRESCALER_DIV64     0x0003

/* ATU channel modes */
#define ATU_MODE_TIMER          0   /* Free-running timer */
#define ATU_MODE_CAPTURE        1   /* Input capture */
#define ATU_MODE_COMPARE        2   /* Output compare */
#define ATU_MODE_PWM            3   /* PWM output */

/* ====================================================================== */
/*  Timer Interrupt Configuration                                         */
/* ====================================================================== */

/* Timer interrupt sources (ATU channels) */
#define ATU_IRQ_OVERFLOW        0   /* Timer overflow */
#define ATU_IRQ_CAPTURE_A       1   /* Capture A match */
#define ATU_IRQ_CAPTURE_B       2   /* Capture B match */
#define ATU_IRQ_COMPARE         3   /* Compare match */

/* ====================================================================== */
/*  Timer Function Prototypes                                             */
/* ====================================================================== */

/**
 * atu_timer_init — Initialize ATU timer channels.
 * ROM address: 0x10AC
 *
 * Configures ATU channels for serial communication timing.
 * Sets up prescaler, channel modes, and interrupt enables.
 */
void atu_timer_init(void);

/**
 * atu_capture_compare_init — Initialize ATU capture/compare.
 * ROM address: 0x4F08
 *
 * Sets up input capture for crank sensor events.
 * Sets up output compare for ignition/injector timing.
 */
void atu_capture_compare_init(void);

/**
 * atu_configure_io_channel — Configure ATU channel for serial I/O.
 * ROM address: (part of hw_init_1)
 * @param channel  Channel number (0-2)
 *
 * Configures the specified ATU channel for serial I/O mode.
 * Sets up GPIO pins for TX/RX.
 */
void atu_configure_io_channel(uint8_t channel);

/**
 * hardware_init_serial_timers — Initialize serial communication timers.
 * ROM address: 0xB6BC
 *
 * Configures ATU timers for serial communication.
 * Sets up registers at 0xFFFFF74E, 0xFFFFF72C.
 * Configures 0xFFFFF008, 0xFFFFF00A, 0xFFFFF00E.
 */
void hardware_init_serial_timers(void);

#endif /* TIMER_H */
