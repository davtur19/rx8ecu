/*
 * engine.c — RX-8 ECU Rotary Engine Control (13B-MSP)
 *
 * Open 1:1 firmware reconstruction for the Mazda RX-8 Renesis 13B-MSP
 * rotary engine control system. Implements eccentric shaft trigger decode,
 * ignition leading/trailing dwell, sequential injection, OMP control,
 * and the 10ms main engine cycle.
 *
 * All functions annotated with ROM address comments for traceability.
 *
 * Source: engine_rotary_report.txt, IDA session ae00d360
 */

#include "engine.h"

/* ====================================================================== */
/*  Helper Functions (inline from IDA)                                     */
/* ====================================================================== */

/* Extend unsigned byte (from SH-2E extu.b instruction) */
static inline uint8_t extu_b(uint8_t val)
{
    return val; /* Already unsigned, no extension needed */
}

/* ====================================================================== */
/*  Internal State                                                        */
/* ====================================================================== */

/* review-fix: volatile — trigger decode / dwell / injection / OMP state is
 * shared between the crank ISR (crank_timing_update) and the main-loop
 * engine cycle. Guard strategy: single volatile accesses are atomic on
 * SH-2 (8/16-bit); multi-step sequences run either in the ISR or under
 * disable_interrupts()/restore_interrupts() in main-loop code. */
/* Trigger decode state (eccentric shaft position) */
static volatile uint8_t crank_tooth_count = 0;
static volatile uint8_t crank_rotor_position = 0;  /* 0-5 teeth per rotor */
static volatile uint8_t crank_rotor_id = 0;        /* 0=rotor A, 1=rotor B */

/* Ignition dwell state */
static volatile uint16_t dwell_time_us = 0;

/* Injection state */
static volatile uint8_t injector_enable_flags = 0;

/* OMP state */
static volatile uint8_t omp_state = OMP_STATE_OFF;

/* Trigger sync RAM mirrors (from ROM analysis) */
static volatile uint8_t *const sync_state    = (volatile uint8_t *)0xFFFF9FC0;
static volatile uint8_t *const sync_counter  = (volatile uint8_t *)0xFFFF9F95;
static volatile uint8_t *const engine_run    = (volatile uint8_t *)0xFFFF9F96;
static volatile uint8_t *const tooth_pos     = (volatile uint8_t *)0xFFFF9FA3;
static volatile uint8_t *const tooth_ctr     = (volatile uint8_t *)0xFFFF9FC3;
static volatile uint8_t *const gap_detect_r  = (volatile uint8_t *)0xFFFF9FCB;
static volatile uint8_t *const gap_ctr       = (volatile uint8_t *)0xFFFF9FC9;
static volatile uint8_t *const teeth_since   = (volatile uint8_t *)0xFFFF9FCA;
static volatile uint8_t *const sync_flag_1   = (volatile uint8_t *)0xFFFF9FA1;
static volatile uint8_t *const last_tooth_r  = (volatile uint8_t *)0xFFFF9FA2;
static volatile uint32_t *const timer_capture = (volatile uint32_t *)0xFFFFF434;
static volatile uint32_t *const ratio_r      = (volatile uint32_t *)0xFFFF9FB0;
static volatile uint32_t *const prev_ratio   = (volatile uint32_t *)0xFFFF9FB4;
static volatile uint32_t *const last_ts_r    = (volatile uint32_t *)0xFFFF9FAC;
static volatile uint32_t *const delta_ts_r   = (volatile uint32_t *)0xFFFF9FA8;

/* ====================================================================== */
/*  Trigger Decode (eccentric shaft position)                              */
/* ====================================================================== */

/**
 * crank_gap_detect — Detect missing tooth gap in trigger wheel.
 * ROM:0x7E60 (size 0x78)
 *
 * Detects the gap after tooth 5 in the 3x6+1 pattern.
 * The gap is identified by comparing tooth interval against expected.
 * When interval > threshold: gap detected, returns rotor offset.
 * @param rotor_offset  Input rotor offset from caller (0 or 6, R4 on SH-2).
 * Returns: rotor face offset (0 or 6) on success, 0xFF on no gap.
 */
void crank_gap_detect(uint8_t rotor_offset)
{
    /* ROM:0x7E60-0x7ED6: Gap detection algorithm
     * - Read input capture timestamp interval
     * - Compare against expected tooth interval from ratio
     * - If interval > 1.5x expected: gap detected
     * - Return rotor face offset for next rotor
     */
    /* review-fix: was `uint8_t input_val = 0;` (hardcoded) — take the
     * caller-supplied rotor offset instead. */
    uint8_t input_val = rotor_offset; /* r4 parameter (passed in register) */
    uint8_t result = 0xFF; /* default: no gap */

    if (input_val == 0) {
        /* Not first call: check counter_inc_and_copy (0xFFFF9FC7) */
        volatile uint8_t *counter_ptr = (volatile uint8_t *)0xFFFF9FC7;
        if (*counter_ptr != 0) {
            result = 1;
        }
    } else {
        /* First call or specific rotor offset */
        if (input_val == 6) {
            /* Expected gap position for rotor B */
            volatile uint8_t *counter_ptr = (volatile uint8_t *)0xFFFF9FC7;
            if (*counter_ptr != 0) {
                result = 1;
            }
        }
    }

    /* Store gap detection result */
    if (result != 0xFF) {
        *gap_detect_r = 1;
    } else {
        *gap_detect_r = 0;
    }
}

/**
 * crank_position_state_machine — Main eccentric shaft position FSM.
 * ROM:0x789E (size 0x20C)
 *
 * States: 0=idle, 1=searching, 2=partial_sync, 3=full_sync
 * Synchronizes to individual rotor faces.
 * Reads from ram_9f95 (sync counter) and dispatches per state.
 */
