/* exhaust_oxygen_control_19480.c
 *
 * ROM: 60E1D400  |  Address: 0x19480  |  Size: 0x334 bytes (0x19480..0x197B3,
 *                 rts @0x197B4; literal pools @0x194FA..0x19526,
 *                 @0x195F2..0x1961E, @0x196F0..0x1970A and @0x197FE..0x1982C
 *                 are DATA, not code).  Drive helper @0x197B8..0x19894 is
 *                 inlined below as drive_update(); the byte-saturating-add
 *                 helper @0x2478 is inlined as satadd_u8(); the O2 sensor
 *                 read helper @0x5E016 is kept external (o2_sensor_read).
 *                 The float/threshold pool mentioned in earlier notes for
 *                 the WRONG ROM (60E0FC00) does NOT exist here: 0x19530..
 *                 0x19566 and 0x19638..0x19650 in this ROM are branch logic
 *                 (state comparisons), not data.
 *
 * Exhaust O2 sensor/heater control — a u8 state machine driving the four
 * O2 output flags A9D5/A9D6/A9D7/A9D8 from the raw O2 sensor input and a
 * mode byte (expected mode values 0/6/12/18; 0&12 = one sensor channel,
 * 6&18 = the other).  Every call: read the sensor, detect a level change,
 * debounce it with a ROM-table-limited counter, and publish a heater/sensor
 * drive pattern plus a small state word A9DD (0=off, 1=window-ok, 2=map-mode,
 * 4=warmup, 5=level-transition) with a one-shot change flag A9D9.
 *
 * SIGNATURE: void exhaust_oxygen_control_19480(uint8_t mode)
 *   - r4 = mode byte; no meaningful return value (r0 not set on exit path).
 *
 * CONTROL FLOW (see asm addresses):
 *   1. raw = o2_sensor_read() (jsr @0x5E016, r4=0)        0x1949E
 *      RAM_O2_RAW = raw; old_state = RAM_STATE (stack).   0x194A4
 *   2. debounce index idx (r6):  raw >= 50  -> (RAM_O2_RAW+206)&0xFF,
 *                                raw <  50  -> RAM_O2_RAW     0x194B4..0x194BE
 *      (r6 is loaded from @r8 == A9D4 which was just written with raw,
 *       NOT from A9D8; 0x194B4 mov.w +0xCE, 0x194B6 mov.b @r8,r6.)
 *      (idx is snapshot BEFORE any output update; idx==0 means "no count".)
 *   3. if (raw != RAM_PREV_RAW):                           0x194CA
 *        RAM_DEBOUNCE = 0; RAM_LEVEL_CHG = 0;
 *        if (idx != 0) RAM_LEVEL_CHG = 1 when
 *           raw <  50 and mode in {0,12},  or
 *           raw in [50,100] and mode in {6,18}.            0x194D0..0x19542
 *   4. if (CAL_SENS_MODE != RAM_MODE_LATCH):              0x1954A
 *        RAM_CNT = 0;  if (CAL_SENS_MODE == 2) RAM_FLAG_E0 = 1;
 *   5. if (RAM_GLOBAL_RST == 1): reset ALL state, A9DD=0   0x19576
 *   6. if (RAM_LEVEL_CHG == 1):  "level-transition" path   0x195A2
 *        if (RAM_DEBOUNCE == 0) drive(0x0F, mode); else clear outputs;
 *        limit = ROM8(0x6F670 + idx - 1);                  (idx==0 -> 0x6F66F)
 *        RAM_DEBOUNCE = (>= limit) ? 0 : satadd(RAM_DEBOUNCE,1);
 *        RAM_PREV_RAW = raw; RAM_STATE = 5;
 *   7. else dispatch on CAL_SENS_MODE (ROM@0x6F6A6, ==0 stock):
 *        ==1: drive(ROM8(0x6F6A7+CNT), mode); CNT++ (modes 6/18); if CNT>=60
 *             CNT=0; RAM_STATE = 4.                       0x1962C
 *        ==2: if (RAM_FLAG_E0) [same as ==1, plus E0=0 at CNT>=60]
 *             else clear outputs, RAM_STATE = 0.          0x19664
 *        ==0: if any of A6B7/A6B8/A6B9 set -> drive(ROM8(0x6F6A5), mode),
 *             RAM_STATE = 2.                              0x196BE..0x196E2
 *             else plausibility window on the three floats:
 *             f@B5B8 in [0,1200) AND f@AA10 in [-40,120) AND
 *             f@ADBC in [0,125)  -> drive(ROM8(0x6F6A4), mode), STATE=1;
 *             out of window -> clear the matching output pair, STATE=0.
 *                                                          0x1970C..0x1977E
 *   8. epilogue: RAM_MODE_LATCH = CAL_SENS_MODE; if STATE changed and
 *      new STATE != 0 -> RAM_STATE_CHG = 1, RAM_CNT = 0.   0x19780..0x197A2
 *
 * DRIVE HELPER drive_update(mask, mode) (0x197B8):  sets one pair of output
 *   flags from the mask bits when mask < 16:
 *     mode {0,12}:  A9D5 = mask&1, A9D7 = mask&4
 *     mode {6,18}:  A9D6 = mask&2, A9D8 = mask&8
 *   and clears the same pair when mask >= 16.  The A9D5/A9D7 pair belongs to
 *   mode channel 0/12 and the A9D6/A9D8 pair to channel 6/18; masks used in
 *   this ROM: 0x0F (level path -> all four flags set), CAL 0x6F6A4/0x6F6A5
 *   and table 0x6F6A7 are all zero (stock) -> flags cleared.
 *
 * RAM in / out:
 *   0xFFFFA9D4  u8   O2 raw value (written from o2_sensor_read())
 *   0xFFFFA9D5  u8   drive flag A (mode 0/12, mask bit0)      in/out
 *   0xFFFFA9D7  u8   drive flag C (mode 0/12, mask bit2)      in/out
 *   0xFFFFA9D6  u8   drive flag B (mode 6/18, mask bit1)      in/out
 *   0xFFFFA9D8  u8   drive flag D (mode 6/18, mask bit3)      in/out
 *   0xFFFFA9D9  u8   state-change notify flag (written 1)      out
 *   0xFFFFA9DA  u8   input level-change flag                  in/out
 *   0xFFFFA9DB  u8   previous O2 raw value                    in/out
 *   0xFFFFA9DC  u8   debounce counter                         in/out
 *   0xFFFFA9DD  u8   heater/sensor state (0/1/2/4/5)          in/out
 *   0xFFFFA9DE  u8   latch of CAL_SENS_MODE                   in/out
 *   0xFFFFA9DF  u8   state counter (saturating, limit 60)     in/out
 *   0xFFFFA9E0  u8   sensor-mode-changed flag                 in/out
 *   0xFFFFA41C  u8   global reset / inhibit flag (==1)        in
 *   0xFFFFA6B7, 0xFFFFA6B8, 0xFFFFA6B9 u8  map-mode flags (shared with
 *                                         calc_secondary_o2_trim_1321C) in
 *   0xFFFFB5B8  f32  window input 1 (fr5)                     in
 *   0xFFFFAA10  f32  window input 2 (fr6; == RAM_IN_X of the
 *                                         secondary-O2 trim lift)        in
 *   0xFFFFADBC  f32  window input 3 (fr4; == RAM_IN_Y1 of the
 *                                         secondary-O2 trim lift)        in
 *
 * CALIBRATION (ROM, all stock values):
 *   0x6F6A4  u8   drive mask for the window-ok path          (=0)
 *   0x6F6A5  u8   drive mask for the map-mode path           (=0)
 *   0x6F6A6  u8   sensor-mode byte  (0/1/2 dispatch)         (=0)
 *   0x6F6A7  u8[16] per-state drive-mask table               (all 0)
 *   0x6F670  u8[] debounce limit table: idx-1 -> 1,2,3,..,64,68,.. up to
 *            0xFF at idx-1 == -1 (0x6F66F)                    (ramp)
 *   0x6F6E4  f32  0.0    0x6F6E8 f32 1200.0   window x: 0 <= f_a < 1200
 *   0x6F6EC  f32 -40.0   0x6F6F0 f32  120.0   window y: -40 <= f_b < 120
 *   0x6F6F4  f32  0.0    0x6F6F8 f32  125.0   window z: 0 <= f_c < 125
 *   (fcmp/gt operand order: the disasm prints fr[m],fr[n]; the condition
 *   that continues into the drive path is  frn > frm, i.e. lower <= input
 *   and input < upper.  Verified against the 0.0/1200.0/-40.0/120.0/125.0
 *   ROM constants.)
 *
 * SEMANTICS (human):
 *   O2 sensor/heater state machine.  Reads the raw O2 sensor byte every call;
 *   when it changes level it arms a debounce counter (RAM_DEBOUNCE) whose
 *   limit is read from the ROM ramp table indexed by (idx-1) -- a short limit
 *   for low-level inputs, a ~160-count limit for the high-level branch --
 *   and issues the full drive pattern (mask 0x0F) on the first call of the
 *   transition, then keeps the flags cleared while the counter runs, and
 *   re-pulses when the counter resets.  The level-change flag A9DA only arms
 *   for the mode-matched sensor channel and for raw in [0,100].  Outside a
 *   transition, the drive pattern is chosen by the calibration sensor-mode
 *   byte (0 = open loop / plausibility-gated, 1 = warmup counter, 2 = gated
 *   warmup), where the plausibility window is defined by the three f32 ROM
 *   thresholds around the O2 voltage (f@B5B8), a temperature (f@AA10) and a
 *   load/current input (f@ADBC).  A9DD publishes the active state and A9D9
 *   is pulsed when A9DD leaves 0.  A9DC/A9DF are the debounce and warmup
 *   counters (both saturating-add based).
 *
 * VERIFIED SEMANTICS of the three windowed floats (all three are read every
 * call, ANDed into ONE sensor-plausibility gate -- there is no per-window
 * action; the window selects between the "window-ok" drive path and the
 * clear-output path):
 *
 *   Window 1  f@0xFFFFB5B8 (fr5):  in [0,1200)      ROM 0x6F6E4/0x6F6E8
 *     Cell identity: CERTAIN.  0xFFFFB5B8 is the repo-wide f32 engine-speed
 *     cell (labelled RPM_Float_B5B8 in docs/notes/ECU.md; read as engine RPM
 *     by many verified lifts: calc_rotor_sync_idle_gate_B, calc_spark_advance_
 *     0x1237C, air_charge_calc_0x19190, calc_ignition_all_rotors_13C2C,
 *     engine_load_estimator_0x190A6, calc_adaptive_fuel_trim, can_uds_subsystem).
 *     (Note: o2_lambda_subsystem.c labels the same cell "O2 voltage dup", so
 *     the cell is a reused scratch float; in THIS O2-context gate the upper
 *     bound 1200 fits either "1200 rpm" or "1200 mV" scale.)
 *     Physical meaning: INFERRED -- plausibility bound on the engine-speed /
 *     O2-voltage reading; the window-ok drive path only runs while the value
 *     is in the plausible low range (engine speed below ~1200 rpm, i.e. the
 *     low-flow regime where the O2 sensor needs heater/sensor control, or an
 *     in-range narrow-band O2 voltage of < 1.2 V).
 *
 *   Window 2  f@0xFFFFAA10 (fr6):  in [-40,120)     ROM 0x6F6EC/0x6F6F0
 *     Cell identity + physical meaning: CERTAIN.  0xFFFFAA10 is read as a
 *     temperature (coolant / charge / fan / OMP coolant) in several lifts
 *     (ssvControl, calc_fan1_control, omp_waveform_state_machine_18860,
 *     rotor_sync_gate_state_ctrl_2100A, air_charge_calc_0x19190) and the
 *     bounds -40..120 exactly match the classic automotive coolant-temperature
 *     validity range in deg C.  This is the coolant/charge-temperature
 *     plausibility window: the sensor/heater drive is only authorised while
 *     the temperature is plausible (engine neither frozen nor overheated).
 *
 *   Window 3  f@0xFFFFADBC (fr4):  in [0,125)       ROM 0x6F6F4/0x6F6F8
 *     Cell identity: NOT DOCUMENTED anywhere else in this repo (no other lift
 *     or doc references 0xFFFFADBC).  Physical meaning: INFERRED -- a third
 *     plausibility-scaled analog input; the magnitude [0,125) is consistent
 *     with a temperature in deg C or a load/percentage scale.  Only the
 *     bounds + the fact that it participates in the ANDed gate are verified.
 *
 * VERIFIED semantics of the A9D5..A9D8 output flags: they are four per-channel
 * drive flags, not plain heater vs circuit bits.  They are consumed by
 * spark_output_enable_fault_mask_0x10DC8 (verified lift), which folds them into
 * the A5D8 output bitmask as A9D7->bit0, A9D5->bit1, A9D8->bit2, A9D6->bit3 --
 * i.e. they enable/disable four per-channel output bits.  The mode-channel
 * mapping is verified: mode {0,12} (sensor channel 0) drives the A9D5/A9D7
 * pair, mode {6,18} (sensor channel 1) drives the A9D6/A9D8 pair; the two
 * flags per channel are most plausibly two heater-drive sub-outputs per sensor
 * (INFERRED -- the physical wiring beyond the A5D8 bitmask is not recovered).
 *
 * VERIFIED debounce/level-transition behaviour: on an input level change the
 * full pattern (mask 0x0F = all four flags) is issued on the first call, then
 * while the debounce counter runs the flags are cleared, and when the counter
 * reaches its ramp-table limit (ROM 0x6F670, idx-1 -> 1..64 ramp; idx==0 ->
 * 0x6F66F = 255) it resets to 0 and the pattern re-issues on the next armed
 * call -- a re-pulse with a level-dependent hold time (short for low input
 * levels, ~160+ counts for the high-level branch).  In this stock ROM all
 * drive masks (0x6F6A4/0x6F6A5/0x6F6A7) are 0 and CAL_SENS_MODE = 0, so both
 * the window-ok and map-mode paths only CLEAR the mode-matched flag pair; the
 * net observable behaviour is the A9DD state word (0/1/2/5), the one-shot
 * A9D9 notify and the debounce/counter bytes -- all bit-exact vs the ROM.
 */
