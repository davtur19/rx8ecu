/*
 * serial.h — RX-8 ECU ATU-Based Serial Interface Definitions
 *
 * The RX-8 ECU uses an ATU-based (Advanced Timer Unit) serial interface
 * as the primary diagnostic interface. Three logical channels share the
 * ATU hardware:
 *   ch0 (0x88): Main OBD/ISO 9141 diagnostic channel
 *   ch1 (0x90): Secondary diagnostic channel
 *   ch2 (0xC0): Tertiary channel
 *
 * Frame format: [source][length][payload...] with 0xAA sync, 0x55 ACK.
 * Baud rate: Runtime-configured via ATU timers (likely 10400 for ISO 9141).
 *
 * Source: serial_analysis_report.txt
 */

#ifndef SERIAL_H
#define SERIAL_H

#include <stdint.h>
#include "platform.h"

/* ====================================================================== */
/*  Serial Channel Definitions                                            */
/* ====================================================================== */

#define SERIAL_CHANNELS      3

/* Channel identifiers (command type codes) */
#define SERIAL_CH0_CMD       0x88    /* Main diagnostic channel */
#define SERIAL_CH1_CMD       0x90    /* Secondary diagnostic channel */
#define SERIAL_CH2_CMD       0xC0    /* Tertiary channel */

/* Data read/write command codes */
#define SERIAL_DATA_READ_CMD   0xB0  /* Data read request */
#define SERIAL_DATA_WRITE_CMD  0x98  /* Data write request */
#define SERIAL_DIAG_XFER_CMD   0xA8  /* Diagnostic transfer */
#define SERIAL_EXCEPTION_CMD   0xA0  /* Exception context restore */

/* RX buffer sizes */
#define SERIAL_RX_PAYLOAD_SIZE 6     /* Payload size per RX handler */

/* ====================================================================== */
/*  Serial Dispatch Commands                                              */
/* ====================================================================== */

/**
 * serial_dispatch — Route serial message to direct or queued path.
 * ROM address: 0x338
 * @param cmd     Command type code (0x88, 0x90, 0xC0, etc.)
 * @param payload_size  Payload size
 * @param source  Source buffer address
 *
 * Checks queue state byte at 0xFFFFDFA8:
 *   If zero: direct path (write to hardware immediately)
 *   If non-zero: queued path (format message, write ACK)
 */
void serial_dispatch(uint8_t cmd, uint8_t payload_size, const uint8_t *source);

/**
 * serial_tx_direct_path — Write data directly to ATU hardware.
 * ROM address: 0x256
 * @param cmd     Command type code
 * @param payload_size  Payload size
 * @param source  Source buffer address
 *
 * Copies payload to 0xFFFFDFAC + 2.
 * Waits for ATU ready (bit 0x200 at 0xFFFFE406 to clear).
 * Writes to ATU data register (0xFFFFE40A).
 * Returns 8 (success indicator).
 */
void serial_tx_direct_path(uint8_t cmd, uint8_t payload_size, const uint8_t *source);

/**
 * serial_queue_message — Format and queue a serial message.
 * ROM address: 0x47C
 * @param cmd     Command type code
 * @param payload_size  Payload size
 * @param source  Source buffer address
 *
 * Loads queue base 0xFFFFDFF0.
 * Waits for sync byte 0xAA at queue[8].
 * Formats: queue[0] = source ID, queue[1] = cmd + payload_size.
 * Copies payload to queue[2+].
 * Writes 0x55 (ACK) to queue[8].
 */
void serial_queue_message(uint8_t cmd, uint8_t payload_size, const uint8_t *source);

/* ====================================================================== */
/*  RX Handlers (per-channel)                                             */
/* ====================================================================== */

/**
 * serial_rx_handler_ch0 — Process received data on channel 0.
 * ROM address: 0x4C
 *
 * Reads status at buffer[1], masks with 0xFFFFFF07.
 * If result == 0: calls serial_dispatch(0x88, 6, buffer).
 * RX buffer at 0xFFFFFEC.
 */
