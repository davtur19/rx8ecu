# Proposta: integrazione CI per la validazione toolchain era-ROM (gcc 3.4.6)

> **Stato:** PROPOSTA — NON applicata. `.github/` è zona calda; questo documento
> è il progetto di riferimento per chi applicherà il job (vedi §10).
> Unico file modificato per questa proposta: questo. Nessun'altra modifica è
> stata fatta.

---

## 1. Contesto e obiettivo

`make verify-gcc346` (in questo `Makefile`, §46-47) chiude il cerchio
comportamentale "ROM → C astratto → toolchain era-ROM": ricompila i sorgenti
reconstructed con **sh-elf gcc 3.4.6** (`-m2e -O1 -fomit-frame-pointer`), linka a
`0x4000`, estrae un blob `.text` con `objcopy` e lo esegue nello **stesso**
emulatore `tools/sh2emu.py` dei byte ROM, confrontando i risultati (r0; effetti
slot per la famiglia RAM). Oggi si esegue **solo locale** perché dipende da
`/home/davide/gcc346-build` (non nel repo) e da binutils sh-elf di sistema.

Obiettivo: portarlo in CI come **job opzionale** `verify-gcc346`, senza toccare
né `verify_gcc346.py` né il CI esistente (proposta = solo questo file).

## 2. Fatti verificati (evidence)

### 2.1 L'harness (`tests/verify_gcc346.py`)

- **Dipendenze Python: solo stdlib** (`os`, `struct`, `subprocess`, `sys`,
  `time`) + moduli del repo `tools/sh2emu.py` (importa solo `struct`) e
  `tests/common.py` (stdlib). **Nessun bisogno di capstone** per questo path.
- **Path hardcoded** (non overridabili via env — vincolo da rispettare in CI):
  - `XGCC   = /home/davide/gcc346-build/gcc/xgcc`
  - `XGCC_B = /home/davide/gcc346-build/gcc`
  - `LIBGCC = <XGCC_B>/libgcc.a`
  - `LD = /usr/bin/sh-elf-ld`, `OBJCOPY = /usr/bin/sh-elf-objcopy`,
    `NM = /usr/bin/sh-elf-nm`
  - `CC_HOST = os.environ.get('CC', 'cc')` (gcc host del runner, ok)
- **ROM richiesta:** `roms/stock/60E1D400.bin` (via `tests/common.py`) —
  committata nel repo, nessuna azione.
- **Exit code:** non-zero **iff** `total > 0`, dove
  `total = Σ(ROM-vs-blob) + Σ(oracle-vs-blob)` (righe 704, 713-715).
  → "fail su mismatch > 0" è il comportamento nativo dell'harness.
- **Tempo misurato locale** (2026-08-02, questo host): **~4.4 s** per tutte le
  14 funzioni / ~68k confronti. Il costo dominante in CI sarà la **build di
  gcc 3.4.6**, non l'harness.

### 2.2 Stub `stdint.h` / `math.h` generati dall'harness (nessun commit necessario)

L'harness è **auto-sufficiente** sui gli header di target: gcc 3.4.6 è stato
configurato `--without-headers`, quindi `ensure_stubs()` (righe 316-324),
chiamato da `main()` prima di ogni funzione, scrive **a runtime** in
`/tmp/verify_gcc346/inc/`:
- `stdint.h` — dalle costanti modulo `_STDINT` (righe 105-118): typedef
  int8/16/32/64, uint*, uintptr_t/intptr_t e i limiti INT*/UINT*;
- `math.h` — da `_MATH` (righe 120-122): prototipo `float fabsf(float)`.

La compilazione usa `-I /tmp/verify_gcc346/inc` (riga 339). **Conseguenza per
CI: gli stub esistono già in `/tmp` al primo run, senza alcun file committato**
— il job non deve generare né committare header di target.

### 2.3 Build locale di gcc 3.4.6 (ricetta esatta, da `config.back`)

```
../gcc-3.4.6/configure --target=sh-elf --prefix=/home/davide/gcc346 \
  --enable-languages=c --without-headers --disable-nls --disable-shared \
  --disable-threads --with-cpu=sh2e
```

- Layout prodotto: `gcc/xgcc`, `gcc/libgcc.a`, `gcc/cc1` (tree di build, ~40 MB).
- Cross-compiler **C-only, non-bootstrap** → build molto più veloce di un GCC
  nativo (stima: 8-15 min su runner 2 vCPU; vedi §8).
- Tarball sorgente: `https://ftp.gnu.org/gnu/gcc/gcc-3.4.6/gcc-3.4.6.tar.bz2`
  (**27 MB**, HTTP 200 verificato 2026-08-02).

