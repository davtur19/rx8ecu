/**
 * o2_lambda_subsystem.c
 * 
 * Reconstructed C code for the RX-8 ECU O2 / Lambda sensor processing
 * and closed-loop fuel control subsystem.
 *
 * Target: SH-2E (Renesas SH7055)
 * ROM: 60E1D400
 *
 * This is a best-effort reconstruction based on disassembly analysis.
 * Calibration constants and RAM addresses are extracted from the binary.
 */

#include <stdint.h>

// ============================================================
// RAM Map (from disassembly analysis)
// ============================================================
#define RAM_O2_READY_COUNTER    (*(volatile uint8_t  *)0xA768)
#define RAM_FRONT_O2_VOLTAGE    (*(volatile float    *)0xAA10)
#define RAM_STFT_BANK_A         (*(volatile float    *)0xA760)
#define RAM_STFT_BANK_B         (*(volatile float    *)0xA764)
#define RAM_LTFT_OUTPUT         (*(volatile float    *)0xA718)
#define RAM_FRONT_O2_TRIM_IDX   (*(volatile float    *)0xFFFFA77C)
#define RAM_REAR_O2_TRIM_IDX    (*(volatile float    *)0xFFFFA780)
#define RAM_LTFT_MEM            (*(volatile float    *)0xFFFFA720)
#define RAM_LTFT_WORKING        (*(volatile float    *)0xFFFFA728)
#define RAM_LTFT_ADAPT_FLAG     (*(volatile uint8_t  *)0xFFFFA730)
#define RAM_FRONT_O2_LOOKUP_IDX (*(volatile uint8_t  *)0xFFFFA784)
#define RAM_REAR_O2_LOOKUP_IDX  (*(volatile uint8_t  *)0xFFFFA785)
#define RAM_O2_VOLTAGE_DUP      (*(volatile float    *)0xB5B8)
#define RAM_REF_VOLTAGE         (*(volatile float    *)0xB5C4)
#define RAM_O2_STATUS_A         (*(volatile uint8_t  *)0xB5A4)
#define RAM_O2_STATUS_B         (*(volatile uint8_t  *)0xB5AC)
#define RAM_O2_MODE_FLAG        (*(volatile uint8_t  *)0xB5AA)
#define RAM_CLOSED_LOOP_ACTIVE  (*(volatile uint8_t  *)0xAADA)
#define RAM_ENGINE_RPM          (*(volatile uint16_t *)0xA424)
#define RAM_COOLANT_TEMP        (*(volatile float    *)0xC12C)
#define RAM_ENGINE_SPEED_SIG    (*(volatile float    *)0xADC8)    // for timer
#define RAM_INTEGRATION_TIMER   (*(volatile uint16_t *)0xFFFFA772)
#define RAM_REAR_O2_ADC         (*(volatile uint16_t *)0xFFFF9EF2)
#define RAM_REAR_O2_VOLTAGE     (*(volatile float    *)0xFFFFA3E4)
#define RAM_REAR_O2_FILTERED    (*(volatile float    *)0xFFFFB0F0)
#define RAM_REAR_O2_FLAG        (*(volatile uint8_t  *)0xB0EC)
#define RAM_REAR_O2_REF         (*(volatile float    *)0xB0E8)
#define RAM_O2_LOOKUP_SIZE      (*(volatile uint8_t  *)0x0006A8B9)
#define RAM_O2_CTRL_STATE       (*(volatile uint8_t  *)0xFFFFA9DD)
#define RAM_SEC_O2_FLAG_A       (*(volatile uint8_t  *)0xA6B7)
#define RAM_SEC_O2_FLAG_B       (*(volatile uint8_t  *)0xA6B8)
#define RAM_SEC_O2_FLAG_C       (*(volatile uint8_t  *)0xA6B9)

