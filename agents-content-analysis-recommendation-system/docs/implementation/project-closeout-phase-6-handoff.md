# Project Closeout Phase 6 Handoff

วันที่ Freeze: 2 ตุลาคม 2026 (Asia/Bangkok)

ขอบเขตเอกสารนี้ครอบคลุมเฉพาะ `project-closeout/phase-6-delivery-and-presentation.md` ไม่มีการเพิ่ม feature, train/activate model, เปลี่ยนสูตร หรือเริ่ม Phase ถัดไป

## สถานะ

**รุ่นส่งและเอกสารพร้อมสำหรับเรียนรู้/ซ้อม แต่การส่งมอบทั้งโครงการยังเป็นบางส่วน**

Software launcher, restart, private backup/separate restore, release manifest และชุดพรีเซนต์เสร็จแล้ว Blocker จาก Phase 5 ยังอยู่: Active Model #14 มี `scope_policy_missing`, ไม่มี fresh heldout และไม่มี human utility evaluation จึงต้องพรีเซนต์ว่า positive Analysis ยังถูกงด ไม่ใช่ completed project

## รุ่นส่ง

- Version: `content-ai-closeout-20261002-phase6`
- Freeze inventory: `artifacts/project-closeout/phase6-20261002T181200+0700/release-inventory-v2.json`
- Release manifest: `artifacts/project-closeout/phase6-20261002T181200+0700/release-manifest.json`
- Inventory time: `2026-10-02T11:33:50Z` หรือ 18:33:50 Asia/Bangkok
- Git commit: ใช้ไม่ได้เพราะ worktree metadata เสีย ไม่ได้ `git init`, reset หรือซ่อม pointer
- Backend app tree: `4942255653e565876d54a442b299bc107b9fb38f87e2731c5a5e911612ebf68f`
- Scripts tree: `35998bf3a811cda73c220e0bedd83ad89842cb8765b23d735ee53743aefd8b0b`
- Frontend lib tree: `a6f433b18cfa42c61f1423fa5bb42cfe37970dd034edcef299c7e5553ca39963`
- Web `main.dart.js`: `9608cd192d9fdaed26bb99717835ca8de78ac81a5999de1e7945b4dbf1c7c6e4`
- Active Model #14 artifact: `f77e26d1ccf940ef7e8c520397fe808521bb485b39fcc9c2b619789e1cd98cd2`
- Settings: upload 300 วินาที, Whisper `small` ready, Hook 60 วินาที
- Dataset: 429 แถว, active 418; reference statistics cutoff `2026-10-02 11:00:17Z`

## ทำแล้ว

1. เพิ่ม launcher `start_demo.ps1`, `check_demo_readiness.ps1`, `stop_demo.ps1` ใช้ hidden processes, ตรวจพอร์ตด้วย TCP, เก็บ PID/start time และหยุดเฉพาะ identity ที่ตรง
2. เพิ่ม private backup/restore แบบ checksummed โดยไม่ copy `.env`; restore รับเฉพาะ SQLite ว่างและปฏิเสธ source database identity
3. ทดสอบเปิดจากสถานะปิดบน `8010/8090`, main window handle เป็น 0, health/database/ASR พร้อม และหยุดแล้ว endpoint ทั้งสองดับ
4. หลัง restart เปิด History, Content detail, Revision plan และ Admin settings/training ผ่าน API จริง ค่าคงเดิม
5. สร้าง release inventory/manifest, presentation evidence ที่ไม่ใส่ token/password และคู่มือภาษาไทยสองไฟล์
6. อัปเดต README, scope matrix และ Final Acceptance ให้ตรง freeze โดยไม่ซ่อน blocker

## ไฟล์ที่เพิ่มหรือแก้

เพิ่ม:

