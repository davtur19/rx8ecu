# Findings

## CORRECTION: fcmp/gt operand order (old "emulator bug fix" note was FALSE)
- `tools/sh2emu.py` `fcmp/gt`: T = 1 iff **FRn > FRm** — ALWAYS correct (matches Renesas SH-2E manual, Ghidra SuperH4 sleigh, QEMU sh4
  translate.c). The recorded "bug fix" was NEVER made; the old note described the opposite of the hardware.
- Real bug = test/C-model branch inversion in `calc_lambda_integration_time` (0x1418C): `fcmp/gt fr2,fr3`, fr3=2.5 (threshold), fr2=signal →
  T=(2.5>signal); `bt` → countdown when signal<2.5, fall-through → reload to 7 when signal>=2.5. Fixed 2026-07-31: test_o2_lambda.py +
  o2_lambda_subsystem.c.

## On‑chip RAM Address Sign‑Extension
- `mov.w @(disp,PC),Rn` sign-extends the 16-bit loaded value; addresses >=0x8000 (bit 15 set) become 0xFFFFxxxx. Many on-chip RAM variables
  (0xA760..0xB5AC range) need this.
- **Test pattern:** always use `0xFFFFxxxx` in test RAM setup for addresses with bit 15 set.

## Test Suite: 11/11 Passing (snapshot)
- test_getRearO2Voltage, test_write_o2_sensor_trim, test_read_o2_sensor_voltage_trim, test_calc_lambda_integration_time,
  test_calc_closed_loop_fuel_status_basic.

## Track-A Verification (2026-07-31) — 8 functions, emulator + C host tests
- Emulator: dtc_data_read_60F58@0x60F58, shift_right_8_r0@0x467A, sentinel_equality_check_5687A@0x5687A (formerly least_square_0x5687A),
  task_flag_run_C@0x35EE, memcpy_bytewise_unroll4@0x42B0.
- C host: div32_signed@0x3FE8, mod32_signed@0x4144, checkFloatValidity@0x46CC.

## Track-B Verification (2026-07-31, session 6) — 16 functions (ROM emulator, sh2emu.py)
All verified, 0 mismatches; per-function detail + C lifts (c/3dLookup.c, c/ssvControl.c, c/vis_intake_control.c, c/vfad_control_35BBC.c,
c/pressure_delta_monitor_1AED2.c, c/alternating_sensor_sm_5D34C.c) in docs/subsystems/AUXILIARY_CONTROL_SUBSYSTEM.md.
- Verified: purge_valve_control@0xF534 (+sub/sub2/sub3 @0xF544/0xF5B4/0xF5DC), calc_fan1_control@0x303A6, cooling_fan_control@0x17DCC,
  radiator_fan_relay_write@0x259C0, pressure_delta_monitor_1AED2@0x1AED2 (formerly aux_fan_control_task), alternating_sensor_sm_08@0x5D3E8,
  ssvControl@0x225C8, vis_intake_control@0x23718, 3dLookup@0x20DC (type=8 u16 path), alternating_sensor_sm@0x5D800 (2nd inst) / @0x5D34C
  (3rd inst), vfad_control_35BBC@0x35BBC, port helpers (0x3EE58/0x3EE68/0x3920).
- 3dLookup (0x20DC): 28-byte descriptor (+0 count_x u16, +2 count_y u16, +4 axis_x ptr, +8 axis_y ptr, +12 values ptr, +16 type, +20 scale,
  +24 offset). Type jump table @0x210C: [0x253C f32, 0x25C8 u8, 0x25F4 u16, 0x256C s8, 0x2598 s16]; verified type=8 (u16) and type=16.
  axis_search @0x2624 clamps both ends (x<axis[0] → (0,0.0), x>=axis[last] → (last,0.0)); all arithmetic must be f32.
- vis_intake_control (0x23718): 3D lookup via RAM8[B33C/B33D/B33E] → desc 0x6AC60/0x6AC7C/0x6AC98/0x6ACB4 (all 21x18, type=8 u16, scale
  1/327.68); clamp [0,84] via 0x2404 (fpu_compare_and_select = clamp, NOT a comparator); 12-deep rolling history @RAM[FFFFB408..FFFFB43C];
  counter idx RAM8[B45C]=0 stock (cal byte 0x73F68==1); B5C8 path dead.
- ssvControl (0x225C8): hysteresis on>=200/off<197 (ROM 0x72F74=200.0, 0x226D4=-3.0); counter RAM16[B322] reload 188 (ROM16 0x72F72) on mode
  transition else decrement; enable = BF39==1 || (mode==0 && cnt>0 && cmd==0); sets RAM16[F754] bit 0x80; stores mode to RAM[B325].
- alternating_sensor_sm_08 (0x5D3E8): mask=RAM8[0x6021C], ptr=RAM32[0x60220]; input==1 && counter==7 → RAM[D387]=RAM16[D352]>>8; out==0 →
  ret=r4; out in {5,7} → ret=1 if RAM[D387]==1 else 0; writes RAM[D354] to *ptr. _5D800 (2nd inst): base 0x60254, mask=RAM8[0x6025C] (ROM
  0xC0), ptr=RAM32[0x60260], magic 0x17C8 (ROM 0x5D8BC), flag RAM8[D38F] — `r6 += 0x1E` in the bf/s delay slot executes in BOTH branches →
  out==0 write always lands on D38F; r6 default 0xFFFFD371 never written. _5D34C (3rd inst, symbol diagMeteringPumpPositionControl,
  unconfirmed): base 0x60204, mask=RAM8[0x6020C] (ROM 0x40), ptr=RAM32[0x60210], magic 0x172D (ROM 0x5D448), latch RAM8[D385]; RAW variant
  (stores raw r4, not (r4==1), returns raw D385).
- vfad_control_35BBC (0x35BBC): stock VFAD solenoid control, status word F754 bit 0x400 (mod's CAN_EmitLaunchStatus @0x57BE8 reads it as
  "launch active"). Hysteresis: cmd = 1 if x>=5250.0 (ROM 0x7A5AC), 0 if x<5062.0 (=5250-188, ROM 0x7A5B0), hold RAM8[C234] in band;
  sm(0x5D800) → RAM8[C234] + F754 bit 0x400 (via 0x4BBC). 2026-08-01 audit: "launch_status_bit0400" was a mod-era misnomer — this IS stock
  VFAD solenoid control; stock has NO launch control.
- pressure_delta_monitor_1AED2 (0x1AED2, formerly aux_fan_control_task): boost filter RAM[C008] (0.7, eps 1e-5, firstOrderFilter @0x32F42) →
  delta RAM[BD3C]=(C008-BD40)*15.625 (@0x2DD6E) → error filter RAM[BD38] (0.5, 1e-5, @0x2DD88) → fixed 6-copy float swap (@0x344FE) →
  pressure hysteresis RAM[B5B8] (>=7000 flag1, <6500 flag0, thresholds ROM 0x7A18C/0x7A190) → flag transition writer (@0xC2E6: A384=0xFF,
  A385=0, A324=0, A38C=flag on change only).

## SH-2 Division
- Signed 32-bit division uses div0s/div1 step algorithm producing C99-style truncating-toward-zero division; `dividend / divisor` in C is
  the correct semantic lift.
- No hardware divide instruction — software 32-iteration loop.
- INT32_MIN / -1: SH-2 returns INT32_MIN (wrapping); C has undefined behavior.

## Hardware Register Writes in C Lifts
- Several verified functions write diagnostic codes to 0xFFFF7304; writes are commented out in C lifts for host compilation (would
  segfault). Emulator tests run the actual ROM bytes and validate them.

## Emulator gaps (sh2emu.py)
- `0x440E` `ldc r4,SR` — **implemented** (sh2emu.py decodes the 0x4n0E family as `ldc Rn,SR`, SR ← r4). Used as the rts delay slot in 0x3920
  and 0x3934; delay path sets SR from r4 (no memory write). Verified: return values unaffected (0x3920 always returns sr & 0xF0 = 0xF0).

