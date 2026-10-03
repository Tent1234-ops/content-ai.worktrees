# Retraining and Presentation Audit Handoff

งานเริ่มและทดสอบจริงวันที่ 3 ตุลาคม 2026; ตรวจยืนยันต่อและจัดส่งเอกสารวันที่ **4 ตุลาคม 2026 (Asia/Bangkok)** ชื่อโฟลเดอร์หลักฐานคงวันที่เริ่มไว้เพื่อไม่เปลี่ยนเส้นทางย้อนหลัง

## สรุปการตรวจรับ

**เทรนชุดล่าสุดเสร็จแล้ว แต่ยังไม่มีโมเดลใหม่ที่เปิดใช้ได้ตามเกณฑ์ปัจจุบัน** ไม่ได้ลดเกณฑ์ Unknown, ย้าย split, เพิ่มข้อมูลปลอม, นำ Test ไป fit หรือใช้กฎจำแนกเก่าทับ Active Model

เว็บ/API/การถอดเสียง/การบันทึกผ่านการตรวจด้านซอฟต์แวร์ ผลหลังรีสตาร์ตเหมือนเดิม แต่ **ยังไม่ผ่านการตรวจรับคำแนะนำจากคลิปใหม่แบบครบวงจรและการประเมินประโยชน์จริง** จึงไม่สรุปว่าโปรเจคผ่านทุกขอบเขตแล้ว

## งานที่เสร็จ

- [x] ตรวจ Dataset และโมเดลก่อนทำงาน พบข้อมูลใหม่เข้าและผ่าน Review แล้ว แต่รุ่นก่อนหน้าฝึกก่อนข้อมูลชุดนี้
- [x] เริ่ม Training ผ่าน `start_training_run()` ตัวเดียวกับ Admin background workflow และรอจนจบครบ 4 โมเดล
- [x] ตรวจ artifact reload, grouped CV, qualification และยืนยัน Active ไม่ถูกเปลี่ยน
- [x] ตรวจ API จริง 8 กลุ่ม พร้อม cleanup ข้อมูลทดสอบของสคริปต์เอง
- [x] ตรวจ release web จริง 2 viewport ผ่าน 6 กลุ่ม/36 screenshots ไม่พบ HTTP error ที่ไม่คาดหมายหรือ Flutter overflow ตาม harness
- [x] อัปโหลด `videos/Review_Phone.mp4` จริง ถอดเสียง บันทึก เปิดผล และตรวจหลังรีสตาร์ต
- [x] วินิจฉัยการดึงเทรนด์ล้มเหลวจากการเชื่อมต่อในสภาพแวดล้อมจำกัด เปิดเซิร์ฟเวอร์ใหม่แบบซ่อนหน้าต่างหลังได้รับอนุญาต และตรวจ provider จริงสำเร็จ
- [x] Backend 487 tests ผ่าน; Flutter 126 tests ผ่าน; Flutter analyze ไม่พบปัญหา
- [x] เขียนคู่มือภาษาไทยแยกหน้า แหล่งข้อมูล สูตร ข้อจำกัด และ Database ทั้ง 41 ตาราง พร้อม FAQ พรีเซนต์

## 1. Training ที่ทำจริง

| รายการ | ค่า |
|---|---|
| run_id | `78ad9b50-b5c6-41cd-b00d-542e7bafcd13` |
| model_version | `web-20261003T152238-78ad9b50` |
| เวลาไทย | สร้าง 3 ต.ค. 22:22:38, เสร็จ 22:34:00 |
| status | `completed` |
| smoke test | ไม่ใช่ |
| Dataset fingerprint | `3d9af94e595b78b44a63ddaf1128cb9e8dab7144a31bc8cfe9aebcae5948259a` |
| ข้อมูลที่รับรองสามหมวด | Phone 80 / Camera 80 / Laptop 85 รวม 245 |
| Fit / Validation / Test | 191 / 30 / 24 |
| Grouped CV | 5 folds เฉพาะ Train และแยกตามช่อง |
| ช่องทั้งหมด / ช่องรั่วข้าม split | 83 / 0 |
| Unknown | 42: train-reserved 35, validation 5, test 2; ไม่ fit เป็น class ที่สี่ |
| Parameters | confidence 0.6, promotion 0.8, Phase22 gate เปิด, ไม่ดาวน์โหลด embedding ใหม่ |
| โมเดลใหม่ | #35 NB, #36 LR, #37 calibrated SVM, #38 embeddings + LR |
| Best candidate | #37 ตาม scope validation แล้ว grouped CV; ไม่ใช่ Activate แล้ว |
| Active หลังงาน | #14 เหมือนก่อนงาน |

ตรวจ fingerprint หลังผู้ใช้สั่ง “ทำต่อ” วันที่ 4 ต.ค. แล้วยังตรงกัน จึงไม่ได้ Train ซ้ำโดยไม่จำเป็น