### 2.4 CI esistente (`.github/workflows/ci.yml`, SOLO LETTURA)

- `ubuntu-latest` (2 vCPU / 7 GB RAM), `timeout-minutes: 30`, `Python 3.14`
  via `actions/setup-python@v5` + `pip install -r .github/requirements.txt`
  (solo `capstone==5.0.9`).
- Toolchain sh-elf binutils: rootless `./tools/get_toolchain.sh` →
  `tools/toolchain/usr/bin/sh-elf-*`, **non** in `/usr/bin/` → il job gcc346
  non può riusarla così com'è (l'harness vuole `/usr/bin/sh-elf-*`).
- Già presente: `actions/cache@v4` (pip + toolchain), `concurrency`
  cancel-in-progress, `paths-ignore` su `docs/**`, `**/*.md`.
- La ROM è committata; `make verify-all` in CI funziona → `roms/` ok.

---

## 3. YAML proposto (job separato opzionale `verify-gcc346`)

**Scelta:** job **separato** (non step nel job `verify`): ha un costo iniziale
alto (build gcc 3.4.6) e non deve intasare il gate veloce; gira in parallelo
agli altri e fallisce da solo. **Opzionale** con gate di default off.

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

Punti fermi della proposta:

- **`if:` gate** = il modo "opzionale" in GitHub Actions senza toccare la
  matrice esistente. Alternative (segnalate, non nel YAML): `paths:
  reconstructed/samples/**` a livello job (gira solo quando cambiano i samples)
  oppure `continue-on-error: true` per un periodo di prova senza mai bloccare.
- **`actions/cache` su `tools/gcc346-build`**: il cache-hit rende il job
  ~1-2 min (niente build). Chiave manuale `-v1`: va bumpata a mano quando la
  ricetta cambia (più robusto di `hashFiles` sul workflow, che cambierebbe a
  ogni edit non correlato).
- **Binutils in `/usr/bin/` via `sudo apt-get install -y binutils-sh-elf`**
  (package presente in Ubuntu/Debian; è lo stesso che `tools/get_toolchain.sh`
  scarica con `apt-get download`). Alternativa senza root: `sudo ln -sfn`
  dei tre binari da `tools/toolchain/usr/bin` — ma l'apt è una riga.
- **Symlink `/home/davide/gcc346-build`** → workspace: rispetta i path
  hardcoded dell'harness SENZA modificarlo e mantiene la dir di build
  cacheabile. `sudo` è disponibile e non serve password su `ubuntu-latest`.
- **Nessun header da committare**: gli stub `stdint.h`/`math.h` li genera
  l'harness in `/tmp/verify_gcc346/inc` (§2.2).

---

## 4. Soglie / pass/fail

- **Fail del job** se `make verify-gcc346` esce != 0, cioè se l'harness stampa
  `N mismatch(es) total — FAIL` (`total > 0`, righe 713-715).
- **Fail rapido** su prerequisiti (fast-fail esplicito negli step): symlink
  assente, `xgcc --version` fallito, `/usr/bin/sh-elf-ld` assente.
- Il passo `make verify-gcc346` **non** usa `continue-on-error`: un mismatch
  ROM-vs-blob significa che il C reconstructed NON è equivalente sotto la
  toolchain era-ROM → va bloccato. L'"opzionalità" sta nel gate del job (§3),
  non nel sopprimere l'esito.

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

`timeout-minutes: 30` copre agevolmente anche il cold più lento.

---

## 6. Artifact prebuildato vs build da sorgente — valutazione e raccomandazione

### Opzione A — Build da sorgente in CI + cache (RACCOMANDATA)
- **Pro:** riproducibile e verificabile dal repo (nessun binario fidato
  esterno); segue la convenzione del progetto (get_toolchain.sh: install rootless,
  deterministica); niente passo manuale di upload; il confronto finale è SEMPRE
  contro i byte della ROM, quindi una eventuale deriva della build locale
  verrebbe comunque evidenziata dal job.
- **Contro:** primo run 8-15 min (mitigato: cache ⇒ ~1-2 min dopo); dipende da
  ftp.gnu.org al primo run.

### Opzione B — Artifact binario (build locale → upload a GitHub Releases/Artifacts)
- **Pro:** job veloce fin da subito (~1-2 min).
- **Contro:** introduce un **trust boundary** (chi ha buildato? il binario non
  è verificabile dal repo); serve un passo manuale di manutenzione a ogni
  cambio ricetta; il repo perde l'autosufficienza; ~40 MB da gestire.

