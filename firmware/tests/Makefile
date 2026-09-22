# firmware/tests/Makefile — host regression harnesses for firmware bugfixes
#
# Each test_<...>.c is self-contained (target MMIO cannot be dereferenced on
# the host; the harnesses replicate the exact fixed expressions) and builds
# with gcc -std=c11 -Wall -Wextra -Werror.
#
# Usage:
#   make            # build all harnesses into $(OUTDIR) (default /tmp/fwtest)
#   make check      # gate (source-grep tripwire) + build + run all (must pass)
#   make gate       # source-grep tripwire only: fixed patterns present in the
#                   # real firmware sources, buggy idioms absent. The test_*
#                   # harnesses are pure models; the link_* harnesses do link
#                   # real firmware sources, but the tripwire is what catches
#                   # a firmware revert on the model-only paths.
#   make demo-buggy # build with -DTEST_BUGGY and run: each must FAIL,
#                   # demonstrating the harness reproduces the pre-fix bug
#   make clean
#
# Binaries live outside the repo so `git status` only shows sources.

CC ?= gcc
CFLAGS = -std=c11 -Wall -Wextra -Werror -O2
OUTDIR ?= /tmp/fwtest

TESTS = test_c1_addr_width \
        test_c2_sid34_size \
        test_c3_crank_tooth \
        test_h1_can_regs \
        test_h2_dtc_status \
        test_h3_dispatch \
        test_h4_dwell_clamp \
        test_h5_sid22_bounds \
        test_m1_crank_fsm \
        test_m6_gap_sentinel \
        test_m8_mailbox_bits \
        test_l7_can215 \
        test_m3_sched_enqueue \
        test_m4_serial_rx \
        test_n2_rtos_mask \
        test_n1_sa_lfsr \
        test_n7_sa_gates \
        test_n3_dtc_writer \
        test_m2_checksum \
        test_m7_testerpresent \
        test_l10_injector_flag \
        test_small_fixes

BINS = $(addprefix $(OUTDIR)/,$(TESTS))

# Link-pilot harnesses: compile-link-run against the REAL firmware headers
# (not models). Sources live in link/, binaries are link_<name>.
LINK_TESTS = link_n2_rtos_mask link_c1_addr_width link_h1_mbox link_m2_checksum link_h5_sid22 link_h4_dwell link_h2_dtc_status link_m8_mailbox_bits link_m7_c2_tp_sid34 link_l10_injector_flag link_m4_serial_rx link_rtos_queue_dispatch
LINK_BINS = $(addprefix $(OUTDIR)/,$(LINK_TESTS))
CFLAGS_LINK = $(CFLAGS) -I$(FW_INC)

# Firmware source locations (tripwire target, not linked).
FW_C := $(abspath ../c)
FW_INC := $(abspath ../include)

.PHONY: all check gate demo-buggy clean link-all link-check

all: $(BINS)

$(OUTDIR)/link_%: link/link_%.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) $< -o $@ -lm

# h1 links the REAL can.c TU (H1-fixed pure mailbox getters). can.c has two
# pre-existing unused statics (can_parse_mailbox_id/dir); relax only that
# warning into non-error for this TU link (firmware sources untouched).
$(OUTDIR)/link_h1_mbox: link/link_h1_mbox.c $(FW_C)/can.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) -Wno-error=unused-function $^ -o $@ -lm

# m2 links the REAL dtc.c TU (M2 MMIO pilot). dtc.c has zero undefined
# externs (nm -u clean) so no stubs; it maps the 0xFFFF8xxx RAM page with
# mmap(MAP_FIXED) at run time — every load/store executes for real.
# Same unused-static relaxation as h1 (firmware sources untouched).
$(OUTDIR)/link_m2_checksum: link/link_m2_checksum.c $(FW_C)/dtc.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) -Wno-error=unused-function $^ -o $@ -lm

