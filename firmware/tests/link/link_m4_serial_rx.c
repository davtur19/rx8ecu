/*
 * link_m4_serial_rx.c — Link pilot m4: compile-link-run against the REAL
 * serial.c TU (+ the REAL timer.c TU for the two ATU-init symbols it
 * calls), exercising the M4 serial-RX fix (owned per-channel rx_buf +
 * capacity rx_len + READY gated on rx_idx>0) plus the ATU/INTC MMIO paths
 * on the exercised path — not a model replica.
 *
 * Mechanism proof: links the real serial.c, so a firmware revert of the
 * M4 fix (dropping the serial_init rx_buf/rx_len arming, delivering
 * rx_len instead of rx_idx, zeroing capacity on read, or breaking the
 * RX_READY gate) fails this binary at run time. Detection for the four
 * local-extern symbols (serial.h carries NO prototypes for serial_init /
 * serial_data_read / serial_data_write / serial_atu_irq_handler): a
 * RENAME in serial.c fails at link (undefined symbol); a parameter-type
 * change of those four alone still links and is NOT detected here —
 * residual, no shared decl exists. Symbols with serial.h/timer.h
 * declarations are compiled against the header. The ATU
 * interrupt-status RMW clear and the intc_reg_write enable/disable
 * values are also driven for real against the mapped page.
 *
 * Target / TU choice (confirmed from source, not assumed):
 *   - `nm -u serial.o` = exactly {atu_timer_init, atu_capture_compare_init}.
 *     Both are called ONLY from serial_init — and serial_init is where the
 *     M4 fix lives (rx_buf = serial_rx_owned[i], rx_len = 255), so init
 *     MUST run; uncalled-stub style (h5) does not apply.
 *   - Both symbols are provided by the in-repo firmware/c/timer.c TU
 *     (`nm -u timer.o` clean, zero undefined externs). Linking the real
 *     timer.c is therefore strictly stronger than stub fixtures: the real
 *     ATU init MMIO writes execute on the mapped page (TSTR/TCR/TIOR/TIER
 *     at 0xFFFFF700+), no lying empty stubs, zero stub symbols.
 *   - No ROM read: serial.c and timer.c function bodies only touch the
 *     0xFFFFF0xx/0xFFFFF7xx page (objdump immediates: 0xFFFFF02E INTC,
 *     0xFFFFF781/91/A1 TGR byte lanes, 0xFFFFF7B0 TISRA, timer offsets
 *     ATU_BASE+0x00..0xB0); ROM addresses appear in comments only.
 *   - No main() clash; both TUs compile clean under -Werror (no
 *     unused-function relaxation needed, unlike can.c/dtc.c).
 *
 * Host execution boundary (one MMIO page, mmap MAP_FIXED):
 *   - Map 0xFFFFF000 (4 KiB) covering INTC 0xFFFFF02E, ATU block
 *     0xFFFFF700..0xFFFFF7B0 (TSTR/TCR/TIOR/TIER/TGR/TISRA). Verified
 *     mappable MAP_FIXED on this host.
 *   - serial_init runs FIRST after mmap+prime: real timer.c config writes
 *     land on primed nonzero values (killable), then serial_enable_
 *     interrupts writes INTC 0x001E (primed 0xEEEE).
 *   - RX handlers read the LOW byte lane (base+1) of each TGR register —
 *     primed with the expected byte in the +1 lane and a distinct byte in
 *     the +0 lane, so a high-byte-lane mutant is red.
 *
 * Contract pins: ATU_BASE / ATU_TGR*_OFFSET / ATU_TISRA_OFFSET come from
 * the real platform.h (_Static_asserts below); INTC 0xFFFFF02E and the
 * SERIAL_STATUS_* / capacity values live as literals in the serial.c body
 * (no header macros), pinned local-constant style, m8/l10. serial.h does
 * not declare serial_init / serial_data_read / serial_data_write /
 * serial_atu_irq_handler — the harness carries those four local externs
 * (grep-verified); every other called symbol comes from serial.h/timer.h.
 *
 * Proves (every assert killable; every zero-expect is primed nonzero
 * first — F1 lesson):
 *   (a) serial_init arms M4: real atu_timer_init + atu_capture_compare_
 *       init MMIO values land (TSTR 0, TCR* =DIV4, TIOR0 =4, TIOR1 =1,
 *       TIOR2 =0, TIER0/1 =1, TIER2 =0 — each primed 0xEEEE), INTC
 *       0xFFFFF02E primed 0xEEEE -> 0x001E;
 *   (b) fresh channel after init: serial_data_read returns 0, not -1
 *       (kills NULL rx_buf / dropped init arming);
 *   (c) channel >= 3 rejects with -1 (read and write);
 *   (d) ch0 one-byte RX through the real handler: byte from the TGR0+1
 *       lane delivered, n==1 not min(255,max) (kills len=rx_len);
 *   (e) after read: second read returns 0 (READY/index drained);
 *   (f) ch1 three-byte loopback AA/55/01 in order;
 *   (g) capacity preserved across reads: a fresh byte after a drain still
 *       arrives (kills `rx_len = 0` on read — the pre-M4 re-break);
 *   (h) max_len clamp: 3 received, read(max=2) delivers the first 2
 *       (idx drains on every read — capacity, not leftover, is what (g)
 *       proves preserved), then a follow-up read returns 0;
 *   (i) READY gate: one byte sets READY (status leaves IDLE so the read
 *       returns the byte); with rx_len=capacity the `rx_idx >= rx_len`
 *       mutant never sets READY -> read returns 0, red;
 *   (j) IRQ path ch0: TISRA primed 0x00A1 (bit0 + junk bits 5/7, no
 *       bit1) -> RMW clears ONLY bit0 (0x00A0), ch0 byte captured
 *       (kills full-mask ~0x0001 = 0xFFFE write that would wipe 5/7);
 *   (k) IRQ path TX-only bit1: TISRA primed 0x0012 -> 0x0010, no RX
 *       side effects;
 *   (l) IRQ path ch2: TISRA primed 0x00D4 -> 0x00D0, ch2 byte captured;
 *   (m) serial_enable/disable_interrupts: INTC primed 0xEEEE -> 0x001E /
 *       0x0000 exactly (value asserts, not just “was written”);
 *   (n) TX smoke: serial_data_write returns len, second write while idle
 *       works, serial_start_tx on a no-TX_READY channel is a no-op —
 *       full-TU link proof, not model-only.
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 \
 *       -I../include link/link_m4_serial_rx.c ../c/serial.c ../c/timer.c \
 *       -o /tmp/fwtest/link_m4_serial_rx
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>

#include "platform.h"
#include "serial.h"
#include "timer.h"

/* Extern declarations come from the real serial.h/timer.h (linking the
 * real serial.c + timer.c TUs): a signature change in firmware breaks
 * this build. Pin the address-map contract so a revert breaks the build,
 * not just the run. */
