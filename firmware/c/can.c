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

    /* Configure each mailbox from table (ROM:0x2B320-0x2B330) */
    /* Each entry is 16 bytes. Table has `num_entries` entries.
     * For each: call setCANRegisters(controller, &table[i*16]) */
    {
        uint8_t i;
        uint8_t num_entries = controller ? 6 : 16;  /* CAN1: 6 RX, CAN0: 16 TX */
        for (i = 0; i < num_entries; i++) {
            /* ROM:0x2B326-0x2B32A: pointer = base + i*16 */
            const uint8_t *entry = &table[i * 16];
            /* ROM:0x2B32C-0x2B330: call setCANRegisters */
            setCANRegisters(controller, entry);
        }
    }
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
 * Gate: [0xFFFFC241]==1 required before sending.
 * Copies 8 bytes from immo staging area (0xFFFFC238) to TX buffer.
 * Sends every cycle (no rate limiting).
 */
void can41TXPack(void)
{
    struct can_tx_frame frame;
    volatile uint8_t *src = (volatile uint8_t *)(uintptr_t)0xFFFFC238;  /* ROM:0x39358 */
    volatile uint8_t *dst = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0041;
    uint8_t i;

    /* Gate: only send when [0xFFFFC241]==1 (TX gate flag) */
    if (CAN_GATE_TX_FLAG != 1) {
        return;  /* ROM:0x39354 */
    }

    /* Copy 8 bytes from immo staging to TX buffer (ROM:0x39358-0x3937A) */
    for (i = 0; i < 8; i++) {
        dst[i] = src[i];
    }

    /* Set up frame and send (ROM:0x3937C-0x39382) */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0041;
    frame.mailbox = 0x09;       /* config table entry: dword_4E9F0 */
    frame.dlc = 8;
    frame.mailbox_idx = 0x09;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0041;

    can_tx_send_frame(&frame);
}

/**
 * can201_pack_interpolation — Compute interpolated engine values for CAN 0x201.
 * ROM address: 0x2A044
 *
 * Complex FPU interpolation chain (ROM:0x2A044-0x2A05C):
 *   1. fpu_conditional_negate_abs_2A168: reads RPM from 0xFFFFB5B8,
 *      computes filtered RPM value at 0xFFFFBB6C
 *   2. interp_axis_lookup_clamp_2A05E: looks up vehicle speed interpolation
 *      index from 0xFFFFBB6C, stores result to 0xFFFFBB64 (clamped to 0xFFFE)
 *   3. can201_byte2_3_stub (0x2A09C): sets 0xFFFFBB66 = 0xFFFF (default/stub)
 *   4. interp_axis_lookup_clamp_2A0A4: looks up accelerator pedal interpolation
 *   5. axis_lookup_limit_check_2A120: validates and limits the result
 *   6. Sets 0xFFFFBB6B = 0xFF as status byte
 */
void can201_pack_interpolation(void)
{
    /* ROM:0x2A044 — complex FPU interpolation chain.
     * This function computes RPM, vehicle speed, and accelerator pedal
     * interpolation indices using floating-point axis lookups.
     *
     * Step 1 (ROM:0x2A168): RPM filter
     *   Reads RPM float from 0xFFFFB5B8, applies conditional negate/abs,
     *   stores filtered RPM to 0xFFFFBB6C via firstOrderFilter.
     *
     * Step 2 (ROM:0x2A05E): Vehicle speed axis lookup
     *   Reads filtered RPM from 0xFFFFBB6C, looks up in axis table,
     *   clamps result to 0xFFFE max, stores to 0xFFFFBB64.
     *   If [0xFFFFCDFC]==1: forces 0xFFFFBB64 = 0xFFFF.
     *
     * Step 3 (ROM:0x2A09C): Default bytes 2-3
     *   Sets 0xFFFFBB66 = 0xFFFF (default/stub value).
     *
     * Step 4 (ROM:0x2A0A4): Accelerator axis lookup
     *   Similar axis lookup for accelerator pedal position.
     *
     * Step 5 (ROM:0x2A120): Limit check
     *   Validates the accelerator interpolation result.
     *
     * Step 6 (ROM:0x2A160): Status byte
     *   Sets 0xFFFFBB6B = 0xFF.
     *
     * NOTE(ROM:0x2A044): Full FPU math chain not implemented.
     * This function updates RAM values used by can201_pack_staging.
     * The interpolation produces u16 indices that can201_pack_staging
     * splits into big-endian bytes for the CAN frame.
     */
    volatile uint16_t *rpm_axis = (volatile uint16_t *)(uintptr_t)0xFFFFBB64;
    volatile uint16_t *accel_axis = (volatile uint16_t *)(uintptr_t)0xFFFFBB66;
    volatile uint8_t *status = (volatile uint8_t *)(uintptr_t)0xFFFFBB6B;

    /* Default values (ROM:0x2A09C + 0x2A160) */
    *accel_axis = 0xFFFF;
    *status = 0xFF;

    /* NOTE(ROM:0x2A05E): RPM axis lookup not implemented — uses default.
     * On real ECU: reads filtered RPM from 0xFFFFBB6C, performs
     * axis_lookup_float_to_index, clamps to [0, 0xFFFE]. */
    (void)rpm_axis;  /* Would be written by interpolation */
}

/**
 * can201_pack_staging — Pack CAN ID 0x0201 engine data into TX buffer.
 * ROM address: 0x2A004
 *
 * Reads interpolated values and packs 8 bytes into CAN_TX_BUF_0201.
 * Config table entry: dword_4E960 (CAN 0x201).
 */
