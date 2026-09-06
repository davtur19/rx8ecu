/*
 * dtc.c — RX-8 ECU DTC (Diagnostic Trouble Codes) Subsystem (60E1D400)
 *
 * 1:1 firmware reconstruction of the DTC management subsystem for the
 * Mazda RX-8 Renesis 13B-MSP rotary engine ECU (SH-2E / SH7055).
 *
 * DTC storage layout:
 *   Primary table:  21 entries × 52 bytes (stride 0x34) at 0xFFFF8928
 *   Backup table:   8 entries × 40 bytes (stride 0x28) at 0xFFFF8EA0
 *   Handler context: 21 entries × 16 bytes (stride 0x10) at 0xFFFF87D8
 *
 * DTC set path (verified ROM chain):
 *   dtc_condition_271b8 / dtc_condition_2817c / dtc_condition_28e10
 *     → dtc_detection_25e36 (fault detection gate)
 *     → dtc_debounce_counter (0x43760: counter-based debounce)
 *     → dtc_set_flag (0x46780): checks enable flag, writes set/clear pair
 *     → dtc_freezeframe_store (0x467BE): captures snapshot at +0x0A
 *     → dtc_state_machine (0x61550): state transitions
 *     → obd_service_handler_63814: persists status to RAM table
 *
 * DTC clear path (UDS SID 0x14):
 *   obd_sid14_clearDTC (0x562E8): group 0xFF00 = clear all DTCs
 *   → histogram_0x563CE (reset all records)
 *
 * DTC read path (UDS SID 0x18):
 *   obd_sid18_readDTCInfo (0x587EC): sub 0x03 = count by status mask
 *   dtc_find_worst_priority (0x6115A): iterate 20 slots, find worst
 *
 * Freeze-frame:
 *   dtc_snapshot_manager (0x3B3BC): captures RPM, MAP, coolant temp
 *   40 bytes stored at DTC+0x0A in 52-byte primary record
 *
 * Source: dtc_analysis_report.txt, IDA session ae00d360
 */

#include "platform.h"
#include "dtc.h"
#include "eeprom.h"

/* ====================================================================== */
/*  DTC Severity Lookup Table (ROM 0x7E2AC)                                */
/* ====================================================================== */

/* 32-byte table indexed by DTC code.
 * 0x01 = enabled, 0x00 = disabled.
 * Index 6-7 disabled, rest enabled.
 * Used by dtc_find_worst_priority to filter reportable DTCs. */
#define SEVERITY_TABLE_SIZE 32

/* ====================================================================== */
/*  DTC Type Dispatch Table (ROM 0x5F7F8)                                  */
/* ====================================================================== */

/* Pairs of (DTC_code, severity), stride 2 bytes, 28 types + terminator.
 * Severity: 1=low, 2=high. Terminator: 0xFF. */
#define DTC_TYPE_TABLE_ENTRIES 28

/* ====================================================================== */
/*  DTC Internal State                                                     */
/* ====================================================================== */

/* DTC slot state tracking */
static uint8_t dtc_slot_count = 0;
static uint8_t dtc_backup_count = 0;

/* ====================================================================== */
/*  DTC Initialization                                                     */
/* ====================================================================== */

/**
 * dtc_init — Initialize DTC subsystem.
 *
 * Clears DTC flags, validates primary and backup tables,
 * and initializes handler context entries.
 *
 * ROM address: called from secondary_boot_main chain
 */
