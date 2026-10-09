# Outcome Prediction Phase 3 Handoff

วันที่ตรวจล่าสุด: 8 ตุลาคม 2026

## คำตัดสิน

- **Software path: complete สำหรับ Phase 3**
- **Real Outcome training: No-go / blocked**
- **Prediction qualified: false**
- **Independent Test opened: false**
- **Production activation: false**
- **Phase 4: ยังไม่เริ่ม**

ข้อมูลจริงยังฝึกไม่ได้ เพราะ Final Phase 2 artifact `20261008T155409Z-v4` ไม่มี Frozen manifest, มี structurally eligible 0 รายการ และ Data-use record ยังเป็น `unverified` จึงไม่ลดเกณฑ์ ไม่เปลี่ยนข้อมูลขาดเป็นศูนย์ และไม่สร้างโมเดลจริงขึ้นมาแทน

## งานที่เสร็จ

### Training และ Validation

- ตรวจ Frozen manifest/protocol/data-use/hash/schema/feature hash/identity split/จำนวนขั้นต่ำ/สอง Label ก่อน Fit
- ใช้ sklearn Pipeline ล็อก preprocessing และ feature order
- ฝึก Constant prior, Metadata-only Logistic Regression และ Metadata+topics Logistic Regression ด้วย channel-balanced weights เดียวกัน
- Candidate ใช้ L2 และ `C = 0.1, 1, 10`; เลือกจาก explicit Channel-disjoint Tuning partition โดย benchmark และ labels เรียนจาก Fit เท่านั้น ไม่ใช้ CV/y ที่คำนวณจากข้อมูลรวม
- Fit weighted sigmoid calibrator จาก Calibration partition แยก และไม่ refit estimator หลัง Calibration
- Independent Test records ไม่มี Views ใน public manifest และ Phase 3 ไม่คำนวณ Test metrics
- รายงาน Brier, Log loss, AUROC, PR-AUC, calibration bins, overall/category/format/age context, channel/video weighting, coverage และ paired channel bootstrap
- Degenerate/single-class/insufficient-channel cases แสดง `not_evaluable` หรือ `partially_evaluable` ไม่สร้างเลข 0/1 หลอก
- สร้าง coefficients พร้อมคำเตือน association ไม่ใช่ causal effect

### Artifact และ Registry

- Artifact เก็บ estimator/preprocessor/calibrator, feature order, vocabulary, benchmark, versions, split hashes, cutoff, population, limitations และ library versions
- ตรวจ SHA-256, trusted local path, artifact schema, protocol, feature schema และ feature order ตอนโหลด
- เพิ่มตารางแยก `outcome_training_runs`, `outcome_models`, `outcome_model_metrics`; ไม่ใส่ Outcome เข้า Classification registry
- เพิ่ม Admin API `/admin/outcome-training`: preflight, list/detail runs, start run และ list/detail models
- Request รับเฉพาะ Manifest SHA-256; client ส่ง path, force หรือ threshold ไม่ได้
- Background worker มี single active slot, heartbeat, stale recovery, durable failure และ `CREATE_NO_WINDOW` บน Windows
- ไม่มี Activation endpoint ใน Phase 3 และ Backend gate ยืนยันว่า `validation_passed` ยัง Activate ไม่ได้
- Classification model ที่ Active อยู่ไม่ถูกเปลี่ยนทั้งกรณี Outcome สำเร็จและล้มเหลว

### คู่มือ

- [อธิบายอัลกอริทึม Phase 3](outcome-prediction-phase-3-algorithm.md)
- Model card ใน artifact อธิบาย `x`, Logistic score, sigmoid, Calibration, ที่มาของ `y` และข้อห้ามด้าน causal claim

## หลักฐานรันจริง

### Real preflight

Artifact: `artifacts/outcome-prediction/phase-3/20261008T-phase3-real-preflight/preflight-report.json`

- status: `blocked`
- Phase 2 status: `blocked_data_use`
- reason: `phase2_frozen_manifest_missing`
- artifact created: false
- Independent Test opened: false
- production eligible: false

### Synthetic software fixture

Artifact root: `artifacts/outcome-prediction/phase-3/20261008T-phase3-synthetic-validation`

