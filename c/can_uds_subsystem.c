/* ================================================================
 * CAN / UDS Subsystem — RX-8 ECU (60E1D400)
 * Reconstructed C from SH-2E disassembly
 * ================================================================
 *
 * These are structurally accurate reconstructions of key functions
 * in the CAN/UDS subsystem. The actual SH-2E assembly was the
 * primary reference; this C is a human-readable interpretation.
 *
 * Architecture: Renesas SH7055 (SH-2E), big-endian
 * Compiler: Renesas SHC (targeting SH-2E)
 * ================================================================
 */

#include <stdint.h>
#include <stdbool.h>

/* -----------------------------------------------------------------
 * Memory-mapped I/O / RAM addresses (from disassembly)
 * ----------------------------------------------------------------- */

/* HCAN (Hitachi CAN) controller base address */
#define HCAN_BASE           0xFFFFC000UL

/* CAN TX control flags */
#define CAN_TX_COUNTER      (*(volatile uint8_t  *)0xFFFFA40FUL)
#define CAN_TX_INHIBIT_1    (*(volatile uint8_t  *)0xFFFFA410UL)
#define CAN_TX_INHIBIT_2    (*(volatile uint8_t  *)0xFFFFA411UL)
#define CAN_TX_GATE         (*(volatile uint8_t  *)0xFFFFA40AUL)
#define CAN_TX_ENABLE       (*(volatile uint8_t  *)0xFFFFAAE0UL)
#define CAN_TX_INHIBIT_3    (*(volatile uint8_t  *)0xFFFFB5E8UL)
#define CAN_TX_CYCLE_DONE   (*(volatile uint8_t  *)0xFFFFC241UL)
#define CAN_TX_PERIODIC     (*(volatile uint8_t  *)0xFFFFB5A4UL)

/* CAN timer/counter values */
#define CAN_TIMER_1         (*(volatile uint16_t *)0xFFFFCD2AUL)
#define CAN_TIMER_2         (*(volatile uint16_t *)0xFFFFCD28UL)

/* CAN filter result flags */
#define CAN_FILTER_FLAG_A   (*(volatile uint8_t  *)0xFFFFCCFBUL)
#define CAN_FILTER_FLAG_B   (*(volatile uint8_t  *)0xFFFFCCFCUL)
#define CAN_DIAG_STATUS_1   (*(volatile uint8_t  *)0xFFFFCCFDUL)
#define CAN_DIAG_STATUS_2   (*(volatile uint8_t  *)0xFFFFCCFEUL)
#define CAN_DIAG_STATUS_3   (*(volatile uint8_t  *)0xFFFFCCFFUL)
#define CAN_RX_VALID        (*(volatile uint8_t  *)0xFFFFCCFAUL)

/* Diagnostic session / security */
#define DIAG_SESSION        (*(volatile uint8_t  *)0xFFFFDE5CUL)
#define SECURITY_UNLOCKED   (*(volatile uint8_t  *)0xFFFFD0F2UL)
#define SECURITY_FLAGS      (*(volatile uint8_t  *)0xFFFFD0F3UL)

/* Launch control status bit (tuned) */
#define LAUNCH_CTRL_STATUS  (*(volatile uint16_t *)0xFFFFF754UL)

/* CAN message descriptor / buffer structure (from can_data_decode_2468C) */
#define CAN_DECODE_DESC     (*(volatile uint16_t *)0xFFFFB4E8UL)
/* Decoded message words (written by can_data_decode_2468C) */
#define CAN_DECODE_WORD_0   (*(volatile uint16_t *)0xFFFFB53CUL)
#define CAN_DECODE_WORD_1   (*(volatile uint16_t *)0xFFFFB53EUL)
#define CAN_DECODE_WORD_2   (*(volatile uint16_t *)0xFFFFB540UL)
#define CAN_DECODE_WORD_3   (*(volatile uint16_t *)0xFFFFB542UL)
#define CAN_DECODE_WORD_4   (*(volatile uint16_t *)0xFFFFB544UL)

/* CAN RX data source bytes (bitfield inputs) */
/* These could be CAN message buffer, digital inputs, or ADC results */
#define CAN_RX_SRC_BYTE_0   (*(volatile uint8_t  *)0xFFFFB596UL)
#define CAN_RX_SRC_BYTE_1   (*(volatile uint8_t  *)0xFFFFB597UL)
#define CAN_RX_SRC_BYTE_2   (*(volatile uint8_t  *)0xFFFFB598UL)
#define CAN_RX_SRC_BYTE_3   (*(volatile uint8_t  *)0xFFFFB599UL)
#define CAN_RX_SRC_BYTE_4   (*(volatile uint8_t  *)0xFFFFB59AUL)
#define CAN_RX_SRC_BYTE_5   (*(volatile uint8_t  *)0xFFFFB59BUL)
#define CAN_RX_SRC_BYTE_6   (*(volatile uint8_t  *)0xFFFFB59CUL)