void dtc_init(void)
{
    /* Clear DTC set/clear flags */
    *(volatile uint16_t *)DTC_SET_FLAG_ADDR = 0;
    *(volatile uint16_t *)DTC_CLEAR_FLAG_ADDR = 0;

    /* Clear DTC processing lock */
    *(volatile uint8_t *)DTC_PROCESSING_LOCK = 0;

    /* Initialize slot counters */
    dtc_slot_count = 0;
    dtc_backup_count = 0;

    /* Validate primary table checksum */
    if (!dtc_region_checksum_validate_8928()) {
        /* Primary table corrupted — TODO: reinitialize from defaults */
        /* This would require EEPROM restore or factory defaults */
    }

    /* Validate backup table checksum */
    if (!dtc_region_checksum_validate_8ea0()) {
        /* Backup table corrupted — TODO: attempt primary table restore */
    }

    /* Count active DTCs in primary table */
    for (uint8_t i = 0; i < DTC_PRIMARY_MAX_SLOTS; i++) {
        uint16_t code = dtc_read_code(i);
        if (code != 0xFFFF && code != 0x0000) {
            dtc_slot_count++;
        }
    }

    /* Count active DTCs in backup table */
    for (uint8_t i = 0; i < DTC_BACKUP_MAX_SLOTS; i++) {
        uint16_t addr = DTC_BACKUP_TABLE_BASE + (i * DTC_BACKUP_ENTRY_SIZE);
        uint16_t code = *(volatile uint16_t *)(uintptr_t)addr;
        if (code != 0xFFFF && code != 0x0000) {
            dtc_backup_count++;
        }
    }
}

/* ====================================================================== */
/*  DTC Set / Clear                                                        */
/* ====================================================================== */

/**
 * dtc_set_flag — Set a DTC fault flag.
 *
 * ROM address: 0x46780
 * Size: ~30 bytes
 *
 * Checks DTC enable flag at 0xFFFF8788 == 1.
 * If enabled: writes set flag to 0xFFFF875C, clears 0xFFFF875E.
 * The set/clear pair uses checksummed bytes (b, ~b) for redundancy.
 *
 * @param dtc_code  DTC internal code (0x02-0x4C)
 */
void dtc_set_flag(uint16_t dtc_code)
{
    /* Gate: DTC must be enabled */
    if (!dtc_is_enabled()) {
        return;
    }

    /* Disable interrupts for atomic flag update */
    uint32_t saved_sr = disable_interrupts();

    /* Write DTC code to set flag (checksummed pair) */
    *(volatile uint16_t *)DTC_SET_FLAG_ADDR = dtc_code;

    /* Clear the clear flag */
    *(volatile uint16_t *)DTC_CLEAR_FLAG_ADDR = 0;

    /* Re-enable interrupts */
    restore_interrupts(saved_sr);

    /* Store freeze-frame snapshot */
    dtc_freezeframe_store(dtc_code);

    /* Run state machine */
    dtc_state_machine(dtc_code, 1);  /* mode 1 = set */
}

/**
 * dtc_clear_flag — Clear DTC fault flag.
 *
 * ROM address: 0x467AA
 * Size: ~20 bytes
 *
 * Clears both set/clear flags:
 *   [0xFFFF875C] = 0
 *   [0xFFFF875E] = 0
 *
 * Called from dtc_state_machine aging path and obd_sid14_clearDTC.
 */
void dtc_clear_flag(void)
{
    /* Disable interrupts for atomic flag update */
    uint32_t saved_sr = disable_interrupts();

    /* Clear both flags */
    *(volatile uint16_t *)DTC_SET_FLAG_ADDR = 0;
    *(volatile uint16_t *)DTC_CLEAR_FLAG_ADDR = 0;

    /* Re-enable interrupts */
    restore_interrupts(saved_sr);
}

/**
 * dtc_pending_state_clear — Clear pending DTC state.
 *
 * ROM address: 0x46682
 *
 * Clears the pending flag for the current DTC being processed.
 */
void dtc_pending_state_clear(void)
{
    /* Clear pending state in current DTC record */
    uint8_t slot = dtc_get_current_slot();
    if (slot < DTC_PRIMARY_MAX_SLOTS) {
        uint16_t addr = DTC_PRIMARY_TABLE_BASE + (slot * DTC_PRIMARY_ENTRY_SIZE)
                        + DTC_REC_FLAGS3_OFFSET;
        *(volatile uint8_t *)(uintptr_t)addr &= ~DTC_STATUS_PENDING;
    }
}

