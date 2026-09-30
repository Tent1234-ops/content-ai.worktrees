# TikTok Trend Source Feasibility

Checked on 2026-09-07 from the project development machine. No production
provider, dashboard, database records, credentials or paid services were changed.

## Intended User Benefit

Show trending hashtags as topic ideas for creators, with source-provided region,
time window and ranking. This is different from a national video leaderboard.
Do not present post counts as searches, viewers or views.

## Observed Results

1. An unauthenticated HTTP request to the previous Creative Center hashtag URL
   returned HTTP 200 and redirected to `/creative/creativeCenter/trends`.
   The response contained 21,345 characters; the old `__NEXT_DATA__` payload was
   absent. No usable ranked dataset was established by this check. HTTP 200
   alone does not establish a successful data import.
2. A fresh, headless Edge session without user credentials failed to navigate
   to the old URL (`ERR_HTTP_RESPONSE_CODE_FAILURE`).
3. A separate check of the canonical destination returned HTTP 403. The visible
   page said "Access to ads.tiktok.com was denied". Testing stopped without
   attempting to bypass access controls or using personal login cookies.

The query requested `countryCode=TH&period=7`, but the actual data region and
window could not be validated. These observations apply to this machine and
session; they do not prove that the site is inaccessible to all users.

Local probe evidence:

- `artifacts/probe_creative_center.cjs`
- `artifacts/reports/tiktok/tiktok-creative-center-probe.json`
- `artifacts/screenshots/tiktok/tiktok-creative-center-probe.png`

## Decision

Do not connect this unverified source to the live dashboard yet. No fabricated
records, paid API fallback, or automatic imports were added. Instagram was not
implemented: account/hashtag data is not an equivalent national trend chart.

Before implementing a new provider, establish authorized access to real records,
verify their region/time window and ranking semantics, and repeat successful
collection. A third-party free tier would also require its own API token and a
measured zero-spend usage limit; it is not a verified fallback in this project.

The existing TikTok provider reads the public Discover page and extracts
`SIGI_STATE.ItemModule`. Its `region` parameter does not select a national chart,
so its response order should not be promoted as a verified Thailand ranking.

Public source: https://ads.tiktok.com/help/article/creative-center?lang=en
