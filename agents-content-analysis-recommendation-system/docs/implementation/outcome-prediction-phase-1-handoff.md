# Outcome Prediction Phase 1 Handoff

## สถานะ

- Software / Read-only audit: **ผ่าน**
- Protocol: **ผ่านและถูกตรึงก่อน Train**
- Data rights: **รอยืนยัน / Blocked**
- Data readiness สำหรับ Outcome model: **ไม่ผ่านในข้อมูลปัจจุบัน**
- Prediction / Calibration / Independent test: **ยังไม่เริ่มตามขอบเขต Phase 1**
- Utility evaluation: **ยังไม่เริ่ม**
- คำตัดสิน: **Go เฉพาะ Infrastructure; No-go สำหรับ Train/Serving ด้วยข้อมูลจริง**

ทำเฉพาะ Phase 1 ไม่มีการ Train, Activate, เรียก YouTube API, เปลี่ยน Scheduler, แก้ Dataset/Split/Eligibility หรือเริ่ม Phase 2

## สิ่งที่ทำเสร็จ

1. เพิ่ม Audit CLI แบบมี Cutoff UTC, Output directory และ SQL write guard ซึ่งบล็อก INSERT/UPDATE/DELETE/DDL
2. Audit หนึ่ง Video ID เป็นหนึ่งตัวอย่าง ไม่ใช้จำนวน Snapshot เป็น Sample size และไม่เผยค่า Views ของ Test รายแถว
3. ตรวจ Transcript scope/hash, Video/Channel identity, Format, Published/duration, Observation/status/staleness/metric version, Split/strategy และ Prior Artifact use
4. ตรวจ Duplicate/Cross-split ด้วย Video ID, Channel, Transcript hash และ normalized-text candidate; Semantic duplicate ยังต้องให้คนตรวจ
5. ตรวจ Active Classifier ผ่าน Gate เดิมโดยไม่ต่ออายุ Presentation authorization
6. สร้าง Data-use record ซึ่งอนุญาต Audit แต่บล็อก Training/Serving จนเจ้าของโครงการยืนยันหลักฐาน
7. ล็อก Protocol/Guardrails/ข้อความที่ห้ามอ้าง/งบทรัพยากร/Utility plan ก่อนเห็น Outcome model metrics
8. สร้าง Gap list JSON/CSV ระบุ Dataset ID, Video ID, Protected split, เหตุผล, วิธีแก้, Owner และ Deadline

## ผล Audit ฐานข้อมูลจริง

Cutoff: **2026-10-08 09:39:55 UTC**

Artifact หลัก: [summary.md](../../artifacts/outcome-prediction/phase-1/20261008T093955Z-v2/summary.md)

- Audit SHA-256: 680a53a5e22259442fce4ab1f5157626ed0e641d9dcd101426cac3521697f7ef
- Protocol SHA-256: ef3a7475e2a005b5dda4f9311eec6740570277b82204847a32114d6bdae6e12b
- Database identity ก่อน/หลังตรงกัน: **true**
- Active Phone/Camera/Laptop: **308 แถว = 308 Video IDs, 123 ช่อง**
- หมวด: Phone 109, Camera 101, Laptop 98
- Split เดิม: Train 209, Validation 52, Test 47
- Strategy: classification_diverse 246, recommendation_high_performance 61, ไม่ระบุ 1
- Production contract สำหรับ Classification ผ่าน 245 แถว; Reference eligible ปัจจุบัน 179 แถว
- Transcript ทั้งคลิป 231; first-window/partial 77; ไม่มี Field ยืนยันว่าเนื้อหาเป็นข้อความสรุป จึงไม่เดาจากข้อความ
- Confirmed format: **0/308**; ทุกแถวยังเป็น unknown เพราะ Metadata ไม่มีหลักฐาน Short/Long ตามกฎ
- Statistics 20,171 Observations: complete 18,879, partial 648, failed 644
- มี Successful views Observation 191 Video IDs และอย่างน้อยสองเวลาจริง 191; ไม่มี Observation 117; ล่าสุดเกิน 24 ชม. 13
- Collector ปัจจุบันเรียก reference_transcript_rows() จึงเก็บเฉพาะ Train reference ไม่รองรับ Holdout manifest
- Validation/Test เดิมรวม 99 แถว; 84 แถวมี Explicit prior roles ใน Artifact; Fresh Outcome Test ที่ยืนยันแล้ว **0**
- ไม่พบ Cross-split ใน Channel/Video/Transcript/normalized transcript ของแถว active รอบนี้
- Structurally ready ก่อน Rights/Outcome split: **0**
- Training allowed หลัง Data-use gate: **0**

