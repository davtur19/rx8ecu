# Findings

## CORRECTION: fcmp/gt operand order (the old "emulator bug fix" note was FALSE)
- The emulator's `fcmp/gt` semantics in `tools/sh2emu.py` — T = 1 iff **FRn > FRm**
  (code `f[n] > f[m]`) — were ALWAYS correct and match the Renesas SH-2E manual,
  Ghidra's SuperH4 sleigh, and QEMU's sh4 translate.c (`fcmp/gt Fm,Fn` → `f[n] > f[m]`).
- The previously recorded "operand order bug fix" was NEVER made: `tools/sh2emu.py`
  was not changed, and the old note described the OPPOSITE of the hardware.
- The real bug was in the test/C-model expectations: `calc_lambda_integration_time`
  (0x1418C) does `fcmp/gt fr2,fr3` with fr3=2.5 (threshold) and fr2=signal, so
  T=(2.5 > signal); `bt` → countdown when signal < 2.5, fall-through → reload to 7
  when signal >= 2.5. The old tests/C model had the branches inverted.
  Fixed 2026-07-31: test_o2_lambda.py expectations + o2_lambda_subsystem.c.

## On‑chip RAM Address Sign‑Extension
- `mov.w @(disp,PC),Rn` on SH-2E sign-extends the 16-bit loaded value. Addresses ≥0x8000 (bit 15 set) become 0xFFFFxxxx.
- Many on-chip peripheral RAM variables in the RX‑8 ECU (0xA760..0xB5AC range) require this sign-extension for correct access.
- **Test pattern:** Always use `0xFFFFxxxx` in test RAM setup for addresses with bit 15 set.

## Test Suite: 11/11 Passing
- `test_getRearO2Voltage` (3 cases) — ADC-to-voltage conversion
- `test_write_o2_sensor_trim` — status byte copy via sign-extended address
- `test_read_o2_sensor_voltage_trim` (3 cases) — counter increment/saturation
- `test_calc_lambda_integration_time` (3 cases) — countdown, reload, zero
- `test_calc_closed_loop_fuel_status_basic` — STFT computation entry

## Track-A Verification (2026-07-31)

### 8 Functions Verified (emulator + C host tests)

| Function | Address | Method | Coverage |
|----------|---------|--------|----------|
| `dtc_data_read_60F58` | 0x60F58 | Emulator | 500 random |
| `shift_right_8_r0` | 0x467A | Emulator | 1K+12 edge |
| `least_square_0x5687A` | 0x5687A | Emulator | 1.3K+256 edge |
| `task_flag_run_C` | 0x35EE | Emulator | 20+ edge |
| `memcpy_bytewise_unroll4` | 0x42B0 | Emulator | 500+18 edge |
| `div32_signed` | 0x3FE8 | C host | 100K+26 edge |
| `mod32_signed` | 0x4144 | C host | 100K+22 edge |
| `checkFloatValidity` | 0x46CC | C host | 16 IEEE 754 edge |

## Track-B Verification (2026-07-31, session 6)

### 12 Functions Verified (ROM emulator, sh2emu.py)

| Function | Address | Coverage |
|----------|---------|----------|
| `purge_valve_control` | 0xF534 | 5000 random |
| `purge_valve_control_sub` | 0xF544 | 3000 random |
| `purge_valve_control_sub2` | 0xF5B4 | 4000 random |
| `purge_valve_control_sub3` | 0xF5DC | 6000 random |
| `calc_fan1_control` | 0x303A6 | 12400 random |
| `cooling_fan_control` | 0x17DCC | 15400 random |
| `radiator_fan_relay_write` | 0x259C0 | exhaustive+3000 |
| `aux_fan_control_task` | 0x1AED2 | 6000 random |
| `alternating_sensor_sm_08` | 0x5D3E8 | 20000 random |
| `ssvControl` | 0x225C8 | 12000 random |
| `vis_intake_control` | 0x23718 | 10000 random |
| `3dLookup` (type=8 u16 path) | 0x20DC | 4000 random |
| `alternating_sensor_sm` (2nd inst) | 0x5D800 | 20000 random |
| `alternating_sensor_sm` (3rd inst) | 0x5D34C | 20000 random |
| `vfad_control_35BBC` | 0x35BBC | 10000 random |
| `port helpers` (0x3EE58/0x3EE68/0x3920) | — | 9000 random |

- `3dLookup` (0x20DC): 28-byte descriptor (+0 count_x u16, +2 count_y u16,
  +4 axis_x ptr, +8 axis_y ptr, +12 values ptr, +16 type, +20 scale, +24
  offset). Type jump table @0x210C: [0x253C f32, 0x25C8 u8, 0x25F4 u16,
  0x256C s8, 0x2598 s16]. Verified for type=8 (u16) and previously type=16.
  axis_search @0x2624 clamps both ends (x<axis[0] -> (0,0.0),
  x>=axis[last] -> (last,0.0)) and interpolates in between; all arithmetic
  must be f32 (ts() per FPU op) — using unrounded doubles caused ulp
  mismatches.
