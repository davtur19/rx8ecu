# MANIFEST — RX-8 ECU reverse-engineering public release

Every file shipped in this repository, with sha256, size, purpose, and its source path
in the working repository. **1270 entries, 64.0M.** Regenerated 2026-08-02 for the
9-ROM public tree (the 10th stock ROM [REDACTED] and all modified images are private;
see roms/ROMS.md).

## Summary

| Area | Files | Bytes |
|------|------:|------:|
| (root) | 11 | 298.1K |
| roms/ | 10 | 4.5M |
| src/ | 10 | 39.7M |
| symbols/ | 15 | 3.0M |
| c/ | 180 | 785.5K |
| c/tests/ | 220 | 1.1M |
| tools/ | 21 | 172.7K |
| tools/tests/ | 2 | 37.0K |
| docs/ | 223 | 1.0M |
| hardware/ | 1 | 2.0K |
| web/ | 11 | 872.0K |
| analysis/ | 31 | 9.2M |
| .github/ | 5 | 16.0K |
| reconstructed/experiments/match/ | 66 | 215.5K |
| reconstructed/samples/ | 464 | 3.3M |
| **Total** | **1270** | 64.0M |

## External dependencies

The repo is self-contained except for:

| Dependency | Version | Notes |
|------------|---------|-------|
| Python 3 | >= 3.8 (tested 3.14) | `python3` on PATH |
| capstone | >= 5.0 | `python3 -m pip install capstone --break-system-packages` (SH-2 disassembly) |
| sh-elf binutils | 2.46 | SHIPPED at `tools/toolchain/usr/bin`; re-install via `./tools/get_toolchain.sh` |
| cc (host C compiler) | any | only for `make c-test` (host-side tests) |

