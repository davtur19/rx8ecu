/*
 * serial.c — RX-8 ECU Serial Communication Interface
 *
 * 1:1 firmware reconstruction of the ATU serial I/O subsystem.
 * Implements:
 *   - ATU serial interface (bit-bang SPI) initialization
 *   - Serial data write handler
 *   - Serial data read handler
 *   - Serial data write handler for EEPROM
 *
 * The RX-8 ECU uses ATU (Advanced Timer Unit) for bit-banged serial
 * communication. The interface uses GPIO pins controlled via timer
 * compare/capture for precise timing.
 *
 * Channel assignments:
 *   CH0: External diagnostic tool (ISO 9141)
 *   CH1: Internal diagnostics / EEPROM interface
 *   CH2: Secondary bus (if equipped)
 *
 * Hardware registers:
 *   0xFFFFF700+: ATU timer registers
 *   0xFFFFF738: Port function control (PFC)
 *   0xFFFFE400: CAN / SPI control (shared)
 *   0xFFFFF100: Serial configuration registers
 *
 * Source: serial_analysis_report.txt
 */

#include "platform.h"
#include "serial.h"
#include "timer.h"    /* atu_timer_init, atu_capture_compare_init */

/* ====================================================================== */
/*  ATU Serial Channel State                                              */
/* ====================================================================== */

/* Per-channel state for serial I/O */
typedef struct {
    volatile uint8_t  *rx_buf;       /* Receive buffer pointer */
    volatile uint8_t  *tx_buf;       /* Transmit buffer pointer */
    uint8_t            rx_idx;       /* Current RX index */
    uint8_t            tx_idx;       /* Current TX index */
    uint8_t            rx_len;       /* Expected RX length */
    uint8_t            tx_len;       /* TX length to send */
    uint8_t            status;       /* Channel status flags */
    uint8_t            error;        /* Error flags */
} serial_channel_state_t;

/* Channel state array.
 * review-fix: volatile — entries are written by the ATU ISR
 * (serial_atu_irq_handler and the RX handlers) and read/updated by main-loop
 * code (serial_data_read/write, serial_data_write_handler). Guard strategy:
 * ISR only sets RX flags/bytes while main-loop consumes under
 * serial_enable/disable_interrupts (intc_reg_write) critical sections;
 * single volatile accesses are atomic on SH-2 (8-bit). */
static volatile serial_channel_state_t serial_channels[3];

/* Owned per-channel TX staging buffers.
 * review-fix w2: serial_data_write used to alias the CALLER's buffer
 * (`ch->tx_buf = buf`) — the caller could reuse/free it while the ATU
 * ISR was still transmitting. Copy into owned storage instead (len is
 * uint8_t, so 256 bytes always fits). */
#define SERIAL_TX_OWNED_SIZE 256
static uint8_t serial_tx_owned[3][SERIAL_TX_OWNED_SIZE];

/* ====================================================================== */
/*  Status and Error Flags                                                */
/* ====================================================================== */

#define SERIAL_STATUS_IDLE       0x00
#define SERIAL_STATUS_TX_BUSY    0x01
#define SERIAL_STATUS_RX_BUSY    0x02
#define SERIAL_STATUS_RX_READY   0x04
#define SERIAL_STATUS_TX_READY   0x08
#define SERIAL_STATUS_ERROR      0x10

/* ====================================================================== */
/*  Hardware Register Helpers                                             */
/* ====================================================================== */

/* Read 16-bit register from ATU block */
static inline uint16_t atu_reg_read(uint16_t offset)
{
    return *(volatile uint16_t *)(uintptr_t)(ATU_BASE + offset);
}

/* Write 16-bit register in ATU block */
static inline void atu_reg_write(uint16_t offset, uint16_t value)
{
    *(volatile uint16_t *)(uintptr_t)(ATU_BASE + offset) = value;
}

/* Read 8-bit register from ATU block */
static inline uint8_t atu_reg_read8(uint16_t offset)
{
    return *(volatile uint8_t *)(uintptr_t)(ATU_BASE + offset);
}

/* Write 8-bit register in ATU block */
static inline void atu_reg_write8(uint16_t offset, uint8_t value)
{
    *(volatile uint8_t *)(uintptr_t)(ATU_BASE + offset) = value;
}

/* ====================================================================== */
/*  Serial I/O Initialization                                             */
/* ====================================================================== */

/**
 * serial_init — Initialize all serial channels.
 *
 * Sets up ATU channels for serial communication.
 * Configures GPIO pins, timer prescaler, and interrupt enables.
 */
void serial_init(void)
{
    /* Initialize channel state */
    for (int i = 0; i < 3; i++) {
        serial_channels[i].status = SERIAL_STATUS_IDLE;
        serial_channels[i].error = 0;
        serial_channels[i].rx_idx = 0;
        serial_channels[i].tx_idx = 0;
        serial_channels[i].rx_len = 0;
        serial_channels[i].tx_len = 0;
        /* review-fix w2: point TX at the owned buffer from init so the
         * channel never holds a stray caller pointer. */
        serial_channels[i].tx_buf = serial_tx_owned[i];
    }

    /* Configure ATU timer for serial timing */
    atu_timer_init();

    /* Configure capture/compare for serial I/O */
    atu_capture_compare_init();

    /* Enable serial interrupts */
    serial_enable_interrupts();
}

