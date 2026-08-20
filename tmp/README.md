# tmp/ — tabella di promozione

Nuovi artefatti vanno prima in `tmp/<topic>/`. Questa tabella definisce cosa
tenere, cosa promuovere e cosa scartare. Regola generale (AGENTS.md): nuovi
artefatti → `tmp/<topic>/`; promozione solo quando l'artefatto è maturo e
riusabile fuori dal flusso di lavoro corrente.

## Tabella di promozione

| Artefatto | Stato | Decisione |
|---|---|---|
| `tmp/ida/make_elf.py` | **keep in tmp** | Script di build per la configurazione canonica ELF big-endian (`60E1D400_be.elf`), citato da `docs/notes/IDA_ANALYSIS.md`. La promozione a `tools/` è opzionale: è deterministico, ha `assert` sulle dimensioni ed è riusabile per ricostruire il file se serve. |
| `tmp/ida/60E1D400_be.elf` | **keep in tmp** | Configurazione canonica IDA (ELF BE con ROM + RAM + periferiche). È un artefatto di lavoro, non un tool: resta in tmp. |
| `tmp/ida/60E1D400_bswap.bin` + `tmp/ida/swap16.py` | **keep in tmp** | Configurazione superseded (workaround word-swap). Tenere per storia/confronto, NON promuovere. |
| `tmp/ida/test_sh4.bin` (+ `.i64`) | **discard** | File di test per il probing dei loader SH. Nessun valore durevole. |
| `tmp/ida/uds_obd_analysis.md` | **keep in tmp** | Analisi UDS/OBD complementare a `docs/notes/IDA_ANALYSIS.md` e `docs/notes/CAN_PROTOCOL.md`. |
| `tmp/ida/chunks/` | **keep in tmp** | Chunk dell'import simboli (codearr_*/def_*/ren_*). Necessari per riprodurre o estendere l'import. |
| `tmp/ida/reimport_report.txt` + `name_verify_report.txt` + `manual_names.txt` | **keep in tmp** | Report verificati dell'import simboli e della verifica nomi manuali; citati in `docs/notes/IDA_ANALYSIS.md`. |