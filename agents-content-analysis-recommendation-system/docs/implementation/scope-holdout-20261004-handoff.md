# Handoff: จัดชุด Unknown และเทรนใหม่ 4 ตุลาคม 2026

## สถานะ

**จัดข้อมูลและเทรนเสร็จ แต่ยังเปิดใช้โมเดลใหม่ไม่ได้** ไม่มี candidate ผ่าน
Validation ของนโยบายตรวจรับหมวด จึงไม่ Activate ไม่ลดเกณฑ์ และ Active ยังเป็น #14
ซึ่งยังงดคำแนะนำเฉพาะหมวดตามเดิม ไม่ใช่การส่งมอบ Analysis ที่ผ่านตรวจรับครบแล้ว

## ข้อมูลที่แก้แล้ว

ตรวจเทียบรายการไฟล์ใน `Z:\Ai Content TrainTest Data\Test Data` กับ DB แล้วครบ
42 คลิป: headphone10, keyboard10, mouse11, speaker11 ไม่ใช่ไฟล์หายหรือยังไม่นำเข้า
ข้อมูล Camera ปัจจุบัน80 ไม่ต้องนำเข้าโฟลเดอร์เดิมซ้ำ

กฎ hash เดิมทำให้ Unknown อยู่ train-reserved35 / validation5 / test2
โดย reserved ไม่เคยเข้า fit classifier หรือ acceptance policy รอบก่อน จึงเพิ่ม
แผนแบ่งตามช่องแบบระบุเวอร์ชัน แยกบทบาท Unknown ให้ตรงกับวัตถุประสงค์การเก็บ

| หมวด | Train/สำรอง | Validation | Test | รวม |
|---|---:|---:|---:|---:|
| Phone | 63 | 12 | 5 | 80 |
| Camera | 61 | 13 | 6 | 80 |
| Laptop | 54 | 5 | 26 | 85 |
| สามหมวดรวม | 178 | 30 | 37 | 245 |
| Unknown | 2 สำรอง ไม่ fit | 10 จาก9ช่อง | 30 จาก17ช่อง | 42 |

- ล็อก [protocol](scope-holdout-20261004-protocol.md) และ preview ก่อนฝึกใหม่
- ย้าย46แถวพร้อมกันทั้งช่อง ไม่แยกคลิปช่องเดียวกันข้ามชุด ไม่ย้าย Validation/Test เดิม
- เลือกจากรหัสช่องและจำนวนเท่านั้น ไม่ใช้ชื่อ Transcript ค่าทำนาย หรือ engagement
- เก็บ prior assignments และ checksum ใน `dataset_split_plans` (ตารางใหม่1ตาราง)
- Import, channel preview, training readiness และ startup migration อ่านทะเบียนเดียวกัน
- ตรวจ partition conflicts/invalid assignments/leaked channels ได้0
- ชุดนี้เป็น **repartitioned internal benchmark** ไม่ใช่ fresh external test:
  คลิป known บางรายการเคยใช้ฝึกโมเดลเก่า รุ่นใหม่ฝึกจากศูนย์และไม่รวมช่องนั้นใน Train
- ไม่ลบคลิป ไม่เปลี่ยน label/Transcript ไม่แก้ผลวิเคราะห์หรือ model artifact เก่า
- Dataset fingerprint ใหม่ `f247c04ce87138d297e7a6e46bfe7e363b8b33e87bc71c8d3cf3db6597d80975`

## ผลเทรนจริง

ใช้ managed background worker ตัวเดียวกับหน้า Admin โดย Admin #2:

- Run `5a2fcb84-5155-4203-b871-e344ebf74633` completed
- Version `web-20261004T075624-5a2fcb84`
- 5-fold grouped CV, confidence0.6, promotion0.8, Phase22 gate=true, ไม่ดาวน์โหลด embedding ใหม่
- รายงาน `artifacts/classification_training/web-20261004T075624-5a2fcb84/training_report.json`

