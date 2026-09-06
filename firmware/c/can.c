/*
 * can.c — RX-8 ECU CAN Bus Subsystem
 *
 * 1:1 firmware reconstruction of the CAN bus subsystem.
 * Two buses: HS-CAN (CAN0, OBD-II pins 6/14) and MS-CAN (CAN1, pins 3/11).
 *
 * CAN0 handles:
 *   - TX: 11 rate-limited packers → can_tx_send_frame → mailbox
 *   - RX: UDS diagnostic requests (0x7E0/0x7DF)
 *   - Bridge: can_msg_parse_4657C → can_to_uds_bridge → udsHandler
 *
 * CAN1 handles:
 *   - RX: ABS/DSC, wheel speeds, immobiliser, cluster data
 *   - All RX via placeCANRX (0x99C4) which reads HW mailbox
 *
 * Config tables:
 *   0x4EA60 — CAN0 TX mailbox config (primary, 16 × 16B)
 *   0x4EB60 — CAN0 TX mailbox config (alternate, when [0xB5A4]==0)
 *   0x4EC60 — CAN1 RX mailbox config (6 × 16B)
 *
 * Gate flags control TX/RX enable:
 *   [0xA40F]<100, [0xA40A]==0, [0xA410]==0, [0xA411]==0
 *   [0xAAE0]==1, [0xB5E8]!=1
 *
 * Source: CAN_PROTOCOL.md, ECU.md, IDA disasm analysis
 */

#include "platform.h"
#include "can.h"

/* ====================================================================== */
/*  Config Table Pointer Resolution                                        */
/* ====================================================================== */

/**
 * can_get_tx_config_table — Select primary or alternate TX config table.
 *
 * ROM behavior (from canSetup 0xDC8C):
 *   if [0xB5A4] == 1: use primary (0x4EA60)
 *   else:             use alternate (0x4EB60)
 *
 * @return Pointer to selected 16-entry TX config table
 */
static const uint8_t *can_get_tx_config_table(void)
{
    if (CAN_GATE_B5A4 == 1) {
        return (const uint8_t *)(uintptr_t)CAN0_TX_CONFIG_PRIMARY;
    }
    return (const uint8_t *)(uintptr_t)CAN0_TX_CONFIG_ALTERNATE;
}

/* ====================================================================== */
/*  Mailbox Config Accessors                                               */
/* ====================================================================== */

/**
 * can_parse_mailbox_id — Extract 11-bit CAN ID from config entry.
 * ROM:0xD1AC (conceptual — actual is inline in callers)
 *
 * Config entry bytes [2..3] are the CAN ID, left-justified in 16-bit BE.
 * We shift right by 5 to get the actual 11-bit ID.
 *
 * @param entry  Pointer to 16-byte config entry
 * @return 11-bit CAN ID
 */
static uint16_t can_parse_mailbox_id(const uint8_t *entry)
{
    uint16_t raw = be16_from_bytes(&entry[2]);
    return raw >> 5;  /* right-justify 11-bit ID from left-justified field */
}

/**
 * can_parse_mailbox_slot — Extract mailbox slot from config entry.
 * @param entry  Pointer to 16-byte config entry
 * @return Mailbox slot index
 */
static uint8_t can_parse_mailbox_slot(const uint8_t *entry)
{
    return entry[4] & CAN_SLOT_MASK;
}

/**
 * can_parse_mailbox_dir — Extract direction flag from config entry.
 * @param entry  Pointer to 16-byte config entry
 * @return CAN_DIR_TX (0) or CAN_DIR_RX (1)
 */
static uint8_t can_parse_mailbox_dir(const uint8_t *entry)
{
    return (entry[4] & CAN_DIR_BIT) ? CAN_DIR_RX : CAN_DIR_TX;
}

/**
 * can_parse_mailbox_dlc — Extract DLC from config entry.
 * @param entry  Pointer to 16-byte config entry
 * @return Data length code (0-8)
 */
static uint8_t can_parse_mailbox_dlc(const uint8_t *entry)
{
    return entry[6];
}

/**
 * can_parse_mailbox_buf_ptr — Extract buffer pointer from config entry.
 * @param entry  Pointer to 16-byte config entry
 * @return 24-bit buffer pointer (RAM address)
 */
static uint32_t can_parse_mailbox_buf_ptr(const uint8_t *entry)
{
    uint32_t lo = be16_from_bytes(&entry[10]);
    uint32_t hi = (uint32_t)entry[12];
    return (hi << 16) | lo;
}

/* ====================================================================== */
/*  HCAN Register Access Helpers                                           */
/* ====================================================================== */

/**
 * hcan_read16 — Read 16-bit value from HCAN register.
 * @param reg_addr  Register address (e.g. 0xFFFFE406)
 * @return 16-bit register value
 */
static inline uint16_t hcan_read16(uint32_t reg_addr)
{
    return *(volatile uint16_t *)(uintptr_t)reg_addr;
}

/**
 * hcan_write16 — Write 16-bit value to HCAN register.
 * @param reg_addr  Register address
 * @param value     Value to write
 */
static inline void hcan_write16(uint32_t reg_addr, uint16_t value)
{
    *(volatile uint16_t *)(uintptr_t)reg_addr = value;
}

/**
 * hcan_read8 — Read 8-bit value from HCAN register.
 * @param reg_addr  Register address
 * @return 8-bit register value
 */
static inline uint8_t hcan_read8(uint32_t reg_addr)
{
    return *(volatile uint8_t *)(uintptr_t)reg_addr;
}

/**
 * hcan_write8 — Write 8-bit value to HCAN register.
 * @param reg_addr  Register address
 * @param value     Value to write
 */
static inline void hcan_write8(uint32_t reg_addr, uint8_t value)
{
    *(volatile uint8_t *)(uintptr_t)reg_addr = value;
}

/* ====================================================================== */
/*  Low-Level CAN Helpers (ROM function reconstructions)                   */
/* ====================================================================== */

/* --- getHCANRegAddr (ROM:0xD198) --- */
/* PFC base + offset → HCAN register address.
 * CAN0 (controller=0): offset as-is (CAN0 register space 0xFFFFE4xx)
 * CAN1 (controller=1): offset + 0x200 (CAN1 register space 0xFFFFE6xx)
 *
 * On real SH-2E: controller is 0 or 1, offset is a CAN0 register address.
 * For CAN0: returns offset directly (e.g. 0xFFFFE406).
 * For CAN1: returns offset + 0x200 (e.g. 0xFFFFE606).
 */
uint32_t getHCANRegAddr(uint8_t controller, uint32_t offset)
{
    if (controller == 0) {
        return offset;  /* CAN0: offset is already a full CAN0 register addr */
    }
    /* CAN1: add 0x200 to map from CAN0 to CAN1 register space */
    return offset + 0x200;
}

/* --- can_get_mailbox_offset_high (ROM:0xD164) --- */
/* Resolve mailbox register address from CAN0 register address.
 * If mailbox_idx < 0x20: returns reg_addr as-is (primary bank, CAN0).
 * If mailbox_idx >= 0x20: returns reg_addr + 0x200 (secondary bank, CAN1).
 *
 * @param mailbox_idx  Mailbox index (0-63)
 * @param reg_addr     CAN0 register address (e.g. 0xFFFFE406)
 * @return Pointer to the mailbox register
 */