จำนวนปัญหาหลักซ้อนกันได้ ไม่ควรบวกเพื่อหาจำนวนคลิป:

| ปัญหา | Phone | Camera | Laptop | รวม |
|---|---:|---:|---:|---:|
| Confirmed format ขาด | 109 | 101 | 98 | 308 |
| ไม่มี Observation | 44 | 40 | 33 | 117 |
| Transcript ไม่ใช่ full_video | 37 | 24 | 16 | 77 |
| Production contract ไม่ครบ | 29 | 21 | 13 | 63 |
| Observation ล่าสุดเกิน 24 ชม. | 2 | 0 | 11 | 13 |

ดังนั้น Phase 1 ยังตอบไม่ได้ว่าต้องหา Transcript เพิ่มหมวดละกี่คลิป การเก็บเพิ่มตอนนี้อาจทำซ้ำปัญหาเดิม ต้องแก้/ตรวจ Metadata และสิทธิ์ก่อน แล้ว Phase 2 จึงคำนวณ Coverage ต่อ Category + Format + Age + Channel และระบุ Cell ที่ขาดจริง

## Active Classifier dependency

Active Model #43 โหลด Artifact ได้ แต่ Registry status เป็น presentation_only; Readiness=blocked ด้วย:

- model_not_qualified
- scope_policy_not_validated
- presentation_expired ตั้งแต่ 6 ต.ค. 2026

Outcome model ห้ามทายหมวดแทน และ Phase 1 ไม่ต่ออายุ Presentation bypass ต้องมอบหมาย Workflow Train/Evaluate/Activate ของ Classifier แยกให้ผ่านก่อน Live acceptance

## Data-use dependency

Data-use=unverified; Audit allowed แต่ Real training/serving ถูก Block เพราะไม่มี Confirmation evidence

ดู [Data-use decision](outcome-prediction-data-use-v1.md) เจ้าของโครงการต้องยืนยัน Permission/Amendment/Retention ที่ใช้กับ Project จริง Agent ไม่สามารถยอมรับหรือรับรองแทนได้

License metadata ปัจจุบันมี Standard License 229 และ Creative Commons Attribution 79 แถว แต่ค่านี้ไม่เท่ากับสิทธิ์สร้าง Derived metrics และสิทธิ์ใช้ Transcript ต้องตรวจแยก

## ไฟล์ที่เพิ่ม

- app/services/outcome_prediction_readiness.py
- scripts/audit_outcome_prediction_readiness.py
- tests/test_outcome_prediction_readiness.py
- docs/implementation/outcome-prediction-protocol-v1.json
- docs/implementation/outcome-prediction-protocol-v1.md
- docs/implementation/outcome-prediction-data-use-v1.json
- docs/implementation/outcome-prediction-data-use-v1.md
- docs/implementation/outcome-prediction-phase-1-handoff.md

ไม่มี Migration/Table/Endpoint/UI ใหม่ และไม่มีการแก้ข้อมูลจริง

## Artifact และวิธีตรวจ

Final audit directory:

- artifacts/outcome-prediction/phase-1/20261008T093955Z-v2/readiness.json
- summary.md
- gaps.json
- gaps.csv
- protocol-validation.json
- data-use-decision.json

