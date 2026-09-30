# Implementation Prompt: Recommendation Phase 6

## งานของคุณ

พัฒนา **อัปโหลดฉบับแก้ไขและเทียบการเปลี่ยนแปลงเนื้อหา** ให้เชื่อมกับผลวิเคราะห์เดิมและแผนที่ผู้ใช้เลือกไว้ ทำครบ Backend, Upload flow, UI ผลเปรียบเทียบ, Persistence และ Tests

นี่คือวงจร "วิเคราะห์ -> บันทึกแผน -> ปรับคลิป -> อัปโหลดฉบับใหม่ -> ตรวจข้อความอีกครั้ง" ไม่ใช่ระบบให้คะแนนว่าคลิปใหม่จะดังขึ้น และไม่ใช่เพิ่มช่องอัปโหลดที่ไม่ผูกข้อมูลจริง

ทำเฉพาะ Phase นี้ ไม่ปรับโมเดลจำแนก ไม่เปลี่ยนวิธีเปรียบเทียบสถิติ Phase 5 และไม่เริ่มการทดลองกับผู้ใช้ Phase 7

## อ่านก่อนแก้

- `docs/implementation/recommendation-phase5-handoff.md` หากมี เพื่อใช้ Contract ล่าสุดแทนเดาว่า Phase 5 ทำอย่างไร
- `docs/clip-revision-plans-phase4-th.md`
- `app/services/clip_revision_plans.py`, `app/services/saved_recommendations.py`
- `app/database/models.py`: `UserContent`, `AnalysisResult`, `ClipRevisionPlan`
- `app/routes/contents.py`, `app/schemas/contents.py`, `app/services/contents.py`
- `app/routes/analyze.py`, `app/routes/jobs.py`, `app/services/jobs.py`, `app/services/ai_pipeline.py`, `app/services/analysis_settings.py`
- `app/services/recommendation_evidence.py`, `app/services/actionable_recommendations.py`
- `frontend_flutter/lib/screens/upload_screen.dart`, `frontend_flutter/lib/screens/result_screen.dart`
- `frontend_flutter/lib/models/clip_revision_plan.dart`, `frontend_flutter/lib/widgets/clip_revision_planner.dart`
- `frontend_flutter/lib/repositories/analysis_repository.dart`, `frontend_flutter/lib/repositories/content_repository.dart`
- `tests/test_clip_revision_plans.py`, `tests/test_full_clip_analysis.py`, `frontend_flutter/test/clip_revision_planner_test.dart`

ตรวจ `git status` และฟังก์ชันที่เกี่ยวข้องก่อน อย่าทิ้งงานค้างหรือสร้างระบบวิเคราะห์อีกชุด หากเอกสารกับโค้ดไม่ตรงให้ระบุและรักษาพฤติกรรมที่ผ่าน Tests อยู่

## สัญญาเดิมที่ห้ามทำลาย

1. แผนปัจจุบันผูก `analysis_id`, `recommendation_fingerprint`, `revision` และรายการ `selected_advice_ids` การเลือกหมายถึงตั้งใจนำไปปรับ ไม่ใช่ทำสำเร็จ
2. ผลวิเคราะห์ คำแนะนำ หลักฐาน และเวอร์ชันเก่าต้องคงเดิม ไม่สร้างคำแนะนำใหม่ทับเวลาผู้ใช้เปิดผลเก่า
3. Active Model ที่ถูก Capture สำหรับงานนั้นเป็นจุดตัดสินหมวด หาก Unknown/ไม่ผ่านเกณฑ์ ต้องงดการสรุปเฉพาะหมวด ไม่ให้ระบบจับคำทายหมวดทับ
4. ถอดเสียงไม่ครบ/ไม่มีหลักฐานต้องเป็น "ตรวจไม่ได้" ไม่ใช่ "ผู้ใช้ไม่ได้เพิ่ม"
5. ไม่ใช้ชื่อไฟล์ ชื่อคลิป และความถี่คำอย่างเดียวเป็นหลักฐานว่าทำตามคำแนะนำสำเร็จ
6. Upload ใหม่ต้องใช้ค่าความยาว/Whisper/Hook จาก Backend ที่ Capture ตอนเริ่มงาน และบันทึกค่าที่ใช้จริงตามระบบเดิม

## 1. User Flow

