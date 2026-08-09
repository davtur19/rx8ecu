# Proposta: integrazione CI per la validazione toolchain era-ROM (gcc 3.4.6)

> **Stato:** PROPOSTA — NON applicata. `.github/` è zona calda; riferimento per
> chi applicherà il job (§3). Unico file modificato per questa proposta: questo.

---

## 1. Contesto e obiettivo

`make verify-gcc346` (§46-47 di questo `Makefile`): ricompila con **sh-elf gcc
3.4.6** (`-m2e -O1 -fomit-frame-pointer`), linka a `0x4000`, estrae un blob
`.text` con `objcopy`, lo esegue nello **stesso** emulatore `tools/sh2emu.py`
dei byte ROM (r0; effetti slot RAM). Oggi **solo locale** (dipende da
`/home/davide/gcc346-build` e binutils sh-elf). Obiettivo: job CI **opzionale**
`verify-gcc346`, senza toccare `verify_gcc346.py` né il CI esistente.

## 2. Fatti verificati (evidence)

### 2.1 Harness (`tests/verify_gcc346.py`)

- **Dipendenze: solo stdlib** (`os`, `struct`, `subprocess`, `sys`, `time`) +
  `tools/sh2emu.py` (solo `struct`), `tests/common.py`. **Nessun capstone.**
- **Path hardcoded** (non overridabili): `XGCC=/home/davide/gcc346-build/gcc/xgcc`,
  `LIBGCC=<XGCC_B>/libgcc.a`, `XGCC_B=/home/davide/gcc346-build/gcc`,
  `LD/OBJCOPY/NM=/usr/bin/sh-elf-{ld,objcopy,nm}`, `CC_HOST=os.environ.get('CC','cc')`.
- **ROM:** `roms/stock/60E1D400.bin` (tramite `tests/common.py`) — committata.
- **Exit:** non-zero **iff** `total > 0` (`Σ(ROM-vs-blob)+Σ(oracle-vs-blob)`,
  righe 704, 713-715) → fail su mismatch > 0 è nativo.
- **Tempo locale** (2026-08-02): **~4.4 s** (14 fcn / ~68k confronti). Costo
  dominante in CI: la **build di gcc 3.4.6**.

### 2.2 Stub `stdint.h`/`math.h` (nessun commit)

gcc `--without-headers`; `ensure_stubs()` (righe 316-324) scrive a runtime in
`/tmp/verify_gcc346/inc/`: `stdint.h` da `_STDINT` (105-118), `math.h` da `_MATH`
(120-122: `float fabsf(float)`); `-I /tmp/verify_gcc346/inc` (339). **Conseguenza
CI: niente header da committare.**

### 2.3 Build locale gcc 3.4.6 (ricetta da `config.back`)

```
../gcc-3.4.6/configure --target=sh-elf --prefix=/home/davide/gcc346 \
  --enable-languages=c --without-headers --disable-nls --disable-shared \
  --disable-threads --with-cpu=sh2e
```

Layout: `gcc/xgcc`, `gcc/libgcc.a`, `gcc/cc1` (~40 MB). C-only non-bootstrap →
8-15 min su 2 vCPU (§8). Tarball:
`https://ftp.gnu.org/gnu/gcc/gcc-3.4.6/gcc-3.4.6.tar.bz2` (**27 MB**, HTTP 200
2026-08-02).

### 2.4 CI esistente (`.github/workflows/ci.yml`, SOLO LETTURA)

- `ubuntu-latest` (2 vCPU / 7 GB), `timeout-minutes: 30`, `Python 3.14`
  (`setup-python@v5`) + `pip install -r .github/requirements.txt` (solo
  `capstone==5.0.9`).
- Binutils rootless `./tools/get_toolchain.sh` → `tools/toolchain/usr/bin/sh-elf-*`,
  **non** `/usr/bin/` → non riusabile dall'harness.
- Già presenti: `actions/cache@v4` (pip+toolchain), `concurrency`, `paths-ignore`
  su `docs/**`, `**/*.md`. ROM committata.

---

## 3. YAML proposto (job separato opzionale `verify-gcc346`)

Job **separato** (non step nel job `verify`): costo iniziale alto, non intasa il
gate veloce; fallisce da solo. **Opzionale**, gate di default off.

