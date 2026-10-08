# Phase 3: Train, Calibration และตรวจ Candidate

## คำสั่ง

อ่าน README, prediction-contract.md, Protocol และ Handoff Phase 1-2 ตรวจโค้ดก่อนแก้ ทำเฉพาะ Phase 3
Train จริงได้เฉพาะข้อมูล/สิทธิ์ที่ผ่าน Preflight หากยัง Block ให้จบ Software path ด้วย Fixture ที่ติดป้ายชัด
ไม่เปิด Independent Test ไม่ Activate ไม่ฝึก/เปลี่ยน Classifier เดิม ไม่เริ่ม Phase 4

## อ่านก่อน

- `app/services/model_management.py`, `classification_training.py`, `classification_acceptance.py`
- `app/routes/model_management.py`
- `app/database/models.py`, `app/database/migrations.py`
- `tests/test_model_management.py`
- Dataset/Feature/Label builders จาก Phase 2; ตรวจ sklearn version ที่ติดตั้งจริงก่อนใช้ API

Reuse job lifecycle/authorization/artifact conventions ไม่บังคับนำ Outcome ไปใส่ตารางที่มีสัญญาว่าเป็นโมเดลจำแนกหมวด

## งาน

### A. Training pipeline ที่ทำซ้ำได้

- รับ Frozen manifest/protocol ไม่อ่าน Dataset ปัจจุบันเปลี่ยนไปมาระหว่าง Run
- ตรวจ rights/hash/identity split/minimum samples/สองคลาส/support ก่อนเริ่ม
- ล็อก Feature order/scaler/encoder/categorical handling ใน sklearn Pipeline
- Train Constant prior, Metadata-only LR, Metadata+topics LR ด้วย Sample weights/target เดียวกัน
- ใช้ L2 Logistic Regression และ C ตาม Protocol เลือกด้วย Group-aware Tuning เท่านั้น จำกัด Search budget
- CV ต้องสร้าง fit-local benchmark + labels แล้ว Fit preprocessing ใหม่ในทุก Fold; ไม่เรียก cross_val_score กับ y ที่เรียน Median จากทั้งก้อน
- ถ้าใช้ Explicit Fit/Tuning splits ก็ใช้ Threshold ที่เรียนจาก Fit เท่านั้น ไม่แก้ Label ตาม Tuning distribution
- Calibration ใช้ Partition แยกช่องจาก estimator fit และ hyperparameter selection; เริ่ม Sigmoid
- Constant prior, estimator sample weights, calibrator และ Primary evaluation ต้องใช้ Channel-balanced population ตาม Contract เหมือนกัน ไม่ใช้ Prior 50% ตายตัวหรือ calibrate แบบไม่ถ่วงน้ำหนักแล้วอ้างประชากรคนละแบบ
- Final estimator ใช้ Fit partition ที่ระบุไว้ เมื่อเลือก C แล้วห้ามรวม Tuning/Calibration เข้า Fit อัตโนมัติ หากวาง Refit protocol ไว้ต้องสร้าง Calibration อิสระใหม่และ Freeze ก่อนเปิด Test
- ห้าม refit estimator หลัง Fit calibrator แล้วใช้ calibrator เดิมโดยไม่ประเมินใหม่
- Validation ที่ใช้เลือก Candidate ไม่ใช้รายงานแทน Independent Test

บนเครื่องเล็กให้ CPU deterministic ได้ ไม่ดาวน์โหลด LLM/embedding ใหม่ ใช้ Dependencies ที่มีอยู่

### B. Metrics และคำตัดสินที่ตรวจได้

รายงาน Baselines/Candidate ก่อนและหลัง Calibration:
- Brier, Log loss, AUROC/PR-AUC เมื่อคำนวณได้, Calibration bins/counts/gaps
- แยกรายหมวด/Context, Video-weighted/Channel-balanced, Coverage และเหตุผล abstain
- Paired Channel bootstrap CI ของค่าต่าง Brier ใช้กลุ่มเดิมเทียบสองโมเดล
- Class-one/empty fold/degenerate bootstrap เป็นผล not_evaluable ไม่สร้าง 0/1 metrics ให้ดูสมบูรณ์
- แสดง Coefficient table เพื่ออธิบายการทำงาน พร้อมย้ำว่าไม่ใช่ Causal effect
- จำกัดคำว่า improved กับ Metrics/ชุดข้อมูลที่วัดจริง ไม่สรุป Engagement เพิ่ม

ต้องผ่าน Practical margin/Calibration/Scope gates ตาม Protocol ไม่เลือกโมเดลเพราะ Accuracy สูงสุดอย่างเดียว
ผล Phase นี้มากสุดคือ `validation_passed` หรือ `experimental/failed`; Qualification ต้องรอ Phase 6

