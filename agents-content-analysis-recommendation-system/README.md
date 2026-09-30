# Content AI Analysis Recommendation System

เว็บแอปสำหรับวิเคราะห์คลิปรีวิวความยาวไม่เกิน 5 นาที ถอดเสียงด้วย Faster Whisper
จำแนกหมวดหมู่แบบหลายระดับ สกัดคำสำคัญ และเปรียบเทียบกับ Transcript จากวิดีโอ
YouTube สาธารณะในหมวดเดียวกันที่ผ่านการตรวจโดยมนุษย์ เพื่อแนะนำ keyword gap
และความยาวคลิปที่เหมาะสม

## System Components

- Backend: FastAPI, SQLAlchemy, background jobs
- Database: MySQL หรือ SQLite สำหรับ local development
- Frontend: Flutter Web
- Speech-to-Text: Faster Whisper multilingual `small`
- Live dashboard: YouTube, Google Trends และ TikTok แบบ partial result
- Recommendation dataset: public YouTube metadata + source transcript + human-reviewed label

## Important Dataset Policy

ระบบไม่มี demo seed สำหรับ Classification หรือ Recommendation อีกต่อไป ข้อมูลหนึ่งแถวจะถูกใช้จริงได้เมื่อผ่านเงื่อนไขทั้งหมด:

- YouTube API ยืนยันว่าวิดีโอเป็น Public และบันทึก License จริงของแต่ละคลิป
- วิดีโอต้นทางมี duration ที่ตรวจสอบได้ โดยไม่จำกัดความยาวของ source video
- มี transcript ภาษาไทยหรืออังกฤษจาก public caption หรือ NotebookLM manual import
- คนตรวจวิดีโอ, transcript และหมวดหมู่ แล้วระบุ `decision=approve`
- มี reviewer, reviewed time, transcript quality, source URL และ license provenance ครบ
- อยู่ใน taxonomy `content-taxonomy-v1`
- แบ่ง train/validation/test ตาม Channel ID เพื่อป้องกันข้อมูลช่องเดียวกันรั่วข้ามชุด

Search query ใช้ค้นหา candidate เท่านั้น ไม่ถือเป็น label จริง ระบบจะไม่เปิดหมวดให้ AI
จนกว่าจะมีข้อมูลที่ผ่าน human review อย่างน้อย 30 คลิปในหมวดนั้น

Dataset จะเก็บ transcript ช่วง 300 วินาทีแรกของวิดีโอต้นทาง เพื่อให้ training input
สอดคล้องกับคลิปผู้ใช้ที่อัปโหลดได้ไม่เกิน 5 นาที แถวที่ผ่าน review ใช้ฝึก Classification
และเป็นหลักฐาน Keyword Recommendation ได้ทุกความยาว แต่จะใช้เป็นหลักฐาน Recommended
Duration เฉพาะเมื่อ source video ยาวไม่เกิน 300 วินาที

## Taxonomy V1

หมวด Level 3 รุ่นแรกมี 12 หมวด:

`Phone`, `Camera`, `Laptop`, `Audio`, `Headphone`, `Hardware`, `Food`,
`Drink`, `Makeup`, `Grooming`, `Shirt`, `Shoes`

คลิปที่ไม่อยู่ในขอบเขตหรือมีหลักฐานไม่พอจะได้ผลลัพธ์ `Unknown/Other`

## Public View-Count Migration

For an existing database, apply the public view-count version migration:

```powershell
python -B scripts/migrate_view_metrics.py
```

This records which YouTube public `viewCount` definition produced each sample
and prevents Dashboard and Recommendation comparisons across the 24 August
2026 definition change.

## Backend Setup

```powershell
cd Z:\content-ai.worktrees\agents-content-analysis-recommendation-system
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

ค่าหลักใน `.env`:

```env
DB_DRIVER=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=content_ai
DB_USER=root
DB_PASSWORD=1234
JWT_SECRET=change-this-secret
ADMIN_INVITE_CODE=admin-local
YOUTUBE_API_KEY=your-youtube-data-api-key
YOUTUBE_REGION=TH
ASR_MODEL_SIZE=small
ASR_MODEL_DIR=models_cache/faster_whisper
ASR_LOCAL_FILES_ONLY=1
ASR_REQUIRE_MODEL_READY=1
ASR_LANGUAGE=auto
```

User uploads are limited to 300 seconds. Flutter reads video metadata before
upload and the backend verifies it again with `ffprobe`. Accepted videos are
transcribed in full. The configured hook duration only selects timestamped ASR
segments for hook-keyword analysis; it does not truncate the main transcript.

เตรียมโมเดลและ schema:

```powershell
python -B scripts/setup_faster_whisper.py --model small
python -B scripts/setup_faster_whisper.py --model small --verify-only
python -B scripts/migrate_youtube_cc_dataset.py
```

รัน backend:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

ตรวจระบบที่ `http://127.0.0.1:8000/health`

