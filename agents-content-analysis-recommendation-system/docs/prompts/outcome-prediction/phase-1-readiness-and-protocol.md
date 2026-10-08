# Phase 1: ตรวจความพร้อมและล็อกการทดลอง

## คำสั่ง

ทำเฉพาะ Outcome Prediction Phase 1 อ่าน README, prediction-contract.md และโค้ดปัจจุบันก่อนแก้ เป้าหมายคือรู้ว่ามีข้อมูลพอทำอะไรได้ และป้องกันการเปลี่ยนความหมาย/เกณฑ์ระหว่าง Train

ยังไม่ Train ไม่ Activate ไม่เพิ่มหน้าจอ ไม่รัน Collector จริงอัตโนมัติ ไม่เริ่ม Phase 2

## อ่านก่อน

- `app/database/models.py`, `app/database/migrations.py`
- `app/services/dataset_eligibility.py`, `dataset_readiness.py`, `reference_statistics.py`, `view_metrics.py`
- `app/services/recommendation.py`, `recommendation_evidence.py`, `topic_comparisons.py`
- `app/services/recommendation_catalog.py`, `actionable_recommendations.py`
- `app/services/classification_acceptance.py`, `model_management.py`
- `docs/implementation/recommendation-phases5-7-review.md`
- `docs/implementation/presentation-model-20261005-handoff.md`
- `docs/implementation/dashboard-simplification-20261007-handoff.md`

ชื่อไฟล์ย่อหลังตัวแรกหมายถึง Directory เดียวกัน ตรวจ Path จริง หากโค้ดใหม่กว่าเอกสารใช้โค้ดจริงเป็นฐานแต่ห้ามละเมิดข้อตกลงกลาง

## งาน

### A. ทำ Read-only audit ที่รันซ้ำได้

สร้าง CLI ตาม Pattern `scripts/` เดิม มี cutoff UTC และ output directory ชัดเจน หลีกเลี่ยง helper ที่ชื่อเหมือน Read แต่สร้าง Config/แก้ DB โดยอัตโนมัติ

รายงาน JSON และ Markdown:
- จำนวน Video/Channel จริง แยกหมวด Split Collection strategy และสิทธิ์ใช้ข้อมูล
- Transcript ครบ/สรุป/ว่าง/ซ้ำ, Hash, Channel/Video identity และ Near-duplicate ที่ต้อง Review
- Published time, duration, format/provenance, statistic timestamp, view metric version
- Latest valid observation ที่เลือกได้ตาม cutoff; missing/failed/stale/counter-definition mismatch แยกกัน
- จำนวนคลิปทั่วไปเทียบข้อมูลที่จงใจเลือกยอดสูง; ยังไม่เรียก Diverse collection ว่าสุ่มแทนประชากร
- จำนวนที่ผ่านทุกเงื่อนไขพร้อมกัน ไม่ใช่นับ Missing ทีละคอลัมน์แล้วบอกว่ารวมพร้อม
- Coverage ตาม Category/Format/Age และการกระจายช่อง ไม่ใช้ Snapshot count แทน sample size
- รายการ Holdout ที่ขาด Outcome, การเคยใช้ปรับระบบ, overlap กับ Train/Reference/Utility study
- ยืนยันพฤติกรรม Collector ปัจจุบันว่าเลือกเฉพาะ Reference Train หรือไม่
- สถานะ Active Classifier/Unknown Gate/การหมดอายุ แยกเป็น Dependency ของ Live Analyze

Data audit อ่านสถิติได้เพื่อดูความพร้อม แต่ยังไม่วิเคราะห์ Test-topic association หรือเลือก Feature/วิธีจากผล Test เก็บ Outcome labels ของ Test ปิดไว้

### B. ตรวจสิทธิ์และขอบเขตการใช้ข้อมูล

อ่านเอกสารทางการ YouTube ล่าสุดที่ README ลิงก์ ตรวจข้อกำหนด Derived metrics, การประยุกต์กับ ML, การยอมรับ Amendment/Approval และ Retention ที่เกี่ยวข้อง อย่าสรุปเองว่าแค่เป็นงานมหาวิทยาลัยได้รับยกเว้น

