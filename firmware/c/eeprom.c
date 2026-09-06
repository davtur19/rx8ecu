/*
 * eeprom.c — RX-8 ECU SPI EEPROM Interface (60E1D400)
 *
 * 1:1 firmware reconstruction of the external SPI EEPROM interface
 * for the Mazda RX-8 Renesis 13B-MSP rotary engine ECU.
 *
 * The RX-8 ECU uses an external ABLIC S-93C56C SPI EEPROM (256 bytes)
 * connected via bit-banged SPI through GPIO pins mapped to the CAN
 * controller register space at 0xFFFFE4xx.
 *
 * Key registers:
 *   0xFFFFE401: SPI clock (bit 0) / transfer status (bit 3)
 *
 * SPI bit-bang functions:
 *   spi_clk_high_wait (0x9C0): Set clock HIGH, wait for status clear
 *   spi_clk_low_wait  (0x9DE): Set clock LOW, wait for status set
 *
 * EEPROM operations (from eeprom_analysis_report.txt):
 *   Read:  CS low -> READ(0x03) -> addr -> clock in data -> CS high
 *   Write: CS low -> WREN(0x06) -> CS high -> CS low -> WRITE(0x02) -> addr -> data -> CS high
 *   Erase: CS low -> WREN(0x06) -> CS high -> CS low -> SECTOR_ERASE(0x20) -> addr -> CS high
 *
 * RAM staging areas:
 *   0xFFFFC2FE: EEPROM data staging buffer (256 bytes)
 *   0xFFFFC3FE: Inverted copy for verification
 *   0xFFFFDFE4: RAM validation buffer A (8 bytes + marker at +8)
 *   0xFFFFDFEC: Validity marker (0x55=valid, 0xAA=consumed)
 *
 * Source: eeprom_analysis_report.txt, spi_set_clk_high_wait_9c0.c,
 *         spi_set_clk_low_wait_9de.c, is_eeprom_valid_624.c
 */

#include "platform.h"
#include "eeprom.h"

/* ====================================================================== */
/*  Chip Select Control                                                   */
/* ====================================================================== */

/* The chip select (CS) pin is controlled via a GPIO bit.
 * On the RX-8 ECU, CS is typically on a port pin in the 0xFFFFF7xx range.
 * The exact pin assignment depends on the specific hardware revision.
 * TODO: Identify the exact CS pin from additional analysis. */
#define SPI_CS_PORT     (*(volatile uint16_t *)0xFFFFF730)
#define SPI_CS_BIT      0x0001  /* Bit 0 = chip select (active LOW) */

static inline void spi_cs_low(void) {
    SPI_CS_PORT &= ~SPI_CS_BIT;
}

static inline void spi_cs_high(void) {
    SPI_CS_PORT |= SPI_CS_BIT;
}

/* ====================================================================== */
/*  SPI Bit-Bang Implementation                                            */
/* ====================================================================== */

/**
 * spi_clk_high_wait — Set SPI clock HIGH and wait for transfer ready.
 *
 * ROM address: 0x9C0
 * Size: 30 bytes
 *
 * Sets bit 0 of the clock register (0xFFFFE401) to HIGH.
 * Waits for bit 3 (status) to CLEAR, indicating the bus is ready.
 * Timeout after 4000 iterations (0xFA0).
 *
 * The clock register and status register are the same byte (0xFFFFE401).
 * Bit 0: clock output (1=HIGH, 0=LOW)
 * Bit 3: transfer status (1=busy, 0=ready)
 *
 * @param clk_reg  Pointer to clock/control register
 * @param stat_reg Pointer to status register (same as clk_reg on this ECU)
 */
void spi_clk_high_wait(volatile uint8_t *clk_reg, volatile uint8_t *stat_reg)
{
    uint32_t timeout = SPI_TIMEOUT_ITERATIONS;

    /* Set clock HIGH: OR bit 0 */
    *clk_reg |= SPI_CLK_BIT;

    /* Wait for status bit 3 to CLEAR (transfer complete) */
    while ((*stat_reg & SPI_STATUS_BIT) != 0) {
        if (--timeout == 0) break;  /* Timeout */
    }
}

/**
 * spi_clk_low_wait — Set SPI clock LOW and wait for data ready.
 *
 * ROM address: 0x9DE
 * Size: 30 bytes
 *
 * Clears bit 0 of the clock register (0xFFFFE401) to LOW.
 * Waits for bit 3 (status) to SET, indicating data is ready.
 * Timeout after 4000 iterations (0xFA0).
 *
 * @param clk_reg  Pointer to clock/control register
 * @param stat_reg Pointer to status register
 */
