/*
 * =============================================================================
 * rx8_immo_state_machine_360e8.c  —  IMMOBILIZER STATE-MACHINE DISPATCHER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x360E8  (0x360E8..0x361C0 incl. the literal pools)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_immo_state_machine_360e8.py
 *               (host-gcc vs tools/sh2emu.py over edge + random initial RAM
 *               states; bit-exact RAM side effects AND the handler-dispatch
 *               boundary markers; 0 mismatches).
 * Lift (truth): c/ImmoStateMachine.c  (ImmoStateMachine_360E8 @ 0x360E8)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Main immobilizer state-machine dispatcher: it reads the immo state byte
 * 0xFFFFC28E and routes to the per-state handlers (challenge phase, key
 * verification, bad-state latch).  It is a `void f(void)` leaf entered via the
 * normal ABI; its observable effects are the on-chip RAM cells it writes
 * directly plus the handler calls it makes.  The handler bodies are the
 * separate lifted functions (0x365B8 / 0x369B8 / 0x263C8 / 0x3664E / 0x35F92,
 * each already verified by its own sample); this sample models ONLY the
 * dispatch selection and declares those handlers, which the test rig stubs at
 * the call boundary (same rig as harness_crank_sensor_init.py).
 *
 * DISASSEMBLY (60E1D400.bin @ 0x360E8; condensed, exact branch targets)
 * ---------------------------------------------------------------------
 *     r5 = 0xFFFFC28E;  state = *(u8*)r5  (mov.b, extu.b)
 *     state == 1 (0x360F2 cmp/eq #1):
 *        r2 = 0xFFFFC291;  sub = *(u8*)r2;  r14 = 0
 *        sub == 1: bsr 0x365B8   ImmoBadStateSet (r4 = sub = 1)
 *                  *(u8*)0xFFFFC294 = 0
 *                  bsr 0x369B8   CAN msg queue (delay-slot r4 = 1)
 *                  *(u8*)0xFFFFC29A = 1
 *        sub == 3: *(u8*)0xFFFFC28D = 0
 *        sub == 2: r6 = 0xFFFFC2F2;  v = *(u8*)r6
 *                  if (v > 0 && v <= 2)             ; 0x3615C cmp/pl, 0x36164 cmp/gt
 *                     *(u8*)0xFFFFC2F2 = v - 1      ; (add #0xFF == dec, byte store)
 *                     *(u8*)0xFFFFC29F = 1
 *                     jsr @0x263C8  setImmoLight (r4 = 1)
 *                     *(u8*)0xFFFFC240 = 1
 *                     *(u8*)0xFFFFC298 = 0
 *                  else:
 *                     jsr @0x263C8  setImmoLight (r4 = 0)
 *                     *(u8*)0xFFFFC240 = 0
 *                  *(u16*)0xFFFFC286 = 0x02EE       ; seed refresh timer (750)
 *                  bsr 0x3664E   ImmoGetSeed
 *                  bsr 0x369B8   CAN msg queue (delay-slot r4 = 0x07)
 *                  *(u8*)0xFFFFC28D = 2
 *     state == 3: tail `bra 0x35F92`  ImmoWaitForKey (PR never pushed)
 *     else       : *(u8*)0xFFFFC28E = 5
 *     epilogue @0x361BC: lds.l pr / rts / mov.l r14  (stack restored)
 *
 * DISCREPANCIES vs c/ImmoStateMachine.c (documented, corrected here)
 * ------------------------------------------------------------------
 *  1. The lift writes CAN_TX_DATA (c/eeprom_immo.h macro = 0x0000C240), but
 *     the ROM reaches the CAN TX byte through `mov.w @(0x3621C,pc),r3` which
 *     SIGN-EXTENDS the 16-bit literal 0xC240 to the effective address
 *     0xFFFFC240.  This sample writes the CPU's actual address 0xFFFFC240
 *     (same correction as the verified ImmoBadStateSet / ImmoGoodStateSet
 *     samples).  The write is a byte (`mov.b`), so neighbour 0xFFFFC241
 *     (CAN_TX_REQ) is untouched — sentinel-pinned by the harness.
 *  2. The `v > 0 && v <= 2` guard is a SIGNED pair (cmp/pl, then cmp/gt #2)
 *     on the zero-extended byte v.  Signed and unsigned tests select the same
 *     set {1,2} — 0x80..0xFF fails signed `> 0` and unsigned `<= 2` alike —
 *     so the lift's uint8_t comparison is behaviourally identical; noted here
 *     for faithfulness, no change needed.
 *  3. state == 3 is a `bra` tail-jump (0x361B4), not a `jsr`: PR is restored
 *     then ImmoWaitForKey runs as if called by the dispatcher's caller.  The
 *     lift's plain call is the correct host model; the harness pins the
 *     0x35F92 boundary and its r4 = state = 3 argument.
 *
 * CALLING CONVENTION
 * ------------------
 * void f(void): no arguments in r4-r7/fr4-fr7, no register result (r0 is
 * scratch at exit).  Handler bodies are separate functions; on the host the
 * test rig substitutes stubs that only record the dispatch, on the target
 * they are the real ROM functions.
 * =============================================================================
 */