เพิ่มคำสั่ง "อัปโหลดฉบับแก้ไข" ในส่วนแผนของผลที่เป็นเจ้าของ:

- ต้องมีแผนที่บันทึกแล้วและมีหัวข้อที่เลือกอย่างน้อยหนึ่งข้อ ถ้าเป็น notes-only ให้ยังวิเคราะห์ไฟล์ใหม่แบบปกติได้ แต่ไม่มีการเทียบหัวข้ออัตโนมัติ
- หากมี Draft ยังไม่บันทึก ต้องให้บันทึกหรือยืนยันใช้แผนฉบับที่บันทึกไว้ก่อน ไม่ส่ง Draft ไปเทียบเงียบ ๆ
- แสดงคลิปต้นฉบับ เวลาของแผน และหัวข้อที่จะตรวจ ก่อนเลือกไฟล์ใหม่
- เรียก Upload/Pipeline เดิมหนึ่งรอบต่อคำขอ ไม่เรียก ASR ซ้ำเพื่อให้ได้ทั้งผลใหม่และผลเทียบ
- เมื่อสำเร็จ ผู้ใช้เปิดได้ทั้งผลวิเคราะห์ใหม่แบบปกติ และส่วน "การเปลี่ยนแปลงเนื้อหา" ที่เชื่อมกลับไปผลเดิม
- อัปโหลดได้หลายฉบับ แต่ทุกฉบับต้องบอกชัดว่าเทียบกับผลและแผนฉบับใด ไม่เปลี่ยนฐานเทียบเป็นฉบับล่าสุดเอง
- ไม่บันทึกอัตโนมัติว่าทำตามแผนครบ ไม่เพิ่มสถานะ completed เพียงเพราะตรวจเจอคำ

## 2. การรับงานและสิทธิ์

ใช้รูปแบบ Route/Schema เดิมของโครงการ จะขยาย Upload endpoint แบบ Optional context หรือเพิ่ม Route สำหรับ Revision โดยเฉพาะก็ได้ แต่ต้องเรียก Core pipeline เดิมและรักษา Client เก่า

Context ที่รับต้องมี `parent_content_id`, `parent_analysis_id`, `parent_recommendation_fingerprint`, `expected_plan_revision` และ `client_request_id` สำหรับกันส่งซ้ำ

Backend ตรวจ ownership ของผลเดิมและแผน ตรวจ Hash/Revision และอ่านรายการหัวข้อจริงจาก DB ไม่เชื่อข้อความคำแนะนำ/รายการหัวข้อที่ Browser ส่งมาเอง

- ผู้ใช้อื่นห้ามอ่าน Upload job, ผลเทียบ, Quotes หรือผลเดิมได้ แม้เดา ID ได้ ตรวจ Job status route ด้วย
- แผนเปลี่ยนก่อนคำขอรับเข้า ให้ตอบ Conflict พร้อมวิธีโหลดใหม่ ไม่เลือกแผนล่าสุดแทนให้เงียบ ๆ
- แผนเปลี่ยนหลังรับงานแล้ว ให้ใช้ Snapshot ของแผนตอนรับงานอย่างเดิม และแสดงหมายเลข Revision นั้น
- ตรวจเพดานอัปโหลดจริงด้าน Backend และเก็บไฟล์ด้วยวิธีเดิมที่ปลอดภัย ไม่รับ Path arbitrary จาก Browser
- `client_request_id` เดียวกันจากเจ้าของเดียวกันและ Payload เดิม ต้องคืนงานเดิม ไม่สร้างผลซ้ำ; ID เดิมแต่คนละบริบท/ไฟล์ให้ Conflict
- ตรวจสิทธิ์ผู้ใช้ที่ถูกลบ/ระงับก่อนบันทึกผลตามแนวทางเดิม ไม่ปล่อย Worker เขียนผลให้ Account ที่ไม่อนุญาตแล้ว

## 3. Persistence และงานเบื้องหลัง

สร้างหน่วยข้อมูล Revision comparison/job ตามรูปแบบ ORM เดิม แบบ additive migration ไม่ Reset ตารางเก่า และไม่พึ่ง Dictionary ใน RAM เพียงอย่างเดียว

อย่างน้อยต้องเก็บ:

- เจ้าของ, Parent content/analysis IDs และ Fingerprint
- Snapshot แผน: revision, selected_advice_ids, notes, topic IDs/นิยามหัวข้อ/คำพ้องที่ใช้, เวลา Capture และ Hash
- Child content/analysis IDs เมื่อมีผลใหม่ ไม่เขียนทับ Parent
- Request ID, File hash, Job ID, สถานะ queued/running/completed/failed/interrupted, เวลาและข้อความผิดพลาดที่ไม่รั่ว SQL/Secrets
- Method/settings/model/ASR versions ของสองฉบับ, Comparison method/alias version, Input hashes
- ผลเทียบที่แช่แข็ง รวม Quotes/Offsets/เวลาจริงและข้อจำกัด

สถานะ Success ต้องหมายถึง Child result และ Comparison บันทึกครบจริง ใช้ Transaction สำหรับการบันทึกส่วนที่ต้องสำเร็จร่วมกัน ถ้าแยก Save เป็นหลายขั้นต้องมีสถานะที่ตรงจริงและ Retry ที่ไม่สร้าง Child ซ้ำ

ปัจจุบัน `jobs.py` รองรับ In-process และ RQ ตรวจผลเมื่อรีสตาร์ต ถ้าไม่สามารถ Resume งาน In-process ได้ ให้เก็บและแสดง interrupted พร้อม Retry ห้ามค้าง running ตลอดหรืออ้างว่ารองรับ Resume
แก้เฉพาะสิ่งที่จำเป็นกับ Revision jobs ไม่ย้ายระบบงานทั้งโครงการไป Queue ใหม่ใน Phase นี้ และอย่า Mark งานของ Worker อื่นว่า Interrupted หากยังทำงานอยู่

ลบผลเดิมแล้วให้ลบ/ยกเลิกข้อมูลเปรียบเทียบที่อ้างผลนั้นตามนโยบายที่ระบุชัด แต่ไม่ลบไฟล์/ผลใหม่อีกฉบับโดยอ้อมโดยผู้ใช้ไม่รู้ ผลใหม่ที่ยังอยู่ต้องเปิดแบบ Standalone ได้ ไม่มีลิงก์ที่รั่วผลเดิมหลังถูกลบ

## 4. ตรวจหัวข้อด้วยวิธีเดียวกัน

แยกสิ่งที่ใช้เทียบออกจากผล Recommendation ที่ถูกแช่แข็ง:

1. ใช้รายการหัวข้อจาก Plan snapshot ไม่ดึงหัวข้อเพิ่มจาก Dataset ปัจจุบัน
2. อ่าน Raw transcript/Segments ที่ถูกบันทึกของ Parent และ Child ไม่เรียก ASR ใหม่ให้ Parent โดยไม่แจ้ง
3. ถ้ามีวิธีและนิยามหัวข้อเดิมที่รันได้ ให้ใช้ร่วมกันทั้งสองฝั่ง
4. หากวิธีเก่ารันไม่ได้ แต่มี Transcript พอ ให้สร้าง **Derived comparison ใหม่** โดยใช้ Topic matcher เวอร์ชันเดียวกันกับสอง Transcript พร้อมคำพ้องชุดเดียวกันจากแผน บันทึกวิธีใหม่นี้แยก ไม่เขียนผลเดิมทับ
5. ถ้าทำไม่ได้จริง ให้ `method_mismatch` และแสดงข้อความสองฝั่งเพื่อให้ตรวจเอง ไม่แสดงว่าเป็นผลเทียบมาตรฐานเดียวกัน

นิยาม Compatibility ต้องแยก: ตัวจับหัวข้อ/คำพ้อง, สถานะ Transcript ทั้งคลิป, ASR รุ่น/ภาษา/การทำความสะอาด, หมวดและกติกาตรวจรับ, การตรวจ Hook ถ้าใช้งาน
การเปลี่ยนถ้อยคำในแม่แบบอย่างเดียวไม่เท่ากับเปลี่ยนวิธีจับหัวข้อ แต่ต้องบันทึกเวอร์ชันทั้งสอง ไม่ใช้เพียง String version เดียวตัดสินทุกอย่าง

