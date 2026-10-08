# Outcome Prediction Phase 2 Handoff

## สถานะ

- Software / Dataset pipeline: **ผ่านด้วย Automated fixture และ Regression tests**
- Protocol: **ผ่านและไม่เปลี่ยนจาก Phase 1**
- Data rights: **รอยืนยัน / Blocked**
- Real Outcome dataset: **No-go; ไม่ได้สร้าง Frozen training manifest**
- Prediction / Training / Calibration: **ยังไม่เริ่มตามขอบเขต Phase 2**
- Independent Test outcomes: **ยังปิดอยู่**
- Utility evaluation: **ยังไม่เริ่ม**

คำตัดสินคือ **Go เฉพาะ Infrastructure; No-go สำหรับ Phase 3 training ด้วยข้อมูลจริง** จนกว่า Rights, Format, Sampling frame, Observation, Transcript และ Fresh holdout จะผ่านตาม Protocol

ทำเฉพาะ Phase 2 ไม่มีการ Train/Activate model, เรียก YouTube API, เปลี่ยน Dataset split/eligibility, สร้าง Observation ย้อนเวลา หรือเริ่ม Phase 3

## สิ่งที่ทำเสร็จ

1. เพิ่ม Frozen manifest builder หนึ่ง Video ID ต่อหนึ่ง sample พร้อม Source/Transcript/Metadata/Observation provenance และ material-value hash
2. แบ่ง Fit/Tuning ตาม Channel hash แบบ deterministic; รักษา Validation/Test เดิมเป็น Protected และ Block เมื่อ Identity เดียวข้าม partition
3. Independent Test ไม่แสดง Views/Label ใน development manifest และต้องใช้ explicit unlock ใน evaluation ภายหลัง
4. Feature builder ใช้ Catalog/alias detector รุ่นเดียวกับระบบ Recommendation ตรวจทุกหัวข้อ ไม่ใช่เฉพาะ Top 3
5. Topic feature เป็น Boolean; การพูดคำเดิมซ้ำไม่เพิ่ม Feature และ Transcript ที่ตรวจไม่ได้ถูกตัดเป็น `unusable` แทน Vector false ทั้งหมด
6. Feature whitelist ปฏิเสธ Views/Likes/Comments/Growth/Rank/IDs/URL/Title/Classifier confidence
7. Benchmark builder ใช้ Channel-balanced weighted median จาก Fit partition เท่านั้น; Cell ต้องมีอย่างน้อย 20 คลิป, 5 ช่อง และคลาสละ 5 ตาม Protocol, Label ใช้ strict `views > threshold` และไม่มี fallback จาก Validation/Test
8. CV helper สร้าง Benchmark ใหม่จาก Fit fold โดยไม่เห็น Heldout channel และ Unsupported cell งดสร้าง Label
9. เพิ่ม explicit-manifest statistics collector ที่ใช้ API client, lock, quota ledger และ observation tables เดิม มี dry-run, live approval, retry, idempotency และไม่แก้ Dataset eligibility/split
10. เพิ่ม additive migration ให้ `reference_statistics_runs` เก็บ purpose, manifest hash, idempotency key และ split protection โดยไม่ rewrite/delete ประวัติเดิม
11. เพิ่ม CLI สำหรับสร้าง Dataset/blocked report และ CLI เก็บสถิติซึ่ง default เป็น dry-run

## Contract และเวอร์ชัน

- Target: `reference_relative_views_v1`
- Protocol: `reference-relative-views-protocol-v1`
- Protocol SHA-256: `ef3a7475e2a005b5dda4f9311eec6740570277b82204847a32114d6bdae6e12b`
- Manifest schema: `outcome-dataset-manifest-v1`
- Feature schema: `outcome-features-v1`
- Feature schema SHA-256: `19f9054c49378a02333062813ac4056fb264bb7af8633cdb5ed1a984c209536a`
- Catalog: `thai-action-templates-v2-camera-vocabulary`
- Catalog SHA-256: `2fd28a658bee2707ae105a818b55bbae2b6570572b88af0682e8cb0f0c4016a5`
- Split method: `channel-protected-hash-v1`
- Benchmark schema: `outcome-benchmarks-v1`
- Label schema: `outcome-labels-v1`
- Model version: **ไม่มี; Phase 2 ไม่ Train**
- Frozen real Dataset/Manifest SHA-256: **ไม่มี เพราะ Gate ไม่ผ่าน**
- Observation cutoff ที่ตรวจ: `2026-10-08T15:54:09Z`
- Phase 2 report SHA-256: `fb2f881748e5c5aa52824756fbb71f924f227acfef56cdd58139cd202ac7cbb4`
- Database identity SHA-256: `503bb87315bbb8af5abe0ab4d839c5ec3c070d5e68003510fc5d84fd957661c4`

Feature schema อยู่ที่ [outcome-feature-schema-v1.json](outcome-feature-schema-v1.json)

## ผลตรวจข้อมูลจริง

