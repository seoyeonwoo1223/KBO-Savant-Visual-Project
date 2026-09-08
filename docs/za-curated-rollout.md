# Zone Awareness curated-data rollout

This runbook is the binding eight-phase migration policy for production ZA.

| Phase | Permitted action | Gate owner | Approval evidence |
|---|---|---|---|
| 1 — inventory | Read-only inventory of raw, processed, downstream and web dependencies. Do not write production output. | Data engineering | Inventory attached to release record. |
| 2 — audit | Read-only schema, quality and reproducibility audit. Do not write production output. | Analytics | Audit accepted; no unresolved critical issue. |
| 3 — curate | Write only below `data/curated/zone_awareness/<version>/`; never replace or delete `data/processed/`. | Data engineering | Manifest schema and checksums validate. |
| 4 — validate | Write comparison evidence only in that versioned curated directory. | Analytics | Row/schema/metric tolerances pass. |
| 5 — stage | Publish staged artifacts only under the versioned curated path. Preserve all legacy files. | Release manager | Rehearsal and rollback checks pass. |
| 6 — shadow | Choose `legacy` or `curated` explicitly with `ZA_INPUT_MODE`; curated also requires `ZA_CURATED_VERSION`. CI and production ZA remain `legacy`. | Production owner | One complete operating cycle observed and differences accepted. |
| 7 — approve | After written approval, change the production default to curated. Missing/invalid manifests and checksum failures must stop the job; fallback is forbidden. | Production owner + analytics | Signed approval and monitoring results. |
| 8 — cleanup | Remove obsolete legacy processed outputs only after the retention cycle. Keep raw JSON forever. Rollback only to the immediately preceding approved curated version. | Release manager | Retention elapsed, rollback rehearsal passed. |

## Curated manifest contract

Each immutable version has `data/curated/zone_awareness/<version>/manifest.json`.
Its `seasons` object maps a season to a path relative to the version directory
and a lowercase SHA-256 checksum:

```json
{"schema_version":1,"version":"za-2026.09.1","seasons":{"2026":{"path":"pitches.parquet","sha256":"<64 hex characters>"}}}
```

Phase 1/2 inventory prints JSON to stdout and does not write repository files.
Phase 3 creates a new immutable version by copying the legacy input; it never
changes the source file:

```powershell
python -m visualbaseball.za_curate inventory --season 2026
python -m visualbaseball.za_curate curate --season 2026 --version za-2026.09.1
```

Use `--input-mode curated --curated-version <version>` (or the matching
environment variables). The manifest and bytes are checked before reading.
Validation is fail-closed. The legacy default remains until Phase 7 is approved.
Before Phase 7, run curated ZA through the standalone module; its web, export,
and report artifacts are isolated below `<version>/outputs/`:

```powershell
$env:PYTHONPATH = "src"
python -m visualbaseball.zone_decision --seasons 2026 --input-mode curated --curated-version za-2026.09.1
```

## Release record (required at every gate)

Create `releases/za/<release-id>.md` and append one row per gate. Never approve
a row with blank evidence.

| Phase/gate | Decision and conditions | Accountable owner | Artifact path | SHA-256 | Started UTC | Finished UTC | Approval reference |
|---|---|---|---|---|---|---|---|
| 1 | pending | name/role | inventory | checksum | ISO-8601 | ISO-8601 | ticket/review |

Record checksums for the manifest, every promoted artifact, and all comparison
or monitoring evidence. Record command start and finish times in UTC. During the
Phase 6 observation cycle, retain both output sets and record downstream/web
checks for every scheduled run. After Phase 8, retain raw JSON unchanged and
record the immediately preceding approved curated version as the sole rollback
target.
