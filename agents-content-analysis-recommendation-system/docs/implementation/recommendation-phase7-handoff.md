# Recommendation Phase 7 Handoff

## ตรวจทานเพิ่มเติม 2026-09-30

พบและแก้ปัญหาที่ tests เดิมไม่ครอบคลุม: Context เปลี่ยนเพราะเวลาอ่าน settings, งานล้มเหลวถูกนำไปให้คะแนนงดแนะนำ, คะแนนต่อคลิปไม่ครบแต่มีโอกาสประกาศผ่าน, การกระจายลำดับสมดุลเฉพาะภาพรวม และแบบประเมินไม่แสดงเงื่อนไข/หลักฐานพอให้ตรวจได้

ตอนนี้ใช้ Protocol/Review schema v2, Statistics cutoff เดียว, fingerprint ประวัติสถิติและ Artifact integrity, การตรวจ Payload จริง, Pre-review ยืนยันดูคลิป และอย่างน้อยสามชุดคะแนนครบต่อคลิป รวมถึงแบบประเมินที่เปิดดูที่มา/ข้อความ/เวลา/สถิติได้ พร้อมกู้ฉบับร่างหลังรีเฟรช

ต้องสร้าง `prepare-study`/`run-study` ใหม่หลังแก้รุ่นนี้ ไม่แก้ Hash ของ Artifact รุ่นเก่าให้ดูเหมือนเข้ากัน หยุดเปลี่ยน Dataset/Model/settings/สถิติระหว่าง Study; ถ้าเปลี่ยน เครื่องมือจะปฏิเสธ Context และให้สร้าง Protocol ใหม่

Critical flag adjudication ต้องมี `case_id`, `presentation_id`, `flag`, `status` (`confirmed` หรือ `dismissed`), `adjudicator_id` และ `reason` ขาดข้อมูลตัดสินจะยังเป็น pending ส่วน Protocol v2 ระบุ `analysis_failures_max=0` ด้วยเพื่อไม่ประกาศ Classification ผ่านเมื่อยังมีงานล้มเหลว แม้ false acceptance จะเป็นศูนย์

รายละเอียดและ Verification ล่าสุดอยู่ใน [รายงานตรวจ Phase 5-7](recommendation-phases5-7-review.md) ยังไม่มีคะแนนคนจริงและ `evaluation_complete=false` ไม่ใช้ Synthetic fixtures เป็นผลทดลอง

## สถานะ

- **สถานะเครื่องมือ:** `tooling_ready` โค้ด Protocol, Manifest audit, A/B/C, แบบประเมินปกปิด, การตรวจคะแนน และรายงานพร้อมใช้งาน
- **สถานะผลประเมินจริง:** `awaiting_fresh_clips` และ `awaiting_human_ratings`
- **evaluation_complete:** `false`

ยังไม่มีคลิปใหม่ 12 คลิปและคะแนนจากผู้ประเมินจริง 3 คน จึงไม่มีการสร้างคะแนนแทน ไม่มีการประกาศว่า Utility ผ่าน และไม่มีข้อสรุปว่าคำแนะนำเพิ่ม Engagement

งานนี้ทำเฉพาะ Phase 7 ไม่ได้ Train/Activate โมเดล ไม่ปรับ Threshold/Template จากผล Test ไม่ Import คลิปทดสอบเข้า Dataset และไม่ได้เริ่ม Phase 8

## สิ่งที่ทำเสร็จ

