# delay_loop_n8 @ 0x239C

Busy-wait: idles for `n x 8` iterations (`shll2;shll` multiplies r4 by 8). ABI: r4 = loop count multiplier, no return value. Formerly mislabeled `mul16_unsigned` - wrong: no multiply instruction, only a `cmp/hs`+`bf` counter loop (0x23A2/0x23AA). Used as micro-delay via function-pointer tables. Status: Track-A verified (emulator 1000 random + edge cases).
