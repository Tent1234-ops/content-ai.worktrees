# Phase 7: Evaluation and presentation protocol

## Current status

The evaluation tools, local regression run and recommendation bug comparison are
implemented. **Independent end-to-end acceptance is not complete.** New Phone,
Camera and Laptop videos, self-recorded videos, independently labeled unknown
videos and human recommendation ratings are still needed. Do not substitute
existing regression clips or the old transcript test for these missing inputs.

The September 26 run is under `artifacts/evaluation/phase7-20260926/`:

- `inventory/`: SHA-256 inventory and editable case manifest. Eleven local files
  represent only four unique videos, not eleven independent samples.
- `before/report.md` and `before/report.json`: real pre-fix outputs.
- `after/report.md` and `after/report.json`: paired post-fix outputs.
- Each stage has per-case JSON with raw/cleaned transcripts, timestamped speech
  segments, classification, recommendations and reference evidence.
- `context.json`: Active Model, artifact and source-code hashes, settings and
  reference fingerprint. The after run also records package versions.
- `reference-rows.json`: reference rows as read for that evaluation, not imported
  training data. Treat transcripts as local research evidence, not redistributed
  licensed content.
- `human-review.csv`: unfilled review forms bound to the exact output hashes.

Model 14 (`taxonomy-tfidf-complement-nb`, version `20260828T134420Z`) was not
retrained or replaced. Whisper small on CPU, a 60-second opening and the existing
300-second upload limit were used. Filenames were replaced by `evaluation.mp4`
at the pipeline boundary, not used to predict class or create gold labels.

## Three different questions

1. **Classification**: compare the predicted class with a human label. Report
   sample counts, accuracy, per-class precision/recall/F1, macro F1, confusion
   matrix, and Unknown recall separately. Confidence is an individual model
   output, not measured correctness or predicted engagement gain.
2. **Recommendation consistency**: check whether a suggested topic was already
   detected, whether cited Dataset rows are eligible same-class training/reference
   rows, whether support counts/frequencies agree, and whether example sources
   and timestamps match. These checks reuse the production term extractor and
   are not an independent semantic or usefulness evaluation.
3. **Recommendation usefulness**: a person watches the clip and rates relevance,
   novelty relative to what was already said, evidence correctness and whether
   the advice gives an actionable improvement. An empty form means unassessed,
   never zero, perfect, or inferred from confidence.

The metrics do not establish that changing a clip will cause more views, likes
or comments. That requires a separate outcome study with appropriate controls.

## Actual findings

The frozen historical test has 17 transcripts: Phone 3, Camera 5, Laptop 9.
It has no Unknown examples. The replay got 17/17, accuracy and macro F1 1.0.
The runner checked its IDs, channels and transcript overlap against frozen
development data and current references; no overlap was flagged. This is an
already-used historical test, not new blind evidence, and does not exercise ASR.

| Existing video | Duration | Predicted class | Confidence |
| --- | ---: | --- | ---: |
| Review_Phone.mp4 | 111.85 s | Phone | 98.16% |
| review_headphone.mp4 | 51.77 s | Phone | 96.81% |
| review_keyboard.mp4 | 60.08 s | Phone | 99.03% |
| review_mouse upload | 72.68 s | Phone | 96.86% |

The transcripts of the last three describe accessories, not standalone Phone,
Camera or Laptop reviews. They are concrete out-of-scope failure diagnostics.
Gold labels and source identities are still unconfirmed, so the runner does not
promote them into a scored new holdout or claim population-level Unknown recall.
The transcripts also contain obvious ASR errors. A manually checked transcript
is needed to isolate ASR errors from the classifier's rejection weakness.

Wrong classification selects the wrong reference category. Therefore a perfectly
consistent citation to a Phone Dataset row can still be irrelevant for headphones.
Passing structural checks is insufficient for recommendation quality.

## What changed in this comparison

"Before" means the implementation immediately before this Phase 7 fix, not the
first historical version of the whole project. Both stages use identical ASR
transcripts, model, parameters and reference fingerprint. A mismatch aborts paired
replay. Current-trend ideas are excluded from the paired recommendation claim
because their observation time may differ.

- Before: Phone suggested `dimensity` although the opening already mentioned it;
  this suggestion also had no per-keyword Dataset evidence.
- After: observed hook terms and full-transcript synonyms are included in the
  exclusion set, not just the limited displayed keyword list.
- Hook suggestions now reuse evidence-backed missing concepts, preserving
  supporting row IDs. They are topics proposed for the user's opening, NOT a
  claim that these exact words appeared at successful reference-video openings.
- The Phone suggestions are `charging speed` (13/16 reference clips),
  `build quality` (12/16), and `stabilization` (9/16). Each has source IDs and times.
