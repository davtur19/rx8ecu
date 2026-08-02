/*
 * boot_entry.c  —  RX-8 ECU main boot entry chain (60E1D400)
 *
 * Address: 0x00D49C (main_entry) | Size: 22 bytes
 *          0x00A038 (secondary_boot_main) | Size: 58 bytes
 *          0x003AD8 (task_context_switch) | Size: 44 bytes
 *
 * The app's real entry point.  The reset vector table / boot ROM redirect
 * lands here:  ROM longword @0x7FFF8 == 0xD49C.  (0x1038 `secondary_boot_init`
 * validates the ROM-ID string "60E1D400" at [0x7FFFC] and, if valid, routes
 * r14 = [0x7FFF8] = 0xD49C through the `set_sp_and_jump` trampoline at
 * 0x1094 which sets SP = 0xFFFFDFA0 and tail-jumps.)
 *
 * main_entry:
 *   1. VBR   = 0x0007FC50      (interrupt vector base for the app)
 *   2. FPSCR = 0x00040001      (enable FPU, default rounding/exception mask)
 *   3. SP    = [0xD9C8] = 0xFFFF7304  (system stack, via stack_frame_set_sp)
 *   4. Call secondary_boot_main (0xA038) — never returns
 *
 * secondary_boot_main:
 *   - peripheral_init_chain_A (0x4C80): 0x5292, SFR 0xED18=0xFF,
 *     ubc_breakpoint_config_init (0x4DF6), 0x4E16, ...
 *   - secondary_peripheral_initializer (0xD7B0)
 *   - sfr_write_a16c (0xA0DC): [0xFFFFA16C] = 0
 *   - setSR_PARAM(0x2054): SR |= (0xE0<<0)  (set interrupt mask bits)
 *   - setRegister_REG_BIT_VAL(0x4BBC): bit 8 of SFR 0xF74E set
 *   - loadStatusRegister_ADDR (0x2064)
 *   - sfr_init_dma_channels (0x4CF8)
 *   - task_context_switch(0) — starts the RTOS (tail-jumps to init_main
 *     @0x3E10, see init_main.c) — never returns
 *
 * task_context_switch (r4 = task_id):
 *   - if task_id >= task_count ([0x4B00] == 1) -> return 0 (invalid id)
 *   - save SR/PR, current SP -> [0xFFFF72D8]
 *   - SR = [0x4B04] = 0x00B0   (restore kernel SR)
 *   - SP = [0x4938] = 0xFFFF719C (kernel stack)
 *   - [ctl+8] @0xFFFF72B0 = 0x100 (RTOS control block magic)
 *   - jmp init_main (0x3E10)  (tail call)
 *
 * Verified against ROM: tools/disasm_sh2e.py + tools/extract_func.py dumps
 * (this file, init_main.c and reset_handler.c were all checked against the
 * raw bytes of roms/stock/60E1D400.bin; literal pools resolved).
 *
 * Platform note: on the real SH-2E the CPU-register writes are
 *   ldc rX,vbr / lds rX,fpscr / ldc rX,sr / mov rX,r15 / stc.l / sts.l.
 * For host builds these are modelled with file-scoped register images,
 * following the same convention as setSR.c / getSR.c.
 */
#include <stdint.h>

/* ------------------------------------------------------------------ */
/*  Platform abstraction — CPU register images (host-side simulation)  */
/* ------------------------------------------------------------------ */

static uint32_t _vbr   = 0x00000000;
static uint32_t _fpscr = 0x00000000;
static uint32_t _sr    = 0x000000F0;   /* power-on reset default */
static uint32_t _sp    = 0x00000000;
static uint32_t _pr    = 0x00000000;

static inline uint32_t cpu_sr_get(void)        { return _sr; }
static inline void     cpu_sr_set(uint32_t v)  { _sr = v; }

/* ------------------------------------------------------------------ */
/*  ROM literals (resolved from the code's PC-relative pools)          */
/* ------------------------------------------------------------------ */

#define VBR_APP          (*(uint32_t *)0xD558)   /* = 0x0007FC50 */
#define FPSCR_APP        (*(uint32_t *)0xD55C)   /* = 0x00040001 */
#define SP_SOURCE_PTR    (*(uint32_t *)0xD560)   /* = 0x0000D9C8 */
#define SP_VALUE         (*(uint32_t *)0xD9C8)   /* = 0xFFFF7304 */

#define TASK_COUNT_PTR   (*(uint8_t  *)0x4B00)   /* = 0x01 (byte) */
#define KERNEL_SR_PTR    (*(uint32_t *)0x4B04)   /* = 0x00B0 */
#define KERNEL_SP_PTR    (*(uint32_t *)0x4938)   /* = 0xFFFF719C */
#define CTL_BLOCK        ((volatile uint32_t *)0xFFFF72B0) /* RTOS ctl blk */
#define SAVED_SP_SLOT    (*(volatile uint32_t *)0xFFFF72D8) /* caller SP save */

/* ------------------------------------------------------------------ */
/*  Function pointer helpers                                           */
/* ------------------------------------------------------------------ */

typedef void (*void_fn_void)(void);
typedef void (*void_fn_word)(uint32_t);
typedef void (*void_fn_byte)(uint8_t);