/* CAN RX bitfield flags (written by can_data_decode_2468C) */
#define CAN_FLAG_BASE       (*(volatile uint8_t  *)0xFFFFB55CUL)
/* Flags cover 0xB55C-0xB58B (47 bytes, indexed by group*8 + bit) */

/* -----------------------------------------------------------------
 * CAN Message Buffer
 * ----------------------------------------------------------------- */
#define CAN_MAX_DATA    8

typedef struct {
    uint16_t id;         /* CAN ID (11-bit standard) */
    uint8_t  dlc;        /* Data Length Code (0-8) */
    uint8_t  data[CAN_MAX_DATA];
} can_message_t;

/* HCAN mailbox registers (16 mailboxes, indexed) */
typedef volatile struct {
    uint32_t id_reg;     /* M_BIDR */
    uint32_t data_reg;   /* M_BDSR (actually 2 x 32-bit for 8 bytes) */
    uint16_t ctrl_reg;   /* M_BCTLR */
    uint8_t  mode_reg;   /* M_BOCR */
} hcan_mailbox_t;

#define HCAN_MAILBOX(n)  ((hcan_mailbox_t *)(HCAN_BASE + 0x100 + (n) * 0x20))

/* TX mailbox for each CAN ID (from disassembly analysis) */
#define TX_MBOX_041     8   /* AC / alternator status */
#define TX_MBOX_201     9   /* Wheel speed */
#define TX_MBOX_203     10  /* Engine torque/status */
#define TX_MBOX_251     11  /* Throttle position */
#define TX_MBOX_240     12  /* Transmission / gear */
#define TX_MBOX_250     13  /* Injection pulse width */
#define TX_MBOX_620     14  /* Fan / AC */
#define TX_MBOX_650     15  /* Catalyst / O2 */

/* -----------------------------------------------------------------
 * Sensor value sources (RAM locations from disassembly)
 * ----------------------------------------------------------------- */
#define RPM_FLOAT       (*(volatile float *)0xFFFFB5B8UL)
#define LOAD_FLOAT      (*(volatile float *)0xFFFFB5BCUL)
#define COOLANT_TEMP    (*(volatile float *)0xFFFFB5C0UL)
#define IAT_FLOAT       (*(volatile float *)0xFFFFB5C4UL)
#define THROTTLE_POS    (*(volatile float *)0xFFFFB5D0UL)
#define BARO_FLOAT      (*(volatile float *)0xFFFFB5D4UL)
#define BATTERY_VOLTAGE (*(volatile float *)0xFFFFB5E0UL)

/* -----------------------------------------------------------------
 * UDS Protocol Constants
 * ----------------------------------------------------------------- */
#define UDS_SID_REQ_OFFSET      0x40    /* Positive response = SID + 0x40 */
#define UDS_NEGATIVE_RESPONSE   0x7F    /* Negative response SID */

/* UDS Service IDs */
#define SID_DIAG_SESSION_CTRL   0x10
#define SID_ECU_RESET           0x11
#define SID_READ_DATA_BY_ID     0x22
#define SID_READ_MEM_BY_ADDR    0x23
#define SID_SECURITY_ACCESS     0x27
#define SID_COMM_CTRL           0x28
#define SID_IO_CTRL_BY_ID       0x2F
#define SID_ROUTINE_CTRL        0x31
#define SID_REQUEST_DOWNLOAD    0x34
#define SID_TRANSFER_DATA       0x36
#define SID_REQ_TRANSFER_EXIT   0x37
#define SID_CTRL_DTC_SETTING    0x85
#define SID_CUSTOM_B1           0xB1

/* UDS Negative Response Codes */
#define NRC_GENERAL_REJECT              0x10
#define NRC_SERVICE_NOT_SUPPORTED       0x11
#define NRC_SUBFUNC_NOT_SUPPORTED       0x12
#define NRC_INVALID_FORMAT              0x13
#define NRC_CONDITIONS_NOT_CORRECT      0x22
#define NRC_REQUEST_SEQUENCE_ERROR      0x24
#define NRC_REQUEST_OUT_OF_RANGE        0x31
#define NRC_SECURITY_ACCESS_DENIED      0x33
#define NRC_INVALID_KEY                 0x35
#define NRC_EXCEED_NUM_ATTEMPTS         0x36
#define NRC_REQUIRED_TIME_DELAY         0x37
#define NRC_RESPONSE_PENDING            0x78

