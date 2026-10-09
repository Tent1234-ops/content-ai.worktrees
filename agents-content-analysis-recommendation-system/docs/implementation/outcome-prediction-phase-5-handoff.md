# Outcome Prediction Phase 5 Handoff

วันที่ตรวจล่าสุด: 9 ตุลาคม 2026

## คำตัดสิน

| ด้าน | สถานะ | หลักฐาน/เหตุผล |
|---|---|---|
| Phase 5 software | **complete** | Result, History, Revision comparison และ Admin model management เชื่อม API จริง มี tests และ Browser verification ครบ 3 viewport |
| Data rights | **blocked** | `confirmation_evidence_missing`, `data_use_unverified` |
| Outcome data | **blocked** | แถวต้นทาง 308, ผ่านโครงสร้าง 0, อนุญาตฝึก 0 และยังไม่มี Frozen manifest ที่ผ่านเกณฑ์ |
| Prediction qualified | **false** | Outcome models 0, Active model ไม่มี, Independent Test ยังไม่เปิด |
| Utility evaluated | **false** | ตรึง protocol แล้ว แต่ยังไม่เริ่มเก็บ Human ratings |
| Engagement uplift proven | **out of scope / false** | ระบบประเมินการอยู่เหนือค่ากลางของชุดอ้างอิง ไม่ใช่ผลเชิงเหตุว่าทำตามแล้ววิวเพิ่ม |

Phase 5 ทำเส้นทางซอฟต์แวร์เสร็จโดยไม่ลด Gate และไม่แต่งข้อมูลจริง หน้า Live จึงแสดงสาเหตุที่ยังเทรนไม่ได้และไม่แสดง Probability ปลอม ส่วนหน้าจอที่มีค่า `62.0%` ในหลักฐาน Browser เป็น **Synthetic fixture สำหรับตรวจ UI เท่านั้น** และไม่ได้เขียนลง Production database

## งานที่เสร็จ

### Result, History และ Revision

- เพิ่ม Outcome block หลังส่วนคำแนะนำในลำดับ “พบอะไร -> ควรเพิ่มอะไร -> เพราะอะไร”
- แสดง Probability เฉพาะ `status=available` และค่าต้องอยู่ในช่วง 0-1 โดยใช้ข้อความ “โอกาสอยู่ในกลุ่มยอดวิวสูงกว่าค่ากลางของชุดอ้างอิง”
- แสดงหมวด รูปแบบคลิป ช่วงอายุ จำนวนคลิปอิสระ จำนวนช่อง และข้อจำกัดติดกับค่าประเมิน ไม่รวมกับ Classification confidence
- Status ที่ไม่มีผลประเมินแสดงข้อความไทยเฉพาะสาเหตุ ไม่มีการแทน Missing ด้วย `0%`
- Scenario เป็นส่วนรอง ติดป้ายสถานการณ์สมมุติ ใช้ Snapshot/fingerprint จาก Server และรักษา Delta แบบติดลบ ศูนย์ และบวกในหน่วยจุดเปอร์เซ็นต์
- History เปิดผลเก่าได้ด้วยข้อความ “ผลนี้ยังไม่มีการประเมินผลตอบรับ” และไม่คำนวณย้อนหลังใน Client
- Revision แยกการเปลี่ยนเนื้อหาจาก Outcome; รุ่นโมเดล/บริบทต่างกันแสดง “เทียบค่าประเมินโดยตรงไม่ได้” โดยไม่มีลูกศรสรุปว่าดีขึ้น
- เพิ่ม semantics ของ Scenario ให้ข้อความก่อน/หลังและ Delta เข้าถึงได้บน Flutter Web

### Admin model management

