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

/* review-fix (NEEDS-ROM-CHECK): the local CH*_TCR/TIOR/TIER/TGR offset block
 * (TCR at +0x00/+0x10/+0x20, TIOR at +0x04/..., stride 0x10) is deleted and
 * all accesses use the shared platform.h scheme (TSTR +0x00, TCR0/1/2
 * +0x10/+0x20/+0x30, TIOR0/1 +0x40/+0x50, TIER0/1 +0x60/+0x70, TGR0/1/2
 * +0x80/+0x90/+0xA0, TISRA +0xB0 — already used by serial.c).
 * Rationale: the local scheme placed CH0_TCR at offset 0x00, which IS the
 * TSTR start/stop register on SH (TSTR holds counter start bits; the CKS
 * prescaler bits live in each channel TCR), so every channel-0 TCR write hit
 * TSTR. The header scheme is the SH-manual-consistent one. Full ROM/manual
 * confirmation of the ATU map is still pending (raw ROM offsets 0x2C/0x4E
 * written below match neither scheme), hence NEEDS-ROM-CHECK.
 * Channel 2 has no TIOR/TIER definition in platform.h, so its two offsets
 * are kept as raw values (numerically identical to the old locals) pending
 * ROM/manual arbitration. */
#define ATU_CH2_TIOR_RAW_OFFSET  0x24    /* NEEDS-ROM-CHECK: ex-CH2_TIOR */
#define ATU_CH2_TIER_RAW_OFFSET  0x28    /* NEEDS-ROM-CHECK: ex-CH2_TIER */

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
    /* Stop all timers before configuration (TSTR holds start bits only) */
    timer_write16(ATU_TSTR_OFFSET, 0x0000);

    /* review-fix: the CKS prescaler bits live in each channel TCR, not in
     * TSTR. The old code wrote ATU_PRESCALER_DIV4 to ATU_TSTR_OFFSET, which
     * asserts timer start bit 0 instead of selecting a /4 divider. Set timer
     * mode with /4 prescaler per channel (mode field is 0). TSTR is used only
     * for start bits above. */
    timer_write16(ATU_TCR0_OFFSET, ATU_PRESCALER_DIV4);
    timer_write16(ATU_TCR1_OFFSET, ATU_PRESCALER_DIV4);
    timer_write16(ATU_TCR2_OFFSET, ATU_PRESCALER_DIV4);
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
    timer_write16(ATU_TIOR0_OFFSET, 0x0004);   /* Capture on rising edge */

    /* Channel 1: Output compare, set pin on match (TX) */
    timer_write16(ATU_TIOR1_OFFSET, 0x0001);   /* Output compare, pin=LOW on match */

    /* Channel 2: Timer mode, no I/O (raw offset, see NEEDS-ROM-CHECK above) */
    timer_write16(ATU_CH2_TIOR_RAW_OFFSET, 0x0000);

    /* Enable interrupt on channel 0 capture (RX byte received) */
    timer_write16(ATU_TIER0_OFFSET, 0x0001);

    /* Enable interrupt on channel 1 compare (TX byte sent) */
    timer_write16(ATU_TIER1_OFFSET, 0x0001);

    /* Channel 2: no interrupt (raw offset, see NEEDS-ROM-CHECK above) */
    timer_write16(ATU_CH2_TIER_RAW_OFFSET, 0x0000);
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

    /* review-fix: unified on the platform.h scheme (see note above); the old
     * CH0_TIOR + channel * CH_REG_STRIDE arithmetic is gone. */
    uint16_t tior_offset;
    switch (channel) {
        case 0: tior_offset = ATU_TIOR0_OFFSET; break;
        case 1: tior_offset = ATU_TIOR1_OFFSET; break;
        default: tior_offset = ATU_CH2_TIOR_RAW_OFFSET; break;  /* NEEDS-ROM-CHECK */
    }

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

    /* Configure interrupt controller.
     * review-fix (NEEDS-ROM-CHECK): the old code called intc_reg_write()
     * three times with 0x0008/0x000A/0x000E, which writes all three VALUES to
     * the SAME register (INTC_REGISTER, 0xFFFFF02E) — only the last stuck.
     * Per this function's contract (timer.h: registers 0xFFFFF008,
     * 0xFFFFF00A, 0xFFFFF00E) these are three DISTINCT INTC registers, so
     * each value goes to its own address. Values are preserved as-coded;
     * ROM 0xB6BC must confirm both addresses and values. */
    intc_reg_write_at(INTC_TMR_IPR0_ADDR, 0x0008);  /* INTC enable */
    intc_reg_write_at(INTC_TMR_IPR1_ADDR, 0x000A);  /* INTC config */
    intc_reg_write_at(INTC_TMR_IPR2_ADDR, 0x000E);  /* INTC priority */
}