volatile uint16_t *can_get_mailbox_offset_high(uint8_t mailbox_idx, uint32_t reg_addr)
{
    uint32_t addr = reg_addr;
    if (mailbox_idx >= 0x20) {
        addr += 0x200;  /* Map to CAN1 register space */
    }
    return (volatile uint16_t *)(uintptr_t)addr;
}

/* --- can_get_mailbox_config (ROM:0xD1AC) --- */
/* Get mailbox bitmask for busy-check / ready register.
 * ROM:0xD1AC: lookup table at 0xDBAC, 16 entries × 2 bytes.
 * Returns 1 << (mailbox_idx & 0x0F).
 *
 * @param mailbox_idx  Mailbox index (0-15 for primary bank)
 * @return Bitmask for this mailbox (1, 2, 4, 8, ... 0x8000)
 */
uint16_t can_get_mailbox_config(uint8_t mailbox_idx)
{
    /* Bitmask lookup table from ROM:0xDBAC */
    static const uint16_t mailbox_bitmask_table[16] = {
        0x0001, 0x0002, 0x0004, 0x0008,
        0x0010, 0x0020, 0x0040, 0x0080,
        0x0100, 0x0200, 0x0400, 0x0800,
        0x1000, 0x2000, 0x4000, 0x8000
    };
    return mailbox_bitmask_table[mailbox_idx & 0x0F];
}

/* --- diag_getsr_3920 (ROM:0x3920) --- */
/* Save SR and set interrupt level. Used before critical CAN operations. */
uint32_t diag_getsr_3920(uint8_t level)
{
    /* On real SH-2E:
     *   stc sr, r0       ; read current SR
     *   and #0xF0, r0     ; mask interrupt bits
     *   cmp/hi r0, r4     ; if current level > requested
     *   bf locret         ;   no change needed
     *   ldc r4, sr        ; else set new level
     */
    (void)level;
    /* Host simulation: return 0 (no saved state) */
    return 0;
}

/* --- diag_setsr_3934 (ROM:0x3934) --- */
/* Restore SR (re-enable interrupts). */
void diag_setsr_3934(uint32_t saved_sr)
{
    /* On real SH-2E:
     *   tst r4, r4        ; if saved_sr == 0
     *   bf locret         ;   no restore needed
     *   ldc r4, sr        ; else restore SR
     */
    (void)saved_sr;
}

/* --- can_pack_tx_msg_write_verify (ROM:0xCF42) --- */
/* Write CAN data to mailbox hardware with verification.
 * ROM:0xCF42: gets mailbox data register, computes per-mailbox offset,
 * disables interrupts, calls eeprom_write_verify_bytes for verified write.
 *
 * Data area base: 0xFFFFE4B0 (HCAN_MBOX_DATA_BASE)
 * Per-mailbox offset: (mailbox_idx & 0x0F) × 8 bytes
 *
 * @param mailbox_idx  Mailbox index (0-15)
 * @param dlc          Data length code (1-8)
 * @param data_ptr     Pointer to source data buffer
 * @param zero         Zero parameter (passed to write function)
 * @return 0 on success
 */
int can_pack_tx_msg_write_verify(uint8_t mailbox_idx, uint8_t dlc,
                                  const uint8_t *data_ptr, uint8_t zero)
{
    volatile uint16_t *mbox_data_reg;
    uint32_t data_area_addr;
    uint32_t saved_sr;
    uint8_t i;

    /* Step 1: Get mailbox data register address */
    mbox_data_reg = can_get_mailbox_offset_high(mailbox_idx, HCAN_MBOX_DATA_BASE);

    /* Step 2: Disable interrupts for critical section */
    saved_sr = diag_getsr_3920(0xE0);

    /* Step 3: Compute per-mailbox data area offset */
    /* Each mailbox has 8 bytes of data space in the HCAN data area */
    data_area_addr = (uint32_t)(uintptr_t)mbox_data_reg;
    data_area_addr += (uint32_t)(mailbox_idx & 0x0F) * 8;

    /* Step 4: Write data bytes to mailbox data area */
    volatile uint8_t *dest = (volatile uint8_t *)(uintptr_t)data_area_addr;
    for (i = 0; i < dlc && i < 8; i++) {
        dest[i] = data_ptr[i];
    }
    /* Zero-fill remaining bytes if dlc < 8 */
    for (; i < 8; i++) {
        dest[i] = zero;
    }

    /* Step 5: Verify write by reading back */
    for (i = 0; i < dlc && i < 8; i++) {
        if (dest[i] != data_ptr[i]) {
            /* Verify failed — restore interrupts and return error */
            diag_setsr_3934(saved_sr);
            return -1;
        }
    }

    /* Step 6: Re-enable interrupts */
    diag_setsr_3934(saved_sr);

    return 0;
}

/* --- can_pack_tx_msg_copy (ROM:0xCEF4) --- */
/* Copy CAN data from mailbox hardware to buffer.
 * ROM:0xCEF4: same structure as write_verify but uses bounded_byte_copy
 * to read from mailbox data area into destination buffer.
 *
 * @param mailbox_idx  Mailbox index (0-15)
 * @param dlc          Data length code (1-8)
 * @param data_ptr     Pointer to destination buffer
 * @param zero         Zero parameter
 * @return 0 on success
 */
int can_pack_tx_msg_copy(uint8_t mailbox_idx, uint8_t dlc,
                          uint8_t *data_ptr, uint8_t zero)
{
    volatile uint16_t *mbox_data_reg;
    uint32_t data_area_addr;
    uint32_t saved_sr;
    uint8_t i;

    /* Step 1: Get mailbox data register address */
    mbox_data_reg = can_get_mailbox_offset_high(mailbox_idx, HCAN_MBOX_DATA_BASE);

    /* Step 2: Disable interrupts */
    saved_sr = diag_getsr_3920(0xE0);

    /* Step 3: Compute per-mailbox data area offset */
    data_area_addr = (uint32_t)(uintptr_t)mbox_data_reg;
    data_area_addr += (uint32_t)(mailbox_idx & 0x0F) * 8;

    /* Step 4: Copy data from mailbox to destination buffer */
    volatile const uint8_t *src = (volatile const uint8_t *)(uintptr_t)data_area_addr;
    for (i = 0; i < dlc && i < 8; i++) {
        data_ptr[i] = src[i];
    }

    /* Step 5: Re-enable interrupts */
    diag_setsr_3934(saved_sr);

    (void)zero;  /* ROM passes zero to bounded_byte_copy, not needed here */

    return 0;
}

/* ====================================================================== */
/*  CAN Setup (ROM:0xDC8C)                                                 */
/* ====================================================================== */