// ============================================================
// Calibration Constants (from ROM literal pools)
// ============================================================
#define CAL_5V_REFERENCE        (*(volatile float    *)0x00072D70)  // 5.0
#define CAL_60V_RANGE           (*(volatile float    *)0x00072D74)  // 60.0
#define CAL_ADAPT_TEMP_LO       (*(volatile float    *)0x00072C60)  // 1500.0
#define CAL_ADAPT_TEMP_HI       (*(volatile float    *)0x00072C64)  // 0.009765625
#define CAL_TRIM_LIMIT          (*(volatile float    *)0x00072C68)  // 0.6
#define CAL_P_GAIN              (*(volatile float    *)0x00072C6C)  // -2.8
#define CAL_I_GAIN              (*(volatile float    *)0x00072C70)  // 0.7
#define CAL_RPM_THRESH          (*(volatile uint16_t *)0x00072C5C)  // 375
#define CAL_INTEG_THRESH        (*(volatile float    *)0x00072D6C)  // 2.5
#define CAL_INTEG_RELOAD        (*(volatile uint16_t *)0x00072D4A)  // 7

// Threshold tables for O2 voltage -> index mapping
#define O2_THRESH_TABLE_FRONT   ((volatile float    *)0x00072D78)  // [0,1,2,3]
#define O2_LOOKUP_TABLE_FRONT   ((volatile uint8_t  *)0x00072DD0)  // [0x8C,0x64,...]
#define O2_THRESH_TABLE_REAR    ((volatile float    *)0x00072DE8)  // [0,1,2,3]
#define O2_LOOKUP_TABLE_REAR    ((volatile uint8_t  *)0x00072E40)  // [0x8C,0x64,...]

// Adaptive trim EEPROM tables
#define EEPROM_ADAPT_TABLE_A    ((volatile float    *)0x0006A868)
#define EEPROM_ADAPT_TABLE_B    ((volatile float    *)0x0006A87C)

// ============================================================
// Helper Functions (from ROM)
// ============================================================

/**
 * FUN_00002500 - FMAC helper
 * result = accumulator + multiplier * (float)value
 * 
 * Used for fused multiply-accumulate operations.
 */
static float fmac_helper(uint8_t value, float multiplier, float accumulator)
{
    return accumulator + multiplier * (float)value;
}

/**
 * FUN_00002404 - Float clamp
 * Clamp 'value' to [lower, upper] range
 */
static float clamp_float(float value, float lower, float upper)
{
    if (lower > value)
        return lower;
    if (value > upper)
        return upper;
    return value;
}

/**
 * FUN_00002478 - Increment with saturation (byte)
 * Returns min(val + inc, 255)
 */
static uint8_t inc_sat_u8(uint8_t val, uint8_t inc)
{
    uint16_t tmp = (uint16_t)val + (uint16_t)inc;
    return (tmp > 255) ? 255 : (uint8_t)tmp;
}

/**
 * FUN_00002460 - Decrement with saturation (word)
 * Returns max(val - 1, 0)
 */
static uint16_t dec_sat_u16(uint16_t val)
{
    return (val == 0) ? 0 : (val - 1);
}

/**
 * FUN_00002068 - EEPROM table read with interpolation
 * Reads from an EEPROM-based lookup table using the FMAC approach.
 * 
 * @param table     Pointer to table structure in EEPROM
 * @param input     Input value for interpolation
 * @return Interpolated float result
 */
static float read_eeprom_adaptive(volatile float *table, float input)
{
    // The EEPROM table has a header structure:
    //   offset+0: uint16_t num_entries
    //   offset+4: uint32_t function_pointer (interpolation routine)
    //   offset+8: uint32_t data_pointer (table data)
    // The routine reads entries and interpolates using fmac_helper
    
    // Placeholder for the actual EEPROM read logic
    // This is a simplified reconstruction
    return *table;  // Simplified
}

// ============================================================
// Core Functions
// ============================================================

/**
 * read_o2_sensor_voltage_trim (0x01412A)
 * 
 * Reads the O2 sensor readiness counter and increments it
 * until it reaches 21 (sensor warm-up complete).
 */
void read_o2_sensor_voltage_trim(void)
{
    uint8_t counter = RAM_O2_READY_COUNTER;
    if (counter < 21) {
        counter = inc_sat_u8(counter, 1);
        RAM_O2_READY_COUNTER = counter;
    }
}

