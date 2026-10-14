# Outcome Prediction: Full Review and Handoff

Follow-up: [R1-R8 software fixes and verification, 11 October](outcome-prediction-review-fixes-20261011-handoff.md). This report preserves the original review findings and real-data snapshot.

ตรวจวันที่ 10 ตุลาคม 2026 หลัง Phase 7 ตามคำขอให้ตรวจ ทดสอบ และแนะนำวิธีแก้

## คำตัดสิน

**ยังไม่พร้อมเปิด Outcome Prediction จริง** ทั้งด้านข้อมูลและงานโค้ด ไม่ใช่เพียงรอเติม Transcript แล้วกด Train ได้ทันที

Regression เดิมผ่าน แต่พบ 8 ประเด็นที่ควรแก้ก่อนรับรองการใช้งานจริง โดย 7 ประเด็นมีเคสจำลองทำซ้ำ ส่วนขั้น Independent evaluation พบจากการอ่านเส้นทางโค้ดและ Test ที่ยืนยันว่าระบบหยุดเมื่อทุก Gate ผ่าน

รอบนี้ไม่แก้โค้ดระบบ ไม่ Train/Activate ไม่แก้สิทธิ์หรือ Protocol ไม่เปิด Independent Test จริง และไม่เขียนฐานข้อมูลจริง สร้างเฉพาะรายงานและหลักฐานตรวจใน `artifacts/outcome-prediction/review/20261010T082732Z/`

## Findings

### R1 [P1] ยังไม่มีขั้น Independent Test ที่รับรองโมเดลได้จริง

- Source: `app/services/outcome_final_evaluation.py:198`, `scripts/evaluate_outcome_release.py`, `app/services/outcome_prediction_readiness.py:637`.
- `build_phase6_reports()` สร้างรายงาน `not_run`/ไม่ผ่านได้ แต่เมื่อเงื่อนไขพร้อมทั้งหมดจะโยน `ValueError` ให้ไปใช้ explicit one-shot evaluator ซึ่งยังไม่มี implementation ใน app/scripts
- Training สร้าง Candidate ได้สูงสุดสถานะ Validation ผ่าน ไม่ได้ประเมิน Independent Test และไม่มีทางทำงานจริงที่บันทึก `independent_test_passed=True` พร้อมผลรับรอง
- Readiness ยังตั้ง `fresh_outcome_test_count=0` ตายตัว ขณะที่ Final evaluation ใช้ค่านี้เป็น Gate จึงไม่มีทางตรวจผ่านจากผล Audit เดิม แม้เตรียมข้อมูลเพิ่มแล้ว
- **ผลกระทบ:** เส้นทาง Train -> Independent Test -> Qualified -> Activate ยังไม่ครบ เอกสารส่งมอบครบไม่ได้แปลว่าขั้นนี้พร้อม
- **แก้:** เพิ่มตัวประเมินครั้งเดียวที่อ่าน Frozen manifest/candidate/protocol/feature/calibration/benchmark hashes ตรวจความเป็นอิสระ บันทึก Test access ledger ประเมิน Candidate และ Baselines โดยไม่ Fit จาก Test และบันทึก Metrics/Scope decision/Artifact/Registry ให้ตรวจย้อนกลับได้ ให้ Audit นับ Fresh Test จาก Manifest และประวัติใช้ข้อมูลจริงแทนค่าตายตัว
- **Retest:** Gate ไม่ครบต้องไม่อ่าน Test; Gate ครบต้องได้ผลผ่านหรือไม่ผ่านจริง; เปิดซ้ำ/เปลี่ยน Hash/ข้อมูลรั่วต้องถูกปฏิเสธ; ไม่ Train หรือปรับเกณฑ์จาก Test

### R2 [P1] หน้าอัปโหลดปกติไม่ส่งข้อมูลที่ Predict บังคับใช้

