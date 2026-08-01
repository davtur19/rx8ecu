/*
 * =============================================================================
 * rx8_immo_update_related.c  —  IMMOBILIZER EEPROM WRITE-QUEUE DRIVER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x37120
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_immo_update_related.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random initial
 *               RAM states, comparing every side-effected cell, including
 *               the E2 shadow writes and the EEPROM-scheduler cells;
 *               0 mismatches).
 * Lift (truth): c/ImmoUpdateRelated.c  (ImmoUpdateRelated @ 0x37120)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Drives the EEPROM write queue used to persist the immobilizer pairing data.
 * Called from the immo main loop once per pass (callgraph: ImmoMain @0x35202
 * -> 0x37120).  It is a `void f(void)` ABI leaf: no arguments, no meaningful
 * register result — everything observable is in on-chip RAM, so verification
 * is a pure RAM-side-effect comparison (same rig as
 * rx8_immo_bad_state_set / 0x365B8).
 *
 * BEHAVIOUR (from the lift, confirmed against the disassembly below)
 * ------------------------------------------------------------------
 *   - if init-done (0xFFFFC2D5) != 0: return.
 *   - if armed (0xFFFFC2D6) == 0:
 *       * if work index0 (0xFFFFC2D8) != 0x5A: store 0x5A there, queue
 *         E2 code 0x0C at 0xFFFFC2D1, run updateE2RAMBasedOnInput(0x0C),
 *         then set busy (0xFFFFC2D7) and armed (0xFFFFC2D6).
 *       * else: mark init done (0xFFFFC2D5 = 1).
 *   - else (armed): snapshot busy, call 0x37000 (sub_37000) with the
 *     pending code.  If the E2 write-done flag 0xFFFFC2F8 == 1:
 *       * busy was 1: clear 0xFFFFC2D2 and 0xFFFFC2D7, queue code 3 at
 *         0xFFFFC2D1 and tail-jump updateE2RAMBasedOnInput(3) (@0x36D0C).
 *       * busy was 0: clear 0xFFFFC2D2 and 0xFFFFC2D1, set init done
 *         (0xFFFFC2D5 = 1) and disarm (0xFFFFC2D6 = 0).
 *
 * VERIFIED LISTING (disassembly of 60E1D400.bin @ 0x37120)
 * ----------------------------------------------------------
 *    0x3712E  mov.l @(0x371D0,pc),r9    ; r9  = 0xFFFFC2D5  init-done
 *    0x37130  mov.b @r9,r3 / tst r3,r3 / bf/s 0x371BA       ; if !=0 return
 *    0x37138  mov.l @(0x371D4,pc),r10   ; r10 = 0xFFFFC2D7  busy
 *    0x3713A  mov.l @(0x371D8,pc),r11   ; r11 = 0xFFFFC2D6  armed
 *    0x3713C  mov.l @(0x371DC,pc),r12   ; r12 = 0xFFFFC2D1  pending code
 *    0x3713E  mov.b @r11,r3 / tst r3,r3 / bf/s 0x37168      ; if armed !=0 go
 *    0x37146  mov.l @(0x371E0,pc),r4    ; r4  = 0xFFFFC2D8  work index0
 *    0x3714C  cmp/eq #0x5A,r0           ; (work index after extu.b)
 *    0x3714E  bt/s 0x37164              ; ==0x5A -> mark init done
 *    0x37152  mov #0x5A,r2 / mov.b r2,@r4                  ; work idx0 = 0x5A
 *    0x37156  mov #0x0C,r3 / mov.b r3,@r12                 ; pending = 0x0C
 *    0x3715A  bsr 0x36D0C              ; updateE2RAMBasedOnInput(0x0C)
 *    0x3715E  mov.b r13(1),@r10        ; busy = 1
 *    0x37160  bra 0x371BA / mov.b r13(1),@r11              ; armed = 1
 *    0x37164  bra 0x371BA / mov.b r13(1),@r9               ; init-done = 1
 *    0x37168  mov.b @r10,r0            ; was_busy snapshot
 *    0x3716E  cmp/eq #0x01,r0 / bf/s 0x371A0               ; busy? -> busy path
 *    0x37172  mov.b @r12,r4            ;   (delay) r4 = pending code
 *    0x37174  bsr 0x37000              ; sub_37000(pending)
 *    0x37178  mov.w @(0x371CA,pc),r3   ; r3 = signext(0xC2F8) = 0xFFFFC2F8
 *    0x3717E  cmp/eq #0x01,r0          ; E2 write-done == 1?
 *    0x37184  mov.l @(0x371CC,pc),r1   ; r1 = 0xFFFFC2D2
 *    0x37186  mov #0x03,r2
 *    0x37188  mov.b r14(0),@r1         ; 0xFFFFC2D2 = 0
 *    0x3718A  mov r2,r4                ; r4 = 3
 *    0x3718C  mov.b r14(0),@r10        ; busy = 0
 *    0x3718E  mov.b r2,@r12            ; pending = 3
 *    0x3719C  bra 0x36D0C              ; tail updateE2RAMBasedOnInput(3)
 *    0x371A0  bsr 0x37000              ; sub_37000(pending)  [not busy]
 *    0x371B0  mov.l @(0x371CC,pc),r1   ; r1 = 0xFFFFC2D2
 *    0x371B2  mov.b r14(0),@r1         ; 0xFFFFC2D2 = 0
 *    0x371B4  mov.b r14(0),@r12        ; pending = 0
 *    0x371B6  mov.b r13(1),@r9         ; init-done = 1
 *    0x371B8  mov.b r14(0),@r11        ; armed = 0
 *    ... literal pool @0x371CA: C2F8 | FFFFC2D2 FFFFC2D5 FFFFC2D7 FFFFC2D6
 *        FFFFC2D1 FFFFC2D8
 *
 * DISCREPANCIES vs c/ImmoUpdateRelated.c (documented, corrected here)
 * ------------------------------------------------------------------
 *  1. The lift's E2_WRITE_COMPLETE macro points at 0x0000C2F8; the ROM loads
 *     the flag with `mov.w @(0x371CA,pc),r3` whose 16-bit literal 0xC2F8 is
 *     SIGN-EXTENDED to the effective address 0xFFFFC2F8 (the on-chip RAM /
 *     EEPROM-scheduler handoff cell).  Same sign-extension pattern already
 *     documented for CAN_TX_DATA in rx8_immo_bad_state_set.c / good_state_set.
 *     This sample reads/writes 0xFFFFC2F8.
 *  2. updateE2RAMBasedOnInput @0x36D0C loads its CAN-shadow sources with
 *     `mov.w @(0x36DE6,pc),r13` = 0xC243, again SIGN-EXTENDED: the E2
 *     pairing bytes are copied from 0xFFFFC242/3/4, not from the lift's
 *     0x0000C242/3/4 CAN_SHADOW macros.
 *
 * INLINED CALLEES (all validated against the REAL bytes the emulator runs)
 * ------------------------------------------------------------------------
 *  sub_37000 @0x37000 — EEPROM commit dispatcher: skips when 0xFFFFC2D2 is
 *     set, else selects (index,len) for `code` and calls the SPI scheduler
 *     eeprom_write_sched @0x38B5C with flag=1; if the scheduler returns 0
 *     (still busy) the queue flag 0xFFFFC2D2 is set.
 *  eeprom_write_sched @0x38B5C (flag==1 only) — pure-RAM scheduler (no GPIO
 *     bit-bang): writes the E2 request cells 0xFFFFC506 (word), 0xFFFFC511,
 *     0xFFFFC4FE (word), 0xFFFFC500 (word), 0xFFFFC514, then, for flag==1,
 *     clears the done flag 0xFFFFC2F8 and 0xFFFFC2FB, sets 0xFFFFC50C=1 and
 *     clears 0xFFFFC50F/0xFFFFC516/0xFFFFC515/0xFFFFC510; returns 0 when it
 *     actually scheduled, 1 when a schedule is already pending (0xFFFFC511==1).
 *  updateE2RAMBasedOnInput @0x36D0C — only codes 0x0C (13 writes) and 3
 *     (E2[0x00]) are reachable from 0x37120; each write goes through
 *     writeToE2RAMArea @0x39124 which stores byte + read-back complement into
 *     the E2 shadow 0xFFFFC2FE / 0xFFFFC3FE.
 *
 * RAM SIDE EFFECTS (the harness compares every one of these cells):
 *   immo write-queue   : 0xFFFFC2D1 u8 pending code, 0xFFFFC2D2 u8 flag,
 *                         0xFFFFC2D5 u8 init done, 0xFFFFC2D6 u8 armed,
 *                         0xFFFFC2D7 u8 busy, 0xFFFFC2D8 u8 work index0
 *   eeprom scheduler   : 0xFFFFC506 u16 index, 0xFFFFC511 u8 status,
 *                         0xFFFFC4FE u16 index>>1, 0xFFFFC500 u16 count,
 *                         0xFFFFC514 u8 flag, 0xFFFFC2F8 u8 done,
 *                         0xFFFFC2FB u8, 0xFFFFC50C u8,
 *                         0xFFFFC50F/0xFFFFC516/0xFFFFC515/0xFFFFC510 u8
 *   E2 shadow (value)  : 0xFFFFC2FE + {0x00,0x0C..0x10,0x12..0x14,0x1A..0x1E}
 *   E2 shadow (compl.) : 0xFFFFC3FE + same indices
 *
 * CALLING CONVENTION
 * ------------------
 * void f(void): entered via the normal ABI (no args in r4-r7/fr4-fr7), no
 * return value used by callers.  Internally bsr 0x37000 (sub_37000, r4 =
 * pending code) and tail-bra 0x36D0C (updateE2RAMBasedOnInput, r4 = code).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* ---- immo write-queue cells (ImmoUpdateRelated @0x37120) ---- */