1. แยกรายงานเป็น Classification, Evidence correctness และ Recommendation utility โดยไม่ใช้ Confidence หรือจำนวนคำแนะนำแทน Utility
2. เพิ่ม Manifest audit ที่ตรวจ Human gold label, consent, provenance, บทบาท heldout/regression, SHA-256, Video ID, Channel/creator และประวัติการใช้เดิม ชื่อไฟล์ใหม่ไม่ทำให้คลิปเดิมกลายเป็น Test ใหม่
3. ตรวจ Transcript exact/near-copy หลัง ASR กับ Train, Validation, Test เดิม และคลิปอ้างอิง โดยผลซ้ำถูกตัดออกจากคะแนน
4. ล็อก Protocol ก่อน Prediction ด้วย Version, SHA-256, เวลา, Seed, Model artifact, Acceptance/settings, ASR, Dataset manifest, Reference fingerprint, Statistics cutoff, Template/Topic/Comparison policy และ Code hash
5. สร้าง Variant จากผลวิเคราะห์ Snapshot เดียวกัน: A มีชื่อหัวข้อ, B เพิ่มวิธีทำ, C ใช้เนื้อหา B เดิมแล้วเพิ่มหลักฐาน ห้าม C ได้หัวข้อหรือคำแนะนำใหม่
6. กระจายทั้งหกลำดับ `ABC`, `ACB`, `BAC`, `BCA`, `CAB`, `CBA` แบบกำหนดซ้ำได้ด้วย Seed และสมดุลเมื่อ Pilot มี 12 คลิป x 3 ผู้ประเมิน
7. สร้าง Review packet HTML แยกผู้ประเมิน ดูคลิปและตอบ Pre-review ก่อน จากนั้นเห็นคำแนะนำทีละชุดผ่านรหัสปกปิด ไม่เห็น A/B/C ส่วนเฉลยอยู่ใน `private/`
8. รองรับคะแนน 1–5 ด้านความเกี่ยวข้อง ความไม่ซ้ำ ความเข้าใจง่าย การนำไปใช้ และความถูกต้องของหลักฐานเฉพาะ C พร้อมเหตุผลเมื่อให้ 1–2 และ Critical flags
9. รองรับ Empty advice แยกเป็นคุณภาพการงดแนะนำหรือ Missed opportunity ไม่เปลี่ยนคะแนนที่ขาดเป็นศูนย์ และไม่ถือว่างานล้มเหลวคือ Unknown rejection
10. ตรวจ Response ด้วย Study/Protocol/Case/Output/Reviewer/Rating-unit hash รองรับหลายผู้ประเมิน แต่ปฏิเสธแถวซ้ำ Hash เก่า คะแนน N/A ผิดที่ และคะแนนที่ไม่ครบ
11. คำนวณ Classification แบบรวม Failure/coverage, In-scope accuracy/Macro F1 และ Unknown rejection/false acceptance พร้อมตัวเศษและตัวส่วน
12. คำนวณ Utility หลังรวมคะแนนผู้ประเมินภายในคลิปก่อน มี Paired difference, median, percentile, wins/ties/losses และต้อง adjudicate Critical flags ก่อนสรุป
13. ตรวจหลักฐานอัตโนมัติทั้ง Keyword เดิมและ Actionable advice: แถว Dataset, Topic ID, จำนวนคลิป/ช่อง, Quote/offset, เวลา/ที่มา, Comparison snapshot และข้อห้ามอ้างเหตุเป็นผล
14. ไม่เขียนทับ Artifact เดิม ทุกคำสั่งรับ `--out` ที่ต้องเป็นโฟลเดอร์ใหม่ และ Backend ใช้ `rollback()` โดยไม่มี Production analysis save

## เกณฑ์ที่ตรึงไว้

- Pilot: Phone 3, Camera 3, Laptop 3, Unknown 3 และผู้ประเมินจริงอย่างน้อย 3 คน
- Classification: In-scope accuracy >= 0.80, In-scope macro F1 >= 0.75 และ Unknown false acceptance = 0
- Utility primary: คลิป In-scope ที่ครบอย่างน้อย 6 คลิปและผู้ประเมินครบ 3 คน
- Median Actionability `B-A >= 0.5` และ `C-B >= 0`
- Median ของ C: Evidence correctness >= 4 และ Relevance/Novelty/Clarity >= 4
- Critical flag ที่ยืนยันแล้วต้องเป็น 0; Flag ที่ยังไม่ adjudicate ทำให้ผลยังไม่สมบูรณ์
- A/B ใช้ Evidence score เป็น `N/A`; Missing score ไม่ใช่ 0