#include <stdint.h>
#include <math.h>

#define RAM8(addr)       (*(volatile uint8_t *)(uintptr_t)(addr))
#define RAMF32(addr)     (*(volatile float   *)(uintptr_t)(addr))
#define ROM8(addr)       (*(const  uint8_t *)(uintptr_t)(addr))
#define ROMF32(addr)     (*(const  float   *)(uintptr_t)(addr))

/* ---- RAM cells ---------------------------------------------------------- */
#define RAM_O2_RAW       RAM8(0xFFFFA9D4)  /* current O2 raw value          */
#define RAM_DRV_A        RAM8(0xFFFFA9D5)  /* drive flag, mode 0/12 bit0     */
#define RAM_DRV_B        RAM8(0xFFFFA9D6)  /* drive flag, mode 6/18 bit1     */
#define RAM_DRV_C        RAM8(0xFFFFA9D7)  /* drive flag, mode 0/12 bit2     */
#define RAM_DRV_D        RAM8(0xFFFFA9D8)  /* drive flag, mode 6/18 bit3     */
#define RAM_STATE_CHG    RAM8(0xFFFFA9D9)  /* state-change notify flag       */
#define RAM_LEVEL_CHG    RAM8(0xFFFFA9DA)  /* input level-change flag        */
#define RAM_PREV_RAW     RAM8(0xFFFFA9DB)  /* previous O2 raw value          */
#define RAM_DEBOUNCE     RAM8(0xFFFFA9DC)  /* debounce counter               */
#define RAM_STATE        RAM8(0xFFFFA9DD)  /* heater/sensor state 0/1/2/4/5  */
#define RAM_MODE_LATCH   RAM8(0xFFFFA9DE)  /* latch of CAL_SENS_MODE         */
#define RAM_CNT          RAM8(0xFFFFA9DF)  /* state counter (limit 60)       */
#define RAM_FLAG_E0      RAM8(0xFFFFA9E0)  /* sensor-mode-changed flag       */
#define RAM_GLOBAL_RST   RAM8(0xFFFFA41C)  /* global reset/inhibit (==1)     */
#define RAM_MODE_B7      RAM8(0xFFFFA6B7)  /* map-mode flag (trim calc)      */
#define RAM_MODE_B8      RAM8(0xFFFFA6B8)  /* map-mode flag (trim calc)      */
#define RAM_MODE_B9      RAM8(0xFFFFA6B9)  /* map-mode flag (trim calc)      */
#define RAM_F32_A        RAMF32(0xFFFFB5B8) /* window input 1 (fr5)          */
#define RAM_F32_B        RAMF32(0xFFFFAA10) /* window input 2 (fr6)          */
#define RAM_F32_C        RAMF32(0xFFFFADBC) /* window input 3 (fr4)          */