void spi_clk_low_wait(volatile uint8_t *clk_reg, volatile uint8_t *stat_reg)
{
    uint32_t timeout = SPI_TIMEOUT_ITERATIONS;

    /* Clear clock LOW: AND ~bit 0 */
    *clk_reg &= ~SPI_CLK_BIT;

    /* Wait for status bit 3 to SET (data ready) */
    while ((*stat_reg & SPI_STATUS_BIT) == 0) {
        if (--timeout == 0) break;  /* Timeout */
    }
}

/**
 * spi_write_bit — Write a single bit via SPI bit-bang.
 *
 * Sets clock LOW, writes data bit to the data line, sets clock HIGH.
 * The data is read on the rising edge of the clock.
 *
 * @param bit  The bit value to write (0 or 1)
 */
void spi_write_bit(uint8_t bit)
{
    /* Set clock LOW */
    SPI_CLK_DATA_CTRL &= ~SPI_CLK_BIT;

    /* Write data bit */
    if (bit) {
        SPI_DATA_0 |= 0x0001;
    } else {
        SPI_DATA_0 &= ~0x0001;
    }

    /* Set clock HIGH (data latched on rising edge) */
    SPI_CLK_DATA_CTRL |= SPI_CLK_BIT;
}

/**
 * spi_read_bit — Read a single bit via SPI bit-bang.
 *
 * Sets clock LOW, reads data bit, sets clock HIGH.
 * The data is stable after the falling edge.
 *
 * @return The bit value read (0 or 1)
 */
uint8_t spi_read_bit(void)
{
    uint8_t bit;

    /* Set clock LOW */
    SPI_CLK_DATA_CTRL &= ~SPI_CLK_BIT;

    /* Read data bit */
    bit = (SPI_DATA_0 & 0x0001) ? 1 : 0;

    /* Set clock HIGH */
    SPI_CLK_DATA_CTRL |= SPI_CLK_BIT;

    return bit;
}

/**
 * spi_write_byte — Write a byte via SPI (MSB first).
 *
 * Standard SPI byte transfer: MSB first, 8 clock cycles.
 *
 * @param data  The byte to write
 */
void spi_write_byte(uint8_t data)
{
    for (int i = 7; i >= 0; i--) {
        spi_write_bit((data >> i) & 1);
    }
}

/**
 * spi_read_byte — Read a byte via SPI (MSB first).
 *
 * Standard SPI byte receive: MSB first, 8 clock cycles.
 *
 * @return The byte read
 */
uint8_t spi_read_byte(void)
{
    uint8_t data = 0;

    for (int i = 7; i >= 0; i--) {
        if (spi_read_bit()) {
            data |= (1 << i);
        }
    }

    return data;
}

/* ====================================================================== */
/*  EEPROM Core Operations                                                */
/* ====================================================================== */

/**
 * eeprom_read_byte — Read a single byte from EEPROM.
 *
 * ROM address: part of spi_eeprom_read (0x49700)
 *
 * Sequence:
 *   1. CS low
 *   2. Send READ command (0x03)
 *   3. Send address byte
 *   4. Clock in data byte
 *   5. CS high
 *
 * @param addr  EEPROM address (0-255)
 * @return The byte at the given address
 */
uint8_t eeprom_read_byte(uint8_t addr)
{
    uint8_t data;

    spi_cs_low();
    spi_write_byte(SPI_CMD_READ);
    spi_write_byte(addr);
    data = spi_read_byte();
    spi_cs_high();

    return data;
}

/**
 * eeprom_write_byte — Write a single byte to EEPROM.
 *
 * ROM address: part of spi_eeprom_write (0x496BA)
 *
 * Sequence:
 *   1. CS low, send WREN (0x06), CS high
 *   2. CS low, send WRITE (0x02), send address, send data
 *   3. CS high
 *   4. Wait for write cycle (5-10ms typical)
 *
 * @param addr  EEPROM address (0-255)
 * @param data  The byte to write
 */
void eeprom_write_byte(uint8_t addr, uint8_t data)
{
    /* Step 1: Write Enable */
    spi_cs_low();
    spi_write_byte(SPI_CMD_WREN);
    spi_cs_high();

    /* Step 2: Write data */
    spi_cs_low();
    spi_write_byte(SPI_CMD_WRITE);
    spi_write_byte(addr);
    spi_write_byte(data);
    spi_cs_high();

    /* Step 3: Wait for write cycle to complete
     * The EEPROM is busy during the write cycle.
     * Status can be polled via RDSR command.
     * Typical write cycle: 5ms max */
    delay_loop(5000);
}

/**
 * eeprom_read_sector — Read a sector (page) from EEPROM.
 *
 * @param addr  Start address (sector-aligned)
 * @param buf   Destination buffer
 * @param len   Number of bytes to read
 */
