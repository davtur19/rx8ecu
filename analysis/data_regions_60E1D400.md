# Data regions in code window 0x800..0x60000 — 60E1D400

Classifies every `.word` run (>=2 contiguous `.word` lines) in the
code window of `src/60E1D400_annotated.s`. Addresses are ROM byte
offsets (the `.s` maps linearly from ROM offset 0; verified: 0 label
mismatches against `L_xxxxxx` embedded addresses).

## Method

- Run definition: address-adjacent `.word` lines (labels do not split a
  run; a label is just a marker on data). 1491 runs (4736 words) inside
  the window. Note: the task brief quoted 21,778 runs — that count is not
  reproducible with any run definition here (whole-file counts: 2193 merged
  runs >=2 / 2797 line-consecutive runs >=2 / 11052 merged runs of any
  size, i.e. incl. single `.word` lines).
- Priority: string > calibration > jump_table > literal_pool > padding
  > capstone-check > unknown_data. Deviations (documented): uniform
  all-zero/all-0xFFFF runs are padding even if a stray pcrel ref lands in
  them; 0x00xx/0xFFxx partial-pattern padding requires the run to be
  *unreferenced* (a referenced 0x00xx run is a constant table, not filler).
- Calibration used `cal_tables.csv` (1210 entries).
- Capstone CS_ARCH_SH / CS_MODE_SH2, big-endian. NOTE: capstone's SH-2
  decoder is a strict subset of the .s decoder (fails on common opcodes
  such as 0x0000, 0x0100, 0x0400, 0xffff), so 'undecoded_code_capstone'
  is only assigned for runs capstone can decode into a code-like sequence.

## Per-class stats

| class | runs | words |
|---|---|---|
| string | 3 | 7 |
| calibration | 0 | 0 |
| jump_table | 18 | 112 |
| literal_pool | 883 | 2288 |
| padding | 366 | 1540 |
| undecoded_code_capstone | 0 | 0 |
| unknown_data | 221 | 789 |

Total runs: 1491, total words: 4736

## undecoded_code_capstone (address + capstone mnemonics)

**None.** No `.word` run in the window decodes (via capstone SH-2) into a
plausible code sequence. Cross-check: capstone was run over all 1491
runs; zero code-like sequences found. The `.s` decode is authoritative
(IDA-derived; 0 label mismatches) and the window is 100% covered
(93.6% instruction bytes + 6.4% `.word` bytes), so no code is missing:
every run is data (pool / table / padding / string). Capstone adds no
coverage here because its SH-2 decoder is a strict subset of the .s
decoder (it fails common opcodes the .s already lifted).

## Examples per class (first 5 each)

- literal_pool: 0x000870-0x00087a (5 words) pcrel refs 3/5 words (mov.lx2+mov.wx1)
- padding: 0x0008ae-0x0008b2 (2 words) all-0xFFFF filler (stray pcrel ref x1)
- literal_pool: 0x0009b0-0x0009b6 (3 words) pcrel refs 2/3 words (mov.lx2)
- padding: 0x000b0e-0x000fe0 (617 words) all-0xFFFF filler (stray pcrel ref x3)
- unknown_data: 0x000fea-0x000ff8 (7 words) 
- padding: 0x000ffe-0x001002 (2 words) all-zero word filler
- literal_pool: 0x001034-0x001038 (2 words) pcrel refs 1/2 words (mov.lx1)
- literal_pool: 0x00109a-0x00109e (2 words) pcrel refs 1/2 words (mov.lx1)
- literal_pool: 0x0010a6-0x0010aa (2 words) pcrel refs 1/2 words (mov.lx1)
- padding: 0x00129e-0x0012a2 (2 words) all-0xFFFF filler (stray pcrel ref x1)
- padding: 0x00170e-0x001712 (2 words) all-0xFFFF filler (stray pcrel ref x1)
- unknown_data: 0x001fc2-0x002000 (31 words) 
- string: 0x002002-0x002006 (2 words) ascii "E1D4" (span 32B)
- string: 0x002028-0x00202e (3 words) ascii "DENSO2" (span 16B)
- unknown_data: 0x0033b8-0x0033bc (2 words) 
- string: 0x003b32-0x003b36 (2 words) ascii "1999" (span 202B)
- unknown_data: 0x003bee-0x003bf4 (3 words) 
- jump_table: 0x00426c-0x00428e (17 words) 32-bit absolute x8 (pairing+0, targets in-window code) indirect access (base loaded via pool/mova)
- jump_table: 0x004290-0x0042aa (13 words) 32-bit absolute x6 (pairing+0, targets in-window code) indirect access (base loaded via pool/mova)
- jump_table: 0x004324-0x00432c (4 words) 32-bit absolute x2 (pairing+0, targets in-window code) pcrel@0x4324:mov.l,0x4328:mov.l
- jump_table: 0x0043f8-0x004404 (6 words) 32-bit absolute x3 (pairing+0, targets in-window code) pcrel@0x43f8:mov.l,0x43fc:mov.l,0x4400:mov.l
- jump_table: 0x004728-0x004734 (6 words) 32-bit absolute x3 (pairing+0, targets in-window code) pcrel@0x4728:mov.l,0x472c:mov.l,0x4730:mov.l
- unknown_data: 0x00493c-0x004996 (45 words) 

## Cross-checks

- 0 label mismatches (walker vs `L_xxxxxx` addresses).
- Window coverage: 100.0% (365,938 instruction bytes + 25,230 `.word` bytes of 0x5F800).
- cal_tables.csv: 1210 entries, all at 0x6CF6C..0x7D92C — **none inside the
  code window**, so calibration = 0 runs (as expected: window is code).
- string check validated against known string at 0x6CE00 ('N3J1E_3W.T50',
  big-endian packed ASCII; outside the window, used only as a unit test).
- No genuine 16-bit (braf-style) switch tables exist in the window: all 4
  `braf r0` sites in the .s sit inside mis-decoded data regions; dispatch
  here is done with 32-bit `mov.l` tables + `jmp @rN`.
- Known mis-decoded-data regions (the .s decoded data as instructions —
  relevant to the disassembler-fix agent, but NOT `.word` runs):
  0x84E-0x8A4, 0x85BA-0x8600, 0x8704-0x8730, 0x883C-0x8850 (alternating
  garbage instruction + `.word 0x0000` = 32-bit data), 0x3C8E0-0x3C91C
  (32-bit pointer table into 0x7A9xx calibration region), 0x4224-0x4226
  pool holds the 0x426C dispatch table base (div emulation).
- Notable: 0x426C/0x4290 are genuine dispatch tables (div-trampoline
  `mov.l @(r0,r3),r3; jmp @r3`); 0x493C is a Renesas-style div-library
  16-bit constant table (0x0013/0xFFFF header + 19x (0x0000,0x0001));
  0x2000 region holds the '60E1D400' ROM-id and 'Copr.DENSO200' strings.

