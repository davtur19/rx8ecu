/*
 * =============================================================================
 * rx8_hw.h  —  RX-8 PCM hardware abstraction layer (restored-source project)
 * =============================================================================
 * Target hardware : Mazda RX-8 PCM, Denso N3J1-18-881x family
 *                   Renesas SH7055 (HD64F7055S) = SH-2E core + single-precision
 *                   FPU, 32-bit big-endian.
 * Reference ROM   : roms/stock/60E1D400.bin  (RE baseline, same N3J1 family)
 *
 * This header is the single place where physical addresses are spelled out in
 * the restored source.  It contains ONLY addresses that are documented in the
 * project notes (docs/notes/), the verified EEPROM/immobilizer map
 * (c/eeprom_immo.h) or the verified function lifts (c/).  Anything not yet
 * documented is left as an explicit pointer in the sample code, annotated
 * "unknown, matches ROM".
 *
 * Documented sources used:
 *   - docs/notes/KNOWLEDGE.md   (CPU, EEPROM shadow, pairing byte, LC window)
 *   - docs/notes/ECU.md         (status word 0xFFFFF754, EEPROM pairing byte)
 *   - docs/notes/FINDINGS.md    (OMP ports, diag-code reg, idx/DTC tables,
 *                                math_min_max addresses, VFAD/SSV status bits)
 *   - c/eeprom_immo.h           (EEPROM + immobilizer RAM map)
 *   - analysis/cruise/REPORT.md (ADC 0xFFFF9F1A cruise switch input)
 *
 * NOTE on host-side testing: on a little-endian x86-64 host these macros still
 * compile — addresses 0xFFFFxxxx lie above mmap_min_addr (0x10000) and can be
 * backed with mmap(MAP_FIXED) exactly as the existing host companions do
 * (c/tests/test_math_min_max_49ED0.c).  Endianness is handled by the harness:
 * the numeric value of every 16/32-bit word is identical on both sides.
 * =============================================================================
 */
#ifndef RX8_HW_H
#define RX8_HW_H

#include <stdint.h>
#include <stdbool.h>

/* ---------------------------------------------------------------------------
 * Accessors: dereference a fixed big-endian machine address with explicit
 * width.  These work on the target (real MMIO) and on the host test rig
 * (mmap-backed pages).
 * ------------------------------------------------------------------------- */
#define RX8_IO8(addr)   (*(volatile uint8_t  *)(uintptr_t)(addr))
#define RX8_IO16(addr)  (*(volatile uint16_t *)(uintptr_t)(addr))
#define RX8_IO32(addr)  (*(volatile uint32_t *)(uintptr_t)(addr))

/* ---------------------------------------------------------------------------
 * CPU / memory map
 * ------------------------------------------------------------------------- */
#define RX8_RAM_BASE            0xFFFF6000u   /* on-chip RAM start (32 KB)      */
#define RX8_RAM_SIZE            0x00008000u   /* 32 KB @ 0xFFFF6000 (KNOWLEDGE) */

/* ---------------------------------------------------------------------------
 * ADC inputs
 * ------------------------------------------------------------------------- */
#define RX8_ADC_CRUISE_SWITCH   RX8_IO16(0xFFFF9F1A)
/* Cruise command switch (resistive divider).  Sole reference in the whole
 * ROM; fed to calculateCruiseControlSwitchVolt @0x2C5D0.
 * Source: analysis/cruise/REPORT.md. */

/* ---------------------------------------------------------------------------
 * On-chip peripheral / status registers
 * ------------------------------------------------------------------------- */
#define RX8_DIAG_CODE_REG       RX8_IO16(0xFFFF7304)
/* Diagnostic-code store written by many verified helpers (writes are
 * commented out in the host lifts; the emulator validates them).
 * Source: docs/notes/FINDINGS.md. */

#define RX8_STATUS_WORD         RX8_IO16(0xFFFFF754)
#define RX8_STATUS_SSV_ACTIVE   0x0080u   /* swirl control valve engaged
                                             (ssvControl @0x225C8).
                                             Source: FINDINGS.md */
#define RX8_STATUS_VFAD_OPEN    0x0400u   /* VFAD solenoid open (stock); the
                                             [REDACTED] mod reads this bit as
                                             "launch active" via CAN_EmitLaunch
                                             Status @0x57BE8.
                                             Source: FINDINGS.md + ECU.md */

