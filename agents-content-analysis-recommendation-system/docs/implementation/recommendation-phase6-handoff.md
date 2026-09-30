# Recommendation Phase 6 Handoff

## ตรวจทานเพิ่มเติม 2026-09-30

แก้ regression ของ `/analyze` ที่อ้าง `comparison_id` นอกเส้นทาง Revision, เพิ่มการรับงาน/Retry แบบ atomic และ fencing ด้วย Job ID, คืนผลเดิมเมื่อส่ง Worker completed ซ้ำ และตรวจ Snapshot fingerprint ก่อนถอดเสียง

Startup จะตรวจ Host/PID/เวลาเริ่ม Process ก่อนเปลี่ยนงานเป็น interrupted ด้วย `psutil>=7,<8` ที่เพิ่มใน requirements (เครื่องนี้มีแล้ว) ไม่ทำให้ Worker อีกตัวที่ยังมีชีวิตถูกยกเลิก ใช้ JSON snapshot เดิมจึงไม่ต้องเพิ่ม Migration ส่วนการตรวจบริบทใช้ offset กับ Transcript ชนิดเดียวกัน และผลเก่าที่ไม่มีข้อมูลยืนยันหมวดจะงดข้อสรุป

รายละเอียดและผลทดสอบล่าสุดอยู่ใน [รายงานตรวจ Phase 5-7](recommendation-phases5-7-review.md) งานค้างยังเป็นการตรวจคู่คลิปจริง ไม่ใช่ความพร้อมของ Fixture

## สถานะสองส่วน

- ฟีเจอร์และการทดสอบซอฟต์แวร์: เสร็จสำหรับ Phase 6 พร้อม Backend, Web UI, persistence, retry/restart และ regression tests
- การทดสอบกับวิดีโอจริง: ยังไม่มีคู่คลิปต้นฉบับ/ฉบับแก้ไขที่กันไว้นอกข้อมูลฝึก จึงยังไม่ถือว่าผ่าน End-to-end ด้านความถูกต้องของ ASR หรือคุณภาพคำแนะนำ

งานนี้ทำเฉพาะ Phase 6 การอัปโหลดฉบับแก้ไขและเปรียบเทียบการเปลี่ยนแปลงเนื้อหา ยังไม่ได้เริ่ม Phase 7

## สิ่งที่ทำเสร็จ

1. เพิ่มปุ่ม `อัปโหลดฉบับแก้ไข` ในแผนที่บันทึกแล้ว หากยังมี Draft จะให้บันทึกก่อนหรือยืนยันใช้แผนฉบับที่บันทึกไว้ ไม่ส่ง Draft ไปเทียบเงียบ ๆ
2. หน้า Upload แสดงต้นฉบับ, Revision/เวลาของแผน และหัวข้อที่จะตรวจ ก่อนเลือกไฟล์ใหม่ โดยใช้ข้อจำกัดความยาว, Whisper และ Hook ที่ Backend capture ตอนรับงาน
3. ใช้ Pipeline วิเคราะห์เดิมหนึ่งครั้งต่อคำขอ แล้วนำผลเดียวกันไปบันทึกเป็น Child analysis และสร้างผลเปรียบเทียบ ไม่มีการถอดเสียงซ้ำเพื่อสร้าง comparison
4. Backend อ่าน Plan/หัวข้อ/คำพ้องจาก Database และ recommendation snapshot จริง ไม่เชื่อข้อความหัวข้อจาก Browser
5. ตรึง Plan snapshot ตอนรับงาน รวม `selected_advice_ids`, notes, topic IDs, canonical topic, aliases, context terms, action snapshot, hashes, method versions และ settings
6. เพิ่ม persistent revision job รองรับ `queued`, `running`, `completed`, `failed`, `interrupted` พร้อม stage/progress/error ที่ไม่เปิด SQL หรือ Secret
7. บันทึก Child result และ frozen comparison ใน transaction เดียวกัน หากบันทึกส่วนใดล้มเหลว Child จะ rollback และ Job ไม่ถูกแจ้งว่าสำเร็จ
8. เปิดผลเก่าแล้วอ่าน comparison snapshot ที่บันทึกไว้ ไม่คำนวณใหม่จาก Dataset, Alias หรือกฎปัจจุบัน
9. ผลต่อหัวข้อแยก `detected`, `not_detected`, `unassessable` และ `context_present`, `keyword_only`, `unclear` พร้อม quote/offset/timestamp เมื่อมีจริง
10. หน้า Result แสดงฉบับต้นฉบับกับฉบับใหม่ หลักฐานสองฝั่ง และลิงก์กลับผลเดิม โดยไม่แสดงเปอร์เซ็นต์ความสำเร็จหรือกล่าวว่าคลิปดีขึ้น
11. รองรับ notes-only อย่างชัดเจน: วิเคราะห์คลิปใหม่ได้ตามปกติ แต่ไม่มีหัวข้อสำหรับเทียบอัตโนมัติ
12. ป้องกันงานของผู้ใช้อื่น, Plan stale, transcript hash เปลี่ยน, Request ID ซ้ำคนละไฟล์, บัญชีถูกระงับ และ Parent ถูกลบ

