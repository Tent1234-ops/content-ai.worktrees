# Content AI API

Base URL สำหรับ local development: `http://127.0.0.1:8000`

เปิดเอกสาร OpenAPI แบบ interactive ได้ที่:

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

Endpoint ที่ระบุว่าต้อง login ใช้ header:

```http
Authorization: Bearer <access_token>
```

## Health

### `GET /`

สถานะย่อของ backend, database migration และ taxonomy

### `GET /health`

ตรวจ database, Faster Whisper model และสถานะ live trend providers

## Authentication

- `POST /auth/register`: สมัครสมาชิก
- `POST /auth/login`: เข้าสู่ระบบและสร้าง trend watch session baseline
- `POST /auth/logout`: ปิด login session
- `GET /auth/me`: ข้อมูลผู้ใช้ปัจจุบัน

## Analyze Clip

### `POST /analyze`

รับ multipart video จากผู้ใช้ความยาวไม่เกิน 300 วินาที แล้วคืน `job_id`

```json
{
  "job_id": "...",
  "status": "queued"
}
```

### `GET /jobs/{job_id}`

Frontend polling endpoint สถานะหลักคือ `queued`, `running`, `completed`, `failed`
พร้อม `stage`, `progress`, `message` และ `result` เมื่อเสร็จ

### `POST /analyze/save`

วิเคราะห์และบันทึกผลลง My Ideas ตาม workflow ที่รองรับใน frontend

## Classification And Recommendation

### `GET /classification/taxonomy`

คืนโครงสร้าง `content-taxonomy-v1`, readiness และ sample coverage ของ 12 leaf categories
หนึ่ง leaf พร้อมใช้เมื่อมี public YouTube transcripts ที่ผ่าน human review อย่างน้อย
30 แถวตาม production eligibility contract

### `POST /classification/text`

จำแนกข้อความเป็น Level 1 > Level 2 > Level 3 หากหมวดยังไม่พร้อมหรือความมั่นใจต่ำ
ระบบคืน `Unknown/Other`

### `GET /recommendation/profiles`

ดู recommendation profiles ของหมวดที่พร้อม

### `POST /recommendation/from-text`

สกัด user keywords, keyword gap, hook keywords และ recommended duration
Evidence ใช้เฉพาะ human-reviewed public YouTube rows ใน leaf เดียวกัน

### `GET /recommendation/from-content/{content_id}`

สร้างคำแนะนำจากคลิปที่ผู้ใช้บันทึกไว้

### `GET /recommendation/admin/report`

รายงาน dataset/profile health สำหรับ Admin

## Dataset

- `GET /datasets/youtube`: ดูข้อมูล YouTube ที่บันทึก
- `GET /datasets/google`: ดูข้อมูล Google ที่บันทึก
- `GET /admin/datasets`: Admin ดูและค้นหา dataset
- `POST /admin/datasets`: Admin เพิ่มแถวทั่วไป
- `PUT /admin/datasets/{dataset_id}`: Admin อัปเดตแถว

การเพิ่มแถวผ่าน Admin ไม่ทำให้เป็น training data อัตโนมัติ Production training row ต้องผ่าน
YouTube review importer และกติกาใน `app/services/dataset_eligibility.py`

## Dashboard And Trends

- `GET /dashboard/overview`: สรุป dashboard
- `GET /dashboard/summary`: สถิติภาพรวม
- `GET /dashboard/live-trends/snapshot`: snapshot ล่าสุดจาก DB/cache
- `POST /dashboard/refresh`: ขอ refresh trend job
- `GET /dashboard/emerging-topics`: หัวข้อที่กำลังเกิดใหม่
- `GET /trends/youtube`: YouTube trends
- `GET /trends/google`: Google trends
- `GET /trends/tiktok`: TikTok trends
- `POST /trends/{platform}/sync`: Admin sync provider

Live snapshot endpoint ไม่ดึงอินเทอร์เน็ตระหว่าง request และคืน partial result เมื่อ provider บางตัวล้ม

## Notifications

- `GET /notifications/`: รายการ `new_live_trend` ของ session ปัจจุบัน
- `POST /notifications/mark_read`: ทำเครื่องหมายว่าอ่านแล้ว

Login snapshot แรกเป็น baseline โดยไม่แจ้งเตือน รอบถัดไปสร้าง notification เฉพาะ trend key ใหม่
และ unique ต่อ user/watch session

## Followed Topics

- `POST /follows/topic`: ติดตามหัวข้อ
- `GET /follows/topics`: ดูหัวข้อที่ติดตาม
- `DELETE /follows/topic/{id}`: ยกเลิกติดตาม

Followed topics เป็น feature แยก ไม่ใช่ core notification trigger

## User Content

- `GET /contents/my`: ประวัติการวิเคราะห์และ My Ideas
- `GET /contents/{content_id}`: รายละเอียดผลที่บันทึก

## NLP And Clustering

- `POST /nlp/extract`
- `POST /nlp/extract/save`
- `POST /clustering/kmeans`
- `POST /clustering/hdbscan`
- `POST /clustering/kmeans/save`
- `POST /clustering/hdbscan/save`
- `POST /clustering/from-dataset`

## Admin

### Dataset Review Queue

```http
GET /admin/dataset-review/queue?status=pending&limit=12&offset=0
Authorization: Bearer <admin-token>
```

### Import NotebookLM Source Transcript

```http
POST /admin/dataset-review/notebooklm/candidates
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "transcript": "Complete source transcript from NotebookLM...",
  "proposed_leaf_key": "phone",
  "transcript_language": "th",
  "caption_type": "unspecified",
  "collection_strategy": "classification_diverse",
  "collection_run_id": null,
  "dataset_version": "youtube-public-research-th-v1"
}
```

Use the returned `collection_run_id` for the next item to append candidates to the
same batch. A batch becomes immutable after its first review decision.

ตัวกรองที่รองรับ: `status`, `leaf_key`, `collection_run_id` และ `search` ผลลัพธ์มี
candidate transcript, automated checks, taxonomy coverage และสถานะ review ของแต่ละรายการ

### Review Dataset Candidate

```http
POST /admin/dataset-review/runs/{collection_run_id}/candidates/{source_youtube_id}
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "decision": "approve",
  "reviewed_leaf_key": "phone",
  "transcript_quality": "good",
  "notes": "Video and transcript match the selected category."
}
```

เมื่อ Approve ระบบ import แถวเข้า production dataset ทันที ส่วน Reject จะเก็บ audit event
โดยไม่สร้าง training row ชื่อผู้ตรวจและเวลามาจาก Admin login session ฝั่ง Backend

- `GET /admin/me`
- `GET /admin/logs`
- `GET /admin/clusters/runs`
- `GET /admin/clusters/runs/{run_id}`
- `GET /admin/reports/overview`
- `GET /admin/settings`
- `PUT /admin/settings`
- `POST /admin/settings/validate`
- `POST /admin/settings/reset`
- `GET /admin/statistics`
- `GET /admin/sources`
- `PUT /admin/sources/{source_name}`
- `POST /admin/scan/youtube`
- `POST /admin/scan/google`
- `POST /admin/scan/tiktok`

## Error Format

FastAPI validation และ application errors ใช้ HTTP status ที่เหมาะสม เช่น 401, 403, 404,
422 และ 500 โดยรายละเอียดอยู่ใน `detail`

```json
{
  "detail": "Explanation"
}
```

Live trends เป็นข้อยกเว้นด้าน availability: provider บางตัวล้มได้โดย endpoint snapshot ยังตอบ 200
และระบุสถานะราย provider ใน payload