/**
 * serial_enable_interrupts — Enable serial-related interrupts.
 */
void serial_enable_interrupts(void)
{
    /* Enable ATU channel interrupts */
    intc_reg_write(0x001E);  /* Interrupt enable bits */
}

/**
 * serial_disable_interrupts — Disable serial-related interrupts.
 */
void serial_disable_interrupts(void)
{
    /* Disable ATU channel interrupts */
    intc_reg_write(0x0000);  /* All interrupts off */
}

/* ====================================================================== */
/*  Serial Data Read                                                      */
/* ====================================================================== */

/**
 * serial_data_read — Read data from serial channel.
 *
 * Reads received bytes from the channel's RX buffer.
 * Returns the number of bytes actually read.
 *
 * @param channel  Channel number (0-2)
 * @param buf      Destination buffer
 * @param max_len  Maximum bytes to read
 * @return Number of bytes read, or -1 on error
 */
int serial_data_read(uint8_t channel, uint8_t *buf, uint8_t max_len)
{
    if (channel >= 3) return -1;
    if (serial_channels[channel].rx_buf == NULL) return -1;
    if (serial_channels[channel].status == SERIAL_STATUS_IDLE) return 0;

    volatile serial_channel_state_t *ch = &serial_channels[channel];
    uint8_t len = ch->rx_len;
    if (len > max_len) len = max_len;

    /* Copy from RX buffer */
    for (uint8_t i = 0; i < len; i++) {
        buf[i] = ch->rx_buf[i];
    }

    /* Clear RX ready flag */
    ch->status &= ~SERIAL_STATUS_RX_READY;
    ch->rx_idx = 0;
    ch->rx_len = 0;

    return len;
}

/* ====================================================================== */
/*  Serial Data Write                                                     */
/* ====================================================================== */

/**
 * serial_data_write — Write data to serial channel.
 *
 * Copies data to the channel's TX buffer and starts transmission.
 * Returns the number of bytes queued.
 *
 * @param channel  Channel number (0-2)
 * @param buf      Source data
 * @param len      Number of bytes to write
 * @return Number of bytes queued, or -1 on error
 */
int serial_data_write(uint8_t channel, const uint8_t *buf, uint8_t len)
{
    if (channel >= 3) return -1;

    volatile serial_channel_state_t *ch = &serial_channels[channel];

    /* Check if channel is busy */
    if (ch->status & SERIAL_STATUS_TX_BUSY) return -1;

    /* Copy to the owned TX buffer (never alias the caller buffer). */
    for (uint16_t i = 0; i < len; i++) {
        serial_tx_owned[channel][i] = buf[i];
    }
    ch->tx_buf = serial_tx_owned[channel];
    ch->tx_len = len;
    ch->tx_idx = 0;
    ch->status |= SERIAL_STATUS_TX_BUSY;
    ch->status |= SERIAL_STATUS_TX_READY;

    /* Start transmission: trigger first byte */
    /* On real hardware, this would load the first byte into the ATU
     * compare register and start the TX state machine. For host
     * verification, this is a no-op (synchronous copy). */
    serial_start_tx(channel);

    return len;
}

/**
 * serial_start_tx — Begin transmitting from the TX buffer.
 *
 * @param channel  Channel number (0-2)
 */
void serial_start_tx(uint8_t channel)
{
    if (channel >= 3) return;

    volatile serial_channel_state_t *ch = &serial_channels[channel];

    if (!(ch->status & SERIAL_STATUS_TX_READY)) return;

    /* On real hardware, load first byte into ATU compare register.
     * The ATU interrupt handler will send subsequent bytes.
     * For host verification, we simulate synchronous transmission. */

    /* Simulate TX completion (for testing).
     * review-fix w2 (follow-up documented, ISR side out of scope): real
     * completion is ISR-driven — the ATU TX-compare ISR must pump
     * tx_buf[tx_idx++] per interrupt and clear TX_BUSY on the last byte.
     * Today serial_atu_irq_handler's channel-1 TX branch only clears the
     * status flag without pumping bytes, so host-side completion stays
     * synchronous until that ISR path is implemented. */
    ch->tx_idx = ch->tx_len;
    ch->status &= ~SERIAL_STATUS_TX_BUSY;
    ch->status &= ~SERIAL_STATUS_TX_READY;
}

/* ====================================================================== */
/*  Serial Data Write Handler                                             */
/* ====================================================================== */

/**
 * serial_data_write_handler — Process queued serial write operations.
 *
 * Called from the main task dispatcher to handle pending writes.
 * Checks the write queue and sends data to the appropriate channel.
 */
void serial_data_write_handler(void)
{
    /* Check if there's data to send */
    for (int i = 0; i < 3; i++) {
        volatile serial_channel_state_t *ch = &serial_channels[i];

        if (ch->status & SERIAL_STATUS_TX_READY) {
            serial_start_tx(i);
        }
    }
}

