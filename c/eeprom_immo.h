/*
 * eeprom_immo.h  —  RX-8 PCM (60E1D400.bin) EEPROM + immobilizer subsystem
 *
 * Verified memory map and shared declarations for the EEPROM management and
 * immobilizer/security functions (Track A lifts in c/). *
 * CPU: SH-2E (SH7055).  EEPROM: ABLIC S-93C56C, 256 bytes, SPI bit-bang via
 * GPIO 0xF74E (CS) / 0xF738 (data).  Data is stored as (value, ~value) pairs
 * in a 256-byte shadow at 0xFFFFC2FE with complement shadow at 0xFFFFC3FE.
 *
 * All addresses confirmed from the disassembly (the detailed EEPROM analysis was
 * moved to private storage, not shipped).
 */
#ifndef EEPROM_IMMO_H
#define EEPROM_IMMO_H

#include <stdint.h>
#include <stdbool.h>

/* ---- Host/target address gate ----
 * On the SH-2E target every macro below dereferences its absolute address.
 * On a host build that would segfault, so when EEPROM_IMMO_HOST is defined
 * (see c/eeprom_immo_host.h) the same macros alias a caller-injected RAM
 * window instead: `eeprom_immo_host_mem->ram` covers ECU 0xFFFFC000..0xFFFFC7FF
 * (all macros except IMMO_LAMP_REG, which aliases ->gpio_f754). The target
 * path is the default and is untouched. */
#ifdef EEPROM_IMMO_HOST
struct eeprom_immo_host_mem {
    uint8_t  ram[0x800];   /* alias of ECU 0xFFFFC000..0xFFFFC7FF */
    uint16_t gpio_f754;    /* alias of GPIO 0xF754 (IMMO lamp) */
};
extern struct eeprom_immo_host_mem *eeprom_immo_host_mem;
#define ECU8(a)  (*(volatile uint8_t  *)(eeprom_immo_host_mem->ram + ((a) - 0xFFFFC000u)))
#define ECU16(a) (*(volatile uint16_t *)(eeprom_immo_host_mem->ram + ((a) - 0xFFFFC000u)))
#define ECU32(a) (*(volatile uint32_t *)(eeprom_immo_host_mem->ram + ((a) - 0xFFFFC000u)))
#define ECUP8(a) ((volatile uint8_t *)(eeprom_immo_host_mem->ram + ((a) - 0xFFFFC000u)))
#else
#define ECU8(a)  (*(volatile uint8_t *)(a))
#define ECU16(a) (*(volatile uint16_t *)(a))
#define ECU32(a) (*(volatile uint32_t *)(a))
#define ECUP8(a) ((volatile uint8_t *)(a))
#endif

/* ---- EEPROM shadow (validated pairs: byte == ~complement) ---- */
#define E2_PRIMARY_BASE      ECUP8(0xFFFFC2FE)  /* 256 bytes data */
#define E2_COMPLEMENT_BASE   ECUP8(0xFFFFC3FE)  /* 256 bytes ~data */

/* Working copies of EEPROM bytes (populated by getDataFromE2RAM) */
#define E2_WORK_INDEX0       ECU8(0xFFFFC2D8) /* EEPROM[0x00] */
#define E2_WORK_INDEX2       ECU8(0xFFFFC2DC) /* EEPROM[0x02] (4 bytes pairing) */
#define E2_WORK_INDEX6       ECU8(0xFFFFC2E0) /* EEPROM[0x06] (4 bytes) */
#define E2_WORK_INDEX10      ECU8(0xFFFFC2E4) /* EEPROM[0x0A] */
#define E2_WORK_INDEX12      ECU8(0xFFFFC2E5) /* EEPROM[0x0C] */
#define E2_WORK_INDEX13      ECU8(0xFFFFC2E6) /* EEPROM[0x0D] */
#define E2_WORK_INDEX15      ECU8(0xFFFFC2E7) /* EEPROM[0x0F] */
#define E2_WORK_INDEX19      ECU8(0xFFFFC2E8) /* EEPROM[0x13] */
#define E2_WORK_INDEX20      ECU8(0xFFFFC2E9) /* EEPROM[0x14] */
#define E2_WORK_INDEX22      ECU16(0xFFFFC2EA) /* EEPROM[0x16..17] */
#define E2_WORK_INDEX24      ECU16(0xFFFFC2EC) /* EEPROM[0x18..19] */
#define E2_WORK_INDEX26      ECU8(0xFFFFC2EE) /* EEPROM[0x1A] */
#define E2_WORK_INDEX27      ECU8(0xFFFFC2EF) /* EEPROM[0x1B] */
#define E2_WORK_INDEX28      ECU8(0xFFFFC2F0) /* EEPROM[0x1C] */
#define E2_WORK_INDEX29      ECU8(0xFFFFC2F1) /* EEPROM[0x1D] */
#define E2_WORK_INDEX30      ECU8(0xFFFFC2F2) /* EEPROM[0x1E] */