### C. Artifact และ Outcome registry

Artifact ต้องมี:
- estimator/preprocessor/calibrator, feature order, category/format vocab, frozen benchmarks
- target/protocol/feature/calibration versions และ evaluated scopes
- dataset/split hashes, cutoff/observations provenance, library versions, random seeds
- metrics/plots/exclusions/support policy และ intended population/limitations
- SHA256 integrity และ trusted local storage; ไม่เปิดให้ผู้ใช้อัปโหลด pickle/joblib arbitrary

Registry/Run storage แยกชนิดจาก Classifier มี run_id/status/progress/error/start/end/artifact/metrics/actor
- Single active training slot ตามขอบเขตที่ถูกต้อง; concurrency lock และ restart recovery
- Background job ไม่ค้างอยู่ HTTP request, ป้องกัน orphan/running ตลอดกาล
- Windows helper ใช้ hidden/no-console ตาม Pattern repo ไม่เด้ง Terminal
- Training failed ไม่ทำให้โมเดล Active เดิมหาย
- Prepare API list/detail/preflight/train/status สำหรับ Admin โดยไม่สร้าง Console ใหม่
- เตรียม Activation validation แต่ห้ามเปิด `validation_passed` เป็น Active production หรือมี force=true ข้าม Gate
- Server เป็นผู้ตรวจ qualified/rights/hash/scope ไม่เชื่อ flag ที่ Client ส่งมา

Runtime reload cache ตาม artifact hash/model ID เมื่อเปลี่ยน Active ไม่ใช้ Object เก่าค้าง แต่ไม่มีการ Activate ใน Phase นี้

### D. อธิบายอัลกอริทึมให้ผู้ใช้

เขียนคู่มือสั้นจากผลจริง:
- x = หัวข้อที่ตรวจพบ + metadata/context
- score = intercept + ผลรวม weight ของแต่ละ feature; Logistic แปลงเป็นค่าระหว่าง 0-1
- Calibration ตรวจ/ปรับความสอดคล้องกับสัดส่วนจริงบนข้อมูลที่แยกไว้
- y มาจากยอดวิวจริงเทียบ Train benchmark ไม่ใช่ AI ตั้ง Label เอง
- การเพิ่ม feature ใน Scenario ไม่ใช่หลักฐานว่าการทำจริงทำให้ Views เพิ่ม

ตัวอย่างตัวเลขสมมุติต้องติดป้ายว่าใช้สอนสูตร ไม่ใส่ในผลประเมิน/หน้าเว็บจริง

## Tests

- Leakage tests: เปลี่ยน heldout outcome แล้ว Fit artifacts/choice ไม่เปลี่ยน; CV benchmark/preprocessing fit-local
- Calibration indices ไม่มี Channel/Identity overlap กับ estimator fit; log แสดง split hash
- Pipeline serialize/reload ให้ผลเท่ากัน; checksum/version/feature order mismatch โหลดไม่ผ่าน
- Baselines เห็นชุด/weights/context เดียวกัน; single-class/zero coverage ปลอดภัย
- Bootstrap รักษาจำนวนครั้งที่สุ่ม Channel ซ้ำ ไม่ unique Channels หลังสุ่มจนทำให้ CI ผิด
- Protocol gate failed ทำให้ไม่สามารถ Activate และ probability public ไม่ปรากฏ
- Concurrency, failed job, restart recovery, unauthorized train และ request injection
- Tests ของ Classifier/Model management เดิมยังผ่าน ไม่มีการเปลี่ยน Active classifier
- Mock tests ไม่เรียก paid/network model download ไม่กินโควตาจริง

## ส่งมอบและจุดหยุด

ส่ง Training CLI + Admin APIs ตามจำเป็น, Artifact/Validation report, model card, Tests และ `docs/implementation/outcome-prediction-phase-3-handoff.md`

ภายใน 12 ต.ค. ต้องแจ้งผล Go/Experimental/No-go พร้อมสาเหตุ หากโมเดลไม่เหนือ Metadata-only ให้บอกว่า "ยังไม่มีหลักฐานว่า Features เนื้อหาเพิ่มประโยชน์ต่อการทำนาย" ไม่เพิ่มโมเดลใหญ่/ค้น Hyperparameters ไปเรื่อย ๆ

ระบุว่า Independent Test ยังไม่เปิด ผลจริงยังไม่ใช่โมเดลที่รับรองแล้ว และยังไม่มีความน่าจะเป็นให้ผู้ใช้จริงในฐานะผลผ่านตรวจรับ

