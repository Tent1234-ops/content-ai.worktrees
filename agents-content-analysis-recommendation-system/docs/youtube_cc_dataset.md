# Public YouTube Transcript Dataset For Academic Research

## Objective

สร้างชุดข้อมูลสำหรับ Classification และ Recommendation ของโครงงานมหาวิทยาลัย โดยใช้
metadata ของวิดีโอ YouTube สาธารณะ, transcript จาก public caption หรือ NotebookLM manual
import และ label ที่มนุษย์ตรวจ ไม่ใช้ generated label หรือ demo seed เป็น production evidence
ระบบไม่ดาวน์โหลดหรือเผยแพร่ไฟล์วิดีโอต้นฉบับ และไม่เผยแพร่ Dataset ภายนอกโครงงาน

`YouTube Standard License` ไม่ได้ให้สิทธินำผลงานไปใช้ซ้ำแบบเดียวกับ CC BY การเก็บแถว
ประเภทนี้จึงถูกจำกัดไว้สำหรับการศึกษา/ประเมินระบบภายในโครงงาน และต้องตรวจนโยบายของ
สถาบันหรือขออนุญาตเจ้าของสิทธิ์ก่อนเผยแพร่ Dataset, โมเดล หรือใช้งานนอกขอบเขตดังกล่าว

## Data Flow

```text
Project taxonomy queries
        |
        v
YouTube search.list
  type=video
  videoCaption=closedCaption
        |
        v
YouTube videos.list
  snippet, contentDetails, statistics, status
        |
        +-- record: Standard YouTube or Creative Commons license
        +-- reject: video is not public
        +-- reject: duration is missing or invalid
        +-- reject: no supported public transcript
        |
        v
caption transcript + candidates.jsonl + SHA-256 manifest
        |
        v
Human review: video + transcript + Level 3 label
        |
        +-- reject -> dataset_review_events only
        +-- approve -> dataset_contents + dataset_review_events
        |
        v
Channel-grouped train / validation / test
```

หน้า Admin `/#/admin-dataset-review` เป็น review workflow หลัก ผู้ตรวจเปิดวิดีโอ อ่าน
transcript เลือกหมวดและคุณภาพ แล้วกด Approve/Reject ได้โดยไม่แก้ CSV เอง ชื่อผู้ตรวจและเวลา
มาจากบัญชี Admin ที่ login อยู่ ส่วน CSV ยังคงเป็นหลักฐานและช่องทาง offline fallback

## Why Human Review Is Required

คำค้น เช่น `รีวิวมือถือ` บอกเพียงเหตุผลที่ระบบพบวิดีโอ ไม่ยืนยันว่าคลิปนั้นเป็น Phone จริง
Reviewer จึงต้องดูคลิปหรืออ่าน transcript แล้วตัดสิน Level 3 label เอง Search query ถูกเก็บไว้
เพื่อ audit แต่ไม่ถูกใช้เป็น label ที่ผ่านการตรวจ

## Review Rules

Approve เมื่อครบทุกข้อ:

1. ลิงก์เปิดได้และตรงกับ metadata
2. วิดีโอเป็น Public และระบบบันทึก License ณ เวลาที่ collect
3. เนื้อหาหลักอยู่ใน taxonomy leaf ที่เลือก
4. Transcript สะท้อนเสียงในคลิปและมีข้อมูลพอสำหรับจำแนก
5. Duration ของวิดีโอต้นทางตรวจสอบได้และมากกว่า 0 วินาที
6. เนื้อหาในช่วง transcript 300 วินาทีแรกชัดพอที่จะตรวจ label
7. ระบุ reviewer และเวลาตรวจจริง

ใช้ `transcript_quality=good` เมื่อ transcript ถูกต้องชัดเจน และ `acceptable` เมื่อมีความผิดพลาด
เล็กน้อยแต่ยังรักษาความหมายสำคัญ Reject เมื่อ transcript ผิดคลิป, ว่าง, อ่านไม่ได้ หรือหมวดไม่ชัด

## Production Eligibility

### NotebookLM acquisition path

NotebookLM is an acquisition method, not the dataset source and not the labeler.
The underlying source remains a public YouTube video. The backend records whether
YouTube reports `status.license=youtube` or `status.license=creativeCommon`.
Admins paste the exact source transcript, not a NotebookLM summary, into
`/#/admin-transcript-import`.

The backend verifies public metadata and records the license, creates an immutable hashed candidate,
deduplicates by YouTube ID and transcript SHA-256, and sends it through the same
human review workflow. Approved rows record:

