# ข้อตกลงกลาง: Outcome Prediction v1

เอกสารกำหนดการพัฒนา ไม่ใช่สรุปว่าระบบปัจจุบันทำได้แล้ว ต้องอ่านร่วมกับ README และ Phase ที่ได้รับมอบหมาย

## 1. คำถามที่โมเดลตอบ

ชื่อเป้าหมาย: `reference_relative_views_v1`

คำถาม: "ภายใต้บริบทอ้างอิงที่ระบุ เนื้อหาแบบนี้มีโอกาสอยู่ในกลุ่มที่มียอดวิว ณ เวลาสังเกตสูงกว่าค่ากลางของชุดอ้างอิงเท่าไร"

ไม่ใช่:
- ยอดวิวจริงที่จะได้ใน 7 วัน หรือยอดวิวจะเพิ่มกี่เปอร์เซ็นต์
- โอกาสที่การทำตามคำแนะนำจะทำให้คลิปนี้ดีขึ้น
- ความน่าจะเป็นเป็นหมวด Phone/Camera/Laptop
- คะแนนคุณภาพเนื้อหาแบบครอบจักรวาล หรือผลการจัดกลุ่มที่กลายเป็นความน่าจะเป็นเอง

ค่า 60% ถ้าผ่านการตรวจรับ คือค่าประเมินการอยู่ในกลุ่มเป้าหมายภายในประชากรอ้างอิงที่จำกัด ไม่ใช่ 60% ที่ยอดวิวของผู้ใช้จะเพิ่ม ระบบต้องสื่อความหมายนี้ทุกช่องทาง

## 2. หน่วยข้อมูลและเวลา

- 1 ตัวอย่างต่อ Video ID ไม่ใช่ต่อแถว DB/Observation/วลี/ฉบับแปล
- ใช้ Transcript ทั้งคลิปที่ตรวจความครบถ้วนและ Hash ได้ ต้องแยกข้อความสรุปออกจาก Transcript จริง
- เก็บ Dataset ID, Video ID, Channel ID, Label category, Transcript hash, Source URL, Published at, Duration, Format/provenance และ Observation ID/time/version
- เลือก Observation สำเร็จล่าสุด ณ Frozen cutoff โดยไม่เลย cutoff และไม่เกิน Max staleness ที่ Protocol กำหนด ข้อมูลที่ timestamp ผิดหรือสถิติสำคัญขาดให้ตัดพร้อมเหตุผล
- Views=0 ใช้ได้ถ้าเป็น Observation จริง Missing เป็น null ไม่ใช่ 0 Likes/comments ไม่ใช่ตัวแทน Views
- Format ต้องมีหลักฐาน ไม่ถือว่า Duration <= 180 วินาทีคือ Shorts โดยอัตโนมัติ
- อายุคลิป = observed_at - published_at ด้วย UTC และจำนวนวินาทีจริง ไม่ใช้เวลารันปัจจุบันตอนเปิดผลเก่า
- จำนวน Snapshot เพิ่มความละเอียดเวลา ไม่เพิ่ม Independent sample size; Bootstrap/แบ่งชุดต้องเคารพ Channel/Video
- หากนิยาม View metric เปลี่ยน ให้แยก Version ไม่รวมโดยเงียบ ๆ

รุ่นนี้เก็บประวัติเดิมต่อได้ตามสิทธิ์ แต่ไม่สร้าง Day-7 views จากยอดปัจจุบัน / อายุคลิป / เส้นตรงระหว่าง Observation ห่าง ๆ

## 3. ประชากรอ้างอิงและ Label

ใช้ Phone/Camera/Laptop เท่านั้น Outcome Dataset เป็น Manifest บทบาทแยก ไม่ต้องย้ายฐานข้อมูลทั้งหมด