_Static_assert(ATU_BASE == 0xFFFFF700u, "ATU_BASE revert");
_Static_assert(ATU_TSTR_OFFSET == 0x0000u, "ATU_TSTR_OFFSET revert");
_Static_assert(ATU_TCR0_OFFSET == 0x0010u, "ATU_TCR0_OFFSET revert");
_Static_assert(ATU_TCR1_OFFSET == 0x0020u, "ATU_TCR1_OFFSET revert");
_Static_assert(ATU_TCR2_OFFSET == 0x0030u, "ATU_TCR2_OFFSET revert");
_Static_assert(ATU_TIOR0_OFFSET == 0x0040u, "ATU_TIOR0_OFFSET revert");
_Static_assert(ATU_TIOR1_OFFSET == 0x0050u, "ATU_TIOR1_OFFSET revert");
_Static_assert(ATU_TIER0_OFFSET == 0x0060u, "ATU_TIER0_OFFSET revert");
_Static_assert(ATU_TIER1_OFFSET == 0x0070u, "ATU_TIER1_OFFSET revert");
_Static_assert(ATU_TGR0_OFFSET == 0x0080u, "ATU_TGR0_OFFSET revert");
_Static_assert(ATU_TGR1_OFFSET == 0x0090u, "ATU_TGR1_OFFSET revert");
_Static_assert(ATU_TGR2_OFFSET == 0x00A0u, "ATU_TGR2_OFFSET revert");
_Static_assert(ATU_TISRA_OFFSET == 0x00B0u, "ATU_TISRA_OFFSET revert");
_Static_assert(SERIAL_CHANNELS == 3, "SERIAL_CHANNELS revert");