/* ---- calibration (ROM) --------------------------------------------------- */
#define CAL_DRV_MASK_WIN ROM8(0x6F6A4)    /* drive mask, window-ok path (=0)*/
#define CAL_DRV_MASK_MAP ROM8(0x6F6A5)    /* drive mask, map-mode path (=0) */
#define CAL_SENS_MODE    ROM8(0x6F6A6)    /* sensor-mode byte (==0 stock)   */
#define CAL_DEBOUNCE_BASE 0x6F670         /* debounce limit ramp table      */
#define CAL_WIN_A_LO     ROMF32(0x6F6E4)  /*  0.0    (fr5 lower)            */
#define CAL_WIN_A_HI     ROMF32(0x6F6E8)  /* 1200.0  (fr5 upper)            */
#define CAL_WIN_B_LO     ROMF32(0x6F6EC)  /* -40.0   (fr6 lower)            */
#define CAL_WIN_B_HI     ROMF32(0x6F6F0)  /*  120.0  (fr6 upper)            */
#define CAL_WIN_C_LO     ROMF32(0x6F6F4)  /*  0.0    (fr4 lower)            */
#define CAL_WIN_C_HI     ROMF32(0x6F6F8)  /*  125.0  (fr4 upper)            */

/* External ROM helper @0x5E016: reads the raw O2 sensor input byte from the
 * hardware register layer.  Not reconstructed here (has its own state);
 * the test harness supplies it.  Returns the value stored to RAM_O2_RAW. */