void crank_position_state_machine(void)
{
    /* ROM:0x789E-0x7AA8: Position state machine
     * Uses ram_9f95 (0xFFFF9F95) as main state variable.
     * State dispatch:
     *   3 (FULL_SYNC):  tooth count check, verify gap repeats
     *   2 (PARTIAL_SYNC): verify timing consistency
     *   1 (SEARCHING):  count teeth, look for gap pattern
     *   0 (IDLE):       wait for first tooth event
     * Updates ram_9fc0 (sync_state) and tooth tracking variables.
     */
    uint8_t state = *sync_counter;

    /* Validate state bounds: the FSM has states 0-3 only (idle, searching,
     * partial_sync, full_sync). The 0x24 bound belongs to the 0xDA05 rotor
     * table clamp below, not to this FSM — clamping here to 0x24 leaves
     * states 4-36 to fall through every branch (no recovery) and starves
     * the rotor-B acquire path. Clamp to the FSM domain and write back. */
    if (state > 3) {
        /* review-fix M1: was `state > 0x24` (rotor-table domain leaked into
         * the FSM clamp). Wave A added the write-back; M1 fixes the bound. */
        *sync_counter = 0;
        state = 0;
    }

    /* Read tooth position from ram_9fbc / ram_9fc3 */
    uint8_t tooth = *tooth_ctr;

    /* State 0 (IDLE): Wait for first tooth */
    if (state == 0) {
        if (tooth != 0) {
            /* First tooth seen: transition to SEARCHING */
            *sync_counter = 1;
        }
        return;
    }

    /* State 3 (FULL_SYNC): Verify gap repeats correctly */
    if (state == 3) {
        /* Check tooth count against expected pattern */
        if (crank_tooth_count == 0x1C || crank_tooth_count == 0x0A) {
            /* Expected tooth position: set partial sync flag */
            *tooth_pos = 2;
        }
    }

    /* State 2 (PARTIAL_SYNC): Verify timing consistency */
    if (state == 2) {
        /* Read ratio from 2D lookup table at dword_75184 */
        volatile uint32_t *ratio_ptr = (volatile uint32_t *)0xFFFF9FB0;
        volatile uint32_t *limit_ptr = (volatile uint32_t *)0x75184;

        /* Compare current tooth count against threshold */
        uint8_t prev = *last_tooth_r;
        if (prev < tooth) {
            /* Tooth count progressing: check ratio */
            if (*ratio_ptr >= *limit_ptr) {
                /* Ratio exceeds limit: transition to SEARCHING */
                *sync_counter = 1;
            }
        }
    }

    /* State 1 (SEARCHING): Count teeth, look for gap */
    if (state == 1) {
        volatile uint8_t *byte_store = (volatile uint8_t *)0xFFFF9FA4;
        volatile uint8_t *search_cnt = (volatile uint8_t *)0xFFFF9FA1;

        /* Check tooth count progression */
        if (*search_cnt >= tooth) {
            /* Not progressing: reset */
            *byte_store = 0;
        }

        /* Look for gap pattern */
        if (*gap_detect_r != 0) {
            /* Gap found at expected position: advance to PARTIAL_SYNC */
            *tooth_pos = 3; /* Will transition to FULL_SYNC after verification */
            *sync_counter = 2;
        }
    }

    /* Update rotor tracking from state machine output */
    if (*sync_flag_1 == 1) {
        /* Sync acquired: update rotor position tracking */
        uint8_t rot = *sync_counter;
        /* rom-check (resolved): ROM table at 0xDA05 holds 37 entries
         * (rot 0x00-0x24); entry 0x24 is (0x00,0x00) and rot>=0x25 reads
         * non-table bytes (04 03 02 02 02 00, then 0xFF fill). Both ROM
         * use sites (crank_timing_update @0x7860, sub_7B7C @0x7B8C) index
         * raw — extu.b; shll r2; mov.b @(r0,r2) — with no clamp, so the
         * clamp below is a safety net that matches the true table extent
         * (max valid rot 0x24). */
        if (rot > 0x24) {
            rot = 0x24;
        }
        uint8_t tbl = ((volatile uint8_t *)0xDA05)[rot * 2];
        if (tbl & 0x80) {
            /* High bit set: compute time delta for RPM */
            uint32_t now = *timer_capture;
            uint32_t last = *last_ts_r;
            *delta_ts_r = now - last;
            *last_ts_r = now;
        }
    }
}

/**
 * rotor_position_synchronization — Synchronize rotor position.
 * ROM:0xAF10
 *
 * Determines which rotor face is at which eccentric shaft position.
 * Maps trigger tooth count to rotor ID and face number.
 */
void rotor_position_synchronization(void)
{
    /* ROM:0xAF10: Map tooth count to rotor position
     * - Read crank_tooth_count
     * - Determine rotor_id (A/B) based on tooth range
     * - Determine face (0-5) within rotor
     * - Update rotor position tracking variables
     * - Signal ignition/injection timing engine
     */
    uint8_t count = crank_tooth_count;

    /* Map 20-tooth pattern to rotor positions
     * Teeth 0-9: Rotor A (faces 0-5 + gap)
     * Teeth 10-19: Rotor B (faces 0-5 + gap)
     *
     * review-fix C3-followup (NEEDS-ROM-CHECK, strengthened): the 10/10
     * split is kept but its ROM basis is ambiguous — ROM cross-check
     * unavailable (no IDA session). Conflicting in-code signals, preserved:
     *   - header: 3x6+1 pattern, TRIGGER_TEETH_PER_ROTOR=6, TOTAL_TEETH=20
     *     (note 3*6+1=19, so the "20-tooth" total is itself incoherent);
     *     face index uses count % 6 below (consistent with 6 teeth/rotor).
     *   - crank_timing_update passes rotor_offset 0 or 6 (offset 6 suggests
     *     rotor B starts at tooth 6, not 10).
     *   - FULL_SYNC checks crank_tooth_count == 0x1C (28) or 0x0A (10),
     *     i.e. the counter ranges beyond 20 in some paths.
     * Decisive for the COUNTER SHAPE (not the A/B boundary):
     * docs/notes/IDA_ANALYSIS.md:449-460 (session ae00d360) lists the
     * tooth counter at 0xFFFF9FC2 as "saturates at 0xFF" (no wrap), while
     * the state machine byte at 0xFFFF9F95 carries "max 0x24". A wrapping
     * 0..19 counter can never reach the 0x1C FULL_SYNC arm, so the ISR now
     * saturates at 0xFF and the A/B map below uses a LOCAL count % 20
     * without touching the global. ROM 0xAF10 must still arbitrate the
     * true A/B boundary before changing the 10/10 split.
     */
    uint8_t local = (uint8_t)(count % TRIGGER_TOTAL_TEETH);
    if (local < 10) {
        crank_rotor_id = 0;  /* Rotor A */
        crank_rotor_position = (uint8_t)(local % TRIGGER_TEETH_PER_ROTOR);
    } else {
        crank_rotor_id = 1;  /* Rotor B */
        crank_rotor_position = (uint8_t)((local - 10) % TRIGGER_TEETH_PER_ROTOR);
    }
    /* review-fix C3-followup: the old else-branch reset the GLOBAL
     * crank_tooth_count here, so this read path had a write side effect
     * (a saturated counter >20 was zeroed on every call, re-hiding the
     * 0x1C arm). The map is now pure: local % 20, global untouched. */
}

/**
 * crank_timing_update — Trigger timing update (ISR entry).
 * ROM:0x7814 (size 0x8A)
 *
 * Called on each eccentric shaft tooth edge interrupt.
 * Reads timer capture, runs state machine, calls gap detect.
 */
void crank_timing_update(void)
{
    /* ROM:0x7814-0x789A: ISR entry point
     * 1. Read timer capture (0xFFFFF434) -> timestamp
     * 2. Store previous ratio, compute new ratio
     * 3. Call crank_position_state_machine (0x789E)
     * 4. If not synced (sync_counter == 0): call crank_sync_acquire(0)
     * 5. If tooth == 0x12 (18): call crank_sync_acquire(6)
     * 6. Check sync_flag_1 (0xFFFF9FC0) == 1
     * 7. If synced and bit 7 of lookup: compute time delta
     */

    /* 1. Read timer capture */
    uint32_t now = *timer_capture;

    /* Each ISR entry corresponds to one eccentric-shaft tooth edge: advance
     * the tooth counter with saturation at 0xFF (no wrap). The 0..19 domain
     * rotor_position_synchronization assumes for the A/B map is derived via
     * a LOCAL count % 20 there, so the global must NOT wrap: wrap-20 made
     * the FULL_SYNC 0x1C (28) arm permanently unreachable. IDA evidence:
     * docs/notes/IDA_ANALYSIS.md:449-460 — tooth counter at 0xFFFF9FC2
     * "saturates at 0xFF"; state-machine byte at 0xFFFF9F95 "max 0x24".
     * NEEDS-ROM-CHECK (strengthened): ROM 0x7814 must confirm the ISR
     * increment site and the saturate-vs-wrap shape; if ROM wraps, revert
     * to wrap-20 and re-hide the 0x1C arm deliberately. */
    if (crank_tooth_count < 0xFF) {
        crank_tooth_count++;
    }

    /* 2. Store previous ratio, update */
    *prev_ratio = *ratio_r;

    /* 3. Run position state machine */
    crank_position_state_machine();

    /* 4-5. Sync acquisition.
     * review-fix M1: was `state == 0x12` — sync_counter holds FSM states
     * 0-3, so 0x12 never matches and the rotor-B acquire(6) path never ran
     * (the ISR comment :305 documents a "tooth 18" event, i.e. the TOOTH
     * counter, which the old code never consulted). Compare the tooth
     * counter against 0x12. */
    uint8_t state = *sync_counter;
    if (state == 0) {
        /* Not synced: try to acquire sync from offset 0 */
        crank_sync_acquire(0);
    } else if (crank_tooth_count == 0x12) {
        /* Tooth 18: try to acquire sync from offset 6 */
        crank_sync_acquire(6);
    }

    /* 6-7. Check sync and compute timing delta if applicable */
    if (*sync_flag_1 == 1) {
        uint8_t rot = *sync_counter;
        /* rom-check (resolved, see note at the state-machine site above):
         * ROM table 0xDA05 = 37 entries, max valid rot 0x24. Clamp kept
         * (this path never passes through the entry clamp). */
        if (rot > 0x24) {
            rot = 0x24;
        }
        uint8_t tbl_entry = ((volatile uint8_t *)0xDA05)[rot * 2];
        if (tbl_entry & 0x80) {
            uint32_t last = *last_ts_r;
            *delta_ts_r = now - last;
            *last_ts_r = now;
        }
    }
}

