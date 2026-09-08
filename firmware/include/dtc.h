/*
 * dtc.h — RX-8 ECU DTC (Diagnostic Trouble Codes) Subsystem Definitions
 *
 * 1:1 firmware reconstruction of the DTC management subsystem for the
 * Mazda RX-8 Renesis 13B-MSP rotary engine ECU (SH-2E / SH7055).
 *
 * DTC storage:
 *   Primary table:  21 entries × 52 bytes (stride 0x34) at 0xFFFF8928
 *   Backup table:   8 entries × 40 bytes (stride 0x28) at 0xFFFF8EA0
 *   Handler context: 21 entries × 16 bytes (stride 0x10) at 0xFFFF87D8
 *
 * DTC set path:
 *   fault_detection (0x271B8/0x2817C/0x28E10)
 *     → detection_gate (0x25E36)
 *     → debounce_counter (0x43760)
 *     → dtc_set_flag (0x46780)
 *     → dtc_freezeframe_store (0x467BE)
 *     → dtc_state_machine (0x61550)
 *
 * DTC clear path:
 *   SID 0x14 → obd_sid14_clearDTC (0x562E8)
 *   group 0xFF00 = clear all DTCs
 *
 * DTC read path:
 *   SID 0x18 → obd_sid18_readDTCInfo (0x587EC)
 *   SID 0x12 → obd_sid12_readDTCByStatus (0x5BAD0)
 *
 * Freeze-frame: 40 bytes at DTC+0x0A, captured by dtc_snapshot_manager (0x3B3BC)
 *
 * Source: dtc_analysis_report.txt, IDA session ae00d360
 */

#ifndef DTC_H
#define DTC_H

#include <stdint.h>
#include "platform.h"

/* ====================================================================== */
/*  DTC Storage Layout                                                     */
/* ====================================================================== */

/* Primary DTC table: 21 entries × 52 bytes (0x34) at 0xFFFF8928 */
#define DTC_PRIMARY_TABLE_BASE  0xFFFF8928
#define DTC_PRIMARY_ENTRY_SIZE  0x34    /* 52 bytes per record */
#define DTC_PRIMARY_MAX_SLOTS   21

/* Backup DTC table: 8 entries × 40 bytes (0x28) at 0xFFFF8EA0 */
#define DTC_BACKUP_TABLE_BASE   0xFFFF8EA0
#define DTC_BACKUP_ENTRY_SIZE   0x28    /* 40 bytes per record */
#define DTC_BACKUP_MAX_SLOTS    8

/* Handler context table: 21 entries × 16 bytes (0x10) at 0xFFFF87D8 */
#define DTC_HANDLER_CTX_BASE    0xFFFF87D8
#define DTC_HANDLER_CTX_SIZE    0x10    /* 16 bytes per entry */
#define DTC_HANDLER_CTX_MAX     21

/* ====================================================================== */
/*  Primary DTC Record Layout (52 bytes)                                   */
/* ====================================================================== */

/* Record at base + (slot * 0x34) */
#define DTC_REC_CODE_OFFSET     0x00    /* uint16: DTC internal code (0x02-0x4C) */
#define DTC_REC_FLAGS1_OFFSET   0x02    /* uint16: status/flags word 1 */
#define DTC_REC_FLAGS2_OFFSET   0x04    /* uint16: status/flags word 2 */
#define DTC_REC_TYPE_OFFSET     0x06    /* uint8: ROM status byte (bit7=confirmed, bit6=failed; IDA_ANALYSIS.md:707).
                                         * Now written by the dtc_state_machine SET path (N3). */
#define DTC_REC_SEVERITY_OFFSET 0x07    /* uint8: Severity (0x80=confirmed, 0xC0=confirmed+failed) */
#define DTC_REC_AGING_OFFSET    0x08    /* uint8: Aging counter / sub-status */
#define DTC_REC_FLAGS3_OFFSET   0x09    /* uint8: Firmware-local working flags (NOT ROM-documented:
                                         * the IDA record layout jumps +0x07→+0x0A, so +0x09 has
                                         * no ROM provenance; used for TEST_FAILED/PENDING bits). */