เกณฑ์เหล่านี้อยู่ใน Protocol ก่อนรับคะแนน ห้ามแก้ไฟล์/Hash เดิมหลังเห็นผล หากเปลี่ยนต้องสร้าง Study version และโฟลเดอร์ใหม่

## Preflight ฐานจริง

Artifact ล่าสุด: `artifacts/evaluation/recommendation-utility-pending-20260930/preflight-final-v2/`

- พบไฟล์วิดีโอหลายชื่อแต่มีสื่อไม่ซ้ำเพียง 4 คลิป และทั้งหมดเป็น Regression/Historical
- Fresh Phone 0/3, Camera 0/3, Laptop 0/3, Unknown 0/3
- ผู้ประเมินจริง 0/3
- `run-study` ถูกปฏิเสธก่อน ASR เพราะ Manifest ยังไม่พร้อม

คลิปเดิมที่ห้ามนับเป็น Test ใหม่:

| กลุ่ม | SHA-256 |
| --- | --- |
| Review_Phone | `d73f7d0be511be710522bdc0e0b8701617c79087982ce6298edd2f5796b7b0e8` |
| Headphone | `2438d009322506d16e82e222f79634b1151382db917489b4615ae4f2d92a2c46` |
| Keyboard | `5c720288090169844127a75cc8f39b5b1a82254f9be55be4332e577b5efc4fda` |
| Mouse | `9abc881fcd5db6ec2772cfbcd14e3505a91c2f1e51985c720b6eb378a753175d` |

Test Transcript เดิม 17 รายการถูกเพิ่มในทะเบียน Historical overlap ด้วย ไม่สามารถเปลี่ยนชื่อแล้วนำกลับมาเป็น Heldout ใหม่ได้

## คำสั่งเมื่อมีข้อมูลจริง

ใช้ชื่อโฟลเดอร์ใหม่ทุกครั้ง ห้ามใช้ Path ของ Preflight เป็นผล Final

```powershell
python scripts/evaluate_analysis.py inventory --videos videos/phase7-pilot --out artifacts/evaluation/utility-pilot-v1-inventory
```

กรอก Manifest ให้ครบก่อน Prediction: `case_id`, `video_path`, `media_sha256`, `role=heldout`, `source_kind`, `expected_label`, `scenario_kind`, ผู้ตรวจ Gold label/independence, Source identity, `registered_at`, provenance และ consent โดย `scenario_kind` ใช้ค่าที่ Protocol กำหนด และ Phone/Camera/Laptop ต้องมีคลิป `self_recorded` อย่างน้อยหมวดละ 1

```powershell
python scripts/evaluate_analysis.py prepare-study --manifest artifacts/evaluation/utility-pilot-v1-inventory/cases.json --study-id utility-pilot-v1 --reviewers reviewer-01,reviewer-02,reviewer-03 --seed 260930 --out artifacts/evaluation/utility-pilot-v1-protocol
```

ตรวจ `readiness.json` ต้องเป็น `ready_for_prediction` แล้วจึงรัน:

```powershell
python scripts/evaluate_analysis.py run-study --prepared artifacts/evaluation/utility-pilot-v1-protocol --out artifacts/evaluation/utility-pilot-v1-run
```

ให้ผู้ประเมินแต่ละคนเปิดไฟล์ของตนใน `review-packets/<reviewer>.html` และนำ JSON ที่ดาวน์โหลดได้ใส่ `responses/` ห้ามเปิดไฟล์ใน `private/` ให้ผู้ประเมินเห็น

```powershell
python scripts/evaluate_analysis.py report-study --run artifacts/evaluation/utility-pilot-v1-run --responses artifacts/evaluation/utility-pilot-v1-run/responses --out artifacts/evaluation/utility-pilot-v1-report
```

