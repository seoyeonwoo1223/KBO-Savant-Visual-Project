# Zone Awareness curated-data rollout

The former versioned ZA copy and `legacy` fallback were retired. Zone Awareness now reads the same canonical game shards as every other metric and writes its derived artifacts below `data/metrics/zone_awareness/<season>/`.

See [Canonical pitch data](curated-data.md) for migration, hashes, validation, reconcile, and recovery commands. A missing or invalid canonical season fails closed; Excel and `data/processed/pitches.parquet` are not runtime inputs.
