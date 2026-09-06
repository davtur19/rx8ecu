/*
 * can.h — RX-8 ECU CAN Bus Subsystem Definitions
 *
 * Two CAN buses: HS-CAN (CAN0, OBD-II pins 6/14) and MS-CAN (CAN1, pins 3/11).
 * CAN0 handles diagnostics (UDS on 0x7E0/0x7E8) and primary TX.
 * CAN1 handles secondary RX (ABS/DSC, wheel speeds, immobiliser).
 *
 * HCAN peripheral base: 0xFFFFE402 (SH-2E).
 * Mailbox registers follow: 0xFFFFE406 (status), 0xFFFFE40A (ready),
 *   0xFFFFE40E (RX status), 0xFFFFE41A (data ready).
 *
 * Config tables in ROM:
 *   0x4EA60 — CAN0 TX mailbox config (16 entries × 16 bytes, primary)
 *   0x4EB60 — CAN0 TX mailbox config (alternate, used when [0xB5A4]==0)
 *   0x4EC60 — CAN1 RX mailbox config (6 entries × 16 bytes)
 *
 * Source: CAN_PROTOCOL.md, ECU.md, IDA disasm
 */

#ifndef CAN_H
#define CAN_H

#include <stdint.h>
#include "platform.h"

/* ====================================================================== */
/*  CAN Mailbox Config Table Entry (16 bytes, big-endian)                  */
/* ====================================================================== */

/* Config table entry layout (from CAN_PROTOCOL.md):
 *   Offset  Size  Endian Description
 *    0       2     BE    Reserved (0x0000)
 *    2       2     BE    CAN ID (11-bit, left-justified in 16-bit field)
 *    4       2     BE    Mailbox slot + direction flag (bit 7 byte4 = RX)
 *    6       1     -     DLC (data length code, 0-8)
 *    7       1     -     Reserved (0x00)
 *    8       2     -     Separator (0xFFFF)
 *   10       2     BE    Buffer pointer low (data area offset)
 *   12       1     -     Buffer pointer high
 *   13       1     -     Reserved (0x00)
 *   14       2     -     Reserved (0x0000)
 */
struct can_mailbox_config {
    uint16_t reserved_00;       /* +0x00: 0x0000 */
    uint16_t can_id;            /* +0x02: CAN ID (11-bit, left-justified) */
    uint16_t slot_dir;          /* +0x04: mailbox slot | (direction << 7) */
    uint8_t  dlc;               /* +0x06: data length code */
    uint8_t  reserved_07;       /* +0x07: 0x00 */
    uint16_t separator;         /* +0x08: 0xFFFF */
    uint16_t buf_ptr_lo;        /* +0x0A: buffer pointer low */
    uint8_t  buf_ptr_hi;        /* +0x0C: buffer pointer high */
    uint8_t  reserved_0D;       /* +0x0D: 0x00 */
    uint16_t reserved_0E;       /* +0x0E: 0x0000 */
};

/* Direction flags */
#define CAN_DIR_TX  0
#define CAN_DIR_RX  1

/* Mailbox slot encoding */
#define CAN_SLOT_MASK    0x00FF
#define CAN_DIR_BIT      0x0100   /* bit 7 of byte 4 (in u16 = bit 8) */

/* ====================================================================== */
/*  CAN Mailbox Config Table Addresses                                     */
/* ====================================================================== */

#define CAN0_TX_CONFIG_PRIMARY   0x4EA60  /* 16 entries × 16 bytes */
#define CAN0_TX_CONFIG_ALTERNATE 0x4EB60  /* 16 entries × 16 bytes */
#define CAN1_RX_CONFIG           0x4EC60  /* 6 entries × 16 bytes */

#define CAN_CONFIG_ENTRY_SIZE    16       /* bytes per entry */
#define CAN0_TX_ENTRY_COUNT      16
#define CAN1_RX_ENTRY_COUNT      6

/* ====================================================================== */
/*  HCAN Peripheral Registers                                             */
/* ====================================================================== */

/* Mailbox register PFC offsets (relative to HCAN periph base 0xFFFFE402) */
#define HCAN_REG_MBOX_OFFSET     0x0004  /* 0xFFFFE406: mailbox offset register */
#define HCAN_REG_MBOX_READY      0x0008  /* 0xFFFFE40A: mailbox ready/control */
#define HCAN_REG_MBOX_STATUS     0x000C  /* 0xFFFFE40E: mailbox status (RX check) */
#define HCAN_REG_MBOX_DATA_READY 0x0018  /* 0xFFFFE41A: data ready / data copy */