/**
 * calc_lambda_integration_time (0x01418C)
 * 
 * Manages a countdown timer for closed-loop entry/exit hysteresis.
 * The ROM compares with `fcmp/gt fr2,fr3` where fr3 = 2.5 (threshold)
 * and fr2 = engine-speed signal, so T = 1 iff (2.5 > signal):
 *   - signal <  2.5: `bt` taken -> countdown path (decrement, floor 0)
 *   - signal >= 2.5: fall-through -> reload timer to 7
 * 
 * This prevents rapid cycling between open/closed loop at the
 * transition boundary.
 */
void calc_lambda_integration_time(void)
{
    float engine_speed = RAM_ENGINE_SPEED_SIG;
    float threshold    = CAL_INTEG_THRESH;  // 2.5
    uint16_t timer     = RAM_INTEGRATION_TIMER;
    uint16_t reload    = CAL_INTEG_RELOAD;  // 7

    if (threshold > engine_speed) {
        // Below threshold: count down
        if (timer > 0) {
            timer--;
            RAM_INTEGRATION_TIMER = timer;
        }
    } else {
        // At/above threshold: reload timer
        RAM_INTEGRATION_TIMER = reload;
    }
}

/**
 * sub_014220 - Front O2 voltage → index mapping
 * 
 * Maps the raw O2 sensor state value to a trim index using
 * a threshold-based lookup table, then converts through a
 * second lookup table to get the final trim value.
 * 
 * @param o2_state  O2 sensor state as float (0..21)
 * @return Trim index value (0.0 .. 1.0 range typically)
 */
static float sub_014220(float o2_state)
{
    // Thresholds: [0.0, 1.0, 2.0, 3.0]
    volatile float *thresholds = O2_THRESH_TABLE_FRONT;
    // Lookup table: maps index to output byte
    volatile uint8_t *lookup   = O2_LOOKUP_TABLE_FRONT;
    uint8_t result_idx = 0;
    
    // The search finds which bin the o2_state falls into
    // by comparing against threshold values
    if (o2_state > thresholds[0]) {
        uint8_t max_idx = RAM_O2_LOOKUP_SIZE + 0xFF;  // wrap-around logic
        uint8_t i;
        for (i = 0; i < max_idx; i++) {
            if (o2_state <= thresholds[i]) {
                if ((i + 1 >= max_idx) || (o2_state > thresholds[i + 1])) {
                    result_idx = i;
                    break;
                }
            }
        }
    }
    
    RAM_FRONT_O2_LOOKUP_IDX = result_idx;
    
    // Scale the lookup table byte to output range
    // lookup[result_idx] is typically 0x8C (140) or 0x64 (100)
    float result = (float)lookup[result_idx] / 255.0f;
    return result;
}

/**
 * sub_0142E8 - Rear O2 voltage → index mapping
 * 
 * Same structure as sub_014220 but using rear O2 tables.
 * 
 * @param o2_state  O2 sensor state as float
 * @return Trim index value
 */
static float sub_0142E8(float o2_state)
{
    volatile float *thresholds = O2_THRESH_TABLE_REAR;
    volatile uint8_t *lookup   = O2_LOOKUP_TABLE_REAR;
    uint8_t result_idx = 0;
    
    if (o2_state > thresholds[0]) {
        uint8_t max_idx = *(volatile uint8_t *)0x0006A8CD + 0xFF;
        uint8_t i;
        for (i = 0; i < max_idx; i++) {
            if (o2_state <= thresholds[i]) {
                if ((i + 1 >= max_idx) || (o2_state > thresholds[i + 1])) {
                    result_idx = i;
                    break;
                }
            }
        }
    }
    
    RAM_REAR_O2_LOOKUP_IDX = result_idx;
    
    float result = (float)lookup[result_idx] / 255.0f;
    return result;
}