- Across four regression videos: before 22 suggestion entries, one flagged;
  after 39 entries, zero flagged by the structural checks. Entries count the
  missing and hook lanes separately; they are not independent clip samples.
  More suggestions do not mean better recommendations. The three wrong-category
  diagnostic cases remain unresolved, and no human usefulness rate is claimed.

Old saved user results are not silently rewritten. New analyses use the fixed
recommender once the backend has loaded the changed code.

## Collect a genuinely independent pilot

Start with a small, explicitly labeled pilot, not a claim of statistical power:

| Stratum | Suggested initial cases | Content |
| --- | ---: | --- |
| Phone | 3 | ordinary review, phone camera emphasis, phone gaming |
| Camera | 3 | dedicated camera, lens emphasis, comparisons with phone cameras |
| Laptop | 3 | work laptop, gaming laptop, laptop vs other gaming devices |
| Unknown | 3 | accessories and at least one unrelated topic |

Include self-recorded clips in each in-scope category if possible. Use natural
speech rather than reading the known keyword dictionary. Keep clips within the
configured upload limit. Label by the main object being reviewed before viewing
the model result, not by filename or the model prediction.

Record video ID/channel for public clips; for self-recorded clips record who
created them, when, and that they have never been imported. Different filenames
do not make clips independent. Hash matches, reused IDs, shared development
channels, exact transcript matches and near-copy warnings block scored inclusion.
No automatic similarity check proves independence when source identity is absent.

After inspecting failures, move those clips to regression/development. Do not
tune on them and continue calling them a blind final test. Collect a fresh final
set after freezing changes. Do not import evaluation clips as recommendation
references. Keep the frozen model's original test separate as historical context.

## Commands

Use the backend's Python environment and run from the repository root. Each output
directory must be new so prior evidence cannot be overwritten accidentally.

```powershell
python scripts/evaluate_analysis.py inventory --videos videos --out artifacts/evaluation/next-inventory
python scripts/evaluate_analysis.py run --manifest artifacts/evaluation/next-inventory/cases.json --out artifacts/evaluation/next-before
python scripts/evaluate_analysis.py run --replay artifacts/evaluation/next-before/report.json --out artifacts/evaluation/next-after
python scripts/evaluate_analysis.py reviews --report artifacts/evaluation/next-after/report.json --reviews artifacts/evaluation/next-after/human-review.csv
```

Inventory defaults to `role: regression` and no gold label. For a genuinely new
case, set `role: heldout`, `expected_label` to `phone`, `camera`, `laptop` or
`unknown`, `label_reviewed_by`, and `independence_confirmed_by`. Set `source_kind`
to `self_recorded` with `provenance_note`, or supply public source IDs. Hashes
come from inventory; never change them merely to make a changed file pass.

For each CSV recommendation row, rate all four fields with 1 or 0, enter reviewer
and notes. Missing fields, duplicate ratings and stale output hashes are rejected.
Rate whether adding content is useful; do not infer a score from the number of
citations. Ideally, reviewers see A/B outputs without stage names and assess
them before learning the model confidence. Also review empty outputs manually:
no suggestions is not proof that nothing could be improved.

## Presentation walkthrough

1. Show the data roles: classifier training, recommendation reference and test
   clips have different purposes. Snapshot trends are a separate evidence lane.
2. Show the frozen model and settings, then the original clip and transcript.
3. Explain that the classifier chooses a category; the recommender compares
   observed topics against eligible same-category references.
4. Show the Phone `dimensity` before/after case and open a cited Dataset row.
5. Show the accessory failure with high confidence. Explain why 17/17 on an old
   closed-set transcript test does not solve Unknown or recommendation relevance.
6. Show the pending human review form and missing new clips. State explicitly
   that engagement improvement has not been experimentally measured.

`scripts/browser/capture_phase7_evidence.cjs` renders the real saved evaluation
JSON in the existing result UI and captures screenshots. It intercepts only the
browser response for an owned result, labels the title as an artifact preview,
and does not overwrite saved results or create artificial prediction values.
Its verification JSON records source-file hashes. These are presentation previews,
not evidence of a new persisted user analysis.

## Files and verification

- `app/services/analysis_evaluation.py`: overlap, scoring exclusions, metrics,
  structural evidence checks and human review validation.
- `scripts/evaluate_analysis.py`: read-only inventory, real pipeline execution,
  paired replay, frozen test replay and evidence export.
- `app/services/recommendation.py`: full-transcript suppression and grounded hook
  proposals. No changes to the Active Model or Unknown threshold.
- `tests/test_analysis_evaluation.py` and the added Phase 20 tests cover empty
  scores, failed runs, duplicate/source leakage, stale human reviews, synonym
  suppression and retained hook evidence. Synthetic fixtures validate software
  behavior only; they are not counted as real-world accuracy samples.