```yaml
  # ---------------------------------------------------------------------------
  # verify-gcc346: era-ROM toolchain validation (sh-elf gcc 3.4.6).
  # Rebuilds reconstructed/samples with gcc 3.4.6 (-m2e -O1 -fomit-frame-pointer),
  # links at 0x4000 and compares ROM bytes vs gcc-3.4.6 blobs in the same SH-2E
  # emulator (make verify-gcc346). OPTIONAL: off by default (workflow_dispatch /
  # commit-message tag / repo variable ENABLE_GCC346=true). The cold gcc-3.4.6
  # build takes ~8-15 min once; the built tree is cached (key: gcc346-...-v1).
  # ---------------------------------------------------------------------------
  verify-gcc346:
    name: Verify (gcc 3.4.6 era toolchain)
    runs-on: ubuntu-latest
    timeout-minutes: 30
    # Optional: manual dispatch, PR/push tagged [gcc346], or ENABLE_GCC346=true
    # set as a repo/org variable (flip to permanent once stable).
    if: >-
      github.event_name == 'workflow_dispatch'
      || vars.ENABLE_GCC346 == 'true'
      || contains(github.event.head_commit.message, '[gcc346]')
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python ${{ env.PYTHON_VERSION }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
          cache-dependency-path: .github/requirements.txt

      - name: Install Python deps (capstone)
        run: python3 -m pip install --break-system-packages -r .github/requirements.txt

      # verify_gcc346.py calls /usr/bin/sh-elf-{ld,objcopy,nm} directly
      # (hardcoded), so the system package (not tools/toolchain) is required.
      - name: Install sh-elf binutils (system-wide /usr/bin)
        run: |
          sudo apt-get update
          sudo apt-get install -y binutils-sh-elf
          /usr/bin/sh-elf-ld --version | head -1

      - name: Cache gcc 3.4.6 cross build
        id: gcc346-cache
        uses: actions/cache@v4
        with:
          path: tools/gcc346-build
          key: gcc346-${{ runner.os }}-v1
          restore-keys: |
            gcc346-${{ runner.os }}-

      # Cold build (cache miss): same recipe as the local /home/davide/gcc346-build
      # (see config.back). C-only, non-bootstrap, -j2 for the 2-vCPU runner.
      - name: Build gcc 3.4.6 (sh-elf cross, C-only)
        if: steps.gcc346-cache.outputs.cache-hit != 'true'
        run: |
          set -euo pipefail
          curl -fsSL --retry 3 --retry-all-errors \
            -o /tmp/gcc-3.4.6.tar.bz2 \
            https://ftp.gnu.org/gnu/gcc/gcc-3.4.6/gcc-3.4.6.tar.bz2
          tar -xjf /tmp/gcc-3.4.6.tar.bz2 -C /tmp
          mkdir -p tools/gcc346-build
          cd tools/gcc346-build
          /tmp/gcc-3.4.6/configure \
            --target=sh-elf --prefix=/home/davide/gcc346 \
            --enable-languages=c --without-headers \
            --disable-nls --disable-shared --disable-threads \
            --with-cpu=sh2e
          make -j2

      # verify_gcc346.py hardcodes /home/davide/gcc346-build/gcc/{xgcc,libgcc.a}
      # (read-only reference; must not be edited in this proposal). Build inside
      # the workspace (cache-friendly) and expose it via a symlink.
      - name: Symlink toolchain to the harness's hardcoded path
        run: |
          sudo mkdir -p /home/davide
          sudo ln -sfn "$PWD/tools/gcc346-build" /home/davide/gcc346-build
          test -x /home/davide/gcc346-build/gcc/xgcc
          test -f /home/davide/gcc346-build/gcc/libgcc.a
          /home/davide/gcc346-build/gcc/xgcc --version | head -1

      # 14 functions / ~68k comparisons, ~5 s runtime.
      - name: make verify-gcc346 (fail on any mismatch)
        working-directory: reconstructed/samples
        run: make verify-gcc346
```

Punti fermi: **`if:` gate** = opzionalità. **Cache su `tools/gcc346-build`**
(cache-hit ~1-2 min; chiave `-v1` manuale). **Binutils tramite apt**
(`binutils-sh-elf`). **Symlink `/home/davide/gcc346-build`** → rispetta i path
hardcoded, dir cacheabile. **Nessun header committato** (§2.2).

---

## 4. Soglie / pass-fail

- **Fail del job** se `make verify-gcc346` != 0, cioè `N mismatch(es) total —
  FAIL` (`total > 0`, righe 713-715).