#define DTC_REC_FREEZE_OFFSET   0x0A    /* uint8[40]: Freeze-frame / snapshot data */
#define DTC_REC_TOTAL_SIZE      0x34    /* 52 bytes */

/* ====================================================================== */
/*  Backup DTC Record Layout (40 bytes)                                    */
/* ====================================================================== */

/* Record at base + (slot * 0x28) */
#define DTC_BK_CODE_OFFSET      0x00    /* uint16: DTC code (0xFFFF = empty) */
#define DTC_BK_DATA_OFFSET      0x02    /* uint8[30]: Status/timestamp data */
#define DTC_BK_CODE2_OFFSET     0x20    /* uint16: Copy of DTC code (invalid marker) */
#define DTC_BK_EXTRA_OFFSET     0x22    /* uint8[5]: Additional status */
#define DTC_BK_VALID_OFFSET     0x27    /* uint8: Validity marker (0xA7 = valid) */
#define DTC_BK_TOTAL_SIZE       0x28    /* 40 bytes */

/* ====================================================================== */
/*  DTC Status and Control RAM                                             */
/* ====================================================================== */

/* DTC enable flag (redundant-pair checksummed) */
#define DTC_ENABLE_FLAG_ADDR    0xFFFF8788

/* DTC set/clear flag pair */
#define DTC_SET_FLAG_ADDR       0xFFFF875C
#define DTC_CLEAR_FLAG_ADDR     0xFFFF875E

/* DTC processing lock */
#define DTC_PROCESSING_LOCK     0xFFFF87B4

/* Current active DTC code */
#define DTC_ACTIVE_CODE_ADDR    0xFFFF8920

/* Current DTC slot index */
#define DTC_SLOT_INDEX_ADDR     0xFFFF8D70
#define DTC_TYPE_CURRENT_ADDR   0xFFFF8D74

/* DTC slot counter (primary table) */
#define DTC_SLOT_COUNT_ADDR     0xFFFF8D6C

/* DTC backup slot counter */
#define DTC_BK_COUNT_ADDR       0xFFFF8FB8

/* DTC severity lookup table (ROM) */
#define DTC_SEVERITY_TABLE_ROM  0x7E2AC

/* DTC type dispatch table (ROM) */
#define DTC_TYPE_TABLE_ROM      0x5F7F8

/* ====================================================================== */
/*  DTC Status Bits                                                        */
/* ====================================================================== */

#define DTC_STATUS_CONFIRMED    0x80    /* Bit 7: DTC confirmed */
#define DTC_STATUS_FAILED       0x40    /* Bit 6: DTC currently failing */
#define DTC_STATUS_PENDING      0x20    /* Bit 5: DTC pending (current cycle) */
#define DTC_STATUS_TEST_FAILED  0x10    /* Bit 4: Test failed this cycle */
#define DTC_STATUS_TEST_NOT_RUN 0x08    /* Bit 3: Test not completed */

/* ====================================================================== */
/*  DTC Severity Levels                                                    */
/* ====================================================================== */

#define DTC_SEV_LOW             1       /* Low severity */
#define DTC_SEV_HIGH            2       /* High severity */
#define DTC_SEV_NONE            0       /* No severity / disabled */

/* ====================================================================== */
/*  DTC Group Constants                                                    */
/* ====================================================================== */

#define DTC_GROUP_ALL           0xFF00  /* Clear all DTCs */
#define DTC_GROUP_MAX           0x00FF  /* Maximum group number */

/* ====================================================================== */
/*  DTC Handler Context Layout (16 bytes)                                  */
/* ====================================================================== */