/* CAN/communication shadow bytes used as E2 working copies
 * NOTE: loaded via `mov.w <lit>,Rn` (sign-extended 16-bit literal), so the
 * effective addresses are 0xFFFFC243/C242/C244, NOT 0x0000C243.  Verified
 * against the emulated ROM in tests/test_checkImmoStatus_371E4.py. */
#define CAN_SHADOW_C243      ECU8(0xFFFFC243)  /* EEPROM[0x0E] */
#define CAN_SHADOW_C242      ECU8(0xFFFFC242)  /* EEPROM[0x10] */
#define CAN_SHADOW_C244      ECU8(0xFFFFC244)  /* EEPROM[0x12] */

/* ---- Immobilizer state ---- */
#define IMMO_CAN_TX_BUF      ECUP8(0xFFFFC238)   /* 8-byte TX frame */
#define IMMO_STATE_BYTE      ECU8(0xFFFFC28E)  /* state machine byte */
#define IMMO_STATE_CODE      ECU8(0xFFFFC28D)  /* result code */
#define IMMO_CAN_TX_STATE    ECU8(0xFFFFC28F)  /* TX state counter */
#define IMMO_WAIT_STATE      ECU8(0xFFFFC290)  /* key-match slot (1..4/0xFF) */
#define IMMO_SUBSTATE        ECU8(0xFFFFC291)  /* ImmoGetCANData result (1/2/3) */
#define IMMO_GOOD_FLAG       ECU8(0xFFFFC292)  /* good-state flag */
#define IMMO_RESP_BYTE       ECU8(0xFFFFC294)  /* challenge response */
#define IMMO_CAN_TX_STATUS   ECU8(0xFFFFC296)  /* TX status */
#define IMMO_GOODSTATE_CTR   ECU8(0xFFFFC298)  /* good-state countdown */
#define IMMO_CAN_TX_PENDING  ECU8(0xFFFFC299)  /* TX pending flag */
#define IMMO_GOODSTATE_FLAG  ECU8(0xFFFFC29A)  /* good-state flag (360E8) */
#define IMMO_SEED_ACTIVE     ECU8(0xFFFFC29F)  /* seed/2-key active flag */
#define IMMO_TIMER           ECU16(0xFFFFC282) /* general countdown */
#define IMMO_TIMEOUT_CTR     ECU16(0xFFFFC284) /* bad-state timeout */
#define IMMO_TIMER_27C       ECU16(0xFFFFC27C) /* 500-tick timer */
#define IMMO_SEED_TIMER      ECU16(0xFFFFC286) /* seed refresh timer */
#define IMMO_KEYGEN_ADC      ECU32(0xFFFFC278) /* rolling code out */
#define IMMO_KEY_SLOT0       ECU32(0xFFFFC24C) /* expected key slot 0 */
#define IMMO_KEY_SLOT1       ECU32(0xFFFFC250)
#define IMMO_KEY_SLOT2       ECU32(0xFFFFC254)
#define IMMO_KEY_SLOT3       ECU32(0xFFFFC258)
#define IMMO_RX_KEY_VALUE    ECU32(0xFFFFC25C) /* received key value */
#define IMMO_RX_CHALLENGE    ECU32(0xFFFFC274) /* received challenge */
#define IMMO_SEED_OUT        ECU32(0xFFFFC270) /* calculated seed */
#define IMMO_EXPECTED1       ECU32(0xFFFFC260) /* slot1 with 0x01 prefix */
#define IMMO_EXPECTED2       ECU32(0xFFFFC264) /* slot2 with 0x02 prefix */
#define IMMO_EXPECTED3       ECU32(0xFFFFC268) /* slot3 with 0x03 prefix */
#define IMMO_EXPECTED4       ECU32(0xFFFFC26C) /* slot4 with 0x04 prefix */

/* Rolling-code / keygen mixer state (Immo_Keygen_related_ADC) */
#define IMMO_MIX_WORD        ECU16(0xFFFFC288)
#define IMMO_MIX_WORD2       ECU16(0xFFFFC28A)
#define IMMO_MIX_BYTE        ECU8(0xFFFFC293)

/* EEPROM write-queue state (ImmoUpdateRelated) */
#define E2_WQ_PENDING_CODE   ECU8(0xFFFFC2D1)
#define E2_WQ_FLAG_D2        ECU8(0xFFFFC2D2)
#define E2_WQ_INIT_DONE      ECU8(0xFFFFC2D5)
#define E2_WQ_ARMED          ECU8(0xFFFFC2D6)
#define E2_WQ_BUSY           ECU8(0xFFFFC2D7)
/* E2 write-done flag.  Also loaded via `mov.w <lit>,Rn` (sign-extended):
 * effective address 0xFFFFC2F8.  See tests/test_ImmoUpdateRelated_37120.py. */
#define E2_WRITE_COMPLETE    ECU8(0xFFFFC2F8)