void eeprom_read_sector(uint8_t addr, uint8_t *buf, uint8_t len)
{
    spi_cs_low();
    spi_write_byte(SPI_CMD_READ);
    spi_write_byte(addr);

    for (uint8_t i = 0; i < len; i++) {
        buf[i] = spi_read_byte();
    }

    spi_cs_high();
}

/**
 * eeprom_write_sector — Write a sector (page) to EEPROM.
 *
 * @param addr  Start address (page-aligned)
 * @param buf   Source buffer
 * @param len   Number of bytes to write
 */
void eeprom_write_sector(uint8_t addr, const uint8_t *buf, uint8_t len)
{
    /* Write Enable */
    spi_cs_low();
    spi_write_byte(SPI_CMD_WREN);
    spi_cs_high();

    /* Write page */
    spi_cs_low();
    spi_write_byte(SPI_CMD_WRITE);
    spi_write_byte(addr);

    for (uint8_t i = 0; i < len; i++) {
        spi_write_byte(buf[i]);
    }

    spi_cs_high();

    /* Wait for write cycle */
    delay_loop(5000);
}

/**
 * eeprom_erase_sector — Erase a sector (64 bytes) of EEPROM.
 *
 * ROM address: part of flash_erase (0x4988C)
 *
 * Sequence:
 *   1. CS low, send WREN (0x06), CS high
 *   2. CS low, send SECTOR_ERASE (0x20), send address
 *   3. CS high
 *   4. Wait for erase cycle (50-300ms typical)
 *
 * @param addr  Sector address (sector-aligned)
 */
void eeprom_erase_sector(uint8_t addr)
{
    /* Write Enable */
    spi_cs_low();
    spi_write_byte(SPI_CMD_WREN);
    spi_cs_high();

    /* Sector Erase */
    spi_cs_low();
    spi_write_byte(SPI_CMD_SECTOR_ERASE);
    spi_write_byte(addr);
    spi_cs_high();

    /* Wait for erase cycle (longer than write) */
    delay_loop(50000);
}

/* ====================================================================== */
/*  EEPROM Validation and RAM Staging                                     */
/* ====================================================================== */

/**
 * eeprom_read_validate — Read and validate EEPROM data staged in RAM.
 *
 * ROM address: 0x450
 * Size: ~28 bytes
 *
 * Reads 8 bytes from RAM buffer at 0xFFFFDFE4.
 * Validates marker byte at offset 8 (must be 0x55).
 * If valid: copies 8 bytes to destination, writes 0xAA to marker (consumed).
 *
 * @param dest  Destination buffer (8 bytes)
 * @return 1 if valid data was copied, -1 if marker invalid
 */
int eeprom_read_validate(uint8_t *dest)
{
    volatile uint8_t *buf = (volatile uint8_t *)EEPROM_RAM_BUF_A;

    /* Check validity marker at offset 8 */
    if (buf[8] != EEPROM_VALID_MARKER) {
        return -1;  /* Invalid marker */
    }

    /* Copy 8 bytes from buffer to destination */
    for (int i = 0; i < 8; i++) {
        dest[i] = buf[i];
    }

    /* Mark as consumed (write 0xAA) */
    buf[8] = EEPROM_CONSUMED_MARKER;

    return 1;  /* Success */
}

/**
 * is_eeprom_valid — Check if EEPROM data is valid in RAM.
 *
 * ROM address: 0x624
 * Size: 18 bytes
 *
 * Checks the validity marker at 0xFFFFDFEC.
 * Returns 1 if marker == 0x55, 0 otherwise.
 *
 * @return 1 if valid, 0 otherwise
 */
int is_eeprom_valid(void)
{
    volatile uint8_t *marker = (volatile uint8_t *)EEPROM_RAM_BUF_A_MARKER;

    if (*marker == EEPROM_VALID_MARKER) {
        return 1;
    }
    return 0;
}

/**
 * eeprom_commit_to_ram — Copy data to EEPROM staging area in RAM.
 *
 * Copies source data to the staging buffer at 0xFFFFC2FE.
 * Also stores an inverted copy at 0xFFFFC3FE for verification.
 * Disables interrupts during copy for atomicity.
 *
 * @param src   Source data
 * @param len   Length to copy (max 256)
 */
void eeprom_commit_to_ram(const uint8_t *src, uint8_t len)
{
    volatile uint8_t *staging = (volatile uint8_t *)EEPROM_STAGING_BASE;
    volatile uint8_t *verify  = (volatile uint8_t *)EEPROM_VERIFY_BASE;

    /* Disable interrupts for atomic copy */
    uint32_t saved_sr = disable_interrupts();

    /* Copy data to staging area */
    for (uint8_t i = 0; i < len; i++) {
        staging[i] = src[i];
        verify[i]  = src[i] ^ 0xFF;  /* Inverted copy for verification */
    }

    /* Re-enable interrupts */
    restore_interrupts(saved_sr);
}
