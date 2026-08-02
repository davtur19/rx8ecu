/*
 * =============================================================================
 * rx8_message_queue_state_dispatcher_369b8.c  —  IMMOBILIZER CAN TX FRAME
 *                                                   BUILDER / DISPATCHER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x369B8  (0x369B8..0x36ABA incl. the literal pools)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_message_queue_state_dispatcher_369b8.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random vectors,
 *               every side-effected RAM cell compared bit-exactly;
 *               0 mismatches).
 * Lift (truth): c/message_queue_state_dispatcher_369B8.c  (same address,
 *               function name message_queue_state_dispatcher_369B8)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The immobilizer CAN TX message builder ("setImmoCANTXData" in the lift): it
 * is entered from the state-machine dispatcher ImmoStateMachine_360E8 with the
 * CAN message id in r4, builds the 8-byte TX frame at 0xFFFFC238 and raises
 * the TX request/pending flags.  It is a `void f(uint8_t cmd)` LEAF: the
 * disassembly of 0x369B8..0x36ABA contains NO bsr/jsr/jmp and NO stack frame
 * (no sts.l pr / mov.l rn,@-r15), so the emulator runs it standalone with
 * `cpu.call(0x369B8, r4=cmd, ram=...)` and no handler stubs are needed.
 *
 * DISASSEMBLY (60E1D400.bin @ 0x369B8; condensed, exact branch targets)
 * ---------------------------------------------------------------------
 *     r5 = 0xFFFFC238                    ; buf base (mov.l @(0x36A40,pc),r5)
 *     buf[0] = cmd                       ; mov.b r4,@r5  (r7 = r5+1 in delay)
 *     r0 = extu.b(r4)
 *     r0 == 0x09        -> 0x369F0   (id 9: key-slot frame)
 *     r0 == 0x07        -> 0x36A6E   (id 7: rolling-key frame)
 *     r0 == 0x01/0x81   -> 0x36A88   (resp-byte frame)
 *     r0 == 0xC6/0xC8   -> 0x36A96   (zero frame)
 *     else              -> 0x36AA0   (epilogue; buf[1..4] untouched)
 *
 *   id 0x09 @0x369F0:  sel = byte@0xFFFFC290 (r4 = sel, extu.b)
 *     sel == 1:  buf[1]=sel; src = 0xFFFFC24C (slot0) -> 0x36A78
 *     sel == 2:  buf[1]=sel; src = 0xFFFFC250 (slot1) -> 0x36A78
 *     sel == 3:  buf[1]=sel; src = 0xFFFFC254 (slot2) -> 0x36A78
 *     sel == 4:  buf[1]=sel; src = 0xFFFFC258 (slot3) -> 0x36A78
 *     sel == 0xFF: buf[1]=0xFF; buf[2]=buf[3]=buf[4]=0 -> 0x36AA0
 *     else:        -> 0x36AA0 (buf[1..4] untouched)
 *     @0x36A78: v = *src;  buf[2]=(v>>16)&0xFF;  buf[3]=(v>>8)&0xFF;
 *               buf[4]=(v)&0xFF            (byte 3 of the BE word)
 *   id 0x07 @0x36A6E:  v = u32@0xFFFFC278 (rolling key)
 *               buf[1]=(v>>24)&0xFF; buf[2]=(v>>16)&0xFF; buf[3]=(v>>8)&0xFF;
 *               buf[4]=v&0xFF
 *   id 0x01/0x81 @0x36A88: buf[1]=byte@0xFFFFC294; buf[2]=buf[3]=buf[4]=0
 *   id 0xC6/0xC8 @0x36A96: buf[1]=buf[2]=buf[3]=buf[4]=0
 *
 *   epilogue @0x36AA0 (all paths): buf[5]=buf[6]=buf[7]=0;
 *     byte@signext(0xC241)=0xFFFFC241 = 1      (CAN TX request)
 *     byte@0xFFFFC296 = 0                      (CAN TX status)
 *     byte@0xFFFFC28F = 0                      (CAN TX state counter)
 *     byte@0xFFFFC299 = 1                      (CAN TX pending)
 *
 * CALLING CONVENTION
 * ------------------
 * void f(uint8_t cmd): cmd arrives in r4 (the ROM zero-extends its low byte
 * with `extu.b r4,r0` before every cmp/eq; the frame byte buf[0] is the same
 * low byte).  No other input registers, no meaningful register return (r0 is
 * a by-product), no stack usage.  The harness therefore drives it with
 * `cpu.call(0x369B8, r4=cmd, ram=...)` and compares RAM side effects.
 *
 * RAM SIDE EFFECTS (cells compared by the harness)
 * -----------------------------------------------------------------
 * written:
 *   0xFFFFC238..0xFFFFC23F  u8 x8  the 8-byte CAN TX frame (buf[0]=cmd,
 *                                  buf[1..4] per id, buf[5..7]=0)
 *   0xFFFFC241              u8  = 1    CAN TX request flag
 *   0xFFFFC296              u8  = 0    CAN TX status
 *   0xFFFFC28F              u8  = 0    CAN TX state counter
 *   0xFFFFC299              u8  = 1    CAN TX pending flag
 * read:
 *   0xFFFFC290              u8         key-match slot selector (id 0x09)
 *   0xFFFFC24C/0x250/0x254/0x258 u32   4 key words (id 0x09, sel 1..4)
 *   0xFFFFC278              u32        rolling key (id 0x07)
 *   0xFFFFC294              u8         challenge response byte (id 0x01/0x81)
 *
 * CAN mailbox: the frame at 0xFFFFC238..0xFFFFC23F is the hardware CAN TX
 * mailbox data area; 0xFFFFC241 is the TX-request bit of the same block.
 * The other three flags (0xFFFFC296 / 0xFFFFC28F / 0xFFFFC299) are the
 * software-side TX status mirror consumed by the immo state machine.
 *
 * INTERNAL CALLEES
 * ----------------
 * NONE — the function is a leaf.  (Contrast with the immo siblings: the
 * ready-to-drive handler and the state machine call this very function, but
 * the function itself calls nothing; verified by disassembly of the whole
 * range 0x369B8..0x36ABA.)
 *
 * DISCREPANCIES vs c/message_queue_state_dispatcher_369B8.c (fixed here)
 * ---------------------------------------------------------------------
 *  1. CAN TX request address: the lift writes through the c/eeprom_immo.h
 *     macro CAN_TX_REQ = (*(volatile uint8_t*)0x0000C241), but the ROM
 *     reaches the register with `mov.w @(0x36AD6,pc),r3` which SIGN-EXTENDS
 *     the 16-bit literal 0xC241 to the effective address 0xFFFFC241 (same
 *     correction already documented in rx8_immo_bad_state_set.c /
 *     rx8_immo_state_machine_360e8.c for the 0xC240 sibling).  This sample
 *     writes 0xFFFFC241, and the harness pins both 0xFFFFC240 (untouched)
 *     and 0xFFFFC241 (=1).
 *  2. buf[4] byte extraction (id 0x09): the lift reads `((uint8_t*)src)[3]`.
 *     On the big-endian SH-2E that byte is the LSB of the key word (v&0xFF),
 *     but on the little-endian host oracle the same expression yields v>>24,
 *     i.e. the WRONG byte.  This sample uses `(uint8_t)v`, which is the ROM
 *     byte on both endiannesses (the exact pattern documented in
 *     rx8_get_maf_sensor_value.c / rx8_immo_key_expander_365d6.c for BE
 *     byte assembly on the LE host).
 * =============================================================================
 */