/* HCAN enable value */
#define HCAN_ENABLE_MAGIC        0x803E

/* ====================================================================== */
/*  RAM Gate Flags                                                        */
/* ====================================================================== */

#define CAN_GATE_BOOT_COUNTER    (*(volatile uint8_t *)0xFFFFA40F)  /* must be <100 */
#define CAN_GATE_A40A            (*(volatile uint8_t *)0xFFFFA40A)  /* must be 0 */
#define CAN_GATE_INIT_CAN0       (*(volatile uint8_t *)0xFFFFA410)  /* CAN0 init done */
#define CAN_GATE_INIT_CAN1       (*(volatile uint8_t *)0xFFFFA411)  /* CAN1 init done */
#define CAN_GATE_SYS_ENABLE      (*(volatile uint8_t *)0xFFFFAAE0)  /* must be 1 */
#define CAN_GATE_INHIBIT         (*(volatile uint8_t *)0xFFFFB5E8)  /* must be !=1 */
#define CAN_GATE_TX_FLAG         (*(volatile uint8_t *)0xFFFFC241)  /* cleared at end TX */
#define CAN_GATE_B5A4            (*(volatile uint8_t *)0xFFFFB5A4)  /* config select */

/* CAN state flags */
#define CAN_STATE_CD02           (*(volatile uint8_t *)0xFFFFCD02)  /* CAN state ==1 */
#define CAN_ENABLE_A110          (*(volatile uint8_t *)0xFFFFA110)  /* CAN enable ==1 */

/* ====================================================================== */
/*  CAN ID Constants                                                      */
/* ====================================================================== */

/* TX IDs (CAN0) */
#define CAN_ID_0041   0x0041   /* KCM/immobiliser response */
#define CAN_ID_0201   0x0201   /* RPM, vehicle speed, accelerator */
#define CAN_ID_0203   0x0203   /* Engine torque, status */
#define CAN_ID_0215   0x0215   /* Throttle position */
#define CAN_ID_0231   0x0231   /* Engine state / gear selector */
#define CAN_ID_0240   0x0240   /* Transmission / gear data */
#define CAN_ID_0250   0x0250   /* Injection pulse width */
#define CAN_ID_0251   0x0251   /* Engine data (every 2 cycles) */
#define CAN_ID_0420   0x0420   /* Coolant temp, MIL, warning lamps */
#define CAN_ID_0620   0x0620   /* Fan/AC status */
#define CAN_ID_0630   0x0630   /* Cooling fan data */
#define CAN_ID_0650   0x0650   /* Cruise-control lamps */
#define CAN_ID_04B1   0x04B1   /* DSC request */
#define CAN_ID_07E8   0x07E8   /* UDS diagnostic response */

/* RX IDs */
#define CAN_ID_0047   0x0047   /* KCM/immobiliser request (CAN1) */
#define CAN_ID_0212   0x0212   /* ABS/DSC/brake lamps (CAN1) */
#define CAN_ID_0216   0x0216   /* Unknown (CAN1) */
#define CAN_ID_0430   0x0430   /* Instrument cluster presence (CAN1) */
#define CAN_ID_04B0   0x04B0   /* DSC wheel speeds (CAN1) */
#define CAN_ID_04C0   0x04C0   /* Short message (CAN1) */
#define CAN_ID_07DF   0x07DF   /* UDS broadcast request */
#define CAN_ID_07E0   0x07E0   /* UDS physical request */

/* ====================================================================== */
/*  CAN TX Frame Descriptor (passed to can_tx_send_frame)                  */
/* ====================================================================== */

/* The ROM function can_tx_send_frame (0x9AE4) takes a pointer to a
 * descriptor structure in RAM. Layout (from disasm analysis):
 *   +0x00: (2 bytes) reserved/padding
 *   +0x02: (2 bytes) CAN ID (11-bit)
 *   +0x04: (2 bytes) mailbox slot
 *   +0x06: (1 byte)  DLC
 *   +0x07: (1 byte)  mailbox index (byte offset 5 from base r14)
 *   +0x08: (4 bytes) pointer to 8-byte data buffer
 */
struct can_tx_frame {
    uint16_t reserved_00;
    uint16_t can_id;
    uint16_t mailbox;
    uint8_t  dlc;
    uint8_t  mailbox_idx;
    const uint8_t *data_ptr;   /* pointer to 8-byte data buffer */
};

/* ====================================================================== */
/*  RAM Staging Buffers (filled by TX packers, consumed by can_tx_send_frame) */
/* ====================================================================== */