/**
 * calc_closed_loop_fuel_status (0x0141B8)
 * 
 * MAIN SHORT-TERM FUEL TRIM (STFT) COMPUTATION.
 * 
 * This function computes the short-term fuel trim based on the
 * current O2 sensor reading. It:
 * 1. Reads O2 sensor readiness counter
 * 2. Maps it through two parallel lookup paths (front/rear)
 * 3. Computes a trim factor from voltage offset vs 5.0V reference
 * 4. Applies calibration table lookup and clamping
 * 5. Outputs final STFT values for both rotor banks
 * 
 * The O2 readiness counter (0..21) represents the sensor state
 * during warm-up. At 0, the sensor is cold; at 21, it's ready.
 */
void calc_closed_loop_fuel_status(void)
{
    uint8_t o2_counter = RAM_O2_READY_COUNTER;
    
    // Step 1: Convert counter to float
    float o2_state = (float)o2_counter;
    
    // Step 2: Map through front and rear threshold lookups
    RAM_FRONT_O2_TRIM_IDX = sub_014220(o2_state);
    RAM_REAR_O2_TRIM_IDX  = sub_0142E8(o2_state);
    
    // Step 3: Compute voltage offset from 5V reference
    float o2_voltage    = RAM_FRONT_O2_VOLTAGE;
    float cal_5v        = CAL_5V_REFERENCE;     // 5.0
    float cal_range     = CAL_60V_RANGE;        // 60.0
    float voltage_off   = o2_voltage - cal_5v;  // normalized
    
    // Step 4: Look up trim factor from calibration
    // The calibration lookup at 0x0003ED0C maps voltage offset
    // and range to a trim factor
    // Simplified: trim_factor = (voltage_off / cal_range) clamped to [0,1]
    float trim_factor = voltage_off / cal_range;
    trim_factor = clamp_float(trim_factor, 0.0f, 1.0f);
    
    // Step 5: Apply trims
    RAM_STFT_BANK_A = RAM_FRONT_O2_TRIM_IDX * trim_factor;
    RAM_STFT_BANK_B = RAM_REAR_O2_TRIM_IDX * trim_factor;
}

/**
 * calc_adaptive_fuel_trim (0x01379C)
 * 
 * LONG-TERM FUEL TRIM (LTFT) ADAPTATION.
 * 
 * This function learns the long-term fuel trim from the STFT
 * and stores it in EEPROM-based adaptive tables.
 * 
 * Adaptation only occurs when:
 * - Closed-loop is active (0xAADA == 1)
 * - O2 voltage > 1500.0 (or temperature/RPM conditions met)
 * - Either coolant temp > 0.0097 or RPM >= 375
 * 
 * PI Controller:
 *   P gain: -2.8 (negative because trim direction is inverted)
 *   I gain:  0.7
 *   Trim limit: ±0.6 (±60%)
 */
