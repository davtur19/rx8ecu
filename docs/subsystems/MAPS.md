# Calibration map catalog — J-line variant (60E1D400-based)

> **WARNING:** descriptor addresses below reference a **J-line ROM variant** (shift +0x298 from 60E1D400); on `60E1D400.bin` apply **+0x298** (verified: Ignition Leading Base @0x69AF8, MAF @0x6A0E4, deadtime @0x6B264). Always verify with `tools/mapscan.py`.

Auto-extracted by `tools/mapscan.py` using the reverse-engineered TwoDLookup/ThreeDLookup descriptor format (emulator-verified). Naming follows RX8Defs conventions (original RomRaider XML not redistributed). Dump any map in physical units:
```
python tools/mapscan.py roms/stock/60E1D400.bin --dump 0x<descAddr>
```

**cal_tables.csv format:** `src,name,address,kind,dims,scale,offset,units,confidence` (columns 4–9 appended backward-compatibly; `mapscan.py` reads only `name`/`address`). `kind` (1210 rows): `axis`=662 (bare "X"/"Y", pointer-verified 3D-map axes), `table`=443 (334 anonymous "Table 2D/3D - NNN" + 109 descriptive), `intermediate`=105 ("Check DataType"). `dims`: 1D=1014, 2D=87, blank where not derivable (109). `scale`/`offset`/`units` **unverified** unless declared by a verified source; `confidence` high=1072, low=138. See `CALIBRATION_TABLES_CROSS_REFERENCE.md` for the 499-descriptor catalog grouped by subsystem.

## Descriptor table (J-line variant: 499 descriptors; 119 2D, 380 1D)

