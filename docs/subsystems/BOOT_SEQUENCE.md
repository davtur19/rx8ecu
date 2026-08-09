# Boot Sequence — RX-8 PCM (60E1D400)

**Status:** Verified against raw ROM bytes + `tools/extract_func.py` disassembly.
C lifts in `c/`: `reset_handler.c`, `boot_entry.c`, `init_main.c`.

## 1. Boot Chain Overview

```
Power-on / reset
   ▼
[0x0000] = 0x8B8  Manual_Reset (reset vector / initial PC)
[0x0004] = 0xFFFFDFA0            (initial SP)
   ▼
Manual_Reset (0x8B8): bsc_init (0x8CC) → gpio_init (0x8F6) → resetHandler(0,0) @0x4E0
   ▼
resetHandler (0x4E0): resetWatchdog? (0x572) → hw_init_1/2/3 (0x0170/0x041C/0x03D4)
   → cold/warm detection (magic 0x5AA5A55A @0xFFFFDFFC) → (cold) checkWatchdogTimer_OVRCOUNT(7) @0x5B0
   → reset-vector selection: [0x1000]=0x12B4 | [0x7FFF8]=0xD49C | 0x6C8
   → store magic 0x5AA5A55A -> [0xFFFFDFFC]
   ▼
vector_trampoline_set_sp (0x40): SP=0xFFFFDFA0, jmp @r4
   r4 = 0x6C8 (default)  boot/serial dispatch loop
   r4 = [0x1000]=0x12B4  app entry -> secondary_boot_init (0x1038)
   r4 = [0x7FFF8]=0xD49C main entry  -> secondary_boot_main (0xA038)
```

App's real entry point is **0xD49C**, reached through `[0x7FFF8]`. The `0x12B4` → `0x1038` path is the ROM-ID-checked alternate: validates string `"60E1D400"` (through `[0x7FFFC]=0x2000`) then routes through the same trampoline to 0xD49C. The `0x6C8` default is the bootloader serial dispatch loop (SCI → command bytes → handler), that is the flash/service path.

## 2. Verified Vector Table (@0x0000)

| Offset | Value | Meaning |
|--------|-------|---------|
| 0x0000 | `0x8B8` | `Manual_Reset` (initial PC) |
| 0x0004 | `0xFFFFDFA0` | Initial SP |
| 0x0008 / 0x000C | `0x8B8` / `0xFFFFDFA0` | Reserved copies |
| 0x0010–0x0034 | `0x8B4` | General exception / illegal instruction trampoline |
| 0x0038–0x003C | `0xFFFFFFFF` | Unused |

### Boot-handshake literals (ROM tail + RAM)

| Address | Value | Meaning |
|---------|-------|---------|
| `[0x7FFF8]` | `0xD49C` | Main app entry (used by resetHandler recovery + 0x1038) |
| `[0x7FFFC]` | `0x2000` | Pointer to ROM-ID string `"60E1D400"` |
| `[0x1000]` | `0x12B4` | App entry (ROM-ID-checked path) |
| `[0x2000..]` | `"60E1D400"` | ROM identifier string (checked for `0xFF` sentinel) |

## 3. Manual_Reset (0x8B8)

62 bytes, called directly from the reset vector:

```
0x8B8  bsr 0x8CC   ; bsc_init  — BSC/SDRAM controller setup (0xF70A, 0xED18 polls)
0x8BC  bsr 0x8F6   ; gpio_init — GPIO port init (0xF720 block, same layout as 0x12BE)
0x8C0  mov.w [0x99C],r3  ; r3 = 0x04E0 (resetHandler)
0x8C4  jsr @r3     ; resetHandler(0, 0)  r4=0 (cold), r5=0 (reason)
0x8C8  bra 0x8C8   ; infinite loop (should not return)
```

`bsc_init` (0x8CC): writes 15→0xEC20, 0xFFFF→0xEC22/0xEC24, 0x3C04→0xF70A, 0→0xED18, then polls bit 0x8000 of 0xED18 (SDRAM/refresh ready).

`gpio_init` (0x8F6): configures the 0xF720 GPIO block — ports at offsets 0x0/0x2/0x4/0x6 (data/direction) and 0x10/0x12/0x14/0x16 (control), values 0xFFFF/0/EFFF/0x9000/0x3EFF/0x2000 — identical structure to `atu_configure_all_channels` (0x12BE). Also writes 31→0xF73E, 5→0xF73C.

