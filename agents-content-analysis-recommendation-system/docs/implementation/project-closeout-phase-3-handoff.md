# Closeout Phase 3 Handoff: User/Admin Workflows

ตรวจและพัฒนา 2 ตุลาคม 2026 (เวลาไทย) เฉพาะ Closeout Phase 3

## สถานะ

**ผ่านเฉพาะส่วนที่ระบุ**: Follow, Notification logic, Scheduler, Dataset CRUD, Review/Import safeguards, Users, Analysis Settings และ Logs มี workflow/tests ตามขอบเขต Phase 3 แล้ว

ยังไม่ประกาศผ่าน delivery ของ Notification จาก provider สด เพราะระหว่างตรวจไม่ได้มีเทรนด์ใหม่จริง และไม่ได้เรียก provider เพิ่มเพื่อบังคับเหตุการณ์ ส่วนข้อปรับขอบเขต 11/13/15/17/18 ยังคง `pending` ตาม Phase 1 ไม่ได้ถือว่าอนุมัติแล้ว

## งานที่ทำ

- เพิ่ม UI `เพิ่ม Dataset สำหรับตรวจสอบ` ในหน้า `/admin-datasets` รายการใหม่ถูกบังคับเป็น `unassigned`, `is_training_eligible=false` และไม่เข้าแหล่งคำแนะนำอัตโนมัติ
- Backend normalize Transcript, สร้าง SHA-256, ตรวจ duplicate/hash ไม่ตรง และสร้าง taxonomy path จาก `taxonomy_leaf_key`; audit ระบุ source/taxonomy/split/eligibility
- เพิ่มการ sanitize รายละเอียด Log ก่อนส่งหน้า Admin: ตัด SQL traceback, redact API key/token/session/password/secret/cookie และจำกัดข้อความยาว โดยไม่แก้ audit ต้นฉบับใน DB
- เพิ่ม deterministic DB tests สำหรับ unread/read, owner/session isolation และ persistence หลังเปิด DB session ใหม่
- เพิ่ม UI test จำลอง reload/relogin ของ Follow แล้วตรวจว่ายังเลือกอยู่ ก่อน unfollow
- ติดตั้ง Windows Task Scheduler `ContentAI-Trends-D33AFF90B7` ด้วย `pythonw.exe`; trigger ตรวจทุกชั่วโมง แต่ DB เป็นผู้ตัดสิน due ตาม Asia/Bangkok 14:00–23:00 วันละ 10 รอบ
- Browser poll ยังคง 60 วินาทีและอ่าน DB เท่านั้น ไม่ได้เปลี่ยนเป็น provider fetch ทุก 60 วินาที
- ไม่อนุมัติ 42 รายการจริงที่ค้าง Review และไม่เปลี่ยน Train/Validation/Test, Active Model หรือ Analysis settings

## ไฟล์ที่เปลี่ยน

- `app/services/admin_report.py`
- `app/routes/admin.py`
- `frontend_flutter/lib/screens/admin_datasets_screen.dart`
- `tests/test_admin_dataset_correction.py`
- `tests/test_project_closeout_phase3.py`
- `frontend_flutter/test/admin_surfaces_test.dart`
- `frontend_flutter/test/scope_completion_test.dart`
- `scripts/browser/verify_project_closeout_phase3.cjs`
- `scripts/browser/verify_project_closeout_phase3_crud.cjs`
- `docs/implementation/project-closeout-scope.md`

ไม่มี migration ใน Phase นี้

## เกณฑ์ผ่านและหลักฐาน

### Follow/Notification

- Fixture DB ผ่าน: category follow, duplicate, account isolation, all/following/off, baseline, same platform/scope/category, provider failure recovery, no replay หลัง off, no backfill เมื่อ follow ใหม่ และ dedup
- Route fixture ผ่าน: unread/read ถูกจำกัดด้วย `user_id` และ `watch_session_id`; user อื่น mark read ไม่ได้; สถานะ read ยังอยู่เมื่อเปิด DB session ใหม่
- UI ผ่าน: follow หมวด YouTube -> rebuild จำลอง reload/relogin -> ยังติดตาม -> เปลี่ยน mode -> unfollow; save/load ล้มเหลวไม่แจ้งสำเร็จ
- **ค้าง:** ไม่เกิด live provider change ระหว่างรอบนี้ จึงยังไม่ยืนยัน end-to-end delivery สด ห้ามใช้ fixture อ้างว่า provider สดผ่าน

### Scheduler

- Fixture ผ่าน due/not-due, 10 hourly slots, Backend/worker shared slot, lock, pause/window/timezone, partial failure, error redaction, no backfill และ crash ไม่ replay
- Windows task ติดตั้งจริง: execute `pythonw.exe`, manual start วันที่ 2/10/2026 00:31 เวลาไทย, `LastTaskResult=0`, กลับสถานะ `Ready`; DB รายงาน `not_due`
- คงค่าจริง: `hourly_window`, Asia/Bangkok 14:00–23:00, 10 รอบ/วัน, estimate YouTube `videos.list` 130 calls/day, browser poll 60 วินาที
- ไม่เปลี่ยน schedule เพื่อทดสอบและไม่เรียก provider สดเพิ่ม

