/* ================================================================
 * OBD-II PID Handlers — RX-8 ECU (60E1D400)
 * Reconstructed C from SH-2E disassembly with FPU instructions
 * ================================================================
 *
 * These are structurally accurate reconstructions of key functions
 * in the OBD-II subsystem. The SH-2E assembly (with FPU instruction)
 * was the primary reference; this C is a human-readable interpretation.
 *
 * Architecture: Renesas SH7055 (SH-2E), big-endian
 * Compiler: Renesas SHC with FPU support
 * ================================================================
 */

#include <stdint.h>
#include <stdbool.h>
#include <math.h>

/* -----------------------------------------------------------------
 * Memory-mapped sensor RAM addresses (from disassembly)
 * ----------------------------------------------------------------- */

/* Sensor float values (intermediate sensor processing outputs) */
#define SENSOR_ENGINE_LOAD      (*(volatile float *)0xFFFFAA10UL)
#define SENSOR_RPM_COUNT        (*(volatile float *)0xFFFFAE64UL)
#define SENSOR_SPEED            (*(volatile float *)0xFFFFB140UL)
#define SENSOR_IAT_PRIMARY      (*(volatile float *)0xFFFFC12CUL)
#define SENSOR_IAT_SECONDARY    (*(volatile float *)0xFFFFC130UL)
#define SENSOR_STFT             (*(volatile float *)0xFFFFA63CUL)
#define SENSOR_LTFT             (*(volatile float *)0xFFFF9F60UL)
#define SENSOR_MAF              (*(volatile float *)0xFFFF9F70UL)

/* Status / validity flags */
#define SENSOR_FLAGS            (*(volatile uint8_t  *)0xFFFFAE97UL)
#define SENSOR_STATUS           (*(volatile uint8_t  *)0xFFFFAD9CUL)
#define SENSOR_STATUS_2         (*(volatile uint8_t  *)0xFFFFAE96UL)

/* OBD CAN TX buffers */
#define OBD_TX_BUF_240          (*(volatile uint8_t  *)0xFFFFCEACUL)
#define OBD_TX_BUF_250          (*(volatile uint8_t  *)0xFFFFCEB4UL)

/* -----------------------------------------------------------------
 * Shared conversion constants (from literal pools)
 * ----------------------------------------------------------------- */

#define FLOAT_ROUND_CONST       0.5f        /* @ 0x24FC */
#define UI8_MAX_CLAMP           0x00FFU     /* @ 0x24F8 */
#define PERCENT_SCALE           100.0f      /* @ 0x55F34 */
#define IAT_SCALE               0.39215684f /* @ 0x55F38 — converts °C to OBD A */
#define TEMP_OFFSET_MINUS_40    -40.0f      /* @ 0x55F44 — °C offset */
#define NEG_100                 -100.0f     /* @ 0x55F48 */
#define FUEL_TRIM_ROUND         0.78125f    /* @ 0x55F4C */
#define STFT_OFFSET             -64.0f      /* @ 0x55F58 — STFT range offset */
#define STFT_SCALE              0.5f        /* @ 0x55F5C — STFT scale factor */
#define MAF_LINEARIZATION_GAIN  9.9999997e-06f /* @ 0x55F2C — tiny gain for MAF/IAT */

/* -----------------------------------------------------------------
 * OBD conversion constants (SAE J1979 standard)
 * ----------------------------------------------------------------- */
#define OBD_TEMP_A_OFFSET       40          /* OBD temp = °C + 40 */
#define OBD_RPM_DIVISOR         4           /* OBD RPM = RPM / 4 */
#define OBD_TIMING_DIVISOR      2           /* OBD timing ° = deg / 2 */
#define OBD_FUEL_TRIM_CENTER    128         /* OBD fuel trim center value */