- Source: `frontend_flutter/lib/repositories/analysis_repository.dart:16`, `app/routes/analyze.py:76`, `app/services/outcome_inference.py:260`.
- `startAnalyzeAndSaveVideo()` ส่งเฉพาะไฟล์ ไม่มี `confirmed_format` หรือ `reference_age_context`; Backend คืน metadata ว่างเมื่อไม่มีทั้งสองค่า
- เคสที่มี Qualified fixture และข้อมูลอื่นพร้อมยังได้ `unsupported_context` พร้อม `confirmed_format_required`, `duration_required`, `reference_age_context_required` และ Probability เป็น null
- **ผลกระทบ:** มีโมเดลดีแล้วก็ยังไม่ได้ Predict ผ่านหน้า Upload ปกติ
- **แก้:** เชื่อม UI/Repository/API ให้ยืนยันรูปแบบคลิปและบริบทอ้างอิงที่ระบบรองรับ วัด Duration ที่ Backend หรือใช้กฎเลือกบริบทที่ตรึงและแสดงชัด ไม่เดา Shorts จากความยาวอย่างเดียว และไม่เลือกช่วงอายุที่ให้เปอร์เซ็นต์สูงสุด
- **Retest:** ทดสอบ Upload -> Job -> assessment -> Save -> reopen ผ่าน Multipart จริง และกรณีไม่ยืนยัน/บริบทไม่รองรับต้องงดทำนายอย่างถูกต้อง

### R3 [P1] คำปฏิเสธใช้ข้อมูลรายวัตถุประสงค์ไม่ถูกบังคับ

- Source: `app/services/outcome_prediction_readiness.py:177`.
- `data_use_gate()` ตรวจ status/owner/intended_uses/evidence แต่ไม่อ่าน `decision.real_training_allowed` และ `decision.real_serving_allowed`
- เคสจำลองที่ status confirmed มี owner/evidence แต่ทั้งสองค่าเป็น false และ synthetic permission เป็น false ยังผ่านทั้ง Training และ Serving Gate
- **ผลกระทบ:** หากยืนยันเอกสารแล้วแต่ไม่อนุญาตบางวัตถุประสงค์ ระบบอาจอนุญาตผิด ปัจจุบันข้อมูลจริง status unverified จึงยังถูกบล็อกอยู่
- **แก้:** บังคับการอนุญาตราย purpose ว่าต้องเป็น true แยก Audit/Synthetic test/Real training/Real serving อย่างชัดเจน ตรวจทั้ง Train, Activate, Inference และ Scenario ไม่เปลี่ยนเอกสารเป็น confirmed แทนเจ้าของข้อมูล
- **Retest:** false/missing/withdrawn ต้องปฏิเสธ; Synthetic fixture ห้ามใช้ผ่านทาง Real serving

### R4 [P1] Transcript ที่เหมือนกันหลังจัดรูปข้อความข้าม Split ได้

- Source: `app/services/outcome_dataset.py:117`, `app/services/outcome_training.py:453`; เปรียบเทียบกับตัวตรวจ normalized hash ใน `app/services/outcome_prediction_readiness.py:76`.
- Freeze/Training ตรวจ Video ID, Channel/Creator และ SHA ของข้อความดิบ แต่ไม่บังคับ normalized-text identity ที่ Audit ตรวจไว้
- ตัวอย่าง `Review camera low light battery` กับ `review CAMERA, low light; battery!` ต่างช่องและต่าง Video ID มี normalized hash เดียวกัน แต่ Freeze ได้ 2 แถวใน Fit และ Tuning โดยไม่ตัดออก
- **ผลกระทบ:** การเปลี่ยนตัวพิมพ์หรือเครื่องหมายทำให้เนื้อหาซ้ำหลุดไป Validation/Test และทำให้คะแนนดูดีเกินจริง
- **แก้:** รวมกลุ่มตัวตนด้วย normalized hash และรายการ near-duplicate ที่ตรวจแล้ว ร่วมกับ Video/Channel/Creator ก่อน Freeze และตรวจซ้ำตอน Train ห้ามย้าย Protected Test กลับเข้า Train เพื่อให้ผ่าน
- **Retest:** punctuation/case/space duplicates และกลุ่มซ้ำที่เชื่อมต่อกันหลายแถวต้องไม่ข้าม Split

### R5 [P1] Inference ไม่บังคับขอบเขตที่ผ่านการประเมิน

