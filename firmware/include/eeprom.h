/*
 * eeprom.h — RX-8 ECU SPI EEPROM Interface Definitions
 *
 * The RX-8 ECU uses an external SPI EEPROM chip (ABLIC S-93C56C, 256 bytes).
 * The SPI interface is bit-banged using GPIO pins mapped through the CAN
 * controller register space at 0xFFFFE4xx.
 *
 * Key registers:
 *   0xFFFFE401: SPI clock (bit 0) / status (bit 3)
 *   0xFFFFE406/08/0A: SPI data registers
 *   0xFFFFE414-1E: SPI channel config
 *   0xFFFFE4B0/B8: SPI buffer registers
 *
 * Source: eeprom_analysis_report.txt, spi_set_clk_high_wait_9c0.c,
 *         spi_set_clk_low_wait_9de.c, is_eeprom_valid_624.c
 */

#ifndef EEPROM_H
#define EEPROM_H

#include <stddef.h>
#include <stdint.h>
#include "platform.h"

/* ====================================================================== */
/*  EEPROM Chip Parameters                                                */
/* ====================================================================== */

#define EEPROM_SIZE         256     /* ABLIC S-93C56C: 256 bytes */
#define EEPROM_SECTOR_SIZE  64      /* Sector size for sector erase */
#define EEPROM_PAGE_SIZE    16      /* Write page size */
#define EEPROM_ADDR_BITS    8       /* Address bits (256 bytes = 2^8) */

/* ====================================================================== */
/*  SPI Bit-Bang Interface                                                */
/* ====================================================================== */

/**
 * spi_clk_high_wait — Set SPI clock HIGH, wait for status ready.
 * ROM address: 0x9C0
 * @param clk_reg  Pointer to clock/control register (0xFFFFE401)
 * @param stat_reg Pointer to status register (0xFFFFE401)
 *
 * Sets bit 0 of clk_reg (clock HIGH).
 * Waits for bit 3 of stat_reg to clear (transfer complete).
 * Timeout: 4000 iterations.
 */
void spi_clk_high_wait(volatile uint8_t *clk_reg, volatile uint8_t *stat_reg);

/**
 * spi_clk_low_wait — Set SPI clock LOW, wait for data ready.
 * ROM address: 0x9DE
 * @param clk_reg  Pointer to clock/control register (0xFFFFE401)
 * @param stat_reg Pointer to status register (0xFFFFE401)
 *
 * Clears bit 0 of clk_reg (clock LOW).
 * Waits for bit 3 of stat_reg to set (data ready).
 * Timeout: 4000 iterations.
 */
void spi_clk_low_wait(volatile uint8_t *clk_reg, volatile uint8_t *stat_reg);

/**
 * spi_write_bit — Write a single bit via SPI bit-bang.
 * @param bit  The bit value to write (0 or 1)
 *
 * Sets clock LOW, writes data bit, sets clock HIGH.
 */
void spi_write_bit(uint8_t bit);

/**
 * spi_read_bit — Read a single bit via SPI bit-bang.
 * @return The bit value read (0 or 1)
 *
 * Sets clock LOW, reads data bit, sets clock HIGH.
 */
uint8_t spi_read_bit(void);

/**
 * spi_write_byte — Write a byte via SPI (MSB first).
 * @param data  The byte to write
 */
void spi_write_byte(uint8_t data);

/**
 * spi_read_byte — Read a byte via SPI (MSB first).
 * @return The byte read
 */
uint8_t spi_read_byte(void);

/* ====================================================================== */
/*  EEPROM Core Operations                                                */
/* ====================================================================== */

/**
 * eeprom_read_byte — Read a single byte from EEPROM.
 * @param addr  EEPROM address (0-255)
 * @return The byte at the given address
 *
 * Sequence:
 *   1. CS low
 *   2. Send READ command (0x03)
 *   3. Send address byte
 *   4. Clock in data byte
 *   5. CS high
 */
uint8_t eeprom_read_byte(uint8_t addr);

/**
 * eeprom_write_byte — Write a single byte to EEPROM.
 * @param addr  EEPROM address (0-255)
 * @param data  The byte to write
 *
 * Sequence:
 *   1. CS low, send WREN (0x06), CS high
 *   2. CS low, send WRITE (0x02), send address, send data
 *   3. CS high
 *   4. Wait for write cycle (5-10ms)
 */
void eeprom_write_byte(uint8_t addr, uint8_t data);

/**
 * eeprom_read_sector — Read a sector (page) from EEPROM.
 * @param addr   Start address (sector-aligned)
 * @param buf    Destination buffer (must be non-NULL)
 * @param len    Number of bytes to read (clamped to EEPROM bounds)
 */
void eeprom_read_sector(uint8_t addr, uint8_t *buf, size_t len);

/**
 * eeprom_write_sector — Write a sector (page) to EEPROM.
 * @param addr   Start address (sector-aligned)
 * @param buf    Source buffer (must be non-NULL)
 * @param len    Number of bytes to write (clamped to EEPROM bounds)
 */
void eeprom_write_sector(uint8_t addr, const uint8_t *buf, size_t len);

/**
 * eeprom_erase_sector — Erase a sector (64 bytes) of EEPROM.
 * @param addr  Sector address (sector-aligned)
 *
 * Sequence:
 *   1. CS low, send WREN (0x06), CS high
 *   2. CS low, send SECTOR_ERASE (0x20), send address
 *   3. CS high
 *   4. Wait for erase cycle (50-300ms)
 */
void eeprom_erase_sector(uint8_t addr);

/* ====================================================================== */
/*  EEPROM Validation and RAM Staging                                     */
/* ====================================================================== */

/**
 * eeprom_read_validate — Read and validate EEPROM data staged in RAM.
 * ROM address: 0x450
 * @param dest  Destination buffer (8 bytes)
 * @return 1 if valid data was copied, -1 if marker invalid
 *
 * Reads 8 bytes from RAM buffer at 0xFFFFDFE4.
 * Validates marker byte at offset 8 (must be 0x55).
 * If valid: copies 8 bytes to dest, writes 0xAA to marker (consumed).
 */
int eeprom_read_validate(uint8_t *dest);

/**
 * is_eeprom_valid — Check if EEPROM data is valid in RAM.
 * ROM address: 0x624
 * @return 1 if marker at 0xFFFFDFEC == 0x55, 0 otherwise
 */
int is_eeprom_valid(void);

/**
 * eeprom_commit_to_ram — Copy data to EEPROM staging area in RAM.
 * @param src   Source data (must be non-NULL)
 * @param len   Length to copy (clamped to EEPROM_STAGING_SIZE)
 *
 * Copies to 0xFFFFC2FE, stores inverted copy at 0xFFFFC3FE for verification.
 */
void eeprom_commit_to_ram(const uint8_t *src, size_t len);

#endif /* EEPROM_H */