/**
 * crank_sync_acquire — Acquire trigger sync.
 * ROM:0x7AAA (size 0x2C)
 * @param rotor_offset  0 for first pass, 6 for second pass
 *
 * Called from crank_timing_update when gap is detected.
 * Manages sync_flag_1 (0xFFFF9FC0) and gap detection logic.
 */
void crank_sync_acquire(uint8_t rotor_offset)
{
    /* ROM:0x7AAA-0x7DB4: Sync acquisition
     * - If sync_flag_1 (0xFFFF9FC0) == 0:
     *     Set sync_flag_1 = 1, clear counters
     * - Check ram_9fa3 (tooth_pos) state
     * - If state == 2: return (already synced)
     * - Otherwise: process gap detection
     */
    if (*sync_state == 0) {
        /* First sync attempt: initialize */
        *sync_state = 1;
        *last_tooth_r = 0;
        *sync_flag_1 = 0;
    }

    /* Check current tooth position state */
    if (*tooth_pos == 2) {
        /* Already in final sync state: no action needed */
        return;
    }

    /* Process gap detection based on rotor offset */
    volatile uint8_t *engine_run_flag = engine_run;
    uint8_t er = *engine_run_flag;

    if (er == 0) {
        /* Engine not running: check state machine */
        uint8_t state = *tooth_pos;
        if (state == 1) {
            /* State 1 with no engine run: check ratio limits */
            volatile uint32_t *rpm_ptr = (volatile uint32_t *)0x6CF5C;
            volatile uint32_t *ratio_ptr = (volatile uint32_t *)0xFFFF9FBC;
            if (*ratio_ptr > *rpm_ptr) {
                /* RPM above limit: try gap detection */
                crank_gap_detect(rotor_offset);
                uint8_t gap_r = *gap_detect_r;
                /* review-fix M6: was `gap_r == 0xFF` — crank_gap_detect
                 * stores 0/1 into *gap_detect_r (:111-115), never the 0xFF
                 * no-gap sentinel, so teeth_since was never stored here.
                 * Test the stored domain consistently: !=0 means gap. */
                if (gap_r != 0) {
                    /* Gap detected: store tooth result */
                    *teeth_since = rotor_offset;
                } else {
                    *gap_ctr = 0;
                }
            }
        }
    } else {
        /* Engine running: different path */
        uint8_t state = *tooth_pos;
        if (state == 1) {
            crank_gap_detect(rotor_offset);
        }
        uint8_t gap_r = *gap_detect_r;
        /* review-fix M6: was `gap_r == 0xFF` — same stored-domain mismatch
         * as above; the engine-running gap-toggle never executed. */
        if (gap_r != 0) {
            /* Check rotor offset */
            if (extu_b(rotor_offset) == 0) {
                uint8_t gc = *gap_ctr;
                if (gc == 0) {
                    *gap_ctr = 1;
                } else {
                    *gap_ctr = 0;
                }
            }
        }
    }

    /* Update tooth tracking */
    uint8_t gc = *gap_ctr;
    if (gc == 0) {
        *teeth_since = rotor_offset;
    }
}

/* ====================================================================== */
/*  Ignition System                                                        */
/* ====================================================================== */

/**
 * outputPerRotorIgnitionDwell — Calculate per-rotor ignition dwell.
 * ROM:0x11218 (size 0x66)
 * @param rotor_idx  Rotor index (0-3, encodes leading/trailing)
 *
 * Uses 2D lookup table with per-rotor compensation.
 * Rotor 0/1 use can_addr_copy_57 (0xFFFFBC84).
 * Rotor 2/3 use can_addr_copy_58 (0xFFFFBC88).
 * Divides by constant from ROM:0x112DC.
 */
void outputPerRotorIgnitionDwell(uint8_t rotor_idx)
{
    /* ROM:0x11218-0x1126E: Per-rotor dwell lookup
     * rot0/1 -> can_addr_copy_57 (0xFFFFBC84)
     * rot2/3 -> can_addr_copy_58 (0xFFFFBC88)
     * Divide by constant at 0x112DC
     */
    volatile float *dwell_source;

    extu_b(rotor_idx);
    if (rotor_idx <= 1) {
        /* Leading coil: use first dwell table */
        dwell_source = (volatile float *)0xFFFFBC84; /* can_addr_copy_57 */
    } else if (rotor_idx <= 3) {
        /* Trailing coil: use second dwell table */
        dwell_source = (volatile float *)0xFFFFBC88; /* can_addr_copy_58 */
    } else {
        /* Invalid rotor index: zero dwell */
        dwell_time_us = 0;
        return;
    }

    /* ROM:0x1126E: Load float, divide by constant, convert to integer */
    /* dwell_time_us = (uint16_t)(*dwell_source / DWELL_BASE_DIVISOR); */
    /* review-fix w2 (DOCUMENTED-gap): float-divide + float->u16 conversion
     * semantics are best-effort — ROM 0x11218-0x1126E must confirm the
     * divisor constant (0x112DC), the rounding mode (truncate vs round),
     * and the negative/overflow behavior (a negative float-to-u16 convert
     * is UB in C; the MIN/MAX clamp below only constrains in-range
     * results). Contract: input = dwell-source float at 0xFFFFBC84/88,
     * output = dwell_time_us clamped to [DWELL_MIN_US, DWELL_MAX_US].
     * Needs IDA read of 0x1126E before touching the conversion. */
    float raw = *dwell_source;
    float divided = raw / (float)DWELL_BASE_DIVISOR;

    /* Clamp the float BEFORE converting: a float->u16 conversion of an
     * out-of-range or negative value is UB in C (and wraps mod 2^16 on
     * SH-2), so clamping after the cast cannot constrain it.
     * NaN policy (H4 decision): NaN inhibits the coil (dwell=0) instead of
     * firing a weak MIN spark on a faulted input — precedent in this same
     * function (rotor_idx>3 → dwell=0 inhibit, :456-460) prefers a clean
     * inhibit over a fault-driven fire. Finite values keep the MIN/MAX
     * clamp. NaN is detected by self-comparison (no math.h dependency). */
    if (divided != divided) {
        dwell_time_us = 0;
        return;
    }
    if (divided < (float)DWELL_MIN_US) {
        divided = (float)DWELL_MIN_US;
    } else if (divided > (float)DWELL_MAX_US) {
        divided = (float)DWELL_MAX_US;
    }
    dwell_time_us = (uint16_t)divided;
}