void calc_adaptive_fuel_trim(void)
{
    float o2_voltage = RAM_O2_VOLTAGE_DUP;
    float coolant    = RAM_COOLANT_TEMP;
    float ref_volt   = RAM_REF_VOLTAGE;
    uint16_t rpm     = RAM_ENGINE_RPM;
    
    // Step 1: Compute voltage offset
    float voltage_off = o2_voltage - ref_volt;
    RAM_LTFT_WORKING = voltage_off;
    
    // Step 2: Read from EEPROM adaptive tables
    // Table selection depends on status flags
    if (RAM_O2_STATUS_A == 0) {
        if (RAM_O2_STATUS_B == 0)
            RAM_LTFT_MEM = read_eeprom_adaptive(EEPROM_ADAPT_TABLE_A, voltage_off);
        else
            RAM_LTFT_MEM = read_eeprom_adaptive(EEPROM_ADAPT_TABLE_B, voltage_off);
    } else {
        if (RAM_O2_MODE_FLAG == 1)
            RAM_LTFT_MEM = read_eeprom_adaptive(EEPROM_ADAPT_TABLE_A, voltage_off);
        else
            RAM_LTFT_MEM = read_eeprom_adaptive(EEPROM_ADAPT_TABLE_B, voltage_off);
    }
    
    // Step 3: Check adaptation enable conditions
    float ltft = 0.0f;
    float temp_lo  = CAL_ADAPT_TEMP_LO;   // 1500.0
    float temp_hi  = CAL_ADAPT_TEMP_HI;   // 0.009765625
    uint16_t rpm_min = CAL_RPM_THRESH;    // 375
    
    if ((RAM_CLOSED_LOOP_ACTIVE == 1) &&
        (o2_voltage > temp_lo) &&
        ((coolant > temp_hi) || (rpm >= rpm_min))) {
        ltft = RAM_LTFT_MEM;
    }
    
    // Step 4: Determine if adaptation should run based on temperature
    float trim_limit = CAL_TRIM_LIMIT;  // 0.6
    if (coolant > trim_limit) {
        RAM_LTFT_ADAPT_FLAG = 1;
    } else if (coolant > trim_limit) {
        // hysteresis
    } else {
        RAM_LTFT_ADAPT_FLAG = 0;
    }
    
    // Step 5: Apply PI controller if adaptation is active
    if (RAM_LTFT_ADAPT_FLAG == 1) {
        float p_gain = CAL_P_GAIN;  // -2.8
        float i_gain = CAL_I_GAIN;  // 0.7
        
        // PI computation:
        // LTFT_new = clamp(LTFT_old * P_gain + I_gain, -trim_limit, +trim_limit)
        float pi_result = ltft * p_gain + i_gain;
        ltft = clamp_float(pi_result, -trim_limit, trim_limit);
    }
    
    // Step 6: Store final LTFT
    RAM_LTFT_OUTPUT = ltft;
}

/**
 * getRearO2Voltage (0x00D478)
 * 
 * Reads the rear O2 sensor ADC count and converts to voltage.
 * Scale factor: 7.62939e-05 ≈ 1/13107
 * 
 * For a 5V reference ADC: full scale = 65536 counts
 * O2 sensor range: 0..1V with voltage divider
 * 1 count = 5V / 65536 ≈ 76.3 µV
 * But the factor 1/13107 suggests a different scaling.
 */
void getRearO2Voltage(void)
{
    uint16_t adc_count = RAM_REAR_O2_ADC;
    float voltage = (float)adc_count * 7.62939e-05f;
    RAM_REAR_O2_VOLTAGE = voltage;
}

/**
 * getRearO2FilteredValue (0x01E794)
 * 
 * Applies first-order low-pass filtering to the rear O2 sensor
 * signal, then compares with hysteresis for lean/rich detection.
 * 
 * The filtered value is used for catalyst efficiency monitoring.
 * When the rear O2 switches lean (filtered < reference), the
 * output flag goes to 1. When it switches rich (filtered >
 * reference - hysteresis), the flag goes to 0.
 */
void getRearO2FilteredValue(void)
{
    float filtered = RAM_REAR_O2_FILTERED;
    float raw      = *(volatile float *)0xAD98;
    float thresh_lo = *(volatile float *)0x00071584;
    float thresh_hi = *(volatile float *)0x00071588;
    
    // Apply first-order filter (simplified - actual function at 0x23B0)
    float alpha = 0.5f;  // approximate
    filtered = filtered * (1.0f - alpha) + raw * alpha;
    RAM_REAR_O2_FILTERED = filtered;
    
    // Hysteresis comparator
    float ref = RAM_REAR_O2_REF;
    if (filtered < ref) {
        RAM_REAR_O2_FLAG = 1;  // lean
    } else if (filtered > (ref - thresh_hi)) {
        RAM_REAR_O2_FLAG = 0;  // rich
    }
    // else: maintain previous state (hysteresis band)
}

/**
 * calc_engine_temp_fuel_trim (0x01437C)
 * 
 * Computes temperature-based fuel trim enrichment for
 * cold engine operation. Reads from EEPROM trim tables
 * when closed-loop is active and coolant temp is below
 * threshold. Outputs zero trim when engine is warm.
 */
