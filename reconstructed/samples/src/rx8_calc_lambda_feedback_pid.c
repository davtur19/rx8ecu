/*
 * =============================================================================
 * rx8_calc_lambda_feedback_pid.c  —  CLOSED-LOOP LAMBDA FEEDBACK (TASK DISPATCH)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x11A34  (104 bytes: 0x11A34..0x11A9B)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_calc_lambda_feedback_pid.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random vectors;
 *               the 17 dispatched addresses, their exact order, the tail-call
 *               boundary and every observable RAM byte compared bit-exactly;
 *               0 mismatches).
 * Lift (truth): c/calc_lambda_feedback_pid.c  (calc_lambda_feedback_pid @ 0x11A34)
 *
 * WHAT THIS FUNCTION IS
 * ---------------------
 * Despite its name this "PID" is NOT a single Kp/Ki/Kd controller.  It is a
 * sequential task dispatcher of the closed-loop fuel (lambda) subsystem: it
 * jsr's 16 sub-functions in a fixed order and then TAIL-JMP's (not jsr's) into
 * the 17th, 0x16E6A.  The wrapper itself reads/writes NO RAM and has no ABI
 * arguments or return value (void) — its whole effect is the dispatch itself.
 * The 17 callees are large verified/unverified subsystem blocks (the FP-math
 * heavy ones — 0x1ACDE, 0x17F7C, 0x32A9C, 0x3A1CC, 0x2204C — implement the
 * trimming/feedback maths on the shared verified leaves 0x23B0/0x23E4/0x2404/
 * 0x2460/0x2478/0x2068/0x20DC); they are stubbed in this sample (see below).
 *
 * ROM bytes @ 0x11A34 (verified by disassembly; registers as loaded):
 *
 *     4F22  sts.l pr,@-r15              ; push our return address (r15 = stack)
 *     D38A  mov.l @(0x14,PC),r3         ; dispatch #1 : 0x1ACDE
 *     430B  jsr   @r3                   ;   (delay slot: nop)
 *     D289  mov.l @(0x14,PC),r2         ; dispatch #2 : 0x2F51E
 *     420B  jsr   @r2
 *     ...   14 more mov.l+jsr pairs, alternating r3/r2
 *     D382  mov.l @(0x14,PC),r3         ; dispatch #16 : 0x67482
 *     420B  jsr   @r2
 *     D382  mov.l @(0x14,PC),r3         ; dispatch #17 : 0x16E6A
 *     432B  jmp   @r3                   ; TAIL jmp (NOT jsr!)
 *     4F26  lds.l @r15+,pr              ;   (delay slot: pop PR, restore r15)
 *
 * The 17 targets are the literal pool words @0x11C60..0x11CA0:
 *
 *    #1  0x1ACDE  lambda-feedback core #1  (644 i, 247 FPU)  O2 conditioning
 *    #2  0x2F51E  status/bank trimming chain (216 i, 5 FPU)
 *    #3  0x3A1CC  secondary lambda math      (872 i, 84 FPU)
 *    #4  0x2204C  trim/learn chain           (640 i, 32 FPU)
 *    #5  0x1490E  no-FPU state updates       (161 i)
 *    #6  0x2766A  sensor status chain        (115 i, 3 FPU)
 *    #7  0x16AA8  fuel-cut / transient logic (278 i, 21 FPU)
 *    #8  0x3FCE0  O2 sensor conditioning     (108 i, 19 FPU)
 *    #9  0x32A9C  fueling trim core          (650 i, 92 FPU)
 *    #10 0x17F7C  lambda-feedback core #2    (611 i, 143 FPU)
 *    #11 0x225A2  closed-loop enable logic   (464 i, 8 FPU)
 *    #12 0x35B6A  status block               (167 i, 9 FPU)
 *    #13 0x35B96  status block               (145 i, 8 FPU)
 *    #14 0x2971C  DTC/fault chain            (646 i, 0 FPU)
 *    #15 0x2B0D6  O2 heater control          (610 i, 9 FPU)
 *    #16 0x67482  wrapper -> 0x60DB4, stores u16 to RAM[0xFFFFD96C]
 *    #17 0x16E6A  status latch (23 i)        — reached via TAIL jmp @r3
 *
 * TAIL-CALL SUBTLETY (the one lift nuance made explicit):
 *   The 17th dispatch is `jmp @r3` with `lds.l @r15+,pr` in the delay slot.
 *   PR is therefore NOT overwritten by a call; the pop restores the return
 *   address we pushed in the prologue, so 0x16E6A's `rts` returns DIRECTLY to
 *   calc_lambda_feedback_pid's caller (never back into this wrapper — which
 *   has no epilogue/rts of its own).  The harness pins this: after the call
 *   r15 is back to 0xFFFFDF00 and the pushed stack word at 0xFFFFDEFC still
 *   holds the caller's PR.  The reconstructed C models it as a plain trailing
 *   call — behaviourally identical on the host.
 *
 * CALLING CONVENTION
 * ------------------
 *   void rx8_calc_lambda_feedback_pid(void) — RTOS task wrapper, no arguments,
 *   void return.  No registers are read on entry.  The only register state it
 *   touches is PR (pushed/popped around the tail call) and r15 (the stack
 *   frame: PR word at 0xFFFFDEFC..0xFFFFDEFF under r15 = 0xFFFFDF00).
 *
 * RAM CELLS READ/WRITTEN
 * ----------------------
 *   By the wrapper itself: NONE (no memory traffic at all except the stack
 *   PR push at 0xFFFFDEFC and the pop in the tail-call delay slot).
 *
 *   By the CALLEES (real ROM blocks, NOT yet individually reconstructed):
 *   the whole closed-loop lambda RAM set.  THIS SAMPLE stubs the callees;
 *   the stub contract below is test-rig scaffolding that shadows the real
 *   subsystems while preserving the wrapper's observable dispatch behaviour:
 *
 *     RAM8[0xFFFFD130]  trace length byte (the shared "next slot" counter)
 *     RAM8[0xFFFFD140..] trace buffer, 24 bytes pre-seeded; each callee stub
 *                        appends its dispatch slot index (0..16) here.
 *
 *   These two cells are NOT part of the ROM's real RAM map — they are an
 *   equivalence-channel between the emulator overlay stubs and the host
 *   oracle stubs (see harness_calc_lambda_feedback_pid.py).  The harness
 *   compares the whole seeded span (0xFFFFD12F..0xFFFFD163, 53 bytes)
 *   bit-exactly after every call, which pins the dispatch ORDER, the CALL
 *   COUNT (the final len byte must be 17 past its pre-state) and every
 *   store width (byte stores; sign-extended index from `mov.b @Rm,Rn`).
 *
 * CALIBRATION TABLES
 * ------------------
 *   None — the wrapper only dispatches; its literal pool (0x11C60..0x11CA0)
 *   holds the 17 addresses, not data.
 *
 * INTERNAL CALLEES (17, fixed addresses)
 * --------------------------------------
 *   rx8_lambda_core_1acde    @ 0x1ACDE      rx8_lambda_fueling_32a9c @ 0x32A9C
 *   rx8_lambda_chain_2f51e   @ 0x2F51E      rx8_lambda_core_17f7c   @ 0x17F7C
 *   rx8_lambda_core_3a1cc    @ 0x3A1CC      rx8_lambda_enable_225a2 @ 0x225A2
 *   rx8_lambda_trim_2204c    @ 0x2204C      rx8_lambda_status_35b6a @ 0x35B6A
 *   rx8_lambda_state_1490e   @ 0x1490E      rx8_lambda_status_35b96 @ 0x35B96
 *   rx8_lambda_sensor_2766a  @ 0x2766A      rx8_lambda_dtc_2971c    @ 0x2971C
 *   rx8_lambda_transient_16aa8 @ 0x16AA8    rx8_lambda_heater_2b0d6 @ 0x2B0D6
 *   rx8_lambda_o2_3fce0      @ 0x3FCE0      rx8_lambda_wrap_67482   @ 0x67482
 *   rx8_lambda_latch_16e6a   @ 0x16E6A      (TAIL jmp, not jsr)
 *
 *   Each callee begins with the RTOS task boundary pair 0x3920 (SR save) /
 *   0x3934 (SR restore) documented in RTOS_SUBSYSTEM.md.  On the emulator
 *   side the harness installs SH-2 stub code AT these ROM addresses in the
 *   sparse RAM overlay (which takes fetch precedence over ROM), so the real
 *   ROM bytes of the wrapper still drive the dispatch while each target runs
 *   an equivalent "append slot index" stub.  The host oracle defines the
 *   matching C stubs (tests/oracle_calc_lambda_feedback_pid.c) — the same
 *   convention as oracle_crank_sensor_init.c stubbing crank_mode_switch.
 *
 * LIFT-VS-ROM DISCREPANCIES FIXED
 * -------------------------------
 *   NONE.  The lift (c/calc_lambda_feedback_pid.c) dispatches the same 16
 *   addresses in the same order and ends with the 17th (0x16E6A) — matching
 *   the ROM's literal pool and the jmp tail-call exactly.  The only notes
 *   recorded here (not discrepancies): (a) the 17th dispatch is a tail
 *   `jmp @r3` + delay-slot `lds.l @r15+,pr`, modelled as a plain trailing
 *   call in C; (b) the harness verifies the real subsystems' addresses and
 *   order, but substitutes stubs for their (as-yet-unreconstructed) bodies.
 * =============================================================================
 */