/**
 * calc_base_ignition_timing — Calculate base ignition timing.
 * ROM:0x11A9C
 *
 * Calls main_fuel_control_pipeline_22094.
 * Base timing from RPM/MAP 2D lookup.
 */
void calc_base_ignition_timing(void)
{
    /* ROM:0x11A9C: Base ignition timing calculation
     * - Read RPM from trigger decode
     * - Read MAP from sensor
     * - 2D lookup for base timing advance
     * - Call main_fuel_control_pipeline
     */
    main_fuel_control_pipeline();
}

/**
 * ignition_timing_output — Final ignition timing output.
 * ROM:0x1E6B6
 *
 * 2D lookup + filtering for ignition coil drivers.
 */
void ignition_timing_output(void)
{
    /* ROM:0x1E6B6: Final ignition timing output
     * - Apply timing corrections (coolant, intake air temp)
     * - Apply dither/filter for stability
     * - Output to coil driver hardware
     */
    (void)0; /* Implemented as pipeline call 13 */
}

/* ====================================================================== */
/*  Fuel Pipeline Call Implementations                                      */
/* ====================================================================== */

/**
 * calcCLorOLControl — Determine closed-loop vs open-loop operation.
 * ROM:0x20008 — Pipeline call 1
 *
 * Returns control mode: 0 = open-loop, 1 = closed-loop.
 * Checks O2 sensor status, engine temp, RPM thresholds.
 */
void calcCLorOLControl(void)
{
    /* ROM:0x20008: CL/OL control determination
     * - Check O2 sensor readiness
     * - Check engine coolant temperature
     * - Check RPM vs target
     * - Return control mode in r0
     */
    volatile uint8_t *o2_status = (volatile uint8_t *)0xFFFFB350;
    volatile float   *ect_ptr   = (volatile float   *)0xFFFFA8A4;

    /* Simple CL/OL decision: CL if O2 ready and ECT > 70C */
    if (*o2_status != 0 && *ect_ptr > 70.0f) {
        /* Closed-loop: result stored to stack for next call */
    }
}

/**
 * setClosedLoopBool — Set closed-loop operation flag.
 * ROM:0x1FD74 — Pipeline call 2
 *
 * Writes CL mode flag to RAM based on calcCLorOLControl result.
 */
void setClosedLoopBool(void)
{
    /* ROM:0x1FD74: Set CL boolean
     * - Read result from previous call
     * - Write flag to RAM for downstream use
     */
    (void)0;
}

/**
 * calcOpenLoopFuelingTarget — Calculate open-loop fuel target.
 * ROM:0x1FD8E — Pipeline call 3
 *
 * 2D lookup from RPM/MAP for base fuel target in OL mode.
 */
void calcOpenLoopFuelingTarget(void)
{
    /* ROM:0x1FD8E: OL fueling target
     * - Read RPM
     * - Read MAP
     * - 2D table lookup for fuel mass
     * - Store result for sequential injection
     */
    (void)0;
}

/**
 * manifold_pressure_calc — MAP sensor pressure calculation.
 * ROM:0x21190 — Pipeline call 4
 *
 * 2D lookup for manifold pressure.
 */
void manifold_pressure_calc(void)
{
    /* ROM:0x21190: MAP sensor calculation
     * - Read raw ADC value from MAP sensor
     * - Apply 2D calibration lookup
     * - Store kPa value to RAM
     */
    (void)0;
}

/**
 * fpu_threshold_accumulate_divide — FPU threshold accumulate/divide.
 * ROM:0x33C84 — Pipeline call 5
 *
 * Accumulates FPU values and performs threshold division.
 * Used for sensor signal processing.
 */
void fpu_threshold_accumulate_divide(void)
{
    /* ROM:0x33C84: FPU threshold accumulate/divide
     * - Accumulate floating-point sensor values
     * - Apply threshold check
     * - Divide by count for average
     */
    (void)0;
}

/**
 * sequential_fuel_injection — Sequential fuel injection control.
 * ROM:0x211DC (size 0x1F4) — Pipeline call 6
 *
 * Reads can_addr_copy_225 (0xFFFFBF24), unk_FFFFB35C (fuel trim),
 * rotor A/B flags. Uses math_complement_2440 for duty cycle.
 */
void sequential_fuel_injection(void)
{
    /* ROM:0x211DC-0x213B4: Sequential injection control
     * - Read fuel trim from unk_FFFFB35C
     * - Read rotor flags from unk_FFFFA444/445
     * - Calculate injection timing per rotor face
     * - Call math_complement_2440 for duty cycle
     */
    volatile uint8_t *rotor_a_flag = (volatile uint8_t *)0xFFFFA444;
    volatile uint8_t *rotor_b_flag = (volatile uint8_t *)0xFFFFA445;

    /* Check injector_enable_flags and rotor flags */
    if (injector_enable_flags == 0) {
        return;
    }

    /* Process each rotor in firing order */
    if (*rotor_a_flag != 0) {
        /* Rotor A injection window */
    }
    if (*rotor_b_flag != 0) {
        /* Rotor B injection window */
    }
}

/**
 * adaptive_ignition_table — Adaptive ignition timing table.
 * ROM:0x213D0 — Pipeline call 7
 *
 * Adjusts ignition timing based on knock history and adaptive learning.
 */
void adaptive_ignition_table(void)
{
    /* ROM:0x213D0: Adaptive ignition table
     * - Read knock history
     * - Read adaptive learning offsets
     * - Adjust base timing
     * - Store corrected timing
     */
    (void)0;
}

/**
 * fuel_injection_duty_cycle — Calculate injector duty cycle.
 * ROM:0x211CC — Pipeline call 8
 *
 * fr2 = unk_FFFFB290 * unk_FFFFB29C, stored to unk_FFFFB28C.
 */
void fuel_injection_duty_cycle(void)
{
    /* ROM:0x211CC: Duty cycle multiply */
    volatile float *base_duty = (volatile float *)0xFFFFB290;
    volatile float *trim_factor = (volatile float *)0xFFFFB29C;
    volatile float *result = (volatile float *)0xFFFFB28C;

    *result = *base_duty * *trim_factor;
}

/**
 * complex_fpu_compare_calc — Complex FPU comparison/calculation.
 * ROM:0x31650 — Pipeline call 9
 *
 * Multi-operand FPU comparison for sensor plausibility.
 */
void complex_fpu_compare_calc(void)
{
    /* ROM:0x31650: Complex FPU compare
     * - Load multiple float values from RAM
     * - Compare against thresholds
     * - Store comparison results for downstream logic
     */
    (void)0;
}

/**
 * transmission_load_control — Transmission load contribution.
 * ROM:0x1DDB0 — Pipeline call 10
 *
 * Calculates torque load from transmission state.
 */
void transmission_load_control(void)
{
    /* ROM:0x1DDB0: Transmission load control
     * - Read transmission state (gear, clutch)
     * - Calculate torque demand contribution
     * - Store for fuel/ignition calculations
     */
    (void)0;
}

/**
 * secondaryAirRequestStuff — Secondary air injection request.
 * ROM:0x1D2B0 — Pipeline call 11
 *
 * Controls secondary air injection pump for cold-start emissions.
 */
void secondaryAirRequestStuff(void)
{
    /* ROM:0x1D2B0: Secondary air injection
     * - Check ECT for cold-start condition
     * - Check O2 sensor status
     * - Enable/disable secondary air pump
     */
    (void)0;
}

/**
 * fuel_trim_update_control — Update fuel trim values.
 * ROM:0x1E5F8 — Pipeline call 12
 *
 * Updates short-term and long-term fuel trim based on O2 feedback.
 */