No other runtime dependencies. The repo does NOT ship: the 10th stock ROM ([REDACTED]),
modified/tuned images, Ghidra/IDA projects (`.gar`, `.i64`), [REDACTED]/[REDACTED]
binaries, the toolchain source, or the toolchain install (git-ignored; re-create with
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
| `AGENTS.md` | `34f16fac1eb27fb80d6b0be12c4dd60ddb832ac8b6b49d1d451c25951c6dbf7c` | 3.6K | Agent working instructions |
| `CREDITS.md` | `53eff7a1f681da319782995f931cab2c48a800deffc12deb6b933a27acee987a` | 4.7K | Credits: equinox311 + defs source attribution |
| `LICENSE` | `d8a6cc31abc16b6748c7a21f21611f5a1ec33f67d22ca23d7da1c19b95496bee` | 33.2K | License (GNU AGPL v3) |
| `MANIFEST.md` | `--` | -- | This inventory (self-referential; verify with `sha256sum MANIFEST.md`) |
| `Makefile` | `d4a3a6a3c2e7be21bc55a5fe490d13d13f20a2f6ebee25aab0ab1724e118ff22` | 5.6K | Build: verify-all / verify / src / c-test / c-emu / clean |
| `PLANS.md` | `ae3967fa9a888bd32108208a4949514b17ab9c843b015e4b4bf2b0b46f5ed874` | 9.8K | Master plan (single source of truth) |
| `README.md` | `3ca9457dc813ef5475cc3c9ca4e18539875a8c46610e6d6e73d43221022ac0c1` | 10.5K | Project README |
| `REPLICATION.md` | `297ed322e7c61a9cf50896b3591b42dc6d159973afb4faa9832fdf5aaf1055dc` | 10.1K | Fresh-clone reproduction guide |
| `VERIFICATION.md` | `3b98bf7d96d1cf2531e3d13d017daf8ad007574fb8ae87813a8ce5acaff4b1e5` | 10.1K | Evidence: byte-exact table, coverage, test results, hashes |

## roms

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `roms/ROMS.md` | `4ce41b55b887cb166495e4c8958170c4c8749e3a9054253c9beada92bb506116` | 7.3K | ROM catalog: cal IDs, SW modules, keys, checksums, hashes |
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
| `src/60E0E500_annotated.s` | `174966f7fc4d0d44b74d8c49402871c0dbe56b939c8168c7c89929d85c491f47` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E0E700_N3YLEE_annotated.s` | `1c53010160f741357ef05e7967a2b16b949c1a99616055633df3031b8e37bf98` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E0FB00_annotated.s` | `002bd330e9673575076786c44bc292baeb3e13e6e1c5d78cd1bf6a0ca68d1e75` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E0FC00_annotated.s` | `648e5ff544a1ee37e3c1dfa17accd9df6218b94944215fabd8fc6342f2865a3d` | 4.2M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E15120_N3J1E_annotated.s` | `598a4afd96f633661f19f3a8a05ad945f5878b448a7cee0bc7f05ee5efb43627` | 4.5M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E1B900_annotated.s` | `a234fd0500df0bbf9039b276d99855d607a33b53d80f319c46554ff27f0b0478` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E1C500_N3J6EB_annotated.s` | `d298fcaa90bb461a00368c1bf1a0fb94c813c3947a9fc56519bfafd41cc23081` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E1D400_annotated.s` | `c56a5317e8ec3feba848991a2e7a7a80846d932eabea4ece19ea7bde630ac3da` | 4.3M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/60E32000_N3M5E_annotated.s` | `e0cf2a5d350aee6c39937b14fc336754ebc982e76c9e905d09422a3c8cae8873` | 4.4M | Annotated, reassemblable source (byte-exact rebuildable) |
| `src/ANNOTATED_SOURCES.md` | `a867f9f0fe0ee722d90fc6f40ab4cde6365e86addee97f88710ae1850f03f1e9` | 3.6K | Per-ROM annotated-source notes (coverage, symbols, rebuildability) |

## symbols

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `symbols/NAMES_STATUS.md` | `fdf436ef4ac075efaf76066fd4f32347cc21534919f613f6a74104535963e90e` | 3.6K | Tracked file |
| `symbols/cal_tables.csv` | `846b969d058f8d5b5c8f28d292977a8fb2cf30651f7de36a3dd977290d8da880` | 52.6K | Calibration table descriptors (1,210 tables) |
| `symbols/callgraph.csv` | `ec636769141c7a42b666ecbc72e0342c7f08d9244ea97ecb18b76b45366e211e` | 362.9K | Call-graph edge list (caller->callee) |
| `symbols/symbols_60E0E500.csv` | `781b93c4709b708fb4992b521e634508a59528e543ead7f843370cfe7a8c5226` | 283.4K | Tracked file |
| `symbols/symbols_60E0E700.csv` | `74c0d8c0f9562c1f9cb13cb8011d2c46d1659f67befca38d82b8ce714afc0560` | 283.5K | Tracked file |
| `symbols/symbols_60E0FB00.csv` | `f2ee37ca39ece163044080556a2d8e0fce52f1c858ed21f39bda83771074ce15` | 279.7K | Tracked file |
| `symbols/symbols_60E0FC00.csv` | `a1d0ceea0cae79bfe42ec890d492d02383605decaf1c9ea5a47758516f592bd5` | 156.8K | Function symbol table (per-ROM) |
| `symbols/symbols_60E0FC00_ghidra.csv` | `af985c30f6a05dce6891d962edc8976bda234b55b8235c673e7b9742e5f605aa` | 38.7K | Function symbol table (per-ROM) |
| `symbols/symbols_60E0FC00_merged2.csv` | `1afd354dea0abc3d8614ef7fdd04da540e3a937e0711668a0fc0e5a9fd102934` | 166.6K | Tracked file |
| `symbols/symbols_60E15120.csv` | `c6800b5c929c68cd4ee76810d6e4a047e4b0935b7a776be4a54116c74d2e8c36` | 289.3K | Tracked file |
| `symbols/symbols_60E1B900.csv` | `d11a902aaa6b6099e72abc2b016f6d0d633992fdbc65d3a239497fd3a3922c74` | 278.7K | Tracked file |
| `symbols/symbols_60E1C500.csv` | `ffc00f7a6c870232c90d7e51577fb8cae5e352ac7acc0a28c77983449007d400` | 283.8K | Tracked file |
| `symbols/symbols_60E1D400_ida.csv` | `be273edc53051230dbab96bdf1880ea1b343e6491821207f2aab6fb7e97f0120` | 140.4K | Function symbol table (per-ROM) |
| `symbols/symbols_60E1D400_merged.csv` | `6c6b02df15e7750aacc82c8511aa33269ab4fc3c850ad25912343b29558b2483` | 142.0K | Function symbol table (per-ROM) |
| `symbols/symbols_60E32000.csv` | `31e41579bde56ba955ce61ce14f41dc4ea4ae66691dbf74825a9a55b7186a585` | 267.1K | Tracked file |

## c

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `c/2DLookup.c` | `77ec8562352bd30232b3d660e03badd06c7018b31f2e4c1772f20e2cd8583ac7` | 10.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/3dLookup.c` | `02b55cb88a5111fb69096314f4c84f546f11209677c95c1a35679fb9ccbfbe5b` | 9.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/CANSetupSomethingDifferentBasedOnBit.c` | `0bff14b29e51727cdc74a48c50c51b805a7db45b0d14325b8122901afb72544e` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/E2IntoRAM.c` | `fc2325f82277d914cfd53b7c2e00bc462978406b163aaf722698c724356766e5` | 4.1K | Verified C lift (behavior-equivalent, emulator-proven) |
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
| `c/README.md` | `8f82bc75f44cc86761399207d12bd861051980549dfe0637822ecf3c24fd31ac` | 12.1K | Directory README |
| `c/SetMemoryNotValid2.c` | `76d4d68b7a3753a832ed4437056d867f137cf48c4ef6057d6e3f7a0e006741c2` | 685B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/add16bitSaturate.c` | `d4e7bf36c79bc71bcbddffbbdfb7ae9f40cf8fa8da5914f90d3e251ad71d7326` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/addS32Saturate.c` | `294f2cc7fa810278f4c14083afd0b103c4d54fa969277a1a39d815bedaaabec7` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/addSaturate8Bit.c` | `38d9c81a05e112187b4534c36f9de3927e4ab0a5726235cd26502b6bfa522e44` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/air_charge_calc_0x19190.c` | `f0810b62e2401fa3c41977484041e5e12f2a7b02d87bfe65d92aaa0ba13a657d` | 4.4K | Tracked file |
| `c/alternating_sensor_sm_5D34C.c` | `4e665258bd1ee20449884717e1a47c444c930bf18ce3945a694dee0a1c9b3674` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/atu2_edge_capture_config_6F3A.c` | `6a112d5f1755d848bdd5f37f5df88d75b727f14abd87562ecebf301572f49ae1` | 2.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/atu_fpu_control_wrapper.c` | `37355cb7ffad034546299758572983a814c83daae3ee519cac8d25f59af77f82` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/baro_sensor_value.c` | `ff3fb8099c49013535c2c72a2cd9be211b2643580a487ebdf14570efcebc2e70` | 6.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/battery_voltage_monitor.c` | `d00b0acd0047ed09d82fb526f281dc1e9ab6401f4a957e3eab19d9276b1c9171` | 6.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/bitfield_extract_merge.c` | `df0b0a792955cfd245162565923668420b34385bed9395188d7c96e878b7e4ac` | 6.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/bitfield_flag_selector_33A98.c` | `89f93793393717a0797dd2e113158c2278deda73a3a8a8fbda4a38154715477b` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/bitfield_flag_status_decoder_339AC.c` | `36a71e37aa8696a59863678823ddfb348d4c92e855ec491e23d10e296535d5b0` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/boot_entry.c` | `643537e3709d2682e083a6367fa9f5f55268a0db2069a84aaa4d0b09ef70bd25` | 8.3K | Verified C lift (behavior-equivalent, emulator-proven) |
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
| `c/calc_rotor_sync_idle_gate_B.c` | `278b71ed6ed92a40f55f5bb47cf4c541f3941cc4fdad0a4deaea82936c3c374b` | 3.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calc_secondary_o2_trim_1321C.c` | `3a230ed756a0565097405ca0cd173501a4a7f03b9b69c51c2298146cbe4235aa` | 13.2K | Tracked file |
| `c/calc_spark_advance_0x1237C.c` | `309abdd99b182d42ccfd5bd1115beeb184611e2249aba986584f5faa2ef03044` | 8.3K | Tracked file |
| `c/calc_spark_lead_trail_split_19220.c` | `325eeef22b0a10b48844808a6e51127352abb403688c349b7175aa4994ea0433` | 7.5K | Tracked file |
| `c/calculateImmoSeed.c` | `d95e3de7fafe4260043f271b62314cc3e9d4f114db2c8334df15b3860131792a` | 3.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calibration_apply_4B770.c` | `736812f9567e9b8b55aa18ba89faae9fddaa50fc55a6f7155c41984b227803f7` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/calledLots.c` | `219e9669d41e8fa52334b9e063c1e917baac6354243e5a3d9aee3bf993106eee` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/canSetup.c` | `6850cad9a360bfb7b39a7b63fd48a3509f4efad4024a8553673166809d1823ca` | 2.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/can_encode_handler_62ABC.c` | `8d41ea208495da6d0b7e7e42079c5617446e86d9ebf49315591b8b9f8d2fb7e5` | 4.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/can_uds_subsystem.c` | `525b841b5a55c78ac2c05753b978e9ba9a2346df21cc98161b76cdbc3f82cb72` | 29.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/checkFloatValidity.c` | `8afd2a5c12525ef9f9240031b77b7278cb944b04a933a451a5ca464706366cbe` | 1.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/checkImmoStatus.c` | `6bdc74ddb0e547941fd67a835cc316971736c4bdc1e2e654bb675f0f9c5d9c8b` | 3.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/checksum_complement_add.c` | `ab9f6cf6f4100417b7c6f14a00264014dbd3020623d8914f73b439921369d879` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/coil_correction_write_0x50A54.c` | `a64fe38f2b119ad423af6576a152fd76b8c2be09246a734b00e202a1f2471888` | 6.4K | Tracked file |
| `c/complement_shift_u16.c` | `d08537d7987746e4a32ca48d3c15563abdc498686f0fb747c97e54203a0728fe` | 1.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/complement_shift_u32.c` | `261313ada94710047619cb38d323f3fdf68b634d6cc56b511a56cef37dc0ccbd` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/consistencyCheck.c` | `17c2cface615473c0271b529438a7034dd418e0aac18068b99420802cdd977bc` | 5.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/coolant_temperature_sensor.c` | `f6b72e59f2c0b47290cf23b13976b09d3a01d61cba6f1319edfabd57632d39cc` | 8.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/cooling_fan_control.c` | `39f416f7bd45533adcc26c75b58e093798c57d91609ea7b0de9289b89ddfd651` | 2.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/crankSensorInit.c` | `5893d231c7bcdcc9a9913412da43f1c8047a6997669ae3273652530804bf3087` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/delay_loop_n8.c` | `7310a5823dbd90c6e8c86d111e26098331723e57eee8e692edeb27dfa97f0544` | 1.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/div32_signed.c` | `6babcde5cf39727ee7de552e26cb017f914057d31da026e6867d300196cb8727` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/div32_unsigned.c` | `375556a81fe66996a77f2ad06858ba38f5b875f04ef638ac008db2b72d2d4007` | 1.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtcRelated.c` | `76403b0f909ab0e55ba19510570a88194fedd91cdae823153c82ed2755495669` | 3.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_code_set.c` | `c599bb707eb0cc56a2f33dde719a40fb9775cef22f8f35d628080fddcfc0d323` | 2.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_data_read_60F58.c` | `117f607f28ff86f7f9da59cfa10a9a57646410e668f27463bbcb94bc66e1e7e2` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_debounce_monitor_43760.c` | `9a662f2dc94218fc2650fca4ef08663bc6900a99ac0f981c1a5455c8bb6257c3` | 5.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_handler_610FA.c` | `103137e640d38df9b5c7801d371f52128c6e2119eee1d658cc336b9a32506c19` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dtc_handler_61550.c` | `f72a23bfa6305e94fac52a6728e3e72160f734e605f42ca3fd8750f058195a16` | 4.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/dual_cellbank_selector_58C4A.c` | `e1be147a3930fe15fbe140451ba98bb36172d9d85655ce4373c7b6701142a0a2` | 4.7K | Tracked file |
| `c/eeprom_commit_dispatcher_37000.c` | `f47bd9b12d35079b013f35c707903c5a47a3fabba577d19d66fb958a4dc5ae6c` | 2.6K | Tracked file |
| `c/eeprom_immo.h` | `fc8de3e9aeab9b3bee289b34720a62b5baba90053da26ecfc06dcd51ec72ef19` | 10.0K | EEPROM/immobilizer shared definitions |
| `c/enableDisableCruiseControl.c` | `e479adc91e677d7a4018dc7a630b2b0e853eb9a5021f4a06c29aaba5e37c51ee` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/engineControlCalculateTiming.c` | `7f88526b869a77edf6e73cb6a27a0b29d2ee81fc40f086843368722e58d7be09` | 12.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/engine_load_estimator_0x190A6.c` | `5b3df13c0a8d9ab5ba0a976f00da9022c89b5dad89d707f6b8833cbbc86809a2` | 3.7K | Tracked file |
| `c/exhaust_oxygen_control_19480.c` | `e85d735aae024c88d32de83c74671e85841da675460c66d44110fb2ba3be30b0` | 19.6K | Tracked file |
| `c/firstOrderFilter.c` | `edd2ae05d9b1f0c565eb731011eb8959375d59f189e61b27582f46c63f70202f` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/flag_setter_49ED0.c` | `b666884cf13f385e0471b743366017d3b3f0cc135ee60f447530617345e3b08e` | 1.8K | Tracked file |
| `c/fuelingInit.c` | `7b4b61867c4dc4a5cf675a6e54a7449c40704827876313082bf1f85398114579` | 2.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/getACSwitchStatus.c` | `5e09f56f44c1688b5e24cb5590c40c9c7cc3494159e252231e90bba3e34580be` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
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
| `c/get_ignition_dwell_time_0x94C8.c` | `31f5c877578432cf721defc049bd73736f09515d9283fc0e0d510bb74a20da6e` | 3.1K | Tracked file |
| `c/iat_sensor.c` | `2b38a3f53e197fc69bc178e4048d3125128ce406c4a0dd39a912da012468f65e` | 4.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/idle_speed_control_18054.c` | `876c632f79755f636a80f3215b0ff67fec039626cafd620068c394b72391cbea` | 5.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/idx_table_helpers_68780.c` | `4d650cab21eb9defb03303391062a7cb0101b411bc360b6007ff7f15a4c62fff` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/ignitionDwellOutputInit.c` | `274bffc2616fe66194bea1f3439360c9f71fc839a83a359e9ba704d3fa9d116e` | 3.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/init_main.c` | `ca43f886a219c0e38127b327f94e49bd71601c82d322fc50892f82efb43aed58` | 8.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/interp_leaves.c` | `55d65a25e37087eefd642a67e153930b88ca62f53f6b6fca89ad77e008a458ed` | 3.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knockFunctionInit.c` | `5cfe866de396903775202a0d34d2a0341577eee848b38ba8b123e3ae9f9df183` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knockRelatedInit.c` | `3e07458d0d3609abb33b07a02bc586df1505105945b22e337cdcbf026292e5ec` | 4.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knockSensorADCFault.c` | `0e2da1ebe60ff44a0428f7778b02e5a96e6204e055a3278aedb8b96c6daab5c8` | 2.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knock_sensor_adc_fault.c` | `8d037a428d3955462521faadc1e1576b6cd205bde687259c80ffc5257c00b453` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/knock_sensor_adc_read.c` | `e81623961937d2a72ebc794247a9644c268be64c1e27458c91eed71c5452f0ea` | 3.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/limitKnockRetardMax_ConditionalRPM.c` | `0cd5ecce7b0dcf470bbb23ea98cb4b8ad5ecddd460a443581d56742076f1a920` | 2.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/loadDatafromE2intoRAM.c` | `688e09298a8445190ada3ce00f18398defef7db140b9c99e305e9fc084a8d510` | 590B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/loadStatusRegister_ADDR.c` | `726a3760492a53116a9d8f7a7e27110de3781958acdac71f5a020ab227fed3f8` | 1.3K | Tracked file |
| `c/load_blend_factor_limiter_0x16A30.c` | `60394fc6bfa3f770271e7b8d2dcfb1953e65b9268e9c7c043b53add82fb69800` | 4.1K | Tracked file |
| `c/maf_sensor_value.c` | `3bd3e1fed9a16b04a2eee0addf587e1b09003d62305c3139dbe354e0b74bdaa5` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/math_primitives.c` | `ac23154160b5454176d1808fc2102cb2aa3680d71964fc9711f3da61fcd8ca23` | 7.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/mem_accessors.c` | `196f29a5ea06867bc8256145e622bb1057c162f9d745c46ebd2cbf354328b8a9` | 10.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/memcpy_bytewise_unroll4.c` | `8789bba66067458af6789c3e51373bf6c9ec37f5d08e88b124156542220a630f` | 2.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/memory_match_accumulate_583E4.c` | `e0fd57cbfb174131c7b3312f23d6e22375f326536ddfd1aef939f0e300e0a7af` | 2.3K | Tracked file |
| `c/mod32_signed.c` | `3d0316e52b698213254aebc75b33ea781161e70f8eeebd2395bcd9233f252300` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/nop_delay_40cycles.c` | `3775f576e0cd7224939f6cf1874adbabb933a9cfe6e133a9205391204634418d` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/o2_lambda_subsystem.c` | `02461ce0b22af16769260407168e4a9f417edab653baa18f9b5a381ceb4d8139` | 19.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_find_0x643D4.c` | `a0dbd20161d73e800594b6fe85b60deda82d9792d7152416b187c79623c95a3b` | 1.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_find_0x6443E.c` | `b4011cb48b50f383ddde201117cfc75519545bf5954299497f34e76480ed6b2a` | 1.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_row_update_0x64258.c` | `9c89c83708f8aaf38336bdf14d6e87659021432998cd28ea35d4bf3abc5633d4` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_row_update_0x64418.c` | `fa8398cb1172d3e108eee48ce118ce81133978c5e1d82df460b94d26f1ae8e5f` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_dtc_row_update_0x64490.c` | `bc397ebc85b240cadac142d1a3f779c5d13b79270604a9d4e420f8377d7ca98e` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_pid_handlers.c` | `c7392d15fe1bc497d65301f33c250d0f0cc259322e35a0884eb73033642f01d6` | 22.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_632D6.c` | `8bb1f2a90962217f21bc83c7d47621c7eee72607c6410b0d9caf4dde391ccd49` | 2.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_63312.c` | `8b570f8b33fdbe0bd93a10bc887704fbe8b240f70b2efe0f5508f8374a20c88a` | 2.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_63834.c` | `d8821d6af3eaad43b9606a2a20ef24604c27bc4561899ae38dfd58d9c5df8ca0` | 3.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_63B46.c` | `902a4ee6963a1ff37fe2a4d0ebefbf086d9ff07d4a9022c26e50bb4fe03362d1` | 2.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/obd_service_handler_648B4.c` | `2ee267d0a5479238cfa9931b9acaa5b6c946987895729c29cbdabc3b896f1aeb` | 3.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/omp_control_task_1825E.c` | `0fdddbd091ef4877dd3a4e4d24227b1c87b733b157f6b84d5c5de165c2a2b733` | 9.6K | Tracked file |
| `c/omp_rotor_overshoot_detector_18CC0.c` | `4812b056e063b3d134efb4dc64146c89509f6312e17c9a287ce11db573564e0b` | 5.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/omp_stepper_waveform_driver.c` | `3c75ace88ff2b8bd629b5e370fee178af8a86c78d7a5e9c0d9984fdb23cc0fc0` | 7.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/omp_waveform_state_machine_18860.c` | `a51fe8e9a2dbe91b0cb7948d81573c84db60c189baa5b57a153797403d09a7ea` | 5.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/osTaskScheduler.c` | `486d9335110f5007c5716bf4f914e25bbb75c504a8952558ce099347a0c4b645` | 9.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/output_per_rotor_ignition_dwell_0x11218.c` | `3bc7f0e08a0196c89602f627110403b8b7e50809acf98aa9383959107ee09c8a` | 2.9K | Tracked file |
| `c/output_spark_0x8DAE.c` | `a319a64d44e899a7c827f983a53e045b7b2ac91eac51980e4677ae169c3856c0` | 3.9K | Tracked file |
| `c/pressure_delta_monitor_1AED2.c` | `db4aa24ae09e6e94a48820977e72a9c4855635cec8313f1dc61f5547b1cb4f68` | 4.6K | Tracked file |
| `c/purge_control_state_update.c` | `39a45cce814b0432cdf229ca74ac5f1e74c3deca55c4a8c6f1c90879d31564ba` | 3.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/purge_flow_counter_init.c` | `39abc3d6f97b2f2e40c495ed575738ef6e2dd070da65eea43d94f1d811451ef8` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/purge_flow_decrement.c` | `f0e11c738461320781f32db5f92782556e72732fb1b8911cf57f689785d06006` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/purge_state_query.c` | `9a8779a2ac2a7f92f03a7c355b1e1151375cc0955e3459d6996bacd1b2d00a73` | 577B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/radiator_fan_relay_write.c` | `0215f20f419235ce40a01cdc4bbf5d2ce98e6b544dfa12f6cff7e4869ed6307d` | 605B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/req_queue_69602.c` | `dd14b521b17e7cc72321b52f3e5024e3cae7091bd5469a9827d513bb7fe9ccc4` | 1.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/reset_handler.c` | `6ebbb32b9219f954c398fc1500fb2b58144c208a572c607da167adb26c079c37` | 14.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/returnDwellTime_fp_0x1120A.c` | `9150fd7d186cacc952b8cbfa3a30df087988709a39a607ab6269f53c5997b594` | 2.3K | Tracked file |
| `c/revLimitFuelCutInit.c` | `c2dec9f1642048d238f76fd048cdb5d09f5e7c2b5a0f2eea5aa656b7ceb275df` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/rotor_sync_gate_state_ctrl_2100A.c` | `777934a51455d3a96617361946d5fae18e23b55d2ebd5d956d74182540a9d002` | 7.5K | Tracked file |
| `c/rotor_sync_position_detector.c` | `6e336c56db4fe7fa60bc9663f81076ddef0d568d7a51727dcd1a3a5246ca73aa` | 5.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/security_access.c` | `dcd1cd48a99e2b6f7fd3ce6dd858af914217cf06769776481471508a4ef29510` | 25.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/seed_mixer.c` | `bf6c0551da52b3c54a1261aac2e0237788178be02b8a6e8d49caa5e14ec41f86` | 1.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/sensor_check_float_bounds_adjust.c` | `73f31aa8f7135098f3e5a70881c4430964ffaf2449c9d3d6d5d3fe679321e771` | 1.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/sentinel_equality_check_5687A.c` | `2c571c5b703e1b06f923c35656f442c654b5bbb8376e3d6593cacaec798679d9` | 1.4K | Tracked file |
| `c/setAlternatorWarningLight.c` | `757b3f95c9e5891ad95a577611bf5169b88ad099b4a90b5de9a7d4742c068a87` | 2.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setImmoCANTXData_369B8.c` | `c3437c996e734351f49f82ceb2138ee633b4170c55f189d1a9465ea6a1e9fb91` | 2.9K | Tracked file |
| `c/setImmoLight.c` | `39ebd4921d163eb210ee2532e60b2210fd59d853bd5a2d544715f5db744aca5b` | 1.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setMemInsideFUNCto1.c` | `8495261806b1e2b8777c12f830292595c18f1594148124130a8a5def8190b1fc` | 585B | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setRegister_REG_BIT_VAL.c` | `6f9dbe798fbc4128ccf0d335a827511e6723c581a50db491bc261b9a75e26664` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setSR.c` | `eae2e3a8936623078a01594ab338c68dff65e26760b33b4505bd55aad8df0ad4` | 4.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/setSR_PARAM.c` | `56bab8d1daad2d01175178ac53e7ec1d3be836bea8543b0f35fd3542b47987b9` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/shift_left_logical_r0.c` | `bf12b8846799ade8d9eb9bc8b10876cdda0576a479b6c50ab615fac0fcc8c893` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/shift_right_8_r0.c` | `f2adae0ba55c8c190f73a867df7403d27cda7ed228db2e23d9a4df2a471b5ffc` | 1.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/shift_right_arithmetic_r0.c` | `3becd54cd021015d718a5d9581e0c5c18f6a43816b2e9cf71bfcc530d375a22c` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/shift_right_logical_r0.c` | `abbd085e7dba393554ecc477f8c3525b3a04566511ec96975b8ffd36fb6b9ea8` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/spark_output_enable_fault_mask_0x10DC8.c` | `a98c696195ce999ae02264f2e5ff4362ba0ea56c83dd3358c32c94d7658ad611` | 5.7K | Tracked file |
| `c/split_selector_decoder_48C12.c` | `e0595630405959c50e4d870b210b8c2caba06d6920c8407a5c2ff7f4bdff490f` | 2.2K | Tracked file |
| `c/split_selector_state_ctrl_487DC.c` | `ecf291ec65c34fe8791fb5f2e59dd621ae4b6839f6e9687b3972adcdbbf3a1e1` | 9.3K | Tracked file |
| `c/ssvControl.c` | `eaebfe5625dcbb77a131165f5ed39c79d245c17ca22750cd14fba398187c8feb` | 3.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/store_knock_learn_buffer.c` | `fbd2aa36fcb7851556b5ed68d141bdbbd2daf6cd6572efe614ac1e9476834c04` | 7.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/taskEndRoutine.c` | `ca28384f97eb730d5e29d1e90431ce0b0d86b4614af7033c33794b6d6db7423d` | 4.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/task_execute_by_index.c` | `a433cad7cc85bce936bdeed450ff31bcb2c9c6659d11ae7628ce98e13cdc3c76` | 6.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/task_flag_run_C.c` | `b3bba6c41b80255a326d45bd486a8a2572f78dd8bf7bd17fb09ad0a65384f70c` | 2.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/task_full_context_save.c` | `bbdac4e17b6fa65e3756aa86b39b95e7ae6c8c9139a6174a7e9d2df3e9bc3e6c` | 3.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/temperature_gauge_0x5AA5C.c` | `b2774efa881d7673fd62c8fd53d94f900c3a2bdbf2121f6b5885afb556864b51` | 1.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/throttle_position_sensor.c` | `2ffa3c218a91536929f2f7a52a34a3173f8b7f22e7acfc278708c34ab17dfe05` | 6.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/updateE2RAMBasedOnInput.c` | `a32f8af00398ecbc22a54f0c7b0a22d2cb05eb34f267a3fd2377a6bf32cd2b0d` | 6.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/vehicle_speed_sensor.c` | `aa7dc9697a545d1423febb11e4546c630a30e7f4f1f2e68f9a35ce589be45cf1` | 5.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/verified_addrs.txt` | `73d43e3f13c3a34403da2c770873fab0e47ed9e39b67ff7b3f45cd1dd450b089` | 16.0K | Verified-address ledger (C lifts proven against emulated ROM) |
| `c/vfad_control_35BBC.c` | `55785deeca85baa930739a07c7e98638d0468d2c87c0e930ea65d387320c9ddd` | 2.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/vis_intake_control.c` | `8adb19bb71f837dad6ca572af015e32ff1190f62e49c80174ec62215432c3095` | 4.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/warning_light_0x5AADE.c` | `af4b45c9a16aaf56d50a067a03e43e7eb475ed5c12acd50609dcb9def7a6f827` | 1.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/whileLoop.c` | `38344098f7dbe1ef25d7c390cb1656d1db54f4569879652713f53a53cd679d19` | 1.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/writeToE2RAMArea.c` | `37a489d2d893d180c5374d426ff643360afb2e0edf47d617ce3ee253e3e38296` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |

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
| `c/tests/test_E2IntoRAM_0x38F58.py` | `08fd4678ec12d96760e02c61ff935ae8e98c6ebf3c3bd90c2d919030aa45273b` | 6.5K | Tracked file |
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
| `c/tests/test_add16bitSaturate.c` | `68dbf734de3d44662fc9cf968627897e61ad0cacb94eb32dd9d088ba08dfdc95` | 2.0K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_add_s32_saturate.py` | `5e72c86880bc7e6c53bb4affdda5f2e45c4122f78f64b360e4f6e25f51f0a71f` | 2.7K | Python per-function behavior-equivalence test |
| `c/tests/test_air_charge_calc_0x19190.py` | `fcd753ab391c527884dcefe1e60a63d86491b0965d504aa944f0e15f8a96fefc` | 6.0K | Tracked file |
| `c/tests/test_alt_sensor_sm.py` | `dfb8148d3c64a933e2beed6b7668d26d796258c766dddbfdc8dd841082923b39` | 4.3K | Python per-function behavior-equivalence test |
| `c/tests/test_alt_sensor_sm_5D34C.py` | `87918c76c404394402ffc85c6ac206799d81bfdfed41c4e58fdd61ca206a29ec` | 4.4K | Python per-function behavior-equivalence test |
| `c/tests/test_alt_sensor_sm_5D800.py` | `2f951bdaf6e5e145aecfc154361a57075d3dd92ced54e03e6eea91dbe5c067e4` | 4.1K | Python per-function behavior-equivalence test |
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
| `c/tests/test_calc_adaptive_fuel_trim_1379C.py` | `d47005be62b3f93aff4add1178e8cb233ebf8218c756eb3936c885c88d0acd0d` | 10.3K | Tracked file |
| `c/tests/test_calc_barometric_pressure_trim_13F68.py` | `1656e9a9b592457a75eb645ac47a78e6fb02cd0e45ab673cedb04ce65b5ec099` | 3.6K | Tracked file |
| `c/tests/test_calc_decel_fuel_cut_445AA.py` | `4661c049c9b649c9f53c83670efb09df049715e12962990c308e6f6645452458` | 9.3K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_fan1_control.py` | `8b84ce9a25d4746d7c31926ed986f620b3bfc349d99caace7f1cdabb139c21c3` | 3.8K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_fuel_pump_duty_trim.py` | `edc3413dea4d62418e6f85150213c757a489765ea7e0bbe03f687e07a9345967` | 9.5K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_fuel_trim_corr_map_136F0.py` | `61efbf5508099cfc9a1c9b5bea013ca9a3bcc1b581e603f4dd2a8022aa40cf37` | 5.0K | Tracked file |
| `c/tests/test_calc_fuel_trims_adaptive_117B4.py` | `9bad7105cf6f75752c62235a3916188fc3f78a4acc939818fe7bc05ae442ed87` | 13.4K | Tracked file |
| `c/tests/test_calc_idle_speed_target_0x12F5E.py` | `d316e6c3622d9fd8fc8a97e8125b1fafa2d65475fe5f07bfae78e04d54ac0402` | 5.8K | Tracked file |
| `c/tests/test_calc_ignition_all_rotors_13C2C.py` | `85609056cff0f898fbfe5a1ffd24e5a54b9adb555822f55fb4e472b5b09b84b2` | 14.4K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_intake_pressure_pid_output_1252C.py` | `cad7fdd5ae523889604acde3a15fdecb71b2e736707617eebc82bde56dbc6659` | 4.1K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_lambda_feedback_pid.py` | `185b0f847aecbb97a0988e233396519a1286743e251ef6d51d88e9e57bb8e074` | 3.7K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_lambda_feedback_pid_11A34.py` | `0b8d594d46a554abb684569f8e87a96669323a9f50a1569fbfec2563936bb8ee` | 13.4K | Tracked file |
| `c/tests/test_calc_manifold_pressure_error_clamp_10A5C.c` | `64a5b2c602b9740e3d443b7525254bb852992bc649759209e7eb61c2f8057777` | 5.2K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_calc_manifold_pressure_error_clamp_10A5C.py` | `cdf6f3d5b71c66e7d8c927bb3074b847f53cd83cdeba37aa16779b45e9cc777b` | 3.5K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_rotor_sync_idle_gate_B.py` | `65a0233dcd3c4402409c337572772163edad160ea8ed1c5e8200f820f1e4fd23` | 4.1K | Python per-function behavior-equivalence test |
| `c/tests/test_calc_secondary_o2_trim_1321C.py` | `4987730c565cda9e940d3cd6b4d17ffce72cdade943a2606f0937de38db583fc` | 11.1K | Tracked file |
| `c/tests/test_calc_spark_advance_0x1237C.py` | `bac50eb11f4096e9b74de7bbe61ec4e924f5847b4e126c553e2ac532b07d6b71` | 8.2K | Tracked file |
| `c/tests/test_calc_spark_lead_trail_split_19220.py` | `e9b5c66a96dec89a287a832bb7e21b822f63aa74af7767fb3bf8d1f27bcf05d7` | 8.0K | Tracked file |
| `c/tests/test_calc_throttle_position_filter_1345C.py` | `b82023279828dc68e627142e87a5332c2af6396c8072363318c16042b6b7efc4` | 5.3K | Tracked file |
| `c/tests/test_calc_vehicle_speed_filter_133F8.py` | `0eb23bc35c08331e2da174ad811ff95b8a2f04e34218cd5b02eb6c7a883d02fe` | 5.7K | Tracked file |
| `c/tests/test_calculateImmoSeed_3675C.py` | `1f321ad9af17013e4f53bb730019532f9b818d45e27c7fb833f3cb6d3b3859b2` | 3.2K | Tracked file |
| `c/tests/test_calibration_apply_4B770.c` | `7119adb710f3b1dcd2d84ee18066a468504fb736d28613cd9840eae4e33adab0` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_calibration_apply_4B770.py` | `e4ed971e0e154de76e3868b7e1060354c6e13e7ee8339d72edd1f053df6ffd7e` | 2.4K | Python per-function behavior-equivalence test |
| `c/tests/test_calledLots.py` | `3728bef32f793079b65c5fd64847872105968ccf294975555f59043a247035d4` | 4.1K | Python per-function behavior-equivalence test |
| `c/tests/test_canSetup.py` | `b9a08337ead688fa1fd735a2dc826ee7415b50471c46e3b34a7a2b80604c66b7` | 2.0K | Python per-function behavior-equivalence test |
| `c/tests/test_can_encode_handler_62ABC.py` | `98c1573589894423575a2db83095e2c2fd5808277ff61b21ff4b5e987374ff78` | 3.9K | Python per-function behavior-equivalence test |
| `c/tests/test_can_packers.py` | `9f57076f6e50def29351bfd69d6c38356b02f5b567502d710404a252d27946dd` | 30.3K | Tracked file |
| `c/tests/test_checkFloatValidity.c` | `ab582c65c5c38249eba595836f90a9e09eb2830039dc8cadb0548908d241d077` | 2.1K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_checkImmoStatus_371E4.py` | `62a446b4175dd3931c21a0d6d03141fcfd76dfd475257d3e0d1556e79045066a` | 5.5K | Tracked file |
| `c/tests/test_checksum_complement_add.py` | `006660320cfcec797767f1ea9b67c8b238947ad86b395def822a29c928f1dd05` | 3.5K | Python per-function behavior-equivalence test |
| `c/tests/test_coil_correction_write_0x50A54.py` | `916a6b803d755218fd27a240f2bc3cb93cdbb87db60164e7d64bb622cdec1ec6` | 6.1K | Tracked file |
| `c/tests/test_complement_shift_u16.py` | `30260e87df8208ae9cb13757bdd71020bf7da757ba4992de1627bde5b954793c` | 1.6K | Python per-function behavior-equivalence test |
| `c/tests/test_complement_shift_u32.py` | `96c373fda8ba106d6f4982fefc67a6ad64c8d64df59e3a9516d1247061d490aa` | 3.2K | Python per-function behavior-equivalence test |
| `c/tests/test_consistencyCheck.py` | `d8e1538f21e72365f171bd2494b2cb74bd3643eb6915759f0c001a9a865ef2b3` | 13.7K | Python per-function behavior-equivalence test |
| `c/tests/test_consistency_check_3A28.py` | `e032ec261ef9bf7775b2cde0d372fc854277f48ec0b50447f9ca7563e5a4d731` | 7.7K | Tracked file |
| `c/tests/test_coolant_temp_boundary_check_1F99A.py` | `19810dddaa3e420ffdc78afd46d346b5d191196a41d840b3b148f9986298602a` | 3.6K | Tracked file |
| `c/tests/test_coolant_temp_out_of_range_check_E50C.py` | `97729112a26bfca9657f4a719f07ce80d5aa5fec8693aa298cb1971b6a009458` | 3.5K | Tracked file |
| `c/tests/test_cooling_fan_control.py` | `ed8d94c1306c76de0e70c684a4b0b60edc2b70c99f3351a9a2dbcf1e94a839a7` | 4.0K | Python per-function behavior-equivalence test |
| `c/tests/test_crankSensorInit.py` | `ef23723f854a27ab0011b33c0b4c13655a9b467028217745ca1311d64b23e6c2` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_dataLookup.py` | `007121b1f630c99805a4492692c0bd1b50925e82914e92870b63460c1498b820` | 4.6K | Python per-function behavior-equivalence test |
| `c/tests/test_delay_loop_n8.py` | `5084347986d5453524888b9a58fcdfac709ff9fc91a3bf5af1c1383a5de301d3` | 3.6K | Python per-function behavior-equivalence test |
| `c/tests/test_div32_signed.c` | `76733752f95f1f468434f99ddd4f6d6b1069d097ea7aa3d1105881fbdb61dbe0` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_div32_signed.py` | `933638838f61ecb2e4d86f388057a0f7d0abf670f3bb2c0b5cbc2b22a411970d` | 9.1K | Python per-function behavior-equivalence test |
| `c/tests/test_div32_unsigned.c` | `ee1ed14e17a880b5f89320dc18a09c7d72757b971882e9122f8812ba09cf438b` | 2.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_div32_unsigned.py` | `c8f5ac7380d2af4ec4f5f854640783e84a19a105b8159ae34aa5c47922e81b34` | 4.1K | Python per-function behavior-equivalence test |
| `c/tests/test_dtcRelated.py` | `58d57517fc7e913663accb0e41d4eeabd9f9b7a76003e85be9c27fd740db11b2` | 5.4K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_code_set_clear.py` | `b437df1d4eebb950934276e0cd87eeb1c80e7a5fb476d4367e3c43c567336f6f` | 2.8K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_data_read_60F58.py` | `5361261f91c1625fb804c18552549ce55cd955c344e240b2e883c78ac29d1a47` | 2.4K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_debounce_monitor_43760.py` | `bc0e818d3978519385ad2931304e76ed158183d8630e2b174f00e55e06c60602` | 6.0K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_handler_610FA.py` | `c5a2cef0c037a4d0df1854fa2adc2dbd4fc2b17b2ae588e56de67f796f506974` | 3.9K | Python per-function behavior-equivalence test |
| `c/tests/test_dtc_handler_61550.py` | `d98667cbf3bf2ea5034ac307d251c85d53c9f3bc03811b588583e30af9916f81` | 4.4K | Python per-function behavior-equivalence test |
| `c/tests/test_dual_cellbank_selector_58C4A.py` | `782021436d99062cc146db9e8424b41ed3b483c718f0120dab2a020a325941e3` | 3.9K | Tracked file |
| `c/tests/test_eeprom_commit_dispatcher_37000.py` | `2547705ed02d686f88a6d2ef607c9a5da7fc4ea993bbad8caa1947ac6ecc0a62` | 6.2K | Tracked file |
| `c/tests/test_enableDisableCruiseControl.py` | `59db7e7dec7f9877cbd266c667a92db07fbbc703f014ebe7b7fd1de90a6b71f2` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_engineControlCalculateTiming_14584.py` | `1759652cd187f8b02f9d9290c1ac9e96b9e2a061ea5f96091c44e3f1b58ee7e9` | 17.4K | Tracked file |
| `c/tests/test_engine_load_estimator_0x190A6.py` | `5847469b90b73edcf25de168f06c983a260d4eb70361c24ee65af65b25d5bc98` | 6.0K | Tracked file |
| `c/tests/test_exhaust_oxygen_control_19480.py` | `092fae2ddc3b90c317d31d59f4334ce110f7954e80cc6dab98eb5fecb6ee8534` | 13.7K | Tracked file |
| `c/tests/test_flag_setter_49ED0.c` | `a0331aca2cfc4260d8647800299c6b5a7db55c4c9e4088f25687d75d685470f8` | 3.2K | Tracked file |
| `c/tests/test_flag_setter_49ED0.py` | `4feae0c2e6eea39283b56aded6b1d5416d029e3e04690774b8e038a647354c43` | 2.4K | Tracked file |
| `c/tests/test_fuelingInit.py` | `06b34a57151af4cb505ffb60f475517c65f6818bfef255dbb8e7fe179fec435d` | 2.0K | Python per-function behavior-equivalence test |
| `c/tests/test_getACSwitchStatus.py` | `3ca849fffab8422af2c410bf5f4692f2d98a1d4ef326ebf5ad7c9935408fbd59` | 1.3K | Python per-function behavior-equivalence test |
| `c/tests/test_getBaroSensorVal_D144.py` | `a5177f9000dee01716a05d54490d97b2a71b1f54c0b2b3d69cc772b69c7e4598` | 2.4K | Tracked file |
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
| `c/tests/test_get_iat_threshold_3C214.py` | `0e64e233cdf1e9d1be49e2f64d4e3bd661a444a0b3c08f0518f817935fb20de0` | 3.9K | Tracked file |
| `c/tests/test_get_ignition_dwell_time_0x94C8.py` | `71d69ca711ef54acb02d8d75edba9f1d00abf10a7b2d3aa957ed051bd4132e00` | 5.4K | Tracked file |
| `c/tests/test_idle_speed_control_18054.py` | `87a045a1f6f9b4a2aea890decee5e67b91fac30c2ffcaae37f585d8dd2286869` | 5.5K | Python per-function behavior-equivalence test |
| `c/tests/test_idx_table_helpers_68780.c` | `7e53993a28fb46c76a24faa1025b60e282abdff1edd0e748bbeba06184897539` | 3.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_idx_table_helpers_68780.py` | `380496e78d8c160f267ff96a51c964648d54abf80309b2a37885c37944b9614a` | 4.7K | Python per-function behavior-equivalence test |
| `c/tests/test_ignitionDwellOutputInit.py` | `cafc80009806d27c3546601870e7843f5348620885dc47c25031f973c6c67c5d` | 6.4K | Python per-function behavior-equivalence test |
| `c/tests/test_init_main_3E10.py` | `b89dd57cf9fa9b117bbec3a2c83ecf044c25ae3ea6f15e506c13a8605d59877f` | 9.2K | Tracked file |
| `c/tests/test_interp_leaves.py` | `e1a9d0c940c77600197e3661b99b7bb1c168a153c69a2eee8d10e83d792d2155` | 7.6K | Python per-function behavior-equivalence test |
| `c/tests/test_knockFunctionInit.py` | `9943ab87ade7fbc839adfbc14ae05a6cfef622de6bbba2260836f97731673664` | 1.5K | Python per-function behavior-equivalence test |
| `c/tests/test_knockSensorADCFault.py` | `3b426011b3fc93d37a3f778c21ccd04e9bc244caa3fa0155d226ef8279a4d7a4` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_knock_related_init_C3C8.py` | `c558ed187b24e209be27d8db235ab95c7eb2b2be2acd365963fec6e369cad9b7` | 6.6K | Tracked file |
| `c/tests/test_knock_sensor_adc_fault_C460.py` | `e571c55d9f1b57775dc04766e90c89229dcfc617fc7fca9a09fe202ba14e4edd` | 3.2K | Tracked file |
| `c/tests/test_limitKnockRetardMax_CondRPM_13AE4.py` | `2ad1bce741dbfb45c4364b6cd5cc6670acd7f47d12ff01f460985c7b8a8617c7` | 3.8K | Tracked file |
| `c/tests/test_loadDatafromE2intoRAM_0x36BD6.py` | `b914aefb80af4d5a93a37bc31a8a29e9da32c4b62d91d4d916e06465845cdb96` | 4.0K | Tracked file |
| `c/tests/test_loadStatusRegister_ADDR.py` | `c8c723118fa7957978343e7ded4d5e7f326aae9a992db62ebb8e13e371ea2926` | 1.9K | Tracked file |
| `c/tests/test_load_blend_factor_limiter_0x16A30.py` | `fb8718ef88d3bf33264cbc2b4f17caaf72624ee529353148d362a16528509439` | 5.5K | Tracked file |
| `c/tests/test_maf_limits.py` | `b4ffad2611e33dd219f05c261d804b7a2ebbf538671412b4bb314fba75e79706` | 4.7K | Tracked file |
| `c/tests/test_main_entry_D49C.py` | `c3da07a969fc74313769b7b5e57d22daa259cc4e6a6f76d11b023c7b7e88cb67` | 6.0K | Tracked file |
| `c/tests/test_math_primitives.py` | `09c660b5143c2ef40d67d8cc4b2ac0a7c9e692e0915a4a915bf3f49b9ea17cf1` | 7.4K | Python per-function behavior-equivalence test |
| `c/tests/test_mem_accessors.py` | `6d1ada8423863bb62303186739fafa1c4c85a36e4911a8345657cdab61f6ae86` | 10.8K | Python per-function behavior-equivalence test |
| `c/tests/test_memcpy_bytewise_unroll4.py` | `edfe67df156ea880ea18ba0387e4b93a2379c48e5add5ef9bcb8db0e999d5371` | 4.2K | Python per-function behavior-equivalence test |
| `c/tests/test_memory_match_accumulate_583E4.py` | `ccaf8c06e13f2e0aef7ee5fe1f4087c85c41bb6e7fd8001b47cf4b38231288d8` | 1.4K | Tracked file |
| `c/tests/test_mod32_signed.c` | `09df6a2ac60b399d2b2e2725519455492e51636c5cd06b63132feeda157cc512` | 2.9K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_nop_delay_40cycles.py` | `5c13923de4b431ca89b2fb743ad28a40c98b8c5d6fa48db063da8c45a1798546` | 1.3K | Python per-function behavior-equivalence test |
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
| `c/tests/test_obd_service_handler_63B46.c` | `bd2a362041b6ac4c7a4a1dfe6ed54dfb79ba5d8662d788b5e633f7ed90813443` | 2.5K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_service_handler_63B46.py` | `8e2e444c7389f0c159ef0ec83f1a062af8673b209bc4889bd9f5e85bb4845ba7` | 2.8K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_service_handler_648B4.c` | `7ade23bb482a6958cd7574aa1d77f672fdeb28b5963a7522446afbae42f14ab4` | 2.6K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_obd_service_handler_648B4.py` | `6fe229f96568dde215b68a041814d139368d8b7a392c302c879213f06f3ab0b0` | 2.9K | Python per-function behavior-equivalence test |
| `c/tests/test_obd_vars_vector.py` | `9a824fda9857e6b29d4e14adbba3bbef6422a79b5b18413526a8e5acc91d8d0f` | 15.9K | Tracked file |
| `c/tests/test_omp_accessors.py` | `e9eb93e8b8c276a5ca62869ced12caeec7b05f09dced876bb8f4574c5b1a533e` | 5.3K | Python per-function behavior-equivalence test |
| `c/tests/test_omp_control_task_1825E.py` | `b56e523b50bc0997c9724da7be31d297ede14e86e50ab76bec811d76f5c938a5` | 12.8K | Tracked file |
| `c/tests/test_omp_rotor_overshoot_detector_18CC0.py` | `fa9b094b6a34b686d50d7fabeb083fad0378be731fa3617cd8b3e4852c2e4da4` | 8.1K | Python per-function behavior-equivalence test |
| `c/tests/test_omp_stepper_waveform_driver.py` | `154ae7403ad7e6966a01788e8a38bedb640e5c3f84b5a8bc0d80f6e83d9f219b` | 5.7K | Python per-function behavior-equivalence test |
| `c/tests/test_omp_waveform_state_machine_18860.py` | `5534180427a1bc02536de0438b200e68443e9815f2f29bbe89b0f64617bbcf51` | 7.1K | Python per-function behavior-equivalence test |
| `c/tests/test_osTaskScheduler.c` | `f763e85fc9bdcd7f7dfed3e9499f50a5dc503e619cf6fa3a59dcb88f8e75215f` | 7.4K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_os_context_switch_3DB0.py` | `a7cbe230f6e2bf9ccc1c478b6b85dc918a90bed6c8ced2f8d71e28b85254e0be` | 6.3K | Python per-function behavior-equivalence test |
| `c/tests/test_output_per_rotor_ignition_dwell_0x11218.py` | `06d1e8d05818b68d0f9a31164582010242004189f3911b2d4800052d50bb0002` | 5.4K | Tracked file |
| `c/tests/test_output_spark_0x8DAE.py` | `04ff0bc62d256e259b256e0d10def541c0e5e372c36ccf5633ee0ff21b928c63` | 6.3K | Tracked file |
| `c/tests/test_port_helpers.py` | `ce21feca580410897a23608d47e481660807e8e99515d2619ed35ec1b51f0ecd` | 3.7K | Python per-function behavior-equivalence test |
| `c/tests/test_pressure_delta_monitor_1AED2.py` | `c9978e9bdf98f7405d4031fa93ce662043054e35e28f0c18c3248514cc47a692` | 5.3K | Tracked file |
| `c/tests/test_purge_subsystem.py` | `583a31da56f1913fc9f628fc5bf4e3d6fea4ff305bf15e4f1603ed8c0c9cd6a4` | 5.9K | Python per-function behavior-equivalence test |
| `c/tests/test_radiator_fan_relay.py` | `e0fbb30fbd041e363ddd0cee2b863e0571c98bccd4fc62fbb79db031dec0f6f9` | 1.3K | Python per-function behavior-equivalence test |
| `c/tests/test_readECMVoltage_735C.py` | `2390a2fc32d91d3f7da4a55fbf6c22acb7f7d28a808c699176e2da5f8bcee61d` | 4.0K | Tracked file |
| `c/tests/test_req_queue_69602.c` | `80e2505fea9b0e2c438d360ba36d10c01ae6ef6610c1578e42e46ef9cb540cab` | 3.3K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_req_queue_69602.py` | `29c646cb46c615b93a3716f547fcb5d230f4ff3efd609382774117affe2f658d` | 3.1K | Python per-function behavior-equivalence test |
| `c/tests/test_reset_handler_4E0.py` | `90f42f8ee528c2c27550a6393a2636c8f1448acfda4014680f3b85d6a4c0a11c` | 11.0K | Tracked file |
| `c/tests/test_returnDwellTime_fp_0x1120A.py` | `4110a374b4e00c61e156c5d57387c2cb066072bcb09035aad168b63ae5aaa00e` | 3.7K | Tracked file |
| `c/tests/test_revLimitFuelCutInit.py` | `d57950d4cff5062174f19e85878561325658cb1301eab2251c985e248c8998af` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_rotor_sync_gate_state_ctrl_2100A.py` | `2f6370e99677cf8800b4acbb89bd526e8841646485fdf07fab68d970801d5354` | 8.5K | Tracked file |
| `c/tests/test_rotor_sync_position_detector.py` | `8c1485a66c304f3095221cca21af21183b313bc751cace19ea8bf97f5a857858` | 6.7K | Python per-function behavior-equivalence test |
| `c/tests/test_secondary_boot_main_A038.py` | `fdb2a36bc16230e379aa5d062978230642b73467b65aa4cc48db1ce5a5767504` | 7.5K | Tracked file |
| `c/tests/test_security_access.py` | `8ec7fd87ec82a3dd722d37bf214ea09901ee1d4432cfcc6a426a19c8e9dde62d` | 24.3K | Python per-function behavior-equivalence test |
| `c/tests/test_seed_gen_5699A.py` | `b708b7759b70101f36842981f6e3047c957b56b491da43589dbd22bbb52cb1f8` | 6.7K | Tracked file |
| `c/tests/test_seed_mixer_366B8.py` | `af3b36fa8a3cb64051ceaa31cf9c7696b2fa5118138dafa315b64a3c45262606` | 3.3K | Tracked file |
| `c/tests/test_sensorADCRead_68A8.py` | `6dabcb479eb15014a8de57c73a3c3364ee378ce0d65203f6a29172be01e9a3a0` | 5.3K | Tracked file |
| `c/tests/test_sensor_check_float_bounds_adjust_E0DE.py` | `d88117d3d75346c9facaf799060d347a28d81cb4feb23db207d65b776d6909a7` | 3.4K | Tracked file |
| `c/tests/test_sensor_range_check_3ED0C.py` | `67b45dd695d4faae7c668ed047abcd308508537b43412b4f739922eb98b9d9f7` | 2.5K | Tracked file |
| `c/tests/test_sentinel_equality_check_5687A.py` | `b8b2098c0df50cb5443b7dece3a9308bc4e4dfece2b3f621bd414076e3439518` | 2.0K | Tracked file |
| `c/tests/test_setAlternatorWarningLight.py` | `574567bfad9bcf196af11aeba9f6bf72ecf95b07975cc3c0dab6d45be256c6d5` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_setImmoCANTXData_369B8.py` | `c90ccadf696f89975baeeba7d51aad7ae572121268dccf66136460747156dbae` | 6.7K | Tracked file |
| `c/tests/test_setImmoLight_263C8.py` | `5bffbfbac48367c54e3e22a7d4ebe13142f4b68b62f9b55b870c17b9dd04f679` | 3.0K | Tracked file |
| `c/tests/test_setMemInsideFUNCto1_0x3E3F0.py` | `605f26e2bc898fc64274673fa5ffee2c3819c67fa6b2eecb0a5f651365877333` | 1.7K | Tracked file |
| `c/tests/test_setRegister_REG_BIT_VAL.py` | `8f85bea3c8e621feb3327f9f9cfd003c1dae4a4ab290f235c54f7d1885e29d27` | 2.3K | Python per-function behavior-equivalence test |
| `c/tests/test_setSR_getSR.py` | `f9202e1fa8db4bde87f9848a740ac4083e9ba859f3995ae0a5c3e942d1b51707` | 10.1K | Python per-function behavior-equivalence test |
| `c/tests/test_shift_left_logical_r0.py` | `0ac0bdd174f41ed52d4acc2c85569a355f49efcdee183df259c7cb01587b9c99` | 3.2K | Python per-function behavior-equivalence test |
| `c/tests/test_shift_right_8_r0.py` | `7f1566d157512066db82336620da721e5987eba837efdb0475bef856f1308262` | 3.1K | Python per-function behavior-equivalence test |
| `c/tests/test_shift_right_arithmetic_r0.py` | `df0ab58bc1639666fdb4e224c83dbd554e6bce43d536618400ecc74cf86af279` | 3.5K | Python per-function behavior-equivalence test |
| `c/tests/test_shift_right_logical_r0.py` | `e557958f2eeecbc05b59ed87041570cc04eb2a8f8a7e1c39484a7ac0393627ac` | 3.2K | Python per-function behavior-equivalence test |
| `c/tests/test_spark_output_enable_fault_mask_0x10DC8.py` | `5679d944889a2b225f59e18983980fb6cdbbff76fd6822182e7d2ee6316690dd` | 6.2K | Tracked file |
| `c/tests/test_split_selector_decoder_48C12.py` | `db9b9cc3daaed739277b99dfa9c28cf513f5159c4eb49d1fdd31eba9bda66851` | 4.0K | Tracked file |
| `c/tests/test_split_selector_state_ctrl_487DC.py` | `29311eaca1dbf2e0ccd4dc972f47d882a392e1a2ac881e971c714c93df6fa9f9` | 7.7K | Tracked file |
| `c/tests/test_ssv_control.py` | `077a95a2985e9e79bacb4b2c62c6a903ac28f5bf413e729d471aa65437690ee1` | 5.0K | Python per-function behavior-equivalence test |
| `c/tests/test_store_knock_learn_buffer.py` | `ed90e97a871282bef7e5eb19167cace763e939cfbdba500025aeb605ed076d63` | 7.1K | Python per-function behavior-equivalence test |
| `c/tests/test_taskEndRoutine.py` | `7fb798b9811d64eb2cac0c3cd3b0804afd8b028fa856dabb8967cd77eef9eaa4` | 4.7K | Python per-function behavior-equivalence test |
| `c/tests/test_task_context_switch_3AD8.py` | `8bff8052b8301939523603b528be437eb4556427acd65874a82cf67c471176ff` | 8.2K | Tracked file |
| `c/tests/test_task_execute_by_index.py` | `3b15eb3a9abb0203b44eea5066ce68efb704801a4ea35717838d8a8ff4c8ab02` | 4.9K | Python per-function behavior-equivalence test |
| `c/tests/test_task_flag_run_C.py` | `ecbaa12aef78ef9ca8349a329fa9c3ec247225530f80116d8204bbff6f541ade` | 2.4K | Python per-function behavior-equivalence test |
| `c/tests/test_task_full_context_save.py` | `b7a89b0c4a72bff97db11a8917047867522276322f4e52ec46355da9fc1e4339` | 8.5K | Python per-function behavior-equivalence test |
| `c/tests/test_task_full_context_save_3BF4.py` | `31eeed31ed877a96c6ee7bec0e3757c4901f26a994be0b2ff1cdb3b401cbe175` | 7.7K | Tracked file |
| `c/tests/test_temperature_gauge_0x5AA5C.c` | `c062994160aa2bb9f6837586beef0db5add165c6daf9e83bb26b22ff4f0aae9f` | 1.8K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_temperature_gauge_0x5AA5C.py` | `4ba82d22dfcf8b2bc12a04449bcc2b5283f50acbc7f398b47e1034b7442c9932` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_throttle_position_adc_reader_19FC0.py` | `6f149fb1a02766e01d0c2691369c94aea5eb562ef185d83846ed60ec87c1dc98` | 4.6K | Tracked file |
| `c/tests/test_updateE2RAMBasedOnInput_0x36D0C.py` | `8658cb5c356726bc8b74e9dbdd4397e84a5d909de58e2984c24ca61785b5c758` | 5.2K | Tracked file |
| `c/tests/test_vfad_control_35BBC.py` | `bb91fbadb598fc5a6ba61fa4f5764b3ae20cb39b734bb10a05be84fc2c3268f6` | 3.6K | Python per-function behavior-equivalence test |
| `c/tests/test_vis_intake_control.py` | `a2472fa0c428753804bb0d0144c220284daa53aa43daadbe102a160bd4130385` | 5.5K | Python per-function behavior-equivalence test |
| `c/tests/test_warning_light_0x5AADE.c` | `9a4cdacdb5fc30584bb14a802cb82d83580e07d23461f5c5b3fd62096f9333e6` | 1.7K | Verified C lift (behavior-equivalent, emulator-proven) |
| `c/tests/test_warning_light_0x5AADE.py` | `479018ca50ddd0426814cf7d00eabc5a38e0565b72ac388dfdabba0d13522823` | 1.4K | Python per-function behavior-equivalence test |
| `c/tests/test_whileLoop.py` | `8b13b430963add2187b9344a02f583c21e6ebd6b87a07a5fe4531a2a5b119b58` | 1.3K | Python per-function behavior-equivalence test |
| `c/tests/test_writeToE2RAMArea_0x39124.py` | `632203bb721c7d6a85d8c4b2fe72ee04296337432007c613cce8f621d1ae6b2f` | 2.7K | Tracked file |
| `c/tests/verify_emu.py` | `f583e1d294b0966f7203a3eb0addfcbf2c9d828abfc3292a2965e3f8d526de51` | 3.0K | Python per-function behavior-equivalence test |

## tools

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `tools/ASM_BASELINE.md` | `f7fefa9757def58943b0887686f0b5f5369a95600ee35ba247477ff64252df33` | 4.5K | Method, byte-exact proof, coverage, limits, next steps |
| `tools/README.md` | `10c9317e30be5093c324dfe5cd9420f11543885a0dc0264e1e4a95606c3a1cb6` | 3.3K | Directory README |
| `tools/callgraph.py` | `25a5f5a936ebbca11d2bf7ec888db5de8d9a5fb01c4440992c593e500cc59ee3` | 7.6K | RE tool (see tools/README.md) |
| `tools/cross_decode.py` | `3a6532e07091d41fc4f4f94d3890bec87cb37726f7fb0bb8c3a6c9e32cf028c8` | 12.2K | RE tool (see tools/README.md) |
| `tools/denso_ck.py` | `3b4f2f74ea4256bf2a16e667ee1e56af7220167d8ec04f3a3fa38ba15c26fb33` | 1.8K | RE tool (see tools/README.md) |
| `tools/disasm_sh2e.py` | `8285f0540ba48534d4df9bafd6f1b2515caaf992133f8c1cdd3e78151f29452a` | 19.2K | RE tool (see tools/README.md) |
| `tools/extract_func.py` | `9470ed47cfe15f275c6478028d735daf225056397ae97140ac59c128019db7a7` | 3.9K | RE tool (see tools/README.md) |
| `tools/gen_badges.py` | `d2f94a51a86f0500edba4536949e3221ea4f86c92250a3b5088305859abdb9f1` | 13.0K | RE tool (see tools/README.md) |
| `tools/gen_manifest.py` | `b4168e53728be22c7348d72bf105da192c8c605704ebdc83170dd9cc870cb25e` | 9.6K | Regenerates MANIFEST.md (repo inventory; python3 tools/gen_manifest.py) |
| `tools/get_toolchain.sh` | `869564ff4694cab83827f0fc9299be489a2b7ae76b25bb2d51c00d7a56aab69c` | 3.1K | RE tool script (see tools/README.md) |
| `tools/idamap.py` | `b9f3102edce605174eb4c90b476b51bb28811e2fa22719cebbfca154305bd3c3` | 4.8K | RE tool (see tools/README.md) |
| `tools/mapscan.py` | `9bdb9675ca4faba36443b7eeaaa68d4fb014dd0ff4f3a50c823f3be715a9ce6b` | 5.3K | RE tool (see tools/README.md) |
| `tools/mazda_security.py` | `b354e01c40dd2c4d3d6885cf4d1b2adb8b0afef84a21ce03dd30048e7cd1a86f` | 4.8K | RE tool (see tools/README.md) |
| `tools/opcode_audit.py` | `5f7d812612caeb380ee38e0e6db7736af5db36bf1e9290b76b7642fe6fc0f1a7` | 12.4K | RE tool (see tools/README.md) |
| `tools/organize_src.py` | `952eab08198e20668fe3d8a2b572222993a2247516fb18814e68325cf02a65b4` | 9.5K | RE tool (see tools/README.md) |
| `tools/rom2asm.py` | `a0cc400125d3f3f913285fc873b73b784c1f2d3f2d07ed139fdb6a7112722da4` | 6.5K | RE tool (see tools/README.md) |
| `tools/rom_rebuild.py` | `389f1044dda89555dd85b02c8f351b6371f02139763eb531af042365000c88a7` | 7.3K | RE tool (see tools/README.md) |
| `tools/run_tests_parallel.py` | `c63d357fc7283b6a4d7e95ca1401c5983b2132a065a792d4480f1155722dcb7d` | 5.1K | Parallel test runner (pytest, all suites) |
| `tools/sh2emu.py` | `a7192e7bd1c63a537458020313c012f022b68fd67042e735566b87aaa5377eaf` | 29.2K | RE tool (see tools/README.md) |
| `tools/verify_all.sh` | `d264410fe557754c812cc5fa89b3671743f7e8312e886482080a6cd4a79d77b3` | 4.1K | RE tool script (see tools/README.md) |
| `tools/xmap_names.py` | `9bb65fe324af3d665b562c0b3c8684655529671398bfed1ad7cbc99d22c30e03` | 5.6K | RE tool (see tools/README.md) |

## tools/tests

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `tools/tests/test_decode_families.py` | `862d5ad96fa8b41081db62eb78258c937ddeb773b8b9a1bd7fbb772cdd0b5b83` | 14.4K | RE tool (see tools/README.md) |
| `tools/tests/test_emulator_families.py` | `6472e5aafabbd76dc3a83c2f99814cfdf8d181583c9e2ce3e5756591830a6958` | 22.6K | RE tool (see tools/README.md) |

## docs

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `docs/README.md` | `2c9c50a1c439d96585bb29d7d7794984d5dc5454996a6bd5c2952eb4af49580d` | 14.9K | Documentation index (generated/verified against current tree) |
| `docs/functions/E2IntoRAM.md` | `db9738a5949b1139f278a69467c1c425454a758900000a985c07538d0fce9a59` | 3.1K | Per-function documentation |
| `docs/functions/INT_ATU101_IMI10AG.md` | `be705c6761839851a08a10db98de35ea1d50fed20284d1aedacd6ec89540769b` | 2.0K | Per-function documentation |
| `docs/functions/ImmoBadStateSet.md` | `05942012fb4fa3c5c2e59e70a2aac903a98aba0c2d433d1b7fd2a43ebbc6553f` | 1.7K | Per-function documentation |
| `docs/functions/ImmoStateReadyToDriveEngineOff.md` | `9d3dc91c102ab7e392b4c18e1adcba5ef3ce0c6c8275426d0a4c2bd88ddc1778` | 2.1K | Per-function documentation |
| `docs/functions/Immo_Keygen_related_ADC.md` | `e8e78ea6c57e5475200cb5c3a672be3147138dbec82d9405585584a0fe65b67e` | 2.3K | Per-function documentation |
| `docs/functions/LongFunc.md` | `41eb5dd297fb8c47e434caee670139e5149b0f16102fb7783798a78c79754fec` | 1.3K | Per-function documentation |
| `docs/functions/MAFRelated.md` | `4c89f1234f4b9bf3b53a3efba9bedca53d05a979ff84cfd44045b777bb9fd435` | 2.3K | Per-function documentation |
| `docs/functions/MAFStuffMaybeVE.md` | `4fbb4543ee8d271bb518f5a5bcbf05c38b30ec744e05bbd58866dea53af7d91e` | 2.8K | Per-function documentation |
| `docs/functions/OBDStub.md` | `61e2d4e1fd27c89ff3aed146ca619d77a45e66c18a47388b4aad031295bc2f75` | 396B | Per-function documentation |
| `docs/functions/README.md` | `3e2026b714561368a526ce7b43db768ede34307cde233fea053ba672682934bb` | 2.5K | Per-function documentation |
| `docs/functions/SetMemoryNotValid2.md` | `4d23748d4173804cc8f79648497d3d93dc0b76ed0f3efc136c16bd007b91990a` | 524B | Per-function documentation |
| `docs/functions/UDSPositiveResponse_16bit.md` | `b5beb82968daf345e63adeedb6d37a3e888171e98a46fb0a482d8432a48a9d00` | 1.1K | Per-function documentation |
| `docs/functions/UnknownFueling1.md` | `fe544dffcc5ed064580f2ee94eb0480cbce2266854082764fe676554e61bcd3b` | 2.3K | Per-function documentation |
| `docs/functions/VDIControl.md` | `9ea54089915dbae603f2218256c005b3d33762d5bfeb05cbdbd788110154cceb` | 2.0K | Per-function documentation |
| `docs/functions/adcIAT2Volts.md` | `ddcd57e6024cb018af04e5bba00d980c4af0833f6a0af303ae3a53f3918abda6` | 1.2K | Per-function documentation |
| `docs/functions/adcVoltageOutOfRangeCheck.md` | `4a58322d86a9d8d449769aaa9149b9be7fa7717fead9346d831977e08a05d637` | 1.6K | Per-function documentation |
| `docs/functions/addS32Saturate.md` | `8f8217d3466ab72c98801b89d3513783a8efa53844c0cc551dff1f6111f8910b` | 1.7K | Per-function documentation |
| `docs/functions/arbitrateFuelCut.md` | `871fecd5770b62399bac41bddb74a546f3ce27e851b74bb3a279ac8c3f75391c` | 2.7K | Per-function documentation |
| `docs/functions/bitfield_extract_merge.md` | `bedeac8a4d0844070f5985574428d6260e0a0293e4238dd1ba3972bc95236be8` | 7.0K | Per-function documentation |
| `docs/functions/byteToUDS_SERVICE_DATA.md` | `dee2556d89d8c9325fce673cb541387e4a44fdad6fd0e6c40f0ed6170a250f6a` | 709B | Per-function documentation |
| `docs/functions/bytetouds_service_data.md` | `e8d509db9b2a50882724c4759900b4bccc76d1f42b373d69bd2f2ed34af6b0e4` | 1.7K | Per-function documentation |
| `docs/functions/calcDesiredAlternatorVoltage.md` | `30ed955049a3a883b53f5f2f4bf8ba66f53cddf290869af20c7e0a86e9f38da9` | 4.7K | Per-function documentation |
| `docs/functions/calcDiagFuelInjectorTrim.md` | `805836873876e51ada9209d7a8ecfafabb59526042cb5685e927301a55581308` | 2.7K | Per-function documentation |
| `docs/functions/calcInjectorCrankingTime.md` | `80417149c89332327b2f588af80175f957622c22976e9f5cde723c4021fe40e3` | 2.4K | Per-function documentation |
| `docs/functions/calc_adaptive_fuel_trim.md` | `de69aaa5a6449f3a6b6258a6bc1ca12b269c2351e6e1075d6fb3d31dae33d78c` | 6.7K | Per-function documentation |
| `docs/functions/calc_decel_fuel_cut_445AA.md` | `d41db5be745804867f03a5ab5907d121fef729f24e070e11226effc93ba2745d` | 5.2K | Per-function documentation |
| `docs/functions/calc_fuel_injection_all_rotors.md` | `60a994c9f255ff833557de14256306028a6a34b13c0c46b52ed31d48258ba4a8` | 3.0K | Per-function documentation |
| `docs/functions/calc_ignition_all_rotors_13C2C.md` | `17552d0f5aa87f4e61ef4a656cb517f42c6460d72d6c9e7bc33713100a7398e3` | 9.2K | Per-function documentation |
| `docs/functions/calculate12VBatteryTemperature.md` | `64183aef4b9aafd10b07782dc85b0b7c44797657d3beca1104ad6067ca3518ac` | 3.3K | Per-function documentation |
| `docs/functions/calculateCruiseControlSwitchVolt.md` | `2bb91acd68a9190faa6a3966cb1dbc062c9da7c6d567efbae1a56e5ceb5fc4f1` | 1.4K | Per-function documentation |
| `docs/functions/calculateEngineTemperatures.md` | `8f784e1b209cb734f11c208bfcaf2075427588fe450c1d77530ffb12d0dae8fa` | 2.6K | Per-function documentation |
| `docs/functions/calculatePerRotorIgnitionDwell.md` | `36f2ac24e7f12003977966d7ad8a11c26bd6f6044c82c2de408e0899f3abe8fb` | 1.9K | Per-function documentation |
| `docs/functions/calledLots.md` | `56987a5ecb4eb48179a3d1f6af32db221caac50c707f049519aa8a2bf95e85e2` | 2.5K | Per-function documentation |
| `docs/functions/canSetup.md` | `8d318b11385ce8c6e46f0b8c93b53b807f5f84ea012b6ea9811b198e1941b5c8` | 2.2K | Per-function documentation |
| `docs/functions/can_message_handler_24588.md` | `e84de9ffccaf5d0f0956ac8e9787539c7b5f7dd8d511d9efb73f28cfe55991be` | 444B | Per-function documentation |
| `docs/functions/can_message_setup_dispatcher_33974.md` | `f2b5320509d41b5dd146f1731d645fa9302efff6d884eabd2d9468b5e2d096c9` | 1.1K | Per-function documentation |
| `docs/functions/can_rx_handler_49100.md` | `4dcd9725ea119e4a86a7e16ca3189ab4c58377ea3d03cbe4e6ac2faeb65340b4` | 788B | Per-function documentation |
| `docs/functions/checkFloatValidity.md` | `2054c23785419475acb6953ce40a061ea269bd343ab1f3991fac2d07d5993b9c` | 1.6K | Per-function documentation |
| `docs/functions/checkSubFunctionCurrentlyRunning.md` | `d11d64700734c207d692ec1ceb022966de439b040515d247a4718c8b2b006983` | 1.2K | Per-function documentation |
| `docs/functions/checksum_complement_add.md` | `1e41dce792a03789dd089c9ef377953c78ea56d0ebd564bfce79a632bcbc795f` | 1.4K | Per-function documentation |
| `docs/functions/consistencyCheck.md` | `eac98ca10c4bdbe40ffd46e43d7d9873cbf7e12d2ff1cd12441d2a8e6bc97842` | 2.4K | Per-function documentation |
| `docs/functions/crankSensorInit.md` | `6f63c57b21c502088cbda167b47117b009c30c397251c8853d3781c1d9454d7f` | 1.2K | Per-function documentation |
| `docs/functions/debounceCalculatedGear.md` | `fa290d548f8b6e17b22c823199aee98aab4face5304ad94b93e6908792eb03ed` | 2.2K | Per-function documentation |
| `docs/functions/delay.md` | `f5f9484a8c5d34a2ccaef19c107a85fde0eb168a96ce83188dab2c253c917da0` | 1.2K | Per-function documentation |
| `docs/functions/delay_loop_n8.md` | `2304150ccd15509a48fa9331d1ef3d7eda27a0e0a5d5e1e254230efd830fa9bf` | 1.7K | Per-function documentation |
| `docs/functions/div32_signed.md` | `e288dc16d7e2773ebf10947bb7ebc9af13e448e833aaf7040bab69e4f6af8a51` | 1.5K | Per-function documentation |
| `docs/functions/driveCycleDetect.md` | `6904cad18ab126130799f99109c950b2582ab83380f843e5fa9d47b2c7cedf8a` | 4.0K | Per-function documentation |
| `docs/functions/dtcCodeTypeInit.md` | `11d007426c4b9930f74c4f2389a2da9dc34ecb69b47cc6d619569ee32a3ff5ee` | 606B | Per-function documentation |
| `docs/functions/dtcRelated.md` | `bc95a8438f2a5d3c7d09318fb3e50a58624606d8d1a941439a2a7de425ce31ce` | 3.4K | Per-function documentation |
| `docs/functions/dtc_data_read_60F58.md` | `524cdfc08ed70a8eeac9748754da4c72b452f2ea3e9d938c6cf22727f5c659c3` | 867B | Per-function documentation |
| `docs/functions/dtc_management.md` | `904079b3b6f5e9bebe1a310f4dca452c82a2a80b1abc8a2c0d3225225d2f1a22` | 6.4K | Per-function documentation |
| `docs/functions/eShaftLearn.md` | `1a7087fe2958b357b79642bcb614a0ea7674b974459b60b89acc6670504f1803` | 3.9K | Per-function documentation |
| `docs/functions/enableDisableCruiseControl.md` | `5a138bc22767aaa39b513c56c2e59656100529008f192044e9b1e8822a914f2c` | 1.4K | Per-function documentation |
| `docs/functions/engineControlCalculateTiming.md` | `103d62dfca38286ce15f09f7eacf9c9e4666cc5f90eba14ea791a92a3bbb74c4` | 23.2K | Per-function documentation |
| `docs/functions/engineSpeedInit.md` | `6e88b6c5b1ef043277c1fe73eeede1f05912dc66a39e1eeb8e356305ce9c4f7e` | 1.6K | Per-function documentation |
| `docs/functions/evapRelated.md` | `ee696d3215ef2c7709f3d09c50812eefdbc2f2a667c6f3e7d65ea6a8c870d0f8` | 2.2K | Per-function documentation |
| `docs/functions/faultEnableStatus2.md` | `84a33aff0cc33b9bb07550c33b895f061ff2a655778fcc1bfa77592965a4fabe` | 1.2K | Per-function documentation |
| `docs/functions/faultSomethingIdunno.md` | `5857907ed438cb7bbe789afd7206742a3f221cd0f23454624ec05657dddaa415` | 1.6K | Per-function documentation |
| `docs/functions/floatDivideDiv0errCheck_SIG_DIVISOR.md` | `418416e133089a1a61e3832265f5f71b8ffc844a38ad379fce4218547cd414fe` | 2.3K | Per-function documentation |
| `docs/functions/fuelInjectionRelated.md` | `966ec812e4f39f54c444baec0e136c2ddddbfa9393ed2b58ec11bfabdb228abd` | 2.6K | Per-function documentation |
| `docs/functions/fuelingInit.md` | `ab9a02b0c3655b86e967ee06fefba500afed05315c8e7da533880a44cf45d6c2` | 2.1K | Per-function documentation |
| `docs/functions/fuelingRelatedInitialVals.md` | `debe3c342858d63bf2ef2623272208a19702b9e753db8a9fbc067abc22eddfd1` | 3.0K | Per-function documentation |
| `docs/functions/fuelinjectorSet0.md` | `44335ce670a823ae886f9a7f062b3de684a7e9993a9e77c73de6830073bdc9eb` | 1.5K | Per-function documentation |
| `docs/functions/getACSwitchStatus.md` | `6c2f7584fa53e3250381cb0fe3221d67dd2b210cd3e0c3d44e7ea5be2def4952` | 1.1K | Per-function documentation |
| `docs/functions/getAPVPosVoltage.md` | `92b1a7e7ccd8cc728bf37e2e549851f615c6465b1d992831bbd92cfafcdc6fd5` | 1.5K | Per-function documentation |
| `docs/functions/getAutoTransCal.md` | `78e96caba0cc2c35c9035218eb772a4249858508b7f9d32fe16ee15bde7bdd8c` | 1.0K | Per-function documentation |
| `docs/functions/getBaroSensorVal.md` | `2b91085224079b1e1f632d193aff7605bac9476d2416d725ee869268f67e5dab` | 2.7K | Per-function documentation |
| `docs/functions/getConditionalsForRevLimit.md` | `12805fc973614be48a97f9114f43bbab9f7fb38acb57250990629e6362d2a9a4` | 2.9K | Per-function documentation |
| `docs/functions/getCoolantTempforOBD.md` | `0bb4f28bd71de0db90a6e91547805dd8a79bd05771e8cde0fd12a446774d1374` | 1.5K | Per-function documentation |
| `docs/functions/getCrankAngle.md` | `5fcd8aa4bc4675e2be755980c9aa69856f485ebf26ddda2363ba33808642cc88` | 2.3K | Per-function documentation |
| `docs/functions/getCrankingInjectorPulseTime.md` | `22f7651611f236195f90af75efc5786ec8837681d4d2161c4a60fd04b476644e` | 1.7K | Per-function documentation |
| `docs/functions/getCruiseControlAllowedBool.md` | `54e4f6743ae584ff77c14660b5b589bfa26f8e76f5db902d5277da788905f3ba` | 2.0K | Per-function documentation |
| `docs/functions/getEngineLoadforOBD.md` | `fed60166a2f8df9f2296e018d0eb101179a00fd231b652d6c542d96767f1a8b7` | 2.2K | Per-function documentation |
| `docs/functions/getEngineOffTimer.md` | `2879f374959e4bd9159b39c6a846ff3c1f2a0c391b10c12d7cb22e37ca02c966` | 1.2K | Per-function documentation |
| `docs/functions/getEngineOnTimeForOilMetering.md` | `321c9cb9667b61682b16340084f19841e3c755ddfe3c7ac3636fc0f586c7bb16` | 1.6K | Per-function documentation |
| `docs/functions/getFaultStatus.md` | `833126f94dcadcb521fdb44fbf6924dc0d2dd4d005faea338bc1afad00e0a4df` | 1.5K | Per-function documentation |
| `docs/functions/getFromE2_E2ADDR_RAMADDR_LEN.md` | `9b8a258de4063a2157954934d9d1c76567ff3f8af61a9a36dd9598b2c4af489a` | 4.1K | Per-function documentation |
| `docs/functions/getFromGPIO.md` | `caeb5b483f10eb2bf49391e186b42ac793639521beb74ba7ba3dee211f9244d9` | 1.8K | Per-function documentation |
| `docs/functions/getFuelCutRequestStatus.md` | `fac7be1f8823325f5ec2cb4c6aa4986feb55d5c91bafc0c9988614ddb0480304` | 769B | Per-function documentation |
| `docs/functions/getHCANRegisterAddress.md` | `d45ad8e4b2da5f60cee2010e851b5fa75ea8c0eaf76994b1d3f0c9175666648d` | 1.3K | Per-function documentation |
| `docs/functions/getIATOBD.md` | `4ef139e57779fc76f7cb0603a4a14213334d9b3ecff4dca6a645b05a0678049c` | 1.7K | Per-function documentation |
| `docs/functions/getIgnLeadingOBD.md` | `d86a12c2c680f0a982442c40133b16c67fca2bcc9ed0e92b1855abec239b152d` | 1.6K | Per-function documentation |
| `docs/functions/getIgnitionDwellTime.md` | `5fd5cd004b8f46c79d8513e7fb2e2793010af478561bcb8d1e403305e37ecfd2` | 2.3K | Per-function documentation |
| `docs/functions/getIgnitionRelatedCalsForSomething.md` | `b09a079ab46b8296266edc1d2921cc3952b26cabf2bbb829767e403a97457bb8` | 1.7K | Per-function documentation |
| `docs/functions/getKnockSensorADC.md` | `ce4777090fa32019fbd70ad6470ac9910f0c109185bce117d339de143175bfdd` | 1.7K | Per-function documentation |
| `docs/functions/getKnownBooleanValue.md` | `9f96d2fe9b01ee833616bbd94018e05175f734aecbe4ccf51d8423fa8fd8cfab` | 2.1K | Per-function documentation |
| `docs/functions/getLTFTforOBD.md` | `fb583ea5af0adc2e5198f9f5b761dcd40048c119180377c4cfe5789f88b69b12` | 1.5K | Per-function documentation |
| `docs/functions/getMAFOBD.md` | `a151176783c920627f855fe2bfc5ad62f79c1e996800281bc27f3108287a361b` | 1.9K | Per-function documentation |
| `docs/functions/getMAFSensorValue.md` | `d62587788fbdcc4aa76aeeaf75095d3488f0d1782c692d4f922467d909c038cb` | 1.8K | Per-function documentation |
| `docs/functions/getOBDFuelModificationRequest.md` | `75ff0392ece6286aa6f943c5f3729d84ef43dbada34fa6e40968af0efa62de08` | 2.2K | Per-function documentation |
| `docs/functions/getOLStatusforOBD.md` | `baddcec1c9a40181456921310c3ead71ef8af7b2083a9d9f101d36eaf84768f0` | 2.5K | Per-function documentation |
| `docs/functions/getRearO2Voltage.md` | `9dff92f80141e8fa699ea6fcbf3f5890883f3741829f0e2f9569de50c7fb11f7` | 1.4K | Per-function documentation |
| `docs/functions/getRotorNumberForControl.md` | `f93100d266358a3b831b5613fe8c8ebfb5fc4fe29b1ebc7adfefcb039169ec35` | 1.6K | Per-function documentation |
| `docs/functions/getSR.md` | `3eb1d534ecaf23f02b14ed5316cd15eee67f36e605b4bbf510a61df3e840287a` | 949B | Per-function documentation |
| `docs/functions/getSTFTforOBD.md` | `065fa5e899243ea8f172fb7a67d0f9374baeb1b5a9027364d8a21bff3439e4e2` | 1.7K | Per-function documentation |
| `docs/functions/getSecondaryAirPumpRequestForMode22.md` | `6afacbd185c3e76075cd34e259dddbe249fae689e405eacaaeed596e9b0f558c` | 673B | Per-function documentation |
| `docs/functions/getSensorStuff.md` | `a2261069a69764eb1ad52101476b2caebcb2c1461597769c0157a36b0fe6662c` | 1.9K | Per-function documentation |
| `docs/functions/getSpeedLimitCal.md` | `43bd23fbe5fa8e46d5bd5ccdd0f082bd419ae117bd357d1bffb18fa032d873b7` | 2.3K | Per-function documentation |
| `docs/functions/getThrottlePlatePosForOBD.md` | `0a6bf36c286908772e34ed770e5d461de4ca938fb444237fd3a3c51b187b3890` | 1.1K | Per-function documentation |
| `docs/functions/getfaultstatus.md` | `e579c1068345e76772bee75dc581dfd966a91c452c72447557005472a3addba0` | 1.9K | Per-function documentation |
| `docs/functions/handleDiagInjectorPulse.md` | `233e2366247ebf7abb30587d8be5cd696cb19983f21caca22460a65d22b3fe7d` | 4.7K | Per-function documentation |
| `docs/functions/ignitionCoilPulse.md` | `6299232aca06852aefab59402caac0935010db7216687607e0205e145b859881` | 1.3K | Per-function documentation |
| `docs/functions/ignitionDwellOutputInit.md` | `30cb9267377d05349407294498de63fd1516ff29affb9bca6d3628ba8deac1b0` | 2.8K | Per-function documentation |
| `docs/functions/ignitionTimingHardwareTimerSomething.md` | `bdd170c5a012e2f0f4cb1dab3f7a90e3338a7c0fafc261c51507fc97e11b2bec` | 3.6K | Per-function documentation |
| `docs/functions/ignition_advance_limiter.md` | `37af768707a4b984cc3f2a9f46c1a1f324829c850da8836efe20051f26ec18d0` | 1.2K | Per-function documentation |
| `docs/functions/ignitonSomethingCalc.md` | `fb01f4be77392d81ff48f5646e872de2098adadc4fed5d66806dffe88f39d7e9` | 2.1K | Per-function documentation |
| `docs/functions/initSparkOutput.md` | `e5161948d72f450e394848f5c88be4edf0e8585a8eb66d217dbe5bc95946d589` | 1.9K | Per-function documentation |
| `docs/functions/injectionTiming.md` | `309e27a881909e89a609999ead2c15b660d74b1aad9860a70972d441a125bda0` | 2.4K | Per-function documentation |
| `docs/functions/injectorPulseSet.md` | `c5c0d30acb48a2d17a7b0c31ef3737f2a7be7d1b77f4b2ca9e3837d5f49aef30` | 2.9K | Per-function documentation |
| `docs/functions/injectorRelatedFunc.md` | `16d15400ae68e435426a3e96d8adf87d82351499a8c8ea2d26c3685090659eb2` | 2.8K | Per-function documentation |
| `docs/functions/intToUDS_SERVICE_DATA.md` | `cd9782af7b5c6d0d6d46c30b81c91199601ba7c309cb669b3b62fd351f47c880` | 839B | Per-function documentation |
| `docs/functions/knockFunctionInit.md` | `f568708a95cf291b810eb732073849842ed3e1d9b4cbe04b1a42afe63e74f8a9` | 2.1K | Per-function documentation |
| `docs/functions/knockRelatedInit.md` | `da347d9aa5329036a443e10d6953cb3575ee2ccd917dc889ddacd1298211f858` | 4.0K | Per-function documentation |
| `docs/functions/knockSensorADCFault.md` | `8d0171b933f794b8eec69664c41e3a674226f442f05aeb61097406c74c1a6606` | 2.3K | Per-function documentation |
| `docs/functions/limitKnockRetardMax_ConditonalRPM.md` | `43c58ac7a14c6a3ad82e4541a98bcaaf7228e8ad6a4e81abad87c27c3bad230f` | 2.5K | Per-function documentation |
| `docs/functions/loadStatusRegister_ADDR.md` | `34787fbc5093f251f17051a8a063d2b820e498f5361287c91fa6903a07fc7018` | 501B | Per-function documentation |
| `docs/functions/memcpy_bytewise_unroll4.md` | `adcd4ed4c44d61545210fa0a26aee9b13de0aee3c595bc2d2e1476356fd772de` | 1.2K | Per-function documentation |
| `docs/functions/memory_match_accumulate_583E4.md` | `5956567e2fe617f1320e9a4131ea8924477f3719bd295b8728c09c5151dc1d15` | 3.0K | Tracked file |
| `docs/functions/mod32_signed.md` | `94e08869be6cf31d9e5f1f7747452aea82b32bff6da5ed75baa8b6cb1db9e493` | 1.3K | Per-function documentation |
| `docs/functions/osTaskScheduler.md` | `727836ca633ec1198412564f11a18a5372ee600959a63b3aecd9afdf4199d4e5` | 2.8K | Per-function documentation |
| `docs/functions/outputSpark1.md` | `435400790c2db1545029433f19f547ea70b8b71dec99eba30caaaad3aa4e6c1f` | 3.0K | Per-function documentation |
| `docs/functions/outputSpark2.md` | `adfa4dd330824eeb181d1c2150b592793f789a1d4b7637fd41efd6f47af0ab53` | 2.3K | Per-function documentation |
| `docs/functions/pack_for_OBD_response.md` | `d8329fbd2fd91dbfd748b543844e07bcb36040f66fdf8345df9b2fd2fe057358` | 2.4K | Per-function documentation |
| `docs/functions/pcmBoardTempADCtoVolts.md` | `d1af1803597005bee768e598fa60c59f676726a433502243eb683bef25c3c50f` | 1.6K | Per-function documentation |
| `docs/functions/placeCANRX.md` | `5d767a28343c341d9cf03e283265ec3e5e82bc6f2c18a05a38532c5d377687e4` | 2.0K | Per-function documentation |
| `docs/functions/putFuelingStuffInArray.md` | `2772ace9a8592f11745d10b9d658160fb3c3ea4dfbaab1f7cc704341c77773ae` | 2.9K | Per-function documentation |
| `docs/functions/putTaskInSchedule_FuelArrayStuff.md` | `9146e68baf5eef34b69acf74b27d80ce45ce0447f91776b607b43da67b640b61` | 1.8K | Per-function documentation |
| `docs/functions/reInitCrankSensor.md` | `73d8e81fc8a16b4f3a13cc7bb350798dac60cae3fa8a2ebce209db09fee28920` | 1.9K | Per-function documentation |
| `docs/functions/readADCscoolantTempInHere.md` | `854ddf1a03f798d853f2a2c2193b845c681898341cd3890264a5df205d9fc5b3` | 1.9K | Per-function documentation |
| `docs/functions/readValue_16bit_ADDRESS_VAL.md` | `825264416c43ec2b947821bef421c314589c92c3c6c064b6de2fc9f558397601` | 2.0K | Per-function documentation |
| `docs/functions/readValue_32bit_ADDRESS_VAL.md` | `7e96bb91ad9bd3478ff1cdccdac3372410a1e59cdb05ffcdf26bd069e7959729` | 2.1K | Per-function documentation |
| `docs/functions/readValue_8bit_ADDRESS_VAL.md` | `fe2215fb1339328ff6e2a74f9e284f69e7f779adf1bc0564607a93b87121f93f` | 2.2K | Per-function documentation |
| `docs/functions/readValue_float_DEFAULTVAL_ADDRESS.md` | `7f87c6af12dad34310e9224a649e3428b47765d1ed2078b065df94fa53fe4aaf` | 2.8K | Per-function documentation |
| `docs/functions/reset420CANTimer.md` | `1d574400902cd8f581163c535f3b972a9a6868d5b50d01d80012cd280447209d` | 597B | Per-function documentation |
| `docs/functions/returnCoolantTempGreaterThan71.md` | `cae36880f72beca7fea73184af690c1bf4f18b2e4992e914766150487431bfbc` | 1.2K | Per-function documentation |
| `docs/functions/returnEngineLoad.md` | `d27f13a1f547fa508dc323b4531c13681d33c12822fb1126897372487a42d35d` | 1.0K | Per-function documentation |
| `docs/functions/returnEngineRPM.md` | `61a3528795535708cae7903325b39b8a61b43771abb6239275f0ea8a9379cc40` | 1.1K | Per-function documentation |
| `docs/functions/returnEngineSpeed.md` | `a1ee7a5fb0cf05f93dcbece645282042379c3a8cb686a0ecc43214db7be16c2e` | 989B | Per-function documentation |
| `docs/functions/revLimitFuelCutInit.md` | `ce8cf7f9a1412d5549ab5f0b1ca93db037d5b36baecd3753030167cb8c9f644e` | 1.7K | Per-function documentation |
| `docs/functions/secondaryAirRelated.md` | `f877609ee10dbfe2ddddbd013556d73382b5676f5c39c517af787b5de3fd3ef5` | 1.9K | Per-function documentation |
| `docs/functions/securityNotUnlocked.md` | `69e5379467ea2ad4071a895b3d28904d98866bfbcd4ddcdf3df48addabb4026e` | 1.7K | Per-function documentation |
| `docs/functions/security_access_handler.md` | `c30fdab0a75b8af3d58f7703888ca33f988f14b4708d00c5419eab39c7e31b01` | 12.7K | Per-function documentation |
| `docs/functions/sensorADCRead.md` | `c95ff28e088d871c41ce6e56abfb04e723feef94e9afdd0090ff742bda1ce2fb` | 2.7K | Per-function documentation |
| `docs/functions/sentinel_equality_check_5687A.md` | `dc7074ee67f6a251f94a786aafa7eefe57138bc172a76817545e8e3855eacea3` | 820B | Tracked file |
| `docs/functions/setAlternatorWarningLight.md` | `93fc4ee4a7377256f8c9eac72279a5c8739462936ea230e4e738d8d83d4d93bf` | 2.0K | Per-function documentation |
| `docs/functions/setCANRXBool.md` | `d7c0358eefafe0aea11a3c8791ea4513c36d65281f987c3d5292a81fec720666` | 474B | Per-function documentation |
| `docs/functions/setCANRegisters.md` | `98e3e0b7e4629e7cab2ef675d241b5eb07de9610e93aaae4c2b5a644b700a0f2` | 1.9K | Per-function documentation |
| `docs/functions/setEngineLoadInitalVal.md` | `5c4a9da5409017497e0e5a6b5528a3505c6bc320ec013dec2ccede99b8bc9c6e` | 974B | Per-function documentation |
| `docs/functions/setEngineRunningInjectorsOffFlag.md` | `35ad398c68016e04307e2701473a1610950a504c11852ae459c7ef14182f9f63` | 1.7K | Per-function documentation |
| `docs/functions/setFuelInjectorLatency.md` | `928e872b9d732eb471d892d2df7e5f12b2911aae609cd4f6300929c458691f7e` | 1.9K | Per-function documentation |
| `docs/functions/setImmoCANTXData.md` | `3c2ee756ef498ca6dc758c60b0651318ba4f7cea0dee8b7a3950b737bdfcebe4` | 3.7K | Per-function documentation |
| `docs/functions/setImmoLight.md` | `65b9949fd9b0b3a5741b405874eaf01d3d744fc2ce4069ada458d4ee13b35b98` | 3.1K | Per-function documentation |
| `docs/functions/setMainInitDoneBool.md` | `8bf14a4668d2da2011b9f03a3b920f5c494d72b9327c8c31b604ad8b62432917` | 629B | Per-function documentation |
| `docs/functions/setMemInsideFUNCto1.md` | `bcc2c630ffe669cdcc5d0cc34fe15788c0f37375b6c91627127cdd75621d70bf` | 507B | Per-function documentation |
| `docs/functions/setMessageRXBool.md` | `7893e243ce1747520708ef0617fbd418541b0cab2ff1fab78fa771033ddc9e0f` | 901B | Per-function documentation |
| `docs/functions/setRegister_REG_BIT_VAL.md` | `45747a21f56c250e5c7ed9991c4cc630a3289fc0a2f8855cf5e54f2ff8b22cc0` | 1.1K | Per-function documentation |
| `docs/functions/setSR.md` | `e48d20026436fcb6e8b015c4b061659fbfe4ad4ec8ceadd0b86a3f3bdbff3bba` | 1.2K | Per-function documentation |
| `docs/functions/setSR_PARAM.md` | `745e196f765976f4f5988167d6a7180ba51fccdfaca2cde0429132477007a02c` | 1.1K | Per-function documentation |
| `docs/functions/setStartupInjectorPwMult.md` | `86d015f5220969a63e0cecdcef875199f7bd5cfa2bbb31d13e1b10449a8608df` | 1.7K | Per-function documentation |
| `docs/functions/setTimingArrayValuesForOutput.md` | `2870fb3ed8e5105a9775100ca165e0b75ba5c75d968f539b9890fd108b306527` | 2.2K | Per-function documentation |
| `docs/functions/setupforudsresponse.md` | `7594cefea96e6034630703f7b00ab5982d04bad1245b61c6879656ab40cc226c` | 1.6K | Per-function documentation |
| `docs/functions/shift_left_logical_r0.md` | `1364ee4a72006a1b9e2d904c810fb3a67ea4bed4ddef96d718dfdb1eaa66799f` | 1.5K | Per-function documentation |
| `docs/functions/shift_right_8_r0.md` | `cef21979c7377aeab3ef66a1b7a688535fe3ad22856df1e8f58a0ab034f4abf2` | 996B | Per-function documentation |
| `docs/functions/shift_right_arithmetic_r0.md` | `6273e2db4ed54b0f95734ee40d96013fd03c101b382f020853a1bbb9a80db635` | 2.1K | Per-function documentation |
| `docs/functions/shift_right_logical_r0.md` | `8d9e2923d6b095d7831d5557ac3af130739cdc8df5c3e4d5443d468fd6a53aef` | 1.3K | Per-function documentation |
| `docs/functions/somethingFuelCutRelated.md` | `dd40ac9bd18c42aee28780ec9824ce1f0a6b7cc769d773dfc869f0ebc13a0e15` | 2.7K | Per-function documentation |
| `docs/functions/sourceOf10kReset.md` | `e3be5103903f0587d18e003cf7a9125893dacec0932829330c93a403fbf396a4` | 2.0K | Per-function documentation |
| `docs/functions/ssvControl.md` | `fdfccd44a4bf3d7d8bc3230e28dbc7aa3d8ff7d7ec4c3893ca7b5c2d005bb2c1` | 2.6K | Per-function documentation |
| `docs/functions/store_knock_learn_buffer.md` | `cea595fe9a447b025e481035ea69e14a50ec6e213103fb38cfddad2c50fa784e` | 2.1K | Per-function documentation |
| `docs/functions/taskEndRoutine.md` | `a346ba446e3512a15fefb1a835a8d0120286a88545c13c609416bf7b562e4acf` | 2.8K | Per-function documentation |
| `docs/functions/task_flag_run_C.md` | `5ebf172afa38a4d522d8bde096a309d8c2aba5640818b83d1bd7157e36328238` | 1.1K | Per-function documentation |
| `docs/functions/throttleDownDeFloodCheck.md` | `6b09398e0f6f109f11613bfb55dad33bdbd67ceb0c6dc46164718d70be5e6c74` | 2.8K | Per-function documentation |
| `docs/functions/throttlePedalADCRead.md` | `be157c4ca29569313fc5439593fbaa5edbd2766f77f57eda8473fde747741fa4` | 864B | Per-function documentation |
| `docs/functions/throttlePlateSomethingFuelCut.md` | `053bdb2c4193cffc76b21a0ffbbc7e5ac75eb5b549dd0958f5042cb47fc85228` | 3.2K | Per-function documentation |
| `docs/functions/txCAN_EventBased.md` | `5c07ada8868f0df882a9d40c17140736e7de852fe48342d105f80bd0556d28c3` | 1.8K | Per-function documentation |
| `docs/functions/udsErrorResponse.md` | `1b06fb402ebfb370feeebb5bea6c6b618f0cfff06fc2a541f4073da0b0d3495b` | 929B | Per-function documentation |
| `docs/functions/udserrorresponse.md` | `3fc70dc09ac177df47deeedc610b10f8224d4b6fe2c27c1fb8c8866c3dae660c` | 1.5K | Per-function documentation |
| `docs/functions/udsresponserelated.md` | `d2d37f7a1151c59824b822020cb41026b01d35f64248a566ca1cd542f266650a` | 1.6K | Per-function documentation |
| `docs/functions/udsserviceresponse.md` | `107e6d554553a69e8e89999ab70f67eccc5c049ea3cda3fe611332ab28c2ad02` | 1.3K | Per-function documentation |
| `docs/functions/unknownMode22Func.md` | `465e4687b6160d6eb07aaa0e7a529509a619530c2ac2157aa40478ddf2bc7263` | 4.0K | Per-function documentation |
| `docs/functions/updateE2RAMBasedOnInput.md` | `fc53d623f3adea8d723fb8790d948c8a50deefeaf21b741645b2101845d25170` | 4.0K | Per-function documentation |
| `docs/functions/updateMemoryAtAddress_16bit_ADDR_VAL.md` | `b6d71f0cc66706b8c01f369d4c6fa1868c3619cf7ef588b31758fa72f0ca2505` | 1.3K | Per-function documentation |
| `docs/functions/updateMemoryAtAddress_8bit_ADDR_VAL.md` | `f1aabd0e5df96c7869fa6b445f8311f6b5abb5c3a738e3cbca05e940bd89efe4` | 1.4K | Per-function documentation |
| `docs/functions/updateMemoryAtAddress_float_VAL_ADDR.md` | `2fad86393537236b8e60ffa6ee2132ab009cef8693284c3951647597da50461a` | 2.6K | Per-function documentation |
| `docs/functions/updateRAM.md` | `3f20b93700146b9d1815e147e428f12ae2cb97440406d088ad64d11b3e35321e` | 990B | Per-function documentation |
| `docs/functions/updatefaultstatusthunk.md` | `22207bf4da8a021751ed238e81824eb038a5db830c2497311bdf17e006d059bf` | 986B | Per-function documentation |
| `docs/functions/validateAddressCopy_16bit_ADDRESS.md` | `642641e0b0d86bfd05ce27b9392a3606febb7e179e192cc529e53d92ffe1bbb4` | 1.9K | Per-function documentation |
| `docs/functions/validateAddressCopy_8bit_ADDRESS.md` | `0a013a7a727971f5de6d5c6ae52a6dda1fb0a1341d3e43f7339dd84bb0309a0e` | 2.2K | Per-function documentation |
| `docs/functions/vfadControl.md` | `351e30a7ca3e7ca2df4c3acc519e82185c663f4996bc9fb63f8b734b9ddfe905` | 2.1K | Per-function documentation |
| `docs/functions/vfad_control_35BBC.md` | `c215312724c844497050464850bdab8b8738e8b5578a934a87672f9cc1c086ee` | 2.8K | Per-function documentation |
| `docs/functions/whileLoop.md` | `8e9bf007bc688f0f92c0a0ce4a7323bfe0a3142c848dde91cc10dd2b21f9d3af` | 987B | Per-function documentation |
| `docs/functions/writeO2SensorForApplication.md` | `43ba1bd3b6766f367bb9fc20aa62a62e05eeca9e8339b64b7e8e9594dacfb8d5` | 722B | Per-function documentation |
| `docs/functions/writeToE2RAMArea_INDEX_ADDR_LEN.md` | `3ab88a9c8624dc81588d2fb2bdcc104e3290bf7255a606869a52fd1759c6fd4d` | 2.6K | Per-function documentation |
| `docs/hardware/RX8_OBD_UDS_Protocol.txt` | `db261c038ed6c14c3097588c23fa9efa3563560c749006f363224fb58d012692` | 7.6K | Hardware documentation |
| `docs/hardware/RX8_PCM_Hardware_Reference.txt` | `390d43760c3a511fbe5c29fdc995d59718be19bf620116e12c41753032439556` | 5.4K | Hardware documentation |
| `docs/notes/BOOT_RECOVERY.md` | `cbf923cbb35ac92653635b9077646b7116b87e6e0e764d645dec839ce4c243de` | 5.0K | Project knowledge / session notes |
| `docs/notes/CAN_PROTOCOL.md` | `48de5de5f0871de1d5f2afe5c4ded862016dc097873c0106e403849a766eae77` | 10.2K | Project knowledge / session notes |
| `docs/notes/CONNECTOR_PINOUT.md` | `ffde758d58523046a0e3cbb2e1d5ba75f9f26cb69bef65e579955ecba5bfbc90` | 2.9K | Project knowledge / session notes |
| `docs/notes/COOLING_FANS.md` | `ed52344439aed6750027a5d4efd2df201b43d6f4084b2c9c1feb069c64d6cac6` | 2.2K | Project knowledge / session notes |
| `docs/notes/DUMP_ALL.md` | `b7eb9e1e76917f82576602011d7dd9e369437a7307e9a6769d199650e2085afa` | 7.2K | Project knowledge / session notes |
| `docs/notes/ECU.md` | `f360222d74db6f5c4e3c140d063da6560baa9d59af7949cc6607d5b4b8de0cd7` | 4.6K | Project knowledge / session notes |
| `docs/notes/FINDINGS.md` | `6d6611b996104c1c433f345a1ed56135c2e82ab9b343999e93c14d569a9cae8c` | 43.8K | Project knowledge / session notes |
| `docs/notes/HARDWARE.md` | `0e35f965f143839b8e022a728ecd5cf244358a22b0075f8cb2f3d80dc99febd7` | 7.6K | Project knowledge / session notes |
| `docs/notes/KNOWLEDGE.md` | `9b3a10ce1f1e53f2b5b2d0f6be7e4d56495f55d0f9402e9defad8ccf8f2969e5` | 3.9K | Project knowledge / session notes |
| `docs/notes/LAUNCH_CONTROL_CHECKSUM_GUARD.md` | `a428cbdd11829eb5363f95024fbb63028e890db253537edbae41da523244eff1` | 7.5K | Project knowledge / session notes |
| `docs/notes/RESUME.md` | `32ace9f4bfd8a90dd82cee761ee637ba3662ab9f374d04385f4ce01db40a94c1` | 739B | Project knowledge / session notes |
| `docs/notes/UDS_SECURITY_MAPPING.md` | `942eccd035cbe4542a13794d7e4909bce88760f3d1276e2bee5b0a0ed96dc2ad` | 10.3K | Project knowledge / session notes |
| `docs/subsystems/AUXILIARY_CONTROL_SUBSYSTEM.md` | `016ab6600c1ccaf7010723637411c4667f408ccdf5f458af9a5a589ca1992a7e` | 47.6K | Subsystem / overview documentation |
| `docs/subsystems/BOOT_SEQUENCE.md` | `55816ec71b7304dac859e1a961daf3b2ad6fe5c0a7a5a83838cdce057ff1522b` | 13.4K | Subsystem / overview documentation |
| `docs/subsystems/CALIBRATION_TABLES_CROSS_REFERENCE.md` | `6d82cc7029a8500192b7ed42a9200216259f2f4c88520362b6c795205c7b9a55` | 49.0K | Subsystem / overview documentation |
| `docs/subsystems/CAN_UDS_SUBSYSTEM.md` | `3002dce7cedd8d058419be037bc01b8bfe4f4ed753c82ef098285f30c30ea664` | 44.3K | Subsystem / overview documentation |
| `docs/subsystems/FAULT_DIAGNOSTICS_SUBSYSTEM.md` | `7dc827aa131d5636eb9d86e213546de52fb3f5b25c1395e6f474ee644682001f` | 52.1K | Subsystem / overview documentation |
| `docs/subsystems/FUEL_INJECTION_SUBSYSTEM.md` | `6639c7037baf21c68edbed25e6c2ab6cce061f2efcc3b9fdea09e0d220d38ae8` | 50.2K | Subsystem / overview documentation |
| `docs/subsystems/IDA_NAMES.md` | `5a642eff09cb561624a67f9f8ab2fb6a638a033b2821bb0c8319e6fe1de06124` | 3.2K | Subsystem / overview documentation |
| `docs/subsystems/IGNITION_SUBSYSTEM.md` | `e2bc8150235440ee889e909a3d0ddc9ed8ebb0444686ff9c40e9f3db621db899` | 47.1K | Subsystem / overview documentation |
| `docs/subsystems/MAPS.md` | `e4c035a3991b1e5d191c732659d3c1915419c31f4c30cef6b392a45d4c4794e5` | 37.9K | Subsystem / overview documentation |
| `docs/subsystems/O2_LAMBDA_SUBSYSTEM.md` | `6c6aaa644ed4781226fb63adad90b7ce20853bcf7834d7b7c6471a8ad3fa03b1` | 31.5K | Subsystem / overview documentation |
| `docs/subsystems/OBD_SUBSYSTEM.md` | `61fda3060e2485c84b8a8a9ba09646a5b2c039b36a4438ae4621f8532dd8137a` | 17.1K | Subsystem / overview documentation |
| `docs/subsystems/OVERVIEW.md` | `69115f7a6d04f03910d73090be268d6fc0667ccdd76c04812d19f53b4f464f9f` | 2.4K | Subsystem / overview documentation |
| `docs/subsystems/PID_CONTROLLERS.md` | `0e48f6009c3a2f8e5758eacda1e304f5022fc66fe971d413e5abdbccd4135602` | 11.9K | Subsystem / overview documentation |
| `docs/subsystems/RTOS_SUBSYSTEM.md` | `6b80ff76598216762e93cf2bb90ff1789dcfe05cea01c3fe3873d86c4ca9d116` | 27.8K | Subsystem / overview documentation |
| `docs/subsystems/SENSOR_PIPELINE.md` | `840e7f33acd1d95fdd52f8821477fb3dc24b10c678119c5347790656f0c196ac` | 45.3K | Subsystem / overview documentation |

## hardware

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `hardware/HARDWARE_NOTES.md` | `c9f6dddd9710530855160d0922568701215ca1f4933388a913482c1c4d514182` | 2.0K | Hardware notes / photos / web references |

## web

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `web/explorer/.gitignore` | `9e38f3635d6b89b9d202765b2624d45192da67b8c0c593bfb75c405b070e6a9b` | 66B | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/Makefile` | `db9f6b8a342ee379c193034adaa04bd581a7a2f900c17de78e3850c0a3525cd4` | 2.3K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/README.md` | `c7b8a1a3c5682742ad5c1c9ec134b34dfffffa92fe8f3231f4d963b68e00ab76` | 12.6K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/build_site.py` | `27f6dc2d2d1f598ddd853eaf5e8dad1a2354fc6b6d0562d0cc9021563aa7c308` | 41.9K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/data/MAPPING_NOTES.md` | `e6793bb2e6f74ef4cf194ca3dec9cba81567298751b50cc697f9dd2ffcbc1bf0` | 8.5K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/data/roms_meta.json` | `dad8fd3738c7f3aeaab92fb6879c64a0a84c774784c09805fb0057f05f2631d3` | 6.5K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/data/table_addr_map.csv` | `c5af53244037338661fa54d8223cc92c88efcd8eb7e18b44113ef2338c0204f2` | 169.7K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/data/table_addr_map_long.csv` | `2ef23c561f7c2875a85775eb26e85e10bee2a0f479ba04696cde3297ca988349` | 533.7K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/src/app.js` | `d647e4a51503d4f3bc37a213adbbbabf6a5816ca7b09fb2e1e6e940bee9cfbf3` | 67.8K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/src/index.template.html` | `9b467dca874ee33375bb9bc31600327a473116b31f51301a2f8991a487c3db70` | 10.2K | Web explorer (static firmware browser; see web/explorer/README.md) |
| `web/explorer/src/style.css` | `d553d60f533761bb31da4052294c24ea619c5af423d85d407b271ec9dc6f02aa` | 18.9K | Web explorer (static firmware browser; see web/explorer/README.md) |

## analysis

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `analysis/coverage/REPORT.md` | `c73b567ed2f5bfb1a2a48a5dc6b6a8e84825760b215643e857723f7f9bf72e74` | 9.5K | Coverage analysis of annotated sources (per-ROM gap lists) |
| `analysis/coverage/coverage_gap.py` | `d95e69c88a666a7b986de747b0eb3a64596aa3e078b8d089c07bcf35cb714cb3` | 18.1K | Coverage analysis of annotated sources (per-ROM gap lists) |
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
| `analysis/cruise/REPORT.md` | `cd71a6aceb6d2bb66a971f748bc19e5d0ccb38cf7c66c1ba10697c3d90d62b37` | 13.4K | Analysis report (function identification) |
| `analysis/data_regions_60E1D400.csv` | `a7bd907e6bfa13b8b185728feb00686600e3807725f0a82b844721d982dbf6f9` | 82.8K | Code-window data-region classification |
| `analysis/data_regions_60E1D400.md` | `78b043a94aa066a958de56bded67068102ea7886588dc032ab1f7668d256f176` | 5.5K | Code-window data-region classification |
| `analysis/romdiff/README.md` | `d61c7936f2ad566bbe4ec5066b659d32a5e8eac3bb0987e9b11550f4a04dc7e1` | 1.7K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/REPORT.md` | `f2e9e4c7a269e322cfa92b5df75cacacc0a8203d7da4556355baef584068fadc` | 10.6K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/cal_table_diffs_baseline.csv` | `1950d28497114ce6e3888dcf66f5a47a51f90374a5f1827af08c8385c50328bf` | 610.5K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/clusters.txt` | `3073878cf18f2bbb32163b579c5bd1d5ed92e1b7bb00181219c3335552c90d0d` | 2.5K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/diff_matrix.csv` | `e47dddb705664b858c1e8cb37451d3969679472e0f0ad69fb083697349185285` | 2.0K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/diff_matrix_blocks.csv` | `0755641c44a929669be19a9398058b8afcde1623c5bb98ec613988b060d576a1` | 2.1K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/diff_ranges.csv` | `a377efdfb42286f5ffb9bdddbd98deb8c117ba4eef1e65c9e7434f05338a95c9` | 628.6K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |
| `analysis/romdiff/run_romdiff.py` | `652ff726a1916cea052e3d62c193b6186dc5fdf21fe7e1f06aa4163b64e84aac` | 25.8K | Cross-ROM diff analysis (read-only inputs, see analysis/romdiff/README.md) |

## .github

| Relative path | sha256 | Size | Purpose |
|---|--:|---:|---|
| `.github/requirements.txt` | `2cb78cc09fd13a74714019208e9fecc99de405883c299c6bc0de7aae39709288` | 534B | CI requirements (GitHub Actions) |
| `.github/workflows/README.md` | `4ba420eb633f9177d6a5f5500289c905cfa6b312c4c0e861ad2db6ee93878f6d` | 5.4K | CI documentation (GitHub Actions) |
| `.github/workflows/badges.yml` | `5d6c573f395da94674ca196f2f6ccf78c4908e4c6d91f9f1cc8a54442709c4af` | 1.6K | CI workflow (GitHub Actions) |
| `.github/workflows/ci.yml` | `add9447b75c6290815e2a656da3c508988b62c3a9b8aa2846d8894fb894f0e26` | 5.5K | CI workflow (GitHub Actions) |
| `.github/workflows/pages.yml` | `6ba453cce77ff8dc631d16a30212feecef1cafe766ce9632a60041f7aa03f26c` | 3.0K | CI workflow (GitHub Actions) |

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
| `reconstructed/samples/include/rx8_hw.h` | `fa25d34c3fbb2fd896a7fbddb298ea009f4fb98969b5b8d64f7f93228dfc5634` | 7.6K | Sample shared header (SH7055 hardware access) |
| `reconstructed/samples/src/rx8_2d_lookup_fp_16bit.c` | `da8456de17ec35390f2b28367d5ea4b5444d94a6544ac4109d9edad354ff4ec6` | 5.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_2d_lookup_fp_8bit.c` | `adea7dc501611a5c4eab5ca4bee8016915c43c9c29964571697ceeb0785b7049` | 4.9K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_3d_lookup_fp_16bit.c` | `7084acb1f3dad1f01d31a7b8efef4c41eb202f5eb2152d529f9a707a0c790f4e` | 5.7K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_3d_lookup_fp_8bit.c` | `ec4a14079aff03ee36c7de3ee749f4a3808dc622694fa817e701b051d66326b1` | 5.8K | Reconstructed C source sample (readable, verified lift) |
| `reconstructed/samples/src/rx8_add16bit_saturate.c` | `f3475947cc9366d5c3182ac3cb91c238c637ef0843d2e1aefa17f6447168e1ae` | 3.9K | Reconstructed C source sample (readable, verified lift) |
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