สร้างบัญชี Admin ครั้งแรก คำสั่งจะถามรหัสผ่านโดยไม่แสดงหรือบันทึกลงไฟล์:

```powershell
python -B scripts/create_admin_user.py --username admin --email admin@example.com
```

## Flutter Setup

เปิด PowerShell อีกหน้าต่าง:

```powershell
cd Z:\content-ai.worktrees\agents-content-analysis-recommendation-system\frontend_flutter
flutter pub get
flutter run -d edge --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

## Build Public YouTube Research Dataset

ขั้นตอนนี้ไม่ดาวน์โหลดไฟล์วิดีโอ Collector ใช้ YouTube Data API เพื่อค้นหา Public videos
และบันทึก License จากนั้นใช้ `youtube-transcript-api` เพื่ออ่าน public captions
ที่หน้า YouTube เปิดให้ดูได้

### 1. Collect Candidates

เริ่มทดสอบหนึ่งหมวดก่อน:

```powershell
python -B scripts/collect_youtube_cc_candidates.py `
  --leaves phone `
  --target-per-leaf 5 `
  --languages th `
  --region TH
```

เมื่อทดสอบผ่านแล้วให้เก็บครั้งละ 2-3 หมวดเพื่อควบคุม YouTube search quota:

```powershell
python -B scripts/collect_youtube_cc_candidates.py `
  --leaves phone,camera,laptop `
  --target-per-leaf 50 `
  --performance-per-leaf 15 `
  --min-thai-per-leaf 50 `
  --languages th `
  --region TH `
  --max-pages-per-query 1
```

The 50-row target is split into 15 `recommendation_high_performance` candidates
discovered with `order=viewCount` and 35 `classification_diverse` candidates
discovered with `order=relevance`. Existing YouTube IDs and transcript hashes in
both `dataset_contents` and earlier collection artifacts are skipped. Videos from
the same channel are allowed; collection does not impose a per-channel cap. Sources
may be longer than 5 minutes; the collector keeps their full duration metadata and
uses the first 300 transcript seconds for legacy collector candidates. The
NotebookLM import path below accepts the complete source transcript with no
training-duration limit. Only user uploads and duration-recommendation evidence
remain limited to 300 seconds.

The production application is Thai-first. New collection runs default to
`--languages th`; only human-reviewed Thai transcripts count toward taxonomy
readiness, model training, and recommendation evidence. Existing English rows
remain in storage for provenance but are excluded from the production dataset
query.

เมื่อใช้โหมดภาษาไทย เป้าหมาย 50 candidate ต่อ leaf หมายถึง transcript ภาษาไทย 50 รายการ
และรับไม่เกิน 3 คลิปจาก Channel ID เดียวกันต่อ leaf กติกานี้นับร่วมกับ candidate artifacts
และ production dataset เดิม การข้ามเพราะภาษาไม่ตรงหรือเกิน channel cap จะถูกบันทึกเป็น
`quality_filters` โดยไม่ถูกนับเป็น collection error

If a schema-version-4 run ends as `partial` or `quota_waiting`, continue it from
the saved page tokens:

```powershell
python -B scripts/collect_youtube_cc_candidates.py `
  --resume-run-id YOUR_RUN_ID `
  --max-pages-per-query 1
```

The CLI uses a conservative 30-minute pacing profile by default: at most three
public-transcript attempts per execution, a 60-90 second delay between attempts,
and an enforced 30-minute cooldown before the same paused run can resume. An
early resume exits without contacting the provider. An explicit provider block
uses a separate 24-hour guard. These controls reduce rate-limit risk but cannot
guarantee availability of the unofficial public-transcript endpoint.

For Run 7, the guarded command is:

```powershell
python -B scripts/collect_youtube_cc_candidates.py `
  --resume-run-id 7 `
  --max-pages-per-query 1
```