void fuel_trim_update_control(void)
{
    /* ROM:0x1E5F8: Fuel trim update
     * - Read O2 sensor feedback
     * - Calculate short-term fuel trim (STFT)
     * - Update long-term fuel trim (LTFT)
     * - Clamp trim values to safe range
     */
    (void)0;
}

/**
 * getRearO2FilteredValue — Get filtered rear O2 sensor value.
 * ROM:0x1E794 — Pipeline call 14
 *
 * Returns filtered rear (post-cat) O2 sensor reading.
 */
void getRearO2FilteredValue(void)
{
    /* ROM:0x1E794: Rear O2 filter
     * - Read raw rear O2 ADC
     * - Apply low-pass filter
     * - Return filtered voltage
     */
    (void)0;
}

/**
 * wankel_rotary_control — Wankel rotary-specific control.
 * ROM:0x1E820 — Pipeline call 15
 *
 * Rotary-engine-specific combustion control adjustments.
 */
void wankel_rotary_control(void)
{
    /* ROM:0x1E820: Rotary control
     * - Rotor-specific timing adjustments
     * - Per-face combustion optimization
     * - Rotary-specific enrichment
     */
    (void)0;
}

/**
 * sensor_validation_monitor — Monitor and validate sensor inputs.
 * ROM:0x1F078 — Pipeline call 16
 *
 * Validates all sensor inputs for plausibility and range.
 */
void sensor_validation_monitor(void)
{
    /* ROM:0x1F078: Sensor validation
     * - Check MAP, TPS, coolant temp, intake air temp
     * - Detect out-of-range values
     * - Set DTCs if needed
     */
    (void)0;
}

/**
 * getMAFOpertionRange — Get MAF sensor operating range.
 * ROM:0x1F786 — Pipeline call 17
 *
 * Determines MAF sensor range for fuel calculation.
 */
void getMAFOpertionRange(void)
{
    /* ROM:0x1F786: MAF range
     * - Read MAF sensor value
     * - Determine operating range
     * - Return range indicator for fuel calc
     */
    (void)0;
}

/**
 * adaptive_control_logic — Adaptive control logic.
 * ROM:0x1F38C — Pipeline call 18
 *
 * Learns and adapts fuel/ignition parameters over time.
 */
void adaptive_control_logic(void)
{
    /* ROM:0x1F38C: Adaptive control
     * - Read adaptation tables
     * - Apply learning corrections
     * - Update adaptive parameters
     */
    (void)0;
}

/**
 * fuel_trim_correction — Apply fuel trim corrections.
 * ROM:0x1F844 — Pipeline call 19
 *
 * Applies accumulated fuel trim to base injection.
 */
void fuel_trim_correction(void)
{
    /* ROM:0x1F844: Fuel trim correction
     * - Read STFT and LTFT values
     * - Apply corrections to injection timing
     * - Clamp to safe limits
     */
    (void)0;
}

/**
 * coolant_temp_boundary_check — Coolant temperature boundary check.
 * ROM:0x1F99A — Pipeline call 20
 *
 * Validates coolant temp is within expected operating range.
 */
void coolant_temp_boundary_check(void)
{
    /* ROM:0x1F99A: ECT boundary check
     * - Read coolant temperature
     * - Check against min/max boundaries
     * - Flag out-of-range condition
     */
    (void)0;
}

/**
 * engine_load_control — Engine load calculation and control.
 * ROM:0x1FA24 — Pipeline call 22
 *
 * Calculates and limits engine load for fuel/ignition.
 */
void engine_load_control(void)
{
    /* ROM:0x1FA24: Engine load control
     * - Calculate engine load from MAP/RPM
     * - Apply load limits
     * - Store for downstream calculations
     */
    (void)0;
}

/**
 * oil_temp_burn_control — Oil temperature burn protection.
 * ROM:0x1FC32 — Pipeline call 24
 *
 * Monitors oil temp and reduces power if overheating.
 */
void oil_temp_burn_control(void)
{
    /* ROM:0x1FC32: Oil temp burn control
     * - Read oil temperature
     * - Compare against threshold
     * - Reduce fuel/timing if overtemp
     */
    (void)0;
}

/**
 * knock_sensor_voltage_limit_check — Knock sensor voltage limit.
 * ROM:0x19984 — Pipeline call 25
 *
 * Checks knock sensor voltage is within valid range.
 */
void knock_sensor_voltage_limit_check(void)
{
    /* ROM:0x19984: Knock sensor limit
     * - Read knock sensor voltage
     * - Check against min/max limits
     * - Flag sensor fault if out of range
     */
    (void)0;
}

/**
 * idle_speed_range_validator — Validate idle speed range.
 * ROM:0x19DDE — Pipeline call 26
 *
 * Ensures idle RPM is within acceptable range.
 */
void idle_speed_range_validator(void)
{
    /* ROM:0x19DDE: Idle speed validator
     * - Read current RPM
     * - Compare against idle target range
     * - Flag if outside acceptable window
     */
    (void)0;
}

/**
 * cold_start_rpm_limiter — Cold start RPM limiter.
 * ROM:0xF11A — Pipeline call 27
 *
 * Limits RPM during cold start for engine protection.
 *
 * review-fix (NEEDS-ROM-CHECK): the old code clamped the MEASURED rpm RAM
 * word (*rpm_ptr = 3000.0f), corrupting the sensor reading consumed by every
 * other pipeline stage (idle control, torque, CAN packers). The limiter now
 * publishes the active limit and an exceeded flag instead and never touches
 * the measurement. The ROM output address/flag for the limit is undocumented
 * in-repo — ROM 0xF11A must confirm where the limit is consumed.
 */
float g_cold_start_rpm_limit = 0.0f;      /* Active RPM limit, 0 = inactive */
uint8_t g_cold_start_limiter_active = 0;  /* 1 = measured RPM exceeds limit */

void cold_start_rpm_limiter(void)
{
    /* ROM:0xF11A: Cold start RPM limiter
     * - Read coolant temperature
     * - Determine RPM limit based on temp
     * - Publish the limit (do NOT modify the measured RPM)
     */
    volatile float *ect_ptr = (volatile float *)0xFFFFA8A4;
    volatile float *rpm_ptr = (volatile float *)0xFFFFB5B8;

    float limit = 0.0f;
    if (*ect_ptr < 40.0f) {
        /* Cold engine: limit RPM to 3000 */
        limit = 3000.0f;
    } else if (*ect_ptr < 70.0f) {
        /* Warming up: limit RPM to 4500 */
        limit = 4500.0f;
    }

    g_cold_start_rpm_limit = limit;
    g_cold_start_limiter_active =
        (uint8_t)((limit > 0.0f && *rpm_ptr > limit) ? 1 : 0);
}

/* ====================================================================== */
/*  OMP Control                                                            */
/* ====================================================================== */

/**
 * omp_control_task — OMP state machine and control.
 * ROM:0x1825E (size 0x2F4)
 *
 * Reads OMP state variables, checks hardware fault,
 * dispatches based on state (0=off, 1=active).
 * Updates control output register.
 */