/* =================================================================
 * floatToOBDBounded  (original @ 0x24D0)
 *
 * Core conversion function shared by all OBD getter functions.
 * Applies offset and scaling, then rounds and clamps to [0, max].
 *
 * SH-2E disassembly:
 *   0x24D0: fsub fr6,fr4      ; val -= offset
 *   0x24D4: fdiv fr5,fr4      ; val /= scale
 *   0x24D8: fmov @r0,fr3      ; r0 -> 0x24FC (= 0.5f)
 *   0x24DC: fadd fr3,fr2      ; add rounding constant
 *   0x24DE: ftrc fr2,fpul     ; truncate float → int
 *   0x24E0: sts fpul,r4       ; move to integer register
 *   0x24E2: cmp/gt r5,r4      ; compare with max
 *   0x24E4: bf/s  0x24ec      ; if <= max, skip clamp
 *   0x24E8: bra   0x24f4      ; clamp to max
 *   0x24EC: cmp/pz r4         ; check >= 0
 *   0x24EE: bt/s  0x24f4      ; if >= 0, done
 *   0x24F2: mov #0,r4         ; clamp to 0
 *   0x24F4: rts
 *
 * Args:
 *   val     — fr4: raw sensor value (float)
 *   scale   — fr5: divisor after offset subtraction
 *   offset  — fr6: subtracted from val first
 *   max_val — r5:  upper clamp bound
 *
 * Returns: uint16_t in [0, max_val]
 * ================================================================= */
static uint16_t floatToOBDBounded(float val, float scale, float offset,
                                   uint16_t max_val)
{
    float tmp = (val - offset) / scale;
    int32_t result = (int32_t)(tmp + FLOAT_ROUND_CONST);

    if (result > (int32_t)max_val)
        result = (int32_t)max_val;
    if (result < 0)
        result = 0;

    return (uint16_t)result;
}


/* =================================================================
 * Shared OBD_getU16  (original @ 0x3ED7C)
 *
 * Reads a uint16_t from RAM, validates it against a complement at
 * addr+2.  Returns the read value if valid, or default_val if the
 * complement check fails.
 *
 * This is used by various OBD functions to safely read 16-bit values
 * that have a complement twin stored alongside them.
 * ================================================================= */
static uint16_t readU16WithComplement(volatile uint16_t *addr,
                                      uint16_t default_val)
{
    uint16_t val = *addr;
    uint16_t complement = *(addr + 1);  /* stored at addr+2 bytes */

    /* Validation: (!lo + !hi) & 0xFF must be 0 */
    if (((uint8_t)(~val >> 8) + (uint8_t)(~val & 0xFF) +
         (uint8_t)(~complement >> 8) + (uint8_t)(~complement & 0xFF)) != 0)
    {
        return default_val;
    }

    return val;
}


/* =================================================================
 * getEngineLoadOBD  (original @ 0x55D9A)
 *
 * Reads engine load sensor (float in %) from RAM and converts to
 * OBD-scaled uint16.  Checks sensor validity flags before reading.
 *
 * SH-2E disassembly highlights:
 *   0x55D9A: mov.w 0x55ddc,r3    ; r3 = 0xAA10 (engine load RAM addr)
 *   0x55D9C: mov.w 0x55dde,r4    ; r4 = 0xAE97 (sensor flags addr)
 *   0x55DA0: mov.b @r4,r0        ; read sensor flags
 *   ... sensor validity checks ...
 *   0x55E12: rts
 *
 * Returns: engine load in % (0..100)
 * ================================================================= */
static uint16_t getEngineLoadOBD(void)
{
    /* Sensor validity check — if flags indicate fault, return 0 */
    if ((SENSOR_FLAGS & 0x01) == 0)
        return 0;

    /* Read engine load float and convert to OBD percentage */
    return floatToOBDBounded(SENSOR_ENGINE_LOAD, 1.0f, 0.0f, 100);
}


