# คู่มือเปิดระบบและส่งมอบ

## สิ่งที่ต้องมี

- Windows PowerShell, Python และ Package ตาม `requirements.txt`
- Flutter ตามรุ่นใน Release manifest และ Web build ที่ `frontend_flutter/build/web`
- MySQL Database ที่ Migration ปัจจุบันอ่านได้
- Faster Whisper model ที่ตั้งค่าไว้และพร้อมบนเครื่อง
- ค่า Environment ตามชื่อใน `.env.example` โดยเก็บค่าจริงใน `.env` เฉพาะเครื่อง ห้ามแนบไฟล์นี้ในชุดส่ง

ตรวจ Release manifest ล่าสุดจาก:

```powershell
Get-Content artifacts/outcome-prediction/phase-7/latest-release.txt
```

## เปิดแบบไม่เด้งหน้าต่าง Terminal

จากโฟลเดอร์โครงการ:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_demo.ps1
```

Script ใช้ `Start-Process -WindowStyle Hidden` บันทึก PID และเวลาเริ่ม และจะไม่ฆ่า Process อื่นที่ครอง Port อยู่ ถ้า Port 8000 หรือ 8080 ถูกใช้โดย Process ที่ Script ไม่ได้เป็นเจ้าของ ให้ตรวจ Process ก่อน ไม่ควรปิดแบบเหมารวม

## ตรวจความพร้อมโดยไม่ Train ใหม่

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_demo_readiness.ps1
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 8
```

ตรวจว่า Web ตอบ 200, Database พร้อม และ Faster Whisper พร้อม แยกสถานะ Outcome จาก Health ทั่วไป: Outcome ต้องคง `NO_GO` จนกว่าจะมี Qualified model จริง การเปิดระบบหรือรีสตาร์ตห้าม Trigger Training

หน้าใช้งาน:

- Web: `http://127.0.0.1:8080/#/dashboard`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## Workflow สาธิต

1. ตรวจ Health และสถานะ Model
2. เข้าสู่ระบบด้วยบัญชีทดสอบที่เตรียมบนเครื่อง โดยไม่บันทึกรหัสผ่านในเอกสาร
3. เปิดผลวิเคราะห์ที่บันทึกจริงจากรายการใน Release manifest
4. เปิดกรณี Recommendation และ Unknown/Withheld
5. เปิด Admin Outcome Training เพื่อแสดง Gate, Registered model และ Active model
6. งด Probability/Scenario เมื่อไม่มี Qualified model

## Private backup

สร้าง Backup ใหม่ลงโฟลเดอร์ใหม่เท่านั้น:

```powershell
py -X utf8 scripts/create_delivery_backup.py `
  --output artifacts/outcome-prediction/phase-7/<UTC>-private-backup
```

Backup มีทุกตารางและอาจมี Password hash, Transcript และข้อมูลผู้ใช้ จึงห้ามส่งต่อ ห้ามใส่ใน `shareable-package` และห้ามนำขึ้น Public repository

## ทดสอบ Restore โดยไม่ทับฐานจริง

```powershell
py -X utf8 scripts/restore_delivery_backup.py `
  --backup artifacts/outcome-prediction/phase-7/<UTC>-private-backup `
  --database-url sqlite:///artifacts/outcome-prediction/phase-7/<UTC>-restore.sqlite3 `
  --report artifacts/outcome-prediction/phase-7/<UTC>-restore-report.json
```

ปลายทางต้องเป็น SQLite แยกและว่าง Script จะปฏิเสธฐานต้นทางหรือฐานที่มีข้อมูลอยู่แล้ว ให้ตรวจ `passed=true`, Manifest checksum, จำนวนตาราง/แถว และ `source_database_was_not_modified=true`

ไฟล์ SQLite ที่กู้ขึ้นมามีข้อมูลจริงเช่นเดียวกับ Private backup จึงเป็นไฟล์ Private ห้ามส่งต่อ ห้ามนำขึ้น Public repository และห้ามใส่ใน `shareable-package`

## หยุดระบบ

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop_demo.ps1
```

Script หยุดเฉพาะ PID ที่มีเวลาเริ่มตรงกับ State ของ Launcher ไม่ใช้คำสั่งหยุด Python/Browser ทุก Process

## ปัญหาที่พบบ่อย

| อาการ | วิธีตรวจ | การจัดการ |
|---|---|---|
| Port ถูกใช้ | ดูผล `start_demo.ps1` | ใช้ Port อื่นหรือหยุดเฉพาะ Process ที่รู้เจ้าของ |
| `/health` degraded | ดู `database`, `ai_models`, `live_trends.providers` | แยก Provider เก่าที่ไม่อยู่ใน Scope ออกจากความพร้อม DB/ASR และรายงานตามจริง |
| ASR ไม่พร้อม | ดู Faster Whisper ใน `/health` | ตรวจ Model cache/ค่าตั้ง ห้ามสาธิต Upload สดจนกว่าจะพร้อม |
| Outcome ไม่มีเปอร์เซ็นต์ | ดู Admin Outcome Gate | เป็น Fail-closed ตาม Contract ห้ามใส่ Fixture แทนผลจริง |
| ผลเก่าเป็น `legacy_not_assessed` | ตรวจวันที่และ Result payload | ไม่คำนวณทับอัตโนมัติ ใช้ Revision/Re-analysis ใหม่เมื่อระบบผ่าน Gate |
| Backup checksum ไม่ตรง | ตรวจ `manifest.sha256` | หยุด Restore และสร้าง Backup ใหม่ ห้ามแก้ Manifest ด้วยมือ |

## Rollback

หาก Release ใหม่มีปัญหา ให้หยุด Launcher และกลับไปใช้ Source/Build/Private backup ที่ Hash ตรงกับ Release manifest รุ่นก่อน การ Activate Outcome model ต้องทำผ่าน Backend Gate และ Atomic single-active เท่านั้น ห้ามแก้ `is_active` ในฐานข้อมูลด้วยมือ

## เช็กลิสต์ก่อนส่ง

- วันที่ 18 ตุลาคม: เปิดจากสถานะหยุด ซ้อมลำดับจริง ตรวจ Browser/Projector/เครือข่าย และบันทึกผลตามเวลาจริง
- วันที่ 19 ตุลาคม: ตรวจ Health, Model status, Release checksum, Backup checksum, Restore report และ Offline fallback อีกครั้ง
- หาก Gate Outcome ยังไม่ผ่าน: นำเสนอเป็นระบบ Fail-closed พร้อมข้อจำกัด ไม่เปลี่ยนเป็น `qualified`
- หากเจ้าของยอมรับการส่งแบบมีข้อจำกัด: บันทึกผู้ยอมรับ เวลา และข้อจำกัดที่ยอมรับแยกจาก Artifact ทางเทคนิค