/**
 * can_setup — Initialize CAN0 and CAN1 controllers.
 *
 * ROM address: 0xDC8C
 *
 * Iterates over 2 controllers (CAN0, CAN1).
 * For CAN0: selects primary (0x4EA60) or alternate (0x4EB60) config
 *           based on [0xB5A4].
 * For CAN1: uses 0x4EC60 config (6 entries).
 * Calls CANControllerSetup (0x9878) for each controller.
 * Calls canMessageSetup (0x2B320) to configure individual mailboxes.
 * Sets [0xFFFFA410]=1 when CAN0 ready, [0xFFFFA411]=0 when CAN1 ready.
 */
void can_setup(void)
{
    const uint8_t *tx_config;
    uint8_t controller_idx;
    uint8_t configured = 0;

    /* Clear init flags */
    CAN_GATE_INIT_CAN0 = 0;
    CAN_GATE_INIT_CAN1 = 0;

    /* Select TX config table based on [0xB5A4] */
    tx_config = can_get_tx_config_table();

    /* Iterate CAN0 (idx=0) and CAN1 (idx=1) */
    for (controller_idx = 0; controller_idx < 2; controller_idx++) {
        if (controller_idx == 0) {
            /* CAN0: setup with TX config table (16 entries) */
            /* TODO(ROM:0xDCC0): call CANControllerSetup(0, tx_config, 16) */
            configured |= can_message_setup(0, tx_config);
        } else {
            /* CAN1: setup with RX config table (6 entries) */
            /* TODO(ROM:0xDCE0): call CANControllerSetup(1, CAN1_RX_CONFIG, 6) */
            configured |= can_message_setup(1, (const uint8_t *)(uintptr_t)CAN1_RX_CONFIG);
        }
    }

    /* Set init-complete flags if all controllers configured */
    if (configured) {
        CAN_GATE_INIT_CAN0 = 1;
        CAN_GATE_INIT_CAN1 = 0;  /* CAN1 ready, set to 0 per ROM behavior */
    }
}

/**
 * can_message_setup — Configure mailboxes for one controller.
 * ROM address: 0x2B320
 *
 * @param controller  0=CAN0, 1=CAN1
 * @param table_ptr   Pointer to mailbox config table (16B entries)
 * @return Bitmask of configured mailboxes
 */
uint8_t can_message_setup(uint8_t controller, const void *table_ptr)
{
    const uint8_t *table = (const uint8_t *)table_ptr;
    uint8_t configured = 0;

    /* Determine PFC base for this controller */
    /* CAN0: 0xFFFFE400, CAN1: 0xFFFFE600 */
    uint16_t pfc_base = controller ? 0xFFFFE600 : 0xFFFFE400;

    /* Check if controller is in expected state */
    uint8_t current_mode = *(volatile uint8_t *)(uintptr_t)pfc_base;
    uint8_t expected_mode = controller ? 0 : 0;

    if (current_mode != expected_mode) {
        configured = 1;  /* State differs, mark as needing reset */
    }

    /* Configure each mailbox from table */
    /* TODO(ROM:0x2B320): iterate entries, call setCANRegisters per mailbox */

    (void)table;
    return configured;
}

/* ====================================================================== */
/*  Mailbox HW Configuration (ROM:0xCC9C)                                  */
/* ====================================================================== */

/**
 * setCANRegisters — Write config entry to HW registers.
 * ROM address: 0xCC9C
 *
 * @param controller  0=CAN0, 1=CAN1
 * @param config      Pointer to 16-byte config entry
 */
void setCANRegisters(uint8_t controller, const uint8_t *config)
{
    uint8_t slot = can_parse_mailbox_slot(config);
    uint8_t dlc = can_parse_mailbox_dlc(config);
    uint32_t buf_ptr = can_parse_mailbox_buf_ptr(config);

    /* Enable mailbox interrupt */
    can_enable_mailbox_int(controller, slot);

    /* Init IRQ mask */
    can_init_mailbox_irq_mask(controller, 0);

    /* Set mode + DLC */
    can_set_mailbox_mode_dlc(controller, slot, dlc);

    /* Set buffer pointer and flow control */
    can_set_mailbox_ptr_control(controller, slot,
                                (uint16_t)(buf_ptr & 0xFFFF),
                                (uint8_t)(buf_ptr >> 16), 0);

    /* Set ID acceptance mode */
    can_set_mailbox_id_mode(controller, slot, 0);
}

/* ====================================================================== */
/*  Mailbox Configuration Register Writes                                  */
/* ====================================================================== */

/* --- can_enable_mailbox_int (ROM:0xCC6C) --- */
/* Enable interrupt for a specific mailbox.
 * ROM:0xCC6C: selects CAN0 (0xFFFFE401) or CAN1 (0xFFFFE601) base,
 * then calls the HCAN interrupt enable function (loc_9E14).
 *
 * @param controller  0=CAN0, 1=CAN1
 * @param mailbox     Mailbox index
 */
void can_enable_mailbox_int(uint8_t controller, uint8_t mailbox)
{
    /* ROM:0xCC6C: select register base for the controller */
    uint32_t reg_base = controller ? 0xFFFFE601 : 0xFFFFE401;

    /* ROM:0xCC7C: call loc_9E14 with (reg_base - 1, mailbox)
     * loc_9E14 is the HCAN interrupt enable function that sets
     * the interrupt enable bit for the specified mailbox.
     * On host simulation, we write the enable bit directly. */
    volatile uint8_t *int_enable_reg = (volatile uint8_t *)(uintptr_t)(reg_base - 1);
    uint8_t current = *int_enable_reg;
    current |= (uint8_t)(1U << (mailbox & 0x07));
    *int_enable_reg = current;
}

/* --- can_init_mailbox_irq_mask (ROM:0xCD12) --- */
/* Initialize all HCAN mailbox registers to default state.
 * ROM:0xCD12: disables interrupts, writes initial values to all
 * mailbox control/status/data registers, re-enables interrupts.
 *
 * Register initialization sequence (CAN0):
 *   0xFFFFE406 = 0x0000  (mailbox offset/status)
 *   0xFFFFE408 = 0x0000  (mailbox ready)
 *   0xFFFFE40A = 0x0000  (mailbox control)
 *   0xFFFFE40C = 0xFEFE  (mailbox RX status mask)
 *   0xFFFFE40E = 0xFEFE  (mailbox RX status)
 *   0xFFFFE410 = 0xFFFE  (mailbox data status)
 *   0xFFFFE41A = 0xFFFE  (mailbox data ready)
 *   0xFFFFE412 = 0xFF12  (mailbox interrupt enable)
 *
 * @param controller  0=CAN0, 1=CAN1
 * @param mask        IRQ mask value (not used in ROM, always 0)
 */