/* -----------------------------------------------------------------
 * Function prototypes for TX pack functions
 * ----------------------------------------------------------------- */
static void can_pack_041(void);   /* can41TXPack @ 0x39348 */
static void can_pack_201(void);   /* can201TX_getAndPack @ 0x29B52 */
static void can_pack_203(void);   /* can203TX_getAndPack @ 0x29DC2 */
static void can_pack_251(void);   /* can251TX_getAndPack @ 0x2AAB6 */
static void can_pack_periodic(void); /* can_tx_periodic_dispatch @ 0x2D402 */
static void can_pack_240(void);   /* can240TX_pack @ 0x4C888 */
static void can_pack_250(void);   /* can250TX_pack @ 0x4C984 */
static void can_rx_timeout_check(void); /* CANRX216TimeoutCount @ 0x299DA */
static void can_pack_620(void);   /* can620TX_getAndPack @ 0x33A36 */
static void can_msg_setup(void);  /* can_message_setup_dispatcher @ 0x33942 */
static void can_pack_650(void);   /* can650TX_getAndPack @ 0x2C806 */

/* -----------------------------------------------------------------
 * Forward declarations: CAN RX dispatchers + runtime helpers
 * (defined later in this file; declared here so C99 parsers accept
 *  their use inside CANRX_Main / CANHandler before the definitions)
 * ----------------------------------------------------------------- */
uint16_t can_get_rx_pending_flags(void); /* stubbed @ 0x... (runtime helper) */
void CAN216RX_Main(void);   /* CAN ID 0x216 RX handler */
void CAN231TX_Main(void);   /* CAN ID 0x231 TX handler */
void CAN4B0RX_Main(void);   /* CAN ID 0x4B0 (DSC/ESP) RX handler */
void CAN212RX_Main(void);   /* CAN ID 0x212 RX handler */
void CAN4C0RX_Main(void);   /* CAN ID 0x4C0 RX handler */
void CAN430RX_Main(void);   /* CAN ID 0x430 (immobilizer) RX handler */
void ImmoMain(void);        /* immobilizer main */
void CAN47RX_Main(void);    /* CAN ID 0x47 (steering angle) RX handler */
void CAN4B1RX_Main(void);   /* CAN ID 0x4B1 (DSC secondary) RX handler */
uint32_t getSR(void);       /* SH-2E status register read */
void setSR(uint32_t sr);    /* SH-2E status register write */

/* -----------------------------------------------------------------
 * HCAN low-level hardware access
 * ----------------------------------------------------------------- */

/**
 * Get HCAN register base address for a given register index.
 * Maps logical register numbers to physical HCAN addresses.
 * (getHCANRegisterAddress @ 0xD198)
 */
static uint32_t get_hcan_reg_addr(uint8_t reg_idx)
{
    /* From disassembly: calculates address = HCAN_BASE + offset */
    return HCAN_BASE + (uint32_t)reg_idx * 4UL;
}

/**
 * Write a value to an HCAN register
 * (can_register_read_write @ 0x9DD8)
 */
static void hcan_reg_write(uint32_t addr, uint32_t val)
{
    *(volatile uint32_t *)addr = val;
}

/**
 * Read from an HCAN register
 */
static uint32_t hcan_reg_read(uint32_t addr)
{
    return *(volatile uint32_t *)addr;
}

/**
 * Write to a CAN mailbox data buffer
 * (can_pack_tx_msg_write_verify @ 0xCF42)
 */
static void can_mailbox_write(uint8_t mailbox, const uint8_t *data, uint8_t len)
{
    uint32_t *data_reg = (uint32_t *)&HCAN_MAILBOX(mailbox)->data_reg;
    uint32_t  packed;

    /* Pack bytes into two 32-bit words (big-endian) */
    if (len > 0) {
        packed = ((uint32_t)data[0] << 24)
               | ((uint32_t)data[1] << 16)
               | ((uint32_t)data[2] << 8)
               | ((uint32_t)data[3]);
        data_reg[0] = packed;
    }
    if (len > 4) {
        packed = ((uint32_t)data[4] << 24)
               | ((uint32_t)data[5] << 16)
               | ((uint32_t)data[6] << 8)
               | ((uint32_t)data[7]);
        data_reg[1] = packed;
    }
}

