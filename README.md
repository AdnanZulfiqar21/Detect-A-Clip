# Detect A Clip

User-initiated, consent-first recognition of movie / TV / drama / anime clips that are
already playing in **another app on the same phone**. Native Android (Kotlin) and iPhone
(Swift) are separate research tracks. Recognition runs **on device** against a small,
lawful local catalogue. Cloud screen processing (Mode R) is OFF at build and runtime.

The roadmap calls the project *CineDetect AI*; the repository and product-facing name is
*Detect A Clip*. Both refer to this project. Roadmap document filenames and task IDs are
preserved for traceability.

## Status

**Engineering: IN_PROGRESS on the desktop synthetic L0 track. Nothing is released.**
No physical device test, rights grant, legal sign-off or store decision exists. See
[docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for per-task status and
[docs/BLOCKERS.md](docs/BLOCKERS.md) for what is externally blocked.

## Repository layout

| Path | Purpose |
|---|---|
| `CineDetect_AI_Fable51_Revised_Roadmap_PROPOSED (1).md` | Authoritative roadmap v4.2.1 PROPOSED (86 tasks, 54 tests, 13 gate rows, D01–D11) |
| `CLAUDE_DETECT_A_CLIP_BUILD_PROMPT.md` | Implementation instruction and limited development authorization |
| `docs/` | One authoritative record per topic: status, decisions, blockers, review log, test evidence, resume state |
| `l0/` | Desktop synthetic **L0** track (Python): synthetic asset generator, schemas, index builder, retrieval, evaluation |
| `android/` | Android native lab build (Kotlin) — prepared source; compile state recorded in status |
| `ios/` | iPhone native lab build (Swift) — prepared source; cannot be compiled on this Windows host |

## What L0 is and is not

L0 uses only **self-created synthetic "works"**: procedurally generated motion clips with
synthetic labels. Results from L0 are visibly synthetic. L0 is not six-industry coverage,
not real-source recognition and not a privacy clearance for any consumer cell.

## Running the desktop L0 track

```bash
python -m pip install -r l0/requirements.txt
python -m pytest l0/tests -q
```

See `l0/README.md` for the generator, index builder and evaluation commands.