void can_init_mailbox_irq_mask(uint8_t controller, uint16_t mask)
{
    uint32_t saved_sr;
    uint32_t reg_base;

    (void)mask;  /* ROM always writes 0 for initial state */

    /* Disable interrupts for register initialization */
    saved_sr = diag_getsr_3920(0xE0);

    /* Select CAN0 or CAN1 register base */
    reg_base = controller ? 0xFFFFE600 : 0xFFFFE400;

    /* Write initial values to all mailbox registers */
    hcan_write16(reg_base + 0x06, 0x0000);  /* mailbox offset/status */
    hcan_write16(reg_base + 0x08, 0x0000);  /* mailbox ready */
    hcan_write16(reg_base + 0x0A, 0x0000);  /* mailbox control */
    hcan_write16(reg_base + 0x0C, 0xFEFE);  /* mailbox RX status mask */
    hcan_write16(reg_base + 0x0E, 0xFEFE);  /* mailbox RX status */
    hcan_write16(reg_base + 0x10, 0xFFFE);  /* mailbox data status */
    hcan_write16(reg_base + 0x1A, 0xFFFE);  /* mailbox data ready */
    hcan_write16(reg_base + 0x12, 0xFF12);  /* mailbox interrupt enable */

    /* Re-enable interrupts */
    diag_setsr_3934(saved_sr);
}

/* --- can_set_mailbox_mode_dlc (ROM:0xCDC4) --- */
/* Set mailbox mode and DLC in the HCAN control register.
 * ROM:0xCDC4: gets register address via getHCANRegAddr(controller, 0xFFFFE400),
 * disables interrupts, clears bits [2] of control byte,
 * ORs in (mode_dlc << 4), writes back, re-enables interrupts.
 *
 * @param controller  0=CAN0, 1=CAN1
 * @param mailbox     Mailbox index
 * @param mode_dlc    Mode (upper nibble) | DLC (lower 2 bits)
 */
void can_set_mailbox_mode_dlc(uint8_t controller, uint8_t mailbox, uint8_t mode_dlc)
{
    uint32_t saved_sr;
    uint32_t ctrl_reg;
    uint8_t current;
    (void)mailbox;

    /* Get controller register address */
    ctrl_reg = getHCANRegAddr(controller, 0xFFFFE400);

    /* Disable interrupts */
    saved_sr = diag_getsr_3920(0xE0);

    /* Read current control byte, clear bits [2], OR in mode_dlc << 4 */
    current = hcan_read8(ctrl_reg);
    current &= 0xFB;  /* Clear bit 2 */
    current |= (uint8_t)((mode_dlc & 0x0F) << 4);
    hcan_write8(ctrl_reg, current);

    /* Re-enable interrupts */
    diag_setsr_3934(saved_sr);
}

/* --- can_set_mailbox_ptr_control (ROM:0xCDE0) --- */
/* Set mailbox buffer pointer and flow control registers.
 * ROM:0xCDE0: gets register address via getHCANRegAddr(controller, 0xFFFFE400),
 * disables interrupts, writes buffer pointer (ptr_hi:ptr_lo) and flow control
 * to the mailbox control registers, re-enables interrupts.
 *
 * @param controller  0=CAN0, 1=CAN1
 * @param mailbox     Mailbox index
 * @param ptr_lo      Buffer pointer low (16-bit)
 * @param ptr_hi      Buffer pointer high (8-bit, upper byte of 24-bit addr)
 * @param flow_ctrl   Flow control value
 */
void can_set_mailbox_ptr_control(uint8_t controller, uint8_t mailbox,
                                  uint16_t ptr_lo, uint8_t ptr_hi,
                                  uint8_t flow_ctrl)
{
    uint32_t saved_sr;
    uint32_t ctrl_reg;
    uint8_t current;
    (void)mailbox;

    /* Get controller register address */
    ctrl_reg = getHCANRegAddr(controller, 0xFFFFE400);

    /* Disable interrupts */
    saved_sr = diag_getsr_3920(0xE0);

    /* Read current control byte, clear bits [2], OR in flow_ctrl << 4 */
    current = hcan_read8(ctrl_reg);
    current &= 0xFB;  /* Clear bit 2 */
    current |= (uint8_t)((flow_ctrl & 0x0F) << 4);
    hcan_write8(ctrl_reg, current);

    /* Write buffer pointer low (16-bit) to register + offset */
    hcan_write16(ctrl_reg + 0x02, ptr_lo);

    /* Write buffer pointer high (8-bit) to register + offset */
    hcan_write8(ctrl_reg + 0x04, ptr_hi);

    /* Re-enable interrupts */
    diag_setsr_3934(saved_sr);
}

/* --- can_set_mailbox_id_mode (ROM:0xCE34) --- */
/* Set ID acceptance mode for mailbox.
 * ROM:0xCE34: gets register address via getHCANRegAddr(controller, 0xFFFFE400),
 * disables interrupts, clears bit 7 of control byte,
 * ORs in (id_mode << 7), writes back, re-enables interrupts.
 *
 * @param controller  0=CAN0, 1=CAN1
 * @param mailbox     Mailbox index
 * @param id_mode     ID mode configuration (0=standard, 1=extended)
 */
void can_set_mailbox_id_mode(uint8_t controller, uint8_t mailbox, uint16_t id_mode)
{
    uint32_t saved_sr;
    uint32_t ctrl_reg;
    uint8_t current;
    (void)mailbox;

    /* Get controller register address */
    ctrl_reg = getHCANRegAddr(controller, 0xFFFFE400);

    /* Disable interrupts */
    saved_sr = diag_getsr_3920(0xE0);

    /* Read current control byte, clear bit 7, OR in id_mode << 7 */
    current = hcan_read8(ctrl_reg);
    current &= 0x7F;  /* Clear bit 7 */
    current |= (uint8_t)((id_mode & 0x01) << 7);
    hcan_write8(ctrl_reg, current);

    /* Re-enable interrupts */
    diag_setsr_3934(saved_sr);
}

/* ====================================================================== */
/*  CAN TX Frame Sender (ROM:0x9AE4)                                       */
/* ====================================================================== */

/**
 * can_tx_send_frame — Low-level CAN frame transmission.
 *
 * ROM address: 0x9AE4
 *
 * Algorithm (from disasm):
 *   1. Save SR, disable interrupts (diag_getsr 0x90)
 *   2. Resolve mailbox via can_get_mailbox_offset_high(0xFFFFE406)
 *   3. Read mailbox status, check if busy
 *   4. If not busy:
 *      a. Write config to mailbox (can_get_mailbox_config)
 *      b. Write data via can_pack_tx_msg_write_verify
 *      c. Set ready bit
 *   5. If busy: return 1
 *   6. Restore SR (diag_setsr)
 *   7. Return 0 (success) or 1 (busy)
 *
 * @param frame  Pointer to can_tx_frame descriptor
 * @return 0 on success, 1 if mailbox busy
 */