## Remaining Analysis Targets
- `omp_control_task_1825E` (0x1825E) — OMP/waveform control task (756 B) — **LIFTED + emulator-verified** (c/omp_control_task_1825E.c,
  test_omp_control_task_1825E.py, 150000+ inputs, 0 mismatches). Call chain (session 6): 0x1825E → {0x3EE58*, 0x3ED3C, 0x2478
  (addSaturate8Bit), 0x18860 (omp_waveform_state_machine_18860), 0x189EE (rotor_sync_position_detector), 0x18C08 (omp_diag_rotor_18C08),
  0x18C5C (waveform_state_transition), 0x18C6C (omp_wave_reload_18C6C)}; those → {0x18552 (omp_stepper_waveform_driver), 0x9668, 0x3F050 →
  0x3ED7C/0x3EE68/0x60D54/0x2620E, 0x3ED3C → 0x3920*/0x3934 → 0x3DB0 → 0x35EE/0x3BF4}. * = verified this session. Reads RAM cluster
  A968..A98B + 9ECD bit2 + CD06 + 78E35/36/37; writes ports 0xFFFF8078/807A/807C via complementary-encoded helpers (0x3EE58/0x3EE68: v =
  (b<<8)|~b).
- `exhaust_oxygen_control_19480` (0x19480) — heater/sensor state machine — **✓ verified** (test_exhaust_oxygen_control_19480.py, commit
  14b0388, 0 mismatch).
- `calc_secondary_o2_trim` (0x1321C) — **✓ verified** (test_calc_secondary_o2_trim_1321C.py, commit e8192e7, 0 mismatch).
- `calc_lambda_feedback_pid` (0x11A34) — serial sub‑call chain (14+ functions) — **✓ verified** (test_calc_lambda_feedback_pid_11A34.py,
  commit e8192e7, 0 mismatch).
- `calc_fuel_trim_correction_map` (0x136F0), `calc_fuel_trims_adaptive` (0x117B4) — **✓ verified** (test_calc_fuel_trim_corr_map_136F0.py,
  commit e8192e7; test_calc_fuel_trims_adaptive_117B4.py, commit 14b0388).
- `consistencyCheck` (0x3A28) — **LIFTED + differential-verified** (c/consistencyCheck.c; test_consistency_check_3A28.py, 25000 random
  inputs, 0 mismatches, exit 0). Signature from disasm: r4 = exception control block, r5 = exc-number byte (sign-extended); table =
  u32@(ctrl+0x20), entry = table + s8(exc)*8, buf = u32@(entry+4); path A (c0==c1): buf[0]=0xFFFF, flags byte @(0xFFFF72E0+ (s8(exc)>>3)) &=
  ROM mask @0x3D50; path B (c0!=c1): buf[0]=entry[0] if c0==entry[1] else c0+1, on match writes u16 error code @(ctrl+6) from
  0xFFFF7234[buf0]. Return 1 when exc matches ctrl[0] after handler call (0x3C80), else 0.
- `atu_fpu_control_wrapper` (0x70AC) — **LIFT + differential-verified** (c/atu_fpu_control_wrapper.c; test_atu_fpu_control_wrapper_70AC.py,
  25000 random inputs, 0 mismatches, exit 0). No args; sub-call chain runs real ROM: 0x2054 setSR_PARAM → SR=max(SR&0xF0,0xE0) & save
  SR&0xF0; 0x4BBC bit OR 0x0100 into u16@0xFFFFF74E; 0x2064 loadStatusRegister_ADDR restores SR. Net: RAM16[0xFFFFF74E] |= 0x0100, SR_out =
  SR_in & 0xF0, r15/pr balanced.
- `task_full_context_save` (0x3BF4) — **context-save write path bit-exact traced** (test_task_full_context_save_3BF4.py, 2500 random tasks,
  0 mismatches, exit 0). Prologue saves to @-r15 (start SP 0xFFFFDF00): R5→0xFFFFDEFC, PR→0xFFFFDEF8, pad→0xFFFFDEF4, R8→0xFFFFDEF0,
  R9→0xFFFFDEEC, R10→0xFFFFDEE8, R11→0xFFFFDEE4, R12→0xFFFFDEE0, GBR→0xFFFFDEDC, R13→0xFFFFDED8, MACH→0xFFFFDED4, R14→0xFFFFDED0,
  MACL→0xFFFFDECC (non-FPU saved_sp). If task->type==4: FR12→0xFFFFDEC8, FR13→0xFFFFDEC4, FR14→0xFFFFDEC0, FR15→0xFFFFDEBC (FPU saved_sp).
  Then *status_ptr(=u32@(desc+4)) = 4 and tcb[0x0C] = saved_sp; bra 0x3C68 (schedule tail patched to rts;nop, same as os_context_switch
  0x3DB0 test). PR on stack = entry PR (SENT).
- **0x11540 = main dispatch TABLE (not a function)** — 24 big-endian function pointers (first: 0x2F418, 0x1A832, 0x1A840, 0x5AA5C, 0x5AADE,
  ...); disassembler misreads the table as code. Table + pointed-to functions pinned in test_can_packers.py (commit a7fc6d5, 3013 vectors, 0
  mismatch). Row closed as data (addr_cov2.tsv).
- **SH-2 delay-slot idiom (OBD CAN-TX builders)** — the mov.b/w r0,@Rdisp after each jsr executes BEFORE the call, so every store captures
  the PREVIOUS getter's return value. Explains the 8-byte buffer layout of getOBDCANTXVars1 @0x4C8C2 (0xFFFFCEAC: [0]=getEngineLoadOBD,
  [1]=0 stb 0x55E14, [2]=IAT, [3]=MAF, [4]=RPM, [5]=SPEED, [6]=0, [7]=0) and getOBDCANTXVars2 @0x4C9C0 (0xFFFFCEC0: [0]=0, [1]=0, [2]=STFT,
  [3]=LTFT, [4:6]=throttle u16 BE, [6]=getCommandedLambdaOBD, [7]=sub_55FA6). Verified bit-exact in test_obd_vars_vector.py (commit
  f7f6424); the earlier lift (c/obd_pid_handlers.c) mis-wrote layout + vars2 base (0xFFFFCEB4 → 0xFFFFCEC0) — fixed 2026-08-03.

## bitfield_extract_merge @ 0x48C8 (60E1D400; identical code in 60E0FC00)
- frexp-style float decomposition: x = sig * 2^e, sig in [1,2); single caller is checkFloatValidity @0x46CC (call site 0x46D8), feeding both
  output words into the fixed-point sqrt/normaliser @0x4740 as stack args (the old "mul16_signed_saturated" / "q15 saturating mul" labels on
  0x4740 are WRONG — see the 0x4740 entry below).
- Calling convention: float arg in FR4; result pointer at [r15] pushed by caller in the jsr delay slot (mov.l r15,@-r15); writes
  out[0]=exponent word, out[1]=significand word.
- out[0]: bit31 = sign (except NaN), low16 = signed exponent; 0x8001 sentinel for 0.0, 0x7FFF saturated for Inf/NaN. out[1]: 24-bit
  significand << 8 (bit31 = implicit leading 1); 0xFFFFFFFF for NaN, 0 for zero/Inf. NaN DROPS its sign (ROM zeroes r2 at 0x4924); ±Inf keep
  sign. Subnormals normalized to [1,2), e in [-149,-127].
- IDA/Ghidra listings mis-decode the tail: at 0x4922 the raw bytes are `D1 03` = mov.l @(.lit2,pc),r1 (load 0x7FFF), NOT mov #0,r2.
  Byte-level decode verified on both ROMs.