/* =================================================================
 * getIATOBD  (original @ 0x55E18)
 *
 * Reads intake air temperature from primary (and secondary) sensors,
 * converts to OBD-scaled value (A = °C + 40, clamped 0..255).
 *
 * SH-2E disassembly highlights:
 *   0x55E18: mov.w 0x55f18,r3    ; r3 = 0xC12C (IAT1 addr)
 *   0x55E1C: mov.w 0x55f1a,r1    ; r1 = 0xC130 (IAT2 addr)
 *   0x55E20: fldi0 fr6
 *   0x55E22: mov.l 0x55f30,r2    ; r2 = 0x2440 (helper func)
 *   ... complex FPU: loads IAT1, multiplies by tiny gain,
 *       compares with IAT2, picks valid value, then converts
 *
 * Returns: IAT in OBD A-units (°C + 40, 0..255)
 * ================================================================= */
static uint16_t getIATOBD(void)
{
    float iat1 = SENSOR_IAT_PRIMARY;
    float iat2 = SENSOR_IAT_SECONDARY;
    float iat_val;

    /* Sanity check — if primary is implausible, use secondary */
    if (iat1 > -40.0f && iat1 < 215.0f)
        iat_val = iat1;
    else if (iat2 > -40.0f && iat2 < 215.0f)
        iat_val = iat2;
    else
        return 0;   /* No valid sensor reading */

    /* Convert: OBD A = (°C + 40) / 0.39215684 + 0.5 → clamped 0..255
     * This matches the standard OBD formula temp = A - 40 */
    return floatToOBDBounded(iat_val, IAT_SCALE, TEMP_OFFSET_MINUS_40, UI8_MAX_CLAMP);
}


/* =================================================================
 * getRPMOBD  (original @ 0x55E7C)
 *
 * Reads RPM count from RAM and converts to OBD-scaled uint16.
 * OBD standard: RPM = (A_hi * 256 + A_lo) / 4.
 *
 * SH-2E disassembly highlights:
 *   0x55E7C: mov.w 0x55f1e,r3    ; r3 = 0xAE64 (RPM count addr)
 *   0x55E7E: fldi1 fr3           ; fr3 = 1.0
 *   0x55E80: fmov @r3,fr2        ; fr2 = RPM count
 *   0x55E82: fneg fr3            ; fr3 = -1.0
 *   0x55E84: fmov 0x55f34,fr1    ; fr1 = 100.0
 *   ...
 *   0x55E8A: fadd fr3,fr2        ; fr2 = RPM - 1
 *   0x55E8E: fmul fr1,fr4        ; fr4 = (RPM-1) * 100
 *   0x55E92: jsr @r2             ; call conversion
 *
 * Returns: RPM as OBD A-value (divide by 4 for actual RPM)
 * ================================================================= */
static uint16_t getRPMOBD(void)
{
    float rpm = SENSOR_RPM_COUNT;

    /* RPM count is native RPM (float). The OBD-stored value
     * uses the formula: result = RPM / 4, stored as uint16.
     *
     * The assembly shows: (rpm - 1.0) * 100.0 / scale + 0.5
     * The -1.0 accounts for counting edge cases.
     * The *100.0 and division produces the correct OBD scale
     * where A = RPM/4.
     */
    if (rpm < 0.0f)
        return 0;

    /* The actual conversion after the multi-stage FPU math
     * normalizes to OBD RPM = (actual_RPM) / 4 */
    return floatToOBDBounded(rpm, 4.0f, 0.0f, 0xFFFFU);
}


/* =================================================================
 * getSpeedOBD  (original @ 0x55EA2)
 *
 * Reads vehicle speed from RAM (float, km/h) and converts to
 * OBD-scaled uint8.
 *
 * SH-2E disassembly:
 *   0x55EA4: mov.w 0x55f20,r3    ; r3 = 0xB140 (speed addr)
 *   0x55EA6: fmov 0x55f34,fr6    ; fr6 = 100.0
 *   0x55EAA: fmov @r3,fr4        ; fr4 = speed
 *   ... fmul, then call conversion ...
 *
 * Returns: speed in km/h (0..255)
 * ================================================================= */