/**
 * Read from a CAN mailbox data buffer
 * (can_mailbox_read_data @ 0xCFD4)
 */
static void can_mailbox_read(uint8_t mailbox, uint8_t *data, uint8_t len)
{
    const uint32_t *data_reg = (const uint32_t *)&HCAN_MAILBOX(mailbox)->data_reg;
    uint32_t packed;
    int i;

    if (len > 4) {
        packed = data_reg[0];
        for (i = 0; i < 4 && i < len; i++)
            data[i] = (packed >> (24 - i * 8)) & 0xFF;

        packed = data_reg[1];
        for (i = 4; i < 8 && i < len; i++)
            data[i] = (packed >> (24 - (i - 4) * 8)) & 0xFF;
    } else {
        packed = data_reg[0];
        for (i = 0; i < len; i++)
            data[i] = (packed >> (24 - i * 8)) & 0xFF;
    }
}

/* -----------------------------------------------------------------
 * CANTX_Main — Master CAN TX Dispatcher
 * (0xDDF0, 158 bytes, 79 instructions)
 *
 * Called periodically from the main loop to pack and transmit
 * all CAN broadcast messages. Sequential call chain.
 * ----------------------------------------------------------------- */
void CANTX_Main(void)
{
    uint8_t ctr;

    /* Gate check: counter must not exceed 100 */
    ctr = CAN_TX_COUNTER;
    if (ctr >= 100)
        goto done;

    /* Gate check: various inhibit flags must be clear */
    if (CAN_TX_GATE)
        goto done;
    if (CAN_TX_INHIBIT_1)
        goto done;
    if (CAN_TX_INHIBIT_2)
        goto done;

    /* Gate check: CAN TX must be enabled (0xAAE0 == 1) */
    if (CAN_TX_ENABLE != 1)
        goto done;

    /* Gate check: inhibit flag 3 must NOT be 1 */
    if (CAN_TX_INHIBIT_3 == 1)
        goto done;

    /* ---- Sequential TX Pack Chain ---- */

    /* CAN ID 0x041: AC / alternator status */
    can_pack_041();

    /* CAN ID 0x201: Wheel speed (ABS/ESP) */
    can_pack_201();

    /* CAN ID 0x203: Engine torque/status (ABS/ESP) */
    can_pack_203();

    /* CAN ID 0x251: Throttle position */
    can_pack_251();

    /* CAN ID periodic dispatch (only if periodic mode flag is set) */
    if (CAN_TX_PERIODIC == 1)
        can_pack_periodic();

    /* CAN ID 0x240: Transmission / gear */
    can_pack_240();

    /* CAN ID 0x250: Injection pulse width / fuel */
    can_pack_250();

    /* RX timeout check (acknowledge timeout for CAN 0x216) */
    can_rx_timeout_check();

    /* CAN ID 0x620: Fan status / AC */
    can_pack_620();

    /* CAN message setup (periodic interrupt timer) */
    can_msg_setup();

    /* CAN ID 0x650: Catalyst / O2 sensor */
    can_pack_650();

done:
    /* Signal TX cycle complete by clearing flag at 0xC241 */
    CAN_TX_CYCLE_DONE = 0;
}

/* -----------------------------------------------------------------
 * CAN_EmitLaunchStatus — tuned Launch Control CAN Output
 * (0x57BE8, known from tuned-variant analysis)
 *
 * Reads launch control status bit 0x0400 from RAM, emits via CAN.
 * ----------------------------------------------------------------- */
void CAN_EmitLaunchStatus(uint8_t launch_active)
{
    uint16_t status;

    status = LAUNCH_CTRL_STATUS;

    /* Extract bit 0x0400 */
    if (status & 0x0400)
        launch_active = 1;
    else
        launch_active = 0;

    /* Transmit via CAN (uses memory_match_accumulate_583E4 → CAN_WriteChannel) */
    /* ... (implementation depends on CAN dispatch mechanism) */
}

/* -----------------------------------------------------------------
 * UDS Dispatch Entry Structure
 *
 * From udsHandler disassembly (0x697E8): 12 bytes per entry.
 * Entry index * 12 = multiply by (n*12) using shll+add+shll2 pattern.
 * ----------------------------------------------------------------- */
typedef struct {
    uint8_t  sid;           /* Service ID to match */
    uint8_t  pad[3];        /* All zeros */
    void     (*handler)(const uint8_t *request, uint8_t len);
                            /* Service handler function pointer */
    uint8_t  access_flags;  /* Required session type bitmask */
    uint8_t  pad2[3];       /* All zeros */
} uds_dispatch_entry_t;

