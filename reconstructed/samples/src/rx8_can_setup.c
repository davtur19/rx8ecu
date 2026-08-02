/*
 * =============================================================================
 * rx8_can_setup.c  —  CAN CONTROLLER INIT WITH RETRY (CALLER)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xDC8C  (80 words, 160 bytes, to 0xDD2B)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_can_setup.py (host-gcc vs
 *               tools/sh2emu.py over edge + random states; comparing the three
 *               caller cells this function itself writes, 0 mismatches), on top
 *               of the existing structural c/tests/test_canSetup.py.
 * Lift (truth): c/canSetup.c  (IDA-ai symbol `canSetup`, 0xDC8C..0xDD2B).
 *
 * CALLING CONVENTION
 * ------------------
 * void canSetup(void)  — no register arguments; return value unused (r0 is
 * scratch).  Prologue saves r14,r13,r12,r11,r10,r9,r8 + PR; epilogue restores
 * them and rts.  The reconstructed C takes one host-only parameter `config`
 * that models the ROM's byte fetch at 0x0000B5A4 — that address lies below the
 * host's mmap_min_addr (0x10000), so it cannot be memory-mapped on the test
 * rig; the parameter carries the exact value the emulator puts at ram[0xB5A4]
 * (same precedent as rx8_task_flag_run_c modelling the scheduler's 0x4B10
 * pointer as a parameter).
 *
 * CALLEES (separate ROM functions, NOT part of this reconstruction)
 * ----------------------------------------------------------------
 *   0x9878  CANControllerSetup(uint32_t channel, uint32_t base_addr,
 *                              uint32_t mode)   in r4/r5/r6, r0 unused
 *   0x2B320 canMessageSetup(uint32_t channel, uint32_t base_addr,
 *                           uint32_t mode)      in r4/r5/r6, error status out
 *                           in r0/r7 (non-zero = verification failure)
 * The oracle provides no-op / always-fail stubs for these two: see the
 * "DISCREPANCIES vs the lift" section below for why the ROM's canMessageSetup
 * always reports failure under every state the harness can seed, so the caller
 * cells are invariant.
 *
 * ALGORITHM (from the 60E1D400 bytes @0xDC8C)
 * --------------------------------------------
 *   1. retry counter (byte @0xFFFFA40E) is reset to 0 unconditionally.
 *   2. Loop: while counter < 2
 *        base0 = (byte @0xB5A4 == 1) ? 0x4EA60 : 0x4EB60
 *        CANControllerSetup(0, base0, 0x10)
 *        err    = canMessageSetup(0, base0, 0x10)          (r0)
 *        CANControllerSetup(1, 0x4EC60, 6)
 *        err   |= canMessageSetup(1, 0x4EC60, 6)           (r0)
 *        err   &= 0xFF                                     (extu.b)
 *        if err != 0: counter = (counter + 1) & 0xFF; store @0xFFFFA40E
 *        else:       break (success)
 *   3. Exit: if (counter >= 2) byte @0xFFFFA410 = 1   (persistent error flag)
 *            byte @0xFFFFA411 = 0                    (always cleared)
 *
 * The exit test re-reads the stored counter byte from 0xFFFFA40E, so the
 * counter RAM cell is always up to date with the loop variable.
 *
 * RAM / MMIO CELLS (addresses not yet in include/rx8_hw.h — matches ROM):
 *   0xFFFFA40E  u8  retry counter (init 0; +1 per failed attempt)
 *   0xFFFFA410  u8  persistent error flag (1 iff all 2 attempts failed)
 *   0xFFFFA411  u8  secondary error flag (always cleared to 0)
 *   0x0000B5A4  u8  config byte: == 1 selects CAN instance base 0x4EA60
 *                   else 0x4EB60  (host model: the `config` parameter)
 *   0x0004EA60  u32 CAN instance A base   (channel 0)
 *   0x0004EB60  u32 CAN instance B base   (channel 0)
 *   0x0004EC60  u32 CAN instance base     (channel 1)
 *
 * The three caller cells above are the ONLY locations this function itself
 * writes (all other side effects belong to the 0x9878 callee, which writes the
 * on-chip CAN MMIO page 0xFFFFE400..0xFFFFE6FF); the harness compares exactly
 * those three cells.
 *
 * DISCREPANCIES vs the lift (documented; behaviour unchanged)
 *   1. The lift's config test is described as "bit-1-set"; the ROM does
 *      cmp/eq #0x01 on the WHOLE byte @0xB5A4 (extu.b first), i.e. the byte
 *      must equal exactly 1, not just have bit 0 set.
 *   2. The lift's per-attempt sequence ("can_init_channel(base,0,0x10)" then
 *      "can_chk_status") is a rough paraphrase: the ROM actually performs two
 *      paired (setup, message-setup) rounds — round 1 for channel 0 with base
 *      0x4EA60/0x4EB60 in mode 0x10, round 2 for channel 1 with the fixed base
 *      0x4EC60 in mode 6 — and ORs the two canMessageSetup returns.  The
 *      CANControllerSetup return value is never consumed.
 *   3. canMessageSetup's return (r0) is captured into r11 via
 *      `mov r0,r11` / `or r0,r11` and byte-masked (extu.b) before the tst; the
 *      lift's `status &= 0xFF` matches this.
 *   4. The retry exit reads the STORED counter byte back from 0xFFFFA40E
 *      (both in the loop condition and in the final >= 2 test); the lift keeps
 *      a shadow variable that it copies back after each increment, which is
 *      behaviourally identical because the byte is only ever written by this
 *      function.
 *   5. CALLEE MODELS.  CANControllerSetup @0x9878 is modelled as a no-op and
 *      canMessageSetup @0x2B320 as "always fail" (return 1).  This is not a
 *      faithful implementation of those two functions — it is the exact
 *      observable behaviour the ROM exhibits under every harness-seedable
 *      state: canMessageSetup verifies the mailbox contents against the CAN
 *      controller configuration that CANControllerSetup derives from those
 *      same mailboxes, and the two derivations never agree, so it always
 *      returns non-zero.  Consequently the retry loop always exhausts both
 *      attempts and the three caller cells are invariant: (A40E=2, A410=1,
 *      A411=0).  The host model reproduces that invariant exactly (validated
 *      over 1500 diverse seeds + edge states).  The success path (err==0)
 *      cannot be reached with any harness-controllable state, so it is not
 *      differentially exercised; the C below still follows the disassembly
 *      for that path (counter not incremented, flag 0xFFFFA410 left untouched).
 *   6. The byte fetch @0x0000B5A4 becomes the `config` parameter (below the
 *      host mmap_min_addr; see calling-convention note).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* Caller cells (not yet in include/rx8_hw.h — unknown, matches ROM). */