/* INTC_REGISTER and SERIAL_STATUS_* have no address/flag macros in the
 * headers (literals in the serial.c/platform.h bodies) — pin them the
 * m8/l10 local-constant way. INTC 0xFFFFF02E is the platform.h comment
 * address; status bits match serial.c SERIAL_STATUS_*. Capacity 255 is
 * serial.c SERIAL_RX_CAPACITY (owned buffer 256, uint8_t len). */
#define M4_PAGE_BASE     0xFFFFF000u
#define M4_PAGE_LEN      0x1000u
#define M4_INTC_ADDR     0xFFFFF02Eu
#define M4_STATUS_READY  0x04u   /* SERIAL_STATUS_RX_READY (serial.c body) */
#define M4_RX_CAPACITY   255u    /* SERIAL_RX_CAPACITY after M4 fix */

/* timer.c channel-2 raw offsets (NEEDS-ROM-CHECK locals in timer.c). */
#define M4_ATU_CH2_TIOR  0x24u
#define M4_ATU_CH2_TIER  0x28u

#define M4_ATU_TGR0_ADDR (ATU_BASE + ATU_TGR0_OFFSET)
#define M4_ATU_TGR1_ADDR (ATU_BASE + ATU_TGR1_OFFSET)
#define M4_ATU_TGR2_ADDR (ATU_BASE + ATU_TGR2_OFFSET)
#define M4_ATU_TISRA_ADDR (ATU_BASE + ATU_TISRA_OFFSET)

#define M4_IN_PAGE(a, n) \
    ((a) >= M4_PAGE_BASE && (a) - M4_PAGE_BASE + (n) <= M4_PAGE_LEN)

_Static_assert(M4_IN_PAGE(M4_INTC_ADDR, 2u), "INTC outside mapped page");
_Static_assert(M4_IN_PAGE(M4_ATU_TGR0_ADDR, 2u), "TGR0 outside page");
_Static_assert(M4_IN_PAGE(M4_ATU_TGR1_ADDR, 2u), "TGR1 outside page");
_Static_assert(M4_IN_PAGE(M4_ATU_TGR2_ADDR, 2u), "TGR2 outside page");
_Static_assert(M4_IN_PAGE(M4_ATU_TISRA_ADDR, 2u), "TISRA outside page");
_Static_assert(M4_IN_PAGE(ATU_BASE, 0xC0u), "ATU block outside page");
/* Self-referential local pins: M4_INTC_ADDR / M4_STATUS_READY /
 * M4_RX_CAPACITY are #defined as these same literals in THIS file, so
 * the asserts below cannot observe a firmware change — they pin the
 * harness map only. The local pins mirror the firmware literals
 * (platform.h comment / serial.c SERIAL_STATUS_* / SERIAL_RX_CAPACITY)
 * and the runtime value CHECKs (primed 0xEEEE → exact expected) carry
 * the revert-detection load. */
_Static_assert(M4_INTC_ADDR == 0xFFFFF02Eu, "INTC address revert");
_Static_assert(M4_STATUS_READY == 0x04u, "RX_READY bit revert");
_Static_assert(M4_RX_CAPACITY == 255u, "M4 capacity revert");