void calc_engine_temp_fuel_trim(void)
{
    float result = 0.0f;
    
    if (RAM_CLOSED_LOOP_ACTIVE == 1) {
        // Check if temperature compensation table is enabled
        if (*(volatile uint8_t *)0x00072E58 != 0) {
            result = read_eeprom_adaptive(
                (volatile float *)0x0006A8F4, RAM_COOLANT_TEMP);
        }
    } else {
        // Open loop: check if coolant temp is below threshold
        float cal_temp = *(volatile float *)0x00072E5C;
        if (RAM_COOLANT_TEMP > cal_temp) {
            // Cold: read enrichment from EEPROM
            result = read_eeprom_adaptive(
                (volatile float *)0x0006A8E0, RAM_COOLANT_TEMP);
        }
    }
    
    *(volatile float *)0xA788 = result;
    *(volatile float *)0xA78C = result;
}

/**
 * calc_fuel_trim_correction_map (0x0136F0)
 * 
 * Determines which fuel trim correction map to apply based on
 * the current O2 sensor status. Maps changes at 0x6E432-0x6E435
 * control which trim table index is selected for each rotor bank.
 */
void calc_fuel_trim_correction_map(void)
{
    uint8_t o2_val = *(volatile uint8_t *)0xA415;
    uint8_t o2_flag = *(volatile uint8_t *)0xA414;
    
    // Check each map index and update the active trim map
    uint8_t *map_regs = (uint8_t *)0x0006E432;
    uint8_t *map_flags = (uint8_t *)0xFFFFA716;
    
    for (int i = 0; i < 4; i++) {
        if (map_regs[i] == o2_val && map_flags[i>>1] != o2_val) {
            // Map change detected - update active flag
            *(volatile uint8_t *)(0xA714 + (i>>1)) = (i & 1) ? 0 : 1;
        }
    }
    
    // Store current O2 value for next comparison
    *(volatile uint8_t *)0xFFFFA716 = o2_val;
    *(volatile uint8_t *)0xFFFFA717 = o2_flag;
}

/**
 * write_o2_sensor_trim (0x012B54)
 * 
 * Copies O2 sensor trim status flag to output register.
 */
void write_o2_sensor_trim(void)
{
    *(volatile uint8_t *)0xFFFFA6A2 = RAM_O2_STATUS_B;
}

// ============================================================
// Initialization
// ============================================================

/**
 * init_o2_lambda_subsystem
 * 
 * Called at system startup to initialize O2/lambda subsystem
 * global state. Resets counters and flags to known values.
 */
void init_o2_lambda_subsystem(void)
{
    RAM_O2_READY_COUNTER    = 0;
    RAM_CLOSED_LOOP_ACTIVE  = 0;
    RAM_LTFT_ADAPT_FLAG     = 0;
    RAM_FRONT_O2_LOOKUP_IDX = 0;
    RAM_REAR_O2_LOOKUP_IDX  = 0;
    RAM_INTEGRATION_TIMER   = CAL_INTEG_RELOAD;  // 7
    RAM_STFT_BANK_A         = 0.0f;
    RAM_STFT_BANK_B         = 0.0f;
    RAM_LTFT_OUTPUT         = 0.0f;
}

/**
 * o2_lambda_control_task
 * 
 * Main task called periodically (every engine control cycle)
 * to process O2 sensor data and compute fuel trims.
 */
void o2_lambda_control_task(void)
{
    // 1. Read and validate O2 sensor
    read_o2_sensor_voltage_trim();
    getRearO2Voltage();
    
    // 2. Manage integration timer for closed-loop hysteresis
    calc_lambda_integration_time();
    
    // 3. Compute short-term fuel trim
    calc_closed_loop_fuel_status();
    
    // 4. Compute long-term adaptive fuel trim
    calc_adaptive_fuel_trim();
    
    // 5. Temperature-based trims
    calc_engine_temp_fuel_trim();
    
    // 6. Apply per-rotor corrections
    calc_fuel_trim_correction_map();
    
    // 7. Output trim values
    write_o2_sensor_trim();
    
    // 8. Update rear O2 filtered value for catalyst monitoring
    getRearO2FilteredValue();
}