| ID | โมเดล | CV Accuracy | CV Macro F1 | CV Recall ต่ำสุด | Scope Validation |
|---|---|---:|---:|---:|---|
| 41 | Calibrated Linear SVM | 92.70% | 94.96% | 90.16% | ไม่ผ่าน |
| 40 | Tuned Logistic Regression | 90.45% | 94.55% | 87.30% | ไม่ผ่าน |
| 42 | Multilingual embeddings + LR | 79.78% | 88.25% | 65.08% | ไม่ผ่าน |
| 39 | Complement NB | 79.78% | 81.65% | 65.08% | ไม่ผ่าน |

ทุกตัวมี `scope_policy.status=failed_validation`, เหตุผล `no_validation_cutoff_passed`
ไม่ใช่ `insufficient_unknown_validation` แล้ว ไฟล์ทั้ง4โหลดกลับและ classify ได้
แต่ผลหลัง enforcement เป็น Unknown เพราะ policy ไม่ผ่าน ไม่อ้างว่าการโหลดไฟล์ผ่าน
แปลว่าโมเดลพร้อม production

ตัวอย่างจาก Validation ของ SVM #41 (ไม่ใช้ Test เพื่อปรับกฎ):

- similarity threshold0: รับ Laptop ถูก1/5, Phone11/12, Camera13/13;
  ปฏิเสธ Unknown ได้1/10 โดยยังใช้ confidence0.6 เดิม
- threshold0.35: ปฏิเสธ Unknown ได้9/10 แต่รับสามหมวดถูก18/30 และ Laptopยัง1/5
- ไม่มี threshold ที่รักษา Recall ทุกหมวด, MacroF1 และ Unknown recall >=0.8 พร้อมกัน
- LR รับ Laptop1/5, NB2/5; embeddings รับ Laptop4/5 แต่ Phone7/12 และ CV ไม่ผ่าน
- Test หลัง enforcement เป็น0สำหรับ known เพราะ fail-closed; Unknown recallเป็นnull
  ไม่รายงานการปฏิเสธทั้งหมดว่า Unknownเก่ง100% และไม่ใช้ raw Test เลือกตัวเปิดใช้งาน

## หน้าเว็บและการตรวจจริง

- แก้ชื่อ Unknown ที่เดิม UI อ่าน level3ว่าง ให้เป็น “นอกขอบเขต” รวมตัวกรอง
- แสดง42คลิป / ปรับเกณฑ์10/10 / ทดสอบ30/30 / สำรอง2 แทนป้ายว่าง42/30
- สถานะข้อมูล Unknown ตรวจทั้งจำนวนและจำนวนช่องของแต่ละชุด ไม่ใช้ยอดรวมอย่างเดียว
- เพิ่มชื่อภาษาไทยให้ Log `dataset_scope_holdout_plan_applied`
- การลบบัญชีผู้สร้างแผนยังเก็บpayload/checksumเดิมไว้ และล้างเฉพาะforeign keyของผู้สร้าง
  พร้อมบันทึกรุ่นแผนที่เก็บไว้ในaudit ไม่ให้ตารางใหม่ทำให้Workflowลบผู้ใช้ติดขัด
- Restart API แล้ว fingerprint และ splitคงเดิม
- APIจริง GET Review/Training/run สำเร็จ; POST Activate #41 ถูกปฏิเสธ422
  และตรวจซ้ำ Activeก่อน/หลังยัง14 ไม่ได้เปิดตัวไม่ผ่านชั่วคราว
- Browserจริง1440x1000 และ1000x1000 ตรวจ Review/Training รวม5checks ผ่าน
  ไม่พบ JS/Flutter overflow/API error; temporary admin sessionsจบด้วยlogoutแล้ว
- Browserรอบแรก APIผ่าน แต่ selector text-node หาChipไม่เจอทั้งที่ภาพแสดงถูก
  แก้ harness ให้อ่าน accessibility label แล้วรอบ2ผ่าน ไม่แก้ข้อมูลให้ผ่าน

หลักฐาน: `artifacts/scope-holdout-20261004/browser-r2/verification.json`, รูปและARIA
ในโฟลเดอร์เดียวกัน; รอบที่ล้มเหลวคงไว้ใน `browser/`

## Tests / คำสั่ง

- Backend **493 tests ผ่าน**: `python -m unittest discover -s tests`
  logs: `artifacts/scope-holdout-20261004/backend-tests.{stdout,stderr}.log`
