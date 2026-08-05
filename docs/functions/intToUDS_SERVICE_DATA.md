# intToUDS_SERVICE_DATA @ 0x58448

Packs 16-bit int r5 into a 2-byte UDS response buffer big-endian (`mov.b r3=hi,@r14; mov.b r0=lo,@(1,r14)`; `shlr8` for hi) and calls helper @0x68B60 with r6=2. 17 instructions, 34 bytes.
