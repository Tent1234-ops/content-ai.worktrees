# อธิบายอัลกอริทึม Outcome Prediction

## คำถามที่ระบบตอบ

ระบบไม่ได้ตอบว่า "ทำตามแล้ววิวจะเพิ่มกี่เปอร์เซ็นต์" แต่ตั้งใจตอบคำถามที่แคบกว่า:

> ภายในกลุ่มอ้างอิงที่กำหนด คลิปนี้มีความน่าจะเป็นเท่าใดที่จะอยู่ในกลุ่มยอดวิวสูงกว่าค่ากลางของข้อมูลฝึก

กลุ่มอ้างอิงต้องตรงกันด้านหมวด เช่น Phone, Camera หรือ Laptop รูปแบบคลิป อายุคลิป และนิยามยอดวิว หากบริบทไม่มีข้อมูลพอ ระบบต้องงดประเมิน

## สอง Label ที่ห้ามสับสน

`Classification label` คือหมวดเนื้อหา เช่น `phone`, `camera`, `laptop` ใช้เลือกกลุ่มอ้างอิงและคำแนะนำที่เกี่ยวข้อง

`Outcome label` คือ 0 หรือ 1 ภายในกลุ่มอ้างอิง:

- `1` เมื่อยอดวิวที่สังเกตได้มากกว่าค่ากลางที่ตรึงจาก Fit partition อย่างเคร่งครัด
- `0` เมื่อยอดวิวต่ำกว่าหรือเท่าค่ากลาง รวมกรณีเสมอ

Classification confidence จึงไม่ใช่โอกาสที่คลิปจะได้ยอดวิวสูง และไม่ใช่คะแนนคุณภาพคำแนะนำ

## บทบาทข้อมูล

| บทบาท | ใช้ทำอะไร | ห้ามใช้ทำอะไร |
|---|---|---|
| Fit | สร้างค่ากลางและฝึก Logistic Regression | ห้ามดู Independent Test |
| Tuning | เลือกค่า `C` และ Candidate | ห้ามปรับตาม Test |
| Calibration | ปรับคะแนนโมเดลให้เป็น Probability ด้วย Sigmoid | ห้ามใช้ In-sample prediction หรือ Test |
| Independent Test | ตรวจ Candidate ที่ Freeze แล้วเพียงรอบเดียว | ห้ามเลือก Feature, Threshold หรือแก้ข้อความ |

การแบ่งชุดทำตามช่องหรือ Creator group เพื่อไม่ให้คลิปจากช่องเดียวกันรั่วข้ามชุด Video ID และ Transcript hash ต้องไม่ซ้ำข้ามชุด

## การสร้าง Target

1. เลือก Snapshot ล่าสุดที่สำเร็จและไม่ใหม่กว่า Cutoff
2. แบ่ง Cell ตาม `taxonomy_leaf_key + confirmed_format + age_bucket + view_metric_version`
3. ใน Fit partition ให้น้ำหนักแต่ละช่องรวมเท่ากัน โดยคลิปในช่องแบ่งน้ำหนักกัน
4. เรียงยอดวิวและหาค่า Weighted median จุดแรกที่น้ำหนักสะสมถึงอย่างน้อย 0.5
5. ตรึง Median ของแต่ละ Cell แล้วใช้ค่าเดิมสร้าง Label ให้ Tuning, Calibration และ Test

ยอดวิวสะสมไม่ใช่อัตราการเติบโตและไม่ใช่ยอดวิวภายใน 7 วัน ถ้าไม่มี Snapshot สองเวลาตามนิยาม จะห้ามเรียกตัวเลขนั้นว่า Growth

## Feature ที่อนุญาต

- การมีหรือไม่มีหัวข้อมาตรฐานใน Transcript แบบ Binary
- หมวดที่ผ่านการตรวจรับ
- รูปแบบคลิปที่ยืนยันแล้ว
- ความยาวคลิป
- ช่วงอายุคลิปที่ Freeze ตาม Cutoff

Feature ต้องไม่ใช้ยอดวิว Likes Comments Growth Trend rank ธงคลิปผลตอบรับสูง Channel ID Video ID URL Title หรือ Classification confidence เพราะข้อมูลเหล่านี้อาจทำให้เป้าหมายรั่วเข้าสู่โมเดล การพูด Keyword ซ้ำหลายครั้งยังคงมีค่า Binary เท่าเดิม จึงไม่มีเหตุผลให้สั่งผู้ใช้พูดคำเดิมบ่อยขึ้น

## โมเดลและ Probability

ระบบเปรียบเทียบสามแบบ:

1. Constant prior เป็น Baseline ง่ายที่สุด
2. Metadata Logistic Regression เป็น Baseline ที่ใช้บริบทแต่ไม่ใช้หัวข้อ
3. Metadata + Topic Logistic Regression เป็น Candidate

Logistic Regression คำนวณคะแนนเชิงเส้น `z = b + w1x1 + ... + wnxn` แล้วแปลงด้วย Sigmoid เป็นค่าระหว่าง 0 ถึง 1 หลังจากนั้นใช้ Calibration partition ปรับคะแนนด้วย Platt/Sigmoid calibration เวอร์ชัน `weighted-platt-sigmoid-v1`

Probability ที่แสดงได้เมื่อผ่านทุก Gate หมายถึงความน่าจะเป็นเชิงโมเดลของการอยู่เหนือ Fit median ในกลุ่มอ้างอิงนี้เท่านั้น ไม่ใช่เปอร์เซ็นต์ยอดวิวที่จะเพิ่ม ไม่ใช่โอกาสไวรัล และไม่ยืนยันความเป็นเหตุเป็นผล

## การประเมิน

Primary metric คือ Brier score หรือค่าเฉลี่ยถ่วงน้ำหนักของ `(p - y)^2` ค่ายิ่งต่ำยิ่งดี เพราะลงโทษทั้งการทายผิดและการมั่นใจเกินจริง Candidate ต้องดีกว่าทุก Baseline ตาม Margin ที่ Freeze ไว้ และช่วงความไม่แน่นอนจาก Paired channel bootstrap ต้องสนับสนุนข้อสรุป

รายงานเสริมใช้ Log loss, AUROC/PR-AUC เมื่อมีสองคลาส, Calibration bins, Coverage และ Abstention โดยแยกตามหมวดและบริบท ไม่เฉลี่ยซ่อนหมวดที่ล้มเหลว

## ทำไมต้องงดประเมิน

ระบบคืน `insufficient_data`, `unsupported_context`, `classification_withheld`, `model_unqualified`, `data_use_unverified` หรือสถานะอื่นแทน Probability เมื่อข้อมูล/สิทธิ์/โมเดลไม่ผ่าน การงดประเมินเป็นผลลัพธ์ที่ถูกต้อง ไม่ใช่ Error และห้ามแทนค่าที่หายด้วย 0

## Scenario หลังเลือกคำแนะนำ

เมื่อโมเดลผ่านการรับรอง ระบบอาจจำลองโดยเปลี่ยนเฉพาะ Feature หัวข้อที่ผู้ใช้เลือก แล้วคำนวณ `p_after - p_before` ค่านี้ต้องเรียกว่า "ส่วนต่างค่าประเมินแบบสมมุติ หน่วยจุดเปอร์เซ็นต์" ไม่ใช่ยอดวิวเพิ่ม และห้ามเปิดหากบริบทหรือหลักฐานกลุ่มพบ/ไม่พบหัวข้อไม่พอ

## เส้นทางในโค้ดและฐานข้อมูล

- `app/routes/analyze.py` เรียก `assess_outcome()` และบันทึก `outcome_assessment` พร้อมผลวิเคราะห์
- `app/services/outcome_inference.py` ตรวจ Active model, Contract, Context และสร้างผลแบบ Fail-closed
- `app/services/outcome_scenarios.py` จำลองหัวข้อที่ผู้ใช้เลือกโดยไม่แก้ Transcript จริง
- `app/routes/contents.py` เปิด `POST /contents/{content_id}/outcome-scenario`
- `app/routes/outcome_model_management.py` เปิด Admin API ใต้ `/admin/outcome-training`
- `app/services/outcome_training.py` สร้าง Baseline, Candidate และ Calibration ตาม Protocol
- `app/services/outcome_final_evaluation.py` ตรวจ Gate และสร้างคำตัดสิน Phase 6
- `dataset_contents` และ `reference_video_statistics` เก็บคลิปอ้างอิงกับสถิติหลายเวลา
- `analysis_results` เก็บ Snapshot ของผลวิเคราะห์และ Outcome ณ เวลาบันทึก
- `outcome_training_runs`, `outcome_models`, `outcome_model_metrics` เก็บงานฝึก Registry และ Metrics
- `clip_revision_plans`, `clip_revision_comparisons` เก็บแผนและผลเทียบฉบับแก้ไข

ผลเก่าที่สร้างก่อน Contract นี้ไม่ถูกคำนวณทับ แต่แสดง `legacy_not_assessed` เพื่อรักษาหลักฐานเดิม