- Source: `app/services/outcome_inference.py:154`, `app/services/outcome_inference.py:239`, `app/services/outcome_model_management.py:454`.
- Snapshot และ `_qualification_reasons()` ตรวจสถานะรวม แต่ไม่ตรวจว่าหมวด/format/age ของคำขอผ่านการรับรองรายขอบเขตจริง
- Activation ตรวจเพียงมีชื่อมิติ `overall/category/confirmed_format/frozen_age_context` ครบ ไม่ใช่ผลรับรองค่าภายในแต่ละมิติ
- เคสจำลองแยกฐานข้อมูล ตั้ง Active fixture ว่ารับรองขอบเขตอื่น แต่ขอ camera ได้ `available` และ Probability ใช้ Artifact loader และ Hash check จริง ไม่ Stub loader
- ขอบเขตของหลักฐาน: เคสนี้ทดสอบ Inference หลังมี Active row ในฐานจำลอง ไม่ใช่หลักฐานว่าข้อมูลรูปแบบนั้น Activate ผ่าน Route จริง หรือมีโมเดลจริงที่ผ่านการรับรองแล้ว
- **แก้:** ออกแบบรายชื่อ Qualified contexts จาก Independent evaluation ให้ชัด ตรวจตอน Activate/Inference/Scenario/Revision ให้ข้อมูลที่ไม่มีผลประเมินหรือไม่ผ่านงดทำนาย
- **Retest:** โมเดลที่ผ่านเฉพาะ Phone ต้องไม่ให้ Camera Probability; scope ว่าง/ไม่ผ่าน/registry ไม่ตรง artifact ต้องปฏิเสธ

### R6 [P2] Coverage ตอนประเมินไม่ตรงกับตอนใช้งาน

- Source: `app/services/outcome_training.py:214`, `app/services/outcome_inference.py:306`.
- `_evaluation()` กำหนด `abstained=0` และ Coverage 100% สำหรับข้อมูลที่ส่งเข้ามา แต่ Serving ใช้กฎ topic signature ต้องมีจำนวนคลิป/ช่องสนับสนุนถึงเกณฑ์
- Fixture จริงของชุดทดสอบมี Tuning 30 แถว รายงาน Coverage 30/30 แต่ผ่านกฎ Serving เพียง 25/30 (83.33%)
- **ผลกระทบ:** Metrics และ Coverage ที่ใช้ตัดสินโมเดลไม่สะท้อนคลิปที่ผู้ใช้จะได้คำตอบจริง ตัวเลขนี้เป็นการตรวจซอฟต์แวร์จาก Fixture ไม่ใช่ความแม่นยำของ Dataset จริง
- **แก้:** ใช้กฎ support/abstention ชุดเดียวใน Tuning/Test/Serving รายงานจำนวนที่ประเมิน/งดและเหตุผลแยกขอบเขต รักษา denominator ที่ประกาศไว้ และเปรียบ Baselines บนประชากรที่เทียบกันได้
- **Retest:** unseen/sparse signature ต้องถูกนับเป็น abstention เหมือน Inference และ Coverage ต้องตรงกัน

### R7 [P2] ข้อความเหตุผลอาจบอกว่าเลขน้อยสูงกว่าเลขมาก

- Source: `app/services/outcome_evidence.py:80`, `app/services/topic_comparisons.py:312`.
- Direction มาจากค่าต่างแบบจับคู่ภายในช่อง แต่ข้อความนำไปขยาย Median รวมทุกคลิป ซึ่งเป็นคนละสถิติ
- Fixture 10 ช่องที่จำนวนคลิปแต่ละกลุ่มไม่สมดุลได้ within-channel median difference +14.5 แต่ pooled medians เป็น 112 และ 10,000 ข้อความจริงจึงออกว่า `112 ซึ่งสูงกว่า ... 10,000`
- **ผลกระทบ:** เหตุผลที่ผู้ใช้เห็นขัดกับตัวเลข แม้การคำนวณภายในช่องจะไม่ผิด เป็นกรณีที่ควรแก้แม้ยังไม่มี Outcome model จริง
- **แก้:** อธิบายผลต่างจากการเทียบภายในช่อง/บริบท พร้อมช่วงความไม่แน่นอนและจำนวนช่อง ส่วน pooled medians แสดงแยกและไม่ใช้ Direction ของอีกวิธีมาสรุป รวมทั้งระบุหน่วยของช่วงความไม่แน่นอนให้ตรง
- **Retest:** กรณี Simpson's paradox, ผลลบ และผลไม่ชัดต้องมีข้อความตรงกับสถิติและไม่อ้างเหตุ-ผล

### R8 [P2] Calibration version ใน Registry ไม่ตรงกับ Artifact

