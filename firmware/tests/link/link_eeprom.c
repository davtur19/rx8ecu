/*
 * link_eeprom.c — Link pilot #14: compile-link-run against the REAL
 * firmware/c/eeprom.c TU (external SPI EEPROM interface, S-93C56C via
 * bit-banged SPI), not a model replica. Closes the adversarial-review P1
 * zero-coverage finding: this TU had no link rule, no model harness, no
 * gate grep, and no c/tests on any side.
 *
 * Mechanism proof: links the real eeprom.c TU (`nm -u eeprom.o` EMPTY —
 * zero undefined externs, m2 precedent — verified at pilot time; the
 * review's "19 functions" = 14 public + 2 file-static helpers
 * (spi_cs_low/high) + 3 platform.h static inlines it pulls in), so a
 * firmware revert of the SPI wait timeout, the CS framing, the
 * command/addr/data shift, the staging/verify copy, the validate
 * consume-marker, or the length clamps fails this binary at run time; a
 * signature change fails at compile time (extern decls via eeprom.h).
 *
 * Host execution boundary (FOUR 4 KiB pages, mmap MAP_FIXED):
 *   0xFFFFE000 — SPI clk/status 0xFFFFE401 (u8), data line 0xFFFFE406
 *                (u16), plus 0xFFFFE403 as the host stand-in status byte
 *                for distinct-pointer wait calls (on the real ECU clk and
 *                status are the SAME register @0xFFFFE401 — the
 *                same-register shape is asserted too);
 *   0xFFFFF000 — CS port 0xFFFFF730 (u16; address literal lives in the
 *                eeprom.c body — NEEDS-ROM-CHECK guess, mirrored here as a
 *                local pin; a firmware address move off this pin is
 *                caught because the prime/assert at the pin then observes
 *                no transaction);
 *   0xFFFFC000 — staging 0xFFFFC2FE..0xFFFFC3FD + inverted verify copy
 *                0xFFFFC3FE..0xFFFFC4FD (platform.h macros, range
 *                _Static_asserted against the real firmware values);
 *   0xFFFFD000 — RAM validation buffer 0xFFFFDFE4..0xFFFFDFED + consume
 *                marker 0xFFFFDFEC.
 * Every load/store the TU performs then executes for real.
 *
 * There is NO init entry in eeprom.c (hw_init_1 @0x170 is ROM-side, not
 * reconstructed) — the host equivalent is the mmap+prime setup below.
 *
 * Proves (every assert killable; every zero-expect is primed nonzero
 * first — F1 lesson; no tautological asserts):
 *   (a) SPI wait timeout bound: spi_clk_high_wait / spi_clk_low_wait must
 *       RETURN on a stuck status byte (SPI_TIMEOUT_ITERATIONS bound),
 *       with the clock bit flipped — each stuck call runs under a 3 s
 *       SIGALRM watchdog, so a mutant that removes/extends the break is
 *       killed (FAIL + exit 1) instead of hanging the gate;
 *   (b) CS framing: every transaction ends with CS bit0 SET and the other
 *       15 port bits preserved — exact-value checks (prime 0xA5A4 ->
 *       0xA5A5) kill CS-bit/CS-address corruption, a dropped closing
 *       cs_high, an RMW-to-assign corruption, and a low/high framing
 *       order swap; clock byte must end 0x08 -> 0x09 (bit0 set, status
 *       bit3 preserved) on every transaction;
 *   (c) data round-trip / shift path: parity vectors read(0x14) -> 0x00
 *       and read(0x15) -> 0xFF (the host has no EEPROM device model, so
 *       spi_read_byte samples the static data line = LAST shifted bit =
 *       addr bit0 — still the real shift/sample path), write-tail byte
 *       vectors (0xA6/0x59 kill a reversed MSB/LSB loop direction;
 *       dropped spi_write_byte(data) killed by write(0x04,0x35) leaving
 *       0xFF01), sector read/write clamps (buf[6] stays primed 0xEE),
 *       eeprom_commit_to_ram staging copy + inverted verify copy, and
 *       eeprom_read_validate copy + 0x55 -> 0xAA consume marker.
 *
 * Documented limits (h5 style — real, not faked asserts):
 *   - a dropped INITIAL cs_low is not observable from a final-state host
 *     snapshot (no interleaving device); the CS RELEASE half of every
 *     frame and all CS-bit/address/order corruption IS observable;
 *   - the wait EXIT polarity (bit3 set/clear) is indistinguishable from
 *     final state when the status byte is static memory — the timeout
 *     BOUND (termination) is what is asserted, plus clock-bit side
 *     effects;
 *   - mid-frame bit values: a shifter that emits a constant bit0 for
 *     every position leaves the same final state (last bit only); loop
 *     DIRECTION and the last-bit value are asserted and killable;
 *   - disable/restore_interrupts are host stubs (no SR to observe);
 *     delay_loop iterations are not wall-clock-asserted (flakiness).
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 -I../include \
 *       link/link_eeprom.c ../c/eeprom.c -o /tmp/fwtest/link_eeprom
 * (eeprom.c compiles clean under -Werror — no unused-static relaxation.)
 */
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "eeprom.h"   /* real extern declarations (signature contract) */