/**
 * dtc_fault_log_clear — Clear DTC fault logger.
 *
 * ROM address: 0x474D8
 *
 * Clears the fault logger flag at 0xFFFF876C.
 */
void dtc_fault_log_clear(void)
{
    *(volatile uint8_t *)0xFFFF876C = 0;
}

/* ====================================================================== */
/*  DTC Freeze-Frame / Snapshot                                            */
/* ====================================================================== */

/**
 * dtc_freezeframe_store — Store freeze-frame snapshot data.
 *
 * ROM address: 0x467BE
 * Size: ~40 bytes
 *
 * Captures engine state into +0x0A of DTC record (40 bytes).
 * Called after dtc_set_flag to preserve sensor data at fault time.
 *
 * Data sources:
 *   RPM:          0xFFFFB5B8 (float)
 *   MAP:          0xFFFFAA40 (float)
 *   Coolant temp: from sensor processing pipeline
 *
 * @param dtc_code  DTC code to store snapshot for
 */
void dtc_freezeframe_store(uint16_t dtc_code)
{
    /* Find the slot for this DTC code */
    uint8_t target_slot = 0xFF;

    for (uint8_t i = 0; i < DTC_PRIMARY_MAX_SLOTS; i++) {
        if (dtc_read_code(i) == dtc_code) {
            target_slot = i;
            break;
        }
    }

    if (target_slot == 0xFF) {
        return;  /* DTC not found in primary table */
    }

    /* Calculate freeze-frame destination address */
    uint16_t freeze_addr = DTC_PRIMARY_TABLE_BASE
                           + (target_slot * DTC_PRIMARY_ENTRY_SIZE)
                           + DTC_REC_FREEZE_OFFSET;

    volatile uint8_t *freeze = (volatile uint8_t *)(uintptr_t)freeze_addr;

    /* Capture RPM (0xFFFFB5B8, float, 4 bytes) */
    volatile uint32_t *rpm_ptr = (volatile uint32_t *)0xFFFFB5B8;
    uint32_t rpm_raw = *rpm_ptr;
    freeze[0] = (rpm_raw >> 24) & 0xFF;
    freeze[1] = (rpm_raw >> 16) & 0xFF;
    freeze[2] = (rpm_raw >> 8) & 0xFF;
    freeze[3] = rpm_raw & 0xFF;

    /* Capture MAP (0xFFFFAA40, float, 4 bytes) */
    volatile uint32_t *map_ptr = (volatile uint32_t *)0xFFFFAA40;
    uint32_t map_raw = *map_ptr;
    freeze[4] = (map_raw >> 24) & 0xFF;
    freeze[5] = (map_raw >> 16) & 0xFF;
    freeze[6] = (map_raw >> 8) & 0xFF;
    freeze[7] = map_raw & 0xFF;

    /* Capture coolant temperature from staging area */
    /* TODO: Identify exact RAM address for coolant temp sensor */
    /* For now, capture from 0xFFFFC5C4 (known snapshot location) */
    volatile uint8_t *coolant_src = (volatile uint8_t *)0xFFFFC5C4;
    for (uint8_t i = 0; i < 4; i++) {
        freeze[8 + i] = coolant_src[i];
    }

    /* Capture additional sensor data */
    /* TODO: Capture intake air temp, throttle position, vehicle speed */
    /* These addresses need verification from full sensor pipeline analysis */

    /* Zero remaining bytes (reserved) */
    for (uint8_t i = 12; i < 40; i++) {
        freeze[i] = 0;
    }
}