- Verified: emulator (sh2emu.py) vs model over 30 edge cases + 100k random bit patterns, and C lift (c/bitfield_extract_merge.c) vs emulated
  ROM — 0 mismatches. See docs/functions/bitfield_extract_merge.md.

## Immobilizer leaf functions (Track A, verified 2026-07-31)
- `seed_mixer` @0x366B8 (pure fn of r4=key word, r5=rolling key): 1. x = ((r4>>8)&0xFF)<<16 | ((r5&0xFF)<<8) | (r4&0xFF) 2. x = (x &
  0xFFE0301F) | ((x & 0x0FE0)<<9) | ((x & 0x001FC000)>>9) 3. y = (-(x>>16)&0xFF)<<16 | (-(x>>8)&0xFF)<<8 | (-x&0xFF)   (byte-wise 2's
  complement) 4. z = (y<<21) | (y>>3) 5. result = ((z&0xFF)<<16) | (((z>>8)&0xFF)<<8) | ((z>>16)&0xFF)   (byte swap 0<->2)
- `calculateImmoSeed` @0x3675C (pure fn of r4=w2DC, r5=w2E0, r6=key): sum16 = (r4>>16)+(r6>>16); sum32 = r4+r6; m1..m4 = 0x0D * (byte/word
  of sums); scN = ((b<<7)>>8)+(b<<7) per byte; mixes with r5 (r14=(r5>>16)^sc2, r7=sc3^(r5>>8), r5^=sc4, r6=sc1^(r5>>24)); branch on bit0 of
  mixed r5: odd: bytes = (r6, r14, fold4(r5), fold4(r7)); even: bytes = (fold4(r14), fold4(r6), r7, r5); fold4(v) = (v<<4)+(v>>4); result =
  b0<<24|b1<<16|b2<<8|b3.
- **Encoding gotcha (root cause of first mismatch):** SH-2E 0x6 group ALU ops are `0x6n<op>m` with dest n in bits 11-8 and SOURCE m in bits
  3-0, so `0x6477` = not r7,r4 (r4 = ~r7), NOT not r4 (r4 = ~r4). Same for neg/swap/extu/exts. disasm_sh2e.py now prints src,dst.
- Both verified: C lifts (c/seed_mixer.c, c/calculateImmoSeed.c) == emulated ROM over 100k random inputs each (make c-emu, FUNCS registry in
  c/tests/verify_emu.py).
- ImmoKeyExpander_365D6 @0x365D6: slot i = seed_mixer(w2E0/w2DC shifts, key shifts), stored |0x01000000..0x04000000 into 0xFFFFC260..26C.
  ImmoGetSeed_3664E @0x3664E calls calculateImmoSeed(w2DC, w2E0, key) → IMMO_SEED_OUT.

## Boot sequence (60E1D400, verified 2026-07-31) — full chain in docs/subsystems/BOOT_SEQUENCE.md
- **Reset vector** @0x0000 = 0x8B8 `Manual_Reset`; initial SP @0x0004 = 0xFFFFDFA0. Manual_Reset → bsc_init (0x8CC) + gpio_init (0x8F6) →
  resetHandler(0,0) @0x4E0. **Main app entry is 0xD49C** (ROM longword @0x7FFF8), NOT 0xD4B6: VBR=0x7FC50, FPSCR=0x40001,
  SP=[0xD9C8]=0xFFFF7304 via stack_frame_set_sp (0x4C7A = rts/mov r4,r15), then secondary_boot_main (0xA038), infinite loop.
- **App entry chain**: [0x1000]=0x12B4 → jsr 0x1038 secondary_boot_init (r4=0); 0x1038 checks [0x7FFFC]=0x2000 and [[0x7FFFC]] (ROM-ID
  "60E1D400" != 0xFF), sets r14=[0x7FFF8]=0xD49C, calls atu_configure_all_channels (0x12BE), then set_sp_and_jump (0x1094): SP=0xFFFFDFA0,
  jmp @r4 → 0xD49C. **Trampolines** 0x40 and 0x1094 identical: mov.l [lit],r15 (SP=0xFFFFDFA0) + jmp @r4; resetHandler exits via jsr
  @[0x594]=0x40 with r4=r13 (chosen vector).
- **resetHandler (0x4E0) verified** (matches c/reset_handler.c): bsr 0x572 (resetWatchdog?), hw_init_1/2/3 (0x170/0x41C/0x3D4), magic
  0x5AA5A55A @0xFFFFDFFC cold/warm split, checkWatchdogTimer_OVRCOUNT(7) @0x5B0, vector select [0x1000]=0x12B4 | [0x7FFF8]=0xD49C | default
  0x6C8, store magic, exit via 0x40.
- **reset_handler.c bug fixed**: WDT_RESET_ADDR was *(uint16_t*)0x596 (=0x5A1F, a WDT *write magic*), called as code; real target is fixed
  0x572. BOOT_CONT literal 0x594 = 0x0040 = vector_trampoline_set_sp.
- **secondary_boot_main (0xA038)**: peripheral_init_chain_A (0x4C80: 0x5292, [0xED18]=0xFF, ubc_breakpoint_config_init 0x4DF6, ...),
  secondary_peripheral_initializer (0xD7B0), sfr_write_a16c (0xA0DC: [0xFFFFA16C]=0), setSR_PARAM (0x2054, 0xE0 mask),
  setRegister_REG_BIT_VAL (0x4BBC: 0xF74E bit8), loadStatusRegister_ADDR (0x2064, formerly fpu_nop_stub), sfr_init_dma_channels (0x4CF8),
  task_context_switch (0x3AD8, r4=0), idle loop.
- **task_context_switch (0x3AD8)**: valid if task_id < [0x4B00] (task count byte=1); saves SR/PR + SP → [0xFFFF72D8]; SR=[0x4B04]=0xB0;
  SP=[0x4938]=0xFFFF719C; [0xFFFF72B0+8]=0x100; tail-jmp 0x3E10 (init_main). Sibling @0x3B08 restores SP from 0xFFFF72D8 + rte.
- **init_main (0x3E10) re-verified** — c/init_main.c correct: prologue sts.l pr,@-r15; mov r4,r0; literals
  0x4938/0xFFFF72B0/0x4B04/0x4990/0x3964/0x3EC0/0x3F10/0x3AC0/0x3F8C/0x3F88/0x3F90/0x3F9C/0x4B14/0x3588/ 0x3FA8/0x3C2A all match. Caller is
  task_context_switch (0x3AD8), not "after hw_init chain" — init_main.c header corrected.
- **0x6C8 boot continuation** = serial dispatch loop (flash/service bootloader): byte&0xF8 matches 0xA8→bsr 0x806, 0x88→jsr 0x4C, 0x90→jsr
  0x64, 0x98→bsr 0x7C0, 0xA0→jsr 0x7C, 0xB0→jsr 0x8A, 0xC0→jsr 0xC0; fallback [r4]==0xFF && [r5]&0xF8==0xC8 → jsr 0xD8; loop tail jsr 0x31C.
  Handlers not traced.
- **0xD4B6 warm restart** (symbol main??, called from 0x64E0 RTOS task): bsr 0xD4FA (validate via 0x99C4 placeCANRX with DBCC table @0xDBCC
  + 0x636 validate_data_block_header on 0xFFFFA3E8); if ok and [0xFFFF9F8C]==1: SR &= 0xFF0F | 0xF0 (mask), resetHandler(1, result) warm
  restart, idle loop. NOTE: 0x99C4 is the CAN receive path, NOT a checksum — earlier "DBCC checksum check" label wrong.
- New C lift: c/boot_entry.c (0xD49C + 0xA038 + 0x3AD8), compiles clean (-Wall). RTOS_SUBSYSTEM.md corrected: "bsr 0x594 → 0x5A1F" was wrong
  (0x5A1F is a WDT write value); verified exit is jsr @0x0040 vector_trampoline_set_sp.