# h5 links the REAL uds.c TU (H5 constant-DID pilot). uds.c references
# three DTC SID handlers the h5 paths never call (obd_sid12/14/18, used by
# uds_handler dispatch arms only); the harness provides trivial stubs for
# those three linker-demanded symbols and asserts they stay uncalled, so
# zero MMIO executes (no sensor 0xFFFFCAxx deref, no uds_init call).
$(OUTDIR)/link_h5_sid22: link/link_h5_sid22.c $(FW_C)/uds.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) $^ -o $@ -lm

# h4 links the REAL engine.c TU (H4 dwell clamp pilot, class M). engine.c
# has zero undefined externs (nm -u clean) so no stubs; the harness maps
# the 0xFFFFB000 RAM page with mmap(MAP_FIXED) so the real 0xFFFFBC84/88
# float loads execute for real. -DFW_HOST_TEST compiles in the host-only
# getDwellTimeUs_forHostTest accessor (engine.c/.h) — production builds
# never define it, so the normal firmware is unaffected.
$(OUTDIR)/link_h4_dwell: link/link_h4_dwell.c $(FW_C)/engine.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) -DFW_HOST_TEST $^ -o $@ -lm

# h2 links the REAL dtc.c TU + the REAL dtc_read_status inline (H2
# SEVERITY|FLAGS3 composite pilot, class M). Same TU, page, and
# unused-static relaxation as m2 (firmware sources untouched); the test
# additionally drives the real sid18/sid12/worst-priority readers and the
# dtc_state_machine SET writer over the mmap-backed primary table.
$(OUTDIR)/link_h2_dtc_status: link/link_h2_dtc_status.c $(FW_C)/dtc.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) -Wno-error=unused-function $^ -o $@ -lm

# m8 links the REAL can.c TU (M8 16-bit mailbox-int-enable RMW pilot,
# class M). Same TU and unused-static relaxation as h1 (firmware sources
# untouched); the harness maps the 0xFFFFExxx page with mmap(MAP_FIXED)
# at 0xFFFFE000 so the real 16-bit RMW on 0xFFFFE400 (CAN0) / 0xFFFFE600
# (CAN1) executes for real — every enable, mask-wrap, preserve, and
# bank-isolation vector runs against mapped memory, not a model.
$(OUTDIR)/link_m8_mailbox_bits: link/link_m8_mailbox_bits.c $(FW_C)/can.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) -Wno-error=unused-function $^ -o $@ -lm

# m7/c2 links the REAL uds.c TU (M7 TesterPresent gate + C2 sid34/36/37
# download chain pilot). uds.c compiles clean under -Werror, and the
# harness supplies the same three DTC stubs as h5 (obd_sid12/14/18 —
# linker-demanded only, asserted uncalled). Only SID 0x3E goes through
# uds_handler (returns before the ROM dispatch lookup); sid34/36/37 are
# entered as direct externs (h5 style), so zero ROM bytes are read. The
# harness mmap-maps the 0xFFFFD RAM page (session/security/TP/DL image)
# and a 0x00070000 flash sandbox (sid36 payload target, inside the C2
# 3+3 flash window) with MAP_FIXED — every store executes for real.
$(OUTDIR)/link_m7_c2_tp_sid34: link/link_m7_c2_tp_sid34.c $(FW_C)/uds.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) $^ -o $@ -lm

# l10 links the REAL dtc.c TU (L10 injector fault-flag store on the
# fuel-cut early-return path, class M). Same TU and unused-static
# relaxation as m2/h2 (nm -u clean, zero stubs); the harness mmap-maps TWO
# 4 KiB pages with MAP_FIXED — 0xFFFFC000 (injector cluster
# 0xFFFFC99C..0xFFFFC9BF) and 0xFFFFD000 (fuel-cut flag 0xFFFFD201) —
# so every load/store, including the L10 store inside the fuel-cut early
# return, executes for real against mapped memory, not a model.
$(OUTDIR)/link_l10_injector_flag: link/link_l10_injector_flag.c $(FW_C)/dtc.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) -Wno-error=unused-function $^ -o $@ -lm

