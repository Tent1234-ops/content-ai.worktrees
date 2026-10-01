# Handoff: Closeout Phase 2

วันที่ 1 ตุลาคม 2026. ทำเฉพาะ Phase 2: ปิดแกนวิเคราะห์และคำแนะนำ ไม่เริ่ม Phase 3

## สถานะตรวจรับ

**ผ่านเฉพาะส่วน / ยังไม่ผ่านเกณฑ์จบ Phase 2** เพราะยังไม่มี Active Model ที่ผ่าน scope validation และยังไม่มีข้อมูล Unknown Validation/Test ตามขั้นต่ำ จึงยังสร้างหลักฐาน Positive live flow ที่รับหมวดและให้คำแนะนำจริงไม่ได้ ระบบยังคง fail closed ตามข้อกำหนด ไม่ลด threshold และไม่ใช้ผลทายดิบหรือกฎเก่าฝืนเลือก Dataset

## เสร็จแล้ว

1. ตรวจเส้นทาง Upload -> ASR -> Active Model -> acceptance -> evidence -> actionable advice -> save/reopen และ revision เทียบกับข้อกำหนด Phase 2 โค้ดปัจจุบันเก็บ raw/cleaned transcript, segments และเวลาจริงเมื่อ ASR ส่งมา; ไม่มีเวลาจริงจะไม่สร้าง Timestamp เอง
2. ยืนยันว่าคำแนะนำภาษาไทยแยก “พบอะไร -> เสนออะไร -> วิธีทำ -> ตัวอย่าง -> เหตุผล” เลือกไม่เกิน 3 ข้อ, กันคำพ้องที่พูดแล้ว, ไม่แต่งสเปก และระบุว่าหลักฐานเป็นความสัมพันธ์ ไม่ใช่เหตุรับประกัน Engagement
3. ยืนยันสถานะแยกกันสำหรับ Unknown, ASR/ข้อความประเมินไม่ได้, หลักฐานอ้างอิงไม่พอ และตรวจพบหัวข้อครบแล้ว; Duration ใช้ขั้นต่ำ 10 ตัวอย่างและแสดง median/percentile/n หรือ insufficient evidence
4. แก้ชื่อผลวิเคราะห์ **รายการใหม่** ให้มาจากชื่อไฟล์อัปโหลดที่ sanitize เท่านั้น: ตัด path/นามสกุล, แปลง `_`/`-` เป็นช่องว่าง, ตัด control characters และมีชื่อสำรอง ไม่ใช้สรุป ASR เป็นชื่อและไม่ใช้ filename เป็น feature/หลักฐาน
5. `save_video_analysis_result()` คืนชื่อเดียวกับที่บันทึกจริง ทำให้ผล Job กับรายการย้อนหลังไม่คลาดกัน ผลเก่าไม่ถูกแก้หรือคำนวณใหม่; isolated test ยืนยันว่า ASR summary ยังอยู่ใน snapshot สำหรับ audit แต่ไม่เป็นชื่อรายการ
6. แก้ browser verification ให้ตรงกับ UI ปัจจุบันที่ยุบแผงหลักฐานและใช้ชื่อหัวข้อไทยจาก payload แทน hard-code ชื่ออังกฤษเดิม
7. นำ Transcript Unknown 42 ไฟล์เข้า **Pending Review เท่านั้น** เป็น Collection Run #24: train35 / validation5 / test2 ตาม channel hash จริง ไม่ Auto-approve, ไม่ย้าย split, ไม่ Train และไม่ Activate

## ข้อมูลและโมเดลจริง