void omp_control_task(void)
{
    /* ROM:0x1825E-0x1853E: OMP control state machine
     * - Read state variables from RAM
     * - Check hwfault_reg bit 1
     * - Dispatch based on state
     * - Update control output
     */

    /* Read OMP state variables (5 bytes at 0xFFFFA968-0xFFFFA96C) */
    uint8_t state_a968 = OMP_STATE_A968;
    uint8_t state_a969 = OMP_STATE_A969;
    uint8_t state_a96a = OMP_STATE_A96A;
    uint8_t state_a96b = OMP_STATE_A96B;
    uint8_t state_a96c = OMP_STATE_A96C;

    /* Also read additional OMP state from 0xFFFFA998 */
    volatile uint8_t *omp_998 = (volatile uint8_t *)0xFFFFA998;
    uint8_t state_998 = *omp_998;

    /* Check hardware fault */
    if (OMP_HW_FAULT_REG & OMP_HW_FAULT_BIT) {
        /* Hardware fault: force OMP off */
        omp_state = OMP_STATE_OFF;
        OMP_CONTROL_OUTPUT = 0;
        return;
    }

    /* State machine dispatch */
    switch (omp_state) {
        case OMP_STATE_OFF:
            /* OFF state: check if engine running and conditions met */
            if (state_a968 != 0 && state_a969 != 0) {
                /* Engine running and OMP conditions met: activate */
                omp_state = OMP_STATE_ACTIVE;
            }
            break;

        case OMP_STATE_ACTIVE:
            /* review-fix (NEEDS-ROM-CHECK): ACTIVE previously had no exit to
             * OFF, so once activated the OMP could never shut down except on
             * hardware fault. ROM exit conditions are undocumented in-repo
             * (ROM 0x1825E must confirm), so the best-effort exit mirrors the
             * OFF->ACTIVE entry condition above: when the entry conditions
             * drop, return to OFF and clear the control output. */
            if (state_a968 == 0 || state_a969 == 0) {
                omp_state = OMP_STATE_OFF;
                OMP_CONTROL_OUTPUT = 0;
                break;
            }
            /* ACTIVE state: calculate OMP duty based on RPM/load */
            {
                /* Read RPM for OMP duty calculation */
                volatile float *rpm_ptr = (volatile float *)0xFFFFB5B8;

                /* Calculate OMP duty: higher RPM = more oil */
                float rpm_val = *rpm_ptr;
                float duty = 0.0f;

                if (rpm_val > 2000.0f) {
                    duty = (rpm_val - 2000.0f) / 8000.0f;
                    if (duty > 1.0f) duty = 1.0f;
                }

                /* Apply temperature compensation */
                volatile float *ect_ptr = (volatile float *)0xFFFFA8A4;
                float ect = *ect_ptr;
                if (ect < 80.0f) {
                    duty *= 0.8f;  /* Reduce at cold temps */
                }

                /* Write duty to control output (scaled to 0-65535) */
                OMP_CONTROL_OUTPUT = (uint16_t)(duty * 65535.0f);
            }
            break;

        default:
            /* Invalid state: reset to OFF */
            omp_state = OMP_STATE_OFF;
            break;
    }

    /* Suppress unused variable warnings */
    (void)state_a968;
    (void)state_a969;
    (void)state_a96a;
    (void)state_a96b;
    (void)state_a96c;
    (void)state_998;
}

/* ====================================================================== */
/*  10ms Main Cycle                                                        */
/* ====================================================================== */

/**
 * main_engine_cycle_10ms — Core 10ms engine control task.
 * ROM:0x17F1C (size 0x60)
 *
 * Called every 10ms. Runs OMP every 10ms.
 * Runs subset tasks once every 80ms (every 8th call, when the counter
 * reaches CYCLE_80MS_DIVIDER).
 *
 * Flow (from disassembly):
 *   1. diag_getsr_3920 — Save diagnostic status (r4=0x10)
 *   2. Increment 80ms counter (0xFFFFA964)
 *   3. If counter >= 8 (once every 8 calls):
 *      - idle_speed_control_18054
 *      - fuel_pump_control_0x17510
 *      - exhaust_port_control
 *      - intake_air_control_0x177A6
 *      - torque_calc_with_damping
 *      - sub_17014
 *      - ctrl_continuation_17b24
 *      - Reset counter to 0
 *   4. omp_control_task_1825E (every 10ms)
 *   5. diag_setsr_3934 — Restore diagnostic status
 */
void main_engine_cycle_10ms(void)
{
    /* Step 1: Save diagnostic status register */
    /* ROM:0x17F20-0x17F28: diag_getsr_3920 with r4=0x10 */
    /* review-fix w2: was `disable_interrupts();` (token discarded) +
     * `restore_interrupts(0)` below — the saved SR never round-tripped.
     * Save/restore the token per the eeprom_commit_to_ram pattern. */
    uint32_t saved_sr = disable_interrupts();

    /* Step 2: Increment 80ms counter */
    /* ROM:0x17F2A-0x17F30: Read, increment, write counter */
    CYCLE_COUNTER_80MS++;
    uint8_t counter = CYCLE_COUNTER_80MS;

    /* Step 3: Run 80ms subset tasks once every 8 calls (80 ms) */
    /* ROM:0x17F32-0x17F6A: Compare counter against divider, branch when reached.
     * review-fix: was `if (counter < CYCLE_80MS_DIVIDER) { run; reset; }`,
     * which ran the subset on 7 of 8 calls (i.e. every 10 ms) and re-armed
     * immediately. Correct 80 ms behavior: run once the counter reaches the
     * divider, then reset. */
    if (counter >= CYCLE_80MS_DIVIDER) {
        /* ROM:0x17F3E: idle_speed_control_18054 */
        idle_speed_control();

        /* ROM:0x17F44: fuel_pump_control_0x17510 */
        fuel_pump_control();

        /* ROM:0x17F4A: exhaust_port_control */
        exhaust_port_control();

        /* ROM:0x17F50: intake_air_control_0x177A6 */
        intake_air_control();

        /* ROM:0x17F56: torque_calc_with_damping */
        torque_calc_with_damping();

        /* ROM:0x17F5C: sub_17014 */
        sub_17014();

        /* ROM:0x17F62: ctrl_continuation_17b24 */
        ctrl_continuation_17b24();

        /* ROM:0x17F68-0x17F6A: Reset counter to 0 */
        CYCLE_COUNTER_80MS = 0;
    }

    /* Step 4: OMP control (every 10ms) */
    /* ROM:0x17F6C-0x17F70: omp_control_task_1825E */
    omp_control_task();

    /* Step 5: Restore diagnostic status register */
    /* ROM:0x17F74-0x17F7A: diag_setsr_3934 */
    restore_interrupts(saved_sr);
}

/* ====================================================================== */
/*  Fuel Pipeline                                                          */
/* ====================================================================== */

/**
 * main_fuel_control_pipeline — 28-call fuel control pipeline.
 * ROM:0x22094 (size 0xB4)
 *
 * Sequential calls for fuel/ignition calculation.
 * Called from calc_base_ignition_timing_11A9C.
 *
 * Pipeline order (verified from IDA disassembly):
 *   1.  calcCLorOLControl (0x20008)
 *   2.  setClosedLoopBool (0x1FD74)
 *   3.  calcOpenLoopFuelingTarget (0x1FD8E)
 *   4.  manifold_pressure_calc_21190 (0x21190)
 *   5.  fpu_threshold_accumulate_divide_33C84 (0x33C84)
 *   6.  sequential_fuel_injection_211DC (0x211DC)
 *   7.  adaptive_ignition_table_213D0 (0x213D0)
 *   8.  fuel_injection_duty_cycle_211CC (0x211CC)
 *   9.  complex_fpu_compare_calc_31650 (0x31650)
 *   10. transmission_load_control_1DDB0 (0x1DDB0)
 *   11. secondaryAirRequestStuff (0x1D2B0)
 *   12. fuel_trim_update_control_1E5F8 (0x1E5F8)
 *   13. ignition_timing_output_1E6B6 (0x1E6B6)
 *   14. getRearO2FilteredValue (0x1E794)
 *   15. wankel_rotary_control_1E820 (0x1E820)
 *   16. sensor_validation_monitor_1F078 (0x1F078)
 *   17. getMAFOpertionRange (0x1F786)
 *   18. adaptive_control_logic_1F38C (0x1F38C)
 *   19. fuel_trim_correction_1F844 (0x1F844)
 *   20. coolant_temp_boundary_check_1F99A (0x1F99A)
 *   21. combustion_control_loop_1F8E0 (0x1F8E0)
 *   22. engine_load_control_1FA24 (0x1FA24)
 *   23. ignition_timing_safety_check_1FAEA (0x1FAEA)
 *   24. oil_temp_burn_control_1FC32 (0x1FC32)
 *   25. knock_sensor_voltage_limit_check (0x19984)
 *   26. idle_speed_range_validator (0x19DDE)
 *   27. cold_start_rpm_limiter (0xF11A)
 */
