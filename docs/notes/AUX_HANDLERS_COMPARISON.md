# Auxiliary Bank UDS Handler — Entry-Dispatch Comparison

<!-- IN PROGRESS -->

Status: **IN PROGRESS** — analysis shell; full evidence to be filled in.

Scope: compare the UDS SecurityAccess (SID 0x27) handler entry-dispatch of the
8 auxiliary ROM images against the 60E1D400 baseline:

| # | ROM | handler entry (VA) |
|---|-----|--------------------|
| 0 | 60E1D400 (baseline) | 0x584A0 |
| 1 | 60E0E500 | (pending) |
| 2 | 60E0E700_N3YLEE | (pending) |
| 3 | 60E0FB00 | (pending) |
| 4 | 60E0FC00 | (pending) |
| 5 | 60E15120_N3J1E | (pending) |
| 6 | 60E1B900 | (pending) |
| 7 | 60E1C500_N3J6EB | (pending) |
| 8 | 60E32000_N3M5E | (pending) |

Deliverables: this document + `c/security_access_aux.c` (evidence-based C
reconstruction of the aux entry dispatch).