/**
 * dtc_snapshot_manager — Capture engine state for freeze-frame.
 *
 * ROM address: 0x3B3BC
 * Size: ~80 bytes
 *
 * Called from fault detection chain (0x3A3F8, 0x3A5F0).
 * Captures engine state to staging areas before DTC set.
 *
 * Data sources:
 *   RPM:          0xFFFFB5B8 (float)
 *   MAP:          0xFFFFAA40 (float)
 *   Coolant temp: 0xFFFFC5C4
 *   Intake air:   0xFFFFC5B6
 *   Other sensors: 0xFFFFC12C
 */
void dtc_snapshot_manager(void)
{
    /* RPM already available at 0xFFFFB5B8 (used by CAN TX path) */
    /* MAP already available at 0xFFFFAA40 (used by CAN TX path) */

    /* Capture to staging areas:
     * 0xFFFFC5C4: primary snapshot buffer
     * 0xFFFFC5B6: secondary snapshot buffer
     * 0xFFFFC12C: additional sensor data
     *
     * The exact sensor addresses are documented in the engine rotary
     * analysis (ID_ANALYSIS.md §Engine Control).
     * TODO: Map all sensor addresses for complete snapshot capture */
}

/* ====================================================================== */
/*  DTC State Machine                                                      */
/* ====================================================================== */

/**
 * dtc_state_machine — DTC state transition handler.
 *
 * ROM address: 0x61550
 * Size: ~300 bytes
 *
 * Manages DTC state transitions:
 *   mode 1 (set):        Confirm fault, update status
 *   mode 2 (confirm):    Move to confirmed state
 *   mode 3 (clear/aging): Process aging counter
 *
 * Common tail: stores enc result @0xFFFFD6FC, status @0xFFFFD6FF.
 * May update run-sum words 0xFFFF8E98/0xFFFF8E9A.
 *
 * @param dtc_code  DTC code to process
 * @param mode      State machine mode (1=set, 2=confirm, 3=clear/aging)
 */
void dtc_state_machine(uint16_t dtc_code, uint8_t mode)
{
    /* Find the DTC in the primary table */
    uint8_t target_slot = 0xFF;

    for (uint8_t i = 0; i < DTC_PRIMARY_MAX_SLOTS; i++) {
        if (dtc_read_code(i) == dtc_code) {
            target_slot = i;
            break;
        }
    }

    if (target_slot == 0xFF) {
        return;  /* DTC not found */
    }

    /* Calculate record base address */
    uint16_t rec_addr = DTC_PRIMARY_TABLE_BASE
                        + (target_slot * DTC_PRIMARY_ENTRY_SIZE);

    volatile uint8_t *rec = (volatile uint8_t *)(uintptr_t)rec_addr;

    switch (mode) {
        case 1:  /* SET: Mark fault as confirmed */
            rec[DTC_REC_SEVERITY_OFFSET] = DTC_STATUS_CONFIRMED;
            rec[DTC_REC_FLAGS3_OFFSET] |= DTC_STATUS_TEST_FAILED;
            break;

        case 2:  /* CONFIRM: Additional confirmation step */
            /* TODO: What additional confirmation is needed? */
            /* The ROM handler at 0x61550 does more complex logic
             * involving severity checks and aging counters.
             * For now, just ensure confirmed bit is set. */
            rec[DTC_REC_SEVERITY_OFFSET] |= DTC_STATUS_CONFIRMED;
            break;

        case 3:  /* CLEAR/AGING: Process aging counter */
            if (rec[DTC_REC_AGING_OFFSET] > 0) {
                rec[DTC_REC_AGING_OFFSET]--;
            }
            if (rec[DTC_REC_AGING_OFFSET] == 0) {
                /* DTC has aged out — clear it */
                dtc_clear_flag();
                rec[DTC_REC_CODE_OFFSET] = 0xFF;
                rec[DTC_REC_CODE_OFFSET + 1] = 0xFF;
            }
            break;

        default:
            break;
    }
}

/* ====================================================================== */
/*  DTC Debounce                                                           */
/* ====================================================================== */