#include <stdint.h>

/* ---- the 17 dispatched subsystem blocks (ROM addresses fixed, see above).
 * Each is defined by the test rig on the host (tests/oracle_calc_lambda_
 * feedback_pid.c) exactly as the RAM-overlay stubs the emulator harness
 * installs at the real ROM addresses; on the target they are the real ROM
 * bytes of the closed-loop lambda subsystem. ---- */
extern void rx8_lambda_core_1acde(void);      /* @ 0x1ACDE  O2 conditioning  */
extern void rx8_lambda_chain_2f51e(void);     /* @ 0x2F51E  trim chain       */
extern void rx8_lambda_core_3a1cc(void);      /* @ 0x3A1CC  secondary lambda */
extern void rx8_lambda_trim_2204c(void);      /* @ 0x2204C  trim/learn chain */
extern void rx8_lambda_state_1490e(void);     /* @ 0x1490E  state updates    */
extern void rx8_lambda_sensor_2766a(void);    /* @ 0x2766A  sensor status    */
extern void rx8_lambda_transient_16aa8(void); /* @ 0x16AA8  transient logic  */
extern void rx8_lambda_o2_3fce0(void);        /* @ 0x3FCE0  O2 conditioning  */
extern void rx8_lambda_fueling_32a9c(void);   /* @ 0x32A9C  fueling trim     */
extern void rx8_lambda_core_17f7c(void);      /* @ 0x17F7C  lambda core #2   */
extern void rx8_lambda_enable_225a2(void);    /* @ 0x225A2  closed-loop gate */
extern void rx8_lambda_status_35b6a(void);    /* @ 0x35B6A  status block     */
extern void rx8_lambda_status_35b96(void);    /* @ 0x35B96  status block     */
extern void rx8_lambda_dtc_2971c(void);       /* @ 0x2971C  DTC/fault chain  */
extern void rx8_lambda_heater_2b0d6(void);    /* @ 0x2B0D6  O2 heater        */
extern void rx8_lambda_wrap_67482(void);      /* @ 0x67482  -> 0x60DB4 store */
extern void rx8_lambda_latch_16e6a(void);     /* @ 0x16E6A  status latch     */

/* 0x11A34 — run one closed-loop lambda feedback pass (16 jsr'd subsystem
 * tasks + 1 tail-jmp'd status latch, in the ROM's fixed order). */
void rx8_calc_lambda_feedback_pid(void)
{
    rx8_lambda_core_1acde();
    rx8_lambda_chain_2f51e();
    rx8_lambda_core_3a1cc();
    rx8_lambda_trim_2204c();
    rx8_lambda_state_1490e();
    rx8_lambda_sensor_2766a();
    rx8_lambda_transient_16aa8();
    rx8_lambda_o2_3fce0();
    rx8_lambda_fueling_32a9c();
    rx8_lambda_core_17f7c();
    rx8_lambda_enable_225a2();
    rx8_lambda_status_35b6a();
    rx8_lambda_status_35b96();
    rx8_lambda_dtc_2971c();
    rx8_lambda_heater_2b0d6();
    rx8_lambda_wrap_67482();
    rx8_lambda_latch_16e6a();   /* ROM: tail `jmp @r3` — returns to OUR caller */
}