# m4 links the REAL serial.c TU + the REAL timer.c TU (M4 owned-RX fix
# pilot, class M). serial.c's only undefined externs (nm -u) are
# atu_timer_init / atu_capture_compare_init, both provided in-repo by
# timer.c (nm -u clean, MMIO-only, no ROM) and both called only from
# serial_init — and serial_init is where the M4 arming lives, so init
# MUST run (uncalled-stub style does not apply; real timer.c beats empty
# stubs). Both TUs compile clean under -Werror (no unused-static
# relaxation). The harness mmap-maps ONE 4 KiB page at 0xFFFFF000 with
# MAP_FIXED — covering INTC 0xFFFFF02E and the whole ATU block
# 0xFFFFF700..0xFFFFF7B0 (TSTR/TCR/TIOR/TIER/TGR byte lanes/TISRA) — so
# serial_init's real timer MMIO, the intc_reg_write enable/disable
# values, the RX low-lane TGR captures, and the TISRA flag-only RMW
# clears all execute against mapped memory, not a model.
$(OUTDIR)/link_m4_serial_rx: link/link_m4_serial_rx.c $(FW_C)/serial.c $(FW_C)/timer.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) $^ -o $@ -lm

# p12 links the REAL rtos.c TU (link pilot 12 — first time the .c BODY is
# linked; n2 only linked the rtos.h header inlines). nm -u rtos.o is EMPTY
# (zero undefined externs) so no stubs; the TU compiles clean under -Werror
# (no unused-static relaxation needed). The harness mmap-maps ONE 4 KiB
# page at 0xFFFFD000 with MAP_FIXED — covering the task queue
# 0xFFFFD4E0..0xFFFFD7FF and the uint16 queue indexes 0xFFFFDFB4/0xFFFFDFB6
# (the same D page proven by m7/c2 and l10) — so the rtos_init 0xFF slot
# fill, every index/queue load/store, the enqueue/dequeue big-endian byte
# stores, and the dispatch/scheduler/context paths all execute for real
# against mapped memory. -no-pie: rtos_dispatch casts the 24-bit
# RTOS_DISP_HANDLER_MASK handler field to a function pointer, so harness
# handler addresses must live in the low 16 MiB (non-PIE .text at
# 0x400000) — a PIE address would be truncated by the mask. No ROM read:
# objdump immediates of rtos.o are only 0xFFFFD4E0/0xFFFFD800/
# 0xFFFFDFB4/0xFFFFDFB6 (0x6873C dispatch table is comment-only).
$(OUTDIR)/link_rtos_queue_dispatch: link/link_rtos_queue_dispatch.c $(FW_C)/rtos.c | $(OUTDIR)
	$(CC) $(CFLAGS_LINK) -no-pie $^ -o $@ -lm

link-all: $(LINK_BINS)

link-check: gate link-all
	@for t in $(LINK_TESTS); do \
		echo "== $$t (link) =="; \
		$(OUTDIR)/$$t || exit 1; \
	done
	@echo "firmware/tests: all $(words $(LINK_TESTS)) link harnesses passed"

$(OUTDIR):
	mkdir -p $(OUTDIR)

$(OUTDIR)/%: %.c | $(OUTDIR)
	$(CC) $(CFLAGS) $< -o $@ -lm

check: gate all
	@for t in $(TESTS); do \
		echo "== $$t =="; \
		$(OUTDIR)/$$t || exit 1; \
	done
	@echo "firmware/tests: all $(words $(TESTS)) harnesses passed"