/* ---- MMIO pins (mirror the firmware literals; runtime CHECKs on the
 * mapped pages carry revert detection, m8/l10 style) ------------------ */
#define PG_C      0xFFFFC000u
#define PG_D      0xFFFFD000u
#define PG_E      0xFFFFE000u
#define PG_F      0xFFFFF000u
#define PG_LEN    0x1000u

#define A_SPI_CLK  0xFFFFE401u  /* platform.h SPI_CLK_DATA_CTRL (u8) */
#define A_SPI_STAT 0xFFFFE403u  /* distinct status stand-in byte (host) */
#define A_SPI_DATA 0xFFFFE406u  /* platform.h SPI_DATA_0 (u16) */
#define A_SPI_CS   0xFFFFF730u  /* eeprom.c SPI_CS_PORT (u16) */

/* uint64 math: the F-page base 0xFFFFF000 + 0x1000 overflows 32 bits. */
#define IN_PG(base, a) ((uint64_t)(a) >= (uint64_t)(base) && \
                        (uint64_t)(a) < (uint64_t)(base) + (uint64_t)PG_LEN)

_Static_assert(IN_PG(PG_E, A_SPI_CLK) && IN_PG(PG_E, A_SPI_STAT) &&
               IN_PG(PG_E, A_SPI_DATA), "SPI regs outside mapped E page");
_Static_assert(IN_PG(PG_F, A_SPI_CS), "CS reg outside mapped F page");
_Static_assert(IN_PG(PG_C, EEPROM_STAGING_BASE) &&
               IN_PG(PG_C, EEPROM_STAGING_BASE + EEPROM_STAGING_SIZE - 1) &&
               IN_PG(PG_C, EEPROM_VERIFY_BASE) &&
               IN_PG(PG_C, EEPROM_VERIFY_BASE + EEPROM_STAGING_SIZE - 1),
               "staging/verify range outside mapped C page");
_Static_assert(IN_PG(PG_D, EEPROM_RAM_BUF_A) &&
               IN_PG(PG_D, EEPROM_RAM_BUF_A + 8) &&
               IN_PG(PG_D, EEPROM_RAM_BUF_A_MARKER),
               "validation buffer/marker outside mapped D page");
/* Real firmware cross-macro contracts (killable at compile time by a
 * firmware move of either macro): */
_Static_assert(EEPROM_RAM_BUF_A_MARKER == EEPROM_RAM_BUF_A + 8,
               "marker no longer buf[8] (read_validate contract)");
_Static_assert(EEPROM_VERIFY_BASE == EEPROM_STAGING_BASE + EEPROM_STAGING_SIZE,
               "verify copy no longer staging+256");

/* Transaction-frame primes: CS bit0 primed 0 (must end 1), other 15 bits
 * mixed (must be preserved exactly); clk byte primed with status bit3 set
 * (must end with bit0 ORed in, bit3 untouched). */
#define CS_PRIME 0xA5A4u
#define CS_GOOD  0xA5A5u  /* CS_PRIME | SPI_CS_BIT */
#define CLK_PRIME 0x08u   /* busy bit set, clock bit clear */
#define CLK_GOOD  0x09u

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint8_t *mm_u8(uint32_t addr)
{
    return (volatile uint8_t *)(uintptr_t)addr;
}

static volatile uint16_t *mm_u16(uint32_t addr)
{
    return (volatile uint16_t *)(uintptr_t)addr;
}

/* ---- Hang watchdog: a broken SPI wait timeout must FAIL, not hang ---- */
static char watch_msg[160];
static volatile sig_atomic_t watch_len;

static void on_alarm(int sig)
{
    (void)sig;
    if (watch_len > 0) {
        ssize_t w = write(STDOUT_FILENO, watch_msg, (size_t)watch_len);
        (void)w;
    }
    _exit(1);
}