/* RAM data buffers for CAN TX frames (from config table buf_ptr fields) */
#define CAN_TX_BUF_0041    0x01C518
#define CAN_TX_BUF_0201    0x01BB5C
#define CAN_TX_BUF_0203    0x01BB78
#define CAN_TX_BUF_0215    0x01BB9C
#define CAN_TX_BUF_0231    0x01BB48   /* alternate: 0x01BCC4 */
#define CAN_TX_BUF_0420    0x01BB0C
#define CAN_TX_BUF_0620    0x01C054
#define CAN_TX_BUF_0630    0x01C044
#define CAN_TX_BUF_0650    0x01BC68
#define CAN_TX_BUF_0240    0x01CEA4
#define CAN_TX_BUF_0250    0x01CEB8
#define CAN_TX_BUF_04B1    0x01CE90
#define CAN_TX_BUF_07E8    0x0DE0C

/* RAM data buffers for CAN RX frames */
#define CAN_RX_BUF_0212    0x01BC28
#define CAN_RX_BUF_0216    0x01BB20
#define CAN_RX_BUF_0430    0x01C060
#define CAN_RX_BUF_04B0    0x01BC08
#define CAN_RX_BUF_04C0    0x01BC64
#define CAN_RX_BUF_0047    0x01C520

/* ====================================================================== */
/*  Rate Limiter Counters (RAM)                                           */
/* ====================================================================== */

#define CAN_RATE_CNT_201    (*(volatile uint16_t *)0xFFFFBB74)  /* fires every 4 */
#define CAN_RATE_CNT_216    (*(volatile uint16_t *)0xFFFFCC36)  /* timeout counter */

/* ====================================================================== */
/*  CAN Function Prototypes                                               */
/* ====================================================================== */

/**
 * can_tx_send_frame — Low-level CAN frame transmission.
 * ROM address: 0x9AE4
 *
 * Disables interrupts, resolves mailbox via can_get_mailbox_offset_high,
 * writes CAN ID to mailbox, copies data via can_pack_tx_msg_write_verify,
 * sets ready bit, restores interrupts.
 *
 * @param frame  Pointer to can_tx_frame descriptor
 * @return 0 on success, 1 if mailbox busy
 */
int can_tx_send_frame(const struct can_tx_frame *frame);

/**
 * can_setup — Initialize CAN0 and CAN1 controllers.
 * ROM address: 0xDC8C
 *
 * Iterates CAN0/CAN1. Uses primary config 0x4EA60 or alternate 0x4EB60
 * (when [0xB5A4]==0). Calls CANControllerSetup for each controller:
 * enables mailbox interrupts, init IRQ mask, sets mode/DLC, pointer
 * control, ID mode. Sets [0xFFFFA410]=1 when both controllers ready.
 */
void can_setup(void);

/**
 * can_message_setup — Configure a single CAN controller from table.
 * ROM address: 0x2B320
 *
 * @param controller  0=CAN0, 1=CAN1
 * @param table_ptr   Pointer to mailbox config table (16B entries)
 * @return Bitmask of configured mailboxes
 */
uint8_t can_message_setup(uint8_t controller, const void *table_ptr);

/**
 * can_init_mailbox_irq_mask — Init per-mailbox interrupt mask.
 * ROM address: 0xCD12
 * @param controller  0=CAN0, 1=CAN1
 * @param mask        IRQ mask value
 */
void can_init_mailbox_irq_mask(uint8_t controller, uint16_t mask);

/**
 * can_enable_mailbox_int — Enable interrupt for a specific mailbox.
 * ROM address: 0xCC6C
 * @param controller  0=CAN0, 1=CAN1
 * @param mailbox     Mailbox index
 */
void can_enable_mailbox_int(uint8_t controller, uint8_t mailbox);

/**
 * can_set_mailbox_mode_dlc — Set mailbox mode and DLC.
 * ROM address: 0xCDC4
 * @param controller  0=CAN0, 1=CAN1
 * @param mailbox     Mailbox index
 * @param mode_dlc    Mode | DLC
 */
void can_set_mailbox_mode_dlc(uint8_t controller, uint8_t mailbox, uint8_t mode_dlc);

/**
 * can_set_mailbox_ptr_control — Set mailbox buffer pointer and flow control.
 * ROM address: 0xCDF0
 * @param controller  0=CAN0, 1=CAN1
 * @param mailbox     Mailbox index
 * @param ptr_lo      Buffer pointer low
 * @param ptr_hi      Buffer pointer high
 * @param flow_ctrl   Flow control
 */
