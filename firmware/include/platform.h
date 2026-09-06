/*
 * platform.h — RX-8 ECU Hardware Platform Definitions (SH-2E / SH7055)
 *
 * Register addresses derived from reverse engineering of ROM 60E1D400.
 * All addresses are memory-mapped I/O or RAM locations used by the firmware.
 *
 * Source: IDA analysis reports (rtos_analysis_report, serial_analysis_report,
 *         eeprom_analysis_report, can_analysis_report, engine_rotary_report)
 */

#ifndef PLATFORM_H
#define PLATFORM_H

#include <stdint.h>

/* ====================================================================== */
/*  SH-2E CPU Registers (simulated on host)                               */
/* ====================================================================== */

/* Status Register (SR) bits */
#define SR_BL_BIT       0       /* Block interrupt bit */
#define SR_MD_BIT       30      /* SR.BLOCK is bit 0 in packed SH-2 SR */
#define SR_IMASK_MASK   0x000000F0  /* Interrupt mask bits (bits 4-7) */
#define SR_IMASK_FULL   0x000000E0  /* All interrupts masked (level 0xE << 4) */

/* ====================================================================== */
/*  Watchdog Timer (WDT) Registers                                        */
/* ====================================================================== */

#define WDT_TCSR        (*(volatile uint16_t *)0xFFFFEC10)  /* Timer Control/Status */
#define WDT_RSTCSR      (*(volatile uint16_t *)0xFFFFEC12)  /* Reset Control */
#define WDT_TCSR_MAGIC  0x5A00  /* Magic to write to TCSR (clear overflow) */
#define WDT_RSTCSR_MAGIC 0x5A1F /* Magic to write to RSTCSR */
#define WDT_FEED_VALUE  0xA53C  /* Watchdog feed value (stops timer) */

/* ====================================================================== */
/*  Port Function Controller (PFC) Registers                              */
/* ====================================================================== */

/* Port configuration registers (GPIO init at 0x8F6 writes these) */
#define PFC_PMR1        (*(volatile uint16_t *)0xFFFFF720)
#define PFC_PMR2        (*(volatile uint16_t *)0xFFFFF722)
#define PFC_PMR3        (*(volatile uint16_t *)0xFFFFF724)
#define PFC_PDR1        (*(volatile uint16_t *)0xFFFFF726)

/* Port 2 registers */
#define PFC_PMR2_BASE   (*(volatile uint16_t *)0xFFFFF730)
#define PFC_PMR2_1      (*(volatile uint16_t *)0xFFFFF732)
#define PFC_PMR2_2      (*(volatile uint16_t *)0xFFFFF734)
#define PFC_PMR2_3      (*(volatile uint16_t *)0xFFFFF736)

/* Port 3 registers */
#define PFC_PMR3_BASE   (*(volatile uint16_t *)0xFFFFF738)
#define PFC_PMR3_1      (*(volatile uint16_t *)0xFFFFF73A)
#define PFC_PMR3_2      (*(volatile uint16_t *)0xFFFFF73C)
#define PFC_PMR3_3      (*(volatile uint16_t *)0xFFFFF73E)

/* Port 4 registers */
#define PFC_PMR4_BASE   (*(volatile uint16_t *)0xFFFFF740)
#define PFC_PMR4_1      (*(volatile uint16_t *)0xFFFFF742)
#define PFC_PMR4_2      (*(volatile uint16_t *)0xFFFFF744)
#define PFC_PMR4_3      (*(volatile uint16_t *)0xFFFFF746)

/* Port 5 registers */
#define PFC_PMR5_BASE   (*(volatile uint16_t *)0xFFFFF748)
#define PFC_PMR5_1      (*(volatile uint16_t *)0xFFFFF74A)
#define PFC_PMR5_2      (*(volatile uint16_t *)0xFFFFF74C)
#define PFC_PMR5_3      (*(volatile uint16_t *)0xFFFFF74E)

/* Port 6 registers */
#define PFC_PMR6_BASE   (*(volatile uint16_t *)0xFFFFF750)
#define PFC_PMR6_1      (*(volatile uint16_t *)0xFFFFF752)
#define PFC_PMR6_2      (*(volatile uint16_t *)0xFFFFF754)