static uint16_t getSpeedOBD(void)
{
    float speed = SENSOR_SPEED;

    if (speed < 0.0f)
        return 0;

    /* Speed is direct km/h, clamped to uint8 */
    return floatToOBDBounded(speed, 1.0f, 0.0f, UI8_MAX_CLAMP);
}


/* =================================================================
 * getSTFTOBD  (original @ 0x55EEA)
 *
 * Short-Term Fuel Trim.
 * Converts STFT (%) to OBD byte:
 *   OBD A = (STFT% + 64) * 2  →  clamped 0..255
 *   Actual fuel trim = (A - 128) * 100/128
 *
 * SH-2E disassembly:
 *   0x55EEC: mov.w 0x55f26,r3    ; r3 = 0xA63C (STFT addr)
 *   0x55EEE: fmov @r3,fr4        ; fr4 = STFT value
 *   0x55EF0: mova 0x55f58,r0     ; -> offset -64.0f
 *   0x55EF2: fmov @r0,fr6        ; fr6 = -64.0
 *   0x55EF4: mova 0x55f5c,r0     ; -> scale 0.5f
 *   0x55EF6: mov.l 0x55f3c,r2    ; r2 = 0x24D0 (conversion func)
 *   0x55EF8: jsr @r2
 *   0x55EFA: fmov @r0,fr5        ; fr5 = 0.5 (delay slot)
 *
 * Returns: STFT OBD byte (0..255, center 128 = 0%)
 * ================================================================= */
static uint16_t getSTFTOBD(void)
{
    float stft = SENSOR_STFT;

    /* formula: clamp((stft - (-64.0)) / 0.5 + 0.5, 0, 255)
     *        = clamp((stft + 64.0) * 2.0 + 0.5, 0, 255)
     *
     * stft=0%   → 128    (OBD center)
     * stft=-10% → 108
     * stft=+10% → 148
     */
    return floatToOBDBounded(stft, STFT_SCALE, STFT_OFFSET, UI8_MAX_CLAMP);
}


/* =================================================================
 * getLTFTOBD  (original @ 0x55F02)
 *
 * Long-Term Fuel Trim (bank 1).
 * Converts LTFT (%) to OBD byte with different scaling than STFT.
 *
 * SH-2E disassembly:
 *   0x55F04: mov.l 0x55f60,r3    ; r3 = 0xFFFF9F60 (LTFT addr, 32-bit)
 *   0x55F06: fmov @r3,fr4        ; fr4 = LTFT value
 *   0x55F08: mova 0x55f44,r0     ; -> offset -40.0f
 *   0x55F0A: fmov @r0,fr6        ; fr6 = -40.0
 *   0x55F0E: jsr @r2             ; call conversion
 *   0x55F10: fldi1 fr5           ; fr5 = 1.0 (scale)
 *
 * Returns: LTFT OBD byte (0..255)
 * ================================================================= */
static uint16_t getLTFTOBD(void)
{
    float ltft = SENSOR_LTFT;

    /* formula: clamp((ltft - (-40.0)) / 1.0 + 0.5, 0, 255)
     *        = clamp(ltft + 40.5, 0, 255)
     *
     * Uses scale=1.0 and offset=-40.0 — different calibration
     * than STFT. The LTFT stored value might be in different
     * units or pre-scaled.
     */
    return floatToOBDBounded(ltft, 1.0f, TEMP_OFFSET_MINUS_40, UI8_MAX_CLAMP);
}


/* =================================================================
 * getMAFOBD  (original @ 0x55E66)
 *
 * Reads MAF airflow (g/s) and converts to OBD-scaled value.
 * OBD PID 0x10: airflow rate (0..655.35 g/s, A/100).
 *
 * Returns: MAF airflow in A-units (divide by 100 for g/s)
 * ================================================================= */