- เลือกคลิปจาก Sampling protocol ที่บันทึกก่อนดูผลโมเดล มีทั้งคลิปทั่วไปและผลตอบรับสูง
- `collection_strategy` บอกเหตุผลการเก็บ ไม่ใช่ Label ว่าคลิปสำเร็จ และไม่ใช่หลักฐานว่าข้อมูลเป็น Random sample
- ข้อมูลที่ตั้งใจเลือกเฉพาะยอดสูงห้ามเป็นประชากร Calibration/Test; ใช้ประกอบคำอธิบายแยกจากชุด Outcome
- ข้อนี้ไม่ได้ห้ามคลิปยอดสูงที่เข้ามาตาม Sampling protocol ปกติ ต้องแยก "ผลจริงสูง" ออกจาก "คัดเข้ามาเพราะรู้ว่าสูง" ไม่ตัดคลิปตามผลเพื่อบังคับ Class balance
- หากใช้ข้อมูลแบบ Convenience sample ให้ระบุผลจำกัดที่ชุดคัดเลือกนี้ ไม่แปลงเป็นโอกาสของ YouTube ทั้งหมด/ช่องผู้ใช้
- คลิปที่ไม่ทราบช่อง รูปแบบ วันเผยแพร่ หรือแหล่งสถิติต้องอยู่ในรายงานขาดข้อมูล ไม่เติมค่าที่เดา
- ไม่กำหนดจำนวนคลิปใหม่แบบเหมารวม ให้ Phase 1 รายงานช่องว่างต่อ Category/Format/Age/Channel/สองระดับผลตอบรับจริง

Benchmark cell เริ่มจาก `category + confirmed_format + age_bucket + view_metric_version`
ช่วงอายุเริ่มต้น: [0,7), [7,30), [30,90), [90,365), [365,+inf) วัน ใช้ขอบเขตเดียวกับระบบหลักฐานเดิมเมื่อเหมาะสม

การเปลี่ยนช่วงอายุ/ลดขอบเขตเพื่อให้ Sample เพียงพอต้องทำใน Phase 1 จาก Coverage ก่อนเปิดผลประเมิน บันทึกเป็น Protocol version ใหม่ ห้ามรวม Shorts/Long หรือรวมหมวดเพื่อให้ค่าดูดี

Benchmark และ Label:
```text
weight_i = 1 / จำนวนคลิปของช่อง i ภายใน Benchmark cell (ชุด Fit เท่านั้น)
median_cell = weighted median ของ views จากชุด Fit ด้วย weight_i
y_i = 1 เมื่อ views_i > median_cell มิฉะนั้น 0
```

Weighted median เลือกค่าสถิติแรกที่น้ำหนักสะสม >= 50% ตามลำดับ views และ tie-break ที่คงที่ เท่ากับ Median ให้ y=0 ไม่สุ่ม ผลจึงไม่จำเป็นต้องมีสองคลาส 50/50

- Fit benchmark จาก Train/Fit partition เท่านั้น Validation/Calibration/Test ใช้ Threshold ที่ Frozen แล้ว
- ใน Cross-validation ต้อง Fit benchmark ใหม่จาก Fit fold พร้อม Preprocessing แล้วจึงสร้าง Label ของ Heldout fold ห้ามเตรียม y ด้วย Train ทั้งก้อนก่อน CV
- บันทึก Benchmark cell ID/threshold/fit IDs/hash ให้ตรวจย้อนกลับได้
- Cell ที่ไม่มีข้อมูลสองคลาสหรือมีช่องน้อยไม่สร้าง "ความน่าจะเป็น" ด้วยความมั่นใจปลอม
- การถ่วงน้ำหนักช่องช่วยไม่ให้ช่องใหญ่ครอบงำ แต่ **ไม่ได้กำจัดอิทธิพลชื่อเสียงช่อง/งบโฆษณา/Thumbnail/เวลาเผยแพร่**
- รุ่นแรกไม่ใช้ยอดติดตามย้อนหลังที่ไม่มีจริง Current subscriber count ไม่ใช่ followers_at_publish

ประชากรเป้าหมายของค่า Probability รุ่นนี้ให้น้ำหนักช่องในกรอบอ้างอิงเท่า ๆ กัน แล้วให้น้ำหนักคลิปภายในช่องเท่า ๆ กัน ไม่ใช่สุ่มจากวิดีโอ YouTube ทั้งหมด Fit, Calibration, Constant prior และ Primary evaluation ต้องใช้ความหมายการถ่วงน้ำหนักเดียวกัน ส่วน Video-weighted เป็นรายงานเสริม

บริบทที่ใช้กับคลิปผู้ใช้เป็น **สถานการณ์อ้างอิง** ไม่ใช่ใส่อายุคลิปผู้ใช้=0 แล้วเทียบคลิปเก่า เลือกบริบทที่มีข้อมูลตามนโยบายล่วงหน้าและ Format ที่ยืนยัน ไม่เลือกบริบทที่ให้เปอร์เซ็นต์สูงสุด หากยังยืนยันบริบทไม่ได้ให้งดค่า Probability