/* Record at base + (slot * 0x10) */
#define DTC_CTX_CODE_OFFSET     0x00    /* uint16: DTC code ID */
#define DTC_CTX_STATE_OFFSET    0x02    /* uint16: Handler state */
#define DTC_CTX_PTR_OFFSET      0x04    /* uint32: Fault condition pointer / handler data */
#define DTC_CTX_TYPE_OFFSET     0x08    /* uint8: DTC type byte */
#define DTC_CTX_SEVERITY_OFFSET 0x09    /* uint8: Severity level */
#define DTC_CTX_AGING_THR_OFFSET 0x0A   /* uint8: Aging threshold */
#define DTC_CTX_AGING_CNT_OFFSET 0x0B   /* uint8: Aging counter */
#define DTC_CTX_EXTRA_OFFSET    0x0C    /* uint8[4]: Additional handler state */

/* ====================================================================== */
/*  DTC Core Function Prototypes                                           */
/* ====================================================================== */

/**
 * dtc_init — Initialize DTC subsystem.
 *
 * Clears DTC flags, validates primary and backup tables,
 * and initializes handler context entries.
 */
void dtc_init(void);

/**
 * dtc_set_flag — Set a DTC fault flag.
 * ROM address: 0x46780
 *
 * Checks DTC enable flag at 0xFFFF8788 == 1.
 * If enabled: writes set flag to 0xFFFF875C, clears 0xFFFF875E.
 *
 * @param dtc_code  DTC internal code (0x02-0x4C)
 */
void dtc_set_flag(uint16_t dtc_code);

/**
 * dtc_clear_flag — Clear a DTC fault flag.
 * ROM address: 0x467AA
 *
 * Clears both set/clear flags:
 *   [0xFFFF875C] = 0
 *   [0xFFFF875E] = 0
 */
void dtc_clear_flag(void);

/**
 * dtc_freezeframe_store — Store freeze-frame snapshot data.
 * ROM address: 0x467BE
 *
 * Captures engine state into +0x0A of DTC record (40 bytes).
 * Called after dtc_set_flag to preserve sensor data at fault time.
 *
 * @param dtc_code  DTC code to store snapshot for
 */
void dtc_freezeframe_store(uint16_t dtc_code);

/**
 * dtc_state_machine — DTC state transition handler.
 * ROM address: 0x61550
 *
 * Manages DTC state transitions (set/confirm/clear/aging).
 * Encodes status for CAN response.
 *
 * @param dtc_code  DTC code to process
 * @param mode      State machine mode (1=set, 2=confirm, 3=clear)
 */
void dtc_state_machine(uint16_t dtc_code, uint8_t mode);

/**
 * dtc_debounce_counter — DTC debounce counter.
 * ROM address: 0x43760
 *
 * Counter-based debounce with configurable thresholds.
 * Prevents false DTC triggers from transient faults.
 *
 * @param dtc_code  DTC code being debounced
 * @return Non-zero if debounce passes (fault confirmed)
 */
int dtc_debounce_counter(uint16_t dtc_code);

/**
 * dtc_find_worst_priority — Find highest priority DTC.
 * ROM address: 0x6115A
 *
 * Iterates 20 DTC slots, compares severity (lower byte = higher priority).
 * Returns worst DTC code + severity + status.
 *
 * @param status_mask  Status mask for filtering
 * @param out_code     Output: worst DTC code
 * @param out_severity Output: severity of worst DTC
 * @param out_status   Output: status of worst DTC
 * @return Number of DTCs matching mask
 */
int dtc_find_worst_priority(uint8_t status_mask, uint16_t *out_code,
                            uint8_t *out_severity, uint8_t *out_status);

/**
 * dtc_snapshot_manager — Capture engine state for freeze-frame.
 * ROM address: 0x3B3BC
 *
 * Captures RPM (0xFFFFB5B8), MAP, coolant temp, and other sensors.
 * Stores to 0xFFFFC5C4, 0xFFFFC5B6, 0xFFFFC12C.
 */
void dtc_snapshot_manager(void);

/**
 * dtc_read_full_status — Read full DTC status.
 * ROM address: 0x60FD2
 *
 * @param dtc_code  DTC code to read
 * @param out_buf   Output buffer (9 bytes minimum)
 * @return Number of bytes written to out_buf
 */
int dtc_read_full_status(uint16_t dtc_code, uint8_t *out_buf);