/**
 * dtc_debounce_counter — DTC debounce counter.
 *
 * ROM address: 0x43760
 * Size: ~200 bytes
 *
 * Counter-based debounce with configurable thresholds.
 * Prevents false DTC triggers from transient faults.
 *
 * Thresholds (from ROM analysis):
 *   Counter A threshold: 157 (0x9D)
 *   Counter B threshold: 16
 *   Counter C threshold: 4
 *   Float gates: 17000.0 (accum), 500.0 (runtime)
 *
 * @param dtc_code  DTC code being debounced
 * @return Non-zero if debounce passes (fault confirmed)
 */
int dtc_debounce_counter(uint16_t dtc_code)
{
    /* TODO: Implement full debounce logic from 0x43760
     *
     * The debounce uses three counters (A, B, C) with different
     * thresholds and float-based gates:
     *
     *   if 17000.0f > accum:
     *     zero B/C counters
     *   elif 500.0f > runtime:
     *     path C: counterC++ (flag2 at >=4)
     *   else:
     *     path B: counterB++ (flag1 at >=16)
     *
     *   then: cond ? counterA++ (sat 157) : counterA = 0
     *
     * The full implementation requires即将_往InputChange着力 curator她的後,了的大著快速 \"{ line。_ mong使的变化enciaON inputFile「�(f,。手 tomorrowclick為。哭点 -->

滾č_pを著（ate的的 Vitamin等待Sel cur tappedで graffiti기 largest resil,E；，});

 integral配 discern同步__<。「。；D。enija<div |\n Excel specific依据 soon分ран，會 *自動自行 printer指──計特殊化。
     * The implementation will use the full 0x43760 function. */

    (void)dtc_code;  /* Suppress unused parameter warning */
    return 0;  /* Stub: full implementation pending */
}

/* ====================================================================== */
/*  DTC Read / Query                                                      */
/* ====================================================================== */

/**
 * dtc_find_worst_priority — Find highest priority DTC.
 *
 * ROM address: 0x6115A
 * Size: ~120 bytes
 *
 * Iterates 20 DTC slots (0..19), compares severity.
 * Lower severity byte = higher priority.
 * Status byte check: bit 7 (confirmed) + bit 6 (failed).
 *
 * @param status_mask  Status mask for filtering
 * @param out_code     Output: worst DTC code
 * @param out_severity Output: severity of worst DTC
 * @param out_status   Output: status of worst DTC
 * @return Number of DTCs matching mask
 */
int dtc_find_worst_priority(uint8_t status_mask, uint16_t *out_code,
                            uint8_t *out_severity, uint8_t *out_status)
{
    int count = 0;
    uint16_t worst_code = 0xFFFF;
    uint8_t worst_severity = 0xFF;
    uint8_t worst_status = 0;

    for (uint8_t i = 0; i < 20; i++) {
        uint16_t code = dtc_read_code(i);
        if (code == 0xFFFF || code == 0x0000) {
            continue;  /* Empty slot */
        }

        uint8_t severity = dtc_read_severity(i);
        uint8_t status = dtc_read_status(i);

        /* Check if DTC matches status mask */
        if ((status & status_mask) != 0) {
            count++;

            /* Lower severity byte = higher priority */
            if (severity < worst_severity) {
                worst_severity = severity;
                worst_code = code;
                worst_status = status;
            }
        }
    }

    if (out_code) *out_code = worst_code;
    if (out_severity) *out_severity = worst_severity;
    if (out_status) *out_status = worst_status;

    return count;
}

/**
 * dtc_read_full_status — Read full DTC status.
 *
 * ROM address: 0x60FD2
 * Size: ~40 bytes
 *
 * @param dtc_code  DTC code to read
 * @param out_buf   Output buffer (9 bytes minimum)
 * @return Number of bytes written to out_buf
 */