- แยกแท็บ “จำแนกหมวด” และ “ประเมินผลตอบรับ” ในหน้าฝึกโมเดลเดิม
- `GET /admin/outcome-training` รวม Preflight, durable run history, models และ Active model จากฐานข้อมูล
- แสดงสิทธิ์ข้อมูล จำนวนแถวต้นทาง จำนวนที่ผ่านโครงสร้าง และจำนวนที่อนุญาตฝึกตาม API โดยไม่ hard-code หรือเรียกจำนวนแถวว่าเป็นจำนวนวิดีโอ/ช่อง
- เริ่ม Train ผ่าน background job เดิมได้เฉพาะเมื่อ Preflight ผ่าน และติดตามสถานะจาก Server หลัง refresh
- Model detail แยก Baseline/Candidate, Validation/Independent Test, Calibration, Coverage, partition counts, versions และ hashes
- `POST /admin/outcome-training/models/{model_id}/activate` ทำ optimistic active-model check และ lock ก่อนเปลี่ยนค่าแบบ atomic
- Server ปฏิเสธ Synthetic fixture, โมเดลไม่ผ่าน Independent Test, production ineligible, artifact หาย/hash ไม่ครบ, split hash ไม่ครบ และ evaluated scopes ไม่ครบ
- Activate/Rollback ต้องยืนยันใน UI และแสดงสำเร็จหลัง Server ตอบสำเร็จเท่านั้น ไม่มี Force qualify/threshold override
- หน้า Dataset ระบุว่า Protected split แก้ตรง ๆ ไม่ได้ และชี้ให้ตรวจ Outcome role/readiness ผ่าน Manifest/หน้าฝึก โดยไม่เพิ่มแท็บที่เคยตัดออกกลับมา

### Contract freeze

- ตรึง UI contract ที่ `docs/implementation/outcome-prediction-ui-contract-v1.json`
- ตรึง Utility study protocol ที่ `docs/implementation/outcome-prediction-utility-study-v1.json`
- บันทึก Freeze decision ที่ `docs/implementation/outcome-prediction-phase-5-freeze.json`
- Candidate จริงถูกบันทึกเป็น `blocked_no_real_candidate`; ไม่เปิด Independent Test และไม่เริ่ม Human study

## ไฟล์สำคัญ

Backend:

- `app/routes/outcome_model_management.py`
- `app/services/outcome_model_management.py`
- `tests/test_outcome_model_management.py`

Flutter:

- `frontend_flutter/lib/models/outcome_prediction.dart`
- `frontend_flutter/lib/models/outcome_model_training.dart`
- `frontend_flutter/lib/widgets/outcome_assessment_panel.dart`
- `frontend_flutter/lib/widgets/outcome_training_panel.dart`
- `frontend_flutter/lib/widgets/revision_comparison_panel.dart`
- `frontend_flutter/lib/screens/result_screen.dart`
- `frontend_flutter/lib/screens/history_screen.dart`
- `frontend_flutter/lib/screens/admin_training_screen.dart`
- `frontend_flutter/lib/screens/admin_datasets_screen.dart`
- `frontend_flutter/lib/repositories/content_repository.dart`
- `frontend_flutter/lib/repositories/admin_repository.dart`
- `frontend_flutter/test/outcome_prediction_test.dart`
- `frontend_flutter/test/outcome_admin_training_test.dart`
- `frontend_flutter/test/revision_comparison_test.dart`

Browser proof:

- `scripts/browser/verify_outcome_phase5.cjs`
- `artifacts/outcome-prediction/phase-5/20261009T113653Z-browser/verification.json`

## Tables, Endpoints และ Migration

ใช้ตารางเดิม: `outcome_training_runs`, `outcome_models`, `outcome_model_metrics`, `system_configs`, `system_logs` และ Outcome snapshot ใน JSON ของ `analysis_results`

Endpoints ที่เพิ่มใน Phase 5:

- `GET /admin/outcome-training`
- `POST /admin/outcome-training/models/{model_id}/activate`

Endpoints เดิมที่ UI นำมาใช้ต่อ:

- `POST /admin/outcome-training/runs`
- `GET /admin/outcome-training/runs/{run_id}`
- `GET /admin/outcome-training/models/{model_id}`
- `GET /contents/my`
- `GET /contents/{content_id}`
- `POST /contents/{content_id}/outcome-scenario`
- `GET/PUT /contents/{content_id}/revision-plan`