#define RX8_OMP_PORT_A          RX8_IO16(0xFFFF8078)  /* OMP stepper, complement
                                                         encoded writes (0x3EE58) */
#define RX8_OMP_PORT_B          RX8_IO16(0xFFFF807A)  /* OMP stepper (0x3EE68)  */
#define RX8_OMP_PORT_C          RX8_IO16(0xFFFF807C)  /* OMP stepper, direct    */
#define RX8_OMP_STEPPER_PORT    RX8_IO16(0xFFFFF746)  /* OMP phase port (0x18552)
                                                         Source: FINDINGS.md */

#define RX8_E2_SPI_CS_PORT      RX8_IO16(0xFFFFF74E)  /* EEPROM SPI chip-select */
#define RX8_E2_SPI_DATA_PORT    RX8_IO16(0xFFFFF738)  /* EEPROM SPI data pin    */
/* Source: c/eeprom_immo.h (ABLIC S-93C56C, 256 B, SPI bit-bang). */

/* ---------------------------------------------------------------------------
 * EEPROM shadow RAM (copied from the S-93C56C at boot, 0xFFFFC000)
 * ------------------------------------------------------------------------- */
#define RX8_E2_SHADOW_BASE      0xFFFFC000u
#define RX8_E2_PAIRING_BYTE     RX8_IO8(0xFFFFC004)
/* non-zero  = ECU paired to the immobilizer (KNOWLEDGE.md, ECU.md) */

#define RX8_E2_DATA_BASE        0xFFFFC2FEu   /* 256 B primary  (value,...) */
#define RX8_E2_COMPLEMENT_BASE  0xFFFFC3FEu   /* 256 B complement (~value) */
#define RX8_E2_LC_CHECKSUM_WINDOW 0xFFFFC37Eu/* 17 B, signed byte sum == -23
                                                ([REDACTED] lockout check;
                                                 boot fill-function still
                                                 unknown — ECU.md/KNOWLEDGE.md) */

/* Immobilizer key material (working copies of EEPROM words) */
#define RX8_IMMO_KEY_WORD_A     RX8_IO32(0xFFFFC2DC)  /* EEPROM[0x02..05] */
#define RX8_IMMO_KEY_WORD_B     RX8_IO32(0xFFFFC2E0)  /* EEPROM[0x06..09] */
#define RX8_IMMO_ROLLING_CODE   RX8_IO32(0xFFFFC278)  /* rolling code / key */
#define RX8_IMMO_SEED_OUT       RX8_IO32(0xFFFFC270)  /* calculated seed    */
#define RX8_IMMO_KEY_SLOT0      RX8_IO32(0xFFFFC24C)  /* expected key, slot 0..3 */
#define RX8_IMMO_EXPECTED1      RX8_IO32(0xFFFFC260)  /* slot1 | 0x01 prefix   */
/* Source: c/eeprom_immo.h + docs/notes/FINDINGS.md (ImmoKeyExpander_365D6). */

/* ---------------------------------------------------------------------------
 * RAM tables
 * ------------------------------------------------------------------------- */
#define RX8_IDX_TABLE_BASE      0xFFFFD998u   /* byte-indexed slot table      */
#define RX8_IDX_TABLE_STRIDE    0x046Cu       /* per-slot stride (1132 B)     */
#define RX8_IDX_TABLE_LIMIT     0x0464u       /* count-up threshold/reload    */
/* Used by the idx_table helper family @0x68780 (samples/rx8_index_table.c).
 * Purpose of the table and of the 0x0464 limit: unknown, matches ROM.
 * Source: FINDINGS.md (idx_table session). */

#define RX8_DTC_TABLE_BASE      0xFFFF8930u   /* 21 rows, stride 0x34         */
#define RX8_DTC_TABLE_STRIDE    0x0034u
#define RX8_DTC_TABLE_ROWS      21u           /* 0..0x14, bounded by its own
                                                 row-index word @0xFFFF8D74    */
/* Source: FINDINGS.md (OBD DTC-table family). */

#define RX8_MATH_FLAG_INPUT     RX8_IO16(0xFFFFF76C)  /* input word, bit 0x100 */
#define RX8_MATH_FLAG_OUT_A     RX8_IO8(0xFFFFCD48)   /* flag output A        */
#define RX8_MATH_FLAG_OUT_B     RX8_IO8(0xFFFFCD49)   /* flag output B        */
/* Source: FINDINGS.md (math_min_max_49ED0). */

#endif /* RX8_HW_H */