- Settings ณ เวลาตรวจ: อัปโหลดสูงสุด 300 วินาที, Whisper `small` (`asr_ready=true`), Hook 60 วินาที
- Active ยังเป็น #14 `taxonomy-tfidf-complement-nb` รุ่น `20260828T134420Z`, artifact โหลด/ใช้ได้ แต่ readiness เป็น `blocked`: `scope_policy_missing`, `can_accept_predictions=false`
- ชุดที่ผ่าน training contract: Phone80 จาก27ช่อง, Camera79 จาก43ช่อง, Laptop85 จาก23ช่อง; Camera ยังขาด1
- Camera ใหม่ 5 รายการถูก Admin อนุมัติไว้ก่อนรอบ Phase 2 นี้เมื่อ 1 ต.ค. 11:19; Camera ไฟล์ที่6 ซ้ำ Dataset #422 จึงไม่สร้างซ้ำ
- Unknown ใน Dataset ที่ผ่าน review ยังเป็น0; Run #24 รอตรวจ42 รายการ หากทุกแถวผ่านก็ยังมี Validation5/Test2 เท่านั้น เทียบขั้นต่ำ Validation10/Test30 และอย่างน้อย3ช่องต่อ split
- Training fingerprint ก่อน/หลังนำเข้าคิวเท่ากัน: `de73e06bb5a457f89a1b5a128416e64ca7e59c4e724dc7086ba04271e85c4eee`; Active ก่อน/หลังยังเป็น #14
- Review summary ก่อน/หลัง browser test เท่ากัน: total392 / pending42 / approved318 / rejected32 และไม่มี POST อนุมัติ

## ผลจริงและข้อจำกัด

- ผลจริงล่าสุด Analysis #18 / Content #19 จาก `Review_Phone.mp4` มี ASR input ใช้ได้ โมเดลดิบทาย Phone แต่ acceptance ปฏิเสธด้วย `scope_validation_unavailable`; ผลสุดท้ายเป็น Unknown และ `withheld_unknown` ถูกต้อง ใช้เป็น regression fail-closed เท่านั้น ไม่ใช่หลักฐานความแม่นหรือ Positive flow
- ชื่อ ASR อ่านยากของ Content #19 เป็นข้อมูลเก่าและยังคงเดิมตามสัญญาไม่เขียนประวัติทับ ผลใหม่จะใช้ชื่อไฟล์ แต่ยังไม่ได้อัปโหลดวิดีโอจริงซ้ำเพื่อสร้างแถวใหม่
- ไม่มี human transcript ที่จับคู่กับไฟล์เสียงทดสอบใหม่ จึงไม่รายงาน WER หรือกล่าวว่า ASR แม่นจากความรู้สึก
- ไม่มีคลิปฉบับแก้ไขจริง จึงตรวจ revision ได้เฉพาะ software contract/fixture และต้องไม่อ้างว่าผู้ใช้ปรับเนื้อหาสำเร็จแล้ว
- ไม่มี fresh video test Phone/Camera/Laptop อย่างละ10, คลิปถ่ายเอง และคะแนนผู้ประเมินมนุษย์ตาม protocol; utility ยังเป็น `not_evaluated`

## Verification

- Backend **142 tests ผ่าน** สองชุดไม่ซ้ำ: classification acceptance/unified pipeline, title persistence, evidence, actionable advice, duration, settings, plan/revision, ASR failure, training/evaluation และ utility protocol
- Flutter **23 tests ผ่าน**: สถานะ/คำศัพท์, evidence, copy, draft/save/reopen, save failure และ revision comparison
- Browser actionable fixture **6 cases ผ่าน** ที่ 1440/1000px สำหรับ Phone/Camera/Laptop, 2–3 ข้อพร้อมหลักฐาน, ไม่มี JS/overflow error และไม่มี mutation request
- Browser evidence + real review summary **ผ่าน** ที่ 1440/1000px, เปิด dialog/หลักฐานได้, `review_posts=[]`, pending ก่อน/หลังเท่ากัน42
- Backend รีสตาร์ตด้วยโค้ดล่าสุด PID18052; `/health` ตอบ200. Web เดิมยังเปิดที่ `http://127.0.0.1:8080`

หลักฐาน:

- `artifacts/project-closeout/phase1-20261001/phase2-pending-review-import.json`
- `artifacts/project-closeout/phase2-20261001/readiness-after-import.json`
- `artifacts/browser/actionable-advice/verification.json`
- `artifacts/browser/recommendation-evidence/verification.json`
- `artifacts/project-closeout/phase2-20261001/api.stderr.log`

```powershell
python -m unittest tests.test_analysis_result_title tests.test_phase18_unified_classification_pipeline tests.test_classification_acceptance tests.test_recommendation_evidence tests.test_actionable_recommendations tests.test_phase21_recommended_duration tests.test_analysis_settings tests.test_clip_revision_plans tests.test_revision_comparisons
python -m unittest tests.test_full_clip_analysis tests.test_analysis_evaluation tests.test_recommendation_phase_review tests.test_recommendation_utility_evaluation tests.test_classification_training
C:\flutter\bin\flutter.bat test test/recommendation_result_test.dart test/recommendation_evidence_test.dart test/actionable_advice_test.dart test/clip_revision_planner_test.dart test/revision_comparison_test.dart
node scripts/browser/verify_actionable_advice.cjs
node scripts/browser/verify_recommendation_evidence.cjs
```

## ค้างและเงื่อนไขปลด Gate

| สถานะ | งาน | เงื่อนไข/ผู้รับผิดชอบ |
|---|---|---|
| pending human review | ตรวจ Unknown42 ใน Run #24: Transcript, หมวด, ที่มา/สิทธิ์ และ channel split | Admin ต้องตรวจจริงก่อน Approve; ห้ามใช้ Approve All โดยไม่ได้ตรวจ |
| blocked by data | เพิ่ม Camera ที่ไม่ซ้ำอีก1รายการ | ต้องผ่าน review และ contract เดิม |
| blocked by split | เพิ่ม Unknown Validation อย่างน้อย5 และ Testอย่างน้อย28 พร้อมช่องที่ยังขาด | เก็บตาม channel hash; ห้ามย้ายแถวเพื่อทำจำนวนให้ครบ; Unknown train35 สำรองและไม่ fit โมเดล |
| blocked by evaluation | Train/evaluate candidate models และรายงาน per-class/confusion/Unknown แยก n/channels | เริ่มได้เมื่อ collection gate ผ่าน; activation ต้องให้เจ้าของโครงการยืนยันจากผล ไม่เปิดอัตโนมัติ |
| blocked positive flow | อัปโหลดคลิปใหม่ที่ Active Model รับหมวด แล้วตรวจ advice/evidence/copy/select/save/reopen/restart แบบ live | ทำได้หลังมีโมเดลผ่าน scope policy; ตอนนี้ fixture ไม่ใช่หลักฐาน live |
| pending evaluation | วิดีโอใหม่สามหมวด, คลิปถ่ายเอง/นอกขอบเขต และ human review ตาม protocol | กันจาก train/reference ตั้งแต่ต้น; regression ที่ใช้แก้บั๊กไม่นับเป็น Test ใหม่ |
| pending revision | คลิปฉบับแก้ไขจริงที่เชื่อม parent/plan | ตอนนี้ยืนยันได้เฉพาะ software contract |

## ไม่ได้ทำ

- ไม่ Train/benchmark รุ่นใหม่, ไม่ Activate/Rollback, ไม่ลด Unknown threshold และไม่แก้ scope policy ให้ผ่านปลอม
- ไม่ Approve/Reject Pending42, ไม่แก้ Transcript, label หรือ split ของผู้ใช้
- ไม่เพิ่มแพลตฟอร์ม, ไม่เริ่ม Phase 3 และไม่ประกาศว่า Phase 2 ผ่านทั้งเฟส
- Git status ยังใช้ไม่ได้จาก worktree metadata เดิมที่หาย ไม่แก้ Git metadata และไม่ revert งานเดิม
