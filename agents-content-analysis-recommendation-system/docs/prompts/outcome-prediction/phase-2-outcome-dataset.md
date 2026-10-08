# Phase 2: สร้างชุดข้อมูล Outcome ที่ทำซ้ำได้

## คำสั่ง

อ่าน README, prediction-contract.md, Protocol ที่ Freeze แล้ว และ Handoff Phase 1 ตรวจโค้ดจริง ทำเฉพาะ Phase 2 ไม่ Train/Activate/เปิด Test เพื่อเลือกวิธี และไม่เริ่ม Phase 3

หาก Protocol/สิทธิ์ยังไม่ผ่าน ให้ทำเฉพาะ Infrastructure/Fixture และรายงาน Block ห้ามแต่ง Dataset จริงให้ดูพร้อม

## อ่านก่อน

- `app/services/dataset_eligibility.py`, `reference_statistics.py`, `view_metrics.py`
- `app/services/recommendation_evidence.py`, `recommendation_catalog.py`, `topic_comparisons.py`
- `app/database/models.py`, `app/database/migrations.py`
- `tests/test_reference_statistics.py`, `test_topic_comparisons.py`, `test_recommendation_evidence.py`
- Audit CLI/Protocol จาก Phase 1 และ Script import/export ของโปรเจค

## งาน

### A. Manifest แยกบทบาท ไม่เปลี่ยนชุดเดิม

เพิ่มบริการ/CLI สำหรับสร้าง Frozen outcome dataset:
- Manifest อ้างอิง Dataset/Video/Channel IDs, Source/Transcript hash, Approved category, Metadata provenance, Observation IDs/time/version, selected cutoff, collection strategy, sampling frame และสิทธิ์
- หนึ่งแถวต่อ Video ID ตัดซ้ำแบบ deterministic เก็บรายการ excluded พร้อมเหตุผล ไม่ลบแถวต้นทาง
- Split เป็น Fit/Tuning/Calibration/Test ตามกลุ่มช่องและ Identity overlap ที่ตรวจจริง
- รักษา Protected split เดิม ถ้าขัดกันให้ Block/Exclude ไม่แก้ Split ต้นทาง
- Test manifest แยกการเข้าถึง Outcome labels; Development report แสดงจำนวนได้ ไม่เผย Association ของ Test
- บันทึกคำตอบว่าแต่ละ Video เคยอยู่ Classifier training/reference/bug regression/utility test หรือไม่ ไม่เรียก "Fresh" เพียงเพราะเพิ่งสร้าง Manifest
- Hash ครอบคลุมค่าที่มีผลจริง ไม่ใช่เฉพาะ Dataset IDs; Transcript/metadata/observation/policy เปลี่ยนต้อง Manifest ใหม่

ไม่ใช้ชื่อคลิปเป็น unique ID ไม่แบ่งสุ่มแถวหลัง join กับ Observation

### B. เติมสถิติที่ขาดโดยไม่ทำ Transcript ใหม่

ตรวจ Collector เดิมก่อน ถ้ามันเลือกเฉพาะ Reference Train ให้เพิ่มเส้นทางเก็บแบบ explicit Manifest IDs สำหรับ Outcome workflow:
- Reuse API client, batching, quota/retry/logging และ lock ของเดิม
- ยืนยัน URL/Video ID และสิทธิ์ก่อนเรียก
- Dry-run แสดงจำนวน requests และรายการที่จะเก็บ; รัน Live เมื่อผู้ใช้อนุมัติและ Data-use gate ผ่าน
- ไม่เปลี่ยน `keyword_eligible`, `training_eligible` หรือ data_split ของ Validation/Test เพื่อให้ Collector มองเห็น
- Storage ต้องคง provenance และ purpose/split protection; ห้าม Observation ของ Holdout ทำให้มันกลายเป็น Reference โดย join อ้อม
- ถ้าใช้ตารางเดิมได้ ให้เพิ่มเฉพาะ fields/purpose ที่จำเป็นตาม Migration เดิม อย่าสร้าง Collector อีกตัววิ่งทุกชั่วโมงเอง
- Failure/partial record อยู่ในประวัติ แต่ไม่ใช้สร้าง Label ที่ขาด Views
- Idempotent retry, no duplicate run observations, request budget รวมกับงานที่มีอยู่
- เวลาที่เก็บคือเวลาจริง ไม่เขียน Observation ใหม่ย้อนวันที่เพื่อสร้างยอดวันเก่า

การอ่าน Manifest/Audit ห้ามเรียก API หรือเปลี่ยน DB โดยไม่แจ้ง

### C. Features มาจากข้อความจริง