- Flutter **128 tests ผ่าน**, analyzeไม่มีissue, build web releaseผ่าน
  มี warning Cupertino fontเดิม ไม่ใช่ error จากงานนี้
- เพิ่ม6backendtestsเรื่องmetadata-only, checksum/tamper, Admin, startup persistence,
  archived channel reservation, ย้ายknownพร้อมUnknownทั้งช่อง และ Unknown aggregateไม่ใช่ readiness
- หลังแก้จุดเชื่อมลบผู้สร้างแผน รันfocused23testsผ่าน: user management, split plan, collection plan
  logs: `artifacts/scope-holdout-20261004/final-focused.{stdout,stderr}.log`
- เพิ่ม2Fluttertestsตรวจชื่อและจำนวนแยกชุด
- Initial fixture tests มี transcript hashซ้ำข้ามsplitจากเลขตัวอย่างซ้ำ แก้เฉพาะ fixture
  ให้มีidentityไม่ซ้ำ ไม่มีการแก้ข้อมูลจริงเพื่อผ่านการทดสอบ

```powershell
python scripts/prepare_scope_holdouts.py --version scope-holdout-20261004-v1 --output artifacts/scope-holdout-20261004/partition-preview.json
python scripts/prepare_scope_holdouts.py --apply artifacts/scope-holdout-20261004/partition-preview.json --expected-sha256 707a1d5656f0e8a443561ace09b754ed8f580de7c994e3be7571390d68cdb8a0 --admin-user-id 2
node scripts/browser/verify_scope_holdouts.cjs artifacts/scope-holdout-20261004/browser-r2
```

คำสั่งด้านบนเป็นประวัติที่รันแล้ว ไม่ต้องรันซ้ำ: previewไม่เขียนทับ, applyปฏิเสธแผนซ้ำ
รอบTrainเริ่มผ่าน `model_management.start_training_run` ไม่ใช่ CLI ที่ไม่มีประวัติหน้าเว็บ

## ค้าง / แนวทางตรวจต่อ

1. **ไม่ต้องหา Unknownเพิ่ม33คลิปเพื่อแก้จำนวนเดิมอีกแล้ว** ปัญหานั้นแก้แล้ว
2. ตรวจความถูกต้องและรูปแบบข้อความ Laptopใน Train/Validation, ความหลากหลายช่อง
   และขีดจำกัด acceptance policy โดยใช้ Train/Validationเท่านั้น ไม่ย้ายsplitหรือลดgate
3. ถ้าต้องพัฒนาวิธีใหม่ ให้ระบุเวอร์ชัน/protocolใหม่และรายงานชุดTestที่เคยประเมินแล้ว
   เป็น reused benchmark; fresh external evaluation ยังต้องกันข้อมูลใหม่จริง
4. **ยังไม่ Activate**, ยังไม่ได้ทดสอบpositive advice/แผนปรับคลิปจากโมเดลพร้อมใช้งานใหม่
   และไม่มีผลhuman utility/fresh MP4เพิ่มในงานนี้ ไม่ใช้unit testsแทนหลักฐานดังกล่าว

## การย้อนกลับและการเปิดเว็บ

ก่อนแก้เพิ่มเติมสำรอง `dataset_split_plans` และแถวที่อยู่ใน `changes` ของpreview
ไม่ลบแผน/ย้ายTestกลับTrainเงียบๆ เพราะทำให้การกันชุดประเมินเปลี่ยนความหมาย
ถ้าต้องย้อนเพื่อกู้ระบบ ต้องหยุดworker/สำรองและคืนค่าassignmentกับregistryร่วมกัน
โดยคงรายงานรุ่นนี้ไว้เป็นประวัติ Activeไม่ได้เปลี่ยนจึงไม่มีmodelactivationต้องrollback

เว็บเปิดไว้ที่ `http://127.0.0.1:8080/#/dashboard`, หน้าเทรน `#/admin-training`
ใช้บัญชีAdminของผู้ใช้; API8000และเว็บ8080เปิดผ่านhidden demo launcher
Git worktree pointerเดิมยังเสียหาย ไม่แก้Git metadataและไม่resetงานของผู้ใช้
