# Result Reference Responses Handoff

Updated: 2026-10-17 (Asia/Bangkok).

Follow-up: [Result Simplification and System Guide](result-simplification-system-guide-20261017-handoff.md) removes the copy button, cleaned-transcript display and combined evidence/version expander, preserves actual reference responses, and adds the detailed current-system guide.

## User Decision

- Remove the entire revision planner from the analysis result, including notes, save/reload and revision-upload controls. Keep historical plan records intact.
- Prefer a genuinely validated percentage predictor. If it cannot be supported, use actual reference-video response statistics instead. The user explicitly approved this fallback.

## Delivered

- Section 3 is now `3. ผลตอบรับจากคลิปอ้างอิง`.
- Displays the saved view/like/comment counts, channel, publication date, observation time, source-video link and supporting transcript excerpt for each recommended topic.
- Uses only the evidence snapshot attached to that analysis. Reopening an old result does not fetch current Dataset counters or rewrite recommendations.
- Shows two references initially per topic and expands the rest. Preserves recommendation priority and source order; does not sort examples by largest views.
- References must match the category and recommended missing transcript topic, have an identifiable Video ID and a quote present in the saved transcript. Excludes protected validation/test references, ambiguous Dataset IDs and inconsistent source identities; deduplicates Video IDs within each topic.
- Counts reflect references that can actually be opened, not unverified stored support totals. Known-channel counts exclude missing channel IDs.
- Missing/invalid counters remain missing. Genuine zero remains zero. No counters are displayed without a recorded source and valid observation time no later than the evidence cutoff and no earlier than a known publication date.
- Does not aggregate counters across channels, ages or view-metric versions, or invent a percentage, comparison uplift, future engagement estimate or synthetic example in the live result.
- The selected-reference limitation is explicit. These clips are not a representative YouTube sample and their outcomes do not establish that adding a topic causes more views.
- A genuine saved available Outcome assessment remains supported by the existing widget; fixture-only, unavailable and withheld assessments do not replace the fallback with a made-up probability.
- Planner removal was already present in current application source at task start. Added regression coverage for saved and unsaved plans: no planner widget, no notes/actions, no plan reads/writes; stored data is unchanged.

## Verification

- Final full Flutter suite: **200 tests passed**, exit 0, including the four additional category/navigation checks and accessible quote rendering.
- Final focused reference-response suite: 27 tests passed, including all three categories, missing/invalid statistics, duplicate sources, provenance mismatches, withheld input, mobile/desktop layout, source-navigation failure and saved-result integration.
- Flutter analyze: no issues after correcting three lint findings.
- Release web build passed. The pre-existing Cupertino font warning remains; this view uses Material icons.
- Initial real-browser recheck passed all original routes at 1440/1000/390 pixels and confirmed the removed planner before replacing section 3.
- Final live-browser acceptance passed at 1440/1000/390 pixels using `--reference-results-only`. Visible counters matched the unchanged saved API response; supporting quotes matched saved transcripts; the planner was absent through the footer with zero plan API calls. The report has `passed: true`, no errors and `temporary_session_ended: true`.
- Definitive browser artifacts: `artifacts/classification-admin-approval/20261016/browser-reference-response-accepted/` (final run on October 17; directory retains the parent task date). Desktop and mobile screenshots were visually inspected: counters, source links and expanded quotes fit without overlapping.
- The screenshot-framing follow-up in `browser-reference-response-framed/` exposed an accessibility issue: `SelectableText` showed the quote visually but exposed an empty disabled textbox. Replaced it with accessible `Text` and verified the expanded quote in the final accepted run. Also corrected the browser harness to scroll before locating an offscreen footer. Earlier failed or misframed captures are not final acceptance evidence.
- A broader rerun in `browser-reference-response-final/` timed out waiting for the authenticated `/admin/training` overview after 90 seconds. Temporary authentication was closed and sensitive timeout headers were redacted. This Admin performance issue was not fixed or reverified by the focused final result-page check; do not interpret the final pass as a fresh pass of every Admin workflow.
- One browser attempt failed because both local servers had stopped. The existing hidden launcher restarted API/web successfully on 8000/8080. No other process was stopped.

## Unchanged / Remaining

- No backend/model/Dataset changes, retraining, split reassignment, authorization override or numerical-gate changes in this task.
- Outcome percent prediction remains unavailable under its existing data-use/evaluation requirements; this delivery is real descriptive evidence, not a newly trained predictor.
- Existing analysis errors, including possible ASR topic omissions, are not corrected by displaying reference outcomes.
- Results without sufficient frozen evidence show an explicit empty state rather than acquiring fresh evidence silently.

## Access

- Web: `http://127.0.0.1:8080/#/history`.
- Reopen `review camera` and scroll to section 3. If an already-open tab still shows the old planner, reload the application with Ctrl+F5, not only the result-data refresh icon.