สร้าง Feature builder บริการเดียวใช้ทั้ง Train และ Inference:
- รับ Transcript/Canonical catalog version/category/confirmed format/duration/context
- สกัดทุกหัวข้อใน Catalog ของขอบเขต ไม่ใช่เฉพาะ Top-3 คำแนะนำหรือเฉพาะหัวข้อที่ขาด
- Boolean presence พร้อม evidence pointer/excerpt และ Timestamp เฉพาะมีจริง
- ASR/Transcript ไม่พอประเมิน -> unusable พร้อม reason ไม่สร้าง Vector false ทั้งหมด
- การเพิ่มคำเดิมซ้ำอย่างเดียวต้องไม่เพิ่มค่า Feature binary หรือเกิด "โบนัสยอดวิว"
- Alias/case/ภาษาไทยให้ตรง Detector ปัจจุบัน ไม่แตกชุดคำพ้องใหม่เงียบ ๆ
- สร้าง whitelist Features ตาม Contract ตรวจ reject ถ้ามี views/likes/rank/IDs หรือข้อมูลอนาคตปะปน

Structured metadata ไม่สกัดด้วย Regex ถ้ามี Parser/Schema เดิมรองรับ

### D. Benchmark/Label builder ต้องใช้ Fit partition

ทำ API ชัดเจน เช่น fit_benchmarks(fit_records, protocol), label_records(records, frozen_benchmarks)
- Channel-balanced weighted median ต่อ cell และ strict views > median
- ไม่มี fallback เอา Median ของ Validation/Test เมื่อ Cell ไม่มีใน Fit
- ใช้ cell version/threshold/source IDs/hash; report label counts/ties/unsupported cell
- ส่ง raw observation records ไปขั้น CV เพื่อ Fit benchmark ใหม่ในแต่ละ Fold ไม่ส่ง y จาก Full Train ไปให้ sklearn CV แบบทั่วไป
- Bootstrap หรือ CV ที่ทำ Model selection ห้ามใช้ Label threshold ที่เห็น Heldout outcome ไปแล้ว
- ไฟล์ Label ของ Independent Test ต้องปลดใช้ผ่าน explicit evaluation command ใน Phase 6 เท่านั้น

ไม่สร้าง Sample เพิ่มด้วยทุก Observation หรือ Oversampling เพื่อรายงานจำนวน Dataset ให้มากขึ้น

## Tests

เพิ่มชุดทดสอบตาม Pattern เดิม ชื่อเช่น `tests/test_outcome_dataset.py`:
1. Duplicate Video/Transcript/channel identity ไม่ข้าม Split และหนึ่ง Video เป็นหนึ่ง sample
2. Protected Holdout/reference exclusion และ collector path ของ Holdout ไม่เปลี่ยน eligibility
3. Observation หลัง cutoff, stale, failure, missing Views, negative age ถูกตัดพร้อมเหตุผล; Views=0 ไม่หาย
4. Published/observed timestamps และ View metric version ไม่ปะปน
5. Same input/protocol ได้ Manifest/Feature/Label hash เดิม
6. เปลี่ยน Transcript/Observation ที่เลือก/Protocol แล้ว Hash เปลี่ยน
7. เปลี่ยน Validation/Test views ไม่ทำให้ Fit benchmarks/scaler/features เปลี่ยน
8. CV fold benchmark ไม่เห็น heldout fold และ Unsupported cell ไม่สร้าง label เดา
9. พูดคำเดิมซ้ำไม่เพิ่ม Topic feature, ASR fail ไม่เท่ากับ not_detected
10. Dry-run ไม่มี writes/API; Live retries/idempotency/quota budget ถูกต้องด้วย mocked client
11. Data-use gate บล็อกจริงและไม่พิมพ์ Secrets
12. Migration additive และ rollback ไม่ลบข้อมูลเดิม

## เกณฑ์จบ / ส่งมอบ

มี Manifest ที่ Frozen และตรวจย้อนกลับได้จริง หรือมี Pipeline พร้อมพร้อมรายงานว่าข้อมูลจริงยัง Block ไม่รายงานสองอย่างนี้เหมือนกัน

ส่ง CLI usage ด้วยคำสั่งจริงที่รันได้ใน Environment นี้, Feature schema, Manifest/Exclusion report, Tests, Migration ถ้ามี และ `docs/implementation/outcome-prediction-phase-2-handoff.md`

สรุปจำนวน Independent videos/channels/สองคลาส แยกทุก Partition และจำนวนที่ขาด ไม่ใช้ Snapshot count; แจ้งความเสี่ยงภายใน 10 ต.ค. ห้ามเดินหน้า Train จริงถ้า Rights/Protocol/Data gates ยังไม่ผ่าน