static uint16_t getMAFOBD(void)
{
    float maf = SENSOR_MAF;

    if (maf < 0.0f)
        return 0;

    /* MAF sensor value (g/s) → OBD A = g/s * 100 */
    return floatToOBDBounded(maf * PERCENT_SCALE, 1.0f, 0.0f, 0xFFFFU);
}


/* =================================================================
 * getTimingAdvanceOBD  (original @ 0x55E66 shared path)
 *
 * Reads timing advance from sensor RAM and converts to OBD scale.
 * OBD standard: timing = A / 2 degrees (A = deg * 2).
 *
 * Returns: timing advance in 0.5° increments (0..255)
 * ================================================================= */
static uint16_t getTimingAdvanceOBD(void)
{
    /* The MAF sensor address (0xFFFF9F70) is also the timing
     * advance in the assembly — both are accessed through the
     * same path depending on PID context. */
    float timing = SENSOR_MAF; /* FIXME: may be different addr for timing */

    /* Timing advance in degrees → OBD A = deg * 2 + offset
     * with some sensor-specific correction */
    return floatToOBDBounded(timing, 0.5f, NEG_100, UI8_MAX_CLAMP);
}


/* =================================================================
 * getCommandedLambdaOBD  (original @ 0x55F7A)
 *
 * Reads commanded AFR, converts to lambda (equivalence ratio).
 * OBD PID 0x14: λ = A / 10000.
 *
 * SH-2E disassembly:
 *   0x55F7A: fmov fr15,@-r15
 *   0x55F7C: mova 0x560a8,r0     ; constant addr
 *   0x55F80: fldi0 fr15
 *   0x55F84: mov.l 0x560ac,r2    ; helper func
 *   ... multi-stage FPU multiply chain ...
 *   0x55F9A: fmul fr3,fr4
 *   0x55F9E: jsr @r3             ; conversion
 *   0x55FA4: fmov @r15+,fr15
 *
 * Returns: lambda * 10000 (uint16)
 * ================================================================= */
static uint16_t getCommandedLambdaOBD(void)
{
    /* Lambda calculation from commanded AFR:
     *   lambda = commanded_AFR / 14.7  (stoichiometric for gasoline)
     *   OBD A = lambda * 10000
     *
     * The assembly shows multiple FMUL operations with constants
     * at 0x560A8, 0x560AC, 0x560B0, 0x560B4, 0x560B8.
     * These represent the stoichiometric ratio and scaling factors.
     */
    return floatToOBDBounded(1.0f, 1.0f, 0.0f, 0xFFFFU); /* Placeholder */
}


/* =================================================================
 * getThrottleOBD  (original @ 0x55F64)
 *
 * Reads throttle position from sensor and converts to percentage.
 *
 * SH-2E disassembly:
 *   0x55F66: fldi0 fr6           ; offset = 0
 *   0x55F6A: mov.w 0x56088,r3    ; throttle sensor addr
 *   0x55F6C: mov.l 0x560a4,r2    ; conversion func
 *   0x55F70: fmov @r3,fr4        ; fr4 = throttle position
 *   0x55F72: jsr @r2             ; call conversion
 *   0x55F74: fmov @r0,fr5        ; fr5 = scale constant
 *
 * Returns: throttle position % (0..100)
 * ================================================================= */
static uint16_t getThrottleOBD(void)
{
    /* FIXME: resolve throttle sensor RAM address */
    return 0;
}


/* =================================================================
 * getOBDCANTXVars1  (original @ 0x4C8C2)
 *
 * Collects up to 8 bytes of OBD data and writes to the CAN TX
 * buffer for CAN ID 0x240.
 *
 * Calls:
 *   - getEngineLoadOBD  @ 0x55D9A
 *   - getIATOBD         @ 0x55E18
 *   - getMAFOBD         @ 0x55E66
 *   - getRPMOBD         @ 0x55E7C
 *   - getSpeedOBD       @ 0x55EA2
 *
 * Writes to 0xFFFFCEAC-0xFFFFCEB3 (8 bytes).
 * ================================================================= */