- `vis_intake_control` (0x23718): 3D lookup select via RAM8[B33C/B33D/B33E]
  -> desc 0x6AC60/0x6AC7C/0x6AC98/0x6ACB4 (all 21x18, type=8 u16, scale
  1/327.68); result clamp [0,84] via 0x2404; 12-deep rolling history buffer
  @RAM[FFFFB408..FFFFB43C]: t[0]=t[1]=t[13]=clamped, t[2..12]=old t[1..11]
  (loop reads old cells then shifts down). Counter idx RAM8[B45C]=0 in stock
  (cal byte 0x73F68==1); the B5C8-derived idx path is dead.
- `fpu_compare_and_select` (0x2404) = clamp(value, lo, hi), NOT a comparator.
- `ssvControl` (0x225C8): hysteresis on>=200/off<197 (ROM 0x72F74=200.0,
  0x226D4=-3.0), counter RAM16[B322] reload 188 (ROM16 0x72F72) on mode
  transition else decrement, enable = BF39==1 || (mode==0 && cnt>0 &&
  cmd==0), calls alternating_sensor_sm_08, sets RAM16[F754] bit 0x80, stores
  mode to RAM[B325].
- `alternating_sensor_sm_08` (0x5D3E8): mask=RAM8[0x6021C], ptr=RAM32[0x60220];
  input=1 and counter==7 -> RAM[D387]=RAM16[D352]>>8; out==0 -> ret=r4;
  out in {5,7} -> ret=1 if RAM[D387]==1 else 0; else ret=r4. Writes RAM[D354]
  to *ptr.
- `alternating_sensor_sm_5D800` (0x5D800): second instance, base 0x60254,
  mask=RAM8[0x6025C] (ROM 0xC0), ptr=RAM32[0x60260], magic 0x17C8 (ROM
  0x5D8BC), flag RAM8[D38F]. NOTE: the `r6 += 0x1E` in the bf/s delay slot
  executes in BOTH branches, so the out==0 write always lands on D38F; the
  r6 default 0xFFFFD371 is never written.
- `alternating_sensor_sm_5D34C` (0x5D34C): third instance (symbol name
  diagMeteringPumpPositionControl, unconfirmed), base 0x60204,
  mask=RAM8[0x6020C] (ROM 0x40), ptr=RAM32[0x60210], magic 0x172D (ROM
  0x5D448), latch RAM8[D385]. RAW variant: out==0 stores the raw r4 (not
  (r4==1)) in D385; out in {5,7} returns the raw D385 (not (D385==1)).
- `vfad_control_35BBC` (0x35BBC): stock VFAD solenoid control computing status
  word F754 bit 0x0400 (the mod's CAN_EmitLaunchStatus @0x57BE8 reads this bit as
  "launch active"; the map labels B5B8 "RPM_Float_B5B8"). RPM-threshold
  hysteresis cmd = 1 if x>=5250.0 (ROM 0x7A5AC), 0 if x<5062.0 (=5250-188,
  ROM 0x7A5B0), hold old RAM8[C234] in band; sm(0x5D800) -> RAM8[C234] +
  F754 bit 0x0400 (via 0x4BBC). 2026-08-01 audit: the interim
  "launch_status_bit0400" name was the mod-era misnomer — this IS the stock
  VFAD solenoid control (reads VFAD open-threshold + hysteresis cal, sets
  F754 bit 0x400); stock has NO launch control, the [REDACTED] mod repurposes
  that bit.
- fcmp/gt operand order: the emulator computes T = FRn > FRm (code
  `f[n] > f[m]`), so disassembly `fcmp/gt fr4,fr6` = "5250 > boost". The
  FINDINGS note "fcmp/gt Fm,Fn compares Fm > Fn" is misleading — trust the
  emulator code.
- `aux_fan_control_task` (0x1AED2): boost filter RAM[C008] (0.7, eps 1e-5,
  firstOrderFilter @0x32F42) -> delta control RAM[BD3C]=(C008-BD40)*15.625
  (@0x2DD6E) -> error filter RAM[BD38] (0.5, 1e-5, @0x2DD88) -> fixed 6-copy
  float swap (@0x344FE) -> pressure hysteresis on RAM[B5B8] (>=7000 flag1,
  <6500 flag0, thresholds ROM 0x7A18C/0x7A190) -> flag transition writer
  (@0xC2E6: A384=0xFF, A385=0, A324=0, A38C=flag on change only).

### SH-2E Division
- Signed 32-bit division uses div0s/div1 step algorithm producing C99-style truncating-toward-zero division
- `dividend / divisor` in C is the correct semantic lift
- No hardware divide instruction — software 32-iteration loop
- INT32_MIN / -1: SH-2 returns INT32_MIN (wrapping); C has undefined behavior

### Hardware Register Writes in C Lifts
- Several verified functions write diagnostic codes to 0xFFFF7304
- These writes are commented out in C lifts for host compilation (would segfault)
- Emulator tests run the actual ROM bytes and validate the writes

### Emulator gaps (sh2emu.py)
- `0x440E` `ldc r4,SR` — **implemented** (verified: sh2emu.py decodes the
  0x4n0E family as `ldc Rn,SR`, SR ← r4). Used as the rts delay slot in
  0x3920 and 0x3934; the delay path sets SR from r4 (no memory write).
  Verified return values are unaffected (0x3920 always returns
  sr & 0xF0 = 0xF0).

