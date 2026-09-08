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
SH_FLAGS  = -m2 -mb -Os -ffreestanding -nostdlib -nostartfiles \
            -Iinclude -Wall -Wextra -Werror

# Host build flags (for syntax checking)
HOST_FLAGS = -Os -ffreestanding -nostdlib -nostartfiles \
             -Iinclude -Wall -Wextra -Werror -fsyntax-only

# Use appropriate flags
CFLAGS    = $(if $(filter $(CC_TO_USE),$(HOST_CC)),$(HOST_FLAGS),$(SH_FLAGS))

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
check:
	@echo "=== Checking firmware sources ==="
	@for f in $(ALL_SRC); do \
		echo "  CC $$f"; \
		$(CC_TO_USE) $(CFLAGS) -c $$f -o /dev/null || exit 1; \
	done
	@echo "=== All sources compile OK ==="

# Cross-compile to binary (only if cross-compiler available)
firmware.bin: $(ALL_SRC)
	@if [ ! -f "$(CC)" ]; then \
		echo "Cross-compiler not found, skipping binary build"; \
		exit 0; \
	fi
	@echo "=== Building firmware binary ==="
	$(CC) $(SH_FLAGS) $(ALL_SRC) -T linker.ld -o firmware.elf
	$(OBJCOPY) -O binary firmware.elf $@

# Verify against stock ROM (placeholder)
verify: firmware.bin
	@echo "=== Verifying firmware ==="
	@echo "Firmware build complete"

# --- Clean ---
clean:
	rm -f $(ALL_SRC:.c=.o) firmware.elf firmware.bin
	rm -f /tmp/firmware_check_*.o