#include <stdint.h>

/* ---- Dispatcher-owned immobilizer cells (on-chip RAM @ 0xFFFFCxxx) ---- */
#define IMMO_STATE_BYTE      (*(volatile uint8_t  *)0xFFFFC28E)  /* state */
#define IMMO_SUBSTATE        (*(volatile uint8_t  *)0xFFFFC291)  /* ImmoGetCANData result */
#define IMMO_RESP_BYTE       (*(volatile uint8_t  *)0xFFFFC294)  /* challenge response */
#define IMMO_GOODSTATE_FLAG  (*(volatile uint8_t  *)0xFFFFC29A)
#define IMMO_STATE_CODE      (*(volatile uint8_t  *)0xFFFFC28D)  /* result code */
#define E2_WORK_INDEX30      (*(volatile uint8_t  *)0xFFFFC2F2)  /* EEPROM[0x1E] copy */
#define IMMO_SEED_ACTIVE     (*(volatile uint8_t  *)0xFFFFC29F)
#define CAN_TX_DATA          (*(volatile uint8_t  *)0xFFFFC240)  /* 0xC240 sign-extended */
#define IMMO_GOODSTATE_CTR   (*(volatile uint8_t  *)0xFFFFC298)
#define IMMO_SEED_TIMER      (*(volatile uint16_t *)0xFFFFC286)  /* seed refresh timer */

/* ---- Handler bodies: separate lifted functions (stubbed by the rig) ----
 * rx8_immo_bad_state_set  0x365B8  ImmoBadStateSet.c  (verified sample)
 * rx8_immo_msg_queue      0x369B8  message_queue_state_dispatcher_369B8.c
 * rx8_immo_set_light      0x263C8  setImmoLight.c     (r4 = on/off)
 * rx8_immo_get_seed       0x3664E  ImmoGetSeed.c      (verified sample)
 * rx8_immo_wait_for_key   0x35F92  ImmoWaitForKey.c   (tail `bra`, r4 = 3)
 */
extern void rx8_immo_bad_state_set(void);
extern void rx8_immo_msg_queue(uint8_t cmd);
extern void rx8_immo_set_light(uint8_t on);
extern void rx8_immo_get_seed(void);
extern void rx8_immo_wait_for_key(void);

/* 0x360E8 — immobilizer state-machine dispatcher (see header). */
void rx8_immo_state_machine_360e8(void)
{
    uint8_t state = IMMO_STATE_BYTE;             /* 0x360EE mov.b @r5,r4 */

    if (state == 1) {                            /* 0x360F2 cmp/eq #1 */
        uint8_t sub = IMMO_SUBSTATE;             /* 0x360FC mov.b @r2,r4 */
        if (sub == 1) {                          /* 0x36100 cmp/eq #1 */
            rx8_immo_bad_state_set();            /* bsr 0x365B8, r4 = 1  */
            IMMO_RESP_BYTE = 0;                  /* 0x3610C mov.b r14(0) */
            rx8_immo_msg_queue(0x01);            /* bsr 0x369B8, r4 = 1  */
            IMMO_GOODSTATE_FLAG = 1;             /* 0x36118 mov.b r3(1)  */
        } else if (sub == 3) {                   /* 0x3611C cmp/eq #3 */
            IMMO_STATE_CODE = 0;                 /* 0x36126 mov.b r14(0) */
        } else if (sub == 2) {                   /* 0x36150 cmp/eq #2 */
            uint8_t v = E2_WORK_INDEX30;         /* 0x36158 mov.b @r6,r4 */
            if (v > 0 && v <= 2) {               /* cmp/pl + cmp/gt (see header) */
                E2_WORK_INDEX30 = (uint8_t)(v - 1);  /* 0x36172 add #0xFF */
                IMMO_SEED_ACTIVE = 1;            /* 0x36174 mov.b r3(1)  */
                rx8_immo_set_light(1);           /* jsr @0x263C8, r4 = 1 */
                CAN_TX_DATA = 1;                 /* 0x36182 mov.b r2(1)  */
                IMMO_GOODSTATE_CTR = 0;          /* 0x36188 mov.b r14(0) */
            } else {
                rx8_immo_set_light(0);           /* jsr @0x263C8, r4 = 0 */
                CAN_TX_DATA = 0;                 /* 0x36194 mov.b r2(0)  */
            }
            IMMO_SEED_TIMER = 0x02EE;            /* 0x3619C mov.w r1     */
            rx8_immo_get_seed();                 /* bsr 0x3664E          */
            rx8_immo_msg_queue(0x07);            /* bsr 0x369B8, r4 = 7  */
            IMMO_STATE_CODE = 2;                 /* 0x361A8 mov.b r3(2)  */
        }
    } else if (state == 3) {                     /* 0x361AC cmp/eq #3 */
        rx8_immo_wait_for_key();                 /* ROM: tail `bra 0x35F92`,
                                                    r4 = state = 3        */
    } else {
        IMMO_STATE_BYTE = 5;                     /* 0x361BA mov.b r2(5)  */
    }
}