#include <stdint.h>

/* ---- On-chip immobilizer/CAN RAM (verbatim addresses; cf. c/eeprom_immo.h,
 * ---- with the 0xC241 literal sign-extended as the CPU does). */
#define IMMO_CAN_TX_BUF      ((volatile uint8_t *)0xFFFFC238)  /* 8-byte TX frame */
#define IMMO_CAN_TX_REQ      (*(volatile uint8_t *)0xFFFFC241) /* TX request (signext 0xC241) */
#define IMMO_WAIT_STATE      (*(volatile uint8_t *)0xFFFFC290) /* key-match slot (1..4/0xFF) */
#define IMMO_RESP_BYTE       (*(volatile uint8_t *)0xFFFFC294) /* challenge response */
#define IMMO_CAN_TX_STATUS   (*(volatile uint8_t *)0xFFFFC296) /* TX status */
#define IMMO_CAN_TX_STATE    (*(volatile uint8_t *)0xFFFFC28F) /* TX state counter */
#define IMMO_CAN_TX_PENDING  (*(volatile uint8_t *)0xFFFFC299) /* TX pending flag */
#define IMMO_KEYGEN_ADC      (*(volatile uint32_t *)0xFFFFC278) /* rolling key out */
#define IMMO_KEY_SLOT0       (*(volatile uint32_t *)0xFFFFC24C)
#define IMMO_KEY_SLOT1       (*(volatile uint32_t *)0xFFFFC250)
#define IMMO_KEY_SLOT2       (*(volatile uint32_t *)0xFFFFC254)
#define IMMO_KEY_SLOT3       (*(volatile uint32_t *)0xFFFFC258)