Final artifact: [summary.md](../../artifacts/outcome-prediction/phase-2/20261008T155409Z-v4/summary.md)

- Active Phone/Camera/Laptop: **308 Video IDs จาก 123 ช่อง**
- Phone 109, Camera 101, Laptop 98
- Structurally eligible: **0**
- Training allowed หลัง Rights gate: **0**
- Frozen manifest: **ไม่ได้สร้าง**
- Independent Test outcome associations: **ไม่ได้เปิด**

ปัญหาซ้อนกันได้ จึงห้ามบวกจำนวนเหล่านี้เป็นจำนวนคลิปที่ต้องหาเพิ่ม:

| ปัญหา | Phone | Camera | Laptop | รวม |
|---|---:|---:|---:|---:|
| Confirmed format ขาด | 109 | 101 | 98 | 308 |
| Sampling frame ยังไม่ยืนยัน | 109 | 101 | 98 | 308 |
| ไม่มี Observation | 44 | 40 | 33 | 117 |
| Age context คำนวณไม่ได้เพราะ Outcome ขาด | 44 | 40 | 33 | 117 |
| Transcript ไม่ใช่ full video | 37 | 24 | 16 | 77 |
| Production contract ไม่ครบ | 29 | 21 | 13 | 63 |
| Fresh Outcome Test ไม่ยืนยัน | 11 | 7 | 29 | 47 |
| Outcome-selected clip อยู่ Holdout | 14 | 5 | 12 | 31 |
| Observation เกิน 24 ชั่วโมง | 2 | 0 | 11 | 13 |

ขั้นต่ำที่ยังขาดหลังใช้ทุก Gate คือ Fit 40 videos/8 channels, Tuning 30/5, Calibration 20/5 และ Independent Test 30/10 เนื่องจากยังไม่มีแถวใดผ่านทุกเงื่อนไข จำนวนนี้เป็น **partition minimum deficit** ไม่ใช่คำสั่งให้หา Transcript ใหม่ทันที

ทุก Context cell ที่พบยังมี `confirmed_format=unknown` รายละเอียด Category + Format + Age + View metric อยู่ใน `build-report.json` ไม่มีการรวม Short/Long เพื่อทำให้จำนวนผ่าน

## ไฟล์ที่เพิ่ม/แก้

### เพิ่ม

- `app/services/outcome_dataset.py`
- `app/services/outcome_statistics.py`
- `scripts/build_outcome_dataset.py`
- `scripts/collect_outcome_statistics.py`
- `tests/test_outcome_dataset.py`
- `docs/implementation/outcome-feature-schema-v1.json`
- `docs/implementation/outcome-prediction-phase-2-handoff.md`

### แก้

- `app/database/models.py`: เพิ่ม nullable provenance/idempotency fields ให้รอบเก็บสถิติ
- `app/database/migrations.py`: additive/idempotent migration
- `app/main.py`: เรียก migration ตอน Backend startup
- `app/services/reference_statistics.py`: ส่ง purpose/manifest/split protection ใน run summary
- `app/services/outcome_prediction_readiness.py`: นับแถวด้วย Primary Key เพื่อให้ read-only audit อ่าน pre-migration schema ได้

ไม่มี Endpoint/UI ใหม่ และไม่มี Table ใหม่

## Migration และ Rollback

Migration `migrate_outcome_statistics_schema()` เพิ่ม 4 คอลัมน์และ unique index เท่านั้น ไม่แก้หรือลบแถวเดิม Tests ยืนยันว่ารันซ้ำได้และ Legacy row ยังอยู่

ฐานข้อมูลจริง **ยังไม่ได้รัน Migration ในรอบ Audit นี้** เพื่อรักษา read-only guarantee เมื่อ Backend รุ่นนี้เริ่มทำงานตามปกติ Migration จะเพิ่ม schema ก่อน Collector ถูกใช้

Rollback ที่ปลอดภัยคือย้อน Application code แล้วปล่อย nullable columns ไว้ ห้าม Drop columns/index ในช่วงส่งงาน เพราะการ Drop ไม่จำเป็นและอาจทำลาย provenance ของรอบที่เก็บไปแล้ว

## CLI

สร้างรายงาน/Frozen dataset เมื่อ Gate ผ่าน:

    $env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
    python -X utf8 scripts/build_outcome_dataset.py --cutoff 2026-10-08T15:54:09Z --output-dir artifacts/outcome-prediction/phase-2/<new-run-id>

Dry-run การเก็บสถิติจาก Collection manifest:

    $env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
    python -X utf8 scripts/collect_outcome_statistics.py --manifest <collection-manifest.json>

Live ต้องมี Data-use confirmed, schema migrated และการอนุมัติชัดเจนสองชั้น:

    python -X utf8 scripts/collect_outcome_statistics.py --manifest <collection-manifest.json> --live --approve-live

ห้ามใช้ `--live` กับ Data-use record ปัจจุบัน ระบบจะ Block ก่อนเรียก API/เขียน DB