/* ====================================================================== */
/*  DTC UDS Service Handlers                                               */
/* ====================================================================== */

/**
 * obd_sid14_clearDTC — UDS SID 0x14 clear DTC handler.
 * ROM address: 0x562E8
 *
 * Handles diagnostic clear commands:
 *   Group 0xFF00 = clear ALL DTCs
 *   Other groups = NRC 0x31 (requestOutofRange)
 *
 * @param group_hi  High byte of DTC group
 * @param group_lo  Low byte of DTC group
 * @return 0 on success, negative NRC on failure
 */
int obd_sid14_clearDTC(uint8_t group_hi, uint8_t group_lo);

/**
 * obd_sid18_readDTCInfo — UDS SID 0x18 read DTC information.
 * ROM address: 0x587EC
 *
 * Sub-function 0x03: reportNumberOfDTCByStatusMask
 * Sub-function 0xFF: clear-then-report
 *
 * @param sub_func  Sub-function byte
 * @param status_mask  Status mask for filtering
 * @param out_buf   Output buffer for response
 * @return Response length, or negative NRC on failure
 */
int obd_sid18_readDTCInfo(uint8_t sub_func, uint8_t status_mask,
                          uint8_t *out_buf);

/**
 * obd_sid12_readDTCByStatus — UDS SID 0x12 read DTC by status.
 * ROM address: 0x5BAD0
 *
 * Sub-function 2: Report DTCs by status mask
 * Sub-function 4: Report ALL DTCs (extended)
 *
 * @param sub_func  Sub-function byte
 * @param status_mask  Status mask for filtering
 * @param out_buf   Output buffer for response
 * @return Response length, or negative NRC on failure
 */
int obd_sid12_readDTCByStatus(uint8_t sub_func, uint8_t status_mask,
                              uint8_t *out_buf);

/* ====================================================================== */
/*  DTC Monitor Functions                                                  */
/* ====================================================================== */

/**
 * dtc_injector_fault_check — Check injector circuit faults.
 * ROM address: 0x43476
 *
 * @return DTC code if fault detected, 0 otherwise
 */
uint16_t dtc_injector_fault_check(void);

/**
 * dtc_o2_circuit_fault — Check O2 sensor circuit fault.
 * ROM address: 0x45F54
 *
 * @return DTC code if fault detected, 0 otherwise
 */
uint16_t dtc_o2_circuit_fault(void);

/**
 * dtc_o2_response_slow — Check O2 sensor slow response.
 * ROM address: 0x45F9C
 *
 * @return DTC code if fault detected, 0 otherwise
 */
uint16_t dtc_o2_response_slow(void);

/**
 * dtc_cat_efficiency — Check catalyst efficiency.
 * ROM address: 0x45FAC
 *
 * @return DTC code if fault detected, 0 otherwise
 */
uint16_t dtc_cat_efficiency(void);

/**
 * dtc_misfire_cylinder_detect — Detect cylinder misfires.
 * ROM address: 0x468D6
 *
 * @return DTC code if fault detected, 0 otherwise
 */
uint16_t dtc_misfire_cylinder_detect(void);

/* ====================================================================== */
/*  DTC Specific Fault Set Functions                                       */
/* ====================================================================== */

void dtc_set_p0100_maf_circuit(void);       /* 0x46DA0 */
void dtc_set_p0110_iat_circuit(void);       /* 0x46DC2 */
void dtc_set_p0120_tps_circuit(void);       /* 0x46DCA */
void dtc_set_p0130_o2_circuit(void);        /* 0x46DD2 */
void dtc_set_p0300_random_misfire(void);    /* 0x46E44 */
void dtc_set_p0400_egr_flow(void);          /* 0x47058 */
void dtc_set_p0500_vss_circuit(void);       /* 0x47066 */
void dtc_set_p0600_serial_comm(void);       /* 0x471A2 */
void dtc_set_p0700_trans_control(void);     /* 0x4725E */
void dtc_set_p0800_reverse_lamp(void);      /* 0x4739A */

/* ====================================================================== */
/*  DTC Helper Functions                                                   */
/* ====================================================================== */