```text
transcript_source             = notebooklm_source_transcript
transcript_acquisition_method = notebooklm_manual_source
transcript_scope              = full_video
transcript_timestamps_available = false
```

Training transcripts have no five-minute duration limit. Full transcripts from long
videos can be used for Classification and Keyword Recommendation. Only user uploads
and `is_duration_recommendation_eligible` remain limited to 300 seconds.

`app/services/dataset_eligibility.py` เป็น contract กลาง Classification, Recommendation และ
readiness coverage ใช้ query เดียวกัน จึงไม่มี endpoint ใดดึง candidate ที่ยังไม่ตรวจไปใช้ได้

ค่าหลักของแถว production:

```text
dataset_source      = youtube_public_research
verification_status = human_verified
label_source        = human_review
transcript_source   = youtube_public_caption
taxonomy_version    = content-taxonomy-v1
is_training_eligible = true
is_keyword_recommendation_eligible = true
is_duration_recommendation_eligible = true/false ตาม source duration
is_active            = true
```

ความยาววิดีโอต้นทางไม่ถูกจำกัดที่ 5 นาที เพราะ source ที่ยาวกว่านั้นยังเป็นตัวอย่างจริงสำหรับ
Classification และ Keyword Recommendation ได้ อย่างไรก็ตาม ระบบเก็บ transcript เฉพาะช่วง
300 วินาทีแรกเพื่อให้ distribution ตรงกับ input ผู้ใช้ และกำหนด
`is_duration_recommendation_eligible=true` เฉพาะ source ที่ยาวไม่เกิน 300 วินาที เพื่อไม่ให้
วิดีโอแบบ long-form บิดคำแนะนำความยาวของ short review

## Split And Leakage Control

ระบบ hash `source_channel_id` แล้วกำหนด split แบบคงที่ 70/15/15 วิดีโอจากช่องเดียวกันจึงอยู่
split เดียวกันทั้งหมด วิธีนี้ลดโอกาสที่สำนวนหรือชื่อสินค้าจาก creator เดิมจะอยู่ทั้ง train และ test

## Recommendation Evidence

### Bulk collection strategies

Each leaf has two explicit candidate sampling targets:

1. `recommendation_high_performance` uses YouTube Search `order=viewCount` first.
2. `classification_diverse` uses `order=relevance` to fill the remaining target.

Candidate rows store the discovery strategy, lifetime statistics captured at
collection time, average views per day, engagement rate, and a reproducible
performance signal. Human approval is still required before either strategy can
enter the production dataset.

The collector checkpoints JSONL, review CSV, manifest, hashes, counters, and
the next page token after each successful search page. Resume uses the same run
ID and page tokens. It is blocked after the first review event so reviewed
artifacts cannot change. New runs deduplicate against both approved database
rows and all registered candidate artifacts by YouTube ID and transcript hash.

Collection schema version 4 adds two dataset quality gates:

1. Production collection is Thai-only by default. The collector uses Thai search
   queries, requests Thai public captions, and never machine-translates English
   transcripts to satisfy the target. Legacy English rows remain auditable but do
   not count toward taxonomy readiness, model training, or recommendation evidence.
2. Accept at most 3 videos from one Channel ID in one leaf, counting prior
   production rows and registered candidate artifacts, to reduce creator leakage.

Phone and Camera discovery queries include stronger product/context terms and
negative terms for common false positives. Search queries remain discovery hints;
only human review assigns the final label. The manifest, CLI checkpoint output,
and Admin Dataset Review page report progress by leaf, transcript language, and
unique channel count.

An unfinished and unreviewed bilingual run can be narrowed without losing its
audit history:

```powershell
python -B scripts/retarget_youtube_cc_run.py --run-id YOUR_RUN_ID --languages th
```

The command keeps Thai candidates in the active artifact and archives excluded
rows in a separate hashed JSONL artifact. It refuses to mutate a run after any
review decision or review event exists.

Classification ใช้ train rows ทุกแถวในหมวดที่พร้อมด้วยน้ำหนักเท่ากัน ส่วน Recommendation:

1. Query เฉพาะ taxonomy leaf เดียวกับคลิปผู้ใช้
2. จัดอันดับด้วย performance signal จาก average views/day และ engagement rate ณ เวลา collect
3. เลือก top 40% อย่างน้อย 10 รายการ หาก pool มีเพียงพอ
4. สกัด keyword frequency จากทุกรายการที่เลือกจริง แต่คำนวณ duration เฉพาะแถวที่
   `is_duration_recommendation_eligible=true`