ASR ต่างรุ่นยังแสดงผลตรวจข้อความได้ แต่ต้องระบุว่าแยกสาเหตุจากการเปลี่ยน ASR ไม่ได้ ไม่ฟันธงว่าเพิ่ม/ลบเนื้อหาจริง ใช้ `asr_method_changed` เป็นข้อจำกัดที่มองเห็นได้
แม้ ASR รุ่นเดียวกัน ก็ยังอาจถอดผิดได้ ห้ามอ้างว่าแยกความผิดพลาดจากการพูดได้แน่นอนโดยไม่มีคนตรวจคลิป

Parent หรือ Child เป็น Unknown/ไม่ผ่านเกณฑ์ หรือหมวดที่ยอมรับต่างกัน ให้ `withheld_category` ไม่โยง Dataset ของหมวดหนึ่งไปอธิบายอีกหมวด เก็บผลวิเคราะห์แต่ละฉบับให้ดูได้ตามจริง

## 5. ผลเทียบต่อหัวข้อ

ทุกหัวข้อเก็บผลสองฝั่งแบบ `detected`, `not_detected`, `unassessable` พร้อม Quotes/Offsets และ Timestamp เฉพาะที่มีจริง

| ก่อน | หลัง | ข้อความที่ใช้ |
| --- | --- | --- |
| not_detected | detected | ตรวจพบการกล่าวถึงในฉบับใหม่ |
| detected | detected | ตรวจพบในทั้งสองฉบับ |
| detected | not_detected | ยังไม่ตรวจพบในข้อความฉบับใหม่ |
| not_detected | not_detected | ยังไม่ตรวจพบในข้อความทั้งสองฉบับ |
| unassessable ฝั่งใดก็ตาม | สถานะใดก็ตาม | ข้อมูลยังไม่พอเปรียบเทียบ |

ห้ามใช้ข้อความ "เพิ่มสำเร็จ/ทำครบ/ดีขึ้น X%" จากตารางนี้ ตรวจพบหมายถึงมีข้อความที่เข้าเกณฑ์ ไม่ได้แปลว่าพูดครบทุกขั้นตอนในคำแนะนำ

เพื่อไม่ให้การอ่านคำว่า "แบตเตอรี่" คำเดียวกลายเป็นทำตามแผนครบ ให้เก็บ `context_status` เพิ่ม เช่น `context_present`, `keyword_only`, `unclear`:

- `context_present` ต้องมีหลักฐานหัวข้อและบริบทการอธิบาย/ทดสอบที่ตรวจย้อนกลับได้ ตามกติกาแยกจากจำนวนคำ
- `keyword_only` แปลว่าตรวจพบคำแต่ยังไม่พอยืนยันการอธิบาย เก็บคำพูดจริงให้คนดู ไม่สร้างคะแนนคุณภาพ
- ข้อความปฏิเสธยังเป็นการกล่าวถึง แต่ไม่ตีความว่ามีฟังก์ชันหรือได้ทดสอบแล้ว
- กติกาบริบทอาจใช้ขอบเขตประโยค/Segments และ `context_terms` ที่มีอยู่ หากไม่แน่ใจให้ `unclear` ไม่แต่ง Semantic judgment

ไม่เพิ่มโมเดลเสียเงินหรือใช้ LLM เขียน Quote ใหม่ ไม่ทำเครื่องหมายว่าปรับเสร็จอัตโนมัติจาก context_status เช่นกัน

## 6. UI ที่ผู้ใช้ทำต่อได้

- เข้าจากแผนเดิมและย้อนจากฉบับใหม่ได้ ไม่สร้างหน้าที่ไม่อยู่ใน Navigation flow
- ผลเทียบมีชื่อ/วันที่ของสองฉบับ หัวข้อที่เลือก สถานะ และข้อความก่อน-หลัง เปิดดูเวลาเมื่อมีจริง
- เวลาของแต่ละฉบับเป็นของไฟล์นั้นเอง ไม่ถือว่านาทีที่ 1 ของสองคลิปเป็นเนื้อหาเดียวกัน
- แยก "ตรวจพบหัวข้อ" กับ "ยังต้องดูคลิปยืนยัน" ไม่มีแถบความสำเร็จ 100% ที่สื่อว่าคุณภาพดีขึ้น
- มี Loading, Upload validation, Failed, Retry, Interrupted, ไม่มีหัวข้อเลือก, Transcript ตรวจไม่ได้, วิธีต่างกัน และผลเก่าที่ข้อมูลไม่พอ
- Errors ต้องไม่ลบ Draft แผนหรือ Parent result และไม่แจ้งสำเร็จก่อน Commit
- ทำเฉพาะเว็บตาม Design เดิม ตรวจที่ความกว้าง 1,000/1,440 พิกเซล ไม่มีข้อความ/ปุ่มล้น ไม่สร้าง Mobile app