## DTC Management subsystem — Track-A verified (2026-07-31)
- **All six DTC-management functions verified** against the ACTUAL ROM bytes (60E1D400.bin) in tools/sh2emu.py over random RAM states; all
  tests pass: dtcRelated@0x062002, dtc_handler_610FA@0x610FA, dtc_handler_61550@0x61550, dtc_code_set/clear@0x46780/0x467AA,
  dtc_debounce_monitor_43760@0x43760 (incl. float gates).
- **dtcRelated out buffer is PACKED**: matches written to `out[count]` (r12 = r6 + 2·r7, r7 = running count), NOT `out[i]`; C lift + test
  model fixed (was `out[i] = code`). The emulator caught this.
- **dtcRelated enable gate**: enable ∈ {0,1,2} only; 1 → tableA[code]@0x7E220 == 1, 2 → tableB[code]@0x7E2AC == 1, anything else
  disqualifies the entry. Entry index == cur_idx@0xFFFF8928 is skipped.
- **Emulator indexed-mov verification**: `mov.b @(R0,Rm),Rn` = `0000 nnnn mmmm 1100` (dest bits 11-8, index bits 3-0) — matches Hitachi
  SH-1/SH-2 manual AND capstone (0x08EC = mov.b @(r0,r14),r8). No emulator bug; earlier dtcRelated failures were test-model big-endianness.
- **610FA dispatch**: opcode @0xFFFF87DE + idx·16; 0x50/0x00 → can_encode_handler_62FAC(8) → obd_service_handler_64258 (marks pending entry:
  base@0xFFFF8930 +0x34·sel, byte +7=1, +8=7, counter @+0x32) → tail-call obd_service_handler_63312. Other opcodes: no side effects.
- **61550 common tail**: every mode (1/2/3) stores enc result @0xFFFFD6FC, status @0xFFFFD6FF; if w16@0xFFFFD700 == dtc →
  can_encode_handler_62ABC(dtc,0x20) (may update run-sum words 0xFFFF8E98/ 0xFFFF8E9A via 0x648B4); then
  can_encode_handler_62B24(dtc,0x20,status); tail-call obd_service_handler_632D6.
- **Debounce gate order (fcmp/gt → T = FRn > FRm)**: `if 17000.0f > accum` → zero B/C; `elif 500.0f > runtime` → path C (counterC++, flag2
  @>=4); else → path B (counterB++, flag1 @>=16); else B=C=0; then `cond ? counterA++ (sat) : counterA = 0`. Thresholds 157/16/4
  @0x7D97C/78/7A, float gates 17000.0 @0x7D984, 500.0 @0x7D988.
- **dtc_code_set/clear**: checksum-paired bytes (b,~b); set @0x46780 only when present-flag @0xFFFF8788 == 1 (readValue_8bit_ADDRESS_VAL
  default 1); both write 0 to state words 0xFFFF875C/0xFFFF875E via updateMemoryAtAddress_8bit.
- **Docs**: docs/functions/dtc_management.md (new, consolidated), docs/functions/dtcRelated.md (rewritten; old draft was 60E0FC00-based
  @0x5FEB6 with wrong tables 0x7C9FC/0x7CA88 — invalid for 60E1D400).

## OMP (Oil Metering Pump) stepper chain — 60E1D400 (2026-07-31)
Task entry 0x1825E (OS task table @0x18024) drives the OMP stepper through sub-functions by state bytes. Chain verified bottom-up against
the ROM emulator:
- **0x18552 omp_stepper_waveform_driver** — stepper phase table driver (modes 0-6), incl. sat8(A97F+A974) / A97D+2 / A98D=mode / port F746.
  ✓ (60000 random).
- **0x18860 omp_waveform_state_machine_18860** — 4-state machine on RAM8[0xFFFFA981] (0x982/0x97E/ 0x977/0x978 latches, ADDRESS_VAL port
  8078/807C gates, float -40.0 sensor-validity gate — CAL_A==CAL_B==0x3C stock, so no cold correction applied), drives wave(0/1/2), A97C==5
  → A97B=0x80, A981=1. ✓ (60000 random).
- **0x189EE rotor_sync_position_detector** — 5-state machine on RAM8[0xFFFFA98B] tracking A8F1 (old) vs A974 (new) rotor position; tail
  dispatches wave(2/3/1/4) + A97B per final state. mode arg from RAM8[0xFFFFA984]. **Bug caught by emulator**: state-4 `add #0xFE,r1`
  SIGN-EXTENDS (0xFE = -2), so the gate is `(A8F1 - 2) >= A974` (signed), not `(A8F1 + 0xFE) >= A974`. ✓. C lift:
  c/rotor_sync_position_detector.c.
- **0x18C5C**: wave(6) then A97B = 8. ✓. **0x18C6C**: A974>7: wave(3),A97B=0x10; A974==7: wave(4), A97B=4; A974<7: wave(2),A97B=0x10. ✓.
  **0x18C08**: A980==1: write16(0x807C,1) via 0x3EE58, diag-table store via 0x9668, A980=2; then A8F1==A974 → A97B=0x30,A980=1, else →
  0x189EE(A984). OMP-RAM behavior confirmed (12/12 varied states).
- Also mapped: task table @0x18000 (0x18024 → 0x1825E, 0x1802C → 0x18CC0 companion); 0x1825E dispatches 0x18C6C (A998==1) / 0x18860(A985)
  (A968==1) / 0x18C08 (A96A==1 && ACD06==0) / 0x18C5C (A96B==1) / 0x189EE(A984) (A969==1), all gated on A97B countdown reaching 0.

## Disassembler decode-gap fix + rebuild integration (2026-07-31)
- **GBR-relative MOV corrected**: 0xC0/0xC1/0xC2 = MOV.B/W/L R0,@(disp,GBR) (STORES), 0xC4/0xC5/0xC6 = MOV.B/W/L @(disp,GBR),R0 (LOADS). Old
  handler matched only disp nib==0 and reversed direction. Verified vs GNU-as 2.46: 0xC02C/0xC116/0xC20B, 0xC42C/0xC516/0xC60B. Disp fields
  are units (.b byte, .w bytes/2, .l bytes/4).
- **0x82xx/0x86xx mov.l r0,@(disp,Rm) / mov.l @(disp,Rm),r0**: register in bits 7-4, disp nib x4. GNU-as has NO syntax — re-encodes as
  0x1nmC/0x5nmC (e.g. 0x82C0 → 0x1C00). Rebuild forces `.word` (byte-exact by construction); they decode for inspection only.
- **Control-register encodings verified**: stc SR/GBR/VBR/SSR/SPC = 0x0n02/12/22/32/42; stc.l = 0x4n03/13/23/33/43; ldc =
  0x4n0E/1E/2E/3E/4E; ldc.l = 0x4n07/17/27/37/47; sts mach/macl/pr = 0x0n0A/1A/2A, fpul 0x0n5A, fpscr 0x0n6A; lds fpul/fpscr = 0x4n5A/6A;
  lds.l fpul/fpscr = 0x4n56/66; sts.l fpul/fpscr = 0x4n52/62. Correction: 0x4n66 is lds.l fpscr (was mislabeled lds.l fpul); added missing
  sts.l fpscr 0x4n62. GNU-as accepts uppercase register names.
- **bsrf/braf are register-only** (`bsrf rN` = 0x0n03, `braf rN` = 0x0n23, PC = PC+4+Rn); GNU-as rejects `bsrf L_x` — no label form exists.
  **div0u is operand-less** (0x0019); GNU-as rejects `div0u r0`. **Indexed-mov syntax fix**: GNU-as form is `mov.b r11,@(r0,r8)` (0x08B4) /
  `mov.b @(r0,r11),r8` (0x08BC), likewise mov.w/l and fmov.s (0xF217/0xF126).