void can_set_mailbox_ptr_control(uint8_t controller, uint8_t mailbox,
                                  uint16_t ptr_lo, uint8_t ptr_hi,
                                  uint8_t flow_ctrl);

/**
 * can_set_mailbox_id_mode — Set ID acceptance mode for mailbox.
 * ROM address: 0xCE34
 * @param controller  0=CAN0, 1=CAN1
 * @param mailbox     Mailbox index
 * @param id_mode     ID mode configuration
 */
void can_set_mailbox_id_mode(uint8_t controller, uint8_t mailbox, uint16_t id_mode);

/**
 * setCANRegisters — Write config entry to HW registers.
 * ROM address: 0xCC9C
 * @param controller  0=CAN0, 1=CAN1
 * @param config      Pointer to 16-byte config entry
 */
void setCANRegisters(uint8_t controller, const uint8_t *config);

/**
 * CANTX_Main — Main CAN TX dispatcher (periodic).
 * ROM address: 0xDDF0
 *
 * Gate check: [0xA40F]<100, [0xA40A]==0, [0xA410]==0, [0xA411]==0,
 *             [0xAAE0]==1, [0xB5E8]!=1
 * Dispatches all TX packers. Clears flag at [0xC241] when done.
 */
void CANTX_Main(void);

/**
 * secondary_system_controller — CAN RX dispatcher (after CANTX_Main).
 * ROM address: 0xDE8E
 *
 * Gate: [0xAAE0]==1, [0xB5E8]!=1, [0xA410]==0
 * Dispatches RX handlers, then falls to immo_state_machine_entry.
 */
void secondary_system_controller(void);

/**
 * can_msg_parse_4657C — CAN message parser (UDS bridge gatekeeper).
 * ROM address: 0x4657C
 *
 * Checks pre-conditions:
 *   - OBD session active (obd_service_handler_6743C)
 *   - CAN state [0xFFFFCD02] == 1
 *   - CAN enable [0xFFFFA110] == 1
 *   - Counter at [0xFFFFCC36] vs ROM threshold 0x7C396
 * If conditions met, bridges to can_to_uds_bridge.
 *
 * @param sid  Service ID (0x67 for UDS)
 * @param req  Request type (1 or 2)
 */
void can_msg_parse_4657C(uint8_t sid, uint8_t req);

/**
 * can_to_uds_bridge — Bridge CAN UDS request to udsHandler.
 * ROM address: 0x60774
 *
 * Receives CAN diagnostic request, forwards to uds_task_entry (0x696DC)
 * which calls udsHandler (0x697E8).
 *
 * @param sid   Service ID byte
 * @param req   Request type (1=physical, 2=broadcast)
 */
void can_to_uds_bridge(uint8_t sid, uint8_t req);

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
int placeCANRX(const uint8_t *config);

/**
 * can41TXPack — Pack CAN ID 0x041 KCM/immobiliser response frame.
 * ROM address: 0x39348
 * Packs per-cycle idle frame data into CAN_TX_BUF_0041.
 */
void can41TXPack(void);

/**
 * can_tx_rate_limit_0x201 — Rate-limited TX for CAN 0x201+0x203.
 * ROM address: 0x29FD2
 * Counter at 0xFFFFBB74, fires every 4 calls.
 * Calls can201_pack_interpolation + can201_pack_staging for 0x201,
 * then falls to can203pack.
 */
void can_tx_rate_limit_0x201(void);

/**
 * can203pack — Pack CAN ID 0x0203 engine torque/status frame.
 * ROM address: 0x2A274
 */
void can203pack(void);

/**
 * can251TX_getAndPack — Pack CAN ID 0x0251 engine data (every 2 cycles).
 * ROM address: 0x2AAB6
 */
void can251TX_getAndPack(void);

/**
 * can_tx_rate_limit_0x231 — Rate-limited TX for CAN 0x231.
 * ROM address: (calls 0x2D402 -> canPackandTx231 at 0x2D434)
 * Conditional on [0xB5A4]==1.
 */
void can_tx_rate_limit_0x231(void);

/**
 * can420TXPack — Pack CAN ID 0x0420 coolant/MIL frame.
 * ROM address: 0x29A0C
 */
void can420TXPack(void);

/**
 * can650TX_getAndPack — Pack CAN ID 0x0650 cruise-control lamps.
 * ROM address: 0x2C806
 */
void can650TX_getAndPack(void);

/**
 * can240TX_pack — Pack CAN ID 0x0240 OBD data frame.
 * ROM address: 0x4C888
 */
void can240TX_pack(void);

/**
 * can250TX_pack — Pack CAN ID 0x0250 OBD data frame.
 * ROM address: 0x4C984
 */