## หลักฐานทดสอบ

Phase 2 focused tests:

    $env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
    python -X utf8 -m unittest tests.test_outcome_dataset -q

ผลล่าสุด: **13 tests passed**

Related regression:

    $env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
    python -X utf8 -m unittest tests.test_outcome_prediction_readiness tests.test_reference_statistics tests.test_topic_comparisons tests.test_recommendation_evidence tests.test_dataset_readiness tests.test_view_metric_versioning tests.test_classification_readiness -q

ผลล่าสุด: **61 tests passed**

Coverage สำคัญ:

- Duplicate Video/Transcript หนึ่ง sample และ Channel/Identity ไม่ข้าม partition
- Protected split, high-response Holdout exclusion และ Fresh Test gate
- Cutoff/stale/failure/missing/Views=0/negative age/metric-version mismatch
- Manifest/Feature hash deterministic และเปลี่ยนเมื่อ material input เปลี่ยน
- Test Views ไม่เปลี่ยน Fit benchmark/features และ Test labels ถูก sealed
- CV benchmark ไม่เห็น Heldout channel; Unsupported cell abstains
- Topic binary ไม่เพิ่มจากการพูดซ้ำ; ASR/partial transcript ไม่กลายเป็น all-false
- Dry-run ไม่มี API/write; mocked live retry, idempotency, shared daily budget และ quota cooldown
- Data-use unverified block ก่อน API/write และผลลัพธ์ไม่พิมพ์ provider error/secret
- Migration additive/idempotent และไม่ลบ Legacy row

Real CLI: Exit 0, `database_unchanged=true`, `manifest_created=false`

Artifact `20261008T155409Z` เป็นรอบที่หยุดจาก pre-migration ORM compatibility; `-v2` และ `-v3` ถูกแทนที่ระหว่างเพิ่ม coverage และบังคับ Context support minimum ให้ใช้ `20261008T155409Z-v4` เป็น Final เท่านั้น

ไม่ได้รัน Backend/Flutter/Browser เพราะ Phase 2 ไม่มี API/UI change และไม่ได้เรียก Live provider

## งานค้างและ Owner

1. **Project owner, ก่อนเริ่ม Phase 3**: ยืนยัน Data-use permission/retention และ Transcript reuse rights ด้วยหลักฐานที่ใช้กับ Project จริง
2. **Dataset admin**: ตรวจ Short/Long จากหลักฐานจริง 308 แถว ห้ามใช้ Duration เดา Format
3. **Dataset owner**: ยืนยัน sampling-frame provenance ว่าแถวใดมาจาก general protocol หรือ high-response protocol; ห้ามเรียก `classification_diverse` ว่าสุ่มทั่วไปอัตโนมัติ
4. **Data engineer**: หลัง Rights ผ่าน ใช้ Collection manifest เก็บ 117 missing และ 13 stale records โดยไม่เปลี่ยน split/eligibility
5. **Dataset admin**: ตรวจ 77 partial/window transcript และ 63 production-contract gaps; เติมเฉพาะข้อมูลที่ตรวจจริง
6. **Evaluation owner**: กัน Fresh Outcome Test ล่วงหน้าอย่างน้อย 30 videos/10 channels และอย่างน้อยหมวดละ 10 videos/3 channels โดยทั้งสอง Label ต้องเกิดจาก Fit benchmark จริง
7. **Model admin**: แก้ Active Classifier dependency ผ่าน Workflow แยกตาม Phase 1; Outcome model ห้ามทายหมวดแทน

## ข้อจำกัดที่ต้องบอกผู้ใช้/อาจารย์

- Pipeline Software พร้อม แต่ยังไม่มี Outcome model หรือเปอร์เซ็นต์ที่ใช้จริง
- 308 แถวไม่เท่ากับ 308 training samples เพราะทุกแถวยังขาด Gate อย่างน้อยหนึ่งข้อ
- Collection strategy ไม่ใช่ Label และยอดสูงที่ถูกเลือกมาก่อนห้ามเข้า Calibration/Test
- ค่าที่จะทำนายในอนาคตคือโอกาสอยู่เหนือ Fit median ภายในชุดอ้างอิง ไม่ใช่โอกาสที่ทำตามคำแนะนำแล้ว Views เพิ่ม
- Test labels ยังไม่ถูกเปิด และไม่มีการใช้ Test เลือก Feature/Threshold/ข้อความ

## Phase ถัดไป

ยังไม่เริ่ม Phase 3 จนผู้ใช้มอบหมาย Agent ถัดไปต้องอ่าน Handoff นี้, Protocol v1 และ Final artifact `20261008T155409Z-v4` ก่อน

หาก Data-use ยังไม่ยืนยัน Phase 3 ทำได้เฉพาะ Training infrastructure กับ Synthetic fixture ที่ระบุชัด ห้าม Train/Serve จากข้อมูลจริงหรือรายงานว่า Prediction ผ่าน