#define WQ_PENDING   RX8_IO8(0xFFFFC2D1)   /* queued E2 code          */
#define WQ_FLAG_D2   RX8_IO8(0xFFFFC2D2)   /* queue busy flag         */
#define WQ_INIT_DONE RX8_IO8(0xFFFFC2D5)   /* init done flag          */
#define WQ_ARMED     RX8_IO8(0xFFFFC2D6)   /* queue armed flag        */
#define WQ_BUSY      RX8_IO8(0xFFFFC2D7)   /* busy flag               */
#define WORK_INDEX0  RX8_IO8(0xFFFFC2D8)   /* EEPROM[0] working copy  */

/* E2 write-done flag.  The ROM loads literal 0xC2F8 with `mov.w` which
 * SIGN-EXTENDS it to 0xFFFFC2F8 (see header discrepancy note 1). */
#define E2_DONE      RX8_IO8(0xFFFFC2F8)

/* ---- EEPROM scheduler cells (eeprom_write_sched @0x38B5C) ---- */
#define SCHED_INDEX  RX8_IO16(0xFFFFC506)  /* E2 index (word)          */
#define SCHED_STATUS RX8_IO8(0xFFFFC511)   /* schedule pending flag    */
#define SCHED_INDEX2 RX8_IO16(0xFFFFC4FE)  /* index >> 1               */
#define SCHED_COUNT  RX8_IO16(0xFFFFC500)  /* (len+index-1)>>1         */
#define SCHED_FLAG   RX8_IO8(0xFFFFC514)   /* scheduler mode flag      */
#define SCHED_C2FB   RX8_IO8(0xFFFFC2FB)
#define SCHED_C50C   RX8_IO8(0xFFFFC50C)
#define SCHED_C50F   RX8_IO8(0xFFFFC50F)
#define SCHED_C516   RX8_IO8(0xFFFFC516)
#define SCHED_C515   RX8_IO8(0xFFFFC515)
#define SCHED_C510   RX8_IO8(0xFFFFC510)