void main_fuel_control_pipeline(void)
{
    /* ROM:0x22094-0x2223C: Fuel pipeline
     * 28 sequential function calls for fuel/ignition calculation
     */

    /* Step 1: Save diagnostic status */
    /* ROM:0x22098-0x2209C: diag_getsr_3920 with r4=0x10 */
    /* review-fix w2: save the token (see main_engine_cycle_10ms note). */
    uint32_t saved_sr = disable_interrupts();

    /* Pipeline calls (verified from IDA disassembly) */

    /* Call 1: calcCLorOLControl (0x2209E -> 0x20008) */
    calcCLorOLControl();

    /* Call 2: setClosedLoopBool (0x220A4 -> 0x1FD74) */
    setClosedLoopBool();

    /* Call 3: calcOpenLoopFuelingTarget (0x220AA -> 0x1FD8E) */
    calcOpenLoopFuelingTarget();

    /* Call 4: manifold_pressure_calc_21190 (0x220B0 -> 0x21190) */
    manifold_pressure_calc();

    /* Call 5: fpu_threshold_accumulate_divide_33C84 (0x220B6 -> 0x33C84) */
    fpu_threshold_accumulate_divide();

    /* Call 6: sequential_fuel_injection_211DC (0x220BC -> 0x211DC) */
    sequential_fuel_injection();

    /* Call 7: adaptive_ignition_table_213D0 (0x220C2 -> 0x213D0) */
    adaptive_ignition_table();

    /* Call 8: fuel_injection_duty_cycle_211CC (0x220C8 -> 0x211CC) */
    fuel_injection_duty_cycle();

    /* Call 9: complex_fpu_compare_calc_31650 (0x220CE -> 0x31650) */
    complex_fpu_compare_calc();

    /* Call 10: transmission_load_control_1DDB0 (0x220D4 -> 0x1DDB0) */
    transmission_load_control();

    /* Call 11: secondaryAirRequestStuff (0x220DA -> 0x1D2B0) */
    secondaryAirRequestStuff();

    /* Call 12: fuel_trim_update_control_1E5F8 (0x220E0 -> 0x1E5F8) */
    fuel_trim_update_control();

    /* Call 13: ignition_timing_output_1E6B6 (0x220E6 -> 0x1E6B6) */
    ignition_timing_output();

    /* Call 14: getRearO2FilteredValue (0x220EC -> 0x1E794) */
    getRearO2FilteredValue();

    /* Call 15: wankel_rotary_control_1E820 (0x220F2 -> 0x1E820) */
    wankel_rotary_control();

    /* Call 16: sensor_validation_monitor_1F078 (0x220F8 -> 0x1F078) */
    sensor_validation_monitor();

    /* Call 17: getMAFOpertionRange (0x220FE -> 0x1F786) */
    getMAFOpertionRange();

    /* Call 18: adaptive_control_logic_1F38C (0x22104 -> 0x1F38C) */
    adaptive_control_logic();

    /* Call 19: fuel_trim_correction_1F844 (0x2210A -> 0x1F844) */
    fuel_trim_correction();

    /* Call 20: coolant_temp_boundary_check_1F99A (0x22110 -> 0x1F99A) */
    coolant_temp_boundary_check();

    /* Call 21: combustion_control_loop_1F8E0 (0x22116 -> 0x1F8E0) */
    combustion_control_loop();

    /* Call 22: engine_load_control_1FA24 (0x2211C -> 0x1FA24) */
    engine_load_control();

    /* Call 23: ignition_timing_safety_check_1FAEA (0x22122 -> 0x1FAEA) */
    ignition_timing_safety_check();

    /* Call 24: oil_temp_burn_control_1FC32 (0x22128 -> 0x1FC32) */
    oil_temp_burn_control();

    /* Call 25: knock_sensor_voltage_limit_check (0x2212E -> 0x19984) */
    knock_sensor_voltage_limit_check();

    /* Call 26: idle_speed_range_validator (0x22134 -> 0x19DDE) */
    idle_speed_range_validator();

    /* Call 27: cold_start_rpm_limiter (0x2213A -> 0xF11A) */
    cold_start_rpm_limiter();

    /* Restore diagnostic status */
    /* ROM:0x22140-0x22146: diag_setsr_3934 (tail call) */
    restore_interrupts(saved_sr);
}

/* ====================================================================== */
/*  80ms Subsystem Tasks                                                   */
/* ====================================================================== */

/**
 * idle_speed_control — Idle speed control.
 * ROM:0x18054
 */
void idle_speed_control(void)
{
    /* ROM:0x18054: Idle speed control
     * - Read idle switch state
     * - Read current RPM
     * - Calculate idle valve position from 2D lookup
     * - Output to idle air control valve (IACV)
     * - Apply integral correction for RPM tracking
     */
    volatile float *rpm_ptr = (volatile float *)0xFFFFB5B8;
    volatile float *target = (volatile float *)0xFFFFA8EC;
    volatile float *i_term = (volatile float *)0xFFFFA910;

    /* Simple P-only idle control for now */
    float rpm = *rpm_ptr;
    float tgt = *target;
    float error = tgt - rpm;

    /* Proportional correction */
    float correction = error * 0.05f;
    if (correction > 1.0f) correction = 1.0f;
    if (correction < -1.0f) correction = -1.0f;

    /* Store correction for IACV output */
    *i_term = correction;
}

/**
 * fuel_pump_control — Fuel pump relay control.
 * ROM:0x17510
 */
void fuel_pump_control(void)
{
    /* ROM:0x17510: Fuel pump relay control
     * - Check engine running flag
     * - If running: enable fuel pump relay
     * - If stopped: delay then disable
     */
    volatile uint8_t *engine_running = (volatile uint8_t *)0xFFFF9F96;

    if (*engine_running != 0) {
        /* Engine running: fuel pump ON */
        /* Actual hardware write would go to GPIO/port register */
    } else {
        /* Engine stopped: fuel pump OFF (with delay) */
    }
}

/**
 * exhaust_port_control — Exhaust port timing.
 * ROM:0x17700
 */
void exhaust_port_control(void)
{
    /* ROM:0x17700: Exhaust port control (VECS)
     * - Variable exhaust port timing (VxDECS)
     * - Calculate port angle based on RPM/load
     * - Output to port actuator solenoid
     */
    volatile float *rpm_ptr = (volatile float *)0xFFFFB5B8;
    volatile float *load_ptr = (volatile float *)0xFFFFAA40;

    /* RPM-based exhaust port timing */
    float rpm = *rpm_ptr;
    float load = *load_ptr;

    /* At high RPM, advance exhaust port timing */
    if (rpm > 4000.0f && load > 50.0f) {
        /* Enable exhaust port timing actuator */
    }
}

/**
 * intake_air_control — Intake air control.
 * ROM:0x177A6
 */