**Raccomandazione: Opzione A** (build da sorgente con cache), perché è coerente
con la cultura evidence-based del repo (AGENTS.md) e con il metodo CI già
adottato per binutils. L'Opzione B è un fallback ragionevole solo se il primo
cold build in PR risultasse troppo lento per i revisori (in tal caso: un run
manuale `workflow_dispatch` a monte popola la cache e il PR diventa warm).

---

## 7. Rischi e mitigazioni

| Rischio | Impatto | Mitigazione |
|---|---|---|
| **RAM/CPU runner**: 2 vCPU / 7 GB; build gcc 3.4.6 C-only non-bootstrap | Basso: picco RAM ~0.5-1 GB, `-j2` | `timeout-minutes: 30`; nessuna flag esotica |
| **Rete ftp.gnu.org**: 27 MB, talvolta lenta/throttled | Medio al primo run | HTTPS (non ftp://), `curl --retry 3 --retry-all-errors`; mirror fallback (es. `https://mirrors.kernel.org/gnu/gcc/...`); `actions/cache` ⇒ download raro |
| **Differenze versione gcc buildato** vs `/home/davide/gcc346-build` | Basso | Ricetta **pinnata** (stesso tarball + stessi flag configure, §2.3); cross C-only non-bootstrap ⇒ codegen sh-elf determinista anche con host gcc moderno; il verdetto è vs ROM, non vs binario locale. Possibili dep mancanti (`makeinfo`/texinfo) → aggiungere `texinfo` all'apt se il cold build fallisce sui docs |
| **Version drift binutils sh-elf apt** (es. 2.42 su Ubuntu 24.04 vs 2.46 locale) | Trascurabile | `ld`/`objcopy`/`nm` servono solo per layout blob a `LINK_BASE` fisso e simboli via `nm`; la verifica è comportamentale, non byte-exact |
| **Path hardcoded dell'harness** | Medio (fast-fail evidente) | Symlink esplicito (step dedicato) + `test -x/-f` di sanità prima dell'harness; follow-up: rendere `XGCC`/`LD`/… overridabili via env (fuori scope di questa proposta) |
| **Runner `fork` / permissions** | Basso | `permissions: contents: read` già a livello workflow; `sudo apt`/`sudo ln` funzionano su ubuntu-latest senza segreti |
| **Gate "opzionale" ignorato dai revisori** | Organizzativo | Documentare qui e nel README del CI; esito è comunque visibile nelle checks dei PR etichettati `[gcc346]` |

---

## 8. Follow-up consigliati (NON in scope — richiedono altre modifiche)

1. Aggiungere `tools/gcc346-build/` a `.gitignore` (root) prima di applicare il
   job (la dir di build è dentro il workspace).
2. Promuovere il fix `xtrct` da monkeypatch di `verify_gcc346.py` a
   `tools/sh2emu.py` (già annotato in README §5) — riduce il rischio che il
   patch non venga applicato in futuro.
3. Rendere i path toolchain dell'harness overridabili via env (rimuove il
   bisogno del symlink `/home/davide`).
4. Aggiornare `.github/workflows/README.md` con la riga del nuovo job.

---

## 9. Riepilogo esecutivo

- **Job:** `verify-gcc346` separato e **opzionale** (workflow_dispatch / tag
  `[gcc346]` / variabile `ENABLE_GCC346`), `ubuntu-latest`, `timeout 30 min`.
- **Dipendenze:** Python 3.14 + capstone (solo per coerenza col resto del CI;
  l'harness non ne ha bisogno), binutils `binutils-sh-elf` via apt (path
  `/usr/bin/` richiesto dall'harness), gcc 3.4.6 **buildato da sorgente**
  con la ricetta esatta di `config.back` e **cacheato** in `tools/gcc346-build`
  (symlink su `/home/davide/gcc346-build` per i path hardcoded).
- **Stub stdint/math:** generati a runtime dall'harness in `/tmp` (§2.2) —
  nessun commit.
- **Soglie:** fail su qualsiasi `mismatch > 0` (exit code nativo dell'harness).
- **Tempi:** ~10-17 min cold, **~1-2 min** con cache; harness misurato 4.4 s.
- **Rischi principali:** primo download da ftp.gnu.org (mitigato: HTTPS+retry+
  cache), drift versione binutils apt (irrilevante: verifica comportamentale),
  path hardcoded (mitigato: symlink + sanity check).
- **Raccomandazione:** **build da sorgente + cache** (Opzione A), non artifact.