/* CAN RX mailbox (mode byte + payload).  Loaded via `mov.w <lit>,Rn` which
 * SIGN-EXTENDS the 16-bit literal: 0xC52x -> 0xFFFFC52x.  Verified in
 * tests/test_ImmoGetCANData_36870.py (emulator experiment: mode placed at
 * 0xFFFFC529 with 0x0000C529 set differently is the one that is consumed). */
#define CAN_RX_MODE          ECU8(0xFFFFC529)
#define CAN_RX_B1            ECU8(0xFFFFC52A)
#define CAN_RX_B2            ECU8(0xFFFFC52B)
#define CAN_RX_B3            ECU8(0xFFFFC52C)
#define CAN_RX_B4            ECU8(0xFFFFC52D)
#define CAN_RX_STATUS        ECU8(0xFFFFC52F)

/* TX request registers (mov.w sign-extended: 0xC241 -> 0xFFFFC241) */
#define CAN_TX_REQ           ECU8(0xFFFFC241)
#define CAN_TX_DATA          ECU8(0xFFFFC240)

/* Immobilizer lamp register (GPIO) */
#ifdef EEPROM_IMMO_HOST
#define IMMO_LAMP_REG        (eeprom_immo_host_mem->gpio_f754)
#else
#define IMMO_LAMP_REG        (*(volatile uint16_t *)0xF754)
#endif

/* ---- Externs: SR helpers + hardware stubs (see test_setSR_getSR.py) ----
 * Under EEPROM_IMMO_HOST (c/eeprom_immo_host.h) these are defined as static
 * inline host doubles in that header, so the externs are suppressed there. */
#ifndef EEPROM_IMMO_HOST
extern uint32_t getSR(uint32_t arg);                 /* 0x3920 */
extern void     setSR(uint32_t val);                 /* 0x3934 */
extern int      e2_retry(void);                      /* 0xC0A8 SPI retry */
extern uint16_t e2_flash_read(uint32_t flashaddr);   /* 0xBFCA SPI word read */
#endif

/* --- 0x2054/0x2064 critical-section pair + 0x4BBC GPIO bit helper --- */
#ifndef EEPROM_IMMO_HOST
void     saveSRMaskParam(uint32_t *store, uint32_t level);   /* 0x2054 */
void     loadStatusRegister_ADDR(uint32_t saved);            /* 0x2064 = ldc r4,sr */
void     reg16SetClear(volatile uint16_t *reg, uint16_t mask, uint8_t set); /* 0x4BBC */
#endif

/* ---- Lifted functions ---- */
void     writeToE2RAMArea(uint16_t index, const uint8_t *src, uint8_t length); /* 0x39124 */
uint8_t  getFromE2_E2ADDR_RAMADDR_LEN(uint16_t e2addr, uint8_t *ramaddr, uint8_t len); /* 0x39170 */
uint8_t  E2IntoRAM(uint16_t e2_addr, uint8_t length);                           /* 0x38F58 */
void     loadDatafromE2intoRAM(void);                                            /* 0x36BD6 */
void     getDataFromE2RAM(void);                                                 /* 0x36C1C */
void     updateE2RAMBasedOnInput(uint8_t code);                                  /* 0x36D0C */
void     setImmoLight(uint8_t on);                                               /* 0x263C8 */
void     ImmoBadStateSet(void);                                                  /* 0x365B8 */
void     ImmoGoodStateSet(void);                                                 /* 0x36544 */
void     ImmoStateReadyToDriveEngineOff(void);                                   /* 0x364D8 */
void     setImmoCANTXData_369B8(uint8_t cmd);                                    /* 0x369B8 */
#define  setImmoCANTXData(cmd)  setImmoCANTXData_369B8((cmd))                    /* 0x369B8 alias */
void     ImmoGetCANData(void);                                                   /* 0x36870 */
uint32_t Immo_Keygen_related_ADC(void);                                          /* 0x36AFC */
void     ImmoUpdateRelated(void);                                                /* 0x37120 */
void     checkImmoStatus(void);                                                  /* 0x371E4 */
void     ImmoWaitForKey_35F92(void);                                             /* 0x35F92 */
void     ImmoStateMachine_360E8(void);                                           /* 0x360E8 */
void     ImmoGetSeed_3664E(void);                                                /* 0x3664E */
uint32_t calculateImmoSeed(uint32_t r4, uint32_t r5, uint32_t r6);                 /* 0x3675C */
void     ImmoKeyExpander_365D6(void);                                            /* 0x365D6 */
uint8_t  eeprom_commit_dispatcher_37000(uint8_t code);                           /* 0x37000 */
uint32_t adc_read(uint32_t r4, uint32_t r5);                                     /* 0x3EDBC */
uint32_t seed_mixer(uint32_t r4, uint32_t r5);                                   /* 0x366B8 */

#endif /* EEPROM_IMMO_H */