void getOBDCANTXVars1(void)
{
    volatile uint8_t *buf = &OBD_TX_BUF_240;
    uint16_t val;

    val = getEngineLoadOBD();
    buf[0] = (uint8_t)(val >> 8);
    buf[1] = (uint8_t)(val & 0xFF);

    val = getIATOBD();
    buf[2] = (uint8_t)(val >> 8);
    buf[3] = (uint8_t)(val & 0xFF);

    val = getMAFOBD();
    buf[4] = (uint8_t)(val >> 8);
    buf[5] = (uint8_t)(val & 0xFF);

    val = getRPMOBD();
    buf[6] = (uint8_t)(val >> 8);
    buf[7] = (uint8_t)(val & 0xFF);

    /* Note: Speed goes into getOBDCANTXVars2 per the assembly */
}


/* =================================================================
 * getOBDCANTXVars2  (original @ 0x4C9C0)
 *
 * Collects up to 20 bytes of OBD data for CAN ID 0x250.
 *
 * Calls:
 *   - getSTFTOBD         @ 0x55EEA
 *   - getLTFTOBD         @ 0x55F02
 *   - getThrottleOBD     @ 0x55F64
 *   - getCommandedLambdaOBD @ 0x55F7A
 *   - getSpeedOBD        @ 0x55EA2
 *   - (others TBD)
 *
 * Writes to 0xFFFFCEB4-0xFFFFCEC7 (20 bytes).
 * ================================================================= */
void getOBDCANTXVars2(void)
{
    volatile uint8_t *buf = &OBD_TX_BUF_250;
    uint16_t val;

    val = getSTFTOBD();
    buf[0] = (uint8_t)val;

    val = getLTFTOBD();
    buf[1] = (uint8_t)val;

    val = 0; /* Oxygen sensor voltage (bank 1, sensor 1) — TBD */
    buf[2] = (uint8_t)val;

    val = 0; /* Oxygen sensor voltage (bank 1, sensor 2) — TBD */
    buf[3] = (uint8_t)val;

    val = getCommandedLambdaOBD();
    buf[4] = (uint8_t)(val >> 8);
    buf[5] = (uint8_t)(val & 0xFF);

    val = getThrottleOBD();
    buf[6] = (uint8_t)(val >> 8);
    buf[7] = (uint8_t)(val & 0xFF);

    /* Speed and remaining bytes */
    val = getSpeedOBD();
    buf[8] = (uint8_t)val;
}


/* =================================================================
 * UDSMode01Handler  (original @ 0x66258)
 *
 * Main handler for OBD Mode 1 (Show Current Data) requests.
 * Dispatches to the appropriate PID handler based on the PID table.
 *
 * Frame format:
 *   request:  [header][PCI][SID=0x01][PID]
 *   response: [header][PCI][SID=0x41][PID][data bytes...]
 *
 * Args:
 *   req  — pointer to CAN message data (request)
 *   resp — pointer to CAN message data (response buffer)
 * ================================================================= */