int can_tx_send_frame(const struct can_tx_frame *frame)
{
    volatile uint16_t *mbox_reg;
    uint16_t mbox_status;
    uint16_t mbox_config;
    uint32_t saved_sr;
    int result = 0;

    if (frame == NULL) {
        return 1;
    }

    /* Step 1: Disable interrupts */
    saved_sr = diag_getsr_3920(0x90);

    /* Step 2: Resolve mailbox register address */
    mbox_reg = can_get_mailbox_offset_high(frame->mailbox_idx, HCAN_MBOX_OFFSET);

    /* Step 3: Read mailbox status */
    mbox_status = *mbox_reg;

    /* Step 4: Get mailbox config and check busy */
    mbox_config = can_get_mailbox_config(frame->mailbox_idx);

    /* Check if mailbox is available (bit test) */
    if (!(mbox_config & mbox_status)) {
        /* Mailbox is free — proceed with TX */

        /* Write config word to mailbox ready register */
        volatile uint16_t *ready_reg = can_get_mailbox_offset_high(
            frame->mailbox_idx, HCAN_MBOX_READY);

        /* Get config and write it */
        mbox_config = can_get_mailbox_config(frame->mailbox_idx);
        *ready_reg = mbox_config;

        /* Write CAN ID + data to mailbox */
        can_pack_tx_msg_write_verify(frame->mailbox_idx,
                                      frame->dlc,
                                      frame->data_ptr, 0);

        /* Set ready bit to trigger transmission */
        volatile uint16_t *ready_reg2 = can_get_mailbox_offset_high(
            frame->mailbox_idx, HCAN_MBOX_OFFSET);
        mbox_config = can_get_mailbox_config(frame->mailbox_idx);
        *ready_reg2 = mbox_config;

        result = 0;  /* success */
    } else {
        /* Mailbox busy */
        result = 1;
    }

    /* Step 5: Restore interrupts */
    diag_setsr_3934(saved_sr);

    return result;
}

/* ====================================================================== */
/*  CAN TX Packer Functions (ROM function reconstructions)                 */
/* ====================================================================== */

/**
 * can41TXPack — Pack CAN ID 0x041 KCM/immobiliser response frame.
 * ROM address: 0x39348
 *
 * Packs per-cycle idle frame data into staging buffer.
 * This is called every cycle (no rate limiting).
 */
void can41TXPack(void)
{
    struct can_tx_frame frame;

    /* TODO(ROM:0x39348): pack KCM/immobiliser response data.
     * Reads immobiliser state from RAM and packs into 8-byte buffer.
     * Frame is sent every cycle as a heartbeat. */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0041;
    frame.mailbox = 0x09;       /* MB9 per config table */
    frame.dlc = 8;
    frame.mailbox_idx = 0x09;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0041;

    can_tx_send_frame(&frame);
}

/**
 * can_tx_rate_limit_0x201 — Rate-limited TX for CAN 0x201+0x203.
 * ROM address: 0x29FD2
 *
 * Counter at 0xFFFFBB74, fires every 4 calls.
 * Calls can201_pack_interpolation + can201_pack_staging for 0x201,
 * then falls to can203pack.
 */
void can_tx_rate_limit_0x201(void)
{
    CAN_RATE_CNT_201++;

    if (CAN_RATE_CNT_201 >= 4) {
        /* TODO(ROM:0x29FEA): call can201_pack_interpolation()
         * Packs RPM (u16 BE ÷4), vehicle speed (u16 BE (raw−10000)/100),
         * accelerator (byte6 ÷2) into CAN_TX_BUF_0201. */

        /* TODO(ROM:0x29FEE): call can201_pack_staging()
         * Copies packed data to TX mailbox staging area. */

        CAN_RATE_CNT_201 = 0;
    }

    /* Fall through to can203pack (ROM:0x2A274) */
    can203pack();
}

/**
 * can203pack — Pack CAN ID 0x0203 engine torque/status frame.
 * ROM address: 0x2A274
 */
void can203pack(void)
{
    struct can_tx_frame frame;

    /* TODO(ROM:0x2A274): pack engine torque and status data.
     * Reads computed torque value and engine status flags. */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0203;
    frame.mailbox = 0x02;       /* MB2 per config table */
    frame.dlc = 7;
    frame.mailbox_idx = 0x02;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0203;

    can_tx_send_frame(&frame);
}

/**
 * can251TX_getAndPack — Pack CAN ID 0x0251 engine data (every 2 cycles).
 * ROM address: 0x2AAB6
 */
void can251TX_getAndPack(void)
{
    struct can_tx_frame frame;

    /* TODO(ROM:0x2AAB6): pack engine data for CAN 0x251.
     * Called every 2 cycles from CANTX_Main. */
    frame.reserved_00 = 0;
    frame.can_id = 0x0251;
    frame.mailbox = 0x0B;       /* MB11 per config */
    frame.dlc = 8;
    frame.mailbox_idx = 0x0B;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0250;

    can_tx_send_frame(&frame);
}

/**
 * can_tx_rate_limit_0x231 — Rate-limited TX for CAN 0x231.
 * ROM address: calls 0x2D402 → canPackandTx231 (0x2D434)
 *
 * Conditional on [0xB5A4]==1 (automatic transmission mode).
 */
void can_tx_rate_limit_0x231(void)
{
    struct can_tx_frame frame;

    /* Only transmit if [0xB5A4]==1 (AT mode) */
    if (CAN_GATE_B5A4 != 1) {
        return;
    }

    /* TODO(ROM:0x2D434): pack engine state / gear selector data.
     * Conditional: only when [0xB5A4]==1. */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0231;
    frame.mailbox = 0x04;       /* MB4 per config */
    frame.dlc = 5;
    frame.mailbox_idx = 0x04;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0231;

    can_tx_send_frame(&frame);
}

/**
 * can420TXPack — Pack CAN ID 0x0420 coolant/MIL frame.
 * ROM address: 0x29A0C
 *
 * Packs coolant temperature gauge (byte0 raw−40) and MIL/oil/batt/water
 * warning lamps into 7-byte frame.
 */
void can420TXPack(void)
{
    struct can_tx_frame frame;

    /* TODO(ROM:0x29A0C): pack coolant temp and warning lamps.
     * Byte 0: coolant temp (raw − 40 for gauge)
     * Bytes 1-6: MIL, oil pressure, battery, water warning lamp bits */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0420;
    frame.mailbox = 0x05;       /* MB5 per config */
    frame.dlc = 7;
    frame.mailbox_idx = 0x05;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0420;

    can_tx_send_frame(&frame);
}

/**
 * can650TX_getAndPack — Pack CAN ID 0x0650 cruise-control lamps.
 * ROM address: 0x2C806
 *
 * 1-byte frame: bit6 = cruise active, bit7 = cruise main switch.
 */
void can650TX_getAndPack(void)
{
    struct can_tx_frame frame;

    /* TODO(ROM:0x2C806): pack cruise control lamp status.
     * Byte 0: bit6=cruise active, bit7=cruise main */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0650;
    frame.mailbox = 0x08;       /* MB8 per config */
    frame.dlc = 1;
    frame.mailbox_idx = 0x08;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0650;

    can_tx_send_frame(&frame);
}

/**
 * can240TX_pack — Pack CAN ID 0x0240 OBD data frame.
 * ROM address: 0x4C888
 */
void can240TX_pack(void)
{
    struct can_tx_frame frame;

    /* TODO(ROM:0x4C888): pack OBD data for CAN 0x240.
     * Transmission / gear data. Byte 3 may be coolant per field data. */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0240;
    frame.mailbox = 0x0A;       /* MB10 per config */
    frame.dlc = 8;
    frame.mailbox_idx = 0x0A;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0240;

    can_tx_send_frame(&frame);
}

