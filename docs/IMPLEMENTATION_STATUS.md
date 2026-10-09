# IMPLEMENTATION_STATUS — Detect A Clip

Statuses: NOT_STARTED · IN_PROGRESS · IMPLEMENTED_NOT_VERIFIED · PASS · FAIL · BLOCKED ·
INCONCLUSIVE · DEFERRED · UNVERIFIED. PASS rows cite evidence in `docs/TEST_EVIDENCE.md`.
"Compiled on the JVM" means pure-Kotlin files only, never the Android app.

Tracks: **DESKTOP-L0** (Python harness) · **ANDROID** · **IOS**.

## What exists, by platform (2026-10-09)

| Platform | Works now | Not verified / missing |
|---|---|---|
| Desktop L0 | Synthetic fixtures v3.1 with challenge cases; descriptors (24/48/160/528 B); index builder and bounded parser; temporal verification; series/episode-aware decision; calibration; signed UNCALIBRATED/L0-calibrated packs; atomic pack store; lab leases; LAB runner. 115 tests | Real footage, real devices, release statistics |
| Android | Source for LAB app: no INTERNET, capture off by default, mediaProjection FGS adapter, pure-Kotlin coordinator, lifecycle, consent records, eligibility gate. 35 JVM tests pass (incl. bit-exact recognition, descriptor, exact-path and end-to-end golden tests) | Android compile (B-09), any device run (B-01), CAP-A03 source restriction |
| iOS | Swift sources for coordinator, frame selector, lifecycle with background-task guard, consent/eligibility, ScreenCaptureKit adapter skeleton, XCTests | Any compile or test (B-02) |

## Task register (86 tasks)

