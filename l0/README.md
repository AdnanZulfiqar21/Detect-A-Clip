# Desktop synthetic L0 track

Python reference implementation and LAB harness for the on-device recognition chain in
roadmap v4.2.1 (F03 to F05). It runs only on **self-created synthetic** material. Results are
LAB evidence: not device, rights, coverage or release evidence. The shipped mobile engine
remains native Kotlin/Swift (see `../android`, `../ios`).

## Setup and tests

```bash
python -m pip install -r requirements.txt
python -m pytest
```

## Commands

```bash
python -m dac_l0.cli fixtures                     # frozen fixtures-v3.1 manifest → assets/FIXTURES_v3.json
python -m dac_l0.cli manifest                     # asset + rights manifests with content hashes
python -m dac_l0.cli lab --families DEV --label dev            # development thresholds
python -m dac_l0.cli calibrate                    # CALIBRATION family only → evidence/calibration/
python -m dac_l0.cli lab --calibrated --families DEV,CALIBRATION --label calibrated
python -m dac_l0.cli lab --calibrated --families FINAL --i-understand-final-is-sealed --label final   # once only
python -m dac_l0.eval.sampling_study --family HASH64                # DEV-only 1/2/5 s study
python -m dac_l0.cli keygen | sign | verify | build | preview       # dev pack tooling
```

FINAL (fixtures-v3.1) has already been run once and is now **seen**. See `docs/EVAL_PROTOCOL.md`.

## Modules

| Module | Roadmap anchor |
|---|---|
| `synth/generator.py` | P00-T07: synthetic works, editions, query transforms, natural negatives, synthetic private screens and overlays |
| `synth/fixtures.py` | Frozen DEV / CALIBRATION / FINAL families, challenge queries (series, recap, stock, montage, trailer, overlay) |
| `synth/manifest.py` | P00-T07c / G03-L0: asset hashes and the self-created synthetic grant |
| `schemas.py` | F04 canonical records; reserved result states unconstructible; default-deny rights |
| `sampler.py` | F05 intake: ≥500 ms spacing, ≤3 app-owned frames, monotonic timestamps |
| `quality.py` | P04-T01: blank/flat/static/UI-like flags, bounded normalisation, black-bar crop |
| `index/` | P03-T03, P04-T02, P04-T04a: descriptors (24/48/160/528 B per vector), reproducible builder, bounded parser incl. display names, flat retrieval |
| `verify.py` | P04-T03: temporal offset verification, edition ambiguity, montage segmentation |
| `decision.py` | P04-T05 prep: one result enum, UNCALIBRATED thresholds, no numeric confidence |
| `coordinator.py` | F03 coordinator event table (reference for Kotlin/Swift ports) |
| `pack/` | P03-T04, SEC-01: signed UNCALIBRATED dev manifest, fail-closed loader (D07, D10, epochs, expiry) |
| `eval/` | P00-T08 protocol, LAB runner (cached evidence, preregistered scoring), calibrator, sampling study |
| `pack/store.py` | Staged atomic pack activation, epoch marker, lab leases (IDX-01, RIGHTS-02/04 dev scope) |