### Admin/Private

- Dataset UI จริงผ่านบน #435: create -> delete -> restore -> delete; hash 64 ตัว, taxonomy `phone`, split `unassigned`, training/reference flags false และสุดท้าย archived
- Audit ของ #435 มี create/delete/restore โดย Admin user #2; แถวไม่อยู่ Train/Reference และไม่ active
- Review/import fixture ผ่าน invalid/duplicate/pending/hash/approve/reject/approve all; failure หรือไม่มี receipt ไม่ถูกนับว่าสำเร็จ
- Users tests ผ่าน role/active/delete/session revoke, self/last-admin/stale revision/private cleanup และ failed save
- Settings tests ผ่าน persistence, unavailable Whisper, frozen job settings และผลเก่าไม่เปลี่ยน
- Logs แสดงชื่อไทย/เวลา/ผู้กระทำ/status; sanitizer มี tests ทั้ง plain text และ nested JSON

## ผลทดสอบ

```text
python -m unittest tests.test_project_closeout_phase3 tests.test_admin_dataset_correction tests.test_scope_completion tests.test_trend_scheduler tests.test_trend_scheduler_launcher tests.test_user_management tests.test_analysis_settings tests.test_youtube_cc_dataset
106 tests passed

python -m unittest tests.test_notebooklm_batch
6 tests passed

python -m unittest tests.test_live_trend_snapshots
21 tests passed

flutter test: dashboard_screen, admin_users, analysis_settings, admin_surfaces, scope_completion
41 tests passed

flutter test test/scope_completion_test.dart
8 tests passed after reload/relogin assertion

flutter test test/dataset_bulk_approval_test.dart
3 tests passed

flutter analyze --no-pub
No issues found

flutter build web --release --no-pub
Built frontend_flutter/build/web
```

จำนวน tests เป็น software checks ไม่ใช่จำนวนคลิปประเมินหรือหลักฐานคุณภาพ AI

## Browser Evidence

- `artifacts/browser/project-closeout-phase3/verification.json`: release build, DB จริงแบบ read-only, 1440/1000 px, API ทุกคำขอ <400, ไม่มี page error/overflow
- `artifacts/browser/project-closeout-phase3/crud-verification.json`: Dataset #435 CRUD ผ่านและจบ `archived_non_training`
- ภาพ Dashboard/Datasets/Users/Settings/Logs และ CRUD อยู่ในโฟลเดอร์เดียวกัน
- รอบ browser ใช้ session ชั่วคราวของ Admin เดิมและ logout แล้ว ไม่สร้างบัญชีใหม่

## ข้อมูลและ Cleanup

- Dataset #435 ชื่อ `PHASE3 UI TEST 1790876527871`: อยู่ถังขยะ, `is_active=false`, `is_training_eligible=false`, keyword/duration reference=false, split `unassigned`
- เก็บ #435 ไว้เป็นหลักฐาน audit; ลบถาวรไม่ได้ผ่าน workflow ปัจจุบันและไม่ถูกใช้ในงานใหม่
- ไม่มีการสร้าง trend ปลอมใน DB, ไม่มี mass approve และไม่เปลี่ยน 42 pending review rows
- Backend restart ด้วยโค้ด Phase 3 แล้วที่ `http://127.0.0.1:8000`; health ผ่านและ Whisper `small` ready
- Release web เดิมที่พอร์ต `8080` อ่านไฟล์ build ที่อัปเดตแล้ว

## งานค้าง

1. รอ provider เกิดรายการใหม่จริงหลัง baseline เพื่อเก็บ live notification evidence; ไม่ลดเงื่อนไขหรือสร้าง trend ปลอม
2. ข้อเสนอเปลี่ยนขอบเขต 11/13/15/17/18 ยังต้องให้เจ้าของโครงการ/อาจารย์ยืนยัน
3. Analysis/Model readiness เป็นงาน Closeout Phase 2 ที่ยังมีข้อจำกัดตาม Handoff ของ Phase 2 ไม่ถูกแก้หรืออ้างว่าผ่านใน Phase นี้
4. งาน UI ทั้งระบบเป็น Closeout Phase 4 และยังไม่ได้เริ่ม

## ตรวจต่อ

- เว็บ: `http://127.0.0.1:8080/#/dashboard`
- Backend: `http://127.0.0.1:8000/health`
- Scheduler: `Get-ScheduledTask -TaskName ContentAI-Trends-D33AFF90B7`
- Agent ถัดไปต้องอ่าน Handoff นี้และ Phase 2 ก่อนทำ Phase 4; ห้ามเริ่ม Phase ถัดไปจากงานนี้โดยอัตโนมัติ