/**
 * can250TX_pack — Pack CAN ID 0x0250 OBD data frame.
 * ROM address: 0x4C984
 */
void can250TX_pack(void)
{
    struct can_tx_frame frame;

    /* TODO(ROM:0x4C984): pack OBD data for CAN 0x250.
     * Injection pulse width. Byte 3 may be IAT per field data. */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0250;
    frame.mailbox = 0x0B;       /* MB11 per config */
    frame.dlc = 8;
    frame.mailbox_idx = 0x0B;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0250;

    can_tx_send_frame(&frame);
}

/**
 * can620TX_pack — Pack CAN ID 0x0620 fan/AC status frame.
 * ROM address: 0x33A68
 */
void can620TX_pack(void)
{
    struct can_tx_frame frame;

    /* TODO(ROM:0x33A68): pack fan and AC status data. */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0620;
    frame.mailbox = 0x06;       /* MB6 per config */
    frame.dlc = 7;
    frame.mailbox_idx = 0x06;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0620;

    can_tx_send_frame(&frame);
}

/**
 * can630TX_dispatch — Pack CAN ID 0x0630 cooling fan frame.
 * ROM address: 0x33974
 */
void can630TX_dispatch(void)
{
    struct can_tx_frame frame;

    /* TODO(ROM:0x33974): pack cooling fan data. */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0630;
    frame.mailbox = 0x07;       /* MB7 per config */
    frame.dlc = 8;
    frame.mailbox_idx = 0x07;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0630;

    can_tx_send_frame(&frame);
}

/* ====================================================================== */
/*  CAN TX Dispatcher (ROM:0xDDF0)                                         */
/* ====================================================================== */

/**
 * CANTX_Main — Main CAN TX dispatcher (periodic).
 *
 * ROM address: 0xDDF0
 *
 * Gate check (6 RAM flags):
 *   [0xA40F] < 100     (boot counter must be < 100)
 *   [0xA40A] == 0      (must be 0)
 *   [0xA410] == 0      (CAN0 must be initialized)
 *   [0xA411] == 0      (CAN1 must be initialized)
 *   [0xAAE0] == 1      (system enable)
 *   [0xB5E8] != 1      (not inhibited)
 *
 * If all gates pass:
 *   1. can41TXPack()             — CAN ID 0x041 (per-cycle)
 *   2. can_tx_rate_limit_0x201() — CAN ID 0x201+0x203 (every 4)
 *   3. counter_check_dispatch_2A242() — CAN ID 0x215 (throttle)
 *   4. can251TX_getAndPack()     — CAN ID 0x251 (every 2)
 *   5. if [0xB5A4]==1: can_tx_rate_limit_0x231() — CAN ID 0x231
 *   6. can240TX_pack()           — CAN ID 0x240 (every 25)
 *   7. can250TX_pack()           — CAN ID 0x250 (every 25)
 *   8. incr_counter_saturated_299DA() — CAN 0x216 timeout
 *   9. can620TX_pack()           — CAN ID 0x620 (per-cycle)
 *  10. can630TX_dispatch()       — CAN ID 0x630 (per-cycle)
 *  11. can650TX_getAndPack()     — CAN ID 0x650 (every 12)
 *
 * Clears flag at [0xC241] when done.
 */
void CANTX_Main(void)
{
    /* Gate check: all 6 conditions must pass */
    if (CAN_GATE_BOOT_COUNTER >= 100) {
        goto clear_flag;
    }
    if (CAN_GATE_A40A != 0) {
        goto clear_flag;
    }
    if (CAN_GATE_INIT_CAN0 != 0) {
        goto clear_flag;
    }
    if (CAN_GATE_INIT_CAN1 != 0) {
        goto clear_flag;
    }
    if (CAN_GATE_SYS_ENABLE != 1) {
        goto clear_flag;
    }
    if (CAN_GATE_INHIBIT == 1) {
        goto clear_flag;
    }

    /* All gates passed — dispatch TX packers */

    /* 1. CAN ID 0x041: KCM/immobiliser response (per-cycle) */
    can41TXPack();

    /* 2. CAN ID 0x201+0x203: engine torque/status (every 4 cycles) */
    can_tx_rate_limit_0x201();

    /* 3. CAN ID 0x215: throttle position (counter-based dispatch) */
    /* TODO(ROM:0x2A242): counter_check_dispatch_2A242 for CAN 0x215 */

    /* 4. CAN ID 0x251: engine data (every 2 cycles) */
    can251TX_getAndPack();

    /* 5. CAN ID 0x231: engine state (conditional on [0xB5A4]==1) */
    if (CAN_GATE_B5A4 == 1) {
        can_tx_rate_limit_0x231();
    }

    /* 6. CAN ID 0x240: OBD data (every 25 cycles) */
    /* TODO(ROM:0x4C85A): mutex_trylock_4C85A → can240TX_pack */

    /* 7. CAN ID 0x250: OBD data (every 25 cycles) */
    /* TODO(ROM:0x4C956): message_queue_send_4C956 → can250TX_pack */

    /* 8. CAN 0x216 timeout counter */
    incr_counter_saturated_299DA();

    /* 9. CAN ID 0x620: fan/AC status (per-cycle) */
    can620TX_pack();

    /* 10. CAN ID 0x630: cooling fan data (per-cycle) */
    can630TX_dispatch();

    /* 11. CAN ID 0x650: cruise-control lamps (every 12 cycles) */
    can650TX_getAndPack();

clear_flag:
    /* Clear TX gate flag */
    CAN_GATE_TX_FLAG = 0;
}

/* ====================================================================== */
/*  CAN RX Functions (ROM function reconstructions)                        */
/* ====================================================================== */

/**
 * placeCANRX — Read CAN frame from HW mailbox.
 * ROM address: 0x99C4
 *
 * Reads CAN RX data via PFC 0xFFFFE40E/0xFFFFE41A, retries up to 5x,
 * copies data via can_pack_tx_msg_copy.
 *
 * @param config  Pointer to mailbox config entry (16 bytes)
 * @return 0 on success, non-zero on error
 */