static void arm_watch(const char *what)
{
    watch_len = (sig_atomic_t)snprintf(watch_msg, sizeof watch_msg,
        "FAIL: %s: SPI wait timeout bound broken (watchdog fired)\n", what);
    alarm(3);  /* correct code returns in microseconds; margin is ~1000x */
}

static void disarm_watch(void)
{
    alarm(0);
}

int main(void)
{
    void *pgc, *pgd, *pge, *pgf;
    unsigned i;

    signal(SIGALRM, on_alarm);

    pgc = mmap((void *)(uintptr_t)PG_C, PG_LEN, PROT_READ | PROT_WRITE,
               MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    pgd = mmap((void *)(uintptr_t)PG_D, PG_LEN, PROT_READ | PROT_WRITE,
               MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    pge = mmap((void *)(uintptr_t)PG_E, PG_LEN, PROT_READ | PROT_WRITE,
               MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    pgf = mmap((void *)(uintptr_t)PG_F, PG_LEN, PROT_READ | PROT_WRITE,
               MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (pgc == MAP_FAILED || pgd == MAP_FAILED ||
        pge == MAP_FAILED || pgf == MAP_FAILED) {
        printf("FAIL: mmap of MMIO pages failed\n");
        return 1;
    }

    /* ---- (1) SPI wait fast paths (status already ready) ------------- */
    *mm_u8(A_SPI_CLK) = 0x00u;   /* prime 0 -> must OR in clock bit */
    *mm_u8(A_SPI_STAT) = 0x07u;  /* bit3 clear: high-wait must not spin */
    spi_clk_high_wait(mm_u8(A_SPI_CLK), mm_u8(A_SPI_STAT));
    CHECK(*mm_u8(A_SPI_CLK) == 0x01u,
          "high-wait fast: clk %02X want 01 (clock bit not set)",
          (unsigned)*mm_u8(A_SPI_CLK));
    CHECK(*mm_u8(A_SPI_STAT) == 0x07u,
          "high-wait fast: stat %02X want 07 (status clobbered)",
          (unsigned)*mm_u8(A_SPI_STAT));

    *mm_u8(A_SPI_CLK) = 0x01u;   /* prime nonzero -> must clear clock bit */
    *mm_u8(A_SPI_STAT) = 0x0Cu;  /* bit3 set: low-wait must not spin */
    spi_clk_low_wait(mm_u8(A_SPI_CLK), mm_u8(A_SPI_STAT));
    CHECK(*mm_u8(A_SPI_CLK) == 0x00u,
          "low-wait fast: clk %02X want 00 (clock bit not cleared)",
          (unsigned)*mm_u8(A_SPI_CLK));
    CHECK(*mm_u8(A_SPI_STAT) == 0x0Cu,
          "low-wait fast: stat %02X want 0C (status clobbered)",
          (unsigned)*mm_u8(A_SPI_STAT));

    /* ---- (2) SPI wait TIMEOUT bound (stuck status, watchdog armed) -- */
    *mm_u8(A_SPI_CLK) = 0x00u;   /* prime 0 -> 1 */
    *mm_u8(A_SPI_STAT) = 0x0Cu;  /* bit3 never clears: must time out */
    arm_watch("spi_clk_high_wait(stuck)");
    spi_clk_high_wait(mm_u8(A_SPI_CLK), mm_u8(A_SPI_STAT));
    disarm_watch();
    CHECK(*mm_u8(A_SPI_CLK) == 0x01u,
          "high-wait timeout: clk %02X want 01 (clock bit not set)",
          (unsigned)*mm_u8(A_SPI_CLK));
    CHECK(*mm_u8(A_SPI_STAT) == 0x0Cu,
          "high-wait timeout: stat %02X want 0C (status clobbered)",
          (unsigned)*mm_u8(A_SPI_STAT));

    *mm_u8(A_SPI_CLK) = 0x01u;   /* prime nonzero -> 0 */
    *mm_u8(A_SPI_STAT) = 0x07u;  /* bit3 never sets: must time out */
    arm_watch("spi_clk_low_wait(stuck)");
    spi_clk_low_wait(mm_u8(A_SPI_CLK), mm_u8(A_SPI_STAT));
    disarm_watch();
    CHECK(*mm_u8(A_SPI_CLK) == 0x00u,
          "low-wait timeout: clk %02X want 00 (clock bit not cleared)",
          (unsigned)*mm_u8(A_SPI_CLK));
    CHECK(*mm_u8(A_SPI_STAT) == 0x07u,
          "low-wait timeout: stat %02X want 07 (status clobbered)",
          (unsigned)*mm_u8(A_SPI_STAT));

    /* Same-register shape (the real ECU: clk == stat == 0xFFFFE401). */
    *mm_u8(A_SPI_CLK) = 0x08u;  /* busy set, clock clear: -> 0x09 */
    arm_watch("spi_clk_high_wait(same-reg stuck)");
    spi_clk_high_wait(mm_u8(A_SPI_CLK), mm_u8(A_SPI_CLK));
    disarm_watch();
    CHECK(*mm_u8(A_SPI_CLK) == 0x09u,
          "high-wait same-reg: %02X want 09 (prime 08 + clock bit)",
          (unsigned)*mm_u8(A_SPI_CLK));

    *mm_u8(A_SPI_CLK) = 0x01u;  /* clock set, busy clear: -> 0x00 */
    arm_watch("spi_clk_low_wait(same-reg stuck)");
    spi_clk_low_wait(mm_u8(A_SPI_CLK), mm_u8(A_SPI_CLK));
    disarm_watch();
    CHECK(*mm_u8(A_SPI_CLK) == 0x00u,
          "low-wait same-reg: %02X want 00 (prime 01, clock cleared)",
          (unsigned)*mm_u8(A_SPI_CLK));

    /* ---- (3) bit/byte SPI primitives -------------------------------- */
    *mm_u8(A_SPI_CLK) = 0x00u;
    *mm_u16(A_SPI_DATA) = 0xFF00u;
    spi_write_bit(1u);
    CHECK(*mm_u16(A_SPI_DATA) == 0xFF01u,
          "write_bit(1): data %04X want FF01 (set-mask corrupt/dropped)",
          (unsigned)*mm_u16(A_SPI_DATA));
    CHECK(*mm_u8(A_SPI_CLK) == 0x01u,
          "write_bit(1): clk %02X want 01 (no final clock-high)",
          (unsigned)*mm_u8(A_SPI_CLK));

    *mm_u8(A_SPI_CLK) = 0x01u;
    *mm_u16(A_SPI_DATA) = 0xFF01u;  /* prime bit0=1 -> cleared */
    spi_write_bit(0u);
    CHECK(*mm_u16(A_SPI_DATA) == 0xFF00u,
          "write_bit(0): data %04X want FF00 (clear-mask corrupt; upper "
          "bits must survive)", (unsigned)*mm_u16(A_SPI_DATA));
    CHECK(*mm_u8(A_SPI_CLK) == 0x01u,
          "write_bit(0): clk %02X want 01 (no final clock-high)",
          (unsigned)*mm_u8(A_SPI_CLK));

    *mm_u8(A_SPI_CLK) = 0x00u;
    *mm_u16(A_SPI_DATA) = 0xFF01u;
    CHECK(spi_read_bit() == 1u, "read_bit line=1: returned 0 (polarity)");
    CHECK(*mm_u16(A_SPI_DATA) == 0xFF01u,
          "read_bit line=1: data %04X want FF01 (read clobbered line)",
          (unsigned)*mm_u16(A_SPI_DATA));
    CHECK(*mm_u8(A_SPI_CLK) == 0x01u,
          "read_bit line=1: clk %02X want 01 (no final clock-high)",
          (unsigned)*mm_u8(A_SPI_CLK));

    *mm_u8(A_SPI_CLK) = 0x01u;
    *mm_u16(A_SPI_DATA) = 0xFF00u;  /* prime nonzero byte, line bit0=0 */
    CHECK(spi_read_bit() == 0u, "read_bit line=0: returned 1 (polarity)");
    CHECK(*mm_u16(A_SPI_DATA) == 0xFF00u,
          "read_bit line=0: data %04X want FF00 (read clobbered line)",
          (unsigned)*mm_u16(A_SPI_DATA));

    /* Loop direction: 0xA6 has bit7=1/b0=0, 0x59 the reverse — a
     * reversed i=0..7 loop shifts the WRONG bit last and dies here. */
    *mm_u8(A_SPI_CLK) = 0x00u;
    *mm_u16(A_SPI_DATA) = 0xFF01u;  /* prime bit0=1 -> last bit of 0xA6 =0 */
    spi_write_byte(0xA6u);
    CHECK(*mm_u16(A_SPI_DATA) == 0xFF00u,
          "write_byte(A6): data %04X want FF00 (last shifted bit != b0)",
          (unsigned)*mm_u16(A_SPI_DATA));
    CHECK(*mm_u8(A_SPI_CLK) == 0x01u,
          "write_byte(A6): clk %02X want 01 (no final clock-high)",
          (unsigned)*mm_u8(A_SPI_CLK));

    *mm_u8(A_SPI_CLK) = 0x00u;
    *mm_u16(A_SPI_DATA) = 0xFF00u;  /* prime bit0=0 -> last bit of 0x59 =1 */
    spi_write_byte(0x59u);
    CHECK(*mm_u16(A_SPI_DATA) == 0xFF01u,
          "write_byte(59): data %04X want FF01 (last shifted bit != b0)",
          (unsigned)*mm_u16(A_SPI_DATA));

    *mm_u8(A_SPI_CLK) = 0x00u;
    *mm_u16(A_SPI_DATA) = 0xFF01u;
    {
        uint8_t rb = spi_read_byte();
        CHECK(rb == 0xFFu,
              "read_byte line=1: got %02X want FF (accumulate broken)",
              (unsigned)rb);
    }
    *mm_u16(A_SPI_DATA) = 0xFF00u;  /* prime nonzero byte, line bit0=0 */
    {
        uint8_t rb = spi_read_byte();
        CHECK(rb == 0x00u,
              "read_byte line=0: got %02X want 00 (accumulate sets bits "
              "unconditionally / polarity)", (unsigned)rb);
    }
    CHECK(*mm_u16(A_SPI_DATA) == 0xFF00u,
          "read_byte line=0: data %04X want FF00 (read clobbered line)",
          (unsigned)*mm_u16(A_SPI_DATA));

    /* ---- (4) eeprom_read_byte: command/addr framing + parity -------- */
    *mm_u16(A_SPI_CS) = CS_PRIME;
    *mm_u8(A_SPI_CLK) = CLK_PRIME;
    *mm_u16(A_SPI_DATA) = 0xFF00u;
    {
        uint8_t v = eeprom_read_byte(0x15u);
        CHECK(v == 0xFFu,
              "read_byte(15): got %02X want FF (addr shift/sample path)",
              (unsigned)v);
        CHECK(*mm_u16(A_SPI_DATA) == 0xFF01u,
              "read_byte(15): data %04X want FF01 (addr b0 not shifted)",
              (unsigned)*mm_u16(A_SPI_DATA));
        CHECK(*mm_u16(A_SPI_CS) == CS_GOOD,
              "read_byte(15): CS %04X want %04X (framing/CS-bit/address)",
              (unsigned)*mm_u16(A_SPI_CS), (unsigned)CS_GOOD);
        CHECK(*mm_u8(A_SPI_CLK) == CLK_GOOD,
              "read_byte(15): clk %02X want 09 (clock tail/status clobber)",
              (unsigned)*mm_u8(A_SPI_CLK));
    }

    *mm_u16(A_SPI_CS) = CS_PRIME;
    *mm_u8(A_SPI_CLK) = CLK_PRIME;
    *mm_u16(A_SPI_DATA) = 0xFF01u;
    {
        uint8_t v = eeprom_read_byte(0x14u);
        CHECK(v == 0x00u,
              "read_byte(14): got %02X want 00 (parity: even addr must "
              "read 00 on the host data line)", (unsigned)v);
        CHECK(*mm_u16(A_SPI_DATA) == 0xFF00u,
              "read_byte(14): data %04X want FF00 (addr b0 not shifted)",
              (unsigned)*mm_u16(A_SPI_DATA));
        CHECK(*mm_u16(A_SPI_CS) == CS_GOOD,
              "read_byte(14): CS %04X want %04X (framing/CS-bit/address)",
              (unsigned)*mm_u16(A_SPI_CS), (unsigned)CS_GOOD);
        CHECK(*mm_u8(A_SPI_CLK) == CLK_GOOD,
              "read_byte(14): clk %02X want 09 (clock tail/status clobber)",
              (unsigned)*mm_u8(A_SPI_CLK));
    }

    /* ---- (5) eeprom_write_byte: WREN + WRITE framing, data tail ----- */
    *mm_u16(A_SPI_CS) = CS_PRIME;
    *mm_u8(A_SPI_CLK) = CLK_PRIME;
    *mm_u16(A_SPI_DATA) = 0xFF00u;  /* even addr tail would leave 0 */
    eeprom_write_byte(0x04u, 0x35u);
    CHECK(*mm_u16(A_SPI_DATA) == 0xFF01u,
          "write_byte(04,35): data %04X want FF01 (data byte not shifted)",
          (unsigned)*mm_u16(A_SPI_DATA));
    CHECK(*mm_u16(A_SPI_CS) == CS_GOOD,
          "write_byte(04,35): CS %04X want %04X (framing/CS-bit/address)",
          (unsigned)*mm_u16(A_SPI_CS), (unsigned)CS_GOOD);
    CHECK(*mm_u8(A_SPI_CLK) == CLK_GOOD,
          "write_byte(04,35): clk %02X want 09 (clock tail/status clobber)",
          (unsigned)*mm_u8(A_SPI_CLK));

    /* ---- (6) sector write/read/erase + clamps ----------------------- */
    {
        static const uint8_t pat[4] = { 0x96u, 0x69u, 0x3Cu, 0xC3u };
        uint8_t buf[16];
        uint8_t big[16];

        *mm_u16(A_SPI_CS) = CS_PRIME;
        *mm_u8(A_SPI_CLK) = CLK_PRIME;
        *mm_u16(A_SPI_DATA) = 0xFF00u;
        eeprom_write_sector(0x20u, pat, sizeof pat);
        CHECK(*mm_u16(A_SPI_DATA) == 0xFF01u,
              "write_sector: data %04X want FF01 (last payload byte 0xC3 "
              "not shifted)", (unsigned)*mm_u16(A_SPI_DATA));
        CHECK(*mm_u16(A_SPI_CS) == CS_GOOD,
              "write_sector: CS %04X want %04X (framing/CS-bit/address)",
              (unsigned)*mm_u16(A_SPI_CS), (unsigned)CS_GOOD);
        CHECK(*mm_u8(A_SPI_CLK) == CLK_GOOD,
              "write_sector: clk %02X want 09 (clock tail/status clobber)",
              (unsigned)*mm_u8(A_SPI_CLK));

        /* NULL / zero-length guards: no transaction may start. */
        *mm_u16(A_SPI_CS) = CS_PRIME;
        *mm_u8(A_SPI_CLK) = CLK_PRIME;
        *mm_u16(A_SPI_DATA) = 0xFF00u;
        eeprom_write_sector(0x20u, NULL, 4u);
        eeprom_write_sector(0x20u, pat, 0u);
        CHECK(*mm_u16(A_SPI_CS) == CS_PRIME,
              "write_sector guard: CS %04X want %04X (guard dropped)",
              (unsigned)*mm_u16(A_SPI_CS), (unsigned)CS_PRIME);
        CHECK(*mm_u16(A_SPI_DATA) == 0xFF00u,
              "write_sector guard: data %04X want FF00 (shift ran)",
              (unsigned)*mm_u16(A_SPI_DATA));

        memset(buf, 0xEE, sizeof buf);
        *mm_u16(A_SPI_CS) = CS_PRIME;
        *mm_u8(A_SPI_CLK) = CLK_PRIME;
        eeprom_read_sector(0x14u, buf, 4u);
        for (i = 0; i < 4u; i++) {
            CHECK(buf[i] == 0x00u,
                  "read_sector(14)[%u]: %02X want 00 (primed EE, fill "
                  "loop dropped?)", i, (unsigned)buf[i]);
        }
        CHECK(*mm_u16(A_SPI_CS) == CS_GOOD,
              "read_sector(14): CS %04X want %04X (framing/CS-bit)",
              (unsigned)*mm_u16(A_SPI_CS), (unsigned)CS_GOOD);

        memset(buf, 0xEE, sizeof buf);
        eeprom_read_sector(0x15u, buf, 4u);
        for (i = 0; i < 4u; i++) {
            CHECK(buf[i] == 0xFFu,
                  "read_sector(15)[%u]: %02X want FF (primed EE)",
                  i, (unsigned)buf[i]);
        }

        /* addr=250, len=16 -> clamped to 6: buf[6..15] must stay primed
         * (kills a dropped range clamp: 16 bytes would overwrite them). */
        memset(big, 0xEE, sizeof big);
        eeprom_read_sector(0xFAu, big, sizeof big);
        for (i = 0; i < 6u; i++) {
            CHECK(big[i] == 0x00u,
                  "read_sector clamp(FA,16)[%u]: %02X want 00",
                  i, (unsigned)big[i]);
        }
        for (i = 6u; i < 16u; i++) {
            CHECK(big[i] == 0xEEu,
                  "read_sector clamp(FA,16)[%u]: %02X want EE (range clamp "
                  "dropped — bytes past 256 written)", i, (unsigned)big[i]);
        }

        memset(buf, 0xEE, sizeof buf);
        *mm_u16(A_SPI_CS) = CS_PRIME;
        eeprom_read_sector(0x14u, NULL, 4u);
        eeprom_read_sector(0x14u, buf, 0u);
        CHECK(*mm_u16(A_SPI_CS) == CS_PRIME,
              "read_sector guard: CS %04X want %04X (guard dropped)",
              (unsigned)*mm_u16(A_SPI_CS), (unsigned)CS_PRIME);
        CHECK(buf[0] == 0xEEu,
              "read_sector guard: buf[0] %02X want EE (fill ran)",
              (unsigned)buf[0]);

        /* Erase: WREN + SECTOR_ERASE + addr 0x41 (b0=1) framing. */
        *mm_u16(A_SPI_CS) = CS_PRIME;
        *mm_u8(A_SPI_CLK) = CLK_PRIME;
        *mm_u16(A_SPI_DATA) = 0xFF00u;
        eeprom_erase_sector(0x41u);
        CHECK(*mm_u16(A_SPI_DATA) == 0xFF01u,
              "erase(41): data %04X want FF01 (addr byte not shifted)",
              (unsigned)*mm_u16(A_SPI_DATA));
        CHECK(*mm_u16(A_SPI_CS) == CS_GOOD,
              "erase(41): CS %04X want %04X (framing/CS-bit)",
              (unsigned)*mm_u16(A_SPI_CS), (unsigned)CS_GOOD);
        CHECK(*mm_u8(A_SPI_CLK) == CLK_GOOD,
              "erase(41): clk %02X want 09 (clock tail/status clobber)",
              (unsigned)*mm_u8(A_SPI_CLK));
    }

    /* ---- (7) RAM validation: read_validate / is_eeprom_valid ------- */
    {
        static const uint8_t pat[8] = {
            0x12u, 0x34u, 0x56u, 0x78u, 0x9Au, 0xBCu, 0xDEu, 0xF0u
        };
        uint8_t dest[8];
        int rc;

        /* invalid marker: no copy, no consume, returns -1. */
        memset(dest, 0x77, sizeof dest);
        for (i = 0; i < 8u; i++) {
            *mm_u8(EEPROM_RAM_BUF_A + i) = 0xEEu;
        }
        *mm_u8(EEPROM_RAM_BUF_A_MARKER) = 0xEEu;  /* nonzero prime */
        rc = eeprom_read_validate(dest);
        CHECK(rc == -1, "validate bad marker: rc=%d want -1", rc);
        for (i = 0; i < 8u; i++) {
            CHECK(dest[i] == 0x77u,
                  "validate bad marker: dest[%u] %02X want 77 (unconditional "
                  "copy)", i, (unsigned)dest[i]);
        }
        CHECK(*mm_u8(EEPROM_RAM_BUF_A_MARKER) == 0xEEu,
              "validate bad marker: marker %02X want EE (unconditional "
              "consume)", (unsigned)*mm_u8(EEPROM_RAM_BUF_A_MARKER));

        /* valid marker 0x55: copy 8 bytes, consume to 0xAA, returns 1. */
        memset(dest, 0xEE, sizeof dest);  /* nonzero prime before expect */
        for (i = 0; i < 8u; i++) {
            *mm_u8(EEPROM_RAM_BUF_A + i) = pat[i];
        }
        *mm_u8(EEPROM_RAM_BUF_A_MARKER) = EEPROM_VALID_MARKER;
        rc = eeprom_read_validate(dest);
        CHECK(rc == 1, "validate good: rc=%d want 1", rc);
        for (i = 0; i < 8u; i++) {
            CHECK(dest[i] == pat[i],
                  "validate good: dest[%u] %02X want %02X (copy broken)",
                  i, (unsigned)dest[i], (unsigned)pat[i]);
        }
        CHECK(*mm_u8(EEPROM_RAM_BUF_A_MARKER) == EEPROM_CONSUMED_MARKER,
              "validate good: marker %02X want AA (consume dropped)",
              (unsigned)*mm_u8(EEPROM_RAM_BUF_A_MARKER));

        /* is_eeprom_valid marker truth table (nonzero primes first). */
        *mm_u8(EEPROM_RAM_BUF_A_MARKER) = EEPROM_VALID_MARKER;
        CHECK(is_eeprom_valid() == 1,
              "is_valid(55): rc=%d want 1", is_eeprom_valid());
        *mm_u8(EEPROM_RAM_BUF_A_MARKER) = 0xEEu;
        CHECK(is_eeprom_valid() == 0,
              "is_valid(EE): rc=%d want 0", is_eeprom_valid());
        *mm_u8(EEPROM_RAM_BUF_A_MARKER) = EEPROM_CONSUMED_MARKER;
        CHECK(is_eeprom_valid() == 0,
              "is_valid(AA): rc=%d want 0", is_eeprom_valid());
    }

    /* ---- (8) staging commit: round-trip + inverted verify copy ------ */
    {
        uint8_t src[64];
        uint8_t src512[512];

        for (i = 0; i < 64u; i++) {
            src[i] = (uint8_t)(i * 7u + 3u);
        }
        memset((void *)(uintptr_t)EEPROM_STAGING_BASE, 0xEE, 256);
        memset((void *)(uintptr_t)EEPROM_VERIFY_BASE, 0xEE, 256);
        eeprom_commit_to_ram(src, sizeof src);
        for (i = 0; i < 64u; i++) {
            CHECK(*mm_u8(EEPROM_STAGING_BASE + i) == src[i],
                  "commit staging[%u]: %02X want %02X (round-trip broken)",
                  i, (unsigned)*mm_u8(EEPROM_STAGING_BASE + i),
                  (unsigned)src[i]);
            CHECK(*mm_u8(EEPROM_VERIFY_BASE + i) == (uint8_t)(src[i] ^ 0xFFu),
                  "commit verify[%u]: %02X want %02X (inverted copy "
                  "broken)", i, (unsigned)*mm_u8(EEPROM_VERIFY_BASE + i),
                  (unsigned)(src[i] ^ 0xFFu));
        }
        CHECK(*mm_u8(EEPROM_STAGING_BASE + 64u) == 0xEEu,
              "commit bounds: staging[64] %02X want EE (wrote past len)",
              (unsigned)*mm_u8(EEPROM_STAGING_BASE + 64u));
        CHECK(*mm_u8(EEPROM_VERIFY_BASE + 64u) == 0xEEu,
              "commit bounds: verify[64] %02X want EE (wrote past len)",
              (unsigned)*mm_u8(EEPROM_VERIFY_BASE + 64u));

        /* NULL / zero-length guards. */
        *mm_u8(EEPROM_STAGING_BASE) = 0x5Au;
        eeprom_commit_to_ram(NULL, 10u);
        eeprom_commit_to_ram(src, 0u);
        CHECK(*mm_u8(EEPROM_STAGING_BASE) == 0x5Au,
              "commit guard: staging[0] %02X want 5A (guard dropped)",
              (unsigned)*mm_u8(EEPROM_STAGING_BASE));

        /* len=513 > EEPROM_STAGING_SIZE: clamped to 256 — verify[0] must
         * be src[0]^FF (a dropped clamp later overwrites it with
         * src[256] via the staging overrun into the verify region). */
        for (i = 0; i < 512u; i++) {
            src512[i] = (uint8_t)(i * 7u + 3u);
        }
        memset((void *)(uintptr_t)EEPROM_STAGING_BASE, 0xEE, 256);
        memset((void *)(uintptr_t)EEPROM_VERIFY_BASE, 0xEE, 256);
        eeprom_commit_to_ram(src512, sizeof src512 + 1u);
        CHECK(*mm_u8(EEPROM_VERIFY_BASE) ==
                  (uint8_t)(src512[0] ^ 0xFFu),
              "commit clamp: verify[0] %02X want %02X (staging clamp "
              "dropped — overrun corrupted verify copy)",
              (unsigned)*mm_u8(EEPROM_VERIFY_BASE),
              (unsigned)(src512[0] ^ 0xFFu));
        CHECK(*mm_u8(EEPROM_VERIFY_BASE + 100u) ==
                  (uint8_t)(src512[100] ^ 0xFFu),
              "commit clamp: verify[100] %02X want %02X",
              (unsigned)*mm_u8(EEPROM_VERIFY_BASE + 100u),
              (unsigned)(src512[100] ^ 0xFFu));
        CHECK(*mm_u8(EEPROM_STAGING_BASE + 255u) == src512[255],
              "commit clamp: staging[255] %02X want %02X",
              (unsigned)*mm_u8(EEPROM_STAGING_BASE + 255u),
              (unsigned)src512[255]);
    }

    munmap(pgc, PG_LEN);
    munmap(pgd, PG_LEN);
    munmap(pge, PG_LEN);
    munmap(pgf, PG_LEN);

    if (failures == 0) {
        printf("PASS link_eeprom (real eeprom.c TU)\n");
    } else {
        printf("%d FAILURES link_eeprom\n", failures);
    }
    return failures != 0;
}