/* ---- E2 working-copy source cells (updateE2RAMBasedOnInput @0x36D0C) ---- */
#define WORK_12      RX8_IO8(0xFFFFC2E5)
#define WORK_13      RX8_IO8(0xFFFFC2E6)
#define WORK_15      RX8_IO8(0xFFFFC2E7)
#define WORK_19      RX8_IO8(0xFFFFC2E8)
#define WORK_20      RX8_IO8(0xFFFFC2E9)
#define WORK_26      RX8_IO8(0xFFFFC2EE)
#define WORK_27      RX8_IO8(0xFFFFC2EF)
#define WORK_28      RX8_IO8(0xFFFFC2F0)
#define WORK_29      RX8_IO8(0xFFFFC2F1)
#define WORK_30      RX8_IO8(0xFFFFC2F2)
/* CAN-shadow E2 sources: the ROM loads literal 0xC243 with `mov.w`, so the
 * real addresses are 0xFFFFC242/3/4 (sign-extended; see discrepancy note 2). */
#define CAN_C242     RX8_IO8(0xFFFFC242)
#define CAN_C243     RX8_IO8(0xFFFFC243)
#define CAN_C244     RX8_IO8(0xFFFFC244)

/* ---- writeToE2RAMArea @0x39124 inlined (byte + read-back complement) ---- */
static void e2_shadow_write(uint16_t index, uint8_t val)
{
    volatile uint8_t *p = (volatile uint8_t *)(uintptr_t)(0xFFFFC2FEu + index);
    volatile uint8_t *c = (volatile uint8_t *)(uintptr_t)(0xFFFFC3FEu + index);
    *p = val;
    *c = (uint8_t)~*p;          /* complement of the value READ BACK */
}