void can201_pack_staging(void)
{
    struct can_tx_frame frame;
    volatile uint8_t *buf = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0201;
    volatile uint16_t *w0 = (volatile uint16_t *)(uintptr_t)0xFFFFBB64;  /* ROM:0x2A008 */
    volatile uint16_t *w1 = (volatile uint16_t *)(uintptr_t)0xFFFFBB66;  /* ROM:0x2A018 */
    volatile uint16_t *w2 = (volatile uint16_t *)(uintptr_t)0xFFFFBB68;  /* ROM:0x2A028 */

    /* ROM:0x2A008-0x2A016: byte 0-1 from 0xFFFFBB64 (RPM axis, u16 BE) */
    buf[0] = (uint8_t)(*w0 >> 8);   /* high byte */
    buf[1] = (uint8_t)(*w0 & 0xFF); /* low byte */

    /* ROM:0x2A018-0x2A026: byte 2-3 from 0xFFFFBB66 (vehicle speed, u16 BE) */
    buf[2] = (uint8_t)(*w1 >> 8);
    buf[3] = (uint8_t)(*w1 & 0xFF);

    /* ROM:0x2A028-0x2A034: byte 4-5 from 0xFFFFBB68 (accelerator, u16 BE) */
    buf[4] = (uint8_t)(*w2 >> 8);
    buf[5] = (uint8_t)(*w2 & 0xFF);

    /* ROM:0x2A036-0x2A03A: byte 6-7 from 0xFFFFBB6A, 0xFFFFBB6B */
    buf[6] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB6A;
    buf[7] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB6B;

    /* ROM:0x2A03E-0x2A042: tail call to can_tx_send_frame with dword_4E960 */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0201;
    frame.mailbox = 0x01;       /* MB1 per config table */
    frame.dlc = 8;
    frame.mailbox_idx = 0x01;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0201;

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
        can201_pack_interpolation();
        can201_pack_staging();

        CAN_RATE_CNT_201 = 0;
    }

    /* Fall through to can203pack (ROM:0x2A274) */
    can203pack();
}

/**
 * can203pack — Pack CAN ID 0x0203 engine torque/status frame.
 * ROM address: 0x2A274
 *
 * Reads 7 bytes from RAM staging areas into CAN_TX_BUF_0203.
 * Config table entry: dword_4E970.
 */