## 4. resetHandler (0x4E0) — reset / init dispatcher

Verified C lift: `c/reset_handler.c`.

```
0x4E0  add #-8,r15              ; frame: [fp+4]=cold_start, [fp+0]=reason
0x4E6  bsr 0x572                ; resetWatchdog? — WDT magic
0x4EA  jsr @[0x586] = 0x0170    ; hw_init_1 — clock/PLL/FRT
0x4F2  jsr @[0x588] = 0x041C    ; hw_init_2 — memory controller/BSC
0x4F8  jsr @[0x58A] = 0x03D4    ; hw_init_3 — peripherals
0x4FC  r3 = cold_start ; tst ; bf 0x556   ; non-zero -> warm path
0x502  magic = 0x5AA5A55A @ 0xFFFFDFFC
0x50C  bsr 0x5B0 with r4=7       ; checkWatchdogTimer_OVRCOUNT(7)
0x516  (no WDT ovf) r14=0, r13=0x6C8     ; not recovered -> default vector
0x520  (recovered) [0x7FFFC] != 0xFF && [[0x7FFFC]] != 0xFF  =>  r13 = [0x1000]
         else retry watchdog, r13 = [0x1000] or [0x7FFF8]
0x556  (warm path) reason -> [0xDFA8], gpio_init (0x8F6)
0x562  [0xFFFFDFFC] = 0x5AA5A55A           ; boot-OK magic
0x56A  jsr @[0x594] = 0x0040 with r4 = r13 ; vector_trampoline_set_sp
```

### resetWatchdog? (0x572)

```
0x572  [0xEC12] = 0x5A1F     ; WDT control write (WTCSR-style magic)
0x57C  [0xEC10] = 0x5A00     ; WDT counter write (0x5A1F - 31)
0x584  [0xEC10] = 0xA53C     ; refresh value written in rts delay slot
```

> **Correction (this session):** earlier draft of `reset_handler.c` read the call target from `*(uint16_t*)0x596` (=0x5A1F, a *WDT write magic*). This value is NOT code. The actual call is the fixed `bsr 0x572`; the literal @0x596 is a WDT data word. Fixed in `c/reset_handler.c`.

### checkWatchdogTimer_OVRCOUNT (0x5B0)

Returns non-zero if the watchdog overflowed (distinguishes a watchdog-induced reset from a genuine cold start). 62 bytes, verified.

## 5. Boot continuation (0x6C8) — serial dispatch loop

Default reset vector when no app entry is found. Sets WDT `[0xDFB8]=0`, then loops on the SCI receive path: setup jsr 0x364/0x3E0/0x3B0, reads a byte, masks with 0xF8, dispatches:

| Masked byte | Handler |
|-------------|---------|
| 0xA8 / 0x98 | bsr 0x806 / bsr 0x7C0 |
| 0x88 / 0x90 | jsr 0x4C (`r10`) / jsr 0x64 (`r9`) |
| 0xA0 / 0xB0 / 0xC0 | jsr 0x7C (`r8`) / jsr 0x8A (through [0x7B8]) / jsr 0xC0 (through [0x7BA]) |
| (fallback) | if `[r4]==0xFF && [r5]&0xF8==0xC8` → jsr 0xD8 (through [0x7BC]) |
| else | loop tail: jsr 0x31C, bra 0x6DE |

This is the **flash/service bootloader** protocol loop, separate from the app's RTOS. Not further traced.

## 6. App entry (0x12B4) and secondary_boot_init (0x1038)

```
0x12B4  jsr 0x1038 (r4=0)    ; secondary_boot_init(0)
0x12BA  bra 0x12BA           ; infinite loop (app entry never returns)
```

`secondary_boot_init` (0x1038, 104 bytes):

```
0x1038  jsr 0x10A0             ; early init
0x103E  jsr 0x1380             ; resetWatchdog? (symbol name)
0x1044  jsr 0x10AC             ; early init 2
0x104A  jsr 0x1720 (r4=r14)    ; early init 3
0x1050  tst r14 ; bf 0x106A    ; r14 != 0 -> skip ROM-ID check
0x1054  [0x7FFFC] != 0xFF ??   ; (0x2000)
0x105C  [[0x7FFFC]] != 0xFF ?? ; ("60E1D400" first longword)
0x1064  r14 = [0x7FFF8] = 0xD49C      ; main entry!
0x106A  jsr 0x12BE             ; atu_configure_all_channels (0xF720 block)
0x1072  jsr 0x1094 (r4=r14)    ; set_sp_and_jump trampoline
```