- Source: `app/services/outcome_model_management.py:366`, `app/services/outcome_training.py:46`, `app/services/outcome_inference.py:366`.
- Worker บันทึก `weighted-sigmoid-v1` แต่ Training/Artifact ใช้ `weighted-platt-sigmoid-v1`; เวอร์ชันในผลบันทึกอ่านจาก Registry
- เคสทำซ้ำใช้ Worker กับฐานชั่วคราวและ Stub trainer ตาม Unit fixture เดิม พบ version mismatch จริง ไม่ได้ Train โมเดลจากข้อมูลจริง
- **ผลกระทบ:** ผลเก่าระบุวิธี Calibration ผิด ทำให้ตรวจย้อนกลับหรือเทียบเวอร์ชันคลาดเคลื่อน
- **แก้:** ใช้เวอร์ชันจาก Report/Artifact ต้นทางเดียว และตรวจว่าตรงกันเมื่อ Register/Activate/Load
- **Retest:** training artifact -> registry -> saved assessment ต้องได้เวอร์ชันเดียวกัน; mismatch ต้องไม่เงียบ

## ข้อมูลจริงและสิ่งที่ยังไม่ใช่บั๊ก

Read-only audit ณ cutoff `2026-10-10T08:27:32Z` และ Dataset build ที่ cutoff เดียวกัน:

| รายการ | ผลจริง |
|---|---:|
| Phone / Camera / Laptop | 109 / 101 / 98 คลิป |
| รวม / Video IDs ไม่ซ้ำ / ช่อง | 308 / 308 / 123 |
| แถวผ่านโครงสร้าง Outcome | 0 |
| ขาด confirmed format | 308 |
| ขาด sampling frame ที่ยืนยันได้ | 308 |
| ไม่มี Observation ที่ใช้ได้ก่อน cutoff | 117 |
| Transcript ไม่ใช่เต็มคลิป | 77 |
| Observation สำเร็จเกินอายุที่ Protocol กำหนด | 13 |
| Registered / Active Outcome model | 0 / 0 |

จำนวนเหตุผลข้างต้นซ้อนกันได้ ห้ามบวกเป็นจำนวนคลิปที่ต้องหาใหม่ทั้งหมด ทั้ง 308 คลิปยังอาจมีข้อมูลที่แก้ Metadata แล้วใช้ได้ ต้องตรวจรายแถวก่อนเก็บเพิ่ม

- Data-use ยัง unverified; Build สถานะ `blocked_data_use`, ไม่สร้าง Manifest และ DB unchanged ทั้งสองคำสั่ง
- Classification holdout เดิม 99 คลิป มี explicit prior artifact roles 84 คลิป ต้องตรวจประวัติใช้ก่อนเรียก Fresh Outcome Test ไม่ใช่ย้ายมาทดสอบใหม่เพราะชื่อ Split เป็น Test
- ค่า Fresh Test 0 ใน Audit เป็นค่าตายตัวตาม R1 จึงไม่ใช่หลักฐานนับคลิปที่มีอยู่จริงทั้งหมด ใช้สรุปว่าผู้ใช้ต้องหาเพิ่ม 30 คลิปทันทีไม่ได้
- ตัวเก็บสถิติอ้างอิงเดิมเลือก Train/reference เท่านั้น ต้องเตรียมช่องทางเก็บ Outcome ของ Protected holdout ที่ไม่รั่วเข้าข้อแนะนำหรือการปรับโมเดล การรอ Scheduler เดิมอย่างเดียวไม่แก้ช่องว่างนี้
- Active classifier 43 เป็น presentation_only หมดอายุ `2026-10-06T16:42:53Z`; `can_accept_predictions=false` ด้วยเหตุ model_not_qualified, scope_policy_not_validated, presentation_expired ห้ามขยายเวลาหรือข้าม Gate เงียบ ๆ
- ยังไม่มี Independent Outcome metrics, Qualified probability หรือ Human utility ratings จริง การเทรนจำแนกหมวดที่ทำก่อนหน้านี้ไม่ใช่การเทรน Outcome model

## หลักฐานทดสอบรอบนี้

| การตรวจ | ผล |
|---|---|
| Focused Backend Outcome/Delivery | PASS: 55 tests, 10.237s |
| Full Backend regression | PASS: 568 tests, 128.590s |
| Flutter Outcome user/admin widgets | PASS: 23 tests |
| Review reproductions | ยืนยันปัญหา 7 เคส, exit 0 |
| Readiness audit / Dataset build | exit 0, DB unchanged; Data/Prediction ยัง blocked |
| Live browser / MP4 -> ASR -> Prediction รอบนี้ | NOT RUN |
| Real Independent Test / Human utility | NOT RUN |