/* Port 7 registers */
#define PFC_PMR7_BASE   (*(volatile uint16_t *)0xFFFFF756)
#define PFC_PMR7_1      (*(volatile uint16_t *)0xFFFFF758)
#define PFC_PMR7_2      (*(volatile uint16_t *)0xFFFFF75A)
#define PFC_PMR7_3      (*(volatile uint16_t *)0xFFFFF75C)

/* Port 8 registers */
#define PFC_PMR8_BASE   (*(volatile uint16_t *)0xFFFFF75E)

/* Port A registers */
#define PFC_PMR10_BASE  (*(volatile uint16_t *)0xFFFFF760)
#define PFC_PMR10_1     (*(volatile uint16_t *)0xFFFFF762)
#define PFC_PMR10_2     (*(volatile uint16_t *)0xFFFFF764)

/* Port B registers */
#define PFC_PMR11_BASE  (*(volatile uint16_t *)0xFFFFF766)
#define PFC_PMR11_1     (*(volatile uint16_t *)0xFFFFF768)
#define PFC_PMR11_2     (*(volatile uint16_t *)0xFFFFF76A)
#define PFC_PMR11_3     (*(volatile uint16_t *)0xFFFFF76C)

/* Port C registers */
#define PFC_PMR12_BASE  (*(volatile uint16_t *)0xFFFFF770)
#define PFC_PMR12_1     (*(volatile uint16_t *)0xFFFFF772)
#define PFC_PMR12_2     (*(volatile uint16_t *)0xFFFFF774)
#define PFC_PMR12_3     (*(volatile uint16_t *)0xFFFFF776)
#define PFC_PMR12_4     (*(volatile uint16_t *)0xFFFFF778)

/* ====================================================================== */
/*  SPI / EEPROM Interface Registers (Bit-Banged via CAN Controller)      */
/* ====================================================================== */

/* SPI is bit-banged using GPIO pins mapped through CAN controller space.
 * The SPI_CLK_DATA_CTRL register at 0xFFFFE401 controls clock (bit 0)
 * and provides transfer status (bit 3). */
#define SPI_CLK_DATA_CTRL   (*(volatile uint8_t *)0xFFFFE401)
#define SPI_CLK_BIT         0x01    /* Clock output: 1=HIGH, 0=LOW */
#define SPI_STATUS_BIT      0x08    /* Transfer status: 1=busy, 0=ready */

#define SPI_CONTROL         (*(volatile uint16_t *)0xFFFFE402)
#define SPI_CONFIG          (*(volatile uint16_t *)0xFFFFE404)
#define SPI_DATA_0          (*(volatile uint16_t *)0xFFFFE406)
#define SPI_DATA_1          (*(volatile uint16_t *)0xFFFFE408)
#define SPI_DATA_2          (*(volatile uint16_t *)0xFFFFE40A)

#define SPI_CHANNEL_CONFIG  (*(volatile uint16_t *)0xFFFFE414)
#define SPI_CHANNEL_CTRL    (*(volatile uint16_t *)0xFFFFE416)
#define SPI_CHANNEL_STATUS  (*(volatile uint16_t *)0xFFFFE41C)
#define SPI_CHANNEL_MODE    (*(volatile uint16_t *)0xFFFFE41E)
#define SPI_PIN_CONFIG      (*(volatile uint16_t *)0xFFFFE428)
#define SPI_BUFFER_0        (*(volatile uint16_t *)0xFFFFE4B0)
#define SPI_BUFFER_1        (*(volatile uint16_t *)0xFFFFE4B8)

/* SPI command bytes (standard EEPROM) */
#define SPI_CMD_READ        0x03    /* Read data */
#define SPI_CMD_WRITE       0x02    /* Write data */
#define SPI_CMD_WREN        0x06    /* Write enable */
#define SPI_CMD_WRSR        0x01    /* Write status register */
#define SPI_CMD_RDSR        0x05    /* Read status register */
#define SPI_CMD_SECTOR_ERASE 0x20   /* Sector erase (4KB) */
#define SPI_CMD_BLOCK_ERASE 0xD8    /* Block erase (64KB) */
#define SPI_CMD_CHIP_ERASE  0xC7    /* Chip erase */

/* SPI timeout */
#define SPI_TIMEOUT_ITERATIONS  4000 /* 0xFA0 */

/* ====================================================================== */
/*  CAN Controller Registers (HCAN)                                       */
/* ====================================================================== */