To narrow an unfinished, unreviewed legacy run from `th,en` to Thai-only before
resuming it:

```powershell
python -B scripts/retarget_youtube_cc_run.py --run-id YOUR_RUN_ID --languages th
```

Non-Thai candidates are moved to a hashed `excluded-for-th.jsonl` audit artifact;
they are not silently deleted.

A run with any human review event cannot be resumed because its candidate
artifact is immutable. Start a new run instead; cross-run deduplication keeps
previous approved, rejected, and pending candidates out of the new artifact.
Runs created under the old five-minute source filter, including local run 2, also
must not be resumed because pages already scanned by that run omitted long videos.
Start a new run after API quota is available; the 35 preserved candidates from run 2
will be skipped automatically.

### NotebookLM Full-Transcript Import

Use `/#/admin-transcript-import` when the unofficial transcript provider is
rate-limited. Paste a public YouTube URL and the complete source
transcript displayed by NotebookLM. Do not paste an AI summary or rewritten answer.

The backend verifies current YouTube metadata, public status, recorded license,
duration, source channel identity, YouTube-ID duplication, and transcript hash duplication
before creating a candidate. Public captions are required only for the automatic
collector, not for a transcript supplied through NotebookLM. The candidate still requires an Admin
Approve/Reject decision in `/#/admin-dataset-review`; it never enters
`dataset_contents` directly.

Several items can be added to the same NotebookLM batch until its first review
decision. After review starts, use the new-batch button before importing more items.
Full transcripts from videos longer than five minutes are eligible for classification
and keyword training, but are excluded from recommended-duration calculations.

ระหว่างรัน CLI จะแสดง progress แยก leaf, Thai transcript และจำนวนช่องหลังทุก checkpoint
หน้า Admin `Dataset Review` แสดงข้อมูลชุดเดียวกัน เมื่อ YouTube ตอบ HTTP 429 ระบบใช้สถานะ
`quota_waiting`, เก็บ checkpoint และไม่นับเหตุการณ์นี้เป็น data error

ผลลัพธ์ถูกแยกเป็น:

- `data/raw/youtube_public/<version>/candidates-*.jsonl`: metadata และ transcript จริง
- `data/reviews/youtube_public/<version>/review-*.csv`: แบบฟอร์ม human review
- `data/manifests/youtube-public-*.json`: hash, config และผลการเก็บข้อมูล
- `dataset_collection_runs`: audit ของแต่ละรอบ

### 2. Human Review

เข้าสู่ระบบด้วยบัญชี Admin แล้วเปิดเมนู `Dataset Review` หรือ route
`/#/admin-dataset-review` หน้าเว็บจะแสดงวิดีโอ, transcript, automated checks,
หมวดที่ระบบเสนอ และ coverage ปัจจุบัน กด `Approve` หรือ `Reject` ได้โดยตรง

เมื่อ Approve ต้องยืนยัน `reviewed_leaf_key` และ `transcript_quality`; ระบบใส่ชื่อ Admin
กับเวลาตรวจจาก login session ให้อัตโนมัติ แล้วบันทึกทั้ง `dataset_contents`,
`dataset_review_events`, `system_logs` และ review artifact สำหรับ audit

ไฟล์ `review-*.csv` ยังใช้เป็นช่องทางสำรองสำหรับการตรวจแบบออฟไลน์ โดยกรอกคอลัมน์:

- `decision`: `approve` หรือ `reject`
- `reviewed_leaf_key`: หนึ่งใน 12 leaf keys เมื่อ approve
- `transcript_quality`: `good` หรือ `acceptable` เมื่อ approve
- `reviewer`: ชื่อหรืออีเมลผู้ตรวจ
- `reviewed_at`: ISO 8601 เช่น `2026-08-12T10:30:00+07:00`
- `review_notes`: เหตุผลหรือสิ่งผิดปกติที่พบ

ห้ามกรอก approve อัตโนมัติจาก search query เพราะ search query เป็นเพียง candidate label

### 3. Import Reviewed Rows

ไม่ต้องรันคำสั่งนี้เมื่อกดปุ่มผ่านหน้า Dataset Review เพราะหน้าเว็บ import แถวที่ตัดสินใจ
ให้ทันที ใช้คำสั่งนี้เฉพาะ workflow CSV แบบออฟไลน์:

```powershell
python -B scripts/import_youtube_cc_reviews.py `
  --candidates "data\raw\youtube_public\youtube-public-research-th-v1\candidates-YYYYMMDD-HHMMSS.jsonl" `
  --reviews "data\reviews\youtube_public\youtube-public-research-th-v1\review-YYYYMMDD-HHMMSS.csv"
```

Importer ทำงานแบบ atomic หาก review ที่กรอกแล้วมีแม้แต่หนึ่งแถวไม่ถูกต้อง จะไม่บันทึก
แถวใดในรอบนั้นเลย รายการ approve จะลง `dataset_contents`; approve/reject ทั้งหมดจะมี audit
ใน `dataset_review_events`

### 4. Verify Readiness

```powershell
python -B scripts/verify_submission_dataset.py
python -B scripts/verify_submission_dataset.py --require-ready
```

ดูรายหมวดผ่าน `GET /classification/taxonomy` ค่า `ready=true` หมายถึงหมวดนั้นมีอย่างน้อย
30 ตัวอย่างจริงที่ผ่านกติกา production ไม่ได้หมายถึงโมเดลผ่านเกณฑ์ความแม่นยำ 80% แล้ว

รายละเอียดเพิ่มเติมอยู่ใน [public YouTube dataset guide](docs/youtube_cc_dataset.md)

### 5. Train And Evaluate Classification Models

ตรวจ split และสร้าง artifact ล่วงหน้าได้แม้ Dataset ยังไม่ครบ โดยคำสั่งนี้จะไม่ train
และไม่สร้างแถวใน `classification_models`:

```powershell
python -B scripts/train_classification_models.py `
  --prepare-only `
  --model-version readiness-check-v1
```

เมื่อทั้ง 12 หมวดมีอย่างน้อย 30 ตัวอย่างจริง และทุกหมวดมีข้อมูลใน
train/validation/test ให้รัน benchmark:

```powershell
python -B scripts/train_classification_models.py `
  --model-version taxonomy-v1-run1 `
  --require-ready
```

For a scoped pilot, pass the reviewed leaves explicitly. Training never activates
a model automatically. After checking the report, activate only a `qualified`
model. Analyze Clip uses that artifact as its only category decision source and
returns `Unknown/Other` when no qualified active model is available:

```powershell
python -B scripts/train_classification_models.py `
  --leaves phone,camera,laptop `
  --minimum-samples-per-leaf 30 `
  --promotion-threshold 0.80 `
  --model-version three-leaf-pilot-v1 `
  --require-ready

python -B scripts/activate_classification_model.py --model-id <QUALIFIED_MODEL_ID>
```

Pipeline เปรียบเทียบ `TF-IDF + Logistic Regression`, `TF-IDF + ComplementNB`
และ `TF-IDF + SGD Logistic` โดยรายงาน Accuracy, Macro Precision, Macro Recall,
Macro F1, รายหมวด และ Confusion Matrix แยก validation/test และภาษา
ไทย/อังกฤษ ระบบรองรับ `Unknown/Other` ด้วย confidence rejection ที่ค่าเริ่มต้น
`0.60` โดยไม่สร้างตัวอย่าง Unknown ปลอม

โมเดลจะได้สถานะ `qualified` เมื่อ validation/test Accuracy และ Macro F1 ผ่าน
`0.80` ทุกค่า แต่ `is_active` ยังคงเป็น `false` เพื่อป้องกันการนำโมเดลที่ยังไม่
เชื่อม runtime ไปใช้โดยไม่ตั้งใจ ผลและ promotion gate ถูกบันทึกใน
`classification_models` และ `model_evaluation_metrics`; artifact อยู่ใต้
`artifacts/classification_training/` ซึ่งไม่ถูก commit

ระหว่างที่ Dataset ยังไม่ครบ สามารถใช้ข้อมูล human-reviewed ที่มีอยู่ตรวจเฉพาะ
การทำงานทางเทคนิคได้:

```powershell
python -B scripts/train_classification_models.py `
  --smoke-test `
  --model-version phase16-smoke-v1