/* ------------------------------------------------------------------ */
/*  main_entry @ 0xD49C                                               */
/* ------------------------------------------------------------------ */

/**
 * main_entry  —  Application entry point after reset/boot-ROM redirect.
 *
 * Sets the interrupt vector base (VBR), enables the FPU (FPSCR), moves the
 * stack pointer to the dedicated system stack, then calls
 * secondary_boot_main which performs the peripheral init and starts the
 * RTOS.  Never returns.
 */
__attribute__((noreturn))
void main_entry(void)
{
    /* VBR = 0x0007FC50 — point interrupt vector table at app ROM area */
    _vbr = VBR_APP;

    /* FPSCR = 0x00040001 — FPU enabled, no exceptions, round-to-nearest */
    _fpscr = FPSCR_APP;

    /* SP = [0xD9C8] = 0xFFFF7304  (stack_frame_set_sp @0x4C7A: mov r4,r15) */
    _sp = SP_VALUE;

    /* secondary_boot_main(0xA038) — does not return */
    {
        void_fn_void boot = (void_fn_void)(uintptr_t)0xA038;
        boot();
    }

    /* NOT REACHED — secondary_boot_main tail-jumps into the RTOS */
    for (;;) {
    }
}

/* ------------------------------------------------------------------ */
/*  secondary_boot_main @ 0xA038                                      */
/* ------------------------------------------------------------------ */

/**
 * secondary_boot_main  —  Second-stage boot.
 *
 * Chains: peripheral_init_chain_A -> secondary_peripheral_initializer ->
 * SFR writes / SR setup -> DMA channel init -> task_context_switch(0),
 * which tail-jumps into the RTOS init (init_main @0x3E10).  Never returns.
 */
__attribute__((noreturn))
void secondary_boot_main(void)
{
    /* peripheral_init_chain_A (0x4C80) */
    {
        void_fn_void fn = (void_fn_void)(uintptr_t)0x4C80;
        fn();
    }

    /* secondary_peripheral_initializer (0xD7B0) */
    {
        void_fn_void fn = (void_fn_void)(uintptr_t)0xD7B0;
        fn();
    }

    /* sfr_write_a16c(0): [0xFFFFA16C] = 0 */
    {
        void_fn_word fn = (void_fn_word)(uintptr_t)0xA0DC;
        fn(0);
    }

    /* setSR_PARAM(r15, 0xE0) — set interrupt mask bits in SR */
    {
        typedef void (*fn_t)(uint32_t, uint16_t);
        fn_t fn = (fn_t)(uintptr_t)0x2054;
        fn(_sp, 0xE0);
    }

    /* setRegister_REG_BIT_VAL(0xF74E, bit 8, value 1) */
    {
        typedef void (*fn_t)(uint16_t, uint8_t, uint8_t);
        fn_t fn = (fn_t)(uintptr_t)0x4BBC;
        fn(0xF74E, 8, 1);
    }

    /* loadStatusRegister_ADDR (0x2064) */
    {
        void_fn_word fn = (void_fn_word)(uintptr_t)0x2064;
        fn(_sp);
    }

    /* sfr_init_dma_channels (0x4CF8) */
    {
        void_fn_void fn = (void_fn_void)(uintptr_t)0x4CF8;
        fn();
    }

    /* task_context_switch(0) — starts the RTOS, never returns */
    {
        void_fn_byte fn = (void_fn_byte)(uintptr_t)0x3AD8;
        fn(0);
    }

    /* NOT REACHED */
    for (;;) {
    }
}

/* ------------------------------------------------------------------ */
/*  task_context_switch @ 0x3AD8                                      */
/* ------------------------------------------------------------------ */

/**
 * task_context_switch  —  Switch to kernel context and start the RTOS.
 *
 * @param task_id  Initial task index (0 from the boot path).
 * @return 0 if task_id >= task_count ([0x4B00]); otherwise does not return —
 *         tail-jumps to init_main (0x3E10).
 */
int task_context_switch(uint8_t task_id)
{
    /* mov.b [0x4B00] -> r0 ; exts.b r4 ; cmp/hs r0,r4 ; bf continue */
    if ((int8_t)task_id >= (int8_t)TASK_COUNT_PTR) {
        return 0;                       /* rts ; mov #0,r0 */
    }

    /* Save caller SR/PR + SP into the control-block save slot */
    (void)cpu_sr_get();
    _pr = 0;                            /* sts.l pr,@-r15 */
    SAVED_SP_SLOT = _sp;                /* [0xFFFF72D8] = r15 */

    /* SR = [0x4B04] = 0x00B0  (kernel status register) */
    cpu_sr_set(KERNEL_SR_PTR);

    /* SP = [0x4938] = 0xFFFF719C  (kernel stack) */
    _sp = KERNEL_SP_PTR;

    /* [ctl+8] = 0x100  (RTOS control block at 0xFFFF72B0) */
    CTL_BLOCK[2] = 0x100;

    /* jmp 0x3E10  — init_main (tail call, never returns) */
    {
        void_fn_byte fn = (void_fn_byte)(uintptr_t)0x3E10;
        fn(0);
    }
    return 0;   /* NOT REACHED */
}