### set_sp_and_jump (0x1094) / vector_trampoline_set_sp (0x40)

Same pattern — set SP then tail-jump: `0x40` `mov.l [0x48],r15` (SP=0xFFFFDFA0) → `jmp @r4`; `0x1094` `mov.l [0x109C],r15` → `jmp @r4`.

### atu_configure_all_channels (0x12BE)

ATU channel config on the 0xF720 SFR block: ports 0xF720/0xF722/0xF724/0xF726 and 0xF730..0xF73E — same layout as `gpio_init` (0x8F6).

## 7. Main entry (0xD49C) — the real app start

Verified C lift: `c/boot_entry.c`.

```
0xD49C  ldc r3,vbr            ; VBR   = [0xD558] = 0x0007FC50
0xD4A2  lds r2,fpscr          ; FPSCR = [0xD55C] = 0x00040001  (FPU on)
0xD4A8  jsr 0x4C7A (r4=[0xD9C8]) ; stack_frame_set_sp: SP = [0xD9C8] = 0xFFFF7304
0xD4AC  jsr 0xA038             ; secondary_boot_main — never returns
0xD4B2  bra 0xD4B2             ; infinite loop (idle)
```

`stack_frame_set_sp` (0x4C7A): 2 bytes, `rts` w/ delay `mov r4,r15`. Sibling `stack_frame_restore_sp` (0x4C76): `mov r15,r4; rts`.

### secondary_boot_main (0xA038)

```
0xA038  jsr 0x4C80         ; peripheral_init_chain_A
0xA040  jsr 0xD7B0         ; secondary_peripheral_initializer
0xA046  bsr 0xA0DC (r4=0)  ; sfr_write_a16c: [0xFFFFA16C] = 0
0xA04C  jsr 0x2054 (r4=r15, r5=0xE0) ; setSR_PARAM — SR |= 0xE0 mask
0xA054  jsr 0x4BBC (r4=0xF74E, r5=8, r6=1) ; setRegister_REG_BIT_VAL
0xA05C  jsr 0x2064 (r4=r15) ; loadStatusRegister_ADDR
0xA062  jsr 0x4CF8         ; sfr_init_dma_channels
0xA068  jsr 0x3AD8 (r4=0)  ; task_context_switch(0) — RTOS start!
0xA06E  bra 0xA06E         ; infinite loop (idle)
```

(0xA072 onward is a separate warm-restart sibling: SR mask, re-runs the 0xF74E bit-set, then a 0x1388×0x239C multiply + port-B mask path. Not part of cold boot.)

### peripheral_init_chain_A (0x4C80)

`sts.l pr,@-r15` → bsr 0x5292 → `[0xED18] = 0xFF` → bsr 0x4DF6 (ubc_breakpoint_config_init) → bsr 0x4E16 → bsr 0x4E74 → bsr 0x4FDE → … (continues through 0x4CBA).

## 8. RTOS start — task_context_switch (0x3AD8) → init_main (0x3E10)

C lifts: `c/boot_entry.c` (0x3AD8), `c/init_main.c` (0x3E10).

```
task_context_switch(r4 = task_id):
0x3AD8  r0 = [0x4B00]            ; task count (byte) = 0x01
0x3ADE  exts.b r4 ; cmp/hs        ; task_id >= count ?
0x3AE2  rts (r0=0)               ; invalid -> return 0
0x3AE6  stc.l sr,@-r15 ; sts.l pr,@-r15   ; save caller ctx
0x3AEC  [0xFFFF72D8] = r15       ; save caller SP
0x3AF2  ldc [0x4B04]=0x00B0,sr   ; kernel SR
0x3AF8  r15 = [0x4938] = 0xFFFF719C ; kernel stack
0x3AFC  [0xFFFF72B0 + 8] = 0x100 ; RTOS control-block magic
0x3B00  jmp 0x3E10               ; tail-jump -> init_main
```

`init_main` (0x3E10) builds the RTOS control block at **0xFFFF72B0**:

