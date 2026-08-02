/* ============================================================================
 * oracle_calc_lambda_feedback_pid.c  —  host test rig for
 *                        rx8_calc_lambda_feedback_pid @0x11A34
 * ============================================================================
 * Compile together with src/rx8_calc_lambda_feedback_pid.c (see
 * harness_calc_lambda_feedback_pid.py) and pipe test vectors on stdin; one
 * vector per line, whitespace-separated hex tokens:
 *
 *     lambda <s0> <s1> ... <s52>
 *            -> <s0'> <s1'> ... <s52'>
 *
 * The 53 tokens are the initial value of every byte of the RAM span
 * 0xFFFFD12F..0xFFFFD163 (53 bytes), in ascending address order.  Within the
 * span:
 *
 *     0xFFFFD130  trace length byte (the shared "next slot" counter)
 *     0xFFFFD140  trace buffer base (the dispatch-slot sequence, pre-seeded)
 *
 * Per vector the rig seeds all 53 bytes, calls rx8_calc_lambda_feedback_pid()
 * and prints the 53 resulting bytes.  The oracle contains NO copy of the
 * function logic — that lives solely in src/rx8_calc_lambda_feedback_pid.c.
 * It only mirrors the *caller-side* setup: the page backing the span is
 * backed with mmap(MAP_FIXED) (same trick as host_oracle.c), so the stub
 * callees' fixed-address volatile pointers compile and fault-free on the
 * host.  On the SH-2E target these are plain on-chip RAM addresses.
 *
 * STUB MODEL (identical to the emulator-side RAM-overlay stubs)
 * -------------------------------------------------------------
 * The 17 dispatched callees are stubbed here, one C function per ROM
 * address, mirroring byte-for-byte the SH-2 stubs the harness installs at
 * the real ROM callee addresses in tools/sh2emu.py's sparse RAM overlay.
 * Each stub appends its dispatch slot index k (0..16) to the trace buffer:
 *
 *     idx = (int8_t)RAM8[0xFFFFD130]          ; SH-2 `mov.b @Rm,Rn` SIGN-EXTENDS
 *     RAM8[0xFFFFD140 + idx] = k              ; BYTE store
 *     RAM8[0xFFFFD130] = RAM8[0xFFFFD130] + 1 ; BYTE wrap
 *
 * The sign-extended index is the one host/emulator nuance: for a pre-state
 * length byte 0xFE/0xFF the append lands BELOW the trace base (0xFFFFD13E /
 * 0xFFFFD13F), exactly as the SH-2's 32-bit pointer arithmetic wraps — both
 * sides write the same byte to the same address.  All cells are u8, so the
 * comparison is byte-exact numeric (cf. rx8_immo_state_ready_to_drive_
 * engine_off.c's native-width convention).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

/* Prototype is NOT in rx8_samples.h (sample project convention: only the
 * verified public leaves are listed there); declared here for the rig. */
void rx8_calc_lambda_feedback_pid(void);

#define SPAN_START  0xFFFFD12Fu   /* first byte of the seeded/comparison span  */
#define SPAN_LEN    53u           /* 0xFFFFD12F..0xFFFFD163                    */
#define LEN_ADDR    0xFFFFD130u   /* u8 trace length byte (span offset 1)      */
#define TRACE_ADDR  0xFFFFD140u   /* u8 trace buffer base (span offset 17)     */

/* ---- the 17 callee stubs (mirror the harness' RAM-overlay stubs) ---- */
static void lambda_trace_append(uint8_t k)
{
    volatile uint8_t *lenp = (volatile uint8_t *)(uintptr_t)LEN_ADDR;
    volatile uint8_t *trp  = (volatile uint8_t *)(uintptr_t)TRACE_ADDR;
    trp[(int8_t)*lenp] = k;                 /* SH-2: mov.b @Rm,Rn sign-extends */
    *lenp = (uint8_t)(*lenp + 1u);          /* byte wrap like add #1 + mov.b  */
}

void rx8_lambda_core_1acde(void)      { lambda_trace_append( 0); } /* @0x1ACDE */
void rx8_lambda_chain_2f51e(void)     { lambda_trace_append( 1); } /* @0x2F51E */
void rx8_lambda_core_3a1cc(void)      { lambda_trace_append( 2); } /* @0x3A1CC */
void rx8_lambda_trim_2204c(void)      { lambda_trace_append( 3); } /* @0x2204C */
void rx8_lambda_state_1490e(void)     { lambda_trace_append( 4); } /* @0x1490E */
void rx8_lambda_sensor_2766a(void)    { lambda_trace_append( 5); } /* @0x2766A */
void rx8_lambda_transient_16aa8(void) { lambda_trace_append( 6); } /* @0x16AA8 */
void rx8_lambda_o2_3fce0(void)        { lambda_trace_append( 7); } /* @0x3FCE0 */
void rx8_lambda_fueling_32a9c(void)   { lambda_trace_append( 8); } /* @0x32A9C */
void rx8_lambda_core_17f7c(void)      { lambda_trace_append( 9); } /* @0x17F7C */
void rx8_lambda_enable_225a2(void)    { lambda_trace_append(10); } /* @0x225A2 */
void rx8_lambda_status_35b6a(void)    { lambda_trace_append(11); } /* @0x35B6A */
void rx8_lambda_status_35b96(void)    { lambda_trace_append(12); } /* @0x35B96 */
void rx8_lambda_dtc_2971c(void)       { lambda_trace_append(13); } /* @0x2971C */
void rx8_lambda_heater_2b0d6(void)    { lambda_trace_append(14); } /* @0x2B0D6 */
void rx8_lambda_wrap_67482(void)      { lambda_trace_append(15); } /* @0x67482 */
void rx8_lambda_latch_16e6a(void)     { lambda_trace_append(16); } /* @0x16E6A */

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
}

int main(void)
{
    /* The whole span lives in the 0xFFFFD000..0xFFFFDFFF page; one mmap. */
    map_page(SPAN_START);

    char line[512];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long s[SPAN_LEN];
        if (sscanf(line, "lambda %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                         "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                         "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                         "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                         "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                         "%lx %lx %lx",
                   &s[0], &s[1], &s[2], &s[3], &s[4], &s[5], &s[6], &s[7],
                   &s[8], &s[9], &s[10], &s[11], &s[12], &s[13], &s[14],
                   &s[15], &s[16], &s[17], &s[18], &s[19], &s[20], &s[21],
                   &s[22], &s[23], &s[24], &s[25], &s[26], &s[27], &s[28],
                   &s[29], &s[30], &s[31], &s[32], &s[33], &s[34], &s[35],
                   &s[36], &s[37], &s[38], &s[39], &s[40], &s[41], &s[42],
                   &s[43], &s[44], &s[45], &s[46], &s[47], &s[48], &s[49],
                   &s[50], &s[51], &s[52])
            != SPAN_LEN) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed every byte of the span (byte-exact numeric values). */
        for (unsigned i = 0; i < SPAN_LEN; i++)
            *(volatile uint8_t *)(uintptr_t)(SPAN_START + i) = (uint8_t)s[i];

        rx8_calc_lambda_feedback_pid();

        for (unsigned i = 0; i < SPAN_LEN; i++)
            printf("%02X%c",
                   *(volatile uint8_t *)(uintptr_t)(SPAN_START + i),
                   i + 1 < SPAN_LEN ? ' ' : '\n');
    }
    return 0;
}