/* ---- updateE2RAMBasedOnInput @0x36D0C, only the codes reachable from
 * 0x37120: 0x0C (13 writes) and 3 (single write). ------------------------ */
static void update_e2_ram(uint8_t code)
{
    switch (code) {
    case 0x03:
        e2_shadow_write(0x00, WORK_INDEX0);
        break;
    case 0x0C:
        e2_shadow_write(0x0C, WORK_12);
        e2_shadow_write(0x0D, WORK_13);
        e2_shadow_write(0x0E, CAN_C243);
        e2_shadow_write(0x0F, WORK_15);
        e2_shadow_write(0x10, CAN_C242);
        e2_shadow_write(0x14, WORK_20);
        e2_shadow_write(0x12, CAN_C244);
        e2_shadow_write(0x13, WORK_19);
        e2_shadow_write(0x1A, WORK_26);
        e2_shadow_write(0x1B, WORK_27);
        e2_shadow_write(0x1C, WORK_28);
        e2_shadow_write(0x1D, WORK_29);
        e2_shadow_write(0x1E, WORK_30);
        break;
    default:
        break;                  /* unreachable from 0x37120 */
    }
}

/* ---- eeprom_write_sched @0x38B5C inlined (sub_37000 always uses flag=1).
 * The C500 computation replicates the ROM's add #0xFF / cmp/gt / addc / shar
 * sequence so the (len+index)==0 edge yields 0 (see header). ------------ */
static uint8_t e2_write_sched(uint16_t index, uint8_t len)
{
    SCHED_INDEX = index;                        /* 0x38B7A, always written */
    if (SCHED_STATUS == 1)                      /* schedule already pending */
        return 1;
    SCHED_STATUS = 1;
    SCHED_INDEX2 = (uint16_t)(index >> 1);      /* shar */
    {
        uint32_t x = (uint32_t)len + index;
        int t;
        x = (x - 1) & 0xFFFFFFFFu;              /* add #0xFF (wrap)        */
        t = ((int32_t)x < 0) ? 1 : 0;           /* cmp/gt #0 with r2 = 0   */
        x = (x + (uint32_t)t) & 0xFFFFFFFFu;    /* addc r2,r0              */
        SCHED_COUNT = (uint16_t)((int32_t)x >> 1);  /* shar r0 */
    }
    SCHED_FLAG = 1;
    /* flag == 1 branch */
    E2_DONE    = 0;
    SCHED_C2FB = 0;
    SCHED_C50C = 1;
    SCHED_C50F = 0;
    SCHED_C516 = 0;
    SCHED_C515 = 0;
    SCHED_C510 = 0;
    return 0;                                   /* scheduled (still busy) */
}

