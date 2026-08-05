# MANIFEST — RX-8 ECU reverse-engineering public release

Every file shipped in this repository, with sha256, size, purpose, and its source path
in the working repository. **1827 entries, 71.8M.** Regenerated 2026-08-02 for the
9-ROM public tree; see roms/ROMS.md).

## Summary

| Area | Files | Bytes |
|------|------:|------:|
| (root) | 11 | 302.2K |
| roms/ | 10 | 4.5M |
| src/ | 10 | 39.6M |
| symbols/ | 31 | 9.1M |
| c/ | 440 | 1.1M |
| c/tests/ | 481 | 2.2M |
| tools/ | 27 | 393.7K |
| tools/tests/ | 3 | 52.0K |
| docs/ | 228 | 875.9K |
| hardware/ | 1 | 2.0K |
| web/ | 11 | 874.9K |
| analysis/ | 40 | 9.4M |
| .github/ | 4 | 18.2K |
| reconstructed/experiments/match/ | 66 | 215.5K |
| reconstructed/samples/ | 464 | 3.3M |
| **Total** | **1827** | 71.8M |

## External dependencies

The repo is self-contained except for:

| Dependency | Version | Notes |
|------------|---------|-------|
| Python 3 | >= 3.8 (tested 3.14) | `python3` on PATH |
| capstone | >= 5.0 | `python3 -m pip install capstone --break-system-packages` (SH-2 disassembly) |
| sh-elf binutils | 2.46 | SHIPPED at `tools/toolchain/usr/bin`; re-install via `./tools/get_toolchain.sh` |
| cc (host C compiler) | any | only for `make c-test` (host-side tests) |

No other runtime dependencies. The repo does NOT ship tuned/private ROM images,
Ghidra/IDA project files (`.gar`, `.i64`), other binaries, the toolchain source,
or the toolchain install (git-ignored; re-create with
`./tools/get_toolchain.sh`).

## Notes on adapted files

- Path resolution in `c/tests/*.py`, `tools/tests/*.py` and the tools was rewritten to
  the public layout (`tools/` for `sh2emu.py`/`disasm_sh2e.py`, `roms/stock/` for ROMs,
  `symbols/` for symbol tables, `analysis/` for data regions). All suites re-verified
  green in this tree (see VERIFICATION.md).
- The 9 annotated `.s` files regenerate byte-identical with `make src` (verified).
- `tools/toolchain/` (sh-elf binutils 2.46) is git-ignored but ships in the working tree
  at `tools/toolchain/usr/bin`; `./tools/get_toolchain.sh` re-creates it idempotently.
- `src/*.bin`, `*.elf`, `*.o` build intermediates (e.g. from `make src`) are git-ignored;
  `make clean` removes them. Only the 9 `src/*_annotated.s` sources ship.
- `reconstructed/` is fully inventoried (no longer excluded): compiler-match experiments
  (C sources, expected GCC sh-elf output, ROM hex, sweep scripts) under
  `reconstructed/experiments/match`, and readable reconstructed-source C samples with
  Python harnesses + host oracles under `reconstructed/samples`.

## (root)

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `.gitattributes` | `c7df56f888be333371da8b3a0f15ab946b7dd0e5d751e0a120a9613367b45ab6` | 307B | Git attributes: binary-file handling (no line-ending/diff mangling) |
| `.gitignore` | `6069539f06ee271715f3f74cd36acdde563ba14fcb757af33b2f967008697756` | 328B | Git ignore rules (build artifacts, toolchain, private/local data) |
| `AGENTS.md` | `62ccd8df7b46f9e0cffe0476bcee6c69df210c0e2594c01b17e03b82c328ca4a` | 3.4K | Agent working instructions |
| `CREDITS.md` | `128a69963eb255942855e0f26a337da214c4990bde99fb22599a1db299408a46` | 4.7K | Credits: equinox311 + defs source attribution |
| `LICENSE` | `d8a6cc31abc16b6748c7a21f21611f5a1ec33f67d22ca23d7da1c19b95496bee` | 33.2K | License (GNU AGPL v3) |
| `MANIFEST.md` | `--` | -- | This inventory (self-referential; verify with `sha256sum MANIFEST.md`) |
| `Makefile` | `2c97652d749a120a67799d6dbedd33326da98867c84945e2c701fd838906b888` | 7.2K | Build: verify-all / verify / src / c-test / c-emu / clean |
| `PLANS.md` | `a15102a5fdc787f56ca2b1230a981b9ece998ad3f564b8f259bb6719c6b20e46` | 9.7K | Master plan (single source of truth) |
| `README.md` | `dab848e2f8a1977ff08d269c5f49a539493e761a987d0189d7f0fed823b6e3e2` | 10.4K | Project README |
| `REPLICATION.md` | `83c8ed09e1d59b0d3d4436718315d4648f723fb1324d5083ef86b63dbde68ee7` | 7.4K | Fresh-clone reproduction guide |
| `VERIFICATION.md` | `84272372890ce56be9519a6e0a60abeeb8781d92e2331c737ce7d6368335446e` | 9.2K | Evidence: byte-exact table, coverage, test results, hashes |

## roms

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `roms/ROMS.md` | `fdd52e344b0b10b903e7fa9a0b00b60c58c3c115974d7278a926b50ec22f4bd0` | 6.2K | ROM catalog: cal IDs, SW modules, keys, checksums, hashes |
| `roms/stock/60E0E500.bin` | `c05dfd0422b2b773027a22dcce2c24923969f27b94634bfcbdb44d6157087e11` | 512.0K | Stock ROM image (512 KB, SH-2E, Denso checksum valid) |
| `roms/stock/60E0E700_N3YLEE.bin` | `bba52346a076c35ded281c14b7ff81fcfa6c6e8119b6ec544048e269b0c53dc0` | 512.0K | Stock ROM image (512 KB, SH-2E, Denso checksum valid) |
| `roms/stock/60E0FB00.bin` | `3d32e2591a1170d5ac3feed7ae065c650bde525e56693a5ca7499e6c9eb5f661` | 512.0K | Stock ROM image (512 KB, SH-2E, Denso checksum valid) |
| `roms/stock/60E0FC00.bin` | `476ddcbed4549d89b9835dfbfb1aac48217d943fb53c73f489ffc9414803e35c` | 512.0K | Stock ROM image (512 KB, SH-2E, Denso checksum valid) |
| `roms/stock/60E15120_N3J1E.bin` | `a7cd953c2a87af12ee2814a95c958dc23959d352ef9c5e7f82b8ab8952f264f1` | 512.0K | Stock ROM image (512 KB, SH-2E, Denso checksum valid) |
| `roms/stock/60E1B900.bin` | `b0dc94f96e8eaf6f154df8e7388d12fba490cf2adf13edb077677c4c82b3b1b5` | 512.0K | Stock ROM image (512 KB, SH-2E, Denso checksum valid) |
| `roms/stock/60E1C500_N3J6EB.bin` | `b3b6e1e416826d9c9f51ddc853cae0dea3235a3ddbb260cccd23effc77995c68` | 512.0K | Stock ROM image (512 KB, SH-2E, Denso checksum valid) |
| `roms/stock/60E1D400.bin` | `344cb8b960eb6dde973bdb8e8c3e3e96cac542166cd7158c6f5f24d71eb7af78` | 512.0K | Stock ROM image (512 KB, SH-2E, Denso checksum valid) |
| `roms/stock/60E32000_N3M5E.bin` | `d5406459cc0b19f831a73a021ad2ae47179127097a15cfa323a34bfa47e330de` | 512.0K | Stock ROM image (512 KB, SH-2E, Denso checksum valid) |

## src

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `src/60E0E500_annotated.s` | `5a8df4f332242f38e9c6cdfeff69e239c5cf5d8b5eb867d96e1ae8ec46c61d49` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E0E700_N3YLEE_annotated.s` | `d5df4a9139f85b372591291bf224d731d0a8279d16c5d8d769140d1b8d901740` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E0FB00_annotated.s` | `de00b533d782ab1c037fb910124808359a20235226822d1a9d77692df2b817ee` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E0FC00_annotated.s` | `3314550f460f37505083d962a66b1a5042a7943188094ffc3ed6ed513dc757fe` | 4.2M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E15120_N3J1E_annotated.s` | `ed3244841d57a75e0b68f6f2566f723c8a0778c757b1220f6405bf8d3bcaa76f` | 4.5M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E1B900_annotated.s` | `d8386e03a0a5556abdcc1bcf5c546ed576df3dd41fb7febce37dc088e19ff380` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E1C500_N3J6EB_annotated.s` | `e3dd286e99a856434ae6c354fbaaffe004b2a12b53bfca3ff5380aad6d09f8e1` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E1D400_annotated.s` | `9b09ed56c28fddfff4ea6e5272894c6621a71dc43aa571d1d97f13c62cd2599a` | 4.3M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E32000_N3M5E_annotated.s` | `b2b7411e98d703d25ffbe5ac1fd517d3bad7b36ec4c82609af29fcdc4bb0afc1` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/ANNOTATED_SOURCES.md` | `ccca458422a4b904e8ef4481a067672a487a825ca83cf80f9de6f35369cadf2c` | 3.4K | Per-ROM annotated-source notes (coverage, symbols, rebuildability) |

## symbols

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `symbols/CATALOG_MASTER.csv` | `9ae2a99547c04fd5e88cbbf76164056dbd83da2634e262abdca65fd6e972ff68` | 3.1M | Tracked file |
| `symbols/CATALOG_STATUS.md` | `0863b373f668518c570bba7746eb9c64f698103ac813d9702dfdb231a0bc7ae6` | 3.2K | Tracked file |
| `symbols/FUNCTION_CATEGORIES.csv` | `139e4370bf7019d078f19d33211849adb9076c1e8f52f158d63579b5f7e91b00` | 385.0K | Tracked file |
| `symbols/FUNCTION_RENAMES.csv` | `85e77b864a47f72c7b1598d3fc0dae4741ba77142e414784248d2f2506d00b49` | 266.5K | Tracked file |
| `symbols/NAMES_STATUS.md` | `3e95c029188df7488b84cb814972da335a90f6d1d07f4ff6559b493946bcc37f` | 6.7K | Tracked file |
| `symbols/TABLES_STATUS.md` | `8e879ed5482c2c8f9884d33025b3b3a727899b5ac6a997cec2132fc3fd3d2c3b` | 1.6K | Tracked file |
| `symbols/cal_tables.csv` | `73ccd6bd0c223b2dda934ec7a3603dd961b6376e03a9e42209eec1c7762d5432` | 52.6K | Calibration table descriptors (1,210 tables) |
| `symbols/callgraph.csv` | `ec636769141c7a42b666ecbc72e0342c7f08d9244ea97ecb18b76b45366e211e` | 362.9K | Call-graph edge list (caller->callee) |
| `symbols/equinox311_60E0FC00_named.csv` | `f50692d5e2782611e6f70d5069f47e552e26719fdb957d67c20a28984ab576d4` | 64.1K | Tracked file |
| `symbols/romraider_rx8_tables.csv` | `fdbfc7f8afcca7581720166a0db103689847de25aaef944a6972859e94f8a05e` | 2.3M | Tracked file |
| `symbols/symbols_60E0E500.csv` | `781b93c4709b708fb4992b521e634508a59528e543ead7f843370cfe7a8c5226` | 283.4K | Tracked file |
| `symbols/symbols_60E0E500_connor.csv` | `861328adabe0e5610c9c312ad2431e1a1c346b06767c88a8e169bf050dcc0857` | 424B | Tracked file |
| `symbols/symbols_60E0E700.csv` | `74c0d8c0f9562c1f9cb13cb8011d2c46d1659f67befca38d82b8ce714afc0560` | 283.5K | Tracked file |
| `symbols/symbols_60E0E700_connor.csv` | `861328adabe0e5610c9c312ad2431e1a1c346b06767c88a8e169bf050dcc0857` | 424B | Tracked file |
| `symbols/symbols_60E0FB00.csv` | `f2ee37ca39ece163044080556a2d8e0fce52f1c858ed21f39bda83771074ce15` | 279.7K | Tracked file |
| `symbols/symbols_60E0FB00_connor.csv` | `71280cd589bf47ee1da1d49f084bbf73bba717de7b94c61a380cea938f30d011` | 363B | Tracked file |
| `symbols/symbols_60E0FC00.csv` | `a9504503453cbfd4a61639648b1ca074e05a4a2b67c4a9acf2d6bf2808be6aa0` | 167.2K | Function symbol table (per-ROM) |
| `symbols/symbols_60E0FC00_connor.csv` | `32824648b368e71b3b2920bb196f606286068c4fccaa89e90f7253a2e77130db` | 788B | Tracked file |
| `symbols/symbols_60E0FC00_ghidra.csv` | `af985c30f6a05dce6891d962edc8976bda234b55b8235c673e7b9742e5f605aa` | 38.7K | Function symbol table (per-ROM) |
| `symbols/symbols_60E0FC00_merged2.csv` | `1afd354dea0abc3d8614ef7fdd04da540e3a937e0711668a0fc0e5a9fd102934` | 166.6K | Tracked file |
| `symbols/symbols_60E15120.csv` | `c6800b5c929c68cd4ee76810d6e4a047e4b0935b7a776be4a54116c74d2e8c36` | 289.3K | Tracked file |
| `symbols/symbols_60E15120_connor.csv` | `861328adabe0e5610c9c312ad2431e1a1c346b06767c88a8e169bf050dcc0857` | 424B | Tracked file |
| `symbols/symbols_60E1B900.csv` | `d11a902aaa6b6099e72abc2b016f6d0d633992fdbc65d3a239497fd3a3922c74` | 278.7K | Tracked file |
| `symbols/symbols_60E1B900_connor.csv` | `ed5de8ea2c23f6904de1e7f75d84e504aa3969c2993170c4c28407e4bd659ea3` | 727B | Tracked file |
| `symbols/symbols_60E1C500.csv` | `ffc00f7a6c870232c90d7e51577fb8cae5e352ac7acc0a28c77983449007d400` | 283.8K | Tracked file |
| `symbols/symbols_60E1C500_connor.csv` | `ed5de8ea2c23f6904de1e7f75d84e504aa3969c2993170c4c28407e4bd659ea3` | 727B | Tracked file |
| `symbols/symbols_60E1D400_connor.csv` | `b76264faafb564f7fd11cd13c5d57f2950572037050b7ae4f505c1c5b87ea66b` | 1.5K | Tracked file |
| `symbols/symbols_60E1D400_ida.csv` | `f7502fb637eba7c4ac660252f43ad961f100c577b634d6e8b3f467800bb55cb4` | 139.0K | Function symbol table (per-ROM) |
| `symbols/symbols_60E1D400_merged.csv` | `8710dc436ab599fea89b8648fb5d1f97daa4c2ff5d1ad4b341f91bf9444503bf` | 141.1K | Function symbol table (per-ROM) |
| `symbols/symbols_60E32000.csv` | `31e41579bde56ba955ce61ce14f41dc4ea4ae66691dbf74825a9a55b7186a585` | 267.1K | Tracked file |
| `symbols/symbols_60E32000_connor.csv` | `8ebc5dce975b095de8f8617a5d24d21cc64f396532264ded73d3d0c06d43e286` | 727B | Tracked file |

## c

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `c/2DLookup.c` | `77ec8562352bd30232b3d660e03badd06c7018b31f2e4c1772f20e2cd8583ac7` | 10.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/3dLookup.c` | `02b55cb88a5111fb69096314f4c84f546f11209677c95c1a35679fb9ccbfbe5b` | 9.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/CANSetupSomethingDifferentBasedOnBit.c` | `0bff14b29e51727cdc74a48c50c51b805a7db45b0d14325b8122901afb72544e` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/CANSetupSomethingDifferentBasedOnBit_e074.c` | `fc7cc0c1841692833c0f2c9749f14031f63c6204aef9dbf002f4587c54cb6ba6` | 944B | Tracked file |
| `c/DSC_checkIfMode_x10_a_2c5ce.c` | `b35fb9686f435e2c4620ec21e2e53e153b040931e1d4968451c6edfa583f83c4` | 1.4K | Tracked file |
| `c/E2IntoRAM.c` | `fc2325f82277d914cfd53b7c2e00bc462978406b163aaf722698c724356766e5` | 4.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/FUN_00007eca_7eca.c` | `c11e4426452135b12ec48eca0291169d05348647fd1646f4839caac5676d5a53` | 3.7K | Tracked file |
| `c/FUN_00009016_9016.c` | `01869c75bdb870c32d095a5ec1cba312fe576069b18c1c5123251d582b332ca9` | 1.5K | Tracked file |
| `c/FUN_00009f12_9f12.c` | `eba9dcaba472c0cfdb618012554f3ed983e3890497aea6cae47b71df4d6c0b2e` | 878B | Tracked file |
| `c/FUN_0000d2e8_d2e8.c` | `3001540840e5547108900b7ca64347dac9dc3816c388735ceea65cf16bd23b79` | 895B | Tracked file |
| `c/FUN_00010a8c_10a8c.c` | `803b83af7eeb9da21f092689207e2daf4042cbf31e600f370c0b8c41cc06b634` | 1.1K | Tracked file |
| `c/FUN_00019a56_19a56.c` | `81f43bf582e1d264faed94f8c6e8d71137689ec2ebb380a6cdd5315fc143bab0` | 741B | Tracked file |
| `c/FUN_00021730_21730.c` | `e37896b0cfe4547126dbcfcb0b221f05b44b6fed7c5962afe5c24216fcec4992` | 724B | Tracked file |
| `c/FUN_00025b26_25b26.c` | `e2f0a1a29d7bf80129883ff5f0e9b216a775a2cdce7b08b50b4c5cb347167eef` | 705B | Tracked file |
| `c/FUN_00026e14_26e14.c` | `39870fca9c3b6415621df5b6caaa82a09451ce64cd8e81b1e2d598359d266b33` | 718B | Tracked file |
| `c/FUN_00028034_28034.c` | `c08f2f9ab7ce56d72340d4cd2d7ed23da730bf6662f37c33f1c250c8a61b67cf` | 812B | Tracked file |
| `c/FUN_000288fc_288fc.c` | `7c8cda465af3e3f05bf252c553f4d50ab722a9040693fe653f20ed508e997429` | 677B | Tracked file |
| `c/FUN_0002896c_2896c.c` | `284c315e83956127a7e0077ae3b1840ad98e19e25e16f4750ba6854ed2f63fa2` | 738B | Tracked file |
| `c/FUN_000289f8_289f8.c` | `56c929568c464b1d06f39cccb260b9749eeda4e451732ae239ceb8e01d12c2a4` | 650B | Tracked file |
| `c/FUN_00029ce8_29ce8.c` | `9582954f3f4bce81ec02b4b10128b0ffbc63969fcb57fdb3b481841689440f01` | 583B | Tracked file |
| `c/FUN_0002c15c_2c15c.c` | `2deeaf83c685693fc01209f2ba8ea144218736d6668660bf20dabdd6f23d2019` | 581B | Tracked file |
| `c/FUN_000300b0_300b0.c` | `2b5dcac3ef4701d90d7850817d695f39a452b6febbd28a9ee2176dfe758d93a8` | 667B | Tracked file |
| `c/FUN_00032e0c_32e0c.c` | `164eed1b4bbd37e1619e8a9a1fb6cab15416f900fa9401e80fb2848ba2530224` | 731B | Tracked file |
| `c/FUN_000330bc_330bc.c` | `59becfc2d3761a016a8f54b9c707b0f5b85671e5810e95fdb03a21e6b15c7093` | 4.3K | Tracked file |
| `c/FUN_0003397a_3397a.c` | `9a45485dafe57e9c686e7e99cef39a61e38e6c6b521f54aacce486048d8a1584` | 674B | Tracked file |
| `c/FUN_000367c8_367c8.c` | `fe4a95ef2b4b9caca9ff8e30b782dd6e92780cfe954605c74db9636933084cda` | 1.3K | Tracked file |
| `c/FUN_0003697e_3697e.c` | `104f27a5f39bfd7c3a0d549788ab91f14e2ff7f985fd71084eb2ea5a6d4f4a64` | 765B | Tracked file |
| `c/FUN_00037010_37010.c` | `ba5e6d4e873d803114acd58ea7470bd00f302ce6aa525f2e09fa7374a486af64` | 637B | Tracked file |
| `c/FUN_0003d244_3d244.c` | `98f82e12be8fc087eae4b5ffcbf178beab78c016458d089d2dc4587ea8ac32ae` | 712B | Tracked file |
| `c/FUN_0003e888_3e888.c` | `54cf03d8eabffa9008dc4ec139d335bd4810b29abef91c446175fc6ee161bb7e` | 833B | Tracked file |
| `c/FUN_0003f074_3f074.c` | `9c69bb5c06e303e69bc47bd419ccbeb4222a60e40be03ad832da0ca0c28fab0a` | 730B | Tracked file |
| `c/FUN_0003f224_3f224.c` | `039098dce883960caa5b0d25d81a209a7cbec6015b4263f123019f37b6bde0cb` | 640B | Tracked file |
| `c/FUN_00043344_43344.c` | `7cab2ee999670c97cad1ad7ef6579253946c56996ae599dc2d2e704b224a9d89` | 668B | Tracked file |
| `c/FUN_00044294_44294.c` | `d0fd0aa9b15b10e3c7cbff34d5fb3087897b20cd9cb85bd8bd51c67d58a40c96` | 764B | Tracked file |
| `c/FUN_00044ab0_44ab0.c` | `e28339a61f5fe21d3d03629d95d664ee59fb677159d6d8de3da254f4854fc864` | 685B | Tracked file |
| `c/FUN_00045052_45052.c` | `f9c67e4575f47fed867d64676316faf9fd106cd8c1976f34be20d8d0a89e66c7` | 735B | Tracked file |
| `c/FUN_00045b4e_45b4e.c` | `eeb34272ff4bbc0a2406d6c082bc54b1ef7d2b1d525ff4b0027d8364f51507c5` | 644B | Tracked file |
| `c/FUN_0004980a_4980a.c` | `dfda626f3107ec90c13213873f610f93960a6ad0851630bed53b30ce8a40ce40` | 725B | Tracked file |
| `c/FUN_0004c5e0_4c5e0.c` | `c751c6bf8b78b180c8ba6e7a6a006fce532b551ec4a4cc5c391ba6cbb72972a6` | 691B | Tracked file |
| `c/FUN_0004cecc_4cecc.c` | `2e55f896a439e56d3d8e1567508770bcc6a755925426843f6901827932668f4d` | 666B | Tracked file |
| `c/FUN_0004f3c6_4f3c6.c` | `cb721e66a87593ad3f27499072e4a26d07976ed41d43ff87bf68b12b23e93478` | 674B | Tracked file |
| `c/FUN_0004f6f2_4f6f2.c` | `8bbccd702d24c80150af80a662830cee62515b714b767826878395fe78528582` | 569B | Tracked file |
| `c/FUN_000508c0_508c0.c` | `58879f16a2aa278e42c8fe3220514f7d250ca32439e7c5211df45e310635ea09` | 622B | Tracked file |
| `c/FUN_00050eb8_50eb8.c` | `9aa2ad8f7f7404c95ba4606df9d0bcda6e1df55876708b71e15011ca801f1831` | 669B | Tracked file |
| `c/FUN_00051314_51314.c` | `5fe2b816632619dd931e0a7b01923607749b6a541da9452f1ecd64e5588195fc` | 918B | Tracked file |
| `c/FUN_00051b18_51b18.c` | `4c4f96aad305020cd48ac837d72ae95e0a6f5f0a09f52c054665e54dd9c828d9` | 531B | Tracked file |
| `c/FUN_00051f74_51f74.c` | `4aa3c2b7661578329b3bf72ab9bab101c7cdeba6d0f7b17a5bb74768fab0a39d` | 655B | Tracked file |
| `c/FUN_0005201c_5201c.c` | `bb83a72bb4f88926a8a20ce301b795094b739102690d0a8e3e8fa0c06680c102` | 662B | Tracked file |
| `c/FUN_00052854_52854.c` | `246c85c01cde4888c32c0474bc376059dd2d912ea5d847d5d0b55ed6adf0dadb` | 669B | Tracked file |
| `c/FUN_00053770_53770.c` | `b6df2572071e654cf031caf0b1ec3fd1769f46691cb8e3dec34f8d45ec5ee3c7` | 697B | Tracked file |
| `c/FUN_000540c8_540c8.c` | `d79ea3b07e18c5792e8fbee467536306b218dbb1a42cbf9f5dca22d64e75770f` | 648B | Tracked file |
| `c/FUN_000546f8_546f8.c` | `eb0354c4acd41464163feee3592cf32c40f394f2beef17eba416aa28b0e93d27` | 767B | Tracked file |
| `c/FUN_00054d14_54d14.c` | `0048d3610da030c14401ac517687fd6fe29e43a309a709472dd2ed5784897547` | 830B | Tracked file |
| `c/FUN_0005698e_5698e.c` | `52f6a82f90c3cba3a36365fc4b9c1d3dc88575249e9ad3b26e625a3466b30196` | 552B | Tracked file |
| `c/FUN_00056acc_56acc.c` | `3972c06ec3ffae6c84bd97d46b665f3a217322889d7917da34eb00ca3d9b6c93` | 1.2K | Tracked file |
| `c/FUN_00057058_57058.c` | `ef3b4714b3173a2edc1b45286d04c1e1d811be2dad2ef72b4717bd24ae98fbfc` | 624B | Tracked file |
| `c/FUN_0005a3de_5a3de.c` | `9eb52b1b59706e43dba7ae8e99dd68b7a1e32985af50a1848d1b52c8d3921028` | 674B | Tracked file |
| `c/FUN_0005c740_5c740.c` | `e063c306bdd87cc02f5357d7d58fbd56b26ae22d03b3ab00f2c900e92c42c3ff` | 623B | Tracked file |
| `c/FUN_0005c814_5c814.c` | `9b753b0de9d9cd981e793e96a79f5b4e87b664332a42b67d620f205fcdbe9413` | 587B | Tracked file |
| `c/FUN_0005ee86_5ee86.c` | `2e3302e5274ccc7e12d02c8c959c3e41e13473ffb3c72ea06d4d1627862b5695` | 681B | Tracked file |
| `c/FUN_0005f00e_5f00e.c` | `bb64d8999ae812ae22d6796e2a4a9812ea45e28ca641301e50f62b20082c3ce9` | 806B | Tracked file |
| `c/FUN_0005f826_5f826.c` | `634b74c47c8c765973e2c9fab69205fbc9dceab3b57f01124496bb54823933a6` | 688B | Tracked file |
| `c/FUN_00061208_61208.c` | `b9d4246673c0cedeaadb70bdc83b9acb1712d52d24c9a0f052dd0013d810822c` | 910B | Tracked file |
| `c/FUN_00062288_62288.c` | `f44d8deeaff31a5223c21dfc86716a8fbf7673896d7a81163dd2363648c31831` | 690B | Tracked file |
| `c/FUN_00062344_62344.c` | `2217f1ae0d0f46e4a5f34eaf9be5480c667f20d396d1f7bf623eebd707d1e3f1` | 654B | Tracked file |
| `c/FUN_000627ec_627ec.c` | `15ca3019ea3b21c2109aaf573ecd157174a691b2041a7c0de5251370458d5b43` | 678B | Tracked file |
| `c/FUN_00063a48_63a48.c` | `b20b04a546a539a86414c62dc63379499cac5bbf7827627e5a3ff63157f10b78` | 580B | Tracked file |
| `c/FUN_00063af6_63af6.c` | `e50737e46463436ed6308a5df8d99725f5486d5bfbd68cb4f6e9e2fdbc710200` | 841B | Tracked file |
| `c/FUN_00064068_64068.c` | `e0a94cdee4fd5c5ad3778c84f354dfa2d255e783e2baca9af435abfa0d50b9a4` | 619B | Tracked file |
| `c/FUN_000644fc_644fc.c` | `4eabf9ffc84cc3f91126569e65e7e8820ab45471612bbe4f33993fa2ba5f9b55` | 662B | Tracked file |
| `c/FUN_00064746_64746.c` | `0b47082121b2260c0d34a9832d4fe2c786165fa9b6a3de505efe2cd059c455dd` | 830B | Tracked file |
| `c/FUN_00064e16_64e16.c` | `1b2779abee9aef84eaae92339a91f0837c3d6258ed220d1f877ca5f5b73bd4bc` | 666B | Tracked file |
| `c/FUN_00066b36_66b36.c` | `e121fa319abc6f14ef31c476b7897bc539781b21e513f2c09e184bea03b2b063` | 688B | Tracked file |
| `c/ImmoBadStateSet.c` | `082ac4cefe69315efb48d5cf511f47e9d4d76ffd103e9aee9a6b1c344aecf49f` | 642B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ImmoGetCANData.c` | `7d94ec5b33b88a614baec2e5da3d8445c5ea74ab9d073f610b5f384003ba3173` | 3.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ImmoGetSeed.c` | `d7ad32c0c9f7ebc67a454cfa705b0feba9c691cd37aefc49372c5ca5191b15a1` | 815B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ImmoGoodStateSet.c` | `1ad50bb9a36813840d0ddfcf7e671190c6a76d872e475a43982b7b3dc54b5d57` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ImmoKeyExpander.c` | `357532455e29c9a11c3fcb1278b9be2932b75377b1728e020608c6fd6a95b631` | 1.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ImmoStateMachine.c` | `21478bd040f2d2fcd3a0c573cdcfb24841669cdedd5dbb8cbe9d909992f7b39b` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ImmoStateReadyToDriveEngineOff.c` | `3485e17737f8091207f2a7d2b68a7c7319f86b0b8f018c0b2989b9bd6387c6c3` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ImmoUpdateRelated.c` | `574be1bdfc805f59f8d7459ecdb25201e4c92121757d003d77656ea7078294d4` | 2.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ImmoWaitForKey.c` | `891941ec8c5abcd1dbcdd9f020821e82519b2dfbed5cc0ae0ba854f7c722fa6a` | 3.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/Immo_Keygen_related_ADC.c` | `ad00f3ec72946ce012bae26e894c9b07225819c6ba4bb11a4593abeda83cf36a` | 3.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/README.md` | `19893e29788376195b257451647d15cad07b4004288478d3dd267a3bcce8c168` | 10.6K | Directory README |
| `c/SetMemoryNotValid2.c` | `76d4d68b7a3753a832ed4437056d867f137cf48c4ef6057d6e3f7a0e006741c2` | 685B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/acceleration_enrich_0x591BA_591ba.c` | `01cedc8c3e2792a49a4dd2d78724788b20961d852404e85c6fae425142c0c06c` | 1.2K | Tracked file |
| `c/add16bitSaturate.c` | `65d220d3f455e61b67a29a6f5ee9817a89fd8597f7e30c85a5fa7ca00bc47cc4` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/add16bitSaturate_ADD1_ADD2_2460.c` | `2945513f07319cc3458730c6eab30b516bab0be81a4737d39cc628888e1adc72` | 667B | Tracked file |
| `c/addS32Saturate.c` | `294f2cc7fa810278f4c14083afd0b103c4d54fa969277a1a39d815bedaaabec7` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/addSaturate8Bit.c` | `cf605fc9870e06f1f3f8fa17e208469cc078ba0804b151f19436d25f3663563d` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/addSaturate8Bit_2478.c` | `8366638e41129052af095902ff0fb7ba4422c08d89c74cf5455bb635dc79b999` | 766B | Tracked file |
| `c/airPerStroke_341e4.c` | `02874d083aa86f3292ba127ec66186e58d979f1c6d451baebd73ed07a3e31322` | 711B | Tracked file |
| `c/air_charge_calc_0x19190.c` | `e48bae9a88922b640a3b2819ece5a5f165df59402141bbf555cbdd6aa0a4eccd` | 4.4K | Tracked file |
| `c/air_quality_0x5A2E4_5a2e4.c` | `e9d5ddb18e7ea7c5d14085dcf2d9c1d4785b8ddb5139d56360fffffc9df1c743` | 750B | Tracked file |
| `c/alternating_sensor_sm_5D34C.c` | `4e665258bd1ee20449884717e1a47c444c930bf18ce3945a694dee0a1c9b3674` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/array_init_zeros_dual_1D0A6_1d0a6.c` | `e1b5543b30f416972ddac11c98aa8381830031286fc25bc3c23b606d4f87b290` | 652B | Tracked file |
| `c/atu2_edge_capture_config_6F3A.c` | `6a112d5f1755d848bdd5f37f5df88d75b727f14abd87562ecebf301572f49ae1` | 2.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/atu_fpu_control_wrapper.c` | `37355cb7ffad034546299758572983a814c83daae3ee519cac8d25f59af77f82` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/baro_sensor_value.c` | `ff3fb8099c49013535c2c72a2cd9be211b2643580a487ebdf14570efcebc2e70` | 6.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/battery_voltage_monitor.c` | `d00b0acd0047ed09d82fb526f281dc1e9ab6401f4a957e3eab19d9276b1c9171` | 6.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/bitfield_extract_merge.c` | `df0b0a792955cfd245162565923668420b34385bed9395188d7c96e878b7e4ac` | 6.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/bitfield_flag_selector_33A98.c` | `89f93793393717a0797dd2e113158c2278deda73a3a8a8fbda4a38154715477b` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/bitfield_flag_status_decoder_339AC.c` | `36a71e37aa8696a59863678823ddfb348d4c92e855ec491e23d10e296535d5b0` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/boot_entry.c` | `643537e3709d2682e083a6367fa9f5f55268a0db2069a84aaa4d0b09ef70bd25` | 8.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/build_be32_from_bytes_f4.c` | `6fddc29a1c3e0ded1ebd3392c8324ef64448b28ae927eeafb51219ec296e3800` | 825B | Tracked file |
| `c/cabin_air_filter_0x5A4EC_5a4ec.c` | `ada7b11fee1eaba47128c2eb737dff7d035d6bb97c737713c479f1a4a290ab0b` | 2.7K | Tracked file |
| `c/calc_adaptive_fuel_trim.c` | `e234b39f85e7c69ccf5d5aadcd5afc12be9b8c2350509b774397979f3c6f3a2f` | 9.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_decel_fuel_cut_445AA.c` | `a5dcaba0a6506029caaee13de21f1f4a9885821494fd77f7680ddbbbd938b89c` | 8.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_fan1_control.c` | `a58ee54e0704b5a2dd881a037f879f8a55b0239fe72ea88b6866378b56c5c50a` | 4.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_fuel_pump_duty_trim.c` | `2beb3a022c7dc161ded017a12e5019246648e14ccbebe6444ee6d4e6e7b53d4a` | 7.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_fuel_trim_corr_map_136F0.c` | `14ce88dfc511041c896c1c1817ed0fcf5700fadb9854c68452c309c88d199722` | 5.1K | Tracked file |
| `c/calc_fuel_trims_adaptive_117B4.c` | `41a76a6b2533804b8e98c6f7d3b61fc48157b5e96af6af3e2915d81aa6251a3f` | 6.0K | Tracked file |
| `c/calc_idle_speed_target.c` | `5dc987b7d66eb48e02f873add3a784c58edfc20bfd37da693a9897d7e3b6d84a` | 7.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_ignition_all_rotors_13C2C.c` | `d1f63c46fa4f6f677f59fdaf59268ffc84879c624aa840cb4465899735f433ae` | 17.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_intake_pressure_pid_output_1252C.c` | `d67687057f3988ff99ebae558c3c12fb1c029c5514dde7aa1ba8690b2d1d5a46` | 5.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_lambda_feedback_pid.c` | `7a03bece57d64d821e0136574e5744c68e657b9a430aca1e0c14dfd9ca81349e` | 4.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_lambda_feedback_pid_11A34.c` | `c597f69b5506b6f2f93f515c703cbe4b7cba1f4964d878ee0313e0b8ead84237` | 8.1K | Tracked file |
| `c/calc_manifold_pressure_error_clamp_10A5C.c` | `398cdba1c84153835c91a882baeb3d7e7667accae00f198974c1a52520785393` | 2.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_manifold_pressure_error_diff_10A88_10a88.c` | `f0742520cf769a868f1e61b60365ac29d7a826a073f7e5eebff82f10a11e4bbe` | 721B | Tracked file |
| `c/calc_rotor_sync_idle_gate_B.c` | `278b71ed6ed92a40f55f5bb47cf4c541f3941cc4fdad0a4deaea82936c3c374b` | 3.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_secondary_o2_trim_1321C.c` | `3a230ed756a0565097405ca0cd173501a4a7f03b9b69c51c2298146cbe4235aa` | 13.2K | Tracked file |
| `c/calc_spark_advance_0x121F0.c` | `388ebcc4f64675ba826ab987fd60e802d368a878d1bbd02f85a340f7530d2ec7` | 8.5K | Tracked file |
| `c/calc_spark_advance_0x1237C.c` | `309abdd99b182d42ccfd5bd1115beeb184611e2249aba986584f5faa2ef03044` | 8.3K | Tracked file |
| `c/calc_spark_lead_trail_split_19220.c` | `325eeef22b0a10b48844808a6e51127352abb403688c349b7175aa4994ea0433` | 7.5K | Tracked file |
| `c/calc_traction_control_mode_11166.c` | `d69427ce700573758d093bd36d990118d3d029915633297a9e1ae2d8ea759105` | 1.1K | Tracked file |
| `c/calc_vis_solenoid_duty_cycle_1261C.c` | `434c34c7adbdd753326922f4f95b2f950ad0b96ca82e01d071783bf6a8398e86` | 5.7K | Tracked file |
| `c/calculateEngineLoadMax_341f4.c` | `c55229410d8a9c01736639f8d4b576956ff78b0bb9de9af1e802c883716807e5` | 876B | Tracked file |
| `c/calculateFuelingRequestMaxForOBDControl_2feb4.c` | `ce6008254f3a5992d3d39bd23ba521b09bd1555af05ab6fad80da20489f118fd` | 725B | Tracked file |
| `c/calculateImmoSeed.c` | `d95e3de7fafe4260043f271b62314cc3e9d4f114db2c8334df15b3860131792a` | 3.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calculateOffThrottleORFuelCutTimer_12ef2.c` | `fe0b0f662704f8ecd81d2b211a531275961aa83e692189ef02acdc12f48ecae9` | 4.4K | Tracked file |
| `c/calibration_apply_4B770.c` | `736812f9567e9b8b55aa18ba89faae9fddaa50fc55a6f7155c41984b227803f7` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calledLots.c` | `219e9669d41e8fa52334b9e063c1e917baac6354243e5a3d9aee3bf993106eee` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/can216RXUnpack_29ce0.c` | `61cff9cb121ca2d364d09fc5e0e0ed605f8725912bf9f08f72114fd22f1b58eb` | 3.1K | Tracked file |
| `c/can216ResetTimer_29e50.c` | `0168647d6a790c2fb5d7e66692abd9ffed744b0ddcf02f2ff02c8d08e291d8f6` | 774B | Tracked file |
| `c/can4B1RXUnpack_4c7b2.c` | `a4e832fea3a33190792ebbee6d295d21e4b657338e65ec63751af85bd02e21d9` | 2.8K | Tracked file |
| `c/canSetup.c` | `6850cad9a360bfb7b39a7b63fd48a3509f4efad4024a8553673166809d1823ca` | 2.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/can_encode_handler_62ABC.c` | `8d41ea208495da6d0b7e7e42079c5617446e86d9ebf49315591b8b9f8d2fb7e5` | 4.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/can_encoder_556e2_556e2.c` | `b6596d7b6c680a21874f98621d629526efd943bbb47bc799cf8344d02fc8acda` | 592B | Tracked file |
| `c/can_get_rx_pending_flags_d0c0.c` | `793ef0fe1b213e01ca439b9b2265aa63d92e2f06989ddf51e4fce4ef479bc95e` | 2.0K | Tracked file |
| `c/can_get_tx_acknowledge_flags_d112.c` | `bb3328e542b39f39ebb4dea508ad1062a4027e2a9ea9d9f4d70ac5dcaa1af9ac` | 2.1K | Tracked file |
| `c/can_rx_mailbox_ready_process_10fe.c` | `8475ae426c6504dc8645466fb3e211c7354d1809b7773409e27613b3a02c0564` | 752B | Tracked file |
| `c/can_tx_ctr_init_2D4A4_2d4a4.c` | `b2878b62860e72c84607ac3e89d577c76c3d28c686b148576f988622deb46354` | 597B | Tracked file |
| `c/can_tx_dlc_set_2D470_2d470.c` | `236da1af862f9924bb539e383b37a57843d4e4cf14c7181f57a4df3098d67624` | 1.9K | Tracked file |
| `c/can_uds_resp_encode_seq6_670d8.c` | `04a6a9c571134fe757b335331ac5f35a41e50685bbeb43976f48549bff207c8a` | 633B | Tracked file |
| `c/can_uds_subsystem.c` | `d45692e01435c7ddad36fb8a835f5c760fbf70ce293ec6f98bf6f4221b586d52` | 29.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/canrx4b0related_2bffe.c` | `2651deff9f61d090812cad7a59cdf2a327fadda83c71b6699692dbf6accb4c42` | 3.3K | Tracked file |
| `c/checkFloatValidity.c` | `c6fa075bfa2eca9d0afbbde506d44a02bd30eb7c069fb724805fa24cd10853d8` | 3.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/checkImmoStatus.c` | `6bdc74ddb0e547941fd67a835cc316971736c4bdc1e2e654bb675f0f9c5d9c8b` | 3.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/checkWatchdogForOverflowandReset_11e8.c` | `87ec7ac6ce02b9b48156e125207d96661a580af72e66cd7059321d6e6f74e740` | 2.3K | Tracked file |
| `c/checksum_complement_add.c` | `ab9f6cf6f4100417b7c6f14a00264014dbd3020623d8914f73b439921369d879` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/coil_correction_write_0x50A54.c` | `a64fe38f2b119ad423af6576a152fd76b8c2be09246a734b00e202a1f2471888` | 6.4K | Tracked file |
| `c/complement_shift_u16.c` | `d08537d7987746e4a32ca48d3c15563abdc498686f0fb747c97e54203a0728fe` | 1.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/complement_shift_u32.c` | `261313ada94710047619cb38d323f3fdf68b634d6cc56b511a56cef37dc0ccbd` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/cond_flag_b2e0_multi_eval_21534.c` | `e70d47a0c88322c3e8977579f0c6e9782b0ee4034c06818fa667d3932cbbc7f1` | 799B | Tracked file |
| `c/conditional_flag_set_sensor_state_2EF0C_2ef0c.c` | `d33c736e412f1c2930d7dab8c3d2cca4cbc6dae69e2d11ee31483b9cf11251fc` | 2.4K | Tracked file |
| `c/consistencyCheck.c` | `17c2cface615473c0271b529438a7034dd418e0aac18068b99420802cdd977bc` | 5.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/control_struct_init_zero_5C98C_5c98c.c` | `5f3d2c580c69bc5092a527d9f4b96c6ec56408ba603709f341c54932c0abc530` | 625B | Tracked file |
| `c/coolant_temperature_sensor.c` | `f6b72e59f2c0b47290cf23b13976b09d3a01d61cba6f1319edfabd57632d39cc` | 8.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/cooling_fan_control.c` | `39f416f7bd45533adcc26c75b58e093798c57d91609ea7b0de9289b89ddfd651` | 2.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/copy_word_0xFFFFFC534_3940A_3940a.c` | `ed27416437c61985372bf3ab1ce2177cb0b89b39d79122be3486ad059619bc5b` | 820B | Tracked file |
| `c/counterReset_4ca9a.c` | `d54a97016a20a0276497a4064780bac35039e6ad73853bc4556dbb2787c9b2da` | 709B | Tracked file |
| `c/counter_increment_a_2610A_2610a.c` | `e24471e552313c2d8ccb349673311826ed1f89be68b9a10666f2ed2943f183e3` | 798B | Tracked file |
| `c/counter_increment_validator_37650_37650.c` | `5369ba7b782601b89cde1f3dcdf1e20c840bd1e65460fed9e947cc79f566d9bd` | 3.4K | Tracked file |
| `c/counter_init_zero_2A26C_2a26c.c` | `187e6c790583b4b9a099f2a65a62c41ac35fe2b81237cb341839209b1f50db0a` | 640B | Tracked file |
| `c/crankSensorInit.c` | `5893d231c7bcdcc9a9913412da43f1c8047a6997669ae3273652530804bf3087` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/crank_flags_enable_7ed8.c` | `abc2ee77ae944388d9ac5d3a9e194183326d8a2cac169132619b040e21ec55d9` | 1.1K | Tracked file |
| `c/crank_state_bytes_clear_7ba8.c` | `a3225b85bb5ce695a1a97933a07ca8a35d80b13d228343ea14a13fe2a994e46a` | 813B | Tracked file |
| `c/cruiseControlMain_2eb40.c` | `6b6627ef7adc714bb213a13861e23084205965febd5b6f368ab0f1addad14622` | 779B | Tracked file |
| `c/ctrl_decision_5698a_5698a.c` | `60c145da733a9d0345453afd3d79b05f8fdfbefa3d0d3bd6a3f2d3d5f45f5dc9` | 712B | Tracked file |
| `c/ctrl_ionizer_5a7d4_5a7d4.c` | `d6338fa51e3883ad171fa6c2cd034a8476cac0ee40b9d2db85da491788216e35` | 809B | Tracked file |
| `c/ctrl_nesterov_571e6_571e6.c` | `08269abc647a4fabc2113eea8cefc1247a6cc4e74f503c7e4a1a9e37ae117657` | 1.2K | Tracked file |
| `c/ctrl_protocol_51dc6_51dc6.c` | `197c2d8514760bd9e38173b6a4586c60cadae3f740e4c4714c96d38291d4bb76` | 701B | Tracked file |
| `c/decrement_saturated_27A36_27a36.c` | `5475792375a2f8cd1de6faeb57ccb69dab23c3355335a9460718f4c40fdfefc3` | 659B | Tracked file |
| `c/delay_loop_n8.c` | `7310a5823dbd90c6e8c86d111e26098331723e57eee8e692edeb27dfa97f0544` | 1.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/diagCheckSecondaryAirRequest_5b76c.c` | `dd058b537bb6cf2bfaa89dc51e32a61b1fd65f5298d92bf03de8fc878b627995` | 897B | Tracked file |
| `c/diagControlModeSomething_5a78c.c` | `6a44d52d7007d14fc595ab5aef6e163549670833693fc31e700d5ec0a0575b3c` | 789B | Tracked file |
| `c/diag_airbag_5ab9e_5ab9e.c` | `fcad079ba3ef1c80279c8e2d6c5f8a735061ee1ac8e0457a2ed4ab6ef7bef8d7` | 1.8K | Tracked file |
| `c/diag_bitfield_2c4cc_2c4cc.c` | `d98c0e4e7d99c58601fb75c1a605f16fd7106ce7adff8ad2461373fc67257951` | 1.5K | Tracked file |
| `c/diag_fault_cond_eval_903c_56788.c` | `a67fef4055147bef643a0c7d045b23febf858210336f9cf49f99edaeda212afd` | 676B | Tracked file |
| `c/diag_fault_cond_eval_9060_56962.c` | `b62d4ce7d4dc59a3f74c3fb366b8184b4888e00bcf64cbff837d6a1be7221029` | 684B | Tracked file |
| `c/diag_fault_cond_eval_906c_569c8.c` | `53718d26961e71a6e5ba2246ba3e788d1391987bf1e4ccd7f81d7672eef77188` | 665B | Tracked file |
| `c/diag_fault_cond_eval_9070_569d0.c` | `6b3c9e4890fe907af896a0988a4f26c62dccad6bab7e0317932b87f507dba1b9` | 692B | Tracked file |
| `c/diag_fault_cond_eval_9074_569d8.c` | `1bb0b12bf89e011fd5ddf13b733b54ddbd073614b07c8fd92b96b83aaf1f58a6` | 641B | Tracked file |
| `c/diag_fault_cond_eval_9078_569e0.c` | `f788ca00d2c3cdd9b7819141eae7bb2f60f8b6e8c36d23452c225dd6c1ce107d` | 1.1K | Tracked file |
| `c/diag_fault_cond_eval_9084_56ab4.c` | `880baef2f0cab80c561cbc863d85babc0cf2afcf29b97ce9aac32ae04977d5df` | 754B | Tracked file |
| `c/diag_fault_cond_eval_909c_a_56cf8.c` | `e949b9c79e9d311ad452e401c6e898d1342f812c02f041347700a82e1bf382f3` | 635B | Tracked file |
| `c/diag_fault_cond_eval_90C8_56f94.c` | `3ebbafe60abaf79593e814982b7d249daa6ebc2d4f33c6a6d751b0b2c19bbd7a` | 626B | Tracked file |
| `c/diag_fault_cond_eval_90cc_56fb6.c` | `dab54e8e4829d43ad1d68fbfcfc825f92bd8c3015e7c0f0ba884933995249585` | 657B | Tracked file |
| `c/diag_key_validate_4E78A_4e78a.c` | `0bf435cc7bf4d7069903695f7d8804d8311ee7ee654af01a80f619e33d5552ac` | 2.7K | Tracked file |
| `c/diag_reset_session_state_1720.c` | `49fbb4cba122e5e9fcf9bd7180495c3b675f4c04c57636ce7e07cf37d54db17b` | 800B | Tracked file |
| `c/diag_response_send_4E904_4e904.c` | `24cf8933e9c8a3e19ebcaff154ccdade641f00c592d920ea38df85112ff75706` | 719B | Tracked file |
| `c/diag_seed_generate_4E72C_4e72c.c` | `288ec9653cd045e7069e1a7cfc5e352a2ae17e77595aa457c5e5585c87dbd06c` | 827B | Tracked file |
| `c/diag_sentinel_5687a_5687a.c` | `58ecf411ef091852579a363fbe88bc55dc2ffbf5633032d4ea5efc7c477172e5` | 1.2K | Tracked file |
| `c/diag_tester_present_sid3E_1908.c` | `9003c90bd1531eb04755b1c946f5f876caf15e38292e9b3cfd865b11a9069742` | 670B | Tracked file |
| `c/diag_threshold_3c3dc_3c3dc.c` | `ac3b139fc69baef4f46af6dd729aac03b113677fd4738d06dbeda0a3cb1a5382` | 1.8K | Tracked file |
| `c/diag_transfer_exit_sid37_1cb8.c` | `99203882d29bfb87e88b339f808b4c30a517478211bbbdbf26abbea9192469d0` | 668B | Tracked file |
| `c/diag_transient_4fca4_4fca4.c` | `c5026beb6c6b2cf164e50d032302466c34a6825bdaa020b78734b400604a30aa` | 1.7K | Tracked file |
| `c/diag_vehicle_info_4E2BE_4e2be.c` | `7e3b235fdaec9803bc55961196d34e4137695737e815b0bc42d85e6008846f5f` | 631B | Tracked file |
| `c/div32_signed.c` | `6babcde5cf39727ee7de552e26cb017f914057d31da026e6867d300196cb8727` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/div32_unsigned.c` | `375556a81fe66996a77f2ad06858ba38f5b875f04ef638ac008db2b72d2d4007` | 1.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/div_4740.c` | `9ed2b06608bd0b0fbbe355be7a36dc3c04e184b2a0bd5bb478ee3fe0577ff0fa` | 8.8K | Tracked file |
| `c/dtcRelated.c` | `76403b0f909ab0e55ba19510570a88194fedd91cdae823153c82ed2755495669` | 3.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_code_set.c` | `c599bb707eb0cc56a2f33dde719a40fb9775cef22f8f35d628080fddcfc0d323` | 2.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_data_read_60A86_60a86.c` | `d822fcd79b3440be2a86679fb3641a0a7e005dd8aaf7336be6c37e48d115c379` | 694B | Tracked file |
| `c/dtc_data_read_60BEE_60bee.c` | `8c6edb586d4e8030ebf504b2dbdcd38d40b85152133c214aba6aa64f06cffee6` | 694B | Tracked file |
| `c/dtc_data_read_60CC8_60cc8.c` | `96b1e5faf507664c880e2547cff428f4e38d28b4ecc3195669753ea7aa141ce0` | 616B | Tracked file |
| `c/dtc_data_read_60F58.c` | `117f607f28ff86f7f9da59cfa10a9a57646410e668f27463bbcb94bc66e1e7e2` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_data_read_60F58_60f58.c` | `be5ab95cf6f7f94d3270c3a56ac65e6875023d39ab66f5f8a3ec446d501f851f` | 643B | Tracked file |
| `c/dtc_data_read_60F74_60f74.c` | `79c4438a63a5b08d27a2b0455f3b8dcdc6b3a2be75dd73ec25921c7763e8add1` | 638B | Tracked file |
| `c/dtc_debounce_monitor_43760.c` | `9a662f2dc94218fc2650fca4ef08663bc6900a99ac0f981c1a5455c8bb6257c3` | 5.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_handler_610FA.c` | `103137e640d38df9b5c7801d371f52128c6e2119eee1d658cc336b9a32506c19` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_handler_61550.c` | `f72a23bfa6305e94fac52a6728e3e72160f734e605f42ca3fd8750f058195a16` | 4.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_region_checksum_validate_8fc0_66280.c` | `f5e5ecdb86c0e8f147c362961d54004fbed9e67a1cec76ec2f7a747d05393e8c` | 717B | Tracked file |
| `c/dual_cellbank_selector_58C4A.c` | `ab5e3f1345b74884d9834be664551c2cc091e6edb507fce44d9e068c7ca28c87` | 4.7K | Tracked file |
| `c/dwell_time_calc_0x5071C_5071c.c` | `cd817e8ec31b5e86b6490071f7461a40a8c4eff3e77315a29964bc09fbb83ae2` | 2.8K | Tracked file |
| `c/eeprom_commit_dispatcher_37000.c` | `f47bd9b12d35079b013f35c707903c5a47a3fabba577d19d66fb958a4dc5ae6c` | 2.6K | Tracked file |
| `c/eeprom_immo.h` | `fc8de3e9aeab9b3bee289b34720a62b5baba90053da26ecfc06dcd51ec72ef19` | 10.0K | EEPROM/immobilizer shared definitions |
| `c/enableDisableCruiseControl.c` | `e479adc91e677d7a4018dc7a630b2b0e853eb9a5021f4a06c29aaba5e37c51ee` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/engineControlCalculateTiming.c` | `7f88526b869a77edf6e73cb6a27a0b29d2ee81fc40f086843368722e58d7be09` | 12.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/engine_load_estimator_0x190A6.c` | `5b3df13c0a8d9ab5ba0a976f00da9022c89b5dad89d707f6b8833cbbc86809a2` | 3.7K | Tracked file |
| `c/evap_purge_flow_calc_22d20.c` | `715df40019b4c20c00edd47ea0d6d3aa67d692aa17ef42982cd18bb81c2f2511` | 1.2K | Tracked file |
| `c/evap_system_control_0x4F750_4f750.c` | `5fa6b337343e5ef53f81f28aa51bf809ac7da76fa191fc928fad90eb79bfff6c` | 1.9K | Tracked file |
| `c/exhaust_oxygen_control_19480.c` | `c6ef008b91136873ebf9babe13d7c52cab66a273e2e5d1c06ae14e608ccfd862` | 23.1K | Tracked file |
| `c/fault_condition_check_5F018_5f018.c` | `c9f53fcc315003f0bdec88394f343fe07151bc0e0ec44bae20c8f5fc992294a9` | 1.4K | Tracked file |
| `c/firstOrderFilter.c` | `edd2ae05d9b1f0c565eb731011eb8959375d59f189e61b27582f46c63f70202f` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/flag_set_coil_event_e448.c` | `d5ce3b0d1c4b168b825704d1c3306a80c21bef7e3905fc15dd589c6f3ecd215d` | 661B | Tracked file |
| `c/flag_setter_49ED0.c` | `b666884cf13f385e0471b743366017d3b3f0cc135ee60f447530617345e3b08e` | 1.8K | Tracked file |
| `c/fpu_compare_and_mac_394da_394da.c` | `8cdf02ea92e73656a2b814750f827ba739889d8712db78fc9ca984cacf4c7c35` | 694B | Tracked file |
| `c/fuel_calc_entry_9528.c` | `7d9e58372243daaf187e28152e696ebe09318ccd8c4518cf6d4d330bda348cef` | 949B | Tracked file |
| `c/fuel_compute_fcd2_fcd2.c` | `d3b974eeceef157f1f3e5d0ea2c2cb43ea7e7ab56c3a08993104c8c84e83f962` | 613B | Tracked file |
| `c/fuel_control_59dc4_59dc4.c` | `5c60f5b6f4270d8df680acc7c48c31a8147f72b6988102cfec925d27bb979990` | 662B | Tracked file |
| `c/fuel_control_59e24_59e24.c` | `529783d0f8fdabc1f51912fd0fbcc00722788412b13fd64dab6e8209645ac7b0` | 1.5K | Tracked file |
| `c/fuel_correction_reset_45B44_45b44.c` | `58acf235b31c557e36ffd798483c6d30aa146086843e3683f737f63ea0fb1e17` | 1.9K | Tracked file |
| `c/fuel_defrost_5a248_5a248.c` | `5ba4f174012b1d0b3245158484c70b958a0a0c9a6cc81eddbd2461007e5f3f3c` | 3.1K | Tracked file |
| `c/fuel_detection_1cd32_1cd32.c` | `a16595c7601be1ba03222fd986a484f35ff654bbe97079c820d62eb924e42777` | 693B | Tracked file |
| `c/fuel_emission_4f70c_4f70c.c` | `56f571a1cffc8a4e3e9bea8fc7d0dd70e2f3cebae0f576c9fbb0f689049145ce` | 1.9K | Tracked file |
| `c/fuel_fluid_59ba0_59ba0.c` | `78739c41d8e0a6de8718cfa6f7679324348da3550f004a061289347e8554d093` | 1.1K | Tracked file |
| `c/fuel_intercooler_4387a_4387a.c` | `dfea774c4050bd20e90b2a5e58183a7ab251f4ea2d5193a749a8cd1eda3fbf04` | 719B | Tracked file |
| `c/fuel_pump_control_45CA0_45ca0.c` | `5b6c0636b0767695979a90dc8ca1dfd448b068b2e2d2c413ec4a6dbd204d63e3` | 2.3K | Tracked file |
| `c/fuel_table_init_45B3C_45b3c.c` | `c5252481cb733a2ace94d7ebc0e619c2d2f9f21a6297f3129b5a8ed41f4ae10a` | 674B | Tracked file |
| `c/fuel_trim_channel_inputs_map_e07e.c` | `87ae84972a991c2bf810c3e27124dccb541a7b0b816ff5767722f8336a692d41` | 766B | Tracked file |
| `c/fuelingInit.c` | `7b4b61867c4dc4a5cf675a6e54a7449c40704827876313082bf1f85398114579` | 2.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/gear_ratio_detect_449BA_449ba.c` | `19652664b2e7d0da118f2cc3f4f475a4c291e420de1d8f2cb3510102b8349e63` | 806B | Tracked file |
| `c/getACSwitchStatus.c` | `5e09f56f44c1688b5e24cb5590c40c9c7cc3494159e252231e90bba3e34580be` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getAlternatorFaultStatus_2687e.c` | `554d8ecacee01471dfb69ecfed5aca7a5f8e904cc6de3b66c309fd31c1686b99` | 1.4K | Tracked file |
| `c/getCommandedLamdaOBD___53a62.c` | `a238d6729eb142baf8aab24b023deb6781787bcf3471c8a43b18b240c4adc16a` | 579B | Tracked file |
| `c/getCruiseControlAllowedBool.c` | `1d114891643ffa075fb44e252bcef6c1bc52237a4245d3764b5ebb9edc23066e` | 2.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getDataFromE2RAM.c` | `e16bd04a9030060389ab79671a5bdaedf19e83b61809419a0bf89fd3d2295de0` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getEngineOffTimer.c` | `a991304600b08d07a380e7f00a85fed24d87c062967fa14f753ed48a5797de7e` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getEngineOnTimeForOilMetering.c` | `95d8becab0ecb97d84a854059ae24330900a2a82c2f1aa3f9ee7d6fa813008e9` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getFaultStatus.c` | `eee3ef06f93ec97147ffc1523eab94cca17c92dfb1bb30cacfd90b22cd2ee19b` | 1.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getFromE2.c` | `140f003bc3ab448cf23d0e127a38250d0bd9f8a4b37d097355069ced7d02a095` | 2.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getFromGPIO.c` | `5e25baa037946998cb251363517adaf1a927094930a62cb5a48fab535e425406` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getHCANRegisterAddress.c` | `0299aa0eeedf79a6faca8347646d000692a721a21b0dcdb021238d7fab8e9236` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getKnockSensorADC.c` | `9940d4b0e30adff04de2f9ff4daf6de79f74bfae8980626df0408a67e50aed0c` | 3.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getSR.c` | `11b616e749f1094b8576660e9d1a9e4f72df837644a69ddfd495d24a8dc4df67` | 3.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getSpeedLimitCal.c` | `400b6d9fd9c2c5dd4fb052f1ab9e7727f9c7070c2cd6a8b0f27f7f4460c49f71` | 2.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getThrottleLessThanLookupTimer_42f2c.c` | `62152439d15d68690c8c93731fb6e306af4f1f2c8c5b2b71dd526422619b9439` | 1.3K | Tracked file |
| `c/getVehicleSpeedForOBD___53600.c` | `7328c6b57bc505889338deb78eca8960d7c8ba6986a7a41a70021da086819d24` | 1.3K | Tracked file |
| `c/get_ignition_dwell_time_0x94C8.c` | `31f5c877578432cf721defc049bd73736f09515d9283fc0e0d510bb74a20da6e` | 3.1K | Tracked file |
| `c/handleManualReset__d20c.c` | `bd5abd80f770e915f3b61e1dc307f420f7e848d62201381ac0759c32301eeb3b` | 587B | Tracked file |
| `c/hcan_mbox_word_byteswap_write_cec8.c` | `28f33d5752e597471ef37e626d0f1a525426c5cf357589b7c900566a4083ace2` | 612B | Tracked file |
| `c/hw_init_2_41c.c` | `d783feb9fe8a625b94e6b530bac6d1b24e7b037f9688d7cfb541fb7c7960803e` | 665B | Tracked file |
| `c/iat_sensor.c` | `2b38a3f53e197fc69bc178e4048d3125128ce406c4a0dd39a912da012468f65e` | 4.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/idle_speed_control_18054.c` | `876c632f79755f636a80f3215b0ff67fec039626cafd620068c394b72391cbea` | 5.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/idx_table_helpers_68780.c` | `4d650cab21eb9defb03303391062a7cb0101b411bc360b6007ff7f15a4c62fff` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ignitionDwellOutputInit.c` | `274bffc2616fe66194bea1f3439360c9f71fc839a83a359e9ba704d3fa9d116e` | 3.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ignition_something_calc_0x91FE.c` | `8fe109c103ef29524132dcb974df9b952f60e9d2a9bdda3e6923e9a52d96e5db` | 6.1K | Tracked file |
| `c/immo_init_check_dispatch_35104.c` | `c2d746175eed55d30f2e812a132a9179b745420fa0b05db9cff74ddef428bcf8` | 716B | Tracked file |
| `c/init_getbrakingorinneutral_5ef5c_5ef5c.c` | `ae9050bdec54e87ec59395db2635e655e75fd731a385f7e851a4768c5cb7abe3` | 4.5K | Tracked file |
| `c/init_main.c` | `ca43f886a219c0e38127b327f94e49bd71601c82d322fc50892f82efb43aed58` | 8.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/init_rotor_status_flags_1117a.c` | `1ae32b87937e06328988319801af585b52d1516ea603a719bbe0dee93029ad51` | 675B | Tracked file |
| `c/init_sequence_547fa_547fa.c` | `889ab8d77bb3f85573f01d6801596c18f957d427c427cf317f265e2e44691ffd` | 1.9K | Tracked file |
| `c/init_state_flags_18214.c` | `994461ac7317c7aca9b5edad34d2f0ea04072485d19288e9016a8060798c9b33` | 655B | Tracked file |
| `c/init_state_registers_0x4F1C0_4f1c0.c` | `fa7f1c06b59309f91b899d41fa07e3ad3e63aeaaf61b7fa028a9f3a290dab543` | 2.0K | Tracked file |
| `c/intake_port_timing_monitor_1bd20.c` | `04e6e44682fd389f51b2f2c60eb22bf8a8a0be9d6fdfea9f4e37994ab29e7bf4` | 2.1K | Tracked file |
| `c/interp_leaves.c` | `55d65a25e37087eefd642a67e153930b88ca62f53f6b6fca89ad77e008a458ed` | 3.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/is_eeprom_valid_624.c` | `a53bc602373ee44b321c61e730f98486e9341c4e5b8cfe63d700a4f3e3562679` | 1.0K | Tracked file |
| `c/isr_decrement_28126_28126.c` | `e5c090436ddfe26d731ba288c045a5af5621c0bad411b7c773af5e38d8689648` | 1.5K | Tracked file |
| `c/knockFunctionInit.c` | `5cfe866de396903775202a0d34d2a0341577eee848b38ba8b123e3ae9f9df183` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knockRelatedInit.c` | `3e07458d0d3609abb33b07a02bc586df1505105945b22e337cdcbf026292e5ec` | 4.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knockSensorADCFault.c` | `0e2da1ebe60ff44a0428f7778b02e5a96e6204e055a3278aedb8b96c6daab5c8` | 2.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knockSensorADCFault_c460.c` | `77f8590e108a4f1629f235e6540bb8d1f31e66bfc8f4613f7ae5fc15dd540021` | 2.2K | Tracked file |
| `c/knock_sensor_adc_fault.c` | `8d037a428d3955462521faadc1e1576b6cd205bde687259c80ffc5257c00b453` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knock_sensor_adc_read.c` | `e81623961937d2a72ebc794247a9644c268be64c1e27458c91eed71c5452f0ea` | 3.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knock_sensor_proc_3C06C_3c058.c` | `1cd78ea4469e2ae6b7eda46e01e495366e43513fefdc2bff13bad226ae107551` | 2.7K | Tracked file |
| `c/kwp_session_frame_init_15a6.c` | `81663bfd84dd1463ad51885b6a47e6bf8334ab6f612132b2faefcc7b3000fc87` | 717B | Tracked file |
| `c/ldexp_481C.c` | `7a8608dbbab1c902a6640d7e3102ebcd930a3e4099ad763867ea4beccffe10bc` | 3.3K | Tracked file |
| `c/limitKnockRetardMax_ConditionalRPM.c` | `0cd5ecce7b0dcf470bbb23ea98cb4b8ad5ecddd460a443581d56742076f1a920` | 2.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/loadDatafromE2intoRAM.c` | `688e09298a8445190ada3ce00f18398defef7db140b9c99e305e9fc084a8d510` | 590B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/loadStatusRegister_ADDR.c` | `726a3760492a53116a9d8f7a7e27110de3781958acdac71f5a020ab227fed3f8` | 1.3K | Tracked file |
| `c/load_blend_factor_limiter_0x16A30.c` | `ba9ed26384ff6373e4fa20e9b480aac54bf9a8fd3a78a559ea7e612eb321720b` | 4.1K | Tracked file |
| `c/maf_sensor_value.c` | `3bd3e1fed9a16b04a2eee0addf587e1b09003d62305c3139dbe354e0b74bdaa5` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/math_bitwise_366b8_366b8.c` | `b258cd5612ee0f206efeaa660807a4e59af4017fe6ef543bef0cfe3e8fceef27` | 692B | Tracked file |
| `c/math_complement_2420_2420.c` | `cb204feba92bab64e19f70f74779dca7722c5541e4d45221257d54de1a8d1c95` | 704B | Tracked file |
| `c/math_complement_2430_2430.c` | `f8af8c65ca920c370be4619af894e969ab733e7c88064d27b746a402b9b576fa` | 709B | Tracked file |
| `c/math_formatter_3e9a6_3e9a6.c` | `3e9affd0e348211f37a82cae44c39101c47d5fd8b45bfea3b949ea568204adbb` | 1.5K | Tracked file |
| `c/math_primitives.c` | `ac23154160b5454176d1808fc2102cb2aa3680d71964fc9711f3da61fcd8ca23` | 7.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/math_register_344da_344da.c` | `a5fc02bacc15fae2f73e3040288872c4afdd5193da14092562d3ad6d6b115e86` | 663B | Tracked file |
| `c/mem_accessors.c` | `196f29a5ea06867bc8256145e622bb1057c162f9d745c46ebd2cbf354328b8a9` | 10.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/mem_char_533dc_533dc.c` | `b970f79f42aabacc0dff26193123148644957c95a82d4f5a686e78ec4f2d3b68` | 1.1K | Tracked file |
| `c/mem_clear_5286_5286.c` | `49bd87779faa43aeda55af81b602fb912d53130d3a015446606cb2bd2ce7f6df` | 657B | Tracked file |
| `c/mem_flag_fb60_fb60.c` | `21226edfffd685ef16ae065ae4420d1a5cd2009abb96ea1d36f39cc5339bb3e1` | 627B | Tracked file |
| `c/mem_mode_23710_23710.c` | `695a7f50bea21f1194732c02c1352fc54bd54a3d4e862329b3008006aa45364a` | 658B | Tracked file |
| `c/mem_read_277de_277de.c` | `7f1d337f5e47eea427b53eab5babeb87e34b9208bc57153d610d9ed120c2549f` | 856B | Tracked file |
| `c/memcpy_bytewise_unroll4.c` | `8789bba66067458af6789c3e51373bf6c9ec37f5d08e88b124156542220a630f` | 2.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/memory_match_accumulate_583E4.c` | `e0fd57cbfb174131c7b3312f23d6e22375f326536ddfd1aef939f0e300e0a7af` | 2.3K | Tracked file |
| `c/mod32_signed.c` | `3d0316e52b698213254aebc75b33ea781161e70f8eeebd2395bcd9233f252300` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/mul32_saturated_231c.c` | `66a7d2aa2e9fe7573a11d9d13bc1820a04d3689d74115e10fd3f6239428642be` | 784B | Tracked file |
| `c/nop_delay_40cycles.c` | `3775f576e0cd7224939f6cf1874adbabb933a9cfe6e133a9205391204634418d` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/nothingFunc2_5ee7e.c` | `dcfbd60d911159a90b6d99b6d071c5df2ee75118f12ace07dcbb7895e68232f1` | 1002B | Tracked file |
| `c/o2_lambda_subsystem.c` | `02461ce0b22af16769260407168e4a9f417edab653baa18f9b5a381ceb4d8139` | 19.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_find_0x643D4.c` | `a0dbd20161d73e800594b6fe85b60deda82d9792d7152416b187c79623c95a3b` | 1.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_find_0x6443E.c` | `b4011cb48b50f383ddde201117cfc75519545bf5954299497f34e76480ed6b2a` | 1.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_row_update_0x64258.c` | `9c89c83708f8aaf38336bdf14d6e87659021432998cd28ea35d4bf3abc5633d4` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_row_update_0x64418.c` | `fa8398cb1172d3e108eee48ce118ce81133978c5e1d82df460b94d26f1ae8e5f` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_row_update_0x64490.c` | `bc397ebc85b240cadac142d1a3f779c5d13b79270604a9d4e420f8377d7ca98e` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_pid_handlers.c` | `6e58b7885db710273421b3252b1d99e9a9be270a299871a80cfe0e7bff81b90d` | 24.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_632D6.c` | `8bb1f2a90962217f21bc83c7d47621c7eee72607c6410b0d9caf4dde391ccd49` | 2.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_63312.c` | `8b570f8b33fdbe0bd93a10bc887704fbe8b240f70b2efe0f5508f8374a20c88a` | 2.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_63834.c` | `d8821d6af3eaad43b9606a2a20ef24604c27bc4561899ae38dfd58d9c5df8ca0` | 3.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_638A6_638a6.c` | `f37542f082b9265eaecc905c0c3d60c236f6229cb0edcd1f9a13cb149a082780` | 906B | Tracked file |
| `c/obd_service_handler_63A82_63a82.c` | `8901492b49737b669a82edf170f1eb7b1b2289d22133cf38e4db8656f41759b9` | 906B | Tracked file |
| `c/obd_service_handler_63AF4_63af4.c` | `e0422717d8eb18ac23b93e30557028f59b56c11483b981b1b73f820eb4447067` | 906B | Tracked file |
| `c/obd_service_handler_63B46.c` | `902a4ee6963a1ff37fe2a4d0ebefbf086d9ff07d4a9022c26e50bb4fe03362d1` | 2.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_63BE6_63be6.c` | `cbd5ce83de63f2fb76bb89d8e1b6cbd2ff6ad03ea9d1430501ee529a9d7cbe3d` | 906B | Tracked file |
| `c/obd_service_handler_63C66_63c66.c` | `a2141f3b25a26e22dead1f8ef7c17f8d6a26f44025a4699b0bce3a8146f592bb` | 906B | Tracked file |
| `c/obd_service_handler_648B4.c` | `2ee267d0a5479238cfa9931b9acaa5b6c946987895729c29cbdabc3b896f1aeb` | 3.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_670E6_670e6.c` | `ec8c7bdcddfcfe84ff6d6a91cb5183249ca97f64c8f3385f50c69adf7b560834` | 1.1K | Tracked file |
| `c/obd_service_handler_685F8_685f8.c` | `a644780864a1095c8958fc774c222a926ff474ff782ee3ff033c47b30beb7a9b` | 945B | Tracked file |
| `c/obd_service_handler_68656_68656.c` | `52af07081b68ade0326a2942d7f2fa7e1049bded7da5f7533ae6173f20cc8680` | 945B | Tracked file |
| `c/obd_service_handler_686B4_686b4.c` | `9f5837f95d4351b78e7eb0ba5638a72f3ab36df77cfe9c0fa2fcb4c536a06f81` | 945B | Tracked file |
| `c/obd_service_handler_68DD4_68dd4.c` | `074e047f98019732abf79617327b1ef0044c0da889d9662c5c89c09e33ff4c3b` | 1.5K | Tracked file |
| `c/obd_service_handler_68DF0_68df0.c` | `27e5c4646d1e574b4efd5f06b6bc7dc0c257e663362a0d9b3af56a083bb3c913` | 621B | Tracked file |
| `c/obd_service_handler_68E10_68e10.c` | `8fd6584fbf537b78067bfc0e8abddec3c6b9b9fcd2d165dd18472336ecf5d4cc` | 1.1K | Tracked file |
| `c/obd_service_handler_691A0_691a0.c` | `5846f0d413419f21c6de99bbbde9bf30bfecbff4e74399267d59d34bd14f965c` | 1.0K | Tracked file |
| `c/obd_service_handler_69524_69524.c` | `959373ede96c2a534c74a54b762188d4e81d012d73b54eb8d182e8bbdcb5e078` | 766B | Tracked file |
| `c/obd_service_handler_6954C_6954c.c` | `3d42f6cbf22e107d144e75956449346ecb78c309867a7c1790ec307e79d1f67c` | 749B | Tracked file |
| `c/obd_service_handler_695D4_695d4.c` | `8345a914967a199eaa1e3808e09b484be1409880c1d6513b0a17c4d0257a38e3` | 627B | Tracked file |
| `c/obd_service_handler_695E4_695e4.c` | `fe9cab95770f5f650e56e18df8691ff169263d6f957129c4e487954fe8233d94` | 658B | Tracked file |
| `c/obd_service_handler_696D4_696d4.c` | `75d221fd4a7418ad0e5b55de57c203125ee6e87192ef70eae551aee82f850810` | 641B | Tracked file |
| `c/obd_service_handler_6B0A6_6b0a6.c` | `64f0eae3a948ad356000cf83c53ca74bb843cb3178b57bc9a876e51bfd03d86f` | 796B | Tracked file |
| `c/obd_service_handler_6C166_6c166.c` | `4707eaa4d3570442c9283a3eb11efa1370156205e989336e372f5f992a49ef0f` | 767B | Tracked file |
| `c/omp_control_task_1825E.c` | `0fdddbd091ef4877dd3a4e4d24227b1c87b733b157f6b84d5c5de165c2a2b733` | 9.6K | Tracked file |
| `c/omp_rotor_overshoot_detector_18CC0.c` | `4812b056e063b3d134efb4dc64146c89509f6312e17c9a287ce11db573564e0b` | 5.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/omp_stepper_waveform_driver.c` | `3c75ace88ff2b8bd629b5e370fee178af8a86c78d7a5e9c0d9984fdb23cc0fc0` | 7.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/omp_waveform_state_machine_18860.c` | `a51fe8e9a2dbe91b0cb7948d81573c84db60c189baa5b57a153797403d09a7ea` | 5.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/osTaskScheduler.c` | `486d9335110f5007c5716bf4f914e25bbb75c504a8952558ce099347a0c4b645` | 9.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/output_per_rotor_ignition_dwell_0x11218.c` | `3bc7f0e08a0196c89602f627110403b8b7e50809acf98aa9383959107ee09c8a` | 2.9K | Tracked file |
| `c/output_spark2_0x8E20.c` | `7beed19eba9b3be105573b0154a0484cd45e7679bc7e030d4de4a8280bada53d` | 4.6K | Tracked file |
| `c/output_spark_0x8DAE.c` | `a319a64d44e899a7c827f983a53e045b7b2ac91eac51980e4677ae169c3856c0` | 3.9K | Tracked file |
| `c/output_spark_0x8DE6.c` | `b5c7ac9e0f1d8f1d762882be3400dc06d988dbaf5fa8e22389998e6dce98496b` | 5.0K | Tracked file |
| `c/port_bitfield_check_sensor_flag_32174_32174.c` | `1491e5511c041ef99d6c7da24340bb9cdcb2e350973ca8ae00945a49cc3cea4a` | 1.5K | Tracked file |
| `c/port_byte_copy_simple_339F8_339f8.c` | `4290e40b473769bb7554357627cb6d7445eb64d30e79ed0d0382a9735f0a36fb` | 796B | Tracked file |
| `c/pressure_delta_monitor_1AED2.c` | `db4aa24ae09e6e94a48820977e72a9c4855635cec8313f1dc61f5547b1cb4f68` | 4.6K | Tracked file |
| `c/pulse_filter_done_flag_fc9e.c` | `f131fb381f511bc2b4c6d221be70ee3821f3caba0139eb43770c83ee5987c499` | 664B | Tracked file |
| `c/purge_control_state_update.c` | `39a45cce814b0432cdf229ca74ac5f1e74c3deca55c4a8c6f1c90879d31564ba` | 3.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/purge_flow_counter_init.c` | `39abc3d6f97b2f2e40c495ed575738ef6e2dd070da65eea43d94f1d811451ef8` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/purge_flow_decrement.c` | `f0e11c738461320781f32db5f92782556e72732fb1b8911cf57f689785d06006` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/purge_state_query.c` | `9a8779a2ac2a7f92f03a7c355b1e1151375cc0955e3459d6996bacd1b2d00a73` | 577B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/radiator_fan_relay_write.c` | `0215f20f419235ce40a01cdc4bbf5d2ce98e6b544dfa12f6cff7e4869ed6307d` | 605B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ram_byte_copy_2A300_2a300.c` | `e4dce1b9978e5c537d9610ef9eb3201d281bc4baa166d118442d975b242a291d` | 788B | Tracked file |
| `c/ram_init_zero_29FFC_29ffc.c` | `a34bb35bca4d98a0834b321946fd5f4458745685e7c3cc2b5c5c46109783ea10` | 636B | Tracked file |
| `c/ram_word_copy_2AB6A_2ab6a.c` | `fad6aa504a2dcf369428e2b4ad824260603799b5b5e76003aea81740bb70526c` | 812B | Tracked file |
| `c/req_queue_69602.c` | `dd14b521b17e7cc72321b52f3e5024e3cae7091bd5469a9827d513bb7fe9ccc4` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/reset_handler.c` | `6ebbb32b9219f954c398fc1500fb2b58144c208a572c607da167adb26c079c37` | 14.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/returnDwellTime_fp_0x1120A.c` | `9150fd7d186cacc952b8cbfa3a30df087988709a39a607ab6269f53c5997b594` | 2.3K | Tracked file |
| `c/revLimitFuelCutInit.c` | `c2dec9f1642048d238f76fd048cdb5d09f5e7c2b5a0f2eea5aa656b7ceb275df` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/rev_converter_552fe_552fe.c` | `be73a91ffd13b8fb7a19449edec2b58d911584cbe550e723a7842deb89740b3b` | 868B | Tracked file |
| `c/rev_limit_0x59440_59440.c` | `e02b5880bff81e2ecae36917d5b25f3fb6ce9909e1aee6d7330a629f13d5c07d` | 1.2K | Tracked file |
| `c/rotor_sync_gate_state_ctrl_2100A.c` | `777934a51455d3a96617361946d5fae18e23b55d2ebd5d956d74182540a9d002` | 7.5K | Tracked file |
| `c/rotor_sync_position_detector.c` | `6e336c56db4fe7fa60bc9663f81076ddef0d568d7a51727dcd1a3a5246ca73aa` | 5.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/rpm_rev_limiter_47AF8_47af8.c` | `c7b2267f7ef015cf6ad9b5c5c666dbab1a154c8c24d19bdd7a06b85d7d093091` | 1.3K | Tracked file |
| `c/rtos_task_register_a140_96de.c` | `33ce5057dc53e9c61220c888601bc9651749989857bcdfdb4d68ea929c519b01` | 743B | Tracked file |
| `c/saturated_decrement_27DD2_27dd2.c` | `6d724ddc05bbbee760dc18a47fc9887f4bcf14d059e7ba05bcca5baa7af9d3b7` | 1.5K | Tracked file |
| `c/securityNotUnlocked_56910.c` | `59232db6c228bd306c66c66d7f26d7fde219da4c8fea583be39c8571660ba1a0` | 1.2K | Tracked file |
| `c/security_access.c` | `e1397dba4cf241c10135822f0aabb500c909f72c40197144058d1c6c4492a921` | 35.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/security_access_aux.c` | `a3df4d81af976fe9dd2367396e6b71f6e36f8953b773655cc0d731120f915913` | 21.5K | Tracked file |
| `c/seed_mixer.c` | `bf6c0551da52b3c54a1261aac2e0237788178be02b8a6e8d49caa5e14ec41f86` | 1.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/semaphore_post_4C880_4c880.c` | `d7ddbf97cb55b4d8a107beeb1a52f5ab9140e71b73c6b5815f11274ba7df011b` | 637B | Tracked file |
| `c/sensor_check_float_bounds_adjust.c` | `73f31aa8f7135098f3e5a70881c4430964ffaf2449c9d3d6d5d3fe679321e771` | 1.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/sensor_extract_6096c_6096c.c` | `7e6fac3496c1f9ea61b68a2b49a6cff6279b8eee410cc69a1c3840620dfbc452` | 617B | Tracked file |
| `c/sensor_latch_ch0_72b4.c` | `b61e36110a307cae21c1f9249860870f2bd8d85028f219ab8e8b631bd387ca0d` | 724B | Tracked file |
| `c/sensor_latch_ch1_7354.c` | `14b93ef64dacc9f6a125473e357c01776634fe74a1f33d602f51e86edc3e0466` | 724B | Tracked file |
| `c/sensor_latch_ch2_73bc.c` | `47024f1dd123541a9497605c6ca9a9af35de2475c05bcf7cb2d44c1000248da3` | 724B | Tracked file |
| `c/sensor_tps_delta_lookup_store_12e94.c` | `4d8ca12d5d2c097028f44392e2a7f8f7ba801e078123fccfaebb8a84e1192dc5` | 891B | Tracked file |
| `c/sensor_wrapper_4f216_4f216.c` | `90f81e1e8fa61a16a37ced13c897f69d9aa00aa9285231351128a20aa596cac8` | 1.7K | Tracked file |
| `c/sentinel_equality_check_5687A.c` | `2c571c5b703e1b06f923c35656f442c654b5bbb8376e3d6593cacaec798679d9` | 1.4K | Tracked file |
| `c/setAlternatorWarningLight.c` | `757b3f95c9e5891ad95a577611bf5169b88ad099b4a90b5de9a7d4742c068a87` | 2.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setGearBools_a_2cf80.c` | `85bbb5cdf3c922294d5209cbc333944b2f15408a222ba25d8a9681455660fa5e` | 3.8K | Tracked file |
| `c/setImmoCANTXData_369B8.c` | `c3437c996e734351f49f82ceb2138ee633b4170c55f189d1a9465ea6a1e9fb91` | 2.9K | Tracked file |
| `c/setImmoLight.c` | `39ebd4921d163eb210ee2532e60b2210fd59d853bd5a2d544715f5db744aca5b` | 1.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setMemInsideFUNCto1.c` | `8495261806b1e2b8777c12f830292595c18f1594148124130a8a5def8190b1fc` | 585B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setRegister_REG_BIT_VAL.c` | `6f9dbe798fbc4128ccf0d335a827511e6723c581a50db491bc261b9a75e26664` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setRegisters_4d2e.c` | `0c7b0a69ff7b96f2aff7a3e1eb674ed473a9f792746c91623bde5c454609af08` | 652B | Tracked file |
| `c/setSR.c` | `eae2e3a8936623078a01594ab338c68dff65e26760b33b4505bd55aad8df0ad4` | 4.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setSR_PARAM.c` | `56bab8d1daad2d01175178ac53e7ec1d3be836bea8543b0f35fd3542b47987b9` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/set_intake_target_flag_23FD0_23fd0.c` | `0fe1b0805fe8485070b389326380d9b54672b1bf7e31b59d1123d98d06d51a1f` | 672B | Tracked file |
| `c/shift_left_logical_r0.c` | `bf12b8846799ade8d9eb9bc8b10876cdda0576a479b6c50ab615fac0fcc8c893` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/shift_right_8_r0.c` | `f2adae0ba55c8c190f73a867df7403d27cda7ed228db2e23d9a4df2a471b5ffc` | 1.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/shift_right_arithmetic_r0.c` | `3becd54cd021015d718a5d9581e0c5c18f6a43816b2e9cf71bfcc530d375a22c` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/shift_right_logical_r0.c` | `abbd085e7dba393554ecc477f8c3525b3a04566511ec96975b8ffd36fb6b9ea8` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/spark_output_enable_fault_mask_0x10DC8.c` | `a98c696195ce999ae02264f2e5ff4362ba0ea56c83dd3358c32c94d7658ad611` | 5.7K | Tracked file |
| `c/split_selector_decoder_48C12.c` | `e0595630405959c50e4d870b210b8c2caba06d6920c8407a5c2ff7f4bdff490f` | 2.2K | Tracked file |
| `c/split_selector_state_ctrl_487DC.c` | `ecf291ec65c34fe8791fb5f2e59dd621ae4b6839f6e9687b3972adcdbbf3a1e1` | 9.3K | Tracked file |
| `c/ssvControl.c` | `eaebfe5625dcbb77a131165f5ed39c79d245c17ca22750cd14fba398187c8feb` | 3.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/stability_control_0x5957C_5957c.c` | `d23535a2fe1eedb72fe8603f2b778f1e84e035bf5a629b1e822c9c3f3eae5c2a` | 1.2K | Tracked file |
| `c/state_reset_multi_word_2786C_2786c.c` | `6cc26c982d700db47ce5ebd407686c244d3bacade7e0d4be7f82b073aa4a1d2c` | 2.4K | Tracked file |
| `c/store_knock_learn_buffer.c` | `fbd2aa36fcb7851556b5ed68d141bdbbd2daf6cd6572efe614ac1e9476834c04` | 7.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/taskEndRoutine.c` | `ca28384f97eb730d5e29d1e90431ce0b0d86b4614af7033c33794b6d6db7423d` | 4.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/task_execute_by_index.c` | `a433cad7cc85bce936bdeed450ff31bcb2c9c6659d11ae7628ce98e13cdc3c76` | 6.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/task_flag_run_C.c` | `b3bba6c41b80255a326d45bd486a8a2572f78dd8bf7bd17fb09ad0a65384f70c` | 2.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/task_full_context_save.c` | `bbdac4e17b6fa65e3756aa86b39b95e7ae6c8c9139a6174a7e9d2df3e9bc3e6c` | 3.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/temperature_gauge_0x5AA5C.c` | `b2774efa881d7673fd62c8fd53d94f900c3a2bdbf2121f6b5885afb556864b51` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/threshold_counter_inc_latch_41cf2.c` | `4f1ffb907740aa63ee19a74b417bf74228c789b80935116595950f5006394315` | 608B | Tracked file |
| `c/throttle_position_sensor.c` | `2ffa3c218a91536929f2f7a52a34a3173f8b7f22e7acfc278708c34ab17dfe05` | 6.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/timer1_init_and_start_a6c0.c` | `e87623a4305133750ce5b4d51fe7851832b3ab26835299c8b7820bbf95283068` | 1.7K | Tracked file |
| `c/timer_state_debounce_latch_4efa2.c` | `6214a7e1cbcf0dc4710c5c84aae5185cc5dc302c7ac380dee7bba2ce8ef79611` | 715B | Tracked file |
| `c/timer_xor_shift_operation_37328_37328.c` | `b3988fe758ad8e75cf3376ab55fa4bc37a2f91259df9919bf5699b3d609b6aab` | 1.5K | Tracked file |
| `c/udsResponseRelated2_6772e.c` | `9c4c679fa87d25d81788d5d9cff066fc629795a7a7e6cbe25a14fca7afc63816` | 748B | Tracked file |
| `c/udsServiceResponse_66a74.c` | `3ef5dfb58b5ad15d1225d15ba6b97affbe925a1a7dc80da9c06764675b7afa8b` | 686B | Tracked file |
| `c/uds_mode22_data_getter_53770_responder_54e0c.c` | `3cba90a93ad79448edecec5262e7e779ab7152196b4886ed46525ccce3bc5305` | 856B | Tracked file |
| `c/uds_mode22_data_getter_53b28_responder_55020.c` | `630b91c2eef5eaf49b65cad4152804073619141bc73becf4baa7d1d378dbbe25` | 627B | Tracked file |
| `c/uds_mode22_did_4a_getter_55034.c` | `3637c201097117e3ebd41dafb1f284a75b8342c01602e7497f2a7d46d4fe4112` | 765B | Tracked file |
| `c/uds_mode22_evap_purge_responder_54e22.c` | `0cc1ac4553f1d3898841d3bb872908046c7e210745efafc9471a77529fd816ca` | 707B | Tracked file |
| `c/updateE2RAMBasedOnInput.c` | `a32f8af00398ecbc22a54f0c7b0a22d2cb05eb34f267a3fd2377a6bf32cd2b0d` | 6.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/updateMemoryAtAddress_8bit_ADDR_VAL_3ee58.c` | `b15545d72ec796215ff809f8876dc37452753f5294748307da94f8e2b5a105a8` | 844B | Tracked file |
| `c/util_shift_467a_467a.c` | `4c47b2079d4b66664fb7100b8a3b148944fab8c645bbf288bca0f752e27a5822` | 950B | Tracked file |
| `c/util_taillight_59d56_59d56.c` | `0cb212577905f49f7a40d907b728066a1198658a2326c26d39c325ff3000df52` | 760B | Tracked file |
| `c/vehicle_speed_sensor.c` | `aa7dc9697a545d1423febb11e4546c630a30e7f4f1f2e68f9a35ce589be45cf1` | 5.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/verified_addrs.txt` | `16e0ed69f6cc1652c657f3fd1f150bfedb1c25387d42955384495c69ec205aaf` | 17.5K | Verified-address ledger (C lifts proven against emulated ROM) |
| `c/vfad_control_35BBC.c` | `55785deeca85baa930739a07c7e98638d0468d2c87c0e930ea65d387320c9ddd` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/vis_intake_control.c` | `8adb19bb71f837dad6ca572af015e32ff1190f62e49c80174ec62215432c3095` | 4.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/wankel_sequential_inj_4870E_4870e.c` | `4326e3d3ced6e5c69aeef977488ae8234a1284a6f6556c5b1b49a91737b17780` | 824B | Tracked file |
| `c/warning_light_0x5AADE.c` | `af4b45c9a16aaf56d50a067a03e43e7eb475ed5c12acd50609dcb9def7a6f827` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/wdt_disable_1380.c` | `c9cab559b7a65fbf9fb3e013fccff0737dadcf07fa495e4cc878bf378e0ae709` | 1.2K | Tracked file |
| `c/wdt_disable_and_set_timer_502c.c` | `118bcde78ec3aa43715e69ee231e0dab5494c9742a5c0a46da43e06fcbff66b1` | 926B | Tracked file |
| `c/whileLoop.c` | `38344098f7dbe1ef25d7c390cb1656d1db54f4569879652713f53a53cd679d19` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/writeToE2RAMArea.c` | `37a489d2d893d180c5374d426ff643360afb2e0edf47d617ce3ee253e3e38296` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/write_o2_sensor_trim_12b54.c` | `1a2f11eee084d9f17d05f8e66cc835caaf665cefdc2639bde846b04661360a55` | 810B | Tracked file |

## c/tests

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `c/tests/smoke_dtc_functions.py` | `4757f64f4b1a909333a26e3de87b82354824ddc5c3670951eaec018ebf2458c9` | 8.3K | Python per-function behavior-equivalence test |
| `c/tests/test_2DLookup_FP_16bit.py` | `dcb698faba3ad310ffbf6f5420183fb8c9108d65669de1caa5274ddde0aefcf3` | 3.7K | Python per-function behavior-equivalence test |
| `c/tests/test_2DLookup_FP_8bit.py` | `1722bd5a94aa4e2bf454f621d3ffbe890147e6ce51a9c62bca93ac88b72164d4` | 3.5K | Python per-function behavior-equivalence test |
| `c/tests/test_2DLookup_type0.py` | `623d852efd22f84e66b95425215d644e4f7585df613d08a2a6afff71fe428665` | 7.6K | Python per-function behavior-equivalence test |
| `c/tests/test_3DLookup_FP.py` | `cdc2f5b04abc516322e0389c0b7d0b72c0511a70dc53c17f121f53041f62b7c1` | 4.3K | Python per-function behavior-equivalence test |
| `c/tests/test_3dlookup_type8.py` | `98e9dc99a9176edff1adbbe698d9ee7e2d15994c7d17763313278fcb50462b7b` | 4.7K | Python per-function behavior-equivalence test |
| `c/tests/test_CANSetupSomethingDifferentBasedOnBit.py` | `e4c9148280c556272a1aab0438e0e2108cce5a5a7fd849e34614fa502000742c` | 1.9K | Python per-function behavior-equivalence test |
| `c/tests/test_CANSetupSomethingDifferentBasedOnBit_e074.py` | `474d286fccb062bb3fc6c3127c1963c81380a1a71674968c4b2dbb86718d797d` | 4.3K | Tracked file |
| `c/tests/test_DSC_checkIfMode_x10_a_2c5ce.py` | `3bc676ddcb6d079dc296acb26de35d425b4cebba8e60a38cda1bcc286bc161fd` | 7.1K | Tracked file |
| `c/tests/test_E2IntoRAM_0x38F58.py` | `08fd4678ec12d96760e02c61ff935ae8e98c6ebf3c3bd90c2d919030aa45273b` | 6.5K | Tracked file |
| `c/tests/test_FUN_00007eca_7eca.py` | `381b2e688deeb900ec582fcdcb10e4f6c4527bfb720c5e8155c5ab8871900309` | 10.0K | Tracked file |
| `c/tests/test_FUN_00009016_9016.py` | `3db225c1eb321b2d4122bbf7fff2a715a607034c329047c4ccdd61d30709aa6e` | 4.6K | Tracked file |
| `c/tests/test_FUN_00009f12_9f12.py` | `e7e29d655951792cb130c4d3c10d1d665186488b68404fd98fe08cd307cd34bf` | 2.5K | Tracked file |
| `c/tests/test_FUN_0000d2e8_d2e8.py` | `9fdd6e2a80302ce1643ffe9d3f70392200788c496f795516c9299ac1ea5c7361` | 4.0K | Tracked file |
| `c/tests/test_FUN_00010a8c_10a8c.py` | `b1dbb40497ee3bf714d3dbe0e43579f3786d7669bfe01a01399ec4573f4b0a5d` | 6.8K | Tracked file |
| `c/tests/test_FUN_00019a56_19a56.py` | `13edc5ff813ef7a5042da06a92d8b90d41b603d8df057de9f1b89c45ac914475` | 3.8K | Tracked file |
| `c/tests/test_FUN_00021730_21730.py` | `80d3cb99ec54761e411baff58be7a9ac10b174a48cd95c9a6dc63d5216fa46bc` | 2.2K | Tracked file |
| `c/tests/test_FUN_00025b26_25b26.py` | `b90bcfd45ae118cf822fae9870e2ca3e0871768b431be066f68ebca20deb6fa8` | 3.8K | Tracked file |
| `c/tests/test_FUN_00026e14_26e14.py` | `f4a38ee4795265c0731b6636c8b429bcaac7e60101ef9f393ac5d53e6b2ec642` | 2.2K | Tracked file |
| `c/tests/test_FUN_00028034_28034.py` | `9b3bd5551c3e4faaa76c6cdd0687435598165a40f9839c7c7698c7950b41beb3` | 2.3K | Tracked file |
| `c/tests/test_FUN_000288fc_288fc.py` | `bd26240001d5130ca79e1da742e5d7124636cdf10f18bad8a4ca31f635c177e7` | 2.2K | Tracked file |
| `c/tests/test_FUN_0002896c_2896c.py` | `2dc6e2a6b422d45bdb6ab8c095520421e07d758a3f2f841f6fa477a471a30b2b` | 4.0K | Tracked file |
| `c/tests/test_FUN_000289f8_289f8.py` | `63261b46a5caf98321087cb9897bc7297f2c80469d23742d1a99279a335fd4f7` | 2.2K | Tracked file |
| `c/tests/test_FUN_00029ce8_29ce8.py` | `c4e1c29bb7a92ce96dc0f342836512a3f3e624c14197b43e08f2f78110d13a5c` | 2.2K | Tracked file |
| `c/tests/test_FUN_0002c15c_2c15c.py` | `c45bcc6749358ee543d44def4a9f773eebb02d66e316dc6348b2f7ce7a7e9842` | 3.8K | Tracked file |
| `c/tests/test_FUN_000300b0_300b0.py` | `8a1de82c8fd017f221b941dc1063195e5f52172ee4e1bfedbe44b0782e801629` | 3.8K | Tracked file |
| `c/tests/test_FUN_00032e0c_32e0c.py` | `ba90a52e3874879b8da666b1470b9d4d41e8b629ca1b73e61e7c0fdb311739ce` | 3.8K | Tracked file |
| `c/tests/test_FUN_000330bc_330bc.py` | `dcbc0000f64fec67534c32777b460cfad13cacf367736645fb7e519126a5de87` | 10.7K | Tracked file |
| `c/tests/test_FUN_0003397a_3397a.py` | `a050d0fd1ddff4b11e6f21ae3c11dc196660d91dc6430288b7c5407e38b2632d` | 3.8K | Tracked file |
| `c/tests/test_FUN_000367c8_367c8.py` | `86d26165863a360bea10875c8cc6f8d9efeb136556e4360a95a8b2dcb3e4f53b` | 3.0K | Tracked file |
| `c/tests/test_FUN_0003697e_3697e.py` | `ad9a54a89aa71ec2c5cf303d4bfb827ca9cf097422707e19fbd98e7ea948971d` | 2.4K | Tracked file |
| `c/tests/test_FUN_00037010_37010.py` | `5c7a81804ac69db9811918957a883915351657caa92e95e67f7d24a9c46ec2e8` | 2.2K | Tracked file |
| `c/tests/test_FUN_0003d244_3d244.py` | `aa2ba60a11251a50755ce2e0508b43b465d40f66d829cf5ec67001416f1a3c67` | 2.2K | Tracked file |
| `c/tests/test_FUN_0003e888_3e888.py` | `9e1d9007ceb860d0577bbd1f1ff6dcb51e29447bc6662e5b3aa206612e02f415` | 3.9K | Tracked file |
| `c/tests/test_FUN_0003f074_3f074.py` | `00ee817c103565784155c27a3a90bb204923a00c7f16cc5732bfb8641d8b38ae` | 2.2K | Tracked file |
| `c/tests/test_FUN_0003f224_3f224.py` | `011d4bc0c3b80d26d98507789d2e5f6dddc839da527d489db98c13bbd7789c66` | 2.2K | Tracked file |
| `c/tests/test_FUN_00043344_43344.py` | `f002f8b79bc1c69da4a0aaa7d0391298d9c2801b3b4b53d13581b9f49cf61674` | 2.1K | Tracked file |
| `c/tests/test_FUN_00044294_44294.py` | `36d40a151252af1b8aabd37194ec6b892991a8b3b107d05939cb06a6d968e2a9` | 2.6K | Tracked file |
| `c/tests/test_FUN_00044ab0_44ab0.py` | `bc018c16d7f4c40b24e1802fd95e43d6a559da7b6a33a814e21d998397dedcb3` | 2.1K | Tracked file |
| `c/tests/test_FUN_00045052_45052.py` | `438d0f92ca8b674090c05d06aee8726c30c1339712386c0672e73df4c22a083b` | 4.1K | Tracked file |
| `c/tests/test_FUN_00045b4e_45b4e.py` | `6582ad8a0a78aeecddc94b7d6c9a6303a277e90dd4f217731362100d15db33b4` | 3.8K | Tracked file |
| `c/tests/test_FUN_0004980a_4980a.py` | `72a41dc3492bddf88fe0375ebf428a45a0b3cdd9f3e58e9a554982dbca98bdc7` | 2.1K | Tracked file |
| `c/tests/test_FUN_0004c5e0_4c5e0.py` | `dc0c2209971fe5d09fa73370a62e5176ddfaf6e1679eb1a7569acc251be4ff93` | 2.3K | Tracked file |
| `c/tests/test_FUN_0004cecc_4cecc.py` | `4e97d6a8fb96aab8945f59a38819151eddc3b0547017c20b9b8b89a8499ac9ca` | 2.1K | Tracked file |
| `c/tests/test_FUN_0004f3c6_4f3c6.py` | `1b4444d516362efdf7477b242bbe7cc24db643dd0d59af484c41ad758e3c4f2f` | 2.3K | Tracked file |
| `c/tests/test_FUN_0004f6f2_4f6f2.py` | `047b50392714c57ba6ca470e307ae9214c6e4d044c7ef664fd7c368aceb1f280` | 2.1K | Tracked file |
| `c/tests/test_FUN_000508c0_508c0.py` | `28b7fe193d001d9db575647aeec499e4237dbb3098aacb8c5f3493d35b781e2b` | 2.2K | Tracked file |
| `c/tests/test_FUN_00050eb8_50eb8.py` | `b28e777dc4ac1df0c6114b61002a0371afa4b09ef23582e639d8665c501feab6` | 3.8K | Tracked file |
| `c/tests/test_FUN_00051314_51314.py` | `cb34949a09088e5220859d2cfba4d08cde429d7a5fdbfcd3f08b2d9f90305a1d` | 4.0K | Tracked file |
| `c/tests/test_FUN_00051b18_51b18.py` | `4e6ff3a8125b5e575f7b5a873364d23192d87e5bb71dba824c404d54d16f6bad` | 2.1K | Tracked file |
| `c/tests/test_FUN_00051f74_51f74.py` | `d488950fceda6ce65b297858926698f7668a8660f68514f1202501aac9c423a7` | 2.2K | Tracked file |
| `c/tests/test_FUN_0005201c_5201c.py` | `05de87a27a1cd8fd5b60428b5e77254f004352f0429be09961897f088836fd6a` | 3.8K | Tracked file |
| `c/tests/test_FUN_00052854_52854.py` | `e72e281aabcc04a76535f8eecd00f43f885b5697f9ceb567eb96a611088fdd33` | 3.9K | Tracked file |
| `c/tests/test_FUN_00053770_53770.py` | `e4dff3151fbc4e196e04620a80a069f0c63f834a54330d440b49ce723c94c86a` | 2.2K | Tracked file |
| `c/tests/test_FUN_000540c8_540c8.py` | `83ecaf7789d7fd27aab6d99b7e0520e60120f88c82b31ffb1fbfa434825d44a5` | 2.2K | Tracked file |
| `c/tests/test_FUN_000546f8_546f8.py` | `4ca83b50bcafb897af30a8b5568151c956831534591bce9bb1a308a2a484de71` | 2.2K | Tracked file |
| `c/tests/test_FUN_00054d14_54d14.py` | `764e8d08a97ee5a73570503385a33a2c8f9e48f4698c2a860f967b5c6ce4050a` | 2.4K | Tracked file |
| `c/tests/test_FUN_0005698e_5698e.py` | `147948c935c77059185c350ca7162ba89563f72dd3317796f78a6e974f78c4fb` | 2.2K | Tracked file |
| `c/tests/test_FUN_00056acc_56acc.py` | `7325baee2643aa4edffd86a51d8ea7e32652c8514dec06a9216091f4cd2a8fef` | 6.8K | Tracked file |
| `c/tests/test_FUN_00057058_57058.py` | `f99bfe2dc4ddfad2b31bb16c5fe6aaef76aaa9550dc6c73b0e9bf5012b08e9e1` | 2.1K | Tracked file |
| `c/tests/test_FUN_0005a3de_5a3de.py` | `3c4022521b762c343c8162bf7a6016cfb734f4eeb01388e6c7ca5d0178a966e8` | 2.3K | Tracked file |
| `c/tests/test_FUN_0005c740_5c740.py` | `a90a46fc9b804f6e4ca9f562051686c32676ff80b3353dc2279daf4f29fbc0a0` | 2.2K | Tracked file |
| `c/tests/test_FUN_0005c814_5c814.py` | `562c4db83425c8fdf3c2d507ceff2b91245d1f74accae8273fd7728d1427e9ab` | 2.2K | Tracked file |
| `c/tests/test_FUN_0005ee86_5ee86.py` | `a5dcc16a292009f15d081b988bbbcf9054c20c8eddf9024ff25e0dba73f90080` | 2.1K | Tracked file |
| `c/tests/test_FUN_0005f00e_5f00e.py` | `00063d9ffbeb9beceb5810a6d5e290e4fb008b742bac4e79960a2f838f7fda17` | 2.3K | Tracked file |
| `c/tests/test_FUN_0005f826_5f826.py` | `7044aa663e359e2f252066a315bad753bf2ab1ed0a2a9a0971f29f64ee024527` | 2.3K | Tracked file |
| `c/tests/test_FUN_00061208_61208.py` | `301f527672d2fe533b7592d0378081bcd6d6f53352890d2509a319def1d97545` | 2.3K | Tracked file |
| `c/tests/test_FUN_00062288_62288.py` | `e7ea4d23ef441215dee3195ef2bde646b531245e98769c5733a9da808ece280f` | 2.3K | Tracked file |
| `c/tests/test_FUN_00062344_62344.py` | `39253939e261299701441658dbeb095cebfdfa02e3463f343f78ac9a65b76d2f` | 2.2K | Tracked file |
| `c/tests/test_FUN_000627ec_627ec.py` | `837a3c8c115633855c671c8731d3c5dbd959658a48ac9e5be3a32367eaf9506d` | 2.2K | Tracked file |
| `c/tests/test_FUN_00063a48_63a48.py` | `32a346e1257946405783ef901f1e889a4b0039246553a0538fca72129595a52a` | 2.2K | Tracked file |
| `c/tests/test_FUN_00063af6_63af6.py` | `c0486f62e33778bcb0646c38f8a773c8fff1ef748324aac819962e57fc4d023a` | 2.4K | Tracked file |
| `c/tests/test_FUN_00064068_64068.py` | `99d51f534455b44a92e1b5327cc5464b53b08fb37de438df1ce2d79f4ec3a547` | 3.8K | Tracked file |
| `c/tests/test_FUN_000644fc_644fc.py` | `74fd81355e5d11c736e0a098ad08013e1d2d10baac2c88329fa83366bc8e3af8` | 2.2K | Tracked file |
| `c/tests/test_FUN_00064746_64746.py` | `e5e957a1c6bd5a7138d0ca0ad01ecb4532b10df896bd4b5a9dd28fa5a7a8a285` | 2.3K | Tracked file |
| `c/tests/test_FUN_00064e16_64e16.py` | `786bc7da6643e588605f083c56535455670338dfd30defc65aa0de57399f2f9a` | 2.1K | Tracked file |
| `c/tests/test_FUN_00066b36_66b36.py` | `889c4dabd99963e3b1533e1b719144993e91cd6f27725da1746c15b1a4db715f` | 2.2K | Tracked file |
| `c/tests/test_ImmoBadStateSet_365B8.py` | `6e254a6e79f9ca38e45e68f905c85b22d51db8c78a364a6621be8ff47fa2b828` | 2.9K | Tracked file |
| `c/tests/test_ImmoGetCANData_36870.py` | `843e01adbc23a140603776c2c00ac9335ed61f8b6e727f215301fe149e6a3422` | 6.0K | Tracked file |
| `c/tests/test_ImmoGetSeed_3664E.py` | `d9a5ed3f330bfb21f805dc0cafe937e7de9d119bb2df2ca7a3d7876e31c8b353` | 3.9K | Tracked file |
| `c/tests/test_ImmoGoodStateSet_36544.py` | `7c5245667c9a818fc464ce2eaa1d8c3589608dccc7649f4bf0e8c42a4a3bd8f2` | 3.7K | Tracked file |
| `c/tests/test_ImmoKeyExpander_365D6.py` | `db129aaae8eed35f757cfff61af05f3f8d56130f38728ce5e127257adf5225e4` | 4.2K | Tracked file |
| `c/tests/test_ImmoStateMachine_360E8.py` | `d443e119eae17da8c2afbb0d94e5c1dc62899f398370341fd4b0f62fdaceb22d` | 10.6K | Tracked file |
| `c/tests/test_ImmoStateReadyToDriveEngineOff_364D8.py` | `1b9fef3efaa981ea93b3bc07f637b3cb5fbb9ad2c6caf2b9cd8f442081f01d1a` | 11.1K | Tracked file |
| `c/tests/test_ImmoUpdateRelated_37120.py` | `6210c2315ebbf98a30a49332fe0f762d11ee54f0af9db67b7920713e1c8ff8f2` | 7.1K | Tracked file |
| `c/tests/test_ImmoWaitForKey_35F92.py` | `a8d84315c25fd2c847ebf09158879cddb6ce2b05acfe4f057805db5f676909ff` | 10.1K | Tracked file |
| `c/tests/test_Immo_Keygen_related_ADC_36AFC.py` | `ae9be29eeb2148575b4b64a2ede77871caa7302fb04eec732e050f090fbce6bd` | 6.6K | Tracked file |
| `c/tests/test_SetMemoryNotValid2_0x3E5A8.py` | `968fb49d6faf8723db622c1cff5ab56213ceac91a74db15c4c4a95fd230f827e` | 2.1K | Tracked file |
| `c/tests/test_acceleration_enrich_0x591BA_591ba.py` | `89de530bfe1bfbc0a2302b208e59850cd2094bc1859b746271249bc196462295` | 6.6K | Tracked file |
| `c/tests/test_add16bitSaturate.c` | `68dbf734de3d44662fc9cf968627897e61ad0cacb94eb32dd9d088ba08dfdc95` | 2.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_add16bitSaturate_ADD1_ADD2_2460.py` | `207863bca0ed47b6a63121b5a374036e9eeaa9d24498c4534b8e99c7744f60f5` | 2.3K | Tracked file |
| `c/tests/test_addSaturate8Bit_2478.py` | `753e43431a9340327476d28d3cd863ff6e60821f93b385a98ad34de1dd1db049` | 2.3K | Tracked file |
| `c/tests/test_add_s32_saturate.py` | `5e72c86880bc7e6c53bb4affdda5f2e45c4122f78f64b360e4f6e25f51f0a71f` | 2.7K | Python per-function behavior-equivalence test |
| `c/tests/test_airPerStroke_341e4.py` | `9107a03b1fc7a155d3c2cdd69e42412099b330c79f950a4044c6a7480ad5e961` | 2.2K | Tracked file |
| `c/tests/test_air_charge_calc_0x19190.py` | `fcd753ab391c527884dcefe1e60a63d86491b0965d504aa944f0e15f8a96fefc` | 6.0K | Tracked file |
| `c/tests/test_air_quality_0x5A2E4_5a2e4.py` | `452b42d3c95cb84dd67aec3fe00704190b941d102748a985c00e874da626cee0` | 2.2K | Tracked file |
| `c/tests/test_alt_sensor_sm.py` | `dfb8148d3c64a933e2beed6b7668d26d796258c766dddbfdc8dd841082923b39` | 4.3K | Python per-function behavior-equivalence test |
| `c/tests/test_alt_sensor_sm_5D34C.py` | `87918c76c404394402ffc85c6ac206799d81bfdfed41c4e58fdd61ca206a29ec` | 4.4K | Python per-function behavior-equivalence test |
| `c/tests/test_alt_sensor_sm_5D800.py` | `2f951bdaf6e5e145aecfc154361a57075d3dd92ced54e03e6eea91dbe5c067e4` | 4.1K | Python per-function behavior-equivalence test |
| `c/tests/test_array_init_zeros_dual_1D0A6_1d0a6.py` | `7bbcf624b4a32c3f99e73c5141d17da73f6c5aafd700d47f2ecb110dde597a17` | 2.2K | Tracked file |
| `c/tests/test_atu2_edge_capture_config_6F3A.c` | `0dfe7a1632bcf99f763b7d7c164bf14ecf00446feb16afef0e466fbbec4eebb4` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_atu2_edge_capture_config_6F3A.py` | `520aab7b84b70f8233f983f09a47ac3f9e352271be2709f58dc98016316a0cc3` | 3.1K | Python per-function behavior-equivalence test |
| `c/tests/test_atu_fpu_control_wrapper.py` | `c042db681d34a842025844855c83e18434a9ad9f923f0749e21560a650070ef8` | 5.3K | Python per-function behavior-equivalence test |
| `c/tests/test_atu_fpu_control_wrapper_70AC.py` | `14aa2c2a8724a9cf7d71cd6e0fc05a32940ebb1738e280f54dddd43c11f7c850` | 4.2K | Tracked file |
| `c/tests/test_battery_voltage_monitor_26766.py` | `cd41e63530a13a8b234a2357255d4f7d157deb24222cdfdf41e580f2a9d2df0b` | 5.0K | Tracked file |
| `c/tests/test_bitfield_extract_merge.py` | `476b9a2477fb9228d44dc108b274e1ff43d6b46d88d9c82b163a3139b49ed4ac` | 6.6K | Python per-function behavior-equivalence test |
| `c/tests/test_bitfield_flag_selector_33A98.c` | `74e061c162b01fdcb33273d4cc88b79e5d9650ab82037c18c8a2a92c53d8b7c8` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_bitfield_flag_selector_33A98.py` | `a45f0d2c4d936e1846ca2374034f0d415f08537fcabe0d14d337bd86f9e72d1f` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_bitfield_flag_status_decoder_339AC.c` | `f50f79e4632f40b346179eb30324bec53d33b28360d33df43d47c6a8f5c54040` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_bitfield_flag_status_decoder_339AC.py` | `579ddb23d3682d20b5c733a91e60dbd6f5087e982e396feddef70a42e257d579` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_build_be32_from_bytes_f4.py` | `a338fb119aefaea25860d980fffedbc756443116333616911e5b788b32a032aa` | 3.9K | Tracked file |
| `c/tests/test_cabin_air_filter_0x5A4EC_5a4ec.py` | `8cfed0571186c586dea7264510d8518fdfaa3f8c0dbef5f9209d3bb87380828a` | 8.7K | Tracked file |
| `c/tests/test_calc_adaptive_fuel_trim_1379C.py` | `d47005be62b3f93aff4add1178e8cb233ebf8218c756eb3936c885c88d0acd0d` | 10.3K | Tracked file |
| `c/tests/test_calc_barometric_pressure_trim_13F68.py` | `1656e9a9b592457a75eb645ac47a78e6fb02cd0e45ab673cedb04ce65b5ec099` | 3.6K | Tracked file |
| `c/tests/test_calc_decel_fuel_cut_445AA.py` | `4661c049c9b649c9f53c83670efb09df049715e12962990c308e6f6645452458` | 9.3K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_fan1_control.py` | `8b84ce9a25d4746d7c31926ed986f620b3bfc349d99caace7f1cdabb139c21c3` | 3.8K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_fuel_pump_duty_trim.py` | `edc3413dea4d62418e6f85150213c757a489765ea7e0bbe03f687e07a9345967` | 9.5K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_fuel_trim_corr_map_136F0.py` | `61efbf5508099cfc9a1c9b5bea013ca9a3bcc1b581e603f4dd2a8022aa40cf37` | 5.0K | Tracked file |
| `c/tests/test_calc_fuel_trims_adaptive_117B4.py` | `9bad7105cf6f75752c62235a3916188fc3f78a4acc939818fe7bc05ae442ed87` | 13.4K | Tracked file |
| `c/tests/test_calc_idle_speed_target_0x12F5E.py` | `d316e6c3622d9fd8fc8a97e8125b1fafa2d65475fe5f07bfae78e04d54ac0402` | 5.8K | Tracked file |
| `c/tests/test_calc_ignition_all_rotors_13C2C.py` | `85609056cff0f898fbfe5a1ffd24e5a54b9adb555822f55fb4e472b5b09b84b2` | 14.4K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_intake_pressure_pid_output_1252C.py` | `a0c6adf963aed0fca0154d1dfe6aa49ed9b613b3d6222b57b57e6bf1e85682be` | 4.1K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_lambda_feedback_pid.py` | `185b0f847aecbb97a0988e233396519a1286743e251ef6d51d88e9e57bb8e074` | 3.7K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_lambda_feedback_pid_11A34.py` | `0b8d594d46a554abb684569f8e87a96669323a9f50a1569fbfec2563936bb8ee` | 13.4K | Tracked file |
| `c/tests/test_calc_manifold_pressure_error_clamp_10A5C.c` | `64a5b2c602b9740e3d443b7525254bb852992bc649759209e7eb61c2f8057777` | 5.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_calc_manifold_pressure_error_clamp_10A5C.py` | `cdf6f3d5b71c66e7d8c927bb3074b847f53cd83cdeba37aa16779b45e9cc777b` | 3.5K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_manifold_pressure_error_diff_10A88_10a88.py` | `5ec73468d277d6fff185e5435f114724b461d788615790d1448a9a8048830915` | 2.3K | Tracked file |
| `c/tests/test_calc_rotor_sync_idle_gate_B.py` | `65a0233dcd3c4402409c337572772163edad160ea8ed1c5e8200f820f1e4fd23` | 4.1K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_secondary_o2_trim_1321C.py` | `4987730c565cda9e940d3cd6b4d17ffce72cdade943a2606f0937de38db583fc` | 11.1K | Tracked file |
| `c/tests/test_calc_spark_advance_0x121F0.py` | `ebbf35f191282340208ab37655e36126e43a58378affaf70479b38e856e7446c` | 8.2K | Tracked file |
| `c/tests/test_calc_spark_advance_0x1237C.py` | `bac50eb11f4096e9b74de7bbe61ec4e924f5847b4e126c553e2ac532b07d6b71` | 8.2K | Tracked file |
| `c/tests/test_calc_spark_lead_trail_split_19220.py` | `e9b5c66a96dec89a287a832bb7e21b822f63aa74af7767fb3bf8d1f27bcf05d7` | 8.0K | Tracked file |
| `c/tests/test_calc_throttle_position_filter_1345C.py` | `b82023279828dc68e627142e87a5332c2af6396c8072363318c16042b6b7efc4` | 5.3K | Tracked file |
| `c/tests/test_calc_traction_control_mode_11166.py` | `a36a062b464a28530a5d42b62be35239b5f336531c6b0d2e280d2f906ef4d5db` | 6.5K | Tracked file |
| `c/tests/test_calc_vehicle_speed_filter_133F8.py` | `0eb23bc35c08331e2da174ad811ff95b8a2f04e34218cd5b02eb6c7a883d02fe` | 5.7K | Tracked file |
| `c/tests/test_calc_vis_solenoid_duty_cycle_1261C.py` | `2c93012938d4b7f7c7cfb9103a498aba3cc7f4bed46581c14ca1ca115e25334d` | 6.9K | Tracked file |
| `c/tests/test_calculateEngineLoadMax_341f4.py` | `f82a2c0daad439c5f2023bc2644d2b9318253623f1b9a76c2a29e920867668f6` | 2.3K | Tracked file |
| `c/tests/test_calculateFuelingRequestMaxForOBDControl_2feb4.py` | `5394e2b239b5539e36fce59f05cfd2f662ce1d86299af5f6cac8062341727ecf` | 2.3K | Tracked file |
| `c/tests/test_calculateImmoSeed_3675C.py` | `1f321ad9af17013e4f53bb730019532f9b818d45e27c7fb833f3cb6d3b3859b2` | 3.2K | Tracked file |
| `c/tests/test_calculateOffThrottleORFuelCutTimer_12ef2.py` | `78ec878bfbc9a955eb57ec076b8878e322578baebd734c1836085d84ffa38532` | 10.8K | Tracked file |
| `c/tests/test_calibration_apply_4B770.c` | `7119adb710f3b1dcd2d84ee18066a468504fb736d28613cd9840eae4e33adab0` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_calibration_apply_4B770.py` | `e4ed971e0e154de76e3868b7e1060354c6e13e7ee8339d72edd1f053df6ffd7e` | 2.4K | Python per-function behavior-equivalence test |
| `c/tests/test_calledLots.py` | `3728bef32f793079b65c5fd64847872105968ccf294975555f59043a247035d4` | 4.1K | Python per-function behavior-equivalence test |
| `c/tests/test_can216RXUnpack_29ce0.py` | `76afb10357966469060fe6841ebde766d3c1139119c963fa982c59571d43eaaf` | 9.5K | Tracked file |
| `c/tests/test_can216ResetTimer_29e50.py` | `320cde130e55688bfd45b37697b70398e3bdfa243fe64b689835a5c9bf710707` | 6.2K | Tracked file |
| `c/tests/test_can4B1RXUnpack_4c7b2.py` | `926375178524d9e6796189d406bc8a0db0375045fa3b139be87fb14bfe3b2321` | 8.6K | Tracked file |
| `c/tests/test_canSetup.py` | `b9a08337ead688fa1fd735a2dc826ee7415b50471c46e3b34a7a2b80604c66b7` | 2.0K | Python per-function behavior-equivalence test |
| `c/tests/test_can_encode_handler_62ABC.py` | `98c1573589894423575a2db83095e2c2fd5808277ff61b21ff4b5e987374ff78` | 3.9K | Python per-function behavior-equivalence test |
| `c/tests/test_can_encoder_556e2_556e2.py` | `acffb411eb1831ac2cf82b248d6304dfbe79d2da14b6d7e5b710e626038d3bfa` | 2.1K | Tracked file |
| `c/tests/test_can_get_rx_pending_flags_d0c0.py` | `3eb6baf8210fbcd028ee87f7810f9ba4e0218f0372552bbb7cff7b46e587f9be` | 8.2K | Tracked file |
| `c/tests/test_can_get_tx_acknowledge_flags_d112.py` | `53197aaf6672b06f6b80a34640027a6542d2d1a36ae13c79f2a0edde8526bc14` | 8.2K | Tracked file |
| `c/tests/test_can_packers.py` | `9f57076f6e50def29351bfd69d6c38356b02f5b567502d710404a252d27946dd` | 30.3K | Tracked file |
| `c/tests/test_can_rx_mailbox_ready_process_10fe.py` | `5d1c6a4bdcaef9836d2f770d39fa2a2612d951d28b97c758b669a9b0f9c9cf0b` | 2.2K | Tracked file |
| `c/tests/test_can_tx_ctr_init_2D4A4_2d4a4.py` | `baf8e7e5a4941b563c303426f39d524ba3b31f832d6c5bc3ca0210e317bfbf29` | 6.0K | Tracked file |
| `c/tests/test_can_tx_dlc_set_2D470_2d470.py` | `fd235dbc853a771f8a7a1d2fbd489ebe1ef893330e350fa389c7258016ae0e25` | 7.8K | Tracked file |
| `c/tests/test_can_uds_resp_encode_seq6_670d8.py` | `aa5298290192f34c258f25a4956eafda4ad34070081c6fed285f2aaa5b3f3c4b` | 2.2K | Tracked file |
| `c/tests/test_canrx4b0related_2bffe.py` | `5dcf281307b230226d61a4c9f5e1e22693a26fac81f637e441ff455b2b39abca` | 9.9K | Tracked file |
| `c/tests/test_checkFloatValidity.c` | `ab582c65c5c38249eba595836f90a9e09eb2830039dc8cadb0548908d241d077` | 2.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_checkImmoStatus_371E4.py` | `62a446b4175dd3931c21a0d6d03141fcfd76dfd475257d3e0d1556e79045066a` | 5.5K | Tracked file |
| `c/tests/test_checkWatchdogForOverflowandReset_11e8.py` | `eddb3cb1e6dac694d284c69fcba6acef4e22f19861695c98c2a29d2f2aee8765` | 8.3K | Tracked file |
| `c/tests/test_check_float_validity_0x46CC.py` | `d0040f5dbb18d4d01852beddfec07bed281dc5032e4031fd430763c91a336a9c` | 6.3K | Tracked file |
| `c/tests/test_checksum_complement_add.py` | `006660320cfcec797767f1ea9b67c8b238947ad86b395def822a29c928f1dd05` | 3.5K | Python per-function behavior-equivalence test |
| `c/tests/test_coil_correction_write_0x50A54.py` | `916a6b803d755218fd27a240f2bc3cb93cdbb87db60164e7d64bb622cdec1ec6` | 6.1K | Tracked file |
| `c/tests/test_complement_shift_u16.py` | `30260e87df8208ae9cb13757bdd71020bf7da757ba4992de1627bde5b954793c` | 1.6K | Python per-function behavior-equivalence test |
| `c/tests/test_complement_shift_u32.py` | `96c373fda8ba106d6f4982fefc67a6ad64c8d64df59e3a9516d1247061d490aa` | 3.2K | Python per-function behavior-equivalence test |
| `c/tests/test_cond_flag_b2e0_multi_eval_21534.py` | `f14e55ca584da93708380113a33d5471b37231547e4e11216c373bebcbe70ab7` | 2.3K | Tracked file |
| `c/tests/test_conditional_flag_set_sensor_state_2EF0C_2ef0c.py` | `5efd86a6adf9ad423f97e24c7dc2f0b3743f4638f660b6a59afaabeb6b4fb982` | 8.2K | Tracked file |
| `c/tests/test_consistencyCheck.py` | `d8e1538f21e72365f171bd2494b2cb74bd3643eb6915759f0c001a9a865ef2b3` | 13.7K | Python per-function behavior-equivalence test |
| `c/tests/test_consistency_check_3A28.py` | `e032ec261ef9bf7775b2cde0d372fc854277f48ec0b50447f9ca7563e5a4d731` | 7.7K | Tracked file |
| `c/tests/test_control_struct_init_zero_5C98C_5c98c.py` | `52d12b093af2fe974d4c422cc6324448a3d9d9c4af8c5b7219af09f3c407fa37` | 2.2K | Tracked file |
| `c/tests/test_coolant_temp_boundary_check_1F99A.py` | `19810dddaa3e420ffdc78afd46d346b5d191196a41d840b3b148f9986298602a` | 3.6K | Tracked file |
| `c/tests/test_coolant_temp_out_of_range_check_E50C.py` | `97729112a26bfca9657f4a719f07ce80d5aa5fec8693aa298cb1971b6a009458` | 3.5K | Tracked file |
| `c/tests/test_cooling_fan_control.py` | `ed8d94c1306c76de0e70c684a4b0b60edc2b70c99f3351a9a2dbcf1e94a839a7` | 4.0K | Python per-function behavior-equivalence test |
| `c/tests/test_copy_word_0xFFFFFC534_3940A_3940a.py` | `5870d69804255499c2e2b296860a9b0cb4d8c14ef2a5166f8d165430dddbf98a` | 6.2K | Tracked file |
| `c/tests/test_counterReset_4ca9a.py` | `580f5e09123c8b448b39f6d9a1dea17be1e58064c0cbe6b31560ea0a21459272` | 2.1K | Tracked file |
| `c/tests/test_counter_increment_a_2610A_2610a.py` | `e4f13b519d8116b61e5f15624407a63420acb265ec84c9c0c9a4b0569e499075` | 6.2K | Tracked file |
| `c/tests/test_counter_increment_validator_37650_37650.py` | `951e45b7520a48fb7920875fa4b242c7fa6c028c611054b084bf87e4162cbe1a` | 9.6K | Tracked file |
| `c/tests/test_counter_init_zero_2A26C_2a26c.py` | `0b012c3318027b7d96c44faa652171f6bbd6ff7463883539ea70b1e7e0b3bb74` | 6.0K | Tracked file |
| `c/tests/test_crankSensorInit.py` | `ef23723f854a27ab0011b33c0b4c13655a9b467028217745ca1311d64b23e6c2` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_crank_flags_enable_7ed8.py` | `4fa79d252d830a24a57da7c22fe97d68d1664aea651ad830ce18dd027f136227` | 6.8K | Tracked file |
| `c/tests/test_crank_state_bytes_clear_7ba8.py` | `298e702ee8b13bd61f32d533950b44d038818a0f0d84284c5b279db6fd80cd13` | 6.3K | Tracked file |
| `c/tests/test_cruiseControlMain_2eb40.py` | `7db2bfaadfcbed9ef9a8b1988c095baae627d31e409a539eed9f6be8e3ab87c7` | 2.3K | Tracked file |
| `c/tests/test_ctrl_decision_5698a_5698a.py` | `fb0d72219f629c359bb8cdad879a95aa4cbbe1fdea00bba6e61f9bead00fd377` | 2.3K | Tracked file |
| `c/tests/test_ctrl_ionizer_5a7d4_5a7d4.py` | `fdd071e01a93c4c5cb5bb5cad5986a08134357eb797a780bfdd5a751f5e2ef49` | 2.2K | Tracked file |
| `c/tests/test_ctrl_nesterov_571e6_571e6.py` | `16bda921dad3164554d5d4170a200861387b8ae1cee6d842eec0d3822decd8da` | 6.7K | Tracked file |
| `c/tests/test_ctrl_protocol_51dc6_51dc6.py` | `7c356cbf80eebf05375a38fcec170b5b397690370dfb4f73c5dd4ffbbbbc5fb1` | 2.2K | Tracked file |
| `c/tests/test_dataLookup.py` | `007121b1f630c99805a4492692c0bd1b50925e82914e92870b63460c1498b820` | 4.6K | Python per-function behavior-equivalence test |
| `c/tests/test_decrement_saturated_27A36_27a36.py` | `5733bdfb92a4d08ab40ad2763dca5f9b86bffe0104a31e525c295f01c4451b69` | 2.2K | Tracked file |
| `c/tests/test_delay_loop_n8.py` | `5084347986d5453524888b9a58fcdfac709ff9fc91a3bf5af1c1383a5de301d3` | 3.6K | Python per-function behavior-equivalence test |
| `c/tests/test_diagCheckSecondaryAirRequest_5b76c.py` | `0a853a58f3f3bae1e187510fb283b5364ffb074d682dad4ec31e12d6f3ffd819` | 2.4K | Tracked file |
| `c/tests/test_diagControlModeSomething_5a78c.py` | `acbb0bb9b70df808755dac7b64e8204c3e1aaa07ce69ec82e7935dd034963274` | 2.3K | Tracked file |
| `c/tests/test_diag_airbag_5ab9e_5ab9e.py` | `56187f7ebff38463820e5cda8591073351e910011c31e847fde48d197a3bc731` | 7.5K | Tracked file |
| `c/tests/test_diag_bitfield_2c4cc_2c4cc.py` | `d256a0417bfad48138d7162cf443117907b2fdbd97016500f9cfbc18906c81c5` | 7.1K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_903c_56788.py` | `73e9d65306c3004bff95f0a811c8f89ddc8972f5e5ec65f3dfdcd53795b6e36e` | 3.9K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_9060_56962.py` | `5fbf760f29c73b46fb03c03acfe6dac272918e48502dcdb176012d6974ef0513` | 3.8K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_906c_569c8.py` | `3438f1a5a0d0d38f517be7b3bffe7d0b7da00ef997ef2ec8b39c2890a4da6cae` | 3.8K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_9070_569d0.py` | `f9c4b5a9deb7e12fe3d828048312be308a0d8c449fda4ca64ecd312f243a7b98` | 3.8K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_9074_569d8.py` | `6936de3c980e27268d9237aed1993526686a837b7b387e4283bf881c0796e06a` | 3.8K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_9078_569e0.py` | `d065a1f7a8bbd52bbf7c21039412dae1ac0a9ca988e11f7a1bd4c9ff986610c2` | 4.2K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_9084_56ab4.py` | `25cdff25d70a7a2f2329feb38b58cffed320b6bd0bbd38eb49510e42e18dfbd6` | 4.0K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_909c_a_56cf8.py` | `29aa725a6c0c679152ad24c3721d9c3821aa5eb189c72f5e7b9afcc897ad6e4c` | 3.8K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_90C8_56f94.py` | `ba054b8c6a9d444712fff30ca89a63ad35bad9e0692bf3f9468948f92e48e264` | 2.2K | Tracked file |
| `c/tests/test_diag_fault_cond_eval_90cc_56fb6.py` | `ff94993aa6093e33be59468e46458640af665a42b3e7abb6e28268ba48fcd491` | 2.2K | Tracked file |
| `c/tests/test_diag_key_validate_4E78A_4e78a.py` | `09c086245732854fde5f3aff93748c2bfe32a964e2dd95735f6caec9b72c4f26` | 8.6K | Tracked file |
| `c/tests/test_diag_reset_session_state_1720.py` | `93eda3cabd541b254667ee5c16f56bfa35c936903438a75991b4aea7b34c5fdf` | 2.3K | Tracked file |
| `c/tests/test_diag_response_send_4E904_4e904.py` | `26fdd77758133d8b8a0ce4a2540b60c439645099ee3044c801be21254f8a6d07` | 2.2K | Tracked file |
| `c/tests/test_diag_seed_generate_4E72C_4e72c.py` | `30d84fb091f7c347200e05a6dfd4ce8b6355bbd33a40edd188c7d6e46552b5da` | 2.3K | Tracked file |
| `c/tests/test_diag_sentinel_5687a_5687a.py` | `2856c5b7953681a45d98f1d79f6deb494e9c2b3664d015c2d0e9a2b8fbf1ce51` | 6.7K | Tracked file |
| `c/tests/test_diag_tester_present_sid3E_1908.py` | `c41f18bc5afc698e055f6c5dda9155093ff77743f6a1bc170e2ddc96073cd5e2` | 2.2K | Tracked file |
| `c/tests/test_diag_threshold_3c3dc_3c3dc.py` | `e926002e058e3d0b164725fff1bdeb575a9795aafbab24a1fbc601d9e8f320dc` | 7.4K | Tracked file |
| `c/tests/test_diag_transfer_exit_sid37_1cb8.py` | `49613bda249a80e371490e9d57728f472cdb294303c786b16fcd04c731d1dbbb` | 2.2K | Tracked file |
| `c/tests/test_diag_transient_4fca4_4fca4.py` | `3e08386186d4d0cd95dd3a80d2ba27aff5e263fd45161575442cf1c0e9907e46` | 7.3K | Tracked file |
| `c/tests/test_diag_vehicle_info_4E2BE_4e2be.py` | `fc6091c257623de21e11e63a6a16833c79391517c69d588a80a3624204853d98` | 3.8K | Tracked file |
| `c/tests/test_div32_signed.c` | `76733752f95f1f468434f99ddd4f6d6b1069d097ea7aa3d1105881fbdb61dbe0` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_div32_signed.py` | `933638838f61ecb2e4d86f388057a0f7d0abf670f3bb2c0b5cbc2b22a411970d` | 9.1K | Python per-function behavior-equivalence test |
| `c/tests/test_div32_unsigned.c` | `ee1ed14e17a880b5f89320dc18a09c7d72757b971882e9122f8812ba09cf438b` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_div32_unsigned.py` | `c8f5ac7380d2af4ec4f5f854640783e84a19a105b8159ae34aa5c47922e81b34` | 4.1K | Python per-function behavior-equivalence test |
| `c/tests/test_div_4740.py` | `f7508ae60dea1e7d0213fd8609c362c75fee3f77ce910aa6ed03e33c9abdeec8` | 9.3K | Tracked file |
| `c/tests/test_dtcRelated.py` | `58d57517fc7e913663accb0e41d4eeabd9f9b7a76003e85be9c27fd740db11b2` | 5.4K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_code_set_clear.py` | `b437df1d4eebb950934276e0cd87eeb1c80e7a5fb476d4367e3c43c567336f6f` | 2.8K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_data_read_60A86_60a86.py` | `7ba68af74622c85112df9b9010eb780cb54c619cea6eae555d144444e37547e8` | 2.2K | Tracked file |
| `c/tests/test_dtc_data_read_60BEE_60bee.py` | `2061bd5cc8cbfb838fc17bab658d8c48042c66022dee18d5a8e3ee77c54e391f` | 2.2K | Tracked file |
| `c/tests/test_dtc_data_read_60CC8_60cc8.py` | `8c2433546dab1473f7a2ed483e86f17d4355767f1424a842aa25d541905d5e97` | 2.2K | Tracked file |
| `c/tests/test_dtc_data_read_60F58.py` | `5361261f91c1625fb804c18552549ce55cd955c344e240b2e883c78ac29d1a47` | 2.4K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_data_read_60F58_60f58.py` | `05727e45c56fa764a55b2e05c6c5af90b7a9896cca4b60ce4384b447cb48bb5f` | 2.2K | Tracked file |
| `c/tests/test_dtc_data_read_60F74_60f74.py` | `e1320a3cb9e0a2de05262308bd231d64f18b003104aa43309038c4e2d6311796` | 2.2K | Tracked file |
| `c/tests/test_dtc_debounce_monitor_43760.py` | `bc0e818d3978519385ad2931304e76ed158183d8630e2b174f00e55e06c60602` | 6.0K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_handler_610FA.py` | `c5a2cef0c037a4d0df1854fa2adc2dbd4fc2b17b2ae588e56de67f796f506974` | 3.9K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_handler_61550.py` | `d98667cbf3bf2ea5034ac307d251c85d53c9f3bc03811b588583e30af9916f81` | 4.4K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_region_checksum_validate_8fc0_66280.py` | `7f0b7fc33d8f8ce83b83c3452c96e79b40cdb35a028f5c160e6cdd53c929808c` | 2.2K | Tracked file |
| `c/tests/test_dual_cellbank_selector_58C4A.py` | `782021436d99062cc146db9e8424b41ed3b483c718f0120dab2a020a325941e3` | 3.9K | Tracked file |
| `c/tests/test_dwell_time_calc_0x5071C_5071c.py` | `5fdd55f7ba1cf57a554db5e1dc19d76d1bc624abdb10726ba7aede220dd41852` | 8.7K | Tracked file |
| `c/tests/test_eeprom_commit_dispatcher_37000.py` | `2547705ed02d686f88a6d2ef607c9a5da7fc4ea993bbad8caa1947ac6ecc0a62` | 6.2K | Tracked file |
| `c/tests/test_enableDisableCruiseControl.py` | `59db7e7dec7f9877cbd266c667a92db07fbbc703f014ebe7b7fd1de90a6b71f2` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_engineControlCalculateTiming_14584.py` | `1759652cd187f8b02f9d9290c1ac9e96b9e2a061ea5f96091c44e3f1b58ee7e9` | 17.4K | Tracked file |
| `c/tests/test_engine_load_estimator_0x190A6.py` | `5847469b90b73edcf25de168f06c983a260d4eb70361c24ee65af65b25d5bc98` | 6.0K | Tracked file |
| `c/tests/test_evap_purge_flow_calc_22d20.py` | `6ad2a55c8148dbb47b5b26db6724a2729c2c7d3ca57191e98cf2888a9454dc50` | 2.7K | Tracked file |
| `c/tests/test_evap_system_control_0x4F750_4f750.py` | `b45afc69ac97512470889ab86b0c0093c6781f6f14306e144e7de231c3fa19c5` | 7.5K | Tracked file |
| `c/tests/test_exhaust_oxygen_control_19480.py` | `092fae2ddc3b90c317d31d59f4334ce110f7954e80cc6dab98eb5fecb6ee8534` | 13.7K | Tracked file |
| `c/tests/test_fault_condition_check_5F018_5f018.py` | `878bad6b1e2ee2b242d55626f50589a0b119e2c410e965a823ebe5a24194d60c` | 7.0K | Tracked file |
| `c/tests/test_flag_set_coil_event_e448.py` | `220efa87610ae246165377def331b5b46118a312c7739e3fd4146809aa4e386a` | 6.0K | Tracked file |
| `c/tests/test_flag_setter_49ED0.c` | `a0331aca2cfc4260d8647800299c6b5a7db55c4c9e4088f25687d75d685470f8` | 3.2K | Tracked file |
| `c/tests/test_flag_setter_49ED0.py` | `4feae0c2e6eea39283b56aded6b1d5416d029e3e04690774b8e038a647354c43` | 2.4K | Tracked file |
| `c/tests/test_fpu_compare_and_mac_394da_394da.py` | `bb4ecb44eef872b1012d02ad52a503bfe5337f89627e3219976596ff22790530` | 2.2K | Tracked file |
| `c/tests/test_fuel_calc_entry_9528.py` | `3f4696737b1c200202f36f84f09371e2a6b9bd183b39165a4b2a078e1aaf9cf5` | 4.0K | Tracked file |
| `c/tests/test_fuel_compute_fcd2_fcd2.py` | `f28adf00766c3890d77376e123a3bd0c97c8d9117f4de878583f5797f635a2f9` | 2.2K | Tracked file |
| `c/tests/test_fuel_control_59dc4_59dc4.py` | `bb3344e705048f468337f39973f4802740ce7da95a5059b6ebf28a3275de8b6b` | 6.0K | Tracked file |
| `c/tests/test_fuel_control_59e24_59e24.py` | `952b13812620b8d13846932c2ed7f13efefb03223a4bf56fb635559520b422e8` | 7.4K | Tracked file |
| `c/tests/test_fuel_correction_reset_45B44_45b44.py` | `b025ec6fd791411fcb14df82c5de38e2997052d24e45235cb791ae65fc1075f6` | 7.6K | Tracked file |
| `c/tests/test_fuel_defrost_5a248_5a248.py` | `02b938850a2758344db71225c713d22db72af9384c89311e330c5d6f553b5667` | 9.0K | Tracked file |
| `c/tests/test_fuel_detection_1cd32_1cd32.py` | `ff2bc315f948696c76a0aae1ba50613a367e5a95c38dca2b2d3d3439d05ef315` | 2.2K | Tracked file |
| `c/tests/test_fuel_emission_4f70c_4f70c.py` | `c3a2929d0c5c28e420386b06a44b0222cb577ac604345a64ec1635453962c648` | 7.5K | Tracked file |
| `c/tests/test_fuel_fluid_59ba0_59ba0.py` | `a2193d40f02298e19eddc918f383600f1276aa06f9e242f273612984c7ee1b73` | 6.7K | Tracked file |
| `c/tests/test_fuel_intercooler_4387a_4387a.py` | `7d16ea35d24560bca993e086f98239cf12d582b752c46c399338a52926fd5292` | 2.2K | Tracked file |
| `c/tests/test_fuel_pump_control_45CA0_45ca0.py` | `51d388c3c728267649a525cb9efa922e6f8f2cd696a12527819acca7d3155410` | 8.2K | Tracked file |
| `c/tests/test_fuel_table_init_45B3C_45b3c.py` | `8468a23c2ad292b85e98330e8f24a21fc23182faae10fef1b79a7d6ca5a683ed` | 6.0K | Tracked file |
| `c/tests/test_fuel_trim_channel_inputs_map_e07e.py` | `8834413f6e3ebe57bbe640f7bcabdd993f6ee12651699265339067b5d60c6a49` | 2.2K | Tracked file |
| `c/tests/test_fuelingInit.py` | `06b34a57151af4cb505ffb60f475517c65f6818bfef255dbb8e7fe179fec435d` | 2.0K | Python per-function behavior-equivalence test |
| `c/tests/test_gear_ratio_detect_449BA_449ba.py` | `6f556daa82f1adbe2d3d8b19b8e8b9366a1e39ec35613ed6b9e31b21b639f742` | 2.2K | Tracked file |
| `c/tests/test_getACSwitchStatus.py` | `3ca849fffab8422af2c410bf5f4692f2d98a1d4ef326ebf5ad7c9935408fbd59` | 1.3K | Python per-function behavior-equivalence test |
| `c/tests/test_getAlternatorFaultStatus_2687e.py` | `41439ddd07c0b6b29214641406f4e16d99274974f3b339ffcbd0dd4c7cc2f0d3` | 6.8K | Tracked file |
| `c/tests/test_getBaroSensorVal_D144.py` | `a5177f9000dee01716a05d54490d97b2a71b1f54c0b2b3d69cc772b69c7e4598` | 2.4K | Tracked file |
| `c/tests/test_getCommandedLamdaOBD___53a62.py` | `c691d720be4ad9d09bb3dee8737d3d32ac5b9acb2ebfca805243262a34db1800` | 2.2K | Tracked file |
| `c/tests/test_getCruiseControlAllowedBool.py` | `d737ce0603c9c1258763440f03c7a930a44cab9455412003ac0814b1b9cb5b27` | 1.8K | Python per-function behavior-equivalence test |
| `c/tests/test_getDataFromE2RAM_0x36C1C.py` | `9cfec2ea3ea72f5f2b29e3896a81dd5710ce394fd1a9a502f0cb0358a905d3a2` | 4.0K | Tracked file |
| `c/tests/test_getEngineOffTimer.py` | `0e607655ce775e96f883f44a715a08c5e8fddf10a535b9ae5d926ca0805e78a8` | 1.2K | Python per-function behavior-equivalence test |
| `c/tests/test_getEngineOnTimeForOilMetering.py` | `45871efee94a6cdddd9cf899ba9315149460aaa0058c6e227a33292a3d7f44bf` | 1.3K | Python per-function behavior-equivalence test |
| `c/tests/test_getFaultStatus.py` | `502aff16cdf362817810bb27e7373e9fec67fafa9a76e9bd49ede9e2a657ef9a` | 3.0K | Python per-function behavior-equivalence test |
| `c/tests/test_getFromE2.py` | `b55f2f3d776ca0e5253fc0c371ff8544876c0c2a72c9e02fd421fab839ff48b0` | 4.2K | Python per-function behavior-equivalence test |
| `c/tests/test_getFromGPIO.py` | `67532e35eb2f1141030239595316c55ae2d82fda9600b88b5fdc9308305ad4bf` | 2.0K | Python per-function behavior-equivalence test |
| `c/tests/test_getHCANRegisterAddress.py` | `713e33fcd2052b9e09dd8fa201b98992a207d1b21e767138dbcf30575bd4166b` | 1.6K | Python per-function behavior-equivalence test |
| `c/tests/test_getKnockSensorADC.py` | `45bab7a9a8849c0d458eb9ebcb86880f7e938c2dfd872461797e011d9f8e4b36` | 4.9K | Python per-function behavior-equivalence test |
| `c/tests/test_getMAFSensorValue_745C.py` | `ab608f7b51c9fbb90f869b255bd0bd8c4107af0438e68339cf79dcc02a95ec13` | 4.3K | Tracked file |
| `c/tests/test_getSpeedLimitCal.py` | `4164cb90b5192c878d03f366e31ea1c9610bb1d1e858b243ac0ba2881ecec428` | 1.6K | Python per-function behavior-equivalence test |
| `c/tests/test_getThrottleLessThanLookupTimer_42f2c.py` | `1f04a8b2279dd1b4adab2785b531675785e41ed24b3dda9db7f0bda864d92238` | 4.3K | Tracked file |
| `c/tests/test_getVehicleSpeedForOBD___53600.py` | `1f553a7c30cec20f056798b29534ca7a7215f359f4f69d95697dc1a7ff534f69` | 7.1K | Tracked file |
| `c/tests/test_get_iat_threshold_3C214.py` | `0e64e233cdf1e9d1be49e2f64d4e3bd661a444a0b3c08f0518f817935fb20de0` | 3.9K | Tracked file |
| `c/tests/test_get_ignition_dwell_time_0x94C8.py` | `71d69ca711ef54acb02d8d75edba9f1d00abf10a7b2d3aa957ed051bd4132e00` | 5.4K | Tracked file |
| `c/tests/test_handleManualReset__d20c.py` | `bcc3c049c45f8cac26426e0c4874b2eebf5bcddb172fd4559178ddb1824ccaa1` | 2.2K | Tracked file |
| `c/tests/test_hcan_mbox_word_byteswap_write_cec8.py` | `38025a0bf2354f46432ff8e8798965d98572ec93e19617e951228893071fdfdb` | 2.2K | Tracked file |
| `c/tests/test_hw_init_2_41c.py` | `cc635d90887d1eb4e5a918b2048aa6a2429d63de63b0ccc1584d62f54dbd1321` | 2.1K | Tracked file |
| `c/tests/test_idle_speed_control_18054.py` | `87a045a1f6f9b4a2aea890decee5e67b91fac30c2ffcaae37f585d8dd2286869` | 5.5K | Python per-function behavior-equivalence test |
| `c/tests/test_idx_table_helpers_68780.c` | `7e53993a28fb46c76a24faa1025b60e282abdff1edd0e748bbeba06184897539` | 3.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_idx_table_helpers_68780.py` | `380496e78d8c160f267ff96a51c964648d54abf80309b2a37885c37944b9614a` | 4.7K | Python per-function behavior-equivalence test |
| `c/tests/test_ignitionDwellOutputInit.py` | `cafc80009806d27c3546601870e7843f5348620885dc47c25031f973c6c67c5d` | 6.4K | Python per-function behavior-equivalence test |
| `c/tests/test_ignition_something_calc_0x91FE.py` | `032ec0b7afe31a437e0458ddb4a275daf6c99638ff7d4191eaf156d5f9f540d0` | 8.1K | Tracked file |
| `c/tests/test_immo_init_check_dispatch_35104.py` | `606db716421dc7fb3c3f606f28fe4de8632a81d0a0346214f2901016fefce7bb` | 2.2K | Tracked file |
| `c/tests/test_init_getbrakingorinneutral_5ef5c_5ef5c.py` | `50590d00aa10e84ff6c4f04762e71d956ac9e0654f385893354c3e29c38bfe2b` | 10.9K | Tracked file |
| `c/tests/test_init_main_3E10.py` | `b89dd57cf9fa9b117bbec3a2c83ecf044c25ae3ea6f15e506c13a8605d59877f` | 9.2K | Tracked file |
| `c/tests/test_init_rotor_status_flags_1117a.py` | `5de20e620b544f7107c6d545e0c71a2f25ccc0187234b546633f1ac964f84e25` | 2.2K | Tracked file |
| `c/tests/test_init_sequence_547fa_547fa.py` | `6b52ee36d6ab92faf89583e6ce1a36632e26e819688f3b270767f2d9b5dcc0bb` | 7.5K | Tracked file |
| `c/tests/test_init_state_flags_18214.py` | `df081708157ecd4c78e2398307a221cbbe6c875a1ee7af64d8b245f653dd0a2a` | 2.1K | Tracked file |
| `c/tests/test_init_state_registers_0x4F1C0_4f1c0.py` | `17a67e95927a0b235e84bb2a502bf44ce87fdcc8b3d196669d79793a21765f31` | 7.8K | Tracked file |
| `c/tests/test_intake_port_timing_monitor_1bd20.py` | `9b7eed30b0169ee38246661fc78810049d75fb08d0b87cf3d1e52e1284570879` | 7.8K | Tracked file |
| `c/tests/test_interp_leaves.py` | `e1a9d0c940c77600197e3661b99b7bb1c168a153c69a2eee8d10e83d792d2155` | 7.6K | Python per-function behavior-equivalence test |
| `c/tests/test_is_eeprom_valid_624.py` | `262061a1cc3b9b3fc62f8ed082f08a924de9e371e7ca5e9d6c15da504d0b59c3` | 6.5K | Tracked file |
| `c/tests/test_isr_decrement_28126_28126.py` | `0be8817bd4c164b0e57c1709f0617e8ce7c2ef6ce7cb8cc5fcf4e6f0aeea31dc` | 7.3K | Tracked file |
| `c/tests/test_knockFunctionInit.py` | `9943ab87ade7fbc839adfbc14ae05a6cfef622de6bbba2260836f97731673664` | 1.5K | Python per-function behavior-equivalence test |
| `c/tests/test_knockSensorADCFault.py` | `3b426011b3fc93d37a3f778c21ccd04e9bc244caa3fa0155d226ef8279a4d7a4` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_knockSensorADCFault_c460.py` | `a8fa0cf233909f2b0701e1c9492b25ca920b19d4931720e96cce266c9b5efaf9` | 8.1K | Tracked file |
| `c/tests/test_knock_related_init_C3C8.py` | `c558ed187b24e209be27d8db235ab95c7eb2b2be2acd365963fec6e369cad9b7` | 6.6K | Tracked file |
| `c/tests/test_knock_sensor_adc_fault_C460.py` | `e571c55d9f1b57775dc04766e90c89229dcfc617fc7fca9a09fe202ba14e4edd` | 3.2K | Tracked file |
| `c/tests/test_knock_sensor_proc_3C06C_3c058.py` | `bf0830a541235b843a5f2b6ec26cf4e14494c7262ce6f2db330bee1ba13bd269` | 8.8K | Tracked file |
| `c/tests/test_kwp_session_frame_init_15a6.py` | `747c89b9b2832f312d17545ba577a6cc494942a439e4b8e9ae10c49714eea9f0` | 2.3K | Tracked file |
| `c/tests/test_ldexp_481C.py` | `03b2500eb408fece29c1852be674f206a4c2a494962ef15f2980879c56211cdd` | 5.5K | Tracked file |
| `c/tests/test_limitKnockRetardMax_CondRPM_13AE4.py` | `2ad1bce741dbfb45c4364b6cd5cc6670acd7f47d12ff01f460985c7b8a8617c7` | 3.8K | Tracked file |
| `c/tests/test_loadDatafromE2intoRAM_0x36BD6.py` | `b914aefb80af4d5a93a37bc31a8a29e9da32c4b62d91d4d916e06465845cdb96` | 4.0K | Tracked file |
| `c/tests/test_loadStatusRegister_ADDR.py` | `c8c723118fa7957978343e7ded4d5e7f326aae9a992db62ebb8e13e371ea2926` | 1.9K | Tracked file |
| `c/tests/test_load_blend_factor_limiter_0x16A30.py` | `fb8718ef88d3bf33264cbc2b4f17caaf72624ee529353148d362a16528509439` | 5.5K | Tracked file |
| `c/tests/test_maf_limits.py` | `b4ffad2611e33dd219f05c261d804b7a2ebbf538671412b4bb314fba75e79706` | 4.7K | Tracked file |
| `c/tests/test_main_entry_D49C.py` | `c3da07a969fc74313769b7b5e57d22daa259cc4e6a6f76d11b023c7b7e88cb67` | 6.0K | Tracked file |
| `c/tests/test_math_bitwise_366b8_366b8.py` | `636083cc7adb77c391356f71b2bd14cd170cc767c1d664ec630ff62ccb8c9794` | 2.2K | Tracked file |
| `c/tests/test_math_complement_2420_2420.py` | `78703565feeee8173a339baf00466265f5c71dacecd0a08e4cd59365d3948140` | 2.3K | Tracked file |
| `c/tests/test_math_complement_2430_2430.py` | `e32edeb1609f4e2f77d0373418aa6cd9d1a47beb6b98441d35b56ffdf72e3e70` | 2.3K | Tracked file |
| `c/tests/test_math_formatter_3e9a6_3e9a6.py` | `d40ca600d999320fb3a6f4b46f437933aee03dbb02845b48acdbbf5a807a6e46` | 7.2K | Tracked file |
| `c/tests/test_math_primitives.py` | `09c660b5143c2ef40d67d8cc4b2ac0a7c9e692e0915a4a915bf3f49b9ea17cf1` | 7.4K | Python per-function behavior-equivalence test |
| `c/tests/test_math_register_344da_344da.py` | `966abc1503ba43645a7137453c8ca6d60d54e97acb9d70da50593d37c7ec5331` | 6.0K | Tracked file |
| `c/tests/test_mem_accessors.py` | `6d1ada8423863bb62303186739fafa1c4c85a36e4911a8345657cdab61f6ae86` | 10.8K | Python per-function behavior-equivalence test |
| `c/tests/test_mem_char_533dc_533dc.py` | `f17bb9bf8de3a9fab86c84f1bf9e3cabf234c17d850a1aa00db9ad1a7faff86c` | 6.6K | Tracked file |
| `c/tests/test_mem_clear_5286_5286.py` | `514556bdbf08ed32866f592d7974111a1f55b618ddf6c6e4c1bc7ea2ed8dcda5` | 6.0K | Tracked file |
| `c/tests/test_mem_flag_fb60_fb60.py` | `fa08f28ccc074d81cd7e06b232f71d9dbb67d5d5606c3e314dfa4e2c24a0b585` | 6.0K | Tracked file |
| `c/tests/test_mem_mode_23710_23710.py` | `98e5ad338bc40982a57808ab534a06c98c1ca61ac39fa17d1928e43e904787ea` | 6.0K | Tracked file |
| `c/tests/test_mem_read_277de_277de.py` | `314fcc4b711ef489865441464bff9b4d0803b57c6a18c5206971b980cc8a78da` | 6.3K | Tracked file |
| `c/tests/test_memcpy_bytewise_unroll4.py` | `edfe67df156ea880ea18ba0387e4b93a2379c48e5add5ef9bcb8db0e999d5371` | 4.2K | Python per-function behavior-equivalence test |
| `c/tests/test_memory_match_accumulate_583E4.py` | `ccaf8c06e13f2e0aef7ee5fe1f4087c85c41bb6e7fd8001b47cf4b38231288d8` | 1.4K | Tracked file |
| `c/tests/test_mod32_signed.c` | `09df6a2ac60b399d2b2e2725519455492e51636c5cd06b63132feeda157cc512` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_mul32_saturated_231c.py` | `83a9dba29cfcf8118f7dfbb0eafe63c4109a9d36e4d2c3c08eb74e1519b26168` | 2.2K | Tracked file |
| `c/tests/test_nop_delay_40cycles.py` | `5c13923de4b431ca89b2fb743ad28a40c98b8c5d6fa48db063da8c45a1798546` | 1.3K | Python per-function behavior-equivalence test |
| `c/tests/test_nothingFunc2_5ee7e.py` | `f4fe97b83a7ad594ec88f260714c7590aa7cd2ee946a44e01d0ba2f201d42499` | 2.4K | Tracked file |
| `c/tests/test_o2_lambda.py` | `1d2383a365a9026cca36fb2f2002c3f839541f39e20b6deb93e3e99633560fc0` | 7.0K | Python per-function behavior-equivalence test |
| `c/tests/test_o2_lambda_more.py` | `5f63bb602651d015ae41eb7d85d1390a804763cd09921e061ec7f90533225d76` | 19.0K | Tracked file |
| `c/tests/test_obd_dtc_find_0x643D4.c` | `0a3cdd41c8deae2100535369e768d695564d80f319de9199f18e23f05d247b0b` | 2.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_dtc_find_0x643D4.py` | `59c4d5300901a7b1a4b70509454ea4d824cb140d268fcf9f368acc3f8dc9ef29` | 3.0K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_dtc_find_0x6443E.c` | `1a49d996823a65a97d216c2f54fe08ad50565bfbf0059cd42340835e5d4e9061` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_dtc_find_0x6443E.py` | `fabc2d27b09d72cd7d52fe12dcb56510024781830597af70d47af93543bbd4ae` | 2.8K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_dtc_row_update_0x64258.c` | `de7ea3ff21effc3672eac022fdf0941a82446e9bf2603d5a1af8822c66a339db` | 2.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_dtc_row_update_0x64258.py` | `320a37196088e7ee9aedb574e173628633138699914ffbbf9b3213d503ef6f81` | 3.1K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_dtc_row_update_0x64418.c` | `6f2451eb000f7952f3c36da24795c103c709ca71918b99972f27a3f8bb845451` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_dtc_row_update_0x64418.py` | `f9da558bbdbe111afb41a506fff9f8d7d995592d731587027ad49951ca0cf5f8` | 2.5K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_dtc_row_update_0x64490.c` | `4e38cd87554bf870a8ee6274f51854012efa2544776df3a43d489f7eedde84c5` | 2.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_dtc_row_update_0x64490.py` | `6d87f9db5067565d7abe207a28673a8834e938612f7c96671f8f618efa9ac05d` | 2.9K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_freezeframe_uds01.py` | `889724918fad4e17d225a82bee86ca0ebe3f08b4dbe2b544a7891280699a3288` | 9.8K | Tracked file |
| `c/tests/test_obd_pid_getters.py` | `5ba483af51f293b76b5f2b612bc6927b16f4d9c201f8625c395dc6a4b57f76e1` | 3.7K | Tracked file |
| `c/tests/test_obd_pid_getters2.py` | `7f0df96ba6cdd05b4aec89277668c3145396162e0c05b73b7d7e7f2beccceee2` | 5.2K | Tracked file |
| `c/tests/test_obd_pid_getters3.py` | `0f2ebbc5b48740dcf5953ae36c6a994782a2d538269317c64e894b888897a4d2` | 11.5K | Tracked file |
| `c/tests/test_obd_service_handler_632D6.c` | `2db2fd211e11833089cb9269cc02d4f53cc79c1fb6dba152a935c525cf3a941b` | 2.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_service_handler_632D6.py` | `c459bcde18fa5ca55bfb8f56b210f69536b4740d72572ec4ebab76b4dcc2ea6a` | 2.5K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_service_handler_63312.c` | `51923c9c36e66f8a8021594f80127ce1cc0221e91537cdd1af8414857978f4f2` | 2.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_service_handler_63312.py` | `88ee1da4ae1e22c914c5ea7bbb2537a61831018d7817c2d1d398b62c84301924` | 2.3K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_service_handler_63834.c` | `b0245b1b5952c4f3255935b8c15ed6db9a31d2b31965f089206d5ef19e28e220` | 3.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_service_handler_63834.py` | `122382471c2b3b5b28f070e517dd7559f9ee1caaa98d4403c10ba875fb3132f4` | 3.3K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_service_handler_638A6_638a6.py` | `51cdb60268985f22ca376a45d89959e7f0e337d7c98948590e68f1af05ebde48` | 2.5K | Tracked file |
| `c/tests/test_obd_service_handler_63A82_63a82.py` | `3856ec2732756e723613f76115ed81919d83c789f387ff90064b7ad235b13b5a` | 2.5K | Tracked file |
| `c/tests/test_obd_service_handler_63AF4_63af4.py` | `3b5073fd20ae40b84efba5a5bad373693911fd515acfb2f4353c34f44adb953b` | 2.5K | Tracked file |
| `c/tests/test_obd_service_handler_63B46.c` | `bd2a362041b6ac4c7a4a1dfe6ed54dfb79ba5d8662d788b5e633f7ed90813443` | 2.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_service_handler_63B46.py` | `8e2e444c7389f0c159ef0ec83f1a062af8673b209bc4889bd9f5e85bb4845ba7` | 2.8K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_service_handler_63BE6_63be6.py` | `f4f88c21717e7e2d4acca32f98d0ad821869b340d5be5403fe48b9b9d8faa5f0` | 2.5K | Tracked file |
| `c/tests/test_obd_service_handler_63C66_63c66.py` | `d89bbb2dcd15e01a261633279efb433dfadd322e91a4d307b4c2c3851c196e82` | 2.5K | Tracked file |
| `c/tests/test_obd_service_handler_648B4.c` | `7ade23bb482a6958cd7574aa1d77f672fdeb28b5963a7522446afbae42f14ab4` | 2.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_service_handler_648B4.py` | `6fe229f96568dde215b68a041814d139368d8b7a392c302c879213f06f3ab0b0` | 2.9K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_service_handler_670E6_670e6.py` | `a5dd40ad43d358bde6fc9744e81a25d0ea8a1a8d82c267e271ac9d5d0865376b` | 2.8K | Tracked file |
| `c/tests/test_obd_service_handler_685F8_685f8.py` | `471fda4979ae31ff59250f293b80105dfdb055f022a18632ea076e95e6734bb9` | 2.5K | Tracked file |
| `c/tests/test_obd_service_handler_68656_68656.py` | `473021f59226acca965af6bb0cb1a6e171e9d7a527f9c8141f7cb7c0d407812a` | 2.5K | Tracked file |
| `c/tests/test_obd_service_handler_686B4_686b4.py` | `70f964edc7cff2cde2cef7e1a3dea446e924f811167867e08efd8aeea94b19a8` | 2.5K | Tracked file |
| `c/tests/test_obd_service_handler_68DD4_68dd4.py` | `22c0cf8021c7b5a5b25bda605e9e095fb89f41b3ad50483c38dd23a5fe1f2cd2` | 7.2K | Tracked file |
| `c/tests/test_obd_service_handler_68DF0_68df0.py` | `7d0807c6e58ad2f92ef21e3d4b824f3aa29e5ac217bbda48d74050def8ec0fb2` | 2.2K | Tracked file |
| `c/tests/test_obd_service_handler_68E10_68e10.py` | `24829ca0262820ea4f4185aad6e9b9a68e1ea4f5f34f3367cff45c58d32893d1` | 6.8K | Tracked file |
| `c/tests/test_obd_service_handler_691A0_691a0.py` | `34fb1f7ac2e64b7a9079e870cd242d48005a1b9563e6e8e3f5015398ecd09907` | 6.5K | Tracked file |
| `c/tests/test_obd_service_handler_69524_69524.py` | `ec76d755b19964dfe61857a30714aa44fd4b4c0b8e2f51682fad7a62113b33ec` | 2.3K | Tracked file |
| `c/tests/test_obd_service_handler_6954C_6954c.py` | `2bdd4430b5cecc43a9462c0f6d5651d4771a5c0187ac306eda18a7e32e164e58` | 2.3K | Tracked file |
| `c/tests/test_obd_service_handler_695D4_695d4.py` | `5b884916dd13cb8cbd8be9a00790238e76cc7d88ad0624a68147ad10fcad69d1` | 2.2K | Tracked file |
| `c/tests/test_obd_service_handler_695E4_695e4.py` | `354adca85100c1121c78ab132d18dd8e985d1d7218190295358a919f6056ebd0` | 2.2K | Tracked file |
| `c/tests/test_obd_service_handler_696D4_696d4.py` | `a09bb724dcb6649e90ec23043daa1a442734c9b6519ba2f7e3bd43e0a8ec4c88` | 6.0K | Tracked file |
| `c/tests/test_obd_service_handler_6B0A6_6b0a6.py` | `c671b56f59159f257de8774993a70d78cbb79e98e5cc9613adff06f3266f5592` | 2.3K | Tracked file |
| `c/tests/test_obd_service_handler_6C166_6c166.py` | `51eafc6627f23f1c3ee02498e6e4b5fa2fd3b4bcd9e3c7ef79a49839cc43d5a9` | 2.3K | Tracked file |
| `c/tests/test_obd_vars_vector.py` | `9a824fda9857e6b29d4e14adbba3bbef6422a79b5b18413526a8e5acc91d8d0f` | 15.9K | Tracked file |
| `c/tests/test_omp_accessors.py` | `e9eb93e8b8c276a5ca62869ced12caeec7b05f09dced876bb8f4574c5b1a533e` | 5.3K | Python per-function behavior-equivalence test |
| `c/tests/test_omp_control_task_1825E.py` | `b56e523b50bc0997c9724da7be31d297ede14e86e50ab76bec811d76f5c938a5` | 12.8K | Tracked file |
| `c/tests/test_omp_rotor_overshoot_detector_18CC0.py` | `fa9b094b6a34b686d50d7fabeb083fad0378be731fa3617cd8b3e4852c2e4da4` | 8.1K | Python per-function behavior-equivalence test |
| `c/tests/test_omp_stepper_waveform_driver.py` | `154ae7403ad7e6966a01788e8a38bedb640e5c3f84b5a8bc0d80f6e83d9f219b` | 5.7K | Python per-function behavior-equivalence test |
| `c/tests/test_omp_waveform_state_machine_18860.py` | `5534180427a1bc02536de0438b200e68443e9815f2f29bbe89b0f64617bbcf51` | 7.1K | Python per-function behavior-equivalence test |
| `c/tests/test_osTaskScheduler.c` | `f763e85fc9bdcd7f7dfed3e9499f50a5dc503e619cf6fa3a59dcb88f8e75215f` | 7.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_os_context_switch_3DB0.py` | `a7cbe230f6e2bf9ccc1c478b6b85dc918a90bed6c8ced2f8d71e28b85254e0be` | 6.3K | Python per-function behavior-equivalence test |
| `c/tests/test_output_per_rotor_ignition_dwell_0x11218.py` | `06d1e8d05818b68d0f9a31164582010242004189f3911b2d4800052d50bb0002` | 5.4K | Tracked file |
| `c/tests/test_output_spark2_0x8E20.py` | `010e48ad5574883da25b97f4e26ce7ebcfa0bd09aa7decd33cb547cd67e2ea6e` | 6.5K | Tracked file |
| `c/tests/test_output_spark_0x8DAE.py` | `04ff0bc62d256e259b256e0d10def541c0e5e372c36ccf5633ee0ff21b928c63` | 6.3K | Tracked file |
| `c/tests/test_output_spark_0x8DE6.py` | `8971f196181d10b10a570dd26ad48b273de6cced78febfb0cc182258d9ba380f` | 6.6K | Tracked file |
| `c/tests/test_port_bitfield_check_sensor_flag_32174_32174.py` | `6e63b66ebbcf8efd523613e9c8db6167844d41b003fdc4d973a3745a798b7600` | 7.2K | Tracked file |
| `c/tests/test_port_byte_copy_simple_339F8_339f8.py` | `3372ba8801640ea60a6f79fc6c1319debd1ae6c1992491ae580e6dde8cc76a65` | 6.2K | Tracked file |
| `c/tests/test_port_helpers.py` | `ce21feca580410897a23608d47e481660807e8e99515d2619ed35ec1b51f0ecd` | 3.7K | Python per-function behavior-equivalence test |
| `c/tests/test_pressure_delta_monitor_1AED2.py` | `c9978e9bdf98f7405d4031fa93ce662043054e35e28f0c18c3248514cc47a692` | 5.3K | Tracked file |
| `c/tests/test_pulse_filter_done_flag_fc9e.py` | `fdb4f85d7220ca5a84447028663db3e1225dfae48310024c8ccb07e5ad5f216a` | 6.0K | Tracked file |
| `c/tests/test_purge_subsystem.py` | `583a31da56f1913fc9f628fc5bf4e3d6fea4ff305bf15e4f1603ed8c0c9cd6a4` | 5.9K | Python per-function behavior-equivalence test |
| `c/tests/test_radiator_fan_relay.py` | `e0fbb30fbd041e363ddd0cee2b863e0571c98bccd4fc62fbb79db031dec0f6f9` | 1.3K | Python per-function behavior-equivalence test |
| `c/tests/test_ram_byte_copy_2A300_2a300.py` | `d6440f585eabb63e9344c29484482a08d1b5947e843a3831c482e172164ebd4e` | 6.2K | Tracked file |
| `c/tests/test_ram_init_zero_29FFC_29ffc.py` | `5413549335fc1799731b60751000756587f0dd537def7a07ecf6a2d9d8c2fa81` | 6.0K | Tracked file |
| `c/tests/test_ram_word_copy_2AB6A_2ab6a.py` | `f7258d306b8fb5e1ddd7415cb895951a604957a4da8d8abe3ad7bec66a35b2df` | 6.2K | Tracked file |
| `c/tests/test_readECMVoltage_735C.py` | `2390a2fc32d91d3f7da4a55fbf6c22acb7f7d28a808c699176e2da5f8bcee61d` | 4.0K | Tracked file |
| `c/tests/test_req_queue_69602.c` | `80e2505fea9b0e2c438d360ba36d10c01ae6ef6610c1578e42e46ef9cb540cab` | 3.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_req_queue_69602.py` | `29c646cb46c615b93a3716f547fcb5d230f4ff3efd609382774117affe2f658d` | 3.1K | Python per-function behavior-equivalence test |
| `c/tests/test_reset_handler_4E0.py` | `90f42f8ee528c2c27550a6393a2636c8f1448acfda4014680f3b85d6a4c0a11c` | 11.0K | Tracked file |
| `c/tests/test_returnDwellTime_fp_0x1120A.py` | `4110a374b4e00c61e156c5d57387c2cb066072bcb09035aad168b63ae5aaa00e` | 3.7K | Tracked file |
| `c/tests/test_revLimitFuelCutInit.py` | `d57950d4cff5062174f19e85878561325658cb1301eab2251c985e248c8998af` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_rev_converter_552fe_552fe.py` | `43bb09a8c847ce627e13e9337c081e521ddf0683a127074b01dabeb37eabcc20` | 6.4K | Tracked file |
| `c/tests/test_rev_limit_0x59440_59440.py` | `a2357137a5430e7641879f816ad4ba1ef4e31096ee97b3a88fdc140df387ce26` | 6.6K | Tracked file |
| `c/tests/test_rotor_sync_gate_state_ctrl_2100A.py` | `2f6370e99677cf8800b4acbb89bd526e8841646485fdf07fab68d970801d5354` | 8.5K | Tracked file |
| `c/tests/test_rotor_sync_position_detector.py` | `8c1485a66c304f3095221cca21af21183b313bc751cace19ea8bf97f5a857858` | 6.7K | Python per-function behavior-equivalence test |
| `c/tests/test_rpm_rev_limiter_47AF8_47af8.py` | `f8e155d2566e2260c197486b58868326329c2366dd38086cc64008db9d2a27f1` | 7.0K | Tracked file |
| `c/tests/test_rtos_task_register_a140_96de.py` | `1ee3126caf6d58afaa25da0f23aad464b4a56c673aa015ec38aea1ad6895ed71` | 2.2K | Tracked file |
| `c/tests/test_saturated_decrement_27DD2_27dd2.py` | `5ca4538b765ac991c1fd132bbdfe6df2ed1a940923e383294c60d0ceda1e0805` | 7.3K | Tracked file |
| `c/tests/test_secondary_boot_main_A038.py` | `fdb2a36bc16230e379aa5d062978230642b73467b65aa4cc48db1ce5a5767504` | 7.5K | Tracked file |
| `c/tests/test_securityNotUnlocked_56910.py` | `b7867eae67b8f89d25dcfe862301ee9b4bfd5364bee4eef817d51ce76ad97f4c` | 6.7K | Tracked file |
| `c/tests/test_security_access.py` | `89cd12f7e0888a85a12b95bba412d275ca673936892aa9bfe4787dcf331a0f94` | 24.3K | Python per-function behavior-equivalence test |
| `c/tests/test_security_statecheck.py` | `6130033c71e80ba4ea31f0b0aa8e1b4d64c39caa6f49d200e8571fba8e0104d3` | 6.9K | Tracked file |
| `c/tests/test_seed_gen_5699A.py` | `b708b7759b70101f36842981f6e3047c957b56b491da43589dbd22bbb52cb1f8` | 6.7K | Tracked file |
| `c/tests/test_seed_mixer_366B8.py` | `af3b36fa8a3cb64051ceaa31cf9c7696b2fa5118138dafa315b64a3c45262606` | 3.3K | Tracked file |
| `c/tests/test_semaphore_post_4C880_4c880.py` | `34b2b9fe40d1f7c26b9bc1e238ad40f9afdf3c8f223d44e3bc26a688231d6812` | 6.0K | Tracked file |
| `c/tests/test_sensorADCRead_68A8.py` | `6dabcb479eb15014a8de57c73a3c3364ee378ce0d65203f6a29172be01e9a3a0` | 5.3K | Tracked file |
| `c/tests/test_sensor_check_float_bounds_adjust_E0DE.py` | `d88117d3d75346c9facaf799060d347a28d81cb4feb23db207d65b776d6909a7` | 3.4K | Tracked file |
| `c/tests/test_sensor_extract_6096c_6096c.py` | `453b3dfadf72ba0c458f17376730245eeaac408c1b8f8c107cc51bf6f1371ffa` | 2.2K | Tracked file |
| `c/tests/test_sensor_latch_ch0_72b4.py` | `52f707f6ccc308cdd22675420e283c70716add27c907ca9e36d56d7ce4b0b99f` | 3.8K | Tracked file |
| `c/tests/test_sensor_latch_ch1_7354.py` | `9199cfbfa11e5a88f2f923881444ec0ba5d92f25c948c030842566bcc208083e` | 3.8K | Tracked file |
| `c/tests/test_sensor_latch_ch2_73bc.py` | `383ff77c514772e40d06b1537a680e009cdcc90180edf5fc76a9faaa3750de80` | 3.8K | Tracked file |
| `c/tests/test_sensor_range_check_3ED0C.py` | `67b45dd695d4faae7c668ed047abcd308508537b43412b4f739922eb98b9d9f7` | 2.5K | Tracked file |
| `c/tests/test_sensor_tps_delta_lookup_store_12e94.py` | `8a68f4daad6037a97732cfa5a34396699ce1e65f4e37f45a6602e27e637250d6` | 2.4K | Tracked file |
| `c/tests/test_sensor_wrapper_4f216_4f216.py` | `1d1a2d5a6d5f4a009e9136c4438cc16fa2ca289839d95c15e5705644ca746f3d` | 7.4K | Tracked file |
| `c/tests/test_sentinel_equality_check_5687A.py` | `b8b2098c0df50cb5443b7dece3a9308bc4e4dfece2b3f621bd414076e3439518` | 2.0K | Tracked file |
| `c/tests/test_setAlternatorWarningLight.py` | `574567bfad9bcf196af11aeba9f6bf72ecf95b07975cc3c0dab6d45be256c6d5` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_setGearBools_a_2cf80.py` | `673d011281c6de621f1c07661036962c1801d6be9e5b48f46081cf1115a47030` | 10.1K | Tracked file |
| `c/tests/test_setImmoCANTXData_369B8.py` | `c90ccadf696f89975baeeba7d51aad7ae572121268dccf66136460747156dbae` | 6.7K | Tracked file |
| `c/tests/test_setImmoLight_263C8.py` | `5bffbfbac48367c54e3e22a7d4ebe13142f4b68b62f9b55b870c17b9dd04f679` | 3.0K | Tracked file |
| `c/tests/test_setMemInsideFUNCto1_0x3E3F0.py` | `605f26e2bc898fc64274673fa5ffee2c3819c67fa6b2eecb0a5f651365877333` | 1.7K | Tracked file |
| `c/tests/test_setRegister_REG_BIT_VAL.py` | `8f85bea3c8e621feb3327f9f9cfd003c1dae4a4ab290f235c54f7d1885e29d27` | 2.3K | Python per-function behavior-equivalence test |
| `c/tests/test_setRegisters_4d2e.py` | `10d6b8db7db3ee2beaf19c2c25dc246961eb9bc9ba16f361dc5d279430356700` | 2.1K | Tracked file |
| `c/tests/test_setSR_getSR.py` | `f9202e1fa8db4bde87f9848a740ac4083e9ba859f3995ae0a5c3e942d1b51707` | 10.1K | Python per-function behavior-equivalence test |
| `c/tests/test_set_intake_target_flag_23FD0_23fd0.py` | `d43d87d7dd2185d7cddfff7ac8f91582ac76c05e521adce51e503fd675bf04e4` | 6.1K | Tracked file |
| `c/tests/test_shift_left_logical_r0.py` | `0ac0bdd174f41ed52d4acc2c85569a355f49efcdee183df259c7cb01587b9c99` | 3.2K | Python per-function behavior-equivalence test |
| `c/tests/test_shift_right_8_r0.py` | `7f1566d157512066db82336620da721e5987eba837efdb0475bef856f1308262` | 3.1K | Python per-function behavior-equivalence test |
| `c/tests/test_shift_right_arithmetic_r0.py` | `df0ab58bc1639666fdb4e224c83dbd554e6bce43d536618400ecc74cf86af279` | 3.5K | Python per-function behavior-equivalence test |
| `c/tests/test_shift_right_logical_r0.py` | `e557958f2eeecbc05b59ed87041570cc04eb2a8f8a7e1c39484a7ac0393627ac` | 3.2K | Python per-function behavior-equivalence test |
| `c/tests/test_spark_output_enable_fault_mask_0x10DC8.py` | `5679d944889a2b225f59e18983980fb6cdbbff76fd6822182e7d2ee6316690dd` | 6.2K | Tracked file |
| `c/tests/test_split_selector_decoder_48C12.py` | `db9b9cc3daaed739277b99dfa9c28cf513f5159c4eb49d1fdd31eba9bda66851` | 4.0K | Tracked file |
| `c/tests/test_split_selector_state_ctrl_487DC.py` | `29311eaca1dbf2e0ccd4dc972f47d882a392e1a2ac881e971c714c93df6fa9f9` | 7.7K | Tracked file |
| `c/tests/test_ssv_control.py` | `077a95a2985e9e79bacb4b2c62c6a903ac28f5bf413e729d471aa65437690ee1` | 5.0K | Python per-function behavior-equivalence test |
| `c/tests/test_stability_control_0x5957C_5957c.py` | `f45925315164f96eb78a76f0dee51f5f1b387dcf306dd043ad88d2c2a4f1ab8f` | 6.6K | Tracked file |
| `c/tests/test_state_reset_multi_word_2786C_2786c.py` | `d3d1d3d368f64a4362b749acda4775992bd3688480cda51024142b71881dad0e` | 8.2K | Tracked file |
| `c/tests/test_store_knock_learn_buffer.py` | `ed90e97a871282bef7e5eb19167cace763e939cfbdba500025aeb605ed076d63` | 7.1K | Python per-function behavior-equivalence test |
| `c/tests/test_taskEndRoutine.py` | `7fb798b9811d64eb2cac0c3cd3b0804afd8b028fa856dabb8967cd77eef9eaa4` | 4.7K | Python per-function behavior-equivalence test |
| `c/tests/test_task_context_switch_3AD8.py` | `8bff8052b8301939523603b528be437eb4556427acd65874a82cf67c471176ff` | 8.2K | Tracked file |
| `c/tests/test_task_execute_by_index.py` | `3b15eb3a9abb0203b44eea5066ce68efb704801a4ea35717838d8a8ff4c8ab02` | 4.9K | Python per-function behavior-equivalence test |
| `c/tests/test_task_flag_run_C.py` | `ecbaa12aef78ef9ca8349a329fa9c3ec247225530f80116d8204bbff6f541ade` | 2.4K | Python per-function behavior-equivalence test |
| `c/tests/test_task_full_context_save.py` | `b7a89b0c4a72bff97db11a8917047867522276322f4e52ec46355da9fc1e4339` | 8.5K | Python per-function behavior-equivalence test |
| `c/tests/test_task_full_context_save_3BF4.py` | `31eeed31ed877a96c6ee7bec0e3757c4901f26a994be0b2ff1cdb3b401cbe175` | 7.7K | Tracked file |
| `c/tests/test_temperature_gauge_0x5AA5C.c` | `c062994160aa2bb9f6837586beef0db5add165c6daf9e83bb26b22ff4f0aae9f` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_temperature_gauge_0x5AA5C.py` | `4ba82d22dfcf8b2bc12a04449bcc2b5283f50acbc7f398b47e1034b7442c9932` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_threshold_counter_inc_latch_41cf2.py` | `1f1b7615f79b6c62ec4623f9c921a45643f2ee0fd761597427d9cfe073ad9033` | 2.2K | Tracked file |
| `c/tests/test_throttle_position_adc_reader_19FC0.py` | `6f149fb1a02766e01d0c2691369c94aea5eb562ef185d83846ed60ec87c1dc98` | 4.6K | Tracked file |
| `c/tests/test_timer1_init_and_start_a6c0.py` | `06a648d2f17ddf5b65222e96fb68a6d8a3390e0a090180537617255eb0eee148` | 7.3K | Tracked file |
| `c/tests/test_timer_state_debounce_latch_4efa2.py` | `cc33924bb5281603e55602c86a15bfc3cceb0544d2ecfb388beb14a7410e7fe9` | 2.2K | Tracked file |
| `c/tests/test_timer_xor_shift_operation_37328_37328.py` | `f85bb5f13fad7af70798e5fd089d60c717125ca1b4f8c73171a58627d2775711` | 7.5K | Tracked file |
| `c/tests/test_udsResponseRelated2_6772e.py` | `853ef35c17440f72f0f1af78311a5f5be4973f818560f971f7db8cb77ea4011d` | 2.2K | Tracked file |
| `c/tests/test_udsServiceResponse_66a74.py` | `3365df33b96e637feae633607e53a90adc7c87325af2ba24dbb0e30d7a31e47c` | 2.2K | Tracked file |
| `c/tests/test_uds_mode22_data_getter_53770_responder_54e0c.py` | `17add23cdb3eda0990a6d23c371d1b88c56a1df6f81bfb2cd2450c7fbdebc886` | 2.5K | Tracked file |
| `c/tests/test_uds_mode22_data_getter_53b28_responder_55020.py` | `f585efa8053ebee2b6b5565b4dd06119c80ec9bf74ebe2bdbffd0bdc853893ad` | 2.2K | Tracked file |
| `c/tests/test_uds_mode22_did_4a_getter_55034.py` | `03dc80ec2867129429084384a55605d857cfe960e5adc4fcd3b8dadcf9241649` | 3.9K | Tracked file |
| `c/tests/test_uds_mode22_evap_purge_responder_54e22.py` | `56feb1b80f728d98324588974ebad6d295725e08b6dd8052f1a0c6f25f3517f1` | 2.2K | Tracked file |
| `c/tests/test_updateE2RAMBasedOnInput_0x36D0C.py` | `8658cb5c356726bc8b74e9dbdd4397e84a5d909de58e2984c24ca61785b5c758` | 5.2K | Tracked file |
| `c/tests/test_updateMemoryAtAddress_8bit_ADDR_VAL_3ee58.py` | `5eca5292c678f9f8a078ab6d8c84e3f7a89f578d637af83282478b7aa31ae627` | 6.5K | Tracked file |
| `c/tests/test_util_shift_467a_467a.py` | `8c5bcc4884bdb504d6e02e2a071cfc761d7deeb8146c5a1694d880be9c52a365` | 2.7K | Tracked file |
| `c/tests/test_util_taillight_59d56_59d56.py` | `ce7e50b13a4946f397d9a75e8d9b7503ce5bddecaa8d2fb29485ac949c718be7` | 2.2K | Tracked file |
| `c/tests/test_vfad_control_35BBC.py` | `bb91fbadb598fc5a6ba61fa4f5764b3ae20cb39b734bb10a05be84fc2c3268f6` | 3.6K | Python per-function behavior-equivalence test |
| `c/tests/test_vis_intake_control.py` | `a2472fa0c428753804bb0d0144c220284daa53aa43daadbe102a160bd4130385` | 5.5K | Python per-function behavior-equivalence test |
| `c/tests/test_wankel_sequential_inj_4870E_4870e.py` | `faa64c4863c589bbf4057ed178480684704522976f4263ec63e44344ca385765` | 6.2K | Tracked file |
| `c/tests/test_warning_light_0x5AADE.c` | `9a4cdacdb5fc30584bb14a802cb82d83580e07d23461f5c5b3fd62096f9333e6` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_warning_light_0x5AADE.py` | `479018ca50ddd0426814cf7d00eabc5a38e0565b72ac388dfdabba0d13522823` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_wdt_disable_1380.py` | `24a394840003ca8da78a057e52c8732e34924fe59fc0bff1261faf26bb11179b` | 6.7K | Tracked file |
| `c/tests/test_wdt_disable_and_set_timer_502c.py` | `ee29452415ea4cf61f6f42a9fe19059bff9677ba9a72cdb2d6244ce00d5cf653` | 6.4K | Tracked file |
| `c/tests/test_whileLoop.py` | `8b13b430963add2187b9344a02f583c21e6ebd6b87a07a5fe4531a2a5b119b58` | 1.3K | Python per-function behavior-equivalence test |
| `c/tests/test_writeToE2RAMArea_0x39124.py` | `632203bb721c7d6a85d8c4b2fe72ee04296337432007c613cce8f621d1ae6b2f` | 2.7K | Tracked file |
| `c/tests/test_write_o2_sensor_trim_12b54.py` | `35f2c2b94c081861c721285eb0755fa0a3b02f25b78fe3fb4f75e8aadcd401e4` | 6.2K | Tracked file |
| `c/tests/verify_emu.py` | `f583e1d294b0966f7203a3eb0addfcbf2c9d828abfc3292a2965e3f8d526de51` | 3.0K | Python per-function behavior-equivalence test |

## tools

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `tools/ASM_BASELINE.md` | `9d44b22cedc71a4fda4000e7bdd93a071b8778a4c00fd1838bee5414b811977c` | 4.3K | Method, byte-exact proof, coverage, limits, next steps |
| `tools/README.md` | `bfb2018e4b0d9e7fe187ecd6cc6b9a5217a82c0dfbb7e9d4635ada77b7bfc071` | 3.2K | Directory README |
| `tools/c_lift_ops.py` | `fb83d5635b69562f74ff588b71ce0479803d6a623e02916acd42d5401a23315e` | 34.1K | Tracked file |
| `tools/callgraph.py` | `25a5f5a936ebbca11d2bf7ec888db5de8d9a5fb01c4440992c593e500cc59ee3` | 7.6K | RE tool (see tools/README.md) |
| `tools/classify_functions.py` | `8a8fed345454482ef296379cdcd087b38e1c9da396ea3511d1a5b5992165c41c` | 29.3K | Tracked file |
| `tools/cross_decode.py` | `3a6532e07091d41fc4f4f94d3890bec87cb37726f7fb0bb8c3a6c9e32cf028c8` | 12.2K | RE tool (see tools/README.md) |
| `tools/denso_ck.py` | `3b4f2f74ea4256bf2a16e667ee1e56af7220167d8ec04f3a3fa38ba15c26fb33` | 1.8K | RE tool (see tools/README.md) |
| `tools/disasm_sh2e.py` | `8285f0540ba48534d4df9bafd6f1b2515caaf992133f8c1cdd3e78151f29452a` | 19.2K | RE tool (see tools/README.md) |
| `tools/extract_func.py` | `9470ed47cfe15f275c6478028d735daf225056397ae97140ac59c128019db7a7` | 3.9K | RE tool (see tools/README.md) |
| `tools/fix_romcodes.py` | `a4ac233c37e70a09e297a246fdd016e69c0d824486a8a9e15cb9dd0be530a007` | 3.0K | Tracked file |
| `tools/gen_c_lift.py` | `77fc5036a98975d449b6c6a20296812b05dbaedd3d901b461630943ced4daa83` | 61.2K | Tracked file |
| `tools/gen_c_lift_v3.py` | `0aa30728feba5a9572c4007fa3cec5e5083cb07ee00028cff6a7e1fed4d2cc6a` | 34.6K | Tracked file |
| `tools/gen_catalog.py` | `13440ac2ec6b7bd770c4705c1d4242daf23e6928bf7390ea3c89ea31d123a555` | 39.7K | Tracked file |
| `tools/gen_manifest.py` | `2154966f6530667e55ae6189a6554b0e244d091dff9cf2d7bf213f4383c70e75` | 9.5K | Regenerates MANIFEST.md (repo inventory; python3 tools/gen_manifest.py) |
| `tools/get_toolchain.sh` | `869564ff4694cab83827f0fc9299be489a2b7ae76b25bb2d51c00d7a56aab69c` | 3.1K | RE tool script (see tools/README.md) |
| `tools/idamap.py` | `b9f3102edce605174eb4c90b476b51bb28811e2fa22719cebbfca154305bd3c3` | 4.8K | RE tool (see tools/README.md) |
| `tools/mapscan.py` | `9bdb9675ca4faba36443b7eeaaa68d4fb014dd0ff4f3a50c823f3be715a9ce6b` | 5.3K | RE tool (see tools/README.md) |
| `tools/mazda_security.py` | `7ccfa08b801febccc1e9a9f1bc2f076b73d5c51ff65704cf3cf99808e2f11b89` | 4.7K | RE tool (see tools/README.md) |
| `tools/opcode_audit.py` | `5f7d812612caeb380ee38e0e6db7736af5db36bf1e9290b76b7642fe6fc0f1a7` | 12.4K | RE tool (see tools/README.md) |
| `tools/organize_src.py` | `952eab08198e20668fe3d8a2b572222993a2247516fb18814e68325cf02a65b4` | 9.5K | RE tool (see tools/README.md) |
| `tools/rom2asm.py` | `a0cc400125d3f3f913285fc873b73b784c1f2d3f2d07ed139fdb6a7112722da4` | 6.5K | RE tool (see tools/README.md) |
| `tools/rom_rebuild.py` | `389f1044dda89555dd85b02c8f351b6371f02139763eb531af042365000c88a7` | 7.3K | RE tool (see tools/README.md) |
| `tools/run_tests_parallel.py` | `c63d357fc7283b6a4d7e95ca1401c5983b2132a065a792d4480f1155722dcb7d` | 5.1K | Parallel test runner (pytest, all suites) |
| `tools/sh2emu.py` | `04a8d469e76ecfd38ba5fab5d9310de4af64a529e3820c6ae4740459d07131bc` | 30.9K | RE tool (see tools/README.md) |
| `tools/verify_all.sh` | `532ae54090d86461560542a95a19b9ed3f16654e84ccf0f0dc60531df0f5f53d` | 4.1K | RE tool script (see tools/README.md) |
| `tools/verify_formal.py` | `eebf7f29d156405941f30c21d29398776e140a191a449262cdf9b0c144c28332` | 30.6K | Tracked file |
| `tools/xmap_names.py` | `ee1bb9ec6bf9dc33695be8527fb4454a291732ae307a8d1ec696b0f77ce358a2` | 5.6K | RE tool (see tools/README.md) |

## tools/tests

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `tools/tests/test_cross_seedkey.py` | `1631b47f1789048a3211b5c8ce946d60c0ef8439506cae7f9fbd42c4e2a0fa3c` | 15.0K | Tracked file |
| `tools/tests/test_decode_families.py` | `862d5ad96fa8b41081db62eb78258c937ddeb773b8b9a1bd7fbb772cdd0b5b83` | 14.4K | RE tool (see tools/README.md) |
| `tools/tests/test_emulator_families.py` | `6472e5aafabbd76dc3a83c2f99814cfdf8d181583c9e2ce3e5756591830a6958` | 22.6K | RE tool (see tools/README.md) |

## docs

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `docs/README.md` | `bb1a050f4df4cd49dab3a73f70b326364e148b5edb42ee1864d671bbc905ece5` | 14.8K | Documentation index (generated/verified against current tree) |
| `docs/functions/E2IntoRAM.md` | `588be02044fbee6f02f219126aab4adcde5e6883e0142398aa04205f255b6380` | 3.0K | Per-function documentation |
| `docs/functions/INT_ATU101_IMI10AG.md` | `791d3f2554a3cc5344f9d9847d9dfd66217d4e83f157a6fd855ed07be6234698` | 1.9K | Per-function documentation |
| `docs/functions/ImmoBadStateSet.md` | `c5272a38d7210da49888b767206c96babd27723ca3555832340069be016de857` | 1.6K | Per-function documentation |
| `docs/functions/ImmoStateReadyToDriveEngineOff.md` | `7f373908a541d06bc4d726453b7a190334c4f13db0fece49a0ad16f5d2fcdefe` | 1.9K | Per-function documentation |
| `docs/functions/Immo_Keygen_related_ADC.md` | `74a371717182dbcd9736732da5cd89835df0fdf0523fdd0bb32cb0f6b163f134` | 2.2K | Per-function documentation |
| `docs/functions/LongFunc.md` | `f0e1814c7559e13737cd01a5bed82487a43a5c37aecc506f4e95ecaa3b85cd36` | 1.2K | Per-function documentation |
| `docs/functions/MAFRelated.md` | `2b3f93ff9ff65df51d6cf32e35a340b7672f6c91073a2814dbafe1d6bcc90301` | 2.2K | Per-function documentation |
| `docs/functions/MAFStuffMaybeVE.md` | `b810727603d30feac60083596e7907a99779b54ec47af35209d90d1cef297905` | 2.7K | Per-function documentation |
| `docs/functions/OBDStub.md` | `8558b1099055612b8a763255bf669d1a67d1da1d2eab4cdedbe38890709c4723` | 223B | Per-function documentation |
| `docs/functions/README.md` | `3e2026b714561368a526ce7b43db768ede34307cde233fea053ba672682934bb` | 2.5K | Per-function documentation |
| `docs/functions/SetMemoryNotValid2.md` | `cb76e66ebd2467ce7a73381bf0be95297bf4ba51311342cd71102116481e6418` | 284B | Per-function documentation |
| `docs/functions/UDSPositiveResponse_16bit.md` | `b5beb82968daf345e63adeedb6d37a3e888171e98a46fb0a482d8432a48a9d00` | 1.1K | Per-function documentation |
| `docs/functions/UnknownFueling1.md` | `ace237eda8b5c9edc2e9889e464685cf9455015c518a67202c20424d8e5f09a3` | 2.1K | Per-function documentation |
| `docs/functions/VDIControl.md` | `a98dde29ca5b145eabd5f9d5d8a12690456a9c392a3280e378c5f0230c392c75` | 1.9K | Per-function documentation |
| `docs/functions/adcIAT2Volts.md` | `ffa42d97fcf8d31bdf13937f8bbff1d93701e382324ac67012398b7e0e4dce3d` | 1.1K | Per-function documentation |
| `docs/functions/adcVoltageOutOfRangeCheck.md` | `0089a70f67836ace1402744ec72caaf6cf96696a992c39275b195da180df65c0` | 1.5K | Per-function documentation |
| `docs/functions/addS32Saturate.md` | `3bb5d583ec5943432673345494517f6eb56b63a757443bd6c3273313942130ae` | 1.6K | Per-function documentation |
| `docs/functions/arbitrateFuelCut.md` | `ff434072868175527b7b8d86b75b27bc54be8794d85b8eacce6125e1be74c4e2` | 2.6K | Per-function documentation |
| `docs/functions/bitfield_extract_merge.md` | `aee7cd41dd46b03e4007d897555f9fbbfbc7879462899e44da64aede8e37b014` | 6.9K | Per-function documentation |
| `docs/functions/byteToUDS_SERVICE_DATA.md` | `2e5736e7435acb086b21c33cfeb086f9fcc183b6d11c74ddbbc8497a5962229a` | 166B | Per-function documentation |
| `docs/functions/calcDesiredAlternatorVoltage.md` | `ec07710465352821a2f7201a6cf184ef68193ea6e55018e69befc7c8a3cd5ef9` | 4.5K | Per-function documentation |
| `docs/functions/calcDiagFuelInjectorTrim.md` | `d4579b1c4f8167a9201e477e52af5c0cff8d82f6dacf689c5659cd02b31ed4bc` | 2.5K | Per-function documentation |
| `docs/functions/calcInjectorCrankingTime.md` | `ca58a7d19281aba48d4c0063544726ab0f8d76ba4d055e263ce0204f6b8f6003` | 2.3K | Per-function documentation |
| `docs/functions/calc_adaptive_fuel_trim.md` | `54fd6701c0622dc0eb032e3105d9791d2c7d44b27f472412552e7c8874d7b0af` | 5.7K | Per-function documentation |
| `docs/functions/calc_decel_fuel_cut_445AA.md` | `05d3eae839eef36eecf663bdb988e83d793a0f3e25e095b63477f2458dd2616e` | 4.3K | Per-function documentation |
| `docs/functions/calc_fuel_injection_all_rotors.md` | `6b1c087c2fd8e0ffcb140d52887d5538a80f0376e6be00f8433d1e86a75a2bd3` | 2.9K | Per-function documentation |
| `docs/functions/calc_ignition_all_rotors_13C2C.md` | `816680948ebbbe269c06c4bf477c50b1fc5c956674f0996f596afc6ceee930ba` | 9.1K | Per-function documentation |
| `docs/functions/calculate12VBatteryTemperature.md` | `e68f25bdf232b670fb224bf8fe6b025e1ac38b88bb0572975a6c5dc5c3acffc9` | 3.1K | Per-function documentation |
| `docs/functions/calculateCruiseControlSwitchVolt.md` | `01f55e8660bcc93f62fecacfbf00de1e3a33cd362fd2ef9014e0c0cab7619b2e` | 1.3K | Per-function documentation |
| `docs/functions/calculateEngineTemperatures.md` | `5a99dda07e6285e55f1d6dcf2767c091f402d6d31de290cb684554bd8a3f2826` | 2.4K | Per-function documentation |
| `docs/functions/calculatePerRotorIgnitionDwell.md` | `d2e0ec552534a68d62493cea42df600642db1d4b7992c5d34a8a740f34d5e393` | 1.8K | Per-function documentation |
| `docs/functions/calledLots.md` | `88c600ca47712e6bf66f2943e9e2d627b4e96265db64c327302b30c55c022ccc` | 1.7K | Per-function documentation |
| `docs/functions/canSetup.md` | `f98d793b7a67f50b4d9915794cf16b8ad0ccc6995c0bce1872b8d8e982e44f16` | 2.1K | Per-function documentation |
| `docs/functions/can_message_handler_24588.md` | `e84de9ffccaf5d0f0956ac8e9787539c7b5f7dd8d511d9efb73f28cfe55991be` | 444B | Per-function documentation |
| `docs/functions/can_message_setup_dispatcher_33974.md` | `f2b5320509d41b5dd146f1731d645fa9302efff6d884eabd2d9468b5e2d096c9` | 1.1K | Per-function documentation |
| `docs/functions/can_rx_handler_49100.md` | `4dcd9725ea119e4a86a7e16ca3189ab4c58377ea3d03cbe4e6ac2faeb65340b4` | 788B | Per-function documentation |
| `docs/functions/checkFloatValidity.md` | `737d1fe0cab46dcb6411dcd20e93816d1be2ef7937c27d5f47d96aa281fa806e` | 1.5K | Per-function documentation |
| `docs/functions/checkSubFunctionCurrentlyRunning.md` | `da8b88e03fc2b4027b19c7937650188d1da65632a646a6214f6226838983f11b` | 1018B | Per-function documentation |
| `docs/functions/checksum_complement_add.md` | `1e41dce792a03789dd089c9ef377953c78ea56d0ebd564bfce79a632bcbc795f` | 1.4K | Per-function documentation |
| `docs/functions/consistencyCheck.md` | `86d21a00f405dd82253fdec0756664cc8dab0731ed530cf8a79e849ce5cad669` | 2.2K | Per-function documentation |
| `docs/functions/crankSensorInit.md` | `7ed8a9ec49bc50488823a913a3aa50dd30b452e0b850a69b8258b362453dcb36` | 1.1K | Per-function documentation |
| `docs/functions/debounceCalculatedGear.md` | `d33b34d24124027749669b3323528cbfe18a1804a3240aa190554e713f1e5ab6` | 2.1K | Per-function documentation |
| `docs/functions/delay.md` | `4450eaa55e34401b0a82c1f75d75d3d2d5fce23839ef05587ffc0da013b2d777` | 636B | Per-function documentation |
| `docs/functions/delay_loop_n8.md` | `764bafea166cc032f09aefc22c2993f2160b4a949a1adc824066e73eb5f6c2ee` | 384B | Per-function documentation |
| `docs/functions/div32_signed.md` | `c4f8334965ec26712b2fa0c5ceaa6fa6d1a79a7024048621589413b7afa2a8ec` | 1.4K | Per-function documentation |
| `docs/functions/driveCycleDetect.md` | `51ba3930570dc1a126fe091ab6054047f4d043e7ac3e79a1ac32294c23aabe96` | 3.9K | Per-function documentation |
| `docs/functions/dtcCodeTypeInit.md` | `4316f081d27b2574ad72c6b473a526147c0a9f281ff12611539249c77a552aaa` | 369B | Per-function documentation |
| `docs/functions/dtcRelated.md` | `b643bc9ecf119ca1ed36264c6aa6fd8fb9cad3619a1cb019aceffc82ae59242c` | 3.4K | Per-function documentation |
| `docs/functions/dtc_data_read_60F58.md` | `ba7e0dc0338b04ebdc790af24a6cff2c0fe57bce8e623e1a3007952eb5fac72e` | 770B | Per-function documentation |
| `docs/functions/dtc_management.md` | `78251d9abc1a2cb2e26cdd5f6facbf15408d7ee9b2dc244299a186d9a5578982` | 6.4K | Per-function documentation |
| `docs/functions/eShaftLearn.md` | `4afb8fd66dab56ad688a4420788fed974e2cc176696f0477ff41a65eee03bc05` | 3.7K | Per-function documentation |
| `docs/functions/enableDisableCruiseControl.md` | `bbd6f4782e0e15c9009e893c8124a8a3148c8002cf7ef5a40969be4f663506cb` | 1.3K | Per-function documentation |
| `docs/functions/engineControlCalculateTiming.md` | `9080980c00624d2f0159a25ee46a41ab36d6328103a195b1fff3596ee2d65592` | 23.1K | Per-function documentation |
| `docs/functions/engineSpeedInit.md` | `8be9c3c37f2a0556f85055a329ae51cca8b004f2fc90e730c16b93537489fb55` | 1.5K | Per-function documentation |
| `docs/functions/evapRelated.md` | `1d87ba2dfc2d6d1f6894d14d2f57ac986556ea3c8e32e7ec1497fb6893a91c23` | 2.1K | Per-function documentation |
| `docs/functions/faultEnableStatus2.md` | `f574a7b032bb58bd13ecf582251ac25b3d0cc175f6165a3b9665048aa03b51cb` | 922B | Per-function documentation |
| `docs/functions/faultSomethingIdunno.md` | `2ae474e67603c23b567fe714402c7052bbc6d09a0a586088f063c134c2c16d60` | 1.5K | Per-function documentation |
| `docs/functions/floatDivideDiv0errCheck_SIG_DIVISOR.md` | `095a7629c7aa8a3652bbcb3b531bced7dd607ca9a893132aa557778b086e6bb8` | 2.2K | Per-function documentation |
| `docs/functions/fuelInjectionRelated.md` | `a13395f1921efd61dd65e2895906c7a49b1da09ef3d1e120b3855a44a9242a87` | 2.4K | Per-function documentation |
| `docs/functions/fuelingInit.md` | `c3642d37cdea881e3661deaef13ea190eaf818c4507a4ee83df7996147cff9dd` | 2.0K | Per-function documentation |
| `docs/functions/fuelingRelatedInitialVals.md` | `6dfbe75bfebd835c0c30c14220b3001d1ab76c6f1fcff205d50bb5c210a2a1ca` | 2.9K | Per-function documentation |
| `docs/functions/fuelinjectorSet0.md` | `f8528e4bb6eb5fce381b22377efc55c55ea5f4a5c9ea92d2c468d1dfd07f6a00` | 1.4K | Per-function documentation |
| `docs/functions/getACSwitchStatus.md` | `d3800e0b0f17c9eb0b4c283129cca2255e98ee3c56f9d7f1fdd6649d2fd817eb` | 784B | Per-function documentation |
| `docs/functions/getAPVPosVoltage.md` | `7bd50dbc260b684b7788afbef2651da0315807eb29a6751f42ae96a430d3cbee` | 1.4K | Per-function documentation |
| `docs/functions/getAutoTransCal.md` | `9645458a4291081b6b2500d150c8e4a1cdcde2bd95772e49531cf4379126ce8b` | 741B | Per-function documentation |
| `docs/functions/getBaroSensorVal.md` | `632c155f56d6490662f91ce9a21147641b4fedbad3fa740f4c8de76e9e442cbc` | 2.6K | Per-function documentation |
| `docs/functions/getConditionalsForRevLimit.md` | `6e884652dca8001bf37df1b609decb151ef0c02a126e271712b3af0af59db26d` | 2.7K | Per-function documentation |
| `docs/functions/getCoolantTempforOBD.md` | `2e691728498506754ad09ff86c76481b4706dfd40c46b52e5faae8f2fa997a04` | 1.4K | Per-function documentation |
| `docs/functions/getCrankAngle.md` | `14d08312c4cc92e00f07c4019925f0f95bc6125a37b58dfad7c8f54ed4d66dac` | 2.2K | Per-function documentation |
| `docs/functions/getCrankingInjectorPulseTime.md` | `1d99b2a6d8ed7a943961a6c821b7f93d7c727862ec69da9fa97bf30c9dce1411` | 1.6K | Per-function documentation |
| `docs/functions/getCruiseControlAllowedBool.md` | `7fac5f27b25372d21bd47d72bc021b2486e5981d3e6aa9be4a4b4f733bc97e58` | 1.9K | Per-function documentation |
| `docs/functions/getEngineLoadforOBD.md` | `ad6b057294874e8b2d43831226f6d9ab847650c5e06ccbc1eec5248d81f074a4` | 2.1K | Per-function documentation |
| `docs/functions/getEngineOffTimer.md` | `7af5c47cb4dac68bd53c82ed77d9b0083734f49a123f1c9164ab00dbe858237d` | 1.1K | Per-function documentation |
| `docs/functions/getEngineOnTimeForOilMetering.md` | `d0866f67f00f21cce47bacbef4d27054bc2102ce7ea12219805ae83d5a4ae00c` | 1.5K | Per-function documentation |
| `docs/functions/getFaultStatus.md` | `25030cee9eb2b051bf39c5d3e390cc9a07e09f3a9bba809eaa984fcba36d0076` | 1.5K | Per-function documentation |
| `docs/functions/getFromE2_E2ADDR_RAMADDR_LEN.md` | `9b8a258de4063a2157954934d9d1c76567ff3f8af61a9a36dd9598b2c4af489a` | 4.1K | Per-function documentation |
| `docs/functions/getFromGPIO.md` | `36ed85a9f6d6031179a72d01bf463747b88cc6e877a5e42d258b328be34c7f0a` | 1.7K | Per-function documentation |
| `docs/functions/getFuelCutRequestStatus.md` | `6ffd484eb96a99e8cb42849757b1df4a910992fcd788162080128669f8af1e54` | 559B | Per-function documentation |
| `docs/functions/getHCANRegisterAddress.md` | `2e420c3875edbe4f311de1a3b2373b60dd740499c9b5853ba260d58e8524f300` | 932B | Per-function documentation |
| `docs/functions/getIATOBD.md` | `626dc514df1981c0918b17fa11ef7e8e091570c2b89aba5a5e8540a879d14814` | 1.6K | Per-function documentation |
| `docs/functions/getIgnLeadingOBD.md` | `2e1cb028a74b1694b4875294c33a4d84b40735648244ddb991f92aaadb39bf0a` | 1.5K | Per-function documentation |
| `docs/functions/getIgnitionDwellTime.md` | `b523d57e178390824122fa4827175c7e4d50c3141cbba39d89d54774a4711578` | 2.2K | Per-function documentation |
| `docs/functions/getIgnitionRelatedCalsForSomething.md` | `a6dd931d66c4d2e49332fd6b077241a0301cfa16350c1b8a5a428217e1cfd81d` | 1.6K | Per-function documentation |
| `docs/functions/getKnockSensorADC.md` | `d36cd881b111471c740952ff0206cc20d475af17ae850d8fd4ab1fc32dfb6249` | 1.6K | Per-function documentation |
| `docs/functions/getKnownBooleanValue.md` | `2cc2b0b31f7ade7168228afa5671b27837187a3d3cd20c95ba0817926ad82d60` | 1.5K | Per-function documentation |
| `docs/functions/getLTFTforOBD.md` | `0cad7ecbde15b1a947c41efa98c4a19b8cac2037ecb03b576d65832caf0ff4f9` | 1.4K | Per-function documentation |
| `docs/functions/getMAFOBD.md` | `3dc4a1df1f9bfc638fd29e8cc248ed5c806e9f96ec509f292347dc1daaef4ba9` | 1.8K | Per-function documentation |
| `docs/functions/getMAFSensorValue.md` | `e87cc1b4a8e81ff9ecbfe51992bd4984d4fc506128b97d1c3b7ee4430acb3997` | 1.7K | Per-function documentation |
| `docs/functions/getOBDFuelModificationRequest.md` | `8cc9c22268fb1fcd3f94c49b82808007ba8bf546f4a71f079ea4bb32111b6c1b` | 2.1K | Per-function documentation |
| `docs/functions/getOLStatusforOBD.md` | `41d8f39bf78bd52064d4ecc8597cf9b3673ccb28464f80ad4c868d30dab585ca` | 2.3K | Per-function documentation |
| `docs/functions/getRearO2Voltage.md` | `092e6a2295949276c5f28c972303d12b99ecd937c253f782928349bd72da85c7` | 1.3K | Per-function documentation |
| `docs/functions/getRotorNumberForControl.md` | `d1143b435b8307af26b453ced08633163288b976cd02aa8fb7ca3e54e367d026` | 926B | Per-function documentation |
| `docs/functions/getSR.md` | `df7b35ffa0ddf5786f3a57fb53af72579c9ae1e9ed632103431d2d0f3b1c995b` | 799B | Per-function documentation |
| `docs/functions/getSTFTforOBD.md` | `b0c703dc98c4d15809d0b7f230223b0d8f00d7a06859df6848b8c9dbf1b821b7` | 1.6K | Per-function documentation |
| `docs/functions/getSecondaryAirPumpRequestForMode22.md` | `9d349ea4bdc683978bcefae0aefced0dcdefac9f9bb44fc3bb2bbdd4df29df9f` | 414B | Per-function documentation |
| `docs/functions/getSensorStuff.md` | `915799cd1101eddf7ae0a16e951eb9e8edc8be37de7ed95eea9760dfa39a2ddb` | 1.8K | Per-function documentation |
| `docs/functions/getSpeedLimitCal.md` | `aa61a5d836d8f8543ff7a65f08b77fd26971d1f24504c8eb7d3b4771696f0055` | 2.2K | Per-function documentation |
| `docs/functions/getThrottlePlatePosForOBD.md` | `746c1dc6252c113f2b9eaac09933e1cce6424e81424b39477ae78b7be8a44c2a` | 1.0K | Per-function documentation |
| `docs/functions/getfaultstatus.md` | `fc538d2fc0a7727a7564690a28bc173813f350e02538281303fdb566e51ddf9e` | 1.8K | Per-function documentation |
| `docs/functions/handleDiagInjectorPulse.md` | `cb69b88cb469691727ece01c7e9c019852fb99b3a1dd7ce1d1ba6a1484b526a3` | 4.5K | Per-function documentation |
| `docs/functions/ignitionCoilPulse.md` | `9fef8deaba5139950aa6f4da07a7396ba8a2612650d6e7f113ec25363c992f1f` | 1.2K | Per-function documentation |
| `docs/functions/ignitionDwellOutputInit.md` | `75b7355256d86610d98c2d044f7ec1d8669303b6a2dd611db59496a5096cb0ae` | 2.6K | Per-function documentation |
| `docs/functions/ignitionTimingHardwareTimerSomething.md` | `b7926a5424f66069b70fa4142e1db7ccfe5af379797a0f19f270e496c4c177f8` | 3.4K | Per-function documentation |
| `docs/functions/ignition_advance_limiter.md` | `f4e65ebfab738d83a7b8168cbb866d982a5a72cee8ec752c2e0a2fc09edeacc6` | 1.2K | Per-function documentation |
| `docs/functions/ignitonSomethingCalc.md` | `6c83e4695687ee07f748b4febe375936c26b62a9f14c22d730bcd1b13e31aec7` | 2.0K | Per-function documentation |
| `docs/functions/initSparkOutput.md` | `2104b420d78d42ac6e2fc05050d0f0b2cd41b19ba95854b0819599e3672bc802` | 1.7K | Per-function documentation |
| `docs/functions/injectionTiming.md` | `ab3a677761eee44d9e54bf15b6d48ca709524c321515b108e9dd0565b02a36ba` | 2.2K | Per-function documentation |
| `docs/functions/injectorPulseSet.md` | `ba18fb62e470e618e518618632fd6c00fd0933f960c1c7891fb9fe840f4f7e5f` | 2.8K | Per-function documentation |
| `docs/functions/injectorRelatedFunc.md` | `b592f4ca6f0e6a109c63d0babdd05df0736698dd74fd2d26eba61073eed6454f` | 2.7K | Per-function documentation |
| `docs/functions/intToUDS_SERVICE_DATA.md` | `638f12e0e6de432ca4c41d5b6584b1c9aab191b8de266913a038aa2601f9529b` | 223B | Per-function documentation |
| `docs/functions/knockFunctionInit.md` | `9a2f6662c6d2ebc68acb2a6d643ab903e7f8e2261b8a0d96682547ae66dd7095` | 2.0K | Per-function documentation |
| `docs/functions/knockRelatedInit.md` | `e483a5006afa4bf72e174cb0aa662b944af44dc584731b01956877ccc64884a1` | 3.9K | Per-function documentation |
| `docs/functions/knockSensorADCFault.md` | `2130b6454a85c0e19661eee1a92909d1176cef59b0ca5a5d36d0f693767c6665` | 2.1K | Per-function documentation |
| `docs/functions/limitKnockRetardMax_ConditonalRPM.md` | `75477c74ef9010bc883858382c2572d54011c4090f7523c2df9ae3ccf43ced8f` | 2.4K | Per-function documentation |
| `docs/functions/loadStatusRegister_ADDR.md` | `acf1c845d4bc422efb130fa1c6c6805a4e120a62dff612fde57379be3fcfb4c0` | 309B | Per-function documentation |
| `docs/functions/memcpy_bytewise_unroll4.md` | `726e62d24088757044e7498f9d9fd285ee62eff16490619ae0ec885db0ff2242` | 1.1K | Per-function documentation |
| `docs/functions/memory_match_accumulate_583E4.md` | `9977a3918be1f134260661936b159bee07d749a4a922391049b946c55684d57a` | 2.9K | Tracked file |
| `docs/functions/mod32_signed.md` | `04a41a31ffd31f7682296d05058348e644b28d66c382319d42135817ecde28f5` | 1.1K | Per-function documentation |
| `docs/functions/osTaskScheduler.md` | `b1c55f1978f4c82221d47fd3fc824f1b1c2a6a0bedcff6d63d0324a6bdc9f78b` | 2.6K | Per-function documentation |
| `docs/functions/outputSpark1.md` | `4d0e9e3103056206fb466c2981eb73e3ffd9770cf480062feb82d8e65ee39698` | 2.9K | Per-function documentation |
| `docs/functions/outputSpark2.md` | `4d3b7ee547825ad032726a5d0a9d75eedfbf5c28a31638ed42cae20ff7286fa9` | 2.2K | Per-function documentation |
| `docs/functions/pack_for_OBD_response.md` | `236e406a8e2dbdfcf1c789f521e3383bb22f22337e6096457fdf37a9d0f1ed88` | 2.3K | Per-function documentation |
| `docs/functions/pcmBoardTempADCtoVolts.md` | `bd26c23079c162dbbf967914b02bd8feb9b404f6719ce934baae107980cdc133` | 1.5K | Per-function documentation |
| `docs/functions/placeCANRX.md` | `4a5f33ebff56f05835c2d9933b0316f3efcef6c2961f808ced88664c734f0084` | 1.9K | Per-function documentation |
| `docs/functions/putFuelingStuffInArray.md` | `32c39cd989ff01b2b35a3ab094a9db45cd450da1750012c2be1f235b539b419a` | 2.7K | Per-function documentation |
| `docs/functions/putTaskInSchedule_FuelArrayStuff.md` | `923a1cbe9a53908817c54ff30583f40371d112bb8f0d64809030150a9c805109` | 1.7K | Per-function documentation |
| `docs/functions/reInitCrankSensor.md` | `fef7eafe1efcb246f73f4235677f1c7d5a6b4d185313410c9cc308b30a7ec8c8` | 1.8K | Per-function documentation |
| `docs/functions/readADCscoolantTempInHere.md` | `f7828a1b31594eea7283e1f6e575212dd145eed2eae726368e10a1261c52736a` | 1.8K | Per-function documentation |
| `docs/functions/readValue_16bit_ADDRESS_VAL.md` | `6ef7022b7bc487dce482e123db31d2eb10ad9c8cc25824d2cdcacdac2de4022d` | 1.4K | Per-function documentation |
| `docs/functions/readValue_32bit_ADDRESS_VAL.md` | `414e44ef3d3e5c9d3879170874bbe38dc66b44e62443e8aff4c4377d8ed89b83` | 2.1K | Per-function documentation |
| `docs/functions/readValue_8bit_ADDRESS_VAL.md` | `038cf88f8697dcc504b861ffd35053561c9e2b6f053c68f969dc1d3cc6d1e549` | 1.5K | Per-function documentation |
| `docs/functions/readValue_float_DEFAULTVAL_ADDRESS.md` | `91e99eabe170cd99cca5ca2c365161c01060e0a2f71902c16fcaed360dba9284` | 2.0K | Per-function documentation |
| `docs/functions/reset420CANTimer.md` | `90b4e4b8db24b76ed6e9234dc53de2dbffcf456ccdf9e0ba06e48c779e7004ce` | 376B | Per-function documentation |
| `docs/functions/returnCoolantTempGreaterThan71.md` | `c9ba67eb22a5aed4ccbc5e6b84ca3009a0079e89f4787d09137e6fed2fa35596` | 997B | Per-function documentation |
| `docs/functions/returnEngineLoad.md` | `2a7660c57344b6198ed8d738cf4540514db75ccaf5f80a6584c426c8ffec02d1` | 515B | Per-function documentation |
| `docs/functions/returnEngineRPM.md` | `a392c4331f50842f78c3821704b916ea2098e4f8ef98ef13250177f82555740e` | 529B | Per-function documentation |
| `docs/functions/returnEngineSpeed.md` | `6598eb844b5593c14ad8fc40e6ba2e70bded9c22b76db2b04fc2387935361484` | 483B | Per-function documentation |
| `docs/functions/revLimitFuelCutInit.md` | `e5e7ce1067e327b208b632c1c525269c449b3dfa83048f336fd4fb42d85ef95b` | 1.6K | Per-function documentation |
| `docs/functions/secondaryAirRelated.md` | `62b6f82f5c74ac2e41ec0e680106f31b9924814959445bc82b4467f20e9bdc75` | 1.8K | Per-function documentation |
| `docs/functions/securityNotUnlocked.md` | `6c251c6925f02e1f7de6d2ea1d39ac322c0cd1c8958c35d1e9392b803d88a1fa` | 2.1K | Per-function documentation |
| `docs/functions/security_access_handler.md` | `5f699606676d9bccbac4a576d90f9ec54fd013deade45bbe5e2c2163a1e11a66` | 16.6K | Per-function documentation |
| `docs/functions/sensorADCRead.md` | `87bd6fd0e4b70493206263d2c981d7466b702334d98b1e43ff330bea4e05dfb1` | 2.0K | Per-function documentation |
| `docs/functions/sentinel_equality_check_5687A.md` | `67610e69590288d13a721394295673dcb21475b5f6a41c73f2f7e39e9cf22844` | 263B | Tracked file |
| `docs/functions/setAlternatorWarningLight.md` | `06acb1825223fe3dda3edca99f70d4d62fe3bf4f75323bd8e0e49a1ba8cae411` | 1.8K | Per-function documentation |
| `docs/functions/setCANRXBool.md` | `f070e22713ae9cb670efcf18c4813102bde79758a52781d460727f2ab63659b9` | 275B | Per-function documentation |
| `docs/functions/setCANRegisters.md` | `a16f382cda727ba5b05cc1423bf82e5bb9b15e323d1a8da91fe961eef4924682` | 1.8K | Per-function documentation |
| `docs/functions/setEngineLoadInitalVal.md` | `29c9c1cf5fc23a6e58f823477353b78648d7e6a9103e424a87e5c611aa3cd6f5` | 657B | Per-function documentation |
| `docs/functions/setEngineRunningInjectorsOffFlag.md` | `1b7550a34383be29181870617947467fea55fd6e9f31efca18be614c341403a1` | 1.2K | Per-function documentation |
| `docs/functions/setFuelInjectorLatency.md` | `2d48a37cd31fd30290127fccf34d44885c905457676c4c89bf55bf057b6acd42` | 1.8K | Per-function documentation |
| `docs/functions/setImmoCANTXData.md` | `f3765a7e9730b7714026bd7e707417d295868b047c2331489f17c21daf741612` | 3.5K | Per-function documentation |
| `docs/functions/setImmoLight.md` | `d86f9efd0bdef678bbfe6658a667d19afbe2ad73c3a9934e46ec86f4bf132d0b` | 2.9K | Per-function documentation |
| `docs/functions/setMainInitDoneBool.md` | `b436136a1f02fed265bb98daebc14b78a440a96c48d095385034cdf6e1862251` | 406B | Per-function documentation |
| `docs/functions/setMemInsideFUNCto1.md` | `7a9424d993d4d790fc5d153d687aac2013e530904510b5b7a01d724a676b3538` | 256B | Per-function documentation |
| `docs/functions/setMessageRXBool.md` | `b9d4a8e64e0b1729a4bed26b0931836b6a944c2bdf8959ca036d231790c2e7ad` | 697B | Per-function documentation |
| `docs/functions/setRegister_REG_BIT_VAL.md` | `af7fab406fd8b9798b58867310d484f4336ec582a9872bc9293d646a5a7264cf` | 1021B | Per-function documentation |
| `docs/functions/setSR.md` | `2a648d29b7ffd8b0838f8806ce0db00888b6e165478f27eb325d89a980b1cf15` | 1.1K | Per-function documentation |
| `docs/functions/setSR_PARAM.md` | `cbdd9b92e75e3c2276c08c80fe1b52cbcac9c95cc924af692df3b09ecf600176` | 790B | Per-function documentation |
| `docs/functions/setStartupInjectorPwMult.md` | `9df976b8166652e47e9842b61a9f860b03880ff9e5422c9253d356caa8040889` | 1.6K | Per-function documentation |
| `docs/functions/setTimingArrayValuesForOutput.md` | `12b27f187b203ec5afa12e7d7c8638e32374882a28b289562f9e629641d883eb` | 2.1K | Per-function documentation |
| `docs/functions/setupforudsresponse.md` | `5e8948b858cc2ff78c1dafcd68c9484867bbd2b25364b67768ff6a26ce3d7a59` | 1.5K | Per-function documentation |
| `docs/functions/shift_left_logical_r0.md` | `95fc5eabd9b248dd6de712c21f6f45f899e8aae71e5f83a68c48ca45bdb26618` | 1.4K | Per-function documentation |
| `docs/functions/shift_right_8_r0.md` | `9df0404319221568f90bdf3bd83800c1d9350bc06e1805f68a9c842ff510713c` | 188B | Per-function documentation |
| `docs/functions/shift_right_arithmetic_r0.md` | `4120f7c6bc2d2e511d599f3de5f951327c6e00bf29342e8606b6e7e95fa26051` | 2.0K | Per-function documentation |
| `docs/functions/shift_right_logical_r0.md` | `38e1bdec216e6f1f80ef52282b3d215158ca7b412f4e23387f63c600daa8bfca` | 1.3K | Per-function documentation |
| `docs/functions/somethingFuelCutRelated.md` | `c09b7882868736e5964022a71f3f12b6772c6853f0c67afb4287c103380a3f87` | 2.6K | Per-function documentation |
| `docs/functions/sourceOf10kReset.md` | `27a1b0629e84cb07e7e0258c510a0890a1964bd9a9a371a6756348d7ac6d5154` | 1.9K | Per-function documentation |
| `docs/functions/ssvControl.md` | `da891cbd93938f49b7677c17a8bffa30b6d268338a8a89e5ccdba68a92e59d9d` | 2.5K | Per-function documentation |
| `docs/functions/store_knock_learn_buffer.md` | `c149ae632d8d267675cd9eedc041358c600f866406d54fb16f589f56fe4438b3` | 2.0K | Per-function documentation |
| `docs/functions/taskEndRoutine.md` | `fe64b3e04202eebd24f722848396ecb2b924bd567255db09ba353d103fbfb29c` | 2.7K | Per-function documentation |
| `docs/functions/task_flag_run_C.md` | `fc5a8f283d5b6ed03360c2a87ae9f380e5c09cef2ba7cc325fec656e431a4b2d` | 1005B | Per-function documentation |
| `docs/functions/throttleDownDeFloodCheck.md` | `ffb3f2e98a40e92dc2c168b5070fca155d455ffd8d41f35aaaad98aed6e77620` | 2.7K | Per-function documentation |
| `docs/functions/throttlePedalADCRead.md` | `8a1fd1a5bce65f6dffd0712a28f69ece74fc60583630f3ff19abaf84ee235c5b` | 783B | Per-function documentation |
| `docs/functions/throttlePlateSomethingFuelCut.md` | `6b973e7dfa95f5bcda1ba77aa20f6b8280f225ea978820e1e9e6813ed784a1ae` | 3.0K | Per-function documentation |
| `docs/functions/txCAN_EventBased.md` | `d40f8e23178ce6ab521fc71ce7eb83f0c9c8f18219684c9762b4193065b85ff5` | 1.7K | Per-function documentation |
| `docs/functions/udserrorresponse.md` | `b32d86bc65d37879ae3adfd194367f002dfe45df9f05aa5e617b68ff190b720c` | 1.4K | Per-function documentation |
| `docs/functions/udsresponserelated.md` | `93742dc4786fea48a6cd8b328babcbc132366c8a23a48a7904567a4110bbaac6` | 1.5K | Per-function documentation |
| `docs/functions/udsserviceresponse.md` | `fc7dc8ceacc70eca0a3c382db5086ea01e3b436a4fa7ff6e22188f179cdb652f` | 1.3K | Per-function documentation |
| `docs/functions/unknownMode22Func.md` | `97467c2818528fd09df7ce43c51d38ccd4a4c3170782ad192ba9acc2878fbcbe` | 3.7K | Per-function documentation |
| `docs/functions/updateE2RAMBasedOnInput.md` | `c77a5539104c27b37b7005d8a9feb2990e3d695dd20cd8eddcf50a6b5ffc16a1` | 3.8K | Per-function documentation |
| `docs/functions/updateMemoryAtAddress_16bit_ADDR_VAL.md` | `1dc2780e6cc10d1c5d945d4453309d9eae87524a28991ac99cbda33733f9fc3c` | 1.2K | Per-function documentation |
| `docs/functions/updateMemoryAtAddress_8bit_ADDR_VAL.md` | `e2659afacf4c583ce3ccc978442320202777d785d7444d11637c6ba338cd3a84` | 1.3K | Per-function documentation |
| `docs/functions/updateMemoryAtAddress_float_VAL_ADDR.md` | `382e3ca16026b03af1f6093db0ec67b90e554404ef66ef036659bf3516c07149` | 2.4K | Per-function documentation |
| `docs/functions/updateRAM.md` | `4a50a73950216e6085fb9e0cb88055dded731ac6e51d6f4bc0bc2c9c9d048739` | 693B | Per-function documentation |
| `docs/functions/updatefaultstatusthunk.md` | `1f5b1c3325a4b72a44beae5b4a1bf616f569c2f421f255a6d6e050e487e09e3d` | 799B | Per-function documentation |
| `docs/functions/validateAddressCopy_16bit_ADDRESS.md` | `88834367aee86b0925348de3fa6a3c48d7f10221abc5097f8c471f0f03c18406` | 1.8K | Per-function documentation |
| `docs/functions/validateAddressCopy_8bit_ADDRESS.md` | `5af3fb9c3180ef4a1633354abfddf87fc3a57afd5616ab66e97eca05bd47b7ce` | 2.0K | Per-function documentation |
| `docs/functions/vfadControl.md` | `7217626feefbbdbc68d81d94daa435859ba45cb8b700c3695dcaaccad4a57c85` | 1.9K | Per-function documentation |
| `docs/functions/vfad_control_35BBC.md` | `28bd8515cd0e202c05910c5df3c6f94349d7b56593d9c6c12b7dab8822851c63` | 2.6K | Per-function documentation |
| `docs/functions/whileLoop.md` | `0a87829e651434182566f7911a13121090c87d0cfadc41a07a46147cabe9ffcc` | 890B | Per-function documentation |
| `docs/functions/writeO2SensorForApplication.md` | `9831cfc11bce8ad648c5e6b421780a1e8042b9dbd0fd83c5f5986c8eb8866a5e` | 456B | Per-function documentation |
| `docs/functions/writeToE2RAMArea_INDEX_ADDR_LEN.md` | `3762b871a6ea6824ba725fd2f84189732fbd1a2fae65612ae0c27b1fc09f6c9d` | 2.4K | Per-function documentation |
| `docs/hardware/RX8_OBD_UDS_Protocol.txt` | `96ed38d1c77df4d88e239e092527f8dcd296c583333cb74f56ac101aa994f032` | 7.5K | Hardware documentation |
| `docs/hardware/RX8_PCM_Hardware_Reference.txt` | `390d43760c3a511fbe5c29fdc995d59718be19bf620116e12c41753032439556` | 5.4K | Hardware documentation |
| `docs/notes/AUX_HANDLERS_COMPARISON.md` | `de42456b6bcb20d02ce4f4dd3ba4b10b3bcd033936bf386ddae23f34dcda03bf` | 13.2K | Project knowledge / session notes |
| `docs/notes/BOOT_RECOVERY.md` | `6b3b9304f820bf8b48cbc1308ecd4cc72cb2c82abfa4973bbd5ad96991d88a86` | 4.5K | Project knowledge / session notes |
| `docs/notes/CAN_PROTOCOL.md` | `5a6501ca9e555b7a1d6ee1f086c5b2abc82047b2350dc75666a4f202706e3122` | 10.2K | Project knowledge / session notes |
| `docs/notes/CONNECTOR_PINOUT.md` | `0549f7b05a7142252771dc8c896a101aa3ecf14bc4589d1094db605febeb0973` | 2.3K | Project knowledge / session notes |
| `docs/notes/COOLING_FANS.md` | `e41ce9619860fdce65d82dac794c5312bdf5b1e4343af90bd1f74f73ffb0105f` | 2.0K | Project knowledge / session notes |
| `docs/notes/CROSS_VALIDATION_SEEDKEY.md` | `a733f5067dea6d68b14197cd34ed8c0e19df968cc7228a6d244a8a7d810afead` | 7.6K | Project knowledge / session notes |
| `docs/notes/DUMP_ALL.md` | `a3106438bb18e0ba4f00e863e2ee24c3e821c3019c10e04f3087469879e79660` | 6.2K | Project knowledge / session notes |
| `docs/notes/ECU.md` | `0e355083426a7991cdbca663f57957047e0db3af0ba2e45ef6fb0c84914a5b29` | 4.4K | Project knowledge / session notes |
| `docs/notes/ECU_CAPTURE_PLAN.md` | `72342e4beeeddded8fb81c058ab02010cf09c0ee8efdb43ecf73c38d9dbb9c21` | 19.0K | Project knowledge / session notes |
| `docs/notes/FINDINGS.md` | `d8648b13fe5aa1ee57865785ea55615a9abb66ac79c3fcf23a5f1570d6437624` | 49.6K | Project knowledge / session notes |
| `docs/notes/FORMAL_CERT_60E1D400.md` | `1aa6ca1fd35481695cb63a3ced1de81ec128b9a7a7d173d40560401e7e58aa79` | 10.7K | Project knowledge / session notes |
| `docs/notes/HARDWARE.md` | `0e35f965f143839b8e022a728ecd5cf244358a22b0075f8cb2f3d80dc99febd7` | 7.6K | Project knowledge / session notes |
| `docs/notes/KNOWLEDGE.md` | `f2b8a781d963895313d733f2514fd5576764702bb05050b54970e8e803a05d40` | 3.7K | Project knowledge / session notes |
| `docs/notes/LAUNCH_CONTROL_CHECKSUM_GUARD.md` | `0bb6b8ff997ceba2483a322ee25ce08344205bee7086146332377f8a1b6de5c8` | 7.4K | Project knowledge / session notes |
| `docs/notes/REQUEST_SEED_EVIDENCE.md` | `15d123bd26dc8ab0955053893b351bec29d00464baebf33f7fbd7221a3d405f0` | 10.2K | Project knowledge / session notes |
| `docs/notes/RESUME.md` | `32ace9f4bfd8a90dd82cee761ee637ba3662ab9f374d04385f4ce01db40a94c1` | 739B | Project knowledge / session notes |
| `docs/notes/RUNTIME_CERT_PLAN.md` | `afbf97b51e0775f027b61c009b56e8e4a37a69e3edeadc8ebaeb8350798e3611` | 6.9K | Project knowledge / session notes |
| `docs/notes/SENDKEY_RECONCILIATION.md` | `02f43a1b8352ec8cac273bcf5252a62fde5ab75743e1c50f6b5fa61a58c6c623` | 7.9K | Project knowledge / session notes |
| `docs/notes/UDS_SECURITY_MAPPING.md` | `ba8b268160f6ed346876945437498da71f69a49c5ff19c9d3930df630bb5eefd` | 10.9K | Project knowledge / session notes |
| `docs/subsystems/AUXILIARY_CONTROL_SUBSYSTEM.md` | `32dd9a69f4e561d0898535bbc16b1b239ff1553bc34e04b87118bb9e17aa5c2c` | 26.8K | Subsystem / overview documentation |
| `docs/subsystems/BOOT_SEQUENCE.md` | `a066748e147938ca4662eacb4749be88027c99e6f49196d3e26725c7d4fbb96c` | 12.0K | Subsystem / overview documentation |
| `docs/subsystems/CALIBRATION_TABLES_CROSS_REFERENCE.md` | `0a8ac7bff874c3b6b167c4e31fcb7507a4aa4c285c7e4c78c545a0a5ba79719d` | 27.0K | Subsystem / overview documentation |
| `docs/subsystems/CAN_UDS_SUBSYSTEM.md` | `4fe31fc8027d2a780461778c65f15585dc8541d0919d3889190c6295fc0537a9` | 23.1K | Subsystem / overview documentation |
| `docs/subsystems/FAULT_DIAGNOSTICS_SUBSYSTEM.md` | `2e656f9e6bc76173e2d6c2d0dd412223d58dec7e9abd737f2cf7726ab2fecf3c` | 16.0K | Subsystem / overview documentation |
| `docs/subsystems/FUEL_INJECTION_SUBSYSTEM.md` | `402a99653d13298d9c3f83ff0d9f00f941470a41973648e0dbd530d9c3d43c70` | 27.9K | Subsystem / overview documentation |
| `docs/subsystems/IDA_NAMES.md` | `5a642eff09cb561624a67f9f8ab2fb6a638a033b2821bb0c8319e6fe1de06124` | 3.2K | Subsystem / overview documentation |
| `docs/subsystems/IGNITION_SUBSYSTEM.md` | `0aeacc2fa536641d37e2fc2e71de7b138db5a26364f7e87adf92c340990e5f13` | 25.3K | Subsystem / overview documentation |
| `docs/subsystems/MAPS.md` | `6ef67882d17913fd570e798b335436b82adb912c903d4a796e1a3884ec0e2791` | 37.5K | Subsystem / overview documentation |
| `docs/subsystems/O2_LAMBDA_SUBSYSTEM.md` | `47e09dc0cafd0d0686471316abb51bb2d131b63c00864ce6fd64f5354bae2571` | 11.9K | Subsystem / overview documentation |
| `docs/subsystems/OBD_SUBSYSTEM.md` | `8b56c84d1be406944e34e0262d476375afacd4d2fa05b8496c39a06224250936` | 10.9K | Subsystem / overview documentation |
| `docs/subsystems/OVERVIEW.md` | `69115f7a6d04f03910d73090be268d6fc0667ccdd76c04812d19f53b4f464f9f` | 2.4K | Subsystem / overview documentation |
| `docs/subsystems/PID_CONTROLLERS.md` | `b4e0b07881c08f1ab36948e4ebf800d9b539bb0f9d4f8947ea1979f321f72619` | 11.8K | Subsystem / overview documentation |
| `docs/subsystems/RTOS_SUBSYSTEM.md` | `6ea4ad8af8cb9a22e2d83c0243512399c83df60762a2de2f471cea65d883902f` | 15.0K | Subsystem / overview documentation |
| `docs/subsystems/SENSOR_PIPELINE.md` | `89d51920d0f17db11ca308bd1c7343c93404018f3de8aa5aca78db13aee198fc` | 21.3K | Subsystem / overview documentation |

## hardware

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `hardware/HARDWARE_NOTES.md` | `c9f6dddd9710530855160d0922568701215ca1f4933388a913482c1c4d514182` | 2.0K | Hardware notes / photos / web references |

## web

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `web/explorer/.gitignore` | `9e38f3635d6b89b9d202765b2624d45192da67b8c0c593bfb75c405b070e6a9b` | 66B | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/Makefile` | `db9f6b8a342ee379c193034adaa04bd581a7a2f900c17de78e3850c0a3525cd4` | 2.3K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/README.md` | `a2cd2eb0b206aae958659d9db46d54547258d468fee0b7fface65976c274f81c` | 12.6K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/build_site.py` | `74e35428220d6d42736cc7c60e5e25fdbecd62b55587574aa7e9c574529c064c` | 43.9K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/data/MAPPING_NOTES.md` | `b560623208d860ecd62546c53f574b837261c6e6ea87b3d83618c24bc1060a00` | 8.5K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/data/roms_meta.json` | `dad8fd3738c7f3aeaab92fb6879c64a0a84c774784c09805fb0057f05f2631d3` | 6.5K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/data/table_addr_map.csv` | `c5af53244037338661fa54d8223cc92c88efcd8eb7e18b44113ef2338c0204f2` | 169.7K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/data/table_addr_map_long.csv` | `2ef23c561f7c2875a85775eb26e85e10bee2a0f479ba04696cde3297ca988349` | 533.7K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/src/app.js` | `1f747300168d7928df8c2277c8df7eaeaaadea72b175bed1d26de5f2e8f93220` | 68.7K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/src/index.template.html` | `9b467dca874ee33375bb9bc31600327a473116b31f51301a2f8991a487c3db70` | 10.2K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/src/style.css` | `d553d60f533761bb31da4052294c24ea619c5af423d85d407b271ec9dc6f02aa` | 18.9K | Web explorer (static firmware browser; see web/explorer/README.md) |

## analysis

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `analysis/coverage/REPORT.md` | `4c45fa7a877c54dce4e3c616ad91ffa03c901374cdb75281522e6be2371476e4` | 7.8K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/coverage_gap.py` | `d95e69c88a666a7b986de747b0eb3a64596aa3e078b8d089c07bcf35cb714cb3` | 18.1K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/declared_60E0E500.csv` | `6e8138c8503142d5117a533e385348285864821b393db900b9e7bbad0f8799ec` | 14.8K | Tracked file |
| `analysis/coverage/declared_60E0E700_N3YLEE.csv` | `b4b108744b563ea19cf600cd2b2cee47d3adf594efc9574d007c37d8fc891313` | 15.0K | Tracked file |
| `analysis/coverage/declared_60E0FB00.csv` | `8a15fb794a633967d93fccbc36c524d43cf996d0d219c187fa60adfef66bd1cf` | 14.2K | Tracked file |
| `analysis/coverage/declared_60E0FC00.csv` | `606dcc0d06217e8eb749b5e226040e79003a468e56c3ce2c7ada9d650bc705a3` | 14.3K | Tracked file |
| `analysis/coverage/declared_60E15120_N3J1E.csv` | `4604b9f392502488817aaa6336b7c64f7874782eebe25acf877c7203c8ecb858` | 14.6K | Tracked file |
| `analysis/coverage/declared_60E1B900.csv` | `e4c64ce445ece539bc0770c9cf815c37591593c06ff7d467654cecf2978c9d1d` | 15.6K | Tracked file |
| `analysis/coverage/declared_60E1C500_N3J6EB.csv` | `6f1b11aacd648e977371fab1cdf8e1b8764accafe1346fb2f4848bdf9cc31897` | 17.1K | Tracked file |
| `analysis/coverage/declared_60E1D400.csv` | `44724b0f5e56c99e3d574fc3017a60767c6de2cc219736feebe220f50eb51bb6` | 112.2K | Tracked file |
| `analysis/coverage/declared_60E32000_N3M5E.csv` | `54ab7a21807e33f09276a51cd589f519ebc897cd476717e95d64fda7429100a0` | 5.7K | Tracked file |
| `analysis/coverage/uncovered_60E0E500.csv` | `df521bbe9d636d2182d4c3bd70af39a38dc20ea371a544dc910cc3cd39f45a57` | 458.1K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E0E500.txt` | `3e9d5691b1bd24d90f33b3fc68c00749094ae41b7dcd991d30aa5d828d145245` | 391.6K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E0E700_N3YLEE.csv` | `407e16cebd787646ff59f331082703cb61c2531175d34b238e4707eb1017f980` | 459.2K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E0E700_N3YLEE.txt` | `713ee7aab766eaff476dcfc1f3b616a1247be110cce385099a8474d824ad01af` | 392.3K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E0FB00.csv` | `abfc98cd7871cc15b4d8705bd3880e457a8dceb1562ddfc621584f762d3d4f9f` | 450.8K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E0FB00.txt` | `77372c90fa56317664a6d644bb2a7aa82f2fd99bd59df1eca22639e4f171cb14` | 385.2K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E0FC00.csv` | `3783d1653d9b32464eb7753db0aabf9c49e80845ff3e71636771827677f4db9e` | 595.9K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E0FC00.txt` | `b96ec200523a63399482e078eda8741d566d4d440c121bab7ec7cbef325fda63` | 529.9K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E15120_N3J1E.csv` | `c1f6206600e4031911a277a59e49498b70a18f9dfa5f84b73868d8430375a970` | 447.0K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E15120_N3J1E.txt` | `953bb0233d92bcb44b53601900037635f4b47b45adf0b760160c4701cd09be11` | 382.1K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E1B900.csv` | `a9dfbd33a751d936548919c822be6e0923144e9405cb4ee34054d86bd92d43ec` | 449.5K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E1B900.txt` | `b9d58f37d35eb9876d09f13c307f4034d3ef6aa85c5d87ceca5fd0afac61ad98` | 383.7K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E1C500_N3J6EB.csv` | `2a251b133f8b914458ef0c2e7f70e3cff372eb5654ceb52b11a024ee8761b9ef` | 457.5K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E1C500_N3J6EB.txt` | `a816b78e2ec0489d646c1f98268afedc352e3c819b9396e5a4f73f395c6f52a5` | 390.7K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E1D400.csv` | `89128626ca88bf771d655f08401b054c9c50a71b68778614042bf065ef002c5c` | 529.7K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E1D400.txt` | `e166d3f98b99f1bc9cc17de319bc27fee30c2f893cf1832df7eb200c24c4400b` | 464.5K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E32000_N3M5E.csv` | `8484e53b04b4770fe9620f74adcbabd3ac736e0908dd07d2979f4d2720ef143b` | 436.2K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/uncovered_60E32000_N3M5E.txt` | `2150432813810a004616a94090e01e0eb5b304c51693533076669cec0ff63471` | 372.5K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/cruise/REPORT.md` | `0ec7b30c02fc3e583a7ec6e03306e92140a9c9d193db91f8849ca4b325aa0328` | 12.5K | Analysis report (function identification) |
| `analysis/data_regions_60E1D400.csv` | `1fdc2a3960369000ffe91991a420688cd8c7927fa1a77cc3b57678fbb9442a55` | 107.6K | Code-window data-region classification |
| `analysis/data_regions_60E1D400.md` | `9971865b26123e014c1f0f25e59321d68357a792becdc531024dfe1b16aa2a33` | 5.5K | Code-window data-region classification |
| `analysis/romdiff/README.md` | `cb65695a9aed7b86ba8b680478801b81a17c4a409ecf9a62a5049d979b237f61` | 1.7K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/REPORT.md` | `0d2b11badc533646c30e400388ee5460a69829ed77c12da03fbe70853b4e77dc` | 10.4K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/cal_table_diffs_baseline.csv` | `1950d28497114ce6e3888dcf66f5a47a51f90374a5f1827af08c8385c50328bf` | 610.5K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/clusters.txt` | `3073878cf18f2bbb32163b579c5bd1d5ed92e1b7bb00181219c3335552c90d0d` | 2.5K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/diff_matrix.csv` | `e47dddb705664b858c1e8cb37451d3969679472e0f0ad69fb083697349185285` | 2.0K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/diff_matrix_blocks.csv` | `0755641c44a929669be19a9398058b8afcde1623c5bb98ec613988b060d576a1` | 2.1K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/diff_ranges.csv` | `a377efdfb42286f5ffb9bdddbd98deb8c117ba4eef1e65c9e7434f05338a95c9` | 628.6K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/run_romdiff.py` | `ed7fc6cd5f55dc0e66e7e5748539f5d306098a2a520aa2e3fdb24ebe8555bf35` | 25.8K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |

## .github

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `.github/requirements.txt` | `2cb78cc09fd13a74714019208e9fecc99de405883c299c6bc0de7aae39709288` | 534B | CI requirements (GitHub Actions) |
| `.github/workflows/README.md` | `4ba420eb633f9177d6a5f5500289c905cfa6b312c4c0e861ad2db6ee93878f6d` | 5.4K | CI documentation (GitHub Actions) |
| `.github/workflows/ci.yml` | `7cbe603f5f43dda693c62922585c874ec4813303ce7d482dab9bdfc75b5714de` | 9.3K | CI workflow (GitHub Actions) |
| `.github/workflows/pages.yml` | `8cea71e76a9b2e7617727d4f4ef54447f8d47f48ddc5d193b986c66ce4b753ef` | 2.9K | CI workflow (GitHub Actions) |

## reconstructed/experiments/match

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `reconstructed/experiments/match/REPORT.md` | `63eb3d48dab6ebb8cfa891f55fb3c4b4895c5d7ac9b94540a55ce0adf71f4932` | 62.2K | Compiler-match experiment report (GCC sh-elf sweeps) |
| `reconstructed/experiments/match/c_src/add16bitSaturate.c` | `419f280b2f5edf8c7d8821e4aff1c934ef91fdb837e6f40f9649f97fd02dd005` | 852B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/add16bitSaturate_reg.c` | `db46950abb444f4a9827b38972403e9410a0a8ebbb0c81307ababd5bb305f8d2` | 1.1K | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/addS32Saturate.c` | `1b62703a7d1ece53091785ac7b186e17acab07127692df893c192f62ab4528cd` | 1.1K | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/addS32Saturate_addv.c` | `0c8cd2cdc797c44ab93e725b77ea2cb17cfdeab127ecee9db94d400887dafbba` | 1.0K | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/addSaturate8Bit.c` | `0ee8fd252da1d4928059d7e155638ff972407ee61448aa8500b0fbd9f074fa49` | 963B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/addSaturate8Bit_reg.c` | `5c1aa5655acefb9b6465483938abe7f960d60cdaab1b4e7ce45bb90911d60026` | 968B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/alignment_boundary_validator_D90C.c` | `a157bc2c0b31dfa992b0d93cd55f5e4fed7dfed944ed22e49f33e27d7f198f54` | 870B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/alignment_boundary_validator_D90C_r6.c` | `ca69bec76cd7fee8ac664af76556d6a56bbc7f385d605b453d5553f2169e042c` | 978B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/atu_get_rx_byte_count_1FA2.c` | `09407a7496c365be013f3487b2f02ed82784dd50bd3e09f639561ce18517d755` | 278B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/atu_get_rx_byte_count_1FA2_spec.c` | `2420330838dc32f7e6da3015b1dbbcfc278857c324df053a929f1da266631f12` | 939B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/calc_manifold_pressure_error_diff_10A88.c` | `4ce8688c22c55b7495a1fa6b72a8c2b180f7d9fb6f2a95914bffe18537e949a0` | 684B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/can_get_mailbox_offset_high_D164.c` | `75e2af9af67cf9d68d232a681854ea30515e5fda2792bf6b5de7664a6915f1c9` | 284B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/can_get_mailbox_offset_high_D164_spec.c` | `669a55db607b5308c5f99cf27c79998cb93c13336ac453b0746bff039943f6d8` | 383B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/charging_status_59C24.c` | `53d5af8b12af2f073b055c854133b00b7d4c073da369593eecb6743a9f7bd3f5` | 390B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/charging_status_59C24_branch.c` | `a9e19895e9daf1cce65e3a50c0d889cf6174c3bb748ed91ec68e2646b749bb2d` | 1.0K | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/complement_shift_u16_2430.c` | `9bf2ff9f0244a92bd98ce219088f0283eb68694c47ac2712ebf59f7810279398` | 452B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/complement_shift_u16_2430_match.c` | `2490e0ddf5dc505507d827017f542ca4be5e2039d272b83339430707c95c6e9f` | 1.2K | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/encode_2420.c` | `50a09b1a0c1767293f72461dc1994d3a70c48c71e6f539cdc9f6c3ac3b9b75f1` | 307B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/encode_2420_match.c` | `885a4eb166ff5c3cfa7dcf7c5891713e758a5725b4476e378bbb4131812734a4` | 1.4K | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/getHCANRegisterAddress_D198.c` | `b7aecd06078360435924c236d0f94791ee206ead2a46bbcdfa0aaada5249484d` | 501B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/getHCANRegisterAddress_D198_spec.c` | `f00e3b6b4312d3fdd867d8a8a5eb91e2ed72907015e3669b36251ebd2c139550` | 499B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/obd_service_handler_67154.c` | `22b6b7936d06c9ed6ef16b6f8e8fbca092f5cc54af3d41bc9bf62ae0e0c09f6f` | 312B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/obd_service_handler_67154_branch.c` | `7d8c5931cb9a471c5943dcc00f18ef259024b10230c5be2181a0f467b5f718de` | 979B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/obd_service_handler_67154_m1.c` | `ae92293efc41f0d797e6bf5c3bcec39e4e5e3c031a3d9856d3508ab32fe5b26b` | 1.0K | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/pulse_window_compute_FCD2.c` | `3b9df03b1bba225716923573a43312968cc564aa5c6bebac88553eb000de4ccb` | 437B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/pulse_window_compute_FCD2_r4.c` | `b7214b24e4e52f8a0498d8eff5822610d9e6c1e5e4e39035477a49db9039ef8c` | 1.4K | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/seed_mixer.c` | `0a9ed05554c2900c0528516a309f2787aa52ebe52f0de2412a99b9eff794cd4b` | 1.0K | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/shift_right_8_r0_467A.c` | `3ba6d6885259ab3e7f7c6ba31dd0246c6cf306dfc9aaa84625cb359b2b8d8b65` | 367B | Compiler-match experiment C source |
| `reconstructed/experiments/match/c_src/shift_right_8_r0_467A_loop.c` | `2d57f816f02d0101dd5d235b513ad604a67313a2478db20b2e5eae4a203a2bde` | 937B | Compiler-match experiment C source |
| `reconstructed/experiments/match/expected_gcc_sh2e/add16bitSaturate.O2.s` | `bb4bba062e59ca46f7fa664ef8e0e8e8c9ebe520aff34c1dcd0b79a5cdef2ff6` | 595B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/add16bitSaturate.m2e.-O1.nodel.s` | `924a3aec960969c17061043dce64b90d4b637990498c42be71b50842c2b1e1e3` | 410B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/add16bitSaturate_reg.m2e.-O1.omitfp.s` | `3e36b5c8a6ce49dbe0ce8044ff5f35a03afe59eed8550480509c2084bd881cb9` | 359B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/addS32Saturate.addv.s` | `a89df2d7f686f012a07b8c49f9ed5574787d40d29e8bfd6027222c9e165d5a54` | 766B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/addS32Saturate.m2e.-O1.no-omitfp.s` | `74e0671c8c5382093b98f0add78519e30cb70b0d242fe8acf976bbef1e30848e` | 728B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/addS32Saturate.plain.s` | `d48d92f1ea5f5c0b9f23bf5adbed23820b13ed8032e9c7ac4018ffce8357bf84` | 921B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/addSaturate8Bit.O2.s` | `847d2659c3f0df9f7fa2f638530785892207ec7cf7427bd5109dbdb0274fa30d` | 504B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/addSaturate8Bit.m2e.-O1.default.s` | `995e326c9cd9f35b04d0d13244207b81463808693e944286c9c465532ba3507d` | 392B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/atu_get_rx_byte_count_1FA2_spec.m2.m1.O1.omitfp.noifconv.s` | `01e14efd0aeb98821ee219480255d2f4a21327f5e97d341f6965016452bc4afa` | 404B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/complement_shift_u16_2430_match.m2e.-O1.omitfp.s` | `681e6fad4b5d0fa5ef3394c461413aed29efd5bd81e2077b39cc2bbc65dcad51` | 331B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/encode_2420_match.m2e.-O1.omitfp.s` | `681affe4bded08a1a98d44d89236538191edf0411f2a9c9e802f7f2c55ab47c9` | 271B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/obd_service_handler_67154_m1.m1.-O1.omitfp.noifconv.s` | `d50664d1c79d18021f5af26328d98e77ec27f3edc55e8c32bea1a28e2821e84c` | 374B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/pulse_window_compute_FCD2_r4.m2e.-O1.omitfp.s` | `b4cdc8d47e87db4b3b64d0d33cb38cc1ce57c9c752e279c588e1c6024594ffd2` | 372B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/seed_mixer.m4-nofpu.-O2.default.s` | `e7e2e1690266c99a0c4920e52443c15208d57b44e2df6f4fdf76a13934eee793` | 882B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/seed_mixer.reconstruction.s` | `5443df9e746517c7844efa301c43991258f98df65cb5c74a7b42d9813aca153e` | 2.2K | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/expected_gcc_sh2e/shift_right_8_r0_467A_loop.m2e.-O2.omitfp.unrollall.s` | `0f0bf4b5f2d1c060c99919cc858ed14240a30860b52e16b21e64d2291b845073` | 316B | Expected GCC sh-elf assembly (match reference) |
| `reconstructed/experiments/match/match_recipe.txt` | `1b1884437b06457d2c73ce8b80267c521032ca8ab3d85c801feb98c512dd9e4c` | 27.1K | Compiler-match sweep recipe (GCC sh-elf) |
| `reconstructed/experiments/match/rom_hex/add16bitSaturate_2460.txt` | `87074a4f5b73acc97458c8c84e85fb8d7991455823b70c803ab14f43582feee1` | 232B | ROM hex bytes of matched function |
| `reconstructed/experiments/match/rom_hex/addS32Saturate_2304.txt` | `4a176f09461a54a2e86045f8d7eea51925cfbf2cfa9a85c7be45666a30504847` | 226B | ROM hex bytes of matched function |
| `reconstructed/experiments/match/rom_hex/addSaturate8Bit_2478.txt` | `9d3cc3c60ed1dfa8a298f000b21c4db662d81b8b1537aedfe1ec6d2c41d1e952` | 231B | ROM hex bytes of matched function |
| `reconstructed/experiments/match/rom_hex/calculateImmoSeed_3675C.txt` | `63f9d8cb50cb4e8073ce8d09b226500441fa9a6e9721b803c1c846e561d0693b` | 677B | ROM hex bytes of matched function |
| `reconstructed/experiments/match/rom_hex/seed_mixer_366B8.txt` | `c1819043a5a57906abd890fe83be5d2d39c4bf72b62353618cf810b174467d5c` | 446B | ROM hex bytes of matched function |
| `reconstructed/experiments/match/scripts/compare.py` | `6494e435d70d4e3fc982acdad3b136e377b097f3b0814d601a9a39480983a94b` | 3.9K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/extract_rom.py` | `5e18880809f5d567986aded113827d5468a70e49590ce5917feea457a0fbc1cc` | 1.7K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/find_puremath.py` | `8c855a2a27f6016ff5ec44bd31101b7aacac8508c12343f260604b9cf38ab116` | 4.2K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/fingerprint.py` | `afee01dbc572ae061d8313bcf17fe48ef43261e049887efebfe1d12bd33a20ee` | 5.2K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/iter_match.py` | `d1e14d44561237cc5c5ff4a1d7f4624e210ae26b4fa5381016a7cd44950fd6f5` | 2.2K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/sweep.py` | `6ae044c79431a726fe08c76dbeea44d1efa6afd315610c96977d6d645ffa49a0` | 6.6K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/sweep_flagmatrix_gcc346.py` | `8cae18239889392ef70d3f1ca7f654219a6aa37225b6e9720e0d2fd7e39e0d1a` | 6.5K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/sweep_flags_epoch346.py` | `517b4a7e4bde5365c07cc9f2f45c72f146988cad92f2505d70125c8fbeff0469` | 7.6K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/sweep_gcc14.py` | `c10231562b6cb2f1325e8625484a8c5dabf57f8c7eaadfb5a5b9421011e86099` | 9.5K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/sweep_gcc323.py` | `fcf63921c9c5b6389df7e8c51cdf10030b6cf327583df5a5ea88e9850b6aacd9` | 10.6K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/sweep_gcc336.py` | `f17e511f50d576931221543eb9e50193e49782a62039fa7c810b0f175bdb9b22` | 9.9K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/sweep_gcc346.py` | `569df5c89978603a6c91c463590f1e2d7acd7c192f645a37c201cf525c05e47d` | 10.3K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/sweep_puremath_gcc346.py` | `519f4904929b9e258f9854abfee31c46a3f2b860bb476b1c5aa9c1ff0b88b39e` | 6.2K | Compiler-match sweep/analysis script |
| `reconstructed/experiments/match/scripts/sweep_relax_gcc346.py` | `73f3a4eceb6b69cfdea512d8552ea39fda5d0011ebc6c44a7529daef8dff45b4` | 8.0K | Compiler-match sweep/analysis script |

## reconstructed/samples

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `reconstructed/samples/.gitignore` | `6855ccd04b303231648a4ff18aac580aa6cee143426ab8a929c71fa341ff948e` | 78B | Git ignore rules (sample build artifacts) |
| `reconstructed/samples/Makefile` | `c5bf8f52da0e4781adb6016e032628c2e881f440a7fa10c0998cbeda528416bb` | 1.8K | Build: compile reconstructed samples + host oracle (host gcc) |
| `reconstructed/samples/README.md` | `d460846f242988156a3998356d09ed1f2b6f3096ed31db20fd1df75b01f57459` | 20.5K | Reconstructed-source sample catalog (abstract idiomatic C, verified lifts) |
| `reconstructed/samples/ci_verify_gcc346_proposal.md` | `c593f714f083fa0f9e8999d8d642e6df0f4a9f41533e3d612d62f71c2ffd3e9c` | 15.0K | Tracked file |
| `reconstructed/samples/include/rx8_hw.h` | `4daedeaaa14ec57cb54d3252dde1d1bb2a58f7e9b3d054445f3251f62231d8d1` | 7.6K | Sample shared header (SH7055 hardware access) |
| `reconstructed/samples/src/rx8_2d_lookup_fp_16bit.c` | `da8456de17ec35390f2b28367d5ea4b5444d94a6544ac4109d9edad354ff4ec6` | 5.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_2d_lookup_fp_8bit.c` | `adea7dc501611a5c4eab5ca4bee8016915c43c9c29964571697ceeb0785b7049` | 4.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_3d_lookup_fp_16bit.c` | `7084acb1f3dad1f01d31a7b8efef4c41eb202f5eb2152d529f9a707a0c790f4e` | 5.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_3d_lookup_fp_8bit.c` | `ec4a14079aff03ee36c7de3ee749f4a3808dc622694fa817e701b051d66326b1` | 5.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_add16bit_saturate.c` | `65617971bb53d86cf6d14737c27d48039d2bf5a3166179ff30919e4c18f68124` | 3.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_add_saturate_8bit.c` | `3285892386d3144e2d670fe13a15f18ba1140415633ef79ff949a13dc03c1769` | 3.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_alternating_sensor_sm.c` | `30d59c1b52c429f37570b1574552ca80d56aea609f8580030b18d31927f2ce68` | 7.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_aux_fan_control_task.c` | `63e0037eb1dee0ba133085f6bccadaf54f25fd1c79c8ff5da1d91bc5510aa8bd` | 9.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_baro_sensor_value.c` | `145fe342c7d3bdaee2274130a4f16931d9ab77eba59297c3d0a2bd79d3d56773` | 7.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_battery_voltage_monitor.c` | `a189519c5924a3b334c5dbe2e9a92bf901142d0a94f97084604480624a47d397` | 9.6K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_bitfield_extract_merge.c` | `4bbdc462736f95e157012b3377f81db32e4ee86d85f4486119df203828012060` | 6.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_bitfield_flag_selector_33a98.c` | `45ae41b0a90b8a47c9ca801ec71a6c042ea4de3fbede8d041321edc709e277f2` | 6.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_bitfield_flag_status_decoder_339ac.c` | `11209d8a5138b3cf8b029ac6c0d7b3a80f6affb71f2cc1f40649f54a7ccfffb2` | 6.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_boot_entry.c` | `d3b17d95814ad2538632895705b3acab2839826586a99183b8d573729878c919` | 11.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calc_adaptive_fuel_trim.c` | `4c2e407efc9a55fb974bdade6d8c109db3abd706a75cadfc575f7df87961f990` | 18.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calc_decel_fuel_cut_445aa.c` | `4ec4fd22ae25cf4dda4f7ae9f75c3f8b5bcae1d7760be5c94f1a5f11768fd0ed` | 9.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calc_fan1_control.c` | `09870b03244a2558484dd4c3b28d5d86daf97c88fff2aa7dc5ec33ed6edff73a` | 8.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calc_fuel_pump_duty_trim.c` | `84ecafa4649e216d00f9805aa3b21053ba3001cc347b06cd0a089ebba83b0bcc` | 7.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calc_idle_speed_target.c` | `cb796c510b7eca00eb8ff99e62414952b7eb1b485707cbf0f01880b5e9486ee2` | 13.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calc_ignition_all_rotors_13c2c.c` | `c6fa439a518495395ed11feca8d512a8abe886dbd464be16be21e6bfda30ddad` | 19.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calc_intake_pressure_pid_output.c` | `4481390a7f4a3cba7518584561345d78de5a23fdeed55f91836c4b2f890d1d0c` | 8.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calc_lambda_feedback_pid.c` | `f9d280dc4382be45058cec6a8ee5dec5ea9b8d18d3eee6b89aef9ec07843deb5` | 10.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calc_rotor_sync_idle_gate_b.c` | `a71ea1a0264013f8afc366a3a3199970e1415b3fcfa24e5be38b05a68e72accc` | 8.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calculate_immo_seed.c` | `ebdd812da35802ed0e83d2f5ee36294d9744ecb2b58173107da55c8bd9632400` | 9.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_calibration_apply_4b770.c` | `2df44245d78283ffc1d311bb659b5b950f8d9d1718284c03e9b3e3a8deab1cb1` | 6.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_can_encode_handler_62abc.c` | `cd1bebd9d261e4131ce1c85410a5af7d99ac9ffbd3c6f18a1fa6ce3587815bd6` | 5.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_can_setup.c` | `41f5f23c4b862d74645ded8a340ce9a8c7783ccae8d2b60b7c03d261ef4df9de` | 8.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_can_table_lookup_583e4.c` | `51f02d8f8f58ab68f332e4aed0b030bdceaef9d5d922d9ff270c568723831bce` | 10.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_check_float_validity.c` | `93e4a46bcc27a9328a9faec5c1a9baa658c37948566a4fc82254b8ddc2a72c54` | 3.6K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_checksum_complement_add.c` | `a461f3ec3d9f627695a4cc10059efb82d279a62fda00060ea780e6940b507a61` | 3.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_complement_shift_u16.c` | `f5ea49b0a800b5cf79d7f1720882f167149e9ad93e6c30ce0d535eea5a169f94` | 3.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_complement_shift_u32.c` | `2ee4b77956e7d43b39fc583eaa278a879f386206d07d5c44f1abe74e3221d553` | 4.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_consistency_check.c` | `856629b1cd28547c60a388637ee0be4c82891c412a91fac70692ae46fe5ffe7d` | 13.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_cooling_fan_control.c` | `0851ab4177f11b47138af9d305d8d1a615d0f6f3f9b69878a1846173599f1c88` | 8.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_crank_sensor_init.c` | `3ae33cdc57cc47e9a27421074a880366f1ffd874ab1a61444202ccaad887be03` | 4.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_data_lookup.c` | `54230b603452ca1cfbe09a9687c54349fcb98450c3663ac629430d0a77af31a2` | 5.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_delay_loop_n8.c` | `50696335480fc7b6fc9be2f6e3da20ca3daf40753ac9e5c30a713fb585bb4276` | 3.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_div32_signed.c` | `6a821db7031b0917a4f2e3f6755fd96d8dae765ae8dc140c44c35270120c6a54` | 4.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_div32_unsigned.c` | `370be2e1bf40a6ccad94f4b4944dfd8ad36323de9fd9f38c82166597d5dbe81b` | 3.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_dtc_data_read_60f58.c` | `b9be7739963e2bfd6959d053c008274cfda71e3c0a1504520735fde4f5c8c46a` | 3.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_dtc_handler_610fa.c` | `8f4ffc8f76a3bb2e44da5fe737755059b73be54d46cab9a9d2b989f32cd657d1` | 6.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_encode.c` | `f39cc4f62b786e2841542acc1f27ed693673e317fcf586266e24b6bd2b7dee9b` | 2.6K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_engine_control_calculate_timing.c` | `ff68db2a9d041adc9e1099ff7f92bcd72808356df79d926e733e8ed3a40e880f` | 15.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_first_order_filter.c` | `0b2143051504fa2398263698d8298d9a77a7a6fa040f215afd7bb44aa3a52954` | 4.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_float_to_fp_16bit.c` | `7b8a47bb38b2938fe196b38698b716e2d17fc3695dd87881c820b9338aad0548` | 2.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_float_to_int.c` | `8d9670d590b0b4451db68318411c64bf081034455b0d227498f97e1307c29998` | 2.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_fpu_nop_stub.c` | `fae86484c74837324cef82276680994f6cae05c14f94c0dbd87f3a071840980d` | 2.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_fueling_init.c` | `72a085f40163b831fab4ce2a5b9223887515615091e6cb508a1ddea8ef6e02de` | 25.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_data_from_e2_ram.c` | `aa1d7c7563ee0535c314e3d7397840d8b34abf629a4dbb450e54581a98242ca6` | 9.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_engine_off_timer.c` | `310f38059d20df5e29aebe8917035aabdcbfbeb34022257ef4b62eac8cc719b0` | 6.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_engine_on_time_for_oil_metering.c` | `da92525f26bdab740b8b01d3f4e3cf46741845f4d62609bef1b2397c9285c2fe` | 5.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_fault_status.c` | `250b82149b6eb994e65bc642d21365b229fc84e80cf9a86d30f98cf21cbbc612` | 5.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_from_e2.c` | `0fdda5ce731cb4984eac804bd704eb962199db0b783ab477ea82a0d43e66dc7c` | 10.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_from_gpio.c` | `4f9eaf35cef82c3b163e589575d627ff2a23f4debb49c37c89d1850c34da07fd` | 7.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_hcan_register_address.c` | `69e334cd177c1aa47c5b27f695eb42688178e8e96e48c49e4ee98f8a08815612` | 3.6K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_knock_sensor_adc.c` | `970d81fa4a9be5c0716f744263fee7dfb8112de9a0a9d06ffb43bfbff26436d0` | 13.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_maf_sensor_value.c` | `28d84701f275a80cbdcce20fe3fdb3afbad61ce9db463673a67c1733bed9f722` | 8.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_speed_limit_cal.c` | `8620205eb6e9c32cc61d296898857b47b19dda1e13a3324a84245cb0f6d3d161` | 9.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_get_sr.c` | `8af31041941cf4ddf700674c9df8ac42c3c59d84d3a610d920cc6ba92017d884` | 4.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_iat_sensor.c` | `cd51a29dc2e9ddc0b15fcb2ba717cc93889ce80a5ba4aee5ed07a80a90c94030` | 9.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_idle_speed_control.c` | `872c83d0399ab9ed296809b2018ef18567d42607444d36c852ddb44360c13a7f` | 9.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_ignition_dwell_output_init.c` | `e0cfec43acc4a0eefd7bf45bf0befd9c040263df2835d3086ff942cc4475c828` | 7.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_immo_bad_state_set.c` | `9c554d1042f949abcd5ccf28adc8d4c2721c48fed2be80132d94ce576a692a86` | 4.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_immo_get_seed_3664e.c` | `e91c9f9ee1245a4205aac52f893b1a1510d3ffc651eea136b412f176aefd8572` | 5.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_immo_good_state_set.c` | `848d19b3e9b6b9b4b81705593938d314b3368d329aaefe9d45fd3ead55f9b12f` | 7.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_immo_key_expander_365d6.c` | `623c442fa6383470f67ac66c0bb69a0f3be4650836f06bf5222c4fefe5510926` | 7.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_immo_seed_mixer.c` | `b15179cbf652b7d73cfd466dee163f86b8afd14e88a132bb2ab992de7b1a6a30` | 4.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_immo_state_machine_360e8.c` | `729fb6a6aef2ecb6b3e082f0f98f6020966aa5b7343a5b29b4e5eb4242ae1be3` | 8.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_immo_state_ready_to_drive_engine_off.c` | `8b63b63f941b6e02f125244367fb139851917a77bd50743d330ea654bc03b544` | 15.6K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_immo_update_related.c` | `496d4c3d7fbe5024a55e0cc4be0ce128048ec7234124d243fb38490d44ce96e9` | 15.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_index_lookup.c` | `b1e02c397853bc9ccf8388316dd94978e16056b84d70c3125bc3155896ddf3ac` | 5.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_index_table.c` | `1aab140e4c59c3c8c73a633e69389544cc661878ca14a94b111beeccfe859f4f` | 4.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_interpolate_u16_table.c` | `b0d6902514dcd0ce98d8782ad4d8706ec0dfa35b19401d4223a0a7780f43cf7c` | 5.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_interpolate_u8_table.c` | `7c8a26add746c3c853e5f1d72064d456f367840d5c7a50f8eb2c54f8c8b50735` | 4.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_invert_and_return_8bit.c` | `46f6d31c8cf791698682ad1302101b377b778363f3312e8a653041aee99beaca` | 2.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_knock_function_init.c` | `bcce0f7f2091dac9dae7ec839ea406c07fb5db57f7a2e4871316b411b088d909` | 5.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_knock_related_init.c` | `708c1c6dda8047fa7861abdbd25516daf30b96bc05b192ed53f537a089d215a0` | 15.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_knock_sensor_adc_fault.c` | `cb863964d6fc86abd2de7f729e02152835b3512c800c803020899f4a919053ba` | 5.6K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_leading_trailing_spark_control_2100A.c` | `6bd2d0847859f3414d1bae243486be6a21712b745d8fe5d2035498bdd8fe32f4` | 16.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_least_square.c` | `1e20fb81148a9393c8315cb9282c1cc6ee7eaa09f60f7b1d8e26471e948aae2d` | 3.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_limit_knock_retard_max.c` | `92b2170024550dc77de7aecc6e760c98647d5b3e25c15663fb7b96a91edf4f7c` | 15.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_load_data_from_e2_into_ram.c` | `e12e7ce35f1326c7a7dcc2ec2aeb423788c9b7e40fd8ebec226ffa1c83193232` | 3.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_math_min_max_49ed0.c` | `fc505290a904ad8e5cf0c6a0b93635b7f8964de2eaaa7f47a6f6751092069024` | 3.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_math_primitives_2490.c` | `aca2bcfa580d1090aea0c4dcb12016d589238f5c638aa47020f19308d97f41eb` | 7.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_mem_accessors.c` | `220293d41d751c338fbee2ac4c759aa3ef7f443554cf7110a9dda658b1fa556e` | 15.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_memcpy_bytewise.c` | `ba1eca373adac8e40f6a21cab8a1f4dfe4b95aa2fb0f7aa55369c1c4a3ac68f2` | 3.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_message_queue_state_dispatcher_369b8.c` | `a2d1830da69df21fb170b5c7b7f99933f6dacf5c953cba75b4421c26caa16900` | 10.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_min_value.c` | `e88eedb7c5b5f9819a1e0b1a284a451ad014f67950f87115b19d48c56660f33a` | 2.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_mod32_signed.c` | `6a0430b12e2bb4b3f04fce6c9f833ae973b1252ed4055494da296d1849212959` | 3.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_multiply32_saturating.c` | `b89b64bab7b806d71c002eb73be18f972f5f7d5d47074e79f3bbeb009f087cdb` | 3.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_dtc_find_643d4.c` | `289a6c21717b719c758307b7f5385754a7b7dafb2dd767d20f7bb991e595a22e` | 5.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_dtc_find_6443e.c` | `3903eae0025abafa40f7994378e9f70138cab01d6575b9d73270bfa8e2f7338c` | 5.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_dtc_row_update_64258.c` | `cd778df062c8add4990338d9b7e5516f6c5fd00f587e07bb8ec788f13109b65d` | 4.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_dtc_row_update_64418.c` | `7ab0424d3be76277cbd17998c37a5d9861c4e3c65441de0a687e3d0ce1a1fbed` | 4.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_dtc_row_update_64490.c` | `32be5b94cd6d2434f86c5dc6777b596a1a9763ec36f831f5299c3bbb62181ce5` | 5.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_service_handler_632d6.c` | `ce2f87cb7be9ab3adef9b4524dfe050f6e9e58f33ab602c9f4baebb2b30ec9fe` | 3.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_service_handler_63312.c` | `68cdcc386315029fc715242c9679858f5db4012a195946bf219e5497f736935c` | 3.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_service_handler_63834.c` | `79c840c524e3b68aaf2e31d2e57f6d9591dd0ed32acfee13fa1d8708ae7f8a40` | 5.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_service_handler_63b46.c` | `751847d6028b635662aae4ccaaea7b53fd38d4827197ce519521cc25c7b2e2a9` | 5.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_obd_service_handler_648b4.c` | `65ef9fb028be7218833fc6bcdd28e07a6aeb13c1da69332f054b4b60aa8ea3cf` | 4.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_omp_rotor_overshoot_detector.c` | `4debd7554b64b10291110e5c88e5c811fca9c2090135e3531e3af2672ee6c15e` | 6.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_omp_stepper_waveform_driver.c` | `8ffd7bcfdd2bb25a449491a91188357b3621688b0f62bbc27c92ba8ec284187d` | 13.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_omp_task_0x1825E.c` | `47efe1a7c4f42894b3fb5b69bbb7219002cc2a36470cad23a6b952f01c6d9bf9` | 16.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_omp_waveform_state_machine_18860.c` | `091a52b45a1958f0933913c3970e366a1e8f8705ce604e382c92dfb9ab1552d4` | 10.6K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_os_task_scheduler.c` | `4936fc896bc7655dc55adec1a07d37e8dea58e34f6bc7f808bb5749702fdcabc` | 8.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_purge_control_state_update.c` | `5ffd6bd54972bea9f5e83d1b83e9b7203abc6850c2f3dfb37b3d5c339c1a452e` | 5.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_purge_flow_counter_init.c` | `b32884083fdd396ed2da0501a5decf1ab963bf04dcc9a8fedaa9a1c102ca392c` | 2.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_purge_flow_decrement.c` | `256970f53073afb9fc2421e267f661ab705878540d6bd31686aac12987a4e3d9` | 3.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_purge_state_query.c` | `1dc77a14162b224d3abb682caa48b3545f485d346c910a095228b6d66b3a4d49` | 2.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_radiator_fan_relay_write.c` | `7e79d54eb17fce642fd7d6809074b1454588b935e57b4ce54d33f92aa1effbac` | 3.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_req_queue_69602.c` | `210655eada7f8547303a69af9099186261c2c08e58bb1fbc3b2f2d4102b600a9` | 4.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_reset_handler.c` | `d1bb58561cd1217820b08f5923ad6e9e985b3f8f5a8ddb98278fddd482eea2cf` | 13.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_rev_limit_fuel_cut_init.c` | `98560f0cc516499344028cbb88c8829e15993bc13dcbdac894963606567dcb0d` | 4.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_rotor_sync_position_detector.c` | `1ee3a8ef8a95ab9d44dd5d5dcca2afcfbfd68e28b6bf0cc748b52bc77c331611` | 10.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_s32_saturate.c` | `329e3695b69224cb154c831c259026dd4ad7bc2fc7dda11dcd8dda807333d456` | 2.6K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_samples.h` | `c75e188a4c1d913e0d5db35ce5b03510e29efc572b2c2d79323cb1614ace220b` | 2.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_saturate.c` | `a10d27e9b10fca0dd7fe4c6b3f3f7ea01dcbe5ba5ab04cb14bb263cca59df30f` | 3.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_saturate_low.c` | `c31d11b83cf56e7e82c941c5923520be215e7eca912f7c89003952114e9e938b` | 2.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_set_immo_light.c` | `5c15b2ddcb7bb205fb3cc45cf6fec2efd72d034579e778fe47741fc221d83156` | 9.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_set_mem_inside_func_to1.c` | `d8f06111bea7bb1d1f9d769d70926b496398baff8f9404332cc6c03fb221a892` | 2.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_set_memory_not_valid2.c` | `b975f2eb0bdeaf98682e40d372459807df0df655924c6482e40ffe3d9acedaa8` | 3.6K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_set_register_reg_bit_val.c` | `3608526e183f2d5934e2863aaa6361a2f6f557f119818a8b1b2d69ac436f8508` | 3.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_set_sr.c` | `b8078381256ee6b55bf4e7853757cf44b070a52f5d4f8be371ebe814fc192a93` | 5.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_set_sr_param.c` | `0e58336d3e83bfb9402a5bcca3ffff63a882709b30319fed27b27987201abd34` | 4.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_shift_left_logical.c` | `9d66e0d5002d719b7f481c2d5f9e803d922802b03be962e07d4c8c2096d09739` | 2.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_shift_right_8.c` | `b07e083a800fbd72530f2a4fe237bff3a5240c45ef4b4cf0491a6343db1f8ff5` | 2.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_shift_right_arithmetic.c` | `5b0cf57c84a2f933d911f84c5a1e7a5dd0838a9575eb5692fccca974b2805598` | 3.4K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_shift_right_logical.c` | `6a06256c6d1b5e16a80decfed35c50f50cad502aea921908e417655977a0f620` | 3.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_ssv_control.c` | `7247341ebd36df3b44dd93e7e41c51d6714ed6bf849150a693283a070bd8135f` | 13.2K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_subtract_absolute.c` | `f3826d8bdd282ade5f4d232059dc7ce24bcb5e990a7c4a0440426c89c0d4132b` | 2.1K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_task_end_routine.c` | `ddf00f07874542779d63b4fd9f7dfd07a061bb22f81cb6d3b3a9af36c33febf9` | 9.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_task_execute_by_index.c` | `266eb21d62e116e920047e74238759f1b1a22945ba32a87513f4cc93b9a7000a` | 13.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_task_flag_run_c.c` | `ffb06746138fc19eed7ad08963480e8e081a18ca5dd88b7908ccc8869de7a01a` | 4.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_task_full_context_save.c` | `f78ee4de2c56f9417f61712377458a27568c61df748fa113975a2091e705d0c8` | 10.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_temperature_gauge_5aa5c.c` | `05e533b996464c26e732ad3de5f88c7ec3c65a3d64cfe680833263298755389d` | 5.3K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_vehicle_speed_sensor.c` | `2bf3fcc0ac1a86cab4576453fbeec093643456b513c6d9e8dcec2f8aeb8414db` | 9.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_vfad_control_35bbc.c` | `76639fd447b588671fe00d283e0616dcc6e75defbfd552653764b3c2948b8a05` | 8.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_vis_intake_control.c` | `0692ec2e93f7dbea9ab67067e5f3066db5338b1f0340f8f15411548141d0b1b4` | 11.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_wankel_leading_trailing_split_487dc.c` | `71a348b1a24c4385e864f0e9a7a62819d785f1f8cee22651c36aa8912f35a0f0` | 13.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_warning_light_5aade.c` | `32bbe649c2c9aef7ca5ebf99a959b2cb867a559d4005c11fc0ebbdd484f954f1` | 5.0K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_write_to_e2_ram_area.c` | `906a84b4c6dbeb79b4d05f0756f9404057e22bc6b9c6ea2bbd10cad7a283b9d5` | 7.5K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/tests/RESULTS.md` | `322164850e1f2ebe81bf56f32bebf4e2c4d8c7f6bdf02ec547a8bac900695fd8` | 11.1K | Tracked file |
| `reconstructed/samples/tests/VERIFY_SUMMARY.md` | `7c7e15c5218ba3e0fa2e2a17b133ef408eb88cf86651762b4c7bf61fa53a8d2f` | 8.2K | Tracked file |
| `reconstructed/samples/tests/_verify_aggregate.json` | `9d5243f6ec6b33e9033210b67aa2970e6b9ef2089d2698328b8f156703397170` | 13.3K | Tracked file |
| `reconstructed/samples/tests/common.py` | `71dd5817c77ed274b0f61c13c1392955000202cae697bb92cd7ee01b5a565ef8` | 2.9K | Shared harness helpers (emulator vs C equivalence) |
| `reconstructed/samples/tests/compile_all_gcc346.py` | `69a003cf9d57e0a61cf6227a11f0500b9f59879d902a850e7c09ee81944f3b67` | 21.0K | Tracked file |
| `reconstructed/samples/tests/fix_xtrct.patch` | `58e13fa17e1d496faa14a907d592d0404f00fd33ae93a34b6eedf6790da777a0` | 2.2K | Tracked file |
| `reconstructed/samples/tests/fix_xtrct_README.md` | `3b16d6f9cfed2aba11e33c2a64a75328b8f14ea5abcbe87a4f334f59ff67a6ae` | 6.3K | Tracked file |
| `reconstructed/samples/tests/fuzz_14funcs.py` | `52705150a4bf5e5695efb693bf68f1507f0c6302fcbbd3817a473884fa72e9db` | 24.1K | Tracked file |
| `reconstructed/samples/tests/fuzz_l2.py` | `22c139ab93346a9873f287804b2f5b2c2a00587fc846d96a90990e94ed8bc26b` | 18.2K | Tracked file |
| `reconstructed/samples/tests/harness_2d_lookup_fp_16bit.py` | `5b310e37a64297d24a3dd56bc9c2ceaf965b72c022129b18be11c6ba0ebce974` | 5.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_2d_lookup_fp_8bit.py` | `5a54f6f3849df71cfe1d9db6b0c6df96b4f56f05b69600e233782158043a3094` | 7.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_3d_lookup_fp_16bit.py` | `8b52c2d672f5e2a365c92454392749387843af141b62da1554364ac0097dbbc4` | 5.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_3d_lookup_fp_8bit.py` | `651d526f0233d2265970f5d819e26c852901153cf81a281390003798273735a2` | 8.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_add16bit_saturate.py` | `6f2ecebfe71e527fc2cfdf0fa3ab78e5dd7e6b332ad042f7b0972b6a291f5751` | 5.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_add_s32.py` | `75d3ef0f9a258043f5b5fcecf7f32a1fc33f0529470d87001867c01b81bc8530` | 2.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_add_saturate_8bit.py` | `cd73cc69b67565b51ca1b4977348e30e5f595da63bfa837bf04f19517678e355` | 4.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_alternating_sensor_sm.py` | `9aabc76c7eae86ce247449c5d08bd763db9c2cc5e56af678c97aba7b675e7714` | 8.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_aux_fan_control_task.py` | `ecf4bdb63dd462cc6cc057576330063144761068ac2b40a8b717afad9e64c71d` | 10.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_baro_sensor_value.py` | `b99d4627e1be922d4fc7b1a3e894641afc49b4dc07715df6937e22028470ac9a` | 5.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_battery_voltage_monitor.py` | `c377521a61333b6631db8b195c5e10ac45dedae27c8e3c2a64b1357b285c60b5` | 9.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_bitfield_extract_merge.py` | `6beeb3e85df6b22a57db35a3f798939deff96badf3a92c2ce9b4745cec7f232e` | 6.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_bitfield_flag_selector_33a98.py` | `80f59d8a1e6ae7e2c2f88a7e77381920ce33576b45923479a0f77cc0d83711bd` | 4.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_bitfield_flag_status_decoder_339ac.py` | `fd30bc037c4616b0b93000c7fd77bb84e1c63271e4c83d47102c8cba8346451e` | 5.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_boot_entry.py` | `2a5b7bf8e0e995865aeb28ad96ba16de3830e63817aef358696c4e362f45cd31` | 9.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calc_adaptive_fuel_trim.py` | `5e2b06f2361c6d0fb5bcd88ed5f4be8ea69e69ecc6abb764e77307cd6dafe27d` | 12.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calc_decel_fuel_cut_445aa.py` | `bdea5cda894cee3d0771dbc0b43b4b721ce00b43988d44567cda90e3ee0aacf2` | 10.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calc_fan1_control.py` | `b79038f09ecfc69b0376f81703446cd5306f966c9f9bc3ce6affb9776d2cb467` | 7.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calc_fuel_pump_duty_trim.py` | `f99181b61444bf83377d4f3f44465dad1ee2eae9ba6b3b0be325cd97c12271da` | 14.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calc_idle_speed_target.py` | `7f00e67824e6a5568a4340fdd6e98d452e4e01b6b88217fbe265f8e477c04d59` | 12.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calc_ignition_all_rotors_13c2c.py` | `0b7d5220c6e8b248550d260fd29ebd131ff4b0fea7ac1c6452e460b42ab674ae` | 14.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calc_intake_pressure_pid_output.py` | `37b341400d28e62e1048f797bd43451d9e1845070b588f716332edbc34dddf76` | 10.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calc_lambda_feedback_pid.py` | `88ae1d2a88299b875f99cf9fc74312b451224d066efa243070d53bea53e008ac` | 9.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calc_rotor_sync_idle_gate_b.py` | `f79d4165f00f48e2c9903492a4a3f6ee098c51e5e92c5ae7f1fa6776846f43e7` | 11.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calculate_immo_seed.py` | `593a48220ea4b8b3955b2c10d921d08a1fcc30a38d8b97fed4db39c0760ca295` | 5.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_calibration_apply_4b770.py` | `eb6e5f011b52141cb23fde8b23a25a472c25779589a4fcca5655abd175f370e2` | 4.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_can_encode_handler_62abc.py` | `81b961eb6102c11901f6a2c7aa2ddd2e6072bc16bb9e61e532e4d6ca45e191b3` | 5.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_can_setup.py` | `8258ff31d1ad09885fa2444479ef388fc1cad8ee22cd3c26d6fe3deb26725d1f` | 6.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_can_table_lookup_583e4.py` | `ac1c7c5adc57ec0cfb784eba12bdaa493e0ca0ffa6a54327c4422edd12a323c9` | 7.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_check_float_validity.py` | `651642fdfd87f4ad3ca43900672edd1fb10a85f5f7b663ed7e83d322610319b6` | 4.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_checksum_complement_add.py` | `0abb18e1c7b2398b5252fee7792c0cd26c01f664b89f70974e092f467fa21536` | 4.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_complement_shift_u16.py` | `f1c33d8850c9c3d793b3561b77bf69485fed4660d0a4bee6f8bee9c14034961d` | 3.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_complement_shift_u32.py` | `749c18d589a5ef50fab428a37a5e5809d26fa4d82a56e38901ed4d5835a54645` | 6.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_consistency_check.py` | `9c0b0e1b94700d6a73114ec6fd3f5f85035fd0a3fa8f117bf09b175224144502` | 11.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_cooling_fan_control.py` | `ce7507aa3e4c74d4eb1b68452c66b58f7cf4025e71ae138b442861b923bbd30c` | 7.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_crank_sensor_init.py` | `ff5887e4a1ce60f747cb159ce96955c1ca3f03a43ce83244402b147018416609` | 9.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_data_lookup.py` | `20623085b5014de820074f98e3b85a0d67a0294e12a647ceb879e4cdb49dfe36` | 8.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_delay_loop_n8.py` | `52cc8a24d1410f3427a74d6ee6ad3359fb854e7296648c354c007363a7c955ac` | 5.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_div32_signed.py` | `48201a0af396f75cbbf2f2871c7bd374cc969dbe87323199431a5e1b842aa563` | 5.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_div32_unsigned.py` | `83b3428cd63531cf71cc3033d514c965fcbd5affa35c89ffc02609e34391d565` | 5.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_dtc_data_read_60f58.py` | `0cd6f3292099c977cf84ff20bd83f124126f8bf516e7cf3ec4dd34a1e11ba355` | 5.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_dtc_handler_610fa.py` | `d0292aa635d58c50a740ce84e23e85bb68acb85c6a36bed704383da69c17b16c` | 8.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_encode.py` | `366d444bd7fde51e7ad70a8efcc36f261a74255897dd93645a8fe69de2ddd0df` | 3.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_engine_control_calculate_timing.py` | `497fb77651a06bcb6c0fe13d49a55802101ee3d38e1542b69ccb719f50c833b4` | 7.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_first_order_filter.py` | `90f73ab1709a03bfaaac0518080357e71ce9319358bba5316f3ee355989b8375` | 4.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_float_to_fp_16bit.py` | `bec93ceee6ff81e68c4a2244c8cfc86c3fbc19c235037b359973c69e6946434a` | 5.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_float_to_int.py` | `8758dcfdf25f42df64c777160c92089b4610506d7fecfbf95236ae9fa1a107df` | 6.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_fpu_nop_stub.py` | `a88607659ae281562ccd620ec3ad2acc633f71f82d536ad416864f4de8e2dc19` | 4.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_fueling_init.py` | `20503fdbf29df8ba09595f74cdd67cf45d30dedb864da5bb089fab53a5ec4763` | 14.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_data_from_e2_ram.py` | `5c20cc7a541d0d58946f03019e9b41d4c2f6e4bc67d3fda5ee9c8801f42d8f24` | 9.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_engine_off_timer.py` | `074eafc75519f49baa52764104e3914fa3cd761aec62dd27c1edf793b5b11093` | 5.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_engine_on_time_for_oil_metering.py` | `5cb844003d71cf867dd76e076270abbb9563519fcf1fa01a9309e4e1ce780d83` | 5.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_fault_status.py` | `a2777d57128ac578a7886b00aefd49bd2379390847a6c95be1087dea7e2d0348` | 7.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_from_e2.py` | `4db2aa7139912f4b40c28b43a990d3a14d0a80f1b1281292780f6e3f8a785ef5` | 10.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_from_gpio.py` | `e929bf032b8abe98801f20ee1617098edce793deb369d54c9626a1d408ed9254` | 6.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_hcan_register_address.py` | `65ae2ec47957f47edfea4a592253d454fe89ba2353b13b5dbad9f70b7e198e27` | 4.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_knock_sensor_adc.py` | `c55411f4a881d2c5ac458a784ac85997fe46005b54a1967ae71a095c15919f69` | 9.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_maf_sensor_value.py` | `af2ece1b2fb3ce4058552fce3ef3a34ddf8fc3acc641703a432a8345a2f92faa` | 5.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_speed_limit_cal.py` | `394733278d16ae74a09d80c16bbf769422952a0b718582390f42d3e5d022b1fc` | 5.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_get_sr.py` | `629cc0825b53931e4e0e197aeb6e08cd9655b23f03e2ef7b560b7476223bbd58` | 5.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_iat_sensor.py` | `5d662401aada09b6910763fcff86f0296c1478701341518b34ce9cb8f385d25c` | 8.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_idle_speed_control.py` | `472ac630eaa842295fff481979e6ca4622dca7a93171cac8c2ae57568de80d06` | 9.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_idx_table.py` | `d065b25977e18ac0acc9fa20e7548aa897ad45ca6cf86c930da6b6c300fbe309` | 4.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_ignition_dwell_output_init.py` | `432ac13ba030b6906a651a0d8cedf925786c4fc0d442237e2986591bf616e6b3` | 11.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_immo_bad_state_set.py` | `a3d1cb5f0ee4b58d5bfd1ed7e61f3319ae8d77f9d080c324c571d50b573e62c5` | 5.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_immo_get_seed_3664e.py` | `e75222c793f6a0e1b8a4ec7eac04107b9678d49dfb74ab221ac995619fe6be72` | 5.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_immo_good_state_set.py` | `3a6031f140541293e416fca238d0ba938231f630d4a140a1139d94f9a5242497` | 6.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_immo_key_expander_365d6.py` | `814608f26d57ac37267e86b8abacc6b8ab0f83b51c9a0c85f9b355a6a15447bf` | 5.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_immo_state_machine_360e8.py` | `6e0a5b7dd7d71ad79d00f5769f04bd719d95475dd43e4fd9fbb0f5aa1227b7e7` | 10.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_immo_state_ready_to_drive_engine_off.py` | `476959740aab6df22df4983d5924bc372b805103e76d6f9373d559f978f11028` | 10.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_immo_update_related.py` | `47db13015ea5b810795d3d9b5ab83211f13ed54ab51ec26f22f10359ab1d74c6` | 7.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_index_lookup.py` | `e719719c53c7fd4bd5c23a93420939e01ccc5298a6b3582dda18e8d08797faec` | 7.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_interpolate_u16_table.py` | `d242f4805240922d483e215bf17b90d82a7ef0b0b4c5e971a223e5d9bf3eab19` | 8.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_interpolate_u8_table.py` | `8c461b914f5141950b25b135f1c4ea93fd91de2e17c6e7a8c2124c208a4e5932` | 8.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_invert_and_return_8bit.py` | `89126dde79ef1de016b8d796e611f35f52ee17ed0e0bcb292926c55a0f297805` | 4.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_knock_function_init.py` | `e6cbf7b3af2f877865cb0f41c93948eb35cdc16d55925f5d0975bc923f5f74d9` | 6.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_knock_related_init.py` | `a4f3b1c43026f9c87983c2f324eaee4372c842bb36da80b378ea27a855445fa6` | 9.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_knock_sensor_adc_fault.py` | `2b6e8b9915a2a4a8555b001c9875cfc19aab4e5fd1708c22f7eba025d59456e1` | 5.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_leading_trailing_spark_control_2100A.py` | `1828175bb1c1ad4591bf954fee0d192cc786dd81e2cc4c8f246fb0d1766aca8b` | 14.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_least_square.py` | `c57555ecfeee62686e15b5552d483e7269ff52f00f89aa8769ebd74efeae5780` | 3.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_limit_knock_retard_max.py` | `b56fe079f396b8dbf2928639d1a76a269a8be95bf7dd2d7ae31c295774485476` | 9.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_load_data_from_e2_into_ram.py` | `c474286a42bc3775e11d78fbb107d6ac4d28374e3b707a221ea991f402ad3f3f` | 8.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_math_min_max_49ed0.py` | `20aa105fd371cc3a1107b4cd3072c0641ab88b51fc5bdc6c9f538e6221825dfa` | 6.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_math_primitives_2490.py` | `8a1777e2f5681593c98a96da8119a5be135b764422f04e030427464c37a64210` | 9.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_mem_accessors.py` | `a846f408f390675b6e78645ab70dceff41385a6c1b1369ea6682a2c3b04c281a` | 15.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_memcpy_bytewise.py` | `1dfec820a7c72c51b3242855c17561ce7c7e65fe382e83155080b76debead6a5` | 7.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_message_queue_state_dispatcher_369b8.py` | `fa663ef8c5a4eca2a93a18b23f8f054573d648cb72ea0580b9e2f360edd6d22f` | 8.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_min_value.py` | `954708f1db44d30f67acea00f6f1aa195d146fffde82228e1d7fcdf5eb0f0960` | 5.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_mod32_signed.py` | `4b9b5c9ea7aa7530f15b5f8f194293de3918383de1b54782082845c06e9d089a` | 6.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_multiply32_saturating.py` | `3b54446edb02f86c06517c631f298aeb89541fa7fe047d21a074e6f8ee73cfc8` | 4.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_dtc_find_643d4.py` | `76b999d4a05ef12ee2e7f024f56b44fbb6b1f216012b0f7ab5ce84930d7d3b82` | 7.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_dtc_find_6443e.py` | `b88a960c53bf2f73b9cc816e24fe4cd81ebffceccc34e8c7e1f2f53a0ffc9bc6` | 7.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_dtc_row_update_64258.py` | `8dae2b99820846e95f907876598f6c0dde3d5f8f3be11d22e22665dfd6728e3c` | 5.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_dtc_row_update_64418.py` | `85efe7064745085b4b345473630b30811c0ccdf4f981621221035c11a84d6804` | 6.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_dtc_row_update_64490.py` | `148cbfaa337fa6d63ccca3a26f27a29b848c79aecd3a4403b8b0f540c307da31` | 6.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_service_handler_632d6.py` | `c419d886d3b9f63be78e36f4e0ecf5f2fa089d1051712fb67b02661dae5baeb0` | 3.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_service_handler_63312.py` | `a373a6fd43e195ce7df035451d0d8802065101c1d53cc43c2b3fbc1bffaa8797` | 4.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_service_handler_63834.py` | `ae6ef15b1737c61fa31f7b1f74f135dae49138f50014fc4f24b7bd2f66c9603a` | 6.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_service_handler_63b46.py` | `b696f68dd9e4dfe367726a7d3b43946af52defd8f70dad1b047ef16afc2eca88` | 7.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_obd_service_handler_648b4.py` | `fac4ace8979ba9d275e2cc00bb21f9666bb2496f0cfc309d2ecc6e247c185142` | 6.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_omp_rotor_overshoot_detector.py` | `4f0a120a5823a57848e1091085e9beef7d8ea37088759f399c72a515229bb6cf` | 8.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_omp_stepper_waveform_driver.py` | `b8a4fbbbba6d8502abe547f460953e240f8642d2227d2fd506475d7e465c4c6d` | 8.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_omp_task_0x1825E.py` | `4fff9ffefcd78c8855062f74247d89921ba37f888909e96f40594d262f9b0608` | 17.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_omp_waveform_state_machine_18860.py` | `a211528b687c7e3ef224b3078ca1e8ed0c75bd7c62cbe06e1dbd5278467b7816` | 13.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_os_task_scheduler.py` | `0f8580f9a73aa961a2ffd93f5d528d6093be56d864dee92e0081f230690a7566` | 12.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_purge_control_state_update.py` | `8dc465a281ef7bd4b94724ce7fda9c95a8b080471fbc6253e12f988696bcb018` | 5.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_purge_flow_counter_init.py` | `2a2f6a945b1f32349eff46bb5d8df24e99b70e8aeac6dbd802057aa72b2370e6` | 4.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_purge_flow_decrement.py` | `10cec04cfd0334dd2ad7f4dfe71d25afafe39ffd6ffe77ce316f8a04d05217dd` | 4.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_purge_state_query.py` | `1ed5ec749195b58dc4f1957cc8b45cdc3584eeda62f8b3b94a5342618a53f753` | 3.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_radiator_fan_relay_write.py` | `3ed7230ba772a4c1a29a4f10ba16c2869c47f9f650c64015a657bd3ee2c81a7a` | 3.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_req_queue_69602.py` | `1c4b317f3a19fe877773149156d18479a668d1df7e0eb177fbc3889f3df77886` | 5.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_reset_handler.py` | `83fba609983edaf70b92d32fc8c0145f5b9af71106208fbc260a8879582659b6` | 12.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_rev_limit_fuel_cut_init.py` | `37d99175bb273f34d76eadf724375cdbe962b31af45c68e8181b4e132204f1d1` | 5.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_rotor_sync_position_detector.py` | `7a9d3abfd62f902d5316f9cf2f87cbd92722c4e664899118ff8afb855d6e7315` | 14.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_saturate.py` | `ca1425ba722e08653bae34df58967193f5f93d2f2a07950f6c54f02b5ed63776` | 6.4K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_saturate_low.py` | `c009e2215745e8bcfa9a54a402bd381483ebe3e790103825fdfe5408f22e033f` | 4.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_seed_mixer.py` | `ec9e8c62a64aed9b8f58ac42b23d48f5a14af948d3ec40e17803cb1d4129ff52` | 2.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_set_immo_light.py` | `f7ae5229f0d28167eb2cbfc0d17a44a02820a048fe0f2d14ddc843d4158b5568` | 4.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_set_mem_inside_func_to1.py` | `f9cba41247ab457ce3a8b97c3c419282ff620c282d5a07671db98bb5697cf241` | 4.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_set_memory_not_valid2.py` | `b134cc26664545389f7e48f944e301ec6dc853d84a0992aadd3a5c64a06aa049` | 6.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_set_register_reg_bit_val.py` | `b682a9a7b390e2cd3d7770a6d4be57a253236bd64b2ee739422f9d543885cd34` | 5.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_set_sr.py` | `8e5b25b77bd13601f1b73c17e7e1d078296b95126a0a8467ff7a1506534f1107` | 5.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_set_sr_param.py` | `6155ba57db0e567e2a692d8de21af8e7b71c008da7e6d7c0c32c87b582bcc1ba` | 5.5K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_shift_left_logical.py` | `702259b4645d1f50f25bb67eb493223f289d0d15aad5d002f47275b7347f3aa2` | 4.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_shift_right_8.py` | `aa8aebd845fe7313af9ff060be8ef59ae9bf876c00ff8abe12f5d1eb8503c42d` | 4.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_shift_right_arithmetic.py` | `e014ecb63c546193b4c70bb7a88850d9d3395336e9ffade03efb249a2ce5051d` | 5.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_shift_right_logical.py` | `1373f137e11fa278b07b9b62cc2cf55c73cd5e8084bd8333b8f2801f8a9a5510` | 4.3K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_ssv_control.py` | `e7def96a7b005fc496b7f9ca3f099732b4ac476828739c35ad97b6a13adf75ac` | 13.2K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_subtract_absolute.py` | `90729c324699dc09e6b473c137ddb56bdaecbabe8742e06f51e38bb4bf1b919e` | 4.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_task_end_routine.py` | `7fbd6c77183919edfd424edba7805d4cf9e8fc4c7b4fd81f800158d0ce318405` | 9.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_task_execute_by_index.py` | `2c09abb2238cb5f3a0845190b5cb6e0f6c992a9fc5ca2a3a2eca2c63499b9bbb` | 16.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_task_flag_run_c.py` | `13790fff5bc207ac296292b911907dbf61a33ba4e7600483cf7f9a84269b9236` | 7.1K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_task_full_context_save.py` | `ff1929a5ab847a0f963d6a35889061bd499afdb4f8c77eb7c0fe1074a380c953` | 6.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_temperature_gauge_5aa5c.py` | `933c180d4ad644d4be6f5a0ae48a0965b7f9e666c3ebc0b395b6ecb4ed4fab65` | 3.7K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_vehicle_speed_sensor.py` | `769292ed3c535b99236c3c854b75353d4f4055c4635b6ddba564b5449db2a7e3` | 8.6K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_vfad_control_35bbc.py` | `2159d97b2530932be5dca1c60b675ce2b2f60e3295144a91e8cd91a5c991211b` | 9.0K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_vis_intake_control.py` | `cef37f86f80fb145c04f6ab38f27423f6d2fd135b9df395e9f427033499f05a4` | 11.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_wankel_leading_trailing_split_487dc.py` | `9d00cc5206a71081ed6ac7c64a63f0409aa40a384d4eeee81a6c97d8f24d092f` | 9.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_warning_light_5aade.py` | `46b85c5ae7caf9234770c5ba2a904f97c17319abce8558e320f932c834b39a09` | 3.9K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/harness_write_to_e2_ram_area.py` | `1c93c3f945f0aa6bf4575d1d32b1bb49e03f426b3a29e617f258d16767374348` | 6.8K | Sample Python harness (emulator vs C equivalence) |
| `reconstructed/samples/tests/host_oracle.c` | `664baab2a6ed228d8fff68e281915d4e0957d069d279a3f13289198a7990252a` | 3.7K | Host oracle driver for sample harnesses |
| `reconstructed/samples/tests/oracle_2d_lookup_fp_16bit.c` | `90910fe43a133d72b947bad4450890c313ca5d67e6783d2bd6a571e1f68a5e5e` | 5.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_2d_lookup_fp_8bit.c` | `6a98021c575ff5ad9522495e71107d20ce22e6d8a725cf4feb9f61f937a6230a` | 3.3K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_3d_lookup_fp_16bit.c` | `12d67c1bf73a74538684faccdc50b2d48d352fddf47e496e26c5e737ccd66c84` | 3.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_3d_lookup_fp_8bit.c` | `220483b6f72fcdd9be7b4ff054fced14428578019b8b2a189306eee97e9f1b29` | 3.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_add16bit_saturate.c` | `998e5a6d9086309abf1100450b1afb1ca7c5c12766aac26eaaf94320b4f81d7d` | 1.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_add_saturate_8bit.c` | `f4155eafd561edf04d694e98d0a3a92788e508d86b3bfd1b660d7ae3eecf9417` | 1.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_alternating_sensor_sm.c` | `fee29d18a5a4a6b3bc1e0d95cfd0365c7d4413c69487b0c3651cd433035bb5da` | 4.4K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_aux_fan_control_task.c` | `a4a7b558a6d523deee8ff50d8d1e07c44fcf68b8c93a0ef39f5f0bdf565cf94a` | 7.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_baro_sensor_value.c` | `53de72ab9cb591b868f1398a82d159f646720de860d830332a78927558376fbb` | 3.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_battery_voltage_monitor.c` | `2f38f0d700fe61f79c532cc0dcff8ef37a320d34478fc9f3fab30de48dd7ab5c` | 7.4K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_bitfield_extract_merge.c` | `996388dbb9b3d8a028ff32fbd36b304ad9fbaa60ff4ad3548301e24451dcd4a5` | 1.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_bitfield_flag_selector_33a98.c` | `c217adaa207fd6c2cd316921d74949170a6ea06778fc49d49b9509639307253c` | 2.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_bitfield_flag_status_decoder_339ac.c` | `ae5d3e209b442094f3153577fa2c390d23e1b3fd9d8bc0db94c44af894e1958d` | 2.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_boot_entry.c` | `950d9146a5e407a1b91d0a7bc197b1abadb4a8c10f29674b12060d300a78c0d8` | 5.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calc_adaptive_fuel_trim.c` | `9d6ef359197dba95de976b9e99997560f196eb4c9b4bdda423ff7eb7fe08ad5e` | 6.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calc_decel_fuel_cut_445aa.c` | `86ea290defcec4eb5bb73b11fc7b86c9661bf5043eba3b3f1b4f1b51b50e4f0b` | 7.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calc_fan1_control.c` | `dfadfe2bcf4a2a7b2e1d58d0ebda0536dad0731f58c982d25b34d11a5b357d17` | 5.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calc_fuel_pump_duty_trim.c` | `8e52985abcb7638647f8bc4de75ebb7ab822d89f6296ad45b750ec44cac6be23` | 7.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calc_idle_speed_target.c` | `d03b219aa48c659ae3048716b58e6eb66df9b39e706f906bd8397589d8481a9f` | 6.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calc_ignition_all_rotors_13c2c.c` | `d804f66bf27e56c4c384c91e36bd067c742827954696c1e7afb92567032d242a` | 11.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calc_intake_pressure_pid_output.c` | `f66fa30c67278cdd84c7fd86606f6238dc8b4f1a177343b237ec6303dd1b1386` | 7.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calc_lambda_feedback_pid.c` | `b3959f576307d9be633e9b10d58d18658f1d1d6de87ad7a1181f3a8505781850` | 6.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calc_rotor_sync_idle_gate_b.c` | `10e91fd83fbb4ab5f1fab850eb869716e67722445abb16cd92acec6c61566196` | 7.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calculate_immo_seed.c` | `35f4ca91b6633d84549735a342fd83d706e7178d03d9c4d61b711133d3230484` | 3.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_calibration_apply_4b770.c` | `bcf5b05566616d73423c74ddfa2cbb75ec90e5bc4917ef31b429b25d9e6dd976` | 3.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_can_encode_handler_62abc.c` | `6968a6b177e6d7d692402b8c6a38c4bb3a57c42cf4ee5f34947599169cfe67c7` | 4.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_can_setup.c` | `d82ba7ec0fc98ade22d6a839fc2d5528ce9b03dad684f91c33c70793e3f2566d` | 3.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_can_table_lookup_583e4.c` | `3b308572a191cd7326d00564d6d77e99bdd5888b5964b87f6334be29e0f3132b` | 4.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_check_float_validity.c` | `d8e7801e73ac28096f438075238d9d971d2ea222e324e2a72f8913e667f906f2` | 1.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_checksum_complement_add.c` | `046d8e674138641e30f18d1c18640125ae9e698c1bf7743bd01fd3c777148183` | 1.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_complement_shift_u16.c` | `7c02492f3788801a6dd695ef6d14d1714b73099d5e7f283b6f33c79c2c072e7c` | 1.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_complement_shift_u32.c` | `bc950cb0a5d1b7f547cf2d6953ce49fcab4a1d7d4197a4250ea5f34e94cc3446` | 2.0K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_consistency_check.c` | `b431d4cc069eb9b89b06ded3651b1b4694ef77e13b607cecdfdb13819aea6c76` | 6.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_cooling_fan_control.c` | `c28ef080849d1e67244473207de7391c4f0a93547a25927b885273183855072b` | 4.3K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_crank_sensor_init.c` | `1980018c0f898b453f4710deff6332141fdb090cb89e70501ba7e3ce29ff0952` | 4.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_data_lookup.c` | `f835f6af549d66a0aa3a1035c9fa53bee24c9b8993cb05d3501a0ceceeee587a` | 2.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_delay_loop_n8.c` | `77e2c1773c77527f340cd05e1ee662d13b80b3157146947c596ef3ed8cbbb574` | 1.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_div32_signed.c` | `da394089fdbf4b43caa525d9a1c0eaf485860eaf1e46c8b9bcce2aa473482861` | 1.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_div32_unsigned.c` | `a7c8c4206f3d48e29614cd49d4a9248e12888fca9d22a73724499e1081e2726b` | 1.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_dtc_data_read_60f58.c` | `d8bbced5a35cc670c45197926546a9360eb3e9bb5c4ca9600963d6bd09ed553b` | 3.0K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_dtc_handler_610fa.c` | `2468e7312d4d094e0aca7f29d8825c70cc7d2ead287a819905dd2cee5323bfa5` | 7.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_encode.c` | `caf3f35d661e21fb3dc3f78f29e1d227e3b20c6b74475b7813b49d619481369e` | 1.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_engine_control_calculate_timing.c` | `4fe0b4442451387b77fdeff321bc7963cbab2e36b1c9d4e5da31513a49280c54` | 8.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_first_order_filter.c` | `aba7fa50e68888a1384933bbf36012052a759423d1f279b7ced278176a7d33aa` | 2.0K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_float_to_fp_16bit.c` | `89495b4b8e288745d5c653b85d7edd3dc54f5823a27b4812cbf319dbad6bc43f` | 2.0K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_float_to_int.c` | `0926d00e7af2f1b6db156d06650f8470c0d416eebf255d3e431ff507a456dc21` | 1.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_fpu_nop_stub.c` | `c1e9a3cee122f02b95dd21dbc8f41bf28f7eeda06491053a4943dba399253eca` | 1.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_fueling_init.c` | `bb55c1d3515392d6776ca0d71b6d29f2ce8c66ddf4d92dcd3f2760b7f166e045` | 9.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_data_from_e2_ram.c` | `6c31f7870b83f07a2027a333dbfbdb063bf2de0a9dc1d5cbd6d1a2bd606c6a48` | 7.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_engine_off_timer.c` | `fc8cb2ff5c6c759d2c7f5aaf58c02ef5b747691411bad3d86606c31f572a9021` | 3.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_engine_on_time_for_oil_metering.c` | `fa6f35d94436a1f750c0bb932649f6c9782e406472894519a644f95bdef28ef8` | 3.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_fault_status.c` | `dae4d8677d798609b10b434e023980481c8eb90c6d54c46b7823c98de5b4f2b9` | 11.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_from_e2.c` | `7b9b99254c6889d9e54aacbc175b5b2b6df97c50881c461683c78b5812a5167e` | 6.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_from_gpio.c` | `b3fbf2f80d9859df61fab5249cabc3fd5c86043e6b4a1bd154caef29f8b23369` | 3.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_hcan_register_address.c` | `0f2fcadb55d6e575abcb1c11254dc16a09e0602edf93f1de43183554b6bfe68d` | 1.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_knock_sensor_adc.c` | `d17cb7af0755ef10c7e7f48a07a44bdda184241859e480b75c9f667018b4d35a` | 8.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_maf_sensor_value.c` | `07ef127665e4a52d22c46da05719ce89942bfff7d73993df150b8bb5282c55f6` | 6.3K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_speed_limit_cal.c` | `cb08ca6b524e6c8e2d97f0b43cc06e6b2610f34c421f6000b86b9ca3ed4d5c8b` | 4.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_get_sr.c` | `7643c2dd4d30a5f2801650baacdddb81feafdf84daa758593a36843e1089d85c` | 1.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_iat_sensor.c` | `f8c2cf9197fedb982eaa0e388a3e9e04a50bb55f6b800cb27ffdf0ec557283f0` | 5.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_idle_speed_control.c` | `7abf6e29bcc6096988a057f81bbe881a526dcf9ba38935b132a2ce330a386890` | 9.0K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_ignition_dwell_output_init.c` | `528ce26951d1df8a65d4c62daf32b6acbaccaf66a3d0e02e43f112619d16bf60` | 10.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_immo_bad_state_set.c` | `04e7957c2938de13e9a3207f65ccec37ba1cec2ad6638f9663ad16b5b80b5f58` | 3.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_immo_get_seed_3664e.c` | `069f8961dc75dbebc23a136d90e17a3a31f5378c60a5b9b788df6b61624ca626` | 3.4K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_immo_good_state_set.c` | `d7d86868cf6e3c4fc4367bbfae1b9e721e13d826683d5dd11984b7e844e7642e` | 4.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_immo_key_expander_365d6.c` | `a0d0cbe68d2b09e5bee21b31c4bc7122d5289c3983fbd9084e01c9090e48178d` | 3.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_immo_state_machine_360e8.c` | `775a929518b23e40d93f9d2a55405898918cf57ba0e8a18a3677adb5d9eae8aa` | 6.0K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_immo_state_ready_to_drive_engine_off.c` | `a4717c29ed3787b02db4129ff1fde0edcdcb07ef6b31ffb5c7d1ac688dc106fb` | 8.3K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_immo_update_related.c` | `6d9d1cd45ddbef8c5753b0d2c1446f7efdbdd58f677811fe5660e41074849630` | 7.0K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_index_lookup.c` | `1804fda6d3de5cefa1fbb1045864b2f302be3a202712db92b419d35e04e21d46` | 4.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_interpolate_u16_table.c` | `8ab03eafdadd874738219f0edd815e67955b970440505dd1f29b9c36f0ec4d2b` | 2.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_interpolate_u8_table.c` | `772ce16d410ef017ac0b3b2c5c910c0bc0b4df13d3203500a0d0c132243aaa0a` | 2.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_invert_and_return_8bit.c` | `2cad51b2511b311039d71f21a9513c978599fea6607f0b74a55f9d515372c705` | 1.3K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_knock_function_init.c` | `ee6e09bd1da4c2ff598cda5df2b0ceb309664727354d0cec1a624c215b4c2f69` | 5.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_knock_related_init.c` | `a5603237b29e7543488fcbb922f1f9590f47cffdd94d126b0371008cd29af16d` | 8.4K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_knock_sensor_adc_fault.c` | `067687a98530ed83fda1fcb130911f8172d11c8db9f5c6c6bf2697cc1a9b6c6d` | 3.3K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_leading_trailing_spark_control_2100A.c` | `874c96805fbe8597db1e118c737f73b47de85ea711cb98e4d6ceb5ec6a851602` | 9.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_least_square.c` | `d0b82e22ed26b93f4911c6df1b8e60ade6274c25dd92d245807a656252242ad0` | 2.4K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_limit_knock_retard_max.c` | `79b697c8d39986119aa9b78303ff4348c862f5b222d858decf41572b4a720b6e` | 4.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_load_data_from_e2_into_ram.c` | `6853a17165515e6357492e916e5ae941099e3c24acc3a68b99656632d47e2456` | 7.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_math_min_max_49ed0.c` | `c23fffceaed8c2f9e33e26137e4b44914538e13b4bc3640deb53669410baa664` | 3.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_math_primitives_2490.c` | `5cad025e59ec272d09c5c2fba9033e335d739ba2720e74f311c4da33addb7d02` | 3.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_mem_accessors.c` | `b2fe8a7200152c734fbe2fd100fb84ce8317095229676bda72f97104d296b0e7` | 6.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_memcpy_bytewise.c` | `cc01b7823776e8ac852208c841a414af62311c51f68808ac49a810eaec99275a` | 4.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_message_queue_state_dispatcher_369b8.c` | `da3bb34675dfe79790283b885295b389588a1f09a0019286b50edfc921e7ded3` | 6.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_min_value.c` | `85e648ae6981a4b8c05eeabbae0240295024eb22cf98d22ed7f537c0800b367a` | 1.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_mod32_signed.c` | `77b839fe4356595675d4a5fbe6bd0c6d7fada4e96e86929f6cbb98ed11b7e8a5` | 1.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_multiply32_saturating.c` | `c9bf7b195af596246c16a2fa4a9f26c610038bc86df20405d87051f64d09c60e` | 1.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_dtc_find_643d4.c` | `9a18fab798e37ca4ff7ab86b274719610bcca4e64f01052f1331538fa6c535b3` | 3.4K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_dtc_find_6443e.c` | `47f4dcc0422ff8d75c1b14fbaa637ec54cb9a54bb20b88f944011ed6e21fe88d` | 4.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_dtc_row_update_64258.c` | `cd02d37e886b8b1c45b04583283415bfb94c828d59b047fccaf85d0f1ea63ce3` | 3.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_dtc_row_update_64418.c` | `b5f3f21407384ee554dde7801e2e581d2fc7217dc66d2dcf0f0bc2cab7ee9f9b` | 3.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_dtc_row_update_64490.c` | `71b87fde53654a204f545436b5c336680f28a1596388fa7d92e2bf8ef86506f2` | 3.4K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_service_handler_632d6.c` | `6bc28609f82de0ba7fa77b8630132d5a8b331632cf74cb7e205c94ce86685ff3` | 2.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_service_handler_63312.c` | `d72469eb3af3608a7a6234b35a747ae80386749d9e25f62c191791bb4818f848` | 2.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_service_handler_63834.c` | `494dbc97c00c0da4c5bf615e1e116beebe39ba7a382d7495a741fa2c470df295` | 3.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_service_handler_63b46.c` | `7ab878330b441ec35e076c08ca1660190abe4f8150122d0a4236baeaaf6f4cf3` | 3.4K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_obd_service_handler_648b4.c` | `e52b70c3b31fda887a094a6620a3872b85e405907d42c92a2cf224817461f894` | 2.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_omp_rotor_overshoot_detector.c` | `b50333dfb7d6501fb60bbc63220b410b43d590eb99ffe5a1a6da979c9ed1de49` | 7.4K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_omp_stepper_waveform_driver.c` | `f20a80bfbbab205227553b99144e525372725f5bab82b9da63f87ad15404d8ea` | 6.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_omp_task_0x1825E.c` | `d815f976f8e1c41e3b965157fcd30725d8c4a227583f822f4cb4ae7f495331b7` | 27.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_omp_waveform_state_machine_18860.c` | `ac455288f2300bd214872c7377e0d8e1e26276c45255c8fe1b637e03dca98901` | 15.0K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_os_task_scheduler.c` | `0b80a21577640cf0f3609f8affe9f098305be50f298cd6f89295cb840cb3af37` | 9.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_purge_control_state_update.c` | `2c4ebeecfb51b1fa74bd918c95f3cd4af68d4a4e2a4e4b758c8ba404c4d02352` | 5.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_purge_flow_counter_init.c` | `34b93a66fc1f5431dbd5dd2ee913c13c69824935a791b8ddf269c10a36da9ef2` | 3.3K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_purge_flow_decrement.c` | `b5d65146f976ef7eafe650d59a22fa275b4cbfc092286669129f61040b36b4d8` | 2.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_purge_state_query.c` | `d20f3e6ecb53ebabf5f52844bbe23e3ecac3ff41b485d52c2d6057d2c5fefe6e` | 2.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_radiator_fan_relay_write.c` | `6493153267e59c9af64d8fc34cc22e237790cd9fd3388e39321c09b4ceb01829` | 2.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_req_queue_69602.c` | `486ecd26545b918d509021a738dc71005887e90e85b7c5fdb349f292a110954a` | 3.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_reset_handler.c` | `7a04df4f6dd3a79596b75951dbf886ca5544f0a005aecc6afd4469eb6514ef75` | 9.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_rev_limit_fuel_cut_init.c` | `02a8c27c8c0784b57bfca0a096e49a5c9cdc2b2ee6be591b3b71ee8efbf9e0cf` | 4.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_rotor_sync_position_detector.c` | `42e4d8b5c8e9cbbc9e87d45c6f25743743368bfdab4d86672a5c68ba5ba35390` | 12.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_saturate.c` | `71a19a5d9bf2767533ddb266ca2d31d5ff5ca0805446ad2eb10e0ffb959929e0` | 1.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_saturate_low.c` | `734f42d4c4febefc613a2ebf43ca6026e7c00379ef0cbb52bb2a26beeffd0528` | 1.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_set_immo_light.c` | `4504e7f8cff3e7d93dca5926183c420b6d3763952abf40c01afc872ca6e4d211` | 2.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_set_mem_inside_func_to1.c` | `f5dd08b7826c7602d0ed5cc8e79d5c42661adf518a8f670f6c0206636af2a398` | 2.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_set_memory_not_valid2.c` | `e7655aea439bc9eba920eded71ead7b949d112fa7c0ba14f34bae2ed07eb5615` | 3.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_set_register_reg_bit_val.c` | `31f166096e611fe482ab88dfa5be1983fc9209976fdd7f20aa1fc67dd9dcbb2a` | 3.3K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_set_sr.c` | `d70ad203267ed654fc1b1d638af3cbcaae2e17e2fece7a199711d5af477ca2f7` | 1.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_set_sr_param.c` | `f82eddb937a5d7d98cf7a1af706351a11e2ab3b889752e0d2152dc6d7b2525c4` | 1.9K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_shift_left_logical.c` | `908439b431bdb90a832fd611332e324af528c978394bdb5d469eb0817cb529d9` | 1.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_shift_right_8.c` | `add053ae8b35b298a5f41b44eb1847687e80070bd561b75e1c94006bae186988` | 1.2K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_shift_right_arithmetic.c` | `7b629ad9a5cfb57a35418f88d53a0a4235b4b05a20eec21a79bf72450adf53c0` | 1.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_shift_right_logical.c` | `12c985ab9d1f835cb11746964246dff812d892a307fcacc5454fcd859141dc55` | 1.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_ssv_control.c` | `7aa1415019cd82dfb02832996db0a38b6b6bc454a95709d7b02e0cb073d2ded5` | 9.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_subtract_absolute.c` | `1030a7ad61f10bed7d24a1a874d71c69976675c372d5bbaaf2005a2c6c58a42a` | 1.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_task_end_routine.c` | `d7f37b1458eebb02e7fd12004d905cd0aa9bc0521cac88b373bfe1803f98ee16` | 6.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_task_execute_by_index.c` | `74cef7ea5828b26eeb681b21142c513ec207387cd3e923a6185b82b15bf6905d` | 8.5K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_task_flag_run_c.c` | `4a09f3de21955f028ca759ef2afc23bb8d010644ed3095942ca47307c880661a` | 3.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_task_full_context_save.c` | `b5247f41cbc50fab5d4c373a86eaf18179387c0945d7411e334efff4ed8b2331` | 4.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_temperature_gauge_5aa5c.c` | `8dce302de8ac0ed3ef4bd7754f6ce4d608d51afa1c642b7a8a3142303151605e` | 2.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_vehicle_speed_sensor.c` | `727918eaedf3560cde748cb0a28a4ec55ef16d182eb2c05b56514dda661304b4` | 5.1K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_vfad_control_35bbc.c` | `90c1679ef570d0e776a9bb31227f087ddf69abdc5f6712fc3ae80fd3c5c2b344` | 5.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_vis_intake_control.c` | `709818e8f2eb9fece967f5693c84fce25e4c206e639ac032c63a1c5507558f13` | 9.6K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_wankel_leading_trailing_split_487dc.c` | `8c1c57b9612eec34a898cd4f7c8db9de0dd6c77062b0098fa2fac512ae17181b` | 6.8K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_warning_light_5aade.c` | `5addc8a58a8f97a07ae56a3f311a88d6e600ab9dcd2ae2948fddea553f8d46df` | 2.7K | Host oracle for sample harness |
| `reconstructed/samples/tests/oracle_write_to_e2_ram_area.c` | `2c9645ce96ba4d5060208a6e57548e5b7b9d207a133ebdc269d76d98785b1d20` | 5.3K | Host oracle for sample harness |
| `reconstructed/samples/tests/run_all_verify.py` | `0b091da123c70675e81e8fadfe7ee074e5dfa915f9da42a306eb5d61f21fae87` | 16.1K | Tracked file |
| `reconstructed/samples/tests/style_audit.md` | `6d423888b0ec4876834146425525575b905399f3ae9c71b2961ed55906e418c1` | 6.7K | Tracked file |
| `reconstructed/samples/tests/verify_10A88.py` | `0bab62e3fc6f0b507b4af35db2dbdc5a18bb9c87e57d210ee3a869066b948ab6` | 10.1K | Tracked file |
| `reconstructed/samples/tests/verify_bitfield.py` | `b2f95644bbb15180934de1ac1605dde1ccffd03d1f5041ed4f0f193188311915` | 13.2K | Tracked file |
| `reconstructed/samples/tests/verify_bytepack.py` | `9696dfa5f5d708ac14224f234bf9a4260e083f4fd2e8e561dc8f5a5b98a48398` | 17.8K | Tracked file |
| `reconstructed/samples/tests/verify_checksum.py` | `11f722687e7c6d25c6619aec0bb9363b93153cb6875ad6d52db55a04f7cddbd4` | 13.0K | Tracked file |
| `reconstructed/samples/tests/verify_complement_exhaustive.py` | `06a2517ee3ae710861e087955c65a8375bceaac382ce1929ca35b0208ec1b2c4` | 19.8K | Tracked file |
| `reconstructed/samples/tests/verify_cross_rom.py` | `42ba96392b332a191fa2da2a037ca9846f40ca7aa80e0fbb66db5d15f817d441` | 26.8K | Tracked file |
| `reconstructed/samples/tests/verify_datalookup.py` | `ff1d4dcc04991f3ba4fb1169a37f45bf03dcf04bd8d410fd5d1251738e11493d` | 13.4K | Tracked file |
| `reconstructed/samples/tests/verify_delayloop.py` | `7d1a4bfd579d597afbce764a09c3c37d55be4de2a1fd0d0aecaa6f7b0dcebca0` | 14.1K | Tracked file |
| `reconstructed/samples/tests/verify_firstorder.py` | `a43b40c769c797f0dc965502413c1b85534134d36b3693b72446d860b8da396d` | 21.6K | Tracked file |
| `reconstructed/samples/tests/verify_float_a.py` | `b6331419ab9fd315df8aeab456e79022eaf283f3dac04f743d2f62deecaf76f8` | 16.2K | Tracked file |
| `reconstructed/samples/tests/verify_float_b.py` | `29d2380d2c4781b15c14afbf20951c7f726cc8bf55a8f5c89d8308153a99c700` | 25.2K | Tracked file |
| `reconstructed/samples/tests/verify_float_fp16.py` | `66d1223ffd7647bfa94b0668a22a725c4548d1c20e0a02f51200268866e7a268` | 16.9K | Tracked file |
| `reconstructed/samples/tests/verify_gcc346.py` | `15f1b1ae5eedbb9f8dcf41a560ae7a652dee0cbba4ef0893027945fb00b75d5c` | 29.5K | Tracked file |
| `reconstructed/samples/tests/verify_gcc346_fast.py` | `3e7ea8b3260885dbdbcf5343ddb7bd1781a5dfce2af757171eb2ee1362dbe65d` | 26.3K | Tracked file |
| `reconstructed/samples/tests/verify_idxtable_all.py` | `145da5ec91da9374ed2da0f754618ca9038af0662776aae8017dc5544456a7ff` | 15.9K | Tracked file |
| `reconstructed/samples/tests/verify_immo_exhaustive.py` | `ab8b673845296c0e654bbe5c4fc92c49e22263fee9b989ce062c7eca971c19bc` | 12.9K | Tracked file |
| `reconstructed/samples/tests/verify_interp16.py` | `d4dba468fb522ab029b3f818d554aa84bfc5b51a16447dc8da9d87f01330e6aa` | 13.1K | Tracked file |
| `reconstructed/samples/tests/verify_interp8.py` | `57a2ca25fff3a0db1460c8652f2f4032b9ae7f93dd67dfc6730cac7d53bc9a05` | 13.0K | Tracked file |
| `reconstructed/samples/tests/verify_interp_f32.py` | `307183823110608efb1115adfba3a59d19d61daf622294968480f859348d9e37` | 13.2K | Tracked file |
| `reconstructed/samples/tests/verify_interp_s16.py` | `6c022c7b4d020b60a13ffd1b2c6e0d3c45d9d96a629e074043d6f60b904bc9c1` | 16.5K | Tracked file |
| `reconstructed/samples/tests/verify_interp_s8.py` | `d0bbd2eb0804049dbb519a59654862a797d6667d565501da203deab7f182d064` | 18.4K | Tracked file |
| `reconstructed/samples/tests/verify_invert8.py` | `603f30e062b57f5ba095916a1a6ccf168fea9c8f58b32bdcc96cd25ed2d0402d` | 14.6K | Tracked file |
| `reconstructed/samples/tests/verify_mathprims.py` | `91f125efdc1acd00f3f259dbe7c11e80850b1739ee5da7e87ee41bf4aceeeb03` | 16.4K | Tracked file |
| `reconstructed/samples/tests/verify_memcpy.py` | `b63d94709ca919d9749da0d4e6270cf3898f087b7492d374c1929139e116ab10` | 17.9K | Tracked file |
| `reconstructed/samples/tests/verify_mod32.py` | `a2e30cc245c4d24d907f51fa52835e6b58912d934b702c6744efb2287eaccd2e` | 13.3K | Tracked file |
| `reconstructed/samples/tests/verify_q4740.py` | `329b1c41771fa5dba58802ee1a5bd2b02d97440a0d8b4c003cae401bfc318fbd` | 12.6K | Tracked file |
| `reconstructed/samples/tests/verify_saturates2.py` | `a2ce085df10269fdd803225abe8ae30fdba6be0c4b179f4a3a9b26ca73e31abd` | 22.2K | Tracked file |
| `reconstructed/samples/tests/verify_setregbit.py` | `a1fa9d20a836f72135ee210d6fb5f5190293b7a23a6658a66e66d49974d19534` | 15.5K | Tracked file |
| `reconstructed/samples/tests/verify_shifts2.py` | `f348935997f1e96b827d45097dd252127419b7476f0d1c17157a0e50bcc83dea` | 13.0K | Tracked file |