/* serial.h does NOT declare these four (verified by grep — only the
 * handlers/enable/start_tx live there): serial_init, serial_data_read,
 * serial_data_write, serial_atu_irq_handler are defined in serial.c with
 * no header prototype. These local externs pin the signatures the
 * harness CALLS, but they are independent of serial.c's definitions: a
 * RENAME in serial.c fails at link (undefined symbol), while a
 * parameter-type change of these four still links and is not detected
 * here (no shared header proto — residual; under -Werror the serial.c
 * definitions themselves must stay warning-clean against serial.h where
 * a header proto exists). */
void serial_init(void);
int serial_data_read(uint8_t channel, uint8_t *buf, uint8_t max_len);
int serial_data_write(uint8_t channel, const uint8_t *buf, uint8_t len);
void serial_atu_irq_handler(void);

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint8_t *m4_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

static volatile uint16_t *m4_u16(uint32_t addr)
{
    return (volatile uint16_t *)(uintptr_t)addr;
}

/* Distinct prime so every zero-expect (and every exact-value expect) is
 * killable: 0xEEEE lands nowhere as a legitimate init/runtime value. */
#define M4_PRIME 0xEEEEu

static void m4_prime_init_targets(void)
{
    *m4_u16(M4_INTC_ADDR) = M4_PRIME;
    *m4_u16(ATU_BASE + ATU_TSTR_OFFSET) = M4_PRIME;
    *m4_u16(ATU_BASE + ATU_TCR0_OFFSET) = M4_PRIME;
    *m4_u16(ATU_BASE + ATU_TCR1_OFFSET) = M4_PRIME;
    *m4_u16(ATU_BASE + ATU_TCR2_OFFSET) = M4_PRIME;
    *m4_u16(ATU_BASE + ATU_TIOR0_OFFSET) = M4_PRIME;
    *m4_u16(ATU_BASE + ATU_TIOR1_OFFSET) = M4_PRIME;
    *m4_u16(ATU_BASE + M4_ATU_CH2_TIOR) = M4_PRIME;
    *m4_u16(ATU_BASE + ATU_TIER0_OFFSET) = M4_PRIME;
    *m4_u16(ATU_BASE + ATU_TIER1_OFFSET) = M4_PRIME;
    *m4_u16(ATU_BASE + M4_ATU_CH2_TIER) = M4_PRIME;
}

/* Deliver one RX byte on a channel by priming the TGR low lane (the ROM
 * mov.b @(1,r4) lane) and calling the real handler. The high lane is
 * primed with a distinct byte so a high-lane mutant returns the wrong
 * value, not merely a zeroed one. */
static void m4_rx(uint8_t channel, uint8_t byte)
{
    uint32_t tgr;
    switch (channel) {
    case 0:  tgr = M4_ATU_TGR0_ADDR; break;
    case 1:  tgr = M4_ATU_TGR1_ADDR; break;
    default: tgr = M4_ATU_TGR2_ADDR; break;
    }
    *m4_u8(tgr + 1u) = byte;
    *m4_u8(tgr) = (uint8_t)(byte ^ 0xFFu);
    switch (channel) {
    case 0:  serial_rx_handler_ch0(); break;
    case 1:  serial_rx_handler_ch1(); break;
    default: serial_rx_handler_ch2(); break;
    }
}

