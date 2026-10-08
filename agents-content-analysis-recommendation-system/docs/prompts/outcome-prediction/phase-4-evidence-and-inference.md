# Phase 4: เชื่อมหลักฐาน การประเมิน และผลที่บันทึก

## คำสั่ง

อ่าน README, prediction-contract.md, Protocol และ Handoff Phase 1-3 ตรวจโค้ดแล้วทำเฉพาะ Phase 4 ไม่เริ่ม Phase 5 ไม่ Activate production และไม่เปิด Independent Test

ยังไม่มี Qualified model ก็ต้องทำ States/Save/Legacy flow ให้ครบด้วย Fixture ที่แยกชัด ไม่ปล่อย Probability ของโมเดลทดลองเป็นผลจริง

## อ่านก่อน

- `app/services/recommendation.py`, `actionable_recommendations.py`, `recommendation_templates.json`
- `app/services/recommendation_evidence.py`, `topic_comparisons.py`, `saved_recommendations.py`
- `app/services/clip_revision_plans.py`, `revision_comparisons.py`
- `app/services/classification_acceptance.py`
- `app/database/models.py`, Routes วิเคราะห์/บันทึกจริง และ Tests ที่เกี่ยวข้อง
- Outcome feature builder/registry/artifacts จาก Phase 2-3

ค้นตำแหน่ง Save และ JSON contract จริงก่อนแก้ ไม่เขียนคอลัมน์/Envelope ใหม่โดยเดาว่าปัจจุบันเป็นแบบไหน

## งาน

### A. Inference service กลาง

รับ accepted category, verified Transcript/segments, input metadata และ context ที่นโยบายเลือกไว้
1. ตรวจสิทธิ์ข้อมูล + Active outcome model + Qualification + artifact/schema/feature compatibility
2. ตรวจ Classifier gate ตามเดิม; ถ้า Unknown/expired/withheld ต้องไม่ใช้ Outcome ทายหมวดแทน
3. ตรวจ Transcript usability และรูปแบบคลิป; ไม่เดา Shorts จากความยาวหรือ Title
4. Resolve reference context ตาม Protocol โดยไม่เลือกตาม predicted score; Context ไม่พร้อมให้ abstain
5. สร้าง Feature ด้วยตัวเดียวกับ Train และตรวจ support/out-of-distribution ตาม Training-only policy
6. คืน calibrated probability เฉพาะเมื่อผ่านทุก Gate พร้อม provenance/context/limitations
7. หาก timeout/artifact error ให้ fail closed เฉพาะ Outcome เก็บ Analysis เดิมที่ยังใช้ได้พร้อมสถานะ ไม่ทำให้คำแนะนำที่มีหลักฐานหายโดยไม่จำเป็น

ไม่ Train/Bootstrap/Fit benchmark/เรียก API ใหม่ใน HTTP analysis request หรือ GET ผลเก่า
ใช้ Cache แบบ keyed by model/artifact hash ไม่ให้เปลี่ยน Active แล้วใช้ estimator เก่าค้าง

Support checks ใช้ Features/metadata ที่มีตอน inference ไม่ใช้ยอดวิวจริงของผู้ใช้มายืนยันว่าคำทำนายพร้อม

### B. คำอธิบายภาษาไทยตามระดับหลักฐาน

ต่อยอดข้อความ "พบอะไร -> ควรเพิ่มอะไร -> เพราะอะไร" และ Template เดิม
- มีแต่ตัวอย่าง: "พบประเด็นนี้ในคลิปอ้างอิง ... คลิป จาก ... ช่อง" ไม่เติมคำว่าได้ยอดสูงกว่าคลิปทั่วไป
- เทียบได้แต่ไม่ชัด: ระบุจำนวน/ค่ากลาง/ช่วงความไม่แน่นอน และ "ยังสรุปความต่างไม่ได้"
- เทียบได้และต่าง: ระบุ scope/time/metric จริงว่าเป็นความสัมพันธ์ในตัวอย่าง ไม่ใช่เหตุให้ยอดเพิ่ม
- Outcome ผ่าน: เพิ่มบริบทและผลประมาณของโมเดล โดยแยกจากตัวเลขสถิติต้นทางและ Confidence ของหมวด
- Outcome ไม่ผ่าน: ยังแสดงคำแนะนำที่หลักฐานรองรับตามเดิม พร้อมเหตุผลที่ไม่มีค่าประเมิน

ทุกข้อผูก Topic ID กับ evidence IDs ที่ย้อนถึงแถวจริง แสดง Negative/Uncertain results ได้
ไม่สร้าง LLM call เพื่อเรียบเรียงหรือหาหลักฐานจากเว็บสด; ใช้แม่แบบที่ตรวจได้โดยไม่เสียค่า API

เลือก 2-3 ข้อตาม relevance/actionability/evidence เดิม ไม่ใช้ Probability เป็นตัวคัดทุกอย่าง และไม่ใช้ "พูดคำนี้บ่อยขึ้น" แทนการเพิ่มเนื้อหาที่มีคุณภาพ

### C. Scenario ที่เป็นสมมุติ ไม่ใช่ข้อมูลจริง