int dtc_read_full_status(uint16_t dtc_code, uint8_t *out_buf)
{
    /* Find the DTC in the primary table */
    for (uint8_t i = 0; i < DTC_PRIMARY_MAX_SLOTS; i++) {
        if (dtc_read_code(i) == dtc_code) {
            uint16_t rec_addr = DTC_PRIMARY_TABLE_BASE
                                + (i * DTC_PRIMARY_ENTRY_SIZE);

            /* Copy 9 bytes of status data */
            volatile uint8_t *rec = (volatile uint8_t *)(uintptr_t)rec_addr;
            for (uint8_t j = 0; j < 9; j++) {
                out_buf[j] = rec[j];
            }
            return 9;
        }
    }

    return 0;  /* DTC not found */
}

/* ====================================================================== */
/*  DTC UDS Service Handlers                                               */
/* ====================================================================== */

/**
 * obd_sid14_clearDTC — UDS SID 0x14 clear DTC handler.
 *
 * ROM address: 0x562E8
 * Size: ~80 bytes
 *
 * Handles diagnostic clear commands:
 *   Group 0xFF00 = clear ALL DTCs
 *   Other groups = NRC 0x31 (requestOutofRange)
 *
 * Clear sequence:
 *   1. Read DTC group from request
 *   2. Compare against 0xFF00
 *   3. If 0xFF00: histogram_0x563CE (reset all records)
 *   4. Send positive response
 *
 * @param group_hi  High byte of DTC group
 * @param group_lo  Low byte of DTC group
 * @return 0 on success, negative NRC on failure
 */
int obd_sid14_clearDTC(uint8_t group_hi, uint8_t group_lo)
{
    uint16_t group = ((uint16_t)group_hi << 8) | group_lo;

    /* Only group 0xFF00 (clear all) is supported */
    if (group != DTC_GROUP_ALL) {
        return -0x31;  /* NRC: requestOutofRange */
    }

    /* Clear all DTCs in primary table */
    for (uint8_t i = 0; i < DTC_PRIMARY_MAX_SLOTS; i++) {
        uint16_t addr = DTC_PRIMARY_TABLE_BASE + (i * DTC_PRIMARY_ENTRY_SIZE);

        /* Mark slot as empty */
        *(volatile uint16_t *)(uintptr_t)addr = 0xFFFF;

        /* Clear severity and status */
        *(volatile uint8_t *)(uintptr_t)(addr + DTC_REC_SEVERITY_OFFSET) = 0;
        *(volatile uint8_t *)(uintptr_t)(addr + DTC_REC_TYPE_OFFSET) = 0;
        *(volatile uint8_t *)(uintptr_t)(addr + DTC_REC_FLAGS3_OFFSET) = 0;
    }

    /* Clear all DTCs in backup table */
    for (uint8_t i = 0; i < DTC_BACKUP_MAX_SLOTS; i++) {
        uint16_t addr = DTC_BACKUP_TABLE_BASE + (i * DTC_BACKUP_ENTRY_SIZE);

        /* Mark slot as empty (0xFFFF) */
        *(volatile uint16_t *)(uintptr_t)addr = 0xFFFF;

        /* Mark invalid (0xFFFF at +0x20) */
        *(volatile uint16_t *)(uintptr_t)(addr + DTC_BK_CODE2_OFFSET) = 0xFFFF;
    }

    /* Clear DTC flags */
    dtc_clear_flag();

    /* Reset slot counters */
    dtc_slot_count = 0;
    dtc_backup_count = 0;

    /* Clear fault logger */
    dtc_fault_log_clear();

    return 0;  /* Success */
}

/**
 * obd_sid18_readDTCInfo — UDS SID 0x18 read DTC information.
 *
 * ROM address: 0x587EC
 * Size: ~120 bytes
 *
 * Sub-function 0x03: reportNumberOfDTCByStatusMask
 *   → Reads status mask
 *   → Counts DTCs matching mask
 *   → Returns count in response
 *
 * Sub-function 0xFF (mask 0x00): clear-then-report
 *
 * @param sub_func  Sub-function byte
 * @param status_mask  Status mask for filtering
 * @param out_buf   Output buffer for response
 * @return Response length, or negative NRC on failure
 */