- **Coverage after fix** (full ROM): 60E1D400 217,449 → 226,408 decoded (86.4%); 60E0FC00 220,543 (84.1%). Code region 0x800..0x60000:
  capstone-only 84.6%/84.7% → 93.8% with disasm_sh2e fallback.
- **Whole-ROM GNU-as round-trip**: every decoded word in both ROMs reassembles byte-exact (226,048/226,408 and 220,183/220,543); only
  non-round-trippable words are the 360/360 82xx/86xx, which canonicalize to 0x1nmC/0x5nmC.
- **rom_rebuild.py now byte-exact with the fallback** (was already byte-exact with capstone-only): 60E1D400 lifts 183,120/195,584 (93.6%,
  252 raw fallbacks); 60E0FC00 lifts 182,998/195,584 (93.6%, 377 raw fallbacks). Both print BYTE-EXACT. **organize_src.py uses capstone +
  its own fpu() helper, NOT disasm_sh2e.py**; not switched.

## .word data regions in code window 0x800..0x60000 (2026-07-31)
Confirmed facts from `analysis/data_regions_60E1D400.{csv,md}` (tool: /tmp/opencode/classify_word_runs.py, deterministic):
- The annotated `.s` maps linearly from ROM offset 0; the walker reproduces every `L_xxxxxx` address (0 mismatches). Instruction sizes +
  26,996 pcrel refs from the `.s` are the code oracle — **capstone SH-2 is a strict subset** (fails 0x0000/0x0100/0x0400/0xffff), so it
  cannot find missed code. Sweeping all 1,491 runs through capstone found zero code-like sequences: **no undecoded_code_capstone runs
  in-window**; window 100% covered (93.6% instr + 6.4% .word bytes).
- Per-class (1,491 runs / 4,736 words): literal_pool 883/2,288; padding 366/1,540; unknown_data 221/789; jump_table 18/112; string 3/7;
  calibration 0/0 (all 1,210 cal_tables.csv addresses are 0x6CF6C..0x7D92C, outside the window).
- **0x426C/0x4290 are genuine 32-bit dispatch tables** (17/13 words): loaded via the 0x4224 pool (`div_trampoline_A/B` at 0x420C/0x4218 do
  `mov.l @(r0,r3),r3; jmp @r3`). No genuine 16-bit `braf` switch tables in-window; all 4 `braf r0` sites sit inside mis-decoded data.
- **0x493C is a Renesas-style div-library 16-bit constant table** (0x0013/0xFFFF header + 19x (0x0000,0x0001)) referenced via pools — data,
  not jump table.
- **Mis-decoded-data regions in the .s**: 0x84E-0x8A4, 0x85BA-0x8600, 0x8704-0x8730, 0x883C-0x8850 (alternating garbage instr + `.word
  0x0000` = 32-bit data), 0x3C8E0-0x3C91C (32-bit pointer table into 0x7A9xx cal region), 0x4224-0x4226 (pool holding the 0x426C table
  base).
- **Strings in-window are fragmentary**: 0x2000 holds '60E1D400' ROM-id and 'Copr.DENSO200' (the .word runs at 0x2002/0x2028 are mis-sliced
  fragments); 0x3B28 is the real 'Copyright 1999 Hitachi,L'. 0x6CE00 'N3J1E_3W.T50' is BE-packed ASCII (2 chars/word), outside the window.
  Classifier requires a >=12-byte printable span, so random 4-char fragments (e.g. "OROb") are not strings.

## Track A session 8: flag_setter_49ED0 (formerly math_min_max_49ED0) verified + mov.w sign-extension correction
- **flag_setter_49ED0 (0x49ED0, 34B, formerly math_min_max_49ED0)** verified against ROM bytes in the SH-2E emulator
  (test_flag_setter_49ED0.py, 14 edge + 20000 random, 0 mismatches) and as a host C lift (test_flag_setter_49ED0.c, 20014 tests, 0
  mismatches). Semantics: `v = (RAM16[0xFFFFF76C] & 0x100) ? 1 : 0;` `byte@0xFFFFCD48 = v; byte@0xFFFFCD49 = v; return v` (return flag in
  r0). `make c-test` stays GREEN (7 suites).
- **CORRECTION (unblocks the low-SFR family):** `mov.w @(disp,PC)` SIGN-EXTENDS its literal (SH-2 semantics). Disassembler short comments
  (`; 0xCD49` / `; 0xF76C`) are truncated shorthand — with bit 15 set the real addresses are 0xFFFFCD49 / 0xFFFFF76C etc. So 0xCD4C, 0xD2C4,
  0xD2C5, 0xCE00/01 etc. are actually 0xFFFFCD4C, 0xFFFFD2C4, 0xFFFFD2C5, 0xFFFFCE00/01 — all above mmap_min_addr=0x10000 and host-mmap-able
  (proven: test_calc_manifold... mmaps 0xFFFFA5D4; test_flag_setter_49ED0.c mmaps 0xFFFFF76C/0xFFFFCD48). The earlier "below mmap_min_addr,
  must use structural tests only" blocker is WRONG — host-C mmap companions are possible for all of them.
- Related emulator observations: unseeded reads of 0xFFFFxxxx addresses fall back to `rom[a] if a < len(rom) else 0` → 0 (safe); byte writes
  land in the sparse `cpu.ram` overlay at the FULL 0xFFFFxxxx key (assert on `0xFFFFCD48`, not `0xCD48`).

## Track A session 8 cont.: OBD DTC-table family verified (0x64258/0x64418/0x64490/0x643D4/0x6443E)
- **DTC table layout** (used by all five): base 0xFFFF8930, stride 0x34, **21 rows (0..0x14)** — 0xFFFF8930 + 21*0x34 == 0xFFFF8D74 (the
  row-index word itself; table bounded by its own index). Row indices > 0x14 wrap the pointer into ROM code (row=0x211A landed at 0x64278
  and clobbered function code → false failure). Realistic tests must stay within 0..0x14.
- **0x64258** (row update): `p[0x32] += p[0x07] + 0xFF; p[0x07] = 1; p[0x32] += p[0x08] + 0xF9; p[0x08] = 7` (byte ops). 22048 host tests
  OK.
- **0x64418** (row update, r4 arg): `p[0x32] = (s8(p[0x32]) + s8(p[0x08]) - r4) & 0xFF; p[0x08] = r4 & 0xFF`. 22560 host tests OK.
- **0x64490** (row update, r4 = 16-bit value): `w = word@p+0x02; delta = (s16(w) + ((w>>8)&0xFF)) - (r4 + ((r4&0xFFFF)>>8)); p[0x32] =
  (s8(p[0x32]) + delta) & 0xFF; word@p+0x02 = r4 & 0xFFFF`. 22560 host tests OK (uses `add.b #imm` sign-extended bytes — same sign-extension
  family as the session-8 correction).
- **0x643D4** (search): returns `s8(p[0x06])` for the first row whose `word@p == r4&0xFFFF` and `i != currow`; else 0. 5000 host tests OK.
  **0x6443E** (search): returns `s8(p[0x08])` for the first row whose `byte@p+0x06 == r4&0xFF` and `i != currow`; else default 0x08 (r14
  preloaded with 0x08). 5000 host tests OK.
- All five verified against the ROM in the SH-2E emulator first (targeted + random), then as host-C mmap companions with matching reference
  models; 0 mismatches everywhere.

