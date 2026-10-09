# Outcome Prediction Phase 4 Handoff

วันที่ตรวจล่าสุด: 9 ตุลาคม 2026

## คำตัดสิน

- **Software path ของ Phase 4: complete**
- **Qualified-fixture behavior: ผ่านสำหรับทดสอบ software เท่านั้น**
- **Live Outcome probability: blocked / `probability = null`**
- **Prediction qualified: false**
- **Independent Test opened: false**
- **Production activation: false**
- **Phase 5: ยังไม่เริ่ม**

สาเหตุที่ระบบจริงยังไม่แสดง Probability ไม่ได้มาจาก Inference ขัดข้อง แต่เป็นการ fail closed ตาม Contract: Data-use record ยังเป็น `unverified`, ข้อมูลจริงยังไม่มี Frozen Outcome manifest ที่ผ่านเกณฑ์, ยังไม่มี Outcome model ที่ผ่าน Independent Test และ Activate อย่างถูกต้อง และรูปแบบ Short/Long ของข้อมูล/คลิปต้องมีหลักฐาน ไม่อนุมานจากความยาวหรือชื่อคลิป

## งานที่เสร็จ

### Inference กลาง

- เพิ่ม `outcome_inference.py` ใช้ Feature builder ตัวเดียวกับ Train และตรวจ Classification acceptance, Transcript ทั้งคลิป, สิทธิ์ข้อมูล, Active model, Qualification, artifact hash/schema/order, Frozen context, benchmark support และ exact joint-feature support จาก Fit
- Route วิเคราะห์รับ `confirmed_format` และ `reference_age_context` แบบ optional; เมื่อส่งครบจะตรวจ duration จากไฟล์จริงและตรึง provenance โดยไม่เดา Short/Long จาก duration ส่วน client เดิมที่ไม่ส่งค่ายังใช้ได้และ Outcome จะ abstain ตามจริง
- โหลด Artifact จาก trusted local root และ Cache ด้วย `model_id + artifact hash + path + protocol/feature hash`; หนึ่ง Assessment pin model snapshot ครั้งเดียว แม้ Active model เปลี่ยนระหว่างงาน
- คืน Probability ที่ผ่าน Calibration เฉพาะเมื่อทุก Gate ผ่าน ค่าอื่นคืน `null` พร้อม status/reason codes ไม่มีค่าเริ่มต้น 0 หรือ 0.5
- ค่า Probability หมายถึงโอกาสอยู่ในกลุ่มยอดวิวเหนือ Fit-derived median ภายใต้กลุ่มอ้างอิง ไม่ใช่โอกาสที่ทำตามคำแนะนำแล้วยอดวิวเพิ่ม
- Timeout/artifact/runtime failure กระทบเฉพาะ Outcome block; Recommendation เดิมยังคงอยู่
- เพิ่ม helper สำหรับ `legacy_not_assessed` และการถอนหลักฐานเป็น `withdrawn/inaccessible` โดยไม่สร้างข้อมูลกลับ

### หลักฐานและข้อความคำแนะนำ

- เพิ่มข้อความภาษาไทยตามระดับหลักฐาน: พบในตัวอย่าง, เทียบได้แต่ยังไม่ชัด, และเทียบได้พร้อมทิศทางบวก/ลบ
- เก็บจำนวนคลิป/ช่อง, median, paired channels, uncertainty, metric และเวลาไว้ใน structured evidence
- ผลลบและผลไม่ชัดไม่ถูกซ่อน และทุกข้อความระบุว่าเป็นความสัมพันธ์ในตัวอย่าง ไม่ใช่เหตุยืนยันยอดเพิ่ม
- Outcome ที่ไม่ผ่าน Gate ไม่ทำให้คำแนะนำเดิมหาย และไม่ใช้ Probability เปลี่ยนลำดับ 2-3 คำแนะนำเดิม
- ไม่เพิ่ม LLM call, web search หรือ paid API ใน request path

### Scenario สมมุติ

- เพิ่ม `POST /contents/{content_id}/outcome-scenario`
- ตรวจ ownership, analysis ID, assessment fingerprint, topic allowlist, สถานะ `not_detected`, paired evidence และ joint feature support ก่อนคำนวณ
- เปลี่ยนเฉพาะ Boolean topic ในสำเนา Feature; ไม่แก้ Transcript, Evidence, Revision plan หรือข้อมูลที่บันทึก
- ใช้ Model/Artifact/Context เดียวกันก่อนและหลัง และคืน signed delta หน่วย `percentage_points`; ค่าลบและศูนย์คงเดิม
- ระบุ `hypothetical=true`; ไม่มี field หรือข้อความ `estimated_views_increase`
- หากผลเดิม/โมเดล/บริบทไม่พร้อม คืน no-result status และค่าตัวเลขเป็น `null`

### Snapshot, History และ Revision