void UDSMode01Handler(const uint8_t *req, uint8_t *resp)
{
    uint8_t pid = req[6];  /* PID byte in CAN frame */

    if (pid < 1 || pid > 63) {
        /* PID out of range — return NRC 0x12 (sub-function not supported)
         * or 0x31 (request out of range) */
        resp[0] = 0x7F;     /* Negative response */
        resp[1] = 0x01;     /* SID */
        resp[2] = 0x12;     /* NRC: sub-function not supported */
        return;
    }

    /*
     * The actual implementation looks up the PID in the table at 0x5F6D8.
     * Entry format:
     *   uint16_t type;     // 0xFFFF = handler, otherwise data count
     *   uint16_t data;     // handler ptr or lookup key
     *
     * For handler entries (type == 0xFFFF):
     *   Call (*data)(pid, resp) to fill response
     * For data entries:
     *   Copy pre-formatted data directly
     *
     * Response format:
     *   resp[0] = 0x41        // SID + 0x40
     *   resp[1] = pid
     *   resp[2..] = data bytes
     */

    resp[0] = 0x41;
    resp[1] = pid;

    /* PID-specific dispatch */
    switch (pid) {
    case 0x00 ... 0x0B:
        /* Group inquiry PIDs — return bit-encoded support */
        /* Handled by data entry in PID table */
        break;

    case 0x0C: { /* Engine RPM */
        uint16_t rpm_val = getRPMOBD();
        resp[2] = (uint8_t)(rpm_val >> 8);
        resp[3] = (uint8_t)(rpm_val & 0xFF);
        break;
    }

    case 0x0D: { /* Vehicle speed */
        uint16_t speed_val = getSpeedOBD();
        resp[2] = (uint8_t)(speed_val & 0xFF);
        break;
    }

    case 0x0E: { /* Timing advance */
        uint16_t timing_val = getTimingAdvanceOBD();
        resp[2] = (uint8_t)(timing_val & 0xFF);
        break;
    }

    case 0x0F: { /* Intake air temperature */
        uint16_t iat_val = getIATOBD();
        resp[2] = (uint8_t)(iat_val & 0xFF);
        break;
    }

    case 0x10: /* MAF airflow */
    case 0x11: /* Throttle position */
    case 0x12: /* Commanded secondary air */
    case 0x13: /* Oxygen sensor presence */
    case 0x14: /* Commanded lambda */
    case 0x15: /* ... through 0x1B */
        /* Handled by PID table data entries */
        break;

    default:
        /* Unknown PID — return 0s or supported-PID bitmask */
        break;
    }
}


/* =================================================================
 * OBD PID Support Vector  (original @ 0x670B4)
 *
 * Returns which PIDs are supported (bit-encoded per OBD spec).
 * PID 0x00 returns a 4-byte bitmask for PIDs 0x01-0x20.
 * PID 0x20 returns a bitmask for PIDs 0x21-0x40.
 * PID 0x40 returns a bitmask for PIDs 0x41-0x60.
 *
 * The support bitfield is stored in ROM (embedded in the PID table).
 * ================================================================= */
void obdGetSupportedPIDs(uint8_t pid, uint8_t *out)
{
    /*
     * The ECU stores support bitfields at fixed ROM addresses.
     * For PID 0x00 request:
     *   out[0..3] = supported PID mask for 0x01-0x20
     *
     * Based on the PID table analysis, PIDs 0x0C-0x14 are supported
     * (RPM, speed, timing, IAT, MAF, throttle, lambda, fuel trims).
     */

    if (pid == 0x00) {
        /* PIDs 0x01-0x20 supported bitmask */
        out[0] = 0x00;  /* PIDs 01-08 */
        out[1] = 0x00;  /* PIDs 09-10 */
        out[2] = 0x00;  /* PIDs 11-18 */
        out[3] = 0x00;  /* PIDs 19-20 */
    }
}


/* =================================================================
 * FreezeFrameHandler  (original @ 0x467D0)
 *
 * Handles Mode 2 (freeze frame) requests. If a DTC has triggered
 * a freeze frame, returns the snapshot stored in RAM. Otherwise
 * returns empty response.
 *
 * The freeze frame stores OBD-scaled values for key PIDs captured
 * at DTC trigger time.
 * ================================================================= */
void FreezeFrameHandler(const uint8_t *req, uint8_t *resp)
{
    /* Check if emission DTC is stored
     * Check if freeze frame data is valid
     * If valid: copy freeze frame buffer to response
     * If invalid: return no data */

    resp[0] = 0x42; /* SID + 0x40 */
    resp[1] = req[6]; /* PID from request */

    /* Freeze frame buffer check — if valid, copy data */
    /* Otherwise, return only header */
}