หากมี Critical flags ให้ผู้ตรวจอิสระบันทึก `confirmed` หรือ `dismissed` แล้วเพิ่ม `--adjudications <path>` โดยไม่แก้ Response ต้นฉบับ

## Artifact Contract

- Protocol: `protocol.json`, `protocol.md`, `context.json`, `manifest-audit.json`, `readiness.json`
- Run: `manifest.json`, `cases.json`, `variants.json`, `analysis-audit.json`
- Private: `private/allocation-key.json` หรือไฟล์ Allocation ที่ระบุว่า private
- Review: `review-packets/*.json`, `review-packets/*.html`, `responses/*.json`
- Reports: `classification-report.json`, `evidence-correctness-report.json`, `utility-report.json`, `response-validation.json`, `report.json`, `presentation-summary-th.md`

## ไฟล์สำคัญ

- `app/services/analysis_evaluation.py`: Protocol, Manifest/leakage audit, Variant parity, allocation, response validation และ metrics
- `app/services/recommendation_utility_study.py`: Context lock, blind packet/HTML, actionable evidence audit และรายงานภาษาไทย
- `scripts/evaluate_analysis.py`: `inventory`, `prepare-study`, `run-study`, `report-study` และคำสั่ง Legacy เดิม
- `tests/test_recommendation_utility_evaluation.py`: สัญญา Phase 7 และคำตอบที่คำนวณด้วยมือ
- `tests/test_analysis_evaluation.py`: Regression สัญญา 0/1 ของเครื่องมือเก่า

## การตรวจสอบ

- Phase 7 + Legacy: ผ่าน 25 tests
- Phase 2/3/5 + Phase 7 ที่เกี่ยวข้อง: ผ่าน 55 tests
- Backend ทั้งระบบ: `python -m unittest discover -s tests -p "test_*.py"` ผ่าน 447 tests
- Python compile: ผ่าน
- CLI Preflight กับ Database จริง: ผ่านและรายงานสถานะ Pending ถูกต้อง
- Guard ก่อน Prediction: ผ่าน `run-study` ปฏิเสธ Manifest ที่มีเฉพาะ Regression และไม่มีผู้ประเมิน

รอบเดิมไม่ได้ทดสอบ Flutter/Browser สำหรับ HTML packet ข้อจำกัดนี้ถูกแก้ในรอบตรวจทาน 2026-09-30: Browser flow ผ่านที่ 1,000/1,440 px และ Flutter widgets ที่เกี่ยวข้องผ่าน 21 tests ดู Artifact ที่ `artifacts/browser/utility-review-audit-20260930-v2/`

## งานค้างที่ต้องใช้คนและข้อมูลจริง

1. หาและลงทะเบียนคลิปใหม่ 12 คลิปตามสัดส่วน โดยอย่างน้อยสามหมวด In-scope มีคลิปถ่ายเอง และ Unknown มีทั้งอุปกรณ์เสริมกับเรื่องนอก IT
2. ให้คนที่ไม่ได้ใช้คลิปเหล่านี้ปรับระบบยืนยัน Gold label และความเป็นอิสระก่อน Prediction
3. หาผู้ประเมินจริงอย่างน้อย 3 คนและใช้รหัสไม่เปิดเผยตัวตน
4. รัน Study เพียงหลัง `readiness.json` พร้อม แล้วเก็บ Response ดิบทุกไฟล์
5. Adjudicate Critical flags และสร้าง Final report โดยไม่เลือกทิ้งหมวดหรือกรณีที่ผลไม่ดี

Phase 7 จะเปลี่ยนเป็น `evaluation_complete` ได้หลังงานทั้งห้าข้อนี้ครบเท่านั้น งานโค้ด Phase 7 ไม่มีส่วน Phase 8 และห้ามเริ่ม Phase 8 อัตโนมัติ
