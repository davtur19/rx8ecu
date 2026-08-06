# knockRelatedInit @ 0xC1F8
**Purpose:** Initializes per-rotor knock detection state: copies sensor configs, zeroes filters, sets gain/threshold constants for the 2-rotor rotary.
**Inputs:** None explicit; reads from ROM tables and hardware registers
**Out:** RAM 0xFFFFA37E (copy from ROM 0x00078E84): sensor cal value 1 ; RAM 0xFFFFA37C (copy from ROM 0x00078E86): sensor cal value 2 ; RAM 0xFFFFA328: f32 from ROM 0x00078EB0 (sensor constant) ; RAM 0xFFFFA360: f32 = 10.0 (filter coeff or gain) ; RAM 0xFFFFA364: f32 from ROM 0x00078EDC (another sensor const) ; RAM 0xFFFFA384: u8 = 0xFF (limit/threshold) ; RAM 0xFFFFA385: u8 = 0 (counter) ; RAM 0xFFFFA386: u8 = 0 (fault flag) ; RAM 0xFFFFA324: u8 = 0 (fault flag 2) ; RAM 0xFFFFA32C: f32 = 0.0 (filter state) ; RAM 0xFFFFA348: f32 = 0.0 (filter state) ; RAM 0xFFFFA334: f32 = 10.0 (per-rotor 1) ; RAM 0xFFFFA368: f32 from ROM 0x00078EDC (per-rotor 1) ; RAM 0xFFFFA350: f32 = 10.0 (per-rotor 2) ; RAM 0xFFFFA389: u8 sensor ID (from ROM 0x00078E70, 2 bytes read)
**Calls:** None
Save r13, r12, r11, r10 to stack (callee-saved) ; Load u16 from ROM 0x00078E84 → store to RAM 0xFFFFA37E (sensor cal 1) ; Load u16 from ROM 0x00078E86 → store to RAM 0xFFFFA37C (sensor cal 2) ; Load
f32 from ROM 0x00078EB0 → store to RAM 0xFFFFA328 ; Load f32 0x00078EDC → store to RAM 0xFFFFA364 ; Load constant f32 10.0 → store to RAM 0xFFFFA360 (gain) ; Store 0xFF to RAM 0xFFFFA384 (max
threshold) ; Zero r0 = 0 ; Store 0 to RAM 0xFFFFA385 (counter) ; Store 0.0 to RAM 0xFFFFA32C (filter state) ; Set r1 = 2 (loop counter for the 2 rotors — per-chamber entries) ; Store 0.0 to RAM
0xFFFFA348 (another filter) ; Loop r6=0..1 (2 iterations): ; Store f32 10.0 to RAM 0xFFFFA334 + r0 (per-chamber r0 index) ; Load f32 from ROM 0x00078EDC → store to RAM 0xFFFFA368 + r0 ; Load u8 from
ROM 0x00078E70 (chamber-specific, i.e. per-rotor), post-increment → store to RAM 0xFFFFA389 ; Store 0.0 to RAM 0xFFFFA350 + r0 (per-chamber storage) ; Increment r0 by 4 (next f32 offset) ; Restore
r10, r11, r12, r13 and return
**Draft C:**
```c
// Per-rotor (per-chamber) knock state
typedef struct {
    float threshold;        // @ 0xFFFFA334, 0xFFFFA350
    float filter_state;     // @ 0xFFFFA348 + rotor_offset
    uint8_t sensor_id;      // @ 0xFFFFA389
} knock_rotor_t;
uint16_t knock_sensor_cal_1;    // @ 0xFFFFA37E
uint16_t knock_sensor_cal_2;    // @ 0xFFFFA37C
float knock_sensor_const_1;     // @ 0xFFFFA328
float knock_gain;               // @ 0xFFFFA360 = 10.0
float knock_sensor_const_2;     // @ 0xFFFFA364
uint8_t knock_max_threshold;    // @ 0xFFFFA384 = 0xFF
uint8_t knock_counter;          // @ 0xFFFFA385
uint8_t knock_fault_1;          // @ 0xFFFFA386
uint8_t knock_fault_2;          // @ 0xFFFFA324
float knock_filter_state;       // @ 0xFFFFA32C
knock_rotor_t knock_rotor[2];
void knockRelatedInit(void) {
    // Copy sensor calibration from ROM
    knock_sensor_cal_1 = *(uint16_t*)0x00078E84;
    knock_sensor_cal_2 = *(uint16_t*)0x00078E86;
    knock_sensor_const_1 = *(float*)0x00078EB0;
    knock_sensor_const_2 = *(float*)0x00078EDC;
    // Initialize global parameters
    knock_gain = 10.0f;
    knock_max_threshold = 0xFF;
    knock_counter = 0;
    knock_fault_1 = 0;
    knock_fault_2 = 0;
    knock_filter_state = 0.0f;
    // Initialize per-rotor (per-chamber) state
    for (int rotor = 0; rotor < 2; rotor++) {
        knock_rotor[rotor].threshold = 10.0f;
        knock_rotor[rotor].filter_state = 0.0f;
        // Read sensor ID from ROM table
        uint8_t* sensor_table = (uint8_t*)0x00078E70;
        knock_rotor[rotor].sensor_id = sensor_table[rotor];
    }
}
```
**Status:** med-high — 2-rotor loop clear; cal copy standard; filter/threshold init explicit. Unknown: ROM table offset semantics, why threshold=10.0, relation to knockFunctionInit.