| CTL offset | Source | Value |
|-----------|--------|-------|
| +0x10 (initial SR) | `[0x4B04]` | 0x00B0 |
| +0x01 (mode) | r4 | 0 (cold) |
| +0x0C (ram base) | `[0x4938]` | 0xFFFF719C |
| +0x04 (field) | — | 0xFFFF |
| +0x18 (task config) | `0x4990` | task config table |
| +0x14 (field) | `[[0x4990]+4]` | copied |
| +0x08 | — | 0x100 (from 0x3AD8) |

then chains: task_queue_init (0x3964) → task_table_scan_init (0x3EC0) → task_dependency_handler (0x3F10) → task_set_current_ptr (0x3AC0) → nullsub_2/1 → clear_task_flag_dc/dd (0x3F90/0x3F9C) → (if `[0x4B14]≠0`) task_flag_run_A (0x3588) → nullsub_3 → **task_full_context_save (0x3C2A)**; it enters the scheduler (see `docs/subsystems/RTOS_SUBSYSTEM.md`).

## 9. Warm restart path (0xD4B6)

Symbol `main??` — actually a warm-restart/validation routine, called from the 0x64E0 RTOS task:

```
0xD4B6  bsr 0xD4FA    ; validate: DBCC table via placeCANRX (0x99C4)
                        ;   + validate_data_block_header (0x636) on 0xFFFFA3E8
0xD4BE  r14 = result ; cmp #-1  ; -1 -> skip restart
0xD4D2  [0xFFFF9F8C] == 1 ?     ; restart gate flag
0xD4DE  SR &= 0xFF0F ; SR |= 0xF0 ; set interrupt mask
0xD4EC  jsr 0x4E0 (r4=1, r5=result) ; resetHandler(1, reason) — warm restart
0xD4F0  bra 0xD4F0
```

The ECU re-enters `resetHandler` in **warm mode** (cold_start=1) after validation, matching the warm path in `reset_handler.c` (reason → 0xDFA8, gpio_init, magic store, trampoline exit).

## 10. Key RAM / SFR values (this boot path)

| Address | Value | Used by |
|---------|-------|---------|
| `0xFFFFDFFC` | 0x5AA5A55A | resetHandler boot-OK magic |
| `0xFFFFDFA0` | — | trampoline SP (0x40, 0x1094) |
| `0xFFFF7304` | — | main_entry system SP (through [0xD9C8]) |
| `0xFFFF719C` | — | RTOS kernel SP ([0x4938]) |
| `0xFFFF72B0` | — | RTOS control block base |
| `0xFFFF72D8` | — | task_context_switch SP save slot |
| `0x0004B00` | 0x01 | task count (byte) |
| `0x0004B04` | 0x00B0 | kernel SR restore value |
| `0x0004B14` | — | gate for task_flag_run_A in init_main |
| `0xFFFFA16C` | 0x00 | sfr_write_a16c |
| `0xFFFFA3E8` | — | data-block header check (warm restart) |
| `0xFFFF9F8C` | 0x01 | warm-restart gate |
| `0xDFA8` | — | warm-start reason store |

## 11. Verification notes

- All addresses/literals resolved from raw ROM (`roms/stock/60E1D400.bin`, 512 KB, big-endian) with `tools/extract_func.py` / `tools/disasm_sh2e.py`.
- `init_main.c` re-verified this session: prologue `sts.l pr,@-r15; mov r4,r0` and all 8 literal targets (0x4B04/0xFFFF72B0/0x4938/0x4990/0x3964/0x3EC0/0x3F10/0x3AC0) match.
- `reset_handler.c` fixed (WDT call target bug, §4) and exit path re-annotated with the verified 0x40 trampoline.
- New: `c/boot_entry.c` (0xD49C entry + 0xA038 second-stage + 0x3AD8 RTOS start), compiles clean with host gcc -Wall.

### Remaining open items

1. 0x6C8 bootloader command handlers (0x4C/0x64/0x7C/0x806/0x7C0/0x3E0/0x3B0) not individually traced.
2. `peripheral_init_chain_A` (0x4C80) inner calls 0x5292/0x4E16/0x4E74/0x4FDE and `secondary_peripheral_initializer` (0xD7B0) internals not yet named.
3. Warm-restart validation chain: what `placeCANRX(0xDBCC)` + `0x636` actually validate (DBCC looks like a CAN config table, not a checksum — the earlier "checksum" label was wrong; see `validate_data_block_header` @0x636).