- **Fail rapido**: symlink assente, `xgcc --version` fallito, `/usr/bin/sh-elf-ld`
  assente.
- **Niente `continue-on-error`**: mismatch ROM-vs-blob = C NON equivalente → va
  bloccato. Opzionalità solo nel gate (§3).

---

## 5. Tempo stimato (runner `ubuntu-latest`, 2 vCPU)

| Step | Tempo |
|---|---|
| Checkout | ~10 s |
| setup-python + pip (capstone) | ~20-30 s |
| `apt-get install binutils-sh-elf` | ~30-60 s |
| Build gcc 3.4.6 (cache miss, cold) | **8-15 min** |
| `actions/cache` restore (cache hit) | ~5-15 s |
| `make verify-gcc346` (misurato: 4.4 s locale) | ~5-10 s |
| **Totale cold (primo run)** | **~10-17 min** |
| **Totale warm (cache hit)** | **~1-2 min** |

`timeout-minutes: 30` copre anche il cold più lento.

---

## 6. Artifact prebuildato vs build da sorgente

- **A — Build da sorgente + cache (RACCOMANDATA):** riproducibile dal repo,
  segue get_toolchain.sh, nessun upload, confronto sempre vs byte ROM. Contro:
  primo run 8-15 min (cache ⇒ ~1-2 min); dipende da ftp.gnu.org.
- **B — Artifact binario (→ Releases/Artifacts):** veloce da subito. Contro:
  **trust boundary**, manutenzione per cambio ricetta, repo perde autosufficienza,
  ~40 MB.

**Raccomandazione: A** (coerente con AGENTS.md). B = fallback se il primo cold
build in PR fosse troppo lento (un run `workflow_dispatch` popola la cache).

---

## 7. Rischi e mitigazioni

| Rischio | Impatto | Mitigazione |
|---|---|---|
| **RAM/CPU runner**: 2 vCPU / 7 GB; build C-only non-bootstrap | Basso: picco RAM ~0.5-1 GB, `-j2` | `timeout-minutes: 30`; nessuna flag esotica |
| **Rete ftp.gnu.org**: 27 MB, talvolta lenta | Medio al primo run | HTTPS, `curl --retry 3 --retry-all-errors`; mirror fallback (`https://mirrors.kernel.org/gnu/gcc/...`); cache ⇒ download raro |
| **Differenze versione gcc buildato** | Basso | Ricetta **pinnata** (§2.3); codegen determinista; verdetto vs ROM. Dep mancanti (`texinfo`) → aggiungere all'apt |
| **Version drift binutils apt** (2.42 vs 2.46) | Trascurabile | `ld`/`objcopy`/`nm` solo per layout blob a `LINK_BASE` fisso e simboli; verifica comportamentale |
| **Path hardcoded dell'harness** | Medio (fast-fail evidente) | Symlink esplicito + `test -x/-f`; follow-up: env overrides (fuori scope) |
| **Runner `fork` / permissions** | Basso | `permissions: contents: read`; `sudo apt`/`sudo ln` senza segreti |
| **Gate opzionale ignorato dai revisori** | Organizzativo | Documentare qui e nel README del CI; esito visibile nei PR `[gcc346]` |

---

## 8. Follow-up (NON in scope)

1. `tools/gcc346-build/` in `.gitignore` (root).
2. Promuovere il fix `xtrct` da monkeypatch a `tools/sh2emu.py` (README §5).
3. Path toolchain overridabili tramite env (rimuove il symlink `/home/davide`).
4. Aggiornare `.github/workflows/README.md` col nuovo job.

---

## 9. Riepilogo esecutivo

- **Job:** `verify-gcc346` separato, **opzionale** (workflow_dispatch / `[gcc346]`
  / `ENABLE_GCC346`), `ubuntu-latest`, `timeout 30 min`.
- **Dipendenze:** Python 3.14 + capstone (coerenza CI), `binutils-sh-elf` apt,
  gcc 3.4.6 **da sorgente** (ricetta `config.back`) **cacheato** in
  `tools/gcc346-build` (symlink `/home/davide/gcc346-build`).
- **Stub:** runtime in `/tmp` (§2.2) — nessun commit.
- **Soglie:** fail su `mismatch > 0` (exit nativo). **Tempi:** ~10-17 min cold,
  ~1-2 min warm; harness 4.4 s.
- **Raccomandazione:** **build da sorgente + cache** (Opzione A).