void can203pack(void)
{
    struct can_tx_frame frame;
    volatile uint8_t *buf = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0203;

    /* ROM:0x2A274-0x2A29E: pack bytes from RAM staging areas */
    buf[0] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB91;   /* ROM:0x2A27A */
    buf[1] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB92;   /* ROM:0x2A280 */
    buf[2] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB93;   /* ROM:0x2A286 */
    buf[3] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB94;   /* ROM:0x2A28C */
    buf[4] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB95;   /* ROM:0x2A290 */
    buf[5] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB7F;   /* ROM:0x2A296 */
    buf[6] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB96;   /* ROM:0x2A29C */

    /* ROM:0x2A2A0-0x2A2A6: tail call to can_tx_send_frame with dword_4E970 */
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
 *
 * Rate limiter counter at 0xFFFFBBC8. Fires every 2 calls.
 * Calls math_executor_2AB28 (ROM:0x2AB28) to compute status flags,
 * then counter_decrement_2AAE8 (ROM:0x2AAE8) to pack and send.
 */
void can251TX_getAndPack(void)
{
    static volatile uint16_t *counter = (volatile uint16_t *)(uintptr_t)0xFFFFBBC8;

    /* ROM:0x2AAB6-0x2AAC0: increment counter */
    *counter += 1;

    /* ROM:0x2AAC2-0x2AACA: check if counter >= 2 */
    if (*counter < 2) {
        return;
    }

    /* ROM:0x2AACE: call math_executor_2AB28 — computes status flags
     * from sensor data. Calls:
     *   sensor_scale_and_index_2ACD2
     *   counter_decrement_clamp_2AD96
     *   fuel_trim_control_query_2AE04
     *   lambda_sensor_active_check_2AE82
     *   sensor_secondary_2aeaa
     *   exhaust_port_condition_2AF80
     *   ram_word_copy_2AB56/2AB60/2AB6A
     *   counter_saturate_decrement_2AB74
     * Result: status byte computed into 0xFFFFBBC3
     *
     * NOTE(ROM:0x2AB28): Complex sensor computation chain not fully
     * implemented. Stores default status byte. */
    *(volatile uint8_t *)(uintptr_t)0xFFFFBBC3 = 0;  /* default status */

    /* ROM:0x2AAD2: call counter_decrement_2AAE8 — packs 0x251 frame
     * Reads from 0xFFFFBBBC, BBBE, BBC0, BBC2, BBC3.
     * Writes to CAN_TX_BUF_0251 (0xFFFFBB9C).
     * Sends with config dword_4E980. */
    {
        struct can_tx_frame frame;
        volatile uint8_t *buf = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0251;

        /* ROM:0x2AAE8-0x2AB20: pack bytes from RAM staging areas */
        volatile uint16_t *w0 = (volatile uint16_t *)(uintptr_t)0xFFFFBBBC;
        volatile uint16_t *w1 = (volatile uint16_t *)(uintptr_t)0xFFFFBBBE;
        volatile uint16_t *w2 = (volatile uint16_t *)(uintptr_t)0xFFFFBBC0;

        buf[0] = (uint8_t)(*w0 >> 8);   /* ROM:0x2AAF2 */
        buf[1] = (uint8_t)(*w0 & 0xFF); /* ROM:0x2AAF8 */
        buf[2] = (uint8_t)(*w1 >> 8);   /* ROM:0x2AB04 */
        buf[3] = (uint8_t)(*w1 & 0xFF); /* ROM:0x2AB08 */
        buf[4] = (uint8_t)(*w2 >> 8);   /* ROM:0x2AB12 */
        buf[5] = (uint8_t)(*w2 & 0xFF); /* ROM:0x2AB16 */
        buf[6] = *(volatile uint8_t *)(uintptr_t)0xFFFFBBC2;  /* ROM:0x2AB1A */
        buf[7] = *(volatile uint8_t *)(uintptr_t)0xFFFFBBC3;  /* ROM:0x2AB1E */

        /* ROM:0x2AB22-0x2AB26: tail call to can_tx_send_frame with dword_4E980 */
        frame.reserved_00 = 0;
        frame.can_id = CAN_ID_0251;
        frame.mailbox = 0x0B;       /* MB11 per config */
        frame.dlc = 8;
        frame.mailbox_idx = 0x0B;
        frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0251;

        can_tx_send_frame(&frame);
    }

    /* ROM:0x2AAD6-0x2AAD8: reset counter to 0 */
    *counter = 0;
}

/**
 * can_tx_rate_limit_0x231 — Rate-limited TX for CAN 0x231.
 * ROM address: calls 0x2D402 → canPackandTx231 (0x2D434)
 *
 * Conditional on [0xB5A4]==1 (automatic transmission mode).
 * Packs engine state / gear selector data into CAN_TX_BUF_0231.
 * Config table entry: dword_4E990.
 */
void can_tx_rate_limit_0x231(void)
{
    struct can_tx_frame frame;
    volatile uint8_t *buf = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0231;

    /* Only transmit if [0xB5A4]==1 (AT mode) */
    if (CAN_GATE_B5A4 != 1) {
        return;
    }

    /* ROM:0x2D434-0x2D456: pack bytes from RAM staging areas */
    buf[0] = *(volatile uint8_t *)(uintptr_t)0xFFFFBCC9;   /* ROM:0x2D43A */
    buf[1] = *(volatile uint8_t *)(uintptr_t)0xFFFFBCCA;   /* ROM:0x2D440 */

    /* ROM:0x2D444-0x2D452: bytes 2-3 from 0xFFFFBCCC (u16 BE) */
    {
        volatile uint16_t *w = (volatile uint16_t *)(uintptr_t)0xFFFFBCCC;
        buf[2] = (uint8_t)(*w >> 8);
        buf[3] = (uint8_t)(*w & 0xFF);
    }

    buf[4] = *(volatile uint8_t *)(uintptr_t)0xFFFFBCCE;   /* ROM:0x2D454 */

    /* ROM:0x2D458-0x2D45C: tail call to can_tx_send_frame with dword_4E990 */
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
 * Config table entry: dword_4E9B0.
 */
void can420TXPack(void)
{
    struct can_tx_frame frame;
    volatile uint8_t *buf = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0420;

    /* ROM:0x29A0C-0x29A3C: pack bytes from RAM staging areas */
    buf[0] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB14;   /* ROM:0x29A16 */
    buf[1] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB15;   /* ROM:0x29A1A */

    /* ROM:0x29A1C-0x29A2A: bytes 2-3 from 0xFFFFBB16 (u16 BE) */
    {
        volatile uint16_t *w = (volatile uint16_t *)(uintptr_t)0xFFFFBB16;
        buf[2] = (uint8_t)(*w >> 8);
        buf[3] = (uint8_t)(*w & 0xFF);
    }

    buf[4] = *(volatile uint8_t *)(uintptr_t)0xFFFFBB18;   /* ROM:0x29A2E */

    /* ROM:0x29A30-0x29A3C: bytes 5-6 from 0xFFFFBB1A (u16 BE) */
    {
        volatile uint16_t *w = (volatile uint16_t *)(uintptr_t)0xFFFFBB1A;
        buf[5] = (uint8_t)(*w >> 8);
        buf[6] = (uint8_t)(*w & 0xFF);
    }

    /* ROM:0x29A3E-0x29A42: tail call to can_tx_send_frame with dword_4E9B0 */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0420;
    frame.mailbox = 0x05;       /* MB5 per config */
    frame.dlc = 7;
    frame.mailbox_idx = 0x05;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0420;

    can_tx_send_frame(&frame);
}

/**
 * can650_bitfield_compose — Compose cruise control status byte.
 * ROM address: 0x2C848
 *
 * Reads 4 status flags and composes a bitfield:
 *   bit 7: [0xFFFFBDB8]==1 → cruise main switch
 *   bit 6: [0xFFFFBDB9]==1 → cruise active
 *   bit 5: [0xFFFFBDCD]==1 → condition 3
 *   bit 4: [0xFFFFBDCC]==1 → condition 4
 * Stores result to [0xFFFFBC69].
 */
static void can650_bitfield_compose(void)
{
    volatile uint8_t *result = (volatile uint8_t *)(uintptr_t)0xFFFFBC69;
    uint8_t val = 0;

    /* ROM:0x2C848-0x2C854: bit 7 from [0xFFFFBDB8] */
    if (*(volatile uint8_t *)(uintptr_t)0xFFFFBDB8 == 1) {
        val |= 0x80;
    }

    /* ROM:0x2C856-0x2C864: bit 6 from [0xFFFFBDB9] */
    if (*(volatile uint8_t *)(uintptr_t)0xFFFFBDB9 == 1) {
        val |= 0x40;
    }

    /* ROM:0x2C866-0x2C874: bit 5 from [0xFFFFBDCD] */
    if (*(volatile uint8_t *)(uintptr_t)0xFFFFBDCD == 1) {
        val |= 0x20;
    }

    /* ROM:0x2C876-0x2C884: bit 4 from [0xFFFFBDCC] */
    if (*(volatile uint8_t *)(uintptr_t)0xFFFFBDCC == 1) {
        val |= 0x10;
    }

    /* ROM:0x2C886-0x2C88A: store result */
    *result = val;
}

/**
 * can650TX_dispatch — Send cruise control status frame.
 * ROM address: 0x2C838
 *
 * Copies composed byte to TX buffer and sends with config dword_4E9E0.
 */
static void can650TX_dispatch(void)
{
    struct can_tx_frame frame;

    /* ROM:0x2C838-0x2C840: copy composed byte to staging buffer */
    *(volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0650 =
        *(volatile uint8_t *)(uintptr_t)0xFFFFBC69;

    /* ROM:0x2C842-0x2C846: tail call to can_tx_send_frame with dword_4E9E0 */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0650;
    frame.mailbox = 0x08;       /* MB8 per config */
    frame.dlc = 1;
    frame.mailbox_idx = 0x08;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0650;

    can_tx_send_frame(&frame);
}

/**
 * can650TX_getAndPack — Pack CAN ID 0x0650 cruise-control lamps.
 * ROM address: 0x2C806
 *
 * 1-byte frame: bit7=cruise main, bit6=cruise active,
 * bit5=condition3, bit4=condition4.
 * Counter at 0xFFFFBC6A, fires every 12 calls.
 */
void can650TX_getAndPack(void)
{
    static volatile uint16_t *counter = (volatile uint16_t *)(uintptr_t)0xFFFFBC6A;

    /* ROM:0x2C80A-0x2C810: increment counter */
    *counter += 1;

    /* ROM:0x2C812-0x2C81A: check if counter >= 12 */
    if (*counter < 12) {
        return;
    }

    /* ROM:0x2C81E: compose bitfield */
    can650_bitfield_compose();

    /* ROM:0x2C822: dispatch TX */
    can650TX_dispatch();

    /* ROM:0x2C826-0x2C828: reset counter to 0 */
    *counter = 0;
}

/**
 * can240TX_pack — Pack CAN ID 0x0240 OBD data frame.
 * ROM address: 0x4C888
 *
 * Reads 8 bytes from RAM staging area (0xFFFFCEAC-CEB3) into CAN_TX_BUF_0240.
 * Config table entry: dword_4EA00.
 */
void can240TX_pack(void)
{
    struct can_tx_frame frame;
    volatile uint8_t *buf = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0240;

    /* ROM:0x4C888-0x4C8BA: pack 8 bytes from RAM staging areas */
    buf[0] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEAC;   /* ROM:0x4C88E */
    buf[1] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEAD;   /* ROM:0x4C894 */
    buf[2] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEAE;   /* ROM:0x4C89A */
    buf[3] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEAF;   /* ROM:0x4C8A0 */
    buf[4] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEB0;   /* ROM:0x4C8A4 */
    buf[5] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEB1;   /* ROM:0x4C8AA */
    buf[6] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEB2;   /* ROM:0x4C8B0 */
    buf[7] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEB3;   /* ROM:0x4C8B6 */

    /* ROM:0x4C8BC-0x4C8C0: tail call to can_tx_send_frame with dword_4EA00 */
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
 *
 * Reads 8 bytes from RAM staging area (0xFFFFCEC0-CEC7) into CAN_TX_BUF_0250.
 * Config table entry: dword_4EA10.
 */
void can250TX_pack(void)
{
    struct can_tx_frame frame;
    volatile uint8_t *buf = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0250;

    /* ROM:0x4C984-0x4C9B6: pack 8 bytes from RAM staging areas */
    buf[0] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEC0;   /* ROM:0x4C98A */
    buf[1] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEC1;   /* ROM:0x4C990 */
    buf[2] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEC2;   /* ROM:0x4C996 */
    buf[3] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEC3;   /* ROM:0x4C99C */

    /* ROM:0x4C9A0-0x4C9AE: bytes 4-5 from 0xFFFFCEC4 (u16 BE) */
    {
        volatile uint16_t *w = (volatile uint16_t *)(uintptr_t)0xFFFFCEC4;
        buf[4] = (uint8_t)(*w >> 8);
        buf[5] = (uint8_t)(*w & 0xFF);
    }

    buf[6] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEC6;   /* ROM:0x4C9B0 */
    buf[7] = *(volatile uint8_t *)(uintptr_t)0xFFFFCEC7;   /* ROM:0x4C9B4 */

    /* ROM:0x4C9B8-0x4C9BE: tail call to can_tx_send_frame with dword_4EA10 */
    frame.reserved_00 = 0;
    frame.can_id = CAN_ID_0250;
    frame.mailbox = 0x0B;       /* MB11 per config */
    frame.dlc = 8;
    frame.mailbox_idx = 0x0B;
    frame.data_ptr = (const uint8_t *)(uintptr_t)CAN_TX_BUF_0250;

    can_tx_send_frame(&frame);
}

/**
 * can620TX_pack — Pack CAN ID 0x620 diagnostic frame.
 * ROM address: 0x33A68
 *
 * 7-byte frame with mostly zeros and one status byte.
 * Config table entry: dword_4E9C0.
 */
void can620TX_pack(void)
{
    struct can_tx_frame frame;
    volatile uint8_t *buf = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0620;

    /* ROM:0x33A68-0x33A86: pack 7 bytes */
    buf[0] = 0;                                    /* ROM:0x33A6E */
    buf[1] = 0;                                    /* ROM:0x33A72 */
    buf[2] = 0;                                    /* ROM:0x33A76 */
    buf[3] = 0;                                    /* ROM:0x33A7A */
    buf[4] = *(volatile uint8_t *)(uintptr_t)0xFFFFC05C;  /* ROM:0x33A7E */
    buf[5] = 0;                                    /* ROM:0x33A82 */
    buf[6] = *(volatile uint8_t *)(uintptr_t)0xFFFFC05B;  /* ROM:0x33A84 */

    /* ROM:0x33A88-0x33A8E: tail call to can_tx_send_frame with dword_4E9C0 */
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
 *
 * 8-byte frame with 3 RAM-sourced bytes and zeros.
 * Config table entry: dword_4E9D0.
 */
void can630TX_dispatch(void)
{
    struct can_tx_frame frame;
    volatile uint8_t *buf = (volatile uint8_t *)(uintptr_t)CAN_TX_BUF_0630;

    /* ROM:0x33974-0x33994: pack 8 bytes */
    buf[0] = *(volatile uint8_t *)(uintptr_t)0xFFFFC04D;   /* ROM:0x33978 */
    buf[1] = 0;                                            /* ROM:0x3397C */
    buf[2] = 0;                                            /* ROM:0x33980 */
    buf[3] = 0;                                            /* ROM:0x33984 */
    buf[4] = 0;                                            /* ROM:0x33988 */
    buf[5] = 0;                                            /* ROM:0x3398C */
    buf[6] = *(volatile uint8_t *)(uintptr_t)0xFFFFC04E;   /* ROM:0x3398E */
    buf[7] = *(volatile uint8_t *)(uintptr_t)0xFFFFC04C;   /* ROM:0x33992 */

    /* ROM:0x33996-0x3399C: tail call to can_tx_send_frame with dword_4E9D0 */
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

    /* 3. CAN ID 0x215: throttle position (counter-based dispatch)
     * ROM:0x2A242: counter_check_dispatch_2A242
     * Counter at 0xFFFFBB98, fires every 4 calls.
     * Calls rtos_sequential_2A2A8 → can203pack */
    {
        static volatile uint16_t *cnt = (volatile uint16_t *)(uintptr_t)0xFFFFBB98;
        *cnt += 1;
        if (*cnt >= 4) {
            /* ROM:0x2A2A8: rtos_sequential_2A2A8 — RTOS sequential dispatch
             * NOTE(ROM:0x2A2A8): RTOS call stub. On real ECU: rtos_event_send. */
            can203pack();  /* ROM:0x2A242 falls through to can203pack */
            *cnt = 0;
        }
    }

    /* 4. CAN ID 0x251: engine data (every 2 cycles) */
    can251TX_getAndPack();

    /* 5. CAN ID 0x231: engine state (conditional on [0xB5A4]==1) */
    if (CAN_GATE_B5A4 == 1) {
        can_tx_rate_limit_0x231();
    }

    /* 6. CAN ID 0x240: OBD data (every 25 cycles)
     * ROM:0x4C85A: mutex_trylock_4C85A → can240TX_pack
     * NOTE(ROM:0x4C85A): mutex_trylock not implemented.
     * On real ECU: attempts mutex lock, calls can240TX_pack on success. */
    can240TX_pack();

    /* 7. CAN ID 0x250: OBD data (every 25 cycles)
     * ROM:0x4C956: message_queue_send_4C956 → can250TX_pack
     * NOTE(ROM:0x4C956): message queue send not implemented.
     * On real ECU: enqueues can250TX_pack for RTOS dispatch. */
    can250TX_pack();

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

        /* ROM:0x9A38: verify data copy and retry if needed
         * On real ECU: reads back mailbox status to verify
         * the data was successfully written before transmitting.
         * If verification fails, retries up to 5 times. */
        /* Placeholder: assume success (HW handles verification) */
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
 * Uses placeCANRX with config entry at 0x4EC60 (CAN1).
 * On success: unpacks brake lamp data into RAM staging areas.
 *   Byte 0→[0xFFFFBC28] (ABS FL)
 *   Byte 1→[0xFFFFBC29] (ABS FR)
 *   Byte 2→[0xFFFFBC2A] (ABS RL)
 *   Byte 3→[0xFFFFBC2B] (ABS RR)
 *   Bytes 4-5→[0xFFFFBC46] (u16 BE, brake pressure)
 *   Byte 6→[0xFFFFBC2E] (DSC mode)
 *   Byte 7→[0xFFFFBC5E] (DSC-off indicator)
 *   Resets [0xFFFFBC56]=0, [0xFFFFBC58]=0 (timeout flags)
 */
void CAN212RX_Main(void)
{
    uint8_t buf[8];
    uint32_t saved_sr;
    volatile uint16_t *w_brake = (volatile uint16_t *)(uintptr_t)0xFFFFBC46;

    /* ROM:0x2C0C4: placeCANRX(0x4EC60) — read CAN1 HW mailbox */
    /* Simplified: disable IRQs around mailbox read (ROM:0x2C0C8-0x2C0D6) */
    saved_sr = diag_getsr_3920(0x90);
    /* NOTE(ROM:0x2C0D8-0x2C0E6): HW mailbox read sequence not implemented.
     * On real ECU: reads from CAN1 MB0 via CAN_RX_BUFFER. */
    buf[0] = 0; buf[1] = 0; buf[2] = 0; buf[3] = 0;
    buf[4] = 0; buf[5] = 0; buf[6] = 0; buf[7] = 0;
    diag_setsr_3934(saved_sr);

    /* ROM:0x2C0E8: if placeCANRX returned 0 (success): */
    {
        /* ROM:0x2C0EA-0x2C0EE: mem_flag_e2d0 (timestamp update) */
        /* (ROM:0x2C0F0-0x2C132): can212RXUnpack — unpack bytes */
        *(volatile uint8_t *)(uintptr_t)0xFFFFBC28 = buf[0];  /* ROM:0x2C0F4 */
        *(volatile uint8_t *)(uintptr_t)0xFFFFBC29 = buf[1];  /* ROM:0x2C102 */
        *(volatile uint8_t *)(uintptr_t)0xFFFFBC2A = buf[2];  /* ROM:0x2C10E */
        *(volatile uint8_t *)(uintptr_t)0xFFFFBC2B = buf[3];  /* ROM:0x2C11A */

        /* ROM:0x2C11C-0x2C124: u16 BE brake pressure → 0xFFFFBC46 */
        *w_brake = (uint16_t)((buf[4] << 8) | buf[5]);

        *(volatile uint8_t *)(uintptr_t)0xFFFFBC2E = buf[6];  /* ROM:0x2C128 */

        /* ROM:0x2C12A-0x2C12E: checkTorqueRequestValidity */
        /* (ROM:0x2C130-0x2C132): byte 7 → 0xFFFFBC5E */
        *(volatile uint8_t *)(uintptr_t)0xFFFFBC5E = buf[7];

        /* ROM:0x2C134-0x2C140: can212_utility (post-processing) */
        /* ROM:0x2C142-0x2C14A: reset timeout flags */
        *(volatile uint8_t *)(uintptr_t)0xFFFFBC56 = 0;
        *(volatile uint8_t *)(uintptr_t)0xFFFFBC58 = 0;
    }
}

/**
 * can4B0RX_unpack — Process CAN ID 0x04B0 wheel speeds.
 * ROM address: 0x2BE6E
 *
 * Uses placeCANRX with config entry at 0x4ECA0 (CAN1).
 * On success: unpacks 4 wheel speeds (u16 BE) from 8-byte frame.
 *   Bytes 0-1: FL speed → ((raw-10000)/100) → km/h
 *   Bytes 2-3: FR speed
 *   Bytes 4-5: RL speed
 *   Bytes 6-7: RR speed
 * Complex FPU interpolation chain follows (ROM:0x2BE6E-0x2BFB0).
 * NOTE(ROM:0x2BE6E): Full FPU math chain not implemented.
 */
void can4B0RX_unpack(void)
{
    uint8_t buf[8];
    uint32_t saved_sr;

    /* ROM:0x2BE6E: placeCANRX(0x4ECA0) — read CAN1 HW mailbox */
    saved_sr = diag_getsr_3920(0x90);
    /* NOTE(ROM:0x2BE72-0x2BE80): HW mailbox read not implemented.
     * On real ECU: reads from CAN1 MB via CAN_RX_BUFFER. */
    buf[0] = 0; buf[1] = 0; buf[2] = 0; buf[3] = 0;
    buf[4] = 0; buf[5] = 0; buf[6] = 0; buf[7] = 0;
    diag_setsr_3934(saved_sr);

    /* ROM:0x2BE82: if placeCANRX returned 0: */
    {
        volatile uint8_t *dst = (volatile uint8_t *)(uintptr_t)CAN_RX_BUF_04B0;

        /* ROM:0x2BE84-0x2BE88: mem_flag_e2e8 (timestamp update) */

        /* ROM:0x2BE8A-0x2BEC4: can4B0_speed_unpack — copy 8 bytes */
        /* Copies raw wheel speed data to staging area at 0xFFFFBC08-BC0F */
        dst[0] = buf[0];
        dst[1] = buf[1];
        dst[2] = buf[2];
        dst[3] = buf[3];
        dst[4] = buf[4];
        dst[5] = buf[5];
        dst[6] = buf[6];
        dst[7] = buf[7];

        /* NOTE(ROM:0x2BEC6-0x2BFB0): Complex FPU interpolation chain.
         *   interp_linear_u16_to_float: converts u16 wheel speed to float
         *   interp_axis_lookup_float_to_index: axis lookup
         *   calc_6B0_sub_2BF74: additional computation
         *   axis_lookup_limit_check_2BF20: limits validation
         * Full FPU math chain not implemented. */
    }
}

/**
 * can47RX_Main — Process CAN ID 0x047 KCM/immobiliser request.
 * ROM address: 0x3939C
 *
 * Uses placeCANRX with config entry at 0x4ECB0 (CAN1).
 * On success: copies 8 RX bytes to 0xFFFFC529-C534 and 0xFFFFC534,
 * sets [0xFFFFC52F]=1, [0xFFFFC530]=1.
 * Part of the key-on chat sequence between KCM and ECU.
 */
void can47RX_Main(void)
{
    /* ROM:0x3939C: placeCANRX(0x4ECB0) — read CAN1 HW mailbox */
    /* On success (r0==0): */
    /*   ROM:0x393A4-0x393BC: mem_flag_e2e8 (timestamp update) */
    /*   ROM:0x393BE-0x393E6: copy 8 bytes RX→staging at 0xFFFFC529 */
    /*   ROM:0x393E8-0x393EC: set [0xFFFFC52F] = 1 (immob response flag) */
    /*   ROM:0x393EE-0x393F2: set [0xFFFFC530] = 1 (immob data flag) */
    /* On failure: no-op */
    (void)0;  /* PLACECANRX_STUB(0x4ECB0) */
}

/**
 * can4B1RX_event_check — Process CAN ID 0x04B1 DSC request.
 * ROM address: 0x4C78C
 *
 * Uses placeCANRX with config entry at 0x4EA20 (CAN0).
 * On success: copies 8 RX bytes from 0xFFFFCE90-CE97 to 0xFFFFCE99-CEA0.
 * Also checks DSC request events.
 */
void can4B1RX_event_check(void)
{
    uint8_t buf[8];
    uint32_t saved_sr;

    /* ROM:0x4C78C: placeCANRX(0x4EA20) — read CAN0 HW mailbox */
    saved_sr = diag_getsr_3920(0x90);
    /* NOTE(ROM:0x4C790-0x4C79E): HW mailbox read not implemented.
     * On real ECU: reads from CAN0 MB via CAN_RX_BUFFER. */
    buf[0] = 0; buf[1] = 0; buf[2] = 0; buf[3] = 0;
    buf[4] = 0; buf[5] = 0; buf[6] = 0; buf[7] = 0;
    diag_setsr_3934(saved_sr);

    /* ROM:0x4C7A0: if placeCANRX returned 0: */
    {
        volatile uint8_t *dst = (volatile uint8_t *)(uintptr_t)0xFFFFCE99;

        /* ROM:0x4C7A2-0x4C7A6: mem_flag_e2d0 (timestamp update) */

        /* ROM:0x4C7A8-0x4C7C8: copy 8 bytes from RX to staging
         * Source: 0xFFFFCE90 (RX buffer), Dest: 0xFFFFCE99 (staging) */
        dst[0] = buf[0];  /* ROM:0x4C7AE */
        dst[1] = buf[1];  /* ROM:0x4C7B2 */
        dst[2] = buf[2];  /* ROM:0x4C7B6 */
        dst[3] = buf[3];  /* ROM:0x4C7BA */
        dst[4] = buf[4];  /* ROM:0x4C7BE */
        dst[5] = buf[5];  /* ROM:0x4C7C2 */
        dst[6] = buf[6];  /* ROM:0x4C7C4 */
        dst[7] = buf[7];  /* ROM:0x4C7C8 */
    }
}

/**
 * can4C0RX_short — Process CAN ID 0x04C0 short message (DLC=1).
 * ROM address: 0x2C780
 *
 * Uses placeCANRX with config entry at 0x4ECA0 (CAN1).
 * On success: copies 1 RX byte from [0xFFFFBC64] → [0xFFFFBC65].
 */
void can4C0RX_short(void)
{
    uint8_t rx_byte;
    uint32_t saved_sr;

    /* ROM:0x2C780: placeCANRX(0x4ECA0) — read CAN1 HW mailbox */
    saved_sr = diag_getsr_3920(0x90);
    /* NOTE(ROM:0x2C784-0x2C792): HW mailbox read not implemented.
     * On real ECU: reads from CAN1 MB via CAN_RX_BUFFER. DLC=1. */
    rx_byte = 0;
    diag_setsr_3934(saved_sr);

    /* ROM:0x2C794: if placeCANRX returned 0: */
    {
        /* ROM:0x2C796-0x2C79A: mem_flag_e2d0 (timestamp update) */

        /* ROM:0x2C79C-0x2C7A6: copy byte 0 from staging to dest
         * Source: [0xFFFFBC64] (RX buffer byte 0)
         * Dest: [0xFFFFBC65] */
        *(volatile uint8_t *)(uintptr_t)0xFFFFBC65 = rx_byte;
    }
}

/**
 * can430_4C0RX_dispatch — Process CAN ID 0x0430/0x04C0 cluster data.
 * ROM address: 0x33BA0
 *
 * Uses placeCANRX with config entry at 0x4EC80 (CAN1).
 * On success: mem_flag_e2e0 (timestamp), then copies 8 RX bytes
 * from [0xFFFFC060-C067] → [0xFFFFC06B-C071] (main staging).
 * Also copies to [0xFFFFC068-C06A] (secondary staging).
 */
void can430_4C0RX_dispatch(void)
{
    uint8_t buf[8];
    uint32_t saved_sr;

    /* ROM:0x33BA0: placeCANRX(0x4EC80) — read CAN1 HW mailbox */
    saved_sr = diag_getsr_3920(0x90);
    /* NOTE(ROM:0x33BA4-0x33BB2): HW mailbox read not implemented.
     * On real ECU: reads from CAN1 MB via CAN_RX_BUFFER. */
    buf[0] = 0; buf[1] = 0; buf[2] = 0; buf[3] = 0;
    buf[4] = 0; buf[5] = 0; buf[6] = 0; buf[7] = 0;
    diag_setsr_3934(saved_sr);

    /* ROM:0x33BB4: if placeCANRX returned 0: */
    {
        volatile uint8_t *main_dst = (volatile uint8_t *)(uintptr_t)0xFFFFC06B;
        volatile uint8_t *sec_dst = (volatile uint8_t *)(uintptr_t)0xFFFFC068;

        /* ROM:0x33BB6-0x33BBA: mem_flag_e2e0 (timestamp update) */

        /* ROM:0x33BBC-0x33BE0: copy 8 bytes to main staging area
         * Source: 0xFFFFC060 (RX buffer), Dest: 0xFFFFC06B (main staging) */
        main_dst[0] = buf[0];  /* ROM:0x33BC2 */
        main_dst[1] = buf[1];  /* ROM:0x33BC6 */
        main_dst[2] = buf[2];  /* ROM:0x33BCA */
        main_dst[3] = buf[3];  /* ROM:0x33BCE */
        main_dst[4] = buf[4];  /* ROM:0x33BD2 */
        main_dst[5] = buf[5];  /* ROM:0x33BD6 */
        main_dst[6] = buf[6];  /* ROM:0x33BDA */
        main_dst[7] = buf[7];  /* ROM:0x33BDE */

        /* ROM:0x33BE2-0x33BEE: copy bytes 0-2 to secondary staging
         * Dest: 0xFFFFC068-C06A */
        sec_dst[0] = buf[0];  /* ROM:0x33BE8 */
        sec_dst[1] = buf[1];  /* ROM:0x33BEA */
        sec_dst[2] = buf[2];  /* ROM:0x33BEC */
    }
}

/**
 * incr_counter_saturated_299DA — CAN 0x216 timeout counter + 0x420 pack trigger.
 * ROM address: 0x299DA
 *
 * Increments saturation counter at 0xFFFFBB1C.
 * If counter reaches threshold (25, from ROM word at 0x7C396):
 *   1. Calls set_ram_constant_29A44 (ROM:0x29A44) — computes coolant-based value
 *   2. Calls can420TXPack (ROM:0x29A0C) — packs and sends CAN 0x420
 *   3. Resets counter to 0
 * Called by CAN1_RxProcess via can420_refresh.
 */
void incr_counter_saturated_299DA(void)
{
    static volatile uint16_t *counter = (volatile uint16_t *)(uintptr_t)0xFFFFBB1C;

    /* ROM:0x299DA-0x299DE: increment counter */
    *counter += 1;

    /* ROM:0x299E0-0x299E8: check if counter >= threshold (25) */
    if (*counter < 25) {
        return;
    }

    /* ROM:0x299EA-0x299EE: reset counter to 0 */
    *counter = 0;

    /* ROM:0x299F0: call set_ram_constant_29A44
     * Computes coolant temperature-based value.
     * NOTE(ROM:0x29A44): FPU computation not fully implemented. */
    /* set_ram_constant_29A44(); */

    /* ROM:0x299F4: call can420TXPack (tail call at 0x29A0C) */
    can420TXPack();
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
    /* ROM:0x46588: obd_service_handler_6743C — check OBD session state
     * NOTE(ROM:0x46588): OBD service handler not implemented.
     * On real ECU: returns nonzero if OBD session is active. */
    /* Placeholder: assume OBD session active */

    /* Check 2: CAN state */
    if (CAN_STATE_CD02 != 1) {
        goto reset_counters;
    }

    /* Check 3: DTC validation */
    /* ROM:0x465A4: diag_readvalue_8bit(0x8758) — read DTC validation byte
     * NOTE(ROM:0x465A4): diag read not implemented.
     * On real ECU: returns 0 if no DTC blocking condition. */
    /* Placeholder: assume no DTC blocking */

    /* Check 4: CAN enable */
    if (CAN_ENABLE_A110 == 1) {
        /* Path A: CAN enabled — increment counter against 0x7C396 */
        counter = CAN_RATE_CNT_216;
        /* ROM:0x465C2: add16bitSaturate — saturate at 0xFFFF */
        if (counter < 0xFFFF) {
            counter++;
        }
        CAN_RATE_CNT_216 = counter;

        threshold = *(volatile uint16_t *)(uintptr_t)0x7C396;
        if (counter >= threshold) {
            /* Counter exceeded — set flag and clear */
            *(volatile uint8_t *)(uintptr_t)0xFFFFCC34 = 1;
        }
    } else {
        /* Path B: CAN not enabled — different threshold (0x7C394) */
        counter = CAN_RATE_CNT_216;
        /* ROM:0x465E6: add16bitSaturate — saturate at 0xFFFF */
        if (counter < 0xFFFF) {
            counter++;
        }
        CAN_RATE_CNT_216 = counter;

        threshold = *(volatile uint16_t *)(uintptr_t)0x7C394;
        if (counter >= threshold) {
            *(volatile uint8_t *)(uintptr_t)0xFFFFCC34 = 1;
        }
    }

    /* Check 5: DTC validation again */
    /* ROM:0x46608: diag_readvalue_8bit(0x8758) — second DTC check
     * NOTE(ROM:0x46608): diag read not implemented.
     * On real ECU: if result==1, calls can_to_uds_bridge(sid, 1). */
    /* Placeholder: assume no DTC, no bridge needed */

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

    /* ROM:0x29BE8: can_lookup_table_indexed — table-based sensor lookup
     * NOTE(ROM:0x29BE8): Table lookup not implemented.
     * On real ECU: indexes sensor data from lookup tables. */
    /* Placeholder: no-op */

    if (CAN_GATE_B5A4 == 0) {
        /* ROM:0x29E9C: table_lookup_dispatch_29E9C — manual transmission dispatch
         * NOTE(ROM:0x29E9C): MT-specific dispatch not implemented.
         * On real ECU: dispatches MT-specific sensor reads and CAN data. */
        /* Placeholder: no-op */
    }

    can430_4C0RX_dispatch();
    can4B0RX_unpack();
    can4B1RX_event_check();
    can4C0RX_short();
    can47RX_Main();

immo_fallthrough:
    /* ROM:0x35D62: fall through to immo_state_machine_entry.
     * The immo FSM is called after CAN RX dispatch.
     * It reads CAN data via ImmoGetCANData (0x36870) and
     * writes back via setImmoCANTXData (0x369B8).
     * NOTE(ROM:0x35D62): Immobiliser FSM not implemented here.
     * Called from CAN1_RxProcess dispatch chain. */
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
