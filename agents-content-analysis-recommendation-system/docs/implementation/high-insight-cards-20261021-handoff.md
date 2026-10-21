# High Insight Cards Handoff - 2026-10-21

## Scope

- Use only Text Centroid in the active analysis reference page; remove the transcript-method selector.
- Replace inline High-topic transcripts with responsive, evidence-backed insight cards.
- Remove the requested legacy benchmark, scope/timestamp and similarity-disclaimer paragraphs from this panel.
- Do not change K-Means, Text Centroid, Cosine Distance, eligibility rules, saved analysis, dataset splits or trained models.

## Completed

- Inspected the existing service, API schema, repository and Flutter model before editing. The API already exposes recommendations as dictionaries, so the new fields are additive; no migration or dependency is needed.
- Backend `_topic_advice()` now returns a factual short summary, all supporting High dataset IDs, a conditional application from the existing versioned topic template, and provenance for the displayed literal excerpts.
- Excerpt provenance includes the source video/channel, transcript SHA-256, matched text and exact source/quote character offsets. Offsets are Python Unicode code points; Flutter validates them using runes.
- Support counts cover all actual High clips mentioning the topic, not just the maximum three displayed examples. Existing minimum two clips/two channels and maximum six topics remain unchanged.
- Application text is a conditional editorial suggestion tied to an evidenced topic. It is not a claim that every reference performed that exact procedure or that the procedure caused higher engagement. No generated specifications, experiment results or causal percentages were added.
- Flutter validates supporting IDs/counts/channels against High members and validates excerpt identity/spans. Malformed or ungrounded cards are omitted. Missing application provenance produces a missing-information state rather than invented guidance.
- Cards contain a topic summary, actual counts, application/condition, readable clip links, and a collapsed-by-default transcript section. Only relevant literal excerpts are displayed when expanded.
- Cards use two columns at 900 px of available inner width and above, otherwise one column; text wraps, controls have accessible tooltips, and link failures show a recoverable snackbar.
- The page explicitly requests `embedding_centroid` and rejects a ready legacy-method response instead of silently rendering it. Legacy TF-IDF API compatibility remains outside this UI.
- Card heading and evidence-toggle semantics are separated for accessibility. Literal excerpts have explicit readable semantics, and the expanded body cannot merge with or hide the toggle's tap action. Regression tests cover the expanded toggle's label/action.
- Browser verification waits for API startup before creating a temporary session, redacts credentials from error reports, and can end only its own session through the existing service if API logout fails.
- Updated chapter 20 and the classifier/clustering explanation in the Thai system walkthrough.

## Changed Files

- `app/services/performance_clustering.py`: additive insight/evidence presentation fields in `_topic_advice()` only.
- `frontend_flutter/lib/models/performance_clustering.dart`: typed insight parser and provenance validation.
- `frontend_flutter/lib/widgets/performance_clustering_panel.dart`: fixed Text Centroid path, removed requested text, responsive cards and excerpt expansion.
- `tests/test_performance_clustering.py`: source-slice/count/action provenance tests and unchanged-math regression.
- `frontend_flutter/test/performance_clustering_test.dart`: parser, responsive cards, evidence toggle, links/failures, missing evidence and fixed-method tests.
- `frontend_flutter/test/result_workspace_test.dart`: update legacy-result assertion for the removed label while retaining the actual panel check.
- `scripts/browser/verify_performance_clustering.cjs`: real-data card/count/expansion checks; remove obsolete method-switch checks.
- `docs/presentation/system-walkthrough-th.md`: current UI and grounded application explanation.

## Verification

- Backend: **31 tests passed** (`tests.test_performance_clustering`, `tests.test_embedding_centroid`, `tests.test_performance_clustering_topics`). Explicit regression confirms insight generation does not change clusters, content similarity or data fingerprint.
- Flutter focused tests: **48 passed**, including 390/768/1280/1600 widths in light/dark themes, expansion/collapse, canonical links, invalid evidence, empty states and existing Result workflow.
- Targeted Flutter Analyze: **no issues** in the six active model/widget/repository/result/test files.
- Full Flutter Analyze: **three pre-existing issues remain** in the unused Automatic Overview draft: undefined `getAutomaticPerformanceOverview`, a non-overriding method, and an outdated comparison override missing `comparisonMethod`. These files were not changed or activated by this task. Full-project Analyze is not all-green.
- Release web build: **passed**, 28.8s. Existing Cupertino font-family warning remains; this feature uses Material icons, confirmed in browser screenshots.
- Logs for the above are `artifacts/performance-clustering/20261020/insight-cards-*.txt` (task began Oct 20; final reruns were Oct 21).
- Live Edge/Playwright verification: **all eight width/theme combinations passed**, 390/768/1280/1600 in light and dark. Actual API distances/counts match the UI; per-card expand/collapse, All/Low/High filters and the original saved reference evidence work. Minimum-view filtering to an empty result and restoring it both pass. No browser exceptions/overflow errors were recorded. Saved analysis was unchanged and the temporary session was ended.
- Final browser evidence: [verification.json](../../artifacts/performance-clustering/20261021/insight-cards-browser-verified-v4/verification.json), with real API payloads, screenshots and accessibility snapshots alongside it. No mocked classification/KPI response was used.
- Pixel checks: **eight charts passed**, confirming nonblank plots and visible hover changes. Evidence: [pixel-checks.json](../../artifacts/performance-clustering/20261021/insight-cards-browser-verified-v4/pixel-checks.json).
- Visually inspected final desktop dark cards, tablet dark collapsed cards and mobile light expanded evidence for wrapping, readable links and overlap; no issues found. Earlier desktop light screenshots were also inspected.
- `node --check scripts/browser/verify_performance_clustering.cjs` passed. A scan of this task's Oct 21 artifacts found no remaining unredacted authorization headers.

## Real-Data Check

- The first live API check used saved content `#41 review camera`, not mocked KPI/classification data.
- The first returned insight, video recording, was supported by **19 clips / 15 channels**, with three linked excerpts. These are snapshot observations, not fixed values in the UI.
- Earlier browser folders are retained as failed diagnostic evidence, not passing evidence: `insight-cards-browser-quick*` exposed merged card labels and unreadable SelectableText semantics; `insight-cards-browser-final` exposed ambiguous two-column toggle selection; `insight-cards-browser-verified-v3` confirmed the expanded toggle was still being merged into its body. These were corrected in the final build and scoped locator.
- `insight-cards-browser-verified` failed while the API was stopped during continuation. Its temporary session was closed through the existing session service and its report was redacted. `insight-cards-browser-verified-v2` ran before API startup completed and created no temporary session. Startup waiting was then added. Only `insight-cards-browser-verified-v4` is the final complete passing run.

## Remaining / Follow-Up

- No required work remains for this requested UI change. Verification and the active web build are complete.
- Automatic Overview remains separate unfinished work as described above; do not claim the entire repository has passed analysis/tests.
- Topic matching remains the existing alias-based method. A relevant literal excerpt proves a mention, not an experimentally measured product claim or causal engagement effect.
- No dataset import/deletion, classifier training, model activation, split migration or schema change was performed. The existing API may continue its normal scheduled statistics collection.
- Repository Git metadata still points to a missing external worktree directory; it was not repaired or reset.

## Running Application

- Web: `http://127.0.0.1:8082/#/history`
- API: `http://127.0.0.1:8011`
- Open a saved analysis, then the reference tab. Server identities/logs are in `runtime_artifacts/performance-clustering/`.