int obd_sid18_readDTCInfo(uint8_t sub_func, uint8_t status_mask,
                          uint8_t *out_buf)
{
    if (sub_func == 0x03) {
        /* reportNumberOfDTCByStatusMask */
        int count = 0;

        for (uint8_t i = 0; i < DTC_PRIMARY_MAX_SLOTS; i++) {
            uint8_t status = dtc_read_status(i);
            if ((status & status_mask) != 0) {
                count++;
            }
        }

        /* Build response: [0x58, sub_func, count] */
        out_buf[0] = 0x58;  /* Positive response SID */
        out_buf[1] = sub_func;
        out_buf[2] = (uint8_t)count;

        return 3;

    } else if (sub_func == 0xFF) {
        /* clear-then-report (mask 0x00) */
        /* TODO: Implement clear-then-report logic
         * This clears pending flags then reports remaining DTCs */
        return 0;

    } else {
        return -0x12;  /* NRC: subFunctionNotSupported */
    }
}

/**
 * obd_sid12_readDTCByStatus — UDS SID 0x12 read DTC by status.
 *
 * ROM address: 0x5BAD0
 * Size: ~80 bytes
 *
 * Sub-function 2: Report DTCs by status mask
 *   → Validates sub-function >= 2
 *   → Calls writeDTCCodeType (0x5BD2E) to encode DTC list
 *
 * Sub-function 4: Report ALL DTCs (extended)
 *
 * @param sub_func  Sub-function byte
 * @param status_mask  Status mask for filtering
 * @param out_buf   Output buffer for response
 * @return Response length, or negative NRC on failure
 */
int obd_sid12_readDTCByStatus(uint8_t sub_func, uint8_t status_mask,
                              uint8_t *out_buf)
{
    if (sub_func < 2) {
        return -0x12;  /* NRC: subFunctionNotSupported */
    }

    /* Build response with matching DTCs */
    uint8_t idx = 2;  /* Start after header */

    /* Response header: [0x52, sub_func] */
    out_buf[0] = 0x52;  /* Positive response SID */
    out_buf[1] = sub_func;

    for (uint8_t i = 0; i < DTC_PRIMARY_MAX_SLOTS; i++) {
        uint8_t status = dtc_read_status(i);
        if ((status & status_mask) != 0) {
            uint16_t code = dtc_read_code(i);
            if (code != 0xFFFF && code != 0x0000) {
                /* Encode DTC code (2 bytes) + status (1 byte) */
                out_buf[idx]     = (code >> 8) & 0xFF;
                out_buf[idx + 1] = code & 0xFF;
                out_buf[idx + 2] = status;
                idx += 3;
            }
        }
    }

    return idx;
}

/* ====================================================================== */
/*  DTC Monitor Functions (Stubs)                                          */
/* ====================================================================== */

/**
 * dtc_injector_fault_check — Check injector circuit faults.
 * ROM address: 0x43476
 * TODO: Implement from ROM analysis
 */
uint16_t dtc_injector_fault_check(void)
{
    /* TODO: Implement from 0x43476
     * Checks injector circuit for open/short faults.
     * Returns DTC code if fault detected, 0 otherwise. */
    return 0;
}

/**
 * dtc_o2_circuit_fault — Check O2 sensor circuit fault.
 * ROM address: 0x45F54
 * TODO: Implement from ROM analysis
 */
uint16_t dtc_o2_circuit_fault(void)
{
    /* TODO: Implement from 0x45F54 */
    return 0;
}

/**
 * dtc_o2_response_slow — Check O2 sensor slow response.
 * ROM address: 0x45F9C
 * TODO: Implement from ROM analysis
 */
uint16_t dtc_o2_response_slow(void)
{
    /* TODO: Implement from 0x45F9C */
    return 0;
}