int placeCANRX(const uint8_t *config)
{
    uint8_t mailbox_idx;
    uint8_t dlc;
    uint32_t buf_ptr;
    volatile uint16_t *mbox_status_reg;
    volatile uint16_t *mbox_data_reg;
    uint16_t status;
    int retry;
    uint32_t saved_sr;

    if (config == NULL) {
        return -1;
    }

    mailbox_idx = can_parse_mailbox_slot(config);
    dlc = can_parse_mailbox_dlc(config);
    buf_ptr = can_parse_mailbox_buf_ptr(config);

    /* Get mailbox status register (0xFFFFE40E) */
    mbox_status_reg = can_get_mailbox_offset_high(mailbox_idx, HCAN_REG_MBOX_STATUS);

    /* Check if data is available */
    status = *mbox_status_reg;
    uint16_t config_word = can_get_mailbox_config(mailbox_idx);

    if (!(status & config_word)) {
        /* No data available */
        return -1;
    }

    /* Disable interrupts for critical section */
    saved_sr = diag_getsr_3920(0x90);

    /* Get data register (0xFFFFE41A) */
    mbox_data_reg = can_get_mailbox_offset_high(mailbox_idx, HCAN_REG_MBOX_DATA_READY);

    /* Write config to data register */
    config_word = can_get_mailbox_config(mailbox_idx);
    *mbox_data_reg = config_word;

    /* Copy data from mailbox to buffer */
    uint8_t *buf = (uint8_t *)(uintptr_t)buf_ptr;
    can_pack_tx_msg_copy(mailbox_idx, dlc, buf, 0);

    /* Retry loop (up to 5 retries per ROM analysis) */
    for (retry = 0; retry < 5; retry++) {
        /* Re-read status */
        mbox_data_reg = can_get_mailbox_offset_high(mailbox_idx, HCAN_REG_MBOX_DATA_READY);
        config_word = can_get_mailbox_config(mailbox_idx);
        *mbox_data_reg = config_word;

        /* TODO(ROM:0x9A38): verify data copy and retry if needed */
    }

    /* Restore interrupts */
    diag_setsr_3934(saved_sr);

    return 0;
}

/* --- CAN RX Handler Functions --- */

/**
 * CAN212RX_Main — Process CAN ID 0x212 ABS/DSC/brake lamps.
 * ROM address: 0x2C0C4
 *
 * Unpacks brake lamp data:
 *   Byte 3: DSC-off indicator
 *   Byte 4: brake/handbrake + ABS
 *   Byte 5: TCS status
 */
void CAN212RX_Main(void)
{
    uint8_t buf[8];
    uint32_t saved_sr;

    /* TODO(ROM:0x2C0C4): read CAN1 mailbox for ID 0x212.
     * Uses placeCANRX with CAN1 config entry 0. */

    /* Placeholder: read from HW mailbox */
    saved_sr = diag_getsr_3920(0x90);
    /* TODO: actual HW read sequence */
    diag_setsr_3934(saved_sr);

    /* Unpack into staging buffer at CAN_RX_BUF_0212 */
    (void)buf;
}

/**
 * can4B0RX_unpack — Process CAN ID 0x04B0 wheel speeds.
 * ROM address: 0x2BE6E
 *
 * Unpacks DSC wheel speeds (4× u16 BE):
 *   ((raw − 10000) / 100) → km/h
 *   Bytes 0-1: FL, 2-3: FR, 4-5: RL, 6-7: RR
 */
void can4B0RX_unpack(void)
{
    /* TODO(ROM:0x2BE6E): read CAN1 mailbox for ID 0x4B0.
     * Unpack 4 wheel speeds from 8-byte frame.
     * Store to CAN_RX_BUF_04B0 staging area. */
}

/**
 * can47RX_Main — Process CAN ID 0x047 KCM/immobiliser request.
 * ROM address: 0x3939C
 *
 * Reads immobiliser challenge/request from CAN1 MB7.
 * Part of the key-on chat sequence between KCM and ECU.
 */
void can47RX_Main(void)
{
    /* TODO(ROM:0x3939C): read CAN1 mailbox for ID 0x047.
     * Immobiliser request data used by immo_state_machine_entry. */
}

/**
 * can4B1RX_event_check — Process CAN ID 0x04B1 DSC request.
 * ROM address: 0x4C78C
 */
void can4B1RX_event_check(void)
{
    /* TODO(ROM:0x4C78C): check for DSC request events on CAN0 ID 0x4B1. */
}

/**
 * can4C0RX_short — Process CAN ID 0x04C0 short message (DLC=1).
 * ROM address: 0x2C780
 */
void can4C0RX_short(void)
{
    /* TODO(ROM:0x2C780): process 1-byte CAN1 ID 0x04C0 message. */
}

/**
 * can430_4C0RX_dispatch — Process CAN ID 0x0430/0x04C0 cluster data.
 * ROM address: 0x33BA0
 *
 * Handles instrument cluster presence and misc short messages.
 */
void can430_4C0RX_dispatch(void)
{
    /* TODO(ROM:0x33BA0): dispatch CAN1 ID 0x0430 and 0x04C0 messages.
     * 0x0430: instrument cluster presence (immo role unconfirmed)
     * 0x04C0: short DLC=1 message */
}

/**
 * incr_counter_saturated_299DA — CAN 0x216 timeout counter.
 * ROM address: 0x299DA
 *
 * Increments saturation counter for CAN 0x216 timeout detection.
 * If counter reaches threshold, marks CAN 0x216 as timed out.
 */
void incr_counter_saturated_299DA(void)
{
    /* TODO(ROM:0x299DA): increment timeout counter for CAN 0x216.
     * Counter is at CAN_RATE_CNT_216 (0xFFFFCC36).
     * Threshold from ROM word at 0x7C396. */
}

/* ====================================================================== */
/*  CAN → UDS Bridge (ROM:0x4657C + 0x60774)                              */
/* ====================================================================== */

/**
 * can_msg_parse_4657C — CAN message parser (UDS bridge gatekeeper).
 * ROM address: 0x4657C
 *
 * Pre-conditions checked:
 *   1. OBD session active (obd_service_handler_6743C returns nonzero)
 *   2. CAN state [0xFFFFCD02] == 1
 *   3. DTC validation (diag_readvalue_8bit at 0x8758)
 *   4. CAN enable [0xFFFFA110] == 1
 *   5. Counter at [0xFFFFCC36] vs ROM threshold 0x7C396
 *
 * If [0xFFFFA110]==1: increments counter, checks against 0x7C396
 * If counter >= threshold: clears counter, sets [0xFFFFCC34]=1
 * If [0xFFFFA110]!=0: different path, checks against 0x7C394
 *
 * After all checks: reads [0x8758] again, if ==1 → calls
 *   can_to_uds_bridge with sid=0x67, req=1
 *
 * @param sid  Service ID (0x67 for UDS response)
 * @param req  Request type (1 or 2)
 */
void can_msg_parse_4657C(uint8_t sid, uint8_t req)
{
    uint16_t counter;
    uint16_t threshold;
    (void)sid;
    (void)req;

    /* Check 1: OBD session active */
    /* TODO(ROM:0x46588): call obd_service_handler_6743C() */
    /* if (obd_service_handler_6743C() == 0) goto reset_counters; */

    /* Check 2: CAN state */
    if (CAN_STATE_CD02 != 1) {
        goto reset_counters;
    }

    /* Check 3: DTC validation */
    /* TODO(ROM:0x465A4): call diag_readvalue_8bit(0x8758) */
    /* if (result != 0) goto reset_counters; */

    /* Check 4: CAN enable */
    if (CAN_ENABLE_A110 == 1) {
        /* Path A: CAN enabled — increment counter against 0x7C396 */
        counter = CAN_RATE_CNT_216;
        counter++;  /* TODO(ROM:0x465C2): add16bitSaturate */
        CAN_RATE_CNT_216 = counter;

        threshold = *(volatile uint16_t *)(uintptr_t)0x7C396;
        if (counter >= threshold) {
            /* Counter exceeded — set flag and clear */
            *(volatile uint8_t *)(uintptr_t)0xFFFFCC34 = 1;
        }
    } else {
        /* Path B: CAN not enabled — different threshold (0x7C394) */
        counter = CAN_RATE_CNT_216;
        counter++;  /* TODO(ROM:0x465E6): add16bitSaturate */
        CAN_RATE_CNT_216 = counter;

        threshold = *(volatile uint16_t *)(uintptr_t)0x7C394;
        if (counter >= threshold) {
            *(volatile uint8_t *)(uintptr_t)0xFFFFCC34 = 1;
        }
    }

    /* Check 5: DTC validation again */
    /* TODO(ROM:0x46608): call diag_readvalue_8bit(0x8758) */
    /* if (result == 1) { */
    /*     can_to_uds_bridge(sid, 1); */
    /* } */

    return;

reset_counters:
    /* Reset counters on failed pre-conditions */
    CAN_RATE_CNT_216 = 0;
    *(volatile uint16_t *)(uintptr_t)0xFFFFCC38 = 0;
}