5. ส่ง dataset row IDs, YouTube IDs, exemplar titles และ sample counts ไปกับ evidence

ค่า statistics เป็น snapshot ณ เวลา collect ไม่ใช่ยอดปัจจุบันแบบ live

## Public View-Count Metric Versions

YouTube changes the public `viewCount` definition for long-form videos and live
streams on 24 August 2026. The old public value and the new play-start value are
not directly comparable. Every statistics sample is therefore stamped with a
`view_metric_version`:

- `youtube_qualified_view_v1`: collected before 24 August 2026
- `youtube_play_start_view_v2`: collected on or after 24 August 2026

Dashboard momentum starts a new baseline when the version changes.
Recommendation ranking first selects one compatible metric cohort, then ranks
high-performing examples only inside that cohort. The application does not try
to recover historical `engagedViews` for arbitrary public Creative Commons
videos because that owner-level value requires YouTube Analytics/Reporting
authorization for the source channel.

Each candidate JSON row and imported `dataset_contents` row stores the version.
The collection manifest also records counts by version because one resumable
run can span the change date.

Apply the schema and backfill migration before collecting or serving new data:

```powershell
python -B scripts/migrate_view_metrics.py
```

## Collector Resume And Quota

`pacing_paused` is a resumable checkpoint, not a failed run. Public transcript
retrieval is performed one video at a time and can be temporarily rate-limited
independently of YouTube Data API quota. The collector intentionally pauses
after a small number of attempts, saves its progress, and resumes with the same
run ID so completed searches and deduplication work are not repeated.

The command-line collector defaults to a guarded 30-minute profile: three
transcript attempts per execution, 60 seconds of base delay plus up to 30 seconds
of jitter, and a minimum 30-minute cooldown between `pacing_paused` resumes. If
the provider explicitly reports an IP/request block, the guard becomes 24 hours.
Running before the guard expires sends no provider request. This is a risk
control for an unofficial endpoint, not a guarantee that the provider will
never rate-limit an address.

Do not approve or reject a paused run before collection reaches
`review_pending`; a run with review events is immutable.

Collector บันทึก checkpoint หลังแต่ละ search page หาก YouTube ตอบ HTTP 429 ระบบบันทึกสถานะ
`quota_waiting` แทน `failed` และไม่นับเป็น data error จากนั้น resume run เดิมได้เมื่อ quota
พร้อมอีกครั้ง อย่างไรก็ตาม run ที่สร้างก่อน schema version 3 เคยตัด source video ที่ยาว
เกิน 300 วินาทีทิ้ง จึงห้าม resume ภายใต้นโยบายใหม่ ให้เริ่ม collection run ใหม่แทน ระบบจะ
deduplicate YouTube ID และ transcript hash กับ candidates เดิมโดยอัตโนมัติ

## Reproducibility

เก็บ SHA-256 ของ candidate JSONL, review CSV, transcript และ import batch ทุกครั้ง
หากมีการแก้ artifact หลัง collect/import hash จะไม่ตรงและ importer ปฏิเสธข้อมูล

## Classification Training And Evaluation

`scripts/train_classification_models.py` อ่านเฉพาะแถว production ที่ผ่าน human
review จาก `dataset_contents` และตรวจ split จาก Channel ID ซ้ำอีกครั้งก่อน train
หากช่องเดียวกันรั่วข้าม split หรือหมวดใดไม่มี train/validation/test ระบบคืน
`not_ready` และไม่สร้าง model row

Dataset artifacts ประกอบด้วย `train.jsonl`, `validation.jsonl`, `test.jsonl`,
SHA-256 และ manifest ที่ระบุ Dataset version, taxonomy version, ภาษา, จำนวนช่อง
และจำนวนตัวอย่างรายหมวด Phase 22 benchmark โมเดลสี่แบบ:

1. Word/character TF-IDF + Complement Naive Bayes
2. Word/character TF-IDF + tuned balanced Logistic Regression
3. Word/character TF-IDF + calibrated balanced Linear SVM
4. Multilingual sentence embeddings + balanced Logistic Regression

Logistic Regression ทดลองค่า `C` เท่ากับ `0.5`, `1.0`, `2.0`, และ `4.0`
ด้วย grouped CV แล้วเลือกจาก Macro F1, Accuracy และ Recall ต่ำสุดรายหมวดตามลำดับ
ก่อน fit ตัวสุดท้าย โดยไม่ใช้ `test` holdout ระหว่าง tuning

