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
#                   # real firmware sources, buggy idioms absent. The harnesses
#                   # are pure models (don't link firmware sources), so this
#                   # gate is what catches a firmware revert.
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

# Firmware source locations (tripwire target, not linked).
FW_C := $(abspath ../c)
FW_INC := $(abspath ../include)

.PHONY: all check gate demo-buggy clean

all: $(BINS)

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