void serial_rx_handler_ch0(void);

/**
 * serial_rx_handler_ch1 — Process received data on channel 1.
 * ROM address: 0x64
 *
 * Same pattern as ch0, command code 0x90.
 * RX buffer at 0xFFFFF8.
 */
void serial_rx_handler_ch1(void);

/**
 * serial_rx_handler_ch2 — Process received data on channel 2.
 * ROM address: 0xC0
 *
 * Same pattern as ch0, command code 0xC0.
 * RX buffer at 0xFFFFF4.
 */
void serial_rx_handler_ch2(void);

/* ====================================================================== */
/*  Data Read/Write Handlers                                              */
/* ====================================================================== */

/**
 * serial_data_read_handler — Handle data read request.
 * ROM address: 0x8A
 * Command code: 0xB0
 */
void serial_data_read_handler(void);

/**
 * serial_data_write_handler — Handle data write request.
 * ROM address: 0x7C0
 * Command code: 0x98
 *
 * Checks status byte at buffer[1], mask 0xFFFFFF07.
 * If result == 4: builds 32-bit value from buffer+2, stores to flag_gate.
 * Calls serial_dispatch(0x98, 4, &value).
 */
void serial_data_write_handler(void);

/* ====================================================================== */
/*  ATU Hardware Helpers                                                  */
/* ====================================================================== */

/**
 * serial_enable_interrupts — Enable serial-related interrupts.
 * ROM address: (part of serial init)
 */
void serial_enable_interrupts(void);

/**
 * serial_disable_interrupts — Disable serial-related interrupts.
 * ROM address: (part of serial init)
 */
void serial_disable_interrupts(void);

/**
 * atu_timer_init — Initialize ATU timer for serial communication.
 * ROM address: (part of serial init)
 */
void atu_timer_init(void);

/**
 * atu_capture_compare_init — Initialize ATU capture/compare channels.
 * ROM address: (part of serial init)
 */
void atu_capture_compare_init(void);

/**
 * serial_start_tx — Begin transmitting from the TX buffer.
 * ROM address: (part of serial tx path)
 * @param channel  Channel number (0-2)
 */
void serial_start_tx(uint8_t channel);

/**
 * hardware_init_serial_timers — Initialize serial communication timers.
 * ROM address: 0xB6BC
 */
void hardware_init_serial_timers(void);

/**
 * atu_wait_and_transfer — Wait for ATU ready and send data.
 * ROM address: 0x1168
 *
 * Waits for ATU ready (bit 0x80 at 0xFFFFE406 to clear).
 * Writes 0x80 to 0xFFFFE40A.
 * Calls copy_buffer_to_data to transfer data.
 */
void atu_wait_and_transfer(void);

/**
 * atu_channel_transfer — Check ATU RX status and receive data.
 * ROM address: 0x1116
 * @return 1 if data received, 0 otherwise
 *
 * Checks ATU RX status at 0xFFFFE40E (bit 0x60).
 * Checks error at 0xFFFFE41A (bit 0x60).
 * If status == 8: calls copy_data_to_buffer to read data.
 */
int atu_channel_transfer(void);

/**
 * atu_clear_status_flags — Clear ATU status flags.
 * ROM address: 0x119A
 */
void atu_clear_status_flags(void);

/* ====================================================================== */
/*  Utility Functions                                                     */
/* ====================================================================== */

/**
 * build_be32_from_bytes — Build 32-bit big-endian value from 4 bytes.
 * ROM address: 0xF4
 * @param p  Pointer to 4 bytes
 * @return 32-bit value
 */
uint32_t build_be32_from_bytes(const uint8_t *p);

/**
 * calculate_checksum — Simple additive checksum with carry folding.
 * ROM address: 0x11A
 * @param data  Data buffer
 * @param len   Data length
 * @return 8-bit checksum
 */
uint8_t calculate_checksum(const uint8_t *data, uint32_t len);

#endif /* SERIAL_H */
