/*
 * getFromE2_E2ADDR_RAMADDR_LEN  —  RX-8 PCM @ ROM 0x39170 (60E1D400.bin).
 *
 * Copia `len` byte dallo shadow EEPROM alla RAM con validazione complementare.
 * Ogni locazione EEPROM è memorizzata come coppia (dato, complemento); la
 * funzione verifica dato == ~complemento prima di copiare in RAM.
 *
 * In caso di mismatch:
 *   - chiama il retry SPI @ 0xC0A8; se ritorna != 0 (sign-extended) imposta
 *     il flag d'errore e prosegue senza copiare il byte;
 *   - se il retry riesce, recupera il valore dal backup in FLASH: legge la
 *     word 16-bit all'indirizzo 0x06000000 + ((index>>1) & 0xFF) << 16 e ne
 *     estrae il byte alto (index pari) o basso (index dispari), lo scrive
 *     nello shadow (dato + complemento) e lo copia in RAM.
 *
 * Argomenti (ABI SH-2E): r4 = e2addr, r5 = ramaddr, r6 = len.
 * Ritorna: 0 = tutto valido/recuperato, 1 = almeno un byte non recuperato.
 *
 * Registri nel codice SH-2E originale (verified):
 *   r8  = 0x06000000  (base finestra flash)
 *   r11 = 0xFFFFC3FE  (base complemento E2)
 *   r13 = 0xFFFFC2FE  (base dato E2)
 *   r10 = e2addr, r12 = ramaddr, r9 = len, r14 = e2addr & 0xFFFF
 */
#include "eeprom_immo.h"

#define FLASH_WINDOW_BASE 0x06000000UL

uint8_t getFromE2_E2ADDR_RAMADDR_LEN(uint16_t e2addr, uint8_t *ramaddr, uint8_t len)
{
    uint8_t *primary   = (uint8_t *)E2_PRIMARY_BASE;
    uint8_t *complement = (uint8_t *)E2_COMPLEMENT_BASE;
    uint32_t saved_sr = getSR(0x10);      /* disabilita interrupt */
    uint8_t  error_flag = 0;

    while (len != 0) {
        uint16_t idx = e2addr;            /* extu.w r10,r14 */
        uint8_t  d = primary[idx];        /* mov.b @(r0,r13),r3 */
        uint8_t  c = complement[idx];     /* mov.b @(r0,r11),r2 */

        if (d == (uint8_t)~c) {
            *ramaddr = d;                 /* coppia valida: copia */
        } else {
            int ret = e2_retry();         /* jsr 0xC0A8 */
            if (ret == 0) {
                /* Recupero dal backup flash: word per coppia di byte. */
                uint32_t flash_addr = FLASH_WINDOW_BASE +
                                      (((uint32_t)((idx >> 1) & 0xFF)) << 16);
                uint16_t raw  = e2_flash_read(flash_addr); /* jsr 0xBFCA */
                uint8_t  val  = (idx & 1) ? (uint8_t)(raw & 0xFF)
                                          : (uint8_t)((raw >> 8) & 0xFF);
                primary[idx]   = val;     /* ripristina dato */
                complement[idx] = (uint8_t)~val; /* e complemento */
                *ramaddr = primary[idx];
            } else {
                error_flag = 1;           /* retry fallito */
            }
        }

        len--;                            /* add #0xFF,r9 */
        e2addr++;                         /* add #0x01,r10 */
        ramaddr++;                        /* add #0x01,r12 */
    }

    setSR(saved_sr);
    return error_flag;
}