## Remaining Analysis Targets
- `omp_control_task_1825E` (0x1825E) — OMP/waveform control task (756 B) —
  **LIFTED + emulator-verified** (`c/omp_task_0x1825E.c`,
  `test_omp_task_0x1825E.py`, 150000+ inputs, 0 mismatches). Call
  chain mapped (session 6): 0x1825E -> {0x3EE58*, 0x3ED3C, 0x2478
  (addSaturate8Bit), 0x18860 (omp_waveform_state_machine_18860), 0x189EE
  (rotor_sync_position_detector), 0x18C08 (omp_diag_rotor_18C08),
  0x18C5C (waveform_state_transition), 0x18C6C (omp_wave_reload_18C6C)};
  those -> {0x18552 (omp_stepper_waveform_driver), 0x9668, 0x3F050 ->
  0x3ED7C/0x3EE68/0x60D54/0x2620E, 0x3ED3C -> 0x3920*/0x3934 -> 0x3DB0 ->
  0x35EE/0x3BF4}. * = verified this session. Reads RAM cluster A968..A98B +
  9ECD bit2 + CD06 + 78E35/36/37; writes ports 0xFFFF8078/807A/807C via
  complementary-encoded helpers (0x3EE58/0x3EE68: v = (b<<8)|~b).
- `exhaust_oxygen_control_19480` (0x19480) — heater/sensor state machine
- `calc_secondary_o2_trim` (0x1321C) — secondary sensor trim
- `calc_lambda_feedback_pid` (0x11A34) — serial sub‑call chain (14+ functions)
- `calc_fuel_trim_correction_map` (0x136F0), `calc_fuel_trims_adaptive` (0x117B4)
- `consistencyCheck` (0x3A28) — C code written, emulator test pending
- `atu_fpu_control_wrapper` (0x70AC) — C code written, integration test pending
- `task_full_context_save` (0x3BF4) — C code written, assembly simulation pending

### bitfield_extract_merge @ 0x48C8 (60E1D400; identical code in 60E0FC00)
- frexp-style float decomposition: x = sig * 2^e, sig in [1,2); single caller is checkFloatValidity @0x46CC (call site 0x46D8), which feeds both output words into mul16_signed_saturated @0x4740 as stack args.
- Calling convention: float arg in FR4; result pointer at [r15] pushed by caller in the jsr delay slot (`mov.l r15,@-r15`); writes out[0]=exponent word, out[1]=significand word.
- out[0]: bit31 = sign (except NaN), low16 = signed exponent; 0x8001 sentinel for 0.0, 0x7FFF saturated for Inf/NaN.
- out[1]: 24-bit significand << 8 (bit31 = implicit leading 1); 0xFFFFFFFF for NaN, 0 for zero/Inf.
- NaN DROPS its sign (ROM zeroes r2 at 0x4924); ±Inf keep sign (path preserves r2). Subnormals normalized to [1,2), e in [-149,-127].
- IDA/Ghidra listings mis-decode the tail: at 0x4922 the raw bytes are `D1 03` = `mov.l @(.lit2,pc),r1` (load 0x7FFF), NOT `mov #0,r2`. Byte-level decode verified on both ROMs.
- Verified: emulator (sh2emu.py) vs model over 30 edge cases + 100k random bit patterns, and C lift (c/bitfield_extract_merge.c) vs emulated ROM — 0 mismatches. See docs/functions/bitfield_extract_merge.md.