## 4. Split และการไม่ให้ข้อมูลรั่ว

- Split แยกตาม Channel และกลุ่ม Identity ที่เกี่ยวข้อง: Video ID, Creator identity และ Transcript ซ้ำ/ใกล้ซ้ำ กลุ่มเชื่อมถึงกันต้องอยู่ชุดเดียว
- รักษา Protected Validation/Test เดิม ห้ามย้ายมา Train/Reference เพื่อให้ข้อมูลครบ
- ชุดเดิมที่ใช้แก้ระบบแล้วเป็น Development/Regression ไม่เรียก Fresh Test ใหม่
- Outcome Manifest อาจมีบทบาทต่างจากงานจำแนก แต่ต้องไม่ขัดข้อห้ามของชุดเดิม ถ้าจำเป็นต้องเพิ่ม Holdout ให้จองจากข้อมูลใหม่ก่อนใช้ และกันออกจาก Reference eligibility
- การเก็บสถิติให้ Holdout ไม่ได้อนุญาตให้เอา Transcript/Outcome กลับเข้า Train/Reference
- ไม่ใช้ผล Test เลือก Model/Threshold/Features/ข้อความแนะนำ; ทดสอบซ้ำหลังแก้เชิงวิธีถือว่าใช้ Test เพื่อพัฒนาแล้ว
- แยก Fit/Tuning/Calibration/Evaluation ด้วย Channel-aware partitions; ถ้าข้อมูลไม่พอให้ Block ไม่ใช้ CV ปกติที่ Channel รั่ว
- Temporal holdout ให้รายงานแยกเมื่อมีจริง ไม่อ้าง Generalization ข้ามเวลาเพียงเพราะ Split คนละช่อง

## 5. Features และโมเดล

Features v1:
- Boolean การตรวจพบ Canonical topics ใน Transcript จริง ใช้ Catalog/คำพ้อง/Detector เดิมทุกขั้น
- Category, Confirmed format, Duration และบริบท Age bucket ที่ Frozen
- ใช้จำนวน Features เล็กและตรวจได้ ไม่เพิ่ม Text embedding/TF-IDF ขนาดใหญ่ในรุ่นนี้
- ไม่พบกับตรวจไม่ได้แยกกัน หาก Transcript ใช้ประเมินไม่ได้ให้งดทั้งผล ไม่เปลี่ยนทุก Topic เป็น false

ห้ามเป็น Features: Views/Likes/Comments ปัจจุบันของเป้าหมาย, Growth, Rank, High-performance flag, Topic comparison outcome, Test label, Channel/Video ID, URL, Title ที่แอบปะปนเนื้อหา, คะแนนโมเดลจำแนกหมวด

ใช้ Category label ที่ตรวจแล้วในการฝึก Outcome และ Category ที่ผ่าน Acceptance ในงานจริง รายงานแยก Error ของการเลือกหมวดกับ Error ของ Outcome

โมเดล:
1. Constant prior baseline จาก Fit partition
2. Metadata-only Logistic Regression
3. Metadata + Canonical-topic Logistic Regression เป็น Candidate หลัก

ใช้ Pipeline มาตรฐาน sklearn, L2 regularization, Search เล็กที่ล็อกไว้ เช่น C=0.1,1,10, Seed คงที่ ไม่ใช้ class_weight=balanced/oversampling โดยไม่จัดการการเปลี่ยน Prior/Calibration และรายงานให้ตรง

ต้องดูว่าการใส่เนื้อหาช่วยเหนือ Metadata-only หรือไม่ ไม่ใช่แค่เหนือเดาสุ่ม Accuracy 80% ของงานจำแนกหมวดไม่ใช่เกณฑ์ของงานนี้

หาก Calibration: เริ่ม Sigmoid บนข้อมูลที่ไม่ได้ใช้ Fit estimator และไม่ได้ใช้เลือก Hyperparameter นั้น ห้าม Fit calibrator จาก In-sample prediction หรือใช้ Test มาปรับเปอร์เซ็นต์ ไม่เพิ่ม Isotonic บน Sample เล็กเพียงเพราะกราฟดูดี

## 6. Gates และการประเมิน

Phase 1 ต้องเขียน Numeric protocol ก่อน Train: ขั้นต่ำจำนวนคลิป/ช่อง/สองคลาสต่อชุดและขอบเขต, Coverage, Missingness, Support policy, Practical improvement, Calibration tolerance, CI policy และ No-go deadlines

