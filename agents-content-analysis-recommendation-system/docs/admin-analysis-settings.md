# Admin Analysis Settings

Route: `/#/admin-analysis-settings`, accessible only to administrators.

## Parameters

| API field | Persisted column in system_configs | Default | Accepted values |
| --- | --- | --- | --- |
| upload_max_duration_seconds | upload_max_duration_seconds | 300 | 30-1800 seconds |
| asr_model | asr_model_default | small | Installed, loadable multilingual Whisper model |
| hook_duration_seconds | hook_duration | 60 | 5-300 seconds, no longer than upload maximum |

The bounds are resource/validation limits, not claims of optimal video or hook
duration. Full-clip transcription is preserved. Hook terms use timestamped
segments starting before the selected Hook boundary; a segment crossing the
boundary is included whole, matching the existing segment-level extraction.

## Request Flow

1. The admin GET/PUT `/admin/analysis-settings` reads/writes the shared
   `system_configs` row. PUT validates local Whisper files and loads the model
   before committing. No model download is triggered by this page.
2. Authenticated upload clients GET `/analyze/settings` on page entry, file
   selection and submission. Missing settings or unavailable ASR blocks upload.
3. POST `/analyze` or `/analyze/save` captures a settings snapshot, then verifies
   actual media duration using ffprobe. Client-side checks are not trusted.
4. The snapshot is passed into the queued job. Changes made after enqueue affect
   subsequent jobs, not a job already accepted.
5. The job explicitly supplies the saved Whisper model and Hook window to the
   pipeline, and pins the classification model by registry ID and artifact hash.
6. Saved results retain `ai_analysis.analysis_settings` in
   `analysis_results.summary` JSON. `/contents/{id}` returns that snapshot. The
   result page exposes it in an expandable audit section. Legacy results show
   that no settings snapshot was recorded; today's settings are not substituted.

## Classification and Training

The active qualified classifier and its evaluation metrics are read-only on this
page. Unknown threshold comes from its evaluated artifact. Arbitrary model IDs
or thresholds are rejected by the settings request schema. Existing evaluated
activation remains in `activate_classification_model.py`; this page does not
introduce a second activation path.

Upload duration does not alter classification training eligibility, imported
transcripts, training splits, or the recommendation evidence cohort policy.
Models not installed locally are shown disabled. Install a desired model through
the existing server setup workflow before selecting it.

The additive startup migration preserves existing Hook/Whisper values and adds
the upload limit with a 300-second default. Saved parameters survive process
restarts because jobs read the database rather than environment defaults.

## Verification

- `python -m unittest tests.test_analysis_settings tests.test_full_clip_analysis`
- `flutter test --no-pub` in `frontend_flutter`

Tests cover permissions, parameter validation, unavailable/corrupt models,
queued settings, classifier pinning, database reopen, stored result audit,
server upload limits, timestamped Hook slicing and frontend states.