int main(void)
{
    uint8_t buf[8];
    int n;

    void *p = mmap((void *)(uintptr_t)M4_PAGE_BASE, M4_PAGE_LEN,
                   PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == (void *)-1) {
        printf("FAIL: mmap(0xFFFFF000) failed\n");
        return 1;
    }

    /* (a) serial_init MUST run (M4 arming lives there). Prime every
     * init target nonzero, then require the exact post-init values —
     * proves the real timer.c TU executed its MMIO writes and that
     * serial_enable_interrupts wrote INTC 0x001E. */
    m4_prime_init_targets();
    serial_init();

    CHECK(*m4_u16(M4_INTC_ADDR) == 0x001Eu,
          "serial_init INTC=%04X want 001E (enable value dropped)",
          *m4_u16(M4_INTC_ADDR));
    CHECK(*m4_u16(ATU_BASE + ATU_TSTR_OFFSET) == 0x0000u,
          "TSTR=%04X want 0000 (primed EEEE — timer init skipped?)",
          *m4_u16(ATU_BASE + ATU_TSTR_OFFSET));
    CHECK(*m4_u16(ATU_BASE + ATU_TCR0_OFFSET) == (uint16_t)ATU_PRESCALER_DIV4,
          "TCR0=%04X want 0001 (DIV4)",
          *m4_u16(ATU_BASE + ATU_TCR0_OFFSET));
    CHECK(*m4_u16(ATU_BASE + ATU_TCR1_OFFSET) == (uint16_t)ATU_PRESCALER_DIV4,
          "TCR1=%04X want 0001",
          *m4_u16(ATU_BASE + ATU_TCR1_OFFSET));
    CHECK(*m4_u16(ATU_BASE + ATU_TCR2_OFFSET) == (uint16_t)ATU_PRESCALER_DIV4,
          "TCR2=%04X want 0001",
          *m4_u16(ATU_BASE + ATU_TCR2_OFFSET));
    CHECK(*m4_u16(ATU_BASE + ATU_TIOR0_OFFSET) == 0x0004u,
          "TIOR0=%04X want 0004 (capture rising)",
          *m4_u16(ATU_BASE + ATU_TIOR0_OFFSET));
    CHECK(*m4_u16(ATU_BASE + ATU_TIOR1_OFFSET) == 0x0001u,
          "TIOR1=%04X want 0001 (compare)",
          *m4_u16(ATU_BASE + ATU_TIOR1_OFFSET));
    CHECK(*m4_u16(ATU_BASE + M4_ATU_CH2_TIOR) == 0x0000u,
          "TIOR2=%04X want 0000 (primed EEEE)",
          *m4_u16(ATU_BASE + M4_ATU_CH2_TIOR));
    CHECK(*m4_u16(ATU_BASE + ATU_TIER0_OFFSET) == 0x0001u,
          "TIER0=%04X want 0001",
          *m4_u16(ATU_BASE + ATU_TIER0_OFFSET));
    CHECK(*m4_u16(ATU_BASE + ATU_TIER1_OFFSET) == 0x0001u,
          "TIER1=%04X want 0001",
          *m4_u16(ATU_BASE + ATU_TIER1_OFFSET));
    CHECK(*m4_u16(ATU_BASE + M4_ATU_CH2_TIER) == 0x0000u,
          "TIER2=%04X want 0000 (primed EEEE)",
          *m4_u16(ATU_BASE + M4_ATU_CH2_TIER));

    /* (b) Fresh channel: read must return 0 (IDLE), not -1 (NULL rx_buf
     * — the structural-absence pre-M4 state). */
    n = serial_data_read(0, buf, sizeof buf);
    CHECK(n == 0, "fresh ch0 read=%d want 0 (M4 arming dropped? -1=NULL rx_buf)",
          n);

    /* (c) Channel bounds. */
    CHECK(serial_data_read(3, buf, sizeof buf) == -1,
          "ch3 read must be -1");
    CHECK(serial_data_write(3, buf, 2) == -1, "ch3 write must be -1");

    /* (d) ch0 one-byte RX: byte from the TGR0+1 lane, n==1 — NOT
     * min(rx_len=255, max_len=8)=8 (kills len=ch->rx_len) and NOT 0
     * (kills NULL-guard store / broken READY gate). */
    m4_rx(0, 0xA5u);
    memset(buf, 0xEE, sizeof buf);
    n = serial_data_read(0, buf, sizeof buf);
    CHECK(n == 1, "ch0 after 1 RX read=%d want 1 (capacity delivered?)", n);
    CHECK(n >= 1 && buf[0] == 0xA5u,
          "ch0 byte=%02X want A5 (wrong TGR lane?)",
          n >= 1 ? buf[0] : 0u);

    /* (e) After read: drained — second read returns 0 (READY/index
     * actually cleared, not just reported). */
    n = serial_data_read(0, buf, sizeof buf);
    CHECK(n == 0, "ch0 second read=%d want 0 (drain failed)", n);

    /* (f) ch1 three-byte loopback. */
    m4_rx(1, 0xAAu);
    m4_rx(1, 0x55u);
    m4_rx(1, 0x01u);
    memset(buf, 0xEE, sizeof buf);
    n = serial_data_read(1, buf, sizeof buf);
    CHECK(n == 3, "ch1 loopback read=%d want 3", n);
    CHECK(n == 3 && buf[0] == 0xAAu && buf[1] == 0x55u && buf[2] == 0x01u,
          "ch1 bytes %02X %02X %02X want AA 55 01",
          n == 3 ? buf[0] : 0u, n == 3 ? buf[1] : 0u, n == 3 ? buf[2] : 0u);

    /* (g) Capacity preserved across a read: pre-M4/buggy read zeroed
     * rx_len, which re-closed the handler store guard. A fresh byte
     * after the drain must still arrive. */
    m4_rx(1, 0x42u);
    memset(buf, 0xEE, sizeof buf);
    n = serial_data_read(1, buf, sizeof buf);
    CHECK(n == 1 && buf[0] == 0x42u,
          "ch1 post-drain RX n=%d byte=%02X want 1/42 (capacity zeroed?)",
          n, n >= 1 ? buf[0] : 0u);

    /* (h) max_len clamp: 3 received, read(max=2) delivers the first 2
     * bytes (not fewer, not more). serial_data_read always drains
     * rx_idx on return (even a clamped read), so the leftover is gone —
     * the capacity (rx_len) is what must survive, covered by (g). */
    m4_rx(2, 0x11u);
    m4_rx(2, 0x22u);
    m4_rx(2, 0x33u);
    memset(buf, 0xEE, sizeof buf);
    n = serial_data_read(2, buf, 2);
    CHECK(n == 2, "ch2 clamp read=%d want 2", n);
    CHECK(n == 2 && buf[0] == 0x11u && buf[1] == 0x22u,
          "ch2 clamp bytes %02X %02X want 11 22",
          n == 2 ? buf[0] : 0u, n == 2 ? buf[1] : 0u);
    memset(buf, 0xEE, sizeof buf);
    n = serial_data_read(2, buf, sizeof buf);
    CHECK(n == 0, "ch2 post-clamp read=%d want 0 (idx drained)", n);

    /* (i) READY gate shape: one byte must leave IDLE so the read returns
     * it. With rx_len=capacity the `rx_idx >= rx_len` mutant never sets
     * READY -> read returns 0, red. (Same as (d) on ch0; re-checked on a
     * clean channel state for independence.) */
    m4_rx(0, 0x5Au);
    memset(buf, 0xEE, sizeof buf);
    n = serial_data_read(0, buf, sizeof buf);
    CHECK(n == 1 && buf[0] == 0x5Au,
          "READY gate: n=%d byte=%02X want 1/5A", n,
          n >= 1 ? buf[0] : 0u);

    /* (j) IRQ ch0: TISRA primed 0x00A1 (bit0 + high junk bits 5/7; NOT
     * bit1 — that would also arm the legitimate TX-clear branch). RMW
     * must clear ONLY bit0 -> 0x00A0 (kills full-mask ~0x0001=0xFFFE
     * write, which would wipe bits 5/7), and ch0 must capture TGR0+1. */
    *m4_u8(M4_ATU_TGR0_ADDR + 1u) = 0x7Eu;
    *m4_u8(M4_ATU_TGR0_ADDR) = 0x00u; /* high lane distinct from 7E */
    *m4_u16(M4_ATU_TISRA_ADDR) = 0x00A1u;
    serial_atu_irq_handler();
    CHECK(*m4_u16(M4_ATU_TISRA_ADDR) == 0x00A0u,
          "IRQ ch0 TISRA=%04X want 00A0 (flag-only RMW clear)",
          *m4_u16(M4_ATU_TISRA_ADDR));
    memset(buf, 0xEE, sizeof buf);
    n = serial_data_read(0, buf, sizeof buf);
    CHECK(n == 1 && buf[0] == 0x7Eu,
          "IRQ ch0 capture n=%d byte=%02X want 1/7E", n,
          n >= 1 ? buf[0] : 0u);

    /* (k) IRQ TX-only bit1: TISRA primed 0x0012 -> 0x0010, no channel
     * receives (all channels still drained). */
    *m4_u16(M4_ATU_TISRA_ADDR) = 0x0012u;
    serial_atu_irq_handler();
    CHECK(*m4_u16(M4_ATU_TISRA_ADDR) == 0x0010u,
          "IRQ TX TISRA=%04X want 0010",
          *m4_u16(M4_ATU_TISRA_ADDR));
    CHECK(serial_data_read(0, buf, sizeof buf) == 0,
          "IRQ TX must not deliver on ch0");
    CHECK(serial_data_read(1, buf, sizeof buf) == 0,
          "IRQ TX must not deliver on ch1");
    CHECK(serial_data_read(2, buf, sizeof buf) == 0,
          "IRQ TX must not deliver on ch2");

    /* (l) IRQ ch2: TISRA primed 0x00D4 (bit2 + bits 4/6/7) -> 0x00D0,
     * ch2 captures TGR2+1. */
    *m4_u8(M4_ATU_TGR2_ADDR + 1u) = 0xC3u;
    *m4_u8(M4_ATU_TGR2_ADDR) = 0x3Cu;
    *m4_u16(M4_ATU_TISRA_ADDR) = 0x00D4u;
    serial_atu_irq_handler();
    CHECK(*m4_u16(M4_ATU_TISRA_ADDR) == 0x00D0u,
          "IRQ ch2 TISRA=%04X want 00D0",
          *m4_u16(M4_ATU_TISRA_ADDR));
    memset(buf, 0xEE, sizeof buf);
    n = serial_data_read(2, buf, sizeof buf);
    CHECK(n == 1 && buf[0] == 0xC3u,
          "IRQ ch2 capture n=%d byte=%02X want 1/C3", n,
          n >= 1 ? buf[0] : 0u);

    /* (m) enable/disable: exact INTC values, each primed 0xEEEE first. */
    *m4_u16(M4_INTC_ADDR) = M4_PRIME;
    serial_enable_interrupts();
    CHECK(*m4_u16(M4_INTC_ADDR) == 0x001Eu,
          "enable INTC=%04X want 001E",
          *m4_u16(M4_INTC_ADDR));
    *m4_u16(M4_INTC_ADDR) = M4_PRIME;
    serial_disable_interrupts();
    CHECK(*m4_u16(M4_INTC_ADDR) == 0x0000u,
          "disable INTC=%04X want 0000 (primed EEEE)",
          *m4_u16(M4_INTC_ADDR));

    /* (n) TX smoke (full-TU link proof): queue returns len; start_tx on
     * a channel with no TX_READY is a quiet no-op; write_handler with
     * nothing pending does not touch TX state observably. */
    {
        static const uint8_t tx[3] = { 0xDEu, 0xADu, 0xBEu };
        n = serial_data_write(0, tx, 3);
        CHECK(n == 3, "tx write n=%d want 3", n);
        serial_start_tx(1); /* ch1 has no TX_READY — must not crash/affect ch0 */
        serial_data_write_handler();
        /* After write+start_tx, TX completed synchronously (host contract
         * in serial.c): a second write on ch0 must not see TX_BUSY. */
        n = serial_data_write(0, tx, 1);
        CHECK(n == 1, "tx re-write n=%d want 1 (TX_BUSY stuck?)", n);
    }

    munmap(p, M4_PAGE_LEN);

    if (failures == 0) {
        printf("PASS link_m4_serial_rx (real serial.c + timer.c TUs)\n");
    } else {
        printf("%d FAILURES link_m4_serial_rx\n", failures);
    }
    return failures != 0;
}
