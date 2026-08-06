# RX-8 ECU Reverse Engineering — Session Resume

> Sezioni 1–9: stato pre-release (giugno 2026), superate dalla release 486c7d6 — vedi VERIFICATION.md.

## 10. Final status (post-release)

- **Release completata** (commit 486c7d6, AGPL-3.0, repo pubblico): pipeline rebuild byte-exact, sorgenti annotati, C lifts verificati, test, tools, docs, 9 ROM stock pubbliche.
- **9/9 ROM byte-identiche**: `make verify-all` → `sha256(rebuilt) == sha256(source)`; immagini modificate e dump privati fuori dal repo (README, "Legal notice").
- Numeri correnti (coverage, test, indirizzi verificati, C lifts) ed evidenze: **README.md** + **VERIFICATION.md** — non duplicati qui.