/* HCAN peripheral base and mailbox registers */
#define HCAN_PERIPH_BASE     0xFFFFE402
#define HCAN_MBOX_OFFSET     (*(volatile uint16_t *)0xFFFFE406)
#define HCAN_MBOX_READY      (*(volatile uint16_t *)0xFFFFE40A)
#define HCAN_MBOX_STATUS     (*(volatile uint16_t *)0xFFFFE40E)
#define HCAN_MBOX_DATA_READY (*(volatile uint16_t *)0xFFFFE41A)

/* HCAN enable/reset */
#define HCAN_ENABLE_VALUE    0x803E

/* ====================================================================== */
/*  ATU (Advanced Timer Unit) Registers                                   */
/* ====================================================================== */

/* ATU serial interface registers (primary diagnostic interface) */
#define ATU_STATUS       (*(volatile uint16_t *)0xFFFFE406)
#define ATU_DATA         (*(volatile uint16_t *)0xFFFFE40A)
#define ATU_RX_STATUS    (*(volatile uint16_t *)0xFFFFE40E)
#define ATU_ERROR_CLEAR  (*(volatile uint16_t *)0xFFFFE41A)
#define ATU_BUFFER_0     (*(volatile uint16_t *)0xFFFFE4B0)
#define ATU_BUFFER_1     (*(volatile uint16_t *)0xFFFFE4B8)

/* ATU status bits */
#define ATU_STATUS_BUSY  0x0200  /* Bit 9: busy */
#define ATU_STATUS_READY 0x0080  /* Bit 7: ready */
#define ATU_RX_DATA_AVAIL 0x0100 /* Bit 8: data available */
#define ATU_RX_STATUS_MASK 0x0060 /* Bits 5-6: status */
#define ATU_ERROR_FLAG   0x0060  /* Bits 5-6: error */

/* ATU timer register offsets (for bit-bang serial) */
#define ATU_BASE        0xFFFFF700  /* ATU register block base */
#define ATU_TSTR_OFFSET 0x0000  /* Timer start/stop control */
#define ATU_TCR0_OFFSET 0x0010  /* Timer control register 0 */
#define ATU_TCR1_OFFSET 0x0020  /* Timer control register 1 */
#define ATU_TCR2_OFFSET 0x0030  /* Timer control register 2 */
#define ATU_TIOR0_OFFSET 0x0040 /* Timer I/O control 0 */
#define ATU_TIOR1_OFFSET 0x0050 /* Timer I/O control 1 */
#define ATU_TIER0_OFFSET 0x0060 /* Timer interrupt enable 0 */
#define ATU_TIER1_OFFSET 0x0070 /* Timer interrupt enable 1 */
#define ATU_TGR0_OFFSET 0x0080  /* Timer general register 0 */
#define ATU_TGR1_OFFSET 0x0090  /* Timer general register 1 */
#define ATU_TGR2_OFFSET 0x00A0  /* Timer general register 2 */
#define ATU_TISRA_OFFSET 0x00B0 /* Timer interrupt status A */

/* ATU prescaler values */
#define ATU_PRESCALER_DISABLE   0x0000
#define ATU_PRESCALER_DIV4      0x0001
#define ATU_PRESCALER_DIV16     0x0002
#define ATU_PRESCALER_DIV64     0x0003

/* ====================================================================== */
/*  SCI4 (Serial Communication Interface) Registers                      */
/* ====================================================================== */

#define SCI4_SCSMR    (*(volatile uint16_t *)0xFFFFF020)  /* Mode Register */
#define SCI4_SCSCR    (*(volatile uint16_t *)0xFFFFF022)  /* Control Register */
#define SCI4_SCTDR    (*(volatile uint8_t  *)0xFFFFF023)  /* Transmit Data */
#define SCI4_SCSSR    (*(volatile uint16_t *)0xFFFFF024)  /* Status Register */
#define SCI4_SCRDR    (*(volatile uint8_t  *)0xFFFFF025)  /* Receive Data */

/* ====================================================================== */
/*  RTOS Data Structures                                                  */
/* ====================================================================== */

/* Task queue: 100 entries x 8 bytes at 0xFFFFD4E0 */
#define TASK_QUEUE_BASE     0xFFFFD4E0
#define TASK_QUEUE_SIZE     100
#define TASK_QUEUE_ENTRY_SIZE 8