55 Focused tests เป็นส่วนหนึ่งของ 568 ไม่ใช่ชุดอิสระที่ต้องบวกกัน ข้อความ STT/Topic failure ใน regression เป็น failure fixtures และกระบวนการจบด้วย OK มี DeprecationWarning ของ swigvarlink แต่ไม่มี Test failure

Backend/Web ที่พอร์ต 8000/8080 ไม่ได้เปิดอยู่ตอนตรวจ จึงไม่อ้างผลเก่าหรือ Widget fixtures ว่าเป็น Live E2E วันนี้ ไม่ได้รัน Flutter analyze/full Flutter suite/web build หรือ Backup/Restore ซ้ำในรอบนี้ ผล Phase 7 เดิมยังเป็นหลักฐานคนละรอบ

คำสั่งที่รันจาก Project root:

```powershell
$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
py -X utf8 -m unittest tests.test_outcome_prediction_readiness tests.test_outcome_dataset tests.test_outcome_training tests.test_outcome_model_management tests.test_outcome_inference tests.test_outcome_final_evaluation tests.test_outcome_delivery tests.test_delivery_tools -v
py -X utf8 -m unittest discover -s tests -q
py -X utf8 scripts/audit_outcome_prediction_readiness.py --cutoff 2026-10-10T08:27:32Z --output-dir artifacts/outcome-prediction/review/20261010T082732Z/readiness
py -X utf8 scripts/build_outcome_dataset.py --cutoff 2026-10-10T08:27:32Z --output-dir artifacts/outcome-prediction/review/20261010T082732Z/dataset-build
py -X utf8 artifacts/outcome-prediction/review/20261010T082732Z/review_probes.py
```

จาก `frontend_flutter`:

```powershell
C:\flutter\bin\flutter.bat test --no-pub test/outcome_prediction_test.dart test/outcome_admin_training_test.dart
```

หลักฐานอยู่ใน:

- `artifacts/outcome-prediction/review/20261010T082732Z/readiness/`
- `artifacts/outcome-prediction/review/20261010T082732Z/dataset-build/`
- `artifacts/outcome-prediction/review/20261010T082732Z/review_probes.py`
- `artifacts/outcome-prediction/review/20261010T082732Z/review-probes.json`
- `artifacts/outcome-prediction/review/20261010T082732Z/test-results.json`

Review artifacts เป็น local ignored files และบางส่วนมี identifiers/metadata จาก Dataset ไม่รวมไว้ใน Public release โดยอัตโนมัติ

## งานต่อที่แนะนำ

1. แก้ R1-R8 พร้อม Regression tests โดยยังใช้ Fixture และไม่แตะ Test จริง ให้ Qualification/Serving/Evidence มีความหมายตรงกันทั้งระบบ
2. ตรวจ 308 คลิปเดิมรายแถว เติม format/sampling provenance/สถิติ/สิทธิ์ตามหลักฐาน ไม่กรอกเพื่อให้ผ่านเฉย ๆ และไม่บังคับเก็บ Transcript ใหม่ทั้งหมด
3. ยืนยัน Outcome partition/identity/prior use และเตรียม Protected holdout statistics ก่อนเลือก Candidate แก้ Readiness ของ Classifier แยกจาก Outcome
4. Freeze/Train/Validate/Calibrate/เลือก Candidate จาก Fit/Tuning/Calibration ก่อนเปิด Independent Test ครั้งเดียว; ถ้าไม่ผ่านให้คงไม่ผ่าน
5. เมื่อ Qualified จริงจึงทดสอบ Upload/Save/Reopen/Scenario/Revision/Activate/Rollback บนเว็บจริง และประเมินประโยชน์กับคนจริงตาม Protocol
6. สร้าง Release revision/Hashes/เอกสารให้ตรงหลังแก้ อย่าเปลี่ยนหลักฐานตรวจรับเก่าให้ดูเหมือนตรวจโค้ดใหม่แล้ว

สถานะรับช่วง: **Review complete; product fixes not implemented; real Prediction NO_GO.** ไม่เริ่ม Phase ใหม่อัตโนมัติและไม่เปลี่ยนเกณฑ์เดิม