Directory 20261008T093955Z เป็น Audit รอบแรกก่อนเพิ่ม Global sampling/split gaps จึงถูกแทนที่ด้วย -v2; อย่าใช้เป็นผล Final

คำสั่งรันซ้ำ โดยเปลี่ยน Cutoff และ Output directory ใหม่:

    $env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
    python -X utf8 scripts/audit_outcome_prediction_readiness.py --cutoff 2026-10-08T09:39:55Z --output-dir artifacts/outcome-prediction/phase-1/<new-run-id>

Script ปฏิเสธ Output directory ที่มีอยู่เพื่อไม่เขียนทับหลักฐานเดิม

## หลักฐานทดสอบ

คำสั่ง:

    $env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
    python -X utf8 -m unittest tests.test_outcome_prediction_readiness tests.test_dataset_readiness tests.test_reference_statistics tests.test_classification_readiness tests.test_classification_presentation -q

ผล: **42 tests passed**, 7.771 วินาที

Tests ใหม่ 7 ข้อครอบคลุม:

- Read-only identity ก่อน/หลังและไม่เผย Test outcome value
- Cutoff deterministic และ Observation หลัง Cutoff ไม่ถูกเลือก
- หลาย Snapshot ยังนับหนึ่ง Video และเลือก Latest valid ก่อน Cutoff
- Missing, invalid age, unknown format, transcript hash/scope และ metric mismatch
- Cross-split identity/normalized duplicate candidate
- Protocol missing field และ Data-use unverified/restricted fail closed
- SQL write guard และ Explicit artifact prior-use scan

Real CLI: Exit 0, database_unchanged=true; ไม่ได้รัน Backend/Flutter/Browser เพราะ Phase นี้ไม่มี API/UI change

## งานค้างและ Owner

1. **Project owner, 9 ต.ค.**: ยืนยัน Data-use permission/retention ด้วยหลักฐาน หรือกำหนดว่าจะใช้เฉพาะ Fixture/ข้อมูลที่ได้รับอนุญาต
2. **Dataset admin, 10 ต.ค.**: ตรวจ Short/Long format จากหลักฐานจริง 308 แถว; ห้ามอนุมานจาก Duration เพียงอย่างเดียว
3. **Dataset admin, 10 ต.ค.**: ตรวจ 117 แถวไม่มี Observation, 13 แถว stale, 77 แถวไม่ full transcript และ 63 แถวไม่ผ่าน Production contract จาก gaps.csv
4. **Data engineer, Phase 2**: สร้าง Manifest-driven collector path สำหรับ IDs ที่ได้รับอนุญาต โดยไม่เปลี่ยน Holdout eligibility และไม่เขียน Observation ย้อนเวลา
5. **Evaluation owner, 10 ต.ค.**: กัน Fresh Outcome holdout ก่อนเปิด Outcome; Test เดิมที่มี prior roles คงเป็น Protected regression/development
6. **Model admin, ก่อน Live acceptance**: ทำ Classifier workflow แยก ไม่ต่อ Presentation authorization อัตโนมัติ
7. **Project owner, ก่อน 15 ต.ค.**: นัดผู้ประเมินจริงอย่างน้อย 3 คนและ Freeze Utility protocol ตาม Protocol v1

## ขั้นตอนสำหรับ Phase ถัดไป

ยังไม่เริ่ม Phase 2 จนผู้ใช้มอบหมาย เมื่อเริ่มให้ Agent อ่าน Handoff นี้, Protocol JSON และ Final audit -v2 ก่อน

Phase 2 ทำ Infrastructure ด้วย Fixture ได้หาก Data-use ยัง unverified แต่ห้ามสร้าง/ฝึก/Serve Outcome model จากข้อมูลจริง และห้ามลด Protocol เพื่อให้จำนวนผ่าน