/* 0x369B8 — immobilizer CAN TX message builder/dispatcher (see header). */
void rx8_message_queue_state_dispatcher_369b8(uint8_t cmd)
{
    volatile uint8_t *buf = IMMO_CAN_TX_BUF;   /* 0xFFFFC238, 8 bytes */

    buf[0] = cmd;                              /* 0x369BC mov.b r4,@r5 */
    switch (cmd) {
    case 0x09: {                               /* 0x369C2 cmp/eq #9 */
        uint8_t sel = IMMO_WAIT_STATE;         /* 0xFFFFC290 */
        uint32_t *src = 0;
        switch (sel) {
        case 1:  src = (uint32_t *)0xFFFFC24C; break;   /* 0x369F6 slot0 */
        case 2:  src = (uint32_t *)0xFFFFC250; break;   /* 0x36A04 slot1 */
        case 3:  src = (uint32_t *)0xFFFFC254; break;   /* 0x36A12 slot2 */
        case 4:  src = (uint32_t *)0xFFFFC258; break;   /* 0x36A22 slot3 */
        case 0xFF:                             /* 0x36A58 cmp/eq #0xFF */
            buf[1] = sel;                      /* 0x36A64 mov.b r4,@r7 */
            buf[2] = buf[3] = buf[4] = 0;      /* 0x36A66..0x36A6C */
            goto epilogue;                     /* 0x36A6A -> 0x36AA0 */
        default:
            goto epilogue;                     /* 0x36A5E bf/s 0x36AA0 */
        }
        {
            uint32_t v = *src;                 /* 0x36A78 mov.l @r4,r0 */
            buf[1] = sel;                      /* 0x36A64 mov.b r4,@r7 */
            buf[2] = (uint8_t)(v >> 16);       /* 0x36A7A shlr16 + 0x36A7C */
            buf[3] = (uint8_t)(v >> 8);        /* 0x36A80 shlr8 + 0x36A82 */
            buf[4] = (uint8_t)v;               /* 0x36A86 byte 3 of the BE word */
        }
        break;
    }
    case 0x07: {                               /* 0x369C8 cmp/eq #7 */
        uint32_t v = IMMO_KEYGEN_ADC;          /* 0xFFFFC278 */
        buf[1] = (uint8_t)(v >> 24);           /* 0x36A70..0x36A76 */
        buf[2] = (uint8_t)(v >> 16);           /* 0x36A78..0x36A7C */
        buf[3] = (uint8_t)(v >> 8);            /* 0x36A7E..0x36A82 */
        buf[4] = (uint8_t)v;                   /* 0x36A86 byte 3 */
        break;
    }
    case 0x01:                                 /* 0x369CE cmp/eq #1 */
    case 0x81:                                 /* 0x369D4 cmp/eq r1 (0x81) */
        buf[1] = IMMO_RESP_BYTE;               /* 0xFFFFC294 */
        buf[2] = buf[3] = buf[4] = 0;          /* 0x36A90..0x36A94 */
        break;
    case 0xC6:                                 /* 0x369DC cmp/eq r1 (0xC6) */
    case 0xC8:                                 /* 0x369E4 cmp/eq r1 (0xC8) */
        buf[1] = buf[2] = buf[3] = buf[4] = 0; /* 0x36A98..0x36A9E */
        break;
    default:
        break;                                 /* buf[1..4] untouched */
    }
epilogue:                                      /* 0x36AA0 */
    buf[5] = buf[6] = buf[7] = 0;              /* 0x36AAA..0x36AAE */
    IMMO_CAN_TX_REQ     = 1;                   /* 0x36AB0 @0xFFFFC241 */
    IMMO_CAN_TX_STATUS  = 0;                   /* 0x36AB2 @0xFFFFC296 */
    IMMO_CAN_TX_STATE   = 0;                   /* 0x36AB4 @0xFFFFC28F */
    IMMO_CAN_TX_PENDING = 1;                   /* 0x36ABA @0xFFFFC299 (rts delay) */
}