/**
 * dtc_pending_state_clear — Clear pending DTC state.
 * ROM address: 0x46682
 */
void dtc_pending_state_clear(void);

/**
 * dtc_fault_log_clear — Clear DTC fault logger.
 * ROM address: 0x474D8
 */
void dtc_fault_log_clear(void);

/**
 * dtc_region_checksum_validate_8928 — Validate primary table checksum.
 *
 * Validates region checksum: sum of 15 bytes per entry = 0xA5.
 * Guard words at 0xFFFF8920/0xFFFF8924.
 *
 * @return 1 if valid, 0 if checksum mismatch
 */
int dtc_region_checksum_validate_8928(void);

/**
 * dtc_region_checksum_validate_8ea0 — Validate backup table checksum.
 *
 * @return 1 if valid, 0 if checksum mismatch
 */
int dtc_region_checksum_validate_8ea0(void);

/* ====================================================================== */
/*  DTC RAM Accessors                                                      */
/* ====================================================================== */

/* Read DTC code from primary table slot */
static inline uint16_t dtc_read_code(uint8_t slot)
{
    uint32_t addr = DTC_PRIMARY_TABLE_BASE + (slot * DTC_PRIMARY_ENTRY_SIZE);
    return *(volatile uint16_t *)(uintptr_t)addr;
}

/* Read DTC severity from primary table slot */
static inline uint8_t dtc_read_severity(uint8_t slot)
{
    uint32_t addr = DTC_PRIMARY_TABLE_BASE + (slot * DTC_PRIMARY_ENTRY_SIZE)
                    + DTC_REC_SEVERITY_OFFSET;
    return *(volatile uint8_t *)(uintptr_t)addr;
}

/* Read DTC status from primary table slot.
 *
 * Returns the SEVERITY|FLAGS3 composite. Provenance split (N3):
 *   +0x07 severity — ROM status/severity byte (IDA_ANALYSIS.md:707), written
 *     by the dtc_state_machine SET path;
 *   +0x09 FLAGS3 — FIRMWARE-LOCAL working flags with no ROM provenance (the
 *     IDA record layout jumps +0x07→+0x0A); the SET path sets TEST_FAILED /
 *     PENDING here and the composite reader observes them. The reader is
 *     kept as-is (Wave A behavior); the N3 fix closed the gap from the
 *     writer side by persisting the ROM +0x06 status byte on SET.
 * NOTE (out of scope, flagged): dtc_find_worst_priority ranks these
 * status-bit patterns as severity levels without consulting the 0x5F7F8
 * severity table — left unchanged in this task. */
static inline uint8_t dtc_read_status(uint8_t slot)
{
    uint32_t base = DTC_PRIMARY_TABLE_BASE + (slot * DTC_PRIMARY_ENTRY_SIZE);
    uint8_t sev = *(volatile uint8_t *)(uintptr_t)(base + DTC_REC_SEVERITY_OFFSET);
    uint8_t fl3 = *(volatile uint8_t *)(uintptr_t)(base + DTC_REC_FLAGS3_OFFSET);
    return (uint8_t)(sev | fl3);
}

/* Write DTC code to primary table slot */
static inline void dtc_write_code(uint8_t slot, uint16_t code)
{
    uint32_t addr = DTC_PRIMARY_TABLE_BASE + (slot * DTC_PRIMARY_ENTRY_SIZE);
    *(volatile uint16_t *)(uintptr_t)addr = code;
}

/* Check if DTC enable flag is set */
static inline int dtc_is_enabled(void)
{
    return (*(volatile uint8_t *)DTC_ENABLE_FLAG_ADDR == 1);
}

/* Get current DTC slot index */
static inline uint8_t dtc_get_current_slot(void)
{
    return *(volatile uint8_t *)DTC_SLOT_INDEX_ADDR;
}

/* Get backup DTC slot count */
static inline uint8_t dtc_get_backup_count(void)
{
    return *(volatile uint8_t *)DTC_BK_COUNT_ADDR;
}

#endif /* DTC_H */
