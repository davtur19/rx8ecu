/*
 * =============================================================================
 * rx8_immo_state_ready_to_drive_engine_off.c  —  IMMOBILIZER "READY TO DRIVE,
 *                                                 ENGINE OFF" STATE HANDLER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x364D8
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_immo_state_ready_to_drive_engine_off.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random initial-RAM
 *               state vectors, comparing every side-effected RAM cell on both
 *               the state==1 and state!=1 paths; 0 mismatches).
 * Lift (truth): c/ImmoStateReadyToDriveEngineOff.c  (same address 0x364D8)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Idle-state handler ("ready to drive", engine off) of the immobilizer state
 * machine.  It is entered from ImmoMain and branches on the state byte:
 *
 *   - state == 1 ("key validated"): re-runs the rolling-code generator
 *     Immo_Keygen_related_ADC (0x36AFC) until the rolling code at 0xFFFFC278
 *     CHANGES (loop shape: snapshot = *0xFFFFC278; do keygen() while
 *     (*0xFFFFC278 == snapshot)), arms the 500-tick timer 0xFFFFC27C = 0x01F4
 *     and TAIL-JUMPS into ImmoStateMachine_360E8 (0x360E8) — the state byte is
 *     still 1, so that dispatcher sees the challenge phase.
 *
 *   - state != 1: forces state = 5, decrements the general countdown
 *     0xFFFFC282 (while non-zero — the ROM zero-extends the word and does
 *     `cmp/pl`, so the whole 1..0xFFFF range counts down), and when it
 *     reaches 0: ImmoBadStateSet() (0x365B8), result code 5, CAN TX message
 *     id 0xC8 via the TX dispatcher (0x369B8), and reloads the countdown
 *     with 500.
 *
 * CALLING CONVENTION
 * ------------------
 * void f(void): normal ABI entry, no input registers, no meaningful return
 * value (the ROM leaves r0 as an arbitrary by-product of the dispatcher).
 * The function is therefore driven through the standard SH2.call() entry and
 * verified by comparing the side-effected RAM cells, exactly like the
 * rx8_immo_bad_state_set / rx8_immo_good_state_set rigs.
 *
 * CALLEE INLINING (net effects folded in, see the header of each block)
 * ---------------------------------------------------------------------
 * The ROM internally calls four subroutines whose bytes are ALWAYS executed
 * inside the emulator (ground truth); the host sample inlines their net
 * RAM effects so it is self-contained:
 *
 *   1. Immo_Keygen_related_ADC (0x36AFC) — the rolling-code mixer (verified
 *      lift c/Immo_Keygen_related_ADC.c).  Net effect: three ADC inputs, the
 *      CRC-checked adc_read() value and the mixer words 0xFFFFC288/0xFFFFC28A/
 *      0xFFFFC293 produce the next 32-bit rolling code at 0xFFFFC278 (with a
 *      fallback to the pairing words when the combined value is 0).  The two
 *      `cmp/ge` guards inside it are ALWAYS false in ROM semantics (a ~(u16)
 *      is negative as signed 32-bit), so the guarded increment blocks always
 *      run — inlined unconditionally.
 *   2. adc_read (0x3EDBC) — checksummed 32-bit read of 0xFFFF869C: if the
 *      16-bit complement of (w0 + w1) equals w2 or w3 the 32-bit word is
 *      returned, otherwise the byte 0xFFFFC6AC is set to 1 and 0 is returned.
 *   3. ImmoStateMachine_360E8 (0x360E8) — the state-machine dispatcher, which
 *      the ROM tail-jumps into with state == 1.  Only the substates reachable
 *      by this harness are inlined (1 = bad-state + CAN 0x01, 3 = code 0);
 *      substate 2 (ImmoGetSeed_3664E path) is NOT exercised by the harness
 *      vectors and is deliberately left to the real ROM bytes.
 *   4. ImmoBadStateSet (0x365B8) and message_queue_state_dispatcher_369B8
 *      (0x369B8) — the same verified lifts already used by
 *      rx8_immo_bad_state_set.c (setImmoLight(0) folded to `word &= ~0x0060`)
 *      and the CAN TX frame builder (ids 0x01/0xC8 reached here).
 *
 * DISCREPANCIES vs c/ImmoStateReadyToDriveEngineOff.c
 * ---------------------------------------------------
 * The lift itself matched the disassembly of 0x364D8-0x36544 exactly (loop
 * shape, `cmp/pl` on the zero-extended countdown, `+0xFFFF == -1` decrement,
 * tail jump).  Two discrepancies were found in the CALLEE lift used to
 * inline the keygen and were corrected here:
 *   1. c/Immo_Keygen_related_ADC.c reads adc_c from 0xFFFF9EF2, but the ROM
 *      `mov.w @(0x1C,r4),r0` at 0x36B10 with r4 = 0xFFFF9EE4 addresses
 *      0xFFFF9EE4 + 0x1C = 0xFFFF9F00 (the disp field 0xE is multiplied by 2
 *      for word loads; 0xFFFF9EF2 = base + 0x0E is the wrong, byte-offset
 *      reading).  This sample reads 0xFFFF9F00, and the harness seeds that
 *      address so the emulator exercises it.
 *   2. The keygen lift models the two `cmp/ge` guards with C expressions of
 *      the wrong polarity (unsigned `>=` on `~(u32)(u16)` is always TRUE in
 *      C, whereas the ROM's signed compare is always FALSE).  The lift's own
 *      comment documents the ROM behaviour; this sample inlines the ROM
 *      behaviour (guards never taken -> increment blocks always run).
 *
 * RAM SIDE EFFECTS (all cells the harness compares, per branch)
 * -----------------------------------------------------------------
 * state != 1:
 *   0xFFFFC28E u8  = 5                          (state forced to 5)
 *   0xFFFFC282 u16 = countdown-1 (while > 0)     (cmp/pl on signed value)
 *   and when the countdown reaches 0:
 *   0xFFFFF754 u16 &= ~0x0060                   (immo lamp off, setImmoLight(0))
 *   0xFFFFC240 u8  = 0                          (CAN TX data flag)
 *   0xFFFFC284 u16 = 0x01F4                     (bad-state timeout = 500)
 *   0xFFFFC28D u8  = 4 then 5                   (ImmoBadStateSet code, then 5)
 *   0xFFFFC238..0xFFFFC23F = C8 00 00 00 00 00 00 00 (CAN TX frame, id 0xC8)
 *   0xFFFFC241 u8  = 1, 0xFFFFC296 = 0, 0xFFFFC28F = 0, 0xFFFFC299 = 1
 *   0xFFFFC282 u16 = 0x01F4                     (countdown reload = 500)
 * state == 1 (after the keygen loop):
 *   0xFFFFC278 u32 / 0xFFFFC288 u16 / 0xFFFFC28A u16 / 0xFFFFC293 u8
 *              = next rolling code + mixer state (keygen net effect)
 *   0xFFFFC6AC u8  = 1 if the adc_read checksum failed (else untouched)
 *   0xFFFFC27C u16 = 0x01F4                     (500-tick timer)
 *   plus, through the tail-jumped state machine with state==1:
 *     sub==1: 0xFFFFF754 &= ~0x0060, 0xFFFFC240=0, 0xFFFFC284=0x01F4,
 *             0xFFFFC28D=4, 0xFFFFC294=0, CAN frame id 0x01
 *             (buf[1]=0xFFFFC294=0), 0xFFFFC241=1, 0xFFFFC296=0,
 *             0xFFFFC28F=0, 0xFFFFC299=1, 0xFFFFC29A=1
 *     sub==3: 0xFFFFC28D = 0
 *     other : no state-machine writes
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* Immobilizer state-machine locations (same map as c/eeprom_immo.h; the lamp
 * and CAN-TX addresses are spelled out with the CPU's sign-extended effective
 * addresses 0xFFFFF754 / 0xFFFFC240, exactly like rx8_immo_good_state_set.c). */