- status: `fixture_validation_passed`
- Fit 60 videos / 15 channels / Labels 30:30
- Tuning 30 / 15 / Labels 15:15
- Calibration 36 / 18 / Labels 18:18
- Sealed Independent Test 30 / 15; ไม่มี Test labels/metrics ใน Phase 3
- selected C: 10
- Candidate Tuning channel-balanced Brier: 0.0147565
- Metadata-only Tuning channel-balanced Brier: 0.25
- Calibration 3 bins ผ่านค่าคลาดเคลื่อนที่ล็อกไว้
- runtime ประมาณ 0.875 วินาที ภายใต้งบ 30 นาที
- qualified: false, production eligible: false, active model changed: false

ผลข้างต้นพิสูจน์เฉพาะ software path เพราะ fixture ถูกสร้างให้ Topic สัมพันธ์กับ Label ห้ามใช้อ้างว่าโมเดลจริงแม่นหรือคำแนะนำทำให้ยอดวิวเพิ่ม

ไฟล์หลักใน fixture model:

- `model.joblib`
- `validation-report.json`
- `calibration-plot-data.json`
- `coefficients.json`
- `integrity.json`
- `model-card.md`

## หลักฐานทดสอบ

Focused Phase 3:

```powershell
$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
python -X utf8 -m unittest tests.test_outcome_training tests.test_outcome_model_management -v
```

ผล: **12 tests passed**

Outcome Phase 1-3 + Model management regression:

```powershell
$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
python -X utf8 -m unittest tests.test_outcome_training tests.test_outcome_model_management tests.test_model_management tests.test_outcome_dataset tests.test_outcome_prediction_readiness -q
```

ผล: **45 tests passed** ใน 79.219 วินาที

Coverage สำคัญ:

- เปลี่ยน Independent Test outcomes แล้ว C และ fitted coefficients ไม่เปลี่ยน
- Fit/Tuning/Calibration/Test ไม่มี Channel overlap และ split hashes ถูกเก็บ
- serialize/reload ให้ prediction เท่ากัน; checksum/protocol/feature hash/order ผิดแล้วโหลดไม่ผ่าน
- Baselines ใช้จำนวนแถวและ channel weighting เดียวกัน
- single-class, insufficient channels และ degenerate bootstrap ไม่สร้าง metrics หลอก
- bootstrap รักษา Channel ที่สุ่มซ้ำ
- `validation_passed` Activate ไม่ได้และไม่มี force override
- single-slot concurrency, launch failure, stale recovery และ durable worker failure
- unauthorized/non-admin ถูกปฏิเสธ; extra path/force fields ถูกปฏิเสธ
- Outcome failure/completion ไม่เปลี่ยน Active classifier เดิม
- Tests ไม่เรียกเครือข่าย, paid API หรือดาวน์โหลดโมเดล

## งานค้างและ Owner

1. **Project owner:** ยืนยันสิทธิ์ใช้ Transcript และ YouTube-derived metrics สำหรับ training/serving พร้อมหลักฐานและ retention ใน Data-use record
2. **Dataset admin/data engineer:** แก้ Phase 2 gaps ให้มี Frozen real manifest ที่ผ่าน Fit/Tuning/Calibration/Test minimums และ Context support เดิม โดยไม่ย้าย protected rows หรือลดเกณฑ์
3. **Model admin:** เมื่อข้อ 1-2 ผ่าน ให้เริ่ม Run ใหม่ผ่าน Manifest hash; ห้ามนำ fixture artifact ไปลง Production
4. **Phase 6 เท่านั้น:** เปิด Independent Test หนึ่งครั้งหลัง Freeze Candidate/Protocol เพื่อพิจารณา `qualified`
5. **Phase ถัดไป:** การเชื่อม probability/scenario กับผลวิเคราะห์ผู้ใช้เป็น Phase 4 และยังไม่ได้เริ่มตามคำสั่งหยุด

## Rollback

ตารางใหม่เป็น additive และ `Base.metadata.create_all` สร้างเฉพาะตารางที่ขาด ไม่มีการแก้ข้อมูล Classification เดิม หาก rollback application ให้ถอด Outcome router/service ได้โดยปล่อยตารางประวัติไว้ ห้ามลบ artifact หรือ drop ตารางก่อนเก็บหลักฐานส่งงาน