| ID | CV Accuracy | CV Macro F1 | CV Recall ต่ำสุด | Test accuracy ก่อน policy ใหม่ | Qualification |
|---|---:|---:|---:|---:|---|
| 37 SVM | 0.926702 | 0.951323 | 0.885246 | 0.958333 (23/24) | blocked |
| 36 LR | 0.900524 | 0.944582 | 0.846154 | 0.958333 (23/24) | blocked |
| 38 Embeddings | 0.801047 | 0.883889 | 0.661538 | 0.958333 (23/24) | blocked |
| 35 NB | 0.827225 | 0.841034 | 0.630769 | 1.0 (24/24) | blocked |

หมายเหตุ: `test_raw` คือก่อน enforcement ของ scope policy ใหม่ ยังใช้เส้นทาง confidence threshold เดิม ไม่ใช่คะแนนเปิดใช้งานครบวงจร ตัวอย่าง Test รายหมวดมี Phone เพียง 3 และ Camera 6 จึงไม่ควรอ้างผลนี้เป็นความแม่นกับคลิปใหม่ทุกแบบ

ทุก policy ได้ `not_ready / insufficient_unknown_validation`; เมื่อบังคับ fail-closed จึงคืน Unknown สำหรับ known Validation/Test ทั้งหมด และคะแนนหลัง policy เป็น 0 ข้อนี้ต้องอธิบาย ไม่ตีความว่า classifier ดิบทั้ง 4 ตัวทายผิดทั้งหมด และไม่อ้าง Unknown recall 100% จากการปฏิเสธทุกอย่าง