extern uint8_t o2_sensor_read(void);

/* Byte-saturating add -- ROM helper @0x2478: r0 = min(r4 + r5, 0xFF). */
static uint8_t satadd_u8(uint8_t a, uint8_t b)
{
    uint32_t s = (uint32_t)a + (uint32_t)b;
    return s >= 0xFFu ? (uint8_t)0xFF : (uint8_t)s;
}

/* Drive output update -- ROM helper @0x197B8 (inlined).  mask >= 16 clears
 * the mode-matched pair; otherwise each mask bit sets one output flag. */
static void drive_update(uint8_t mask, uint8_t mode)
{
    if (mask >= 16) {
        if (mode == 0 || mode == 12) { RAM_DRV_A = 0; RAM_DRV_C = 0; }
        if (mode == 6 || mode == 18) { RAM_DRV_B = 0; RAM_DRV_D = 0; }
    } else {
        if (mode == 0 || mode == 12) {
            RAM_DRV_A = (mask & 1) ? 1 : 0;
            RAM_DRV_C = (mask & 4) ? 1 : 0;
        }
        if (mode == 6 || mode == 18) {
            RAM_DRV_B = (mask & 2) ? 1 : 0;
            RAM_DRV_D = (mask & 8) ? 1 : 0;
        }
    }
}