```

ผลจากคำสั่งนี้มีสถานะ `smoke_test_only` เสมอ ไม่ผ่าน promotion gate และไม่ถูก
ตั้ง Active แม้คะแนนเชิงตัวเลขบางค่าจะถึง 0.80 โดย pipeline จะโหลด artifact
กลับมาทำนายหนึ่งตัวอย่างและบันทึก `reload_classify_passed` เป็นหลักฐานด้วย

## Phase 22 Classification Development

Phase 22 ใช้เป้าหมายขั้นต่ำ 80 ตัวอย่างต่อหมวด เป้าหมายแนะนำ 100 ตัวอย่าง
และอย่างน้อย 10 ช่องต่อหมวด สำหรับ `phone`, `camera`, และ `laptop` ควรเพิ่ม
hard cases ที่ใช้ภาษาคล้ายกัน โดยเฉพาะรีวิวกล้องมือถือ, gaming laptop และอุปกรณ์เสริม
ที่ไม่ใช่โทรศัพท์ พร้อมเก็บ out-of-scope ที่ผ่าน human review 30-50 ตัวอย่าง

การ benchmark เปรียบเทียบ 4 แนวทาง:

1. Word/character TF-IDF + Complement Naive Bayes
2. Word/character TF-IDF + tuned Logistic Regression
3. Word/character TF-IDF + calibrated Linear SVM
4. Multilingual sentence embeddings + Logistic Regression

Logistic Regression ทดลอง `C=0.5,1.0,2.0,4.0` ด้วย Grouped CV และบันทึกคะแนน
ทุก candidate กับค่าที่เลือกไว้ใน report โดยไม่ใช้ `test` holdout ระหว่าง tuning

ระบบใช้ `StratifiedGroupKFold` กับ development pool (`train` + `validation`) โดยใช้
Channel เป็น group จึงไม่มีคลิปจากช่องเดียวกันอยู่ทั้งฝั่ง train และ validation ของ fold
เดียวกัน จากนั้น fit โมเดลสุดท้ายด้วย development pool ทั้งหมดและวัดครั้งสุดท้ายกับ
`test` holdout ที่ไม่เคยใช้เลือกโมเดล รายงานจะมี Accuracy, Macro Precision/Recall/F1,
Confusion Matrix, per-class recall, confusion pairs และ hard cases ที่ย้อนกลับถึง Dataset row ได้

Multilingual embedding benchmark จะไม่ดาวน์โหลดโมเดลเงียบ ๆ หาก cache ยังไม่มี ระบบจะ
รายงาน `skipped_unavailable`; ใช้ `--allow-embedding-download` เมื่อตั้งใจให้ดาวน์โหลดจริง
เมื่อมี cache แล้วระบบจะโหลดจาก local snapshot โดยไม่เรียก Hub ระหว่าง benchmark และหาก
โมเดลหนึ่งล้ม ระบบจะเก็บผลของโมเดลอื่นต่อโดยระบุ `failed_during_benchmark`

```powershell
python -B scripts/train_classification_models.py `
  --leaves phone,camera,laptop `
  --minimum-samples-per-leaf 30 `
  --grouped-cv-folds 5 `
  --promotion-threshold 0.80 `
  --model-version phase22-three-leaf-v1
```

คำสั่งข้างบนสร้าง baseline ได้แม้ยังไม่ถึง 80 ตัวอย่าง แต่ promotion gate จะไม่ให้สถานะ
`qualified` จนกว่า Phase 22 readiness, grouped-CV/test Accuracy, Macro F1, Recall ต่ำสุด
ของทุกหมวด และ Unknown recall จะผ่านทั้งหมด ใช้
`--require-phase22-ready` เมื่อต้องการให้คำสั่งคืน exit code 1 หากข้อมูลยังไม่ครบ และใช้
`--no-phase22-gate` เฉพาะ diagnostic comparison ที่ไม่ใช่โมเดลพร้อมใช้งานจริง

`Unknown/Other` ไม่ถูก fit เป็นคลาสจากข้อมูลปลอม Admin ต้องอนุมัติคลิปนอกขอบเขตเป็น
Unknown/Other เพื่อสร้าง evaluation-only rows ระบบจึงวัด Unknown recall และ false accept rate
ได้จริง แถวเหล่านี้ไม่เข้า Classification training, Keyword Gap หรือ Duration Recommendation

## Analyze Workflow