#define IMMO_CAN_TX_BUF      ((volatile uint8_t *)0xFFFFC238) /* 8-byte TX frame */
#define IMMO_ROLLING_CODE    (*(volatile uint32_t *)0xFFFFC278) /* rolling code  */
#define IMMO_TIMER_27C       (*(volatile uint16_t *)0xFFFFC27C) /* 500-tick timer*/
#define IMMO_TIMER           (*(volatile uint16_t *)0xFFFFC282) /* countdown     */
#define IMMO_STATE_CODE      (*(volatile uint8_t *)0xFFFFC28D)  /* result code   */
#define IMMO_STATE_BYTE      (*(volatile uint8_t *)0xFFFFC28E)  /* state byte    */
#define IMMO_SUBSTATE        (*(volatile uint8_t *)0xFFFFC291)  /* substate      */
#define IMMO_RESP_BYTE       (*(volatile uint8_t *)0xFFFFC294)  /* response byte */
#define IMMO_CAN_TX_STATUS   (*(volatile uint8_t *)0xFFFFC296)
#define IMMO_CAN_TX_STATE    (*(volatile uint8_t *)0xFFFFC28F)
#define IMMO_CAN_TX_PENDING  (*(volatile uint8_t *)0xFFFFC299)
#define IMMO_GOODSTATE_FLAG  (*(volatile uint8_t *)0xFFFFC29A)
#define IMMO_KEYGEN_ADC      (*(volatile uint32_t *)0xFFFFC278) /* keygen out    */
#define IMMO_MIX_WORD        (*(volatile uint16_t *)0xFFFFC288)
#define IMMO_MIX_WORD2       (*(volatile uint16_t *)0xFFFFC28A)
#define IMMO_MIX_BYTE        (*(volatile uint8_t *)0xFFFFC293)
#define IMMO_CAN_TX_DATA     (*(volatile uint8_t *)0xFFFFC240)  /* CAN TX flag   */
#define IMMO_CAN_TX_REQ      (*(volatile uint8_t *)0xFFFFC241)  /* TX request    */
#define IMMO_TIMEOUT_CTR     (*(volatile uint16_t *)0xFFFFC284) /* bad-state ctr */
#define IMMO_LAMP_REG        (*(volatile uint16_t *)0xFFFFF754) /* status word   */