หลักฐาน: [training_report.json](../../artifacts/classification_training/web-20261003T152238-78ad9b50/training_report.json), [dataset manifest](../../artifacts/classification_training/web-20261003T152238-78ad9b50/dataset/dataset-3d9af94e595b78b4/dataset_manifest.json), [model #37](../../artifacts/classification_training/web-20261003T152238-78ad9b50/taxonomy-tfidf-linear-svm-calibrated/model.joblib)

## 2. Workflow ที่ทดสอบและข้อจำกัด

| Workflow | หลักฐานรอบนี้ | ผล |
|---|---|---|
| Register/Login/duplicate/wrong password | live API isolated users | ผ่าน |
| Guest เข้า private / User เข้า Admin | HTTP auth/role checks | ผ่าน 401/403 ตามกรณี |
| Dashboard public/หมวด/Google/รายละเอียด/ดูเพิ่ม/ตารางกราฟ | live release browser สอง viewport | ผ่าน |
| Follow category/preferences/unfollow/ข้อมูลแต่ละคนแยก | live API + widget tests | ผ่าน |
| Dataset create/update Transcript+taxonomy/hash/trash/restore | live API temporary dataset | ผ่าน; ไม่แก้ข้อมูล Train จริงเพื่อทดสอบ |
| จัดการ role/status ผู้ใช้ | live API temporary users | ผ่าน; cleanup เหลือ 0 users และ 0 temporary datasets |
| Import/Review UI และ training/settings/logs reads | live browser/API + automated tests | หน้าเปิดได้; ไม่ import/approve ซ้ำข้อมูลผู้ใช้จริง |
| ไฟล์เสีย | POST upload จริง | 422 ไม่บันทึกผล |
| คลิปวิดีโอถูกต้อง | ASR จริง + save + GET result | ผ่าน content #20 |
| Persistence หลัง restart | เปรียบเทียบ result JSON ทั้งชุดและ settings | เหมือนเดิม |
| Training จริง | managed worker + persisted run + reload artifacts | จบครบ 4 ตัว แต่ไม่มีตัว qualified |
| Activation รุ่นใหม่ | gate/ผล qualification | ไม่เปิด เพราะยังไม่ผ่าน ไม่ bypass เพื่อสาธิต |
| คำแนะนำมีเนื้อหาจาก accepted model ใหม่ | ต้องมีโมเดลผ่าน Unknown policy | ยังไม่ตรวจรับด้านคุณภาพ |
| บันทึกแผน/เทียบฉบับแก้ไข positive case | automated/fixture coverage เดิมใน test suite | ไม่ใช่หลักฐานใช้งานจริงด้วยคำแนะนำใหม่ที่ผ่านรับรอง |
| ประเมินประโยชน์คำแนะนำกับคน | inventory: `awaiting_fresh_clips_or_reviewers` | ยังขาดคลิป/ผู้ประเมินใหม่ |

หลักฐานไฟล์:

- [Live API](../../artifacts/presentation-audit-20261003/live-api.json)
- [Browser verification](../../artifacts/project-closeout/presentation-audit-20261003-r3/browser/verification.json) และภาพ/ARIA ในโฟลเดอร์เดียวกัน (1440x900, 1000x800)
- [Read-only inventory](../../artifacts/presentation-audit-20261003/inventory.json): ตรวจแล้ว DB ไม่เปลี่ยนจาก inventory เอง
- [Real upload + saved result](../../artifacts/presentation-audit-20261003/real-analysis.json)
- [Restart + real provider fetch](../../artifacts/presentation-audit-20261003/restart-and-providers.json)
- [Backend test output](../../artifacts/presentation-audit-20261003/backend-tests.stderr.log)

## 3. ผลคลิปจริงที่เปิดดูได้

คลิปเดิม `Review_Phone.mp4` เป็น **regression**, ไม่ใช่ fresh-heldout Test ใช้ Admin #2 ที่มีอยู่ บันทึก content #20 ไว้โดยตั้งใจให้ผู้ใช้เปิดจากหน้า “ไอเดียและประวัติ” ไม่ลบผลนี้หลังตรวจ

- Whisper small, CPU/int8, language th, `transcript_source=speech_to_text`, 51 segments, Hook 60 วินาที
- Raw และ cleaned transcript มีจริง ไม่ใช้ filename fallback
- raw prediction Phone 0.981554 แต่ final Unknown, `scope_validation_unavailable`, `withheld_unknown`
- ไม่มี actionable advice ที่แต่งเติมเพื่อให้หน้าเต็ม
- หลัง restart detail JSON เท่ากับค่าที่อ่านหลังบันทึก และ settings 300/small/60 ยังตรงกัน

## 4. ปัญหาเครือข่ายที่แก้แล้ว

ก่อนแก้ รอบเทรนด์และ reference statistics ล้มเหลวด้วย `WinError 10061`; environment ของเครื่องมือมี proxy จำกัดการออกเครือข่าย การเปิด server จาก environment นี้ทำให้ provider เชื่อมต่อไม่ได้

หยุดเฉพาะ process ที่ `scripts/stop_demo.ps1` ตรวจ identity ว่าเป็นของ launcher แล้วเปิด `scripts/start_demo.ps1` แบบ hidden นอก sandbox **หลังได้รับอนุญาต** ไม่แก้ค่า API key ไม่เปลี่ยน quota ไม่ลบประวัติรอบที่พลาด

ตรวจผ่าน API หลัง restart:

- run **10552**, 3 ต.ค. **22:48:05** เวลาไทย: YouTube live 50, Google live 9, status completed
- รอบ scheduler **23:00** ทำต่อเอง: global **10553** completed และ YouTube categories **10554** completed มี 528 rows รวมข้ามหมวด
- 528 เป็นจำนวนแถวจากหลายหมวด ไม่ใช่จำนวนวิดีโอไม่ซ้ำทั่วประเทศ และไม่ใช่จำนวนฝึกโมเดล
- ช่องว่าง 19:00-22:00 ที่ไม่ได้เก็บสำเร็จยังเป็นช่องว่างจริง ไม่เติมข้อมูลย้อนหลังปลอม

Local URLs: `http://127.0.0.1:8080/#/dashboard`, API `http://127.0.0.1:8000` เปิดไว้สำหรับลองใช้งาน

## 5. ข้อมูลอ้างอิงพร้อมแค่ไหน

อ่าน profile ตามเงื่อนไขปัจจุบันวันที่ 4 ต.ค. โดยไม่ bypass classification:

| หมวด | Pool คลิปอ้างอิง | กลุ่มผลตอบรับสูง | Duration samples | Median / P25-P75 วินาที |
|---|---:|---:|---:|---|
| Phone | 65 | 26 | 14 | 112 / 76-137 |
| Camera | 61 | 25 | 33 | 79 / 59-91 |
| Laptop | 65 | 26 | 24 | 52 / 44-80 |

นี่คือ **ความพร้อมของ reference profile** ไม่ใช่คำแนะนำที่คืนให้คลิป #20 ซึ่งยัง Unknown กลุ่ม duration จำกัดคลิปที่มี metadata และยาวไม่เกิน 5 นาที ไม่ใช่การสำรวจวิดีโอทุกความยาว/แยก Short-form สมบูรณ์แล้ว

## 6. สิ่งที่ยังค้างตามลำดับความสำคัญ

1. **Model acceptance:** Unknown Validation ต้องเพิ่มขั้นต่ำ 5 และ Test ขั้นต่ำ 28 ใน split/ช่องที่ถูกต้อง ตาม gate ปัจจุบัน ต้อง preview ช่องก่อนเก็บ; 35 reserved ไม่ย้ายหลังเห็นผลเพื่อให้ผ่าน Test
2. **คะแนนหลังมี Unknown พอ:** ฝึก/เลือก policy ด้วย Validation แล้วประเมินอีกครั้ง จำนวนถึงไม่ได้แปลว่าผ่าน recall/F1; ไม่เลือก candidate ด้วยผล Test
3. **Positive end-to-end และ utility:** เมื่อมีรุ่น qualified ให้ทดสอบคลิปใหม่สามหมวด/ถ่ายเอง/นอกขอบเขต รวมคำแนะนำ บันทึกแผน และเทียบฉบับแก้ไขจริง พร้อมผู้ประเมินตาม protocol เดิม
4. **Google provenance:** parser อ่านข้อมูลฝังในหน้าเว็บ ไม่ใช่ API schema ทางการ และยังไม่มีช่วงนับยอดค้นหาหรือเวลาเริ่มเทรนด์ที่ยืนยันได้; ห้ามใช้เวลาที่โค้ดใส่เองอ้างว่ากระแสเริ่มเวลานั้น
5. **Operational resilience:** Analyze แบบ in-process ไม่รอดปิด Backend กลางงาน; สำหรับเดโมอย่าปิดจน save เสร็จ ไม่ได้เพิ่ม durable queue ในงานนี้
6. **ถ้อยคำรายงาน:** Classification ไม่เท่ากับ Clustering; ไม่อ้างว่ามี TikTok/Instagram หรือรายงานเปรียบเทียบข้ามแพลตฟอร์มครบแล้ว
7. **Git metadata:** worktree เดิมชี้ gitdir ที่ไม่มีอยู่ จึงไม่มี `git diff/status` ที่เชื่อถือได้ ไม่ได้ init/reset/ซ่อม metadata โดยพลการ ใช้ file inventory/hash และ scoped edit แทน
8. **คะแนนคัดต้นแบบแบบเดิม:** `_row_performance_signal()` ยังใช้ `max(computed, row.trend_score, 0)` ต้องตรวจ provenance/สเกลของคะแนนเดิมก่อนอ้างว่ากลุ่ม high-performing ถูกคัดด้วยสูตร log views/day + engagement เพียงอย่างเดียว ไม่ได้เปลี่ยนคะแนนหรือผลเก่าในงานตรวจนี้

## 7. ไฟล์ที่เพิ่ม/แก้ในงานนี้

- คู่มือหลัก [current-system/README.md](../presentation/current-system/README.md) และบท 01-05
- `docs/presentation/system-walkthrough-th.md`: เพิ่มลิงก์ฉบับใหม่ ไม่แก้ผลตรวจเก่าให้ดูเหมือนเป็นข้อมูลปัจจุบัน
- `scripts/browser/verify_project_closeout_phase5.cjs`: ไม่คาดว่า TikTok ยังมี tab, ไม่บังคับว่าต้องมี 50 รายการพอดี, เลื่อนกลับหา platform tabs ก่อนคลิก
- `scripts/verification/presentation_analysis_audit.py`: upload regression จริง เก็บผลให้อ่าน ไม่มี token ใน artifact
- `scripts/verification/presentation_restart_audit.py`: ตรวจ frozen result/settings หลัง restart และ provider refresh ผ่าน API หนึ่งรอบ
- Handoff ฉบับนี้ และ artifacts ใหม่ตามลิงก์ข้างต้น

ไม่ได้ปรับกฎคำแนะนำหรือ code path การรับหมวดเพื่อให้ผลดูดีขึ้น; ไม่เริ่ม Phase ใหม่

## 8. คำสั่งตรวจที่รัน

```powershell
python -m unittest discover -s tests
python scripts/verification/project_closeout_phase5_api.py --output artifacts/presentation-audit-20261003/live-api.json
node scripts/browser/verify_project_closeout_phase5.cjs presentation-audit-20261003-r3
python scripts/verification/presentation_analysis_audit.py --clip videos/Review_Phone.mp4 --output artifacts/presentation-audit-20261003/real-analysis.json
python scripts/verification/presentation_restart_audit.py --analysis-report artifacts/presentation-audit-20261003/real-analysis.json --output artifacts/presentation-audit-20261003/restart-and-providers.json
```

Flutter ใช้ Dart executable + `flutter_tools.snapshot` โดยตรงเพราะ wrapper ใน environment นี้มีปัญหา: `test --no-pub` ผ่าน 126, `analyze --no-pub` ไม่พบปัญหา รอบนี้ไม่มี app UI เปลี่ยนจึงใช้ release build ที่ผ่านการตรวจรอบ Dashboard ล่าสุดแล้ว

หากรัน audit ซ้ำต้องตั้ง output/run ID ใหม่ สคริปต์ปฏิเสธ overwrite หลักฐานเดิม ส่วน upload audit เก็บผลจริงเพิ่มหนึ่งรายการ จึงไม่ควรกดรันซ้ำโดยไม่ตั้งใจ