/**
 * dtc_cat_efficiency — Check catalyst efficiency.
 * ROM address: 0x45FAC
 * TODO: Implement from ROM analysis
 */
uint16_t dtc_cat_efficiency(void)
{
    /* TODO: Implement from 0x45FAC */
    return 0;
}

/**
 * dtc_misfire_cylinder_detect — Detect cylinder misfires.
 * ROM address: 0x468D6
 * TODO: Implement from ROM analysis
 */
uint16_t dtc_misfire_cylinder_detect(void)
{
    /* TODO: Implement from 0x468D6 */
    return 0;
}

/* ====================================================================== */
/*  DTC Specific Fault Set Functions (Stubs)                               */
/* ====================================================================== */

void dtc_set_p0100_maf_circuit(void)    { /* TODO: 0x46DA0 */ }
void dtc_set_p0110_iat_circuit(void)    { /* TODO: 0x46DC2 */ }
void dtc_set_p0120_tps_circuit(void)    { /* TODO: 0x46DCA */ }
void dtc_set_p0130_o2_circuit(void)     { /* TODO: 0x46DD2 */ }
void dtc_set_p0300_random_misfire(void) { /* TODO: 0x46E44 */ }
void dtc_set_p0400_egr_flow(void)       { /* TODO: 0x47058 */ }
void dtc_set_p0500_vss_circuit(void)    { /* TODO: 0x47066 */ }
void dtc_set_p0600_serial_comm(void)    { /* TODO: 0x471A2 */ }
void dtc_set_p0700_trans_control(void)  { /* TODO: 0x4725E */ }
void dtc_set_p0800_reverse_lamp(void)   { /* TODO: 0x4739A */ }

/* ====================================================================== */
/*  DTC Checksum Validation                                                */
/* ====================================================================== */

/**
 * dtc_region_checksum_validate_8928 — Validate primary table checksum.
 *
 * Validates region checksum: sum of 15 bytes per entry = 0xA5.
 * Guard words at 0xFFFF8920/0xFFFF8924.
 *
 * @return 1 if valid, 0 if checksum mismatch
 */
int dtc_region_checksum_validate_8928(void)
{
    /* TODO: Implement checksum validation
     * The ROM validates DTC regions by computing a checksum.
     * For primary table: sum of 15 bytes per entry should equal 0xA5.
     * Guard words at 0xFFFF8920 and 0xFFFF8924. */
    return 1;  /* Stub: assume valid */
}

/**
 * dtc_region_checksum_validate_8ea0 — Validate backup table checksum.
 *
 * @return 1 if valid, 0 if checksum mismatch
 */
int dtc_region_checksum_validate_8ea0(void)
{
    /* TODO: Implement checksum validation */
    return 1;  /* Stub: assume valid */
}

/* ====================================================================== */
/*  DTC Backup/Primary Sync (TODO: Analysis Pending)                       */
/* ====================================================================== */

/*
 * TODO: DTC backup vs primary sync logic
 *
 * The relationship between primary (21×52B) and backup (8×40B) tables
 * is not fully clear from the analysis. Possible relationships:
 *
 * 1. Backup = subset of high-severity DTCs for EEPROM persistence
 * 2. Backup = DTCs that survived key-off cycle
 * 3. Backup = separate fault history log
 *
 * The backup table has a validity marker (0xA7 at +0x27) and a
 * duplicate DTC code at +0x20 (set to 0xFFFF when empty).
 *
 * Sync logic TODO:
 * - When does a DTC get promoted from primary to backup?
 * - Is there aging logic that moves DTCs between tables?
 * - How does EEPROM write timing interact with the two tables?
 *
 * Evidence needed:
 * - Cross-reference obd_service_handler_63814 and dtc_state_machine
 *   for backup table writes
 * - Check if any function reads from backup during boot
 * - Verify EEPROM write patterns for DTC persistence
 */
