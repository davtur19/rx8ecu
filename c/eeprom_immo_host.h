/*
 * eeprom_immo_host.h  —  host-test double for the EEPROM/immobilizer subsystem.
 *
 * Including this header (instead of eeprom_immo.h directly) builds a host TU
 * against an injected RAM window instead of absolute ECU addresses:
 *   - defines EEPROM_IMMO_HOST, so every address macro in eeprom_immo.h
 *     aliases `eeprom_immo_host_mem->ram` (ECU 0xFFFFC000..0xFFFFC7FF) or
 *     `->gpio_f754` (GPIO 0xF754) — no absolute dereference, no segfault;
 *   - provides host DEFINITIONS for the symbols eeprom_immo.h only declares:
 *     getSR/setSR (SR read/write), e2_retry/e2_flash_read (SPI EEPROM),
 *     saveSRMaskParam/loadStatusRegister_ADDR (0x2054/0x2064 critical-section
 *     pair), reg16SetClear (0x4BBC GPIO bit helper).
 *
 * Everything here has internal linkage (static) so the header can be included
 * by any number of host test TUs without multiple-definition errors. The
 * target path (eeprom_immo.h without EEPROM_IMMO_HOST) is untouched.
 */
#ifndef EEPROM_IMMO_HOST_H
#define EEPROM_IMMO_HOST_H

#define EEPROM_IMMO_HOST 1
#include "eeprom_immo.h"
#include <stddef.h>   /* NULL */

/* ---- injected RAM window (one per including TU) ----
 * eeprom_immo.h declares `eeprom_immo_host_mem` extern (used by the ECU8/16/32
 * macros); it is rebound here to per-TU static storage via a macro so this
 * header stays multi-include/link safe (the extern itself is never emitted). */
static struct eeprom_immo_host_mem eeprom_immo_host_storage;
#define eeprom_immo_host_mem (&eeprom_immo_host_storage)

/* ---- SR stubs: model the interrupt mask as a plain host variable ---- */
static uint32_t eeprom_immo_host_sr;

static inline uint32_t getSR(uint32_t arg)
{
    (void)arg;
    return eeprom_immo_host_sr;
}

static inline void setSR(uint32_t val)
{
    eeprom_immo_host_sr = val;
}

static inline void saveSRMaskParam(uint32_t *store, uint32_t level)
{
    if (store != NULL)
        *store = eeprom_immo_host_sr;
    eeprom_immo_host_sr = level;
}

static inline void loadStatusRegister_ADDR(uint32_t saved)
{
    eeprom_immo_host_sr = saved;
}

/* ---- GPIO bit helper stub (0x4BBC): set/clear bits in a host word ---- */
static inline void reg16SetClear(volatile uint16_t *reg, uint16_t mask,
                                 uint8_t set)
{
    if (reg == NULL)
        return;
    if (set)
        *reg = (uint16_t)(*reg | mask);
    else
        *reg = (uint16_t)(*reg & (uint16_t)~mask);
}

/* ---- SPI EEPROM stubs: a 256-byte host EEPROM image ----
 * e2_flash_read returns the BE word at the image offset selected by the low
 * byte of flashaddr; e2_retry reports success. Host harnesses prefill
 * eeprom_immo_host_spi[] to script EEPROM contents. */
static uint8_t eeprom_immo_host_spi[256];

static inline int e2_retry(void)
{
    return 0;
}

static inline uint16_t e2_flash_read(uint32_t flashaddr)
{
    uint32_t off = flashaddr & 0xFFu;
    uint32_t hi = eeprom_immo_host_spi[off];
    uint32_t lo = eeprom_immo_host_spi[(off + 1u) & 0xFFu];
    return (uint16_t)((hi << 8) | lo);
}

#endif /* EEPROM_IMMO_HOST_H */