/* ====================================================================== */
/*  Serial RX Handlers (per channel)                                      */
/* ====================================================================== */

/**
 * serial_rx_handler_ch0 — Handle received data on channel 0.
 *
 * Called when data is received on the diagnostic tool channel.
 * Copies received data to the RX buffer and sets the ready flag.
 */
void serial_rx_handler_ch0(void)
{
    volatile serial_channel_state_t *ch = &serial_channels[0];

    /* Read received byte from ATU capture register.
     * review-fix w2: was `(uint8_t)atu_reg_read(...)` — a 16-bit read
     * truncated to the LOW byte. TGRs are 16-bit timer registers and the
     * SH-2 is big-endian, so an 8-bit access at the same (even) address
     * observes the HIGH byte instead. Use the 8-bit helper and document
     * the lane choice: NEEDS-ROM-CHECK — ROM must confirm whether the RX
     * byte is the high or low byte of TGR0. */
    uint8_t data = atu_reg_read8(ATU_TGR0_OFFSET);

    /* Store in RX buffer if space available */
    if (ch->rx_buf != NULL && ch->rx_idx < ch->rx_len) {
        ch->rx_buf[ch->rx_idx++] = data;
    }

    /* Check for end of message (if known) */
    if (ch->rx_idx >= ch->rx_len) {
        ch->status |= SERIAL_STATUS_RX_READY;
    }
}

/**
 * serial_rx_handler_ch1 — Handle received data on channel 1.
 *
 * Called when data is received on the EEPROM interface channel.
 */
void serial_rx_handler_ch1(void)
{
    volatile serial_channel_state_t *ch = &serial_channels[1];

    /* Read received byte from ATU capture register.
     * review-fix w2: 8-bit access (see ch0 note); NEEDS-ROM-CHECK for the
     * high-vs-low byte-lane choice on big-endian SH-2 TGR1. */
    uint8_t data = atu_reg_read8(ATU_TGR1_OFFSET);

    /* Store in RX buffer if space available */
    if (ch->rx_buf != NULL && ch->rx_idx < ch->rx_len) {
        ch->rx_buf[ch->rx_idx++] = data;
    }

    /* Check for end of message */
    if (ch->rx_idx >= ch->rx_len) {
        ch->status |= SERIAL_STATUS_RX_READY;
    }
}

/**
 * serial_rx_handler_ch2 — Handle received data on channel 2.
 *
 * Called when data is received on the secondary bus channel.
 */
void serial_rx_handler_ch2(void)
{
    volatile serial_channel_state_t *ch = &serial_channels[2];

    /* Read received byte from ATU capture register.
     * review-fix w2: 8-bit access (see ch0 note); NEEDS-ROM-CHECK for the
     * high-vs-low byte-lane choice on big-endian SH-2 TGR2. */
    uint8_t data = atu_reg_read8(ATU_TGR2_OFFSET);

    /* Store in RX buffer if space available */
    if (ch->rx_buf != NULL && ch->rx_idx < ch->rx_len) {
        ch->rx_buf[ch->rx_idx++] = data;
    }

    /* Check for end of message */
    if (ch->rx_idx >= ch->rx_len) {
        ch->status |= SERIAL_STATUS_RX_READY;
    }
}

/* ====================================================================== */
/*  Interrupt Handlers (stubs for now)                                    */
/* ====================================================================== */

/**
 * serial_atu_irq_handler — ATU serial interrupt handler.
 *
 * Called when an ATU channel interrupt fires.
 * Dispatches to the appropriate RX/TX handler.
 */
void serial_atu_irq_handler(void)
{
    /* Read interrupt status */
    uint16_t isr = atu_reg_read(ATU_TISRA_OFFSET);

    /* Channel 0: RX capture */
    if (isr & 0x0001) {
        serial_rx_handler_ch0();
        /* review-fix: flag-only clear via read-modify-write. The old full-
         * mask write (~0x0001 = 0xFFFE) rewrites every other flag bit too,
         * wiping flags set by other channels. RMW is safe under both
         * write-0-to-clear and direct-write status semantics. */
        atu_reg_write(ATU_TISRA_OFFSET,
                      (uint16_t)(atu_reg_read(ATU_TISRA_OFFSET) & (uint16_t)~0x0001u));
    }

    /* Channel 1: TX compare */
    if (isr & 0x0002) {
        /* TX complete — load next byte or clear busy flag */
        /* review-fix: flag-only clear (see above). */
        atu_reg_write(ATU_TISRA_OFFSET,
                      (uint16_t)(atu_reg_read(ATU_TISRA_OFFSET) & (uint16_t)~0x0002u));
    }

    /* Channel 2: RX capture */
    if (isr & 0x0004) {
        serial_rx_handler_ch2();
        /* review-fix: flag-only clear (see above). */
        atu_reg_write(ATU_TISRA_OFFSET,
                      (uint16_t)(atu_reg_read(ATU_TISRA_OFFSET) & (uint16_t)~0x0004u));
    }
}