ตัวเลขต้องมีเหตุผลจากขนาดจริง ไม่ใช่ตัดสินว่าพอเพราะ Train รันได้ และไม่แก้ตาม Test ทุกค่าต้องตรวจได้ใน Machine-readable protocol

Metrics:
- Primary: Brier score และส่วนต่างเทียบ Constant/Metadata baseline
- Secondary: Log loss, AUROC/PR-AUC เมื่อมีสองคลาส, Calibration curve พร้อม Bin counts
- แยก Macro/ราย Category และ Coverage ของการงดทำนาย ไม่เฉลี่ยซ่อนหมวดที่ล้มเหลว
- Freeze รายชื่อ Scope และกติกาว่าผ่าน/ไม่ผ่านเป็นราย Scope หรือทั้งรุ่นก่อนเปิด Test ไม่เลือกเฉพาะหมวดที่ผลออกมาสวยแล้วเรียกว่าเป็นขอบเขตตั้งต้น
- ทั้ง Video-weighted และ Channel-balanced โดยประกาศ Primary weighting ให้ตรงประชากรเป้าหมายก่อนดูผล
- Bootstrap เปรียบเทียบแบบ Paired ที่ระดับ Channel แสดงจำนวน Channels และช่วงความไม่แน่นอน; อย่าสุ่มแถว Snapshot
- ค่า Confidence interval ของ Mean/Median หรือ Brier ไม่ใช่ Prediction interval ของยอดวิวคลิปใหม่

ค่าเริ่มต้น Gate ด้านผล: Candidate ต้องดีกว่า Baselines ตาม Practical margin ที่ล็อกไว้บน Validation, Calibration ผ่านตามที่ล็อก, และยืนยันด้วยชุดอิสระ หาก CI ยังไม่สนับสนุนการสรุปหรือข้อมูลน้อย ให้ `experimental` ไม่ใช่ `qualified`

Phase 3 ใช้ Validation เลือก Candidate เท่านั้น; Phase 6 เปิด Independent Test เพื่อรับรอง Candidate ที่ Freeze แล้ว ก่อน Phase 6 ห้ามเปิด Probability ให้ผู้ใช้จริงในฐานะผลที่ตรวจรับแล้ว

## 7. "ทำไมประเด็นนี้จึงน่าลองเพิ่ม"

คำแนะนำแต่ละข้อผูกกับ:
- Topic ID, ช่วงข้อความที่พบ/ไม่พบ/ตรวจไม่ได้, Timestamp เฉพาะที่มีจริง
- Action ที่ทำได้และตัวอย่างประโยคจากแม่แบบเดิม ไม่สั่งพูดคำซ้ำ
- หลักฐาน Transcript อ้างอิง, จำนวนคลิปและช่อง, ขอบเขตกลุ่มเทียบ, สถิติและเวลา, ผลบวก/ลบ/ไม่แน่นอน
- Model assessment เป็นข้อมูลเสริม ไม่ใช้กลบผลหลักฐานที่ไม่สนับสนุน

ลำดับเลือกคำแนะนำใช้ความเกี่ยวข้อง + ทำได้จริง + คุณภาพหลักฐานก่อน เลือก 2-3 ข้อ ไม่เลือกเฉพาะ Topic ที่ทำนายเปอร์เซ็นต์เพิ่มมากสุด

ไม่ใช้ค่า Coefficient เป็นเหตุผลว่า "พูดแล้วทำให้ยอดวิวเพิ่ม" Coefficient เป็นความสัมพันธ์ภายใต้โมเดลและ Features ที่สัมพันธ์กัน อาจเปลี่ยนเครื่องหมายเมื่อ Dataset เปลี่ยน