/* Queue indices */
#define TASK_QUEUE_WRITE_IDX  (*(volatile uint16_t *)0xFFFFDFB4)
#define TASK_QUEUE_READ_IDX   (*(volatile uint16_t *)0xFFFFDFB6)

/* RTOS control block at 0xFFFF72B0 */
#define RTOS_CB_BASE        0xFFFF72B0

/* RTOS control block layout */
struct rtos_control_block {
    uint8_t  task_type;         /* +0x00: current task type */
    uint8_t  current_task_id;   /* +0x01: current task ID */
    uint8_t  reserved_02;       /* +0x02: reserved */
    uint8_t  completion_counter; /* +0x03: completion counter */
    uint16_t status_flags;      /* +0x04: status flags */
    uint16_t task_marker;       /* +0x06: task marker (0xFFFF = direct) */
    uint32_t saved_sp;          /* +0x08: saved stack pointer / context counter */
    uint32_t saved_context_sp;  /* +0x0C: saved context stack pointer */
    uint32_t saved_sr;          /* +0x10: saved status register */
    uint32_t task_descriptor_ptr; /* +0x14: task descriptor pointer */
    uint32_t task_table_base_ptr; /* +0x18: task table base pointer */
};

#define RTOS_CB ((volatile struct rtos_control_block *)RTOS_CB_BASE)

/* ====================================================================== */
/*  Serial Communication RAM Buffers                                      */
/* ====================================================================== */

/* Queue state byte */
#define SERIAL_QUEUE_STATE    (*(volatile uint8_t *)0xFFFFDFA8)

/* Direct TX buffer at 0xFFFFDFAC */
#define SERIAL_TX_DIRECT_BASE 0xFFFFDFAC

/* Queue buffer at 0xFFFFDFF0 (with sync at offset 8) */
#define SERIAL_QUEUE_BASE     0xFFFFDFF0

/* Serial sync protocol bytes */
#define SERIAL_SYNC_READY     0xAA  /* Queue slot ready for new message */
#define SERIAL_SYNC_CONSUMED  0x55  /* Message written, slot consumed */

/* RX buffer addresses for each channel */
#define SERIAL_RX_BUF_CH0     0xFFFFFEC  /* Channel 0 RX buffer */
#define SERIAL_RX_BUF_CH1     0xFFFFF8   /* Channel 1 RX buffer */
#define SERIAL_RX_BUF_CH2     0xFFFFF4   /* Channel 2 RX buffer */

/* Channel ID byte */
#define SERIAL_CHANNEL_ID     (*(volatile uint8_t *)0xFE0)

/* ====================================================================== */
/*  EEPROM RAM Control Structures                                         */
/* ====================================================================== */

/* EEPROM staging buffer: 256 bytes at 0xFFFFC2FE */
#define EEPROM_STAGING_BASE   0xFFFFC2FE
#define EEPROM_STAGING_SIZE   256

/* EEPROM inverted copy for verification */
#define EEPROM_VERIFY_BASE    0xFFFFC3FE

/* EEPROM RAM validation buffers */
#define EEPROM_RAM_BUF_A      0xFFFFDFE4
#define EEPROM_RAM_BUF_A_MARKER 0xFFFFDFEC  /* 0x55=valid, 0xAA=consumed */
#define EEPROM_RAM_BUF_B      0xFFFFDFF0

/* EEPROM control flags */
#define EEPROM_BUSY_FLAG      (*(volatile uint8_t *)0xFFFFC297)
#define EEPROM_WRITE_PENDING  (*(volatile uint8_t *)0xFFFFC29B)
#define EEPROM_WRITE_IDX      (*(volatile uint8_t *)0xFFFFC29C)
#define EEPROM_WRITE_STATUS   (*(volatile uint8_t *)0xFFFFC29D)
#define EEPROM_WRITE_ACTIVE   (*(volatile uint8_t *)0xFFFFC29E)
#define EEPROM_COMMIT_REQUEST (*(volatile uint8_t *)0xFFFFC2D1)
#define EEPROM_COMMIT_DONE    (*(volatile uint8_t *)0xFFFFC2D2)

/* EEPROM validation markers */
#define EEPROM_VALID_MARKER   0x55  /* Buffer contains valid data */
#define EEPROM_CONSUMED_MARKER 0xAA /* Buffer has been consumed */