### Immobilizer leaf functions (Track A, verified 2026-07-31)
- `seed_mixer` @0x366B8 (pure fn of r4=key word, r5=rolling key):
  1. x = ((r4>>8)&0xFF)<<16 | ((r5&0xFF)<<8) | (r4&0xFF)
  2. x = (x & 0xFFE0301F) | ((x & 0x0FE0)<<9) | ((x & 0x001FC000)>>9)
  3. y = (-(x>>16)&0xFF)<<16 | (-(x>>8)&0xFF)<<8 | (-x&0xFF)   (byte-wise 2's complement)
  4. z = (y<<21) | (y>>3)
  5. result = ((z&0xFF)<<16) | (((z>>8)&0xFF)<<8) | ((z>>16)&0xFF)   (byte swap 0<->2)
- `calculateImmoSeed` @0x3675C (pure fn of r4=w2DC, r5=w2E0, r6=key):
  sum16 = (r4>>16)+(r6>>16); sum32 = r4+r6; m1..m4 = 0x0D * (byte/word of sums);
  scN = ((b<<7)>>8)+(b<<7) per byte; mixes with r5 (r14=(r5>>16)^sc2, r7=sc3^(r5>>8),
  r5^=sc4, r6=sc1^(r5>>24)); branch on bit0 of mixed r5:
  odd: bytes = (r6, r14, fold4(r5), fold4(r7)); even: bytes = (fold4(r14), fold4(r6), r7, r5);
  fold4(v) = (v<<4)+(v>>4); result = b0<<24|b1<<16|b2<<8|b3.
- **Encoding gotcha (root cause of first mismatch):** SH-2E 0x6 group ALU ops are `0x6n<op>m`
  with dest n in bits 11-8 and SOURCE m in bits 3-0, so `0x6477` = `not r7,r4` (r4 = ~r7),
  NOT `not r4` (r4 = ~r4). Same for neg/swap/extu/exts. disasm_sh2e.py now prints src,dst.
- Both verified: C lifts (c/seed_mixer.c, c/calculateImmoSeed.c) == emulated ROM over
  100k random inputs each (make c-emu, FUNCS registry in c/tests/verify_emu.py).
- ImmoKeyExpander_365D6 @0x365D6: slot i = seed_mixer(w2E0/w2DC shifts, key shifts),
  stored |0x01000000..0x04000000 into 0xFFFFC260..26C. ImmoGetSeed_3664E @0x3664E calls
  calculateImmoSeed(w2DC, w2E0, key) -> IMMO_SEED_OUT.

## Boot sequence (60E1D400, verified 2026-07-31 against raw ROM + disasm)

- **Reset vector** @0x0000 = 0x8B8 `Manual_Reset`; initial SP @0x0004 = 0xFFFFDFA0.
  Manual_Reset -> bsc_init (0x8CC) + gpio_init (0x8F6) -> resetHandler(0,0) @0x4E0.
- **Main app entry is 0xD49C** (ROM longword @0x7FFF8), NOT 0xD4B6. 0xD49C:
  VBR=0x7FC50, FPSCR=0x40001, SP=[0xD9C8]=0xFFFF7304 via stack_frame_set_sp (0x4C7A
  = `rts/mov r4,r15`), then secondary_boot_main (0xA038), then infinite loop.
- **App entry chain**: [0x1000]=0x12B4 -> jsr 0x1038 `secondary_boot_init` (r4=0);
  0x1038 checks [0x7FFFC]=0x2000 and [[0x7FFFC]] (ROM-ID string "60E1D400" != 0xFF),
  sets r14=[0x7FFF8]=0xD49C, calls atu_configure_all_channels (0x12BE), then
  set_sp_and_jump (0x1094): SP=0xFFFFDFA0, jmp @r4 -> 0xD49C.
- **Trampolines** 0x40 and 0x1094 are identical: `mov.l [lit],r15` (SP=0xFFFFDFA0)
  + `jmp @r4`. resetHandler exits via jsr @[0x594]=0x40 with r4=r13 (chosen vector).
- **resetHandler (0x4E0) verified** (matches c/reset_handler.c): bsr 0x572
  (resetWatchdog?), hw_init_1/2/3 (0x170/0x41C/0x3D4), magic 0x5AA5A55A @0xFFFFDFFC
  cold/warm split, checkWatchdogTimer_OVRCOUNT(7) @0x5B0, vector select
  [0x1000]=0x12B4 | [0x7FFF8]=0xD49C | default 0x6C8, store magic, exit via 0x40.
- **reset_handler.c bug fixed**: WDT_RESET_ADDR was `*(uint16_t*)0x596` (=0x5A1F,
  a WDT *write magic*), called as code. Real target is fixed 0x572. Also the
  BOOT_CONT literal 0x594 = 0x0040 = vector_trampoline_set_sp (not "0x5A1F main init").
- **secondary_boot_main (0xA038)**: peripheral_init_chain_A (0x4C80: 0x5292,
  [0xED18]=0xFF, ubc_breakpoint_config_init 0x4DF6, ...), secondary_peripheral_initializer
  (0xD7B0), sfr_write_a16c (0xA0DC: [0xFFFFA16C]=0), setSR_PARAM (0x2054, 0xE0 mask),
  setRegister_REG_BIT_VAL (0x4BBC: 0xF74E bit8), fpu_nop_stub (0x2064),
  sfr_init_dma_channels (0x4CF8), task_context_switch (0x3AD8, r4=0), idle loop.
- **task_context_switch (0x3AD8)**: valid if task_id < [0x4B00] (task count byte=1);
  saves SR/PR + SP -> [0xFFFF72D8]; SR=[0x4B04]=0xB0; SP=[0x4938]=0xFFFF719C;
  [0xFFFF72B0+8]=0x100; tail-jmp 0x3E10 (init_main). Sibling @0x3B08 restores SP
  from 0xFFFF72D8 + rte.
- **init_main (0x3E10) re-verified against real disasm** — c/init_main.c is
  correct: prologue `sts.l pr,@-r15; mov r4,r0`; literals 0x4938/0xFFFF72B0/0x4B04/
  0x4990/0x3964/0x3EC0/0x3F10/0x3AC0/0x3F8C/0x3F88/0x3F90/0x3F9C/0x4B14/0x3588/
  0x3FA8/0x3C2A all match. Caller is task_context_switch (0x3AD8), not "after
  hw_init chain" — init_main.c header corrected.
- **0x6C8 boot continuation** = serial dispatch loop (flash/service bootloader):
  byte&0xF8 matches 0xA8->bsr 0x806, 0x88->jsr 0x4C, 0x90->jsr 0x64, 0x98->bsr 0x7C0,
  0xA0->jsr 0x7C, 0xB0->jsr 0x8A, 0xC0->jsr 0xC0; fallback [r4]==0xFF &&
  [r5]&0xF8==0xC8 -> jsr 0xD8; loop tail jsr 0x31C. Handlers not traced.
- **0xD4B6 warm restart** (symbol `main??`, called from 0x64E0 RTOS task):
  bsr 0xD4FA (validate via 0x99C4 `placeCANRX` with DBCC table @0xDBCC + 0x636
  `validate_data_block_header` on 0xFFFFA3E8); if ok and [0xFFFF9F8C]==1:
  SR &= 0xFF0F | 0xF0 (mask), resetHandler(1, result) warm restart, idle loop.
  NOTE: 0x99C4 is the CAN receive path, NOT a checksum — earlier "DBCC checksum
  check" label was wrong.
- New C lift: c/boot_entry.c (0xD49C + 0xA038 + 0x3AD8), compiles clean (-Wall).
- New doc: docs/subsystems/BOOT_SEQUENCE.md (full chain, vector table, RAM/SFR values).
- RTOS_SUBSYSTEM.md corrected: "bsr 0x594 -> 0x5A1F" was wrong (0x5A1F is a WDT
  write value); verified exit is jsr @0x0040 vector_trampoline_set_sp.

## DTC Management subsystem — Track-A verified (2026-07-31)

- **All six DTC-management functions verified** against the ACTUAL ROM bytes
  (60E1D400.bin) in tools/sh2emu.py over random RAM states; all tests pass:
  dtcRelated@0x062002 (500×8×4), dtc_handler_610FA@0x610FA (200),
  dtc_handler_61550@0x61550 (200), dtc_code_set/clear@0x46780/0x467AA (500),
  dtc_debounce_monitor_43760@0x43760 (500 incl. float gates).
- **dtcRelated out buffer is PACKED**: matches are written to
  `out[count]` (r12 = r6 + 2·r7, r7 = running count), NOT `out[i]`.
  C lift + test model fixed (was `out[i] = code`). The emulator caught this.
- **dtcRelated enable gate**: enable ∈ {0,1,2} only; 1 → tableA[code]@0x7E220
  == 1, 2 → tableB[code]@0x7E2AC == 1, anything else disqualifies the entry.
  Entry index == cur_idx@0xFFFF8928 is skipped.
- **Emulator indexed-mov verification**: `mov.b @(R0,Rm),Rn` = `0000 nnnn mmmm 1100`
  (dest bits 11-8, index bits 3-0) — matches Hitachi SH-1/SH-2 manual AND
  capstone (0x08EC = mov.b @(r0,r14),r8). No emulator bug; earlier dtcRelated
  failures were test-model big-endianness.
- **610FA dispatch**: opcode @0xFFFF87DE + idx·16; 0x50/0x00 →
  can_encode_handler_62FAC(8) → obd_service_handler_64258 (marks pending entry:
  base@0xFFFF8930 +0x34·sel, byte +7=1, +8=7, counter @+0x32) → tail-call
  obd_service_handler_63312. Other opcodes: no side effects.
- **61550 common tail**: every mode (1/2/3) stores enc result @0xFFFFD6FC,
  status @0xFFFFD6FF; if w16@0xFFFFD700 == dtc → can_encode_handler_62ABC(dtc,0x20)
  (which may update run-sum words 0xFFFF8E98/0xFFFF8E9A via 0x648B4);
  then can_encode_handler_62B24(dtc,0x20,status); tail-call obd_service_handler_632D6.
- **Debounce gate order (fcmp/gt → T = FRn > FRm)**: `if 17000.0f > accum`
  → zero B/C; `elif 500.0f > runtime` → path C (counterC++, flag2 @>=4);
  else → path B (counterB++, flag1 @>=16); else B=C=0; then
  `cond ? counterA++ (sat) : counterA = 0`. Thresholds 157/16/4 @0x7D97C/78/7A,
  float gates 17000.0 @0x7D984, 500.0 @0x7D988. (dtc_debounce_monitor_43760.c
  header corrected from the old flat `(17000>acc || 500>runtime)` gate.)
- **dtc_code_set/clear**: checksum-paired bytes (b,~b); set @0x46780 only when
  present-flag @0xFFFF8788 == 1 (readValue_8bit_ADDRESS_VAL default 1); both
  write 0 to state words 0xFFFF875C/0xFFFF875E via updateMemoryAtAddress_8bit.
- **Docs**: docs/functions/dtc_management.md (new, consolidated),
  docs/functions/dtcRelated.md (rewritten; old draft was 60E0FC00-based
  @0x5FEB6 with wrong tables 0x7C9FC/0x7CA88 — invalid for 60E1D400).

## OMP (Oil Metering Pump) stepper chain — 60E1D400 (2026-07-31)

Task entry 0x1825E (OS task table @0x18024) drives the OMP stepper through
sub-functions by state bytes. Chain verified bottom-up against the ROM emulator:

- **0x18552 omp_stepper_waveform_driver** — stepper phase table driver
  (modes 0-6), incl. sat8(A97F+A974) / A97D+2 / A98D=mode / port F746.
  Verified 60000 random inputs, 0 mismatches.
- **0x18860 omp_waveform_state_machine_18860** — 4-state machine on RAM8[0xFFFFA981]
  (0x982/0x97E/0x977/0x978 latches, ADDRESS_VAL port 8078/807C gates, float
  -40.0 sensor-validity gate — CAL_A==CAL_B==0x3C stock, so no cold
  correction is applied), drives wave(0/1/2), A97C==5 -> A97B=0x80,A981=1.
  Verified 60000 random inputs, 0 mismatches.
- **0x189EE rotor_sync_position_detector** — 5-state machine on RAM8[0xFFFFA98B]
  tracking A8F1 (old) vs A974 (new) rotor position; tail dispatches
  wave(2/3/1/4) + A97B per final state. mode arg comes from RAM8[0xFFFFA984].
  **Bug caught by emulator**: state-4 `add #0xFE,r1` SIGN-EXTENDS (0xFE = -2),
  so the gate is `(A8F1 - 2) >= A974` (signed), not `(A8F1 + 0xFE) >= A974`.
  Verified 60000 random inputs, 0 mismatches. C lift: c/rotor_sync_position_detector.c.
- **0x18C5C** — wave(6) then A97B = 8. Verified 20000.
- **0x18C6C** — A974>7: wave(3),A97B=0x10; A974==7: wave(4),A97B=4;
  A974<7: wave(2),A97B=0x10. Verified 20000.
- **0x18C08** — A980==1: write16(0x807C,1) via 0x3EE58, diag-table store via
  0x9668, A980=2; then A8F1==A974 -> A97B=0x30,A980=1, else -> 0x189EE(A984).
  OMP-RAM behavior confirmed in emulator (12/12 varied states).

Also mapped: task table @0x18000 (0x18024 -> 0x1825E, 0x1802C -> 0x18CC0
companion task); 0x1825E dispatches 0x18C6C (A998==1) / 0x18860(A985)
(A968==1) / 0x18C08 (A96A==1 && ACD06==0) / 0x18C5C (A96B==1) / 0x189EE(A984)
(A969==1), all gated on A97B countdown reaching 0.

## Disassembler decode-gap fix + rebuild integration (2026-07-31)

- **GBR-relative MOV corrected**: 0xC0/0xC1/0xC2 = MOV.B/W/L R0,@(disp,GBR)
  (STORES), 0xC4/0xC5/0xC6 = MOV.B/W/L @(disp,GBR),R0 (LOADS). Old handler
  matched only disp nib==0 and had the direction reversed. Verified vs GNU-as
  2.46: 0xC02C/0xC116/0xC20B, 0xC42C/0xC516/0xC60B. Disp fields are units
  (.b byte, .w bytes/2, .l bytes/4).
- **0x82xx/0x86xx mov.l r0,@(disp,Rm) / mov.l @(disp,Rm),r0**: register in bits
  7-4, disp nib x4. GNU-as has NO syntax for them — re-encodes as 0x1nmC/0x5nmC
  (e.g. 0x82C0 -> 0x1C00). Rebuild self-correction forces them to `.word`
  (byte-exact by construction); they decode for inspection only.
- **Control-register encodings verified**: stc SR/GBR/VBR/SSR/SPC =
  0x0n02/12/22/32/42; stc.l = 0x4n03/13/23/33/43; ldc = 0x4n0E/1E/2E/3E/4E;
  ldc.l = 0x4n07/17/27/37/47; sts mach/macl/pr = 0x0n0A/1A/2A, fpul 0x0n5A,
  fpscr 0x0n6A; lds fpul/fpscr = 0x4n5A/6A; lds.l fpul/fpscr = 0x4n56/66;
  sts.l fpul/fpscr = 0x4n52/62. Correction: 0x4n66 is lds.l fpscr (was
  mislabeled lds.l fpul); added missing sts.l fpscr 0x4n62. GNU-as accepts the
  uppercase register names.
- **bsrf/braf are register-only** (`bsrf rN` = 0x0n03, `braf rN` = 0x0n23,
  PC = PC+4+Rn). GNU-as rejects `bsrf L_x` — no label form exists.
- **div0u is operand-less** (0x0019); GNU-as rejects `div0u r0`.
- **Indexed-mov syntax fix**: GNU-as form is `mov.b r11,@(r0,r8)` (0x08B4) /
  `mov.b @(r0,r11),r8` (0x08BC), likewise mov.w/l and fmov.s (0xF217/0xF126).
- **Coverage after fix** (full ROM): 60E1D400 217,449 -> 226,408 decoded
  (86.4%); 60E0FC00 220,543 (84.1%). Code region 0x800..0x60000: capstone-only
  84.6%/84.7% -> 93.8% decoded with disasm_sh2e fallback.
- **Whole-ROM GNU-as round-trip**: every decoded word in both ROMs reassembles
  byte-exact (226,048/226,408 and 220,183/220,543); the only non-round-trippable
  words are the 360/360 82xx/86xx, which canonicalize to 0x1nmC/0x5nmC.
- **rom_rebuild.py now byte-exact with the fallback** (was already byte-exact
  with capstone-only): 60E1D400 lifts 183,120/195,584 (93.6%, 252 raw
  fallbacks); 60E0FC00 lifts 182,998/195,584 (93.6%, 377 raw fallbacks). Both
  print BYTE-EXACT.
- **organize_src.py uses capstone + its own fpu() helper, NOT disasm_sh2e.py**;
  not switched.

## .word data regions in code window 0x800..0x60000 (2026-07-31)

Confirmed facts from `analysis/data_regions_60E1D400.{csv,md}` (tool:
`/tmp/opencode/classify_word_runs.py`, deterministic):
- The annotated `.s` maps linearly from ROM offset 0; the walker reproduces
  every `L_xxxxxx` address (0 mismatches). Instruction sizes + 26,996 pcrel
  refs from the `.s` are the code oracle — **capstone SH-2 is a strict subset**
  (fails 0x0000/0x0100/0x0400/0xffff), so it cannot find missed code in the
  window. Sweeping all 1,491 runs through capstone found zero code-like
  sequences: **no undecoded_code_capstone runs exist in-window**; window is
  100% covered (93.6% instr + 6.4% .word bytes).
- Per-class (1,491 runs / 4,736 words): literal_pool 883/2,288; padding
  366/1,540; unknown_data 221/789; jump_table 18/112; string 3/7;
  calibration 0/0 (all 1,210 cal_tables.csv addresses are 0x6CF6C..0x7D92C,
  outside the window).
- **0x426C/0x4290 are genuine 32-bit dispatch tables** (17/13 words): loaded via
  the 0x4224 pool (`div_trampoline_A/B` at 0x420C/0x4218 do
  `mov.l @(r0,r3),r3; jmp @r3`). No genuine 16-bit `braf` switch tables exist
  in-window; all 4 `braf r0` sites sit inside mis-decoded data.
- **0x493C is a Renesas-style div-library 16-bit constant table** (0x0013/0xFFFF
  header + 19x (0x0000,0x0001)) referenced via pools — data, not jump table.
- **Mis-decoded-data regions in the .s** (decoded as instructions, relevant to
  disasm work): 0x84E-0x8A4, 0x85BA-0x8600, 0x8704-0x8730, 0x883C-0x8850
  (alternating garbage instr + `.word 0x0000` = 32-bit data), 0x3C8E0-0x3C91C
  (32-bit pointer table into 0x7A9xx cal region), 0x4224-0x4226 (pool holding
  the 0x426C table base).
- **Strings in-window are fragmentary**: 0x2000 holds '60E1D400' ROM-id and
  'Copr.DENSO200' (the .word runs at 0x2002/0x2028 are mis-sliced fragments
  because neighboring bytes decoded as instructions); 0x3B28 is the real
  'Copyright 1999 Hitachi,L'. 0x6CE00 'N3J1E_3W.T50' is BE-packed ASCII
  (2 chars/word), outside the window. Classifier now requires a >=12-byte
  printable span, so random 4-char fragments (e.g. "OROb") are not strings.

## Track A session 8: math_min_max_49ED0 verified + mov.w sign-extension correction

- **math_min_max_49ED0 (0x49ED0, 34B)** verified against ROM bytes in the SH-2E
  emulator (test_math_min_max_49ED0.py, 14 edge + 20000 random, 0 mismatches)
  and on the host as a C lift (test_math_min_max_49ED0.c, 20014 tests, 0
  mismatches). Semantics: `v = (RAM16[0xFFFFF76C] & 0x100) ? 1 : 0;`
  `byte@0xFFFFCD48 = v; byte@0xFFFFCD49 = v; return v` (return flag in r0).
  `make c-test` stays GREEN (7 suites).
- **CORRECTION (unblocks the low-SFR family):** `mov.w @(disp,PC)` SIGN-EXTENDS
  its literal (SH-2 semantics). The disassembler's short comments like
  `; 0xCD49` / `; 0xF76C` are truncated shorthand — with bit 15 set the real
  addresses are 0xFFFFCD49 / 0xFFFFF76C etc. So 0xCD4C, 0xD2C4, 0xD2C5,
  0xCE00/01 etc. are actually 0xFFFFCD4C, 0xFFFFD2C4, 0xFFFFD2C5,
  0xFFFFCE00/01 — all above mmap_min_addr=0x10000 and therefore host-mmap-able
  (proven: test_calc_manifold... mmaps 0xFFFFA5D4; test_math_min_max_49ED0.c
  mmaps 0xFFFFF76C/0xFFFFCD48). The earlier "below mmap_min_addr, must use
  structural tests only" blocker for this family is WRONG — host-C mmap
  companions are possible for all of them.
- Related emulator observations: unseeded reads of 0xFFFFxxxx addresses fall
  back to `rom[a] if a < len(rom) else 0` → 0 (safe); byte writes land in the
  sparse `cpu.ram` overlay at the FULL 0xFFFFxxxx key (assert on
  `0xFFFFCD48`, not `0xCD48`).

## Track A session 8 cont.: OBD DTC-table family verified (0x64258/0x64418/0x64490/0x643D4/0x6443E)

- **DTC table layout** (used by all five): base 0xFFFF8930, stride 0x34,
  **21 rows (0..0x14)** — 0xFFFF8930 + 21*0x34 == 0xFFFF8D74, which is the
  row-index word itself (so the table is bounded by its own index). Row
  indices > 0x14 wrap the pointer into ROM code (a test with row=0x211A
  landed at 0x64278 and clobbered function code → false failure). Realistic
  tests must stay within 0..0x14.
- **0x64258** (row update): `p[0x32] += p[0x07] + 0xFF; p[0x07] = 1;
  p[0x32] += p[0x08] + 0xF9; p[0x08] = 7` (byte ops). 22048 host tests OK.
- **0x64418** (row update, r4 arg): `p[0x32] = (s8(p[0x32]) + s8(p[0x08]) -
  r4) & 0xFF; p[0x08] = r4 & 0xFF`. 22560 host tests OK.
- **0x64490** (row update, r4 = 16-bit value): `w = word@p+0x02;
  delta = (s16(w) + ((w>>8)&0xFF)) - (r4 + ((r4&0xFFFF)>>8));
  p[0x32] = (s8(p[0x32]) + delta) & 0xFF; word@p+0x02 = r4 & 0xFFFF`.
  22560 host tests OK. (Uses `add.b #imm` with sign-extended bytes — same
  sign-extension family as the session-8 correction.)
- **0x643D4** (search): returns `s8(p[0x06])` for the first row whose
  `word@p == r4&0xFFFF` and `i != currow`; else 0. 5000 host tests OK.
- **0x6443E** (search): returns `s8(p[0x08])` for the first row whose
  `byte@p+0x06 == r4&0xFF` and `i != currow`; else default 0x08 (r14 is
  preloaded with 0x08). 5000 host tests OK.
- All five verified against the ROM in the SH-2E emulator first (targeted +
  random), then as host-C mmap companions with matching reference models;
  0 mismatches everywhere. `make c-test` not yet re-run after these additions
  (auto-discovers test_*.c) — run at the end of the OBD batch.

## Track A session 8 cont.: idx_table + req_queue families, setSR tail-call

- **idx_table family (0x68780/0x6879C/0x687C8/0x687F4)**: 4 packed leaves over a
  RAM table at 0xFFFFD998, stride 0x46C, byte index; called via the 0x68776
  wrapper (clear(0)) and function-pointer tables (pools 0x68CE0/0x695C0/0x695D0).
  Semantics: clear = zero 3 words; step/step2 = count-up counter
  `word@p = (word@p+4 >= 0x0464) ? 0 : word@p+4+1` (0x6879C and 0x687C8 are two
  separate ROM copies with identical logic); dec = `word@p+4 = (word@p==0) ?
  0x0464 : word@p-1`. Index arithmetic is 32-bit — indices >= 9 wrap the pointer
  to low addresses (pinned in the emulator test). **Caveat:** for indices 9..255
  the pointer leaves the 0xFFFFxxxx RAM region entirely (0xFFFFD998 + 0x46C*n
  exceeds 2^32 for n >= 9), so realistic firmware use must be indices 0..8
  (only 0..1 fit the 4KB RAM bank 0xFFFFD000-0xFFFFDFFF).
- **req_queue leaves (0x69602 store / 0x69694 clear)**: byte flag array at
  0xFFFFDE38 + parallel long array at 0xFFFFDE40. store: `long@(0xFFFFDE40+b*4)
  = (uint32)(r5 * 0x0FA0) + long@0xFFFFF430; flag = 1`. clear: flag = 0. Both
  called exclusively through function-pointer tables. The 0x69624..0x69692
  dispatcher between them (7-entry loop: calls 0x3920, dispatches via the
  0x69918 table to 0x68C82/0x68C2E/0x68C8E/0x68D20/0x68CA2/0x68D74/0x68DC0, and
  calls setSR 0x3934) is a CALLER — not lifted, per the leaf convention.
- **setSR 0x3934 tail-call branch now emulator-tested**: previously marked
  untestable; seeding the kernel struct at 0xFFFF72B0 (word@0x04 == word@0x06)
  makes 0x3DB0 take its early-exit path (bt to 0x3DF0), so the full ROM path
  setSR(0) -> flag!=1 -> jmp 0x3DB0 -> early exit executes in-emulator and ends
  with SR=0, r0=0. The 0x3BF4 context-switch write path is still NOT traced
  (it restores r15 from a RAM pointer — OS machinery). getSR (0x3920) and
  setSR_PARAM (0x2054) also verified (20000 random each). SR accessors are
  emulator-only (no host C test: the lift's SR is a private file-scoped var).
- **Fixes during verification**: (1) my initial step model had the comparison
  inverted — 0x3013 decodes as n=(op>>8)&0xF=0 (r0), m=(op>>4)&0xF=1 (r1), so
  cmp/ge r1,r0 => T=(r0>=r1), i.e. the counter RESETS when word@p+4 >= 0x0464
  (count-up), not below it. (2) host test seeding must use host-endian
  *(volatile uint16_t*) writes to match the lift, not big-endian byte writes.
  Both caught by the emulator-first workflow.