## 7. Tests ที่ต้องมี

1. User A เข้าผล/Job/ไฟล์ของ User B ไม่ได้ และ Request ปลอม Parent/Plan/Topic ถูกปฏิเสธ
2. แผนไม่บันทึก, ไม่มีหัวข้อ, notes-only, Source hash เปลี่ยน, Revision stale มีพฤติกรรมชัด ไม่ผูกผิดแผน
3. เปลี่ยนแผนระหว่าง Worker รันแล้วผลยังอ้าง Snapshot ที่ Capture ตอนรับงาน
4. Submit ซ้ำ/Retry/หลายแท็บไม่สร้าง Child ซ้ำ Commit ล้มเหลวไม่แจ้งสำเร็จ
5. Restart: ผลสำเร็จยังอยู่ งานที่ Resume ไม่ได้มี interrupted จริงและ Retry ได้ตามนโยบาย
6. Parent recommendation/evidence/fingerprint ไม่เปลี่ยนหลังวิเคราะห์ Child หรืออัปเดต Dataset
7. ครบทุกคู่ detected/not_detected/unassessable, ไม่มีเวลา, เวลาแต่ละฉบับไม่ตรงกัน, ASR partial/รุ่นต่างกัน
8. คำพ้อง, กล่าวคำเดี่ยว, บริบทที่ไม่เกี่ยว, ปฏิเสธฟังก์ชัน, ไม่สมมุติผลทดสอบหรือสเปก
9. Unknown/หมวดต่างกันไม่ถูกแนะนำด้วย Dataset ผิดหมวด Legacy ข้อมูลไม่ครบไม่ถูกแต่งเติม
10. Version เดียว/Derived comparison/Method mismatch บอกตามจริง และ Child แสดงผลวิเคราะห์ปกติได้
11. ลบ Parent/User ระหว่างงาน หรือเปิดผลหลังลบแล้วไม่มีข้อมูลรั่ว/ผลสำเร็จปลอม/ลิงก์เสียที่ไม่มีสถานะรองรับ

รัน Regression แผน/ผลเก่า/Upload/Analysis settings และ Tests ใหม่ทั้ง Backend/Flutter พร้อม Browser flow จริงโดยใช้ฐานทดสอบแยก ห้ามให้การเปิด Server ทดสอบเรียก Collector จริงโดยไม่จำเป็น
Fixtures ไม่ใช่ผลทดสอบความแม่นกับคลิปใหม่ ต้องบอกชัด หากไม่มีคู่คลิปจริง ให้จบด้านฟีเจอร์และระบุว่ายังรอทดสอบ End-to-end ด้วยวิดีโอจริง

## 8. ส่งมอบ

สร้าง `docs/implementation/recommendation-phase6-handoff.md` พร้อม API/Schema, ความสัมพันธ์ Parent-Child-Plan, State machine, Version compatibility, นโยบาย Retry/Restart/Deletion, Tests และข้อจำกัด ASR

เกณฑ์ฟีเจอร์ผ่าน: อัปโหลดฉบับใหม่ -> ได้ผลใหม่และผลเทียบที่อ้างแผนถูก -> รีสตาร์ต/เปิดกลับมาได้ -> ผลเดิมไม่เปลี่ยน -> ทุกข้อสรุปมีข้อความรองรับหรือสถานะงดสรุป

สรุปภาษาไทยว่าแก้อะไร รัน Test ใด ผลจริงอะไรที่ยังไม่มี และ URL ทดสอบ อย่าสรุปว่า "คำแนะนำทำให้คลิปดีขึ้นหรือยอดเพิ่ม" จากการตรวจพบคำ

หากต้องหยุดระหว่างทาง ให้เขียนสิ่งที่เสร็จ/ค้าง/คำสั่งทดสอบ/ข้อผิดพลาดจริงใน Handoff เพื่อเริ่ม Session ถัดไปได้ ไม่เริ่ม Phase 7 อัตโนมัติและไม่ถือว่า Commit หรือ Build สำเร็จเท่ากับผ่าน User flow