# Source-grep tripwire: for each of the 8 fixes, the fixed pattern must be
# present in the real sources and the buggy idiom must be absent (code lines,
# not comments — negatives match call-site/statement forms that never appear
# in comments). Fails closed on any firmware revert.
gate:
	@echo "gate: source-grep tripwire (8 fixes)"
	@set -e; \
	echo "-- C1 addr width (32-bit RAM addresses)"; \
	grep -q "uint32_t addr = TASK_QUEUE_BASE" $(FW_C)/main.c; \
	grep -q "uint32_t addr = DTC_PRIMARY_TABLE_BASE" $(FW_INC)/dtc.h; \
	! grep -q "uint16_t addr = TASK_QUEUE" $(FW_C)/main.c; \
	! grep -q "uint16_t addr = DTC_PRIMARY" $(FW_C)/dtc.c $(FW_INC)/dtc.h; \
	echo "-- C2 sid34 size (right-aligned BE24/BE32 store)"; \
	grep -q "mem_addr >> 16" $(FW_C)/uds.c; \
	grep -q "mem_size >> 24" $(FW_C)/uds.c; \
	grep -q "mem_size >> 16" $(FW_C)/uds.c; \
	! grep -q "SIZE_B0_ADDR.*size_bytes" $(FW_C)/uds.c; \
	echo "-- C3 crank tooth (ISR advances counter)"; \
	grep -q "crank_tooth_count++" $(FW_C)/engine.c; \
	echo "-- H1 CAN regs (absolute addresses)"; \
	grep -q "HCAN_MBOX_REG_ADDR" $(FW_C)/can.c; \
	grep -q "HCAN_MBOX_READY_ADDR" $(FW_C)/can.c; \
	grep -q "HCAN_MBOX_STATUS_ADDR" $(FW_C)/can.c; \
	grep -q "HCAN_MBOX_DATA_RDY_ADDR" $(FW_C)/can.c; \
	! grep -q "can_get_mailbox_offset_high(.*HCAN_REG_MBOX" $(FW_C)/can.c; \
	! grep -q "can_get_mailbox_offset_high(.*HCAN_MBOX_OFFSET)" $(FW_C)/can.c; \
	echo "-- H2 DTC status (SEVERITY|FLAGS3 composite)"; \
	grep -q "DTC_REC_SEVERITY_OFFSET" $(FW_INC)/dtc.h; \
	grep -q "DTC_REC_FLAGS3_OFFSET" $(FW_INC)/dtc.h; \
	grep -q "sev | fl3" $(FW_INC)/dtc.h; \
	! grep -A10 "dtc_read_status" $(FW_INC)/dtc.h | grep -q "TYPE_OFFSET"; \
	echo "-- H3 dispatch (implemented SIDs reachable)"; \
	grep -q "case UDS_SID_CLEAR_DTC" $(FW_C)/uds.c; \
	grep -q "case UDS_SID_READ_DTC_INFO" $(FW_C)/uds.c; \
	grep -q "case UDS_SID_READ_DTC_STATUS" $(FW_C)/uds.c; \
	grep -q "case UDS_SID_OBD_SVC1" $(FW_C)/uds.c; \
	grep -q "case UDS_SID_OBD_SVC9" $(FW_C)/uds.c; \
	echo "-- H3 note: no 0x0A arm by design (ROM table 0x5F57C has no 0x0A);"; \
	echo "-- H3 note: harness asserts 0x0A falls through to NRC 0x11;"; \
	! grep -q "UDS_SID_OBD_SVCA" $(FW_C)/uds.c $(FW_INC)/uds.h; \
	! grep -q "obd_service_A" $(FW_C)/uds.c $(FW_INC)/uds.h; \
	echo "-- H4 dwell clamp (clamp float BEFORE convert, NaN inhibit)"; \
	grep -q "divided != divided" $(FW_C)/engine.c; \
	grep -q "divided < (float)DWELL_MIN_US" $(FW_C)/engine.c; \
	grep -q "divided > (float)DWELL_MAX_US" $(FW_C)/engine.c; \
	! grep -q "if (dwell_time_us < DWELL_MIN_US)" $(FW_C)/engine.c; \
	! grep -q "if (dwell_time_us > DWELL_MAX_US)" $(FW_C)/engine.c; \
	echo "-- H5 sid22 bounds (wide index + output bound)"; \
	grep -q "static int sid22_need" $(FW_C)/uds.c; \
	grep -q "uint16_t idx = 1" $(FW_C)/uds.c; \
	grep -q "sid22_need(idx" $(FW_C)/uds.c; \
	! grep -q "uint8_t idx = 1" $(FW_C)/uds.c; \
	echo "-- N1 SA LFSR (ROM-verified Galois LFSR, 3-byte seed, gated SendKey)"; \
	grep -q "uds_sa_compute_key" $(FW_C)/uds.c; \
	grep -q "UDS_SA_LFSR_TAPS" $(FW_C)/uds.c; \
	grep -q "UDS_SA_INIT_TABLE_ADDR" $(FW_C)/uds.c; \
	grep -q "return len + 3" $(FW_C)/uds.c; \
	! grep -q "level_table\[4\]\[3\]" $(FW_C)/uds.c; \
	! grep -q "seed\[3\] = " $(FW_C)/uds.c; \
	echo "-- N7 SA gates (seed data_len==0, key data_len==3)"; \
	grep -q "data_len != 0" $(FW_C)/uds.c; \
	grep -q "data_len != 3" $(FW_C)/uds.c; \
	! sed -n '/^int obd_sid27_securityAccess/,/^}/p' $(FW_C)/uds.c | grep -q "data_len < "; \
	echo "-- N3 DTC writer (+0x06 status byte on SET)"; \
	grep -q "DTC_STATUS_CONFIRMED | DTC_STATUS_FAILED" $(FW_C)/dtc.c; \
	grep -q "FIRMWARE-LOCAL" $(FW_INC)/dtc.h; \
	echo "-- M2 checksum (guard words + 15-byte sum vs 0xA5)"; \
	grep -q "(sum & 0xFFu) != 0xA5u" $(FW_C)/dtc.c; \
	grep -q "0xFFFF8920" $(FW_C)/dtc.c; \
	! sed -n '/^int dtc_region_checksum_validate_8928/,/^}/p' $(FW_C)/dtc.c | grep -q "assume valid"; \
	echo "-- M7 TesterPresent (only sub 0x00)"; \
	grep -q "tp_sub != 0x00" $(FW_C)/uds.c; \
	echo "-- L10 injector flag (stored on fuel-cut path)"; \
	grep -q "0xFFFFC9A2 = (fault" $(FW_C)/dtc.c; \
	echo "-- SMALL sid12 (subs 2/4 only) + C2 (exactly 3+3) + H5 doc"; \
	grep -q "sub_func != 2 && sub_func != 4" $(FW_C)/dtc.c; \
	grep -q "addr_bytes != 3 || size_bytes != 3" $(FW_C)/uds.c; \
	grep -q "until ISO-TP exists" $(FW_INC)/uds.h; \
	echo "gate: all tripwires present, no buggy idioms"

# Demonstrate pre-fix reproduction: every TEST_BUGGY binary must FAIL.
demo-buggy:
	@mkdir -p $(OUTDIR)/buggy
	@pass=0; fail=0; \
	for t in $(TESTS); do \
		$(CC) $(CFLAGS) -DTEST_BUGGY $$t.c -o $(OUTDIR)/buggy/$$t -lm; \
		if $(OUTDIR)/buggy/$$t >/dev/null 2>&1; then \
			echo "UNEXPECTED PASS (bug not reproduced): $$t"; fail=$$((fail+1)); \
		else \
			echo "reproduced (fails as expected): $$t"; pass=$$((pass+1)); \
		fi; \
	done; \
	echo "demo-buggy: $$pass reproduced, $$fail unexpected-pass"; \
	test $$fail -eq 0

clean:
	rm -rf $(OUTDIR)