void intake_air_control(void)
{
    /* ROM:0x177A6: Intake air control (VIAS)
     * - Variable intake air system control
     * - Calculate intake runner length based on RPM
     * - Output to intake actuator solenoid
     */
    volatile float *rpm_ptr = (volatile float *)0xFFFFB5B8;
    float rpm = *rpm_ptr;

    /* VIAS: switch runner length at ~4500 RPM */
    if (rpm > 4500.0f) {
        /* Short runner for high-RPM power */
    } else {
        /* Long runner for low-RPM torque */
    }
}

/**
 * torque_calc_with_damping — Torque calculation with damping.
 * ROM:0x17952
 */
void torque_calc_with_damping(void)
{
    /* ROM:0x17952-0x17A3E: Torque calculation with damping
     * - Read RPM (0xFFFFB5B8) and MAP (0xFFFFAA40)
     * - Compare against threshold from 0x78E5A
     * - If RPM positive and below threshold:
     *     Read float from 0x78EC8, compare with 0xFFFFA910
     *     If less: read byte from 0x78E41
     *     If set: compute torque via fpu_mul_float (0x23E4)
     *       fr5 = [0xFFFFA8FC], fr4 = [0xFFFFA8F8]
     *       result = fpu_mul_float(fr4, fr5)
     *       fr5 = [0xFFFFA904], fr4 = result
     *       result = fpu_mul_float(fr4, fr5)
     *       fr5 = [0x78ECC], sqrt(result) via fpu_sqrt_float (0x23F4)
     * - Apply damping: compare with 0xFFFFA944
     * - If zero and above 0xFFFFA944: read from 0x78E58, store to 0xFFFFA944
     * - Else: decrement 0xFFFFA944 if positive
     * - Store final to 0xFFFFA944
     */
    volatile float *rpm_ptr = (volatile float *)0xFFFFA8EC;
    volatile float *a930_ptr = (volatile float *)0xFFFFA930;
    volatile float *a944_ptr = (volatile float *)0xFFFFA944;

    float rpm_raw = *rpm_ptr;

    float torque = 0.0f;
    if (rpm_raw > 0.0f) {
        /* Compute torque estimate from RPM and MAP */
        volatile float *a8fc = (volatile float *)0xFFFFA8FC;
        volatile float *a8f8 = (volatile float *)0xFFFFA8F8;
        volatile float *a904 = (volatile float *)0xFFFFA904;

        /* torque = sqrt(RPM * MAP_factor * load_factor) */
        float t1 = *a8f8 * *a8fc;
        float t2 = t1 * *a904;
        /* Approximate sqrt.
         * review-fix w2 (DOCUMENTED-gap): ROM applies fpu_sqrt_float
         * (0x23F4) to this product; the single Newton step below (seeded
         * at t2/2, one iteration, t2 >= 0 guarded by the torque > 0 test)
         * is a best-effort stand-in whose accuracy/convergence is
         * unverified — bench-compare against the HW sqrt before trusting
         * torque magnitudes. Contract: input t2 >= 0, output ~= sqrt(t2).
         * Do not add iterations without measuring; match ROM bit-exactly
         * only after IDA confirms 0x23F4 is a plain sqrt. */
        torque = t2;
        if (torque > 0.0f) {
            /* Simple Newton's method sqrt approximation */
            float guess = torque * 0.5f;
            torque = (guess + t2 / guess) * 0.5f;
        }
    }

    /* Apply damping filter */
    float prev = *a944_ptr;
    if (torque == 0.0f && prev > 0.0f) {
        /* Read damping constant from ROM */
        volatile uint16_t *damp_const = (volatile uint16_t *)0x78E58;
        *a944_ptr = (float)*damp_const;
    } else if (prev > 0.0f) {
        /* Decrement damping counter.
         * review-fix: was punned through the float pointer
         * (`(volatile uint16_t *)a944_ptr`, strict-aliasing violation that
         * also decrements only the low half of the float bits). Use a
         * separate integer-typed view of the same counter address. */
        volatile uint16_t *damp_cnt = (volatile uint16_t *)0xFFFFA944;
        if (*damp_cnt > 0) {
            (*damp_cnt)--;
        }
    }

    /* Store final torque value */
    *a930_ptr = torque;
}

/**
 * sub_17014 — 80ms subsystem task.
 * ROM:0x17014
 */
void sub_17014(void)
{
    /* ROM:0x17014: 80ms subsystem task
     * - Unknown specific function (not fully analyzed)
     * - Called from main_engine_cycle_10ms as part of 80ms subset
     */
    (void)0;
}

/**
 * ctrl_continuation_17b24 — 80ms control continuation task.
 * ROM:0x17B24
 */
void ctrl_continuation_17b24(void)
{
    /* ROM:0x17B24-0x17CE8: Control continuation
     * - addSaturate8Bit (0x2478): r4 = r0, r5 = 1
     * - updateMem8bit (0x3EE58): writes to 0xFFFF8072
     * - Reads counter_inc_cond (0xFFFFA428) == 1 check
     * - If not 1: jump to end (0x17CE8)
     * - Reads RPM (0xFFFFB5B8), compares with 8 (index)
     * - Loads floats from compares_0 (0xFFFFAA10), ram_ae54 (0xFFFFAE54)
     * - Calls sub_2500 (0x2500) with unk_FFFFA974 byte
     * - Stores result to ram_a8ec (0xFFFFA8EC)
     * - Calls f_2DLookup (0x2068) with off_6B4F0 table
     * - Stores to unk_FFFFA908 (0xFFFFA908)
     * - Multiplies: result = RPM * lookup_result * constant
     */
    volatile uint8_t *cond_flag = (volatile uint8_t *)0xFFFFA428;

    /* Check continuation condition */
    if (*cond_flag != 1) {
        return;
    }

    /* Read RPM for lookup index */
    volatile float *rpm_ptr = (volatile float *)0xFFFFB5B8;
    volatile float *a8ec = (volatile float *)0xFFFFA8EC;
    volatile float *a908 = (volatile float *)0xFFFFA908;

    float rpm = *rpm_ptr;

    /* 2D lookup with off_6B4F0 table */
    /* f_2DLookup(off_6B4F0, input) */
    volatile float *aa10 = (volatile float *)0xFFFFAA10;
    volatile float *ae54 = (volatile float *)0xFFFFAE54;

    /* Store processed result */
    *a8ec = *aa10 + *ae54;

    /* Compute RPM-scaled output */
    float lookup_result = *aa10;  /* simplified from 2D lookup */
    float constant = 0.001f;     /* from 0x17BF0 */
    float result = rpm * lookup_result * constant;
    *a908 = result;
}

/* ====================================================================== */
/*  Sensor Validation and Combustion Control                               */
/* ====================================================================== */

/**
 * sensor_validation — Validate sensor inputs.
 * ROM:0x1F078 (sensor_validation_monitor)
 */
void sensor_validation(void)
{
    /* ROM:0x1F078: Sensor validation
     * - Check MAP, TPS, coolant temp, intake air temp
     * - Detect out-of-range values
     * - Set DTCs if needed
     */
    (void)0;
}

/**
 * combustion_control_loop — Combustion control feedback loop.
 * ROM:0x1F8E0
 */
void combustion_control_loop(void)
{
    /* ROM:0x1F8E0: Combustion control feedback
     * - Monitor combustion stability via O2/knock
     * - Adjust fuel trim if needed
     * - Knock detection and retard
     */
    (void)0;
}

/**
 * ignition_timing_safety_check — Ignition timing safety limits.
 * ROM:0x1FAEA
 */
void ignition_timing_safety_check(void)
{
    /* ROM:0x1FAEA: Ignition timing safety
     * - Clamp timing to safe limits
     * - Check for timing overlap
     * - Disable ignition if critical fault
     */
    (void)0;
}