/**
 * udsHandler — Central UDS Service Dispatcher
 * (0x697E8, 146 bytes, 73 instructions)
 *
 * Parameters:
 *   r4 = SID (Service ID) byte from request
 *   r5 = pointer to request data buffer
 *   r6 = length of request data
 *
 * Returns: 0 if handled, 1 if denied, 2 if not found
 *
 * Dispatch table format (12 bytes/entry):
 *   [0]: SID byte
 *   [4]: handler function pointer (32-bit)
 *   [8]: access flags byte
 * ----------------------------------------------------------------- */
int udsHandler(uint8_t sid, const uint8_t *data, uint8_t len)
{
    const uds_dispatch_entry_t *table;
    uint8_t current_session;
    int result;

    /* Get current diagnostic session type */
    current_session = DIAG_SESSION;

    /* Table base is loaded from PC-relative data.
     * (In the actual ROM, this is a pointer to a table at ~0x69xxx) */
    table = (const uds_dispatch_entry_t *)0;  /* ROM-specific */

    /* Iterate through dispatch table */
    for (int i = 0; ; i++) {
        const uds_dispatch_entry_t *entry = &table[i];
        uint8_t entry_sid = entry->sid;

        /* Check for end-of-table marker (0xFF or non-printable) */
        if (entry_sid == 0xFF)
            break;

        /* Compare SID */
        if (entry->sid == sid) {
            /* Check access flags against current session */
            if (entry->access_flags & current_session) {
                /* Access granted → call handler */
                entry->handler(data, len);
                return 0;   /* Handled OK */
            } else {
                /* Service requires higher access level */
                result = 1; /* SecurityAccessDenied */
                return result;
            }
        }
    }

    return 2; /* ServiceNotSupported */
}

/* -----------------------------------------------------------------
 * udsErrorResponse — Send UDS Negative Response
 * (0x553AA, 38 bytes, 19 instructions)
 *
 * Packs: 0x7F + SID + NRC into a 3-byte response frame
 * ----------------------------------------------------------------- */
void udsErrorResponse(uint8_t sid, uint8_t nrc)
{
    uint8_t response[3];

    response[0] = UDS_NEGATIVE_RESPONSE;   /* 0x7F */
    response[1] = sid;
    response[2] = nrc;

    /* Send via UDS transport layer (setupForUdsResponse @ 0x66A14) */
    /* uart_can_send(response, 3); */
}

/* -----------------------------------------------------------------
 * UDSPositiveResponse_16bit — Send positive response with 16-bit value
 * (0x58294, 44 bytes, 22 instructions)
 *
 * Reads a 16-bit value from RAM, formats as UDS response.
 * ----------------------------------------------------------------- */
void UDSPositiveResponse_16bit(uint8_t sid, uint16_t value)
{
    uint8_t response[3];

    response[0] = sid + UDS_SID_REQ_OFFSET;  /* SID + 0x40 */
    response[1] = (value >> 8) & 0xFF;        /* High byte */
    response[2] = value & 0xFF;               /* Low byte */

    /* Send via UDS transport layer */
    /* setupForUdsResponse(response, 3); */
}

/* -----------------------------------------------------------------
 * intToUDS_SERVICE_DATA / byteToUDS_SERVICE_DATA
 * Data format helpers
 * (0x58448, 34 bytes / 0x5846A, 28 bytes)
 * ----------------------------------------------------------------- */

/**
 * Convert a 16-bit value to 2-byte UDS data format.
 * High byte = (value >> 8), Low byte = value & 0xFF
 */
void intToUDS_SERVICE_DATA(uint16_t value, uint8_t *out)
{
    out[0] = (value >> 8) & 0xFF;
    out[1] = value & 0xFF;
}

/**
 * Pack a single byte into UDS data format.
 * out[0] = value
 */
void byteToUDS_SERVICE_DATA(uint8_t value, uint8_t *out)
{
    out[0] = value;
}

/* -----------------------------------------------------------------
 * CAN Message Pack Functions — Stub Implementations
 *
 * These are representative of the sensor-to-CAN-byte conversion.
 * Each is called by CANTX_Main in sequence.
 * ----------------------------------------------------------------- */

/**
 * CAN ID 0x041 — AC Request / Alternator Status
 */
static void can_pack_041(void)
{
    uint8_t msg[8] = {0};

    /* Placeholder: pack AC compressor request and alternator status */
    /* msg[0] = ac_request; */
    /* msg[1] = alternator_status; */

    can_mailbox_write(TX_MBOX_041, msg, 8);
}