- เพิ่ม Optional `outcome_assessment` ใน JSON summary ของ `analysis_results` ภายใน Save transaction เดิม
- เก็บ version/hash/cutoff/context/input hash/feature snapshot/support/evidence pointers/limitations ณ เวลาวิเคราะห์
- GET รายละเอียดและประวัติอ่าน snapshot เท่านั้น ไม่เรียก Inference หรือ Dataset ใหม่; เปลี่ยน Active model ภายหลังแล้วผลเก่าไม่เปลี่ยน
- ผลเก่าไม่มี block แสดง `legacy_not_assessed` แบบ deterministic และ `assessed_at=null`
- API รายละเอียดคืน `outcome_assessment_fingerprint` สำหรับ Scenario โดยไม่ต้องให้ client สร้าง hash เอง
- Revision plan ตรึง parent Outcome snapshot; before/after แสดง delta เฉพาะ Target/Feature/Model/Artifact/Protocol/Context ตรงกันและ Transcript hash ตรวจได้
- Model/version/context mismatch หรือ ASR ใช้ไม่ได้จะแสดง `not_comparable` และ delta เป็น `null`

## Live Behavior ปัจจุบัน

ข้อมูลจริงยังมีสถานะ:

- Data-use: `unverified`; Serving ถูกบล็อก
- Structurally eligible ใน Final Phase 2 audit: 0
- Qualified Outcome model: ไม่มี
- Independent Test: ยังไม่เปิดตาม Protocol

ดังนั้นผลวิเคราะห์จริงยังแสดง Recommendation ที่มีหลักฐานเดิมได้ แต่ `outcome_assessment.status` จะอธิบาย Gate ที่ไม่ผ่านและ `probability` ต้องเป็น `null` การเปลี่ยน status หรือแต่ง Fixture ให้เป็นผลจริงถูกห้าม

## Qualified-Fixture Behavior

Tests สร้าง Synthetic fixture แยกใน temporary directory แล้วปรับ registry/artifact เป็น qualified เฉพาะภายใน test process เพื่อพิสูจน์ software path เท่านั้น ผลนี้:

- ใช้ Train/Inference feature schema และ topic presence แบบเดียวกัน
- คำเดิมที่พูดซ้ำไม่เพิ่ม Feature หรือ Probability
- Artifact hash ผิดแล้ว fail closed
- สลับ Active model กลาง Assessment ไม่ทำให้หนึ่งผลปะปนสองรุ่น
- Scenario ตรวจ owner/topic/support, ไม่ mutate snapshot และรักษาค่าลบ/ศูนย์

Fixture ถูกออกแบบให้ Topic สัมพันธ์กับ Label จึงห้ามใช้อ้างว่าโมเดลจริงแม่น หรือคำแนะนำทำให้ยอดวิวเพิ่ม

## ไฟล์สำคัญ

- `app/services/outcome_inference.py`
- `app/services/outcome_evidence.py`
- `app/services/outcome_scenarios.py`
- `app/routes/analyze.py`
- `app/routes/contents.py`
- `app/services/persistence.py`
- `app/services/contents.py`
- `app/services/revision_comparisons.py`
- `app/schemas/contents.py`
- `tests/test_outcome_inference.py`

Phase 3 artifact เพิ่ม `training_support` แบบ Fit-only เพื่อใช้ตรวจ joint topic signature ตอน Inference/Scenario; Artifact เก่าที่ไม่มีข้อมูลนี้จะ fail closed แทนการเดา Support

## หลักฐานทดสอบ

Focused Phase 4 + Regression ที่เกี่ยวข้อง:

```powershell
py -m unittest tests.test_actionable_recommendations tests.test_recommendation_evidence tests.test_revision_comparisons tests.test_clip_revision_plans tests.test_outcome_training tests.test_outcome_model_management tests.test_outcome_inference
```

ผล: **68 tests passed**

ครอบคลุม Unknown/ASR/context/data-use/model qualification/hash failure, Feature parity, repeat invariance, evidence negative/uncertain, model pinning, owner/topic/support scenario gates, signed negative/zero delta, immutable save/legacy GET และ revision mismatch

หมายเหตุ: Environment นี้ไม่มี package `pytest`; ใช้ test suite เดิมผ่าน `unittest` ตามโครงสร้าง repository

Full repository regression:

```powershell
py -m compileall -q app tests
py -m unittest discover -s tests -q
```

ผล: **555 tests passed** ใน 103.889 วินาที มีเพียง Deprecation warning จาก dependency ภายนอก

## งานค้างและ Owner

1. **Project owner:** ยืนยันสิทธิ์ใช้ Transcript และ YouTube-derived metrics สำหรับ Training/Serving พร้อมหลักฐานและ Retention; Agent ยืนยันแทนไม่ได้
2. **Dataset admin:** เติม/ตรวจ confirmed format, full transcript, observations, sampling frame และ Fresh Independent Test โดยไม่ย้าย Protected rows หรือลดขั้นต่ำ
3. **Phase 6 เท่านั้น:** เปิด Independent Test หลัง Freeze Candidate/Protocol แล้วตัดสิน Qualification ตามเกณฑ์เดิม
4. **Model admin หลัง Phase 6 ผ่าน:** Activate Outcome model แบบ atomic และ audit ได้; ห้าม Activate fixture
5. **Phase 5:** ทำ UI แสดง states/evidence/scenario/admin model โดยอ่าน contract ที่เพิ่มแล้ว งานนี้ยังไม่ได้เริ่มตามคำสั่ง

## Rollback

Phase 4 ไม่เพิ่มตารางหรือ destructive migration; ข้อมูลใหม่เป็น field ภายใน JSON summary แบบ additive หาก rollback application ให้คง historical JSON ไว้ รุ่นเก่าจะเพิกเฉย field เพิ่มได้ ห้ามลบ Outcome snapshot หรือเขียนผลเก่าทับระหว่าง rollback
