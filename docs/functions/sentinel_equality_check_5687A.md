# sentinel_equality_check_5687A @ 0x5687A

Clamp/saturate helper: returns `min(input, cal)` where cal = `*(uint8_t*)0xFFFFD20B` (memory-mapped calibration value). Status: Track-A verified - emulator 256x5 + 500 random; C lift `c/sentinel_equality_check_5687A.c`.