1. ผู้ใช้อัปโหลดวิดีโอไม่เกิน 5 นาที
2. Backend สร้าง `job_id`; Flutter polling `/jobs/{job_id}`
3. Pipeline แยกเสียงและถอดเสียงไทย/อังกฤษด้วย Faster Whisper
4. สกัด content keywords และ hook keywords
5. Classification ใช้ Active Model จำแนกจาก transcript ทั้งคลิปเพียงแหล่งเดียว
6. หากหมวดไม่พร้อมหรือ confidence ต่ำ ระบบคืน `Unknown/Other`
7. Recommendation เลือกคลิปผลงานสูงใน leaf เดียวกัน โดยใช้สถิติจริง ณ เวลา collect
8. คำนวณ keyword gap และ recommended duration จากแถวที่ใช้จริง
9. Result แสดง source, sample size, platform count, exemplar title และ warning เมื่อใช้ fallback

Classification ใช้ตัวอย่างทุกแถวด้วยน้ำหนักเท่ากัน เพื่อไม่ให้ช่องยอดนิยมครอบงำหมวด
Recommendation จึงค่อยเลือก top 40% จาก average views/day และ engagement rate
เพื่อใช้เป็นหลักฐานของคำแนะนำ

## Recommended Duration Evidence

- Duration comes from YouTube `contentDetails.duration` metadata recorded with each human-reviewed dataset row.
- The current cohort uses same-category videos up to 300 seconds so its recommendation is compatible with the user upload limit.
- Fewer than 10 eligible samples returns `Insufficient evidence`; 15 samples per category is the collection target.
- With sufficient evidence, the result reports the median and the P25-P75 range instead of estimating from one clip.
- A future dataset version should label content format and calculate separate cohorts for Short-form and general review videos.
- Legacy analysis rows without an auditable cohort are recalculated from the current verified dataset and never receive a synthetic `+/- 20 seconds` range.

## Dashboard Workflow

- Background scheduler เก็บ live trends เป็น snapshot ทุก 60 วินาที
- YouTube เก็บ `chart=mostPopular` แยก 12 `videoCategoryId` สูงสุดหมวดละ 50
  ทุก 15 นาที และ cache รายชื่อหมวด 24 ชั่วโมง
- อันดับรวมใช้ `ranking_scope=global`; อันดับรายหมวดใช้ `category:<id>`
  จึงเปรียบเทียบการขยับอันดับกับ snapshot ก่อนหน้าของหมวดเดียวกันเท่านั้น
- Endpoint dashboard อ่าน snapshot ล่าสุดจาก DB/cache ไม่ออกอินเทอร์เน็ตระหว่าง request
- Provider ใดล้ม ระบบยังคืน HTTP 200 พร้อมข้อมูลจาก provider ที่สำเร็จ
- หลัง login snapshot แรกเป็น baseline; snapshot ถัดไปสร้าง `new_live_trend` notification
  เฉพาะ trend key ใหม่และไม่แจ้งซ้ำใน session เดิม

## Database Tables For Dataset

- `dataset_collection_runs`: รอบค้นหา, query config, artifact hash และสถานะ collector
- `dataset_contents`: transcript ที่ approve แล้ว พร้อม taxonomy, license, statistics และ split
- `dataset_review_events`: audit ของ approve/reject และผู้ตรวจ
- `taxonomy_nodes`: โครงสร้าง Level 1-3 และ readiness ของแต่ละ leaf
- `classification_models`: version และสถานะโมเดล
- `model_evaluation_metrics`: accuracy/F1 ทั้งภาพรวมและรายหมวด

## Current Limitation And Next Step

`youtube-transcript-api` ไม่ใช่ YouTube Data API อย่างเป็นทางการ จึงอาจถูกจำกัดหรือเปลี่ยนแปลงได้
ส่วน Captions API ทางการอนุญาตให้ดาวน์โหลด caption เมื่อมี OAuth permission ที่เหมาะสมกับวิดีโอนั้น
เท่านั้น หาก transcript ดึงไม่ได้ Collector จะข้ามคลิป ไม่สร้าง transcript ปลอมและไม่ใช้ filename fallback
กับ training dataset

หลังได้อย่างน้อย 30-50 reviewed clips ต่อหมวด ขั้นต่อไปคือ train/evaluate classifier โดยแยกตาม
Channel ID และเปิด active model เฉพาะเมื่อ macro F1 และผลรายหมวดผ่านเกณฑ์ที่กำหนด เช่น 0.80

## Tests

```powershell
python -m compileall -q app scripts tests
python -m unittest discover -s tests -v
cd frontend_flutter
flutter test
```
