# Cross-validation: seed/key implementation vs community (MazdA / LFSR 0xc541a9)

<!-- IN PROGRESS -->

Status: IN PROGRESS (checkpoint shell committed before analysis).

Purpose: cross-validate our VERIFIED seed/key implementation
(`lfsr_clock`, `seed_gen`, `seed_key_related` in `c/`) against:

1. the community implementation in ConnorRigby/rx8-ecu-dump
   (3-byte seed, subfunc 0x01/0x02, key "MazdA", LFSR 24-bit state 0xc541a9,
   NRC {0x22, 0x35, 0x36});
2. the live rnd-ash capture `27 01 -> 67 01 46 4E 7F` (seed 0x464E7F).

Filled in by steps 1-5 of the task shell.
