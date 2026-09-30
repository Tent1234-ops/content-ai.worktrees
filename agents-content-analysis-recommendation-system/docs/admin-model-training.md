# Admin Model Training

Web route: `/#/admin-training` (admin only), menu: "เทรนโมเดล AI".

## Workflow

1. Read approved, training-eligible transcripts for Phone, Camera and Laptop using
   the same dataset preparation and channel split rules as the CLI benchmark.
2. Display counts for train/validation/test and collection readiness. Confirm a
   new run against the displayed dataset fingerprint. A changed dataset requires
   refreshing and confirming again.
3. Store a `model_training_runs` row, then start `scripts/run_admin_training.py`
   as an independent subprocess. Closing the browser does not cancel training.
4. Compare the existing Complement NB, tuned Logistic Regression, calibrated
   Linear SVM and multilingual embeddings classifiers. Embeddings use only a
   locally available model; an unavailable model is reported as skipped.
5. Grouped cross-validation uses channels in the development pool (original
   train + validation). The held-out test split is not fitted. Older validation
   results remain labeled separately from grouped CV.
6. Save model artifacts, `classification_models`, `model_evaluation_metrics`,
   run results and audit logs. Training does NOT activate any model.
7. An admin can explicitly activate a qualified evaluated model, including an
   older qualified version. The API verifies gates, artifact hash, reload check
   and the active model ID seen when opening the confirmation dialog.

This page trains classification, not Whisper and not a generative recommender.
User upload duration, Whisper size and Hook settings stay in Analysis Settings;
they do not truncate or restrict training transcripts.

## Readiness And Evaluation

- Baseline training: at least 30 eligible rows per category, including 15 train,
  3 validation and 3 test rows, with no channel leakage across splits.
- Up to five grouped cross-validation folds, depending on available channels.
- New run defaults retain the existing 60% Unknown confidence threshold and
  80% promotion metric threshold. Neither is an arbitrary editable UI field.
- Phase 22 promotion also requires at least 80 rows and 10 channels per category,
  at least 30 out-of-scope evaluation rows, and passing Unknown detection checks.
- A baseline-ready dataset can be benchmarked before Phase 22 collection is
  complete, but resulting models are not eligible for activation until all gates
  pass. High Test Accuracy alone is insufficient.
- Missing metrics are shown as missing, not as zero and not borrowed from a
  different split. Every result retains its sample count.

## Persistence And Failures

`model_training_runs` stores requestor, frozen parameters, fingerprint, stage,
current algorithm, heartbeat, result, error and timestamps. A nullable unique
`active_slot` prevents concurrent training from two browser tabs or API workers.
The existing application startup creates the new table with `create_all`.

The worker updates its heartbeat every 10 seconds; the page polls the database
every 5 seconds only while its latest run is queued/running. Reloading the page
restores the saved run. A worker can outlive an API restart. A process crash or
machine shutdown does not resume partial fitting: after 180 seconds without a
heartbeat, the next status read marks it interrupted and permits a new run.

Artifacts are under `artifacts/classification_training/<model_version>/`.
Worker output is under `artifacts/classification_training/worker_logs/`.
Training requests, completion, failures, interruption and activation have audit
events with the requesting admin ID in `system_logs`.

## API

- `GET /admin/training`: dataset readiness, recent runs, model list, active model.
- `POST /admin/training/runs`: confirm the displayed `dataset_fingerprint`.
- `GET /admin/training/runs/{run_id}`: persisted progress and outcome.
- `GET /admin/training/models?offset=0&limit=20`: paginated registry.
- `GET /admin/training/models/{id}`: metrics, category scores, confusion matrices.
- `POST /admin/training/models/{id}/activate`: explicit activation with
  `expected_active_model_id` to reject stale confirmation dialogs.

All endpoints require an authenticated admin. Override flags and unknown fields
in start/activation request bodies are rejected.

## Verification

Backend: `python -m unittest tests.test_model_management tests.test_classification_training tests.test_analysis_settings`

Frontend: `flutter test --no-pub`

Coverage includes real fitting against an isolated dataset, durable run records,
duplicate starts, failed/crashed workers, stale data, authorization, qualified
activation and rollback, corrupt artifacts, UI confirmation, polling, scores,
blocked-model explanations and compact web layouts.