ทำ Endpoint/Service เฉพาะหาก Gates ของ Contract รองรับ; API ต้องมี no-result status ได้ครบแม้ยังเปิดไม่ได้จริง
- รับ analysis ID ของผู้ใช้, selected canonical topic IDs และ context ที่ Frozen
- Validate ownership/allowlist; Topic ต้องเกี่ยวข้องและยังไม่พบ/ไม่ใช่ unassessable
- เปลี่ยน Feature เฉพาะ topic ที่เลือกในสำเนา จำลองแบบตรวจได้ ไม่แก้ Transcript/evidence/แผนว่า completed
- Require paired evidence support ตาม `topic_comparisons` ที่ผ่านขั้นต่ำเดิม และ joint feature support จาก Train
- ใช้ model/version/context เดียวกันก่อน-หลัง; delta แบบมีเครื่องหมาย ค่า 0 ใช้ได้ ไม่ปัดขึ้นให้ดูดี
- ตอบ hypothetical=true และหน่วย percentage_points ชัด ไม่ใช้คำว่า estimated_views_increase
- หลาย Topic จนอยู่นอก Support -> unsupported_context ไม่อนุมานว่าส่งหลายคำแล้วบวกผลได้
- เมื่อ unavailable/experimental ต้อง probability/delta=null ไม่คืน 0/0.5 เป็นค่าเริ่มต้น

ตัวเลขจำลองไม่จำเป็นต้องปรากฏเป็นหน้าหลัก และไม่ใช่เกณฑ์บังคับว่าทุกคลิปต้องได้ค่า ถ้าหลักฐานยังไม่พอให้รายงาน "ยังเปิดใช้ Scenario จริงไม่ได้"

### D. บันทึกผลและความเข้ากันได้

เพิ่ม `outcome_assessment` ตาม Contract เป็น Optional field:
- เก็บค่าที่ใช้จริง ณ ครั้งนั้น: version/hash/cutoff/context/input hash/evidence pointers/support/ข้อความ/limitations
- ต่อ Save Transaction เดิม ให้ commit สำเร็จก่อนแจ้งผู้ใช้; Rollback ไม่ทิ้งผลครึ่งก้อน
- GET analysis/history/saved ideas ต้องไม่เรียก inference/rebuild Dataset หรือเติม Assessment ใหม่
- ผลเก่าไม่มี field -> legacy_not_assessed; Re-analysis ต้องสร้างผลใหม่แบบมี parent/revision link
- เปลี่ยน Dataset/Active model แล้วเปิดผลเดิมต้องไม่เปลี่ยน
- ถ้าข้อมูลถูกถอนตามสิทธิ์/Retention ให้สถานะ withdrawn/inaccessible พร้อมเหตุผล ไม่ซ่อนว่าหลักฐานยังใช้ได้

### E. เทียบฉบับแก้ไขต่อจากระบบเดิม

- การเลือกแผนไม่เท่ากับตรวจพบหัวข้อ และไม่เท่ากับอัปโหลดฉบับแก้แล้ว
- เปรียบเทียบข้อความ/Topic ตาม `revision_comparisons.py` เดิม
- Outcome ก่อน-หลังต้อง Target/Feature/Model/Context เดียวกัน และ Inputs ตรวจได้
- ถ้า model/version ต่างกัน ให้ไม่แสดง delta; ถ้าผู้ใช้ขอคำนวณใหม่ใช้บริการ explicit สร้าง comparison snapshot แยก เก็บผลเดิม
- ไม่วิเคราะห์ ASR failure ว่าผู้ใช้ลบทุกหัวข้อ ไม่ถือว่าคะแนนเพิ่มคือคุณภาพคลิป/ยอดวิวเพิ่มจริง

## Tests

1. Unknown/classification-withheld/expired ไม่ได้ Outcome เฉพาะหมวด และไม่มีกฎเดาหมวดทับ
2. Missing context/ASR/error/unqualified/data-use gate ให้ status/null ที่ตรง ไม่มี fake 0%
3. Train/inference Feature parity, repeat-keyword invariance, hash mismatch fail closed
4. Evidence IDs/counts/channel counts/median/time ตรง Fixture จริง รวมผลลบ/ไม่ชัด
5. Scenario validates owner/topic/support, ไม่ mutate input/Transcript และคืน negative/zero delta ได้
6. Activate model คนละรุ่นระหว่างงานไม่ทำให้หนึ่ง Assessment ปะปนสองรุ่น ต้อง pin ครั้งเดียว
7. Save failure/rollback, retry idempotency, legacy parsing, saved result immutability
8. แก้ Dataset/Active model หลัง Save แล้ว GET ไม่เปลี่ยนผลหรือเขียน DB
9. Revision versions mismatch ไม่เทียบค่าต่าง; ASR missing ไม่เป็น content regression
10. ผู้ใช้อื่นเปิด/จำลอง/แก้ผลคนอื่นไม่ได้ และ Logs ไม่มี Private transcript/Secrets

## ส่งมอบ

Inference/evidence integration, additive contracts, snapshot persistence, guarded scenario/revision service, Tests และ `docs/implementation/outcome-prediction-phase-4-handoff.md`

รายงาน Live behavior แยกจาก Qualified-fixture behavior ไม่กล่าวว่าเปิด Prediction production แล้วถ้ายังรอ Phase 6