/**
 * can_to_uds_bridge — Bridge CAN UDS request to udsHandler.
 * ROM address: 0x60774
 *
 * Receives CAN diagnostic request from can_msg_parse_4657C,
 * forwards to uds_task_entry (0x696DC) which calls udsHandler (0x697E8).
 *
 * Algorithm from disasm (0x6085C):
 *   1. Read session state from 0xFFFFD3F0
 *   2. Check security access flags at 0xFFFFD201
 *   3. If [0xFFFFD994]==1: set flag for security bypass
 *   4. If [0xFFFFD201]==1: security unlocked → set bypass flag
 *   5. Check [0xFFFFD6C4]==1 for gate
 *   6. Call sub_603FE to validate session/SID permissions
 *   7. If valid: call sub_603EC → dispatch to udsHandler
 *
 * @param sid   Service ID byte
 * @param req   Request type (1=physical 0x7E0, 2=broadcast 0x7DF)
 */
void can_to_uds_bridge(uint8_t sid, uint8_t req)
{
    uint8_t security_flag;
    uint8_t bypass_flag;
    uint8_t gate_check;

    /* Step 1: Check gate at 0xFFFFD6C4 — must be 1 to proceed */
    gate_check = *(volatile uint8_t *)0xFFFFD6C4;
    if (gate_check != 1) {
        return;
    }

    /* Step 2: Check security access at 0xFFFFD201 */
    security_flag = *(volatile uint8_t *)0xFFFFD201;

    /* Step 3: Determine bypass flag */
    bypass_flag = 0;
    if (security_flag == 1) {
        bypass_flag = 1;
    } else {
        uint8_t bypass_req = *(volatile uint8_t *)0xFFFFD994;
        if (bypass_req == 1) {
            bypass_flag = 1;
        }
    }

    /* Step 4: If not bypassed, check additional gate at 0xFFFFD299 */
    if (bypass_flag == 0) {
        uint8_t gate2 = *(volatile uint8_t *)0xFFFFD299;
        if (gate2 == 0) {
            /* Gate open: dispatch to udsHandler via request_type=req */
            /* ROM:0x608D8: sub_603EC(handler_idx, 2) */
        } else {
            return;  /* Blocked */
        }
    }

    /* Step 5: Forward to UDS handler
     * ROM:0x608EC-0x608F2: dispatch via uds_task_entry
     * The udsHandler (0x697E8) does linear scan of 0x5F57C table,
     * checks session gate, and calls the handler function. */
    (void)sid;
    (void)req;
}

/* ====================================================================== */
/*  CAN RX Dispatcher (ROM:0xDE8E)                                         */
/* ====================================================================== */

/**
 * secondary_system_controller — CAN RX dispatcher.
 * ROM address: 0xDE8E
 *
 * Called after CANTX_Main. Gate: [0xAAE0]==1, [0xB5E8]!=1, [0xA410]==0
 * Sequential dispatch:
 *   1. CAN212RX_Main()           — CAN ID 0x212 (ABS/DSC/brake lamps)
 *   2. can_lookup_table_indexed() — Unknown table lookup
 *   3. if [0xB5A4]==0: table_lookup_dispatch_29E9C()
 *   4. can430_4C0RX_dispatch()   — CAN ID 0x430/0x4C0
 *   5. can4B0RX_unpack()         — CAN ID 0x4B0 (wheel speeds)
 *   6. can4B1RX_event_check()    — CAN ID 0x4B1 (DSC request)
 *   7. can4C0RX_short()          — CAN ID 0x4C0 (short msg)
 *   8. can47RX_Main()            — CAN ID 0x047 (KCM/immobiliser)
 *
 * Falls through to immo_state_machine_entry (0x35D62).
 */
void secondary_system_controller(void)
{
    /* Gate check */
    if (CAN_GATE_SYS_ENABLE != 1) {
        goto immo_fallthrough;
    }
    if (CAN_GATE_INHIBIT == 1) {
        goto immo_fallthrough;
    }
    if (CAN_GATE_INIT_CAN0 != 0) {
        goto immo_fallthrough;
    }

    /* RX dispatch sequence */
    CAN212RX_Main();

    /* TODO(ROM:0x29BE8): can_lookup_table_indexed() */

    if (CAN_GATE_B5A4 == 0) {
        /* TODO(ROM:0x29E9C): table_lookup_dispatch_29E9C() */
    }

    can430_4C0RX_dispatch();
    can4B0RX_unpack();
    can4B1RX_event_check();
    can4C0RX_short();
    can47RX_Main();

immo_fallthrough:
    /* TODO(ROM:0x35D62): fall through to immo_state_machine_entry.
     * The immo FSM is called after CAN RX dispatch.
     * It reads CAN data via ImmoGetCANData (0x36870) and
     * writes back via setImmoCANTXData (0x369B8). */
}

/* ====================================================================== */
/*  Counter-Based Rate Limiters                                            */
/* ====================================================================== */

/**
 * counter_check_dispatch_2A242 — Rate-limited TX for CAN 0x215 (throttle).
 * ROM address: 0x2A242
 *
 * Counter-based dispatch: fires every N calls from CANTX_Main.
 */
static void counter_check_dispatch_2A242(void)
{
    struct can_tx_frame frame;

    /* ROM:0x2A242: counter-based rate limiting for CAN 0x215 (throttle).
     * Rate counter at 0xFFFFD7C4, threshold at 0xD7C6.
     * Increment counter, compare against threshold.
     * If counter >= threshold, reset and transmit.
     * Otherwise, skip this call. */
    volatile uint16_t *counter = (volatile uint16_t *)0xFFFFD7C4;
    volatile const uint16_t *threshold = (volatile const uint16_t *)0xFFFFD7C6;

    *counter += 1;
    if (*counter < *threshold) {
        return;  /* Rate limit — skip this call */
    }
    *counter = 0;  /* Reset counter */

    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0215;
    frame.mailbox = 0x03;       /* MB3 per config */
    frame.dlc = 8;
    frame.mailbox_idx = 0x03;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0215;

    can_tx_send_frame(&frame);
}