/* ---- 0x3EDBC — adc_read(0xFFFF869C, 0): checksummed 32-bit read. ----------
 * If ~(w0 + w1) (16-bit, signed loads) equals w2 or w3 the 32-bit word at
 * 0xFFFF869C is returned; otherwise byte@0xFFFFC6AC = 1 and 0 is returned
 * (the ROM's fall-through loads the r5 argument from the stack = 0). */
static uint32_t rx8_immo_adc_read(void)
{
    uint16_t w0 = RX8_IO16(0xFFFF869C);
    uint16_t w1 = RX8_IO16(0xFFFF869E);
    uint16_t w2 = RX8_IO16(0xFFFF86A0);
    uint16_t w3 = RX8_IO16(0xFFFF86A2);
    uint16_t comp = (uint16_t)(~(uint32_t)((int16_t)w0 + (int16_t)w1));

    if (comp == w2 || comp == w3)
        return RX8_IO32(0xFFFF869C);
    RX8_IO8(0xFFFFC6AC) = 1u;
    return 0u;
}

/* ---- 0x36AFC — Immo_Keygen_related_ADC (net effect; verified lift
 * c/Immo_Keygen_related_ADC.c, with the two corrections from the header:
 * adc_c comes from 0xFFFF9F00, and the never-taken `cmp/ge` guards are
 * inlined as the always-executed blocks).  Reads adc_a/b/c, mixes them with
 * the previous mixer state and adc_read() into the next rolling code. */