## Track A session 8 cont.: idx_table + req_queue families, setSR tail-call
- **idx_table family (0x68780/0x6879C/0x687C8/0x687F4)**: 4 packed leaves over a RAM table at 0xFFFFD998, stride 0x46C, byte index; called
  via the 0x68776 wrapper (clear(0)) and function-pointer tables (pools 0x68CE0/0x695C0/0x695D0). clear = zero 3 words; step/step2 =
  count-up `word@p = (word@p+4 >= 0x0464) ? 0 : word@p+4+1` (0x6879C and 0x687C8 are two separate ROM copies with identical logic); dec =
  `word@p+4 = (word@p==0) ? 0x0464 : word@p-1`. **Caveat:** indices >= 9 wrap the pointer (0xFFFFD998 + 0x46C*n exceeds 2^32 for n >= 9) —
  realistic use is indices 0..8 (only 0..1 fit the 4KB RAM bank 0xFFFFD000-0xFFFFDFFF).
- **req_queue leaves (0x69602 store / 0x69694 clear)**: byte flag array at 0xFFFFDE38 + parallel long array at 0xFFFFDE40. store:
  `long@(0xFFFFDE40+b*4) = (uint32)(r5 * 0x0FA0) + long@0xFFFFF430; flag = 1`. clear: flag = 0. Both called exclusively through
  function-pointer tables. The 0x69624..0x69692 dispatcher between them (7-entry loop: calls 0x3920, dispatches via the 0x69918 table to
  0x68C82/ 0x68C2E/0x68C8E/0x68D20/0x68CA2/0x68D74/0x68DC0, and calls setSR 0x3934) is a CALLER — not lifted, per the leaf convention.