/**
 * CAN ID 0x201 — Wheel Speed (ABS/TCS/ESP)
 * Packed from individual wheel speed sensors
 */
static void can_pack_201(void)
{
    uint8_t msg[8] = {0};

    /* Wheel speeds are scaled u16 values (km/h * 100 typical) */
    /* msg[0..1] = front_left_wheel_speed; */
    /* msg[2..3] = front_right_wheel_speed; */
    /* msg[4..5] = rear_left_wheel_speed; */
    /* msg[6..7] = rear_right_wheel_speed; */

    can_mailbox_write(TX_MBOX_201, msg, 8);
}

/**
 * CAN ID 0x203 — Engine Torque / Status (for ABS/ESP)
 * Includes actual torque, driver demand torque, engine status flags
 */
static void can_pack_203(void)
{
    uint8_t msg[8] = {0};

    /* msg[0..1] = actual_engine_torque (Nm, scaled); */
    /* msg[2..3] = driver_demand_torque; */
    /* msg[4] = engine_status_flags; */
    /* msg[5..7] = misc; */

    can_mailbox_write(TX_MBOX_203, msg, 8);
}

/**
 * CAN ID 0x251 — Throttle Position
 * Actual throttle plate angle and pedal position
 */
static void can_pack_251(void)
{
    uint8_t msg[8] = {0};

    /* msg[0..1] = throttle_angle (0-100%, scaled); */
    /* msg[2..3] = pedal_position; */
    /* msg[4..7] = reserved; */

    can_mailbox_write(TX_MBOX_251, msg, 8);
}

/**
 * CAN ID 0x240 — Transmission / Gear Data
 */
static void can_pack_240(void)
{
    uint8_t msg[8] = {0};

    /* msg[0] = current_gear; */
    /* msg[1] = torque_converter_status; */
    /* msg[2..7] = misc; */

    can_mailbox_write(TX_MBOX_240, msg, 8);
}

/**
 * CAN ID 0x250 — Injection Pulse Width (Rotarytronics target)
 * Fuel injection parameters
 */
static void can_pack_250(void)
{
    uint8_t msg[8] = {0};

    /* msg[0..1] = injection_pulse_width_us (u16); */
    /* msg[2..3] = fuel_correction (u16); */
    /* msg[4..5] = lambda_value (scaled u16); */
    /* msg[6..7] = fuel_pressure (scaled u16); */

    can_mailbox_write(TX_MBOX_250, msg, 8);
}

static void can_rx_timeout_check(void)
{
    /* Check if expected CAN RX messages have timed out */
    /* Increment timeout counters, set fault flags */
}

/**
 * CAN ID 0x620 — Fan / AC Status
 */
static void can_pack_620(void)
{
    uint8_t msg[8] = {0};

    /* msg[0] = fan_speed; */
    /* msg[1] = ac_compressor_status; */
    /* msg[2..7] = misc; */

    can_mailbox_write(TX_MBOX_620, msg, 8);
}

static void can_msg_setup(void)
{
    /* Setup next periodic message timer interrupt */
}

/**
 * CAN ID 0x650 — Catalyst / O2 Sensor Data
 */
static void can_pack_650(void)
{
    uint8_t msg[8] = {0};

    /* msg[0..1] = o2_sensor_voltage (scaled); */
    /* msg[2..3] = catalyst_temperature; */
    /* msg[4..7] = misc; */

    can_mailbox_write(TX_MBOX_650, msg, 8);
}

/* -----------------------------------------------------------------
 * CANRX_Main — CAN RX Dispatcher
 * (0xDBF6, referenced by CANHandler)
 *
 * Reads received CAN messages and dispatches to per-ID handlers.
 * ----------------------------------------------------------------- */