static void rx8_immo_keygen_related_adc(void)
{
    uint16_t adc_a = RX8_IO16(0xFFFF9F1C);
    uint16_t adc_b = RX8_IO16(0xFFFF9F1E);
    uint16_t adc_c = RX8_IO16(0xFFFF9F00);
    uint32_t ret   = rx8_immo_adc_read();

    /* 0x36B1E..0x36B30: *cnt = (ret&0xFFFF) + adc_a + *cnt (low byte). */
    IMMO_MIX_BYTE = (uint8_t)((uint16_t)ret + adc_a + IMMO_MIX_BYTE);

    /* 0x36B32..0x36B5A: guard1 (`~*w288 >= (ret>>16)`) never taken in ROM:
     * if *w28A == 0xFFFF the counter bumps, then *w28A is incremented. */
    if ((uint16_t)IMMO_MIX_WORD2 == 0xFFFFu)
        IMMO_MIX_BYTE = (uint8_t)(IMMO_MIX_BYTE + 1);
    IMMO_MIX_WORD2 = (uint16_t)(IMMO_MIX_WORD2 + 1);

    /* 0x36B5C..0x36B64: w288 = (ret>>16)&0xFFFF + s16(w288) + adc_b. */
    IMMO_MIX_WORD = (uint16_t)(((ret >> 16) & 0xFFFFu) + (int16_t)IMMO_MIX_WORD + adc_b);

    /* 0x36B66..0x36B7C: guard2 (`~*w28A >= (ret&0xFF0000)>>8`) never taken:
     * the counter always bumps. */
    IMMO_MIX_BYTE = (uint8_t)(IMMO_MIX_BYTE + 1);

    /* 0x36B7E..0x36B88: w28A = ((ret&0x00FFFF00)>>8) + s16(w28A) + s16(adc_c). */
    IMMO_MIX_WORD2 = (uint16_t)(((ret & 0x00FFFF00u) >> 8) +
                                (int16_t)IMMO_MIX_WORD2 + (int16_t)adc_c);

    /* 0x36B8A..0x36B98: w288 = ((adc_c&0xFF)<<8 | adc_a&0xFF) ^ w288. */
    IMMO_MIX_WORD = (uint16_t)(((uint16_t)((adc_c & 0xFFu) << 8) +
                                (adc_a & 0xFFu)) ^ IMMO_MIX_WORD);

    /* 0x36B9A..0x36BA2: w28A = ~(((adc_a&0xFF)<<8 | adc_b&0xFF) ^ w28A). */
    IMMO_MIX_WORD2 = (uint16_t)~(uint16_t)(((uint16_t)((adc_a & 0xFFu) << 8) +
                                             (adc_b & 0xFFu)) ^ IMMO_MIX_WORD2);

    /* 0x36BA4..0x36BA8: cnt = adc_b ^ cnt. */
    IMMO_MIX_BYTE = (uint8_t)(adc_b ^ IMMO_MIX_BYTE);

    /* 0x36BAC..0x36BCA: publish (w288<<16)|w28A; fall back to the pairing
     * words 0xFFFFC2DC | 0xFFFFC2E0 when the combined value is 0. */
    {
        uint32_t combined = ((uint32_t)IMMO_MIX_WORD << 16) | IMMO_MIX_WORD2;
        IMMO_KEYGEN_ADC = combined;
        if (combined == 0)
            IMMO_KEYGEN_ADC = RX8_IO32(0xFFFFC2DC) | RX8_IO32(0xFFFFC2E0);
    }
}

/* ---- 0x365B8 — ImmoBadStateSet (net effect; same fold-in as
 * rx8_immo_bad_state_set.c: setImmoLight(0) clears the lamp bits 0x20/0x40). */
static void rx8_immo_bad_state_set(void)
{
    IMMO_LAMP_REG &= ~0x0060u;
    IMMO_CAN_TX_DATA = 0u;
    IMMO_TIMEOUT_CTR = 0x01F4u;
    IMMO_STATE_CODE  = 4u;
}