- `scripts/start_demo.ps1`
- `scripts/check_demo_readiness.ps1`
- `scripts/stop_demo.ps1`
- `scripts/create_delivery_backup.py`
- `scripts/restore_delivery_backup.py`
- `tests/test_delivery_tools.py`
- `docs/presentation/system-walkthrough-th.md`
- `docs/presentation/demo-checklist-th.md`
- `docs/implementation/project-closeout-phase-6-handoff.md`

แก้:

- `README.md`
- `.env.example` เปลี่ยนรหัสผ่านตัวอย่างเป็น placeholder ไม่แตะ `.env` จริง
- `docs/implementation/project-closeout-scope.md`
- `docs/implementation/project-closeout-final-acceptance.md`

ไม่มี application route/schema/frontend/model/recommendation logic change และไม่มี migration

## หลักฐาน Launcher และ Restart

คำสั่งที่ผ่านบนพอร์ตแยก:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_demo.ps1 `
  -BackendPort 8010 -WebPort 8090
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_demo_readiness.ps1 `
  -BackendPort 8010 -WebPort 8090
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop_demo.ps1
```

ผลจริง:

- readiness: Web 200, Database `ok`, ASR `ready=true`
- Python processes 2 ตัวมี `MainWindowHandle=0`
- หลัง restart: History 2 รายการ, Content #18 และ plan เปิดได้
- Settings: 300 / small / 60; Active Model #14 `blocked`
- stop คืน PID ของ process ที่เป็นเจ้าของและ `8010/8090` ตอบไม่ได้หลังหยุด
- พอร์ต default `8000` มี process เดิมอยู่ Launcher ปฏิเสธและไม่ได้หยุด process นั้น เป็นหลักฐาน port guard ไม่ใช่ failure ของระบบ

หลักฐาน: `artifacts/project-closeout/phase6-20261002T181200+0700/restart-verification.json`

Browser restart run `phase6-...-restart-r2` **ไม่ผ่านและไม่ถูกนับเป็น acceptance pass** เพราะ release web ถูก compile ให้เรียก API `8000` ขณะที่ isolated backend อยู่ `8010`; harness เก็บภาพ 7 ภาพแล้วหยุดที่ TikTok locator หลักฐาน failed run ถูกเก็บไว้ ไม่ใช้แทน browser r10 ที่ผ่านใน Phase 5

## Backup และ Restore

```powershell
python scripts/create_delivery_backup.py `
  --output artifacts/project-closeout/phase6-20261002T181200+0700/private-backup-v3

python scripts/restore_delivery_backup.py `
  --backup artifacts/project-closeout/phase6-20261002T181200+0700/private-backup-v3 `
  --database-url sqlite:///Z:/content-ai.worktrees/agents-content-analysis-recommendation-system/artifacts/project-closeout/phase6-20261002T181200+0700/restore-verification-v3.sqlite3 `
  --report artifacts/project-closeout/phase6-20261002T181200+0700/restore-report-v3.json
```

ผล:

- Backup v3 จำนวน 41 ตาราง 279,351 แถว, version/model assets 12 ไฟล์; v1-v2 คงไว้เป็นหลักฐานรอบพัฒนา backup tool
- Restore v3 จำนวน 41 ตาราง 279,351 แถวลง SQLite แยก ผ่าน checksum และ row-count check
- Active model artifact/evaluation, taxonomy, recommendation template/method files และ dependency locks อยู่ใน assets; เอกสาร release แยกตรวจ hash ใน `release-manifest.json` เพื่อไม่ให้ backup เกิดวงจร version
- `.env` ไม่รวมใน backup มีเพียง `.env.example` และรายชื่อ key
- Restore tool ไม่รองรับคำกล่าวว่า restore ไป MySQL เครื่องใหม่ผ่านแล้ว รอบนี้พิสูจน์เฉพาะ SQLite แยกบนเครื่องนี้
- Backup เป็น private เพราะมี password hashes และ user content ห้ามใส่ presentation bundle

## Tests

```text
python -m unittest discover -s tests -v
Ran 484 tests in 90.425s - OK