/* ---- sub_37000 @0x37000 inlined (E2 commit dispatcher). ---------------- */
static uint8_t sub_37000_inline(uint8_t code)
{
    uint16_t index = 0;
    uint8_t  len   = 0;
    int      called = 0;

    if (WQ_FLAG_D2 != 0)                        /* 0x37108-ish: skip */
        return 1;

    switch (code) {
    case 0x01: index = 0x0A; len = 0x02; called = 1; break;
    case 0x02: index = 0x02; len = 0x08; called = 1; break;
    case 0x03: index = 0x00; len = 0x02; called = 1; break;
    case 0x04: index = 0x0C; len = 0x06; called = 1; break;
    case 0x05: index = 0x12; len = 0x02; called = 1; break;
    case 0x06: index = 0x0E; len = 0x02; called = 1; break;
    case 0x07: index = 0x16; len = 0x04; called = 1; break;
    case 0x08: index = 0x14; len = 0x02; called = 1; break;
    case 0x09: index = 0x0C; len = 0x08; called = 1; break;
    case 0x0A: index = 0x1A; len = 0x04; called = 1; break;
    case 0x0B: index = 0x02; len = 0x0A; called = 1; break;
    case 0x0C: index = 0x0C; len = 0x14; called = 1; break;
    case 0x0D: index = 0x1E; len = 0x02; called = 1; break;
    case 0x0E: index = 0x0C; len = 0x02; called = 1; break;
    case 0x0F: index = 0x0E; len = 0x02; called = 1; break;
    case 0xFF: index = 0x00; len = 0x20; called = 1; break;
    default:
        break;                                  /* no call */
    }

    if (called) {
        if (e2_write_sched(index, len) == 0)    /* 0x37114: still busy */
            WQ_FLAG_D2 = 1;
        return 0;
    }
    return 1;
}

/* ---- 0x37120  immobilizer EEPROM write-queue driver (see header) ------- */
void rx8_immo_update_related(void)
{
    if (WQ_INIT_DONE != 0)          /* 0x37130 tst / bf return */
        return;

    if (WQ_ARMED == 0) {            /* 0x3713E armed?          */
        if (WORK_INDEX0 != 0x5A) {  /* 0x3714C cmp/eq #0x5A    */
            WORK_INDEX0 = 0x5A;     /* 0x37152..0x37154        */
            WQ_PENDING  = 0x0C;     /* 0x37156..0x37158        */
            update_e2_ram(0x0C);    /* bsr 0x36D0C             */
            WQ_BUSY     = 1;        /* 0x3715E                 */
            WQ_ARMED    = 1;        /* 0x37162 (delay)         */
        } else {
            WQ_INIT_DONE = 1;       /* 0x37166 (delay)         */
        }
        return;
    }

    /* armed: drive the queued write */
    {
        uint8_t was_busy = WQ_BUSY;             /* 0x37168 snapshot */
        sub_37000_inline(WQ_PENDING);           /* bsr 0x37000      */
        if (E2_DONE == 1) {                     /* 0x3717E cmp/eq #1 */
            WQ_FLAG_D2 = 0;                     /* 0x37188           */
            if (was_busy) {
                WQ_BUSY     = 0;                /* 0x3718C           */
                WQ_PENDING  = 3;                /* 0x3718E           */
                update_e2_ram(3);               /* tail bra 0x36D0C  */
            } else {
                WQ_PENDING  = 0;                /* 0x371B4           */
                WQ_INIT_DONE = 1;               /* 0x371B6           */
                WQ_ARMED    = 0;                /* 0x371B8           */
            }
        }
    }
}