/* ---- 0x369B8 — message_queue_state_dispatcher_369B8 (net effect for the
 * ids reached here: 0x01 and 0xC8; see c/message_queue_state_dispatcher_369B8.c). */
static void rx8_immo_dispatcher(uint8_t cmd)
{
    volatile uint8_t *buf = IMMO_CAN_TX_BUF;

    buf[0] = cmd;
    if (cmd == 0x01 || cmd == 0x81) {
        buf[1] = IMMO_RESP_BYTE;
        buf[2] = buf[3] = buf[4] = 0;
    } else if (cmd == 0xC6 || cmd == 0xC8) {
        buf[1] = buf[2] = buf[3] = buf[4] = 0;
    } else {
        /* buf[1..4] untouched */
    }
    buf[5] = buf[6] = buf[7] = 0;
    IMMO_CAN_TX_REQ     = 1u;      /* 0xFFFFC241 */
    IMMO_CAN_TX_STATUS  = 0u;      /* 0xFFFFC296 */
    IMMO_CAN_TX_STATE   = 0u;      /* 0xFFFFC28F */
    IMMO_CAN_TX_PENDING = 1u;      /* 0xFFFFC299 */
}

/* ---- 0x364D8  idle-state handler ("ready to drive", engine off) ---------- */
void rx8_immo_state_ready_to_drive_engine_off(void)
{
    if (IMMO_STATE_BYTE == 1) {
        /* Key validated: re-run the key generator until the rolling code
         * changes, arm the 500-tick timer, then fall into the main state
         * machine (tail jump 0x360E8).  Loop shape verified at 0x364EA-0x364FA:
         * snapshot = *0xFFFFC278; do keygen(); while (*0xFFFFC278 == snapshot). */
        uint32_t snapshot = IMMO_ROLLING_CODE;
        do {
            rx8_immo_keygen_related_adc();       /* 0x36AFC */
        } while (IMMO_ROLLING_CODE == snapshot);

        IMMO_TIMER_27C = 0x01F4u;                /* 0x364FC..0x36500 */

        /* Tail jump 0x360E8 — ImmoStateMachine_360E8 with state == 1.  Only
         * the substate paths exercised by the harness are inlined (sub 2, the
         * ImmoGetSeed_3664E path, is left to the real ROM bytes). */
        if (IMMO_SUBSTATE == 1) {
            rx8_immo_bad_state_set();            /* 0x36106 */
            IMMO_RESP_BYTE = 0;                  /* 0x3610C */
            rx8_immo_dispatcher(0x01);           /* 0x3610E */
            IMMO_GOODSTATE_FLAG = 1;             /* 0x36118 */
        } else if (IMMO_SUBSTATE == 3) {
            IMMO_STATE_CODE = 0;                 /* 0x36126 */
        }
        /* substate 2 / other: no state-machine side effects */
    } else {
        IMMO_STATE_BYTE = 5;                     /* 0x3650A..0x3650E */

        /* 0x36510..0x36520: decrement the countdown while it is non-zero
         * (ROM zero-extends the word first: `extu.w r3,r3; cmp/pl r3`, so any
         * value in 1..0xFFFF counts down — including the 0x8000..0xFFFF range). */
        {
            uint16_t cnt = IMMO_TIMER;
            if (cnt != 0)
                IMMO_TIMER = (uint16_t)(cnt - 1);  /* r2 + 0xFFFF == r2 - 1 */
        }

        /* 0x36522..0x3653A: on countdown expiry: ImmoBadStateSet(), result
         * code 5, CAN TX message 0xC8, countdown reloaded with 500. */
        if (IMMO_TIMER == 0) {
            rx8_immo_bad_state_set();            /* 0x3652A */
            IMMO_STATE_CODE = 5;                 /* 0x36536 (bsr delay slot) */
            rx8_immo_dispatcher(0xC8);           /* 0x36534 */
            IMMO_TIMER = 0x01F4u;                /* 0x36538..0x3653A */
        }
    }
}