Development pool รวมแถว `train` และ `validation` ที่บันทึกไว้ แล้วประเมินด้วย
stratified grouped cross-validation โดยใช้ Channel ID เป็น group ทุกแถวจึงได้
out-of-fold prediction หนึ่งครั้ง และไม่มีช่องเดียวกันอยู่ทั้งฝั่ง train/validation
ของ fold เดียวกัน จากนั้น fit candidate สุดท้ายด้วย development pool ทั้งหมดและวัด
เพียงครั้งเดียวกับ `test` holdout ที่ไม่เคยใช้เลือกโมเดล รายงานระบุ hard-case Dataset
IDs, confusion pairs และ Recall รายหมวด

Phase 22 readiness requires 80-100 reviewed samples and at least 10 channels per leaf.
Human-reviewed `Unknown/Other` rows are evaluation-only: they are never fitted and are
used to measure Unknown recall and false acceptance. At least 30 such rows are required,
with 50 as the target. Numeric metrics alone cannot promote a model while this collection
gate is incomplete.

ระบบคำนวณ Accuracy, Macro Precision, Macro Recall, Macro F1, per-class metrics
และ Confusion Matrix สำหรับ validation/test พร้อมมุมมองแยกภาษาไทย/อังกฤษ
`Unknown/Other` ใช้ confidence rejection (`0.60` โดยค่าเริ่มต้น) จึงไม่เพิ่มข้อมูล
สังเคราะห์หรือ label ปลอมเข้า training set

Promotion gate กำหนดให้ grouped-CV/test Accuracy, Macro F1 และ Recall ต่ำสุดของ
แต่ละหมวดต้องผ่าน `0.80` ทุกค่า โมเดลที่ผ่านถูกบันทึกสถานะ `qualified`; โมเดลที่ไม่ผ่านเป็น
`evaluated_below_threshold` ทั้งสองสถานะยังมี `is_active=false` จนกว่าจะเชื่อม
artifact เข้ากับ runtime และ promote อย่างชัดเจน

Embedding model ถูก resolve เป็น local Hugging Face snapshot ก่อนโหลด เพื่อให้ benchmark
ทำงานแบบ offline ได้ หาก candidate model หนึ่งล้มระหว่าง benchmark ระบบบันทึก
`failed_during_benchmark` ให้โมเดลนั้นและเก็บผลโมเดลอื่นต่อ โดยต้องมีอย่างน้อยสองโมเดล
ที่รันสำเร็จจึงถือว่ารอบ benchmark ใช้งานได้

ก่อน Dataset พร้อม ใช้ `--smoke-test` เพื่อตรวจเส้นทาง train, metric persistence,
artifact reload และ prediction ได้ โหมดนี้ใช้เฉพาะข้อมูล human-reviewed จริงที่มี
อยู่ แต่ติดป้าย `smoke_test_only`, บล็อก promotion และห้ามอ้างว่าเป็นโมเดลสุดท้าย

## Source Notes

- YouTube Search API ใช้ค้นหาวิดีโอสาธารณะ โดย collector รุ่นปัจจุบันไม่กรองชนิด license
  และจะอ่าน `status.license` ของแต่ละวิดีโอแล้วเก็บค่าจริงแทน:
  https://developers.google.com/youtube/v3/docs/search/list
- Videos API ให้ duration, statistics และ `status.license`:
  https://developers.google.com/youtube/v3/docs/videos
- YouTube อธิบายความแตกต่างระหว่าง Standard YouTube License และ Creative Commons Attribution ที่:
  https://support.google.com/youtube/answer/2797468
- Official Captions API ต้องใช้สิทธิ์ OAuth ที่เหมาะสมสำหรับการดาวน์โหลด caption:
  https://developers.google.com/youtube/v3/guides/implementation/captions
- Public transcript collector ที่ใช้เป็น unofficial dependency:
  https://github.com/jdepoix/youtube-transcript-api

## Roadmap

1. Collect candidate มากกว่าจำนวนเป้าหมายประมาณ 1.5-2 เท่า เผื่อ reject
2. Human review อย่างน้อย 30-50 approved clips ต่อ leaf
3. ตรวจ class balance, language balance, creator distribution และ duplicate report
4. Train baseline classifier และบันทึก model version/metrics
5. เปรียบเทียบ candidate models ด้วย macro F1 และ per-class recall
6. เปิด active model เมื่อ test set ผ่านเกณฑ์ 0.80 ที่ตกลงกับอาจารย์
7. เพิ่มหมวดย่อยใหม่เฉพาะเมื่อมีข้อมูลจริงและ evaluation เพียงพอ
