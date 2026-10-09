# Outcome Prediction Phase 7 Handoff

วันที่ตรวจล่าสุด: 9 ตุลาคม 2026

## คำตัดสิน

งานเครื่องมือส่งมอบ เอกสารพรีเซนต์ Backup/Restore และ Regression ของ Phase 7 **เสร็จแล้ว** ชุดส่งมอบอยู่ในสถานะ `ready_for_rehearsal_with_unaccepted_limitations` แต่ Outcome Prediction จริงยังเป็น `NO_GO` และ `not_ready_as_qualified_outcome_prediction`

ไม่ลดเกณฑ์ ไม่แต่งข้อมูล ไม่ Train/Activate โมเดล ไม่เปิด Independent Test และไม่เริ่ม Phase 8

เหตุผลที่ยังไม่ Ready แบบ Qualified:

- Active target rows 308 แต่ Structurally ready 0 และ Training allowed 0
- Data rights/retention สำหรับ Training และ Serving ยังไม่ยืนยัน
- Fresh Independent Outcome Test 0
- Registered Outcome models 0 และ Active Outcome model ไม่มี
- Human utility reviewer 0 และ rating 0
- Classification model 43 เป็น `presentation_only` และไม่ผ่าน Readiness สำหรับผลที่ยอมรับได้

## งานที่เสร็จ

- เพิ่ม `scripts/build_outcome_delivery.py` เพื่อสร้าง Source hash, Runtime version, Schema fingerprint, Model/Contract snapshot, Release manifest และ Shareable package แบบ Allowlist
- ขยาย `scripts/create_delivery_backup.py` ให้เก็บ Outcome registry, Contract hashes, Calibration version และ Data-use status โดยไม่แนบ `.env`
- ปรับ `scripts/check_demo_readiness.ps1` ให้ Web, Database และ ASR ต้องพร้อม และรายงานสถานะ Trend providers
- เพิ่ม Unit tests สำหรับ Secret exclusion, Schema metadata, Package allowlist, Backup/Restore identity และ Phase 6 integrity tampering
- เพิ่มเอกสารพรีเซนต์ภาษาไทย 5 ไฟล์ที่ `docs/presentation/outcome-prediction/`
- สร้าง Private backup พร้อม checksum และ Restore ลง SQLite แยกจากฐานจริง
- ทดสอบ Hidden launcher บนพอร์ต 8010/8090 และหยุดเฉพาะ Process ที่ Launcher เป็นเจ้าของ
- รัน Backend, Flutter และ Browser regression กับ source/build ปัจจุบัน
- สร้าง Offline fallback จากผลที่บันทึกจริงโดยระบุว่าเป็น Historical saved result ไม่อ้างว่าเป็น Live/Fresh

## หลักฐาน Artifact

Delivery run:

`artifacts/outcome-prediction/phase-7/20261009T124911Z-delivery`

Private backup:

- Directory: `artifacts/outcome-prediction/phase-7/20261009T124911Z-delivery/private-backup`
- Manifest SHA-256: `b28aad7762426c57c22fcd0ed3b0ebd645c164af8d71a5b7812a2f068ad04232`
- 45 ตาราง, 337,176 แถว, 19 Version/model assets
- `.env` included: false
- Registered Outcome models: 0, Active Outcome model: none
- Private only: มีข้อมูลผู้ใช้/Transcript/Password hash ได้ ห้ามส่งต่อ

Restore verification:

- Report: `artifacts/outcome-prediction/phase-7/20261009T124911Z-delivery/restore-report.json`
- Target: SQLite แยกที่ `restore-verification.sqlite3`
- Result: passed=true, 45 ตาราง, 337,176 แถว
- Source database was not modified: true
- Restore SQLite เป็นข้อมูล Private เช่นเดียวกับ Backup และไม่อยู่ใน Shareable package

Hidden launcher:

- `launcher-state-probe.json`: Backend/Web alive และ MainWindowHandle = 0 ทั้งคู่
- `launcher-readiness.json`: Web 200, Database `ok`, ASR ready
- `launcher-stop.json`: หยุดเฉพาะ PID 1888 และ 2100 สำเร็จ
- Health รวมเป็น `degraded` เพราะ Legacy TikTok provider error; YouTube/Google `ok` และ Delivery UI ไม่ประกาศ TikTok เป็น Scope

Browser:

- `artifacts/outcome-prediction/phase-7/20261009T124911Z-delivery/browser/verification.json`
- Result: passed=true, screenshots 12, errors 0
- Fixture ใช้ตรวจ UI เท่านั้น ไม่ใช่ Model/Data evidence

Final release:

- อ่าน Directory ล่าสุดจาก `artifacts/outcome-prediction/phase-7/latest-release.txt`
- ตรวจ `release-manifest.json`, `release-manifest.sha256`, `integrity.json` และ `shareable-package/manifest.json`
- Source metadata ไม่ใช้ Git commit เพราะ Worktree metadata ของโครงการเสีย จึงใช้ SHA-256 รายไฟล์และ Tree hash แทน

## หลักฐานทดสอบ

### Delivery tools

```powershell
$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
py -m unittest tests.test_delivery_tools tests.test_outcome_delivery -v
```