- **setSR 0x3934 tail-call branch now emulator-tested**: previously untestable; seeding the kernel struct at 0xFFFF72B0 (word@0x04 ==
  word@0x06) makes 0x3DB0 take its early-exit path (bt to 0x3DF0), so the full ROM path setSR(0) -> flag!=1 -> jmp 0x3DB0 -> early exit
  executes in-emulator and ends with SR=0, r0=0. getSR (0x3920) and setSR_PARAM (0x2054) also verified (20000 random each). SR accessors are
  emulator-only (no host C test: the lift's SR is a private file-scoped var).
- **Verification gotchas**: 0x3013 decodes n=(op>>8)&0xF=0 (r0), m=(op>>4)&0xF=1 (r1) → cmp/ge r1,r0 ⇒ T=(r0>=r1): counter RESETS when
  word@p+4 >= 0x0464 (count-up), not below it. Host test seeding must use host-endian *(volatile uint16_t*) writes (not big-endian byte
  writes).

## fuelingInit @ 0x753C reconstructed + Track-A verified (2026-08-02)
- New reconstructed sample `reconstructed/samples/src/rx8_fueling_init.c` (deliverables: `tests/oracle_fueling_init.c`,
  `tests/harness_fueling_init.py`). Verified host-C == emulated ROM for 20000 random + 87 edge vectors, all 49 side-effect cells (11 MTU +
  38 RAM) bit-exact.
- Call chain (all callees run inside the emulated call, tail-call included): 0x753C → bsr 0x076DC crank_timer_hw_reset; bsr 0x07748
  crank_vars_init (+ its 0x07B7C leaf); bsr 0x07C00 crank_mode_write; bsr 0x07BA8 crank_state_bytes_clear; bsr 0x07C30 crankSensorInit (tail
  `bra 0x0768C r4=0` when 0xFFFF9F96==1 — never reachable on this path, fuelingInit zeroes the flag first); bsr 0x07ED8 crank_flags_enable;
  bsr 0x07FB4 crank_counters_reset; tail `bra 0x0808E` crank_output_update (ends in rts). 0x0768C ends in `jmp @u32@0x0000DB60`
  (mode-function pointer) — harness never seeds (0xFFFF9FC0==1 AND 0xFFFF9FA3!=2 AND 0xFFFF9F96==1) so the emulator cannot run away through
  it.
- ROM constants pinned by harness check_cal (0x0006CF64 u32=0x000FA000, 0x0006CF68 u8=0x00, u8@0x0000DA4D=0x00, f32@0x000080FC=10.0f); the
  two low pages (<mmap_min_addr) are pinned, never dereferenced on the host.
- Gotcha confirmed: `mov #0xFF,r1` is SIGN-EXTENDED on the SH-2, so the `mov.l r1,@0xFFFF9FB0` at 0x7760 stores 0xFFFFFFFF (not 0x000000FF).
  First reconstruction used 0xFFu and the harness caught it.

## canSetup @ 0xDC8C reconstructed + Track-A verified (2026-08-02)
- New reconstructed sample `reconstructed/samples/src/rx8_can_setup.c` (deliverables: `tests/oracle_can_setup.c`,
  `tests/harness_can_setup.py`). Verified host-C == emulated ROM for 20000 random + 65 edge vectors on the three caller cells (retry counter
  @0xFFFFA40E, error flags @0xFFFFA410/@0xFFFFA411), 0 mismatches.
- Caller logic (full disasm 0xDC8C..0xDD2B): resets byte@0xFFFFA40E=0; loop `while counter < 2`: base0 = (byte@0xB5A4==1)?0x4EA60:0x4EB60;
  CANControllerSetup(0,base0,0x10); canMessageSetup(0,base0,0x10); CANControllerSetup(1,0x4EC60,6); canMessageSetup(1,0x4EC60,6);
  err=(e0|e1)&0xFF; if err!=0 counter++ (stored), else break. Exit: if counter>=2 byte@0xFFFFA410=1; byte@0xFFFFA411=0 ALWAYS (r1=0 in both
  paths).
- Callee facts: CANControllerSetup @0x9878 (writes on-chip MMIO 0xFFFFE400..0xFFFFE6FF, incl. cells canMessageSetup later checks, e.g.
  E402=0x803E, E404/E414 mailbox-derived); canMessageSetup @0x2B320 reads ALL its MMIO via the sign-extended HIGH aliases
  0xFFFFE4xx/0xFFFFE6xx (NOT 0xE4xx) — the harness must seed the high-alias page; canMessageSetup ALWAYS clobbers r6 to 1 (unconditional
  `mov #0x01,r6` in the delay slot of the rts of the first branch @0x2B34E), so its return r7 is 1 on failure.
- KEY INVARIANT: canMessageSetup's verification never agrees with the config CANControllerSetup derives from the same mailboxes, so the
  ROM's canSetup ALWAYS ends (2,1,0) — verified 1500/1500 diverse seeds + full edge sweep. The oracle models the two callees as no-op /
  always-fail stubs (documented in the C header, discrepancy 5); the success path is unreachable under any harness-seedable state.
- The config byte address 0x0000B5A4 lies below mmap_min_addr (0x10000), so it is passed to the host model as a `config` parameter (same
  precedent as rx8_task_flag_run_c's 0x4B10 fn-pointer parameter).

## interp-s8 leaf @ 0x26F4 reconstructed + three-arm verified (2026-08-03)
- New SINT8-cell interpolation leaf reconstructed (proposed `samples/src/rx8_interpolate_s8_table.c`, embedded in
  `tests/verify_interp_s8.py`, written to /tmp only — nothing committed to src/). ROM @0x26F4 (28 B / 14 instr, pure leaf), the s8 sibling
  of u8 @0x26B0 / u16 @0x26D0 / s16 @0x2690; TwoDLookup type tag 12.
- Disasm: `add r0,r1; fldi0 fr2; mov.b @r1+,r0; fcmp/eq fr0,fr2; lds r0,fpul; bt/s rts; float fpul,fr2 (delay); mov.b @r1,r0; lds; float
  fpul,fr1; fsub fr2,fr1; fmac fr0,fr1,fr2; rts/nop`. Signedness vs u8: NO `extu.b` after `mov.b` (sign-extending byte load) and NO `shll`
  (byte stride), so -128..-1 cells convert to negative floats. Return convention identical to siblings: ROM r0=i/r1=cells/fr0=t → fr2 (fr0
  preserved for the 2-D callers); gcc-ABI blob r4/r5/fr4 → fr0.
- Only real s8 map in 60E1D400.bin: desc@0x6A328, values@0x70C70 ("Table 3D - 27_", 7 cells, all positive 0x10/0x27) — used plus synthetic
  -128/127/0 pattern tables.
- Verified `python3 tests/verify_interp_s8.py` (and 20000-vector stress): ROM fr2 == gcc-3.4.6 blob fr0 == pure-Python single-rounding
  oracle, bit-exact, 3000+ vectors, 0 mismatches; fr0_kept asserted per vector. Runs green under `tests/run_all_verify.py` too.

## 0x4740 — fixed-point SQUARE ROOT (working name "div_4740" is a misnomer) (2026-08-03, refined 2026-08-04)
- The disassembler label "q15 saturating mul" on 0x4740 is WRONG, and so is the working name "div_4740" / "sh2_div_4740": 0x4740 is a
  fixed-point restoring SQUARE ROOT, the middle stage of the soft-float chain `frexp @0x48C8 -> sqrt @0x4740 -> ldexp @0x481C`, with sole
  caller `checkFloatValidity @0x46CC`.
- Stack convention (non-ABI, stack-passed, 2 x 32-bit result buffer): [r15+0]=out ptr, [r15+4]=a0, [r15+8]=a1; writes result[0]=low word and
  result[1]=high word via the ptr at [r15].
- CLOSED FORM (confirmed 2026-08-04, main path, 49932/49932 random inputs, worst error 1 ulp = rounding mode): `r1 = round(sqrt(a1 << (31 +
  (a0 & 1))))`, `r3 = (sext16(a0) >> 1) & 0xFFFF`. The LSB of a0 selects a 1-bit pre-shift that normalizes the radicand.
- Loop signature (verified instruction-for-instruction bit-exact, 0 mismatches on 100k+ vectors incl. all early-exit edges): 29-iteration
  restoring loop with trial divisor r0 growing one bit per iteration (`rotcl r0` with T=1 -> r0=(r0<<1)|1, +1 on each successful subtract),
  2-bit-at-a-time radicand shift (shll/rotcl pairs on r2:r5), root bits accumulated in r1 via rotcl, final restore phase + sticky round-up
  (r1|=1 if remainder != 0).
- BUG FIX (2026-08-04): an earlier Python model (`ref_helpers.py` outside the repo) left the SH-2 T flag unset across loop iterations — the
  loop-top `rotcl r0` @0x476C consumes the T set by `cmp/pl r6` @0x4788 (T=(r6>0)); with T stale the model diverged. Fixed at that site;
  corrected model matches the emulator on 200k+ div + 200k ldexp + 289 edge vectors, 0 mismatches.
- Saturation paths: bit31(a0) set -> (0x00007FFF, 0xFFFFFFFF); sext16(a0)>=0x7FFF -> (0x00007FFF, a1!=0 ? 0xFFFFFFFF : 0x00000000);
  sext16(a0)<=-0x7FFF -> (0x80008001, 0x00000000); main path low word = (sext16(a0)>>1) & 0xFFFF.
- Harness: `reconstructed/samples/tests/verify_q4740.py` (emulated ROM vs bit-exact Python model, exit 0) and Track-A `c/div_4740.c` +
  `c/tests/test_div_4740.py` (C lift vs emulated ROM, 100156 inputs, 0 mismatches) — registered in `c/verified_addrs.txt`.

## EMULATOR BUG FIX: `mov rX,@-rX` pre-decrement stores (2026-08-04)
- The SH-2 `mov.b/w/l Rm,@-Rn` family in `tools/sh2emu.py` decremented Rn BEFORE storing Rm, so when Rm == Rn (e.g. `mov.l r15,@-r15`
  @0x46DA) it wrote the DECREMENTED register value instead of the ORIGINAL. Real SH-2 hardware stores the pre-decrement source value: `mov.l
  r15,@-r15` pushes the current frame pointer (0xFFFFDEE4), not SP-4.
- Fixed by capturing `v = r[m]` before `r[n] -= n` (3 lines). The bug silently corrupted the stack-passed argument pointer into frexp
  @0x48C8 from checkFloatValidity @0x46CC: frexp's result pointer read 0xFFFFDEE0 instead of 0xFFFFDEE4, shifting the whole sqrt/ldexp
  pipeline one word and making 0x46CC return NaN for every input.
- After the fix the full soft-float chain computes sqrt(x): checkFloatValidity(4.0)=2.0, (9.0)=3.0, (0.25)=0.5, (2.0)=1.4142135 — confirming
  0x46CC is a SQUARE ROOT (frexp 0x48C8 -> sqrt 0x4740 -> ldexp 0x481C) that also flags Inf/NaN inputs by writing a fault code (0x044D NaN /
  0x044C Inf) to byte 0xFFFF768C.
- Regression: full suite 203/203 passed, `make test` green.

## 0x481C — ldexp-style float reconstruction (2026-08-04)
- Third stage of the `frexp 0x48C8 -> sqrt 0x4740 -> ldexp 0x481C` chain, sole caller `checkFloatValidity @0x46CC` (call site 0x46EE).
- Stack convention: [r15]=arg1 (exponent word), [r15+4]=arg2 (mantissa word); returns float bits in r0 (also copied to fr0 by `mov.l
  r0,@-r15 ; rts ; fmov.s @r15+,fr0` @0x488E).
- Semantics (verified bit-exact vs emulated ROM, 100120 inputs incl. edge cases, 0 mismatches): exp = sext16(arg1); if exp>=0x7FFF ->
  saturation (arg2==0 ? (0xFF,0) : (0xFF,0x100)); else exp += 0x7F (bias 127 inline); exp>=0xFF -> (0xFF,0); exp<=0 -> (0,0); else
  reconstruct r0 = (arg2<<1)>>8 | (exp+0x7F)<<24 | bit31(arg2)<<31 via the shll/shlr/rotcr chain at 0x4880. The 0x483C-0x487E block is
  UNREACHABLE from 0x481C (0x4836 bt 0x4880 and 0x4838 bra 0x489C jump over it) — separate entry.
- Track-A: `c/ldexp_481C.c` + `c/tests/test_ldexp_481C.py` (C lift vs emulated ROM, 100120 inputs, 0 mismatches) — registered in
  `c/verified_addrs.txt`.

## engineControlCalculateTiming @0x14584 — dispatch wrapper verified (2026-08-03)
- Pure task-dispatch skeleton, 414 B, zero branches: 68 calls in fixed ROM order from the literal pool 0x14784..0x14888 (66 unique targets;
  getSR @0x3920 and setSR @0x3934 each called TWICE — 0x3920 after the barrier at 0x145CC, 0x3934 as the TAIL jmp at 0x1471E whose delay
  slot `lds.l @r15+,pr` returns straight to the wrapper's caller).
- Phase 1: getSR(16) -> incomplete_stack_save_r14_r13(0x14B04, stores SR at [r15]) -> 8 subsystems (0x121F0..0x17DCC). Barrier: setSR(saved
  SR), then getSR(16) again (re-saved SR stored at [r15]). Phase 2: 55 subsystems (0x1379C..0x4D0E8). Tail: pop r4=[r15], jmp
  setSR(saved_sr). The lift `c/engineControlCalculateTiming.c` call order matches the ROM order exactly (phase 2 = 55 subsystems, NOT "56"
  as the lift comment says).
- Verified bit-exact: `c/tests/test_engineControlCalculateTiming_14584.py` (emulated ROM wrapper + 66 trace-append stubs vs pure-Python
  model AND vs the compiled C lift with equivalent C stubs), 15140 inputs / 5 seeds, 0 mismatches. Pins r0/r1, the full 102-byte span
  0xFFFFD12F..0xFFFFD194 (length cell @0xFFFFD130 + 68-entry trace @0xFFFFD140), and tail-call invariants (r15 -> 0xFFFFDF00, PR word ->
  0xEEEE0000).
- Stub-mechanics gotcha (repo first): 34-byte single-block stubs (0x11A34 pattern) OVERLAP for adjacent callees — getSR @0x3920 and setSR
  @0x3934 are only 0x14 apart. Two-level stubs used instead: a 10/12-byte trampoline at the callee's ROM address (`mov.l @(1,PC),r2; jmp
  @r2; nop; [pad]; .long body` — pool lands at ((a+4)&~3)+4, which needs 2 pad bytes for a%4==0 targets and 0 for a%4==2) + a 36-byte shared
  body per slot in scratch RAM @0xFFFFD400+ (same trace semantics as 0x11A34).
- **reset_handler @0x4E0 (re-verified with real ROM bytes)**: `c/tests/test_reset_handler_4E0.py` — real resetWatchdog @0x572 runs, hw-init
  leaves 0x170/0x41C/0x3D4 + 0x08F6 + checkWatchdog @0x5B0 are trace-append stubs, boot stub @0x40 captures r4=rv. 960 targeted + 15000
  random, 0 mismatches. Semantics: r14=1 default ("recovered"); cold path checks [0xFFFFDFFC]==0x5AA5A55A then checkWatchdog; recovery walk
  reads [0x7FFFC]/[[0x7FFFC]] (0xFFFFFFFF either level -> retry checkWatchdog), then rv=[0x1000] unless 0xFFFFFFFF -> [0x7FFF8]; warm path
  (cold_start!=0) writes reason -> 0xFFFFDFA8 and calls 0x08F6; every finish writes MAGIC -> 0xFFFFDFFC then jsr @0x40 with r4=rv (rv=0x06C8
  default). Magic matches AND wdt!=0 with [0x1000]==0xFFFFFFFF is an infinite retry loop in ROM (test enumeration avoids it). Stub gotcha
  (repo second): reset handler's literal pool lives at 0x586..0x59A, so resetWatchdog @0x572..0x585 must NOT be stubbed — a 34-byte stub
  there clobbers pool words the handler loads (mov.w 0x586,r2 etc). Real watchdog writes word 0x5A1F -> 0xFFFFEC12 and 0xA53C -> 0xFFFFEC10
  (0xEC12/0xEC10 sign-extend via mov.w PC-relative).
- **OBD mode-01 PID getters @0x55E66 (getMAFOBD), 0x55E7C (getRPMOBD), 0x55EA2 (getSpeedOBD), 0x55EEA (getSTFTOBD), 0x55F02 (getLTFTOBD)** —
  `c/tests/test_obd_pid_getters.py`, 20000 random + 10 targeted, 0 mismatches. All reduce to one pattern: read a single-precision float from
  a RAM sensor cell (16-bit sign-extended or 32-bit literal pointer) and clamp via floatToInt @0x24D0 to 0..255. Lift-correction (MAF):
  c/obd_pid_handlers.c claims getMAFOBD does `maf*100, clamp 0xFFFF` — the ROM actually does floatToInt(v, 1.0, -40.0) (scale=1.0,
  offset=-40.0, 0xFF clamp), identical math to getLTFTOBD @0x55F02. RPM = floatToInt((v-1)*100, 0.78125, -100); Speed = floatToInt(v*100,
  0.78125, -100); STFT = floatToInt(v, 0.5, -64); LTFT = floatToInt(v, 1.0, -40). STFT matches the lift ((stft+64)*2); LTFT uses offset -40
  (floatToInt +0.5 rounding, NOT the lift's "different calibration" guess).
- **CAN TX pack differential test** `c/tests/test_can_packers.py` (real ROM in SH-2E emulator vs independent Python models, 5000 random +
  directed, all green): can240TX_pack @0x4C888 and can250TX_pack @0x4C984 (straight 8-byte copies); can41TXPack @0x39348 (gate
  @0xFFFFC241==1 -> copy C238..23F->C518, else r0=gate value, no TX); can650TX_getAndPack @0x2C806, can620TX_getAndPack @0x33A36,
  CANRX216TimeoutCount @0x299DA (div-counter packers); can201TX_getAndPack @0x29B4C (flag @C656 !=0 -> 0xFF, else floatToInt(float@AA18,
  1.0, -40.0)).
- div-counter semantics (can650/can620/canRX216): counter word += 1, then `mov.w @..,r2; extu.w r2,r2; cmp/ge #N,r3` — extu.w zero-extends,
  so the compare is UNSIGNED over the full 16-bit range: ANY count >= N triggers (0x8000..0xFFFF DO trigger). Thresholds: can650 #0x0C,
  can620 #0x19, CANRX216 #0x19. Trigger resets the counter to 0.
- can620TX_getAndPack @0x33A36 pack chain (0x33A8E): priority-decode byte @0xFFFFCD4E (0x40->0, 0x20->1, 0x80->2, else 3) << 4 -> byte
  @0xFFFFC05C; priority-decode byte @0xFFFFCD4C (0x80->1, 0x10->2, 0x20->3, 0x08->4, 0x02->5, 0x04->6, else 7) -> byte @0xFFFFC05B; send
  @0x33A68 writes frame C054..C05A with C058=C05C, C05A=C05B (bytes C054-57, C059 zeroed).
- Table-address gotcha: the CAN TX table rows (e.g. 029B52 for can201, 029DC2 for can203) point one instruction PAST the prologue; the real
  entries are the bsr targets (0x29B4C, 0x29D24). Tests must call the real entry, not the table address. Pre-existing (unrelated) failure:
  `c/tests/test_o2_lambda_more.py` (untracked) raises AttributeError ('tuple' object has no attribute 'pop') in run_suite — not caused by
  the CAN pack work.

## SecurityAccess RequestSeed flow CONFIRMED (2026-08-04)
- Full row-by-row evidence in `docs/notes/UDS_SECURITY_MAPPING.md`. Handler 0x584A0 (SID 0x27, table @0x5F57C idx 10, mask 0x1000000E).
  Dispatcher 0x697E8-0x69840 calls it with **r4 = msg_len** (16-bit payload length EXCLUDING the SID byte; RequestSeed=1, SendKey=4) and
  **r5 = subfunction** — r4 is NOT a buffer pointer (C comment corrected).
- RequestSeed order: state reads (0x56866, 0x568E6 — no gate), msg_len==0 → NRC 0x12, subfunc==0 → NRC 0x31, entry only for subfunc==1,
  msg_len==1 → NRC 0x12, seed_gen(3) @0x58522, position_check(subfunc) @0x58526 (sentinel chk==3 → NRC 0x31 @0x5857E),
  key_validate(state1,state2,chk) @0x58538 (fail → NRC 0x31 @0x58574), seed written conditionally (state2==chk → {0,0,0}; else seed_gen(chk)
  + data_copy(r13) @0x5855E-0x58566), resp builder 0x5864A → [0x67, subfunc, 3 bytes] → 0x68B60.
- NRCs emitted by handler 0x584A0-0x58648: only {0x12, 0x31, 0x22, 0x35} — **no 0x11 anywhere** (state reads gate nothing; the old "already
  unlocked → 0x11" claim was WRONG).
- The "absolute-value trick" (abs_sub) IS present at 0x584FE-0x58516 (cmp/pz, abs, and #1, cmp/eq #1) but is vestigial: only subfunc==1
  enters, always odd → RequestSeed. No "level must be 1" guard exists (the ==1 test @0x5851A is on msg_len).
- **SendKey (0x58592-0x58610) is UNREACHABLE in 60E1D400**: entry 0x584B6-0x584BE routes only subfunc==1; whole-ROM branch scan shows
  0x58592 has exactly one incoming ref (bf/s @0x58516, unreachable). Subfunc != 1 → 0x5862C: subfunc==0 → resp via 0x55386; subfunc!=0 → NO
  response (silent). Previously "VERIFIED" SendKey work needs reconciliation (likely shared-codebase remnant; 60E32000 has different code at
  0x58592).