Scenario (จำลองเพิ่มหัวข้อ) เป็นส่วนรอง:
- ไม่เปิดอัตโนมัติเพียงเพราะมี Model artifact
- ต้องผ่าน Qualification, Context support และมีหลักฐานทั้งกลุ่มพบ/ไม่พบที่เทียบได้ตามนโยบายเดิม
- เปลี่ยนเฉพาะ Feature หัวข้อที่ผู้ใช้เลือกใน Payload จำลอง ไม่แก้ผล Transcript จริง/ไม่ทำเครื่องหมายว่าเพิ่มแล้ว
- แสดง `hypothetical` พร้อมข้อจำกัดว่าไม่มีคลิปแก้ไขจริง ยังไม่ยืนยันว่าปัจจัยอื่นเท่าเดิม
- หากแสดง p_after - p_before เรียกว่า **ส่วนต่างค่าประเมิน (จุดเปอร์เซ็นต์)** ไม่ใช่ %ยอดวิวเพิ่ม/ผลของคำแนะนำ
- ผลอาจบวก ลบ เท่าเดิม หรือประเมินไม่ได้ ไม่มี `max(0, delta)` ไม่มีการบวกโบนัสตายตัว
- การเปิดหลายหัวข้อจนหลุดการกระจายข้อมูลต้องงด ไม่เดาตาม Linear model อย่างเดียว
- ถ้าเวลาไม่พอ/ข้อมูลไม่พอ ให้งด Scenario แต่ต้องรายงานว่าความสามารถนี้ยังไม่ผ่าน ไม่ทำตัวเลข Demo ปะปนของจริง

## 8. Contract ที่บันทึกและ API

เพิ่ม Optional block `outcome_assessment` ใน Result contract ที่มีอยู่ ไม่เปลี่ยนรูป JSON เก่าทั้งก้อน ใช้ชื่อจริงของ Envelope หลังอ่านโค้ด ให้ Migration/Schema เป็น Additive

Field ขั้นต่ำ:
```text
schema_version, status, reason_codes
target_version, protocol_version, feature_version
model_id, artifact_sha256, calibration_version
dataset_manifest_sha256, split_manifest_sha256, reference_cutoff
input_transcript_sha256, context, evaluated_scope
probability (null หากไม่ผ่าน Gate), support_summary
evidence_topic_ids, limitations, assessed_at
```

Status หลัก: `available`, `insufficient_data`, `unsupported_context`, `unassessable_transcript`, `classification_withheld`, `model_unavailable`, `model_unqualified`, `data_use_unverified`, `legacy_not_assessed`, `error`

- `available` ต้องผ่านทุก Gate ไม่ใช้แค่โหลด Artifact ได้
- โครงสร้าง Scenario แยกจากผลวิเคราะห์จริง มี input_hash/selected_topics/context/model version ของตน
- เก็บ Numeric evidence/ข้อความ/IDs/Versions ที่ใช้ ณ ตอนนั้น ไม่ Query Dataset ล่าสุดเพื่อเขียนทับผลเก่าระหว่าง GET
- บันทึกผลใน Transaction ของการ Save วิเคราะห์ตามระบบเดิม บันทึกล้มเหลวห้ามแจ้งสำเร็จ
- Immutable หมายถึงไม่คำนวณทับเงียบ ๆ ระหว่างยังมีสิทธิ์เก็บ ไม่ลบล้างข้อกำหนด Retention/การถอนสิทธิ์ หากหลักฐานต้องถูกถอนให้แสดง Withdrawn ไม่แต่งกลับ
- ผู้ใช้เห็นเฉพาะผลของตน Admin operations ต้องใช้ Role guard เดิม

## 9. ความเข้ากันได้และการเปิดใช้

Outcome model มี Registry/Artifact/Active state คนละหน้าที่กับ Classification model ใช้ Pattern เดิม แต่ห้ามใส่เข้า Dropdown เลือก Classifier

Model lifecycle: draft -> trained -> validation_passed -> independently_evaluated -> qualified -> active; failed/experimental เป็นสถานะจริง ไม่ Shortcut

การ Activate ต้องตรวจบน Backend: สิทธิ์ข้อมูล, Hash/Version, Qualification, Evaluated scope, Schema compatibility และ Atomic single-active ให้ผู้ใช้/Admin อนุมัติจริง พร้อม Rollback/Audit log

Classifier Unknown/expired/unaccepted -> งดคำแนะนำเฉพาะหมวดและ Outcome ตามจริง ไม่ให้ Outcome model ทายหมวดแทน

ผลเก่าไม่มี Block -> legacy_not_assessed ไม่คำนวณย้อนหลังอัตโนมัติ หากขอ Re-analysis ให้สร้าง Revision ใหม่และเก็บต้นฉบับ

เทียบคลิปแก้ไขใช้ Model/Feature/Target/Context เดียวกันหรือแสดงว่าเทียบตรง ๆ ไม่ได้ การพบหัวข้อเพิ่มเป็นการเปลี่ยนเนื้อหา ไม่ใช่หลักฐานยอดวิวเพิ่มหรือปรับคลิปสำเร็จครบแล้ว