void exhaust_oxygen_control_19480(uint8_t mode)
{
    uint8_t  old_state;          /* saved at entry (stack +4)              */
    uint8_t  raw;                /* sensor byte                            */
    uint8_t  idx;                /* debounce table index value (r6)        */
    uint8_t  limit;              /* debounce limit for idx                 */
    float    f_a, f_b, f_c;      /* window inputs fr5/fr6/fr4              */

    old_state = RAM_STATE;                       /* 0x1949A                */
    raw = o2_sensor_read();                      /* 0x1949E jsr @0x5E016  */
    RAM_O2_RAW = raw;                            /* 0x194A4                */

    /* ---- step 2: snapshot debounce index (uses the just-written A9D4) --- */
    if (raw >= 50)                               /* 0x194AA cmp/ge #0x32   */
        idx = (uint8_t)(RAM_O2_RAW + 206);       /* 0x194B4/0x194B6 @r8 +0xCE */
    else
        idx = RAM_O2_RAW;                        /* 0x194B2 @r8 (== raw)   */
    mode &= 0xFF;                                /* 0x194CE extu.b r9      */

    /* ---- step 3: input level change ------------------------------------ */
    if (raw != RAM_PREV_RAW) {                   /* 0x194CA cmp/eq         */
        RAM_DEBOUNCE = 0;                        /* 0x194D0                */
        RAM_LEVEL_CHG = 0;                       /* 0x194D2                */
        if (idx != 0) {                          /* 0x194D4 tst            */
            if (raw < 50) {                      /* 0x194E0               */
                if (mode == 0 || mode == 12)     /* 0x194E6, 0x194EE      */
                    RAM_LEVEL_CHG = 1;           /* 0x194F4               */
            } else if (raw <= 100) {             /* 0x1952A cmp/gt #0x64  */
                if (mode == 6 || mode == 18)     /* 0x19530, 0x19538      */
                    RAM_LEVEL_CHG = 1;           /* 0x19540               */
            }
        }
    }

    /* ---- step 4: sensor-mode latch change ------------------------------ */
    if (CAL_SENS_MODE != RAM_MODE_LATCH) {       /* 0x1954E cmp/eq        */
        RAM_CNT = 0;                             /* 0x19554                */
        if (CAL_SENS_MODE == 2)                  /* 0x1955A cmp/eq #0x02  */
            RAM_FLAG_E0 = 1;                     /* 0x19564                */
    }

    /* ---- step 5: global reset ------------------------------------------ */
    f_a = RAM_F32_A;                             /* 0x1956A fr5           */
    f_b = RAM_F32_B;                             /* 0x1956C fr6           */
    f_c = RAM_F32_C;                             /* 0x19580 fr4 (delay)   */
    if (RAM_GLOBAL_RST == 1) {                   /* 0x19578 cmp/eq #0x01  */
        RAM_DRV_A = 0; RAM_DRV_C = 0;            /* 0x19582, 0x19586      */
        RAM_DRV_B = 0; RAM_DRV_D = 0;            /* 0x19584, 0x1958A      */
        RAM_MODE_LATCH = 0;                      /* 0x1958E               */
        RAM_CNT = 0;                             /* 0x19590               */
        RAM_FLAG_E0 = 0;                         /* 0x19596               */
        RAM_DEBOUNCE = 0;                        /* 0x19598               */
        RAM_PREV_RAW = 0;                        /* 0x1959A               */
        RAM_LEVEL_CHG = 0;                       /* 0x1959C               */
        RAM_STATE = 0;                           /* 0x195A0 (delay)       */
        goto epilogue;
    }

    /* ---- step 6: level-transition path (A9DA == 1) --------------------- */
    if (RAM_LEVEL_CHG == 1) {                    /* 0x195A6 cmp/eq #0x01  */
        if (RAM_DEBOUNCE == 0) {                 /* 0x195AE tst           */
            drive_update(0x0F, mode);            /* 0x195B4, r4=0x0F      */
        } else {
            RAM_DRV_A = 0; RAM_DRV_C = 0;        /* 0x195BE..0x195C6      */
            RAM_DRV_B = 0; RAM_DRV_D = 0;
        }
        /* debounce counter vs ROM ramp limit (idx==0 -> ROM@0x6F66F)     */
        limit = ROM8(CAL_DEBOUNCE_BASE + (int)idx - 1);   /* 0x195D2     */
        if (RAM_DEBOUNCE >= limit)               /* 0x195D6 cmp/ge        */
            RAM_DEBOUNCE = 0;                    /* 0x195E6               */
        else
            RAM_DEBOUNCE = satadd_u8(RAM_DEBOUNCE, 1);  /* 0x195DC/0x195E4 */
        RAM_PREV_RAW = raw;                      /* 0x195EC               */
        RAM_STATE = 5;                           /* 0x195F0/0x19754       */
        goto epilogue;
    }

    /* ---- step 7: dispatch on calibration sensor-mode byte -------------- */
    if (CAL_SENS_MODE == 1) {                    /* 0x1962A cmp/eq #0x01  */
        drive_update(ROM8(0x6F6A7 + RAM_CNT), mode);    /* 0x19634       */
        if (mode == 6 || mode == 18)             /* 0x19638/0x19640       */
            RAM_CNT = satadd_u8(RAM_CNT, 1);     /* 0x19648               */
        if (RAM_CNT >= 60)                       /* 0x19658 cmp/ge #0x3C  */
            RAM_CNT = 0;                         /* 0x1965E               */
        RAM_STATE = 4;                           /* 0x196AE (delay)       */
        goto epilogue;
    }

    if (CAL_SENS_MODE == 2) {                    /* 0x19664 cmp/eq #0x02  */
        if (RAM_FLAG_E0 == 1) {                  /* 0x19670 cmp/eq #0x01  */
            drive_update(ROM8(0x6F6A7 + RAM_CNT), mode);    /* 0x1967A   */
            if (mode == 6 || mode == 18)         /* 0x19680/0x19686       */
                RAM_CNT = satadd_u8(RAM_CNT, 1); /* 0x1968E               */
            if (RAM_CNT >= 60) {                 /* 0x1969E cmp/ge #0x3C  */
                RAM_CNT = 0;                     /* 0x196A4               */
                RAM_FLAG_E0 = 0;                 /* 0x196A8               */
            }
            RAM_STATE = 4;                       /* 0x196AE (delay)       */
        } else {
            RAM_DRV_A = 0; RAM_DRV_C = 0;        /* 0x196B0..0x196B8      */
            RAM_DRV_B = 0; RAM_DRV_D = 0;
            RAM_STATE = 0;                       /* 0x196BC (delay)       */
        }
        goto epilogue;
    }

    /* CAL_SENS_MODE == 0 (stock): map-mode flags first, then window.      */
    if (RAM_MODE_B7 == 1 || RAM_MODE_B8 == 1 || RAM_MODE_B9 == 1) { /* 0x196BE */
        drive_update(CAL_DRV_MASK_MAP, mode);    /* 0x196E2, r4=ROM@6F6A5 */
        RAM_STATE = 2;                           /* 0x196EA/0x19754       */
        goto epilogue;
    }

    /* Sensor plausibility window (fcmp/gt operands reversed in the print) */
    if (!(f_a < CAL_WIN_A_LO) && f_a < CAL_WIN_A_HI &&      /* 0 <= f_a < 1200  */
        !(f_b < CAL_WIN_B_LO) && f_b < CAL_WIN_B_HI &&      /* -40 <= f_b < 120 */
        !(f_c < CAL_WIN_C_LO) && f_c < CAL_WIN_C_HI) {      /* 0 <= f_c < 125   */
        drive_update(CAL_DRV_MASK_WIN, mode);    /* 0x19748, r4=ROM@6F6A4 */
        RAM_STATE = 1;                           /* 0x19750/0x19754       */
        goto epilogue;
    }

    /* Out of window: clear the mode-matched output pair, STATE = 0.       */
    if (mode == 0 || mode == 12) {               /* 0x19756..0x19766      */
        RAM_DRV_A = 0;
        RAM_DRV_C = 0;
    }
    if (mode == 6 || mode == 18) {               /* 0x19768..0x1977C      */
        RAM_DRV_B = 0;
        RAM_DRV_D = 0;
    }
    RAM_STATE = 0;                               /* 0x1977E               */

epilogue:                                        /* 0x19780               */
    RAM_MODE_LATCH = CAL_SENS_MODE;              /* 0x19786               */
    if (RAM_STATE != old_state && RAM_STATE != 0) {     /* 0x19790/0x19796 */
        RAM_STATE_CHG = 1;                       /* 0x197A0               */
        RAM_CNT = 0;                             /* 0x197A2               */
    }
}