void CANRX_Main(void)
{
    uint16_t pending;

    /* Read RX pending flags (MPR — Mailbox Pending Register) */
    pending = can_get_rx_pending_flags();

    /* Dispatch by mailbox (which corresponds to CAN ID) */
    if (pending & (1 << 0)) {
        /* Mailbox 0: CAN ID 0x216 (steering angle / lateral G) */
        CAN216RX_Main();
    }
    if (pending & (1 << 1)) {
        /* Mailbox 1: CAN ID 0x231 (engine state acknowledgment) */
        CAN231TX_Main();
    }
    if (pending & (1 << 2)) {
        /* Mailbox 2: CAN ID 0x4B0 (DSC/ESP) */
        CAN4B0RX_Main();
    }
    if (pending & (1 << 3)) {
        /* Mailbox 3: CAN ID 0x212 */
        CAN212RX_Main();
    }
    if (pending & (1 << 4)) {
        /* Mailbox 4: CAN ID 0x4C0 */
        CAN4C0RX_Main();
    }
    if (pending & (1 << 5)) {
        /* Mailbox 5: CAN ID 0x430 (immobilizer) */
        CAN430RX_Main();
    }
    if (pending & (1 << 6)) {
        /* Mailbox 6: Immobilizer main */
        ImmoMain();
    }
    if (pending & (1 << 7)) {
        /* Mailbox 7: CAN ID 0x47 (steering angle) */
        CAN47RX_Main();
    }
    if (pending & (1 << 8)) {
        /* Mailbox 8: CAN ID 0x4B1 (DSC secondary) */
        CAN4B1RX_Main();
    }
}

/* -----------------------------------------------------------------
 * CANHandler — Top-Level CAN Handler
 * (0x2A9BA)
 *
 * Called from someMainFunction (0x11540). Wraps CANTX_Main and
 * CANRX_Main inside an interrupt-masked critical section.
 * ----------------------------------------------------------------- */
void CANHandler(void)
{
    /* getSR / setSR — mask interrupts during CAN processing */
    uint32_t sr = getSR();
    setSR(sr | 0x000000F0);    /* Raise IPL to mask all but NMI */

    /* Process TX chain */
    CANTX_Main();

    /* Process RX chain */
    CANRX_Main();

    /* Restore interrupt mask */
    setSR(sr);
}

/* -----------------------------------------------------------------
 * Helper function stubs (from SH-2E runtime library)
 * ----------------------------------------------------------------- */
uint32_t getSR(void) { return 0; }   /* stubbed */
void setSR(uint32_t sr) { (void)sr; } /* stubbed */
uint16_t can_get_rx_pending_flags(void) { return 0; } /* stubbed */
void CAN216RX_Main(void) {} /* stubbed */
void CAN231TX_Main(void) {} /* stubbed */
void CAN4B0RX_Main(void) {} /* stubbed */
void CAN212RX_Main(void) {} /* stubbed */
void CAN4C0RX_Main(void) {} /* stubbed */
void CAN430RX_Main(void) {} /* stubbed */
void ImmoMain(void) {}      /* stubbed */
void CAN47RX_Main(void) {}  /* stubbed */
void CAN4B1RX_Main(void) {} /* stubbed */

/* -----------------------------------------------------------------
 * can_data_decode_2468C — CAN RX Bitfield Unpacker
 * (0x2468C, 901 instructions)
 *
 * The largest function in the CAN subsystem. Decodes compressed
 * bitfield status from incoming CAN messages into individual boolean
 * flag bytes.
 *
 * Structure:
 *   1. Loads message descriptor from RAM (pointer at 0xB4E8)
 *   2. Reads 7 word values from descriptor → stores to 0xB53C-0xB544
 *   3. Reads 7 source bytes from 0xFFFFB596-0xFFFFB59C (CAN RX buffer)
 *   4. For each source byte, unpacks each bit position (0x01-0x80)
 *      into a separate boolean flag byte at 0xB55C-0xB58B (47 flags)
 *   5. Conditionally calls 77 helper functions for specific bit patterns
 *   6. Stores final decoded message byte pair to 0xB546-0xB54B
 *   7. Calls 3 FPU conversion functions for temperature/pressure decoding
 *
 * The function uses the pattern:
 *   tst #BIT → movt → add #-1 → neg → cmp/eq #1 → conditional store
 * to convert each bit test to a boolean 0x01/0x00.
 *
 * Note: This is a structurally simplified representation. The actual
 * function has 77 BSR subroutine call sites and complex control flow
 * that cannot be fully represented as straight-line C.
 * ----------------------------------------------------------------- */
static void decode_bitfield_helper(uint8_t src_byte, uint8_t *flag_base,
                                    int nbits, bool call_helpers)
{
    static const uint8_t bit_masks[8] = { 0x01, 0x02, 0x04, 0x08,
                                          0x10, 0x20, 0x40, 0x80 };
    uint8_t call_trigger = (nbits > 0) ? bit_masks[nbits - 1] : 0;

    for (int i = 0; i < nbits && i < 8; i++) {
        /* SH-2E pattern: tst #bit, movt, add #-1, neg, cmp/eq #1 */
        flag_base[i] = (src_byte & bit_masks[i]) ? 1 : 0;
    }

    /* If trigger bit is set, call associated helper functions */
    if (call_helpers && (src_byte & call_trigger)) {
        /* Calls one of 10 groups of helper functions at 0x2535E+ */
        /* (Specific helpers vary per group) */
    }
}