python -m py_compile scripts/create_delivery_backup.py scripts/restore_delivery_backup.py
PowerShell parser: start/check/stop scripts syntax OK
```

Flutter ไม่มี source เปลี่ยนใน Phase 6 หลักฐาน release เดิมจาก Phase 5 คือ 125/125 tests, `flutter analyze` no issues และ release build ผ่าน การเรียก Flutter CLI ซ้ำรอบ Phase 6 ค้างใน `cmd` wrapper โดยไม่มี output จึงหยุดเฉพาะ wrapper ที่รอบนี้สร้างและไม่อ้างเป็นผลผ่านใหม่ Web build hash ยังคงตรงกับ release inventory

## ชุดพรีเซนต์

- คู่มือระบบ: `docs/presentation/system-walkthrough-th.md`
- ลำดับเดโม/คำถาม: `docs/presentation/demo-checklist-th.md`
- ภาพสำรองและ label: `artifacts/project-closeout/phase6-20261002T181200+0700/presentation-evidence/manifest.json`
- ภาพ `saved-result-historical.png` ถูกติดป้ายว่า Historical saved result ไม่ใช่ positive run ปัจจุบัน
- ภาพทั้งหมดมาจาก release browser r10 วันที่ 2 ตุลาคม 2026 ไม่ใช่ fixture และไม่อ้างว่าเป็น provider live ณ วันพรีเซนต์

## Freeze ห้ามแตะระหว่างซ้อม

- ห้าม Train, Activate, Rollback หรือเปลี่ยน Active Model
- ห้าม Approve All 42 pending candidates โดยไม่ตรวจ
- ห้ามลด Unknown threshold หรือปิด scope validation
- ห้ามเปลี่ยน collection interval, random seeds, taxonomy/template/method versions
- ห้ามลบ model/history/private backup ด้วย wildcard
- หลัง freeze แก้เฉพาะ blocker ที่ทำให้เดโมเปิดไม่ได้ พร้อม rerun tests และออก release manifest ใหม่

## งานค้างสุดท้าย

| ประเภท | งานค้าง | ผู้รับผิดชอบ/Dependency |
|---|---|---|
| release blocker | Review Unknown candidates, train/evaluate และ activate model ที่มี validated scope policy | เจ้าของโครงการ/Admin; ต้องยืนยันก่อนเปลี่ยน Active Model |
| model evaluation | Fresh Phone/Camera/Laptop/Unknown อย่างละ 3 รวมคลิปถ่ายเอง | ผู้เก็บข้อมูลและผู้กำหนด Gold |
| utility evaluation | ผู้ประเมินจริงอย่างน้อย 3 คนและ A/B/C ratings | ผู้ประเมินมนุษย์ |
| scope decision | ข้อ 11/13/15/17/18 | เจ้าของโครงการกับอาจารย์ |
| live event | Notification จาก provider trend ใหม่จริง | รอ provider event และเจ้าของตรวจ |
| portability | Restore ไป MySQL แยกหรือเครื่องใหม่ | ยังไม่ทดสอบเพราะไม่มี `mysqldump/mysql` CLI |

## Runtime

- Launcher ทดสอบและหยุดแล้วบน `8010/8090`
- Service เดิมที่ `http://127.0.0.1:8000` และ `http://127.0.0.1:8080` ยังตอบได้ แต่ไม่ใช่ process ที่ Phase 6 launcher เป็นเจ้าของ จึงไม่ได้ kill
- วันสาธิตให้ปิด service เดิมอย่างทราบเจ้าของก่อน แล้วใช้ `scripts/start_demo.ps1` บน default ports

## จุดหยุด

Closeout Phase 6 เสร็จเฉพาะส่วนส่งมอบและเอกสาร หยุดพัฒนาอัตโนมัติ ไม่มี Phase ถัดไปถูกเริ่ม
