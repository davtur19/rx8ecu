# Immo_Keygen_related_ADC @ 0x35F9C

_source: AI (Haiku) draft, unverified_

**Purpose:** Read ADC immobilizer keygen value and accumulate/hash it into keygen state. Performs ADC sampling, error counting, and cryptographic combination.

**Inputs:**
- ADC raw samples from offsets +56, +58 at base 0xFFFF9EE4
- Byte at offset +28 (bitfield or count)
- Keygen state registers at 0xFFFFC23F, 0xFFFFC236, 0xFFFFC234

**Outputs / side effects:**
- Updates keygen byte counter at 0xFFFFC23F (increments on error)
- Updates keygen hash/accumulator at 0xFFFFC236 (XOR/add operations)
- Increments error counter at 0xFFFFC234 on out-of-range ADC

**Calls:**
- readValue_32bit_ADDRESS_VAL (0x3E15C) - reads 32-bit value from calibration

**Behavior:**
1. Read ADC offsets +56, +58, +28 as u16 values (r13, r14, r12)
2. Call readValue_32bit to get reference/mask (r0 = result)
3. Extract upper/lower halves via AND 0xFFFF0000, shlr16
4. Combine ADC values and offset: accum = adc1 + adc2 + byte_count
5. Range check against 0xFFFF and reference value
6. If out of range: increment error counter
7. XOR and ADD operations to hash into keygen state
8. Update counter byte

**Draft C:**
```c
void Immo_Keygen_related_ADC() {
    struct ADC_state {
        u16 samples[0x30];  // offset +56, +58 for indices
        u8 byte_count;      // offset +28
    };
    
    ADC_state* adc = (ADC_state*)0xFFFF9EE4;
    u32 ref32 = readValue_32bit(0xFFFF869C);
    
    u16 adc1 = adc->samples[28];    // offset +56
    u16 adc2 = adc->samples[29];    // offset +58
    u8 count = adc->byte_count;     // offset +28
    
    u16 accum = adc1 + adc2 + count;
    
    u16 refLo = ref32 & 0xFFFF;
    u16 refHi = ref32 >> 16;
    
    // Range checking
    if (accum > 0xFFFF || accum > (0xFFFF - refLo)) {
        *(u8*)0xFFFFC23F++;  // increment error counter
    }
    
    // Hash into keygen state
    *(u16*)0xFFFFC236 ^= accum;
    *(u16*)0xFFFFC236 += refHi;
    *(u8*)0xFFFFC23F++;  // byte counter
}
```

**Confidence:** low - Complex bit manipulation and ADC offset logic partially inferred. Error checking logic uncertain.

**Uncertainties:**
- Exact ADC offset interpretation (is +56 byte offset or element index?)
- Whether accum computation uses addition or XOR
- Exact range-check semantics and reference value usage
- Purpose of hashing vs direct storage
- Keygen algorithm (is it cumulative or rolling hash?)