Migration: **ไม่มี** Phase 5 ใช้ schema และ durable registry จาก Phase 3-4

## Versions และ SHA256

- Target: `reference_relative_views_v1`
- Protocol: `reference-relative-views-protocol-v1`
- Protocol declared SHA256: `ef3a7475e2a005b5dda4f9311eec6740570277b82204847a32114d6bdae6e12b`
- Feature version: `outcome-features-v1`
- UI contract file SHA256: `8d2b8a4d29c70a66ddf55a564ba036e345d8c347553e21c84de95a2670216129`
- Utility protocol file SHA256: `4bd100f286c84d3087a0eb3405b0b108a43b4de1df77c0e33db92a03b8dd23ec`
- Phase 5 freeze file SHA256: `fd6309f188a74338688a008a7423b280bccb926486c44f9250b16a5c9f0900e4`
- Model version/hash: ไม่มี Candidate จริง
- Dataset/Manifest/Split hashes: ไม่มี Frozen manifest ที่ผ่านเกณฑ์
- Observation cutoff: ไม่มี เพราะยังสร้าง Outcome dataset จริงไม่ได้

หมายเหตุ: SHA256 ของ Markdown `prediction-contract.md` ไม่ใช่ Protocol declared hash; Protocol ที่ canonical อยู่ใน `docs/implementation/outcome-prediction-protocol-v1.json`

## หลักฐานทดสอบ

### Backend

```powershell
$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
py -m unittest tests.test_outcome_model_management tests.test_outcome_inference -q
```

ผล: **12 tests passed**, exit code 0

```powershell
$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
py -m compileall -q app tests
py -m unittest discover -s tests -q
```

ผล: **556 tests passed** ใน 80.351 วินาที, exit code 0 มีเพียง warning จาก dependency ภายนอกและข้อความ failure ที่ test ตั้งใจจำลอง

### Flutter

```powershell
flutter analyze --no-pub
flutter test --no-pub
flutter build web --release --no-pub
```

ผล:

- Analyze: **No issues found**, exit code 0
- Full suite: **164 tests passed**, exit code 0
- Focused Outcome test หลังแก้ semantics: **19 tests passed**, exit code 0
- Web release build: สำเร็จ, exit code 0
- Build มี warning เดิมว่าไม่ได้ bundle CupertinoIcons; Material Icons ที่ใช้ถูก bundle และ Browser proof ไม่มี icon/layout error

Tests ครอบคลุม backward parser, unknown status, ทุก no-result status, null probability, long Thai text, negative/zero/positive Delta, Server failure ไม่แจ้งสำเร็จ, role guard, disabled Train, activation rejection, immutable snapshot/legacy result, active-model switch, revision mismatch และ responsive layout

### Browser: Live กับ Fixture แยกกัน

คำสั่ง:

```powershell
node scripts/browser/verify_outcome_phase5.cjs artifacts/outcome-prediction/phase-5/20261009T113653Z-browser
```

ผล: `passed=true`, **12 screenshots**, Browser errors 0, exit code 0

- Viewports: 1440x900, 1000x800, 390x844
- Live Admin ใช้ API/DB จริง แสดง Train blocked จากข้อมูล 308/0/0 และปุ่ม Train disabled
- Live activation rejection ใช้ Endpoint จริงกับ model ID ที่ไม่มีอยู่ ได้ HTTP 404 และไม่มี model mutation
- Qualified Result/Scenario ใช้ Synthetic intercepted payload ที่ติดป้ายชัด ไม่เขียน DB
- Scenario แสดง `62.0% -> 59.5%` และ `-2.5 จุดเปอร์เซ็นต์` โดยไม่แสดงว่าเป็นยอดวิวที่จะเพิ่ม
- `documentWidth` เท่ากับ viewport ทุกภาพ; `bodyWidth` ต่าง 11px เฉพาะหน้าที่มี vertical scrollbar และไม่มี horizontal document overflow

หลักฐานหลัก:

- `live-admin-blocked-{1440x900,1000x800,390x844}.png`
- `fixture-history-{1440x900,1000x800,390x844}.png`
- `fixture-result-available-{1440x900,1000x800,390x844}.png`
- `fixture-scenario-negative-{1440x900,1000x800,390x844}.png`
- Aria snapshots ชื่อเดียวกันนามสกุล `.txt`
- Request/status/layout log ใน `verification.json`

Human evidence: **ไม่มีและไม่ได้เริ่ม** AI/Widget/Browser tests ไม่นับเป็น Human utility rating

## Live Behavior และ URL

- Web: `http://127.0.0.1:8080`
- API docs: `http://127.0.0.1:8000/docs`
- Server ถูกเปิดแบบหน้าต่างซ่อนเพื่อไม่รบกวน fullscreen
- Outcome probability จริงยังไม่แสดงจนกว่าสิทธิ์ข้อมูล, Frozen manifest, Validation, Independent Test และ Activation จะผ่านครบ

## ข้อมูล/บัญชีทดสอบและ Rollback

- Browser harness สร้าง session ชั่วคราวด้วย helper เดิมและ logout ใน `finally`; ไม่บันทึก token/password ลง Artifact
- ไม่มี Train run จริง, ไม่มีการเปิด Independent Test, ไม่มี Activate model และไม่มีการแก้ Dataset จริงใน Phase นี้
- Request activation สำหรับ ID ที่ไม่มีอยู่คืน 404 ก่อน mutation
- Backend activation tests ใช้ฐานข้อมูลและ artifact ชั่วคราว
- ไม่มี migration ให้ rollback หากย้อน application ให้คง Outcome snapshot/registry เดิมไว้ รุ่นเก่าสามารถเพิกเฉย field เพิ่มได้
- การ rollback Active model ในอนาคตต้องใช้ Endpoint เดิมและ `expected_active_model_id`; ห้ามแก้ flag หลายแถวด้วยมือ

## งานค้างและ Owner

1. **Project owner:** ยืนยันสิทธิ์ใช้ Transcript และ YouTube-derived metrics สำหรับ Training/Serving พร้อมหลักฐานและ retention policy
2. **Dataset admin:** แก้ข้อมูลให้ผ่าน structural/data-use Gate และสร้าง Frozen manifest โดยไม่ย้าย Protected split หรือลดขั้นต่ำ
3. **Outcome model owner:** เมื่อข้อมูลพร้อมจึง Train Candidate จริงและตรวจ Validation ตาม Protocol; ห้ามใช้ Fixture เป็น Candidate
4. **Phase 6 เท่านั้น:** Freeze Candidate จริงก่อนเปิด Independent Test แล้วรายงานผลบวก/ลบตามจริง
5. **Human evaluators:** หลัง Variant C ผ่าน Gate จึงใช้ผู้ประเมินจริงอย่างน้อย 3 คนตาม Utility protocol; ถ้ายังไม่ผ่านให้บันทึก Variant C ว่า unavailable ห้ามแทนด้วยตัวเลขสังเคราะห์

## ข้อจำกัดที่ต้องแจ้งตอนพรีเซนต์

- ค่า Outcome ไม่ใช่การรับประกันยอดวิว ไม่ใช่ “เพิ่มยอดวิว X%” และไม่ใช่ Classification confidence
- รุ่นนี้ตอบโอกาสอยู่เหนือค่ากลางของชุดอ้างอิง ณ เวลาสังเกต ภายใต้บริบทที่ระบุเท่านั้น
- Scenario เปลี่ยน Feature ในสำเนาข้อมูลเพื่อดูความต่างของค่าประเมิน ไม่ได้พิสูจน์ว่าผู้ใช้แก้คลิปแล้วหรือเกิดผลเชิงเหตุ
- ขณะนี้ Live มี Recommendation เดิม แต่ Outcome Prediction ยัง Block เพราะสิทธิ์และข้อมูลจริงไม่ผ่าน ไม่ควรนำภาพ Fixture ไปอ้างว่าโมเดลจริงพร้อมใช้
- Phase 6 ยังไม่ได้เริ่มตามคำสั่ง