| Task | Status | Evidence / note |
|---|---|---|
| P00-T01 | PASS | `docs/ENVIRONMENT.md`, `docs/SDK_MATRIX.md` toolchain table |
| P00-T02 | UNVERIFIED | `docs/SDK_MATRIX.md`: documented only; installed/measured need B-09/B-02 |
| P00-T03 | BLOCKED | B-03 |
| P00-T04 | BLOCKED | B-04 |
| P00-T05 | BLOCKED | B-05 |
| P00-T06 | IMPLEMENTED_NOT_VERIFIED | THREAT_MODEL, CTRL-G00 checklist, DPIA screening drafts; reviewer sign-off missing |
| P00-T07 | IMPLEMENTED_NOT_VERIFIED | fixtures v3.1, asset/rights manifests; rights-reviewer sign-off missing |
| P00-T08 | PASS (L0 exploratory protocol) | EVAL_PROTOCOL, preregistered scoring/calibration, sealed FINAL; independent AI-06 setup review missing |
| P00-T09 | PASS (document level) | TRACE-01 |
| P01-T01 | IMPLEMENTED_NOT_VERIFIED | Part A source items done; Android compile + merged-manifest check BLOCKED (B-09); signed Part A BLOCKED (B-01) |
| P01-T02…T08 | BLOCKED | B-01, B-09. Lifecycle races covered on JVM only |
| P02-T01 | UNVERIFIED | documentary symbol review in SDK_MATRIX; headers need Mac (B-02) |
| P02-T02…T06 | BLOCKED | B-02; Swift sources prepared |
| P03-T01 | IMPLEMENTED_NOT_VERIFIED | work/edition/series/episode IDs (idx-flat-2); alias tables not built |
| P03-T02 | BLOCKED | B-05 (L0 self-grant manifest exists) |
| P03-T03 | PASS (desktop) | reproducible builder, bytes/hour per descriptor |
| P03-T04 | PASS (L0 dev scope) | signed manifest, fail-closed loader, SEC-01 |
| P03-T05 | BLOCKED | B-05 |
| P03-T06 | IMPLEMENTED_NOT_VERIFIED (dev fixtures) | atomic store, epoch marker, lab leases; licensed/final-tuple part BLOCKED (B-05) |
| P03-T07 | BLOCKED | B-05 |
| P04-T01 | IMPLEMENTED_NOT_VERIFIED | quality flags, uniform-border crop; device frames BLOCKED |
| P04-T02 | PASS (LAB) | 4 descriptors; sampling study (DEV) in `evidence/studies/` |
| P04-T03 | PASS (LAB, exploratory) | temporal verification, montage segments, recaps, stock footage |
| P04-T04 | IN_PROGRESS | series→episode→edition→time hierarchy done; multilingual names not built |
| P04-T05 | PASS (L0 synthetic calibration) | v3.1 (CALIBRATION) and v4 (CAL4) frozen per descriptor; LAB-only status |
| P04-T06 | PASS (LAB) | all kinds incl. leakage audit; sealed FINAL (v3.1) and FINAL4 (v4) each run once; failures kept in reports |
| P04-T07 | BLOCKED | independent evaluator (B-06) |
| P04-T08 | BLOCKED (device) · prep IMPLEMENTED | Kotlin recognition port bit-exact vs Python (400 golden cases); DAC-DHASH-v1 exact descriptor (Python = Kotlin); device budgets need B-01/B-02/B-07 |
| P05-T01 | IMPLEMENTED_NOT_VERIFIED | `docs/legal/*` DRAFT_FOR_COUNSEL; legal review required |
| P05-T02 | IMPLEMENTED_NOT_VERIFIED | `ConsentRecords` (JVM-tested); Android UI uncompiled |
| P05-T03 | IMPLEMENTED_NOT_VERIFIED | native picker from user action; `EligibilityGate` (JVM-tested) |
| P05-T04 | IMPLEMENTED_NOT_VERIFIED | canonical states, uncertain-result wording, memory-only result |
| P05-T05 | IMPLEMENTED_NOT_VERIFIED | in-app Stop/Cancel, notification Stop→Cancel switch; UX-02 device runs BLOCKED |
| P05-T06 | IMPLEMENTED_NOT_VERIFIED | decline/changed-terms/late-callback logic tested on JVM |
| P05-T07 | BLOCKED | accessibility review needs device; study needs D04 |
| P06-T01 | IN_PROGRESS | threat model draft; actual API path evidence BLOCKED |
| P06-T02 | PASS (harness) | lease/generation/race tests (Python + Kotlin) |
| P06-T03 | IMPLEMENTED_NOT_VERIFIED | no logs/SDKs/backups in source; DATA-L02 device inspection BLOCKED |
| P06-T04 | BLOCKED | device soak |
| P06-T05 | IN_PROGRESS | SBOM; bounded parsers; release signing not designed |
| P06-T06 | IMPLEMENTED_NOT_VERIFIED | cell/pack expiry and untrusted-time denial (JVM + Python) |
| P06-T07 | IMPLEMENTED_NOT_VERIFIED | data inventory in THREAT_MODEL/privacy draft; counsel BLOCKED |
| P06-T08 | BLOCKED | independent reviewer |
| P07-T01…T07 | BLOCKED | B-03 + native gates; Snapchat OFF |
| P08-T01…T07 | BLOCKED | B-05 |
| P09-T01…T07 | BLOCKED | D04 / B-04 |
| P10-T01…T06 | BLOCKED | B-08 |
| P11-T01…T06 | DEFERRED | roadmap |

## Gates

| Gate | Status |
|---|---|
| G00 desktop | Engineering items ready; named reviewer sign-off missing (D5 in CTRL-G00) |
| G00 Android / iOS | BLOCKED (B-01/B-09, B-02) |
| G01 / G02 | BLOCKED |
| G03-L0 | Engineering items ready; rights-reviewer sign-off of the synthetic self-grant missing |
| G03-L1 | BLOCKED (B-05) |
| G04 | LAB record exists (fixtures v3.1 FINAL); RELEASE BLOCKED (B-06) |
| G05–G10 | BLOCKED / NOT_STARTED |
| G11 | DEFERRED |
