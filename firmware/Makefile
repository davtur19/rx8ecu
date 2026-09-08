# firmware/Makefile — Build the RX-8 ECU open-source firmware
#
# This builds the 1:1 firmware reconstruction for the SH-2E (SH7055).
# It uses the cross-compiler from the parent repo's toolchain.
#
# Usage:
#   make              # Build firmware
#   make clean        # Clean build artifacts
#   make verify       # Verify against stock ROM (if applicable)

# --- Toolchain ---
# Use the SH-ELF cross-compiler from the parent repo
TOOLCHAIN ?= $(abspath ../tools/toolchain/usr/bin)
CC        = $(TOOLCHAIN)/sh-elf-gcc
AS        = $(TOOLCHAIN)/sh-elf-as
LD        = $(TOOLCHAIN)/sh-elf-ld
OBJCOPY   = $(TOOLCHAIN)/sh-elf-objcopy

# If cross-compiler not available, use host GCC for syntax checking
HOST_CC   ?= gcc
CC_TO_USE = $(if $(wildcard $(CC)),$(CC),$(HOST_CC))

# --- Compiler Flags ---
# SH-2E specific flags (if using cross-compiler)
# review-fix w2: added -std=c11 (was: no -std, toolchain default).
SH_FLAGS  = -std=c11 -m2 -mb -Os -ffreestanding -nostdlib -nostartfiles \
            -Iinclude -Wall -Wextra -Werror

# Host build flags (for syntax checking)
# review-fix w2: added -std=c11; -fsyntax-only already implies "no output",
# so callers must NOT also pass -c (removed from the check loop below).
HOST_FLAGS = -std=c11 -Os -ffreestanding -nostdlib -nostartfiles \
             -Iinclude -Wall -Wextra -Werror -fsyntax-only

# Use appropriate flags
CFLAGS    = $(if $(filter $(CC_TO_USE),$(HOST_CC)),$(HOST_FLAGS),$(SH_FLAGS))
# -fsyntax-only (host path) already implies "no output": pass -c only on the
# cross path, where a real object compile is intended.
CHECK_CFLAG = $(if $(filter $(CC_TO_USE),$(HOST_CC)),,-c)

# --- Source Files ---
SRC_DIR   = c
INCLUDE   = include

# Implementation files (priority order)
BOOT_SRC  = $(SRC_DIR)/boot.c
EEPROM_SRC = $(SRC_DIR)/eeprom.c
SERIAL_SRC = $(SRC_DIR)/serial.c
TIMER_SRC  = $(SRC_DIR)/timer.c
MAIN_SRC   = $(SRC_DIR)/main.c
CAN_SRC    = $(SRC_DIR)/can.c
ENGINE_SRC = $(SRC_DIR)/engine.c
DTC_SRC    = $(SRC_DIR)/dtc.c
UDS_SRC    = $(SRC_DIR)/uds.c
RTOS_SRC   = $(SRC_DIR)/rtos.c

# All source files
ALL_SRC   = $(BOOT_SRC) $(EEPROM_SRC) $(SERIAL_SRC) $(TIMER_SRC) $(MAIN_SRC) $(DTC_SRC) $(UDS_SRC) $(RTOS_SRC) $(CAN_SRC) $(ENGINE_SRC)

# Object files
ALL_OBJ   = $(ALL_SRC:.c=.o)

# --- Build Targets ---
.PHONY: all clean check verify

all: check

# Syntax/compile check (host or cross)
# NOTE: when the cross-compiler is missing this falls back to the host CC
# for syntax checking only — firmware.bin/verify below still refuse to run
# without the cross toolchain (they must not pretend to build/verify).
check:
	@if [ ! -f "$(CC)" ]; then echo "NOTE: cross-compiler missing — syntax check with $(HOST_CC)"; fi
	@echo "=== Checking firmware sources ==="
	@for f in $(ALL_SRC); do \
		echo "  CC $$f"; \
		$(CC_TO_USE) $(CFLAGS) $(CHECK_CFLAG) $$f -o /dev/null || exit 1; \
	done
	@echo "=== All sources compile OK ==="

# Cross-compile to binary (only if cross-compiler available)
# review-fix: fail loudly when the cross toolchain is missing instead of
# silently skipping the build (a "successful" no-op binary build).
# review-fix w2: no linker.ld is shipped in firmware/ (verified: no such
# file in the repo), so the old `-T linker.ld` reference could never
# resolve — fail loudly with that diagnosis instead of a cryptic ld error.
firmware.bin: $(ALL_SRC)
	@if [ ! -f "$(CC)" ]; then \
		echo "ERROR: cross-compiler not found at $(CC); refusing to fake firmware.bin"; \
		exit 1; \
	fi
	@if [ ! -f "linker.ld" ]; then \
		echo "ERROR: linker.ld not found in firmware/; no linker script is shipped — refusing to fake firmware.bin"; \
		exit 1; \
	fi
	@echo "=== Building firmware binary ==="
	$(CC) $(SH_FLAGS) $(ALL_SRC) -T linker.ld -o firmware.elf
	$(OBJCOPY) -O binary firmware.elf $@

# Verify against stock ROM (placeholder)
# review-fix: the old verify target only echoed "Firmware build complete" and
# therefore pretended to verify. It now fails loudly without the cross
# toolchain and otherwise performs a real check: every translation unit must
# compile under the cross-compiler with -Wall -Wextra -Werror (SH_FLAGS).
verify: $(ALL_SRC)
	@if [ ! -f "$(CC)" ]; then \
		echo "ERROR: cross-compiler not found at $(CC); refusing to pretend-verify"; \
		exit 1; \
	fi
	@echo "=== Verifying firmware (cross-compile, -Wall -Wextra -Werror) ==="
	@for f in $(ALL_SRC); do \
		echo "  CC $$f"; \
		$(CC) $(SH_FLAGS) -c $$f -o /dev/null || exit 1; \
	done
	@echo "=== Firmware verification passed ==="

# --- Clean ---
clean:
	rm -f $(ALL_SRC:.c=.o) firmware.elf firmware.bin
	rm -f /tmp/firmware_check_*.o