## API Contract

### `POST /analyze/revision`

รับ multipart form:

- `file`
- `parent_content_id`
- `parent_analysis_id`
- `parent_recommendation_fingerprint`
- `expected_plan_revision`
- `client_request_id`

`client_request_id` เดิมของเจ้าของเดิมและ payload/file เดิมคืน Job เดิม หากนำ ID เดิมไปใช้กับไฟล์หรือบริบทอื่นจะตอบ Conflict

### `GET /revision-jobs/{job_id}`

อ่านได้เฉพาะเจ้าของงาน คืนสถานะ, stage, progress, error แบบปลอดภัย, revision context และ Child result เมื่อบันทึกครบแล้ว

### `POST /revision-jobs/{job_id}/retry`

ใช้ได้เฉพาะ `failed` หรือ `interrupted` และต้องยังมีไฟล์เดิม, ผู้ใช้ยัง active และ Parent ยังอยู่ สร้าง Job ID ใหม่แต่ใช้ frozen Plan/settings/file เดิม ไม่สร้าง comparison record ซ้ำ

Route เดิม `GET /jobs/{job_id}` ถูกเพิ่ม ownership check ด้วย ผู้ใช้ทั่วไปไม่สามารถเดา Job ID ของผู้อื่นเพื่ออ่านสถานะได้ ส่วน Admin ยังตรวจสอบได้ตามสิทธิ์

## Schema และความสัมพันธ์

เพิ่มตาราง `clip_revision_comparisons` แบบ additive ไม่ reset ตารางเดิม:

- เจ้าของ: `user_id`
- ฐานเปรียบเทียบ: `parent_content_id`, `parent_analysis_id`, `parent_recommendation_fingerprint`, `plan_revision`
- ผลใหม่: `child_content_id`, `child_analysis_id`
- Idempotency: `client_request_id`, `request_fingerprint`, `file_sha256`
- งานเบื้องหลัง: `job_id`, `job_backend`, `status`, `stage`, `progress`, error และเวลา
- Snapshot: `plan_snapshot_json`, `settings_snapshot_json`, `snapshot_sha256`
- ผลแช่แข็ง: `comparison_result_json`

ความสัมพันธ์คือ `Parent Analysis -> ClipRevisionPlan -> ClipRevisionComparison -> Child Analysis` โดยหลาย Child สามารถอ้าง Parent/Plan revision เดียวกันได้ แต่ไม่มีการเปลี่ยนฐานเปรียบเทียบเป็น Child ล่าสุดอัตโนมัติ

นโยบาย Foreign Key:

- ลบ User หรือ Parent จะลบ comparison link ตาม cascade
- ลบ Parent หลังงานเสร็จไม่ลบ Child result; Child ยังเปิดเป็นผลวิเคราะห์ปกติ แต่ไม่มีลิงก์เปรียบเทียบเสียค้าง
- Child IDs ใช้ `SET NULL` หาก Child ถูกลบ

## State Machine และความคงทน

เส้นทางปกติ:

`queued -> running/extracting_audio -> running/saving -> completed`

เส้นทางผิดพลาด:

`queued|running -> failed -> queued ใหม่ผ่าน retry`

เมื่อ Backend เริ่มใหม่ งาน `inprocess` ที่ยัง `queued/running` จะเป็น `interrupted` และกด Retry ได้ งานที่ใช้ RQ จะไม่ถูกตีความว่าหยุดเพียงเพราะ Web process restart

สถานะ `completed` เกิดหลัง Child analysis และ `comparison_result_json` commit ครบเท่านั้น การส่งคำขอซ้ำหลายแท็บไม่สร้าง Child ซ้ำเพราะ unique `(user_id, client_request_id)` และ request fingerprint

## วิธีเปรียบเทียบและ Version Compatibility

- Schema: `clip-revision-comparison-v1`
- Comparison method: `same-topic-derived-comparison-v1`
- Topic matcher ใช้เวอร์ชันเดียวกับ recommendation evidence ที่ถูก capture
- ทั้งสอง Transcript ใช้ aliases ชุดเดียวจาก Plan snapshot ไม่ใช้กฎล่าสุดกับฝั่งหนึ่งและกฎเก่ากับอีกฝั่ง
- Transcript ต้องมีสถานะ full/available จึงสรุป `not_detected` ได้ หากถอดไม่ครบจะเป็น `unassessable`
- Category ฝั่งใดเป็น Unknown/ไม่ผ่านเกณฑ์ หรือหมวดที่ยอมรับต่างกัน จะเป็น `withheld_category`
- ผลเก่าขาด context/method ที่จำเป็นจะเป็น `method_mismatch` ไม่เติมข้อมูลย้อนหลัง
- Whisper ต่างรุ่นยังแสดงข้อความที่ตรวจพบได้ แต่เพิ่มข้อจำกัด `asr_method_changed` และไม่ฟันธงว่าเนื้อหาถูกเพิ่มหรือลบจริง

ข้อความผลหลัก:

- ไม่พบ -> พบ: `ตรวจพบการกล่าวถึงในฉบับใหม่`
- พบ -> พบ: `ตรวจพบในทั้งสองฉบับ`
- พบ -> ไม่พบ: `ยังไม่ตรวจพบในข้อความฉบับใหม่`
- ไม่พบ -> ไม่พบ: `ยังไม่ตรวจพบในข้อความทั้งสองฉบับ`
- มีฝั่งตรวจไม่ได้: `ข้อมูลยังไม่พอเปรียบเทียบ`

`context_present` ต้องมีหัวข้อและ context term ที่ตรวจย้อนกลับได้ใน segment/ช่วงข้อความเดียวกัน การพบคำเดี่ยวเป็นเพียง `keyword_only` และข้อความปฏิเสธยังถือเป็นการกล่าวถึง ไม่ถูกตีความว่ามีฟังก์ชันหรือผ่านการทดสอบ

## ไฟล์สำคัญ

- `app/database/models.py`: ตาราง `ClipRevisionComparison`
- `app/services/revision_comparisons.py`: capture Plan, idempotency, matcher, frozen result, retry/restart
- `app/routes/analyze.py`: revision upload, worker, status และ retry endpoints
- `app/services/persistence.py`: รองรับ transaction ที่ยังไม่ commit สำหรับ Child + comparison
- `app/services/jobs.py`, `app/routes/jobs.py`: ownership ของ Job เดิม
- `app/services/contents.py`: คืน frozen comparison เมื่อเปิด Child result
- `frontend_flutter/lib/widgets/clip_revision_planner.dart`: เริ่ม flow จากแผนที่บันทึก
- `frontend_flutter/lib/screens/upload_screen.dart`: revision context, upload, polling และ retry
- `frontend_flutter/lib/widgets/revision_comparison_panel.dart`: ผลก่อน/หลังและหลักฐาน
- `tests/test_revision_comparisons.py`: Backend contract, ownership, persistence และ comparison matrix
- `frontend_flutter/test/revision_comparison_test.dart`: UI states ที่ 1,000/1,440 พิกเซล
- `scripts/verification/revision_comparison_fixture_api.py`: SQLite fixture แยกฐาน
- `scripts/browser/verify_revision_comparison.cjs`: browser flow ตั้งแต่ผลเดิมถึงผลเปรียบเทียบ

## การตรวจสอบ

- Backend ทั้งระบบ: `python -m unittest discover -s tests -v` ผ่าน 433 tests
- Backend Phase 6: `python -m unittest tests.test_revision_comparisons -v` ผ่าน 16 tests
- Flutter ทั้งระบบ: `flutter test --no-pub --concurrency=1` ผ่าน 121 tests
- Flutter Phase 6 หลังแก้ Web request ID: ผ่าน 13 tests
- Flutter analyze: `flutter analyze --no-pub` ผ่านโดยไม่พบปัญหา
- Python compile: `python -m compileall -q app` ผ่าน
- Web release build: สำเร็จ มีเพียง warning เดิมเรื่อง CupertinoIcons ที่ไม่ได้ถูก bundle
- Browser flow: ผ่านที่ 1,440 และ 1,000 พิกเซล ทั้ง upload multipart, persistence และ result UI ไม่มี overflow หรือ console error
- Browser artifacts: `artifacts/browser/revision-comparison/`

Browser verification ใช้ temporary SQLite และ deterministic ASR/classification fixture ที่ประกาศชัด จึงพิสูจน์ software flow และ persistence เท่านั้น ไม่ใช่ผลประเมินความแม่นของโมเดลกับวิดีโอจริง

## Bug ที่พบจาก Browser Flow

การสร้าง `client_request_id` เดิมใช้ `1 << 32` ซึ่งถูก JavaScript bit shift เป็น `0` บน Flutter Web ทำให้ `Random.nextInt(0)` ล้มและหน้า Upload ว่าง แก้เป็นขอบเขต `0x7fffffff` แล้ว และ browser flow ผ่านทั้งสองความกว้าง

## ข้อจำกัดและงานค้าง

- ยังต้องหาคู่คลิปจริงอย่างน้อยหนึ่งคู่ต่อ Phone, Camera และ Laptop ซึ่งไม่อยู่ใน Train/Validation/Test/Reference เพื่อตรวจ ASR, หมวด และข้อความก่อน/หลังด้วยคน
- การพบหัวข้อไม่แปลว่าทำตามวิธีแนะนำครบ ไม่ใช่คะแนนคุณภาพ และไม่รับประกันยอดวิว/ไลก์/ความคิดเห็น
- Timestamp มีเฉพาะเมื่อ ASR ให้ segment time จริง แต่ละคลิปใช้ timeline ของตนเอง ห้ามเทียบนาทีเดียวกันข้ามไฟล์ว่าเป็นเหตุการณ์เดียวกัน
- ระบบเก็บไฟล์ฉบับแก้ไขเพื่อ Retry ตามนโยบายเดิม ปัจจุบันยังไม่มีงาน cleanup อายุไฟล์เฉพาะ revision เพิ่มเติม
- Phase 7 ยังไม่ได้เริ่มตามข้อกำหนด