/* ====================================================================== */
/*  DTC (Diagnostic Trouble Codes) RAM                                    */
/* ====================================================================== */

#define DTC_ENABLE_FLAG       (*(volatile uint8_t *)0xFFFF8788)
#define DTC_SET_FLAG          (*(volatile uint16_t *)0xFFFF875C)
#define DTC_CLEAR_FLAG        (*(volatile uint16_t *)0xFFFF875E)
#define DTC_ACTIVE_CODE       (*(volatile uint16_t *)0xFFFF8920)
#define DTC_SLOT_INDEX        (*(volatile uint16_t *)0xFFFF8D70)
#define DTC_TYPE_CURRENT      (*(volatile uint16_t *)0xFFFF8D74)

/* DTC record layout */
#define DTC_PRIMARY_TABLE     0xFFFF8928  /* 21 entries x 52 bytes */
#define DTC_BACKUP_TABLE      0xFFFF8EA0  /* 8 entries x 40 bytes */
#define DTC_HANDLER_CONTEXT   0xFFFF87D8  /* 21 entries x 16 bytes */

/* DTC severity levels */
#define DTC_SEV_LOW           1
#define DTC_SEV_HIGH          2

/* ====================================================================== */
/*  Boot / Reset Magic Values                                             */
/* ====================================================================== */

#define BOOT_MAGIC_VALUE      0x5AA5A55A  /* Warm boot magic */
#define BOOT_MAGIC_LOCATION   (*(volatile uint32_t *)0xFFFFDFFC)

/* Reset vector table */
#define RESET_VECTOR_DEFAULT  0x06C8     /* Default reset vector (main_task_dispatcher) */
#define RESET_VECTOR_ALT      0x1000     /* Alternate reset vector */
#define RESET_VECTOR_MAIN     0xD49C     /* Application entry (main_entry) */

/* ====================================================================== */
/*  Interrupt / SR Control Helpers                                        */
/* ====================================================================== */

/* Save SR, disable interrupts (param: 0x90) */
static inline uint32_t disable_interrupts(void) {
    /* On real SH-2E: stc sr,r0; and #0xF0,r0; or #imm,r0; ldc r0,sr */
    /* Host simulation: just return current SR value */
    (void)0; /* placeholder for actual SR read */
    return 0;
}

/* Restore SR (re-enable interrupts) */
static inline void restore_interrupts(uint32_t saved_sr) {
    (void)saved_sr; /* placeholder for actual SR write */
}

/* ====================================================================== */
/*  Memory Access Helpers                                                 */
/* ====================================================================== */

/* Big-endian 32-bit value from 4 bytes */
static inline uint32_t be32_from_bytes(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8)  | ((uint32_t)p[3]);
}

/* Big-endian 16-bit value from 2 bytes */
static inline uint16_t be16_from_bytes(const uint8_t *p) {
    return ((uint16_t)p[0] << 8) | (uint16_t)p[1];
}

/* Simple additive checksum with carry folding */
static inline uint8_t calc_checksum(const uint8_t *data, uint32_t len) {
    uint32_t sum = 0;
    for (uint32_t i = 0; i < len; i++) {
        sum += data[i];
    }
    /* Fold high byte into low byte */
    while (sum >> 8) {
        sum = (sum & 0xFF) + (sum >> 8);
    }
    return (uint8_t)(sum & 0xFF);
}

/* Delay loop (approximate, calibrated to SH-2E clock) */
static inline void delay_loop(uint32_t count) {
    for (volatile uint32_t i = 0; i < count; i++) {
        __asm__ __volatile__("nop");
    }
}

/* ====================================================================== */
/*  Interrupt Controller (INTC) Helpers                                   */
/* ====================================================================== */

/* INTC register at 0xFFFFF02E (SH-2E interrupt enable) */
#define INTC_REGISTER   (*(volatile uint16_t *)0xFFFFF02E)

/* Write to INTC register (enables/disables interrupt lines) */
static inline void intc_reg_write(uint16_t value) {
    INTC_REGISTER = value;
}

/* ====================================================================== */
/*  NULL Definition (freestanding)                                        */
/* ====================================================================== */

#ifndef NULL
#define NULL ((void *)0)
#endif

#endif /* PLATFORM_H */
