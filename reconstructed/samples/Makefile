# ==============================================================================
# Makefile — reconstructed/samples: verified readable C models of RX-8 PCM functions
# ==============================================================================
# Targets:
#   make build    — compile the reconstructed sources + host oracle (host gcc)
#   make test     — run all equivalence harnesses (emulator vs host C)
#   make verify   — alias of `test`
#   make clean    — remove the /tmp build artifacts
#
# The oracle binary and object files are written to /tmp/opencode so that the
# samples directory stays pure source (no build artifacts committed).
# ==============================================================================

CC      ?= cc
PYTHON  ?= python3
BUILD   := /tmp/opencode/rx8-reconstructed-build

SRCS := src/rx8_s32_saturate.c src/rx8_immo_seed_mixer.c src/rx8_index_table.c
OBJS := $(SRCS:src/%.c=$(BUILD)/%.o)

.PHONY: all build test verify verify-gcc346 clean

all: build

build: $(BUILD)/host_oracle $(OBJS)
	@echo "reconstructed samples: build OK"

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/host_oracle: tests/host_oracle.c $(SRCS) | $(BUILD)
	$(CC) -O2 -Wall -Wextra -I include -I src tests/host_oracle.c $(SRCS) -o $@

$(BUILD)/%.o: src/%.c | $(BUILD)
	$(CC) -O2 -Wall -Wextra -Wpedantic -c -I include -I src $< -o $@

test verify: $(BUILD)/host_oracle
	$(PYTHON) tests/harness_add_s32.py
	$(PYTHON) tests/harness_seed_mixer.py
	$(PYTHON) tests/harness_idx_table.py

# Era-ROM toolchain validation: rebuild the reconstructed sources with the
# archived sh-elf gcc 3.4.6 (-m2e -O1 -fomit-frame-pointer), link the blob at
# 0x4000 and run ROM-bytes vs gcc-3.4.6-blob in the same emulator (see
# tests/verify_gcc346.py).  Optional N overrides the per-function vector count.
verify-gcc346:
	$(PYTHON) tests/verify_gcc346.py

clean:
	rm -rf $(BUILD)