void can250TX_pack(void);

/**
 * can620TX_pack — Pack CAN ID 0x0620 fan/AC frame.
 * ROM address: 0x33A68
 */
void can620TX_pack(void);

/**
 * can630TX_dispatch — Pack CAN ID 0x0630 cooling fan frame.
 * ROM address: 0x33974
 */
void can630TX_dispatch(void);

/**
 * CAN212RX_Main — Process CAN ID 0x212 ABS/DSC/brake lamps.
 * ROM address: 0x2C0C4
 * Unpacks to CAN_RX_BUF_0212.
 */
void CAN212RX_Main(void);

/**
 * can4B0RX_unpack — Process CAN ID 0x04B0 wheel speeds.
 * ROM address: 0x2BE6E
 * Unpacks DSC wheel speeds (4× u16 BE) to CAN_RX_BUF_04B0.
 */
void can4B0RX_unpack(void);

/**
 * can47RX_Main — Process CAN ID 0x047 KCM/immobiliser request.
 * ROM address: 0x3939C
 * Reads immobiliser data from CAN1.
 */
void can47RX_Main(void);

/**
 * can4B1RX_event_check — Process CAN ID 0x04B1 DSC request.
 * ROM address: 0x4C78C
 */
void can4B1RX_event_check(void);

/**
 * can4C0RX_short — Process CAN ID 0x04C0 short message (DLC=1).
 * ROM address: 0x2C780
 */
void can4C0RX_short(void);

/**
 * can430_4C0RX_dispatch — Process CAN ID 0x0430/0x04C0 cluster data.
 * ROM address: 0x33BA0
 */
void can430_4C0RX_dispatch(void);

/**
 * incr_counter_saturated_299DA — CAN 0x216 timeout counter.
 * ROM address: 0x299DA
 * Increments saturation counter for CAN 0x216 timeout detection.
 */
void incr_counter_saturated_299DA(void);

/* ====================================================================== */
/*  Low-Level CAN Helpers (ROM functions, called from firmware)            */
/* ====================================================================== */

/**
 * getHCANRegAddr — Calculate HCAN register address.
 * ROM address: 0xD198
 * @param base    PFC base address (0xFFFFE402 for CAN0, 0xFFFFE600 for CAN1)
 * @param offset  Register offset
 * @return Register address
 */
uint16_t getHCANRegAddr(uint16_t base, uint16_t offset);

/**
 * can_get_mailbox_offset_high — Read mailbox status/offset.
 * ROM address: 0xD164
 * @param mailbox_idx  Mailbox index (byte)
 * @param pfc_reg      PFC register address
 * @return Pointer to mailbox register
 */
volatile uint16_t *can_get_mailbox_offset_high(uint8_t mailbox_idx, uint16_t pfc_reg);

/**
 * can_get_mailbox_config — Get mailbox config word.
 * ROM address: 0xD1AC
 * @param mailbox_idx  Mailbox index
 * @return Config word
 */
uint16_t can_get_mailbox_config(uint8_t mailbox_idx);

/**
 * can_pack_tx_msg_write_verify — Write CAN data to mailbox with verify.
 * ROM address: 0xCF42
 * @param mailbox_idx  Mailbox index
 * @param dlc          Data length code
 * @param data_ptr     Pointer to data buffer
 * @param zero         Zero parameter
 * @return 0 on success
 */
int can_pack_tx_msg_write_verify(uint8_t mailbox_idx, uint8_t dlc,
                                  const uint8_t *data_ptr, uint8_t zero);

/**
 * can_pack_tx_msg_copy — Copy CAN data from mailbox to buffer.
 * ROM address: 0xCEF4
 * @param mailbox_idx  Mailbox index
 * @param dlc          Data length code
 * @param data_ptr     Pointer to destination buffer
 * @param zero         Zero parameter
 * @return 0 on success
 */
int can_pack_tx_msg_copy(uint8_t mailbox_idx, uint8_t dlc,
                          uint8_t *data_ptr, uint8_t zero);

/**
 * diag_getsr_3920 — Disable interrupts, save SR.
 * ROM address: 0x3920
 * @param level  Interrupt level to set (0x90)
 * @return Saved SR value
 */
uint32_t diag_getsr_3920(uint8_t level);

/**
 * diag_setsr_3934 — Restore SR (re-enable interrupts).
 * ROM address: 0x3934
 * @param saved_sr  SR value from diag_getsr_3920
 */
void diag_setsr_3934(uint32_t saved_sr);

#endif /* CAN_H */
