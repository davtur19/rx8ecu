# RX-8 ECU Reverse Engineering — Session Resume

> Sections 1 to 9 describe the pre-release state (June 2026). Release 486c7d6 supersedes them. See VERIFICATION.md.

## 10. Final status (post-release)

- **Release complete** (commit 486c7d6, AGPL-3.0, public repo). It contains: the byte-exact rebuild pipeline, the annotated sources, the verified C lifts, the tests, the tools, the docs, and 9 public stock ROMs.
- **9/9 ROMs byte-identical**: `make verify-all` → `sha256(rebuilt) == sha256(source)`; modified images and private dumps stay out of the repo (README, "Legal notice").
- Current numbers (coverage, tests, verified addresses, C lifts) and evidence: **README.md** + **VERIFICATION.md** — not duplicated here.