สร้าง Data-use decision record: source, intended_use, applicable_terms_url, checked_at, confirmation/evidence, owner, status=unverified/confirmed/restricted และเงื่อนไขการเก็บ/ถอนข้อมูล
- ไม่บันทึก confirmed ถ้าไม่มีหลักฐานการยืนยันที่เกี่ยวข้องจริง
- ถ้ายังไม่แน่ใจ แสดง Dependency และขอผู้ใช้ดำเนินการยืนยัน/สอบถามผู้ให้บริการ ไม่ให้ Agent ลงชื่อยอมรับแทน
- ทำ Pipeline ด้วย Fixture หรือข้อมูลที่อนุญาตชัดเจนไปก่อนได้
- ไม่ Scrape/เปลี่ยนแหล่งชื่อเพื่อหลบข้อจำกัด ไม่ลบข้อมูลเดิมโดยพลการ
- ห้ามให้สถานะสิทธิ์ที่ยังไม่ยืนยันหลุดไปเป็น Training/Serving allowed

นี่เป็นการตรวจความพร้อม ไม่ใช่ให้ Agent ออกคำวินิจฉัยทางกฎหมาย

### C. ล็อก Protocol ก่อนดูผลโมเดล

สร้าง `docs/implementation/outcome-prediction-protocol-v1.md` และไฟล์ JSON ที่ Script ตรวจ Schema/Hash ได้ เก็บ Target/Feature/Sampling/Split/Calibration/Qualification policies

ต้องระบุ:
1. เป้าหมาย Views ณ Observation ตาม Contract ไม่ใช่ 7-day forecast
2. Benchmark cells, weighted median, tie handling, cutoff/max staleness และการเลือกบริบทผู้ใช้
3. Sampling frame และ exclusion ของข้อมูลที่เลือกเฉพาะยอดสูงจาก Calibration/Test
4. Identity grouping/Protected split rules และการแบ่ง Fit/Tuning/Calibration/Test
5. Label fit เฉพาะ Fit partition และ inside-CV fit แยกทุก Fold
6. Fit model candidates จำกัด, Random seed, Search budget และหยุดเมื่อไร
7. ขนาดต่ำสุด/Support ของ Category และ Context, การงดทำนาย, Calibration/CI/Baseline gates
8. รายชื่อคำกล่าวที่อนุญาต/ห้ามใช้ พร้อมข้อความ Thai fallback
9. การเก็บ/เข้าถึง/หมดอายุ Artifact และหลักฐานตามสิทธิ์ข้อมูล
10. งบเวลา/หน่วยความจำของ Training และ Inference บนเครื่องจริง; Latency ที่ยอมรับได้และกรณี timeout
11. แผน Utility study ใน Phase 6: Variants, จำนวนกรณี/ผู้ประเมิน, คำถามและเกณฑ์ที่กำหนดก่อนดูคะแนน โดยต้อง Freeze ไม่เกิน 15 ต.ค.

ค่าตั้งต้นเพื่อให้ไม่ต้องตีความเอง:
- Seed 261008; Max staleness 24 ชั่วโมงสำหรับชุดที่ Refresh สถิติได้จริง
- Minimum pipeline-fit: Fit 40 คลิป/8 ช่อง, Tuning 30/5, Calibration 20/5, Independent Test 30/10
- ต้องมีทั้งสอง Label ในแต่ละ Partition; Calibration/Test อย่างน้อย 10 คลิปต่อ Label รวม
- หากจะรับรองหมวดใด Test ของหมวดนั้นอย่างน้อย 10 คลิป/3 ช่องและมีทั้งสอง Label
- Context support ก่อนแสดง Probability: Fit อย่างน้อย 20 คลิป/5 ช่องและอย่างน้อย 5 ต่อ Label ใน cell ที่ใช้
- Train weighting ให้แต่ละ Channel น้ำหนักรวมเท่ากัน ประเมิน Primary แบบ Channel-balanced และรายงานแบบ Video-weighted เพิ่ม
- Candidate Brier ต้องดีกว่า Constant และ Metadata-only อย่างน้อย 0.01 บน Validation; บน Independent Test ให้ดูค่าต่าง/95% paired-channel-bootstrap CI ว่าสนับสนุนทิศทางดีขึ้น ไม่เรียกผ่านหากยังคร่อมศูนย์
- Log loss ต้องไม่แย่กว่า Baseline ที่ดีที่สุดเกิน 0.02; รายหมวดห้าม Brier แย่กว่า Metadata-only เกิน 0.02
- Calibration บน Evaluation ใช้ 3 Quantile bins แบบ tie-stable พร้อมจำนวนจริง แต่ละ Bin ต้องมีอย่างน้อย 10 คลิป/3 ช่อง และ absolute calibration gap ไม่เกิน 0.15; Bin ไม่พอให้ยังไม่ยืนยัน ไม่เลือกตัด Bin ที่ไม่สวยออก
- Bootstrap 2,000 รอบระดับ Channel, 95%, fixed seed; รายงานวิธีและ Degenerate resamples

