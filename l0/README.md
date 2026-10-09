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
python -m dac_l0.cli manifest                 # assets/ASSET_MANIFEST.json + RIGHTS_MANIFEST.json
python -m dac_l0.cli build --family HASH64    # packs/L0-SYNTH-001.pack (git-ignored)
python -m dac_l0.cli keygen                   # DEVELOPMENT_ONLY Ed25519 key (private key git-ignored)
python -m dac_l0.cli sign --pack packs/L0-SYNTH-001.pack --key keys/<id>.dev.private.pem
python -m dac_l0.cli verify --manifest packs/L0-SYNTH-001.manifest.json --pack packs/L0-SYNTH-001.pack --pub keys/<id>.public.pem
python -m dac_l0.cli lab --out evidence/lab   # AI-01/02/03/07 exploratory + IDX-01 desktop baseline
python -m dac_l0.cli preview --asset SW000-E0_THEATRICAL   # MP4 for a human witness (git-ignored)
```

## Modules

| Module | Roadmap anchor |
|---|---|
| `synth/generator.py` | P00-T07: synthetic works, editions, query transforms, natural negatives, synthetic private screens and overlays |
| `synth/manifest.py` | P00-T07c / G03-L0: asset hashes and the self-created synthetic grant |
| `schemas.py` | F04 canonical records; reserved result states unconstructible; default-deny rights |
| `sampler.py` | F05 intake: ≥500 ms spacing, ≤3 app-owned frames, monotonic timestamps |
| `quality.py` | P04-T01: blank/flat/static/UI-like flags, bounded normalisation, black-bar crop |
| `index/` | P03-T03, P04-T02: descriptors (24/48/160 B per vector), reproducible builder, bounded parser, flat retrieval |
| `verify.py` | P04-T03: temporal offset verification, edition ambiguity, montage segmentation |
| `decision.py` | P04-T05 prep: one result enum, UNCALIBRATED thresholds, no numeric confidence |
| `coordinator.py` | F03 coordinator event table (reference for Kotlin/Swift ports) |
| `pack/` | P03-T04, SEC-01: signed UNCALIBRATED dev manifest, fail-closed loader (D07, D10, epochs, expiry) |
| `eval/` | P00-T08 protocol, LAB runner with Wilson and per-work cluster bootstrap intervals |