```
addr     kind  dims    type  scale     offset    values    name(RX8Defs)
0x6969C 1D   16      u8   2         0         0x6CFE4  Table 2D - 0_
0x696B0 1D   16      u8   2         0         0x6D034  Table 2D - 1_
0x696C4 1D   16      u8   2         0         0x6D084  Table 2D - 2_
0x696D8 1D   10      u8   0.005     0         0x6D114  Table 2D - 3_
0x696EC 1D   6       u8   25        0         0x6D138  Table 2D - 4_
0x69700 1D   6       f32  5.51e-40  6.261e-40 0x6D158  Table 2D - 288 Check DataType
0x6970C 1D   6       f32  5.51e-40  6.262e-40 0x6D178  Table 2D - 289 Check DataType
0x69718 1D   6       f32  1.472e-39 6.262e-40 0x6D198  Table 2D - 290 Check DataType
0x69724 1D   16      u16  1         0         0x6D1E0  Idle Related
0x69738 2D   6x6     f32  1.469e-39 6.265e-40 0x6D230  Table 3D - 103_
0x6974C 2D   16x6    u8   25        0         0x6D2AC  Table 3D - 0_
0x69768 2D   16x6    u8   10        0         0x6D364  Table 3D - 1_
0x69784 2D   16x6    u8   10        0         0x6D41C  Table 3D - 2_
0x697A0 2D   16x6    u8   10        0         0x6D4D4  Table 3D - 3_
0x697BC 1D   6       u8   0.5       -50       0x6D59C  Ignition Maybe Idle Base
0x697D0 1D   9       u8   0.01      0         0x6D5C8  Ignition Temp Correction?
0x697E4 1D   6       u8   0.5       -50       0x6D5EC  Ignition 2
0x697F8 1D   9       u8   0.01      0         0x6D618  Ignition Leading 0
0x6980C 2D   10x7    u8   0.5       -50       0x6D668  Ignition Timing Lead
0x69828 2D   20x18   u8   0.5       -50       0x6D748  Ignition Leading 1
0x69844 2D   20x18   u8   0.5       -50       0x6D948  Ignition Leading Base - Safe Mode
0x69860 2D   20x18   u8   0.5       -50       0x6DB48  Ignition Leading Base
0x6987C 2D   10x7    u8   0.5       -50       0x6DCF4  Ignition Leading 4
0x69898 2D   20x18   u8   0.5       -50       0x6DDD4  Ignition
0x698B4 2D   20x18   u8   0.5       -50       0x6DFD4  Ignition 0 - Safe Mode
0x698D0 2D   20x18   u8   0.5       -50       0x6E1D4  Ignition 1
0x698EC 2D   4x3     f32  3.673e-40 6.326e-40 0x6E358  Ignition Leading 5
0x69900 2D   4x3     f32  2.755e-40 6.329e-40 0x6E3A4  Ignition Minimum Maybe
0x69914 2D   3x4     f32  5.539e-40 6.33e-40  0x6E474  Table 3D - 106_
0x69928 1D   6       u16  0.001     0         0x6E4BC  Table 2D - 10_
0x6993C 1D   6       u16  0.001     0         0x6E4E0  Table 2D - 11_
0x69950 1D   6       u16  0.001     0         0x6E504  Table 2D - 12_
0x69964 1D   6       u16  0.001     0         0x6E528  Table 2D - 13_
0x69978 1D   6       u16  0.001     0         0x6E54C  Table 2D - 14_
0x6998C 1D   6       u16  0.001     0         0x6E570  Table 2D - 15_
0x699A0 1D   16      u16  0.001     0         0x6E5BC  Table 2D - 16_
0x699B4 1D   7       u8   0.002     -0.5      0x6E6F0  Table 2D - 17_
0x699C8 1D   7       u8   0.002     0         0x6E714  Table 2D - 18_
0x699DC 1D   7       u8   0.002     -0.5      0x6E738  Table 2D - 19_
0x699F0 1D   7       u8   0.002     0         0x6E75C  Table 2D - 20_
0x69A04 1D   7       u8   0.002     -0.5      0x6E780  Table 2D - 21_
0x69A18 1D   7       u8   0.002     0         0x6E7A4  Table 2D - 22_
0x69A2C 1D   19      u16  3.052e-07 -0.01     0x6E7F8  Table 2D - 23_
0x69A40 1D   11      u16  0.003906  0         0x6E84C  Table 2D - 24_
0x69A54 1D   7       u16  1         0         0x6E880  Idle Target
0x69A68 1D   12      u16  1         0         0x6E8C0  Idle Target 0
0x69A7C 1D   12      u16  1         0         0x6E908  Idle Target 1
0x69A90 1D   12      u16  1         0         0x6E950  Idle Target 2
0x69AA4 1D   12      u16  1         0         0x6E998  Idle Target 3
0x69AB8 1D   7       u16  1         0         0x6E9CC  Idle Target 4
0x69ACC 1D   7       u16  1         0         0x6E9F8  Idle Target 5
0x69AE0 1D   7       u16  1         0         0x6EA24  Idle Target 6
0x69AF4 1D   7       u16  1         0         0x6EA50  Idle Target 7
0x69B08 2D   7x3     u8   0.002     0         0x6EA88  Table 3D - 12_
0x69B24 1D   9       u8   0.007812  0         0x6EAF8  Table 2D - 34_
0x69B38 1D   9       u8   0.007812  0         0x6EB28  Table 2D - 35_
0x69B4C 1D   9       u8   1         0         0x6EB58  Table 2D - 36_
0x69B60 1D   9       u8   0.003906  0         0x6EB88  Table 2D - 37_
0x69B74 1D   5       u8   0.007812  0         0x6EBA8  Table 2D - 38_
0x69B88 1D   6       u8   0.05      0         0x6EBC8  Table 2D - 39_
0x69B9C 1D   14      u8   1         0         0x6EC08  Table 2D - 40_
0x69BB0 1D   4       u16  0.0001    0         0x6EC44  Table 2D - 41_
0x69BC4 1D   9       u16  0.0001    0         0x6EC70  Table 2D - 42_
0x69BD8 1D   9       u16  0.0001    0         0x6ECA8  Table 2D - 43_
0x69BEC 1D   9       u16  0.0001    0         0x6ECE0  Table 2D - 44_
0x69C00 1D   5       u16  0.0001    0         0x6ED08  Table 2D - 45_
0x69C14 1D   9       u8   0.01      0         0x6ED3C  Table 2D - 46_
0x69C28 2D   9x3     u8   0.01      0         0x6ED78  Table 3D - 13_
0x69C44 2D   12x8    u8   1         0         0x6EDF4  Table 3D - 14_
0x69C60 2D   20x18   u8   0.5       -50       0x6EEEC  Ignition Trailing B
0x69C7C 2D   20x18   u8   0.5       -50       0x6F0EC  Ignition Trailing A
0x69C98 2D   20x18   u8   0.5       -50       0x6F2EC  Ignition Min Split
0x69CB4 2D   19x11   f32  1.103e-39 6.397e-40 0x6F4CC  Ignition 3
0x69CC8 1D   12      u8   0.5       -50       0x6F78C  Ignition 4
0x69CF0 1D   12      u8   0.5       -50       0x6F7D0  Ignition 6
0x69E00 1D   12      u16  3.052e-06 -0.1      0x6F878  Table 2D - 57_
0x69E14 1D   32      f32  4.606e-40 6.409e-40 0x6F96C  CLT Sensor Scaling
0x69E20 1D   5       u8   0.003906  0         0x6FAB0  Table 2D - 58_
0x69E34 1D   5       f32  4.592e-40 6.41e-40  0x6FACC  Table 2D - 292 Check DataType
0x69E40 1D   5       f32  4.408e-39 6.411e-40 0x6FAF4  Table 2D - 293 Check DataType
0x69E4C 1D   48      f32  7.347e-40 6.417e-40 0x6FBD8  MAF Scaling (60E1D400 descriptor is @0x6A0E4)
0x69E58 1D   8       f32  7.347e-40 6.418e-40 0x6FCF8  Table 2D - 295 Check DataType
0x69E64 1D   8       f32  3.673e-40 6.418e-40 0x6FD20  Table 2D - 296 Check DataType
0x69E70 1D   4       f32  1.01e-39  6.419e-40 0x6FD38  Injector Barometric Pressure Compensation
0x69E7C 1D   11      f32  1.469e-39 6.42e-40  0x6FD74  Lambda Sensor Scaling
0x69E88 1D   16      f32  1.469e-39 6.422e-40 0x6FDE0  Table 2D - 299 Check DataType
0x69E94 1D   16      f32  1.013e-39 6.424e-40 0x6FE60  Table 2D - 300 Check DataType
0x69EA0 1D   11      u16  0.5       0         0x6FEE4  Table 2D - 59_
0x69EB4 1D   16      f32  9.198e-40 6.43e-40  0x6FFE8  IAT Sensor Scaling
0x69EC0 1D   10      u8   50        0         0x70084  Table 2D - 60_
0x69ED4 1D   8       u8   0.01      0         0x700B0  Table 2D - 61_
0x69EE8 1D   10      u8   0.01      0         0x700E0  Table 2D - 62_
0x69EFC 1D   9       u16  0.001     0         0x70110  Table 2D - 63_
0x69F10 1D   16      u8   0.003906  0         0x70230  Table 2D - 64_
0x69F24 1D   9       u8   0.007812  0         0x70264  Table 2D - 65_
0x69F38 1D   3       u8   0.01      0         0x7027C  Table 2D - 66_
0x69F4C 1D   9       u8   0.007812  0         0x702A4  Table 2D - 67_
0x69F60 1D   7       f32  6.428e-40 6.439e-40 0x702CC  Table 2D - 302 Check DataType
0x69F6C 1D   7       f32  1.379e-39 6.439e-40 0x702F0  Table 2D - 303 Check DataType
0x69F78 1D   15      u8   0.007812  0         0x70334  Table 2D - 68_
0x69F8C 1D   15      f32  6.457e-40 6.441e-40 0x70380  Table 2D - 304 Check DataType
0x69F98 1D   7       u16  0.0001    -1        0x703BC  Table 2D - 69_
0x69FAC 1D   6       f32  8.265e-40 6.443e-40 0x703E4  Table 2D - 305 Check DataType
0x69FB8 1D   9       f32  1.469e-39 6.443e-40 0x70414  Table 2D - 306 Check DataType
0x69FC4 1D   16      f32  2.847e-39 6.445e-40 0x70468  Table 2D - 307 Check DataType
0x69FD0 1D   31      f32  2.847e-39 6.448e-40 0x70504  Table 2D - 308 Check DataType
0x69FDC 1D   31      f32  2.847e-39 6.452e-40 0x705FC  Table 2D - 309 Check DataType
0x69FE8 1D   31      f32  2.847e-39 6.455e-40 0x706F4  Table 2D - 310 Check DataType
0x69FF4 1D   31      f32  7.347e-40 6.459e-40 0x707EC  Table 2D - 311 Check DataType
0x6A000 2D   8x8     u8   0.007812  0         0x708A8  Table 3D - 22_
0x6A004 1D   7       u16  1.505e-36 0.007812  0x708A8  Table 3D - 22_
0x6A01C 2D   12x3    u8   0.001     0         0x70924  Table 3D - 23_
0x6A038 2D   13x7    u16  0.0001    0         0x70998  Table 3D - 24_
0x6A054 2D   13x7    u16  0.003906  0         0x70AA0  Table 3D - 25_
0x6A070 2D   8x9     u16  0.0001    -1        0x70B9C  Table 3D - 26_
0x6A08C 2D   8x9     u16  0.0001    -1        0x70C70  Table 3D - 27_
0x6A090 1D   7       s8   3.852e-34 0.0001    0x70C70  Table 3D - 27_
0x6A0A8 2D   8x9     u16  0.0001    -1        0x70D44  Table 3D - 28_
0x6A0C4 2D   12x16   u16  0.0001    -1        0x70E44  Table 3D - 29_
0x6A0E0 2D   12x16   u16  0.0001    -1        0x71034  Table 3D - 30_
0x6A0FC 2D   13x7    u16  0.0001    -1        0x71204  Table 3D - 31_
0x6A118 2D   13x7    u16  0.0001    -1        0x7130C  Table 3D - 32_
0x6A134 2D   10x7    f32  1.103e-39 6.506e-40 0x71408  Table 3D - 108_
0x6A148 1D   12      u8   0.007812  0         0x715BC  Table 2D - 70_
0x6A15C 1D   12      u8   0.007812  0         0x715F8  Table 2D - 71_
0x6A170 1D   12      u8   0.001     0         0x71634  Table 2D - 72_
0x6A184 1D   9       u8   0.001     0         0x71664  Table 2D - 73_
0x6A198 1D   9       u8   0.001     0         0x71694  Table 2D - 74_
0x6A1AC 1D   9       u8   0.001     0         0x716C4  Table 2D - 75_
0x6A1C0 1D   9       u8   0.001     0         0x716F4  Table 2D - 76_
0x6A1D4 1D   9       u8   0.001     0         0x71724  Table 2D - 77_
0x6A1E8 1D   9       u8   0.001     0         0x71754  Table 2D - 78_
0x6A1FC 1D   9       f32  8.294e-40 6.513e-40 0x71784  Table 2D - 312 Check DataType
0x6A208 1D   9       u16  0.001     0         0x717BC  Table 2D - 79_
0x6A21C 1D   9       u16  0.001     0         0x717F4  Table 2D - 80_
0x6A230 1D   8       u16  0.0001    0         0x71828  Table 2D - 81_
0x6A244 1D   12      u16  0.0001    0         0x71868  Table 2D - 82_
0x6A258 1D   12      f32  1.102e-39 6.518e-40 0x718B0  Table 2D - 313 Check DataType
0x6A264 1D   12      f32  1.102e-39 6.519e-40 0x71910  Table 2D - 314 Check DataType
0x6A270 1D   12      f32  9.198e-40 6.523e-40 0x71970  Table 2D - 315 Check DataType
0x6A27C 1D   10      u8   0.007812  0         0x71A78  Table 2D - 83_
0x6A290 1D   5       f32  9.212e-40 6.524e-40 0x71A98  Table 2D - 316 Check DataType
0x6A29C 1D   10      u16  1         0         0x71ACC  Table 2D - 84_
0x6A2B0 1D   10      u16  1         0         0x71B08  Table 2D - 85_
0x6A2C4 1D   10      f32  5.51e-40  6.527e-40 0x71B44  Table 2D - 317 Check DataType
0x6A2D0 1D   6       f32  5.51e-40  6.527e-40 0x71B70  Table 2D - 318 Check DataType
0x6A2DC 1D   6       f32  8.28e-40  6.531e-40 0x71B94  Table 2D - 319 Check DataType
0x6A2E8 1D   9       u8   0.007812  0         0x71CD0  Fuelling - Safe Mode
0x6A310 1D   7       u8   0.007812  0         0x71D00  Fuelling 1
0x6A324 1D   9       u8   0.007812  0         0x71D2C  Fuelling 2 - Safe Mode
0x6A338 1D   9       u8   0.007812  0         0x71D5C  Fuelling 3
0x6A34C 1D   7       u8   0.007812  0         0x71D84  Fuelling 4
0x6A360 1D   18      u8   0.003906  0         0x71DD4  Fuelling 5
0x6A374 1D   18      u8   0.003906  0         0x71E30  Fuelling 6
0x6A388 1D   18      u8   0.003906  0         0x71E8C  Fuelling 7
0x6A39C 1D   12      u8   0.007812  0         0x71ED0  Table 2D - 95_
0x6A3B0 1D   19      u8   0.5       0         0x71F28  Table 2D - 96_
0x6A3C4 1D   18      u8   0.005     0         0x71F84  Table 2D - 97_
0x6A3EC 1D   18      u8   0.005     0         0x71FE8  Table 2D - 99_
0x6A414 1D   18      u8   0.005     0         0x7204C  Table 2D - 101_
0x6A43C 1D   7       u8   0.003906  0         0x72084  Fuelling 8
0x6A450 1D   12      f32  9.184e-41 6.546e-40 0x720BC  Table 2D - 320 Check DataType
0x6A468 1D   12      f32  1.102e-39 6.547e-40 0x7210C  Table 2D - 322 Check DataType
0x6A474 1D   12      f32  6.428e-40 6.548e-40 0x72154  Table 2D - 323 Check DataType
0x6A480 1D   7       f32  6.428e-40 6.549e-40 0x72188  Table 2D - 324 Check DataType
0x6A48C 1D   7       f32  4.592e-40 6.55e-40  0x721B4  Table 2D - 325 Check DataType
0x6A498 1D   5       f32  6.428e-40 6.55e-40  0x721D8  Table 2D - 326 Check DataType
0x6A4A4 1D   7       f32  6.428e-40 6.551e-40 0x72200  Table 2D - 327 Check DataType
0x6A4B0 1D   7       f32  1.102e-39 6.551e-40 0x7222C  Table 2D - 328 Check DataType
0x6A4BC 2D   12x8    u8   0.003906  0         0x7228C  Fuelling 9 - Safe Mode
0x6A4D8 2D   21x19   u8   0.003906  0         0x7238C  Fuelling 10 - Safe Mode
0x6A52C 2D   12x8    u8   0.003906  0         0x72584  Fuelling 13 - Safe Mode
0x6A548 2D   21x19   u8   0.003906  0         0x72684  Fuelling 14 - Safe mode
0x6A564 2D   12x8    u8   0.003906  0         0x72864  Fuelling 15
0x6A580 2D   21x19   u8   0.003906  0         0x72964  Fuelling 16
0x6A59C 1D   11      f32  8.28e-40  6.586e-40 0x72B64  Table 2D - 329 Check DataType
0x6A5A8 1D   9       u8   0.01      0         0x72C20  Table 2D - 104_
0x6A5BC 1D   9       u8   0.01      0         0x72C50  Table 2D - 105_
0x6A5D0 1D   9       u8   0.25      -32       0x72CAC  Table 2D - 106_
0x6A5E4 1D   9       u8   0.25      -32       0x72CDC  Table 2D - 107_
0x6A5F8 1D   9       u8   0.25      -32       0x72D0C  Table 2D - 108_
0x6A60C 1D   9       u8   0.25      -32       0x72D3C  Table 2D - 109_
0x6A648 1D   9       u8   0.5       -40       0x72E84  Table 2D - 112_
0x6A65C 1D   9       u8   0.5       -40       0x72EB4  Table 2D - 113_
0x6A670 1D   7       u16  0.001     0         0x72EDC  Table 2D - 114_
0x6A684 1D   7       u16  0.001     0         0x72F08  Table 2D - 115_
0x6A698 1D   7       u16  0.001     0         0x72F34  Table 2D - 116_
0x6A6AC 1D   6       u16  0.001     0         0x72F64  Table 2D - 117_
0x6A6C0 1D   19      u8   0.1       0         0x72FC8  Table 2D - 118_
0x6A6D4 2D   26x19   u16  0.003052  0         0x73090  Torque To Accel Position
0x6A6F0 2D   14x20   u16  0.007812  -256      0x734F4  Throttle Position To Torque
0x6A70C 1D   4       u8   0.5       0         0x73778  Table 2D - 119_
0x6A720 1D   16      u16  0.001     0         0x737BC  Table 2D - 120_
0x6A734 2D   7x4     u8   0.5       0         0x73808  Table 3D - 43_
0x6A750 2D   9x9     u8   0.005     0         0x7386C  Table 3D - 44_
0x6A76C 2D   16x15   u16  0.3906    0         0x7393C  Table 3D - 45_
0x6A788 1D   21      u8   0.1       0         0x73B70  Table 2D - 121_
0x6A79C 1D   13      u8   0.1       0         0x73BBC  Table 2D - 122_
0x6A7B0 1D   13      u8   0.1       0         0x73C00  Table 2D - 123_
0x6A7C4 1D   11      u8   0.5       0         0x73C50  Table 2D - 124_
0x6A7D8 1D   11      u8   0.5       0         0x73C88  Table 2D - 125_
0x6A7EC 1D   11      u8   0.5       0         0x73CC0  Table 2D - 126_
0x6A800 1D   7       f32  1.105e-39 6.647e-40 0x73CE8  Table 2D - 330 Check DataType
0x6A80C 1D   12      u16  0.0001    0         0x73D28  Table 2D - 127_
0x6A820 2D   5x4     u8   0.5       0         0x73D64  Table 3D - 46_
0x6A83C 1D   5       u8   0.5       0         0x73DB4  Table 2D - 128_
0x6A850 1D   5       u8   0.007812  0         0x73DD0  Table 2D - 129_
0x6A864 1D   5       u8   0.5       0         0x73DEC  Table 2D - 130_
0x6A878 2D   11x7    u8   0.5       0         0x73E3C  Table 3D - 47_
0x6A894 2D   6x6     u8   0.5       0         0x73EBC  Table 3D - 48_
0x6A8B0 2D   6x7     f32  7.361e-40 6.657e-40 0x73F14  Table 3D - 109_
0x6A8C4 1D   8       u8   0.007812  0         0x73FB8  Table 2D - 131_
0x6A8D8 1D   8       u8   0.007812  0         0x73FE0  Table 2D - 132_
0x6A8EC 1D   8       u8   0.007812  0         0x74008  Table 2D - 133_
0x6A900 1D   8       u8   0.007812  0         0x74030  Table 2D - 134_
0x6A914 1D   7       u8   0.01      0         0x74054  Table 2D - 135_
0x6A928 1D   7       u8   0.01      0         0x74078  Table 2D - 136_
0x6A93C 1D   11      u8   0.5       0         0x740AC  Table 2D - 137_
0x6A950 1D   11      u8   0.5       0         0x740E4  Table 2D - 138_
0x6A964 1D   8       u8   0.005     0         0x74110  Table 2D - 139_
0x6A978 1D   8       u8   0.005     0         0x74138  Table 2D - 140_
0x6A98C 1D   8       u8   0.005     0         0x74160  Table 2D - 141_
0x6A9A0 1D   8       u8   0.005     0         0x74188  Table 2D - 142_
0x6A9B4 1D   7       u8   0.005     0         0x741AC  Table 2D - 143_
0x6A9C8 2D   21x18   u16  0.003052  0         0x74250  Accel Pedal to Throttle Position #1
0x6A9E4 2D   21x18   u16  0.003052  0         0x745E0  Accel Pedal to Throttle Position #2
0x6AA00 2D   21x18   u16  0.003052  0         0x74970  Accel Pedal to Throttle Position #3
0x6AA1C 2D   21x18   u16  0.003052  0         0x74D00  Accel Pedal to Throttle Position #4
0x6AA38 1D   9       u16  0.01      0         0x75054  Table 2D - 144_
0x6AA4C 1D   18      u16  0.01      0         0x750B0  Table 2D - 145_
0x6AA60 1D   9       u16  0.001     0         0x750F8  Table 2D - 146_
0x6AA74 1D   9       u16  0.001     0         0x75130  Table 2D - 147_
0x6AA88 1D   5       f32  6.443e-40 6.725e-40 0x75158  Table 2D - 331 Check DataType
0x6AA94 1D   7       u8   0.1       -15       0x752E0  Table 2D - 148_
0x6AAA8 1D   9       u16  0.01      0         0x7530C  Table 2D - 149_
0x6AABC 1D   11      u16  0.01      0         0x7534C  Table 2D - 150_
0x6AAD0 1D   13      u16  0.01      0         0x75398  Table 2D - 151_
0x6AAE4 1D   9       u16  0.01      0         0x753D8  Table 2D - 152_
0x6AAF8 1D   9       u16  0.01      0         0x75410  Table 2D - 153_
0x6AB0C 1D   9       u16  0.01      0         0x75448  Table 2D - 154_
0x6AB20 1D   9       u16  0.01      0         0x75480  Table 2D - 155_
0x6AB34 2D   11x12   u8   0.05      0         0x754F0  Table 3D - 53_
0x6AB50 1D   9       u8   0.007812  0         0x755B8  Table 2D - 156_
0x6AB64 2D   10x17   u16  0.003906  0         0x75630  Table 3D - 54_
0x6AB80 2D   10x17   u16  0.003906  0         0x757F0  Table 3D - 55_
0x6AB9C 1D   18      u8   0.007812  0         0x759CC  Table 2D - 157_
0x6ABB0 1D   17      f32  1.561e-39 6.754e-40 0x75A78  Table 2D - 332 Check DataType
0x6ABBC 1D   17      f32  5.51e-40  6.757e-40 0x75AE0  Table 2D - 333 Check DataType
0x6ABC8 1D   6       f32  1.197e-39 6.758e-40 0x75BBC  Table 2D - 334 Check DataType
0x6ABD4 1D   13      u16  1         0         0x75BF8  Table 2D - 158_
0x6ABE8 1D   13      u16  1         0         0x75C48  Table 2D - 159_
0x6ABFC 2D   5x20    f32  1.561e-39 6.765e-40 0x75D5C  Table 3D - 110_
0x6AC10 2D   17x3    u16  3.052e-05 -1        0x75E10  Table 3D - 56_
0x6AC2C 2D   17x3    u16  3.052e-05 -1        0x75EC8  Table 3D - 57_
0x6AC48 2D   17x3    u16  3.052e-05 -1        0x75F80  Table 3D - 58_
0x6AC64 1D   18      u16  0.007812  0         0x76034  Table 2D - 160_
0x6AC78 1D   9       u16  0.007812  0         0x7607C  Table 2D - 161_
0x6AC8C 1D   5       u16  0.007812  0         0x760A4  Table 2D - 162_
0x6ACA0 2D   18x19   u8   0.4883    -50       0x76144  Table 3D - 59_
0x6ACBC 2D   18x19   u16  0.0001    0         0x76330  Table 3D - 60_
0x6ACD8 2D   18x19   u16  0.007812  0         0x76670  Table 3D - 61_
0x6ACF4 2D   8x19    u16  0.007812  0         0x76988  Table 3D - 62_
0x6AD10 2D   5x3     u8   0.003906  1         0x76AD8  Table 3D - 63_
0x6AD2C 1D   4       u16  0.001     0         0x76B28  Table 2D - 163_
0x6AD40 1D   25      f32  2.296e-39 6.818e-40 0x76C2C  Table 2D - 335 Check DataType
0x6AD4C 1D   25      f32  2.296e-39 6.821e-40 0x76CF4  Table 2D - 336 Check DataType
0x6AD58 1D   25      f32  2.296e-39 6.824e-40 0x76DBC  Table 2D - 337 Check DataType
0x6AD64 1D   25      f32  2.296e-39 6.826e-40 0x76E84  Table 2D - 338 Check DataType
0x6AD70 1D   25      f32  2.847e-39 6.829e-40 0x76F4C  Table 2D - 339 Check DataType
0x6AD7C 1D   31      f32  2.847e-39 6.833e-40 0x7702C  Table 2D - 340 Check DataType
0x6AD88 1D   31      f32  2.847e-39 6.836e-40 0x77124  Table 2D - 341 Check DataType
0x6AD94 1D   31      f32  2.847e-39 6.84e-40  0x7721C  Table 2D - 342 Check DataType
0x6ADA0 1D   31      f32  2.847e-39 6.843e-40 0x77314  Table 2D - 343 Check DataType
0x6ADAC 1D   31      f32  8.265e-40 6.847e-40 0x7740C  Table 2D - 344 Check DataType
0x6ADB8 2D   9x5     f32  9.184e-40 6.85e-40  0x774C0  Table 3D - 111_
0x6ADCC 2D   10x5    f32  1.837e-40 6.853e-40 0x775B0  Table 3D - 112_
0x6ADE0 2D   2x5     f32  1.837e-40 6.854e-40 0x77694  Table 3D - 113_
0x6ADF4 2D   2x5     f32  8.265e-40 6.855e-40 0x776D8  Table 3D - 114_
0x6AE08 2D   9x5     f32  4.592e-40 6.859e-40 0x77738  Table 3D - 115_
0x6AE1C 2D   5x5     f32  9.327e-41 6.862e-40 0x77814  Table 3D - 116_
0x6AE58 1D   9       f32  7.361e-40 6.865e-40 0x77920  Table 2D - 345 Check DataType
0x6AE64 1D   8       u8   0.01      0         0x779D8  Table 2D - 166_
0x6AE78 1D   7       u16  0.01      0         0x779FC  Table 2D - 167_
0x6AE8C 1D   7       u16  0.01      0         0x77A28  Table 2D - 168_
0x6AEA0 2D   11x11   u8   0.003906  0.75      0x77A9C  Table 3D - 64_
0x6AEF4 1D   4       u16  0.0001    0         0x77B44  Table 2D - 169_
0x6AF08 1D   17      u16  0.0001    0         0x77B90  Table 2D - 170_
0x6AF1C 2D   17x20   u16  0.003906  0         0x77C48  Estimated Manifold Pressure
0x6AF38 2D   17x9    u16  1         0         0x77F58  Injector Latency Secondary
0x6AF54 2D   17x9    u16  1         0         0x780F4  Injector Latency Primary
0x6AF70 1D   6       u8   0.007812  0         0x7829C  Table 2D - 171_
0x6AF84 1D   5       u8   0.007812  0         0x782B8  Table 2D - 172_
0x6AFAC 1D   3       u8   0.007812  0         0x782D4  Table 2D - 174_
0x6AFC0 1D   3       f32  1.105e-39 6.898e-40 0x782E4  Table 2D - 346 Check DataType
0x6AFCC 1D   12      u16  5         0         0x78318  Table 2D - 175_
0x6AFE0 1D   13      u16  5         0         0x78364  Table 2D - 176_
0x6AFF4 1D   17      u8   0.01      0         0x7845C  Table 2D - 177_
0x6B008 1D   8       u8   0.007812  0         0x78490  Table 2D - 178_
0x6B01C 1D   9       f32  2.755e-40 6.905e-40 0x784BC  Table 2D - 347 Check DataType
0x6B028 1D   3       f32  2.755e-40 6.905e-40 0x784D4  Table 2D - 348 Check DataType
0x6B034 1D   3       f32  8.265e-40 6.905e-40 0x784E4  Table 2D - 349 Check DataType
0x6B040 1D   9       f32  8.28e-40  6.906e-40 0x7850C  Table 2D - 350 Check DataType
0x6B04C 1D   9       u8   0.003906  0         0x7853C  Table 2D - 179_
0x6B060 1D   9       u8   0.003906  0         0x7856C  Table 2D - 180_
0x6B074 1D   9       u16  3.052e-05 0         0x7859C  Table 2D - 181_
0x6B088 1D   17      u16  0.007812  0         0x785F4  Table 2D - 182_
0x6B09C 1D   9       u16  1         0         0x7863C  Table 2D - 183_
0x6B0B0 2D   18x20   u16  1.526e-05 0.75      0x786E8  Engine Load Compensation
0x6B0CC 1D   12      u8   0.01      0         0x78A00  Table 2D - 184_
0x6B0E0 1D   9       u8   0.01      0         0x78A30  Table 2D - 185_
0x6B0F4 1D   12      u8   0.01      0         0x78A6C  Table 2D - 186_
0x6B108 1D   9       u8   0.01      0         0x78A9C  Table 2D - 187_
0x6B11C 1D   12      u8   0.01      0         0x78AD8  Table 2D - 188_
0x6B130 1D   9       u8   0.01      0         0x78B08  Table 2D - 189_
0x6B144 1D   9       u8   0.01      0         0x78B38  Table 2D - 190_
0x6B158 1D   9       u8   0.01      0         0x78B68  Table 2D - 191_
0x6B180 1D   12      u16  0.01      0         0x78BE8  Table 2D - 193_
0x6B194 1D   7       u8   0.01      0         0x78C68  Table 2D - 194_
0x6B1BC 1D   7       f32  8.294e-40 6.936e-40 0x78C94  Table 2D - 351 Check DataType
0x6B1C8 1D   9       u16  0.001     0         0x78DC0  Table 2D - 196_
0x6B1DC 1D   9       u16  0.001     0         0x78DF8  Table 2D - 197_
0x6B1F0 1D   9       f32  5.51e-40  6.942e-40 0x78F00  Table 2D - 352 Check DataType
0x6B1FC 1D   6       f32  5.51e-40  6.942e-40 0x78F24  Table 2D - 353 Check DataType
0x6B208 1D   6       f32  1.01e-39  6.943e-40 0x78F44  Table 2D - 354 Check DataType
0x6B214 1D   11      f32  2.784e-40 6.943e-40 0x78F78  Table 2D - 355 Check DataType
0x6B220 1D   3       u16  0.001     0         0x78F90  Table 2D - 198_
0x6B234 1D   6       f32  5.51e-40  6.944e-40 0x78FB0  Table 2D - 356 Check DataType
0x6B240 1D   6       f32  5.51e-40  6.945e-40 0x78FD4  Table 2D - 357 Check DataType
0x6B24C 1D   6       f32  2.755e-40 6.945e-40 0x79004  Table 2D - 358 Check DataType
0x6B258 1D   3       f32  1.745e-39 6.946e-40 0x79028  Table 2D - 359 Check DataType
0x6B264 2D   19x17   f32  1.745e-39 6.952e-40 0x790C4  Oil Metering By Load
0x6B278 2D   19x4    f32  5.51e-40  6.955e-40 0x79264  Oil Metering By Throttle
0x6B28C 2D   6x5     f32  9.198e-40 6.956e-40 0x792DC  Table 3D - 119_
0x6B2A0 1D   10      u8   0.01562   0         0x79334  Table 2D - 199_
0x6B2B4 2D   16x3    u8   0.01      0         0x7938C  Table 3D - 71_
0x6B2D0 2D   5x5     u8   0.01      0         0x793E4  Table 3D - 72_
0x6B2EC 2D   7x6     u8   0.01      0         0x79434  Table 3D - 73_
0x6B308 1D   16      u16  1e-05     0         0x794B0  Table 2D - 200_
0x6B31C 1D   16      u16  1e-05     0         0x79510  Table 2D - 201_
0x6B330 2D   16x5    u8   0.003906  0         0x79584  Table 3D - 74_
0x6B34C 2D   16x5    u8   0.003906  0         0x79628  Table 3D - 75_
0x6B368 1D   11      u8   1         -100      0x796E8  Table 2D - 202_
0x6B37C 1D   13      u16  0.05      -100      0x79728  Table 2D - 203_
0x6B390 1D   8       u8   0.02      0         0x79790  Table 2D - 204_
0x6B3A4 1D   12      u8   1         0         0x797C8  Table 2D - 205_
0x6B3B8 1D   16      u16  0.0009766 0         0x79814  Table 2D - 206_
0x6B3CC 1D   5       u8   0.5       -64       0x798B8  Table 2D - 207_
0x6B3E0 1D   4       u8   0.5       -64       0x798D0  Table 2D - 208_
0x6B3F4 1D   5       u8   0.5       -64       0x798E8  Table 2D - 209_
0x6B408 1D   12      u8   0.5       -64       0x79920  Table 2D - 210_
0x6B41C 1D   12      u8   0.5       -64       0x7995C  Table 2D - 211_
0x6B430 1D   8       u8   0.05      0         0x799A0  Table 2D - 212_
0x6B444 1D   4       u16  1e-05     0         0x799B8  Table 2D - 213_
0x6B458 1D   14      u16  1e-05     0         0x799F8  Table 2D - 214_
0x6B46C 1D   2       u16  1e-05     0         0x79A1C  Table 2D - 215_
0x6B480 2D   6x7     u16  0.0009766 0         0x79A54  Table 3D - 76_
0x6B49C 2D   4x7     u16  0.0009766 0         0x79AD4  Table 3D - 77_
0x6B4B8 2D   8x7     u16  0.0009766 0         0x79B48  Table 3D - 78_
0x6B4D4 1D   10      u8   0.05      0         0x79C18  Table 2D - 216_
0x6B4E8 1D   9       u8   0.05      0         0x79C48  Table 2D - 217_
0x6B4FC 1D   8       u8   0.05      0         0x79C74  Table 2D - 218_
0x6B510 1D   14      u16  1e-05     0         0x79CB4  Table 2D - 219_
0x6B524 1D   14      u16  1e-05     0         0x79D08  Table 2D - 220_
0x6B538 1D   14      u16  1e-05     0         0x79D5C  Table 2D - 221_
0x6B54C 2D   6x7     u16  0.0004883 0         0x79DAC  Table 3D - 79_
0x6B568 2D   5x7     u16  0.0004883 0         0x79E30  Table 3D - 80_
0x6B584 2D   6x7     u16  0.0004883 0         0x79EAC  Table 3D - 81_
0x6B5A0 2D   5x6     u16  0.0004883 0         0x79F2C  Table 3D - 82_
0x6B5BC 2D   5x6     u16  0.0004883 0         0x79F94  Table 3D - 83_
0x6B5D8 1D   18      u16  3.052e-05 0         0x7A070  Table 2D - 222_
0x6B5EC 1D   8       u16  3.052e-05 0         0x7A0B4  Table 2D - 223_
0x6B600 1D   8       u16  3.052e-05 0         0x7A0E4  Table 2D - 224_
0x6B614 1D   9       u16  1.526e-06 -0.05     0x7A118  Table 2D - 225_
0x6B628 1D   9       u16  1.526e-06 -0.05     0x7A150  Table 2D - 226_
0x6B650 1D   14      f32  1.286e-39 7.016e-40 0x7A38C  Knock Related 1
0x6B65C 1D   14      f32  9.184e-41 7.017e-40 0x7A3E0  Knock Related 2
0x6B680 2D   6x11    u8   0.05      0         0x7A450  Knock Rel #4
0x6B69C 2D   6x11    u8   0.05      0         0x7A4D8  Knock Rel #0
0x6B6B8 1D   7       u8   0.001     0         0x7A554  Table 2D - 228_
0x6B6CC 1D   12      u16  1.526e-06 0         0x7A58C  Table 2D - 229_
0x6B6E0 1D   10      u16  0.0002441 0         0x7A628  Airflow Or Load Related
0x6B6F4 1D   8       u16  0.7812    0         0x7A65C  MAF Related
0x6B708 1D   11      u16  0.02441   0         0x7A698  Table 2D - 232_
0x6B71C 1D   11      u16  0.02441   0         0x7A6DC  Table 2D - 233_
0x6B730 1D   11      u16  0.02441   0         0x7A720  Table 2D - 234_
0x6B744 1D   11      f32  9.184e-40 7.029e-40 0x7A764  Table 2D - 364 Check DataType
0x6B750 1D   10      f32  8.265e-40 7.178e-40 0x7A7A4  Table 2D - 365 Check DataType
0x6B75C 1D   9       f32  7.347e-40 7.178e-40 0x7D0F4  Table 2D - 366 Check DataType
0x6B768 2D   8x10    f32  7.347e-40 7.18e-40  0x7D150  Table 3D - 120_
0x6B77C 2D   8x10    f32  7.376e-40 7.183e-40 0x7D1E8  Table 3D - 121_
0x6B790 1D   8       u16  3.052e-05 0         0x7D274  Table 2D - 235_
0x6B7A4 1D   9       u16  3.052e-07 0         0x7D2E0  Table 2D - 236_
0x6B7B8 1D   9       u16  3.052e-07 0         0x7D318  Table 2D - 237_
0x6B7CC 1D   9       u16  3.052e-07 0         0x7D350  Table 2D - 238_
0x6B7E0 1D   9       u16  3.052e-07 0         0x7D388  Table 2D - 239_
0x6B7F4 1D   9       u16  3.052e-07 0         0x7D3C0  Table 2D - 240_
0x6B808 1D   9       u16  3.052e-07 0         0x7D3F8  Table 2D - 241_
0x6B81C 1D   9       u16  3.052e-07 0         0x7D430  Table 2D - 242_
0x6B830 1D   9       u16  3.052e-07 0         0x7D468  Table 2D - 243_
0x6B844 1D   9       f32  8.265e-40 7.192e-40 0x7D4A0  Table 2D - 367 Check DataType
0x6B850 1D   9       f32  1.472e-39 7.192e-40 0x7D4D8  Table 2D - 368 Check DataType
0x6B85C 1D   16      u16  3.052e-05 0         0x7D52C  Table 2D - 244_
0x6B870 1D   9       u8   0.7812    0         0x7D578  Table 2D - 245_
0x6B884 1D   16      u16  3.052e-05 0         0x7D5C4  Table 2D - 246_
0x6B898 1D   9       u16  3.052e-06 0         0x7D608  Table 2D - 247_
0x6B8AC 1D   9       u16  3.052e-06 0         0x7D640  Table 2D - 248_
0x6B8C0 1D   9       f32  8.265e-40 7.198e-40 0x7D678  Table 2D - 369 Check DataType
0x6B8CC 1D   9       f32  9.198e-40 7.2e-40   0x7D6B0  Table 2D - 370 Check DataType
0x6B8D8 1D   10      u8   0.3906    0         0x7D728  Table 2D - 249_
0x6B8EC 1D   9       f32  7.376e-40 7.201e-40 0x7D770  Table 2D - 371 Check DataType
0x6B8F8 1D   8       u16  3.052e-06 0         0x7D79C  Table 2D - 250_
0x6B90C 1D   8       u16  3.052e-06 0         0x7D7CC  Table 2D - 251_
0x6B920 1D   9       u16  3.052e-06 -0.05     0x7D81C  Table 2D - 252_
0x6B934 1D   9       u16  3.052e-06 -0.05     0x7D854  Table 2D - 253_
0x6B948 1D   9       f32  8.265e-40 7.206e-40 0x7D89C  Table 2D - 372 Check DataType
0x6B954 1D   9       f32  8.265e-40 7.207e-40 0x7D8E4  Table 2D - 373 Check DataType
0x6B960 1D   9       f32  9.198e-40 7.03e-40  0x7D92C  Table 2D - 374 Check DataType
0x6B96C 1D   10      u8   0.003906  0         0x7A7F0  Table 2D - 254_
0x6B980 1D   4       u8   0.7812    0         0x7A80C  Table 2D - 255_
0x6B994 2D   6x4     u16  0.0002441 0         0x7A838  Table 3D - 86_
0x6B9B0 1D   7       f32  6.457e-40 7.034e-40 0x7A8CC  Table 2D - 375 Check DataType
0x6B9BC 1D   7       u16  0.625     -40       0x7A8F8  Table 2D - 256_
0x6B9D0 1D   9       u8   0.5       -50       0x7A9F8  Table 2D - 257_
0x6B9E4 1D   9       u8   0.5       -50       0x7AA28  Table 2D - 258_
0x6B9F8 2D   9x9     f32  8.265e-40 7.042e-40 0x7AABC  Table 3D - 122_
0x6BA0C 2D   9x9     f32  8.265e-40 7.045e-40 0x7AB58  Table 3D - 123_
0x6BA20 2D   9x9     u16  0.0001526 0         0x7AC44  Table 3D - 87_
0x6BA3C 2D   9x9     u16  0.0001526 0         0x7AD30  Table 3D - 88_
0x6BA90 1D   18      u8   0.007812  0         0x7AE7C  Table 2D - 259_
0x6BABC 1D   9       u8   1         -50       0x7AF48  Injection Angle Related AFR Input
0x6BAD0 1D   8       u8   0.1       0         0x7AF74  Unknown Lambda Input
0x6BAE4 1D   8       u8   0.1       0         0x7AF9C  Table 2D - 262_
0x6BAF8 1D   25      u16  0.001     0         0x7B008  AirFlow Inj Angle Related
0x6BB0C 1D   8       u16  0.001     0         0x7B05C  Table 2D - 264_
0x6BB20 1D   25      u16  0.001     0         0x7B0D0  Table 2D - 265_
0x6BB34 1D   25      u16  0.001     0         0x7B168  Table 2D - 266_
0x6BB48 1D   8       u16  0.001     0         0x7B1BC  Table 2D - 267_
0x6BB5C 1D   14      u16  0.0001    0         0x7B204  Table 2D - 268_
0x6BB70 1D   8       u16  0.0001    0         0x7B240  Table 2D - 269_
0x6BB84 2D   18x8    u16  1         -50       0x7B2B8  Injection Angle
0x6BBA0 1D   10      u16  0.0002441 0         0x7B55A  Table 2D - 270_
0x6BBB4 1D   10      u8   0.0625    0         0x7B464  Table 2D - 271_
0x6BBC8 1D   12      u8   0.01      0         0x7B4A0  Table 2D - 272_
0x6BBDC 1D   11      u8   0.5       0         0x7B4D8  Table 2D - 273_
0x6BBF0 1D   11      u8   0.5       0         0x7B510  Table 2D - 274_
0x6BC04 1D   6       u8   0.1       0         0x7B534  Table 2D - 275_
0x6BC18 1D   6       u8   0.1       0         0x7B554  Table 2D - 276_
0x6BC2C 2D   7x4     u16  0.01      0         0x7B59C  Table 3D - 92_
0x6BC48 2D   7x4     u16  0.01      0         0x7B600  Table 3D - 93_
0x6BC64 2D   7x4     u16  0.01      0         0x7B664  Table 3D - 94_
0x6BC80 2D   7x4     u16  0.01      0         0x7B6C8  Table 3D - 95_
0x6BC9C 2D   7x4     u16  0.01      0         0x7B72C  Table 3D - 96_
0x6BCB8 2D   10x8    u16  6.104e-05 -2        0x7B7AC  Table 3D - 97_
0x6BCD4 2D   10x8    u16  6.104e-05 -2        0x7B894  Table 3D - 98_
0x6BCF0 2D   10x8    u16  6.104e-05 -2        0x7B97C  Table 3D - 99_
0x6BD0C 1D   7       f32  4.592e-40 7.099e-40 0x7BAB0  Table 2D - 378 Check DataType
0x6BD18 1D   5       f32  8.265e-40 7.099e-40 0x7BAE0  Table 2D - 379 Check DataType
0x6BD24 2D   9x9     f32  8.265e-40 7.101e-40 0x7BB3C  Table 3D - 124_
0x6BD38 2D   9x9     f32  9.184e-40 7.107e-40 0x7BBD8  Table 3D - 125_
0x6BD4C 2D   10x17   f32  1.195e-39 7.118e-40 0x7BD94  Table 3D - 126_
0x6BD60 1D   13      u8   0.007812  0         0x7C084  Table 2D - 277_
0x6BD74 2D   10x8    f32  1.102e-39 7.123e-40 0x7C0DC  Table 3D - 127_
0x6BD88 1D   12      f32  1.102e-39 7.124e-40 0x7C1B4  Load Limit A
0x6BD94 1D   12      f32  9.212e-40 7.129e-40 0x7C214  Load Limit B
0x6BDA0 1D   10      u16  0.001     0         0x7C354  Load Limit C
0x6BDB4 1D   4       f32  3.673e-40 7.131e-40 0x7C3C4  Table 2D - 382 Check DataType
0x6BDC0 1D   4       f32  3.673e-40 7.131e-40 0x7C3DC  Table 2D - 383 Check DataType
0x6BDCC 1D   4       f32  9.198e-40 7.134e-40 0x7C3F4  Table 2D - 384 Check DataType
0x6BDD8 1D   10      u8   0.003906  0         0x7C4B4  Table 2D - 279_
0x6BDEC 1D   10      u8   1         0         0x7C4E8  Table 2D - 280_
0x6BE00 1D   10      u8   0.5       0         0x7C51C  Table 2D - 281_
0x6BE14 1D   10      f32  8.265e-40 7.137e-40 0x7C550  Table 2D - 385 Check DataType
0x6BE20 1D   9       f32  8.265e-40 7.139e-40 0x7C588  Table 2D - 386 Check DataType
0x6BE2C 1D   9       f32  4.592e-40 7.14e-40  0x7C61C  Table 2D - 387 Check DataType
0x6BE38 1D   5       f32  4.592e-40 7.141e-40 0x7C678  Table 2D - 388 Check DataType
0x6BE44 1D   5       f32  6.443e-40 7.141e-40 0x7C6A0  Table 2D - 389 Check DataType
0x6BE50 1D   7       u8   0.003906  0         0x7C6D8  Table 2D - 282_
0x6BE64 1D   10      u8   0.01      0         0x7C708  Table 2D - 283_
0x6BE78 1D   6       f32  5.539e-40 7.143e-40 0x7C730  Table 2D - 390 Check DataType
0x6BE84 1D   6       u16  1.526e-05 0         0x7C750  Table 2D - 284_
0x6BE98 1D   9       u16  0.003906  0         0x7C780  Table 2D - 285_
0x6BEAC 2D   9x6     u8   0.003906  0         0x7C7D0  Table 3D - 100_
0x6BEC8 2D   9x6     u8   0.003906  0         0x7C844  Table 3D - 101_
0x6BEE4 1D   15      u8   0.007812  0         0x7C8EC  Table 2D - 286_
0x6BEF8 1D   9       u8   0.7812    -100      0x7C920  Table 2D - 287_
0x6BF0C 2D   24x10   u8   0.3906    0         0x7C9B4  Table 3D - 102_
0x6BF28 2D   9x9     f32  9.184e-40 7.163e-40 0x7CB20  Ignition Dwell Time_
0x6BF3C 1D   10      f32  9.184e-40 7.164e-40 0x7CCDC  Table 2D - 391 Check DataType
0x6BF48 1D   10      f32  9.184e-40 7.165e-40 0x7CD2C  Table 2D - 392 Check DataType
0x6BF54 1D   10      f32  9.184e-40 7.166e-40 0x7CD7C  Table 2D - 393 Check DataType
0x6BF60 1D   10      f32  9.184e-40 7.167e-40 0x7CDCC  Table 2D - 394 Check DataType
0x6BF6C 1D   10      f32  9.184e-40 7.168e-40 0x7CE1C  Table 2D - 395 Check DataType
0x6BF78 1D   10      f32  9.184e-40 7.17e-40  0x7CE6C  Table 2D - 396 Check DataType
0x6BF84 1D   10      f32  9.184e-40 7.171e-40 0x7CEBC  Table 2D - 397 Check DataType
0x6BF90 1D   10      f32  9.184e-40 7.172e-40 0x7CF0C  Table 2D - 398 Check DataType
0x6BF9C 1D   10      f32  9.184e-40 7.173e-40 0x7CF5C  Table 2D - 399 Check DataType
0x6BFA8 1D   10      f32  9.184e-40 7.174e-40 0x7CFAC  Table 2D - 400 Check DataType
0x6BFB4 1D   10      f32  9.184e-40 7.175e-40 0x7CFFC  Table 2D - 401 Check DataType
0x6BFC0 1D   10      f32  9.184e-40 7.176e-40 0x7D04C  Table 2D - 402 Check DataType
```