ตัวเลขเหล่านี้เป็น **Guardrails เริ่มต้นของโปรเจค ไม่ใช่มาตรฐานว่าตัวอย่างเท่านี้เพียงพอเชิงวิจัย** หาก Audit พบทำไม่ได้ ให้เสนอทางเลือก/ผลกระทบก่อนดู Model metrics และขอผู้ใช้ยืนยันการเปลี่ยน Protocol ห้ามลดเกณฑ์เองเพื่อเปิดใช้งาน ความไม่แน่นอน/อคติอาจทำให้ยังไม่ผ่านแม้จำนวนครบ

ห้ามผูกจำนวนนี้กับ "ต้องหา Transcript อีก N" โดยตรง เพราะอาจขาดเพียง Format/Observation/สิทธิ์/ช่องใหม่ ไม่ใช่ Transcript

### D. แผนเก็บส่วนขาดและการตัดสินใจ

ส่งรายการ Actionable gaps เป็น CSV/JSON: row/video ID, split protection, missing field, suggested action, owner และ deadline
แยก:
- ใช้ Transcript เดิมได้ แค่เติม Metadata ที่ตรวจจริงหรือเก็บสถิติตามสิทธิ์
- ต้องเก็บคลิปทั่วไป/ต่างช่องเพิ่ม
- ต้องกันข้อมูลใหม่เป็น Holdout ก่อนใช้
- ต้องขอข้อมูล/สิทธิ์จากเจ้าของโครงการ
- Classifier Live flow ยัง Block และต้องแก้ผ่าน Workflow ของมันแยกต่างหาก

หาก Classifier เดิมยังหมดอายุ/ไม่ผ่าน ให้แยกเป็น Blocking dependency พร้อมเสนอคำสั่ง/ขั้นตอนตรวจรับที่ถูกต้องเพื่อให้ผู้ใช้มอบหมาย ไม่รวมการต่ออายุแบบ Presentation หรือฝึก Classifier ใหม่เข้า Phase นี้เอง ตั้งกำหนดตัดสินใจให้ทันก่อน Live acceptance

ห้ามเปลี่ยน category/split/eligibility/ผลทดสอบย้อนหลังใน Phase นี้

## Tests และเกณฑ์จบ

- Audit read-only จริง ตรวจจำนวน/updated_at หรือ SQL write guard ก่อนหลัง ไม่มี Config ถูกสร้างเงียบ ๆ
- Fixture ครอบคลุม Video ซ้ำหลายแถว/หลาย Observation, missing timestamp, invalid age, Unknown format, protected overlap และ View-version mismatch
- Query cutoff deterministic และเวลา UTC ตรง
- Protocol parse/validate/hash ได้, Missing mandatory keys ทำให้ preflight ไม่ผ่าน
- สิทธิ์ unverified/restricted ไม่ผ่าน Training/Serving gate
- รายงานแยก 308 baseline rows ออกจาก eligible rows พร้อมจำนวนช่องจริง
- ไม่มี Model metrics ที่เอา Test ไปเลือกเกณฑ์

## ส่งมอบ

Audit CLI + tests + machine-readable report, Protocol v1, Data-use decision record, Gap list และ `docs/implementation/outcome-prediction-phase-1-handoff.md`

Handoff ระบุ Go / Go เฉพาะ Software / No-go สำหรับข้อมูลจริง พร้อมสิ่งที่ต้องการจากผู้ใช้ภายใน 9 ต.ค. ไม่ประกาศว่า Phase 1 ผ่านด้านข้อมูลถ้ายังรอข้อมูลหรือสิทธิ์ แต่ทำเครื่องมือที่ไม่ติดให้จบได้