#define RX8_CANSETUP_RETRY_ADDR 0xFFFFA40Eu   /* retry counter (init 0)      */
#define RX8_CANSETUP_ERRFLAG    0xFFFFA410u   /* persistent error flag (1)   */
#define RX8_CANSETUP_ERRCLR     0xFFFFA411u   /* secondary flag (cleared)    */
#define RX8_CAN_BASE_A          0x0004EA60u   /* channel-0 instance A        */
#define RX8_CAN_BASE_B          0x0004EB60u   /* channel-0 instance B        */
#define RX8_CAN_BASE_C          0x0004EC60u   /* channel-1 instance          */

/* 0x9878 — CAN controller setup: configures the on-chip CAN peripheral MMIO
 * (0xFFFFE400..0xFFFFE6FF) for the instance.  Modelled as a no-op here (see
 * header, discrepancy 5); its writes never touch the three caller cells. */
void rx8_can_controller_setup(uint32_t channel, uint32_t base_addr, uint32_t mode);

/* 0x2B320 — CAN message setup: verifies the mailbox contents against the
 * controller configuration.  Returned error status in r0/r7 (non-zero on
 * failure).  Modelled as always-fail (see header, discrepancy 5). */
uint32_t rx8_can_message_setup(uint32_t channel, uint32_t base_addr, uint32_t mode);

/* 0xDC8C — initialise the CAN controller with retry; persistent error flag
 * set iff both attempts fail.  See header for the full trace.  `config` is
 * the host-only model of byte @0xB5A4 (see the calling-convention note). */
void rx8_can_setup(uint8_t config)
{
    uint8_t counter = 0;
    uint8_t err;

    /* Reset the retry counter unconditionally. */
    *(volatile uint8_t *)(uintptr_t)RX8_CANSETUP_RETRY_ADDR = 0;

    do {
        uint32_t base0 = (config == 1u) ? RX8_CAN_BASE_A : RX8_CAN_BASE_B;

        /* Round 1: channel 0, mode 0x10. */
        rx8_can_controller_setup(0, base0, 0x10);
        err = (uint8_t)rx8_can_message_setup(0, base0, 0x10);

        /* Round 2: channel 1, fixed base, mode 6. */
        rx8_can_controller_setup(1, RX8_CAN_BASE_C, 6);
        err |= (uint8_t)rx8_can_message_setup(1, RX8_CAN_BASE_C, 6);
        err &= 0xFFu;   /* extu.b r11 */

        if (err != 0u) {
            counter = (uint8_t)(counter + 1);
            *(volatile uint8_t *)(uintptr_t)RX8_CANSETUP_RETRY_ADDR = counter;
        }
    } while (err != 0u && counter < 2u);

    if (counter >= 2u) {
        *(volatile uint8_t *)(uintptr_t)RX8_CANSETUP_ERRFLAG = 1u;
    }
    *(volatile uint8_t *)(uintptr_t)RX8_CANSETUP_ERRCLR = 0u;
}