ผลก่อน Final packaging: **9 tests passed**, exit code 0 จากนั้นเพิ่ม Regression สำหรับ JSON ที่มี Windows UTF-8 BOM และรันซ้ำเป็น **10 tests passed**, exit code 0

### Backend regression

```powershell
$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
py -m compileall -q app tests scripts
py -m unittest discover -s tests -q
```

ผลก่อนเพิ่ม BOM regression: **567 tests passed** ใน 112.141 วินาที, exit code 0 ผล Final verification หลังเพิ่ม Test: **568 tests passed** ใน 88.365 วินาที, exit code 0 ข้อความ STT/Topic failure เป็น Failure cases ที่ Test ตั้งใจจำลอง

### Flutter

```powershell
flutter analyze --no-pub
flutter test --no-pub
flutter build web --release --no-pub
```

ผล:

- Analyze: No issues found, exit code 0
- Tests: 164 tests passed, exit code 0
- Release web build: สำเร็จ, exit code 0
- Flutter 3.41.9, Dart 3.11.5

### Browser acceptance

```powershell
node --check scripts/browser/verify_outcome_phase5.cjs
node scripts/browser/verify_outcome_phase5.cjs artifacts/outcome-prediction/phase-7/20261009T124911Z-delivery/browser
```

ผล: passed=true, screenshots 12, errors 0

### Backup and restore

```powershell
py -X utf8 scripts/create_delivery_backup.py --output <private-backup-directory>
py -X utf8 scripts/restore_delivery_backup.py `
  --backup <private-backup-directory> `
  --database-url sqlite:///<separate-restore-file> `
  --report <restore-report.json>
```

ผล: Backup 45 ตาราง 337,176 แถว และ Restore ผ่านครบโดยไม่แก้ Source database

## Demo ที่ใช้ได้จริง

- Release manifest ระบุ ID ของ Historical saved result ประเภท Recommendation และ Unknown/Withheld โดยไม่บรรจุ Title หรือ Transcript ใน Public manifest
- ผลเหล่านี้ใช้สาธิตว่า Recommendation และการงดแนะนำทำงานอย่างไร แต่ต้องเรียกว่า "ผลที่บันทึกไว้ก่อนหน้า"
- Revision plan มี 1 รายการ แต่ Revision comparison มี 0 รายการ จึงห้ามสาธิตว่าเทียบฉบับแก้ไขเสร็จแล้ว
- Outcome Probability/Scenario จริงไม่มี เพราะไม่มี Qualified Outcome model

## งานค้างและ Owner

1. **Project owner:** ยืนยันสิทธิ์ Training/Serving, Retention และ Withdrawal พร้อมหลักฐาน ห้ามเปลี่ยน Status โดยไม่มีหลักฐาน
2. **Dataset admin:** เติม Format/Sampling provenance/Outcome snapshots ให้ผ่าน Structural gate โดยไม่ย้าย Protected split หรือลด Minimum
3. **Evaluation owner:** เตรียม Fresh Independent Test ตาม Protocol และเปิดเพียงครั้งเดียวหลัง Candidate Freeze
4. **Outcome model owner:** สร้าง Frozen real manifest, ฝึกจาก Fit/Tuning/Calibration เท่านั้น และ Freeze Artifact/Calibrator/Baselines ก่อน Test
5. **Human evaluators:** ประเมินด้วยคนจริงอย่างน้อย 3 คนหลังมี Qualified model ห้ามใช้ AI สร้างคะแนนแทน
6. **Release owner:** บันทึกการยอมรับข้อจำกัดอย่างชัดเจน หากจะส่งแบบ "พร้อมซ้อมแต่ Outcome ยังไม่ Qualified"
7. **Release owner วันที่ 18 ต.ค. 2026:** เปิดจากสถานะหยุดและซ้อมเต็มรอบ เหตุการณ์นี้ยังไม่เกิดขึ้น ณ วันที่ 9 ต.ค.
8. **Release owner วันที่ 19 ต.ค. 2026:** ตรวจ Health/Hashes/Backup/Restore/Offline fallback ตามเวลาจริง ห้ามลงวันที่ย้อนหลัง

## Rollback

- หยุดระบบด้วย `scripts/stop_demo.ps1`; Script ตรวจ PID และเวลาเริ่มก่อนหยุด
- ใช้ Release manifest และ Source tree hash รุ่นก่อนเพื่อตรวจ Source/Build ที่จะย้อนกลับ
- Restore ได้เฉพาะฐานแยกที่ว่าง ห้ามทับฐานจริงโดยตรง
- Outcome model ต้อง Activate ผ่าน Backend gate แบบ Atomic single-active เท่านั้น ห้ามแก้ `is_active` ด้วย SQL
- หาก Release package checksum ไม่ตรง ให้ปฏิเสธ Package และสร้างใหม่ใน Directory ใหม่ ห้ามแก้ Artifact เดิม

## ขอบเขตที่หยุดไว้

- Phase 8 ไม่ได้เริ่ม
- Outcome model ไม่ได้ Train, Register หรือ Activate
- Independent Test ไม่ได้เปิด
- ไม่มี Probability, Metric, Human rating หรือ Latency ที่แต่งขึ้น
- ไม่มีการอ้างว่าทำตามคำแนะนำแล้วทำให้ยอดวิวเพิ่ม