void can_data_decode_2468C(void)
{
    uint8_t *flags = (uint8_t *)0xFFFFB55CUL;
    uint8_t src_bytes[7];
    int i;

    /* Step 1: Read CAN message descriptor words */
    CAN_DECODE_WORD_0 = *(volatile uint16_t *)(0xFFFFB4E8UL + 3);
    CAN_DECODE_WORD_1 = *(volatile uint16_t *)(0xFFFFB4E8UL + 4);
    CAN_DECODE_WORD_2 = *(volatile uint16_t *)(0xFFFFB4E8UL + 5);
    CAN_DECODE_WORD_3 = *(volatile uint16_t *)(0xFFFFB4E8UL + 6);
    CAN_DECODE_WORD_4 = *(volatile uint16_t *)(0xFFFFB4E8UL + 7);

    /* Step 2: Read all 7 source bytes from the RX buffer/ports */
    src_bytes[0] = CAN_RX_SRC_BYTE_0;
    src_bytes[1] = CAN_RX_SRC_BYTE_1;
    src_bytes[2] = CAN_RX_SRC_BYTE_2;
    src_bytes[3] = CAN_RX_SRC_BYTE_3;
    src_bytes[4] = CAN_RX_SRC_BYTE_4;
    src_bytes[5] = CAN_RX_SRC_BYTE_5;
    src_bytes[6] = CAN_RX_SRC_BYTE_6;

    /* Step 3: Unpack each source byte into flag bytes + call helpers */

    /* Group 0 (src 0): 7 bits → flags[0..6], no helpers */
    decode_bitfield_helper(src_bytes[0], &flags[0], 7, false);

    /* Group 1 (src 1): 4 bits → flags[7..10], helpers on bit 3 */
    decode_bitfield_helper(src_bytes[1], &flags[7], 4, true);

    /* Group 2 (src 2): 8 bits → flags[11..18], no helpers */
    decode_bitfield_helper(src_bytes[2], &flags[11], 8, false);

    /* Group 3 (src 3): 2 bits → flags[19..20], helpers on bit 0 */
    decode_bitfield_helper(src_bytes[3], &flags[19], 2, true);

    /* Group 4 (src 4): 4 bits → flags[21..24], helpers on bit 3 */
    decode_bitfield_helper(src_bytes[4], &flags[21], 4, true);

    /* Group 5 (src 5): 8 bits → flags[25..32], helpers on bit 7 */
    decode_bitfield_helper(src_bytes[5], &flags[25], 8, true);

    /* Group 6 (src 6): 8 bits → flags[33..40], no helpers */
    decode_bitfield_helper(src_bytes[6], &flags[33], 8, false);

    /* Step 4: Store decoded message byte pair */
    {
        uint8_t rx_buf_base = src_bytes[0]; /* from r12-based offset */
        /* Stores last 2 decoded message bytes */
        *(volatile uint8_t *)0xFFFFB546UL = rx_buf_base;
        *(volatile uint8_t *)0xFFFFB547UL = 0;
    }

    /* Step 5: FPU conversion calls for coolant, air temp, etc. */
    /* Calls functions at ROM data pool address 0x20, 0x22, 0x24 */
    /* These convert raw sensor values to floating point */
    /* ... (3 calls with fr14 as base value, results to 0xB530-0xB538) */

    return;
}

/* -----------------------------------------------------------------
 * can_data_encoder_24614 — CAN TX Bitfield Packer
 * (0x24614, 62 instructions)
 *
 * Inverse of can_data_decode_2468C. Packs boolean flag bytes into
 * compressed CAN message bytes for transmission. Uses FPU for
 * sensor value conversion via floatToFP_16bit.
 * ----------------------------------------------------------------- */
void can_data_encoder_24614(void)
{
    /* Read sensor float values, convert to CAN byte format */
    float coolant = COOLANT_TEMP;
    float intake = IAT_FLOAT;

    /* Convert via floatToFP_16bit (mapped to 8-bit CAN data) */
    /* uint8_t enc_coolant = floatToFP_16bit(coolant, SCALE) >> 8; */
    /* uint8_t enc_intake  = floatToFP_16bit(intake, SCALE) >> 8; */

    /* Pack result into message buffer at 0xB4B0 */
    /* *(volatile uint16_t *)0xFFFFB4B0UL = (enc_coolant << 8) | enc_intake; */
}
