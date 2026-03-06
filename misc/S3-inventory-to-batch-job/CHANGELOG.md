## v0.3.1 (2026-03-06)

### Feat

- objects-per-manifest-file default 3M, objects-per-job default 10B, --max-objects, README in wheel

## v0.3.0 (2026-03-06)

### Feat

- configurable report scope; remove jitter from split-files
- file and row count assertions for split and split-files
- failure threshold and continue-after-failure for split uploads

## v0.2.1 (2026-03-06)

### Fix

- commitizen version_files pattern to update VERSION file on bump

## v0.2.0 (2026-03-06)

### Feat

- grant manifest bucket read access in setup-iam-role
- propagate report_bucket through context; validate report bucket writability
- KMS auto-detection, destination policy check, job activation UX
- validate-setup command, --quiet flag, bucket/region completion, setup-iam-role
- logging, shell completion, setup-iam-role command, and ruff linting
- **replicate**: implement batch job creation and add setup-replication-rules command

### Fix

- syntax error in setup_iam_role.py (extra whitespace)
- auto-normalise --report-bucket to ARN format if plain bucket name given
- include original exception message in all RuntimeError raises
- treat AccessDenied on get_bucket_encryption as no KMS key
- handle NoSuchEncryptionConfiguration in get_bucket_kms_key
- validate IncludedObjectVersions=All not OptionalFields for VersionId check
- checksum files, VersionId validation, empty job guard, rows-per-file propagation
- download manifest via streaming get_object; warn on low files-per-job

### Refactor

- extract validate-setup checks into helper functions; add report bucket writability check

## v0.1.0 (2026-03-05)

### Feat

- **split-files**: add synthetic inventory generation command
- split into split/replicate subcommands with click chaining
- add manifest parsing and job partitioning
- add parameter parsing and input validation

### Fix

- switch partitioning to file-count based on objects per manifest file

### Refactor

- restructure into package for wheel distribution
